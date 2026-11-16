"""Shared position-level kinematic closed-chain solver for MuJoCo Studio V2.5.0.

The module intentionally owns the only closure-solving algorithm used by simulation,
Viewer playback and Hybrid Dynamics driver scenes.  It performs damped least-squares
position correction on hinge/slide qpos only; it never advances dynamics or solves
constraint forces.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ClosureJointRuntime:
    joint_id: str
    joint_name: str
    joint_index: int
    qpos_address: int
    dof_address: int
    kind: str
    limited: bool
    range_min: float
    range_max: float


@dataclass(frozen=True)
class ClosureEndpointRuntime:
    """Compiled endpoint binding.

    Hidden MJCF sites are preferred when available for backward compatibility.
    ``body_id + local_point_m`` is the authoritative fallback and is sufficient
    to evaluate both world position and translational Jacobian.
    """

    site_id: int
    body_id: int
    local_point_m: tuple[float, float, float]


@dataclass(frozen=True)
class ClosureConstraintRuntime:
    closure_id: str
    name: str
    endpoint_a: ClosureEndpointRuntime
    endpoint_b: ClosureEndpointRuntime
    solve_joint_ids: tuple[str, ...]
    tolerance_mm: float
    max_iterations: int
    damping: float
    max_angle_step_deg: float
    max_slide_step_mm: float


@dataclass
class ClosureRuntime:
    constraints: list[ClosureConstraintRuntime] = field(default_factory=list)
    joints: dict[str, ClosureJointRuntime] = field(default_factory=dict)
    initial_qpos: np.ndarray | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.constraints)


@dataclass
class ClosureSolveResult:
    converged: bool
    iterations: int
    residual_mm: float
    qpos: np.ndarray
    constraint_residuals_mm: dict[str, float]
    reason: str = ""


def _safe_name(text: str, prefix: str = "item") -> str:
    normalized = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9_]+", "_", normalized).strip("_")
    if not value:
        value = prefix
    if value[0].isdigit():
        value = f"{prefix}_{value}"
    return value


def _default_site_name(closure_id: str, side: str) -> str:
    return f"__mjs_closure_{_safe_name(closure_id, 'closure')}_{side}"


def _dump_like(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return dict(getattr(value, "__dict__", {}))


def _project_payload(
    project_or_payload: Any,
) -> tuple[
    list[dict[str, Any]],
    dict[str, str],
    dict[str, str],
    dict[str, dict[str, str]],
    dict[str, str],
]:
    raw = _dump_like(project_or_payload)
    closures = [_dump_like(item) for item in raw.get("kinematic_closures", [])]
    site_map = {
        str(key): {str(side): str(name) for side, name in dict(value).items()}
        for key, value in dict(raw.get("closure_site_map", {})).items()
    }
    joint_map = {str(key): str(value) for key, value in dict(raw.get("joint_map", {})).items()}
    joint_types = {str(key): str(value) for key, value in dict(raw.get("joint_types", {})).items()}
    layer_body_map = {
        str(key): str(value) for key, value in dict(raw.get("layer_body_map", {})).items()
    }

    # ProjectSpec input is useful in tests, but generated runtime payload is preferred
    # because it has collision-safe MJCF names.  Reconstruct names when possible.
    if not joint_map and getattr(project_or_payload, "layers", None) is not None:
        try:
            from .xml_generator import stable_xml_name
            used: set[str] = set()
            for layer in project_or_payload.layers:
                if not getattr(layer, "active", True):
                    continue
                for joint in layer.joints:
                    base = stable_xml_name(joint.name, joint.id, "joint")
                    name = base
                    counter = 2
                    while name in used:
                        name = f"{base}_{counter}"
                        counter += 1
                    used.add(name)
                    joint_map[joint.id] = name
                    joint_types[joint.id] = joint.type
        except Exception:
            pass

    # ProjectSpec fallback for direct unit tests. Generated runtime payloads
    # should always provide collision-safe ``layer_body_map`` names.
    if not layer_body_map and getattr(project_or_payload, "layers", None) is not None:
        try:
            from .xml_generator import stable_xml_name
            used_bodies: set[str] = set()
            for layer in project_or_payload.layers:
                if not getattr(layer, "active", True):
                    continue
                base = stable_xml_name(layer.name, layer.id, "body")
                body_name = base
                if body_name in used_bodies:
                    from .xml_generator import safe_name
                    body_name = safe_name(f"{base}_{layer.id}", "body")
                used_bodies.add(body_name)
                layer_body_map[str(layer.id)] = body_name
        except Exception:
            pass
    return closures, joint_map, joint_types, site_map, layer_body_map


def build_closure_runtime(mujoco: Any, model: Any, project_or_payload: Any) -> ClosureRuntime:
    """Bind closure endpoints and passive solve joints to a compiled MuJoCo model.

    V2.5.3.3 no longer treats hidden MJCF sites as a hard runtime dependency.
    Site ids are used when present; otherwise the same endpoint is reconstructed
    from ``layer_body_map + endpoint.point_mm``.
    """
    closures, joint_map, joint_types, site_map, layer_body_map = _project_payload(project_or_payload)
    runtime = ClosureRuntime(initial_qpos=None)
    used_joint_ids: list[str] = []

    def bind_endpoint(
        raw_closure: dict[str, Any],
        closure_id: str,
        side: str,
        site_name: str,
    ) -> ClosureEndpointRuntime:
        site_id = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, site_name))
        endpoint = _dump_like(raw_closure.get(f"endpoint_{side}", {}))
        layer_id = str(endpoint.get("layer_id", ""))
        body_name = str(layer_body_map.get(layer_id, ""))
        body_id = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)) if body_name else -1

        raw_point = list(endpoint.get("point_mm", [0.0, 0.0, 0.0]) or [0.0, 0.0, 0.0])
        if len(raw_point) != 3:
            raise ValueError(f"kinematic_closure_endpoint_point_invalid: {closure_id}/{side}")
        local_point_m = tuple(float(value) * 0.001 for value in raw_point)

        if site_id < 0 and body_id < 0:
            raise ValueError(
                f"kinematic_closure_endpoint_missing: {closure_id}/{side}/{layer_id or '?'}"
            )
        return ClosureEndpointRuntime(
            site_id=site_id,
            body_id=body_id,
            local_point_m=local_point_m,
        )

    for raw in closures:
        if not bool(raw.get("enabled", True)):
            continue
        closure_id = str(raw.get("id", ""))
        names = site_map.get(closure_id, {})
        site_a_name = names.get("a") or _default_site_name(closure_id, "a")
        site_b_name = names.get("b") or _default_site_name(closure_id, "b")
        endpoint_a = bind_endpoint(raw, closure_id, "a", site_a_name)
        endpoint_b = bind_endpoint(raw, closure_id, "b", site_b_name)
        requested_solve_ids = tuple(str(item) for item in list(raw.get("solve_joint_ids", []) or []) if str(item))
        # Generated payloads should already be normalized, but runtime binding is
        # deliberately defensive for older snapshots/imports: inactive/deleted
        # joints have no MJCF mapping and are not valid DLS degrees of freedom.
        # Ignore those stale ids rather than raising missing_joint_map mid-Viewer.
        solve_ids = tuple(
            joint_id for joint_id in requested_solve_ids
            if joint_id in joint_map and joint_types.get(joint_id, "") in {"rotation", "translation"}
        )
        if not solve_ids:
            raise ValueError(f"kinematic_closure_empty_solver_set: {closure_id}")
        used_joint_ids.extend(item for item in solve_ids if item not in used_joint_ids)
        runtime.constraints.append(ClosureConstraintRuntime(
            closure_id=closure_id,
            name=str(raw.get("name", closure_id or "closure")),
            endpoint_a=endpoint_a,
            endpoint_b=endpoint_b,
            solve_joint_ids=solve_ids,
            tolerance_mm=max(float(raw.get("tolerance_mm", 0.05)), 1e-9),
            max_iterations=max(int(raw.get("max_iterations", 40)), 1),
            damping=max(float(raw.get("damping", 1e-4)), 1e-12),
            max_angle_step_deg=max(float(raw.get("max_angle_step_deg", 8.0)), 1e-9),
            max_slide_step_mm=max(float(raw.get("max_slide_step_mm", 5.0)), 1e-9),
        ))

    for joint_id in used_joint_ids:
        name = joint_map.get(joint_id, "")
        if not name:
            raise ValueError(f"kinematic_closure_runtime_invariant_missing_joint_map: {joint_id}")
        mj_joint = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name))
        if mj_joint < 0:
            raise ValueError(f"kinematic_closure_missing_joint: {joint_id}")
        kind = joint_types.get(joint_id, "")
        if kind not in {"rotation", "translation"}:
            # Infer from MuJoCo enum only as a compatibility fallback.
            raw_type = int(model.jnt_type[mj_joint])
            slide_enum = int(getattr(mujoco.mjtJoint, "mjJNT_SLIDE", 2))
            hinge_enum = int(getattr(mujoco.mjtJoint, "mjJNT_HINGE", 3))
            if raw_type == slide_enum:
                kind = "translation"
            elif raw_type == hinge_enum:
                kind = "rotation"
            else:
                raise ValueError(f"kinematic_closure_joint_type_unsupported: {joint_id}")
        limited = bool(model.jnt_limited[mj_joint])
        limits = np.asarray(model.jnt_range[mj_joint], dtype=float)
        runtime.joints[joint_id] = ClosureJointRuntime(
            joint_id=joint_id,
            joint_name=name,
            joint_index=mj_joint,
            qpos_address=int(model.jnt_qposadr[mj_joint]),
            dof_address=int(model.jnt_dofadr[mj_joint]),
            kind=kind,
            limited=limited,
            range_min=float(limits[0]) if len(limits) >= 2 else -math.inf,
            range_max=float(limits[1]) if len(limits) >= 2 else math.inf,
        )
    return runtime


def _endpoint_world_position(data: Any, endpoint: ClosureEndpointRuntime) -> np.ndarray:
    if endpoint.site_id >= 0:
        return np.asarray(data.site_xpos[endpoint.site_id], dtype=float).copy()
    if endpoint.body_id < 0:
        raise ValueError("kinematic_closure_endpoint_unbound")
    origin = np.asarray(data.xpos[endpoint.body_id], dtype=float)
    rotation = np.asarray(data.xmat[endpoint.body_id], dtype=float).reshape(3, 3)
    return origin + rotation @ np.asarray(endpoint.local_point_m, dtype=float)


def _endpoint_jacobian(
    mujoco: Any,
    model: Any,
    data: Any,
    endpoint: ClosureEndpointRuntime,
    world_point: np.ndarray,
) -> np.ndarray:
    jac = np.zeros((3, int(model.nv)), dtype=float)
    if endpoint.site_id >= 0:
        mujoco.mj_jacSite(model, data, jac, None, endpoint.site_id)
    else:
        mujoco.mj_jac(model, data, jac, None, world_point, endpoint.body_id)
    return jac


def _constraint_residuals(data: Any, runtime: ClosureRuntime) -> tuple[np.ndarray, dict[str, float]]:
    chunks: list[np.ndarray] = []
    per_constraint: dict[str, float] = {}
    for constraint in runtime.constraints:
        point_a = _endpoint_world_position(data, constraint.endpoint_a)
        point_b = _endpoint_world_position(data, constraint.endpoint_b)
        residual = point_a - point_b
        chunks.append(residual)
        per_constraint[constraint.closure_id] = float(np.linalg.norm(residual) * 1000.0)
    return (np.concatenate(chunks) if chunks else np.zeros(0, dtype=float), per_constraint)


def prepare_kinematic_state(mujoco: Any, model: Any, data: Any) -> None:
    """Refresh only the position-stage data required by closure solving.

    Jacobian evaluation needs forward kinematics plus center-of-mass transforms,
    not collision detection, constraint assembly or dynamics.  Native MuJoCo
    exposes that smaller pipeline directly.  The ``mj_forward`` fallback keeps
    old/fake bindings compatible.
    """
    kinematics = getattr(mujoco, "mj_kinematics", None)
    com_pos = getattr(mujoco, "mj_comPos", None)
    if callable(kinematics) and callable(com_pos):
        kinematics(model, data)
        com_pos(model, data)
        return
    mujoco.mj_forward(model, data)


def _refresh_solver_state(mujoco: Any, model: Any, data: Any, *, kinematics_only: bool) -> None:
    if kinematics_only:
        prepare_kinematic_state(mujoco, model, data)
    else:
        mujoco.mj_forward(model, data)


def solve_kinematic_closure(
    mujoco: Any,
    model: Any,
    data: Any,
    runtime: ClosureRuntime,
    *,
    driven_joint_ids: set[str] | None = None,
    previous_qpos: np.ndarray | None = None,
    kinematics_only: bool = False,
) -> ClosureSolveResult:
    """Solve enabled point closures at the current prescribed-drive frame.

    Driven qpos values are left untouched.  Only configured passive joint columns
    participate in the DLS solve, with deterministic previous-frame seeding.
    """
    if not runtime.enabled:
        _refresh_solver_state(mujoco, model, data, kinematics_only=kinematics_only)
        return ClosureSolveResult(True, 0, 0.0, data.qpos.copy(), {})

    driven = {str(item) for item in (driven_joint_ids or set())}
    conflict = sorted(driven.intersection(runtime.joints))
    if conflict:
        return ClosureSolveResult(
            False, 0, math.inf, data.qpos.copy(), {},
            reason="kinematic_closure_driven_joint_conflict:" + ",".join(conflict),
        )

    solve_ids = list(runtime.joints)
    if previous_qpos is not None and len(previous_qpos) == len(data.qpos):
        for joint_id in solve_ids:
            address = runtime.joints[joint_id].qpos_address
            data.qpos[address] = float(previous_qpos[address])

    _refresh_solver_state(mujoco, model, data, kinematics_only=kinematics_only)
    residual, per_constraint = _constraint_residuals(data, runtime)
    max_iterations = max((item.max_iterations for item in runtime.constraints), default=0)

    def converged() -> bool:
        return all(
            per_constraint.get(item.closure_id, math.inf) <= item.tolerance_mm
            for item in runtime.constraints
        )

    if converged():
        return ClosureSolveResult(True, 0, max(per_constraint.values(), default=0.0), data.qpos.copy(), per_constraint)

    dof_columns = [runtime.joints[joint_id].dof_address for joint_id in solve_ids]
    nv = int(model.nv)
    joint_col = {joint_id: index for index, joint_id in enumerate(solve_ids)}

    for iteration in range(1, max_iterations + 1):
        rows: list[np.ndarray] = []
        for constraint in runtime.constraints:
            point_a = _endpoint_world_position(data, constraint.endpoint_a)
            point_b = _endpoint_world_position(data, constraint.endpoint_b)
            jac_a = _endpoint_jacobian(
                mujoco, model, data, constraint.endpoint_a, point_a,
            )
            jac_b = _endpoint_jacobian(
                mujoco, model, data, constraint.endpoint_b, point_b,
            )
            row = (jac_a - jac_b)[:, dof_columns]
            allowed = set(constraint.solve_joint_ids)
            for joint_id, column in joint_col.items():
                if joint_id not in allowed:
                    row[:, column] = 0.0
            rows.append(row)
        jacobian = np.vstack(rows) if rows else np.zeros((0, len(solve_ids)), dtype=float)
        if not jacobian.size or not np.all(np.isfinite(jacobian)) or not np.all(np.isfinite(residual)):
            return ClosureSolveResult(False, iteration - 1, max(per_constraint.values(), default=math.inf), data.qpos.copy(), per_constraint, "kinematic_closure_singular")

        damping = max(item.damping for item in runtime.constraints)
        system = jacobian @ jacobian.T + (damping * damping) * np.eye(jacobian.shape[0], dtype=float)
        try:
            solved = np.linalg.solve(system, residual)
        except np.linalg.LinAlgError:
            try:
                solved = np.linalg.lstsq(system, residual, rcond=None)[0]
            except np.linalg.LinAlgError:
                return ClosureSolveResult(False, iteration - 1, max(per_constraint.values(), default=math.inf), data.qpos.copy(), per_constraint, "kinematic_closure_singular")
        delta = -(jacobian.T @ solved)
        if not np.all(np.isfinite(delta)):
            return ClosureSolveResult(False, iteration - 1, max(per_constraint.values(), default=math.inf), data.qpos.copy(), per_constraint, "kinematic_closure_singular")

        for joint_id, raw_step in zip(solve_ids, delta):
            joint = runtime.joints[joint_id]
            relevant = [item for item in runtime.constraints if joint_id in item.solve_joint_ids]
            if joint.kind == "translation":
                limit = min((item.max_slide_step_mm for item in relevant), default=5.0) * 0.001
            else:
                limit = math.radians(min((item.max_angle_step_deg for item in relevant), default=8.0))
            step = float(np.clip(raw_step, -limit, limit))
            address = joint.qpos_address
            next_value = float(data.qpos[address]) + step
            if joint.limited:
                next_value = float(np.clip(next_value, joint.range_min, joint.range_max))
            data.qpos[address] = next_value

        _refresh_solver_state(mujoco, model, data, kinematics_only=kinematics_only)
        residual, per_constraint = _constraint_residuals(data, runtime)
        if converged():
            return ClosureSolveResult(True, iteration, max(per_constraint.values(), default=0.0), data.qpos.copy(), per_constraint)

    return ClosureSolveResult(
        False,
        max_iterations,
        max(per_constraint.values(), default=math.inf),
        data.qpos.copy(),
        per_constraint,
        "kinematic_closure_nonconvergence",
    )


def closure_failure_payload(result: ClosureSolveResult, *, time_s: float) -> dict[str, Any]:
    return {
        "code": result.reason or "kinematic_closure_nonconvergence",
        "constraint_ids": [key for key, value in result.constraint_residuals_mm.items() if math.isfinite(value)],
        "time_s": float(time_s),
        "iterations": int(result.iterations),
        "residual_mm": float(result.residual_mm),
        "constraint_residuals_mm": dict(result.constraint_residuals_mm),
        "hint": "检查闭链端点、从动运动副、运动副范围和机构是否到达奇异/不可达位置",
    }
