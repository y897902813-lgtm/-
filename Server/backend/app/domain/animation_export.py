"""Adapter from the Studio state tree to the V21.4.4.3.3 offline player."""
from __future__ import annotations

import base64
import json
import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .crank import crank_displacement, crank_meta
from .legacy_animation_html_export import export_interactive_animation_html
from .models import ProjectSpec
from .motion import drive_positions, joint_positions, mapping_gantt_blocks, resolve_schedule
from .simulation import load_qpos_trajectory, run_project_simulation, sample_qpos_trajectory
from .xml_generator import generate_project, load_with_mujoco


Progress = Callable[[float, str], None]


class AnimationExportDiagnosticError(ValueError):
    """Job-safe structured diagnostic for export failures that need UI detail."""

    def __init__(self, payload: Mapping[str, Any]):
        self.job_error = dict(payload)
        super().__init__(str(self.job_error.get("message", "动画 HTML 导出失败")))


def _closure_diagnostic(exc: ValueError) -> dict[str, Any] | None:
    try:
        payload = json.loads(str(exc))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("code") != "kinematic_closure_nonconvergence":
        return None
    return {
        "code": "kinematic_closure_nonconvergence",
        "message": "闭链求解未收敛，无法生成动画 HTML",
        "closure_ids": list(payload.get("constraint_ids", []) or []),
        "time_s": payload.get("time_s"),
        "residual_mm": payload.get("residual_mm"),
        "iterations": payload.get("iterations"),
        "hint": payload.get("hint") or "请检查闭链约束、初始姿态与驱动行程；修正后重新运行仿真或导出动画。",
    }


def _assert_trajectory_nq_compatible(scene_path: str | Path, trajectory_qpos: np.ndarray) -> None:
    if trajectory_qpos.ndim != 2 or trajectory_qpos.shape[0] < 1:
        raise AnimationExportDiagnosticError({
            "code": "trajectory_invalid",
            "message": "trajectory.npz 不包含二维 qpos 轨迹",
            "hint": "请重新运行仿真后再导出动画 HTML。",
        })
    model_info = load_with_mujoco(str(scene_path))
    model_nq = int(model_info["nq"])
    trajectory_nq = int(trajectory_qpos.shape[1])
    if trajectory_nq != model_nq:
        raise AnimationExportDiagnosticError({
            "code": "trajectory_nq_mismatch",
            "message": f"动画轨迹与当前模型自由度不一致：trajectory nq={trajectory_nq}, model nq={model_nq}",
            "trajectory_nq": trajectory_nq,
            "model_nq": model_nq,
            "hint": "当前模型拓扑已变化，请重新运行仿真后再导出动画 HTML。",
        })


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", str(value or "模型")).strip(" ._")
    return cleaned or "模型"


def _legacy_drive_payload(project: ProjectSpec, joint_map: Mapping[str, str]) -> tuple[list[dict[str, Any]], list[Any]]:
    _variables, schedule = resolve_schedule(project)
    joints = {joint.id: joint for layer in project.layers for joint in layer.joints}
    segments_by_drive: dict[str, list[Any]] = {}
    for segment in schedule:
        segments_by_drive.setdefault(segment.drive_id, []).append(segment)
    rows: list[dict[str, Any]] = []
    for drive in project.drives:
        if not drive.enabled or drive.joint_id not in joints:
            continue
        joint = joints[drive.joint_id]
        segments = []
        for segment in segments_by_drive.get(drive.id, []):
            if segment.profile == "mapping":
                for block in mapping_gantt_blocks(segment, schedule):
                    segments.append({
                        "name": block["name"],
                        "_start": float(block["start"]),
                        "_duration": float(block["duration"]),
                        "_end": float(block["end"]),
                        "travel": float(block["travel"]),
                        "_travel_start": float(block["travel_start"]),
                        "_travel_end": float(block["travel_end"]),
                        "motion_profile": "drive_mapping",
                    })
                continue
            segments.append({
                "name": segment.name,
                "_start": float(segment.start),
                "_duration": float(segment.duration),
                "_end": float(segment.end),
                "travel": float(segment.travel),
                "motion_profile": "drive_mapping" if segment.profile == "mapping" else segment.profile,
            })
        rows.append({
            "id": drive.id,
            "name": drive.name,
            "joint_id": drive.joint_id,
            "joint_name": str(joint_map.get(drive.joint_id, "")),
            "joint_type": joint.type,
            "segments": segments,
        })
    return rows, list(schedule)


