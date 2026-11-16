from __future__ import annotations

import re
from typing import Any

from .models import (
    DistancePairSpec,
    DriveSegmentSpec,
    DriveSpec,
    FilterRule,
    JointSpec,
    LayerSpec,
    MeshSpec,
    OptimizationSettings,
    ProjectSpec,
    ResultAxisSpec,
    ResultCurveSpec,
    ResultLayout,
    SimulationSettings,
    VariableRange,
    strip_distance_pair_variables,
)


def is_legacy_project(data: dict[str, Any]) -> bool:
    return "root_id" in data or "stl_folder" in data or any(
        isinstance(item, dict) and ("color_text" in item or "file_name" in item)
        for item in data.get("layers", [])
    )


def migrate_legacy_project(data: dict[str, Any]) -> ProjectSpec:
    """Migrate a V21.5-style complete model JSON into the Studio schema.

    Cross-generation contract (V21.5 -> Studio):
    - joints: only rotation / translation / crank are imported;
    - motion profiles: trapezoid, external_csv and drive_mapping are imported;
    - distance pairs: only name + selected mesh objects are imported;
    - custom variables are first-class interoperable data;
    - unsupported motion profiles are skipped and reported as non-fatal warnings.

    The source payload is retained in metadata for diagnostics.  Local paths and
    generation-specific simulation/UI/optimization settings are intentionally
    not promoted into the Studio runtime contract, except simulation end time.
    """
    if not is_legacy_project(data):
        return ProjectSpec.model_validate(data)

    warnings: list[str] = []
    ignored_joint_types: list[dict[str, str]] = []
    ignored_motion_profiles: list[dict[str, str]] = []

    root_id = str(data.get("root_id", "root"))
    layers: list[LayerSpec] = []
    joint_choices: dict[str, str] = {}
    unqualified: dict[str, list[str]] = {}
    for raw_layer in data.get("layers", []):
        if not isinstance(raw_layer, dict) or str(raw_layer.get("id", "")) == root_id:
            continue
        layer_id = str(raw_layer.get("id") or LayerSpec().id)
        layer_name = str(raw_layer.get("name") or layer_id)
        joints: list[JointSpec] = []
        for raw_joint in raw_layer.get("joints", []):
            if not isinstance(raw_joint, dict):
                continue
            raw_joint_type = str(raw_joint.get("joint_type", raw_joint.get("type", "rotation")) or "rotation")
            joint_type = _joint_type(raw_joint_type)
            if joint_type is None:
                ignored_joint_types.append({"layer": layer_name, "joint": str(raw_joint.get("name", "")), "type": raw_joint_type})
                continue
            excluded = {
                "id", "name", "type", "joint_type", "point", "point_text", "axis", "axis_text",
                "reverse", "invert_axis", "limited", "range",
            }
            exchange_extra = raw_joint.get("exchange_extra", {}) if isinstance(raw_joint.get("exchange_extra"), dict) else {}
            studio_extra = exchange_extra.get("mujoco_studio", {}) if isinstance(exchange_extra.get("mujoco_studio"), dict) else {}
            joint = JointSpec(
                id=str(raw_joint.get("exchange_id") or raw_joint.get("id") or JointSpec().id),
                name=str(raw_joint.get("name", "joint1")),
                type=joint_type,
                point=_point(raw_joint.get("point_text", raw_joint.get("point", "0, 0, 0"))),
                axis=str(raw_joint.get("axis_text", raw_joint.get("axis", "0, 0, 1"))),
                crank_center=_point(raw_joint.get("crank_center_text", raw_joint.get("crank_center", "0, 0, 0"))),
                crank_end=_point(raw_joint.get("crank_end_text", raw_joint.get("crank_end", "0, 10, 0"))),
                rod_end=_point(raw_joint.get("rod_end_text", raw_joint.get("rod_end", "30, 0, 0"))),
                slide_axis=str(raw_joint.get("slide_axis_text", raw_joint.get("slide_axis", "1, 0, 0"))),
                reverse=bool(raw_joint.get("invert_axis", raw_joint.get("reverse", False))),
                limited=bool(studio_extra.get("limited", raw_joint.get("limited", False))),
                range=list(studio_extra.get("range", raw_joint.get("range", [-180.0, 180.0]))),
                damping=max(_float(studio_extra.get("damping", raw_joint.get("damping", 0.1)), 0.1), 0.0),
                armature=max(_float(studio_extra.get("armature", raw_joint.get("armature", 0.01)), 0.01), 0.0),
                frictionloss=max(_float(studio_extra.get("frictionloss", raw_joint.get("frictionloss", 0.0)), 0.0), 0.0),
                stiffness=max(_float(studio_extra.get("stiffness", raw_joint.get("stiffness", 0.0)), 0.0), 0.0),
                spring_reference=_float(studio_extra.get("spring_reference", raw_joint.get("spring_reference", 0.0)), 0.0),
                parameters={key: value for key, value in raw_joint.items() if key not in excluded and key not in {"exchange_extra", "exchange_id"}},
            )
            joints.append(joint)
            joint_choices[f"{layer_name}/{joint.name}"] = joint.id
            joint_choices[f"{layer_id}/{joint.name}"] = joint.id
            unqualified.setdefault(joint.name, []).append(joint.id)
        meshes = []
        for item in raw_layer.get("meshes", []):
            if not isinstance(item, dict):
                continue
            filename = item.get("filename", item.get("file_name", item.get("file", "")))
            if not filename:
                continue
            opacity = _float(item.get("opacity", item.get("opacity_text", 1)), 1.0)
            raw_color = item.get("rgba", item.get("color", item.get("color_text", "")))
            meshes.append(MeshSpec(
                id=str(item.get("exchange_id") or item.get("id") or MeshSpec(filename=str(filename)).id),
                filename=str(filename),
                collision=bool(item.get("collision", item.get("collide", False))),
                rgba=_rgba_with_opacity(str(raw_color), opacity) if str(raw_color or "").strip() else "",
                opacity=opacity,
                mass_kg=_optional_positive(item.get("mass_kg", item.get("mass"))),
            ))
        parent_id = raw_layer.get("parent_id")
        layers.append(LayerSpec(
            id=layer_id,
            name=layer_name,
            parent_id="root" if parent_id in {None, "", root_id} else str(parent_id),
            active=bool(raw_layer.get("active", True)),
            color=_rgba_with_opacity(str(raw_layer.get("color_text", raw_layer.get("color", "0.72 0.75 0.80 1"))), 1.0),
            position_mm=list(raw_layer.get("position_mm", [0.0, 0.0, 0.0])),
            mass_kg=_optional_positive(raw_layer.get("mass_kg", raw_layer.get("mass"))),
            meshes=meshes,
            joints=joints,
        ))
    for name, ids in unqualified.items():
        if len(ids) == 1:
            joint_choices[name] = ids[0]

    drives: list[DriveSpec] = []
    for raw_drive in data.get("drives", []):
        if not isinstance(raw_drive, dict):
            continue
        choice = str(raw_drive.get("target_joint_choice", raw_drive.get("joint_name", raw_drive.get("joint_choice", ""))))
        joint_id = str(raw_drive.get("joint_id", "")) or joint_choices.get(choice, "")
        # Drives attached to unsupported/ignored joint types are ignored with the joint.
        if not joint_id:
            continue
        segments: list[DriveSegmentSpec] = []
        raw_segments = list(raw_drive.get("segments", []) or [])
        for raw_segment in raw_segments:
            if not isinstance(raw_segment, dict):
                continue
            raw_profile = str(raw_segment.get("motion_profile", raw_segment.get("profile", "trapezoid")) or "trapezoid")
            profile = _profile(raw_profile)
            if profile is None:
                item = {
                    "drive": str(raw_drive.get("name", "")),
                    "segment": str(raw_segment.get("name", "")),
                    "profile": raw_profile,
                }
                ignored_motion_profiles.append(item)
                warnings.append(
                    f"驱动“{item['drive']}”运动段“{item['segment']}”使用不兼容运动函数 {raw_profile}，二代已忽略该运动段。"
                )
                continue
            if profile == "mapping":
                point_rows = raw_segment.get("mapping_values", raw_segment.get("points", []))
            elif profile == "external_csv":
                point_rows = raw_segment.get("external_csv_values", raw_segment.get("points", []))
            else:
                point_rows = []
            points = _legacy_points(point_rows)
            mapping_choice = str(raw_segment.get("mapping_source_joint_choice", ""))
            travel_default = points[-1][1] if points else 0.0
            mapping_csv_path = str(raw_segment.get("mapping_csv_path", "") or "")
            external_csv_path = str(raw_segment.get("external_csv_path", "") or "")
            exchange_extra = raw_segment.get("exchange_extra", {}) if isinstance(raw_segment.get("exchange_extra"), dict) else {}
            studio_extra = exchange_extra.get("mujoco_studio", {}) if isinstance(exchange_extra.get("mujoco_studio"), dict) else {}
            segment = DriveSegmentSpec(
                id=str(raw_segment.get("id") or DriveSegmentSpec().id),
                name=str(raw_segment.get("name", f"seg{len(segments) + 1}")),
                start_mode="reference" if raw_segment.get("start_time_mode") in {"ref", "reference"} else "direct",
                start=_number_expression(raw_segment.get("start_time_value", raw_segment.get("start", 0)), 0.0),
                reference=_legacy_reference(raw_segment),
                reference_boundary=_boundary(raw_segment.get("ref_boundary", "end")),
                mode="speed" if raw_segment.get("mode") == "speed" else "duration",
                duration=_number_expression(raw_segment.get("duration"), 1.0),
                speed=_number_expression(raw_segment.get("max_speed", raw_segment.get("speed")), 30.0),
                travel=_number_expression(raw_segment.get("travel"), travel_default),
                profile=profile,
                ease_in=bool(raw_segment.get("enable_ease_in", raw_segment.get("enable_soft_start", True))),
                ease_out=bool(raw_segment.get("enable_ease_out", raw_segment.get("enable_soft_stop", True))),
                easing_mode=str(studio_extra.get("easing_mode", "time")) if str(studio_extra.get("easing_mode", "time")) in {"time", "acceleration"} else "time",
                ease_in_time=studio_extra.get("ease_in_time"),
                ease_out_time=studio_extra.get("ease_out_time"),
                ease_in_acceleration=_number_expression(studio_extra.get("ease_in_acceleration"), 150.0),
                ease_out_acceleration=_number_expression(studio_extra.get("ease_out_acceleration"), 150.0),
                acceleration_time=_number_expression(raw_segment.get("acceleration_time", studio_extra.get("acceleration_time")), 0.2),
                points=points,
                # CSV point tables are model data. Machine-local source paths are
                # retained only as display provenance, never as a runtime dependency.
                csv_path="",
                external_csv_name=_basename(external_csv_path),
                external_csv_header=str(raw_segment.get("external_csv_header", "") or ""),
                external_csv_source_metric=str(raw_segment.get("external_csv_source_metric", "") or ""),
                mapping_source_joint_id=joint_choices.get(mapping_choice, ""),
                mapping_csv_name=_basename(mapping_csv_path) or str(raw_segment.get("mapping_csv_name", "") or ""),
                mapping_point_count=len(points) if profile == "mapping" else 0,
                exchange_extra={"legacy_v21_5": {
                    key: value for key, value in raw_segment.items()
                    if key not in {"mapping_values", "external_csv_values"}
                }},
            )
            segments.append(segment)
        # If a drive had segments and every one was unsupported, ignore the drive too.
        if raw_segments and not segments:
            continue
        drive_extra = raw_drive.get("exchange_extra", {}) if isinstance(raw_drive.get("exchange_extra"), dict) else {}
        studio_drive_extra = drive_extra.get("mujoco_studio", {}) if isinstance(drive_extra.get("mujoco_studio"), dict) else {}
        drives.append(DriveSpec(
            id=str(raw_drive.get("id") or DriveSpec(joint_id=joint_id).id),
            name=str(raw_drive.get("name", f"act{len(drives) + 1}")),
            joint_id=joint_id,
            role=str(raw_drive.get("fivebar_role", raw_drive.get("role", ""))),
            enabled=bool(raw_drive.get("enabled", True)),
            dynamic_kp=max(_float(studio_drive_extra.get("dynamic_kp", 100.0), 100.0), 1e-12),
            dynamic_kv=max(_float(studio_drive_extra.get("dynamic_kv", 20.0), 20.0), 0.0),
            dynamic_lock_force=max(_float(studio_drive_extra.get("dynamic_lock_force", 2000.0), 2000.0), 0.0),
            segments=segments,
        ))

    # Cross-generation distance-pair contract intentionally includes only the
    # pair name and selected mesh objects. Studio-native sampling values remain defaults.
    pairs = []
    for index, item in enumerate(data.get("pairs", data.get("distance_pairs", []))):
        if not isinstance(item, dict):
            continue
        pairs.append(DistancePairSpec(
            id=str(item.get("id") or DistancePairSpec().id),
            name=str(item.get("name", f"distance{index + 1}")),
            objects_a=list(item.get("objects_a", [])),
            objects_b=list(item.get("objects_b", [])),
        ))

    variables = strip_distance_pair_variables(
        _legacy_variables(data.get("custom_variables", data.get("variables", {}))),
        (pair.name for pair in pairs),
    )
    # Optimization is generation-specific and intentionally outside the direct
    # model-JSON contract.  Importing V21 optimization rows can rewrite drive
    # expressions, so Studio keeps its own defaults here.
    optimization = OptimizationSettings()
    result_layout = _legacy_result_layout(data, layers, pairs, drives)
    project = ProjectSpec(
        schema_version=5,
        name=str(data.get("model_name", data.get("project_name", data.get("name", "Migrated V21.5 model")))) or "Migrated V21.5 model",
        layers=layers,
        drives=drives,
        distance_pairs=pairs,
        variables=variables,
        # Per the model-JSON interop contract, only simulation end time is shared.
        simulation=SimulationSettings(end_time=_float(data.get("sim_end_time"), 12.0)),
        optimization=optimization,
        result_layout=result_layout,
        metadata={
            "legacy_format": "mujoco_xml_tool_v21_5_model_json",
            "legacy_source": data,
            "legacy_ui_settings": data.get("ui_settings", {}),
            "legacy_drive_versions": data.get("drive_versions", {}),
            "model_json_interop": {
                "contract": "V21.5<->V2.11.7",
                "ignored_joint_types": ignored_joint_types,
                "ignored_motion_profiles": ignored_motion_profiles,
                "warnings": warnings,
            },
        },
    )
    return project

