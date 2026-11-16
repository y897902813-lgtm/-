"""Thread-safe, bounded registry for server-local Viewer processes."""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


WINDOWS_ACCESS_VIOLATION_CODES = {3221225477, -1073741819}
CLEAN_SHUTDOWN_MARKER = "MUJOCO_STUDIO_VIEWER_CLEAN_SHUTDOWN"


@dataclass
class ViewerRecord:
    process: subprocess.Popen
    launch_id: str
    project_id: str
    actor: str
    workspace: Path
    log_path: Path
    started_at: float
    finished_at: float | None = None
    marker_offset: int = 0
    ready: bool = False
    sampling_done: int = 0
    sampling_total: int = 1
    sampling_points: int = 0


class ViewerRegistry:
    def __init__(self, *, maximum: int = 32, per_actor_running: int = 3,
                 retention_seconds: int = 600) -> None:
        self.maximum = max(1, int(maximum))
        self.per_actor_running = max(1, int(per_actor_running))
        self.retention_seconds = max(30, int(retention_seconds))
        self._items: dict[int, ViewerRecord] = {}
        self._reservations: dict[str, str] = {}
        self._lock = RLock()

    def reserve(self, actor: str) -> str:
        with self._lock:
            self._reap_locked()
            running_for_actor = sum(
                1 for item in self._items.values()
                if item.actor.casefold() == str(actor).casefold() and item.process.poll() is None
            )
            reserved_for_actor = sum(1 for value in self._reservations.values() if value.casefold() == str(actor).casefold())
            if running_for_actor + reserved_for_actor >= self.per_actor_running:
                raise RuntimeError("viewer_limit_reached")
            if len(self._items) + len(self._reservations) >= self.maximum:
                # Finished processes have a diagnostic retention window, not a
                # running-capacity lease. Reclaim oldest finished records when
                # a new request arrives; six closed/crashed sessions must not
                # lock every user out for the next ten minutes.
                finished = sorted(
                    (record for record in self._items.values() if record.process.poll() is not None),
                    key=lambda record: (record.finished_at or record.started_at),
                )
                for record in finished:
                    self._items.pop(record.process.pid, None)
                    if len(self._items) + len(self._reservations) < self.maximum:
                        break
            if len(self._items) + len(self._reservations) >= self.maximum:
                raise RuntimeError("viewer_registry_full")
            token = uuid4().hex
            self._reservations[token] = str(actor)
            return token

    def release(self, reservation: str) -> None:
        with self._lock:
            self._reservations.pop(str(reservation), None)

    def register(self, record: ViewerRecord, *, reservation: str | None = None) -> None:
        with self._lock:
            if reservation is not None:
                expected = self._reservations.pop(str(reservation), None)
                if expected is None or expected.casefold() != record.actor.casefold():
                    raise RuntimeError("viewer_reservation_invalid")
            else:
                # Compatibility for direct callers and tests.
                token = self.reserve(record.actor)
                self._reservations.pop(token, None)
            self._items[record.process.pid] = record

    def record(self, pid: int) -> ViewerRecord | None:
        with self._lock:
            self._reap_locked()
            return self._items.get(int(pid))

    def protected_workspaces(self) -> set[Path]:
        with self._lock:
            return {item.workspace.resolve() for item in self._items.values() if item.process.poll() is None}

    @staticmethod
    def _tail(path: Path) -> str:
        try:
            return "\n".join(path.read_text("utf-8", errors="replace").splitlines()[-80:])
        except OSError:
            return ""

    def _refresh_marker_state(self, record: ViewerRecord) -> None:
        """Consume only newly written Viewer log bytes and retain readiness/progress."""
        try:
            with record.log_path.open("rb") as stream:
                stream.seek(record.marker_offset)
                data = stream.read()
                record.marker_offset = stream.tell()
        except OSError:
            return
        if not data:
            return
        text = data.decode("utf-8", errors="replace")
        if "MUJOCO_STUDIO_VIEWER_READY" in text:
            record.ready = True
        matches = list(re.finditer(r"MUJOCO_STUDIO_SAMPLING_PROGRESS\s+(\d+)/(\d+)\s+(\d+)", text))
        if matches:
            last = matches[-1]
            record.sampling_done = int(last.group(1))
            record.sampling_total = max(1, int(last.group(2)))
            record.sampling_points = int(last.group(3))

    def status(self, pid: int) -> dict[str, Any]:
        record = self.record(pid)
        if record is None:
            return {"pid": int(pid), "tracked": False, "running": False, "exit_code": None,
                    "native_exit_code": None, "recovered_native_close": False,
                    "reason": "未找到该 Viewer 进程的启动记录", "log_tail": "", "launch_id": None}
        native = record.process.poll()
        with self._lock:
            self._refresh_marker_state(record)
        tail = self._tail(record.log_path)
        recovered = native in WINDOWS_ACCESS_VIOLATION_CODES and CLEAN_SHUTDOWN_MARKER in tail
        exit_code = 0 if recovered else native
        if exit_code is None:
            reason = "Viewer 正在运行"
        elif exit_code == 0:
            reason = "Viewer 已正常关闭"
        elif exit_code < 0:
            reason = f"Viewer 被系统信号 {-exit_code} 终止（可能是原生库崩溃）"
        else:
            reason = f"Viewer 异常退出，退出码 {exit_code}"
        if exit_code not in (None, 0) and not tail:
            tail = "子进程未来得及写入 Python 异常，可能是 MuJoCo/OpenGL 原生层退出。"
        return {
            "pid": record.process.pid, "tracked": True, "running": native is None,
            "exit_code": exit_code, "native_exit_code": native, "recovered_native_close": recovered,
            "reason": reason, "log_tail": tail, "launch_id": record.launch_id,
            "project_id": record.project_id, "started_at": record.started_at,
            "ready": bool(record.ready),
            "sampling": {"done": int(record.sampling_done), "total": max(1, int(record.sampling_total)),
                         "points": int(record.sampling_points)},
        }

    def _reap_locked(self) -> None:
        now = time.time()
        for pid, item in list(self._items.items()):
            ended = item.process.poll() is not None
            if ended and item.finished_at is None:
                item.finished_at = now
            if item.finished_at is not None and now - item.finished_at >= self.retention_seconds:
                self._items.pop(pid, None)


# Protect the shared desktop/OpenGL and RAM from dozens of concurrent native
# subprocesses. The class remains parameterized for existing tests/callers.
VIEWER_REGISTRY = ViewerRegistry(maximum=6, per_actor_running=2)
