from __future__ import annotations

import copy
import math
import re
from datetime import datetime, timezone
from typing import Any

from .models import (
    DriveSegmentSpec,
    DriveSpec,
    DistancePairSpec,
    KinematicClosureSpec,
    JointSpec,
    LayerSpec,
    MeshSpec,
    ProjectLifecycle,
    ProjectSpec,
    SimulationSettings,
    new_id,
    strip_distance_pair_variables,
)


FORMAT = "mujoco_modeling_exchange"
SCHEMA_VERSION = "2.1"


def is_modeling_exchange(data: Any) -> bool:
    return isinstance(data, dict) and data.get("format") == FORMAT


def export_modeling_exchange(
    project: ProjectSpec, application_version: str, *, include_measurements: bool = True,
) -> dict[str, Any]:
    """Build the old/new-tool neutral modeling document used by V21.4.3."""
    joint_choice_by_id = {
        joint.id: f"{layer.name}/{joint.name}"
        for layer in project.layers
        for joint in layer.joints
    }
    # A mapped segment may reference another drive in Studio as ``drive:<id>``.
    # Expose that drive's target-joint choice as a neutral exchange alias so V21
    # and VZ readers can preserve the mapping relationship as a joint choice.
    joint_choice_by_id.update({
        f"drive:{drive.id}": joint_choice_by_id.get(drive.joint_id, "")
        for drive in project.drives
    })
    joint_type_by_id = {
        joint.id: joint.type
        for layer in project.layers
        for joint in layer.joints
    }
    layer_rows: list[dict[str, Any]] = []
    old_layers: list[dict[str, Any]] = [_old_root_layer()]
    for layer in project.layers:
        layer_rgba = _rgba(layer.color)
        models: list[dict[str, Any]] = []
        old_meshes: list[dict[str, Any]] = []
        for index, mesh in enumerate(layer.meshes):
            inherits_layer_color = not str(mesh.rgba or "").strip()
            base_rgba = _rgba(layer.color if inherits_layer_color else mesh.rgba)
            opacity = _clamp(_float(mesh.opacity, 1.0))
            effective = list(base_rgba)
            effective[3] = _clamp(effective[3] * opacity)
            models.append({
                "id": mesh.id,
                "index": index,
                "file_name": mesh.filename,
                "name": mesh.filename,
                "collision": bool(mesh.collision),
                "mass_kg": mesh.mass_kg,
                "color": {
                    "rgba": base_rgba,
                    "opacity_alpha": opacity,
                    "effective_rgba": effective,
                    "inherits_layer_color": inherits_layer_color,
                },
            })
            old_meshes.append({
                "file_name": mesh.filename,
                "name": mesh.filename,
                "collision": bool(mesh.collision),
                "color_text": "" if inherits_layer_color else _rgba_text(mesh.rgba),
                "opacity_text": _number_text(opacity),
            })
        joints = [_export_joint(joint, layer, index) for index, joint in enumerate(layer.joints)]
        layer_rows.append({
            "id": layer.id,
            "name": layer.name,
            "parent_id": layer.parent_id or "root",
            "depth": _layer_depth(project.layers, layer),
            "active": bool(layer.active),
            "position_mm": list(layer.position_mm),
            "mass_kg": layer.mass_kg,
            "color_rgba": layer_rgba,
            "alpha": layer_rgba[3],
            "models": models,
            "joints": joints,
        })
        old_layers.append({
            "id": layer.id,
            "name": layer.name,
            "parent_id": layer.parent_id or "root",
            "color_text": _rgba_text(layer.color),
            "active": bool(layer.active),
            "position_mm": list(layer.position_mm),
            "mass_kg": layer.mass_kg,
            "meshes": old_meshes,
            "joints": [_old_snapshot_joint(joint) for joint in layer.joints],
        })

    old_drives = [
        _old_drive(drive, joint_choice_by_id, project)
        for drive in project.drives
    ]
    # Preserve Studio-only logical mapping semantics outside the strict V21.4.x
    # AppState snapshots.  The native project schema stays unchanged: direct
    # drive references continue to use the compatible ``drive:<id>`` encoding.
    studio_extensions = {
        # Studio-only metadata; older exchange readers safely ignore it.
        "project_category": project.category,
        "logical_drive_ids": [
            drive.id for drive in project.drives if not str(drive.joint_id or "").strip()
        ],
        "mapping_source_drive_by_segment": {
            segment.id: str(segment.mapping_source_joint_id)[6:]
            for drive in project.drives
            for segment in drive.segments
            if str(segment.mapping_source_joint_id or "").startswith("drive:")
        },
    }
    variables = [{"name": name, "value": value} for name, value in project.variables.items()]
    latest = {
        "drives": copy.deepcopy(old_drives),
        "custom_variables": copy.deepcopy(variables),
    }
    measurement_pairs = [_export_pair(pair) for pair in project.distance_pairs]
    application_state = {
        "model_name": project.name,
        "root_id": "root",
        "stl_folder": project.mesh_root,
        "template_scene_path": project.template_scene,
        "last_output_dir": project.output_dir,
        "sim_timestep": _number_text(project.simulation.timestep),
        "sim_start_time": _number_text(project.simulation.start_time),
        "sim_end_time": _number_text(project.simulation.end_time),
        "layers": old_layers,
        "drives": copy.deepcopy(old_drives),
        "custom_variables": copy.deepcopy(variables),
        "drive_versions": {"latest": copy.deepcopy(latest)},
        "latest_drive_version_name": "latest",
        # Keep the legacy AppState spelling as well as the dedicated exchange
        # section.  V21.4.x uses this snapshot when importing exchange files.
        "pairs": copy.deepcopy(measurement_pairs) if include_measurements else [],
        "opt_variables": [],
        "opt_filter_conditions": [],
        "ui_settings": {},
    }
    drive_rows = []
    for index, drive in enumerate(project.drives):
        choice = joint_choice_by_id.get(drive.joint_id, "")
        rich_drive = _old_drive(drive, joint_choice_by_id, project)
        drive_row = copy.deepcopy(rich_drive)
        drive_row.update({
            "id": drive.id,
            "index": index,
            "name": drive.name,
            "type": joint_type_by_id.get(drive.joint_id, ""),
            "target_joint": {
                "choice": choice,
                "id": drive.joint_id,
                "joint_type": joint_type_by_id.get(drive.joint_id, ""),
                "resolution": "resolved" if choice else "unresolved",
            },
            "target_joint_choice": choice,
            "fivebar_role": drive.role,
            "enabled": bool(drive.enabled),
            "dynamic_kp": drive.dynamic_kp,
            "dynamic_kv": drive.dynamic_kv,
            "dynamic_lock_force": drive.dynamic_lock_force,
            "segments": [
                {**segment, "index": segment_index}
                for segment_index, segment in enumerate(rich_drive["segments"])
            ],
        })
        drive_rows.append(drive_row)
    closure_rows = [_closure_row(item) for item in project.kinematic_closures]
    payload = {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "exported_by": {"software": "MuJoCo Studio", "version": application_version},
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "model_name": project.name,
        "model_folder_path": project.mesh_root,
        "stl_obj_folder": project.mesh_root,
        "output_directory": project.output_dir,
        "hierarchical_modeling": {
            "root_id": "root",
            "relation_field": "parent_id",
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
        "measurement_configuration": {
            "pairs": copy.deepcopy(measurement_pairs),
        },
        "kinematic_closure_configuration": {
            "closures": copy.deepcopy(closure_rows),
        },
        # Kept outside legacy AppState/drive snapshots so older V21.4.x tools
        # can ignore it safely while Studio can losslessly round-trip logical drives.
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
    }
    if not include_measurements:
        payload.pop("measurement_configuration", None)
    return payload


def import_modeling_exchange(
    data: dict[str, Any], *, import_measurements: bool = True,
) -> ProjectSpec:
    """Convert V21.3/V21.4 modeling exchange JSON into a Studio project."""
    if not is_modeling_exchange(data):
        raise ValueError("这不是建模信息 JSON（format 必须为 mujoco_modeling_exchange）")
    snapshot = data.get("application_state") if isinstance(data.get("application_state"), dict) else {}
    hierarchy = data.get("hierarchical_modeling") if isinstance(data.get("hierarchical_modeling"), dict) else {}
    root_id = str(hierarchy.get("root_id") or snapshot.get("root_id") or "root")
    raw_layers = list(hierarchy.get("layers", []) or [])
    if not raw_layers:
        raw_layers = [item for item in list(snapshot.get("layers", []) or []) if str(item.get("id", "")) != root_id]
    layers: list[LayerSpec] = []
    choice_to_joint_id: dict[str, str] = {}
    for raw in raw_layers:
        if not isinstance(raw, dict):
            continue
        try:
            layer = _import_layer(raw, root_id, from_exchange=bool(hierarchy.get("layers")))
        except Exception:
            # Modeling exchange is intentionally tolerant: a malformed layer must
            # not prevent the remaining hierarchy from being imported.
            continue
        layers.append(layer)
        for joint in layer.joints:
            choice_to_joint_id[f"{layer.name}/{joint.name}"] = joint.id
            choice_to_joint_id[f"{layer.id}/{joint.name}"] = joint.id
    for layer in layers:
        for joint in layer.joints:
            if sum(1 for item in layers for candidate in item.joints if candidate.name == joint.name) == 1:
                choice_to_joint_id[joint.name] = joint.id

    drive_config = data.get("drive_configuration") if isinstance(data.get("drive_configuration"), dict) else {}
    latest = drive_config.get("latest_version") if isinstance(drive_config.get("latest_version"), dict) else None
    if latest is None and isinstance(drive_config.get("latest"), dict):
        latest = drive_config.get("latest")
    snapshot_versions = snapshot.get("drive_versions") if isinstance(snapshot.get("drive_versions"), dict) else {}
    if latest is None and isinstance(snapshot_versions.get("latest"), dict):
        latest = snapshot_versions.get("latest")
    exchange_mode = str(drive_config.get("mode") or "").strip().lower()
    if exchange_mode in {"full", "full_fidelity", "rich"} and isinstance(drive_config.get("drives"), list):
        raw_drives = list(drive_config.get("drives", []) or [])
    else:
        raw_drives = drive_config.get("bindings") if isinstance(drive_config.get("bindings"), list) else []
    if not raw_drives:
        raw_drives = list(drive_config.get("drives", []) or [])
    if not raw_drives:
        raw_drives = list(drive_config.get("bindings", []) or [])
    if not raw_drives:
        raw_drives = list((latest or {}).get("drives", []) or [])
    if not raw_drives:
        raw_drives = list(snapshot.get("drives", []) or [])
    studio_extensions = data.get("studio_extensions") if isinstance(data.get("studio_extensions"), dict) else {}
    logical_drive_ids = {
        str(item) for item in list(studio_extensions.get("logical_drive_ids", []) or []) if str(item)
    }
    mapping_source_drive_by_segment = {
        str(key): str(value)
        for key, value in dict(studio_extensions.get("mapping_source_drive_by_segment", {}) or {}).items()
        if str(key) and str(value)
    }
    drives: list[DriveSpec] = []
    for raw in raw_drives:
        if not isinstance(raw, dict):
            continue
        try:
            drive = _import_drive(
                raw, choice_to_joint_id,
                allow_unbound=str(raw.get("id") or "") in logical_drive_ids,
            )
        except Exception:
            drive = None
        if drive is not None:
            drives.append(drive)
    for drive in drives:
        for segment in drive.segments:
            source_drive_id = mapping_source_drive_by_segment.get(segment.id, "")
            if source_drive_id:
                segment.mapping_source_joint_id = f"drive:{source_drive_id}"

    variables_raw = (latest or {}).get("custom_variables", snapshot.get("custom_variables", []))
    variables = _variables(variables_raw)
    model_name = str(data.get("model_name") or snapshot.get("model_name") or "导入建模信息").strip() or "导入建模信息"
    mesh_root = str(data.get("model_folder_path") or data.get("stl_obj_folder") or snapshot.get("stl_folder") or "")
    project_category = str(studio_extensions.get("project_category") or "").replace("\\", "/").strip(" /")
    if not project_category and mesh_root.startswith("@model_assets/"):
        reference_parts = [
            part.strip()
            for part in mesh_root[len("@model_assets/"):].replace("\\", "/").split("/")
            if part.strip()
        ]
        if len(reference_parts) >= 2:
            project_category = "/".join(reference_parts[:-1])
    if project_category:
        category_parts = [part.strip() for part in project_category.split("/")]
        if any(
            not part or part in {".", ".."}
            or re.search(r'[<>:"|?*\x00-\x1f]', part)
            for part in category_parts
        ):
            project_category = "None"
        else:
            project_category = "/".join(category_parts)
    else:
        project_category = "None"
    output_dir = str(data.get("output_directory") or snapshot.get("last_output_dir") or "")
    measurement = data.get("measurement_configuration") if isinstance(data.get("measurement_configuration"), dict) else {}
    raw_pairs = measurement.get("pairs")
    if not isinstance(raw_pairs, list):
        raw_pairs = snapshot.get("pairs", [])
    variables = strip_distance_pair_variables(
        variables,
        (item.get("name", "") for item in (raw_pairs or []) if isinstance(item, dict)),
    )
    distance_pairs: list[DistancePairSpec] = []
    if import_measurements:
        for index, item in enumerate(raw_pairs or []):
            if not isinstance(item, dict):
                continue
            try:
                distance_pairs.append(_import_pair(item, index))
            except Exception:
                continue
    try:
        closures = _extract_closures(data)
    except Exception:
        closures = []
    project = ProjectSpec(
        id=new_id("project"),
        name=model_name,
        description="由建模信息 JSON 导入",
        category=project_category,
        mesh_root=mesh_root,
        output_dir=output_dir,
        template_scene=str(snapshot.get("template_scene_path", "") or ""),
        layers=layers,
        drives=drives,
        distance_pairs=distance_pairs,
        kinematic_closures=closures,
        variables=variables,
        simulation=SimulationSettings(
            start_time=_float(snapshot.get("sim_start_time"), 0.0),
            end_time=_float(snapshot.get("sim_end_time"), 12.0),
            timestep=max(_float(snapshot.get("sim_timestep"), 0.01), 1e-9),
        ),
        lifecycle=ProjectLifecycle(status="checked_in"),
        metadata={
            "modeling_exchange_format": FORMAT,
            "modeling_exchange_schema_version": str(data.get("schema_version", "1.0")),
            "modeling_exchange_exported_by": copy.deepcopy(data.get("exported_by", {})),
            "modeling_exchange_source": copy.deepcopy(data),
        },
    )
    return project


def _closure_row(raw: Any) -> dict[str, Any]:
    value = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw or {})
    def endpoint(side: str) -> dict[str, Any]:
        item = value.get(f"endpoint_{side}") if isinstance(value.get(f"endpoint_{side}"), dict) else {}
        return {
            "layer_id": str(item.get("layer_id") or value.get(f"layer_{side}_id") or ""),
            "point_mm": _vector_values(item.get("point_mm", value.get(f"point_{side}_mm", [0, 0, 0]))),
        }
    return {
        "id": str(value.get("id") or new_id("closure")),
        "name": str(value.get("name") or "closure1"),
        "enabled": bool(value.get("enabled", True)),
        "kind": "point",
        "endpoint_a": endpoint("a"),
        "endpoint_b": endpoint("b"),
        "solve_joint_ids": [str(item) for item in list(value.get("solve_joint_ids", []) or []) if str(item)],
        "tolerance_mm": max(_float(value.get("tolerance_mm", 0.05), 0.05), 1e-9),
        "max_iterations": max(int(_float(value.get("max_iterations", 40), 40)), 1),
        "damping": max(_float(value.get("damping", 1e-4), 1e-4), 1e-12),
        "max_angle_step_deg": max(_float(value.get("max_angle_step_deg", 8.0), 8.0), 1e-9),
        "max_slide_step_mm": max(_float(value.get("max_slide_step_mm", 5.0), 5.0), 1e-9),
    }


