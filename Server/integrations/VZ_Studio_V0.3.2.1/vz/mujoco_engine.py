from __future__ import annotations

import ast
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

from .simulation import timeline_values_at


class MuJoCoUnavailable(RuntimeError):
    pass


def safe_name(value: str, prefix: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_")
    if not name:
        name = prefix
    if name[0].isdigit():
        name = f"{prefix}_{name}"
    return name


def parse_vector(value: Any) -> list[float]:
    if isinstance(value, str):
        value = [x for x in re.split(r"[,，\s]+", value.strip()) if x]
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("三维坐标/矢量必须包含三个数")
    return [float(x) for x in value]


def _fmt(values: list[float]) -> str:
    return " ".join(f"{float(x):.12g}" for x in values)


def _rgba(value: str, opacity: float = 1.0) -> str:
    parts = [float(x) for x in re.split(r"[,，\s]+", str(value).strip()) if x]
    if len(parts) < 3:
        parts = [0.72, 0.75, 0.80, 1.0]
    while len(parts) < 4:
        parts.append(1.0)
    parts[3] *= opacity
    return _fmt(parts[:4])


def _layer_reference_origins_mm(model: dict[str, Any]) -> dict[str, list[float]]:
    """Return each layer body's world origin at the zero/reference pose.

    Engineer/second-generation point fields are world-space millimetres, while
    MuJoCo joint/site ``pos`` attributes are local to their body.  Layer static
    translations are the only reference-pose transform currently modeled, so a
    cumulative parent translation is sufficient for the world->local conversion.
    """
    layers = {str(layer.get("id")): layer for layer in model.get("layers", [])}
    cache: dict[str, list[float]] = {"root": [0.0, 0.0, 0.0]}

    def resolve(layer_id: str, stack: set[str] | None = None) -> list[float]:
        if layer_id in cache:
            return cache[layer_id]
        layer = layers.get(layer_id)
        if layer is None:
            return [0.0, 0.0, 0.0]
        active = set(stack or ())
        if layer_id in active:
            raise ValueError("层级关系存在循环")
        active.add(layer_id)
        parent = resolve(str(layer.get("parent_id", "root")), active)
        local = parse_vector(layer.get("position_mm", [0.0, 0.0, 0.0]))
        cache[layer_id] = [parent[i] + local[i] for i in range(3)]
        return cache[layer_id]

    for layer_id in layers:
        resolve(layer_id)
    return cache


def _world_point_to_body_local_mm(point: Any, layer_id: str, origins: dict[str, list[float]]) -> list[float]:
    world = parse_vector(point)
    origin = origins.get(str(layer_id), [0.0, 0.0, 0.0])
    return [world[i] - origin[i] for i in range(3)]


def build_mjcf(model: dict[str, Any], model_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    mesh_dir = output_dir / "meshes"
    mesh_dir.mkdir(exist_ok=True)
    root = ET.Element("mujoco", {"model": safe_name(model["name"], "vz_model")})
    ET.SubElement(root, "compiler", {"angle": "degree", "coordinate": "local", "meshdir": "meshes", "autolimits": "true"})
    ET.SubElement(root, "option", {"timestep": f"{float(model['simulation']['timestep']):.12g}", "gravity": "0 0 0", "integrator": "implicitfast"})
    defaults = ET.SubElement(root, "default")
    ET.SubElement(defaults, "joint", {"damping": "0.1", "armature": "0.01"})
    ET.SubElement(defaults, "geom", {"density": "1000", "contype": "0", "conaffinity": "0"})
    asset_el, world = ET.SubElement(root, "asset"), ET.SubElement(root, "worldbody")
    ET.SubElement(world, "light", {"pos": "0 0 4", "dir": "0 0 -1"})
    assets = {x["id"]: x for x in model.get("assets", [])}
    reference_origins_mm = _layer_reference_origins_mm(model)
    mesh_map: dict[str, str] = {}
    for index, layer in enumerate(model["layers"]):
        if not layer.get("active", True):
            continue
        for mesh in layer.get("meshes", []):
            source_info = assets.get(mesh.get("asset_id", ""))
            if not source_info:
                filename = str(mesh.get("filename", "") or "").strip()
                if filename:
                    raise ValueError(f"数模库中不存在已选择的数模：{filename}（层级“{layer['name']}”）")
                continue
            source = model_dir / "assets" / source_info["stored_name"]
            if not source.is_file():
                raise ValueError(f"数模文件不存在：{source_info['name']}")
            target = mesh_dir / f"mesh_{index:04d}_{safe_name(mesh['id'], 'mesh')}{source.suffix.lower()}"
            shutil.copy2(source, target)
            mesh_name = safe_name(mesh["id"], "mesh")
            mesh_map[mesh["id"]] = mesh_name
            ET.SubElement(asset_el, "mesh", {"name": mesh_name, "file": target.name, "scale": "0.001 0.001 0.001"})
    bodies: dict[str, ET.Element] = {"root": world}
    body_names: dict[str, str] = {}
    joint_names: dict[str, str] = {}
    joint_types: dict[str, str] = {}
    remaining = [x for x in model["layers"] if x.get("active", True)]
    while remaining:
        progressed = False
        for layer in list(remaining):
            if layer["parent_id"] not in bodies:
                continue
            body_name = safe_name(f"body_{layer['id']}", "body")
            body = ET.SubElement(bodies[layer["parent_id"]], "body", {"name": body_name, "pos": _fmt([x * 0.001 for x in layer["position_mm"]])})
            bodies[layer["id"]] = body
            body_names[layer["id"]] = body_name
            for joint in layer.get("joints", []):
                joint_name = safe_name(f"joint_{joint['id']}", "joint")
                kind = "slide" if joint["type"] in {"translation", "crank"} else "hinge"
                axis = parse_vector(joint.get("slide_axis" if joint["type"] == "crank" else "axis", "1, 0, 0"))
                if joint.get("reverse"):
                    axis = [-x for x in axis]
                attrs = {"name": joint_name, "type": kind, "axis": _fmt(axis)}
                if kind == "hinge":
                    local_point = _world_point_to_body_local_mm(joint.get("point", "0, 0, 0"), layer["id"], reference_origins_mm)
                    attrs["pos"] = _fmt([x * 0.001 for x in local_point])
                if joint.get("limited"):
                    lo, hi = map(float, joint.get("range", [-180, 180]))
                    if kind == "slide":
                        lo, hi = lo * 0.001, hi * 0.001
                    attrs.update({"limited": "true", "range": f"{lo:.12g} {hi:.12g}"})
                ET.SubElement(body, "joint", attrs)
                joint_names[joint["id"]] = joint_name
                joint_types[joint["id"]] = joint["type"]
            emitted = 0
            for mesh in layer.get("meshes", []):
                if mesh["id"] not in mesh_map:
                    continue
                ET.SubElement(body, "geom", {"name": safe_name(f"geom_{mesh['id']}", "geom"), "type": "mesh", "mesh": mesh_map[mesh["id"]], "rgba": _rgba(mesh.get("rgba") or layer["color"], float(mesh.get("opacity", 1))), "contype": "0", "conaffinity": "0"})
                emitted += 1
            if layer.get("joints") and not emitted:
                ET.SubElement(body, "inertial", {"pos": "0 0 0", "mass": "0.001", "diaginertia": "0.000001 0.000001 0.000001"})
            remaining.remove(layer)
            progressed = True
        if not progressed:
            raise ValueError("层级关系无法生成 MuJoCo body 树")
    site_map: dict[str, dict[str, str]] = {}
    for closure in model.get("kinematic_closures", []):
        if not closure.get("enabled", True):
            continue
        names = {"a": safe_name(f"site_{closure['id']}_a", "site"), "b": safe_name(f"site_{closure['id']}_b", "site")}
        for side in ("a", "b"):
            endpoint = closure[f"endpoint_{side}"]
            local_point = _world_point_to_body_local_mm(endpoint["point_mm"], endpoint["layer_id"], reference_origins_mm)
            ET.SubElement(bodies[endpoint["layer_id"]], "site", {"name": names[side], "pos": _fmt([x * 0.001 for x in local_point]), "size": "0.0005", "rgba": "0 0 0 0"})
        site_map[closure["id"]] = names
    ET.indent(root, space="  ")
    xml_path = output_dir / "model.xml"
    xml_path.write_text(ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")
    metadata = {"joint_names": joint_names, "joint_types": joint_types, "body_names": body_names, "site_names": site_map}
    (output_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"xml_path": xml_path, "xml": xml_path.read_text("utf-8"), "metadata": metadata}


_OPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: a**b, ast.USub: lambda a: -a, ast.UAdd: lambda a: a}


def expression(value: Any, variables: dict[str, Any]) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    tree = ast.parse(str(value), mode="eval")
    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Expression): return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return float(node.value)
        if isinstance(node, ast.Name) and node.id in variables: return expression(variables[node.id], variables)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS: return _OPS[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS: return _OPS[type(node.op)](visit(node.operand))
        raise ValueError(f"不允许的表达式：{value}")
    return float(visit(tree))


def resolve_schedule(model: dict[str, Any]) -> list[dict[str, Any]]:
    variables = model.get("variables", {})
    rows: list[dict[str, Any]] = []
    by_ref: dict[str, dict[str, Any]] = {}
    pending = [(drive, segment) for drive in model["drives"] if drive.get("enabled", True) and drive.get("joint_id") for segment in drive.get("segments", [])]
    while pending:
        progressed = False
        for drive, segment in list(pending):
            if segment.get("start_mode", "direct") == "reference":
                reference = by_ref.get(str(segment.get("reference", "")))
                if reference is None:
                    continue
                boundary = reference["start"] if segment.get("reference_boundary") == "start" else reference["end"]
                start = boundary + expression(segment.get("start", 0), variables)
            else:
                start = expression(segment.get("start", 0), variables)
            travel = expression(segment.get("travel", 0), variables)
            mode = str(segment.get("mode", "duration"))
            if mode == "speed":
                speed = abs(expression(segment.get("speed", drive.get("rated_speed", 30)), variables))
                if speed <= 0: raise ValueError(f"运动段“{segment['name']}”速度必须大于 0")
                duration = max(abs(travel) / speed, 0.001)
            else:
                duration = expression(segment.get("duration", 1), variables)
                speed = abs(travel) / duration if duration > 0 else 0.0
            if duration <= 0: raise ValueError(f"运动段“{segment['name']}”时长必须大于 0")
            row = {"drive_id": drive["id"], "drive_name": drive["name"], "joint_id": drive["joint_id"], "segment_id": segment["id"], "segment_name": segment["name"], "start": start, "end": start + duration, "duration": duration, "mode": mode, "speed": speed, "travel": travel, "profile": segment.get("profile", "s_curve"), "ease_in": bool(segment.get("ease_in", True)), "ease_out": bool(segment.get("ease_out", True))}
            rows.append(row);by_ref[f"{drive['name']}/{segment['name']}"] = row;pending.remove((drive, segment));progressed = True
        if not progressed:
            raise ValueError("运动段相对时间引用不存在或形成循环")
    return sorted(rows, key=lambda x: (x["start"], x["drive_name"], x["segment_name"]))


def _shape(profile: str, x: float) -> float:
    x = max(0.0, min(1.0, x))
    if profile == "smoothstep": return x * x * (3 - 2 * x)
    if profile == "s_curve": return x**3 * (x * (x * 6 - 15) + 10)
    return x


def positions_at(schedule: list[dict[str, Any]], time_s: float) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in schedule:
        prior = result.get(row["joint_id"], 0.0)
        if time_s < row["start"]: continue
        if time_s >= row["end"]: result[row["joint_id"]] = prior + row["travel"]
        else: result[row["joint_id"]] = prior + row["travel"] * _shape(row["profile"], (time_s - row["start"]) / row["duration"])
    return result


def _require_mujoco():
    try:
        import mujoco  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as exc:
        raise MuJoCoUnavailable("当前 Python 尚未安装 mujoco/numpy；重新运行 run.py 会自动安装仿真依赖") from exc
    return mujoco, np


def _solve_closures(mujoco: Any, np: Any, mj_model: Any, data: Any, model: dict[str, Any], metadata: dict[str, Any], driven: set[str]) -> float:
    """Solve all enabled point closures as one coupled DLS system.

    V0.2.13.0 mirrors the second-generation Studio solver contract: all closure
    residuals are stacked and solved together, each closure can mask the passive
    joints it is allowed to move, damping is applied as lambda^2, and the current
    frame starts from the previous frame's solved qpos (handled by the caller).
    """
    constraints: list[dict[str, Any]] = []
    solve_ids: list[str] = []
    for closure in model.get("kinematic_closures", []):
        if not closure.get("enabled", True):
            continue
        site_names = metadata["site_names"].get(closure["id"], {})
        a = mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_SITE, site_names.get("a", ""))
        b = mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_SITE, site_names.get("b", ""))
        if a < 0 or b < 0:
            raise ValueError(f"闭链“{closure['name']}”端点未绑定到 MuJoCo site")
        allowed = [
            jid for jid in closure.get("solve_joint_ids", [])
            if jid not in driven
            and jid in metadata["joint_names"]
            and metadata["joint_types"].get(jid) in {"rotation", "translation"}
        ]
        if not allowed:
            raise ValueError(f"闭链“{closure['name']}”没有可用的非驱动从动运动副")
        for jid in allowed:
            if jid not in solve_ids:
                solve_ids.append(jid)
        constraints.append({"closure": closure, "a": a, "b": b, "allowed": tuple(allowed)})

    if not constraints:
        mujoco.mj_forward(mj_model, data)
        return 0.0

    bound: dict[str, tuple[int, int, int]] = {}
    for jid in solve_ids:
        jidx = mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_JOINT, metadata["joint_names"][jid])
        if jidx < 0:
            raise ValueError(f"闭链从动运动副“{jid}”未绑定到 MuJoCo joint")
        bound[jid] = (jidx, int(mj_model.jnt_qposadr[jidx]), int(mj_model.jnt_dofadr[jidx]))

    dof_columns = [bound[jid][2] for jid in solve_ids]
    joint_column = {jid: index for index, jid in enumerate(solve_ids)}

    def residuals() -> tuple[Any, dict[str, float]]:
        chunks = []
        per_constraint: dict[str, float] = {}
        for item in constraints:
            closure = item["closure"]
            error = np.asarray(data.site_xpos[item["a"]] - data.site_xpos[item["b"]], dtype=float)
            chunks.append(error)
            per_constraint[closure["id"]] = float(np.linalg.norm(error) * 1000.0)
        return np.concatenate(chunks), per_constraint

    def converged(per_constraint: dict[str, float]) -> bool:
        return all(
            per_constraint.get(item["closure"]["id"], math.inf) <= float(item["closure"]["tolerance_mm"])
            for item in constraints
        )

    mujoco.mj_forward(mj_model, data)
    residual, per_constraint = residuals()
    if converged(per_constraint):
        return max(per_constraint.values(), default=0.0)

    max_iterations = max(int(item["closure"]["max_iterations"]) for item in constraints)
    for _iteration in range(1, max_iterations + 1):
        rows = []
        for item in constraints:
            ja = np.zeros((3, mj_model.nv))
            jb = np.zeros((3, mj_model.nv))
            mujoco.mj_jacSite(mj_model, data, ja, None, item["a"])
            mujoco.mj_jacSite(mj_model, data, jb, None, item["b"])
            row = (ja - jb)[:, dof_columns]
            allowed = set(item["allowed"])
            for jid, column in joint_column.items():
                if jid not in allowed:
                    row[:, column] = 0.0
            rows.append(row)
        jacobian = np.vstack(rows)
        if not jacobian.size or not np.all(np.isfinite(jacobian)) or not np.all(np.isfinite(residual)):
            raise ValueError("闭链求解遇到奇异或非有限 Jacobian")

        damping = max(float(item["closure"]["damping"]) for item in constraints)
        system = jacobian @ jacobian.T + (damping * damping) * np.eye(jacobian.shape[0])
        try:
            solved = np.linalg.solve(system, residual)
        except np.linalg.LinAlgError:
            try:
                solved = np.linalg.lstsq(system, residual, rcond=None)[0]
            except np.linalg.LinAlgError as exc:
                raise ValueError("闭链求解遇到奇异 Jacobian") from exc
        delta = -(jacobian.T @ solved)
        if not np.all(np.isfinite(delta)):
            raise ValueError("闭链求解产生非有限关节修正量")

        for jid, raw_step in zip(solve_ids, delta):
            jidx, qadr, _dof = bound[jid]
            relevant = [item["closure"] for item in constraints if jid in item["allowed"]]
            if metadata["joint_types"][jid] == "translation":
                limit = min(float(item["max_slide_step_mm"]) for item in relevant) * 0.001
            else:
                limit = math.radians(min(float(item["max_angle_step_deg"]) for item in relevant))
            step = float(np.clip(raw_step, -limit, limit))
            next_value = float(data.qpos[qadr]) + step
            if bool(mj_model.jnt_limited[jidx]):
                next_value = float(np.clip(next_value, mj_model.jnt_range[jidx, 0], mj_model.jnt_range[jidx, 1]))
            data.qpos[qadr] = next_value

        mujoco.mj_forward(mj_model, data)
        residual, per_constraint = residuals()
        if converged(per_constraint):
            return max(per_constraint.values(), default=0.0)

    worst = max(constraints, key=lambda item: per_constraint.get(item["closure"]["id"], -math.inf))
    closure = worst["closure"]
    worst_residual = per_constraint.get(closure["id"], math.inf)
    raise ValueError(
        f"闭链“{closure['name']}”未在最大迭代次数内收敛，残差 {worst_residual:.6f} mm"
    )


