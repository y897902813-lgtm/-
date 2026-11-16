"""Bounded frame preparation; physical trajectory integration stays sequential."""
from __future__ import annotations

import os
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any, Callable, Iterator

FRAME_BATCH_SIZE = 50
MAX_FRAME_WORKERS = 5


def frame_worker_count(
    frame_count: int, workers: int = MAX_FRAME_WORKERS, *, batch_size: int = FRAME_BATCH_SIZE,
) -> int:
    if batch_size < 1:
        raise ValueError("frame batch size must be positive")
    batches = max(1, (frame_count + batch_size - 1) // batch_size)
    return min(MAX_FRAME_WORKERS, max(1, workers), max(1, os.cpu_count() or 1), batches)


def iter_frame_batches(
    frame_count: int, sample: Callable[[int, int, Callable[[], bool]], Any], *,
    should_cancel: Callable[[], bool] | None = None, workers: int = MAX_FRAME_WORKERS,
    batch_size: int = FRAME_BATCH_SIZE, cancel_message: str = "动画 HTML 导出已取消",
    thread_name_prefix: str = "html-frames",
) -> Iterator[tuple[int, int, Any]]:
    """Yield finished batches, keeping at most one pending batch per worker.

    Results carry their original indexes: completion order never defines frame
    order. Callbacks/progress/publication remain on the consuming thread.
    """
    stopped = threading.Event()

    def cancelled() -> bool:
        return stopped.is_set() or bool(should_cancel and should_cancel())

    count = frame_worker_count(frame_count, workers, batch_size=batch_size)
    executor = ThreadPoolExecutor(max_workers=count, thread_name_prefix=thread_name_prefix)
    pending = {}
    next_start = 0

    def submit() -> None:
        nonlocal next_start
        while next_start < frame_count and len(pending) < count:
            if cancelled():
                raise InterruptedError(cancel_message)
            start = next_start
            stop = min(start + batch_size, frame_count)
            pending[executor.submit(sample, start, stop, cancelled)] = (start, stop)
            next_start = stop

    try:
        submit()
        while pending:
            if cancelled():
                raise InterruptedError(cancel_message)
            finished, _ = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
            for future in finished:
                start, stop = pending.pop(future)
                result = future.result()
                if cancelled():
                    raise InterruptedError(cancel_message)
                yield start, stop, result
            submit()
    finally:
        stopped.set()
        for future in pending:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
