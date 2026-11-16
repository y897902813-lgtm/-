from __future__ import annotations

import csv
import itertools
import json
import math
import random
from pathlib import Path
from typing import Callable, Protocol

from .crank import crank_displacement, crank_meta
from .models import OptimizationSettings, ProjectSpec, QuickOptimizationStep, SimulationSettings, VariableRange
from .motion import collect_boundaries, joint_positions, latest_drive_stop_time, resolve_schedule
from .simulation import build_time_grid, load_generated_mujoco_model
from .scratch import scratch_project
from .xml_generator import generate_project


def _range_values(item: VariableRange) -> list[float]:
    values: list[float] = []
    current = item.minimum
    while current <= item.maximum + item.step * 1e-9:
        values.append(round(current, 12))
        current += item.step
        if len(values) > 1_000_000:
            raise ValueError(f"range for {item.name} is too large")
    return values


def _candidate_overrides(settings: OptimizationSettings) -> list[dict[str, float]]:
    if not settings.variables:
        return [{}]
    if settings.mode == "grid":
        names = [item.name for item in settings.variables]
        products = itertools.product(*[_range_values(item) for item in settings.variables])
        return [dict(zip(names, values)) for values in itertools.islice(products, settings.trials)]
    rng = random.Random(settings.seed)
    seen: set[tuple[float, ...]] = set()
    rows: list[dict[str, float]] = []
    attempts = 0
    while len(rows) < settings.trials and attempts < settings.trials * 50:
        attempts += 1
        values = []
        for item in settings.variables:
            choices = _range_values(item)
            values.append(rng.choice(choices))
        key = tuple(values)
        if key in seen:
            continue
        seen.add(key)
        rows.append(dict(zip([item.name for item in settings.variables], values)))
    return rows


