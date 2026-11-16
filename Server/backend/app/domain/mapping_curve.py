"""Shared minimum-jerk interpolation for drive mapping curves.

This module is intentionally dependency-free.  It is used by the Server motion
scheduler and is also shipped beside the standalone Viewer controller, so both
surfaces evaluate one mathematical mapping contract.

For three or more knots we construct the piecewise quintic Hermite interpolant
whose free knot velocities/accelerations minimise the integral of squared jerk
while every imported mapping knot remains a hard position constraint.  The
result is the natural quintic/minimum-jerk interpolant: position is exact at
all knots and the optimality conditions make the interior curve C4 in exact
arithmetic.  One/two-point mappings retain constant/linear semantics.
"""
from __future__ import annotations

from functools import lru_cache
import math
from typing import Iterable

_EPS = 1e-12

Matrix2 = tuple[tuple[float, float], tuple[float, float]]
Vector2 = tuple[float, float]
Quintic = tuple[float, float, float, float, float, float]
Point = tuple[float, float]


def _mat_add(a: Matrix2, b: Matrix2) -> Matrix2:
    return (
        (a[0][0] + b[0][0], a[0][1] + b[0][1]),
        (a[1][0] + b[1][0], a[1][1] + b[1][1]),
    )


def _mat_sub(a: Matrix2, b: Matrix2) -> Matrix2:
    return (
        (a[0][0] - b[0][0], a[0][1] - b[0][1]),
        (a[1][0] - b[1][0], a[1][1] - b[1][1]),
    )


def _mat_mul(a: Matrix2, b: Matrix2) -> Matrix2:
    return (
        (
            a[0][0] * b[0][0] + a[0][1] * b[1][0],
            a[0][0] * b[0][1] + a[0][1] * b[1][1],
        ),
        (
            a[1][0] * b[0][0] + a[1][1] * b[1][0],
            a[1][0] * b[0][1] + a[1][1] * b[1][1],
        ),
    )


def _mat_vec(a: Matrix2, value: Vector2) -> Vector2:
    return (
        a[0][0] * value[0] + a[0][1] * value[1],
        a[1][0] * value[0] + a[1][1] * value[1],
    )


def _vec_sub(a: Vector2, b: Vector2) -> Vector2:
    return (a[0] - b[0], a[1] - b[1])


def _transpose(a: Matrix2) -> Matrix2:
    return ((a[0][0], a[1][0]), (a[0][1], a[1][1]))


def _inverse_2x2(a: Matrix2) -> Matrix2:
    """Invert a positive-definite 2x2 block with a tiny numerical guard."""
    a00, a01 = a[0]
    a10, a11 = a[1]
    determinant = a00 * a11 - a01 * a10
    scale = max(abs(a00 * a11), abs(a01 * a10), 1.0)
    if abs(determinant) <= 1e-15 * scale:
        # Pathological spacing can make a block numerically singular even
        # though the complete minimum-jerk system is well-defined.  A relative
        # diagonal guard is preferable to switching to a dense O(n^3) solve.
        regularizer = max(abs(a00), abs(a11), 1.0) * 1e-12
        a00 += regularizer
        a11 += regularizer
        determinant = a00 * a11 - a01 * a10
    if not math.isfinite(determinant) or abs(determinant) <= 1e-300:
        raise ValueError("mapping minimum-jerk system is numerically singular")
    inverse = 1.0 / determinant
    return ((a11 * inverse, -a01 * inverse), (-a10 * inverse, a00 * inverse))