def _extract_closures(data: dict[str, Any]) -> list[KinematicClosureSpec]:
    block = data.get("kinematic_closure_configuration") if isinstance(data.get("kinematic_closure_configuration"), dict) else {}
    raw = block.get("closures")
    if not isinstance(raw, list):
        vzext = data.get("vz_extensions") if isinstance(data.get("vz_extensions"), dict) else {}
        raw = vzext.get("kinematic_closures", [])
    return [KinematicClosureSpec.model_validate(_closure_row(item)) for item in list(raw or []) if isinstance(item, dict)]


def _export_pair(pair: DistancePairSpec) -> dict[str, Any]:
    """Emit the V21.4 PairItem shape plus lossless newer spacing fields."""
    return {
        "id": pair.id,
        "name": pair.name,
        "objects_a": list(pair.objects_a),
        "objects_b": list(pair.objects_b),
        "density_mode": "spacing_mm",
        "density_value": _number_text(pair.strategy_spacing_mm),
        "precise_enabled": True,
        "distmax": _number_text(pair.distmax_m),
        "strategy_density_value": pair.strategy_spacing_mm,
        "precise_density_value": pair.precise_spacing_mm,
        "animation_density_value": pair.animation_spacing_mm,
        "boundary_mm": pair.boundary_mm,
    }


