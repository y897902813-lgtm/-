"""Stable input fingerprints and result provenance for derived artifacts."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
PROVENANCE_FILENAME = "provenance.json"

# ---------------------------------------------------------------------------
# Windows transient-share atomic replace retry.  Mirrors the behaviour in
# ``core.atomic_io.atomic_replace`` so this domain module can be imported by
# simulation.py / migration.py without pulling the full core import graph.
# ---------------------------------------------------------------------------
import sys as _sys
import time as _time

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
            if _sys.platform != "win32" or attempt == _ATOMIC_REPLACE_MAX_ATTEMPTS - 1:
                raise
            _time.sleep(_ATOMIC_REPLACE_BASE_BACKOFF_S * (attempt + 1))
    if last_error is not None:  # pragma: no cover - defensive guard
        raise last_error


_VOLATILE_METADATA = {
    "updated_at", "created_at", "last_opened_at", "version_summary",
    "version_summary_archived", "archive_base_name",
    # Delivery naming is a presentation/export projection.  Changing which
    # critical values appear in a filename must never invalidate a MuJoCo
    # trajectory that was produced from otherwise identical model physics.
    "delivery_name_suffix",
}


class FingerprintError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AssetDigestCache:
    """Small process cache keyed by immutable-enough file stat identity."""

    def __init__(self, maximum: int = 2048) -> None:
        self.maximum = max(1, int(maximum))
        self._items: OrderedDict[tuple[str, int, int], str] = OrderedDict()
        self._lock = threading.RLock()

    def digest(self, path: Path) -> tuple[str, int]:
        before = path.stat()
        key = (str(path.resolve()), before.st_size, before.st_mtime_ns)
        with self._lock:
            cached = self._items.get(key)
            if cached is not None:
                self._items.move_to_end(key)
                return cached, before.st_size
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise FingerprintError("asset_changed_during_hash", f"资产在计算指纹时发生变化：{path.name}")
        value = digest.hexdigest()
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.maximum:
                self._items.popitem(last=False)
        return value, before.st_size


_ASSET_CACHE = AssetDigestCache()


def _json_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _project_payload(project: Any) -> dict[str, Any]:
    raw = project.model_dump() if hasattr(project, "model_dump") else dict(project)
    data = json.loads(json.dumps(raw, ensure_ascii=False, allow_nan=False))
    data.pop("lifecycle", None)
    data.pop("mesh_root", None)  # deployment path is not model content
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        data["metadata"] = {key: value for key, value in metadata.items() if key not in _VOLATILE_METADATA}
    return data


def solver_project_digest(project: Any) -> str:
    """Conservative solver-input identity: exclude ONLY result layout display.

    It is safe to reuse qpos after axis/preset/color/order changes, but any
    drives, mesh bindings, constraints, sampling, distance definitions or
    simulation settings remain in the digest and force a new solve. Assets are
    independently validated with the existing hashed inventory.
    """
    payload = _project_payload(project)
    payload.pop("result_layout", None)
    return _json_digest(payload)


def legacy_v2571_project_digests(project: Any) -> set[str]:
    """Return V2.5.7.1-compatible project digests for trajectory reuse.

    V2.5.7.1 incorrectly treated ``metadata.delivery_name_suffix`` as a
    physical simulation input and used ``_`` between critical values.  V2.5.8
    excludes that presentation-only field.  These digests are read-only
    migration candidates so a successfully solved closed-chain trajectory does
    not become unusable merely because its delivery filename was reformatted.
    """
    raw = project.model_dump() if hasattr(project, "model_dump") else dict(project)
    raw = json.loads(json.dumps(raw, ensure_ascii=False, allow_nan=False))
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    suffix = str(metadata.get("delivery_name_suffix", "") or "")
    base = _project_payload(project)
    variants = {suffix, suffix.replace(",", "_")}
    digests: set[str] = set()
    for value in variants:
        candidate = json.loads(json.dumps(base, ensure_ascii=False, allow_nan=False))
        candidate.setdefault("metadata", {})["delivery_name_suffix"] = value
        digests.add(_json_digest(candidate))
    return digests


def _asset_inventory(
    roots: Iterable[Path], *, max_files: int = 10000, max_bytes: int = 20 * 1024**3,
) -> tuple[list[dict[str, Any]], int]:
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for root_index, root_value in enumerate(roots):
        root = Path(root_value).resolve()
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            if len(entries) >= max_files:
                raise FingerprintError("asset_limit_exceeded", f"资产文件数量超过指纹上限 {max_files}")
            digest, size = _ASSET_CACHE.digest(path)
            total_bytes += size
            if total_bytes > max_bytes:
                raise FingerprintError("asset_limit_exceeded", f"资产总大小超过指纹上限 {max_bytes} bytes")
            entries.append({
                "root": root_index,
                "path": path.relative_to(root).as_posix(),
                "size": size,
                "sha256": digest,
            })
    return entries, total_bytes


def input_fingerprint(project: Any, asset_roots: Iterable[Path]) -> dict[str, Any]:
    project_digest = _json_digest(_project_payload(project))
    assets, asset_bytes = _asset_inventory(asset_roots)
    assets_digest = _json_digest(assets)
    combined = _json_digest({"project": project_digest, "assets": assets_digest})
    return {
        "algorithm": "sha256",
        "project": project_digest,
        "assets": assets_digest,
        "combined": combined,
        "asset_count": len(assets),
        "asset_bytes": asset_bytes,
    }


def engine_identity(application_version: str) -> dict[str, str]:
    try:
        import mujoco  # type: ignore

        mujoco_version = str(getattr(mujoco, "__version__", "unknown"))
    except Exception:  # optional runtime dependency
        mujoco_version = "unavailable"
    return {
        "application": str(application_version),
        "mujoco": mujoco_version,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def write_provenance(
    result_dir: Path,
    *,
    job_id: str,
    kind: str,
    application_version: str,
    fingerprint: dict[str, Any],
    parameters: dict[str, Any] | None = None,
    ephemeral: bool = False,
) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "job_id": str(job_id),
        "kind": str(kind),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": engine_identity(application_version),
        "input_fingerprint": fingerprint,
        "parameters_sha256": _json_digest(parameters or {}),
        "ephemeral": bool(ephemeral),
    }
    result_dir = Path(result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)
    destination = result_dir / PROVENANCE_FILENAME
    temporary = destination.with_suffix(f".json.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), "utf-8")
    _atomic_replace(temporary, destination)
    return payload


def read_provenance(result_dir: Path) -> dict[str, Any] | None:
    path = Path(result_dir) / PROVENANCE_FILENAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def freshness(
    provenance: dict[str, Any] | None, current: dict[str, Any], *, expected_application_version: str | None = None,
) -> dict[str, Any]:
    if not provenance or not isinstance(provenance.get("input_fingerprint"), dict):
        return {"status": "unknown", "stale": None, "reasons": ["missing_provenance"]}
    recorded = provenance["input_fingerprint"]
    reasons = [f"{name}_changed" for name in ("project", "assets") if recorded.get(name) != current.get(name)]
    if expected_application_version is not None:
        engine = provenance.get("engine") if isinstance(provenance.get("engine"), dict) else {}
        if str(engine.get("application", "")) != str(expected_application_version):
            reasons.append("application_version_changed")
    return {
        "status": "stale" if reasons else "current",
        "stale": bool(reasons),
        "reasons": reasons,
        "recorded": recorded.get("combined"),
        "current": current.get("combined"),
    }