def _legacy_project_payload(project: ProjectSpec, drives: list[dict[str, Any]], mesh_manifest: Mapping[str, Any]) -> dict[str, Any]:
    settings = project.animation_html
    return {
        "drives": drives,
        "mesh_manifest": dict(mesh_manifest),
        "pairs": [
            {
                "id": pair.id,
                "name": pair.name,
                "objects_a": list(pair.objects_a),
                "objects_b": list(pair.objects_b),
                "distmax": float(pair.distmax_m),
                "strategy_density_mode": "spacing_mm",
                "strategy_density_value": float(pair.animation_spacing_mm),
                "precise_density_mode": "spacing_mm",
                "precise_density_value": float(pair.precise_spacing_mm),
                "precise_enabled": True,
            }
            for pair in project.distance_pairs
        ],
        # V2.5.1.4: keep the authoritative Viewer measurement contract beside
        # the legacy fields so the exporter can use exactly the same surface
        # sampling budget/spacing and nearest-point evaluator as MuJoCo View.
        "distance_pairs": [pair.model_dump() for pair in project.distance_pairs],
        "distance_sampling": project.distance_sampling.model_dump(),
        "sim_start_time": float(project.simulation.start_time),
        "sim_end_time": float(project.simulation.end_time),
        "single_distance_strategy_enabled": True,
        "single_distance_precise_enabled": True,
        # V21 defaults to unsigned surface distance.  Negative penetration is
        # an explicit diagnostic option that Studio does not expose.
        "single_distance_interference_enabled": False,
        "animation_distance_follow_damping": settings.distance_follow_damping,
        "animation_adaptive_threshold_mm": settings.adaptive_threshold_mm,
        "animation_watermark_text": settings.watermark_text,
        "animation_watermark_position": settings.watermark_position_mm,
        "animation_watermark_size_mm": settings.watermark_size_mm,
        "animation_watermark_thickness_mm": settings.watermark_thickness_mm,
        "animation_watermark_color": settings.watermark_color,
    }


def _geom_to_file(model: Any, manifest: Mapping[str, Sequence[str]]) -> dict[str, list[int]]:
    import mujoco

    result: dict[str, list[int]] = {}
    for filename, geom_names in manifest.items():
        for geom_name in geom_names:
            geom_id = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, str(geom_name)))
            if geom_id >= 0:
                result.setdefault(str(filename), []).append(geom_id)
    return result


def _group_runtime(
    group_files: Sequence[str], geom_to_file: Mapping[str, Sequence[int]], model: Any,
    _strategy_mode: Any, strategy_value: Any, _precise_mode: Any,
    precise_value: Any, precise_enabled: Any,
) -> dict[str, Any]:
    from .viewer_runner import _mesh_surface_points

    items = []
    for name in group_files:
        for geom_id in geom_to_file.get(str(name), []):
            gid = int(geom_id)
            strategy = _mesh_surface_points(model, gid, max(float(strategy_value), 0.1), 600)
            precise = (
                _mesh_surface_points(model, gid, max(float(precise_value), 0.1), 1_200)
                if bool(precise_enabled) else np.empty((0, 3), dtype=float)
            )
            items.append({"gid": gid, "strategy_local": strategy, "precise_local": precise})
    return {"items": items}


def _world_group_points(group: Mapping[str, Any], data: Any, *, use_precise: bool = False, **_options: Any) -> np.ndarray:
    world = []
    for item in group.get("items", []):
        local = item.get("precise_local") if use_precise and len(item.get("precise_local", [])) else item.get("strategy_local")
        if local is None or not len(local):
            continue
        gid = int(item["gid"])
        matrix = np.asarray(data.geom_xmat[gid], dtype=float).reshape(3, 3)
        position = np.asarray(data.geom_xpos[gid], dtype=float)
        world.append(np.asarray(local, dtype=float) @ matrix.T + position)
    return np.concatenate(world, axis=0) if world else np.empty((0, 3), dtype=float)


