from __future__ import annotations

import struct
import os
from collections import OrderedDict
from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np

from .models import ProjectSpec


DEFAULT_DENSITY_KG_M3 = 1000.0
MESH_VOLUME_CACHE_MAX = max(16, int(os.getenv("MUJOCO_STUDIO_MESH_VOLUME_CACHE", "256")))
_MESH_VOLUME_CACHE: OrderedDict[tuple[str, int, int], float | None] = OrderedDict()
_MESH_VOLUME_CACHE_LOCK = RLock()


def mesh_volume_m3(path: str | Path) -> float | None:
    """Return the enclosed mesh volume in m³ (CAD input coordinates are mm)."""
    target = Path(path)
    try:
        stat = target.stat()
    except OSError:
        return None
    if not target.is_file():
        return None
    key = (str(target.resolve()), stat.st_mtime_ns, stat.st_size)
    with _MESH_VOLUME_CACHE_LOCK:
        if key in _MESH_VOLUME_CACHE:
            value = _MESH_VOLUME_CACHE.pop(key)
            _MESH_VOLUME_CACHE[key] = value
            return value
    try:
        triangles = _obj_triangles(target) if target.suffix.lower() == ".obj" else _stl_triangles(target)
        if not len(triangles):
            result = None
        else:
            # Signed tetrahedra are translation invariant for a closed, consistently
            # wound surface. MuJoCo likewise expects volumetric meshes for inertia.
            volume_mm3 = abs(float(np.einsum("ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])).sum())) / 6.0
            result = volume_mm3 * 1e-9 if volume_mm3 > 1e-12 else None
    except (OSError, ValueError, IndexError, struct.error):
        result = None
    with _MESH_VOLUME_CACHE_LOCK:
        for stale in [candidate for candidate in _MESH_VOLUME_CACHE if candidate[0] == key[0] and candidate != key]:
            _MESH_VOLUME_CACHE.pop(stale, None)
        _MESH_VOLUME_CACHE[key] = result
        while len(_MESH_VOLUME_CACHE) > MESH_VOLUME_CACHE_MAX:
            _MESH_VOLUME_CACHE.popitem(last=False)
    return result


def resolve_mass_properties(project: ProjectSpec, *, mesh_root: str | Path | None = None) -> dict[str, Any]:
    """Resolve layer/mesh target masses into per-geom density and mass.

    Mesh mass overrides are authoritative. A layer target mass applies to the
    whole layer; after explicit mesh masses are deducted, the remainder is
    distributed by mesh volume (equal shares only when source geometry is not
    available). With no override, MuJoCo's default density remains in force.
    """
    physical_mesh_root = Path(mesh_root) if mesh_root is not None else (Path(project.mesh_root) if project.mesh_root else None)
    mesh_rows: dict[str, dict[str, Any]] = {}
    layers: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for layer in project.layers:
        rows: list[dict[str, Any]] = []
        for mesh in layer.meshes:
            source = physical_mesh_root / mesh.filename if physical_mesh_root is not None else Path(mesh.filename)
            volume = mesh_volume_m3(source)
            row = {
                "mesh_id": mesh.id,
                "layer_id": layer.id,
                "layer_name": layer.name,
                "filename": mesh.filename,
                "volume_m3": volume,
                "target_mass_kg": mesh.mass_kg,
                "resolved_mass_kg": mesh.mass_kg,
                "density_kg_m3": (mesh.mass_kg / volume if mesh.mass_kg is not None and volume else None),
                "source": "mesh" if mesh.mass_kg is not None else "default",
            }
            rows.append(row)

        explicit_total = sum(float(row["target_mass_kg"]) for row in rows if row["target_mass_kg"] is not None)
        unspecified = [row for row in rows if row["target_mass_kg"] is None]
        if layer.mass_kg is not None:
            remainder = float(layer.mass_kg) - explicit_total
            tolerance = max(float(layer.mass_kg), 1.0) * 1e-9
            if remainder < -tolerance:
                errors.append({
                    "code": "layer_mass_below_mesh_mass",
                    "path": f"layers.{layer.id}.mass_kg",
                    "message": f"层级“{layer.name}”质量小于其数模显式质量之和",
                })
            elif unspecified and remainder <= tolerance:
                errors.append({
                    "code": "layer_mass_no_remainder",
                    "path": f"layers.{layer.id}.mass_kg",
                    "message": f"层级“{layer.name}”没有可分配给未设质量数模的剩余质量",
                })
            elif rows and not unspecified and abs(remainder) > tolerance:
                errors.append({
                    "code": "layer_mass_conflict",
                    "path": f"layers.{layer.id}.mass_kg",
                    "message": f"层级“{layer.name}”质量与其全部数模质量之和不一致",
                })
            elif unspecified:
                known_volumes = [row["volume_m3"] for row in unspecified]
                total_volume = sum(float(value) for value in known_volumes if value is not None)
                use_volume = total_volume > 0 and all(value is not None for value in known_volumes)
                for row in unspecified:
                    share = (float(row["volume_m3"]) / total_volume) if use_volume else (1.0 / len(unspecified))
                    resolved = remainder * share
                    row["resolved_mass_kg"] = resolved
                    row["density_kg_m3"] = resolved / float(row["volume_m3"]) if row["volume_m3"] else None
                    row["source"] = "layer_volume" if use_volume else "layer_equal_fallback"

        for row in rows:
            if row["resolved_mass_kg"] is None and row["volume_m3"]:
                row["resolved_mass_kg"] = float(row["volume_m3"]) * DEFAULT_DENSITY_KG_M3
                row["density_kg_m3"] = DEFAULT_DENSITY_KG_M3
            # ``resolved_mass_kg`` is authoritative only when it came from an
            # explicit/default mesh target or from a Layer target allocation.
            # Pure default-density rows intentionally remain density-driven.
            row["mass_application"] = (
                "direct_mass"
                if row["resolved_mass_kg"] is not None and row["source"] != "default"
                else "density"
            )
            mesh_rows[str(row["mesh_id"])] = row
        resolved_layer_mass = (
            sum(float(row["resolved_mass_kg"] or 0.0) for row in rows) if rows else layer.mass_kg
        )
        layers.append({
            "layer_id": layer.id,
            "name": layer.name,
            "target_mass_kg": layer.mass_kg,
            "resolved_mass_kg": resolved_layer_mass or None,
            "mesh_count": len(rows),
        })
    return {"default_density_kg_m3": DEFAULT_DENSITY_KG_M3, "layers": layers, "meshes": mesh_rows, "errors": errors}


def _stl_triangles(path: Path) -> np.ndarray:
    payload = path.read_bytes()
    if len(payload) >= 84:
        count = struct.unpack_from("<I", payload, 80)[0]
        if 84 + count * 50 == len(payload):
            result = np.empty((count, 3, 3), dtype=float)
            for face in range(count):
                offset = 84 + face * 50 + 12
                result[face] = np.asarray(struct.unpack_from("<9f", payload, offset), dtype=float).reshape(3, 3)
            return result
    vertices: list[list[float]] = []
    for line in payload.decode("utf-8", errors="ignore").splitlines():
        parts = line.strip().split()
        if len(parts) >= 4 and parts[0].lower() == "vertex":
            vertices.append([float(value) for value in parts[1:4]])
    usable = len(vertices) - len(vertices) % 3
    return np.asarray(vertices[:usable], dtype=float).reshape(-1, 3, 3)


def _obj_triangles(path: Path) -> np.ndarray:
    vertices: list[list[float]] = []
    triangles: list[list[list[float]]] = []
    for line in path.read_text("utf-8", errors="ignore").splitlines():
        parts = line.strip().split()
        if len(parts) >= 4 and parts[0] == "v":
            vertices.append([float(value) for value in parts[1:4]])
        elif len(parts) >= 4 and parts[0] == "f":
            indices = [_obj_index(token, len(vertices)) for token in parts[1:]]
            for index in range(1, len(indices) - 1):
                triangles.append([vertices[indices[0]], vertices[indices[index]], vertices[indices[index + 1]]])
    return np.asarray(triangles, dtype=float).reshape(-1, 3, 3)


def _obj_index(token: str, count: int) -> int:
    value = int(token.split("/", 1)[0])
    return value - 1 if value > 0 else count + value
