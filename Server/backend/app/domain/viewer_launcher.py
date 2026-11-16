"""Generate current project files and launch the native viewer subprocess."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .models import ProjectSpec
from .viewer_registry import VIEWER_REGISTRY, ViewerRecord
from .xml_generator import generate_project
from .simulation_process import run_project_simulation_isolated


class ViewerLaunchError(RuntimeError):
    pass


def viewer_process_status(pid: int) -> dict[str, Any]:
    return VIEWER_REGISTRY.status(pid)


def _viewer_argument_path(value: str | Path, working_dir: str | Path | None) -> str:
    """Prefer a cwd-relative subprocess argument without assuming one filesystem anchor."""
    target = Path(value).resolve()
    if working_dir is None:
        return str(target)
    base = Path(working_dir).resolve()
    try:
        return os.path.relpath(target, base)
    except ValueError:
        # Windows can raise when target/base are on different drives.  Preserve
        # the absolute fallback for that exceptional deployment instead of
        # manufacturing an invalid path.
        return str(target)


def viewer_command(
    scene_path: str | Path, drives_path: str | Path, *, loop: bool, speed: float,
    gantt_cache_dir: str | Path | None = None, trajectory_path: str | Path | None = None,
    working_dir: str | Path | None = None,
) -> list[str]:
    interpreter = shutil.which("mjpython") if sys.platform == "darwin" else None
    command = [
        interpreter or sys.executable or "python", "-m", "app.domain.viewer_runner",
        _viewer_argument_path(scene_path, working_dir),
        _viewer_argument_path(drives_path, working_dir),
        "--speed", f"{float(speed):.12g}",
    ]
    if gantt_cache_dir is not None:
        command.extend(("--gantt-cache-dir", _viewer_argument_path(gantt_cache_dir, working_dir)))
    if trajectory_path is not None:
        command.extend(("--trajectory", _viewer_argument_path(trajectory_path, working_dir)))
    if loop:
        command.append("--loop")
    return command


def viewer_environment(*, project_json: str | Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    backend_root = str(Path(__file__).resolve().parents[2])
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(item for item in (backend_root, current) if item)
    env["MUJOCO_STUDIO_VIEWER_MODE"] = "1"
    if project_json is not None:
        env["MUJOCO_STUDIO_VIEWER_PROJECT_JSON"] = str(Path(project_json).resolve())
    else:
        env.pop("MUJOCO_STUDIO_VIEWER_PROJECT_JSON", None)
    env["PYTHONUNBUFFERED"] = "1"
    child_threads = str(max(1, min(4, int(os.getenv("MUJOCO_STUDIO_CHILD_THREADS", "1")))))
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = child_threads
    if getattr(sys, "frozen", False):
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def launch_project_viewer(
    project: ProjectSpec, project_dir: str | Path, *, check_files: bool = True,
    loop: bool = False, speed: float = 1.0, actor: str = "system",
    trajectory_path: str | Path | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if importlib.util.find_spec("mujoco") is None:
        raise ViewerLaunchError('MuJoCo 未安装。请先执行 pip install ".[simulation]"。')
    try:
        reservation = VIEWER_REGISTRY.reserve(actor)
    except RuntimeError as exc:
        raise ViewerLaunchError(str(exc)) from exc
    launch_id = uuid4().hex
    viewer_root = Path(project_dir).resolve() / "outputs" / "viewer"
    output_dir = viewer_root / launch_id
    try:
        generated = generate_project(project, output_dir, check_files=check_files)
        runtime = ProjectSpec.model_validate(project.model_dump())
        runtime.simulation.engine = "mujoco"
        # The browser just ran /simulate. Reuse that *fingerprint-verified*
        # trajectory instead of solving the same model a second time. For
        # direct/legacy callers without a current result, keep the native
        # calculation killable in the existing isolated simulation worker.
        reused_trajectory = Path(trajectory_path).resolve() if trajectory_path else None
        if reused_trajectory is not None and reused_trajectory.is_file():
            trajectory = reused_trajectory
        else:
            simulation = run_project_simulation_isolated(
                runtime, output_dir / "simulation", should_cancel=should_cancel,
                max_wall_seconds=240,
            )
            trajectory = Path(str(simulation.get("artifacts", {}).get("trajectory", "")))
            if not trajectory.is_file():
                raise ValueError("Viewer trajectory.npz 未生成")
    except Exception as exc:  # noqa: BLE001
        VIEWER_REGISTRY.release(reservation)
        raise ViewerLaunchError(f"Viewer 文件生成失败: {exc}") from exc
    log_path = output_dir / "viewer.log"
    gantt_cache_dir = Path(project_dir).resolve() / "core" / "artifacts" / "gantt_cache"
    command = viewer_command(
        generated["scene"], generated["drives"], loop=loop, speed=speed,
        gantt_cache_dir=gantt_cache_dir, trajectory_path=trajectory, working_dir=output_dir,
    )
    creationflags = 0
    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    try:
        # Each PID must be judged only by its own shutdown marker.  Reusing an
        # older appended marker could hide a genuine crash in a later process.
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(  # noqa: S603
                command, cwd=str(output_dir),
                env=viewer_environment(project_json=Path(project_dir) / "project.json"), stdout=log,
                stderr=subprocess.STDOUT, creationflags=creationflags, **popen_kwargs,
            )
    except OSError as exc:
        VIEWER_REGISTRY.release(reservation)
        raise ViewerLaunchError(f"Viewer 子进程启动失败: {exc}") from exc
    try:
        VIEWER_REGISTRY.register(ViewerRecord(
            process=process, launch_id=launch_id, project_id=project.id, actor=str(actor),
            workspace=output_dir, log_path=log_path, started_at=time.time(),
        ), reservation=reservation)
    except RuntimeError as exc:
        VIEWER_REGISTRY.release(reservation)
        process.terminate()
        raise ViewerLaunchError(str(exc)) from exc
    protected = VIEWER_REGISTRY.protected_workspaces()
    old_directories = sorted(
        (path for path in viewer_root.iterdir() if path.is_dir() and path.resolve() not in protected),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    keep_completed = max(0, 3 - len(protected))
    for stale in old_directories[keep_completed:]:
        shutil.rmtree(stale, ignore_errors=True)
    return {
        "status": "launched", "pid": process.pid, "scene": generated["scene"],
        "drives": generated["drives"], "log": str(log_path), "loop": loop,
        "playback_speed": speed, "launch_id": launch_id,
    }
