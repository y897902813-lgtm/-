"""Artifact Store —— 架构总纲 §8.3。

昂贵计算的产物（仿真结果、间隙曲线、XML、CSV）不塞进状态树权威区，
而是内容寻址存储，状态树里只留 handle 引用。防止状态树膨胀，
也让 LLM 能读回自己上一步输出的文件做下一步判断（闭环遍历前提）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ArtifactStore:
    def __init__(self, base_dir: str) -> None:
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, dict[str, Any]] = {}

    def put(self, content: Any, *, kind: str = "json", name: str | None = None) -> dict[str, Any]:
        if kind == "json":
            raw = json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")
            ext = "json"
        else:
            raw = content if isinstance(content, bytes) else str(content).encode("utf-8")
            ext = kind
        digest = hashlib.sha256(raw).hexdigest()[:16]
        handle = f"{digest}.{ext}"
        path = self.base / handle
        path.write_bytes(raw)
        meta = {"handle": handle, "kind": kind, "name": name or handle, "bytes": len(raw)}
        self._index[handle] = meta
        return meta

    def get(self, handle: str) -> Any:
        path = self.base / handle
        if not path.exists():
            raise KeyError(f"artifact not found: {handle}")
        raw = path.read_bytes()
        if handle.endswith(".json"):
            return json.loads(raw.decode("utf-8"))
        return raw.decode("utf-8", errors="replace")

    def discard(self, handles: list[str]) -> int:
        """Discard artifacts produced by a transaction that did not commit."""
        removed = 0
        for handle in dict.fromkeys(str(item) for item in handles if item):
            path = self.base / handle
            existed = path.is_file()
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue
            self._index.pop(handle, None)
            if existed and not path.exists():
                removed += 1
        return removed

    def list(self) -> list[dict[str, Any]]:
        # Rebuild lightweight metadata after a process restart.
        known = dict(self._index)
        for path in self.base.iterdir():
            if path.is_file() and path.name not in known:
                known[path.name] = {
                    "handle": path.name,
                    "kind": path.suffix.lstrip(".") or "bin",
                    "name": path.name,
                    "bytes": path.stat().st_size,
                }
        return sorted(known.values(), key=lambda item: item["handle"])
