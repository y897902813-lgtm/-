"""Compact oversized project event streams to their configured undo window."""
from __future__ import annotations

import argparse
import json
import os
from collections import deque
from pathlib import Path
from typing import Iterable


DEFAULT_KEEP = max(1, int(os.getenv("MUJOCO_STUDIO_MAX_EVENTS", "100")))


def event_files(data_dir: Path) -> Iterable[Path]:
    if not data_dir.is_dir():
        return ()
    return data_dir.glob("*/core/events.jsonl")


def compact(path: Path, keep: int = DEFAULT_KEEP) -> bool:
    with path.open("r", encoding="utf-8") as stream:
        tail = deque((line for line in stream if line.strip()), maxlen=keep)
    if len(tail) < keep:
        return False
    for line in tail:
        json.loads(line)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.writelines(tail)
    os.replace(temporary, path)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", nargs="?", default="data/projects", type=Path)
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    args = parser.parse_args()
    if args.keep < 1:
        parser.error("--keep must be positive")
    changed = sum(compact(path, args.keep) for path in event_files(args.data_dir))
    print(f"compacted {changed} event file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
