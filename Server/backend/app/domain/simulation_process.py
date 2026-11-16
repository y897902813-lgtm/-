"""Killable subprocess boundary for long-running background simulation jobs.

The generic JobManager intentionally uses threads and cooperative cancellation.  MuJoCo,
mesh loading and other native calls can hold a worker thread inside C code long enough that
the cooperative flag is not observed.  This module keeps the existing Job contract but runs
the actual simulation in a child process, so cancellation can terminate the native workload.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import sys
import time
import traceback
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .models import ProjectSpec
from .simulation import run_project_simulation

ProgressCallback = Callable[[float, str], None]

# ---------------------------------------------------------------------------
# Windows transient-share atomic replace retry.  Mirrors core.atomic_io so
# this domain module keeps a clean import graph.
# ---------------------------------------------------------------------------
_ATOMIC_REPLACE_MAX_ATTEMPTS = 6
_ATOMIC_REPLACE_BASE_BACKOFF_S = 0.05


def _atomic_replace(src: Path, dst: Path) -> None:
    last_error: BaseException | None = None
    for attempt in range(_ATOMIC_REPLACE_MAX_ATTEMPTS):
        try:
            os.replace(Path(src), Path(dst))
            return
        except PermissionError as exc:
            last_error = exc
            if sys.platform != "win32" or attempt == _ATOMIC_REPLACE_MAX_ATTEMPTS - 1:
                raise
            time.sleep(_ATOMIC_REPLACE_BASE_BACKOFF_S * (attempt + 1))
    if last_error is not None:  # pragma: no cover - defensive guard
        raise last_error


# ---------------------------------------------------------------------------
# Progress watchdog.  10 minutes with no forward progress => consider the
# worker stalled on the Windows atomic-write race / a hung MuJoCo call and
# perform exactly one automatic reload (per user request).  If the restarted
# worker also stalls for another full window, surface a structured error.
# ---------------------------------------------------------------------------
PROGRESS_WATCHDOG_SECONDS = 600  # 10 minutes
_MAX_RELOAD_ATTEMPTS = 1  # "10分钟重载一次" — exactly one auto-restart


class SimulationProcessError(RuntimeError):
    """Simulation worker failed and exposed a structured Job error."""

    def __init__(self, message: str, job_error: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.job_error = dict(job_error or {"code": "simulation_worker_failed", "message": message})


def _atomic_json(path: Path, payload: object) -> None:
    """Atomically write a JSON payload with Windows sharing-violation retry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    staged.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        _atomic_replace(staged, path)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def _worker_environment() -> dict[str, str]:
    env = dict(os.environ)
    backend_root = str(Path(__file__).resolve().parents[2])
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(item for item in (backend_root, current) if item)
    env["PYTHONUNBUFFERED"] = "1"
    # Only the child is limited; never globally rewrite the parent server's
    # BLAS/OpenMP settings. One runaway native process must not monopolize CPU.
    child_threads = str(max(1, min(4, int(os.getenv("MUJOCO_STUDIO_CHILD_THREADS", "1")))))
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = child_threads
    if getattr(sys, "frozen", False):
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def _terminate_worker(process: subprocess.Popen[bytes], *, grace_seconds: float = 0.75) -> None:
    """Terminate the isolated simulation, escalating to a hard kill when necessary."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=max(0.05, float(grace_seconds)))
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        # The OS owns the final reap from here; importantly the Job thread is no longer
        # blocked waiting for cooperative cancellation inside MuJoCo/native code.
        pass


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _launch_simulation_worker(
    command: list[str],
    result_dir: Path,
    log_path: Path,
    creationflags: int,
    popen_kwargs: dict[str, object],
) -> subprocess.Popen[bytes]:
    """Open the log file and start a new worker subprocess."""
    log_handle = log_path.open("ab")  # append so reload attempts don't clobber prior logs
    # Popen owns the handle; it will be closed when the process is reaped via
    # the log_handle going out of scope in the parent.  We intentionally return
    # both via the return tuple so callers can close it explicitly.
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=str(result_dir),
        env=_worker_environment(),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        **popen_kwargs,
    )
    # Stash the handle on the process object so the caller can close it.
    setattr(process, "_log_handle", log_handle)  # noqa: B010
    return process


def _run_project_simulation_without_slot(
    project: ProjectSpec,
    result_dir: Path,
    *,
    variable_overrides: dict[str, float] | None = None,
    progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
    poll_seconds: float = 0.05,
    max_wall_seconds: float | None = None,
) -> dict[str, object]:
    """Run simulation in a killable child while preserving the existing Job callbacks.

    V2.8.15 hardening:
      * An initial ``progress=0.0`` status is written BEFORE the worker starts so the
        UI never sees an indefinitely empty progress bar ("任务已受理，等待后台执行").
      * 10-minute **progress watchdog**: if no progress delta is observed within the
        window, the worker is terminated and automatically restarted **exactly once**
        ("后台计时10分钟，10分钟重载一次").  A second stall raises a structured error.
      * ``error.json`` is polled mid-run so a worker that dies during startup before
        touching result.json still exposes its structured diagnostic promptly.
      * All atomic writes use Windows sharing-violation retry so transient
        ``[WinError 5]`` from AV / Explorer watchers never kills the job.
    """
    result_dir = Path(result_dir).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    control = result_dir / ".simulation_control"
    if control.exists():
        shutil.rmtree(control, ignore_errors=True)
    control.mkdir(parents=True, exist_ok=True)
    request_path = control / "request.json"
    status_path = control / "status.json"
    result_path = control / "result.json"
    error_path = control / "error.json"
    log_path = control / "worker.log"
    request_payload = {
        "project": project.model_dump(mode="json"),
        "result_dir": str(result_dir),
        "variable_overrides": variable_overrides or {},
        "status_path": str(status_path),
        "result_path": str(result_path),
        "error_path": str(error_path),
    }
    _atomic_json(request_path, request_payload)
    # V2.8.15: publish the "queued / accepted" status BEFORE launching the
    # worker so the polling Job thread has a non-empty status to report even
    # if the worker's first report() suffers a transient sharing race on
    # Windows or the worker Python takes time to start importing mujoco.
    _atomic_json(status_path, {
        "progress": 0.0,
        "message": "任务已受理，后台仿真进程启动中…",
        "reloaded": 0,
    })
    if progress is not None:
        progress(0.0, "任务已受理，后台仿真进程启动中…")

    command = [sys.executable or "python", "-m", "app.domain.simulation_process", "--worker", str(request_path)]
    creationflags = 0
    popen_kwargs: dict[str, object] = {}
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    process: subprocess.Popen[bytes] | None = None
    last_status: tuple[float, str] | None = None
    # Watchdog bookkeeping
    reload_count = 0
    last_progress_value = 0.0
    last_progress_monotonic = time.monotonic()
    # Optional hard wall-clock budget for latency-sensitive Viewer bootstrap.
    # Unlike the legacy progress watchdog this includes *all* reload attempts.
    wall_deadline = (last_progress_monotonic + max(0.1, float(max_wall_seconds))) if max_wall_seconds is not None else None

    def _close_log(process: subprocess.Popen[bytes] | None) -> None:
        handle = getattr(process, "_log_handle", None)
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass

    def _drain_process_result(process: subprocess.Popen[bytes]) -> dict[str, object] | None:
        """Check post-exit conditions; return result dict or raise structured error."""
        if process.returncode != 0:
            error = _read_json(error_path) or {
                "code": "simulation_worker_failed",
                "message": f"仿真子进程异常退出 (code {process.returncode})，请查看 worker.log",
            }
            raise SimulationProcessError(str(error.get("message") or "Simulation worker failed"), error)
        result = _read_json(result_path)
        if result is None:
            return None
        if progress is not None:
            progress(1.0, "仿真完成")
        return result

    def _stalled_error() -> SimulationProcessError:
        return SimulationProcessError(
            "仿真进程10分钟无任何进度更新，自动重载一次后仍未恢复；请检查模型约束、行程与机构干涉后重试",
            {
                "code": "simulation_watchdog_stalled",
                "message": "仿真进程10分钟无进度更新，重载一次后仍卡住；请检查模型后重试",
                "hint": "常见原因：闭链约束无解、极长仿真时长、驱动行程反向自锁或 MuJoCo 求解器在首次时间步收敛失败",
                "watchdog_window_seconds": PROGRESS_WATCHDOG_SECONDS,
                "reload_attempts": reload_count,
            },
        )

    try:
        for _lifetime in range(_MAX_RELOAD_ATTEMPTS + 1):  # 1 original run + 1 reload
            process = _launch_simulation_worker(command, result_dir, log_path, creationflags, popen_kwargs)
            worker_died: bool = False
            while process.poll() is None:
                if wall_deadline is not None and time.monotonic() >= wall_deadline:
                    _terminate_worker(process)
                    raise SimulationProcessError(
                        f"Viewer 预计算超过 {max_wall_seconds:g} 秒限制，请先执行后台坐标系仿真后重试",
                        {"code": "viewer_precompute_timeout", "wall_seconds": max_wall_seconds},
                    )
                # Cooperative cancellation (user cancel or Job deadline sweep)
                if should_cancel is not None and should_cancel():
                    _terminate_worker(process)
                    raise InterruptedError("simulation cancelled")

                # Poll status.json for forward progress
                status = _read_json(status_path)
                if status is not None and progress is not None:
                    current_value = float(status.get("progress", 0.0))
                    current_message = str(status.get("message", "仿真进行中"))
                    current = (current_value, current_message)
                    if current != last_status:
                        progress(*current)
                        last_status = current
                    # Watchdog feed: any numerical progress forward resets the clock
                    if current_value > last_progress_value + 1e-6:
                        last_progress_value = current_value
                        last_progress_monotonic = time.monotonic()

                # Early error detection: worker may have written error.json before exiting
                error = _read_json(error_path)
                if error is not None:
                    # Do NOT raise here; wait for process.poll() so we get the
                    # proper exit code and standard exit handling.  Just mark.
                    worker_died = True

                # Progress watchdog check
                if time.monotonic() - last_progress_monotonic >= PROGRESS_WATCHDOG_SECONDS:
                    # 10 minutes without forward progress: treat as stalled
                    _terminate_worker(process)
                    # Drain any last-minute written error/result after kill wait
                    _close_log(process)
                    process = None
                    break

                time.sleep(max(0.01, float(poll_seconds)))

            if process is None:
                # Watchdog fired; attempt one reload exactly
                if reload_count < _MAX_RELOAD_ATTEMPTS:
                    reload_count += 1
                    _atomic_json(status_path, {
                        "progress": last_progress_value,
                        "message": f"检测到10分钟无进度更新，正在第 {reload_count} 次自动重载仿真进程…",
                        "reloaded": reload_count,
                    })
                    if progress is not None:
                        progress(last_progress_value, f"自动重载仿真进程（第 {reload_count} 次）…")
                    # Clear per-run transient output paths so the new worker
                    # does not inherit stale partial error/result.
                    for control_file in (result_path, error_path):
                        try:
                            control_file.unlink(missing_ok=True)
                        except OSError:
                            pass
                    # Rewind the watchdog clock for the fresh worker.
                    last_progress_monotonic = time.monotonic()
                    continue
                # Watchdog fired twice (original + reload both stalled): fail explicitly
                raise _stalled_error()

            # Normal process exit path
            try:
                # Check cancellation first
                if should_cancel is not None and should_cancel():
                    raise InterruptedError("simulation cancelled")

                result = _drain_process_result(process)
                if result is None:
                    # Worker exited 0 but wrote no result.json — treated as stall
                    if reload_count < _MAX_RELOAD_ATTEMPTS:
                        reload_count += 1
                        last_progress_monotonic = time.monotonic()
                        _close_log(process)
                        process = None
                        continue
                    raise SimulationProcessError("仿真子进程正常退出但未生成结果文件，自动重载一次后仍失败")
                _close_log(process)
                process = None
                return result
            except SimulationProcessError:
                _close_log(process)
                process = None
                raise
    finally:
        if process is not None:
            if process.poll() is None:
                _terminate_worker(process)
            _close_log(process)
        # Control files are transient Job state, not result artifacts.
        shutil.rmtree(control, ignore_errors=True)



# V2.16.2 shared per-process pressure gate for coordinate refresh, native
# Viewer bootstrap and Client Bundle precomputation. Keep 2 CPU-heavy MuJoCo
# workers max; busy contenders return a structured retriable error rather than
# consuming *all* JobManager threads indefinitely. No global thread settings
# or extra queues are introduced.
_simulation_cpu_slots = threading.BoundedSemaphore(
    max(1, min(4, int(os.getenv("MUJOCO_STUDIO_SIMULATION_CPU_SLOTS", "2"))))
)


def run_project_simulation_isolated(
    project: ProjectSpec,
    result_dir: Path,
    *,
    variable_overrides: dict[str, float] | None = None,
    progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
    poll_seconds: float = 0.05,
    max_wall_seconds: float | None = None,
) -> dict[str, object]:
    """Run MuJoCo within the existing isolated child, with CPU admission."""
    deadline = time.monotonic() + max(0.0, float(os.getenv("MUJOCO_STUDIO_SIMULATION_SLOT_WAIT", "12")))
    admitted = False
    while time.monotonic() < deadline:
        if should_cancel and should_cancel():
            raise InterruptedError("仿真在等待计算资源时已取消")
        admitted = _simulation_cpu_slots.acquire(timeout=min(0.25, max(0.001, deadline - time.monotonic())))
        if admitted:
            break
    if not admitted:
        raise SimulationProcessError(
            "计算资源繁忙：当前已有其他模型的 MuJoCo 仿真。请稍后重试刷新坐标系。",
            {"code": "simulation_capacity_busy", "message": "MuJoCo CPU slots exhausted", "retryable": True},
        )
    try:
        return _run_project_simulation_without_slot(
            project, result_dir, variable_overrides=variable_overrides,
            progress=progress, should_cancel=should_cancel,
            poll_seconds=poll_seconds, max_wall_seconds=max_wall_seconds,
        )
    finally:
        _simulation_cpu_slots.release()


def _worker(request_path: Path) -> int:
    request = _read_json(request_path)
    if request is None:
        return 2
    status_path = Path(str(request["status_path"]))
    result_path = Path(str(request["result_path"]))
    error_path = Path(str(request["error_path"]))

    def report(value: float, message: str) -> None:
        _atomic_json(status_path, {"progress": min(max(float(value), 0.0), 1.0), "message": str(message)})

    try:
        project = ProjectSpec.model_validate(request["project"])
        result = run_project_simulation(
            project,
            Path(str(request["result_dir"])),
            variable_overrides={str(key): float(value) for key, value in dict(request.get("variable_overrides") or {}).items()},
            progress=report,
        )
        _atomic_json(result_path, result)
        return 0
    except BaseException as exc:  # noqa: BLE001 - subprocess boundary must preserve diagnostics
        structured = getattr(exc, "job_error", None)
        if isinstance(structured, dict):
            error = dict(structured)
            error.setdefault("message", str(exc))
        else:
            error = {"code": "simulation_worker_failed", "message": str(exc)}
        error["worker_traceback"] = traceback.format_exc()
        _atomic_json(error_path, error)
        return 1


def _main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--worker":
        return _worker(Path(argv[1]).resolve())
    print("simulation_process is an internal worker entry point", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
