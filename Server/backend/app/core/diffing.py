"""Conservative structural diffs for event-sourced state changes."""
from __future__ import annotations

import copy
import os
from typing import Any

from .event_store import PathDiff


MAX_DEPTH = max(1, int(os.getenv("MUJOCO_STUDIO_DIFF_MAX_DEPTH", "32")))


def _leaf(path: str, before: Any, after: Any) -> list[PathDiff]:
    return [PathDiff(path, copy.deepcopy(before), copy.deepcopy(after))]


def _stable_ids(items: list[Any]) -> list[str] | None:
    ids: list[str] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            return None
        ids.append(item["id"])
    return ids if len(ids) == len(set(ids)) else None


def structural_diffs(path: str, before: Any, after: Any, *, depth: int = 0) -> list[PathDiff]:
    """Return deepest safe diffs while preserving exact replay and inverse replay.

    Key-set changes and list structure changes deliberately become one leaf diff:
    without a stable one-to-one mapping, a more granular guess can silently make
    undo target the wrong entity.
    """
    if before == after:
        return []
    if depth >= MAX_DEPTH or type(before) is not type(after):
        return _leaf(path, before, after)

    if isinstance(before, dict):
        if before.keys() != after.keys():
            return _leaf(path, before, after)
        diffs: list[PathDiff] = []
        for key in before:
            child_path = f"{path}.{key}" if path else str(key)
            diffs.extend(structural_diffs(child_path, before[key], after[key], depth=depth + 1))
        return diffs

    if isinstance(before, list):
        if len(before) != len(after):
            return _leaf(path, before, after)
        before_ids = _stable_ids(before)
        after_ids = _stable_ids(after)
        if before_ids is not None or after_ids is not None:
            if before_ids is None or before_ids != after_ids:
                return _leaf(path, before, after)
            tokens = [f"@{entity_id}" for entity_id in before_ids]
        else:
            tokens = [str(index) for index in range(len(before))]
        diffs = []
        for token, old_item, new_item in zip(tokens, before, after):
            diffs.extend(structural_diffs(f"{path}.{token}", old_item, new_item, depth=depth + 1))
        return diffs

    return _leaf(path, before, after)