def _segment_system(step: float, delta: float) -> tuple[Matrix2, Matrix2, Matrix2, Vector2, Vector2]:
    """Return one segment's Hessian blocks and negative-gradient RHS.

    Unknowns at each knot are (dy/dt, d2y/dt2), where t is the complete
    mapping source range normalised to [0, 1].  These coefficients are the
    analytic Hessian of integral (d3y/dt3)^2 dt for a quintic Hermite segment.
    """
    h = max(float(step), 1e-15)
    h2 = h * h
    h3 = h2 * h
    h4 = h3 * h
    h00: Matrix2 = ((384.0 / h3, 72.0 / h2), (72.0 / h2, 18.0 / h))
    h01: Matrix2 = ((336.0 / h3, -48.0 / h2), (48.0 / h2, -6.0 / h))
    h11: Matrix2 = ((384.0 / h3, -72.0 / h2), (-72.0 / h2, 18.0 / h))
    # Solve H*x = -g.  These are already -g for the two segment endpoints.
    rhs0: Vector2 = (720.0 * delta / h4, 120.0 * delta / h3)
    rhs1: Vector2 = (720.0 * delta / h4, -120.0 * delta / h3)
    return h00, h01, h11, rhs0, rhs1


def _block_tridiagonal_solve(
    diagonal: list[Matrix2], upper: list[Matrix2], rhs: list[Vector2],
) -> tuple[Vector2, ...]:
    """O(n) block Thomas solve for the symmetric 2x2 minimum-jerk system."""
    count = len(diagonal)
    if count == 0:
        return ()
    if count == 1:
        return (_mat_vec(_inverse_2x2(diagonal[0]), rhs[0]),)

    c_prime: list[Matrix2] = [((0.0, 0.0), (0.0, 0.0)) for _ in range(count - 1)]
    d_prime: list[Vector2] = [(0.0, 0.0) for _ in range(count)]

    inverse = _inverse_2x2(diagonal[0])
    c_prime[0] = _mat_mul(inverse, upper[0])
    d_prime[0] = _mat_vec(inverse, rhs[0])

    for index in range(1, count):
        lower = _transpose(upper[index - 1])
        effective = _mat_sub(diagonal[index], _mat_mul(lower, c_prime[index - 1]))
        effective_rhs = _vec_sub(rhs[index], _mat_vec(lower, d_prime[index - 1]))
        inverse = _inverse_2x2(effective)
        if index < count - 1:
            c_prime[index] = _mat_mul(inverse, upper[index])
        d_prime[index] = _mat_vec(inverse, effective_rhs)

    solution: list[Vector2] = [(0.0, 0.0) for _ in range(count)]
    solution[-1] = d_prime[-1]
    for index in range(count - 2, -1, -1):
        solution[index] = _vec_sub(d_prime[index], _mat_vec(c_prime[index], solution[index + 1]))
    return tuple(solution)


def _segment_coefficients(y0: float, y1: float, step: float, left: Vector2, right: Vector2) -> Quintic:
    """Quintic coefficients in local u=(x-x0)/(x1-x0), u in [0,1]."""
    velocity0, acceleration0 = left
    velocity1, acceleration1 = right
    h = float(step)
    delta = float(y1 - y0)
    d0 = h * velocity0
    d1 = h * velocity1
    dd0 = h * h * acceleration0
    dd1 = h * h * acceleration1
    return (
        float(y0),
        d0,
        0.5 * dd0,
        10.0 * delta - 6.0 * d0 - 4.0 * d1 - 1.5 * dd0 + 0.5 * dd1,
        -15.0 * delta + 8.0 * d0 + 7.0 * d1 + 1.5 * dd0 - dd1,
        6.0 * delta - 3.0 * d0 - 3.0 * d1 - 0.5 * dd0 + 0.5 * dd1,
    )


def _linear_coefficients(y0: float, y1: float) -> Quintic:
    return (float(y0), float(y1 - y0), 0.0, 0.0, 0.0, 0.0)


