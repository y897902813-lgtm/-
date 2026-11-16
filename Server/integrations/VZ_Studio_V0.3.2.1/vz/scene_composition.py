from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

from .models import validate_model


def instance_suffix(index: int) -> str:
    """Excel-like lower-case suffixes: a..z, aa..az, ba..."""
    value = max(0, int(index))
    chars: list[str] = []
    while True:
        value, remainder = divmod(value, 26)
        chars.append(chr(ord("a") + remainder))
        if value == 0:
            break
        value -= 1
    return "".join(reversed(chars))


def _ns(value: Any, suffix: str) -> str:
    raw = str(value or "item").strip() or "item"
    return f"{raw}_{suffix}"


def _name(value: Any, suffix: str, fallback: str) -> str:
    raw = str(value or fallback).strip() or fallback
    return f"{raw}_{suffix}"


def _vec3(value: Any) -> list[float]:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        result = []
        for item in value:
            try:
                number = float(item)
            except (TypeError, ValueError):
                number = 0.0
            result.append(number if math.isfinite(number) else 0.0)
        return result
    return [0.0, 0.0, 0.0]


def _point_plus(value: Any, offset: list[float]) -> str:
    if isinstance(value, str):
        raw = value.replace(",", " ").split()
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        raw = []
    try:
        point = [float(raw[i]) for i in range(3)]
    except (IndexError, TypeError, ValueError):
        point = [0.0, 0.0, 0.0]
    return ", ".join(f"{point[i] + offset[i]:.12g}" for i in range(3))


