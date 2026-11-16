from __future__ import annotations

from typing import Any


def _clamp(drive: dict[str, Any], value: float) -> float:
    return max(float(drive["reverse_limit"]), min(float(drive["forward_limit"]), float(value)))


def _resolve_target(model: dict[str, Any], drive: dict[str, Any], step: dict[str, Any], memories: dict[str, dict[str, float]], current: float) -> float:
    end = step.get("end", {})
    mode = end.get("mode", "action")
    if mode == "memory":
        memory = memories.get(str(end.get("memory_id", "")), {})
        if drive["id"] not in memory:
            raise ValueError(f"所选记忆位置没有驱动“{drive['name']}”的数据")
        value = float(memory[drive["id"]])
    elif mode == "value":
        value = float(end.get("value", current))
    else:
        action = next((item for item in drive.get("actions", []) if item["id"] == step.get("action_id")), None)
        if action is None:
            raise ValueError(f"驱动“{drive['name']}”未选择有效动作")
        value = float(action["target"])
    return _clamp(drive, value)


def _shape(profile: str, x: float) -> float:
    x = max(0.0, min(1.0, float(x)))
    if profile in {"mapping", "linear"}:
        return x
    if profile == "smoothstep":
        return x * x * (3.0 - 2.0 * x)
    return x**3 * (x * (x * 6.0 - 15.0) + 10.0)