def _import_pair(raw: dict[str, Any], index: int) -> DistancePairSpec:
    strategy = _float(raw.get("strategy_density_value", raw.get("density_value", 12.0)), 12.0)
    precise = _float(raw.get("precise_density_value", strategy), strategy)
    animation = _float(raw.get("animation_density_value", raw.get("animation_spacing_mm", precise)), precise)
    return DistancePairSpec(
        id=str(raw.get("id") or new_id("pair")),
        name=str(raw.get("name") or f"distance{index + 1}"),
        objects_a=[str(item) for item in list(raw.get("objects_a", []) or [])],
        objects_b=[str(item) for item in list(raw.get("objects_b", []) or [])],
        strategy_spacing_mm=max(strategy, 0.001),
        precise_spacing_mm=max(precise, 0.001),
        animation_spacing_mm=max(animation, 0.001),
        boundary_mm=max(_float(raw.get("boundary_mm", 0.0), 0.0), 0.0),
        distmax_m=max(_float(raw.get("distmax", raw.get("distmax_m", 0.1)), 0.1), 1e-6),
    )


def _import_layer(raw: dict[str, Any], root_id: str, *, from_exchange: bool) -> LayerSpec:
    layer_id = str(raw.get("id") or new_id("layer"))
    layer_name = str(raw.get("name") or layer_id)
    if from_exchange:
        color = _rgba_text(raw.get("color_rgba", "0.72 0.75 0.80 1"))
        raw_meshes = list(raw.get("models", []) or [])
    else:
        color = _rgba_text(raw.get("color_text", raw.get("color", "0.72 0.75 0.80 1")))
        raw_meshes = list(raw.get("meshes", []) or [])
    meshes: list[MeshSpec] = []
    for item in raw_meshes:
        if not isinstance(item, dict):
            continue
        try:
            if from_exchange:
                color_data = item.get("color") if isinstance(item.get("color"), dict) else {}
                rgba = "" if color_data.get("inherits_layer_color") is True else (
                    color_data.get("rgba") or color_data.get("effective_rgba") or color
                )
                opacity = _clamp(_float(color_data.get("opacity_alpha"), 1.0))
                filename = item.get("file_name", item.get("name", item.get("filename", "")))
            else:
                rgba = item.get("color_text", item.get("rgba", ""))
                opacity = _clamp(_float(item.get("opacity_text", item.get("opacity", 1.0)), 1.0))
                filename = item.get("file_name", item.get("name", item.get("filename", "")))
            if not str(filename).strip():
                continue
            meshes.append(MeshSpec(
                id=str(item.get("id") or new_id("mesh")),
                filename=str(filename),
                collision=bool(item.get("collision", False)),
                rgba="" if not str(rgba or "").strip() else _rgba_text(rgba),
                opacity=opacity,
                mass_kg=_optional_positive(item.get("mass_kg")),
            ))
        except Exception:
            continue
    joints: list[JointSpec] = []
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
    return LayerSpec(
        id=layer_id,
        name=layer_name,
        parent_id="root" if parent in {None, "", root_id} else str(parent),
        active=bool(raw.get("active", True)),
        color=color,
        position_mm=position_mm,
        mass_kg=_optional_positive(raw.get("mass_kg")),
        meshes=meshes,
        joints=joints,
    )