def run_optimization(
    project: ProjectSpec,
    result_dir: Path,
    *,
    progress: Callable[[float, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    # Optimization is L3 scratch work. Even though the current search mostly reads
    # project state and injects variable_overrides into motion resolution, detach
    # eagerly so later evaluators/search strategies cannot accidentally share or
    # mutate authoritative ProjectSpec objects used by live editing/manual Viewer.
    working = scratch_project(project)
    settings = working.optimization
    candidates = _candidate_overrides(settings)
    rows: list[dict[str, object]] = []
    for index, overrides in enumerate(candidates):
        if should_cancel and should_cancel():
            raise InterruptedError("optimization cancelled")
        variables, schedule = resolve_schedule(working, overrides)
        end_time = latest_drive_stop_time(schedule, working.simulation.start_time)
        row: dict[str, object] = {"trial": index + 1, **overrides, "EndTime": end_time}
        for name, value in variables.items():
            if name in {item.name for item in settings.variables}:
                row[name] = value
        passed = True
        for rule in settings.filters:
            value = row.get(rule.variable, variables.get(rule.variable))
            if value is None:
                passed = False
                continue
            numeric = float(value)
            if rule.minimum is not None and numeric < rule.minimum:
                passed = False
            if rule.maximum is not None and numeric > rule.maximum:
                passed = False
        row["passed"] = passed
        rows.append(row)
        if progress:
            progress((index + 1) / max(len(candidates), 1), f"Trial {index + 1}/{len(candidates)}")

    eligible = [row for row in rows if row["passed"]]
    objective = settings.objective
    reverse = settings.direction == "max"
    eligible.sort(key=lambda row: float(row.get(objective, float("-inf") if reverse else float("inf"))), reverse=reverse)
    best = eligible[0] if eligible else None
    result_dir.mkdir(parents=True, exist_ok=True)
    json_path = result_dir / "optimization_result.json"
    csv_path = result_dir / "optimization_result.csv"
    payload = {"project_id": project.id, "objective": objective, "direction": settings.direction, "trials": rows, "best": best}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fieldnames = sorted({key for row in rows for key in row}) if rows else ["trial", "EndTime", "passed"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    payload["artifacts"] = {"result": str(json_path), "csv": str(csv_path)}
    return payload


class ConstraintEvaluator(Protocol):
    def __call__(self, project: ProjectSpec) -> dict[str, float]: ...


def _joint_type(project: ProjectSpec, drive_id: str) -> str:
    joint_by_id = {joint.id: joint for layer in project.layers for joint in layer.joints}
    drive = next((item for item in project.drives if item.id == drive_id), None)
    joint = joint_by_id.get(drive.joint_id) if drive else None
    return joint.type if joint else "rotation"


def _default_quick_step(step: QuickOptimizationStep, joint_type: str) -> float:
    if step.step_size is not None:
        return float(step.step_size)
    if step.mode == "time":
        return 0.05
    return 1.0 if joint_type in {"translation", "crank"} else 0.1


def _find_segment(project: ProjectSpec, step: QuickOptimizationStep):
    drive = next((item for item in project.drives if item.id == step.drive_id), None)
    if drive is None:
        raise ValueError(f"快速寻优对象引用了不存在的驱动：{step.drive_id}")
    segment = next((item for item in drive.segments if item.id == step.segment_id), None)
    if segment is None:
        raise ValueError(f"快速寻优对象引用了不存在的运动段：{step.segment_id}")
    return segment


def apply_quick_results(project: ProjectSpec, values: dict[str, float]) -> ProjectSpec:
    """Apply step-id keyed values to a project copy; used by load and Viewer preview."""
    for step in project.quick_optimization.steps:
        if step.id not in values:
            continue
        segment = _find_segment(project, step)
        setattr(segment, step.field, float(values[step.id]))
    return project


def _constraint_rows(project: ProjectSpec, minima: dict[str, float]) -> tuple[bool, list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    passed = True
    if not project.distance_pairs:
        raise ValueError("快速寻优至少需要一个测距对")
    for pair in project.distance_pairs:
        value = float(minima.get(pair.id, float("nan")))
        boundary = float(pair.boundary_mm)
        item_passed = math.isfinite(value) and value > boundary
        rows.append({
            "pair_id": pair.id,
            "name": pair.name,
            "minimum_mm": value if math.isfinite(value) else None,
            "boundary_mm": boundary,
            "passed": item_passed,
        })
        passed = passed and item_passed
    return passed, rows


def _candidate_direction(step: QuickOptimizationStep, initial_feasible: bool, initial: float) -> float:
    if step.mode == "time":
        preferred = -1.0
    elif step.mode == "speed":
        preferred = -1.0 if step.speed_direction == "decrease" else 1.0
        if initial < 0:
            preferred *= -1.0
    else:
        preferred = -1.0 if initial < 0 else 1.0
    return preferred if initial_feasible else -preferred


def _quick_search_step(
    project: ProjectSpec,
    step: QuickOptimizationStep,
    evaluate: ConstraintEvaluator,
    *,
    on_trial: Callable[[int, float, bool], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    segment = _find_segment(project, step)
    initial = float(step.initial_value)
    setattr(segment, step.field, initial)
    initial_minima = evaluate(project)
    initial_feasible, initial_constraints = _constraint_rows(project, initial_minima)
    increment = _default_quick_step(step, _joint_type(project, step.drive_id))
    direction = _candidate_direction(step, initial_feasible, initial)
    last_feasible = initial if initial_feasible else None
    last_feasible_constraints = initial_constraints if initial_feasible else None
    last_constraints = initial_constraints
    if on_trial:
        on_trial(0, initial, initial_feasible)

    for attempt in range(1, step.max_attempts + 1):
        if should_cancel and should_cancel():
            raise InterruptedError("快速寻优已取消")
        candidate = initial + direction * increment * attempt
        if step.mode in {"time", "speed"} and initial >= 0:
            candidate = max(0.0, candidate)
        crossed_zero_speed = step.mode == "speed" and (
            (initial >= 0 and candidate <= 0) or (initial < 0 and candidate >= 0)
        )
        if crossed_zero_speed:
            if initial_feasible and last_feasible is not None:
                setattr(segment, step.field, float(last_feasible))
                return {
                    "step_id": step.id, "variable_name": step.variable_name,
                    "initial_value": initial, "result_value": float(last_feasible),
                    "attempts": attempt + 1, "status": "completed",
                    "boundary_found": True,
                    "constraints": last_feasible_constraints or last_constraints,
                }
            break
        if attempt > 1 and math.isclose(candidate, float(getattr(segment, step.field)), abs_tol=1e-12):
            break
        setattr(segment, step.field, candidate)
        minima = evaluate(project)
        feasible, constraints = _constraint_rows(project, minima)
        last_constraints = constraints
        if on_trial:
            on_trial(attempt, candidate, feasible)
        if initial_feasible:
            if not feasible:
                setattr(segment, step.field, float(last_feasible))
                return {
                    "step_id": step.id, "variable_name": step.variable_name,
                    "initial_value": initial, "result_value": float(last_feasible),
                    "attempts": attempt + 1, "status": "completed",
                    "boundary_found": True,
                    "constraints": last_feasible_constraints or initial_constraints,
                }
            last_feasible = candidate
            last_feasible_constraints = constraints
        elif feasible:
            setattr(segment, step.field, candidate)
            return {
                "step_id": step.id, "variable_name": step.variable_name,
                "initial_value": initial, "result_value": candidate,
                "attempts": attempt + 1, "status": "completed",
                "boundary_found": True, "constraints": constraints,
            }

    if initial_feasible and last_feasible is not None:
        setattr(segment, step.field, float(last_feasible))
        return {
            "step_id": step.id, "variable_name": step.variable_name,
            "initial_value": initial, "result_value": float(last_feasible),
            "attempts": step.max_attempts + 1, "status": "limit_reached",
            "boundary_found": False,
            "constraints": last_feasible_constraints or last_constraints,
        }
    setattr(segment, step.field, initial)
    return {
        "step_id": step.id, "variable_name": step.variable_name,
        "initial_value": initial, "result_value": None,
        "attempts": step.max_attempts + 1, "status": "no_feasible_value",
        "boundary_found": False, "constraints": last_constraints,
    }


class MuJoCoConstraintEvaluator:
    """Reuse one generated model while drive variables change between trials."""

    def __init__(self, project: ProjectSpec, work_dir: Path):
        try:
            import mujoco  # type: ignore
        except ImportError as exc:
            raise RuntimeError('快速寻优需要 MuJoCo；请安装 "mujoco>=3.1,<4"。') from exc
        self.mujoco = mujoco
        generated = generate_project(project, work_dir / "generated", check_files=True)
        drive_payload = json.loads(Path(generated["drives"]).read_text("utf-8"))
        self.model = load_generated_mujoco_model(generated["model"], mujoco)
        self.data = mujoco.MjData(self.model)
        self.base_qpos = self.data.qpos.copy()
        self.joint_lookup = {joint.id: joint for layer in project.layers for joint in layer.joints}
        self.target_addresses: dict[str, int] = {}
        for joint_id, name in drive_payload.get("joint_map", {}).items():
            mj_joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if mj_joint_id >= 0:
                self.target_addresses[joint_id] = int(self.model.jnt_qposadr[mj_joint_id])
        geom_ids_by_file: dict[str, list[int]] = {}
        for filename, names in drive_payload.get("mesh_manifest", {}).items():
            geom_ids_by_file[str(filename).casefold()] = [
                int(geom_id) for name in names
                if (geom_id := mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, name)) >= 0
            ]
        self.pairs: dict[str, tuple[list[int], list[int], float]] = {}
        for pair in project.distance_pairs:
            group_a = [gid for name in pair.objects_a for gid in geom_ids_by_file.get(name.casefold(), [])]
            group_b = [gid for name in pair.objects_b for gid in geom_ids_by_file.get(name.casefold(), [])]
            if not group_a or not group_b:
                raise ValueError(f"测距对“{pair.name}”没有可用的 A/B 几何体")
            distmax = max(float(pair.distmax_m), max(float(pair.boundary_mm), 0.0) * 0.001 + 0.001)
            self.pairs[pair.id] = (group_a, group_b, distmax)

    def __call__(self, project: ProjectSpec) -> dict[str, float]:
        _variables, schedule = resolve_schedule(project)
        end_time = max(project.simulation.end_time, max((item.end for item in schedule), default=project.simulation.end_time))
        settings = SimulationSettings(
            start_time=project.simulation.start_time,
            end_time=end_time,
            timestep=project.simulation.timestep,
            engine="mujoco",
        )
        times = build_time_grid(settings, collect_boundaries(schedule), include_boundaries=True)
        minima = {pair_id: float("inf") for pair_id in self.pairs}
        for time_s in times:
            raw_positions = joint_positions(schedule, float(time_s))
            self.data.qpos[:] = self.base_qpos
            for joint_id, value in raw_positions.items():
                if joint_id not in self.target_addresses or joint_id not in self.joint_lookup:
                    continue
                joint = self.joint_lookup[joint_id]
                display = crank_displacement(crank_meta(joint), value) if joint.type == "crank" else value
                internal = display * 0.001 if joint.type in {"translation", "crank"} else math.radians(display)
                address = self.target_addresses[joint_id]
                self.data.qpos[address] = self.base_qpos[address] + internal
            self.mujoco.mj_forward(self.model, self.data)
            for pair_id, (group_a, group_b, distmax) in self.pairs.items():
                for geom_a in group_a:
                    for geom_b in group_b:
                        if geom_a == geom_b:
                            continue
                        value = max(float(self.mujoco.mj_geomDistance(
                            self.model, self.data, geom_a, geom_b, distmax, None,
                        )), 0.0) * 1000.0
                        minima[pair_id] = min(minima[pair_id], value)
        return minima


def run_quick_optimization(
    project: ProjectSpec,
    result_dir: Path,
    *,
    step_ids: list[str] | None = None,
    progress: Callable[[float, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    evaluator_factory: Callable[[ProjectSpec, Path], ConstraintEvaluator] = MuJoCoConstraintEvaluator,
) -> dict[str, object]:
    working = scratch_project(project)
    selected = set(step_ids or [])
    steps = [step for step in working.quick_optimization.steps if not selected or step.id in selected]
    if not steps:
        raise ValueError("快速寻优工作流中没有可执行对象")
    result_dir.mkdir(parents=True, exist_ok=True)
    evaluator = evaluator_factory(working, result_dir)
    results: list[dict[str, object]] = []
    total_budget = sum(step.max_attempts + 1 for step in steps)
    completed_trials = 0

    for index, step in enumerate(steps):
        def on_trial(attempt: int, value: float, feasible: bool) -> None:
            nonlocal completed_trials
            completed_trials += 1
            if progress:
                progress(
                    min(completed_trials / max(total_budget, 1), 0.99),
                    f"步骤 {index + 1}/{len(steps)} · {step.variable_name} · {value:.6g} · {'满足' if feasible else '不满足'}",
                )

        item = _quick_search_step(
            working, step, evaluator, on_trial=on_trial, should_cancel=should_cancel,
        )
        results.append(item)
        if item["result_value"] is None:
            break
    final_values = {
        str(item["step_id"]): float(item["result_value"])
        for item in results if item["result_value"] is not None
    }
    status = "completed" if len(results) == len(steps) and all(item["result_value"] is not None for item in results) else "partial"
    payload: dict[str, object] = {
        "project_id": project.id,
        "workflow_name": working.quick_optimization.name,
        "status": status,
        "steps": results,
        "final_values": final_values,
    }
    json_path = result_dir / "quick_optimization_result.json"
    csv_path = result_dir / "quick_optimization_result.csv"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["step_id", "variable_name", "initial_value", "result_value", "attempts", "status", "boundary_found"])
        writer.writeheader()
        writer.writerows({key: item.get(key) for key in writer.fieldnames} for item in results)
    payload["artifacts"] = {"result": str(json_path), "csv": str(csv_path)}
    if progress:
        progress(1.0, "快速寻优完成")
    return payload
