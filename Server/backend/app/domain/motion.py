from __future__ import annotations

import csv
import math
import re
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .expressions import ExpressionError, evaluate, resolve_variables
from .mapping_curve import mapping_value as _minimum_jerk_mapping_value
from .models import DriveSegmentSpec, ProjectSpec


@dataclass(frozen=True)
class ResolvedSegment:
    drive_id: str
    drive_name: str
    joint_id: str
    segment_id: str
    name: str
    start: float
    duration: float
    speed: float
    travel: float
    profile: str
    ease_in: bool
    ease_out: bool
    acceleration_time: float
    ease_in_time: float
    ease_out_time: float
    points: tuple[tuple[float, float], ...]
    mapping_source_joint_id: str = ""

    @property
    def end(self) -> float:
        return self.start + self.duration


class ScheduleResolutionError(ExpressionError):
    """Drive-schedule failure with the safely resolved projection retained.

    Validation/generation still fail closed, but preview callers may use the
    partial values to show fields that are already numerically determined.
    """

    def __init__(
        self,
        message: str,
        *,
        partial_variables: dict[str, float] | None = None,
        partial_schedule: list[ResolvedSegment] | None = None,
    ) -> None:
        super().__init__(message)
        self.partial_variables = dict(partial_variables or {})
        self.partial_schedule = list(partial_schedule or [])


MAX_EXTERNAL_CSV_POINTS = 250_000


@dataclass(frozen=True)
class ExternalMotionCsvData:
    header: str
    source_metric: str
    points: tuple[tuple[float, float], ...]
    duration: float
    travel: float
    max_speed: float


def _decode_csv_bytes(content: bytes) -> str:
    # Excel's Unicode text export uses a BOM. UTF-32 must precede UTF-16
    # because their little-endian BOMs share the first two bytes.
    if content.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return content.decode("utf-32")
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16")
    if b"\x00" in content:
        raise ValueError("无 BOM 的 Unicode CSV 或二进制表格无法识别，请另存为带 BOM 的 Unicode 或 UTF-8 CSV")
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise ValueError("CSV 编码无法识别；请使用 UTF-8、GBK 或 GB18030") from last_error
    return ""


def parse_mapping_csv(content: bytes | str) -> list[list[float]]:
    """Read mapping coordinates unchanged, ignoring leading text/header rows."""
    text = _decode_csv_bytes(content) if isinstance(content, bytes) else str(content or "")
    points: list[list[float]] = []
    for line_number, row in enumerate(_split_external_csv_rows(text), 1):
        if not row or str(row[0]).lstrip().startswith("#"):
            continue
        try:
            if len(row) < 2:
                raise ValueError("需要两列")
            values = [float(str(cell).strip()) for cell in row[:2]]
        except (TypeError, ValueError) as exc:
            if not points:  # Chinese/English names, units and Excel sep= line.
                continue
            raise ValueError(f"映射 CSV 第 {line_number} 行不是两列数值") from exc
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"映射 CSV 第 {line_number} 行含 NaN 或无穷值")
        points.append(values)
        if len(points) > MAX_EXTERNAL_CSV_POINTS:
            raise ValueError(f"CSV 数值点超过上限 {MAX_EXTERNAL_CSV_POINTS}")
    if len(points) < 2 or len({row[0] for row in points}) < 2:
        raise ValueError("至少需要两行有限数值映射，且源坐标不能全部相同")
    return points