def _import_joint(raw: dict[str, Any]) -> JointSpec:
    raw_type = str(raw.get("joint_type", raw.get("type", "rotation")) or "rotation")
    joint_type = raw_type if raw_type in {"rotation", "translation", "crank"} else "rotation"
    known = {
        "id", "index", "choice", "layer_id", "layer_name", "name", "joint_type", "type",
        "point_text", "point", "axis_text", "axis", "invert_axis", "reverse", "limited", "range",
        "crank_center_text", "crank_center", "crank_end_text", "crank_end", "rod_end_text", "rod_end",
        "slide_axis_text", "slide_axis", "parameters", "damping", "armature", "frictionloss",
        "stiffness", "spring_reference",
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
    return JointSpec(
        id=str(raw.get("id") or new_id("joint")),
        name=str(raw.get("name") or "joint1"),
        type=joint_type,
        point=_safe_vector_text(raw.get("point_text", raw.get("point", "0, 0, 0")), (0.0, 0.0, 0.0)),
        axis=_safe_vector_text(raw.get("axis_text", raw.get("axis", "0, 1, 0")), (0.0, 1.0, 0.0)),
        crank_center=_safe_vector_text(raw.get("crank_center_text", raw.get("crank_center", "0, 0, 0")), (0.0, 0.0, 0.0)),
        crank_end=_safe_vector_text(raw.get("crank_end_text", raw.get("crank_end", "0, 10, 0")), (0.0, 10.0, 0.0)),
        rod_end=_safe_vector_text(raw.get("rod_end_text", raw.get("rod_end", "30, 0, 0")), (30.0, 0.0, 0.0)),
        slide_axis=_safe_vector_text(raw.get("slide_axis_text", raw.get("slide_axis", "1, 0, 0")), (1.0, 0.0, 0.0)),
        reverse=bool(raw.get("invert_axis", raw.get("reverse", False))),
        limited=bool(raw.get("limited", False)),
        range=[_float(rng[0], -180.0), _float(rng[1], 180.0)],
        damping=max(_float(raw.get("damping", parameters.get("damping", 0.1)), 0.1), 0.0),
        armature=max(_float(raw.get("armature", parameters.get("armature", 0.01)), 0.01), 0.0),
        frictionloss=max(_float(raw.get("frictionloss", parameters.get("frictionloss", 0.0)), 0.0), 0.0),
        stiffness=max(_float(raw.get("stiffness", parameters.get("stiffness", 0.0)), 0.0), 0.0),
        spring_reference=_float(raw.get("spring_reference", parameters.get("spring_reference", 0.0)), 0.0),
        parameters=parameters,
    )


def _import_drive(
    raw: dict[str, Any], choices: dict[str, str], *, allow_unbound: bool = False,
) -> DriveSpec | None:
    target = raw.get("target_joint") if isinstance(raw.get("target_joint"), dict) else {}
    choice = str(raw.get("target_joint_choice") or target.get("choice") or raw.get("joint_choice") or "")
    joint_id = str(raw.get("joint_id") or target.get("id") or choices.get(choice, ""))
    if not joint_id and not allow_unbound:
        return None
    raw_segments = list(raw.get("segments", []) or [])
    segments = [
        _import_segment(item, choices)
        for item in raw_segments if isinstance(item, dict)
    ]
    exchange_extra = copy.deepcopy(raw)
    exchange_extra.pop("exchange_extra", None)
    return DriveSpec(
        id=str(raw.get("id") or new_id("drive")),
        name=str(raw.get("name", "act1")),
        joint_id=joint_id,
        role=str(raw.get("fivebar_role", raw.get("role", ""))),
        enabled=bool(raw.get("enabled", True)),
        dynamic_kp=max(_float(raw.get("dynamic_kp", 100.0), 100.0), 1e-9),
        dynamic_kv=max(_float(raw.get("dynamic_kv", 20.0), 20.0), 0.0),
        dynamic_lock_force=max(_float(raw.get("dynamic_lock_force", 2000.0), 2000.0), 0.0),
        exchange_extra=exchange_extra,
        segments=segments,
    )


def _import_segment(raw: dict[str, Any], choices: dict[str, str]) -> DriveSegmentSpec:
    profile = _new_profile(raw.get("motion_profile", raw.get("profile", "s_curve")))
    if profile == "mapping":
        raw_points = raw.get("mapping_values", raw.get("points", []))
        points = [_point_pair(item, mapping=True) for item in raw_points]
    elif profile == "external_csv":
        raw_points = raw.get("external_csv_values", raw.get("points", []))
        points = [_point_pair(item) for item in raw_points]
    else:
        raw_points = raw.get("point_values", raw.get("points", []))
        points = [_point_pair(item) for item in raw_points]
    points = [item for item in points if item is not None]
    start_mode_raw = str(raw.get("start_time_mode", raw.get("start_mode", "direct")))
    reference = str(raw.get("reference", "") or "")
    if not reference:
        ref_drive = str(raw.get("ref_drive_name", "") or "")
        ref_segment = str(raw.get("ref_segment_name", "") or "")
        reference = f"{ref_drive}/{ref_segment}" if ref_drive and ref_segment else ""
    mapping_choice = str(raw.get("mapping_source_joint_choice", "") or "")
    external_csv_path = str(raw.get("external_csv_path", raw.get("csv_path", "")) or "")
    mapping_csv_path = str(raw.get("mapping_csv_path", raw.get("csv_path", "")) or "")
    return DriveSegmentSpec(
        id=str(raw.get("id") or new_id("seg")),
        name=str(raw.get("name", "seg1")),
        start_mode="reference" if start_mode_raw in {"ref", "reference"} else "direct",
        start=raw.get("start_time_value", raw.get("start", 0.0)),
        reference=reference,
        reference_boundary=str(raw.get("ref_boundary", raw.get("reference_boundary", "end"))) if str(raw.get("ref_boundary", raw.get("reference_boundary", "end"))) in {"start", "end"} else "end",
        mode="speed" if str(raw.get("mode", "duration")) == "speed" else "duration",
        duration=raw.get("duration", 1.0),
        speed=raw.get("max_speed", raw.get("speed", 30.0)),
        travel=raw.get("travel", points[-1][1] if points else 0.0),
        profile=profile,
        ease_in=bool(raw.get("enable_ease_in", raw.get("ease_in", raw.get("enable_soft_start", True)))),
        ease_out=bool(raw.get("enable_ease_out", raw.get("ease_out", raw.get("enable_soft_stop", True)))),
        easing_mode=str(raw.get("easing_mode", "time")) if str(raw.get("easing_mode", "time")) in {"time", "acceleration"} else "time",
        ease_in_time=raw.get("ease_in_time"),
        ease_out_time=raw.get("ease_out_time"),
        ease_in_acceleration=raw.get("ease_in_acceleration", 150.0),
        ease_out_acceleration=raw.get("ease_out_acceleration", 150.0),
        acceleration_time=raw.get("acceleration_time", 0.2),
        points=points,
        csv_path=(
            "" if points else (external_csv_path if profile == "external_csv" else mapping_csv_path if profile == "mapping" else "")
        ),
        external_csv_name=str(raw.get("external_csv_name", "") or "") or _source_name(external_csv_path),
        external_csv_header=str(raw.get("external_csv_header", "") or ""),
        external_csv_source_metric=str(raw.get("external_csv_source_metric", "") or ""),
        mapping_source_joint_id=str(raw.get("mapping_source_joint_id") or choices.get(mapping_choice, "")),
        mapping_csv_name=str(raw.get("mapping_csv_header", raw.get("mapping_csv_name", "")) or ""),
        mapping_point_count=len(points) if profile == "mapping" else max(int(_float(raw.get("mapping_point_count", 0), 0)), 0),
        archive_start=bool(raw.get("archive_start", False)),
        archive_end=bool(raw.get("archive_end", False)),
        archive_start_time=bool(raw.get("archive_start_time", False)),
        archive_motion_value=bool(raw.get("archive_motion_value", False)),
        archive_rate_value=bool(raw.get("archive_rate_value", False)),
        gantt_travel_input_mode=(
            str(raw.get("gantt_travel_input_mode", "travel"))
            if str(raw.get("gantt_travel_input_mode", "travel")) in {"travel", "end_position"}
            else "travel"
        ),
        exchange_extra={key: copy.deepcopy(value) for key, value in raw.items() if key != "exchange_extra"},
    )


def _export_joint(joint: JointSpec, layer: LayerSpec, index: int) -> dict[str, Any]:
    value = _old_joint(joint)
    value.update({
        "id": joint.id,
        "index": index,
        "choice": f"{layer.name}/{joint.name}",
        "layer_id": layer.id,
        "layer_name": layer.name,
    })
    return value


def _old_joint(joint: JointSpec) -> dict[str, Any]:
    params = copy.deepcopy(joint.parameters)
    legacy_type = str(params.get("legacy_joint_type", joint.type))
    value = {
        "name": joint.name,
        "joint_type": legacy_type,
        "point_text": f"Point( {joint.point} )",
        "axis_text": joint.axis,
        "invert_axis": bool(joint.reverse),
        "crank_center_text": f"Point( {joint.crank_center} )",
        "crank_end_text": f"Point( {joint.crank_end} )",
        "rod_end_text": f"Point( {joint.rod_end} )",
        "slide_axis_text": joint.slide_axis,
        "motion_axis_text": str(params.get("motion_axis_text", joint.slide_axis)),
        "limited": bool(joint.limited),
        "range": list(joint.range),
        "damping": joint.damping,
        "armature": joint.armature,
        "frictionloss": joint.frictionloss,
        "stiffness": joint.stiffness,
        "spring_reference": joint.spring_reference,
        "parameters": {key: copy.deepcopy(item) for key, item in params.items() if key != "legacy_joint_type"},
    }
    for key, item in params.items():
        if key != "legacy_joint_type":
            value.setdefault(key, copy.deepcopy(item))
    return value


def _old_snapshot_joint(joint: JointSpec) -> dict[str, Any]:
    """Return only fields accepted by V21.4.3's strict JointItem dataclass."""
    value = _old_joint(joint)
    allowed = {
        "name", "joint_type", "point_text", "axis_text", "invert_axis",
        "crank_center_text", "crank_end_text", "rod_end_text", "slide_axis_text",
        "motion_axis_text", "fivebar_point_a_text", "fivebar_point_b_text",
        "fivebar_point_c_text", "fivebar_point_d_text", "fivebar_point_e_text",
        "fivebar_ignore_axis", "custom_point_count", "custom_point_values",
    }
    return {key: copy.deepcopy(item) for key, item in value.items() if key in allowed}


def _old_drive(drive: DriveSpec, choices: dict[str, str], project: ProjectSpec) -> dict[str, Any]:
    """Export a drive binding together with its complete editable schedule."""
    value = copy.deepcopy(drive.exchange_extra) if isinstance(drive.exchange_extra, dict) else {}
    value.pop("exchange_extra", None)
    value.update({
        "id": drive.id,
        "name": drive.name,
        "joint_id": drive.joint_id,
        "target_joint_choice": choices.get(drive.joint_id, ""),
        "fivebar_role": drive.role,
        "enabled": bool(drive.enabled),
        "dynamic_kp": drive.dynamic_kp,
        "dynamic_kv": drive.dynamic_kv,
        "dynamic_lock_force": drive.dynamic_lock_force,
        "segments": [_old_segment(segment, choices) for segment in drive.segments],
    })
    return value


def _old_segment(segment: DriveSegmentSpec, choices: dict[str, str]) -> dict[str, Any]:
    ref_drive, ref_segment = _split_reference(segment.reference)
    point_rows = [{"time": _number_text(item[0]), "value": _number_text(item[1])} for item in segment.points]
    mapping_rows = [{"source": _number_text(item[0]), "value": _number_text(item[1])} for item in segment.points]
    profile = _old_profile(segment.profile)
    value = copy.deepcopy(segment.exchange_extra) if isinstance(segment.exchange_extra, dict) else {}
    value.pop("exchange_extra", None)
    value.update({
        "id": segment.id,
        "name": segment.name,
        "mode": segment.mode,
        "enable_soft_start": bool(segment.ease_in),
        "enable_soft_stop": bool(segment.ease_out),
        "enable_ease_in": bool(segment.ease_in),
        "enable_ease_out": bool(segment.ease_out),
        "easing_mode": segment.easing_mode,
        "ease_in_time": _number_or_expression(segment.ease_in_time) if segment.ease_in_time is not None else None,
        "ease_out_time": _number_or_expression(segment.ease_out_time) if segment.ease_out_time is not None else None,
        "ease_in_acceleration": _number_or_expression(segment.ease_in_acceleration),
        "ease_out_acceleration": _number_or_expression(segment.ease_out_acceleration),
        "acceleration_time": _number_or_expression(segment.acceleration_time),
        "start_time_mode": "ref" if segment.start_mode == "reference" else "direct",
        "start_time_value": _number_or_expression(segment.start),
        "ref_drive_name": ref_drive,
        "ref_segment_name": ref_segment,
        "ref_boundary": segment.reference_boundary,
        "max_speed": _number_or_expression(segment.speed),
        "duration": _number_or_expression(segment.duration),
        "travel": _number_or_expression(segment.travel),
        "motion_profile": profile,
        "point_count": str(len(segment.points) if segment.profile == "points" else 0),
        "point_values": point_rows if segment.profile == "points" else [],
        # External CSV samples are embedded model data. The original path is
        # machine-local provenance and is intentionally not exported.
        "external_csv_path": "",
        "external_csv_name": segment.external_csv_name if segment.profile == "external_csv" else "",
        "external_csv_header": segment.external_csv_header if segment.profile == "external_csv" else "",
        "external_csv_source_metric": segment.external_csv_source_metric if segment.profile == "external_csv" else "",
        "external_csv_values": point_rows if segment.profile == "external_csv" else [],
        "mapping_source_joint_choice": choices.get(segment.mapping_source_joint_id, ""),
        "mapping_source_joint_id": segment.mapping_source_joint_id,
        "mapping_csv_path": segment.csv_path if segment.profile == "mapping" else "",
        "mapping_csv_header": segment.mapping_csv_name,
        "mapping_point_count": segment.mapping_point_count,
        "mapping_values": mapping_rows if segment.profile == "mapping" else [],
        "archive_start": bool(segment.archive_start),
        "archive_end": bool(segment.archive_end),
        "archive_start_time": bool(segment.archive_start_time),
        "archive_motion_value": bool(segment.archive_motion_value),
        "archive_rate_value": bool(segment.archive_rate_value),
        "gantt_travel_input_mode": segment.gantt_travel_input_mode,
    })
    return value


def _old_root_layer() -> dict[str, Any]:
    return {"id": "root", "name": "root", "parent_id": None, "color_text": "0.72 0.75 0.80 1", "active": True, "meshes": [], "joints": []}


def _layer_depth(layers: list[LayerSpec], layer: LayerSpec) -> int:
    lookup = {item.id: item for item in layers}
    depth, parent, seen = 0, layer.parent_id, set()
    while parent and parent != "root" and parent in lookup and parent not in seen:
        seen.add(parent)
        depth += 1
        parent = lookup[parent].parent_id
    return depth


def _new_profile(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"smoothstep"}:
        return "smoothstep"
    if text in {"point_spline", "points", "自定义点", "插值光滑运动(过指定点, 无缓起缓停)"}:
        return "points"
    if text in {"external_csv", "外部 csv", "外部导入csv曲线"}:
        return "external_csv"
    if text in {"drive_mapping", "mapping", "映射电机", "驱动映射模式(伴生驱动)"}:
        return "mapping"
    return "s_curve"


def _old_profile(value: str) -> str:
    return {
        "s_curve": "trapezoid",
        "smoothstep": "smoothstep",
        "points": "point_spline",
        "external_csv": "external_csv",
        "mapping": "drive_mapping",
    }.get(value, "trapezoid")


def _variables(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    if not isinstance(value, list):
        return {}
    return {str(item.get("name")): item.get("value", 0) for item in value if isinstance(item, dict) and item.get("name")}


def _point_pair(value: Any, mapping: bool = False) -> list[float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return [_float(value[0]), _float(value[1])]
    if not isinstance(value, dict):
        return None
    x = value.get("source", value.get("time", 0)) if mapping else value.get("time", value.get("source", 0))
    y = value.get("value", value.get("target", 0))
    return [_float(x), _float(y)]


def _rgba(value: Any) -> list[float]:
    if isinstance(value, (list, tuple)):
        values = [_float(item) for item in value]
    else:
        text = str(value or "").replace(",", " ").split()
        values = [_float(item) for item in text]
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
    text = text.strip("()[]{} ")
    parts = [item for item in re.split(r"[,，;；\s]+", text) if item]
    if len(parts) != 3:
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


def _split_reference(value: Any) -> tuple[str, str]:
    text = str(value or "")
    if "/" not in text:
        return "", ""
    return tuple(text.split("/", 1))


def _number_or_expression(value: Any) -> Any:
    return _number_text(value) if isinstance(value, (float, int)) else value


def _number_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value or "")
    if math.isfinite(number) and abs(number - round(number)) < 1e-12:
        return str(int(round(number)))
    return f"{number:.12g}"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else float(default)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _optional_positive(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    result = _float(value)
    return result if result > 0 else None


def _source_name(value: Any) -> str:
    """Return a portable basename for either Windows- or POSIX-style provenance paths."""
    text = str(value or "").strip()
    return re.split(r"[\\/]", text)[-1] if text else ""
