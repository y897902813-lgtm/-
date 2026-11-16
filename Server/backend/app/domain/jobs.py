from __future__ import annotations

import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4


TERMINAL_STATUSES = {"completed", "cancelled", "failed", "timed_out"}
# Work kinds that execute native MuJoCo/mesh calculations or long export work.
# This is deliberately a single policy owned by the existing JobManager.
HEAVY_JOB_KINDS = frozenset({
    "simulation", "native_viewer_launch", "web_viewer_export",
    "animation_html_export", "lab_animation_export", "quick_optimization", "optimization", "delivery_refresh",
})


class JobLimitError(RuntimeError):
    pass


class JobManager:
    """Bounded in-process jobs with cooperative cancellation and deadlines.

    Python cannot safely terminate a native worker thread.  A timed-out running
    task is therefore asked to stop first; after ``cancel_grace_seconds`` its
    public state is sealed as ``timed_out``.  Any late return is ignored by the
    terminal-state guard, so an unresponsive task can never overwrite timeout.
    """

    def __init__(
        self,
        max_workers: int = 4,
        *,
        max_records: int = 200,
        retention_seconds: int = 1800,
        max_per_user: int = 4,
        default_timeout_seconds: float = 900,
        cancel_grace_seconds: float = 5,
        sweep_interval_seconds: float = 0.25,
    ):
        # Keep CPU-intensive MuJoCo/geometry work out of the responsive job lane.
        # The two executors share the configured global worker budget (except
        # max_workers=1, where one slot is reserved for each class).  Do not
        # create a second JobManager or change job IDs/status/cancellation.
        self.heavy_workers = max(1, min(2, int(max_workers) // 2))
        self.light_workers = max(1, int(max_workers) - self.heavy_workers)
        self._executor = ThreadPoolExecutor(max_workers=self.light_workers, thread_name_prefix="mujoco-studio-light")
        self._heavy_executor = ThreadPoolExecutor(max_workers=self.heavy_workers, thread_name_prefix="mujoco-studio-heavy")
        self.max_records = max(10, int(max_records))
        self.retention_seconds = max(60, int(retention_seconds))
        self.max_per_user = max(1, int(max_per_user))
        self.default_timeout_seconds = max(0.01, float(default_timeout_seconds))
        self.cancel_grace_seconds = max(0.0, float(cancel_grace_seconds))
        self.sweep_interval_seconds = max(0.01, float(sweep_interval_seconds))
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._deadlines: dict[str, float] = {}
        self._timeout_requested_at: dict[str, float] = {}
        self._finished_at: dict[str, float] = {}
        self._stop_event = threading.Event()
        self._sweeper = threading.Thread(target=self._sweep_loop, name="mujoco-studio-job-sweeper", daemon=True)
        self._sweeper.start()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _remove_locked(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)
        self._cancel_events.pop(job_id, None)
        self._deadlines.pop(job_id, None)
        self._timeout_requested_at.pop(job_id, None)
        self._finished_at.pop(job_id, None)

    def _prune_locked(self, now: float | None = None) -> None:
        current = time.monotonic() if now is None else float(now)
        expired = [
            job_id for job_id, finished in self._finished_at.items()
            if current - finished >= self.retention_seconds
        ]
        for job_id in expired:
            self._remove_locked(job_id)
        if len(self._jobs) <= self.max_records:
            return
        terminal = sorted(
            (job_id for job_id, job in self._jobs.items() if job["status"] in TERMINAL_STATUSES),
            key=lambda job_id: self._finished_at.get(job_id, float("inf")),
        )
        while len(self._jobs) > self.max_records and terminal:
            self._remove_locked(terminal.pop(0))

    def _seal_locked(
        self,
        job_id: str,
        status: str,
        *,
        message: str,
        result: Any = None,
        error: Any = None,
    ) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job["status"] in TERMINAL_STATUSES:
            return False
        job.update({"status": status, "message": message, "result": result, "error": error})
        if status == "completed":
            job["progress"] = 1.0
        job["updated_at"] = self._now_iso()
        self._finished_at[job_id] = time.monotonic()
        return True

    def _request_timeout_locked(self, job_id: str, now: float) -> None:
        job = self._jobs.get(job_id)
        if job is None or job["status"] in TERMINAL_STATUSES:
            return
        event = self._cancel_events.get(job_id)
        if event is not None:
            event.set()
        if job["status"] == "queued":
            self._seal_locked(
                job_id,
                "timed_out",
                message="Job timed out before execution",
                error={"code": "job_timeout", "message": "Job exceeded its execution deadline while queued"},
            )
            return
        requested = self._timeout_requested_at.setdefault(job_id, now)
        job["message"] = "Timeout reached; cancellation requested"
        job["updated_at"] = self._now_iso()
        if now - requested >= self.cancel_grace_seconds:
            self._seal_locked(
                job_id,
                "timed_out",
                message="Job timed out",
                error={
                    "code": "job_unresponsive_to_cancel",
                    "message": "Job did not stop within the cancellation grace period",
                },
            )

    def _sweep_once(self) -> None:
        now = time.monotonic()
        with self._lock:
            for job_id, deadline in list(self._deadlines.items()):
                if now >= deadline:
                    self._request_timeout_locked(job_id, now)
            self._prune_locked(now)

    def _sweep_loop(self) -> None:
        while not self._stop_event.wait(self.sweep_interval_seconds):
            self._sweep_once()

    def prune(self) -> None:
        with self._lock:
            self._prune_locked()

    def close(self, *, wait: bool = False) -> None:
        self._stop_event.set()
        self._executor.shutdown(wait=wait, cancel_futures=True)
        self._heavy_executor.shutdown(wait=wait, cancel_futures=True)

    def submit(
        self,
        kind: str,
        task: Callable[[Callable[[float, str], None], Callable[[], bool]], Any],
        *,
        project_id: str,
        owner: str,
        owner_lease_id: str,
        job_id: str | None = None,
        workspace: str | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        job_id = str(job_id or uuid4().hex)
        cancel_event = threading.Event()
        created_at = datetime.now(timezone.utc)
        timeout = self.default_timeout_seconds if timeout_seconds is None else max(0.01, float(timeout_seconds))
        deadline_at = created_at + timedelta(seconds=timeout)
        # Limit by *account*, not browser login lease. One person opening several
        # sessions must not fill the global worker pool and starve other users.
        # The per-session lease ID remains attached for ownership/cancellation.
        owner_key = str(owner).casefold()
        with self._lock:
            self._prune_locked()
            if job_id in self._jobs:
                raise ValueError(f"Job id already exists: {job_id}")
            active_for_owner = sum(
                1 for item in self._jobs.values()
                if item["status"] not in TERMINAL_STATUSES
                and str(item["owner"]).casefold() == owner_key
            )
            if active_for_owner >= self.max_per_user:
                raise JobLimitError(f"当前用户并发 Job 已达上限 {self.max_per_user}")
            if len(self._jobs) >= self.max_records:
                terminal = sorted(
                    (job_key for job_key, item in self._jobs.items() if item["status"] in TERMINAL_STATUSES),
                    key=lambda job_key: self._finished_at.get(job_key, float("inf")),
                )
                if terminal:
                    self._remove_locked(terminal[0])
                else:
                    raise JobLimitError(f"Job 记录已达上限 {self.max_records}，请稍后重试")
            self._cancel_events[job_id] = cancel_event
            self._deadlines[job_id] = time.monotonic() + timeout
            now_iso = created_at.isoformat()
            self._jobs[job_id] = {
                "id": job_id,
                "kind": str(kind),
                "project_id": str(project_id),
                "owner": str(owner),
                "owner_lease_id": str(owner_lease_id),
                "status": "queued",
                "progress": 0.0,
                "message": "Queued",
                "created_at": now_iso,
                "updated_at": now_iso,
                "deadline_at": deadline_at.isoformat(),
                "cancel_requested_at": None,
                "workspace": str(workspace) if workspace else None,
                "result": None,
                "error": None,
            }

        def update(progress: float, message: str) -> None:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job["status"] in TERMINAL_STATUSES:
                    return
                job["progress"] = min(max(float(progress), 0.0), 1.0)
                job["message"] = str(message)
                job["updated_at"] = self._now_iso()

        def finish(status: str, *, message: str, result: Any = None, error: Any = None) -> None:
            with self._lock:
                self._seal_locked(job_id, status, message=message, result=result, error=error)
                self._prune_locked()

        def runner() -> None:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job["status"] in TERMINAL_STATUSES or cancel_event.is_set():
                    return
                job["status"] = "running"
                job["message"] = "Running"
                job["updated_at"] = self._now_iso()
            try:
                result = task(update, cancel_event.is_set)
                if cancel_event.is_set():
                    raise InterruptedError("Cancellation requested")
                finish("completed", message="Completed", result=result)
            except InterruptedError as exc:
                with self._lock:
                    timed_out = job_id in self._timeout_requested_at
                if timed_out:
                    finish(
                        "timed_out",
                        message="Job timed out",
                        error={"code": "job_timeout", "message": str(exc) or "Job exceeded its execution deadline"},
                    )
                else:
                    finish("cancelled", message=str(exc) or "Cancelled")
            except Exception as exc:  # noqa: BLE001 - job boundary must capture failures
                with self._lock:
                    timed_out = job_id in self._timeout_requested_at
                if timed_out:
                    error = {
                        "code": "job_timeout",
                        "message": str(exc),
                        "hint": "查看管理员诊断日志以获取完整 traceback",
                        "traceback": traceback.format_exc(),
                    }
                else:
                    structured = getattr(exc, "job_error", None)
                    if isinstance(structured, dict):
                        error = dict(structured)
                        error.setdefault("message", str(exc))
                        error.setdefault("hint", "查看管理员诊断日志以获取完整 traceback")
                        error["traceback"] = traceback.format_exc()
                    else:
                        error = {
                            "code": "job_failed",
                            "message": str(exc),
                            "hint": "查看管理员诊断日志以获取完整 traceback",
                            "traceback": traceback.format_exc(),
                        }
                finish(
                    "timed_out" if timed_out else "failed",
                    message="Job timed out" if timed_out else str(error.get("message", str(exc))),
                    error=error,
                )

        executor = self._heavy_executor if kind in HEAVY_JOB_KINDS or kind.startswith(("distance_curve:", "baseline_fork:")) else self._executor
        try:
            executor.submit(runner)
        except RuntimeError:
            # A shutdown race must not leave a permanently queued Job record.
            with self._lock:
                self._remove_locked(job_id)
            raise
        return job_id

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            self._prune_locked()
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return dict(self._jobs[job_id])

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            self._prune_locked()
            jobs = sorted(self._jobs.values(), key=lambda item: item["created_at"], reverse=True)
            return [dict(item) for item in jobs[:limit]]

    def has_active(self, *, project_id: str, owner_lease_id: str | None = None) -> bool:
        """Return whether a project still owns queued/running work.

        Lease convergence uses this read-only projection so a long simulation
        cannot be invalidated by an idle or browser-close check-in.
        """
        with self._lock:
            self._prune_locked()
            return any(
                item["status"] not in TERMINAL_STATUSES
                and str(item.get("project_id", "")) == str(project_id)
                and (owner_lease_id is None or str(item.get("owner_lease_id", "")) == str(owner_lease_id))
                for item in self._jobs.values()
            )

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            self._prune_locked()
            if job_id not in self._jobs:
                raise KeyError(job_id)
            job = self._jobs[job_id]
            if job["status"] in TERMINAL_STATUSES:
                return dict(job)
            self._cancel_events[job_id].set()
            now_iso = self._now_iso()
            job["cancel_requested_at"] = now_iso
            if job["status"] == "queued":
                self._seal_locked(job_id, "cancelled", message="Cancelled before execution")
            else:
                job["message"] = "Cancellation requested"
                job["updated_at"] = now_iso
            return dict(job)