def _viewer_distance_pair_builder(mujoco: Any, model: Any, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Reuse the native Viewer's distance-pair sampler for offline HTML."""
    from .viewer_runner import _build_distance_pairs

    return _build_distance_pairs(mujoco, model, dict(payload))


def _viewer_distance_pair_measure(
    mujoco: Any, model: Any, data: Any, pair_runtime: dict[str, Any],
) -> tuple[float, np.ndarray | None]:
    """Reuse the native Viewer's unsigned sampled-surface distance semantics."""
    from .viewer_runner import _measure_pair

    return _measure_pair(mujoco, model, data, pair_runtime)


def _gantt_snapshot(cache_dir: Path) -> tuple[str, dict[str, Any]]:
    png_path = cache_dir / "latest_gantt.png"
    json_path = cache_dir / "latest_gantt.json"
    try:
        metadata = json.loads(json_path.read_text("utf-8"))
        image = png_path.read_bytes()
        if not image:
            return "", {}
        return "data:image/png;base64," + base64.b64encode(image).decode("ascii"), metadata
    except (OSError, ValueError, TypeError):
        return "", {}




def _resolve_gantt_snapshot(
    project: ProjectSpec,
    generated_payload: Mapping[str, Any],
    cache_dir: Path,
    fallback_dir: Path,
) -> tuple[str, dict[str, Any], str, Path | None]:
    """Prefer the browser popup cache; render fallback only in an isolated directory."""
    image, metadata = _gantt_snapshot(cache_dir)
    if image:
        return image, metadata, "popup_cache", cache_dir / "latest_gantt.png"

    try:
        from .viewer_runner import _mapping_gantt_segments, _write_legacy_gantt_cache

        segments = [dict(item) for item in list(generated_payload.get("segments", []) or [])]
        cumulative: dict[str, float] = {}
        for segment in sorted(
            segments,
            key=lambda item: (str(item.get("drive_id", "")), float(item.get("start", 0.0))),
        ):
            drive_id = str(segment.get("drive_id", ""))
            start_value = cumulative.get(drive_id, 0.0)
            end_value = start_value + float(segment.get("travel", 0.0) or 0.0)
            segment["travel_start"] = start_value
            segment["travel_end"] = end_value
            cumulative[drive_id] = end_value
        gantt_segments = _mapping_gantt_segments(segments)
        drives = [dict(item) for item in list(generated_payload.get("drives", []) or []) if item.get("enabled", True)]
        fallback_dir.mkdir(parents=True, exist_ok=True)
        _write_legacy_gantt_cache(
            gantt_segments,
            drives,
            float(project.simulation.start_time),
            float(project.simulation.end_time),
            fallback_dir,
            runtime_segments=segments,
        )
        image, metadata = _gantt_snapshot(fallback_dir)
        if image:
            return image, metadata, "fallback_render", fallback_dir / "latest_gantt.png"
    except Exception:  # noqa: BLE001 - Gantt is supplemental and must never abort animation export.
        pass
    return "", {}, "unavailable", None

def export_project_animation_html(
    project: ProjectSpec,
    result_dir: Path,
    *,
    destination: Path | None = None,
    check_files: bool = True,
    progress: Progress | None = None,
    should_cancel: Callable[[], bool] | None = None,
    gantt_cache_dir: Path | None = None,
    gantt_fallback_dir: Path | None = None,
    trajectory_source: Path | None = None,
    trajectory_warnings: Sequence[str] | None = None,
    lab_identity: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Generate one fully offline interactive animation HTML artifact."""
    started_at = time.perf_counter()
    result_dir.mkdir(parents=True, exist_ok=True)
    generated = generate_project(project, result_dir / "generated", check_files=check_files)
    generated_payload = json.loads(Path(generated["drives"]).read_text("utf-8"))
    drives, schedule = _legacy_drive_payload(project, generated_payload.get("joint_map", {}))
    adapter_payload = _legacy_project_payload(project, drives, generated_payload.get("mesh_manifest", {}))
    adapter_payload["lab_identity"] = dict(lab_identity or {})
    adapter_path = result_dir / "animation_export_input.json"
    adapter_path.write_text(json.dumps(adapter_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    joints = {joint.id: joint for layer in project.layers for joint in layer.joints}

    # V2.5.1.4: HTML is a playback artifact, not a second solver.  Mirror the
    # native Viewer launch path and always create an authoritative MuJoCo qpos
    # trajectory from the current project snapshot.  Dynamic mode therefore
    # retains gravity/contact/equality effects (including natural leg droop and
    # closed chains); kinematic mode retains the same closure-solved qpos used
    # by Viewer instead of rebuilding poses from drive commands.
    runtime_project = ProjectSpec.model_validate(project.model_dump())
    runtime_project.simulation.engine = "mujoco"
    scene_ready_at = time.perf_counter()

    def simulation_progress(fraction: float, message: str) -> None:
        if progress is not None:
            progress(0.36 * float(fraction), f"动画轨迹：{message}")

    trajectory_path = Path(trajectory_source).resolve() if trajectory_source is not None else Path()
    reused_trajectory = trajectory_source is not None and trajectory_path.is_file()
    if reused_trajectory:
        if progress is not None:
            progress(0.36, "动画轨迹：复用当前仿真 trajectory.npz")
    else:
        try:
            simulation = run_project_simulation(
                runtime_project,
                result_dir / "simulation",
                progress=simulation_progress,
                should_cancel=should_cancel,
            )
        except ValueError as exc:
            diagnostic = _closure_diagnostic(exc)
            if diagnostic is not None:
                raise AnimationExportDiagnosticError(diagnostic) from exc
            raise
        trajectory_path = Path(str(simulation.get("artifacts", {}).get("trajectory", "")))
        if not trajectory_path.is_file():
            raise ValueError("动画 HTML 需要完整 trajectory.npz；MuJoCo 轨迹未生成")
    trajectory_times, trajectory_qpos = load_qpos_trajectory(trajectory_path)
    if reused_trajectory:
        _assert_trajectory_nq_compatible(generated["scene"], trajectory_qpos)
    trajectory_ready_at = time.perf_counter()

    def resolve_qpos(time_s: float) -> np.ndarray:
        frame = sample_qpos_trajectory(trajectory_times, trajectory_qpos, float(time_s))
        if frame is None:
            raise ValueError("trajectory.npz 不包含可用 qpos 帧")
        return frame

    def resolve_offsets(targets: Sequence[tuple[Mapping[str, Any], int]], time_s: float):
        display_drives = drive_positions(schedule, time_s)
        display_joints = joint_positions(schedule, time_s)
        sampled: dict[str, float] = {}
        qadr_by_joint: dict[str, int] = {}
        for drive, qadr in targets:
            drive_id = str(drive.get("id", ""))
            joint_id = str(drive.get("joint_id", ""))
            joint = joints.get(joint_id)
            value = float(display_drives.get(drive_id, 0.0))
            sampled[str(drive.get("name", drive_id))] = (
                math.radians(value) if joint is not None and joint.type in {"rotation", "crank"}
                else value * 0.001
            )
            qadr_by_joint.setdefault(joint_id, int(qadr))
        offsets = []
        for joint_id, qadr in qadr_by_joint.items():
            joint = joints.get(joint_id)
            if joint is None:
                continue
            value = float(display_joints.get(joint_id, 0.0))
            if joint.type == "crank":
                internal = crank_displacement(crank_meta(joint), value) * 0.001
            elif joint.type == "translation":
                internal = value * 0.001
            else:
                internal = math.radians(value)
            offsets.append((qadr, internal))
        return sampled, offsets

    def legacy_progress(message: str, fraction: float) -> None:
        if progress is not None:
            progress(0.36 + 0.64 * float(fraction), str(message))

    cache_dir = Path(gantt_cache_dir).resolve() if gantt_cache_dir is not None else (result_dir / "gantt_cache").resolve()
    fallback_dir = Path(gantt_fallback_dir).resolve() if gantt_fallback_dir is not None else (result_dir / "gantt_fallback").resolve()
    gantt_image, gantt_metadata, gantt_source, gantt_path = _resolve_gantt_snapshot(
        project, generated_payload, cache_dir, fallback_dir
    )
    gantt_ready_at = time.perf_counter()

    destination = destination or result_dir / f"{_safe_filename(project.name)}_anim.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = export_interactive_animation_html(
        generated["scene"], adapter_path, destination,
        fps=project.animation_html.fps,
        max_faces_per_mesh=project.animation_html.max_faces_per_mesh,
        schedule_resolver=lambda value: value,
        offset_resolver=resolve_offsets,
        qpos_resolver=resolve_qpos,
        geom_to_file_builder=_geom_to_file,
        group_runtime_builder=_group_runtime,
        world_group_points=_world_group_points,
        measurement_pair_builder=_viewer_distance_pair_builder,
        measurement_pair_evaluator=_viewer_distance_pair_measure,
        progress_callback=legacy_progress,
        gantt_snapshot_loader=lambda: (gantt_image, gantt_metadata),
        should_cancel=should_cancel,
    )
    completed_at = time.perf_counter()
    exporter_timings = dict(result.get("timings_seconds", {}))
    result["timings_seconds"] = {
        "scene_generation": round(scene_ready_at - started_at, 3),
        "trajectory_build_or_load": round(trajectory_ready_at - scene_ready_at, 3),
        "gantt_preparation": round(gantt_ready_at - trajectory_ready_at, 3),
        "html_export": round(completed_at - gantt_ready_at, 3),
        "total": round(completed_at - started_at, 3),
        "exporter": exporter_timings,
    }
    warnings = list(result.get("warnings", []) or [])
    for warning in list(trajectory_warnings or []):
        if warning not in warnings:
            warnings.append(str(warning))
    if gantt_source == "unavailable" and "gantt_snapshot_unavailable" not in warnings:
        warnings.append("gantt_snapshot_unavailable")
    result["warnings"] = warnings
    result["artifact"] = str(destination)
    result["artifact_relative"] = destination.name if destination.parent != result_dir else f"results/{result_dir.name}/{destination.name}"
    result["legacy_exporter_version"] = "21.4.4.3.3"
    result["studio_version"] = "2.16.11.6"
    result["trajectory"] = str(trajectory_path)
    result["trajectory_reused"] = bool(reused_trajectory)
    result["gantt_cache"] = str(gantt_path) if gantt_path is not None else ""
    result["gantt_source"] = gantt_source
    result["trajectory_solver_mode"] = runtime_project.solver_mode
    return result
