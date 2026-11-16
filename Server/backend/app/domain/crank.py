"""Legacy-compatible crank-slider geometry shared by generation and simulation."""
from __future__ import annotations

import math
import re
from typing import Any


def _vector(text: str) -> tuple[float, float, float]:
    value = re.sub(r"^\s*point\s*", "", str(text), flags=re.IGNORECASE)
    values = [part for part in re.split(r"[\s,()]+", value) if part]
    if len(values) != 3:
        raise ValueError(f"应输入 3 个坐标值：{text}")
    return tuple(float(value) for value in values)  # type: ignore[return-value]


def _sub(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, float, float]:
    return tuple(a[index] - b[index] for index in range(3))  # type: ignore[return-value]


def _dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sum(a[index] * b[index] for index in range(3))


def _length(value: tuple[float, ...]) -> float:
    return math.sqrt(_dot(value, value))


def _normal(value: tuple[float, ...]) -> tuple[float, float, float]:
    length = _length(value)
    if length <= 1e-12:
        raise ValueError("运动副矢量长度必须大于 0")
    return tuple(item / length for item in value)  # type: ignore[return-value]


def _cross(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def crank_meta(joint: Any) -> dict[str, Any]:
    """Reproduce the old application's three-point crank-slider branch logic."""
    center = _vector(joint.crank_center)
    crank_end = _vector(joint.crank_end)
    rod_end = _vector(joint.rod_end)
    axis_raw = _vector(joint.slide_axis or "1, 0, 0")
    if joint.reverse:
        axis_raw = tuple(-value for value in axis_raw)
    u = _normal(axis_raw)
    crank_vector = _sub(crank_end, center)
    crank_length = _length(crank_vector)
    if crank_length <= 1e-12:
        raise ValueError("曲柄末端坐标不能与曲柄旋转中心重合")
    projected = _dot(crank_vector, u)
    perpendicular = tuple(crank_vector[index] - projected * u[index] for index in range(3))
    if _length(perpendicular) <= 1e-12:
        raise ValueError("曲柄向量不能与运动副矢量平行")
    v = _normal(perpendicular)
    plane_normal = _normal(_cross(u, v))
    center_to_rod = _sub(rod_end, center)
    slider_coord0 = _dot(center_to_rod, u)
    offset_vector = tuple(center_to_rod[index] - slider_coord0 * u[index] for index in range(3))
    slider_offset = _dot(offset_vector, v)
    residual = tuple(offset_vector[index] - slider_offset * v[index] for index in range(3))
    if _length(residual) > 1e-6:
        raise ValueError("三点与运动副矢量必须位于同一运动平面内")
    rod_length = _length(_sub(rod_end, crank_end))
    if rod_length <= 1e-12:
        raise ValueError("连杆长度必须大于 0")
    x0, y0 = _dot(crank_vector, u), _dot(crank_vector, v)
    initial_angle = math.atan2(y0, x0)
    inside = rod_length**2 - (slider_offset - y0) ** 2
    if inside < -1e-6:
        raise ValueError("当前输入几何无法形成有效的曲柄滑块机构")
    root = math.sqrt(max(inside, 0.0))
    branch_sign = 1.0 if abs(x0 + root - slider_coord0) <= abs(x0 - root - slider_coord0) else -1.0
    return {
        "center": list(center), "crank_end": list(crank_end), "rod_end": list(rod_end),
        "slide_axis": list(u), "plane_normal": list(plane_normal), "plane_perp": list(v),
        "crank_length": crank_length, "rod_length": rod_length,
        "slider_coord0": slider_coord0, "slider_offset": slider_offset,
        "initial_angle_rad": initial_angle, "branch_sign": branch_sign,
    }


def crank_displacement(meta: dict[str, Any], angle_degrees: float) -> float:
    """Return slider displacement in the same length unit as the input points (mm)."""
    phi = float(meta["initial_angle_rad"]) + math.radians(float(angle_degrees))
    radius, rod = float(meta["crank_length"]), float(meta["rod_length"])
    offset, origin = float(meta["slider_offset"]), float(meta["slider_coord0"])
    sign = 1.0 if float(meta.get("branch_sign", 1.0)) >= 0 else -1.0
    x, y = radius * math.cos(phi), radius * math.sin(phi)
    inside = rod**2 - (offset - y) ** 2
    if inside < -1e-6:
        raise ValueError("当前角位移超出曲柄滑块机构可达范围")
    return x + sign * math.sqrt(max(inside, 0.0)) - origin
