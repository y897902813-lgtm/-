from __future__ import annotations

import csv
import io
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from .models import DriveSpec, ProjectSpec
from .motion import ScheduleResolutionError, resolve_schedule

TIME_SERIES_SCHEMA = "vz_time_series_library"
TIME_SERIES_SCHEMA_VERSION = "1.0"
MAPPING_TABLE_SUFFIX = "映射表格.csv"


def _dump(model: Any, **kwargs: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


def _validate_drive(data: dict[str, Any]) -> DriveSpec:
    if hasattr(DriveSpec, "model_validate"):
        return DriveSpec.model_validate(data)
    return DriveSpec.parse_obj(data)


def safe_csv_stem(value: str, fallback: str = "时序") -> str:
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", str(value or "")).strip(" ._")
    return text[:96] or fallback


def is_mapping_table_name(name: str) -> bool:
    return str(name or "").endswith(MAPPING_TABLE_SUFFIX)


def _joint_name_map(project: ProjectSpec) -> dict[str, str]:
    return {
        str(joint.id): str(joint.name or joint.id)
        for layer in project.layers
        for joint in layer.joints
    }


def _resolved_schedule(project: ProjectSpec) -> dict[tuple[str, str], Any]:
    try:
        _variables, schedule = resolve_schedule(project)
    except ScheduleResolutionError as exc:
        schedule = exc.partial_schedule
    except (ValueError, TypeError):
        schedule = []
    return {(str(item.drive_id), str(item.segment_id)): item for item in schedule}


def _finite_or_blank(value: Any) -> Any:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return number if math.isfinite(number) else ""


def build_time_series_bundle(
    project: ProjectSpec,
    axes: Iterable[dict[str, Any]],
    *,
    generated_at: datetime | None = None,
) -> tuple[str, str, list[tuple[str, str]]]:
    """Build one portable merged time-series CSV plus companion mapping tables.

    The CSV intentionally contains both human-readable columns and lossless JSON
    payload cells for drive/segment parameters.  Mapping rows are embedded in the
    main CSV and also emitted as standalone ``<drive>--<segment>映射表格.csv`` files.
    """
    timestamp = generated_at or datetime.now(timezone.utc)
    stamp = timestamp.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S")
    main_name = f"{safe_csv_stem(project.name, '模型')}--{stamp}时序.csv"
    joints = _joint_name_map(project)
    resolved = _resolved_schedule(project)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(["VZ_TIME_SERIES", TIME_SERIES_SCHEMA_VERSION, "schema", TIME_SERIES_SCHEMA])
    writer.writerow(["META", "model_id", project.id, "model_name", project.name, "generated_at", timestamp.isoformat()])
    writer.writerow(["COLUMNS", "record_type", "human_fields...", "json_payload"])

    mapping_files: list[tuple[str, str]] = []
    used_mapping_names: set[str] = set()
    for drive in project.drives:
        drive_data = _dump(drive, exclude={"segments"})
        joint_name = joints.get(str(drive.joint_id), str(drive.joint_id))
        writer.writerow([
            "DRIVE", drive.id, drive.name, drive.joint_id, joint_name,
            json.dumps(drive_data, ensure_ascii=False, separators=(",", ":")),
        ])
        for segment in drive.segments:
            segment_data = _dump(segment)
            item = resolved.get((str(drive.id), str(segment.id)))
            source_joint_name = joints.get(str(segment.mapping_source_joint_id), str(segment.mapping_source_joint_id or ""))
            writer.writerow([
                "SEGMENT", drive.id, segment.id, segment.name, segment.profile,
                _finite_or_blank(getattr(item, "start", "")),
                _finite_or_blank(getattr(item, "end", "")),
                source_joint_name,
                json.dumps(segment_data, ensure_ascii=False, separators=(",", ":")),
            ])
            point_kind = "MAPPING_POINT" if segment.profile == "mapping" else "POINT"
            for index, row in enumerate(segment.points or []):
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    continue
                writer.writerow([point_kind, drive.id, segment.id, index, row[0], row[1]])
            if segment.profile == "mapping" and segment.points:
                stem = f"{safe_csv_stem(drive.name, 'drive')}--{safe_csv_stem(segment.name, 'segment')}"
                name = f"{stem}映射表格.csv"
                suffix_index = 2
                while name.casefold() in used_mapping_names:
                    name = f"{stem}_{suffix_index}映射表格.csv"
                    suffix_index += 1
                used_mapping_names.add(name.casefold())
                mapping = io.StringIO(newline="")
                mw = csv.writer(mapping, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
                mw.writerow(["source", "target"])
                for row in segment.points:
                    if isinstance(row, (list, tuple)) and len(row) >= 2:
                        mw.writerow([row[0], row[1]])
                mapping_files.append((name, "\ufeff" + mapping.getvalue()))
                writer.writerow(["MAPPING_TABLE", drive.id, segment.id, name, len(segment.points)])

    writer.writerow(["RESULT_HEADER", "coordinate_system", "time_s", "curve", "value", "unit"])
    for axis in axes:
        axis_name = str(axis.get("name") or "坐标系")
        times = list(axis.get("times") or [])
        for curve in axis.get("curves") or []:
            values = list(curve.get("values") or [])
            label = str(curve.get("label") or "曲线")
            unit = str(curve.get("unit") or "")
            for index, sample_time in enumerate(times):
                if index >= len(values):
                    break
                value = values[index]
                if value is None or value == "":
                    continue
                writer.writerow(["RESULT", axis_name, sample_time, label, value, unit])
    return main_name, "\ufeff" + stream.getvalue(), mapping_files


def parse_time_series_csv(content: str, project: ProjectSpec | None = None) -> dict[str, Any]:
    """Parse a V2.13+ time-series CSV into authoritative DriveSpec payloads."""
    text = str(content or "").lstrip("\ufeff")
    if not text.strip():
        raise ValueError("时序 CSV 为空")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 2 or rows[0][0] != "VZ_TIME_SERIES":
        raise ValueError("不是 V2.13+ 时序库 CSV（缺少 VZ_TIME_SERIES 标记）")
    if str(rows[0][1]).strip() != TIME_SERIES_SCHEMA_VERSION:
        raise ValueError(f"不支持的时序库版本：{rows[0][1]}")

    joints_by_id: dict[str, str] = {}
    joints_by_name: dict[str, str] = {}
    if project is not None:
        for layer in project.layers:
            for joint in layer.joints:
                joints_by_id[str(joint.id)] = str(joint.id)
                joints_by_name[str(joint.name or "").strip()] = str(joint.id)

    drive_rows: dict[str, dict[str, Any]] = {}
    drive_order: list[str] = []
    segment_rows: dict[tuple[str, str], dict[str, Any]] = {}
    segment_order: dict[str, list[str]] = {}
    point_rows: dict[tuple[str, str], list[list[float]]] = {}
    segment_source_names: dict[tuple[str, str], str] = {}
    warnings: list[str] = []

    for row in rows[1:]:
        if not row:
            continue
        kind = str(row[0]).strip()
        if kind == "DRIVE" and len(row) >= 6:
            drive_id = str(row[1]).strip()
            try:
                payload = json.loads(row[5])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"驱动 {row[2] if len(row) > 2 else drive_id} 参数 JSON 无效") from exc
            if not isinstance(payload, dict):
                raise ValueError("驱动参数必须是 JSON 对象")
            payload["id"] = drive_id or str(payload.get("id", ""))
            payload["name"] = str(row[2] or payload.get("name", "act1"))
            raw_joint_id = str(row[3] or payload.get("joint_id", ""))
            joint_name = str(row[4] or "").strip()
            if joints_by_id:
                mapped = joints_by_id.get(raw_joint_id) or joints_by_name.get(joint_name)
                if mapped:
                    payload["joint_id"] = mapped
                else:
                    payload["joint_id"] = raw_joint_id
                    warnings.append(f"驱动“{payload['name']}”未在当前模型找到运动副“{joint_name or raw_joint_id}”，已保留原引用")
            else:
                payload["joint_id"] = raw_joint_id
            payload["segments"] = []
            if drive_id not in drive_rows:
                drive_order.append(drive_id)
            drive_rows[drive_id] = payload
            segment_order.setdefault(drive_id, [])
        elif kind == "SEGMENT" and len(row) >= 9:
            drive_id, segment_id = str(row[1]).strip(), str(row[2]).strip()
            try:
                payload = json.loads(row[8])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"运动段 {row[3] if len(row) > 3 else segment_id} 参数 JSON 无效") from exc
            if not isinstance(payload, dict):
                raise ValueError("运动段参数必须是 JSON 对象")
            payload["id"] = segment_id or str(payload.get("id", ""))
            payload["name"] = str(row[3] or payload.get("name", "seg1"))
            payload["profile"] = str(row[4] or payload.get("profile", "s_curve"))
            segment_rows[(drive_id, segment_id)] = payload
            segment_order.setdefault(drive_id, []).append(segment_id)
            segment_source_names[(drive_id, segment_id)] = str(row[7] or "").strip()
        elif kind in {"POINT", "MAPPING_POINT"} and len(row) >= 6:
            key = (str(row[1]).strip(), str(row[2]).strip())
            try:
                x, y = float(row[4]), float(row[5])
            except (TypeError, ValueError):
                continue
            if math.isfinite(x) and math.isfinite(y):
                point_rows.setdefault(key, []).append([x, y])

    if not drive_order:
        raise ValueError("时序 CSV 中没有 DRIVE 记录")

    output: list[dict[str, Any]] = []
    for drive_id in drive_order:
        drive = drive_rows[drive_id]
        segments: list[dict[str, Any]] = []
        for segment_id in segment_order.get(drive_id, []):
            key = (drive_id, segment_id)
            segment = segment_rows[key]
            if key in point_rows:
                segment["points"] = point_rows[key]
                if segment.get("profile") == "mapping":
                    segment["mapping_point_count"] = len(point_rows[key])
            source_id = str(segment.get("mapping_source_joint_id", "") or "")
            source_name = segment_source_names.get(key, "")
            if source_id and joints_by_id:
                segment["mapping_source_joint_id"] = joints_by_id.get(source_id) or joints_by_name.get(source_name) or source_id
                if segment["mapping_source_joint_id"] == source_id and source_id not in joints_by_id:
                    warnings.append(f"运动段“{segment.get('name', segment_id)}”的映射源“{source_name or source_id}”未在当前模型找到，已保留原引用")
            segment["csv_path"] = ""
            segments.append(segment)
        drive["segments"] = segments
        validated = _validate_drive(drive)
        output.append(_dump(validated))

    return {
        "schema": TIME_SERIES_SCHEMA,
        "schema_version": TIME_SERIES_SCHEMA_VERSION,
        "drives": output,
        "warnings": warnings,
    }