def build_timeline(
    model: dict[str, Any],
    steps: list[dict[str, Any]],
    initial_positions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    drives = {item["id"]: item for item in model.get("drives", [])}
    memories = {item["id"]: item.get("positions", {}) for item in model.get("memories", [])}
    initial = {
        item["id"]: float(item.get("initial_position", item["reverse_limit"] if item.get("zero_at") == "reverse" else item["forward_limit"]))
        for item in drives.values()
    }
    supplied = initial_positions if isinstance(initial_positions, dict) else {}
    for drive_id, value in supplied.items():
        drive = drives.get(str(drive_id))
        if drive is None:
            continue
        try:
            initial[drive["id"]] = _clamp(drive, float(value))
        except (TypeError, ValueError):
            raise ValueError(f"驱动“{drive['name']}”的当前动画位置无效") from None
    current = dict(initial)
    segments: list[dict[str, Any]] = []
    time_s = 0.0
    for index, step in enumerate(steps):
        drive = drives.get(str(step.get("drive_id", "")))
        if not drive:
            raise ValueError(f"第 {index + 1} 步的驱动对象无效")
        start = current[drive["id"]]
        start_spec = step.get("start", {})
        if start_spec.get("mode") == "memory":
            values = memories.get(str(start_spec.get("memory_id", "")), {})
            if drive["id"] not in values:
                raise ValueError(f"第 {index + 1} 步的起点记忆位置缺少该驱动")
            start = float(values[drive["id"]])
        elif start_spec.get("mode") == "value":
            start = float(start_spec.get("value", start))
        start = _clamp(drive, start)
        end = _resolve_target(model, drive, step, memories, start)
        speed = max(1e-6, float(drive["rated_speed"]))
        duration = max(0.001, abs(end - start) / speed)
        source_segment = next((item for item in drive.get("segments", []) if item.get("id") == step.get("action_id")), None)
        profile = str((source_segment or {}).get("profile", "s_curve"))
        segments.append({
            "index": index, "drive_id": drive["id"], "action_id": step.get("action_id", ""),
            "start_value": start, "end_value": end, "start_time": time_s, "end_time": time_s + duration,
            "duration": duration, "speed": speed, "mode": "speed", "profile": profile,
        })
        current[drive["id"]] = end
        time_s += duration
    return {"duration": max(time_s, 0.001), "segments": segments, "initial": initial}




def build_table_timeline(
    model: dict[str, Any],
    table_sequence: dict[str, Any],
    initial_positions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a timestamp-driven, multi-drive timeline from imported table data.

    ``table_sequence`` is produced by the user client after CSV parsing.  Each row
    has ``time`` in seconds and a ``positions`` mapping keyed by drive id.  Blank
    CSV cells are omitted from ``positions`` and therefore hold the previous
    value.  Values between two timestamps are linearly interpolated so every
    table timestamp is reached exactly.
    """
    if not isinstance(table_sequence, dict):
        raise ValueError("外部表格数据格式无效")
    rows = table_sequence.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("外部表格没有可执行的数据行")

    drives = {str(item["id"]): item for item in model.get("drives", [])}
    supplied = initial_positions if isinstance(initial_positions, dict) else {}
    initial: dict[str, float] = {}
    for drive_id, drive in drives.items():
        default = float(
            drive.get(
                "initial_position",
                drive["reverse_limit"] if drive.get("zero_at") == "reverse" else drive["forward_limit"],
            )
        )
        try:
            initial[drive_id] = _clamp(drive, float(supplied.get(drive_id, default)))
        except (TypeError, ValueError):
            raise ValueError(f"驱动“{drive['name']}”的当前动画位置无效") from None

    normalized_rows: list[tuple[float, dict[str, float]]] = []
    participating: set[str] = set()
    previous_time = -1.0
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"外部表格第 {index + 1} 行格式无效")
        try:
            time_s = float(row.get("time"))
        except (TypeError, ValueError):
            raise ValueError(f"外部表格第 {index + 1} 行时间无效") from None
        if time_s < 0:
            raise ValueError(f"外部表格第 {index + 1} 行时间不能小于 0")
        if time_s <= previous_time:
            raise ValueError("外部表格时间必须严格递增")
        previous_time = time_s

        raw_positions = row.get("positions", {})
        if not isinstance(raw_positions, dict):
            raise ValueError(f"外部表格第 {index + 1} 行位置数据格式无效")
        positions: dict[str, float] = {}
        for raw_drive_id, raw_value in raw_positions.items():
            drive_id = str(raw_drive_id)
            drive = drives.get(drive_id)
            if drive is None:
                raise ValueError(f"外部表格包含未知驱动 ID：{drive_id}")
            if drive.get("enabled", True) is False:
                raise ValueError(f"外部表格引用了已禁用驱动“{drive['name']}”")
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                raise ValueError(f"外部表格第 {index + 1} 行驱动“{drive['name']}”位置无效") from None
            low, high = float(drive["reverse_limit"]), float(drive["forward_limit"])
            if value < low - 1e-9 or value > high + 1e-9:
                raise ValueError(f"外部表格第 {index + 1} 行驱动“{drive['name']}”位置超出 {low:g} ~ {high:g}")
            positions[drive_id] = value
            participating.add(drive_id)
        normalized_rows.append((time_s, positions))

    if not participating:
        raise ValueError("外部表格没有可识别的驱动位置数据")

    current = dict(initial)
    segments: list[dict[str, Any]] = []
    interval_start = 0.0
    for row_index, (time_s, positions) in enumerate(normalized_rows):
        target = dict(current)
        target.update(positions)
        if row_index == 0 and time_s == 0.0:
            for drive_id in participating:
                initial[drive_id] = target[drive_id]
                current[drive_id] = target[drive_id]
            interval_start = 0.0
            continue
        duration = time_s - interval_start
        if duration <= 0:
            raise ValueError("外部表格时间必须严格递增")
        for drive_id in sorted(participating):
            drive = drives[drive_id]
            start_value = float(current[drive_id])
            end_value = float(target[drive_id])
            source_segment = next(iter(drive.get("segments", [])), None)
            action_id = str((source_segment or {}).get("id", ""))
            segments.append({
                "index": len(segments),
                "drive_id": drive_id,
                "action_id": action_id,
                "start_value": start_value,
                "end_value": end_value,
                "start_time": interval_start,
                "end_time": time_s,
                "duration": duration,
                "speed": abs(end_value - start_value) / duration,
                "mode": "table",
                "profile": "linear",
            })
        current = target
        interval_start = time_s

    duration = max(normalized_rows[-1][0], 0.001)
    return {"duration": duration, "segments": segments, "initial": initial}


def build_memory_jump_timeline(
    model: dict[str, Any],
    memory_id: str,
    initial_positions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a parallel move from the currently displayed end pose to a memory pose.

    Every drive starts at t=0 and uses its engineer-configured ``rated_speed``.
    The timeline ends when the slowest/longest drive reaches its recorded position.
    """
    drives = {item["id"]: item for item in model.get("drives", [])}
    memory = next((item for item in model.get("memories", []) if str(item.get("id", "")) == str(memory_id)), None)
    if memory is None:
        raise ValueError("记忆位置不存在")
    targets = memory.get("positions", {})
    supplied = initial_positions if isinstance(initial_positions, dict) else {}
    initial: dict[str, float] = {}
    segments: list[dict[str, Any]] = []
    duration = 0.001
    for index, drive in enumerate(drives.values()):
        drive_id = str(drive["id"])
        default = float(drive.get("initial_position", drive["reverse_limit"] if drive.get("zero_at") == "reverse" else drive["forward_limit"]))
        start = _clamp(drive, float(supplied.get(drive_id, default)))
        if drive_id not in targets:
            raise ValueError(f"记忆位置缺少驱动“{drive['name']}”的数据")
        end = _clamp(drive, float(targets[drive_id]))
        speed = max(1e-6, float(drive["rated_speed"]))
        drive_duration = max(0.001, abs(end - start) / speed)
        source_segment = next(iter(drive.get("segments", [])), None)
        profile = str((source_segment or {}).get("profile", "s_curve"))
        initial[drive_id] = start
        segments.append({
            "index": index, "drive_id": drive_id, "action_id": "",
            "start_value": start, "end_value": end, "start_time": 0.0, "end_time": drive_duration,
            "duration": drive_duration, "speed": speed, "mode": "speed", "profile": profile,
        })
        duration = max(duration, drive_duration)
    return {"duration": duration, "segments": segments, "initial": initial}

def build_position_jump_timeline(
    model: dict[str, Any],
    target_positions: dict[str, Any],
    initial_positions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the same parallel move used by memory jumps for temporary pose snapshots.

    Temporary undo snapshots live in the browser only; the server receives the
    target positions for the current request and does not persist another model
    memory record.
    """
    if not isinstance(target_positions, dict):
        raise ValueError("暂时记忆位置格式无效")
    drives = {item["id"]: item for item in model.get("drives", [])}
    supplied = initial_positions if isinstance(initial_positions, dict) else {}
    initial: dict[str, float] = {}
    segments: list[dict[str, Any]] = []
    duration = 0.001
    for index, drive in enumerate(drives.values()):
        drive_id = str(drive["id"])
        default = float(drive.get("initial_position", drive["reverse_limit"] if drive.get("zero_at") == "reverse" else drive["forward_limit"]))
        try:
            start = _clamp(drive, float(supplied.get(drive_id, default)))
        except (TypeError, ValueError):
            raise ValueError(f"驱动“{drive['name']}”的当前动画位置无效") from None
        if drive_id not in target_positions:
            raise ValueError(f"暂时记忆位置缺少驱动“{drive['name']}”的数据")
        try:
            end = _clamp(drive, float(target_positions[drive_id]))
        except (TypeError, ValueError):
            raise ValueError(f"暂时记忆位置中的驱动“{drive['name']}”数据无效") from None
        speed = max(1e-6, float(drive["rated_speed"]))
        drive_duration = max(0.001, abs(end - start) / speed)
        source_segment = next(iter(drive.get("segments", [])), None)
        profile = str((source_segment or {}).get("profile", "s_curve"))
        initial[drive_id] = start
        segments.append({
            "index": index, "drive_id": drive_id, "action_id": "",
            "start_value": start, "end_value": end, "start_time": 0.0, "end_time": drive_duration,
            "duration": drive_duration, "speed": speed, "mode": "speed", "profile": profile,
        })
        duration = max(duration, drive_duration)
    return {"duration": duration, "segments": segments, "initial": initial}


def timeline_values_at(timeline: dict[str, Any], time_s: float) -> dict[str, float]:
    values = {str(key): float(value) for key, value in dict(timeline.get("initial", {})).items()}
    now = float(time_s)
    for segment in timeline.get("segments", []):
        start_time = float(segment.get("start_time", 0.0))
        end_time = float(segment.get("end_time", start_time))
        drive_id = str(segment.get("drive_id", ""))
        if now < start_time:
            continue
        if now >= end_time or end_time <= start_time:
            values[drive_id] = float(segment.get("end_value", values.get(drive_id, 0.0)))
            continue
        fraction = (now - start_time) / (end_time - start_time)
        shaped = _shape(str(segment.get("profile", "s_curve")), fraction)
        start_value = float(segment.get("start_value", values.get(drive_id, 0.0)))
        end_value = float(segment.get("end_value", start_value))
        values[drive_id] = start_value + (end_value - start_value) * shaped
    return values