def schedule_to_timeline(model: dict[str, Any], schedule: list[dict[str, Any]]) -> dict[str, Any]:
    drives = {drive["id"]: drive for drive in model.get("drives", [])}
    initial = {
        drive_id: float(drive.get("initial_position", drive["reverse_limit"] if drive.get("zero_at") == "reverse" else drive["forward_limit"]))
        for drive_id, drive in drives.items()
    }
    current = dict(initial)
    segments: list[dict[str, Any]] = []
    for index, row in enumerate(schedule):
        drive_id = str(row["drive_id"])
        if drive_id not in drives:
            continue
        start_value = float(current.get(drive_id, initial[drive_id]))
        end_value = start_value + float(row["travel"])
        segment = {
            "index": index,
            "drive_id": drive_id,
            "action_id": row.get("segment_id", ""),
            "start_value": start_value,
            "end_value": end_value,
            "start_time": float(row["start"]),
            "end_time": float(row["end"]),
            "duration": float(row["duration"]),
            "speed": float(row.get("speed", 0.0)),
            "mode": str(row.get("mode", "speed")),
            "profile": str(row.get("profile", "s_curve")),
        }
        segments.append(segment)
        current[drive_id] = end_value
    duration = max([float(item["end_time"]) for item in segments] or [0.001])
    return {"duration": max(duration, 0.001), "segments": segments, "initial": initial}