def legacy_ui_state(data: dict[str, Any]) -> dict[str, Any]:
    settings = data.get("ui_settings", {}) if isinstance(data.get("ui_settings"), dict) else {}
    return {
        "legacy": settings,
        "drives": {"two_columns": int(settings.get("drive_per_column", 3) or 3) > 1},
        "results": {
            "gantt_font_size": int(settings.get("timeline_font_size", 10) or 10),
        },
    }


def _legacy_optimization(data: dict[str, Any], drives: list[DriveSpec], variables: dict[str, Any]) -> OptimizationSettings:
    ranges: list[VariableRange] = []
    drive_lookup = {drive.name: drive for drive in drives}
    for raw in data.get("opt_variables", []):
        name = str(raw.get("parameter_name") or raw.get("name") or f"variable_{len(ranges) + 1}")
        ranges.append(VariableRange(
            name=name,
            minimum=_float(raw.get("min_value"), 0.0),
            maximum=_float(raw.get("max_value"), 1.0),
            step=max(_float(raw.get("step_value"), 0.1), 1e-12),
        ))
        match = re.fullmatch(r"([^/.]+)[/.](startTime|Duration|Speed|Stroke)(\d+)", name, re.IGNORECASE)
        if not match:
            continue
        drive = drive_lookup.get(match.group(1))
        index = int(match.group(3)) - 1
        if not drive or not 0 <= index < len(drive.segments):
            continue
        segment = drive.segments[index]
        field = {"starttime": "start", "duration": "duration", "speed": "speed", "stroke": "travel"}[match.group(2).lower()]
        variables.setdefault(name, getattr(segment, field))
        setattr(segment, field, name)
    objectives = data.get("opt_objectives", [])
    objective = str(objectives[0].get("variable_name", "EndTime")) if objectives else "EndTime"
    goal = str(objectives[0].get("goal", "min")) if objectives else "min"
    filters = [FilterRule(
        variable=str(item.get("variable_name", "")),
        minimum=_optional_float(item.get("min_value")),
        maximum=_optional_float(item.get("max_value")),
    ) for item in data.get("opt_filter_conditions", []) if item.get("variable_name")]
    return OptimizationSettings(
        mode="grid",
        trials=max(int(_float(data.get("opt_batch_count"), 1000)), 1),
        variables=ranges,
        filters=filters,
        objective=objective,
        direction="max" if goal == "max" else "min",
    )


