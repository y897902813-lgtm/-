"""Bounded, observable registry for native Viewer child processes."""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


WINDOWS_ACCESS_VIOLATION_CODES = {3221225477, -1073741819}
CLEAN_SHUTDOWN_MARKER = "MUJOCO_STUDIO_VIEWER_CLEAN_SHUTDOWN"


@dataclass
class ViewerRecord:
    pid: int
    launch_id: str
    project_id: str
    started_at: float
    log_path: Path
    bundle_dir: Path
    process: subprocess.Popen
    ready: bool = False
    sampling_done: int = 0
    sampling_total: int = 1
    sampling_points: int = 0


class ViewerRegistry:
    def __init__(self, log_root: Path, *, running_limit: int = 3, history_limit: int = 20,
                 retention_seconds: int = 7 * 86400, log_max_bytes: int = 8 * 1024 * 1024) -> None:
        self.log_root = Path(log_root)
        self.running_limit = max(1, int(running_limit))
        self.history_limit = max(self.running_limit, int(history_limit))
        self.retention_seconds = max(60, int(retention_seconds))
        self.log_max_bytes = max(1024, int(log_max_bytes))
        self._items: dict[int, ViewerRecord] = {}
        self._lock = threading.RLock()
        self._prune_log_files()

    def _prune_log_files(self) -> None:
        if not self.log_root.is_dir():
            return
        now = time.time()
        protected = {item.log_path.resolve() for item in self._items.values() if item.process.poll() is None}
        files = sorted(self.log_root.glob("viewer_*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
        for index, path in enumerate(files):
            if path.resolve() in protected:
                continue
            if index >= self.history_limit or now - path.stat().st_mtime > self.retention_seconds:
                path.unlink(missing_ok=True)

    def launch(self, command: list[str], *, project_id: str, bundle_dir: Path,
               cwd: Path, env: dict[str, str]) -> ViewerRecord:
        with self._lock:
            self._prune_locked()
            running = [item for item in self._items.values() if item.process.poll() is None]
            if len(running) >= self.running_limit:
                raise RuntimeError("viewer_limit_reached")
            launch_id = uuid4().hex
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
            kwargs: dict[str, Any] = {"start_new_session": True} if os.name != "nt" else {}
            try:
                process = subprocess.Popen(
                    command, cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    creationflags=creationflags, **kwargs,
                )
            except OSError as exc:
                raise RuntimeError(f"popen_failed: {exc}") from exc
            self.log_root.mkdir(parents=True, exist_ok=True)
            log_path = self.log_root / f"viewer_{process.pid}_{launch_id}.log"
            record = ViewerRecord(
                pid=process.pid, launch_id=launch_id, project_id=str(project_id), started_at=time.time(),
                log_path=log_path, bundle_dir=Path(bundle_dir), process=process,
            )
            self._items[record.pid] = record
        threading.Thread(target=self._pump_output, args=(record,), daemon=True,
                         name=f"viewer-log-{record.pid}").start()
        return record

    def _pump_output(self, record: ViewerRecord) -> None:
        written = 0
        truncated = False
        stream = record.process.stdout
        if stream is None:
            return
        with record.log_path.open("wb") as log:
            # READY/progress markers are short newline-terminated records. A fixed
            # 64 KiB read can wait for EOF while the Viewer is still open, making
            # the Web loading dialog appear stuck. Read one line at a time instead.
            while chunk := stream.readline():
                text = chunk.decode("utf-8", errors="replace")
                with self._lock:
                    if "MUJOCO_STUDIO_VIEWER_READY" in text:
                        record.ready = True
                    match = re.search(r"MUJOCO_STUDIO_SAMPLING_PROGRESS\s+(\d+)/(\d+)\s+(\d+)", text)
                    if match:
                        record.sampling_done = int(match.group(1))
                        record.sampling_total = max(1, int(match.group(2)))
                        record.sampling_points = int(match.group(3))
                remaining = self.log_max_bytes - written
                if remaining > 0:
                    data = chunk[:remaining]
                    log.write(data)
                    log.flush()
                    written += len(data)
                if len(chunk) > max(remaining, 0):
                    truncated = True
            if truncated:
                log.write("\n[MUJOCO_STUDIO_LOG_TRUNCATED]\n".encode("utf-8"))

    @staticmethod
    def _tail(path: Path, lines: int = 80) -> str:
        try:
            return "\n".join(path.read_text("utf-8", errors="replace").splitlines()[-lines:])
        except OSError:
            return ""

    def status(self, pid: int) -> dict[str, Any]:
        with self._lock:
            record = self._items.get(int(pid))
        if record is None:
            return {"pid": int(pid), "tracked": False, "running": False, "exit_code": None,
                    "native_exit_code": None, "recovered_native_close": False,
                    "reason": "未找到该 Viewer 进程的启动记录", "log_tail": "", "launch_id": None}
        native = record.process.poll()
        tail = self._tail(record.log_path)
        recovered = native in WINDOWS_ACCESS_VIOLATION_CODES and CLEAN_SHUTDOWN_MARKER in tail
        exit_code = 0 if recovered else native
        if exit_code is None:
            reason = "Viewer 正在运行"
        elif exit_code == 0:
            reason = "Viewer 已正常关闭"
        elif "无法读取 Viewer XML" in tail or "No such file" in tail or "FileNotFoundError" in tail:
            reason = "xml_open_failed"
        elif "ParseXML" in tail or "XML Error" in tail or "mujoco.FatalError" in tail:
            reason = "mujoco_parse_failed"
        elif "GLFW" in tail or "OpenGL" in tail:
            reason = "opengl_window_failed"
        else:
            reason = "native_crash"
            if not tail:
                tail = "子进程未来得及写入 Python 异常，可能是 MuJoCo/OpenGL 原生层退出。"
        return {
            "pid": record.pid, "tracked": True, "running": native is None, "exit_code": exit_code,
            "native_exit_code": native, "recovered_native_close": recovered, "reason": reason,
            "log_tail": tail, "launch_id": record.launch_id, "project_id": record.project_id,
            "started_at": record.started_at, "ready": bool(record.ready),
            "sampling": {"done": int(record.sampling_done), "total": max(1, int(record.sampling_total)),
                         "points": int(record.sampling_points)},
        }

    def protected_bundles(self) -> set[Path]:
        """Return bundle directories still owned by Viewer children in this process."""
        with self._lock:
            return {item.bundle_dir.resolve() for item in self._items.values() if item.process.poll() is None}

    def terminate(self, pid: int) -> bool:
        with self._lock:
            record = self._items.get(int(pid))
        if record is None:
            return False
        if record.process.poll() is None:
            record.process.terminate()
        return True

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            self._prune_locked()
            records = sorted(self._items.values(), key=lambda item: item.started_at, reverse=True)
        return [{
            "pid": item.pid, "launch_id": item.launch_id, "running": item.process.poll() is None,
            "started_at": item.started_at, "project_id": item.project_id,
        } for item in records]

    def _prune_locked(self) -> None:
        now = time.time()
        records = sorted(self._items.values(), key=lambda item: item.started_at, reverse=True)
        keep: set[int] = set()
        for index, item in enumerate(records):
            running = item.process.poll() is None
            if running or (index < self.history_limit and now - item.started_at <= self.retention_seconds):
                keep.add(item.pid)
        for pid, item in list(self._items.items()):
            if pid not in keep:
                self._items.pop(pid, None)
                item.log_path.unlink(missing_ok=True)
        self._prune_log_files()
