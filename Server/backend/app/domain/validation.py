from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

from .expressions import ExpressionError
from .models import ProjectSpec, StrictModel
from .motion import resolve_schedule
from .crank import crank_meta
from .mass_properties import resolve_mass_properties


class ValidationIssue(StrictModel):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    path: str = ""


def validate_project(project: ProjectSpec, check_files: bool = True) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    ids: dict[str, str] = {"root": "root"}

    def register(identifier: str, path: str) -> None:
        if identifier in ids:
            issues.append(ValidationIssue(severity="error", code="duplicate_id", message=f"Duplicate id: {identifier}", path=path))
        ids[identifier] = path

    layer_ids = {layer.id for layer in project.layers}
    layer_lookup = {layer.id: layer for layer in project.layers}
    joint_ids: set[str] = set()
    joint_lookup = {}
    joint_layer_lookup: dict[str, object] = {}
    mesh_names: set[str] = set()
    for layer_index, layer in enumerate(project.layers):
        path = f"layers[{layer_index}]"
        register(layer.id, path)
        if layer.parent_id != "root" and layer.parent_id not in layer_ids:
            issues.append(ValidationIssue(severity="error", code="missing_parent", message=f"Layer '{layer.name}' references a missing parent", path=f"{path}.parent_id"))
        if layer.id == layer.parent_id:
            issues.append(ValidationIssue(severity="error", code="self_parent", message=f"Layer '{layer.name}' cannot be its own parent", path=f"{path}.parent_id"))
        for mesh_index, mesh in enumerate(layer.meshes):
            register(mesh.id, f"{path}.meshes[{mesh_index}]")
            mesh_names.add(mesh.filename)
            if check_files and project.mesh_root and not (Path(project.mesh_root) / mesh.filename).is_file():
                issues.append(ValidationIssue(severity="error", code="missing_mesh", message=f"Mesh file does not exist: {mesh.filename}", path=f"{path}.meshes[{mesh_index}].filename"))
        if layer.joints and len(layer.meshes) > 1:
            issues.append(ValidationIssue(
                severity="info",
                code="layer_joint_applies_to_all_meshes",
                message=(
                    f"层级 '{layer.name}' 包含 {len(layer.meshes)} 个数模且定义了运动副；"
                    "这些数模属于同一个刚体，运动副会作用于整个层级。"
                    "若只有某个附加物体需要相对运动，请把它建为 child Layer，并把运动副放在 child Layer 上"
                ),
                path=f"{path}.joints",
            ))
        for joint_index, joint in enumerate(layer.joints):
            register(joint.id, f"{path}.joints[{joint_index}]")
            joint_ids.add(joint.id)
            joint_lookup[joint.id] = joint
            joint_layer_lookup[joint.id] = layer
            range_valid = (
                len(joint.range) == 2
                and all(math.isfinite(float(value)) for value in joint.range)
                and float(joint.range[0]) < float(joint.range[1])
            )
            if joint.limited and not range_valid:
                issues.append(ValidationIssue(
                    severity="error", code="invalid_joint_range",
                    message=f"Joint '{joint.name}' has an invalid active limit range; lower must be smaller than upper",
                    path=f"{path}.joints[{joint_index}].range",
                ))
            elif not joint.limited and not range_valid:
                issues.append(ValidationIssue(
                    severity="warning", code="inactive_joint_range",
                    message=f"Joint '{joint.name}' has an invalid stored range, but limits are disabled so it is ignored",
                    path=f"{path}.joints[{joint_index}].range",
                ))
            if joint.type == "crank":
                try:
                    crank_meta(joint)
                except ValueError as exc:
                    issues.append(ValidationIssue(severity="error", code="invalid_crank", message=f"曲柄副 '{joint.name}'：{exc}", path=f"{path}.joints[{joint_index}]"))

    # Closed-chain configuration is shared project state, but the role of
    # ``solve_joint_ids`` is solver-specific.  Dynamic mode turns an enabled
    # closure into a MuJoCo equality/connect and does not consume the kinematic
    # DLS solver set.  Kinematic mode, on the other hand, may only solve joints
    # that actually exist in the generated active MJCF tree and are scalar
    # hinge/slide joints.  Stale references are warnings when at least one
    # usable solver joint remains; they must never survive into runtime binding.
    for closure_index, closure in enumerate(project.kinematic_closures):
        if not closure.enabled:
            continue
        closure_path = f"kinematic_closures[{closure_index}]"
        for side, endpoint in (("endpoint_a", closure.endpoint_a), ("endpoint_b", closure.endpoint_b)):
            endpoint_layer = layer_lookup.get(endpoint.layer_id)
            if endpoint_layer is None:
                issues.append(ValidationIssue(
                    severity="error", code="kinematic_closure_missing_endpoint_layer",
                    message=f"闭链 '{closure.name}' 的 {side} 引用了不存在的层级",
                    path=f"{closure_path}.{side}.layer_id",
                ))
            elif not endpoint_layer.active:
                issues.append(ValidationIssue(
                    severity="error", code="kinematic_closure_inactive_endpoint_layer",
                    message=f"闭链 '{closure.name}' 的 {side} 层级 '{endpoint_layer.name}' 未激活，无法生成闭链端点",
                    path=f"{closure_path}.{side}.layer_id",
                ))

        effective_solver_ids: list[str] = []
        seen_solver_ids: set[str] = set()
        for solver_index, joint_id in enumerate(closure.solve_joint_ids):
            joint_id = str(joint_id or "")
            solver_path = f"{closure_path}.solve_joint_ids[{solver_index}]"
            if not joint_id or joint_id in seen_solver_ids:
                continue
            seen_solver_ids.add(joint_id)
            joint = joint_lookup.get(joint_id)
            owner = joint_layer_lookup.get(joint_id)
            if joint is None or owner is None:
                issues.append(ValidationIssue(
                    severity="warning", code="kinematic_closure_missing_solver_joint",
                    message=f"闭链 '{closure.name}' 保存了已不存在的从动运动副 '{joint_id}'；该引用将被忽略",
                    path=solver_path,
                ))
                continue
            if not owner.active:
                issues.append(ValidationIssue(
                    severity="warning", code="kinematic_closure_inactive_solver_joint",
                    message=f"闭链 '{closure.name}' 的从动运动副 '{joint.name}' 位于未激活层级 '{owner.name}'；该引用将被忽略",
                    path=solver_path,
                ))
                continue
            if joint.type not in {"rotation", "translation"}:
                issues.append(ValidationIssue(
                    severity="warning", code="kinematic_closure_unsupported_solver_joint",
                    message=f"闭链 '{closure.name}' 的从动运动副 '{joint.name}' 类型 '{joint.type}' 不支持运动学闭链 DLS；该引用将被忽略",
                    path=solver_path,
                ))
                continue
            effective_solver_ids.append(joint_id)

        if project.solver_mode == "kinematic" and not effective_solver_ids:
            issues.append(ValidationIssue(
                severity="error", code="kinematic_closure_no_active_solver_joint",
                message=f"运动学闭链 '{closure.name}' 没有有效从动运动副；请选择至少一个已激活的旋转副或滑动副，或关闭该闭链",
                path=f"{closure_path}.solve_joint_ids",
            ))

    drive_ids = {drive.id for drive in project.drives}
    mapping_parent: dict[str, str] = {}
    drives_for_joint: dict[str, list[str]] = {}
    for item in project.drives:
        if item.joint_id:
            drives_for_joint.setdefault(item.joint_id, []).append(item.id)
    for drive_index, drive in enumerate(project.drives):
        register(drive.id, f"drives[{drive_index}]")
        if drive.joint_id:
            if drive.joint_id not in joint_ids:
                issues.append(ValidationIssue(severity="error", code="missing_joint", message=f"Drive '{drive.name}' references a missing joint", path=f"drives[{drive_index}].joint_id"))
        for segment_index, segment in enumerate(drive.segments):
            register(segment.id, f"drives[{drive_index}].segments[{segment_index}]")
            if segment.profile == "mapping":
                source = str(segment.mapping_source_joint_id or "")
                source_drive_id = source[6:] if source.startswith("drive:") else ""
                source_valid = source in joint_ids or (source_drive_id in drive_ids and source_drive_id != drive.id)
                if not source_valid:
                    issues.append(ValidationIssue(severity="error", code="missing_mapping_source", message=f"映射段 '{drive.name}/{segment.name}' 未选择有效源运动副/源驱动", path=f"drives[{drive_index}].segments[{segment_index}].mapping_source_joint_id"))
                if source_drive_id:
                    mapping_parent[f"drive:{drive.id}"] = f"drive:{source_drive_id}"
                elif source:
                    source_drives = drives_for_joint.get(source, [])
                    mapping_parent[f"drive:{drive.id}"] = f"drive:{source_drives[0]}" if source_drives else f"joint:{source}"
            if segment.profile == "mapping" and len(segment.points) < 2:
                if not segment.csv_path:
                    issues.append(ValidationIssue(severity="error", code="missing_mapping_points", message=f"映射段 '{drive.name}/{segment.name}' 尚未保存至少两个内嵌映射点", path=f"drives[{drive_index}].segments[{segment_index}].points"))
                elif not Path(segment.csv_path).is_file():
                    issues.append(ValidationIssue(severity="error", code="missing_mapping_points", message=f"映射段 '{drive.name}/{segment.name}' 没有内嵌映射点，兼容 CSV 也不存在：{segment.csv_path}", path=f"drives[{drive_index}].segments[{segment_index}].points"))
            if segment.profile == "external_csv" and not segment.points:
                if not segment.csv_path:
                    issues.append(ValidationIssue(severity="error", code="missing_external_csv_points", message=f"外部 CSV 段 '{drive.name}/{segment.name}' 尚未保存内嵌运动点", path=f"drives[{drive_index}].segments[{segment_index}].points"))
                elif not Path(segment.csv_path).is_file():
                    issues.append(ValidationIssue(severity="error", code="missing_external_csv_points", message=f"外部 CSV 段 '{drive.name}/{segment.name}' 没有内嵌运动点，兼容 CSV 也不存在：{segment.csv_path}", path=f"drives[{drive_index}].segments[{segment_index}].points"))

    for target in mapping_parent:
        visited: set[str] = set(); current = target
        while current in mapping_parent:
            if current in visited:
                issues.append(ValidationIssue(severity="error", code="mapping_cycle", message="映射电机关系存在循环", path="drives")); break
            visited.add(current); current = mapping_parent[current]

    pair_names: set[str] = set()
    for pair_index, pair in enumerate(project.distance_pairs):
        register(pair.id, f"distance_pairs[{pair_index}]")
        if pair.name in pair_names:
            issues.append(ValidationIssue(severity="error", code="duplicate_pair_name", message=f"Duplicate distance pair name: {pair.name}", path=f"distance_pairs[{pair_index}].name"))
        pair_names.add(pair.name)
        for side, values in (("objects_a", pair.objects_a), ("objects_b", pair.objects_b)):
            for filename in values:
                if filename not in mesh_names:
                    issues.append(ValidationIssue(severity="warning", code="unassigned_pair_mesh", message=f"Distance pair '{pair.name}' references a mesh not assigned to an active layer: {filename}", path=f"distance_pairs[{pair_index}].{side}"))

    # Detect hierarchy cycles.
    parents = {layer.id: layer.parent_id for layer in project.layers}
    for layer in project.layers:
        visited: set[str] = set()
        current = layer.id
        while current in parents and current != "root":
            if current in visited:
                issues.append(ValidationIssue(severity="error", code="layer_cycle", message=f"Layer hierarchy contains a cycle near '{layer.name}'", path="layers"))
                break
            visited.add(current)
            current = parents[current]

    mass_properties = resolve_mass_properties(project)
    for item in mass_properties["errors"]:
        issues.append(ValidationIssue(
            severity="error", code=str(item["code"]), message=str(item["message"]), path=str(item["path"]),
        ))
    if check_files:
        for row in mass_properties["meshes"].values():
            if row["target_mass_kg"] is not None and row["volume_m3"] is None:
                issues.append(ValidationIssue(
                    severity="warning", code="mesh_volume_unavailable",
                    message=f"数模 '{row['filename']}' 无法计算封闭体积；XML 将直接使用目标质量",
                    path=f"layers.{row['layer_id']}.meshes.{row['mesh_id']}.mass_kg",
                ))

    try:
        resolve_schedule(project)
    except ExpressionError as exc:
        issues.append(ValidationIssue(severity="error", code="drive_resolution", message=str(exc), path="drives"))

    if not project.layers:
        issues.append(ValidationIssue(severity="warning", code="empty_model", message="Project has no model layers", path="layers"))
    if not any(issue.severity == "error" for issue in issues):
        issues.append(ValidationIssue(severity="info", code="ready", message="Project is ready for generation"))
    return issues


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)