def _legacy_result_layout(
    data: dict[str, Any], layers: list[LayerSpec], pairs: list[DistancePairSpec], drives: list[DriveSpec],
) -> ResultLayout:
    """Map the V21.5 result-axis names, selected curve sources and basic metrics."""
    raw = data.get("result_curve_layout_v19_2") or data.get("ui_settings", {}).get("result_axis_layout_v19") or {}
    choices = {f"{layer.name}/{joint.name}": joint.id for layer in layers for joint in layer.joints}
    pair_ids = {pair.name: pair.id for pair in pairs}
    drive_ids = {drive.name: drive.id for drive in drives}
    metric_map = {"位移": "raw", "速度": "d1", "加速度": "d2", "距离": "raw"}
    axes: list[ResultAxisSpec] = []
    for axis in list(raw.get("drive_axes", [])) + list(raw.get("pair_axes", [])):
        if not isinstance(axis, dict):
            continue
        curves = []
        for item in axis.get("curves", []):
            if not isinstance(item, dict):
                item = {"name": item}
            name = str(item.get("name", ""))
            if name in choices:
                source = f"joint:{choices[name]}"
            elif name in drive_ids:
                source = f"drive:{drive_ids[name]}"
            elif name in pair_ids:
                source = f"pair:{pair_ids[name]}"
            else:
                source = ""
            metric = str(item.get("metric", "位移") or "位移")
            curves.append(ResultCurveSpec(source=source, label=name or "曲线", operation=metric_map.get(metric, "raw")))
        operation = str(axis.get("operation", ""))
        axes.append(ResultAxisSpec(
            name=str(axis.get("title", "坐标系")),
            combine="sum" if "求和" in operation else ("difference" if "差" in operation else "none"),
            keep_operands="保留全部" in str(axis.get("keep_mode", "")) or "保留" in str(axis.get("keep_mode", "")),
            add_to_gantt=bool(axis.get("add_to_gantt", False)),
            curves=curves,
        ))
    height = int(_float(data.get("ui_settings", {}).get("result_axis_height_px"), 220))
    return ResultLayout(axes=axes, height=max(50, min(height, 1000)))

