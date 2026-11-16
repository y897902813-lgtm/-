"""Private Job workspaces and atomic publication helpers."""
from __future__ import annotations

import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Iterable
from uuid import uuid4


# ---------------------------------------------------------------------------
# Windows atomic-replace retry.  Mirrors the behaviour defined in
# ``core.atomic_io.atomic_replace`` so this domain module remains importable
# without a circular dependency on the core package.
# ---------------------------------------------------------------------------
_ATOMIC_REPLACE_MAX_ATTEMPTS = 6
_ATOMIC_REPLACE_BASE_BACKOFF_S = 0.05


def _atomic_replace(src: Path, dst: Path) -> None:
    """Same-directory ``os.replace`` with Windows transient-share retry."""
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


class JobWorkspaceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class JobWorkspaceManager:
    def __init__(self, *, completed_keep: int = 20) -> None:
        self.completed_keep = max(1, int(completed_keep))
        self._lock = RLock()

    @staticmethod
    def _safe_kind(kind: str) -> str:
        value = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in str(kind))
        return value.strip("_") or "job"

    def allocate(self, base: Path, kind: str, job_id: str) -> Path:
        base = Path(base).resolve()
        base.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        stem = f"{self._safe_kind(kind)}_{stamp}_{str(job_id)[:8]}"
        with self._lock:
            for suffix in range(4):
                candidate = base / (stem if suffix == 0 else f"{stem}_{suffix}")
                try:
                    candidate.mkdir(exist_ok=False)
                    return candidate
                except FileExistsError:
                    continue
                except OSError as exc:
                    raise JobWorkspaceError("workspace_create_failed", f"无法创建 Job 私有目录：{exc}") from exc
        raise JobWorkspaceError("workspace_conflict", "Job 私有目录连续发生命名冲突")

    @staticmethod
    def publish_file(staged: Path, destination: Path) -> Path:
        staged = Path(staged).resolve()
        destination = Path(destination).resolve()
        if not staged.is_file():
            raise JobWorkspaceError("artifact_publish_failed", f"待发布文件不存在：{staged}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".{destination.name}.{os.getpid()}.{uuid4().hex}.publish.tmp"
        try:
            shutil.copyfile(staged, temporary)
            _atomic_replace(temporary, destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise JobWorkspaceError("artifact_publish_failed", f"工件原子发布失败：{exc}") from exc
        return destination

    @staticmethod
    def publish_directory(staged: Path, destination: Path) -> Path:
        """Atomically move a staged directory to its published location.

        On Windows directory ``os.replace`` can transiently fail with
        ``[WinError 5]`` while Explorer / antivirus / a file watcher still
        holds a handle on the source tree (common after the simulation
        worker just finished writing hundreds of artifacts).  The bounded
        retry with short backoff resolves the transient share without
        masking genuine permission or lock errors.
        """
        staged = Path(staged).resolve()
        destination = Path(destination).resolve()
        if not staged.is_dir():
            raise JobWorkspaceError("artifact_publish_failed", f"待发布目录不存在：{staged}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise JobWorkspaceError("artifact_publish_failed", f"发布目录已存在：{destination}")
        last_error: BaseException | None = None
        for attempt in range(_ATOMIC_REPLACE_MAX_ATTEMPTS):
            try:
                os.replace(staged, destination)
                return destination
            except PermissionError as exc:
                last_error = exc
                if sys.platform != "win32" or attempt == _ATOMIC_REPLACE_MAX_ATTEMPTS - 1:
                    raise JobWorkspaceError(
                        "artifact_publish_failed",
                        f"结果目录原子发布失败：{exc}",
                    ) from exc
                time.sleep(_ATOMIC_REPLACE_BASE_BACKOFF_S * (attempt + 1))
            except OSError as exc:
                raise JobWorkspaceError("artifact_publish_failed", f"结果目录原子发布失败：{exc}") from exc
        # Defensive: raise the last transient PermissionError if the loop
        # somehow exited without raising.
        if last_error is not None:  # pragma: no cover
            raise JobWorkspaceError(
                "artifact_publish_failed",
                f"结果目录原子发布失败：{last_error}",
            ) from last_error
        return destination  # pragma: no cover

    @staticmethod
    def discard(workspace: Path) -> None:
        workspace = Path(workspace)
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)

    def prune(self, base: Path, *, protected: Iterable[Path] = ()) -> list[Path]:
        base = Path(base).resolve()
        if not base.is_dir():
            return []
        protected_set = {Path(path).resolve() for path in protected}
        with self._lock:
            candidates = sorted(
                (path for path in base.iterdir() if path.is_dir() and path.resolve() not in protected_set),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            removed: list[Path] = []
            for path in candidates[self.completed_keep:]:
                shutil.rmtree(path, ignore_errors=True)
                if not path.exists():
                    removed.append(path)
            return removed
