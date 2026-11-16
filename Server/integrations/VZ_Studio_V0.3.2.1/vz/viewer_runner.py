from __future__ import annotations

from typing import Any

import numpy as np


def _nearest_points(points_a: Any, points_b: Any) -> tuple[float, np.ndarray | None]:
    """Exact sampled-point nearest pair used by the vendored HTML exporter."""
    a = np.asarray(points_a, dtype=float).reshape(-1, 3)
    b = np.asarray(points_b, dtype=float).reshape(-1, 3)
    if not len(a) or not len(b):
        return float("inf"), None
    origin = b[0]
    centered_b = b - origin
    b_squared = np.einsum("ij,ij->i", centered_b, centered_b)
    matrix_elements = max(1, (8 * 1024 * 1024) // np.dtype(float).itemsize)
    chunk_rows = max(1, min(1024, matrix_elements // max(len(b), 1)))
    best_squared = float("inf")
    best_a_index = best_b_index = 0
    eps = np.finfo(float).eps
    for start in range(0, len(a), chunk_rows):
        chunk = a[start:start + chunk_rows]
        centered_a = chunk - origin
        a_squared = np.einsum("ij,ij->i", centered_a, centered_a)
        squared = centered_a @ centered_b.T
        squared *= -2.0
        squared += a_squared[:, None]
        squared += b_squared[None, :]
        np.maximum(squared, 0.0, out=squared)
        local = int(np.argmin(squared))
        local_a, local_b = np.unravel_index(local, squared.shape)
        value = float(squared[local_a, local_b])
        if value + eps < best_squared:
            best_squared = value
            best_a_index = start + int(local_a)
            best_b_index = int(local_b)
    return float(np.sqrt(best_squared)), np.concatenate([a[best_a_index], b[best_b_index]])