def compose_scene(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Create one runtime-only VZ model from scene instances.

    Each source hierarchy is attached under the synthetic root.  Every instance
    receives a deterministic namespace suffix, and all ID/name cross-references
    (parents, joints, closures, drives, assets and meshes) are remapped together.
    The returned ``asset_copies`` plan lets the HTTP layer stage source mesh files
    next to the runtime composite without persisting another model.
    """
    if not entries:
        raise ValueError("联合仿真场景至少需要一个模型")

    layers: list[dict[str, Any]] = []
    closures: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    activity_parts: list[dict[str, Any]] = []
    asset_copies: list[dict[str, Any]] = []
    instances: list[dict[str, Any]] = []
    timestep = 0.01
    end_time = 0.001
    render_scene: dict[str, Any] = {}

    for index, entry in enumerate(entries):
        source = copy.deepcopy(entry.get("model") or {})
        model_dir = Path(entry.get("model_dir") or ".").resolve()
        node = entry.get("node") if isinstance(entry.get("node"), dict) else {}
        suffix = instance_suffix(index)
        offset = _vec3(node.get("transform_mm"))
        if index == 0:
            render_scene = copy.deepcopy(source.get("render_scene") or {})
        try:
            timestep = min(timestep, max(1e-6, float((source.get("simulation") or {}).get("timestep", 0.01))))
        except (TypeError, ValueError):
            pass

        layer_map = {str(item.get("id")): _ns(item.get("id"), suffix) for item in source.get("layers", []) if isinstance(item, dict)}
        joint_map: dict[str, str] = {}
        mesh_map: dict[str, str] = {}
        asset_map = {str(item.get("id")): _ns(item.get("id"), suffix) for item in source.get("assets", []) if isinstance(item, dict)}
        drive_map = {str(item.get("id")): _ns(item.get("id"), suffix) for item in source.get("drives", []) if isinstance(item, dict)}

        for raw_asset in source.get("assets", []) or []:
            if not isinstance(raw_asset, dict):
                continue
            asset = copy.deepcopy(raw_asset)
            old_id = str(asset.get("id"))
            asset["id"] = asset_map[old_id]
            stored = Path(str(asset.get("stored_name") or asset.get("name") or old_id)).name
            target_stored = f"{suffix}__{stored}"
            asset["stored_name"] = target_stored
            assets.append(asset)
            asset_copies.append({
                "source": str((model_dir / "assets" / stored).resolve()),
                "stored_name": target_stored,
                "source_model_id": str(source.get("id") or ""),
            })

        for raw_layer in source.get("layers", []) or []:
            if not isinstance(raw_layer, dict):
                continue
            layer = copy.deepcopy(raw_layer)
            old_layer_id = str(layer.get("id"))
            layer["id"] = layer_map[old_layer_id]
            layer["name"] = _name(layer.get("name"), suffix, "层级")
            parent = str(layer.get("parent_id") or "root")
            layer["parent_id"] = "root" if parent == "root" else layer_map.get(parent, _ns(parent, suffix))
            position = _vec3(layer.get("position_mm"))
            if parent == "root":
                position = [position[i] + offset[i] for i in range(3)]
            layer["position_mm"] = position
            for joint in layer.get("joints", []) or []:
                if not isinstance(joint, dict):
                    continue
                old_joint_id = str(joint.get("id"))
                joint_map[old_joint_id] = _ns(old_joint_id, suffix)
                joint["id"] = joint_map[old_joint_id]
                joint["name"] = _name(joint.get("name"), suffix, "运动副")
                joint["point"] = _point_plus(joint.get("point", "0, 0, 0"), offset)
            for mesh in layer.get("meshes", []) or []:
                if not isinstance(mesh, dict):
                    continue
                old_mesh_id = str(mesh.get("id"))
                mesh_map[old_mesh_id] = _ns(old_mesh_id, suffix)
                mesh["id"] = mesh_map[old_mesh_id]
                old_asset_id = str(mesh.get("asset_id") or "")
                if old_asset_id:
                    mesh["asset_id"] = asset_map.get(old_asset_id, _ns(old_asset_id, suffix))
            layers.append(layer)

        for raw_closure in source.get("kinematic_closures", []) or []:
            if not isinstance(raw_closure, dict):
                continue
            closure = copy.deepcopy(raw_closure)
            closure["id"] = _ns(closure.get("id"), suffix)
            closure["name"] = _name(closure.get("name"), suffix, "闭链")
            for side in ("a", "b"):
                endpoint = closure.get(f"endpoint_{side}") if isinstance(closure.get(f"endpoint_{side}"), dict) else {}
                endpoint["layer_id"] = layer_map.get(str(endpoint.get("layer_id")), _ns(endpoint.get("layer_id"), suffix))
                point = _vec3(endpoint.get("point_mm"))
                endpoint["point_mm"] = [point[i] + offset[i] for i in range(3)]
                closure[f"endpoint_{side}"] = endpoint
            closure["solve_joint_ids"] = [joint_map.get(str(value), _ns(value, suffix)) for value in closure.get("solve_joint_ids", []) or []]
            closures.append(closure)

        # Runtime drives are synthesized from validated VZ drive calibration, not
        # from Hub motion segments.  Actual timing comes from the selected 时序库.
        for drive_index, raw_drive in enumerate(source.get("drives", []) or []):
            if not isinstance(raw_drive, dict):
                continue
            old_drive_id = str(raw_drive.get("id") or f"drive_{drive_index+1}")
            mapped_drive_id = drive_map[old_drive_id]
            joint_id = joint_map.get(str(raw_drive.get("joint_id") or ""), "")
            if not joint_id:
                continue
            p0 = float(raw_drive.get("position_0_percent", raw_drive.get("initial_position", 0.0)) or 0.0)
            p100 = float(raw_drive.get("position_100_percent", raw_drive.get("forward_limit", p0 + 30.0)) or (p0 + 30.0))
            if abs(p100 - p0) <= 1e-12:
                p100 = p0 + 30.0
            speed = max(1e-6, float(raw_drive.get("rated_speed", 30.0) or 30.0))
            drive_name = _name(raw_drive.get("name"), suffix, f"驱动{drive_index+1}")
            motion_id = _ns(f"motion_{old_drive_id}", suffix)
            activity_parts.append({
                "id": _ns(f"part_{old_drive_id}", suffix),
                "name": drive_name,
                "enabled": bool(raw_drive.get("enabled", True)),
                "motions": [{
                    "id": motion_id,
                    "name": drive_name,
                    "joint_id": joint_id,
                    "position_0_percent": p0,
                    "position_100_percent": p100,
                    "mode": "ease",
                    "rated_speed": speed,
                    "enabled": bool(raw_drive.get("enabled", True)),
                    "exchange_drive_id": mapped_drive_id,
                    "exchange_drive_name": drive_name,
                    "exchange_drive_role": str(raw_drive.get("role") or ""),
                }],
            })

        instances.append({
            "node_id": str(node.get("id") or f"node_{index+1}"),
            "model_id": str(source.get("id") or ""),
            "model_name": str(source.get("name") or "模型"),
            "suffix": suffix,
            "offset_mm": offset,
            "layer_map": layer_map,
            "joint_map": joint_map,
            "drive_map": drive_map,
            "schedule": copy.deepcopy(entry.get("schedule")) if isinstance(entry.get("schedule"), dict) else None,
        })

    raw_model = {
        "id": "scene_runtime",
        "name": "联合仿真场景",
        "description": "V2.13.4 runtime-only joint simulation composite",
        "revision": 1,
        "assets": assets,
        "variables": {},
        "simulation": {"start_time": 0.0, "end_time": max(end_time, 6.0), "timestep": timestep},
        "render_scene": render_scene,
        "scene_coordinates": {},
        "layers": layers,
        "kinematic_closures": closures,
        "activity_parts": activity_parts,
        "drives": [],
        "presets": [],
        "memories": [],
    }
    model = validate_model(raw_model)
    return {"model": model, "asset_copies": asset_copies, "instances": instances}


def compose_scene_timeline(composite_model: dict[str, Any], instances: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge selected per-model time-series schedules into one parallel timeline."""
    drive_by_id = {str(item.get("id")): item for item in composite_model.get("drives", []) if isinstance(item, dict)}
    initial: dict[str, float] = {}
    for drive_id, drive in drive_by_id.items():
        initial[drive_id] = float(drive.get("initial_position", drive.get("position_0_percent", 0.0)) or 0.0)

    segments: list[dict[str, Any]] = []
    for instance in instances:
        schedule = instance.get("schedule") if isinstance(instance.get("schedule"), dict) else None
        if not schedule:
            continue
        drive_map = instance.get("drive_map") if isinstance(instance.get("drive_map"), dict) else {}
        for source_drive in schedule.get("drives", []) or []:
            if not isinstance(source_drive, dict) or source_drive.get("enabled", True) is False:
                continue
            mapped_drive = str(drive_map.get(str(source_drive.get("id")), ""))
            if not mapped_drive or mapped_drive not in drive_by_id:
                continue
            base = float(initial.get(mapped_drive, 0.0))
            cursor = 0.0
            for order, source_segment in enumerate(source_drive.get("segments", []) or []):
                if not isinstance(source_segment, dict):
                    continue
                try:
                    start_time = max(0.0, float(source_segment.get("start", 0.0)))
                    end_time = max(start_time, float(source_segment.get("end", start_time)))
                    travel = float(source_segment.get("travel", 0.0) or 0.0)
                except (TypeError, ValueError):
                    continue
                position_start = source_segment.get("position_start")
                position_end = source_segment.get("position_end")
                try:
                    local_start = float(position_start) if position_start is not None else cursor
                except (TypeError, ValueError):
                    local_start = cursor
                try:
                    local_end = float(position_end) if position_end is not None else local_start + travel
                except (TypeError, ValueError):
                    local_end = local_start + travel
                cursor = local_end
                duration = max(0.000001, end_time - start_time)
                speed_raw = source_segment.get("speed", 0.0)
                try:
                    speed = float(speed_raw)
                except (TypeError, ValueError):
                    speed = 0.0
                if not math.isfinite(speed) or abs(speed) <= 1e-12:
                    speed = abs(local_end - local_start) / duration
                segments.append({
                    "index": len(segments),
                    "drive_id": mapped_drive,
                    "action_id": _ns(source_segment.get("id") or f"seg_{order+1}", str(instance.get("suffix") or "a")),
                    "start_value": base + local_start,
                    "end_value": base + local_end,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration,
                    "speed": speed,
                    "mode": str(source_segment.get("mode") or "duration"),
                    "profile": str(source_segment.get("profile") or "s_curve"),
                })
    duration = max([float(item.get("end_time", 0.0)) for item in segments] or [0.001])
    return {"duration": max(duration, 0.001), "segments": segments, "initial": initial}