def _split_external_csv_rows(text: str) -> list[list[str]]:
    lines = [line for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return []
    sample = "\n".join(lines[:20])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return [row for row in csv.reader(lines, dialect) if any(str(cell).strip() for cell in row)]
    except csv.Error:
        rows: list[list[str]] = []
        for line in lines:
            if "\t" in line:
                row = next(csv.reader([line], delimiter="\t"))
            elif ";" in line:
                row = next(csv.reader([line], delimiter=";"))
            elif "," in line:
                row = next(csv.reader([line], delimiter=","))
            else:
                row = re.split(r"\s+", line.strip())
            if any(str(cell).strip() for cell in row):
                rows.append(row)
        return rows


def normalize_external_motion_points(points: Iterable[Iterable[float]]) -> tuple[tuple[float, float], ...]:
    """Normalize V21.5 external-motion rows to a zero-based, deduplicated time axis."""
    dedup: dict[float, tuple[float, float]] = {}
    for item in points or ():
        try:
            time_s, value = float(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (math.isfinite(time_s) and math.isfinite(value)):
            continue
        dedup[round(time_s, 9)] = (time_s, value)
    rows = [dedup[key] for key in sorted(dedup)]
    if not rows:
        return ()
    t0 = rows[0][0]
    return tuple((max(0.0, float(time_s) - t0), float(value)) for time_s, value in rows)


def external_motion_summary(points: Iterable[Iterable[float]]) -> tuple[float, float, float]:
    rows = list(normalize_external_motion_points(points))
    if not rows:
        return 0.0, 0.0, 0.0
    max_speed = 0.0
    for left, right in zip(rows, rows[1:]):
        dt = right[0] - left[0]
        if dt > 1e-12:
            max_speed = max(max_speed, abs((right[1] - left[1]) / dt))
    return max(rows[-1][0], 0.0), rows[-1][1], max_speed


def parse_external_motion_csv(content: bytes | str) -> ExternalMotionCsvData:
    """Parse the V21.5 external CSV contract and convert velocity/acceleration to position."""
    text = _decode_csv_bytes(content) if isinstance(content, bytes) else str(content or "")
    rows = _split_external_csv_rows(text)
    if not rows:
        raise ValueError("CSV 为空")

    first = rows[0]
    has_header = True
    if len(first) >= 2:
        try:
            float(str(first[0]).strip())
            float(str(first[1]).strip())
            has_header = False
        except (TypeError, ValueError):
            has_header = True
    header = [str(cell).strip() for cell in first] if has_header else ["time_s", "external"]
    data_rows = rows[1:] if has_header else rows
    if len(header) < 2:
        header = [*header, "external"]
    if len(header) > 2 and data_rows and all(len(row) <= 2 for row in data_rows[: min(8, len(data_rows))]):
        value_header = " ".join(str(cell).strip() for cell in header[1:] if str(cell).strip())
    else:
        value_header = str(header[1] or "external").strip()

    header_text = value_header.lower()
    if (
        "加速度" in value_header
        or "acceleration" in header_text
        or "accel" in header_text
        or "/s^2" in header_text
        or "/s²" in header_text
    ):
        source_metric = "加速度"
    elif "速度" in value_header or "speed" in header_text or "/s" in header_text:
        source_metric = "速度"
    else:
        source_metric = "位置"

    entries: list[tuple[float, float]] = []
    for row in data_rows:
        if len(row) < 2:
            continue
        try:
            time_s = float(str(row[0]).strip())
            value = float(str(row[1]).strip())
        except (TypeError, ValueError):
            continue
        if math.isfinite(time_s) and math.isfinite(value):
            entries.append((time_s, value))
            if len(entries) > MAX_EXTERNAL_CSV_POINTS:
                raise ValueError(f"CSV 数值点超过上限 {MAX_EXTERNAL_CSV_POINTS}")
    if not entries:
        raise ValueError("CSV 中没有可读取的数值行；需要至少两列：time_s 和曲线值")

    rows_normalized = list(normalize_external_motion_points(entries))
    times = [item[0] for item in rows_normalized]
    values = [item[1] for item in rows_normalized]
    if source_metric == "速度":
        positions = [0.0]
        for index in range(1, len(times)):
            dt = max(0.0, times[index] - times[index - 1])
            positions.append(positions[-1] + 0.5 * (values[index - 1] + values[index]) * dt)
        values = positions
    elif source_metric == "加速度":
        positions = [0.0]
        velocities = [0.0]
        for index in range(1, len(times)):
            dt = max(0.0, times[index] - times[index - 1])
            next_velocity = velocities[-1] + 0.5 * (values[index - 1] + values[index]) * dt
            positions.append(positions[-1] + 0.5 * (velocities[-1] + next_velocity) * dt)
            velocities.append(next_velocity)
        values = positions

    points = tuple((float(time_s), float(value)) for time_s, value in zip(times, values))
    duration, travel, max_speed = external_motion_summary(points)
    return ExternalMotionCsvData(
        header=value_header,
        source_metric=source_metric,
        points=points,
        duration=duration,
        travel=travel,
        max_speed=max_speed,
    )


def _load_external_motion_csv(path: str) -> ExternalMotionCsvData:
    try:
        return parse_external_motion_csv(Path(path).read_bytes())
    except (OSError, ValueError) as exc:
        raise ExpressionError(f"external motion CSV cannot be read: {path}: {exc}") from exc


def normalize_mapping_points(points: Iterable[Iterable[float]]) -> tuple[tuple[float, float], ...]:
    """Normalize mapping rows to the legacy V21 runtime contract.

    Rows are finite, ordered by source coordinate, duplicate source coordinates
    keep the last imported row (rounded at 1e-9 for stable CSV behavior), and an
    implicit (0, 0) is added only when all imported source points lie on one
    side of zero. Imported ProjectSpec/CSV data itself is not mutated.
    """
    dedup: dict[float, tuple[float, float]] = {}
    for item in points or ():
        try:
            x, y = float(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        dedup[round(x, 9)] = (x, y)
    rows = [dedup[key] for key in sorted(dedup)]
    if rows and (rows[0][0] > 1e-12 or rows[-1][0] < -1e-12):
        rows.append((0.0, 0.0))
        rows.sort(key=lambda item: item[0])
    return tuple(rows)


def _load_csv_points(path: str) -> list[tuple[float, float]]:
    if not path:
        return []
    try:
        # Historical recovery tolerates malformed rows and keeps valid points;
        # new uploads use the stricter parser before changing the project.
        text = _decode_csv_bytes(Path(path).read_bytes())
        points = []
        for row in _split_external_csv_rows(text):
            try:
                x, y = float(row[0]), float(row[1])
                if math.isfinite(x) and math.isfinite(y):
                    points.append((x, y))
            except (ValueError, TypeError, IndexError):
                continue
        return points
    except (OSError, ValueError) as exc:
        raise ExpressionError(f"mapping CSV cannot be read: {path}: {exc}") from exc


def _time_value(value: Any, fallback: Any, variables: dict[str, float]) -> float:
    return max(0.0, evaluate(fallback if value is None else value, variables))


def _resolve_duration_speed(
    segment: DriveSegmentSpec, travel: float, variables: dict[str, float],
) -> tuple[float, float, float, float]:
    rise = _time_value(segment.ease_in_time, segment.acceleration_time, variables) if segment.ease_in else 0.0
    fall = _time_value(segment.ease_out_time, segment.acceleration_time, variables) if segment.ease_out else 0.0
    if segment.mode == "duration":
        duration = evaluate(segment.duration, variables)
        if duration < 0:
            raise ExpressionError(f"segment {segment.name}: duration must not be negative")
        if duration == 0:
            return 0.0, 0.0, 0.0, 0.0
        if segment.easing_mode == "acceleration" and (segment.ease_in or segment.ease_out):
            inverse_acceleration = 0.0
            for enabled, raw in (
                (segment.ease_in, segment.ease_in_acceleration),
                (segment.ease_out, segment.ease_out_acceleration),
            ):
                if not enabled:
                    continue
                acceleration = abs(evaluate(raw, variables))
                if acceleration <= 0:
                    raise ExpressionError(f"segment {segment.name}: easing acceleration must be positive")
                inverse_acceleration += 1.0 / acceleration
            distance = abs(travel)
            discriminant = duration * duration - 2.0 * inverse_acceleration * distance
            if discriminant < -1e-9:
                raise ExpressionError(f"segment {segment.name}: duration is too short for easing acceleration")
            speed = (duration - math.sqrt(max(0.0, discriminant))) / max(inverse_acceleration, 1e-12)
            rise = speed / abs(evaluate(segment.ease_in_acceleration, variables)) if segment.ease_in else 0.0
            fall = speed / abs(evaluate(segment.ease_out_acceleration, variables)) if segment.ease_out else 0.0
            return duration, speed, rise, fall
        ramp_total = min(duration, rise + fall)
        effective = max(duration - 0.5 * ramp_total, 1e-12)
        return duration, abs(travel) / effective, rise, fall
    speed = abs(evaluate(segment.speed, variables))
    if speed <= 0:
        raise ExpressionError(f"segment {segment.name}: speed must be positive")
    if segment.easing_mode == "acceleration":
        if segment.ease_in:
            acceleration = abs(evaluate(segment.ease_in_acceleration, variables))
            if acceleration <= 0:
                raise ExpressionError(f"segment {segment.name}: ease-in acceleration must be positive")
            rise = speed / acceleration
        if segment.ease_out:
            acceleration = abs(evaluate(segment.ease_out_acceleration, variables))
            if acceleration <= 0:
                raise ExpressionError(f"segment {segment.name}: ease-out acceleration must be positive")
            fall = speed / acceleration
    ramp = rise + fall
    duration = abs(travel) / speed + 0.5 * ramp
    return max(duration, 1e-12), speed, rise, fall


def resolve_schedule(project: ProjectSpec, variable_overrides: dict[str, float] | None = None) -> tuple[dict[str, float], list[ResolvedSegment]]:
    variables = resolve_variables(project.variables, variable_overrides)
    compatibility_aliases: set[str] = set()
    resolved: list[ResolvedSegment] = []

    def public_variables() -> dict[str, float]:
        return {key: value for key, value in variables.items() if key not in compatibility_aliases}

    def publish_drive_value(drive_name: str, suffix: str, value: float) -> None:
        canonical = f"{drive_name}/{suffix}"
        variables[canonical] = value
        dot_alias = f"{drive_name}.{suffix}"
        variables[dot_alias] = value
        compatibility_aliases.add(dot_alias)
        base_suffix = suffix.rstrip("0123456789")
        legacy_suffix = {
            "starttime": "startTime",
            "endtime": "endTime",
            "duration": "Duration",
            "speed": "Speed",
            "stroke": "Stroke",
        }.get(base_suffix)
        if legacy_suffix:
            index = suffix[len(base_suffix):]
            legacy_alias = f"{drive_name}/{legacy_suffix}{index}"
            variables[legacy_alias] = value
            compatibility_aliases.add(legacy_alias)

    boundaries: dict[str, tuple[float, float]] = {}
    unresolved = [(drive, segment) for drive in project.drives if drive.enabled for segment in drive.segments]
    resolution_errors: dict[tuple[str, str], str] = {}
    known_drive_variables: set[str] = set()
    for drive in project.drives:
        if not drive.enabled:
            continue
        for index, _segment in enumerate(drive.segments, 1):
            for suffix, legacy_suffix in (
                ("starttime", "startTime"),
                ("endtime", "endTime"),
                ("duration", "Duration"),
                ("speed", "Speed"),
                ("stroke", "Stroke"),
            ):
                known_drive_variables.update({
                    f"{drive.name}/{suffix}{index}",
                    f"{drive.name}.{suffix}{index}",
                    f"{drive.name}/{legacy_suffix}{index}",
                })

    def active_segment_expressions(segment: DriveSegmentSpec) -> tuple[Any, ...]:
        # External CSV points are the authoritative motion function. Its stale
        # duration/travel/speed form fields must not create false dependencies.
        expressions: list[Any] = [segment.start]
        if segment.profile == "external_csv":
            return tuple(expressions)
        expressions.extend([segment.travel, segment.acceleration_time])
        expressions.append(segment.duration if segment.mode == "duration" else segment.speed)
        for enabled, time_expression in (
            (segment.ease_in, segment.ease_in_time),
            (segment.ease_out, segment.ease_out_time),
        ):
            if enabled and time_expression is not None:
                expressions.append(time_expression)
        if segment.easing_mode == "acceleration":
            if segment.ease_in:
                expressions.append(segment.ease_in_acceleration)
            if segment.ease_out:
                expressions.append(segment.ease_out_acceleration)
        return tuple(expressions)

    def unresolved_drive_dependencies(segment: DriveSegmentSpec) -> list[str]:
        expressions = active_segment_expressions(segment)
        missing: list[str] = []
        for name in sorted(known_drive_variables, key=len, reverse=True):
            if name in variables:
                continue
            pattern = rf"(?<![\w/]){re.escape(name)}(?![\w/])"
            if any(raw is not None and re.search(pattern, str(raw)) for raw in expressions):
                missing.append(name)
        return missing

    for _pass in range(len(unresolved) + 2):
        progress = False
        for drive, segment in list(unresolved):
            error_key = (drive.id, segment.id)
            try:
                if segment.profile == "mapping":
                    raw_points = [tuple(item) for item in segment.points] if len(segment.points) >= 2 else (_load_csv_points(segment.csv_path) if segment.csv_path else [])
                    points = normalize_mapping_points(raw_points)
                    item = ResolvedSegment(
                        drive_id=drive.id, drive_name=drive.name, joint_id=drive.joint_id,
                        segment_id=segment.id, name=segment.name,
                        start=project.simulation.start_time,
                        duration=max(project.simulation.end_time - project.simulation.start_time, 1e-12),
                        speed=0.0, travel=points[-1][1] if points else 0.0,
                        profile="mapping", ease_in=False, ease_out=False,
                        acceleration_time=0.0, ease_in_time=0.0, ease_out_time=0.0, points=points,
                        mapping_source_joint_id=segment.mapping_source_joint_id,
                    )
                    resolved.append(item)
                    boundaries[f"{drive.name}/{segment.name}"] = (item.start, item.end)
                    unresolved.remove((drive, segment))
                    resolution_errors.pop(error_key, None)
                    progress = True
                    continue

                index = drive.segments.index(segment) + 1
                if segment.profile == "external_csv":
                    raw_points = segment.points
                    if not raw_points and segment.csv_path:
                        raw_points = [list(item) for item in _load_external_motion_csv(segment.csv_path).points]
                    points = normalize_external_motion_points(raw_points)
                    if not points:
                        raise ExpressionError(f"segment {segment.name}: external CSV has no embedded motion points")
                    duration, travel, speed = external_motion_summary(points)
                    early_values = {
                        f"duration{index}": duration,
                        f"speed{index}": speed,
                        f"stroke{index}": travel,
                    }
                    for suffix, value in early_values.items():
                        publish_drive_value(drive.name, suffix, value)
                    if segment.start_mode == "reference":
                        if segment.reference not in boundaries:
                            reference = segment.reference or "<empty>"
                            resolution_errors[error_key] = f"reference boundary unresolved: {reference}"
                            continue
                        ref_start, ref_end = boundaries[segment.reference]
                        base = ref_start if segment.reference_boundary == "start" else ref_end
                        start = base + evaluate(segment.start, variables)
                    else:
                        start = evaluate(segment.start, variables)
                    item = ResolvedSegment(
                        drive_id=drive.id, drive_name=drive.name, joint_id=drive.joint_id,
                        segment_id=segment.id, name=segment.name, start=start,
                        duration=duration, speed=speed, travel=travel, profile="external_csv",
                        ease_in=False, ease_out=False, acceleration_time=0.0,
                        ease_in_time=0.0, ease_out_time=0.0, points=points,
                        mapping_source_joint_id=segment.mapping_source_joint_id,
                    )
                    resolved.append(item)
                    boundaries[f"{drive.name}/{segment.name}"] = (item.start, item.end)
                    for suffix, value in {
                        f"starttime{index}": item.start, f"endtime{index}": item.end,
                        f"duration{index}": item.duration, f"speed{index}": item.speed,
                        f"stroke{index}": item.travel,
                    }.items():
                        publish_drive_value(drive.name, suffix, value)
                    unresolved.remove((drive, segment))
                    resolution_errors.pop(error_key, None)
                    progress = True
                    continue

                travel = evaluate(segment.travel, variables)
                duration, speed, ease_in_time, ease_out_time = _resolve_duration_speed(segment, travel, variables)
                # Duration, speed and travel do not depend on the segment's
                # start boundary. Publish canonical slash/lowercase names early
                # so expressions can reference e.g. ``drive/duration1``. Legacy
                # dot and slash/CamelCase spellings remain evaluation aliases.
                # Keep these values even if the start boundary is unresolved so
                # preview can expose numerically valid fields without allowing
                # validation/generation to proceed with an incomplete segment.
                early_values = {
                    f"duration{index}": duration,
                    f"speed{index}": speed,
                    f"stroke{index}": travel,
                }
                for suffix, value in early_values.items():
                    publish_drive_value(drive.name, suffix, value)

                if segment.start_mode == "reference":
                    if segment.reference not in boundaries:
                        reference = segment.reference or "<empty>"
                        resolution_errors[error_key] = f"reference boundary unresolved: {reference}"
                        continue
                    ref_start, ref_end = boundaries[segment.reference]
                    base = ref_start if segment.reference_boundary == "start" else ref_end
                    start = base + evaluate(segment.start, variables)
                else:
                    start = evaluate(segment.start, variables)

                points = segment.points
                normalized_points = tuple(sorted((float(x), float(y)) for x, y in points))
                item = ResolvedSegment(
                    drive_id=drive.id,
                    drive_name=drive.name,
                    joint_id=drive.joint_id,
                    segment_id=segment.id,
                    name=segment.name,
                    start=start,
                    duration=duration,
                    speed=speed,
                    travel=travel,
                    profile=segment.profile,
                    ease_in=segment.ease_in,
                    ease_out=segment.ease_out,
                    acceleration_time=max(0.0, evaluate(segment.acceleration_time, variables)),
                    ease_in_time=ease_in_time,
                    ease_out_time=ease_out_time,
                    points=normalized_points,
                    mapping_source_joint_id=segment.mapping_source_joint_id,
                )
                resolved.append(item)
                boundaries[f"{drive.name}/{segment.name}"] = (item.start, item.end)
                values = {
                    f"starttime{index}": item.start, f"endtime{index}": item.end,
                    f"duration{index}": item.duration, f"speed{index}": item.speed,
                    f"stroke{index}": item.travel,
                }
                for suffix, value in values.items():
                    publish_drive_value(drive.name, suffix, value)
                unresolved.remove((drive, segment))
                resolution_errors.pop(error_key, None)
                progress = True
            except ExpressionError as exc:
                resolution_errors[error_key] = str(exc)
                continue
        if not unresolved or not progress:
            break

    ordered = sorted(resolved, key=lambda item: (item.start, item.drive_name, item.name))
    if unresolved:
        detail_rows: list[str] = []
        for drive, segment in unresolved:
            reason = resolution_errors.get((drive.id, segment.id), "dependency did not resolve")
            dependencies = unresolved_drive_dependencies(segment)
            if dependencies:
                reason = f"unresolved drive dependency: {', '.join(dependencies)}"
            detail_rows.append(f"{drive.name}/{segment.name}: {reason}")
        details = "; ".join(detail_rows)
        raise ScheduleResolutionError(
            f"unresolved drive segments: {details}",
            partial_variables=public_variables(),
            partial_schedule=ordered,
        )
    return public_variables(), ordered


def _smoothstep(progress: float) -> float:
    u = min(max(progress, 0.0), 1.0)
    return 10 * u**3 - 15 * u**4 + 6 * u**5


def _integral_s(u: float) -> float:
    return 2.5 * u**4 - 3 * u**5 + u**6


def _s_curve_progress(segment: ResolvedSegment, elapsed: float) -> float:
    duration = segment.duration
    rise = min(segment.ease_in_time if segment.ease_in else 0.0, duration)
    fall = min(segment.ease_out_time if segment.ease_out else 0.0, duration)
    if rise + fall > duration:
        scale = duration / max(rise + fall, 1e-12)
        rise *= scale
        fall *= scale
    constant = duration - rise - fall
    effective = constant + 0.5 * (rise + fall)
    peak = 1.0 / max(effective, 1e-12)
    t = min(max(elapsed, 0.0), duration)
    if rise and t < rise:
        return peak * rise * _integral_s(t / rise)
    accumulated = 0.5 * peak * rise
    if t <= rise + constant:
        return accumulated + peak * (t - rise)
    accumulated += peak * constant
    if fall:
        u = (t - rise - constant) / fall
        return accumulated + peak * fall * (u - _integral_s(u))
    return 1.0


def _point_progress(segment: ResolvedSegment, elapsed: float) -> float:
    if not segment.points:
        return _smoothstep(elapsed / max(segment.duration, 1e-12))
    points = list(segment.points)
    max_x = max(points[-1][0], 1e-12)
    phase = min(max(elapsed / max(segment.duration, 1e-12), 0.0), 1.0)
    normalized = [(x / max_x if max_x > 1 else x, y) for x, y in points]
    if normalized[0][0] > 0:
        normalized.insert(0, (0.0, 0.0))
    if normalized[-1][0] < 1:
        normalized.append((1.0, segment.travel))
    for left, right in zip(normalized, normalized[1:]):
        if left[0] <= phase <= right[0]:
            ratio = (phase - left[0]) / max(right[0] - left[0], 1e-12)
            value = left[1] + ratio * (right[1] - left[1])
            return value / segment.travel if abs(segment.travel) > 1e-12 else 0.0
    return 1.0


def _external_csv_value(segment: ResolvedSegment, elapsed: float) -> float:
    points = list(segment.points)
    if not points:
        return 0.0
    local_time = max(float(elapsed), 0.0)
    if local_time <= points[0][0]:
        return float(points[0][1])
    if local_time >= points[-1][0]:
        return float(points[-1][1])
    for left, right in zip(points, points[1:]):
        if left[0] <= local_time <= right[0]:
            ratio = (local_time - left[0]) / max(right[0] - left[0], 1e-12)
            return float(left[1] + ratio * (right[1] - left[1]))
    return float(points[-1][1])


def segment_value(segment: ResolvedSegment, time_s: float) -> float:
    if segment.profile == "mapping":
        return 0.0
    if segment.profile == "external_csv":
        if time_s < segment.start:
            return 0.0
        return _external_csv_value(segment, time_s - segment.start)
    if segment.duration <= 0:
        return 0.0 if time_s < segment.start else segment.travel
    if time_s <= segment.start:
        return 0.0
    if time_s >= segment.end:
        return segment.travel
    elapsed = time_s - segment.start
    if segment.profile == "smoothstep":
        progress = _smoothstep(elapsed / segment.duration)
    elif segment.profile == "points":
        progress = _point_progress(segment, elapsed)
    else:
        progress = _s_curve_progress(segment, elapsed)
    return segment.travel * min(max(progress, -1e9), 1e9)


def _mapping_source_drive_id(reference: str) -> str:
    value = str(reference or "").strip()
    return value[6:] if value.startswith("drive:") else ""


def _mapping_source_value(
    reference: str, drive_values: dict[str, float], joint_values: dict[str, float],
) -> tuple[bool, float]:
    drive_id = _mapping_source_drive_id(reference)
    if drive_id:
        return drive_id in drive_values, float(drive_values.get(drive_id, 0.0))
    return reference in joint_values, float(joint_values.get(reference, 0.0))


MAPPING_INTERPOLATION_MODE = "minimum_jerk_quintic"


@lru_cache(maxsize=256)
def _mapping_runtime_curve(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[tuple[float, float], ...], str]:
    """Prepare one authoritative mapping curve without density-dependent branches.

    V2.12.2.1 removes the 2049-point split.  Every finite, deduplicated mapping
    knot remains a hard positional constraint and all mappings with at least
    three points use the shared natural-quintic/minimum-jerk interpolator.
    One/two-point mappings retain constant/linear semantics inside the helper.
    """
    normalized = normalize_mapping_points(points)
    return normalized, MAPPING_INTERPOLATION_MODE


def _mapping_runtime_points(points: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    """Compatibility projection: runtime knots are exactly the normalized source table."""
    return _mapping_runtime_curve(points)[0]


def _interpolate_mapping(points: tuple[tuple[float, float], ...], source: float) -> float:
    runtime, _mode = _mapping_runtime_curve(points)
    return _minimum_jerk_mapping_value(runtime, float(source))


def resolved_positions(schedule: Iterable[ResolvedSegment], time_s: float) -> tuple[dict[str, float], dict[str, float]]:
    items = list(schedule)
    drive_values: dict[str, float] = {}
    joint_values: dict[str, float] = {}
    mappings: list[ResolvedSegment] = []
    for segment in items:
        if segment.profile == "mapping":
            mappings.append(segment); continue
        value = segment_value(segment, time_s)
        drive_values[segment.drive_id] = drive_values.get(segment.drive_id, 0.0) + value
        if segment.joint_id:
            joint_values[segment.joint_id] = joint_values.get(segment.joint_id, 0.0) + value
    # Mapping sources may be a physical joint id (legacy/current) or a tagged
    # drive:<id> scalar source.  The latter allows a head/source motor to stay
    # intentionally unbound from MuJoCo geometry while remaining authoritative.
    pending = list(mappings)
    target_joint_ids = {item.joint_id for item in mappings if item.joint_id}
    target_drive_ids = {item.drive_id for item in mappings if item.drive_id}
    for _ in range(len(pending) + 1):
        progress = False
        for segment in list(pending):
            source_ref = segment.mapping_source_joint_id
            source_drive = _mapping_source_drive_id(source_ref)
            if not source_ref:
                continue
            if source_drive:
                if source_drive in target_drive_ids and source_drive not in drive_values:
                    continue
                ready, source_value = _mapping_source_value(source_ref, drive_values, joint_values)
                if not ready and source_drive not in target_drive_ids:
                    source_value = 0.0
            else:
                if source_ref in target_joint_ids and source_ref not in joint_values:
                    continue
                _ready, source_value = _mapping_source_value(source_ref, drive_values, joint_values)
            value = _interpolate_mapping(segment.points, source_value)
            drive_values[segment.drive_id] = drive_values.get(segment.drive_id, 0.0) + value
            if segment.joint_id:
                joint_values[segment.joint_id] = joint_values.get(segment.joint_id, 0.0) + value
            pending.remove(segment); progress = True
        if not progress:
            break
    for segment in pending:
        drive_values.setdefault(segment.drive_id, 0.0)
        if segment.joint_id:
            joint_values.setdefault(segment.joint_id, 0.0)
    return drive_values, joint_values


def drive_positions(schedule: Iterable[ResolvedSegment], time_s: float) -> dict[str, float]:
    return resolved_positions(schedule, time_s)[0]


def joint_positions(schedule: Iterable[ResolvedSegment], time_s: float) -> dict[str, float]:
    return resolved_positions(schedule, time_s)[1]


def _reference_driven_by_mapping(items: Iterable[ResolvedSegment], reference: str) -> bool:
    """Whether the direct mapping source is itself produced by another mapping.

    The clean cumulative-source projection below reads ``mapping.points`` in the
    coordinate of the *direct* source. When that direct source is another
    mapping's output (nested mapping chain), the concrete leaf blocks no longer
    share that coordinate, so those rare cases keep the historical time-sampled
    projection instead.
    """
    reference = str(reference or "").strip()
    if not reference:
        return False
    source_drive = _mapping_source_drive_id(reference)
    for item in items:
        if item.profile != "mapping":
            continue
        if source_drive:
            if item.drive_id == source_drive:
                return True
        elif item.joint_id == reference:
            return True
    return False


def mapping_gantt_blocks(
    mapping: ResolvedSegment, schedule: Iterable[ResolvedSegment],
) -> list[dict[str, Any]]:
    """Project a mapping follower onto every concrete source motor block."""
    items = list(schedule)

    def source_blocks(reference: str, seen: set[str]) -> list[ResolvedSegment]:
        if not reference or reference in seen:
            return []
        next_seen = {*seen, reference}
        source_drive = _mapping_source_drive_id(reference)
        result: list[ResolvedSegment] = []
        for item in items:
            if source_drive:
                if item.drive_id != source_drive:
                    continue
            elif item.joint_id != reference:
                continue
            if item.profile == "mapping":
                result.extend(source_blocks(item.mapping_source_joint_id, next_seen))
            else:
                result.append(item)
        return result

    blocks = source_blocks(mapping.mapping_source_joint_id, {f"drive:{mapping.drive_id}", mapping.joint_id})
    ordered = sorted(blocks, key=lambda item: (item.start, item.end, item.segment_id))
    # V2.6.4 fix — Gantt companion breakpoints must follow the source's own
    # per-block travel, not a time sample of the follower joint.
    #
    # The follower joint value sampled at a source block's start/end *time*
    # (the previous behavior) is the superposition of every source segment
    # active at that instant. When source segments overlap in time, that sample
    # bleeds a neighbouring segment's motion into the boundary, so companion
    # blocks drift off the mapping breakpoints even though the source rows stay
    # correct (e.g. a block whose source spans 107.42→381.88 rendered companion
    # 15→106.5 instead of 15→100.01).
    #
    # The source signal advances through the ordered concrete blocks, so its
    # clean position at each boundary is the running sum of the block travels —
    # exactly the accumulator the source rows themselves display. Mapping those
    # boundary positions through ``mapping.points`` yields the intended
    # breakpoints and is immune to time-overlap superposition. Nested mapping
    # sources cannot use this coordinate, so they retain the time sample.
    nested_source = _reference_driven_by_mapping(items, mapping.mapping_source_joint_id)
    cumulative_source = 0.0
    output: list[dict[str, Any]] = []
    for index, source in enumerate(ordered):
        if nested_source:
            start_value = float(joint_positions(items, source.start).get(mapping.joint_id, 0.0))
            end_value = float(joint_positions(items, source.end).get(mapping.joint_id, start_value))
        else:
            source_start = cumulative_source
            source_end = cumulative_source + float(source.travel)
            cumulative_source = source_end
            start_value = float(_interpolate_mapping(mapping.points, source_start))
            end_value = float(_interpolate_mapping(mapping.points, source_end))
        output.append({
            "id": f"{mapping.segment_id}--source--{source.segment_id}--{index}",
            "drive_id": mapping.drive_id,
            "drive_name": mapping.drive_name,
            "joint_id": mapping.joint_id,
            "name": f"{mapping.name} ← {source.drive_name}/{source.name}",
            "start": float(source.start),
            "end": float(source.end),
            "duration": float(source.duration),
            "travel": end_value - start_value,
            "travel_start": start_value,
            "travel_end": end_value,
            "source_drive_id": source.drive_id,
            "source_drive_name": source.drive_name,
            "source_segment_id": source.segment_id,
            "source_segment_name": source.name,
            "mapping_segment_id": mapping.segment_id,
            "mapping_source_joint_id": mapping.mapping_source_joint_id,
            "profile": "mapping",
        })
    return output


def latest_drive_stop_time(schedule: Iterable[ResolvedSegment], fallback: float) -> float:
    """Return the latest concrete drive stop, excluding mapping carrier duration.

    Mapping segments use the simulation window as an evaluation carrier. Their
    synthetic ``end`` is therefore not a physical drive stop. Reuse the Gantt
    projection to resolve each mapping follower back to its concrete source
    blocks and take those real block ends instead.
    """
    items = list(schedule)
    stops: list[float] = []
    for item in items:
        if item.profile == "mapping":
            for block in mapping_gantt_blocks(item, items):
                try:
                    end = float(block.get("end"))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(end):
                    stops.append(end)
            continue
        try:
            end = float(item.end)
        except (TypeError, ValueError):
            continue
        if getattr(item, "drive_id", "") and math.isfinite(end):
            stops.append(end)
    return max(stops, default=float(fallback))


def collect_boundaries(schedule: Iterable[ResolvedSegment]) -> list[float]:
    return sorted({value for segment in schedule for value in (segment.start, segment.end) if math.isfinite(value)})