@lru_cache(maxsize=128)
def compile_minimum_jerk(points: tuple[Point, ...]) -> tuple[Quintic, ...]:
    """Compile exact mapping knots into minimum-jerk quintic segments.

    The source coordinate is globally normalised before solving.  Affine source
    normalisation changes the objective by only one positive constant, so it
    does not change the minimiser while keeping large degree/mm ranges stable.
    """
    count = len(points)
    if count < 2:
        return ()
    if count == 2:
        return (_linear_coefficients(points[0][1], points[1][1]),)

    start = float(points[0][0])
    span = float(points[-1][0] - start)
    if not math.isfinite(span) or span <= _EPS:
        return ()
    parameters = tuple((float(x) - start) / span for x, _ in points)

    zero: Matrix2 = ((0.0, 0.0), (0.0, 0.0))
    diagonal: list[Matrix2] = [zero for _ in range(count)]
    upper: list[Matrix2] = [zero for _ in range(count - 1)]
    rhs: list[Vector2] = [(0.0, 0.0) for _ in range(count)]

    for index in range(count - 1):
        step = parameters[index + 1] - parameters[index]
        if step <= 1e-15:
            raise ValueError("mapping source coordinates must be strictly increasing")
        delta = float(points[index + 1][1] - points[index][1])
        h00, h01, h11, rhs0, rhs1 = _segment_system(step, delta)
        diagonal[index] = _mat_add(diagonal[index], h00)
        upper[index] = _mat_add(upper[index], h01)
        diagonal[index + 1] = _mat_add(diagonal[index + 1], h11)
        rhs[index] = (rhs[index][0] + rhs0[0], rhs[index][1] + rhs0[1])
        rhs[index + 1] = (rhs[index + 1][0] + rhs1[0], rhs[index + 1][1] + rhs1[1])

    derivatives = _block_tridiagonal_solve(diagonal, upper, rhs)
    return tuple(
        _segment_coefficients(
            points[index][1], points[index + 1][1],
            parameters[index + 1] - parameters[index],
            derivatives[index], derivatives[index + 1],
        )
        for index in range(count - 1)
    )


def _segment_index(points: tuple[Point, ...], source: float) -> int:
    lo, hi = 0, len(points) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if points[mid][0] <= source:
            lo = mid
        else:
            hi = mid
    return min(max(lo, 0), len(points) - 2)


def _eval_polynomial(coefficients: Quintic, u: float, derivative: int = 0) -> float:
    c0, c1, c2, c3, c4, c5 = coefficients
    if derivative <= 0:
        return (((((c5 * u + c4) * u + c3) * u + c2) * u + c1) * u + c0)
    if derivative == 1:
        return ((((5.0 * c5 * u + 4.0 * c4) * u + 3.0 * c3) * u + 2.0 * c2) * u + c1)
    if derivative == 2:
        return (((20.0 * c5 * u + 12.0 * c4) * u + 6.0 * c3) * u + 2.0 * c2)
    if derivative == 3:
        return ((60.0 * c5 * u + 24.0 * c4) * u + 6.0 * c3)
    if derivative == 4:
        return 120.0 * c5 * u + 24.0 * c4
    return 120.0 * c5


def mapping_value(points: tuple[Point, ...], source: float) -> float:
    """Evaluate the exact minimum-jerk mapping, clamped outside its source range."""
    if not points:
        return 0.0
    if len(points) == 1 or source <= points[0][0]:
        return float(points[0][1])
    if source >= points[-1][0]:
        return float(points[-1][1])
    index = _segment_index(points, float(source))
    x0 = float(points[index][0])
    width = max(float(points[index + 1][0] - x0), _EPS)
    u = min(max((float(source) - x0) / width, 0.0), 1.0)
    coefficients = compile_minimum_jerk(points)
    if not coefficients:
        return float(points[index][1])
    return float(_eval_polynomial(coefficients[index], u))