# V2.15.6: one canonical exchange format in the Studio time-series library.
# Legacy VZ CSV remains a *transient transport encoding* and a supported reader.
TSJSON_SCHEMA = "mujoco_studio_time_series"
TSJSON_SCHEMA_VERSION = 2
DELIVERY_TABLE_FOLDER = "表格文件夹"


def build_tsjson_bundle(
    project: ProjectSpec, axes: Iterable[dict[str, Any]], *,
    generated_at: datetime | None = None,
) -> tuple[str, str]:
    """Lossless drive specification + per-axis, independently sampled result channels."""
    now = generated_at or datetime.now(timezone.utc)
    name = f"{safe_csv_stem(project.name, '模型')}--{now.strftime('%Y%m%d_%H%M%S_%f')}时序.tsjson"
    channels: list[dict[str, Any]] = []
    for index, axis in enumerate(axes):
        channels.append({
            "axis_id": str(axis.get("id", "")),
            "name": str(axis.get("name") or f"坐标系{index + 1}"),
            "combine": str(axis.get("combine", "none")),
            "times": [_finite_or_blank(value) for value in axis.get("times", [])],
            "curves": [{
                "label": str(curve.get("label", "")),
                "unit": str(curve.get("unit", "")),
                "values": [_finite_or_blank(value) for value in curve.get("values", [])],
            } for curve in axis.get("curves", [])],
            "combined_curve": ({
                "label": str(axis["combined_curve"].get("label", "")),
                "unit": str(axis["combined_curve"].get("unit", "")),
                "values": [_finite_or_blank(v) for v in axis["combined_curve"].get("values", [])],
            } if isinstance(axis.get("combined_curve"), dict) else None),
        })
    # Include a readable joint name only in the portable exchange payload;
    # the ProjectSpec's joint_id remains the single authoritative reference.
    joint_names = _joint_name_map(project)
    exchange_drives: list[dict[str, Any]] = []
    for drive in project.drives:
        row = _dump(drive)
        row["joint_name"] = joint_names.get(str(drive.joint_id), "")
        exchange_drives.append(row)
    document = {
        "schema": TSJSON_SCHEMA, "schema_version": TSJSON_SCHEMA_VERSION,
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "model": {"id": project.id, "name": project.name},
        "drives": exchange_drives,
        "channels": channels,
    }
    return name, json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def parse_tsjson(content: str, project: ProjectSpec | None = None, *,
                 joint_mapping: dict[str, str] | None = None,
                 require_joint_match: bool = False,
                 source_joint_names: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        document = json.loads(str(content or "").lstrip("\ufeff"))
    except (ValueError, TypeError) as exc:
        raise ValueError("TSJSON 不是有效的 JSON") from exc
    if not isinstance(document, dict) or document.get("schema") != TSJSON_SCHEMA:
        raise ValueError("不是 MuJoCo Studio TSJSON 时序文件")
    if document.get("schema_version") != TSJSON_SCHEMA_VERSION:
        raise ValueError(f"不支持的 TSJSON 版本：{document.get('schema_version')}")
    drives = document.get("drives")
    channels = document.get("channels")
    if not isinstance(drives, list) or not isinstance(channels, list):
        raise ValueError("TSJSON 缺少 drives 或 channels 列表")
    output = []
    joint_ids = {j.id for layer in project.layers for j in layer.joints} if project else set()
    joint_names = {j.name: j.id for layer in project.layers for j in layer.joints} if project else {}
    warnings: list[str] = []
    unresolved: list[dict[str, Any]] = []
    target_joints = [joint for layer in project.layers for joint in layer.joints] if project else []
    target_names: dict[str, list[str]] = {}
    for joint in target_joints:
        target_names.setdefault(str(joint.name), []).append(str(joint.id))
    mapping = joint_mapping or {}
    for drive in drives:
        if not isinstance(drive, dict):
            raise ValueError("TSJSON 驱动必须是 JSON 对象")
        payload = dict(drive)
        exchange_joint_name = str(payload.pop("joint_name", ""))
        joint_id = str(payload.get("joint_id", ""))
        if require_joint_match:
            if project is None:
                raise ValueError("跨模型时序导入必须指定目标模型")
            display_name = str(payload.get("name") or payload.get("id") or "未命名驱动")
            # Use the stable source drive id as a key when a name is duplicated.
            prompt_key = f"{display_name} [{payload.get('id', '')}]"
            explicit = str(mapping.get(prompt_key, mapping.get(display_name, ""))).strip()
            if explicit and explicit not in joint_ids:
                raise ValueError(f"跨模型运动副映射不存在：{display_name} -> {explicit}")
            if explicit:
                resolved = explicit
            elif joint_id in joint_ids and (not exchange_joint_name or
                    next((str(j.name) for j in target_joints if str(j.id) == joint_id), None) == exchange_joint_name):
                resolved = joint_id
            else:
                candidates = target_names.get(exchange_joint_name, []) if exchange_joint_name else []
                resolved = candidates[0] if len(candidates) == 1 else None
            if not resolved:
                unresolved.append({"name": prompt_key, "suggested_joint":exchange_joint_name,
                    "joint_candidates":[{"id":str(j.id), "name":str(j.name)} for j in target_joints]})
            else:
                payload["joint_id"] = resolved
            # Mapping motors may reference a second source joint. This ID is
            # equally model-local, so never carry it into a different model.
            for segment in payload.get("segments", []):
                source_ref = str(segment.get("mapping_source_joint_id") or "")
                if not source_ref:
                    continue
                source_ref_name = (source_joint_names or {}).get(source_ref, "")
                segment_key = f"{prompt_key} / {segment.get('name') or segment.get('id')} · 映射源"
                selected_ref = str(mapping.get(segment_key, "")).strip()
                if selected_ref and selected_ref not in joint_ids:
                    raise ValueError(f"跨模型映射源运动副不存在：{selected_ref}")
                if selected_ref:
                    mapped_ref = selected_ref
                elif source_ref in joint_ids and (not source_ref_name or
                        next((str(j.name) for j in target_joints if str(j.id) == source_ref), None) == source_ref_name):
                    mapped_ref = source_ref
                else:
                    candidates = target_names.get(source_ref_name, []) if source_ref_name else []
                    mapped_ref = candidates[0] if len(candidates) == 1 else None
                if not mapped_ref:
                    unresolved.append({"name":segment_key, "suggested_joint":source_ref_name,
                        "joint_candidates":[{"id":str(j.id), "name":str(j.name)} for j in target_joints]})
                else:
                    segment["mapping_source_joint_id"] = mapped_ref
        elif project is not None and joint_id and joint_id not in joint_ids:
            mapped = joint_names.get(exchange_joint_name)
            if mapped:
                payload["joint_id"] = mapped
            else:
                warnings.append(f"驱动“{payload.get('name', joint_id)}”的运动副在当前模型中不存在，已保留原引用")
        output.append(_dump(_validate_drive(payload)))
    for axis in channels:
        if not isinstance(axis, dict) or not isinstance(axis.get("times", []), list) or not isinstance(axis.get("curves", []), list):
            raise ValueError("TSJSON 通道的 times/curves 结构无效")
    return {"schema": TSJSON_SCHEMA, "schema_version": TSJSON_SCHEMA_VERSION,
            "drives": output if not unresolved else [], "channels": channels,
            "warnings": warnings, "unresolved": unresolved}


def build_merged_axes_csv(axes: Iterable[dict[str, Any]]) -> str:
    """Plain wide CSV: time, one Y column per axis, exact union of sample times.

    Combined curves win over individual curves. Never interpolate absent samples.
    """
    sources: list[tuple[str, dict[float, Any]]] = []
    all_times: set[float] = set()
    seen_names: dict[str, int] = {}
    for index, axis in enumerate(axes):
        name = str(axis.get("name") or f"坐标系{index + 1}")
        seen_names[name] = seen_names.get(name, 0) + 1
        if seen_names[name] > 1:
            name = f"{name} ({seen_names[name]})"
        curves = list(axis.get("curves") or [])
        combined = axis.get("combined_curve")
        if not isinstance(combined, dict):
            combined = curves[-1] if axis.get("combine") in {"sum", "difference"} and curves else None
        selected = combined if isinstance(combined, dict) and combined.get("values") else next(
            (curve for curve in curves if curve.get("values")), None)
        if selected is None:
            continue
        series: dict[float, Any] = {}
        for time_value, y in zip(axis.get("times") or [], selected.get("values") or []):
            time_num = _finite_or_blank(time_value)
            if time_num == "":
                continue
            series[float(time_num)] = _finite_or_blank(y)
        all_times.update(series)
        sources.append((name, series))
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(["time", *[name for name, _ in sources]])
    for time_value in sorted(all_times):
        writer.writerow([time_value, *[series.get(time_value, "") for _, series in sources]])
    return "\ufeff" + stream.getvalue()


def parse_exported_timing(content: str, filename: str, project: ProjectSpec,
                          joint_mapping: dict[str, str] | None = None) -> dict[str, Any]:
    """Recover a legacy schedule without evaluating HTML JavaScript or Python.

    Any ambiguous drive is reported for explicit user mapping. Never invent
    motion curves, a mapping source, or ease-in/out durations.
    """
    import ast
    mapping = joint_mapping or {}
    joints = [joint for layer in project.layers for joint in layer.joints]
    joint_ids = {joint.id for joint in joints}
    joint_names: dict[str, list[str]] = {}
    for joint in joints:
        joint_names.setdefault(joint.name, []).append(joint.id)
    existing_drives = {}
    for drive in project.drives:
        existing_drives.setdefault(drive.name, []).append(drive)
    warnings: list[str] = []
    unresolved: list[dict[str, Any]] = []

    if filename.lower().endswith('.html'):
        match = re.search(r'\bconst\s+DATA\s*=\s*', content)
        if not match:
            raise ValueError('动画 HTML 缺少 Studio 导出的 const DATA 数据段')
        try:
            document, _ = json.JSONDecoder().raw_decode(content[match.end():].lstrip())
        except ValueError as exc:
            raise ValueError('动画 HTML 的内嵌数据无法解析') from exc
        if not isinstance(document, dict) or not isinstance(document.get('ganttRows'), list):
            raise ValueError('动画 HTML 没有可解析的 ganttRows')
        rows = document['ganttRows']
        html_drives = document.get('drives') if isinstance(document.get('drives'), list) else []
        warnings.append('动画 HTML 甘特图通常不包含原始缓起缓停参数、映射点表；缺失时关闭缓起缓停，不会伪造运动规律。')
    elif filename.lower().endswith('.py'):
        try:
            tree = ast.parse(content, filename=filename)
        except (SyntaxError, ValueError, RecursionError) as exc:
            raise ValueError('Python 文件语法不完整，无法读取静态清单') from exc
        candidates = [node.value for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
                      and (any(isinstance(t, ast.Name) and t.id == 'MUJOCO_TIMING_JSON' for t in node.targets)
                           if isinstance(node, ast.Assign) else isinstance(node.target, ast.Name)
                           and node.target.id == 'MUJOCO_TIMING_JSON')]
        if len(candidates) != 1:
            raise ValueError('Python 只接受一个顶层 MUJOCO_TIMING_JSON 静态清单；不会执行脚本')
        try:
            raw = ast.literal_eval(candidates[0])
            document = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
            raise ValueError('Python 时序清单必须是 JSON 字符串或 Python 字面量') from exc
        if not isinstance(document, dict):
            raise ValueError('Python 时序清单必须是对象')
        rows = document.get('ganttRows')
        html_drives = []
        if not isinstance(rows, list) and not isinstance(document.get('drives'), list):
            raise ValueError('Python 时序清单缺少 drives 或 ganttRows')
    else:
        raise ValueError('不支持的时序格式')

    def resolve_joint(name: str, proposed_id: str, hint: str = '') -> str | None:
        selected = str(mapping.get(name, '')).strip()
        if selected:
            if selected not in joint_ids:
                raise ValueError(f'驱动“{name}”映射到不存在的运动副 {selected}')
            return selected
        if proposed_id and proposed_id in joint_ids:
            return proposed_id
        if hint and len(joint_names.get(hint, [])) == 1:
            return joint_names[hint][0]
        matches = existing_drives.get(name, [])
        if len(matches) == 1 and matches[0].joint_id in joint_ids:
            return matches[0].joint_id
        if len(joint_names.get(name, [])) == 1:
            return joint_names[name][0]
        unresolved.append({'name': name, 'suggested_joint': hint, 'joint_candidates':
                           [{'id': joint.id, 'name': joint.name} for joint in joints]})
        warnings.append(f'“{name}”缺少唯一运动副映射；请选择目标运动副后重新解析')
        return None

    output = []
    if isinstance(document.get('drives'), list) and filename.lower().endswith('.py'):
        for index, raw_drive in enumerate(document['drives']):
            if not isinstance(raw_drive, dict):
                warnings.append(f'第 {index + 1} 个驱动结构无效，已跳过')
                continue
            payload = dict(raw_drive)
            name = str(payload.get('name') or f'驱动{index+1}')
            joint = resolve_joint(name, str(payload.get('joint_id') or ''), str(payload.pop('joint_name', '') or ''))
            if not joint:
                continue
            payload['joint_id'] = joint
            valid_segments = []
            for pos, segment in enumerate(payload.get('segments') or []):
                if not isinstance(segment, dict):
                    warnings.append(f'“{name}”第 {pos+1} 段无效，已跳过')
                    continue
                segment = dict(segment)
                # Explicit mapping profiles MUST have an embedded curve and an existing source.
                if segment.get('profile') == 'mapping':
                    source = str(segment.get('mapping_source_joint_id') or '')
                    if source.startswith('drive:'):
                        source_id = source[6:]
                        if not any(d.id == source_id for d in project.drives) and not any(
                            isinstance(d, dict) and d.get('id') == source_id for d in document['drives']):
                            warnings.append(f'“{name}”映射源驱动 {source_id} 不存在，映射段已跳过')
                            continue
                    elif source not in joint_ids:
                        candidates = joint_names.get(source, [])
                        if len(candidates) == 1:
                            segment['mapping_source_joint_id'] = candidates[0]
                        else:
                            warnings.append(f'“{name}”映射源运动副无法确定，映射段已跳过')
                            continue
                    if len(segment.get('points') or []) < 2:
                        warnings.append(f'“{name}”映射段缺少内嵌点表，已跳过，不依赖外部 CSV 路径')
                        continue
                try:
                    valid_segments.append(_dump(_validate_drive({'name': name, 'joint_id': joint,
                                                                 'segments': [segment]}).segments[0]))
                except (ValueError, TypeError) as exc:
                    warnings.append(f'“{name}”第 {pos+1} 段校验失败：{str(exc)[:100]}')
            if valid_segments:
                payload['segments'] = valid_segments
                try:
                    output.append(_dump(_validate_drive(payload)))
                except (ValueError, TypeError) as exc:
                    warnings.append(f'“{name}”驱动校验失败：{str(exc)[:100]}')
        return {'drives': output, 'channels': [], 'warnings': warnings, 'unresolved': unresolved,
                'lossy': bool(warnings or unresolved)}

    for idx, row in enumerate(rows or []):
        if not isinstance(row, dict) or not isinstance(row.get('segments'), list) or not row['segments']:
            continue
        name = str(row.get('name') or f'驱动{idx+1}')
        source_drive = None
        drive_index = row.get('driveIndex')
        if isinstance(drive_index, int) and 0 <= drive_index < len(html_drives):
            source_drive = html_drives[drive_index] if isinstance(html_drives[drive_index], dict) else None
        joint = resolve_joint(name, str((source_drive or {}).get('joint_id') or ''),
                              str((source_drive or {}).get('joint_name') or ''))
        if not joint:
            continue
        segments = []
        for pos, item in enumerate(row['segments']):
            try:
                start, end = float(item['start']), float(item['end'])
                travel = float(item['travelEnd']) - float(item['travelStart'])
            except (TypeError, KeyError, ValueError):
                warnings.append(f'“{name}”第 {pos+1} 段数据缺失，已跳过')
                continue
            if not all(math.isfinite(v) for v in (start, end, travel)) or end <= start:
                warnings.append(f'“{name}”第 {pos+1} 段时间/位移无效，已跳过')
                continue
            segments.append({'name': str(item.get('name') or f'运动段{pos+1}'),
                             'start': start, 'duration': end-start, 'travel': travel,
                             'profile': 's_curve', 'ease_in': False, 'ease_out': False,
                             'ease_in_time': 0.0, 'ease_out_time': 0.0, 'acceleration_time': 0.0,
                             'exchange_extra': {'legacy_import': 'gantt_only', 'curve_unknown': True}})
        if segments:
            output.append(_dump(_validate_drive({'name': name, 'joint_id': joint, 'segments': segments})))
    if not output and not unresolved:
        raise ValueError('没有可解析的甘特图驱动')
    return {'drives': output, 'channels': [], 'warnings': warnings, 'unresolved': unresolved,
            'lossy': True}
