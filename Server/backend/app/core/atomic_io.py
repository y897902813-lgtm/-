"""Durable atomic file replacement shared by persistence sites."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from ..config import FSYNC_ENABLED

_PathLike = TypeVar("_PathLike", bound=Path)

# Windows sharing-violation / antivirus transient hold-off retry budget.
# POSIX-style atomic rename over an open file is not supported on Windows;
# another thread/process or even the OS AV scanner briefly holding the
# destination handle will surface as PermissionError [WinError 5].
_ATOMIC_REPLACE_MAX_ATTEMPTS = 6
_ATOMIC_REPLACE_BASE_BACKOFF_S = 0.05


def atomic_replace(src: str | Path, dst: str | Path) -> None:
    """``os.replace`` with bounded retry for transient Windows PermissionError.

    On POSIX platforms this is byte-identical to a single ``os.replace`` call.
    On Windows it catches ``PermissionError`` and retries up to
    ``_ATOMIC_REPLACE_MAX_ATTEMPTS`` with linear backoff so a transient
    sharing violation (antivirus, Explorer thumbnails, watchers, concurrent
    readers) does not fail the atomic publish.

    Raises the underlying error verbatim on the final attempt and for every
    non-PermissionError OSError, regardless of platform.
    """
    src_path = Path(src)
    dst_path = Path(dst)
    last_error: BaseException | None = None
    for attempt in range(_ATOMIC_REPLACE_MAX_ATTEMPTS):
        try:
            os.replace(src_path, dst_path)
            return
        except PermissionError as exc:
            last_error = exc
            if sys.platform != "win32" or attempt == _ATOMIC_REPLACE_MAX_ATTEMPTS - 1:
                raise
            # Transient sharing-violation backoff.  Linear growth keeps the
            # total worst-case wait below ~1 s (0.05 + 0.10 + 0.15 + 0.20 + 0.25).
            time.sleep(_ATOMIC_REPLACE_BASE_BACKOFF_S * (attempt + 1))
    if last_error is not None:  # pragma: no cover - defensive guard
        raise last_error


def _temporary_for(path: Path) -> Path:
    """Return a same-directory, process- and write-unique temporary path."""
    path = Path(path)
    return path.parent / f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp"


def _fsync_directory(directory: Path) -> None:
    """Persist a directory entry where the platform supports directory fsync."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(str(directory), flags)
    except (OSError, AttributeError):
        return
    try:
        os.fsync(fd)
    except OSError:
        # Windows and some network filesystems cannot fsync directories.
        pass
    finally:
        os.close(fd)


def atomic_write_text(
    path: Path, text: str, *, encoding: str = "utf-8", mode: int | None = None,
    sync_directory: bool = True,
) -> None:
    """Write text using same-directory temp + fsync + atomic replacement.

    ``sync_directory=False`` is for a caller that is committing several files
    into the same directory and will fsync that directory after the final
    replacement.  File contents are still flushed/fsynced individually.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_for(path)
    try:
        with temporary.open("w", encoding=encoding, newline="\n") as stream:
            stream.write(text)
            stream.flush()
            if FSYNC_ENABLED:
                os.fsync(stream.fileno())
        if mode is not None and os.name != "nt":
            os.chmod(temporary, mode)
        atomic_replace(temporary, path)
        if FSYNC_ENABLED and sync_directory:
            _fsync_directory(path.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_bytes(path: Path, data: bytes, *, sync_directory: bool = True) -> None:
    """Publish original table bytes with the same atomic + Windows retry rules as text."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_for(path)
    try:
        with temporary.open("wb") as stream:
            stream.write(bytes(data))
            stream.flush()
            if FSYNC_ENABLED:
                os.fsync(stream.fileno())
        atomic_replace(temporary, path)
        if FSYNC_ENABLED and sync_directory:
            _fsync_directory(path.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