def _legacy_variables(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {str(item.get("name")): item.get("value", 0) for item in value if isinstance(item, dict) and item.get("name")}


def _joint_type(value: object) -> str | None:
    value = str(value)
    return value if value in {"rotation", "translation", "crank"} else None


def _profile(value: object) -> str | None:
    # Cross-generation contract: preserve only profiles with verified equivalent
    # runtime semantics in both generations.
    return {
        "trapezoid": "s_curve",
        "external_csv": "external_csv",
        "drive_mapping": "mapping",
    }.get(str(value))


def _legacy_points(rows: Any) -> list[list[float]]:
    points: list[list[float]] = []
    for item in list(rows or []):
        if isinstance(item, dict):
            x, y = item.get("source", item.get("time")), item.get("value", item.get("target"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            x, y = item[0], item[1]
        else:
            continue
        try:
            points.append([float(x), float(y)])
        except (TypeError, ValueError):
            continue
    return points


def _basename(value: Any) -> str:
    text = str(value or "").strip()
    return re.split(r"[\\/]", text)[-1] if text else ""


def _legacy_reference(segment: dict[str, Any]) -> str:
    drive = str(segment.get("ref_drive_name", ""))
    name = str(segment.get("ref_segment_name", ""))
    return f"{drive}/{name}" if drive and name else ""


def _boundary(value: Any) -> str:
    return str(value) if str(value) in {"start", "end"} else "end"


def _point(value: Any) -> str:
    return str(value).replace("Point", "").strip().strip("()").strip()


def _rgba_with_opacity(value: str, opacity: float) -> str:
    text = str(value or "").strip()
    if text.startswith("#") and len(text) in {7, 9}:
        try:
            red = int(text[1:3], 16) / 255.0
            green = int(text[3:5], 16) / 255.0
            blue = int(text[5:7], 16) / 255.0
            alpha = int(text[7:9], 16) / 255.0 if len(text) == 9 else 1.0
            return f"{red:.6g} {green:.6g} {blue:.6g} {alpha:.6g}"
        except ValueError:
            pass
    parts = [item for item in re.split(r"[\s,]+", text) if item]
    if len(parts) < 3:
        parts = ["0.72", "0.75", "0.80"]
    # Preserve base alpha and opacity as separate fields.  The XML generator
    # applies opacity once, avoiding double multiplication after a round-trip.
    alpha = parts[3] if len(parts) >= 4 else "1"
    return " ".join(parts[:3] + [alpha])


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or str(value).strip() == "":
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _optional_float(value: Any) -> float | None:
    return None if value is None or str(value).strip() == "" else _float(value)


def _optional_positive(value: Any) -> float | None:
    result = _optional_float(value)
    return result if result is not None and result > 0 else None


def _number_expression(value: Any, default: float) -> Any:
    return default if value is None or str(value).strip() == "" else value
