from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path
from typing import Any

DATA_FOLDER_NAME = "V2_projec"
LINUX_DEFAULT_ANCESTOR_LEVELS = 2
WINDOWS_DEFAULT_ANCESTOR_LEVELS = 4
FALLBACK_DEFAULT_ANCESTOR_LEVELS = LINUX_DEFAULT_ANCESTOR_LEVELS
MIN_ANCESTOR_LEVELS = 1
MAX_ANCESTOR_LEVELS = 8


def default_ancestor_levels(system_name: str | None = None) -> int:
    """Return the unconfigured Hub storage search depth for the deployed OS."""
    name = str(system_name if system_name is not None else platform.system()).strip().casefold()
    if name.startswith("windows"):
        return WINDOWS_DEFAULT_ANCESTOR_LEVELS
    if name.startswith("linux"):
        return LINUX_DEFAULT_ANCESTOR_LEVELS
    return FALLBACK_DEFAULT_ANCESTOR_LEVELS


# Compatibility constant for existing imports. It is evaluated for the current
# deployment platform at process start; persisted admin choices still win.
DEFAULT_ANCESTOR_LEVELS = default_ancestor_levels()


def _server_root() -> Path:
    return Path(__file__).resolve().parents[2]


def storage_config_path(server_root: Path | None = None) -> Path:
    root = (server_root or _server_root()).resolve()
    return root / ".studio_config" / "storage_location.json"


def _normalize_levels(value: Any) -> int:
    try:
        levels = int(value)
    except (TypeError, ValueError):
        levels = DEFAULT_ANCESTOR_LEVELS
    return max(MIN_ANCESTOR_LEVELS, min(MAX_ANCESTOR_LEVELS, levels))


def _base_from_levels(server_root: Path, levels: int) -> Path:
    current = server_root.resolve()
    for _ in range(_normalize_levels(levels)):
        parent = current.parent
        if parent == current:
            break
        current = parent
    return current



def _candidate_from_base(base: Path) -> Path:
    resolved = base.expanduser().resolve()
    return resolved if resolved.name.casefold() == DATA_FOLDER_NAME.casefold() else (resolved / DATA_FOLDER_NAME).resolve()


def load_storage_location(server_root: Path | None = None) -> dict[str, Any]:
    root = (server_root or _server_root()).resolve()
    path = storage_config_path(root)
    payload: dict[str, Any] = {}
    try:
        parsed = json.loads(path.read_text("utf-8"))
        if isinstance(parsed, dict):
            payload = parsed
    except (OSError, ValueError):
        pass
    levels = _normalize_levels(payload.get("ancestor_levels", DEFAULT_ANCESTOR_LEVELS))
    raw_base = str(payload.get("base_path", "") or "").strip()
    try:
        base = Path(raw_base).expanduser().resolve() if raw_base else _base_from_levels(root, levels)
    except (OSError, RuntimeError):
        # A stale/broken manual path must not prevent Server startup.  The admin
        # probe still receives ``manual_base_path`` and reports it as invalid.
        base = _base_from_levels(root, levels)
    platform_name = platform.system() or os.name
    return {
        "ancestor_levels": levels,
        "default_ancestor_levels": default_ancestor_levels(platform_name),
        "platform": platform_name,
        "base_path": str(base),
        "manual_base_path": raw_base,
        "server_path": str(root),
        "candidate_path": str(_candidate_from_base(base)),
        "config_path": str(path),
    }


def probe_storage_location(
    *, server_root: Path | None = None, ancestor_levels: Any = None, base_path: str | None = None,
) -> dict[str, Any]:
    root = (server_root or _server_root()).resolve()
    current = load_storage_location(root)
    levels = _normalize_levels(current["ancestor_levels"] if ancestor_levels is None else ancestor_levels)
    if base_path is None:
        manual_base = str(current.get("manual_base_path", "") or "").strip()
    else:
        manual_base = str(base_path or "").strip()
    try:
        base = Path(manual_base).expanduser().resolve() if manual_base else _base_from_levels(root, levels)
    except (OSError, RuntimeError) as exc:
        return {
            "ok": False, "found": False, "writable": False, "ancestor_levels": levels,
            "default_ancestor_levels": current["default_ancestor_levels"],
            "platform": current["platform"],
            "base_path": manual_base, "candidate_path": "", "server_path": str(root),
            "message": f"基础目录无法解析：{exc}",
        }
    candidate = _candidate_from_base(base)
    found = candidate.is_dir() and candidate.name.casefold() == DATA_FOLDER_NAME.casefold()
    writable = False
    message = ""
    if not base.exists() or not base.is_dir():
        message = f"基础目录不存在：{base}"
    elif not found:
        message = f"未在基础目录下识别到 {DATA_FOLDER_NAME}：{candidate}"
    else:
        probe = candidate / ".mujoco_studio_storage_probe"
        try:
            probe.write_bytes(b"MuJoCo Studio")
            probe.unlink(missing_ok=True)
            writable = True
            message = f"查找成功：{candidate}"
        except OSError as exc:
            message = f"已找到 {DATA_FOLDER_NAME}，但当前用户不可写：{exc}"
    return {
        "ok": bool(found and writable),
        "found": bool(found),
        "writable": bool(writable),
        "ancestor_levels": levels,
        "default_ancestor_levels": current["default_ancestor_levels"],
        "platform": current["platform"],
        "base_path": str(base),
        "manual_base_path": manual_base,
        "candidate_path": str(candidate),
        "server_path": str(root),
        "message": message,
    }


def save_storage_location(
    *, server_root: Path | None = None, ancestor_levels: Any = None, base_path: str = "",
) -> dict[str, Any]:
    root = (server_root or _server_root()).resolve()
    probe = probe_storage_location(server_root=root, ancestor_levels=ancestor_levels, base_path=base_path)
    if not probe["ok"]:
        raise ValueError(str(probe["message"]))
    path = storage_config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_base = str(base_path or "").strip()
    payload = {
        "schema_version": 1,
        "ancestor_levels": probe["ancestor_levels"],
        # Persist manual selections as absolute paths so restart behavior never
        # depends on the process working directory. Blank keeps level mode.
        "base_path": str(probe["base_path"]) if raw_base else "",
    }
    fd, temporary = tempfile.mkstemp(prefix=".storage_location.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {**probe, "saved": True, "restart_required": True, "config_path": str(path)}


def resolved_data_root(server_root: Path | None = None) -> Path:
    override = os.getenv("MUJOCO_STUDIO_DATA", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    location = load_storage_location(server_root)
    return Path(location["candidate_path"]).resolve()
