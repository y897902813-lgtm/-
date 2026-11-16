from __future__ import annotations

import csv
from contextlib import closing
import json
import math
import time
from pathlib import Path
from typing import Callable

import numpy as np

from .models import ProjectSpec, SimulationSettings
from .motion import ResolvedSegment, drive_positions, joint_positions, resolve_schedule
from .crank import crank_displacement, crank_meta


ProgressCallback = Callable[[float, str], None]


def load_qpos_trajectory(path: str | Path, *, expected_nq: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Load and validate the authoritative Viewer/HTML qpos trajectory artifact."""
    trajectory_path = Path(path)
    with np.load(trajectory_path, allow_pickle=False) as trajectory:
        times = np.asarray(trajectory["times"], dtype=float)
        qpos = np.asarray(trajectory["qpos"], dtype=float)
    if times.ndim != 1 or qpos.ndim != 2 or len(times) != len(qpos):
        raise ValueError("trajectory.npz 的 times/qpos 维度或帧数不一致")
    if expected_nq is not None and qpos.shape[1] != int(expected_nq):
        raise ValueError(
            f"trajectory.npz 与当前模型 nq 不一致：trajectory={qpos.shape[1]}, model={int(expected_nq)}"
        )
    if len(times) > 1 and np.any(np.diff(times) < 0.0):
        raise ValueError("trajectory.npz 的 times 必须单调递增")
    return times, qpos


def sample_qpos_trajectory(times: np.ndarray, qpos: np.ndarray, time_s: float) -> np.ndarray | None:
    """Sample qpos exactly like the native Viewer: clamp ends, linearly interpolate inside."""
    sample_times = np.asarray(times, dtype=float).reshape(-1)
    frames = np.asarray(qpos, dtype=float)
    if frames.ndim != 2 or not len(sample_times) or len(sample_times) != len(frames):
        return None
    if float(time_s) <= float(sample_times[0]):
        return frames[0].copy()
    if float(time_s) >= float(sample_times[-1]):
        return frames[-1].copy()
    right = int(np.searchsorted(sample_times, float(time_s), side="right"))
    left = max(0, right - 1)
    right = min(right, len(sample_times) - 1)
    t0, t1 = float(sample_times[left]), float(sample_times[right])
    if right == left or t1 <= t0:
        return frames[left].copy()
    alpha = (float(time_s) - t0) / (t1 - t0)
    return frames[left] * (1.0 - alpha) + frames[right] * alpha


def build_drive_curves(
    project: ProjectSpec, schedule: list[ResolvedSegment], times: np.ndarray,
) -> dict[str, dict[str, object]]:
    """Return commanded drive displacement curves in Studio display units."""
    joint_lookup = {joint.id: joint for layer in project.layers for joint in layer.joints}
    schedule_by_drive: dict[str, list[ResolvedSegment]] = {}
    for segment in schedule:
        schedule_by_drive.setdefault(segment.drive_id, []).append(segment)
    payload: dict[str, dict[str, object]] = {}
    # V2.16.2: resolve the whole schedule once per time sample, not once per
    # (drive, sample) pair. The old loop was O(frames * drives * segments)
    # and repeated mapping interpolation for every drive at every frame.
    enabled: list[tuple[object, str]] = []
    for drive in project.drives:
        segments = schedule_by_drive.get(drive.id, [])
        if not drive.enabled or not segments:
            continue
        joint = joint_lookup.get(drive.joint_id)
        angular = joint is not None and joint.type != "translation"
        payload[drive.id] = {
            "name": drive.name,
            "joint_id": drive.joint_id,
            "unit": "value" if joint is None else ("deg" if angular else "mm"),
            "position": [],
        }
        enabled.append((drive, drive.id))
    if not enabled:
        return payload
    for time_s in times:
        positions = drive_positions(schedule, float(time_s))
        for _drive, drive_id in enabled:
            payload[drive_id]["position"].append(positions.get(drive_id, 0.0))
    return payload


def build_time_grid(
    settings: SimulationSettings,
    boundaries: list[float] | None = None,
    *,
    include_boundaries: bool = False,
) -> np.ndarray:
    """Build the canonical sampling grid for simulation results.

    Result samples are integer timestep ticks from ``start_time`` and never gain an
    off-grid endpoint or motion-boundary sample.  This keeps a configured 0.01 s
    timestep visually and numerically on the 0.01 s grid.  Callers that need extra
    evaluation probes (for example optimization constraint searches) must opt in
    explicitly with ``include_boundaries=True``; those probes are not result frames.
    """
    start = float(settings.start_time)
    end = float(settings.end_time)
    step = float(settings.timestep)
    if not math.isfinite(start) or not math.isfinite(end) or not math.isfinite(step) or step <= 0:
        raise ValueError("仿真时间范围和步长必须是有限数值，且步长必须大于 0")
    span = max(0.0, end - start)
    tick_count = int(math.floor(span / step + 1e-10))
    values = np.round(start + np.arange(tick_count + 1, dtype=float) * step, 12)
    values = values[values <= end + 1e-10]
    if not include_boundaries:
        return values
    extras = {round(end, 12)}
    for value in boundaries or []:
        numeric = float(value)
        if start <= numeric <= end:
            extras.add(round(numeric, 12))
    return np.asarray(sorted(set(values.tolist()) | extras), dtype=float)


def _require_mujoco():
    try:
        import mujoco  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "MuJoCo 引擎不可用：当前 Python 环境未安装 mujoco。请执行 "
            'python -m pip install "mujoco>=3.1,<4" 后重启 Studio。'
        ) from exc
    return mujoco


def load_generated_mujoco_model(xml_path: str | Path, mujoco_module):
    """Load generated XML through the existing Unicode/VFS compatibility contract.

    Server simulations run in-process, so changing process cwd to make a generated
    XML path relative would be unsafe under concurrent requests.  Reuse the native
    Viewer loader instead: ASCII paths keep MuJoCo's normal file loader while any
    Unicode XML/mesh path is virtualized before it reaches MuJoCo on Windows.
    """
    from .viewer_runner import load_mujoco_model

    return load_mujoco_model(xml_path, mujoco_module)


def _project_joint_lookup(project: ProjectSpec):
    return {joint.id: joint for layer in project.layers for joint in layer.joints}


def _display_positions(
    project: ProjectSpec, schedule: list[ResolvedSegment], time_s: float,
    *, joint_lookup: dict[str, object] | None = None,
) -> dict[str, float]:
    # The model topology is immutable for this run. Avoid rebuilding the whole
    # joint dictionary at every dynamic time-step.
    lookup = joint_lookup if joint_lookup is not None else _project_joint_lookup(project)
    raw = joint_positions(schedule, float(time_s))
    return {
        joint_id: crank_displacement(crank_meta(lookup[joint_id]), value)
        if joint_id in lookup and lookup[joint_id].type == "crank" else float(value)
        for joint_id, value in raw.items()
    }


def _to_internal(joint, value: float) -> float:
    return float(value) * 0.001 if joint.type in {"translation", "crank"} else math.radians(float(value))


def _from_internal(joint, value: float) -> float:
    return float(value) * 1000.0 if joint.type in {"translation", "crank"} else math.degrees(float(value))


def _bind_runtime(mujoco, model, drive_payload: dict[str, object], project: ProjectSpec):
    joint_map = dict(drive_payload.get("joint_map", {}))
    joint_lookup = _project_joint_lookup(project)
    addresses: dict[str, int] = {}
    dof_addresses: dict[str, int] = {}
    for joint_id, name in joint_map.items():
        mj_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, str(name))
        if mj_joint >= 0 and joint_id in joint_lookup:
            addresses[str(joint_id)] = int(model.jnt_qposadr[mj_joint])
            dof_addresses[str(joint_id)] = int(model.jnt_dofadr[mj_joint])
    actuator_ids: dict[str, int] = {}
    for joint_id, name in dict(drive_payload.get("actuator_map", {})).items():
        actuator = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, str(name))
        if actuator >= 0:
            actuator_ids[str(joint_id)] = int(actuator)
    mesh_manifest = dict(drive_payload.get("mesh_manifest", {}))
    geom_ids_by_file: dict[str, list[int]] = {}
    for filename, geom_names in mesh_manifest.items():
        ids: list[int] = []
        for geom_name in geom_names:
            geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, str(geom_name))
            if geom >= 0:
                ids.append(int(geom))
        geom_ids_by_file[str(filename).casefold()] = ids
    return joint_lookup, addresses, dof_addresses, actuator_ids, geom_ids_by_file


def _set_dynamic_position_controls(
    data, *, actuator_ids: dict[str, int], addresses: dict[str, int], lookup: dict[str, object],
    base_qpos: np.ndarray, positions: dict[str, float],
) -> None:
    """Write Studio drive targets into MuJoCo actuator controls.

    ``actuator_ids`` is keyed by authoritative Studio joint id but its values are
    compiled MuJoCo actuator ids.  Never index ``data.ctrl`` with a joint id or
    qpos address: those index spaces are independent in MuJoCo.
    """
    for joint_id, actuator_id in actuator_ids.items():
        address = addresses.get(joint_id)
        joint = lookup.get(joint_id)
        if address is None or joint is None:
            continue
        data.ctrl[actuator_id] = base_qpos[address] + _to_internal(joint, positions.get(joint_id, 0.0))



def _dynamic_lock_force_by_joint(project: ProjectSpec) -> dict[str, float]:
    """Collapse enabled per-drive stationary brake limits to one value per joint."""
    limits: dict[str, float] = {}
    for drive in project.drives:
        if not drive.enabled or not drive.joint_id:
            continue
        limits[drive.joint_id] = max(
            limits.get(drive.joint_id, 0.0),
            max(float(drive.dynamic_lock_force), 0.0),
        )
    return limits


def _apply_dynamic_self_lock(
    model, *, project: ProjectSpec, dof_addresses: dict[str, int],
    positions: dict[str, float], next_positions: dict[str, float],
    joint_lookup: dict[str, object] | None = None,
    lock_limits: dict[str, float] | None = None,
) -> None:
    """Project a motor-brake style self-lock into the current MuJoCo model.

    The persistent JointSpec.frictionloss remains the always-on dry-friction
    baseline.  A drive's dynamic_lock_force is added only while its commanded
    target is stationary across the current fixed physics step.  This gives a
    bounded static holding force without making normal commanded motion fight
    the brake.  The mutation is run-local L3 state and is never persisted.
    """
    joint_lookup = joint_lookup if joint_lookup is not None else _project_joint_lookup(project)
    lock_limits = lock_limits if lock_limits is not None else _dynamic_lock_force_by_joint(project)
    for joint_id, dof_address in dof_addresses.items():
        joint = joint_lookup.get(joint_id)
        if joint is None:
            continue
        baseline = max(float(joint.frictionloss), 0.0)
        lock_limit = max(float(lock_limits.get(joint_id, 0.0)), 0.0)
        current_target = float(positions.get(joint_id, 0.0))
        next_target = float(next_positions.get(joint_id, current_target))
        stationary = math.isclose(current_target, next_target, rel_tol=0.0, abs_tol=1e-9)
        model.dof_frictionloss[dof_address] = max(baseline, lock_limit) if stationary else baseline


def _step_dynamic_with_drive_controls(
    mujoco, model, data, *, project: ProjectSpec, schedule: list[ResolvedSegment],
    actuator_ids: dict[str, int], addresses: dict[str, int], dof_addresses: dict[str, int],
    lookup: dict[str, object], base_qpos: np.ndarray, positions: dict[str, float] | None = None,
    next_positions: dict[str, float] | None = None,
    lock_limits: dict[str, float] | None = None,
) -> dict[str, float]:
    """Advance exactly one dynamic step with Studio drives connected to actuation.

    MuJoCo's two-phase stepping API gives an explicit and testable boundary:
    position/velocity dependent state is prepared by ``mj_step1``; then the
    current Studio drive command is written to ``mjData.ctrl``; finally
    ``mj_step2`` computes actuator forces/constraints and integrates.  The model
    generator uses ``implicitfast``, for which this API preserves the configured
    single-step integrator.
    """
    if positions is None:
        positions = _display_positions(project, schedule, float(data.time), joint_lookup=lookup)
    if next_positions is None:
        next_positions = _display_positions(
            project, schedule, float(data.time) + float(model.opt.timestep), joint_lookup=lookup,
        )
    _apply_dynamic_self_lock(
        model, project=project, dof_addresses=dof_addresses,
        positions=positions, next_positions=next_positions,
        joint_lookup=lookup, lock_limits=lock_limits,
    )
    # frictionloss participates in the constraint stage, so the stationary brake
    # must be projected before mj_step1 builds position-dependent constraints.
    mujoco.mj_step1(model, data)
    _set_dynamic_position_controls(
        data, actuator_ids=actuator_ids, addresses=addresses, lookup=lookup,
        base_qpos=base_qpos, positions=positions,
    )
    mujoco.mj_step2(model, data)
    return positions


def _validate_dynamic_bindings(project: ProjectSpec, addresses: dict[str, int], actuator_ids: dict[str, int]) -> None:
    """Fail loudly if an enabled physical drive was not compiled/bound to MuJoCo."""
    expected = {drive.joint_id for drive in project.drives if drive.enabled and drive.joint_id}
    missing_joint = sorted(expected - set(addresses))
    missing_actuator = sorted(expected - set(actuator_ids))
    if missing_joint or missing_actuator:
        details = []
        if missing_joint:
            details.append("joint=" + ",".join(missing_joint))
        if missing_actuator:
            details.append("actuator=" + ",".join(missing_actuator))
        raise RuntimeError("dynamic_actuator_binding_failed: " + "; ".join(details))


def _bind_distance_runtime(project: ProjectSpec, geom_ids_by_file: dict[str, list[int]]):
    """Resolve immutable distance-pair geom groups once per simulation run."""
    runtime = []
    for pair in project.distance_pairs:
        group_a = tuple(geom for filename in pair.objects_a for geom in geom_ids_by_file.get(filename.casefold(), ()))
        group_b = tuple(geom for filename in pair.objects_b for geom in geom_ids_by_file.get(filename.casefold(), ()))
        runtime.append((pair.id, float(pair.distmax_m), group_a, group_b))
    return tuple(runtime)


def _measure_bound_distances(mujoco, model, data, distance_runtime):
    values: dict[str, float] = {}
    for pair_id, distmax_m, group_a, group_b in distance_runtime:
        minimum = float("inf")
        for geom_a in group_a:
            for geom_b in group_b:
                if geom_a == geom_b:
                    continue
                distance = max(float(mujoco.mj_geomDistance(model, data, geom_a, geom_b, distmax_m, None)), 0.0)
                minimum = min(minimum, distance)
        values[pair_id] = minimum * 1000.0 if math.isfinite(minimum) else float("inf")
    return values


def _measure_distances(mujoco, model, data, project: ProjectSpec, geom_ids_by_file: dict[str, list[int]]):
    """Compatibility wrapper for callers/tests that still pass ProjectSpec + mesh lookup."""
    return _measure_bound_distances(mujoco, model, data, _bind_distance_runtime(project, geom_ids_by_file))


def _curve_payload_from_qpos(
    project: ProjectSpec, times: np.ndarray, qpos: np.ndarray, base_qpos: np.ndarray,
    addresses: dict[str, int], *, qvel: np.ndarray | None = None, qacc: np.ndarray | None = None,
    dof_addresses: dict[str, int] | None = None,
) -> dict[str, dict[str, object]]:
    """Build display curves, preferring solver velocity/acceleration when available.

    Dynamic MuJoCo runs already expose qvel/qacc.  Re-differentiating qpos twice
    amplifies tiny position quantisation and mapping-knot noise, so only analytical
    or unavailable channels fall back to numerical gradients.
    """
    lookup = _project_joint_lookup(project)
    dof_addresses = dof_addresses or {}
    payload: dict[str, dict[str, object]] = {}
    for joint_id, address in addresses.items():
        joint = lookup[joint_id]
        position = np.asarray([_from_internal(joint, row[address] - base_qpos[address]) for row in qpos], dtype=float)
        dof = dof_addresses.get(joint_id)
        if qvel is not None and dof is not None and qvel.ndim == 2 and dof < qvel.shape[1]:
            velocity = np.asarray([_from_internal(joint, row[dof]) for row in qvel], dtype=float)
        else:
            velocity = np.gradient(position, times) if len(times) > 1 else np.zeros_like(position)
        if qacc is not None and dof is not None and qacc.ndim == 2 and dof < qacc.shape[1]:
            acceleration = np.asarray([_from_internal(joint, row[dof]) for row in qacc], dtype=float)
        else:
            acceleration = np.gradient(velocity, times) if len(times) > 1 else np.zeros_like(position)
        payload[joint_id] = {
            "name": joint.name,
            "joint_type": joint.type,
            "unit": "deg" if joint.type == "rotation" else "mm",
            "position": position.tolist(),
            "velocity": velocity.tolist(),
            "acceleration": acceleration.tolist(),
        }
    return payload


def _write_results(project: ProjectSpec, result_dir: Path, *, mode: str, times: np.ndarray, qpos: np.ndarray,
                   qvel: np.ndarray, ctrl: np.ndarray, base_qpos: np.ndarray, addresses: dict[str, int],
                   schedule: list[ResolvedSegment], variables: dict[str, float], contacts: list[int],
                   distance_values: dict[str, list[float]], model, dof_addresses: dict[str, int] | None = None,
                   qacc: np.ndarray | None = None) -> dict[str, object]:
    curve_payload = _curve_payload_from_qpos(
        project, times, qpos, base_qpos, addresses, qvel=qvel, qacc=qacc, dof_addresses=dof_addresses,
    )
    distance_payload: dict[str, dict[str, object]] = {}
    pair_lookup = {pair.id: pair for pair in project.distance_pairs}
    for pair_id, values in distance_values.items():
        pair = pair_lookup[pair_id]
        finite = [(i, value) for i, value in enumerate(values) if math.isfinite(value)]
        if finite:
            min_index, min_value = min(finite, key=lambda item: item[1])
            min_time = float(times[min_index])
        else:
            min_value, min_time = float("inf"), None
        distance_payload[pair_id] = {
            "name": pair.name, "unit": "mm", "values": values,
            "minimum_mm": min_value if finite else None, "minimum_time_s": min_time,
            "objects_a": pair.objects_a, "objects_b": pair.objects_b,
            # V2.15.10: The authoritative trajectory is solved first. Expensive
            # Viewer-equivalent sampled distances are requested per selected pair.
            "method": "viewer_sampled_surface_v1" if finite else "pending_viewer_sampled_surface_v1",
            "status": "ready" if finite else "not_computed",
        }

    result_dir.mkdir(parents=True, exist_ok=True)
    trajectory_path = result_dir / "trajectory.npz"
    np.savez_compressed(trajectory_path, times=times, qpos=qpos, qvel=qvel, ctrl=ctrl)
    result_path = result_dir / "simulation_result.json"
    csv_path = result_dir / "simulation_curves.csv"
    payload: dict[str, object] = {
        "project_id": project.id,
        "solver_mode": mode,
        "engine": "mujoco",
        "times": times.tolist(),
        "curves": curve_payload,
        "drive_curves": build_drive_curves(project, schedule, times),
        "variables": variables,
        "contacts": contacts,
        "distance_curves": distance_payload,
        "maximum_contacts": max(contacts, default=0),
        "end_time": float(times[-1]) if len(times) else project.simulation.start_time,
        "trajectory_file": "trajectory.npz",
        "trajectory": {"nframes": int(len(times)), "nq": int(model.nq), "nv": int(model.nv), "nu": int(model.nu)},
        "model_summary": {"nq": int(model.nq), "nv": int(model.nv), "nu": int(model.nu), "nbody": int(model.nbody), "ngeom": int(model.ngeom), "njnt": int(model.njnt)},
    }
    result_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        joint_ids = list(curve_payload)
        pair_ids = list(distance_payload)
        writer.writerow(["time_s", "contact_count"] + [f"{curve_payload[item]['name']}_position" for item in joint_ids] + [f"{distance_payload[item]['name']}_mm" for item in pair_ids])
        for index, time_s in enumerate(times):
            writer.writerow([time_s, contacts[index] if index < len(contacts) else 0] + [curve_payload[item]["position"][index] for item in joint_ids] + [distance_payload[item]["values"][index] if index < len(distance_payload[item]["values"]) else "" for item in pair_ids])
    payload["artifacts"] = {"result": str(result_path), "csv": str(csv_path), "trajectory": str(trajectory_path)}
    return payload


def run_analytical_simulation(
    project: ProjectSpec, result_dir: Path, *, variable_overrides: dict[str, float] | None = None,
    progress: ProgressCallback | None = None, should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    """Compatibility-only fast curve evaluation. It does not create Viewer trajectory data."""
    variables, schedule = resolve_schedule(project, variable_overrides)
    times = build_time_grid(project.simulation)
    joint_lookup = _project_joint_lookup(project)
    curves: dict[str, list[float]] = {joint_id: [] for joint_id in {item.joint_id for item in schedule if item.joint_id}}
    for index, time_s in enumerate(times):
        if should_cancel and should_cancel():
            raise InterruptedError("simulation cancelled")
        positions = _display_positions(project, schedule, float(time_s), joint_lookup=joint_lookup)
        for joint_id in curves:
            curves[joint_id].append(float(positions.get(joint_id, 0.0)))
        if progress and (index % max(1, len(times)//100) == 0 or index == len(times)-1):
            progress((index+1)/max(len(times),1), f"Kinematic curve {index+1}/{len(times)}")
    curve_payload = {}
    for joint_id, values in curves.items():
        position = np.asarray(values, dtype=float)
        velocity = np.gradient(position, times) if len(times)>1 else np.zeros_like(position)
        acceleration = np.gradient(velocity, times) if len(times)>1 else np.zeros_like(position)
        joint = joint_lookup[joint_id]
        curve_payload[joint_id] = {"name": joint.name, "joint_type": joint.type, "unit": "deg" if joint.type == "rotation" else "mm", "position": position.tolist(), "velocity": velocity.tolist(), "acceleration": acceleration.tolist()}
    result_dir.mkdir(parents=True, exist_ok=True)
    result_path = result_dir / "simulation_result.json"
    payload = {"project_id": project.id, "solver_mode": project.solver_mode, "engine": "analytical", "times": times.tolist(), "curves": curve_payload, "drive_curves": build_drive_curves(project,schedule,times), "variables": variables, "end_time": max((item.end for item in schedule), default=project.simulation.start_time)}
    result_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    payload["artifacts"] = {"result": str(result_path)}
    return payload


def run_kinematic_simulation(
    project: ProjectSpec, result_dir: Path, *, variable_overrides: dict[str, float] | None = None,
    progress: ProgressCallback | None = None, should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    """Pure position-level kinematics: write qpos, solve optional closure, then mj_forward; never mj_step."""
    started_at = time.perf_counter()
    mujoco = _require_mujoco()
    from .xml_generator import generate_project
    from .kinematic_closure import build_closure_runtime, solve_kinematic_closure, closure_failure_payload

    result_dir.mkdir(parents=True, exist_ok=True)
    generated = generate_project(project, result_dir / "generated", check_files=True)
    xml_generated_at = time.perf_counter()
    drive_payload = json.loads(Path(generated["drives"]).read_text("utf-8"))
    variables, schedule = resolve_schedule(project, variable_overrides)
    times = build_time_grid(project.simulation)
    model = load_generated_mujoco_model(generated["model"], mujoco)
    model_loaded_at = time.perf_counter()
    data = mujoco.MjData(model)
    base_qpos = data.qpos.copy()
    lookup, addresses, dof_addresses, _, geom_ids = _bind_runtime(mujoco, model, drive_payload, project)
    closure_runtime = build_closure_runtime(mujoco, model, drive_payload)
    previous_qpos = base_qpos.copy()
    qpos_frames: list[np.ndarray] = []
    contacts: list[int] = []
    distance_values = {pair.id: [] for pair in project.distance_pairs}
    setup_ready_at = time.perf_counter()
    distance_seconds = 0.0  # V2.15.10: deferred by selected-pair Job
    closure_seconds = 0.0

    for index, time_s in enumerate(times):
        if should_cancel and should_cancel():
            raise InterruptedError("simulation cancelled")
        positions = _display_positions(project, schedule, float(time_s), joint_lookup=lookup)
        data.qpos[:] = base_qpos
        for joint_id, value in positions.items():
            if joint_id in addresses:
                data.qpos[addresses[joint_id]] = base_qpos[addresses[joint_id]] + _to_internal(lookup[joint_id], value)
        closure_started_at = time.perf_counter() if closure_runtime.enabled else 0.0
        if closure_runtime.enabled:
            solved = solve_kinematic_closure(
                mujoco, model, data, closure_runtime, driven_joint_ids=set(positions),
                previous_qpos=previous_qpos, kinematics_only=False,
            )
            closure_seconds += time.perf_counter() - closure_started_at
            if not solved.converged:
                raise ValueError(json.dumps(closure_failure_payload(solved, time_s=float(time_s)), ensure_ascii=False))
            previous_qpos = data.qpos.copy()
        # With a closure, its solver already called mj_forward() at the final
        # converged qpos. Without a closure we still need one native forward.
        if not closure_runtime.enabled:
            mujoco.mj_forward(model, data)
        qpos_frames.append(data.qpos.copy())
        contacts.append(int(data.ncon))
        # Distance curves are deliberately NOT computed as part of trajectory
        # refresh. UI selection schedules one pair via the existing JobManager.
        # See compute_selected_viewer_distance_curve below.
        if progress and (index % max(1, len(times)//100) == 0 or index == len(times)-1):
            progress((index+1)/max(len(times),1), f"Kinematic trajectory {index+1}/{len(times)}")

    result_ready_at = time.perf_counter()
    qpos = np.asarray(qpos_frames, dtype=float)
    qvel = np.gradient(qpos, times, axis=0) if len(times)>1 else np.zeros((len(times), model.nv), dtype=float)
    if qvel.shape[1] != model.nv:
        qvel = np.zeros((len(times), model.nv), dtype=float)
    ctrl = np.zeros((len(times), model.nu), dtype=float)
    payload = _write_results(project, result_dir, mode="kinematic", times=times, qpos=qpos, qvel=qvel, ctrl=ctrl, base_qpos=base_qpos, addresses=addresses, dof_addresses=dof_addresses, schedule=schedule, variables=variables, contacts=contacts, distance_values=distance_values, model=model)
    payload["artifacts"].update(generated)
    completed_at = time.perf_counter()
    payload["timings_seconds"] = {
        "scene_and_runtime_setup": round(setup_ready_at - started_at, 4),
        "xml_generation": round(xml_generated_at - started_at, 4),
        "model_compile_and_load": round(model_loaded_at - xml_generated_at, 4),
        "runtime_binding": round(setup_ready_at - model_loaded_at, 4),
        "trajectory_evaluation": round(result_ready_at - setup_ready_at - distance_seconds, 4),
        "closure_solver": round(closure_seconds, 4),
        "distance_evaluation": round(distance_seconds, 4),
        "result_serialization": round(completed_at - result_ready_at, 4),
        "total": round(completed_at - started_at, 4),
        "sample_count": int(len(times)),
    }
    return payload


def run_dynamic_simulation(
    project: ProjectSpec, result_dir: Path, *, variable_overrides: dict[str, float] | None = None,
    progress: ProgressCallback | None = None, should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    """Pure MuJoCo dynamics: drives become position actuators; no qpos is overwritten after initialization."""
    started_at = time.perf_counter()
    mujoco = _require_mujoco()
    from .xml_generator import generate_project

    result_dir.mkdir(parents=True, exist_ok=True)
    generated = generate_project(project, result_dir / "generated", check_files=True)
    xml_generated_at = time.perf_counter()
    drive_payload = json.loads(Path(generated["drives"]).read_text("utf-8"))
    variables, schedule = resolve_schedule(project, variable_overrides)
    # Dynamic integration remains strictly fixed-step. Segment boundaries are sampled by the command evaluator,
    # not by inserting irregular physics steps.
    times = build_time_grid(project.simulation)
    model = load_generated_mujoco_model(generated["model"], mujoco)
    model_loaded_at = time.perf_counter()
    data = mujoco.MjData(model)
    base_qpos = data.qpos.copy()
    lookup, addresses, dof_addresses, actuator_ids, geom_ids = _bind_runtime(mujoco, model, drive_payload, project)
    _validate_dynamic_bindings(project, addresses, actuator_ids)
    qpos_frames: list[np.ndarray] = []
    qvel_frames: list[np.ndarray] = []
    qacc_frames: list[np.ndarray] = []
    ctrl_frames: list[np.ndarray] = []
    contacts: list[int] = []
    distance_values = {pair.id: [] for pair in project.distance_pairs}
    cached_command_time: float | None = None
    cached_positions: dict[str, float] | None = None
    next_control_time: float | None = None
    next_control_positions: dict[str, float] | None = None
    lock_limits = _dynamic_lock_force_by_joint(project)
    setup_ready_at = time.perf_counter()
    distance_seconds = 0.0  # V2.15.10: deferred by selected-pair Job

    # Simulate from t=0 to the requested end; record only requested sample times.
    for index, target_time in enumerate(times):
        if should_cancel and should_cancel():
            raise InterruptedError("simulation cancelled")
        while data.time + 1e-12 < float(target_time):
            step_time = float(data.time)
            if cached_command_time is not None and abs(cached_command_time - step_time) <= 1e-10:
                step_positions = cached_positions
            elif next_control_time is not None and abs(next_control_time - step_time) <= 1e-10:
                step_positions = next_control_positions
            else:
                step_positions = _display_positions(project, schedule, step_time, joint_lookup=lookup)
            # Evaluate once for the next step. The same result is used by the
            # current self-lock check and becomes next step's drive command.
            projected_time = step_time + float(model.opt.timestep)
            projected_positions = _display_positions(project, schedule, projected_time, joint_lookup=lookup)
            _step_dynamic_with_drive_controls(
                mujoco, model, data, project=project, schedule=schedule,
                actuator_ids=actuator_ids, addresses=addresses, dof_addresses=dof_addresses,
                lookup=lookup, base_qpos=base_qpos, positions=step_positions,
                next_positions=projected_positions, lock_limits=lock_limits,
            )
            next_control_time = projected_time
            next_control_positions = projected_positions
            cached_command_time = None
            cached_positions = None
            if should_cancel and should_cancel():
                raise InterruptedError("simulation cancelled")
        # Refresh command at exact sample for ctrl trace, without changing qpos. The same
        # command is cached for the next fixed step so schedule/mapping evaluation is not
        # repeated at an identical timestamp.
        positions = _display_positions(project, schedule, float(target_time), joint_lookup=lookup)
        cached_command_time = float(target_time)
        cached_positions = positions
        _set_dynamic_position_controls(
            data, actuator_ids=actuator_ids, addresses=addresses, lookup=lookup,
            base_qpos=base_qpos, positions=positions,
        )
        mujoco.mj_forward(model, data)
        qpos_frames.append(data.qpos.copy())
        qvel_frames.append(data.qvel.copy())
        qacc_frames.append(data.qacc.copy())
        ctrl_frames.append(data.ctrl.copy())
        contacts.append(int(data.ncon))
        # Distance curves are deliberately NOT computed as part of trajectory
        # refresh. UI selection schedules one pair via the existing JobManager.
        # See compute_selected_viewer_distance_curve below.
        if progress and (index % max(1, len(times)//100) == 0 or index == len(times)-1):
            progress((index+1)/max(len(times),1), f"Dynamic trajectory {index+1}/{len(times)}")

    result_ready_at = time.perf_counter()
    qpos = np.asarray(qpos_frames, dtype=float)
    qvel = np.asarray(qvel_frames, dtype=float)
    qacc = np.asarray(qacc_frames, dtype=float)
    ctrl = np.asarray(ctrl_frames, dtype=float) if model.nu else np.zeros((len(times),0),dtype=float)
    payload = _write_results(project, result_dir, mode="dynamic", times=times, qpos=qpos, qvel=qvel, qacc=qacc, ctrl=ctrl, base_qpos=base_qpos, addresses=addresses, dof_addresses=dof_addresses, schedule=schedule, variables=variables, contacts=contacts, distance_values=distance_values, model=model)
    payload["artifacts"].update(generated)
    completed_at = time.perf_counter()
    payload["timings_seconds"] = {
        "scene_and_runtime_setup": round(setup_ready_at - started_at, 4),
        "xml_generation": round(xml_generated_at - started_at, 4),
        "model_compile_and_load": round(model_loaded_at - xml_generated_at, 4),
        "runtime_binding": round(setup_ready_at - model_loaded_at, 4),
        "dynamic_stepping": round(result_ready_at - setup_ready_at - distance_seconds, 4),
        "distance_evaluation": round(distance_seconds, 4),
        "result_serialization": round(completed_at - result_ready_at, 4),
        "total": round(completed_at - started_at, 4),
        "sample_count": int(len(times)),
    }
    return payload


def run_project_simulation(
    project: ProjectSpec, result_dir: Path, *, variable_overrides: dict[str, float] | None = None,
    progress: ProgressCallback | None = None, should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    if project.simulation.engine == "analytical" and project.solver_mode == "kinematic" and not project.kinematic_closures:
        return run_analytical_simulation(project, result_dir, variable_overrides=variable_overrides, progress=progress, should_cancel=should_cancel)
    if project.solver_mode == "dynamic":
        return run_dynamic_simulation(project, result_dir, variable_overrides=variable_overrides, progress=progress, should_cancel=should_cancel)
    return run_kinematic_simulation(project, result_dir, variable_overrides=variable_overrides, progress=progress, should_cancel=should_cancel)


def run_mujoco_simulation(
    project: ProjectSpec, result_dir: Path, *, variable_overrides: dict[str, float] | None = None,
    progress: ProgressCallback | None = None, should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    """Compatibility alias used by older tools."""
    return run_dynamic_simulation(project, result_dir, variable_overrides=variable_overrides, progress=progress, should_cancel=should_cancel) if project.solver_mode == "dynamic" else run_kinematic_simulation(project, result_dir, variable_overrides=variable_overrides, progress=progress, should_cancel=should_cancel)


# Demand-driven distance curves reuse the native Viewer's sampled-point metric.
# V2.16.6: the trajectory is already frozen; unlike its physical integration,
# its individual poses can be evaluated independently by private MjData workers.
def compute_viewer_distance_curves(
    scene_path: str | Path, drives_path: str | Path, trajectory_path: str | Path,
    pair_ids: list[str] | None = None, *, progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
    partial: Callable[[dict[str, dict[str, object]]], None] | None = None,
    pair_workers: int = 5,
    shared_context: dict[str, Any] | None = None,
) -> dict[str, dict[str, object]]:
    """Evaluate exact sampled-surface distances in bounded, independent frame chunks.

    A previously solved qpos trajectory supplies all sampled poses.  We are NOT
    stepping dynamics in parallel: each thread owns its own ``MjData`` and
    mutable query buffers, sharing only read-only ``MjModel`` and KD indexes.
    ``mj_kinematics`` computes the same geom transforms used by ``mj_forward``
    without repeatedly solving contacts/actuators for a read-only distance
    query.  Completed chunks are merged by *global frame index*, never by
    thread completion order. Published partials contain only contiguous frames.
    """
    import os
    import threading
    from time import perf_counter as clock
    from .parallel_sampling import frame_worker_count, iter_frame_batches
    from .viewer_runner import _build_distance_pairs, _clone_distance_pair, _measure_pair

    def check_cancel() -> None:
        if should_cancel and should_cancel():
            raise InterruptedError("已取消测距曲线计算")

    check_cancel()
    started_at = clock()
    mujoco = _require_mujoco()
    # Only a Job-local holder may survive waves. Never retain cross-lease state.
    prepared = shared_context if shared_context is not None else {}
    drives = prepared.get("drives")
    if drives is None:
        drives = json.loads(Path(drives_path).read_text(encoding="utf-8"))
        prepared["drives"] = drives
    requested = set(map(str, pair_ids)) if pair_ids is not None else None
    pairs = [item for item in drives.get("distance_pairs", ())
             if requested is None or str(item.get("id")) in requested]
    if not pairs or (requested is not None and {str(p.get("id")) for p in pairs} != requested):
        raise ValueError("测距对不在本次仿真的冻结配置中，请刷新坐标系后重试")
    if len({str(p.get("id")) for p in pairs}) != len(pairs):
        raise ValueError("本次仿真含重复测距对 ID")
    manifest = drives.get("mesh_manifest", {})
    if not isinstance(manifest, dict):
        raise ValueError("仿真数模映射信息无效")
    model = prepared.get("model")
    if model is None:
        model = load_generated_mujoco_model(scene_path, mujoco)
        prepared["model"] = model
    model_ready_at = clock()
    trajectory_data = prepared.get("trajectory_data")
    if trajectory_data is None:
        trajectory_data = load_qpos_trajectory(trajectory_path, expected_nq=int(model.nq))
        prepared["trajectory_data"] = trajectory_data
    times, qpos = trajectory_data
    if not len(times) or not np.all(np.isfinite(times)) or not np.all(np.isfinite(qpos)):
        raise ValueError("仿真轨迹为空或包含无效数值")
    trajectory_ready_at = clock()
    check_cancel()
    if progress:
        progress(0.01, "轨迹已读取；正在准备完全精确表面采样")
    def sampling_progress(done, amount, sample_count):
        check_cancel()
        if progress:
            progress(0.01 + 0.09 * done / max(1, amount),
                     f"表面采样 {done}/{amount} 对象 · {sample_count} 点")
    build_payload = {"mesh_manifest": manifest, "distance_sampling": drives.get("distance_sampling", {}),
                     "distance_pairs": pairs}
    try:
        runtime = _build_distance_pairs(
            mujoco, model, build_payload, progress=sampling_progress,
            geometry_sample_pool=prepared.setdefault("geometry_samples", {}),
        )
    except TypeError as exc:
        # Preserve compatibility with test/adaptor implementations of the
        # existing viewer builder that predate its optional pool argument.
        if "unexpected keyword argument 'geometry_sample_pool'" not in str(exc):
            raise
        runtime = _build_distance_pairs(mujoco, model, build_payload, progress=sampling_progress)
    if len(runtime) != len(pairs):
        raise ValueError("测距对缺少可用数模，请检查对象 A/B 的绑定")
    for pair in runtime:
        pair["_distance_low_latency"] = False
        pair["_distance_skip_display_points"] = True
        if any(not any(len(pair["samples"].get(gid, ())) for gid in pair[side])
               for side in ("group_a", "group_b")):
            raise ValueError(f"测距对“{pair['name']}”缺少网格表面点，不能使用 Viewer 的表面测距算法")
    sampling_ready_at = clock()
    # A Job-local geometryIndexPool shares one read-only sampled point cloud,
    # bounding sphere and cKDTree across all pairs AND subsequent pending waves.
    # Each worker still owns every mutable query/transformation array.
    index_pool = prepared.setdefault("geometry_indexes", {})
    runtime = [_clone_distance_pair(pair, geometry_index_pool=index_pool) for pair in runtime]
    index_ready_at = clock()
    total = len(times)
    requested_workers = min(5, max(1, int(pair_workers)), max(1, os.cpu_count() or 1))
    # Keep the first true contiguous partial responsive on long trajectories.
    # Small chunks also allow the bounded workers to balance unequal meshes.
    batch_size = min(150, max(32, math.ceil(total / (requested_workers * 6))))
    count = frame_worker_count(total, requested_workers, batch_size=batch_size)
    pair_count = len(runtime)
    curves: dict[str, dict[str, object]] = {
        str(pair["id"]): {
            "id": str(pair["id"]), "name": str(pair.get("name", pair["id"])),
            "unit": "mm", "method": "viewer_sampled_surface_v1", "status": "partial",
            "values": [], "minimum_mm": None, "minimum_time_s": None,
            "completed_frames": 0, "total_frames": total,
            "viewer_query_mode": "exact_all_samples", "pair_workers": count,
            "sample_count": int(pair.get("sample_count", 0)),
            "animation_spacing_mm": float(pair.get("animation_spacing_mm", 2.0)),
            "max_points_per_object": int(pair.get("max_points_per_object", 400)),
            "invalid_frames": 0,
        } for pair in runtime
    }
    # Write block results only on the caller thread. NaN here represents the
    # legacy JSON null for an invalid geometric measurement.
    ordered = np.empty((total, pair_count), dtype=np.float64)
    completed: dict[int, int] = {}
    contiguous = 0
    evaluated = 0
    previous_partial = time.monotonic()
    published_prefix = 0
    worker_local = threading.local()
    reused_pose_frames = 0
    kinematics_worker_s = 0.0
    kd_worker_s = 0.0
    reused_pose_guard = threading.Lock()

    def evaluate_frames(start: int, stop: int, cancelled: Callable[[], bool]) -> np.ndarray:
        nonlocal reused_pose_frames, kinematics_worker_s, kd_worker_s
        local_kinematics_s = 0.0
        local_kd_s = 0.0
        context = getattr(worker_local, "context", None)
        if context is None:
            # Each worker owns its MjData and KD query arrays. Previous qpos
            # and distance row are likewise local and cannot cross threads.
            private_data = mujoco.MjData(model)
            if hasattr(private_data, "qvel"):
                private_data.qvel[:] = 0
            private_pairs = [_clone_distance_pair(pair, share_trees=True) for pair in runtime]
            context = [private_data, private_pairs, None, None]
            worker_local.context = context
        data, work_pairs = context[:2]
        block = np.empty((stop - start, pair_count), dtype=np.float64)
        block_reused = 0
        for offset, index in enumerate(range(start, stop)):
            if offset % 8 == 0 and cancelled():
                raise InterruptedError("已取消测距曲线计算")
            data.time = float(times[index])
            pose = qpos[index]
            # Static/hold segments repeat identical qpos at dozens of frames.
            # mj_kinematics and the fully exact KD result depend on qpos, not
            # the time stamp; reuse *only* bitwise-identical poses. Unlike
            # interpolating/downsampling this preserves every output frame.
            if context[2] is not None and np.array_equal(pose, context[2]):
                block[offset] = context[3]
                block_reused += 1
                continue
            data.qpos[:] = pose
            kin_start = clock()
            mujoco.mj_kinematics(model, data)
            local_kinematics_s += clock() - kin_start
            kd_start = clock()
            for column, pair in enumerate(work_pairs):
                distance_m, _line = _measure_pair(mujoco, model, data, pair)
                block[offset, column] = (float(distance_m) * 1000.0
                                         if math.isfinite(distance_m) else np.nan)
            local_kd_s += clock() - kd_start
            context[2] = pose.copy()
            context[3] = block[offset].copy()
        if cancelled():
            raise InterruptedError("已取消测距曲线计算")
        with reused_pose_guard:
            reused_pose_frames += block_reused
            kinematics_worker_s += local_kinematics_s
            kd_worker_s += local_kd_s
        return block

    def populate_curves(limit: int) -> None:
        """Publish an ordered prefix, preserving original minimum-tie semantics."""
        for column, pair in enumerate(runtime):
            values = ordered[:limit, column]
            finite = np.isfinite(values)
            curve = curves[str(pair["id"])]
            curve["values"] = [float(x) if math.isfinite(x) else None for x in values]
            curve["completed_frames"] = limit
            curve["invalid_frames"] = int(limit - np.count_nonzero(finite))
            if np.any(finite):
                minimum_index = int(np.argmin(np.where(finite, values, np.inf)))
                curve["minimum_mm"] = float(values[minimum_index])
                curve["minimum_time_s"] = float(times[minimum_index])
            else:
                curve["minimum_mm"] = None
                curve["minimum_time_s"] = None

    # Always close the iterator explicitly: callback failures must also join
    # and release worker threads, not rely on a garbage collector to do so.
    with closing(iter_frame_batches(
        total, evaluate_frames, should_cancel=should_cancel, workers=count,
        batch_size=batch_size, cancel_message="已取消测距曲线计算",
        thread_name_prefix="curve-frames",
    )) as batches:
        for start, stop, block in batches:
            check_cancel()
            if block.shape != (stop - start, pair_count):
                raise RuntimeError("测距批次输出维度错误")
            ordered[start:stop] = block
            evaluated += stop - start
            completed[start] = stop
            while contiguous in completed:
                contiguous = completed.pop(contiguous)
            if progress:
                progress(0.10 + 0.90 * evaluated / total, f"完全精确测距 {evaluated}/{total} 帧 · {pair_count} 对 · {count} 线程")
            now = time.monotonic()
            if partial and contiguous > published_prefix and contiguous < total and now - previous_partial >= 5.0:
                populate_curves(contiguous)
                # Avoid sending mutable published values while future chunks run.
                partial({key: {**curve, "values": curve["values"].copy()}
                         for key, curve in curves.items()})
                previous_partial = now
                published_prefix = contiguous
    check_cancel()
    populate_curves(total)
    completed_at = clock()
    candidate_count = sum(len(pair["_distance_runtime"].get("local_searches", ())) for pair in runtime)
    timings = {
        "snapshot_context_s": 0.0,  # frozen context is validated in HTTP handler
        "model_load_s": round(model_ready_at - started_at, 4),
        "trajectory_load_s": round(trajectory_ready_at - model_ready_at, 4),
        "sampling_s": round(sampling_ready_at - trajectory_ready_at, 4),
        "tree_build_s": round(index_ready_at - sampling_ready_at, 4),
        "kinematics_s": round(kinematics_worker_s, 4),  # summed worker CPU-wall time
        "kd_query_s": round(kd_worker_s, 4),  # summed worker CPU-wall time
        "cache_write_s": 0.0,  # file writes owned by the HTTP Job adapter
        "model_and_trajectory_s": round(trajectory_ready_at - started_at, 4),
        "surface_sampling_and_tree_s": round(index_ready_at - trajectory_ready_at, 4),
        "exact_distance_frames_s": round(completed_at - index_ready_at, 4),
        "total_s": round(completed_at - started_at, 4),
        "pair_count": pair_count,
        "unique_geom_count": len(index_pool),
        "candidate_pair_count": candidate_count,
        "reused_pose_frames": reused_pose_frames,
        "reused_identical_pose_frames": reused_pose_frames,
        "worker_count": count,
        "processed_frames": total,
        "geometry_searches_per_frame": candidate_count,
        "frame_count": total,
    }
    for curve in curves.values():
        if curve["minimum_time_s"] is None:
            raise ValueError(f"测距对“{curve['name']}”整段轨迹均无有效表面距离")
        curve["status"] = "ready"
        curve["timings_seconds"] = timings.copy()
    return curves


def compute_selected_viewer_distance_curve(
    scene_path: str | Path, drives_path: str | Path, trajectory_path: str | Path,
    pair_id: str, *, progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
    partial: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Compatibility entry for one pair, using the same fully exact evaluator."""
    curves = compute_viewer_distance_curves(
        scene_path, drives_path, trajectory_path, [str(pair_id)], progress=progress,
        should_cancel=should_cancel,
        partial=(lambda rows: partial(rows[str(pair_id)])) if partial else None,
    )
    return curves[str(pair_id)]