def mapping_derivatives(points: tuple[Point, ...], source: float) -> tuple[float, float, float, float]:
    """Return position and first three derivatives with respect to source x."""
    if not points:
        return 0.0, 0.0, 0.0, 0.0
    if len(points) == 1:
        return float(points[0][1]), 0.0, 0.0, 0.0
    clamped = min(max(float(source), float(points[0][0])), float(points[-1][0]))
    index = _segment_index(points, clamped)
    width = max(float(points[index + 1][0] - points[index][0]), _EPS)
    u = min(max((clamped - points[index][0]) / width, 0.0), 1.0)
    coefficients = compile_minimum_jerk(points)
    if not coefficients:
        return float(points[index][1]), 0.0, 0.0, 0.0
    curve = coefficients[index]
    return (
        float(_eval_polynomial(curve, u, 0)),
        float(_eval_polynomial(curve, u, 1) / width),
        float(_eval_polynomial(curve, u, 2) / (width * width)),
        float(_eval_polynomial(curve, u, 3) / (width * width * width)),
    )


def inverse_mapping_value(
    points: tuple[Point, ...], target: float, preferred_source: float = 0.0,
) -> float:
    """Invert the smooth mapping near ``preferred_source``.

    Endpoint-straddling segments are solved against the same quintic used by
    forward evaluation.  If no such segment exists (for example a target just
    outside a non-monotone local excursion), the nearest imported knot is used,
    preserving deterministic manual-control behaviour without inventing a
    second inverse curve.
    """
    if not points:
        return float(preferred_source)
    if len(points) == 1:
        return float(points[0][0])
    target_value = float(target)
    preferred = float(preferred_source)

    exact = [
        (abs(float(source) - preferred), float(source))
        for source, value in points
        if abs(float(value) - target_value) <= 1e-9
    ]
    if exact:
        return min(exact)[1]

    coefficients = compile_minimum_jerk(points)
    candidates: list[tuple[float, float]] = []
    for index, ((x0, y0), (x1, y1)) in enumerate(zip(points, points[1:])):
        f0 = float(y0) - target_value
        f1 = float(y1) - target_value
        if f0 == 0.0:
            candidates.append((abs(float(x0) - preferred), float(x0)))
            continue
        if f1 == 0.0:
            candidates.append((abs(float(x1) - preferred), float(x1)))
            continue
        if f0 * f1 > 0.0:
            continue
        left_u, right_u = 0.0, 1.0
        left_f, right_f = f0, f1
        curve = coefficients[index] if coefficients else _linear_coefficients(y0, y1)
        for _ in range(42):
            mid_u = 0.5 * (left_u + right_u)
            mid_f = _eval_polynomial(curve, mid_u) - target_value
            if abs(mid_f) <= 1e-11:
                left_u = right_u = mid_u
                break
            if left_f * mid_f <= 0.0:
                right_u, right_f = mid_u, mid_f
            else:
                left_u, left_f = mid_u, mid_f
        u = 0.5 * (left_u + right_u)
        source = float(x0) + u * float(x1 - x0)
        candidates.append((abs(source - preferred), source))

    if candidates:
        return min(candidates)[1]

    # Deterministic fallback for targets outside the mapped target range.
    nearest = min(
        ((abs(float(value) - target_value), abs(float(source) - preferred), float(source)) for source, value in points),
        default=(0.0, 0.0, preferred),
    )
    return nearest[2]


def integrated_squared_jerk(points: tuple[Point, ...], samples_per_segment: int = 8) -> float:
    """Diagnostic only: numerically integrate jerk^2 with respect to source."""
    if len(points) < 2:
        return 0.0
    total = 0.0
    samples = max(2, int(samples_per_segment))
    coefficients = compile_minimum_jerk(points)
    for index, (left, right) in enumerate(zip(points, points[1:])):
        width = max(float(right[0] - left[0]), _EPS)
        curve = coefficients[index]
        previous_u = 0.0
        previous = _eval_polynomial(curve, 0.0, 3) / (width ** 3)
        for sample in range(1, samples + 1):
            u = sample / samples
            current = _eval_polynomial(curve, u, 3) / (width ** 3)
            du = u - previous_u
            total += 0.5 * (previous * previous + current * current) * du * width
            previous_u, previous = u, current
    return float(total)
