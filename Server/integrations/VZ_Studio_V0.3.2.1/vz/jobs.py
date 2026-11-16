from __future__ import annotations

import threading
import time
from copy import deepcopy
from typing import Any, Callable

from .models import new_id


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def start(self, kind: str, target: Callable[[str, Callable[[float, str], None]], dict[str, Any]]) -> str:
        job_id = new_id("job")
        now = time.time()
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id, "kind": kind, "status": "queued", "progress": 0.0,
                "message": "任务已提交", "created_at": now, "updated_at": now,
                "result": None, "error": None,
            }

        def report(fraction: float, message: str) -> None:
            with self._lock:
                job = self._jobs[job_id]
                job["progress"] = max(0.0, min(1.0, float(fraction)))
                job["message"] = str(message)
                job["updated_at"] = time.time()

        def runner() -> None:
            with self._lock:
                self._jobs[job_id]["status"] = "running"
                self._jobs[job_id]["updated_at"] = time.time()
            try:
                result = target(job_id, report)
                with self._lock:
                    job = self._jobs[job_id]
                    job.update({"status": "completed", "progress": 1.0, "message": "任务已完成", "result": result, "updated_at": time.time()})
            except Exception as exc:
                with self._lock:
                    job = self._jobs[job_id]
                    job.update({"status": "failed", "message": str(exc), "error": {"message": str(exc), "type": type(exc).__name__}, "updated_at": time.time()})

        threading.Thread(target=runner, name=f"vz-{kind}-{job_id}", daemon=True).start()
        return job_id

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return deepcopy(self._jobs[job_id])
