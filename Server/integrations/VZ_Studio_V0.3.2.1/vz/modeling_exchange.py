from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from .models import new_id, validate_model

FORMAT = "mujoco_modeling_exchange"
SCHEMA_VERSION = "2.1"
VZ_EXTENSION_VERSION = 2


def is_modeling_exchange(data: Any) -> bool:
    return isinstance(data, dict) and data.get("format") == FORMAT


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else float(default)
    except (TypeError, ValueError):
        return float(default)


def _optional_positive(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    result = _float(value)
    return result if result > 0 else None


def _safe_import_id(value: Any, prefix: str, used: set[str]) -> str:
    """Map an external identifier to a VZ-safe, layer-local identifier.

    Modeling-exchange files are allowed to come from older/third-party tools
    whose mesh ids may contain spaces, dots, slashes or non-ASCII characters.
    Keep VZ's strict internal ID contract and normalize only at the import edge.
    """
    raw = str(value or "").strip()
    if not raw:
        candidate = new_id(prefix)
    elif re.fullmatch(r"[A-Za-z0-9_-]+", raw):
        candidate = raw
    else:
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_-") or prefix
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        candidate = f"{prefix}_{slug[:40]}_{digest}"
    base = candidate
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _clamp(value: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    return min(max(_float(value), lo), hi)


def _number_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value or "")
    if math.isfinite(number) and abs(number - round(number)) < 1e-12:
        return str(int(round(number)))
    return f"{number:.12g}"


def _number_or_expression(value: Any) -> Any:
    return _number_text(value) if isinstance(value, (float, int)) else value


def _rgba(value: Any) -> list[float]:
    if isinstance(value, (list, tuple)):
        values = [_float(item) for item in value]
    else:
        values = [_float(item) for item in str(value or "").replace(",", " ").split()]
    if values and max(values[:4]) > 1.0:
        values = [item / 255.0 for item in values]
    if len(values) < 3:
        values = [0.72, 0.75, 0.80, 1.0]
    elif len(values) == 3:
        values.append(1.0)
    else:
        values = values[:4]
    return [_clamp(item) for item in values]


def _rgba_text(value: Any) -> str:
    return " ".join(_number_text(item) for item in _rgba(value))


def _vector_values(value: Any, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list[float]:
    """Normalize exchange coordinates from string/list/dict wrappers to three floats.

    Older Studio branches have emitted Point(...), plain strings and arrays; some
    projects also carry {x,y,z} dictionaries in extension parameters.  Normalize
    all of those shapes at the exchange boundary instead of leaking them into
    VZ's strict model validator.
    """
    if value is None or value == "":
        return [float(item) for item in default]
    if isinstance(value, dict):
        lowered = {str(key).lower(): item for key, item in value.items()}
        if all(key in lowered for key in ("x", "y", "z")):
            value = [lowered["x"], lowered["y"], lowered["z"]]
        else:
            nested = next((value.get(key) for key in ("point", "value", "values", "xyz") if key in value), None)
            if nested is not None:
                value = nested
            elif len(value) == 3:
                value = list(value.values())
    if isinstance(value, (list, tuple)):
        if len(value) != 3:
            raise ValueError("坐标必须包含三个数字")
        return [_float(item) for item in value]
    text = str(value).strip()
    if not text:
        return [float(item) for item in default]
    text = re.sub(r"(?i)\b(?:point|vector3?|vec3|xyz)\s*", "", text).strip()
    text = text.strip("()[]{}（）【】 ")
    parts = [item for item in re.split(r"[,，;；\s]+", text) if item]
    if len(parts) != 3:
        # Accept labeled coordinates such as x=1, y=2, z=3 without accepting
        # arbitrary text containing unrelated numbers.
        labels = dict(re.findall(r"(?i)\b([xyz])\s*[:=]\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", text))
        if all(key in labels for key in ("x", "y", "z")):
            parts = [labels["x"], labels["y"], labels["z"]]
    if len(parts) != 3:
        raise ValueError("坐标必须包含三个数字")
    return [_float(item) for item in parts]


def _vector_text(value: Any, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> str:
    return ", ".join(_number_text(item) for item in _vector_values(value, default))


def _safe_vector_text(value: Any, default: tuple[float, float, float]) -> str:
    try:
        return _vector_text(value, default)
    except Exception:
        return ", ".join(_number_text(item) for item in default)


def _point(value: Any) -> str:
    return _safe_vector_text(value, (0.0, 0.0, 0.0))


def _profile_to_vz(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "smoothstep":
        return "smoothstep"
    if text in {"point_spline", "points", "自定义点", "插值光滑运动(过指定点, 无缓起缓停)"}:
        return "points"
    if text in {"external_csv", "外部 csv", "外部导入csv曲线"}:
        return "external_csv"
    if text in {"drive_mapping", "mapping", "映射电机", "驱动映射模式(伴生驱动)"}:
        return "mapping"
    return "s_curve"


def _profile_to_exchange(value: Any) -> str:
    return {
        "s_curve": "trapezoid",
        "smoothstep": "smoothstep",
        "points": "point_spline",
        "external_csv": "external_csv",
        "mapping": "drive_mapping",
    }.get(str(value or "s_curve"), "trapezoid")


def _point_pair(value: Any, mapping: bool = False) -> list[float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return [_float(value[0]), _float(value[1])]
    if not isinstance(value, dict):
        return None
    x = value.get("source", value.get("time", 0)) if mapping else value.get("time", value.get("source", 0))
    y = value.get("value", value.get("target", 0))
    return [_float(x), _float(y)]


def _variables(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    if not isinstance(value, list):
        return {}
    return {
        str(item.get("name")): item.get("value", 0)
        for item in value
        if isinstance(item, dict) and item.get("name")
    }


def _activity_fingerprint(parts: Any) -> str:
    payload = parts if isinstance(parts, list) else []
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _layer_depth(layers: list[dict[str, Any]], layer: dict[str, Any]) -> int:
    lookup = {str(item.get("id")): item for item in layers}
    depth = 0
    parent = str(layer.get("parent_id") or "root")
    seen: set[str] = set()
    while parent and parent != "root" and parent in lookup and parent not in seen:
        seen.add(parent)
        depth += 1
        parent = str(lookup[parent].get("parent_id") or "root")
    return depth


def _layer_reference_origins_mm(layers: list[dict[str, Any]]) -> dict[str, list[float]]:
    """Resolve each layer origin in VZ's zero-pose world frame.

    VZ's editor intentionally exposes hinge/closure points as world coordinates,
    while MuJoCo Studio V2 serializes those point fields in the owning layer's
    local frame.  Keep that product-specific distinction at the exchange boundary
    instead of changing VZ's editor/runtime coordinate contract.
    """
    lookup = {str(item.get("id")): item for item in layers}
    cache: dict[str, list[float]] = {"root": [0.0, 0.0, 0.0]}

    def resolve(layer_id: str, stack: set[str] | None = None) -> list[float]:
        if layer_id in cache:
            return cache[layer_id]
        layer = lookup.get(layer_id)
        if layer is None:
            return [0.0, 0.0, 0.0]
        active = set(stack or ())
        if layer_id in active:
            raise ValueError("层级关系存在循环")
        active.add(layer_id)
        parent = resolve(str(layer.get("parent_id") or "root"), active)
        local = _vector_values(layer.get("position_mm", [0.0, 0.0, 0.0]))
        cache[layer_id] = [parent[i] + local[i] for i in range(3)]
        return cache[layer_id]

    for layer_id in lookup:
        resolve(layer_id)
    return cache


def _point_add_origin(value: Any, layer_id: str, origins: dict[str, list[float]]) -> list[float]:
    point = _vector_values(value)
    origin = origins.get(str(layer_id), [0.0, 0.0, 0.0])
    return [point[i] + origin[i] for i in range(3)]


def _point_subtract_origin(value: Any, layer_id: str, origins: dict[str, list[float]]) -> list[float]:
    point = _vector_values(value)
    origin = origins.get(str(layer_id), [0.0, 0.0, 0.0])
    return [point[i] - origin[i] for i in range(3)]


def _exchange_points_are_layer_local(data: dict[str, Any]) -> bool:
    """Return whether incoming exchange point fields use owner-layer coordinates.

    MuJoCo Studio V2's generated MJCF consumes joint/closure points directly as
    body-local ``pos`` values.  VZ <= 0.2.12 historically exported its own world
    editor points without an explicit coordinate-space marker, so retain a small
    compatibility exception for those old VZ payloads.
    """
    hierarchy = data.get("hierarchical_modeling") if isinstance(data.get("hierarchical_modeling"), dict) else {}
    closure_block = data.get("kinematic_closure_configuration") if isinstance(data.get("kinematic_closure_configuration"), dict) else {}
    marker = str(
        hierarchy.get("point_coordinate_space")
        or hierarchy.get("joint_point_coordinate_space")
        or closure_block.get("point_coordinate_space")
        or ""
    ).strip().lower()
    if marker in {"layer_local", "layer_local_mm", "local", "body_local", "body_local_mm"}:
        return True
    if marker in {"world", "world_mm", "global", "global_mm"}:
        return False

    exported = data.get("exported_by") if isinstance(data.get("exported_by"), dict) else {}
    software = str(exported.get("software") or "").strip().lower()
    version = str(exported.get("version") or "").strip()
    if software == "vz studio":
        numbers = [int(item) for item in re.findall(r"\d+", version)[:4]]
        while len(numbers) < 4:
            numbers.append(0)
        return tuple(numbers) >= (0, 2, 13, 0)
    # The second-generation MuJoCo Studio runtime treats these points as local.
    return True


def _old_root_layer() -> dict[str, Any]:
    return {
        "id": "root", "name": "root", "parent_id": None,
        "color_text": "0.72 0.75 0.80 1", "active": True,
        "meshes": [], "joints": [],
    }


def _old_joint(joint: dict[str, Any]) -> dict[str, Any]:
    known = {
        "id", "name", "type", "point", "axis", "reverse", "limited", "range",
        "crank_center", "crank_end", "rod_end", "slide_axis", "damping", "armature",
        "frictionloss", "stiffness", "spring_reference", "parameters",
    }
    params = copy.deepcopy(joint.get("parameters", {})) if isinstance(joint.get("parameters"), dict) else {}
    for key, item in joint.items():
        if key not in known and key not in {"render_config", "material_slots", "_exchange_source_id"}:
            params.setdefault(key, copy.deepcopy(item))
    legacy_type = str(params.get("legacy_joint_type", joint.get("type", "rotation")))
    value = {
        "name": str(joint.get("name") or "joint1"),
        "joint_type": legacy_type,
        "point_text": f"Point( {joint.get('point', '0, 0, 0')} )",
        "axis_text": str(joint.get("axis", "0, 1, 0")),
        "invert_axis": bool(joint.get("reverse", False)),
        "crank_center_text": f"Point( {joint.get('crank_center', '0, 0, 0')} )",
        "crank_end_text": f"Point( {joint.get('crank_end', '0, 10, 0')} )",
        "rod_end_text": f"Point( {joint.get('rod_end', '30, 0, 0')} )",
        "slide_axis_text": str(joint.get("slide_axis", "1, 0, 0")),
        "motion_axis_text": str(params.get("motion_axis_text", joint.get("slide_axis", "1, 0, 0"))),
        "limited": bool(joint.get("limited", False)),
        "range": list(joint.get("range", [-180.0, 180.0])),
        "damping": _float(joint.get("damping", params.get("damping", 0.1)), 0.1),
        "armature": _float(joint.get("armature", params.get("armature", 0.01)), 0.01),
        "frictionloss": _float(joint.get("frictionloss", params.get("frictionloss", 0.0)), 0.0),
        "stiffness": _float(joint.get("stiffness", params.get("stiffness", 0.0)), 0.0),
        "spring_reference": _float(joint.get("spring_reference", params.get("spring_reference", 0.0)), 0.0),
        "parameters": {key: copy.deepcopy(item) for key, item in params.items() if key != "legacy_joint_type"},
    }
    for key, item in params.items():
        if key != "legacy_joint_type":
            value.setdefault(key, copy.deepcopy(item))
    return value


def _old_snapshot_joint(joint: dict[str, Any]) -> dict[str, Any]:
    value = _old_joint(joint)
    allowed = {
        "name", "joint_type", "point_text", "axis_text", "invert_axis",
        "crank_center_text", "crank_end_text", "rod_end_text", "slide_axis_text",
        "motion_axis_text", "fivebar_point_a_text", "fivebar_point_b_text",
        "fivebar_point_c_text", "fivebar_point_d_text", "fivebar_point_e_text",
        "fivebar_ignore_axis", "custom_point_count", "custom_point_values",
    }
    return {key: copy.deepcopy(item) for key, item in value.items() if key in allowed}


def _export_joint(joint: dict[str, Any], layer: dict[str, Any], index: int) -> dict[str, Any]:
    value = _old_joint(joint)
    value.update({
        "id": str(joint.get("id") or new_id("joint")),
        "index": index,
        "choice": f"{layer.get('name', layer.get('id', 'layer'))}/{joint.get('name', 'joint1')}",
        "layer_id": str(layer.get("id") or ""),
        "layer_name": str(layer.get("name") or ""),
    })
    return value


def _old_segment(segment: dict[str, Any], choices: dict[str, str]) -> dict[str, Any]:
    reference = str(segment.get("reference", "") or "")
    ref_drive, ref_segment = (
        (reference.split("/", 1) + [""])[:2] if "/" in reference else ("", "")
    )
    points = list(segment.get("points", []) or [])
    point_rows = [
        {"time": _number_text(item[0]), "value": _number_text(item[1])}
        for item in points if isinstance(item, (list, tuple)) and len(item) >= 2
    ]
    mapping_rows = [
        {"source": _number_text(item[0]), "value": _number_text(item[1])}
        for item in points if isinstance(item, (list, tuple)) and len(item) >= 2
    ]
    profile = str(segment.get("profile", "s_curve"))
    value = copy.deepcopy(segment.get("exchange_extra", {})) if isinstance(segment.get("exchange_extra"), dict) else {}
    value.pop("exchange_extra", None)
    value.update({
        "id": str(segment.get("id") or new_id("seg")),
        "name": str(segment.get("name") or "seg1"),
        "mode": "speed" if str(segment.get("mode")) == "speed" else "duration",
        "enable_soft_start": bool(segment.get("ease_in", True)),
        "enable_soft_stop": bool(segment.get("ease_out", True)),
        "enable_ease_in": bool(segment.get("ease_in", True)),
        "enable_ease_out": bool(segment.get("ease_out", True)),
        "easing_mode": str(segment.get("easing_mode", "time")),
        "ease_in_time": _number_or_expression(segment.get("ease_in_time")) if segment.get("ease_in_time") is not None else None,
        "ease_out_time": _number_or_expression(segment.get("ease_out_time")) if segment.get("ease_out_time") is not None else None,
        "ease_in_acceleration": _number_or_expression(segment.get("ease_in_acceleration", 150.0)),
        "ease_out_acceleration": _number_or_expression(segment.get("ease_out_acceleration", 150.0)),
        "acceleration_time": _number_or_expression(segment.get("acceleration_time", 0.2)),
        "start_time_mode": "ref" if str(segment.get("start_mode", "direct")) == "reference" else "direct",
        "start_time_value": _number_or_expression(segment.get("start", 0.0)),
        "ref_drive_name": ref_drive,
        "ref_segment_name": ref_segment,
        "ref_boundary": str(segment.get("reference_boundary", "end")),
        "max_speed": _number_or_expression(segment.get("speed", 30.0)),
        "duration": _number_or_expression(segment.get("duration", 1.0)),
        "travel": _number_or_expression(segment.get("travel", 0.0)),
        "motion_profile": _profile_to_exchange(profile),
        "point_count": str(len(points) if profile == "points" else 0),
        "point_values": point_rows if profile == "points" else [],
        "external_csv_path": str(segment.get("csv_path", "")) if profile == "external_csv" else "",
        "external_csv_header": "",
        "external_csv_source_metric": "",
        "external_csv_values": point_rows if profile == "external_csv" else [],
        "mapping_source_joint_choice": choices.get(str(segment.get("mapping_source_joint_id", "")), ""),
        "mapping_source_joint_id": str(segment.get("mapping_source_joint_id", "")),
        "mapping_csv_path": str(segment.get("csv_path", "")) if profile == "mapping" else "",
        "mapping_csv_header": str(segment.get("mapping_csv_name", "")),
        "mapping_point_count": int(_float(segment.get("mapping_point_count", len(points) if profile == "mapping" else 0), 0)),
        "mapping_values": mapping_rows if profile == "mapping" else [],
        "archive_start": bool(segment.get("archive_start", False)),
        "archive_end": bool(segment.get("archive_end", False)),
        "archive_start_time": bool(segment.get("archive_start_time", False)),
        "archive_motion_value": bool(segment.get("archive_motion_value", False)),
        "archive_rate_value": bool(segment.get("archive_rate_value", False)),
        "gantt_travel_input_mode": str(segment.get("gantt_travel_input_mode", "travel")),
    })
    return value


def _old_drive(drive: dict[str, Any], choices: dict[str, str]) -> dict[str, Any]:
    """Export a neutral drive binding plus the full motion schedule."""
    value = copy.deepcopy(drive.get("exchange_extra", {})) if isinstance(drive.get("exchange_extra"), dict) else {}
    value.pop("exchange_extra", None)
    value.update({
        "id": str(drive.get("id") or new_id("drive")),
        "name": str(drive.get("name") or "act1"),
        "joint_id": str(drive.get("joint_id", "")),
        "target_joint_choice": choices.get(str(drive.get("joint_id", "")), ""),
        "fivebar_role": str(drive.get("role", "")),
        "enabled": bool(drive.get("enabled", True)),
        "dynamic_kp": _float(drive.get("dynamic_kp", value.get("dynamic_kp", 100.0)), 100.0),
        "dynamic_kv": _float(drive.get("dynamic_kv", value.get("dynamic_kv", 20.0)), 20.0),
        "dynamic_lock_force": _float(drive.get("dynamic_lock_force", value.get("dynamic_lock_force", 2000.0)), 2000.0),
        "segments": [
            _old_segment(segment, choices)
            for segment in list(drive.get("segments", []) or [])
            if isinstance(segment, dict)
        ],
    })
    return value


def _drive_rows_from_old(
    old_drives: list[dict[str, Any]],
    joint_id_by_choice: dict[str, str],
    joint_type_by_id: dict[str, str],
) -> list[dict[str, Any]]:
    rows = []
    for index, drive in enumerate(old_drives):
        choice = str(drive.get("target_joint_choice", "") or "")
        joint_id = str(drive.get("joint_id") or joint_id_by_choice.get(choice, ""))
        row = copy.deepcopy(drive)
        row.pop("exchange_extra", None)
        row.update({
            "id": str(drive.get("id") or new_id("drive")),
            "index": index,
            "name": str(drive.get("name") or "act1"),
            "type": joint_type_by_id.get(joint_id, ""),
            "target_joint": {
                "choice": choice,
                "id": joint_id,
                "joint_type": joint_type_by_id.get(joint_id, ""),
                "resolution": "resolved" if joint_id else "unresolved",
            },
            "fivebar_role": str(drive.get("fivebar_role", drive.get("role", ""))),
            "enabled": bool(drive.get("enabled", True)),
            "dynamic_kp": _float(drive.get("dynamic_kp", 100.0), 100.0),
            "dynamic_kv": _float(drive.get("dynamic_kv", 20.0), 20.0),
            "dynamic_lock_force": _float(drive.get("dynamic_lock_force", 2000.0), 2000.0),
            "segments": [
                {**copy.deepcopy(segment), "index": i}
                for i, segment in enumerate(list(drive.get("segments", []) or []))
                if isinstance(segment, dict)
            ],
        })
        rows.append(row)
    return rows


def _mesh_extension_payload(model: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for layer in model.get("layers", []):
        for mesh in layer.get("meshes", []):
            extra = {}
            for key in ("render_config", "material_slots"):
                if key in mesh:
                    extra[key] = copy.deepcopy(mesh[key])
            if extra:
                result[str(mesh.get("id"))] = extra
    return result


def _closure_row(raw: dict[str, Any]) -> dict[str, Any]:
    def endpoint(side: str) -> dict[str, Any]:
        value = raw.get(f"endpoint_{side}") if isinstance(raw.get(f"endpoint_{side}"), dict) else {}
        return {
            "layer_id": str(value.get("layer_id") or raw.get(f"layer_{side}_id") or ""),
            "point_mm": _vector_values(value.get("point_mm", raw.get(f"point_{side}_mm", [0, 0, 0]))),
        }
    return {
        "id": str(raw.get("id") or new_id("closure")),
        "name": str(raw.get("name") or "closure1"),
        "enabled": bool(raw.get("enabled", True)),
        "kind": "point",
        "endpoint_a": endpoint("a"),
        "endpoint_b": endpoint("b"),
        "solve_joint_ids": [str(item) for item in list(raw.get("solve_joint_ids", []) or []) if str(item)],
        "tolerance_mm": max(_float(raw.get("tolerance_mm", 0.05), 0.05), 1e-9),
        "max_iterations": max(int(_float(raw.get("max_iterations", 40), 40)), 1),
        "damping": max(_float(raw.get("damping", 1e-4), 1e-4), 1e-12),
        "max_angle_step_deg": max(_float(raw.get("max_angle_step_deg", 8.0), 8.0), 1e-9),
        "max_slide_step_mm": max(_float(raw.get("max_slide_step_mm", 5.0), 5.0), 1e-9),
    }


def _extract_closures(data: dict[str, Any]) -> list[dict[str, Any]]:
    block = data.get("kinematic_closure_configuration") if isinstance(data.get("kinematic_closure_configuration"), dict) else {}
    raw = block.get("closures")
    if not isinstance(raw, list):
        vzext = data.get("vz_extensions") if isinstance(data.get("vz_extensions"), dict) else {}
        raw = vzext.get("kinematic_closures", [])
    return [_closure_row(item) for item in list(raw or []) if isinstance(item, dict)]


def export_modeling_exchange(
    model: dict[str, Any], application_version: str = "0.2.16.1", *,
    include_measurements: bool = True,
) -> dict[str, Any]:
    model = validate_model(model, expected_id=str(model.get("id")))
    layers = list(model.get("layers", []))
    reference_origins_mm = _layer_reference_origins_mm(layers)
    choices = {
        str(joint.get("id")): f"{layer.get('name', layer.get('id'))}/{joint.get('name', 'joint1')}"
        for layer in layers for joint in layer.get("joints", [])
    }
    joint_id_by_choice = {choice: joint_id for joint_id, choice in choices.items()}
    joint_types = {
        str(joint.get("id")): str(joint.get("type", "rotation"))
        for layer in layers for joint in layer.get("joints", [])
    }

    layer_rows: list[dict[str, Any]] = []
    old_layers: list[dict[str, Any]] = [_old_root_layer()]
    for layer in layers:
        layer_origin = reference_origins_mm.get(str(layer.get("id")), [0.0, 0.0, 0.0])
        exchange_joints: list[dict[str, Any]] = []
        for joint in layer.get("joints", []):
            item = copy.deepcopy(joint)
            if str(item.get("type", "rotation")) == "rotation":
                item["point"] = _vector_text(
                    [
                        value - layer_origin[index]
                        for index, value in enumerate(_vector_values(item.get("point", "0, 0, 0")))
                    ]
                )
            exchange_joints.append(item)
        layer_rgba = _rgba(layer.get("color", "0.72 0.75 0.80 1"))
        models: list[dict[str, Any]] = []
        old_meshes: list[dict[str, Any]] = []
        for index, mesh in enumerate(layer.get("meshes", [])):
            inherits = not str(mesh.get("rgba", "") or "").strip()
            base_rgba = _rgba(layer.get("color") if inherits else mesh.get("rgba"))
            opacity = _clamp(mesh.get("opacity", 1.0))
            effective = list(base_rgba)
            effective[3] = _clamp(effective[3] * opacity)
            row = {
                "id": str(mesh.get("id") or new_id("mesh")),
                "index": index,
                "file_name": str(mesh.get("filename", "")),
                "name": str(mesh.get("filename", "")),
                "collision": bool(mesh.get("collision", False)),
                "mass_kg": mesh.get("mass_kg"),
                "color": {
                    "rgba": base_rgba,
                    "opacity_alpha": opacity,
                    "effective_rgba": effective,
                    "inherits_layer_color": inherits,
                },
            }
            if mesh.get("friction") is not None:
                row["friction"] = mesh.get("friction")
            if mesh.get("collision_margin_mm") is not None:
                row["collision_margin_mm"] = mesh.get("collision_margin_mm")
            models.append(row)
            old_meshes.append({
                "file_name": str(mesh.get("filename", "")),
                "collision": bool(mesh.get("collision", False)),
                "color_text": "" if inherits else _rgba_text(mesh.get("rgba")),
                "opacity_text": _number_text(opacity),
            })
        layer_rows.append({
            "id": str(layer.get("id")),
            "name": str(layer.get("name")),
            "parent_id": str(layer.get("parent_id") or "root"),
            "depth": _layer_depth(layers, layer),
            "active": bool(layer.get("active", True)),
            "position_mm": list(layer.get("position_mm", [0.0, 0.0, 0.0])),
            "mass_kg": layer.get("mass_kg"),
            "color_rgba": layer_rgba,
            "alpha": layer_rgba[3],
            "models": models,
            "joints": [
                _export_joint(joint, layer, i)
                for i, joint in enumerate(exchange_joints)
            ],
        })
        old_layers.append({
            "id": str(layer.get("id")),
            "name": str(layer.get("name")),
            "parent_id": str(layer.get("parent_id") or "root"),
            "color_text": _rgba_text(layer.get("color")),
            "active": bool(layer.get("active", True)),
            "position_mm": list(layer.get("position_mm", [0.0, 0.0, 0.0])),
            "mass_kg": layer.get("mass_kg"),
            "meshes": old_meshes,
            "joints": [_old_snapshot_joint(joint) for joint in exchange_joints],
        })

    compat = model.get("_modeling_exchange") if isinstance(model.get("_modeling_exchange"), dict) else {}
    preserved_drives = compat.get("latest_drives") if isinstance(compat.get("latest_drives"), list) else []
    same_activity = str(compat.get("activity_fingerprint") or "") == _activity_fingerprint(model.get("activity_parts", []))
    # If an imported activity definition has not been edited, use its original
    # rich neutral drive rows verbatim. This gives lossless V2/V21 -> VZ -> V2/V21
    # round-tripping even for schedule features that VZ does not expose directly.
    old_drives = copy.deepcopy(preserved_drives) if preserved_drives and same_activity else [
        _old_drive(drive, choices) for drive in model.get("drives", [])
    ]

    variables = [
        {"name": str(name), "value": value}
        for name, value in model.get("variables", {}).items()
    ]
    latest = {"drives": copy.deepcopy(old_drives), "custom_variables": copy.deepcopy(variables)}
    measurement = (
        copy.deepcopy(compat.get("measurement_configuration", {"pairs": []}))
        if isinstance(compat.get("measurement_configuration"), dict)
        else {"pairs": []}
    )
    measurement.setdefault("pairs", [])
    studio_extensions = (
        copy.deepcopy(compat.get("studio_extensions", {}))
        if isinstance(compat.get("studio_extensions"), dict)
        else {}
    )

    mesh_root = str(compat.get("model_folder_path", "") or "")
    output_dir = str(compat.get("output_directory", "") or "")
    template_scene = str(compat.get("template_scene_path", "") or "")
    simulation = model.get("simulation", {})
    application_state = {
        "model_name": model.get("name", "模型"),
        "root_id": "root",
        "stl_folder": mesh_root,
        "template_scene_path": template_scene,
        "last_output_dir": output_dir,
        "sim_timestep": _number_text(simulation.get("timestep", 0.01)),
        "sim_start_time": _number_text(simulation.get("start_time", 0.0)),
        "sim_end_time": _number_text(simulation.get("end_time", 6.0)),
        "layers": old_layers,
        "drives": copy.deepcopy(old_drives),
        "custom_variables": copy.deepcopy(variables),
        "drive_versions": {"latest": copy.deepcopy(latest)},
        "latest_drive_version_name": "latest",
        "pairs": copy.deepcopy(measurement.get("pairs", [])) if include_measurements else [],
        "opt_variables": [],
        "opt_filter_conditions": [],
        "ui_settings": {},
    }

    drive_rows = _drive_rows_from_old(old_drives, joint_id_by_choice, joint_types)
    closure_rows = []
    for item in model.get("kinematic_closures", []):
        if not isinstance(item, dict):
            continue
        closure = _closure_row(item)
        for side in ("a", "b"):
            endpoint = closure[f"endpoint_{side}"]
            endpoint["point_mm"] = _point_subtract_origin(
                endpoint["point_mm"], endpoint["layer_id"], reference_origins_mm,
            )
        closure_rows.append(closure)
    payload = {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "exported_by": {"software": "VZ Studio", "version": application_version},
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "model_name": model.get("name", "模型"),
        "model_folder_path": mesh_root,
        "stl_obj_folder": mesh_root,
        "output_directory": output_dir,
        "hierarchical_modeling": {
            "root_id": "root",
            "relation_field": "parent_id",
            "point_coordinate_space": "layer_local_mm",
            "layers": layer_rows,
        },
        "drive_configuration": {
            "mode": "full",
            "bindings": copy.deepcopy(drive_rows),
            "drives": drive_rows,
            "selected_version_name": "latest",
            "latest_version": latest,
            "all_versions": {"latest": copy.deepcopy(latest)},
        },
        "measurement_configuration": measurement,
        "kinematic_closure_configuration": {
            "point_coordinate_space": "layer_local_mm",
            "closures": copy.deepcopy(closure_rows),
        },
        "studio_extensions": studio_extensions,
        "exchange_capabilities": {
            "hierarchy": True,
            "joints": True,
            "measurements": bool(include_measurements),
            "drive_bindings": True,
            "drive_schedules": True,
            "kinematic_closures": True,
        },
        "application_state": application_state,
        "vz_extensions": {
            "schema_version": VZ_EXTENSION_VERSION,
            "render_scene": copy.deepcopy(model.get("render_scene", {})),
            "mesh_rendering": _mesh_extension_payload(model),
            "kinematic_closures": copy.deepcopy(closure_rows),
            "presets": copy.deepcopy(model.get("presets", [])),
            "memories": copy.deepcopy(model.get("memories", [])),
        },
    }
    if not include_measurements:
        payload.pop("measurement_configuration", None)
    return payload


def _import_joint(raw: dict[str, Any]) -> dict[str, Any]:
    raw_type = str(raw.get("joint_type", raw.get("type", "rotation")) or "rotation")
    joint_type = raw_type if raw_type in {"rotation", "translation", "crank"} else "rotation"
    known = {
        "id", "index", "choice", "layer_id", "layer_name", "name", "joint_type", "type",
        "point_text", "point", "axis_text", "axis", "invert_axis", "reverse", "limited", "range",
        "crank_center_text", "crank_center", "crank_end_text", "crank_end",
        "rod_end_text", "rod_end", "slide_axis_text", "slide_axis", "parameters",
        "damping", "armature", "frictionloss", "stiffness", "spring_reference",
    }
    parameters = copy.deepcopy(raw.get("parameters", {})) if isinstance(raw.get("parameters"), dict) else {}
    for key, value in raw.items():
        if key not in known:
            parameters.setdefault(key, copy.deepcopy(value))
    if raw_type != joint_type:
        parameters["legacy_joint_type"] = raw_type
    rng = raw.get("range", [-180.0, 180.0])
    if not isinstance(rng, (list, tuple)) or len(rng) != 2:
        rng = [-180.0, 180.0]
    return {
        "id": str(raw.get("id") or new_id("joint")),
        "name": str(raw.get("name") or "joint1"),
        "type": joint_type,
        "point": _safe_vector_text(raw.get("point_text", raw.get("point", "0, 0, 0")), (0.0, 0.0, 0.0)),
        "axis": _safe_vector_text(raw.get("axis_text", raw.get("axis", "0, 1, 0")), (0.0, 1.0, 0.0)),
        "crank_center": _safe_vector_text(raw.get("crank_center_text", raw.get("crank_center", "0, 0, 0")), (0.0, 0.0, 0.0)),
        "crank_end": _safe_vector_text(raw.get("crank_end_text", raw.get("crank_end", "0, 10, 0")), (0.0, 10.0, 0.0)),
        "rod_end": _safe_vector_text(raw.get("rod_end_text", raw.get("rod_end", "30, 0, 0")), (30.0, 0.0, 0.0)),
        "slide_axis": _safe_vector_text(raw.get("slide_axis_text", raw.get("slide_axis", "1, 0, 0")), (1.0, 0.0, 0.0)),
        "reverse": bool(raw.get("invert_axis", raw.get("reverse", False))),
        "limited": bool(raw.get("limited", False)),
        "range": [_float(rng[0], -180.0), _float(rng[1], 180.0)],
        "damping": max(_float(raw.get("damping", parameters.get("damping", 0.1)), 0.1), 0.0),
        "armature": max(_float(raw.get("armature", parameters.get("armature", 0.01)), 0.01), 0.0),
        "frictionloss": max(_float(raw.get("frictionloss", parameters.get("frictionloss", 0.0)), 0.0), 0.0),
        "stiffness": max(_float(raw.get("stiffness", parameters.get("stiffness", 0.0)), 0.0), 0.0),
        "spring_reference": _float(raw.get("spring_reference", parameters.get("spring_reference", 0.0)), 0.0),
        "parameters": parameters,
    }


def _import_layer(raw: dict[str, Any], root_id: str, from_exchange: bool) -> dict[str, Any]:
    layer_id = str(raw.get("id") or new_id("layer"))
    if from_exchange:
        color = _rgba_text(raw.get("color_rgba", "0.72 0.75 0.80 1"))
        raw_meshes = list(raw.get("models", []) or [])
    else:
        color = _rgba_text(raw.get("color_text", raw.get("color", "0.72 0.75 0.80 1")))
        raw_meshes = list(raw.get("meshes", []) or [])
    meshes = []
    used_mesh_ids: set[str] = set()
    for item in raw_meshes:
        if not isinstance(item, dict):
            continue
        try:
            if from_exchange:
                color_data = item.get("color") if isinstance(item.get("color"), dict) else {}
                rgba = "" if color_data.get("inherits_layer_color") is True else (
                    color_data.get("rgba") or color_data.get("effective_rgba") or color
                )
                opacity = _clamp(color_data.get("opacity_alpha", 1.0))
                filename = item.get("file_name", item.get("name", item.get("filename", "")))
            else:
                rgba = item.get("color_text", item.get("rgba", ""))
                opacity = _clamp(item.get("opacity_text", item.get("opacity", 1.0)))
                filename = item.get("file_name", item.get("name", item.get("filename", "")))
            if not str(filename).strip():
                continue
            source_mesh_id = str(item.get("id") or "").strip()
            mesh_id = _safe_import_id(source_mesh_id, "mesh", used_mesh_ids)
            mesh = {
                "id": mesh_id,
                "filename": str(filename),
                "asset_id": "",
                "collision": bool(item.get("collision", False)),
                "rgba": "" if not str(rgba or "").strip() else _rgba_text(rgba),
                "opacity": opacity,
            }
            if source_mesh_id and source_mesh_id != mesh_id:
                mesh["_exchange_source_id"] = source_mesh_id
            meshes.append(mesh)
        except Exception:
            continue
    joints = []
    for item in list(raw.get("joints", []) or []):
        if not isinstance(item, dict):
            continue
        try:
            joints.append(_import_joint(item))
        except Exception:
            continue
    parent = raw.get("parent_id")
    try:
        position_mm = _vector_values(raw.get("position_mm", [0.0, 0.0, 0.0]))
    except Exception:
        position_mm = [0.0, 0.0, 0.0]
    return {
        "id": layer_id,
        "name": str(raw.get("name") or layer_id),
        "parent_id": "root" if parent in {None, "", root_id} else str(parent),
        "active": bool(raw.get("active", True)),
        "color": color,
        "position_mm": position_mm,
        "meshes": meshes,
        "joints": joints,
    }


def _repair_import_structure(layers: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    layer_map: dict[str, str] = {}
    used_layers: set[str] = set()
    for layer in layers:
        source = str(layer.get("id") or "").strip()
        safe = _safe_import_id(source, "layer", used_layers)
        if source and source != safe:
            layer["_exchange_source_id"] = source
        layer["id"] = safe
        if source:
            layer_map.setdefault(source, safe)
    for layer in layers:
        parent = str(layer.get("parent_id") or "root")
        layer["parent_id"] = "root" if parent == "root" else layer_map.get(parent, "root")

    joint_map: dict[str, str] = {}
    used_joints: set[str] = set()
    for layer in layers:
        for joint in list(layer.get("joints", []) or []):
            source = str(joint.get("id") or "").strip()
            safe = _safe_import_id(source, "joint", used_joints)
            if source and source != safe:
                params = joint.setdefault("parameters", {})
                if isinstance(params, dict):
                    params.setdefault("exchange_source_id", source)
            joint["id"] = safe
            if source:
                joint_map.setdefault(source, safe)
    return layer_map, joint_map


def _repair_drive_rows(rows: list[dict[str, Any]], joint_map: dict[str, str]) -> list[dict[str, Any]]:
    used_drives: set[str] = set()
    used_segments: set[str] = set()
    repaired: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        drive = copy.deepcopy(raw)
        source_id = str(drive.get("id") or "").strip()
        drive["id"] = _safe_import_id(source_id, "drive", used_drives)
        direct = str(drive.get("joint_id") or "")
        if direct in joint_map:
            drive["joint_id"] = joint_map[direct]
        target = drive.get("target_joint")
        if isinstance(target, dict):
            target_id = str(target.get("id") or "")
            if target_id in joint_map:
                target["id"] = joint_map[target_id]
        segments = []
        for segment_raw in list(drive.get("segments", []) or []):
            if not isinstance(segment_raw, dict):
                continue
            segment = copy.deepcopy(segment_raw)
            segment["id"] = _safe_import_id(segment.get("id"), "seg", used_segments)
            mapping_id = str(segment.get("mapping_source_joint_id") or "")
            if mapping_id in joint_map:
                segment["mapping_source_joint_id"] = joint_map[mapping_id]
            segments.append(segment)
        drive["segments"] = segments
        repaired.append(drive)
    return repaired


def _extract_latest_drives(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the richest available neutral drive rows, including schedules.

    schema 2.1 ``mode=full`` canonical rows are authoritative because they can
    carry fields that legacy latest_version snapshots intentionally omit.
    """
    snapshot = data.get("application_state") if isinstance(data.get("application_state"), dict) else {}
    config = data.get("drive_configuration") if isinstance(data.get("drive_configuration"), dict) else {}
    canonical = list(config.get("drives", []) or []) if isinstance(config.get("drives"), list) else []
    if canonical and str(config.get("mode", "full") or "full").lower() == "full":
        return [copy.deepcopy(item) for item in canonical if isinstance(item, dict)]
    latest = config.get("latest_version") if isinstance(config.get("latest_version"), dict) else None
    if latest is None and isinstance(config.get("latest"), dict):
        latest = config.get("latest")
    versions = snapshot.get("drive_versions") if isinstance(snapshot.get("drive_versions"), dict) else {}
    if latest is None and isinstance(versions.get("latest"), dict):
        latest = versions.get("latest")
    raw = list((latest or {}).get("drives", []) or [])
    if not raw:
        raw = canonical
    if not raw:
        raw = list(config.get("bindings", []) or [])
    if not raw:
        raw = list(snapshot.get("drives", []) or [])
    return [copy.deepcopy(item) for item in list(raw or []) if isinstance(item, dict)]


def _drive_to_activity(
    raw: dict[str, Any],
    choices: dict[str, str],
    joints: dict[str, dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    target = raw.get("target_joint") if isinstance(raw.get("target_joint"), dict) else {}
    choice = str(raw.get("target_joint_choice") or target.get("choice") or raw.get("joint_choice") or "")
    joint_id = str(raw.get("joint_id") or target.get("id") or "")
    if joint_id not in joints:
        joint_id = str(choices.get(choice, ""))
    if not joint_id or joint_id not in joints:
        return None
    joint = joints[joint_id]
    rng = list(joint.get("range", [-180.0, 180.0]))
    if len(rng) != 2:
        rng = [-180.0, 180.0]
    base0, base100 = _float(rng[0], -180.0), _float(rng[1], 180.0)
    if base0 == base100:
        base100 = base0 + 1.0
    drive_id = str(raw.get("id") or new_id("drive"))
    drive_name = str(raw.get("name") or f"驱动{index + 1}")
    raw_segments = [item for item in list(raw.get("segments", []) or []) if isinstance(item, dict)]
    motions = []
    cursor = base0
    for seg_index, segment in enumerate(raw_segments):
        profile = _profile_to_vz(segment.get("motion_profile", segment.get("profile", "s_curve")))
        if profile == "mapping":
            raw_points = segment.get("mapping_values", segment.get("points", []))
            points = [_point_pair(item, mapping=True) for item in list(raw_points or [])]
        elif profile == "external_csv":
            raw_points = segment.get("external_csv_values", segment.get("points", []))
            points = [_point_pair(item) for item in list(raw_points or [])]
        else:
            raw_points = segment.get("point_values", segment.get("points", []))
            points = [_point_pair(item) for item in list(raw_points or [])]
        points = [item for item in points if item is not None]
        travel = _float(segment.get("travel"), points[-1][1] if points else 0.0)
        speed = max(_float(segment.get("max_speed", segment.get("speed", 30.0)), 30.0), 1e-6)
        end = cursor + travel
        if end == cursor:
            end = cursor + max(abs(base100 - base0), 1.0)
        start_mode = str(segment.get("start_time_mode", segment.get("start_mode", "direct")))
        reference = str(segment.get("reference", "") or "")
        if not reference:
            rd = str(segment.get("ref_drive_name", "") or "")
            rs = str(segment.get("ref_segment_name", "") or "")
            reference = f"{rd}/{rs}" if rd and rs else ""
        exchange_extra = copy.deepcopy(segment)
        exchange_extra.pop("exchange_extra", None)
        internal_segment = {
            "id": str(segment.get("id") or new_id("seg")),
            "name": str(segment.get("name") or f"动作{seg_index + 1}"),
            "start_mode": "reference" if start_mode in {"ref", "reference"} else "direct",
            "start": segment.get("start_time_value", segment.get("start", 0.0)),
            "reference": reference,
            "reference_boundary": str(segment.get("ref_boundary", segment.get("reference_boundary", "end"))),
            "mode": "speed" if str(segment.get("mode", "duration")) == "speed" else "duration",
            "duration": segment.get("duration", 1.0),
            "speed": segment.get("max_speed", segment.get("speed", 30.0)),
            "travel": segment.get("travel", travel),
            "profile": profile,
            "ease_in": bool(segment.get("enable_ease_in", segment.get("ease_in", segment.get("enable_soft_start", True)))),
            "ease_out": bool(segment.get("enable_ease_out", segment.get("ease_out", segment.get("enable_soft_stop", True)))),
            "easing_mode": str(segment.get("easing_mode", "time")),
            "ease_in_time": segment.get("ease_in_time", 0.2),
            "ease_out_time": segment.get("ease_out_time", 0.2),
            "ease_in_acceleration": segment.get("ease_in_acceleration", 150.0),
            "ease_out_acceleration": segment.get("ease_out_acceleration", 150.0),
            "acceleration_time": segment.get("acceleration_time", 0.2),
            "points": points,
            "csv_path": str(segment.get("external_csv_path", segment.get("mapping_csv_path", segment.get("csv_path", ""))) or ""),
            "mapping_source_joint_id": str(segment.get("mapping_source_joint_id", "") or ""),
            "mapping_csv_name": str(segment.get("mapping_csv_header", segment.get("mapping_csv_name", "")) or ""),
            "mapping_point_count": int(_float(segment.get("mapping_point_count", len(points) if profile == "mapping" else 0), 0)),
            "archive_start": bool(segment.get("archive_start", False)),
            "archive_end": bool(segment.get("archive_end", False)),
            "archive_start_time": bool(segment.get("archive_start_time", False)),
            "archive_motion_value": bool(segment.get("archive_motion_value", False)),
            "archive_rate_value": bool(segment.get("archive_rate_value", False)),
            "gantt_travel_input_mode": str(segment.get("gantt_travel_input_mode", "travel")),
            "exchange_extra": exchange_extra,
        }
        motions.append({
            "id": f"motion_{drive_id}_{seg_index + 1}",
            "name": internal_segment["name"],
            "joint_id": joint_id,
            "position_0_percent": cursor,
            "position_100_percent": end,
            "mode": "mapping" if profile == "mapping" else "ease",
            "rated_speed": speed,
            "enabled": bool(raw.get("enabled", True)),
            "exchange_drive_id": drive_id,
            "exchange_drive_name": drive_name,
            "exchange_drive_role": str(raw.get("fivebar_role", raw.get("role", "")) or ""),
            "exchange_drive_extra": {key: copy.deepcopy(value) for key, value in raw.items() if key not in {"segments", "exchange_extra"}},
            "exchange_segment": internal_segment,
            "exchange_segment_order": seg_index,
            "exchange_motion_snapshot": {
                "name": internal_segment["name"],
                "joint_id": joint_id,
                "position_0_percent": cursor,
                "position_100_percent": end,
                "mode": "mapping" if profile == "mapping" else "ease",
                "rated_speed": speed,
                "enabled": bool(raw.get("enabled", True)),
            },
        })
        cursor = end
    if not motions:
        motions = [{
            "id": f"motion_{drive_id}",
            "name": drive_name,
            "joint_id": joint_id,
            "position_0_percent": base0,
            "position_100_percent": base100,
            "mode": "ease",
            "rated_speed": 30.0,
            "enabled": bool(raw.get("enabled", True)),
            "exchange_drive_id": drive_id,
            "exchange_drive_name": drive_name,
            "exchange_drive_role": str(raw.get("fivebar_role", raw.get("role", "")) or ""),
            "exchange_drive_extra": {key: copy.deepcopy(value) for key, value in raw.items() if key not in {"segments", "exchange_extra"}},
            "exchange_motion_snapshot": {
                "name": drive_name,
                "joint_id": joint_id,
                "position_0_percent": base0,
                "position_100_percent": base100,
                "mode": "ease",
                "rated_speed": 30.0,
                "enabled": bool(raw.get("enabled", True)),
            },
        }]
    return {
        "id": f"part_{drive_id}" if not drive_id.startswith("part_") else drive_id,
        "name": drive_name,
        "enabled": bool(raw.get("enabled", True)),
        "motions": motions,
    }


def import_modeling_exchange(data: dict[str, Any], *, import_measurements: bool = True) -> dict[str, Any]:
    if not is_modeling_exchange(data):
        raise ValueError("这不是建模信息 JSON（format 必须为 mujoco_modeling_exchange）")
    snapshot = data.get("application_state") if isinstance(data.get("application_state"), dict) else {}
    hierarchy = data.get("hierarchical_modeling") if isinstance(data.get("hierarchical_modeling"), dict) else {}
    root_id = str(hierarchy.get("root_id") or snapshot.get("root_id") or "root")
    raw_layers = list(hierarchy.get("layers", []) or [])
    from_exchange = bool(raw_layers)
    if not raw_layers:
        raw_layers = [
            item for item in list(snapshot.get("layers", []) or [])
            if isinstance(item, dict) and str(item.get("id", "")) != root_id
        ]
    layers = []
    for item in raw_layers:
        if not isinstance(item, dict):
            continue
        try:
            layers.append(_import_layer(item, root_id, from_exchange))
        except Exception:
            continue
    _layer_id_map, joint_id_map = _repair_import_structure(layers)
    points_are_layer_local = _exchange_points_are_layer_local(data)
    reference_origins_mm = _layer_reference_origins_mm(layers)
    if points_are_layer_local:
        for layer in layers:
            layer_id = str(layer.get("id"))
            for joint in layer.get("joints", []):
                if str(joint.get("type", "rotation")) == "rotation":
                    joint["point"] = _vector_text(
                        _point_add_origin(joint.get("point", "0, 0, 0"), layer_id, reference_origins_mm)
                    )

    choice_to_joint_id: dict[str, str] = {}
    joints: dict[str, dict[str, Any]] = {}
    for layer in layers:
        for joint in layer.get("joints", []):
            joint_id = str(joint.get("id"))
            joints[joint_id] = joint
            choice_to_joint_id[f"{layer.get('name')}/{joint.get('name')}"] = joint_id
            choice_to_joint_id[f"{layer.get('id')}/{joint.get('name')}"] = joint_id
    for joint_id, joint in joints.items():
        if sum(1 for candidate in joints.values() if candidate.get("name") == joint.get("name")) == 1:
            choice_to_joint_id[str(joint.get("name"))] = joint_id

    latest_drives = _repair_drive_rows(_extract_latest_drives(data), joint_id_map)
    activity_parts = [
        item
        for i, raw in enumerate(latest_drives)
        if (item := _drive_to_activity(raw, choice_to_joint_id, joints, i)) is not None
    ]

    latest_block = None
    drive_config = data.get("drive_configuration") if isinstance(data.get("drive_configuration"), dict) else {}
    if isinstance(drive_config.get("latest_version"), dict):
        latest_block = drive_config.get("latest_version")
    snapshot_versions = snapshot.get("drive_versions") if isinstance(snapshot.get("drive_versions"), dict) else {}
    if latest_block is None and isinstance(snapshot_versions.get("latest"), dict):
        latest_block = snapshot_versions.get("latest")
    variables = _variables((latest_block or {}).get("custom_variables", snapshot.get("custom_variables", [])))

    vzext = data.get("vz_extensions") if isinstance(data.get("vz_extensions"), dict) else {}
    closures = _extract_closures(data)
    if points_are_layer_local:
        for closure in closures:
            for side in ("a", "b"):
                endpoint = closure[f"endpoint_{side}"]
                endpoint["point_mm"] = _point_add_origin(
                    endpoint["point_mm"], endpoint["layer_id"], reference_origins_mm,
                )

    model = {
        "id": "temporary",
        "name": str(data.get("model_name") or snapshot.get("model_name") or "导入建模信息").strip() or "导入建模信息",
        "description": "由 mujoco_modeling_exchange 建模信息 JSON 导入",
        "revision": 1,
        "assets": [],
        "variables": variables,
        "simulation": {
            "start_time": _float(snapshot.get("sim_start_time"), 0.0),
            "end_time": _float(snapshot.get("sim_end_time"), 6.0),
            "timestep": max(_float(snapshot.get("sim_timestep"), 0.01), 1e-6),
        },
        "render_scene": copy.deepcopy(vzext.get("render_scene", {})) if isinstance(vzext.get("render_scene"), dict) else {},
        "layers": layers,
        "kinematic_closures": closures,
        "activity_parts": activity_parts,
        "drives": [],
        "presets": copy.deepcopy(vzext.get("presets", [])) if isinstance(vzext.get("presets"), list) else [],
        "memories": copy.deepcopy(vzext.get("memories", [])) if isinstance(vzext.get("memories"), list) else [],
    }

    mesh_rendering = vzext.get("mesh_rendering") if isinstance(vzext.get("mesh_rendering"), dict) else {}
    for layer in model["layers"]:
        for mesh in layer.get("meshes", []):
            source_mesh_id = str(mesh.pop("_exchange_source_id", "") or mesh.get("id"))
            extra = mesh_rendering.get(source_mesh_id)
            if not isinstance(extra, dict) and source_mesh_id != str(mesh.get("id")):
                extra = mesh_rendering.get(str(mesh.get("id")))
            if isinstance(extra, dict):
                for key in ("render_config", "material_slots"):
                    if key in extra:
                        mesh[key] = copy.deepcopy(extra[key])

    normalized = validate_model(model)
    normalized["_modeling_exchange"] = {
        "format": FORMAT,
        "source_schema_version": str(data.get("schema_version", "1.0")),
        "exported_by": copy.deepcopy(data.get("exported_by", {})),
        "model_folder_path": str(
            data.get("model_folder_path")
            or data.get("stl_obj_folder")
            or snapshot.get("stl_folder")
            or ""
        ),
        "output_directory": str(data.get("output_directory") or snapshot.get("last_output_dir") or ""),
        "template_scene_path": str(snapshot.get("template_scene_path", "") or ""),
        "latest_drives": copy.deepcopy(latest_drives),
        "measurement_configuration": (
            copy.deepcopy(
                data.get(
                    "measurement_configuration",
                    {"pairs": copy.deepcopy(snapshot.get("pairs", []))},
                )
            )
            if import_measurements
            else {"pairs": []}
        ),
        "studio_extensions": copy.deepcopy(data.get("studio_extensions", {})),
        "activity_fingerprint": _activity_fingerprint(normalized.get("activity_parts", [])),
    }
    return normalized