def _timeline_schedule(model: dict[str, Any], timeline: dict[str, Any]) -> list[dict[str, Any]]:
    drives = {drive["id"]: drive for drive in model.get("drives", [])}
    rows = []
    for segment in timeline.get("segments", []):
        drive = drives.get(str(segment.get("drive_id", "")), {})
        rows.append({
            "drive_id": segment.get("drive_id", ""),
            "drive_name": drive.get("name", ""),
            "joint_id": drive.get("joint_id", ""),
            "segment_id": segment.get("action_id", ""),
            "segment_name": next((x.get("name", "动作") for x in drive.get("segments", []) if x.get("id") == segment.get("action_id")), "动作"),
            "start": float(segment.get("start_time", 0.0)),
            "end": float(segment.get("end_time", 0.0)),
            "duration": float(segment.get("duration", 0.0)),
            "mode": str(segment.get("mode", "speed")),
            "speed": float(segment.get("speed", 0.0)),
            "travel": float(segment.get("end_value", 0.0)) - float(segment.get("start_value", 0.0)),
            "profile": str(segment.get("profile", "s_curve")),
            "ease_in": True,
            "ease_out": True,
        })
    return rows


def simulate_timeline(
    model: dict[str, Any],
    model_dir: Path,
    output_dir: Path,
    timeline: dict[str, Any],
    *,
    schedule: list[dict[str, Any]] | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    mujoco, np = _require_mujoco()
    output_dir.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(0.02, "生成 MuJoCo 模型")
    generated = build_mjcf(model, model_dir, output_dir / "generated")
    mj_model = mujoco.MjModel.from_xml_path(str(generated["xml_path"]))
    data = mujoco.MjData(mj_model)
    base = data.qpos.copy()
    joint_bind: dict[str, tuple[int, int]] = {}
    for joint_id, name in generated["metadata"]["joint_names"].items():
        idx = mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_JOINT, name)
        joint_bind[joint_id] = (idx, int(mj_model.jnt_qposadr[idx]))
    drive_bind: dict[str, tuple[str, int, str]] = {}
    driven_joint_ids: set[str] = set()
    for drive in model.get("drives", []):
        if not drive.get("enabled", True):
            continue
        joint_id = str(drive.get("joint_id", ""))
        if joint_id not in joint_bind:
            continue
        _idx, address = joint_bind[joint_id]
        drive_bind[str(drive["id"])] = (joint_id, address, generated["metadata"]["joint_types"][joint_id])
        driven_joint_ids.add(joint_id)
    dt = float(model.get("simulation", {}).get("timestep", 0.01))
    duration = max(float(timeline.get("duration", 0.001)), dt)
    times = np.arange(0.0, duration + dt * 0.5, dt)
    if len(times) == 0 or times[-1] < duration - 1e-12:
        times = np.append(times, duration)
    qpos = []
    max_residual = 0.0
    previous_qpos = base.copy()
    frame_total = max(len(times), 1)
    for frame_index, time_s in enumerate(times):
        # Continuation/warm-start: passive closure joints begin from the previous
        # solved frame instead of being reset to zero for every sample.
        data.qpos[:] = previous_qpos
        values = timeline_values_at(timeline, float(time_s))
        for drive_id, (_joint_id, address, kind) in drive_bind.items():
            value = float(values.get(drive_id, timeline.get("initial", {}).get(drive_id, 0.0)))
            data.qpos[address] = math.radians(value) if kind == "rotation" else value * 0.001
        max_residual = max(max_residual, _solve_closures(mujoco, np, mj_model, data, model, generated["metadata"], driven_joint_ids))
        mujoco.mj_forward(mj_model, data)
        previous_qpos = data.qpos.copy()
        qpos.append(previous_qpos.copy())
        if progress and (frame_index == 0 or frame_index == frame_total - 1 or frame_index % max(1, frame_total // 40) == 0):
            progress(0.08 + 0.90 * ((frame_index + 1) / frame_total), f"MuJoCo 采样 {frame_index + 1}/{frame_total} 帧")
    result_schedule = schedule if schedule is not None else _timeline_schedule(model, timeline)
    result = {
        "times": times.tolist(),
        "qpos": np.asarray(qpos).tolist(),
        "schedule": result_schedule,
        "timeline": timeline,
        "joint_names": generated["metadata"]["joint_names"],
        "summary": {
            "engine": "MuJoCo", "mode": "kinematic", "frames": int(len(times)),
            "duration_s": float(duration), "nq": int(mj_model.nq), "nv": int(mj_model.nv),
            "nbody": int(mj_model.nbody), "ngeom": int(mj_model.ngeom),
            "max_closure_residual_mm": max_residual,
        },
    }
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    if progress:
        progress(1.0, "MuJoCo 轨迹生成完成")
    return result


def simulate(
    model: dict[str, Any],
    model_dir: Path,
    output_dir: Path,
    *,
    progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    schedule = resolve_schedule(model)
    timeline = schedule_to_timeline(model, schedule)
    return simulate_timeline(model, model_dir, output_dir, timeline, schedule=schedule, progress=progress)
