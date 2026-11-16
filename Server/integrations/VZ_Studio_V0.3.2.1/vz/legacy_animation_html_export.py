#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V21.4.4.3.3 standalone MuJoCo animation HTML exporter.

The exporter deliberately keeps MuJoCo on the desktop side.  It samples the
already configured scene, embeds the visual meshes, rigid transforms and
measurement-pair nearest points, then writes a single offline HTML file with a
small WebGL2 player.  No Blender, GLB conversion or hand-authored keyframes are
required from the user.

Vendored for MuJoCo Studio 2.3.9.4 with narrow host adapters for project-local
Gantt snapshots, cooperative Job cancellation and a scipy-free nearest-point
fallback. The offline player HTML/CSS/WebGL behavior remains unchanged.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import threading
from collections import OrderedDict
import html
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .viewer_runner import _nearest_points


V21_EXPORT_VERSION = "21.4.4.3.3"
DEFAULT_EXPORT_FPS = 30
DEFAULT_MAX_FACES_PER_MESH = 120_000
MAX_EXPORT_FRAMES = 6_000

# User-side animation previews are regenerated frequently while the source mesh
# usually stays unchanged. Cache only the compact, smooth-normal preview mesh
# payloads; formal fast/high/perfect exports keep their exact quality pipeline.
_PREVIEW_MESH_CACHE_MAX_BYTES = 64 * 1024 * 1024
_PREVIEW_MESH_CACHE: OrderedDict[str, tuple[dict[str, Any], int]] = OrderedDict()
_PREVIEW_MESH_CACHE_BYTES = 0
_PREVIEW_MESH_CACHE_LOCK = threading.Lock()


class AnimationHtmlExportError(RuntimeError):
    pass


def _report(callback: Callable[[str, float], None] | None, message: str, fraction: float) -> None:
    if callback is None:
        return
    try:
        callback(str(message), max(0.0, min(1.0, float(fraction))))
    except Exception:
        pass


def _b64_f32(values: Any) -> str:
    import numpy as np

    arr = np.asarray(values, dtype="<f4").reshape(-1)
    return base64.b64encode(arr.tobytes(order="C")).decode("ascii")


def _b64_u32(values: Any) -> str:
    import numpy as np

    arr = np.asarray(values, dtype="<u4").reshape(-1)
    return base64.b64encode(arr.tobytes(order="C")).decode("ascii")


def _preview_mesh_cache_key(vertices: Any, faces: Any) -> str:
    """Stable key for a preview mesh after any face-limit simplification."""
    import numpy as np

    v = np.ascontiguousarray(vertices, dtype="<f4")
    f = np.ascontiguousarray(faces, dtype="<u4")
    digest = hashlib.blake2b(digest_size=16)
    digest.update(str(v.shape).encode("ascii"))
    digest.update(v.tobytes(order="C"))
    digest.update(str(f.shape).encode("ascii"))
    digest.update(f.tobytes(order="C"))
    return digest.hexdigest()


def _preview_mesh_cache_get(key: str) -> dict[str, Any] | None:
    with _PREVIEW_MESH_CACHE_LOCK:
        item = _PREVIEW_MESH_CACHE.pop(key, None)
        if item is None:
            return None
        _PREVIEW_MESH_CACHE[key] = item
        return dict(item[0])


def _preview_mesh_cache_put(key: str, record: dict[str, Any]) -> None:
    global _PREVIEW_MESH_CACHE_BYTES
    size = 512 + len(str(record.get("positions", ""))) + len(str(record.get("normals", ""))) + len(str(record.get("indices", "")))
    if size > _PREVIEW_MESH_CACHE_MAX_BYTES:
        return
    with _PREVIEW_MESH_CACHE_LOCK:
        previous = _PREVIEW_MESH_CACHE.pop(key, None)
        if previous is not None:
            _PREVIEW_MESH_CACHE_BYTES -= previous[1]
        while _PREVIEW_MESH_CACHE and _PREVIEW_MESH_CACHE_BYTES + size > _PREVIEW_MESH_CACHE_MAX_BYTES:
            _old_key, (_old_record, old_size) = _PREVIEW_MESH_CACHE.popitem(last=False)
            _PREVIEW_MESH_CACHE_BYTES -= old_size
        _PREVIEW_MESH_CACHE[key] = (dict(record), size)
        _PREVIEW_MESH_CACHE_BYTES += size


def _clear_preview_mesh_cache() -> None:
    global _PREVIEW_MESH_CACHE_BYTES
    with _PREVIEW_MESH_CACHE_LOCK:
        _PREVIEW_MESH_CACHE.clear()
        _PREVIEW_MESH_CACHE_BYTES = 0


def _matrix_to_quaternion_xyzw(matrix: Any) -> list[float]:
    """Convert a 3x3 rotation matrix to a normalized [x, y, z, w] quaternion."""
    import numpy as np

    m = np.asarray(matrix, dtype=float).reshape(3, 3)
    trace = float(m[0, 0] + m[1, 1] + m[2, 2])
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(max(1.0 + m[0, 0] - m[1, 1] - m[2, 2], 1e-16)) * 2.0
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(max(1.0 + m[1, 1] - m[0, 0] - m[2, 2], 1e-16)) * 2.0
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(max(1.0 + m[2, 2] - m[0, 0] - m[1, 1], 1e-16)) * 2.0
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    q = np.asarray([x, y, z, w], dtype=float)
    n = float(np.linalg.norm(q))
    if not math.isfinite(n) or n <= 1e-12:
        return [0.0, 0.0, 0.0, 1.0]
    q /= n
    return [float(v) for v in q]


def _compute_vertex_normals(vertices: Any, faces: Any) -> Any:
    import numpy as np

    verts = np.asarray(vertices, dtype=float).reshape(-1, 3)
    tri = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    normals = np.zeros_like(verts, dtype=float)
    if len(verts) == 0 or len(tri) == 0:
        return normals
    valid = np.all((tri >= 0) & (tri < len(verts)), axis=1)
    tri = tri[valid]
    if len(tri) == 0:
        return normals
    v0 = verts[tri[:, 0]]
    v1 = verts[tri[:, 1]]
    v2 = verts[tri[:, 2]]
    face_normals = np.cross(v1 - v0, v2 - v0)
    for column in range(3):
        np.add.at(normals, tri[:, column], face_normals)
    lengths = np.linalg.norm(normals, axis=1)
    good = lengths > 1e-12
    normals[good] /= lengths[good, None]
    normals[~good] = (0.0, 0.0, 1.0)
    return normals


def _compute_creased_mesh(vertices: Any, faces: Any, crease_angle_deg: float = 35.0, *, flat: bool = False) -> tuple[Any, Any, Any]:
    """Expand triangle corners so hard edges can carry independent normals.

    This mirrors three.js BufferGeometryUtils.toCreasedNormals semantics: faces
    sharing a spatial vertex are averaged only when their normal angle is within
    the configured crease threshold. Area-weighting keeps large CAD faces stable.
    """
    import numpy as np

    verts = np.asarray(vertices, dtype=float).reshape(-1, 3)
    tri = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    valid = np.all((tri >= 0) & (tri < len(verts)), axis=1)
    tri = tri[valid]
    tri = tri[(tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 2] != tri[:, 0])]
    if len(tri) == 0:
        return verts[:0], np.empty((0, 3), dtype=float), np.empty((0, 3), dtype=np.uint32)
    corners = verts[tri]
    raw = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    lengths = np.linalg.norm(raw, axis=1)
    face_normals = np.zeros_like(raw)
    good = lengths > 1e-14
    face_normals[good] = raw[good] / lengths[good, None]
    face_normals[~good] = (0.0, 0.0, 1.0)
    expanded_vertices = corners.reshape(-1, 3)
    if flat:
        expanded_normals = np.repeat(face_normals, 3, axis=0)
    else:
        extent = float(np.max(np.ptp(verts, axis=0))) if len(verts) else 1.0
        tolerance = max(extent * 1e-7, 1e-10)
        quantized = np.round(expanded_vertices / tolerance).astype(np.int64)
        buckets: dict[tuple[int, int, int], list[int]] = {}
        for corner_index, key_values in enumerate(quantized):
            buckets.setdefault(tuple(int(v) for v in key_values), []).append(corner_index // 3)
        crease_dot = math.cos(math.radians(max(0.0, min(180.0, float(crease_angle_deg)))))
        expanded_normals = np.empty_like(expanded_vertices)
        for corner_index, key_values in enumerate(quantized):
            face_index = corner_index // 3
            base = face_normals[face_index]
            candidates = buckets[tuple(int(v) for v in key_values)]
            total = np.zeros(3, dtype=float)
            for other_index in candidates:
                other = face_normals[other_index]
                if float(np.dot(base, other)) >= crease_dot - 1e-12:
                    weight = max(float(lengths[other_index]), 1e-14)
                    total += other * weight
            norm = float(np.linalg.norm(total))
            expanded_normals[corner_index] = total / norm if norm > 1e-14 else base
    expanded_faces = np.arange(len(expanded_vertices), dtype=np.uint32).reshape(-1, 3)
    return expanded_vertices, expanded_normals, expanded_faces


def _compact_mesh(vertices: Any, faces: Any) -> tuple[Any, Any]:
    import numpy as np

    verts = np.asarray(vertices, dtype=float).reshape(-1, 3)
    tri = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if len(tri) == 0:
        return verts, tri
    valid = np.all((tri >= 0) & (tri < len(verts)), axis=1)
    tri = tri[valid]
    tri = tri[(tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 2] != tri[:, 0])]
    if len(tri) == 0:
        return verts[:0], tri
    used, inverse = np.unique(tri.reshape(-1), return_inverse=True)
    compact_vertices = verts[used]
    compact_faces = inverse.reshape(-1, 3)
    return compact_vertices, compact_faces


def _cluster_mesh(vertices: Any, faces: Any, target_faces: int) -> tuple[Any, Any, bool]:
    """Small dependency-free vertex-clustering fallback for very large STL meshes."""
    import numpy as np

    verts = np.asarray(vertices, dtype=float).reshape(-1, 3)
    tri = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if len(tri) <= target_faces or target_faces <= 0:
        return verts, tri, False

    vmin = np.min(verts, axis=0)
    extent = np.max(verts, axis=0) - vmin
    extent[extent < 1e-12] = 1.0
    best = None
    # High to low resolution.  The first result under the face target preserves
    # the greatest amount of detail among this deterministic set.
    for resolution in (160, 128, 112, 96, 80, 72, 64, 56, 48, 40, 32, 28, 24, 20, 16, 12, 10, 8):
        keys = np.floor((verts - vmin) / extent * float(resolution) + 0.5).astype(np.int32)
        unique_keys, inverse = np.unique(keys, axis=0, return_inverse=True)
        counts = np.bincount(inverse, minlength=len(unique_keys)).astype(float)
        clustered = np.zeros((len(unique_keys), 3), dtype=float)
        for axis in range(3):
            clustered[:, axis] = np.bincount(inverse, weights=verts[:, axis], minlength=len(unique_keys)) / np.maximum(counts, 1.0)
        remapped = inverse[tri]
        remapped = remapped[
            (remapped[:, 0] != remapped[:, 1])
            & (remapped[:, 1] != remapped[:, 2])
            & (remapped[:, 2] != remapped[:, 0])
        ]
        if len(remapped) == 0:
            continue
        sorted_faces = np.sort(remapped, axis=1)
        _, unique_idx = np.unique(sorted_faces, axis=0, return_index=True)
        remapped = remapped[np.sort(unique_idx)]
        candidate = _compact_mesh(clustered, remapped)
        best = candidate
        if len(candidate[1]) <= target_faces:
            return candidate[0], candidate[1], True

    if best is not None and len(best[1]):
        return best[0], best[1], True

    # Last-resort deterministic triangle selection.  This path is rarely used,
    # but guarantees that export cannot be blocked by an unusually malformed mesh.
    indexes = np.linspace(0, len(tri) - 1, max(1, target_faces), dtype=np.int64)
    compact_v, compact_f = _compact_mesh(verts, tri[indexes])
    return compact_v, compact_f, True


def _box_mesh(size: Sequence[float]) -> tuple[Any, Any]:
    import numpy as np

    sx, sy, sz = [float(v) for v in list(size)[:3]]
    vertices = np.asarray(
        [
            [-sx, -sy, -sz], [sx, -sy, -sz], [sx, sy, -sz], [-sx, sy, -sz],
            [-sx, -sy, sz], [sx, -sy, sz], [sx, sy, sz], [-sx, sy, sz],
        ],
        dtype=float,
    )
    faces = np.asarray(
        [
            [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
            [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
        ],
        dtype=np.int64,
    )
    return vertices, faces


def _uv_surface(radius_xyz: Sequence[float], rings: int = 12, segments: int = 20) -> tuple[Any, Any]:
    import numpy as np

    rx, ry, rz = [max(abs(float(v)), 1e-7) for v in list(radius_xyz)[:3]]
    vertices = []
    for ring in range(rings + 1):
        phi = -0.5 * math.pi + math.pi * ring / rings
        cp, sp = math.cos(phi), math.sin(phi)
        for segment in range(segments):
            theta = 2.0 * math.pi * segment / segments
            vertices.append([rx * cp * math.cos(theta), ry * cp * math.sin(theta), rz * sp])
    faces = []
    for ring in range(rings):
        for segment in range(segments):
            nxt = (segment + 1) % segments
            a = ring * segments + segment
            b = ring * segments + nxt
            c = (ring + 1) * segments + nxt
            d = (ring + 1) * segments + segment
            faces.append([a, b, c])
            faces.append([a, c, d])
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64)


def _cylinder_mesh(radius: float, half_length: float, segments: int = 24) -> tuple[Any, Any]:
    import numpy as np

    r = max(abs(float(radius)), 1e-7)
    h = max(abs(float(half_length)), 1e-7)
    vertices = []
    for z in (-h, h):
        for i in range(segments):
            theta = 2.0 * math.pi * i / segments
            vertices.append([r * math.cos(theta), r * math.sin(theta), z])
    vertices.extend([[0.0, 0.0, -h], [0.0, 0.0, h]])
    bottom_center = 2 * segments
    top_center = bottom_center + 1
    faces = []
    for i in range(segments):
        j = (i + 1) % segments
        faces.extend([[i, j, segments + j], [i, segments + j, segments + i]])
        faces.append([bottom_center, j, i])
        faces.append([top_center, segments + i, segments + j])
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64)


def _capsule_mesh(radius: float, half_length: float, segments: int = 24, hemi_rings: int = 6) -> tuple[Any, Any]:
    import numpy as np

    r = max(abs(float(radius)), 1e-7)
    h = max(abs(float(half_length)), 0.0)
    rings: list[tuple[float, float]] = []
    for i in range(hemi_rings + 1):
        phi = -0.5 * math.pi + (0.5 * math.pi) * i / hemi_rings
        rings.append((r * math.cos(phi), -h + r * math.sin(phi)))
    if h > 1e-12:
        rings.append((r, h))
    for i in range(1, hemi_rings + 1):
        phi = (0.5 * math.pi) * i / hemi_rings
        rings.append((r * math.cos(phi), h + r * math.sin(phi)))
    vertices = []
    for rr, z in rings:
        for i in range(segments):
            theta = 2.0 * math.pi * i / segments
            vertices.append([rr * math.cos(theta), rr * math.sin(theta), z])
    faces = []
    for ring in range(len(rings) - 1):
        for i in range(segments):
            j = (i + 1) % segments
            a = ring * segments + i
            b = ring * segments + j
            c = (ring + 1) * segments + j
            d = (ring + 1) * segments + i
            faces.extend([[a, b, c], [a, c, d]])
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64)


def _plane_mesh(extent: float) -> tuple[Any, Any]:
    import numpy as np

    e = max(float(extent), 1.0)
    vertices = np.asarray([[-e, -e, 0.0], [e, -e, 0.0], [e, e, 0.0], [-e, e, 0.0]], dtype=float)
    faces = np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return vertices, faces


def _mesh_from_geom(model: Any, geom_id: int, mujoco_module: Any, max_faces: int) -> tuple[str, Any, Any, bool]:
    import numpy as np

    geom_type = int(model.geom_type[geom_id])
    size = np.asarray(model.geom_size[geom_id], dtype=float)
    enum = mujoco_module.mjtGeom
    simplified = False

    if geom_type == int(enum.mjGEOM_MESH):
        mesh_id = int(model.geom_dataid[geom_id])
        if mesh_id < 0:
            return f"missing-mesh-{geom_id}", *_box_mesh((0.01, 0.01, 0.01)), False
        vadr = int(model.mesh_vertadr[mesh_id])
        vnum = int(model.mesh_vertnum[mesh_id])
        fadr = int(model.mesh_faceadr[mesh_id])
        fnum = int(model.mesh_facenum[mesh_id])
        vertices = np.asarray(model.mesh_vert[vadr:vadr + vnum], dtype=float).copy()
        faces = np.asarray(model.mesh_face[fadr:fadr + fnum], dtype=np.int64).copy()
        vertices, faces, simplified = _cluster_mesh(vertices, faces, max_faces)
        return f"mesh-{mesh_id}-{max_faces}", vertices, faces, simplified
    if geom_type == int(enum.mjGEOM_BOX):
        return "box-" + "-".join(f"{v:.7g}" for v in size[:3]), *_box_mesh(size[:3]), False
    if geom_type == int(enum.mjGEOM_SPHERE):
        r = float(size[0])
        return f"sphere-{r:.7g}", *_uv_surface((r, r, r)), False
    if geom_type == int(enum.mjGEOM_ELLIPSOID):
        return "ellipsoid-" + "-".join(f"{v:.7g}" for v in size[:3]), *_uv_surface(size[:3]), False
    if geom_type == int(enum.mjGEOM_CYLINDER):
        return f"cylinder-{size[0]:.7g}-{size[1]:.7g}", *_cylinder_mesh(size[0], size[1]), False
    if geom_type == int(enum.mjGEOM_CAPSULE):
        return f"capsule-{size[0]:.7g}-{size[1]:.7g}", *_capsule_mesh(size[0], size[1]), False
    if geom_type == int(enum.mjGEOM_PLANE):
        extent = max(float(getattr(model.stat, "extent", 1.0)) * 4.0, 1.0)
        return f"plane-{extent:.7g}", *_plane_mesh(extent), False

    # Height fields, SDFs and less common types get a conservative visual proxy
    # rather than blocking the entire one-click export.
    proxy_size = [max(abs(float(v)), 0.01) for v in size[:3]]
    return f"proxy-{geom_type}-" + "-".join(f"{v:.7g}" for v in proxy_size), *_box_mesh(proxy_size), False


def _native_pair_distance(mujoco_module: Any, model: Any, data: Any, group_a: Mapping[str, Any], group_b: Mapping[str, Any], distmax: float) -> tuple[float, list[float] | None]:
    import numpy as np

    best = float("inf")
    best_line = None
    query_limit = max(float(distmax), float(getattr(model.stat, "extent", 1.0)) * 4.0, 1.0)
    for item_a in list(group_a.get("items", []) or []):
        gid_a = int(item_a.get("gid", -1))
        if gid_a < 0:
            continue
        for item_b in list(group_b.get("items", []) or []):
            gid_b = int(item_b.get("gid", -1))
            if gid_b < 0:
                continue
            fromto = np.zeros((6,), dtype=float)
            try:
                value = float(mujoco_module.mj_geomDistance(model, data, gid_a, gid_b, query_limit, fromto))
            except Exception:
                continue
            if value < best:
                best = value
                best_line = [float(v) for v in fromto]
    return best, best_line



def _drive_is_angular(joint_type: Any) -> bool:
    return str(joint_type or "").strip().lower() in {"rotation", "crank", "custom", "fivebar_ab"}


def _drive_display_unit(joint_type: Any) -> str:
    return "°" if _drive_is_angular(joint_type) else "mm"


def _drive_value_to_display(joint_type: Any, value_internal: Any) -> float:
    try:
        value = float(value_internal)
    except Exception:
        return float("nan")
    if not math.isfinite(value):
        return float("nan")
    return math.degrees(value) if _drive_is_angular(joint_type) else value * 1000.0


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return float(default)
    return out if math.isfinite(out) else float(default)


def _build_gantt_rows(drives: Sequence[Mapping[str, Any]], start_time: float, end_time: float) -> list[dict[str, Any]]:
    """Create browser-safe Gantt rows from the already resolved drive schedule."""
    rows: list[dict[str, Any]] = []
    for drive_index, drive in enumerate(drives):
        name = str(drive.get("name", "") or "").strip() or f"驱动{drive_index + 1}"
        unit = _drive_display_unit(drive.get("joint_type", ""))
        cumulative = 0.0
        segments: list[dict[str, Any]] = []
        for segment_index, segment in enumerate(list(drive.get("segments", []) or []), start=1):
            seg_start = _finite_float(segment.get("_start", segment.get("start_time_value", start_time)), start_time)
            duration = max(0.0, _finite_float(segment.get("_duration", segment.get("duration", 0.0)), 0.0))
            seg_end = _finite_float(segment.get("_end", seg_start + duration), seg_start + duration)
            if seg_end < seg_start:
                seg_start, seg_end = seg_end, seg_start
            # The serialized `travel` field is already in user display units.
            travel_display = _finite_float(segment.get("travel", 0.0), 0.0)
            travel_start = _finite_float(segment.get("_travel_start", cumulative), cumulative)
            travel_end = _finite_float(segment.get("_travel_end", travel_start + travel_display), travel_start + travel_display)
            cumulative = travel_end
            profile = str(segment.get("motion_profile", "") or "")
            if seg_end <= seg_start + 1e-12 and profile == "drive_mapping":
                # Mapping followers are still represented by the real-time sampled
                # channel value on the right; a zero-width block would not be useful.
                continue
            segments.append(
                {
                    "name": str(segment.get("name", "") or f"运动段{segment_index}"),
                    "start": max(float(start_time), min(float(end_time), float(seg_start))),
                    "end": max(float(start_time), min(float(end_time), float(seg_end))),
                    "travelStart": float(travel_start),
                    "travelEnd": float(travel_end),
                    "unit": unit,
                }
            )
        rows.append(
            {
                "name": name,
                "driveIndex": int(drive_index),
                "unit": unit,
                "segments": segments,
            }
        )
    return rows


def _load_latest_qt_gantt_snapshot() -> tuple[str, dict[str, Any]]:
    """Return the latest saved Qt Gantt PNG and its coordinate metadata."""
    cache_dir = Path(tempfile.gettempdir()) / "mujoco_xml_tool_v20_7"
    png_path = cache_dir / "latest_gantt.png"
    json_path = cache_dir / "latest_gantt.json"
    try:
        if not png_path.is_file() or not json_path.is_file():
            return "", {}
        with json_path.open("r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        if metadata.get("format") != "MUJOCO_XML_TOOL_GANTT_CACHE":
            return "", {}
        image_bytes = png_path.read_bytes()
        if not image_bytes:
            return "", {}
        return "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii"), metadata
    except Exception:
        return "", {}


def _animation_watermark_config(
    payload: Mapping[str, Any],
    *,
    default_color: str = "#B3B3B3",
) -> dict[str, Any]:
    text = str(payload.get("animation_watermark_text", "C项目-时序仿真组") or "")
    raw_position = str(payload.get("animation_watermark_position", "0, 0, 0") or "0, 0, 0")
    cleaned = raw_position.replace("Point", "").replace("point", "")
    for char in "()[]，;；":
        cleaned = cleaned.replace(char, "," if char in "，;；" else " ")
    parts = [part for part in cleaned.replace(",", " ").split() if part]
    if len(parts) != 3:
        raise AnimationHtmlExportError("水印位置必须包含 X、Y、Z 三个坐标值，例如：0, 0, 0。")
    try:
        position_mm = [float(part) for part in parts]
        size_mm = float(payload.get("animation_watermark_size_mm", 150) or 150)
        thickness_mm = float(payload.get("animation_watermark_thickness_mm", 10) or 10)
    except (TypeError, ValueError) as ex:
        raise AnimationHtmlExportError("水印位置、大小和厚度必须是有效数字。") from ex
    if not all(math.isfinite(value) for value in position_mm + [size_mm, thickness_mm]):
        raise AnimationHtmlExportError("水印位置、大小和厚度必须是有限数字。")
    if size_mm <= 0:
        raise AnimationHtmlExportError("水印大小必须大于 0 mm。")
    if thickness_mm <= 0:
        raise AnimationHtmlExportError("水印厚度必须大于 0 mm。")
    color = str(payload.get("animation_watermark_color", default_color) or default_color).strip()
    # V21.4.2 stored the old fixed default in every payload. Treat that value
    # as "use the scene floor" so older project files also get a true match.
    if color.upper() == "#B3B3B3" and default_color.upper() != "#B3B3B3":
        color = default_color
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        raise AnimationHtmlExportError("水印颜色必须是 #RRGGBB 格式。")
    color_rgb = [int(color[index:index + 2], 16) / 255.0 for index in (1, 3, 5)]
    return {
        "text": text,
        "position": [value / 1000.0 for value in position_mm],
        "height": size_mm / 1000.0,
        "thickness": thickness_mm / 1000.0,
        "color": color_rgb + [1.0],
    }


def _build_html_document(title: str, payload: Mapping[str, Any]) -> str:
    safe_title = html.escape(title or "MuJoCo animation", quote=True)
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>__TITLE__</title>
<style>
:root{color-scheme:dark;--bg:#0d1117;--panel:rgba(18,24,34,.94);--panel2:#111823;--line:#2b3442;--text:#edf2f8;--muted:#aab5c3;--accent:#4da3ff;--accent-soft:rgba(77,163,255,.24);--danger:#ff5f68;--active:#ffb454;--positive:#4ed6b3}*{box-sizing:border-box}html,body{width:100%;height:100%;margin:0;overflow:hidden;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}button,select,input{font:inherit}[hidden]{display:none!important}.app{position:relative;width:100%;height:100%}canvas{display:block;width:100%;height:100%;touch-action:none;background:#505860}.topbar{position:absolute;left:12px;right:12px;top:12px;display:flex;align-items:flex-start;gap:10px;pointer-events:none}.titlebox{pointer-events:auto;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:9px 12px;backdrop-filter:blur(8px);max-width:min(48vw,620px)}.title{font-weight:650;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.render-mode-suffix{font-size:10px;font-weight:500;color:rgba(237,242,248,.82)}.subtitle{font-size:12px;color:var(--muted);margin-top:2px}.top-actions{margin-left:auto;display:flex;flex-wrap:wrap;justify-content:flex-end;gap:5px;pointer-events:auto;max-width:58vw}.btn{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:10px;padding:8px 11px;cursor:pointer;white-space:nowrap}.top-actions .btn{border-radius:7px;padding:5px 8px;font-size:9px}.btn:hover{border-color:var(--accent)}.btn.active{border-color:var(--accent);background:var(--accent-soft)}.btn:disabled{cursor:not-allowed;opacity:.45}.panel{position:absolute;right:12px;top:106px;width:min(340px,calc(100vw - 24px));max-height:calc(100vh - 210px);overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;backdrop-filter:blur(8px)}.panel-head{display:flex;align-items:flex-start;gap:10px;justify-content:space-between;margin-bottom:6px}.panel-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 8px;align-items:center;min-width:150px}.panel-options .adaptive{justify-content:flex-start;text-align:left;white-space:nowrap}.panel h2{font-size:14px;margin:2px 0 0}.drive-status-head{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(0,1fr) minmax(110px,.9fr);gap:8px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,.12);font-size:11px;color:var(--muted);font-weight:650}.drive-status-row{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(0,1fr) minmax(110px,.9fr);gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.07);font-size:12px}.drive-status-row:last-child{border-bottom:0}.drive-status-name,.drive-status-motion{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.drive-status-value{text-align:right;font-variant-numeric:tabular-nums}.drive-status-value b{color:var(--accent);font-weight:700;margin-left:5px}.adaptive{display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted);cursor:pointer;text-align:right}.adaptive input,.pair input{accent-color:var(--accent)}.pair{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:8px;align-items:center;padding:7px 0;border-top:1px solid rgba(255,255,255,.07)}.pair:first-of-type{border-top:0}.pair.filtered{opacity:.45}.pair-name{font-size:13px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pair-value{font-variant-numeric:tabular-nums;font-size:12px;color:var(--muted)}.empty{font-size:13px;color:var(--muted);padding:8px 0}.controls{position:absolute;left:12px;right:12px;bottom:12px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:10px 12px;backdrop-filter:blur(9px)}.transport{display:grid;grid-template-columns:auto minmax(120px,1fr) auto auto;gap:10px;align-items:center}.transport-buttons{display:flex;gap:5px}.transport-button{min-width:40px;height:34px;padding:0 8px}.timeline{width:100%;accent-color:var(--accent)}.time{font-variant-numeric:tabular-nums;font-size:13px;white-space:nowrap}.speed{border:1px solid var(--line);background:var(--panel2);color:var(--text);border-radius:8px;padding:6px}.hint{font-size:11px;color:var(--muted);margin-top:6px}.developer-support{font-size:10px;color:var(--muted);margin-top:3px;text-align:right;line-height:1.2}.label-layer{position:absolute;inset:0;pointer-events:none;overflow:hidden}.distance-label{position:absolute;transform:translate(-50%,-50%);padding:3px 6px;border-radius:6px;background:transparent;border:1px solid transparent;text-shadow:0 1px 2px rgba(0,0,0,.85);font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}.warning{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);max-width:620px;padding:18px;background:#291f22;border:1px solid #704148;border-radius:12px;color:#ffd9dc;display:none}.loading{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);padding:14px 18px;background:var(--panel);border:1px solid var(--line);border-radius:12px;color:var(--muted)}
.gantt-window{position:absolute;z-index:20;left:24px;top:84px;width:900px;height:506px;min-width:320px;min-height:72px;display:flex;flex-direction:column;background:rgba(15,21,31,.97);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 18px 48px rgba(0,0,0,.42);backdrop-filter:blur(8px)}.gantt-header{display:flex;align-items:center;gap:10px;height:42px;padding:6px 8px 6px 12px;border-bottom:1px solid var(--line);cursor:move;touch-action:none;user-select:none}.gantt-header h2{font-size:14px;margin:0}.gantt-close{margin-left:auto;padding:5px 9px}.gantt-body{min-height:0;flex:1;overflow:hidden}.gantt-scroll{overflow-y:auto;overflow-x:hidden;width:100%;height:100%;padding:8px}.gantt-chart{--gantt-second-step:10%;width:100%;min-width:0}.gantt-axis,.gantt-row{display:grid;grid-template-columns:minmax(84px,22%) minmax(80px,1fr) minmax(78px,20%);align-items:stretch;width:100%;min-width:0}.gantt-axis-label,.gantt-row-label,.gantt-axis-value,.gantt-row-value{border-bottom:1px solid rgba(255,255,255,.07);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}.gantt-axis-label,.gantt-row-label{padding:0 10px;border-right:1px solid var(--line);display:flex;align-items:center}.gantt-axis-label,.gantt-axis-value{height:34px;color:var(--muted)}.gantt-axis-value,.gantt-row-value{padding:0 10px;border-left:1px solid var(--line);display:flex;align-items:center;justify-content:flex-end;font-variant-numeric:tabular-nums}.gantt-axis-track{height:34px;position:relative;border-bottom:1px solid var(--line);background-image:linear-gradient(to right,rgba(255,255,255,.10) 1px,transparent 1px);background-size:var(--gantt-second-step) 100%;min-width:0;overflow:visible}.gantt-tick{position:absolute;top:0;bottom:0;border-left:1px solid rgba(255,255,255,.18);pointer-events:none}.gantt-tick span{position:absolute;top:5px;left:5px;font-size:11px;color:var(--muted);white-space:nowrap}.gantt-row-label,.gantt-track,.gantt-row-value{height:44px}.gantt-track{position:relative;border-bottom:1px solid rgba(255,255,255,.07);background-color:rgba(255,255,255,.012);background-image:linear-gradient(to right,rgba(255,255,255,.07) 1px,transparent 1px);background-size:var(--gantt-second-step) 100%;min-width:0;overflow:visible}.gantt-segment{position:absolute;top:9px;height:26px;border-radius:6px;background:#6d7888;border:1px solid rgba(255,255,255,.22);padding:4px 7px;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;z-index:2;transition:background .12s,border-color .12s,filter .12s}.gantt-segment.completed{filter:saturate(.8);background:#496b91}.gantt-segment.active{background:var(--active);border-color:#ffd291;color:#1f1608;font-weight:650}.gantt-mask{position:absolute;left:0;top:0;bottom:0;width:0;background:rgba(50,139,255,.17);z-index:3;pointer-events:none}.gantt-cursor{position:absolute;top:0;bottom:0;width:16px;transform:translateX(-8px);background:transparent;z-index:5;cursor:ew-resize;touch-action:none;pointer-events:auto}.gantt-cursor::before{content:"";position:absolute;left:7px;top:0;bottom:0;width:2px;background:#64b5ff;box-shadow:0 0 0 1px rgba(0,0,0,.25)}.gantt-cursor:hover::before,.gantt-cursor.dragging::before{width:3px;left:6.5px;background:#9bd2ff}.gantt-axis-cursor{z-index:6}.gantt-row-value.active{color:var(--active);font-weight:650}.gantt-row-value.positive:not(.active){color:var(--positive)}.gantt-row-value.negative:not(.active){color:#ff858d}.gantt-row-value.zero{color:var(--muted)}.gantt-footer{height:44px;border-top:1px solid var(--line);padding:7px 12px;display:grid;grid-template-columns:minmax(120px,1fr) auto;gap:10px;align-items:center}.gantt-footer input{width:100%;accent-color:var(--accent)}.gantt-time{font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}.gantt-resize{position:absolute;right:0;bottom:0;width:22px;height:22px;cursor:nwse-resize;touch-action:none}.gantt-resize::before,.gantt-resize::after{content:"";position:absolute;right:4px;bottom:4px;border-right:2px solid rgba(255,255,255,.55);border-bottom:2px solid rgba(255,255,255,.55)}.gantt-resize::before{width:12px;height:12px}.gantt-resize::after{width:6px;height:6px}
@media(max-width:900px){.topbar{align-items:flex-start}.titlebox{max-width:42vw}.top-actions{max-width:58vw}.top-actions .btn{padding:5px 6px;font-size:9px}.panel{top:122px}.gantt-axis,.gantt-row{grid-template-columns:minmax(76px,24%) minmax(70px,1fr) minmax(72px,22%)}}@media(max-width:720px){.titlebox{max-width:52vw}.subtitle{display:none}.top-actions{max-width:48vw}.top-actions .view-secondary{display:none}.panel{top:102px;max-height:38vh;width:245px}.controls{padding:8px}.transport{grid-template-columns:1fr}.transport-buttons{justify-content:center}.time{text-align:center}.speed{display:none}.hint{display:none}.gantt-axis,.gantt-row{grid-template-columns:minmax(68px,26%) minmax(60px,1fr) minmax(66px,24%)}.gantt-axis-label,.gantt-row-label,.gantt-axis-value,.gantt-row-value{font-size:11px;padding-left:6px;padding-right:6px}.gantt-footer{grid-template-columns:1fr}.gantt-time{text-align:center;display:none}}
.gantt-image-stage{position:relative;width:100%;height:100%;overflow:hidden;background:#fbfcfd;touch-action:none;cursor:ew-resize}.gantt-image-stage img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;user-select:none;pointer-events:none}.gantt-image-stage canvas{position:absolute;inset:0;width:100%;height:100%;background:transparent;touch-action:none}.gantt-fallback{width:100%;height:100%}
/* Keep the no-cache HTML renderer visually aligned with Qt's light gantt scene. */
.gantt-window{background:#eef1f5;color:#2b353c;border-color:#c8d1d9}.gantt-header{background:#017a81;color:#fff;border-bottom-color:#018c94}.gantt-header h2{color:#fff}.gantt-body,.gantt-scroll{background:#fbfcfd}.gantt-axis-label,.gantt-row-label,.gantt-axis-value,.gantt-row-value{color:#2b353c;border-color:#e4e9ee}.gantt-axis-label,.gantt-row-label{background:#fff}.gantt-axis-value,.gantt-row-value{background:#fff}.gantt-axis-track,.gantt-track{background-color:#fbfcfd;background-image:linear-gradient(to right,#e7ecf1 1px,transparent 1px);border-color:#e4e9ee}.gantt-tick{border-color:#94a2ac}.gantt-tick span{color:#687681}.gantt-segment{background:#f9b665;color:#2b353c;border-color:#e4e9ee}.gantt-segment.completed{background:#f9b665;filter:none}.gantt-segment.active{background:#018c94;border-color:#016e74;color:#fff}.gantt-mask{background:rgba(1,140,148,.15)}.gantt-cursor::before{background:#018c94;box-shadow:none}.gantt-cursor:hover::before,.gantt-cursor.dragging::before{background:#03a0a9}.gantt-row-value.active{color:#016e74}.gantt-row-value.positive:not(.active){color:#02787f}.gantt-row-value.negative:not(.active){color:#c33d32}.gantt-row-value.zero{color:#687681}.gantt-footer{background:#fff;border-top-color:#e4e9ee}.gantt-time{color:#687681}.perspective-switch{display:inline-flex;align-items:center;gap:5px;padding:5px 7px;border:1px solid var(--line);border-radius:7px;background:var(--panel);color:var(--text);font-size:9px;cursor:pointer;white-space:nowrap}.perspective-switch input{position:absolute;opacity:0;pointer-events:none}.perspective-switch span{position:relative;width:24px;height:14px;border-radius:999px;background:#66717e;box-shadow:inset 0 0 0 1px rgba(255,255,255,.12)}.perspective-switch span::after{content:"";position:absolute;left:2px;top:2px;width:10px;height:10px;border-radius:50%;background:#fff;transition:transform .16s}.perspective-switch input:checked+span{background:var(--accent)}.perspective-switch input:checked+span::after{transform:translateX(10px)}.perspective-switch b{font-weight:500}
.titlebox{background:rgba(18,24,34,.72);padding:7px 10px}.panel{top:58px;background:rgba(18,24,34,.20);padding:8px 9px;max-height:calc(100vh - 150px)}.panel h2{font-size:11px}.drive-status-head{grid-template-columns:minmax(0,1.4fr) minmax(0,.9fr) minmax(96px,.82fr);font-size:8px;padding:4px 0}.drive-status-row{grid-template-columns:minmax(0,1.4fr) minmax(0,.9fr) minmax(96px,.82fr);font-size:9px;padding:4px 0}.drive-status-value{white-space:nowrap;font-size:9px}.drive-status-value b{margin-left:3px}.controls{left:6px;right:6px;bottom:6px;background:rgba(18,24,34,.20);border-color:rgba(43,52,66,.20);border-radius:7px;padding:4px 5px;backdrop-filter:blur(4px)}.transport{grid-template-columns:auto minmax(60px,1fr) auto;gap:5px}.transport-buttons{gap:2px}.transport-button{min-width:20px;height:17px;padding:0 4px;border-radius:4px;font-size:7px}.timeline{height:9px}.time{font-size:7px}.developer-support{position:absolute;right:2px;bottom:2px;z-index:30;margin:0;padding:0;background:transparent;border:0;backdrop-filter:none;font-size:8px;line-height:1;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.72);pointer-events:none}</style>
</head>
<body>
<div class="app" id="app">
<canvas id="glcanvas" aria-label="MuJoCo 三维动画"></canvas>
<div class="label-layer" id="labelLayer"></div>
<div class="topbar">
  <div class="titlebox"><div class="title"><span id="modelTitle"></span><span class="render-mode-suffix" id="renderModeSuffix"></span></div></div>
  <div class="top-actions">
    <button class="btn" id="downloadAnimation">下载动画</button>
    <button class="btn" id="frontView">正视图</button>
    <button class="btn" id="sideView">侧视图</button>
    <button class="btn" id="povView">POV视图</button>
    <label class="perspective-switch view-secondary" title="开启透视后呈现近大远小效果"><input id="perspectiveToggle" type="checkbox"><span aria-hidden="true"></span><b>近大远小</b></label>
  </div>
</div>
<section class="panel" id="drivePanel">
  <div class="panel-head"><h2>模型总体位置</h2></div>
  <div class="drive-status-head"><span>控制对象</span><span>运动</span><span style="text-align:right">数值 / 百分比</span></div>
  <div id="driveStatusList"></div>
</section>
<div hidden aria-hidden="true"><button id="togglePanel"></button><span id="openGantt"></span><section id="pairPanel"><input id="selectAllPairs" type="checkbox"><input id="adaptiveVisibility" type="checkbox"><input id="showPairNames" type="checkbox"><input id="showPairBorders" type="checkbox"><div id="pairList"></div></section></div>
<div class="controls">
  <div class="transport">
    <div class="transport-buttons">
      <button class="btn transport-button" id="reverseButton" aria-label="倒放" title="倒放">◀</button>
      <button class="btn transport-button" id="playButton" aria-label="正向播放" title="正向播放">▶</button>
    </div>
    <input class="timeline" id="timeline" type="range">
    <div class="time" id="timeText">0.000 s</div>
  </div>
</div>
<div class="developer-support">开发支持：喻惟刚</div>
<section class="gantt-window" id="ganttWindow" role="dialog" aria-modal="false" aria-labelledby="ganttTitle" hidden>
  <header class="gantt-header" id="ganttDragHandle"><h2 id="ganttTitle">甘特图</h2><button class="btn gantt-close" id="exportGanttPng">导出甘特图png</button><button class="btn" id="closeGantt">关闭</button></header>
  <div class="gantt-body"><div class="gantt-image-stage" id="ganttImageStage" hidden><img id="ganttImage" alt="Qt 甘特图 PNG"><canvas id="ganttOverlay"></canvas></div><div class="gantt-fallback" id="ganttFallback"><div class="gantt-scroll"><div class="gantt-chart" id="ganttChart"></div></div></div></div>
  <footer class="gantt-footer"><input id="ganttTimeline" type="range" aria-label="甘特图时间"><div class="gantt-time" id="ganttTime">0.000 s</div></footer>
  <div class="gantt-resize" id="ganttResizeHandle" aria-hidden="true"></div>
</section>
<div class="loading" id="loading">正在载入离线动画…</div><div class="warning" id="warning"></div>
</div>
<script>
"use strict";
const DATA=__DATA_JSON__;
const QUERY=new URLSearchParams(location.search),MODEL_ID=QUERY.get("model_id")||"";
const $=id=>document.getElementById(id);
const canvas=$("glcanvas"),loading=$("loading"),warning=$("warning"),timeline=$("timeline"),playButton=$("playButton"),reverseButton=$("reverseButton"),timeText=$("timeText"),pairList=$("pairList"),labelLayer=$("labelLayer"),driveStatusList=$("driveStatusList"),ganttWindow=$("ganttWindow"),ganttDragHandle=$("ganttDragHandle"),ganttResizeHandle=$("ganttResizeHandle"),ganttTimeline=$("ganttTimeline"),ganttTime=$("ganttTime"),ganttImageStage=$("ganttImageStage"),ganttImage=$("ganttImage"),ganttOverlay=$("ganttOverlay"),ganttFallback=$("ganttFallback");
function showRendererBootFailure(reason){try{if(loading)loading.style.display="none";if(warning){warning.style.display="block";warning.textContent=`离线动画载入失败：${String(reason||"未知渲染错误")}`}}catch(_){}}
window.addEventListener("error",event=>showRendererBootFailure(event.error?.message||event.message));
window.addEventListener("unhandledrejection",event=>showRendererBootFailure(event.reason?.message||event.reason));
const RENDER_MODE_LABEL=String(DATA.renderProfile?.label||"快速渲染"),MODEL_DISPLAY_NAME=String(DATA.modelName||DATA.title||"模型");$("modelTitle").textContent=MODEL_DISPLAY_NAME;$("renderModeSuffix").textContent=`_${RENDER_MODE_LABEL}`;
timeline.min=String(DATA.start);timeline.max=String(DATA.end);timeline.step="0.001";timeline.value=String(DATA.start);
ganttTimeline.min=String(DATA.start);ganttTimeline.max=String(DATA.end);ganttTimeline.step="0.001";ganttTimeline.value=String(DATA.start);
function decodeB64(text,Type){const raw=atob(text||""),bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);return new Type(bytes.buffer)}
const times=decodeB64(DATA.times,Float32Array),transforms=decodeB64(DATA.transforms,Float32Array),measurements=decodeB64(DATA.measurements,Float32Array),driveValues=decodeB64(DATA.driveValues||"",Float32Array);
// Measurement values and endpoints are physical data.  Keep them raw; only the floating label UI is smoothed.
const measurementValues=measurements;
const gl=canvas.getContext("webgl2",{antialias:true,alpha:false,preserveDrawingBuffer:false});
if(!gl){loading.style.display="none";warning.style.display="block";warning.textContent="当前浏览器不支持 WebGL2。请使用最新版 Chrome、Edge、Firefox 或 Safari 打开。";throw new Error("WebGL2 unavailable")}
function compile(type,source){const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader)||"shader error");return shader}
function program(vs,fs){const p=gl.createProgram();gl.attachShader(p,compile(gl.VERTEX_SHADER,vs));gl.attachShader(p,compile(gl.FRAGMENT_SHADER,fs));gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(p)||"link error");return p}
const meshProgram=program(`#version 300 es
layout(location=0)in vec3 aPosition;layout(location=1)in vec3 aNormal;uniform mat4 uMVP;uniform mat4 uModel;uniform mat4 uLightVP;out vec3 vNormal;out vec3 vWorld;out vec3 vLocal;out vec3 vLocalNormal;out vec4 vShadow;void main(){vec4 world=uModel*vec4(aPosition,1.0);gl_Position=uMVP*vec4(aPosition,1.0);vNormal=normalize(mat3(uModel)*aNormal);vWorld=world.xyz;vLocal=aPosition;vLocalNormal=aNormal;vShadow=uLightVP*world;}`,`#version 300 es
precision highp float;in vec3 vNormal;in vec3 vWorld;in vec3 vLocal;in vec3 vLocalNormal;in vec4 vShadow;uniform mat4 uModel;uniform vec4 uColor;uniform vec3 uEye;uniform vec3 uFogColor;uniform float uFogNear;uniform float uFogFar;uniform float uMetallic;uniform float uRoughness;uniform float uSpecular;uniform float uClearcoat;uniform float uClearcoatRoughness;uniform float uEnvStrength;uniform float uQuality;uniform float uTextureScaleMm;uniform float uTextureScale;uniform float uTextureRotation;uniform float uNormalStrength;uniform float uAoStrength;uniform float uExposure;uniform float uEnvRotation;uniform float uShadowStrength;uniform float uShadowTexel;uniform vec3 uKeyLightDir;uniform vec3 uKeyLightColor;uniform int uHasBaseMap;uniform int uHasNormalMap;uniform int uHasRoughnessMap;uniform int uHasMetallicMap;uniform int uHasAoMap;uniform int uHasEnvironment;uniform int uShadowEnabled;uniform int uScenePresetMode;uniform sampler2D uBaseMap;uniform sampler2D uNormalMap;uniform sampler2D uRoughnessMap;uniform sampler2D uMetallicMap;uniform sampler2D uAoMap;uniform sampler2D uEnvironmentMap;uniform sampler2D uShadowMap;out vec4 outColor;const float PI=3.14159265359;float sat(float x){return clamp(x,0.0,1.0);}vec3 fresnel(vec3 f0,float vh){return f0+(1.0-f0)*pow(1.0-sat(vh),5.0);}float distribution(float nh,float r){float a=max(.035,r*r),a2=a*a,d=nh*nh*(a2-1.0)+1.0;return a2/max(PI*d*d,1e-5);}float geometry(float nv,float nl,float r){float k=pow(r+1.0,2.0)/8.0;float gv=nv/(nv*(1.0-k)+k),glv=nl/(nl*(1.0-k)+k);return gv*glv;}vec3 lightBRDF(vec3 n,vec3 v,vec3 l,vec3 radiance,vec3 base,vec3 f0,float rough,float metallic){vec3 h=normalize(v+l);float nl=sat(dot(n,l)),nv=sat(dot(n,v)),nh=sat(dot(n,h)),vh=sat(dot(v,h));vec3 F=fresnel(f0,vh);float D=distribution(nh,rough),G=geometry(nv,nl,rough);vec3 spec=D*G*F/max(4.0*nv*nl,.001);vec3 kd=(1.0-F)*(1.0-metallic);return(kd*base/PI+spec)*radiance*nl;}vec3 aces(vec3 x){float a=2.51,b=.03,c=2.43,d=.59,e=.14;return clamp((x*(a*x+b))/(x*(c*x+d)+e),0.0,1.0);}vec3 pbrNeutral(vec3 x){x=max(x,vec3(0.0));float peak=max(x.r,max(x.g,x.b));if(peak<=.8)return x;float shoulder=.8+.2*(1.0-exp(-(peak-.8)*1.65));return x*(shoulder/max(peak,1e-6));}vec3 triWeights(vec3 n){vec3 w=pow(abs(normalize(n)),vec3(5.0));return w/max(w.x+w.y+w.z,1e-5);}vec2 texUv(vec2 uv){float a=radians(uTextureRotation),c=cos(a),s=sin(a);uv*=max(uTextureScale,.1);return mat2(c,-s,s,c)*uv;}vec4 triSample(sampler2D tex,vec3 p,vec3 n){float scaleM=max(uTextureScaleMm*.001,.0001);vec3 q=p/scaleM,w=triWeights(n);vec4 sx=texture(tex,texUv(q.yz)),sy=texture(tex,texUv(q.xz)),sz=texture(tex,texUv(q.xy));return sx*w.x+sy*w.y+sz*w.z;}vec3 triNormalLocal(vec3 p,vec3 n){float scaleM=max(uTextureScaleMm*.001,.0001);vec3 q=p/scaleM,w=triWeights(n),sgn=sign(n);vec3 tx=texture(uNormalMap,texUv(q.yz)).xyz*2.0-1.0,ty=texture(uNormalMap,texUv(q.xz)).xyz*2.0-1.0,tz=texture(uNormalMap,texUv(q.xy)).xyz*2.0-1.0;tx.xy*=uNormalStrength;ty.xy*=uNormalStrength;tz.xy*=uNormalStrength;vec3 nx=normalize(vec3(sgn.x*tx.z,tx.x,tx.y));vec3 ny=normalize(vec3(ty.x,sgn.y*ty.z,ty.y));vec3 nz=normalize(vec3(tz.x,tz.y,sgn.z*tz.z));return normalize(nx*w.x+ny*w.y+nz*w.z);}vec2 envUv(vec3 d){d=normalize(d);float a=atan(d.y,d.x)+radians(uEnvRotation);float u=fract(a/(2.0*PI)+.5);float v=acos(clamp(d.z,-1.0,1.0))/PI;return vec2(u,v);}vec3 envSample(vec3 dir,float lod){if(uHasEnvironment==0){vec3 d=normalize(dir);float h=.5+.5*d.z;if(uScenePresetMode==2){vec3 base=mix(vec3(.055,.060,.068),vec3(.30,.315,.335),smoothstep(.02,.95,h));float roof=pow(sat(dot(d,normalize(vec3(.04,-.06,.997)))),2.2),windshield=pow(sat(dot(d,normalize(vec3(.10,-.88,.47)))),7.0),leftWindow=pow(sat(dot(d,normalize(vec3(.92,-.12,.37)))),8.0),rightWindow=pow(sat(dot(d,normalize(vec3(-.92,.10,.38)))),8.0),rearBounce=pow(sat(dot(d,normalize(vec3(-.08,.90,.43)))),6.0);return base+vec3(.28,.275,.265)*roof+vec3(.22,.225,.235)*windshield+vec3(.14,.145,.155)*leftWindow+vec3(.13,.138,.15)*rightWindow+vec3(.075,.067,.060)*rearBounce;}if(uScenePresetMode==1){vec3 base=mix(vec3(.40,.42,.44),vec3(.88,.91,.95),smoothstep(.05,.92,h));float topSoft=pow(sat(dot(d,normalize(vec3(.12,-.08,.99)))),4.0),leftSoft=pow(sat(dot(d,normalize(vec3(.78,-.38,.50)))),9.0),rightSoft=pow(sat(dot(d,normalize(vec3(-.70,.42,.57)))),10.0);return base+vec3(.18,.18,.17)*topSoft+vec3(.13,.125,.12)*leftSoft+vec3(.09,.095,.105)*rightSoft;}return mix(vec3(.10,.115,.13),vec3(.44,.48,.52),h);}return pow(max(textureLod(uEnvironmentMap,envUv(dir),lod).rgb,vec3(0.0)),vec3(2.2));}float shadowVisibility(vec3 n){if(uShadowEnabled==0)return 1.0;vec3 sc=vShadow.xyz/max(vShadow.w,1e-6);sc=sc*.5+.5;if(sc.x<=0.0||sc.x>=1.0||sc.y<=0.0||sc.y>=1.0||sc.z<=0.0||sc.z>=1.0)return 1.0;vec3 l=normalize(uKeyLightDir);float bias=max(.00018,.0011*(1.0-sat(dot(n,l))));float current=sc.z-bias,sum=0.0;float pcf=1.0;if(uQuality>1.5){for(int x=-2;x<=2;x++)for(int y=-2;y<=2;y++){float depth=texture(uShadowMap,sc.xy+vec2(float(x),float(y))*uShadowTexel*.72).r;sum+=current<=depth?1.0:0.0;}pcf=sum/25.0;}else{for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++){float depth=texture(uShadowMap,sc.xy+vec2(float(x),float(y))*uShadowTexel).r;sum+=current<=depth?1.0:0.0;}pcf=sum/9.0;}return mix(1.0,pcf,sat(uShadowStrength));}void main(){vec3 localN=normalize(vLocalNormal),n=normalize(vNormal);if(uHasNormalMap==1)n=normalize(mat3(uModel)*triNormalLocal(vLocal,localN));vec3 base=pow(max(uColor.rgb,vec3(0.0)),vec3(2.2));if(uHasBaseMap==1)base*=pow(max(triSample(uBaseMap,vLocal,localN).rgb,vec3(0.0)),vec3(2.2));float rough=clamp(uRoughness,.045,1.0),metal=sat(uMetallic),ao=1.0;if(uHasRoughnessMap==1)rough=clamp(rough*max(triSample(uRoughnessMap,vLocal,localN).r,.02),.045,1.0);if(uHasMetallicMap==1)metal=sat(metal*triSample(uMetallicMap,vLocal,localN).r);if(uHasAoMap==1)ao=mix(1.0,triSample(uAoMap,vLocal,localN).r,sat(uAoStrength));vec3 v=normalize(uEye-vWorld);vec3 f0=mix(vec3(.04*max(uSpecular,.05)),base,metal);float shadow=shadowVisibility(n);vec3 color;if(uScenePresetMode==2){color=lightBRDF(n,v,uKeyLightDir,uKeyLightColor*vec3(1.02,.99,.95),base,f0,rough,metal)*shadow;color+=lightBRDF(n,v,normalize(vec3(.02,-.93,.36)),vec3(1.18,1.20,1.24),base,f0,rough,metal);if(uQuality>.5){color+=lightBRDF(n,v,normalize(vec3(.88,-.10,.47)),vec3(.88,.90,.94),base,f0,rough,metal);color+=lightBRDF(n,v,normalize(vec3(-.86,.14,.49)),vec3(.82,.86,.92),base,f0,rough,metal);}if(uQuality>1.5){color+=lightBRDF(n,v,normalize(vec3(-.05,.91,.41)),vec3(.38,.33,.29),base,f0,rough,metal);color+=lightBRDF(n,v,normalize(vec3(.12,.12,.985)),vec3(.48,.47,.45),base,f0,rough,metal);}}else if(uScenePresetMode==1){color=lightBRDF(n,v,uKeyLightDir,uKeyLightColor,base,f0,rough,metal)*shadow;color+=lightBRDF(n,v,normalize(vec3(-.12,-.74,.66)),vec3(1.05,1.08,1.12),base,f0,rough,metal);if(uQuality>.5){color+=lightBRDF(n,v,normalize(vec3(-.72,.28,.58)),vec3(1.35,1.42,1.52),base,f0,rough,metal);color+=lightBRDF(n,v,normalize(vec3(.08,.82,.36)),vec3(.72,.76,.82),base,f0,rough,metal);}if(uQuality>1.5){color+=lightBRDF(n,v,normalize(vec3(-.18,-.86,.46)),vec3(.48,.50,.54),base,f0,rough,metal);color+=lightBRDF(n,v,normalize(vec3(.76,.30,.34)),vec3(.34,.33,.31),base,f0,rough,metal);}}else{color=lightBRDF(n,v,uKeyLightDir,uKeyLightColor*vec3(.98,.98,1.02),base,f0,rough,metal)*shadow;if(uQuality>.5){color+=lightBRDF(n,v,normalize(vec3(-.72,.28,.58)),vec3(1.55,1.78,2.05),base,f0,rough,metal);color+=lightBRDF(n,v,normalize(vec3(.08,.82,.36)),vec3(.62,.72,.88),base,f0,rough,metal);}if(uQuality>1.5){color+=lightBRDF(n,v,normalize(vec3(-.18,-.86,.46)),vec3(.42,.52,.72),base,f0,rough,metal);color+=lightBRDF(n,v,normalize(vec3(.76,.30,.34)),vec3(.28,.24,.22),base,f0,rough,metal);}}vec3 R=reflect(-v,n),envSpec=envSample(R,rough*6.0),envDiff=envSample(n,5.5);float nv=sat(dot(n,v));vec3 F=fresnel(f0,nv);float specOcc=sat(pow(nv+ao,exp2(-16.0*rough-1.0))-1.0+ao);float diffuseWeight=.24+.18*(1.0-rough),specWeight=.30+.74*(1.0-rough);vec3 ambient=(base*(1.0-metal)*envDiff*diffuseWeight*ao+(F*envSpec)*specWeight*specOcc)*uEnvStrength;color+=ambient;if(uQuality>1.5&&uScenePresetMode==2){float softSheen=(1.0-metal)*smoothstep(.48,.92,rough)*pow(1.0-nv,2.2);color+=base*envDiff*softSheen*.16*uEnvStrength;}float coatR=clamp(uClearcoatRoughness,.03,1.0);vec3 coatF=fresnel(vec3(.04),nv);color+=envSample(R,coatR*5.5)*coatF*uClearcoat*.46*(1.0-coatR*.45)*specOcc;color=uQuality>1.5?pbrNeutral(color*max(uExposure,.05)):aces(color*max(uExposure,.05));color=pow(color,vec3(1.0/2.2));float fog=smoothstep(uFogNear,uFogFar,distance(vWorld,uEye));outColor=vec4(mix(color,uFogColor,fog),uColor.a);}`);
const shadowProgram=program(`#version 300 es
layout(location=0)in vec3 aPosition;uniform mat4 uMVP;void main(){gl_Position=uMVP*vec4(aPosition,1.0);}`,`#version 300 es
precision highp float;void main(){}`);
const lineProgram=program(`#version 300 es
layout(location=0)in vec3 aPosition;uniform mat4 uVP;void main(){gl_Position=uVP*vec4(aPosition,1.0);}`,`#version 300 es
precision highp float;uniform vec4 uColor;out vec4 outColor;void main(){outColor=uColor;}`);
const backgroundProgram=program(`#version 300 es
out vec2 vUv;void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);vUv=p*.5;gl_Position=vec4(p*2.0-1.0,0.9999,1.0);}`,`#version 300 es
precision highp float;in vec2 vUv;uniform vec3 uFloorEdgeColor;uniform vec3 uBackgroundTop;uniform vec3 uBackgroundMid;uniform vec3 uBackgroundHorizon;uniform int uScenePresetMode;out vec4 outColor;void main(){if(uScenePresetMode==0){vec3 c=uFloorEdgeColor;float vignette=smoothstep(.92,.20,distance(vUv,vec2(.5,.48)));c*=.96+.04*vignette;outColor=vec4(c,1.0);return;}float y=clamp(vUv.y,0.0,1.0);vec3 c=mix(uBackgroundHorizon,uBackgroundMid,smoothstep(.08,.52,y));c=mix(c,uBackgroundTop,smoothstep(.50,1.0,y));float radial=distance(vUv,vec2(.5,.50));c*=1.0-.025*smoothstep(.28,.78,radial);float horizonGlow=exp(-pow((y-.19)/.17,2.0));c=mix(c,uBackgroundMid,horizonGlow*.18);outColor=vec4(c,1.0);}`);
const floorProgram=program(`#version 300 es
uniform mat4 uVP;uniform vec3 uCenter;uniform float uFloorZ;uniform float uSize;out vec3 vWorld;void main(){vec2 corner=vec2((gl_VertexID==1||gl_VertexID==2||gl_VertexID==4)?1.0:-1.0,(gl_VertexID==2||gl_VertexID==4||gl_VertexID==5)?1.0:-1.0);vWorld=vec3(uCenter.xy+corner*uSize,uFloorZ);gl_Position=uVP*vec4(vWorld,1.0);}`,`#version 300 es
precision highp float;in vec3 vWorld;uniform vec3 uEye;uniform vec3 uFogColor;uniform vec3 uFloorEdgeColor;uniform vec3 uFloorColor;uniform vec3 uCenter;uniform float uGridSize;uniform float uMajorEvery;uniform float uFadeStart;uniform float uFadeEnd;uniform float uGridStrength;uniform float uRingRadius;uniform int uScenePresetMode;out vec4 outColor;float gridLine(vec2 p,float size){vec2 q=p/size;vec2 d=fwidth(q);vec2 a=abs(fract(q-.5)-.5)/max(d,vec2(1e-5));return 1.0-min(min(a.x,a.y),1.0);}void main(){if(!gl_FrontFacing)discard;float minor=gridLine(vWorld.xy,uGridSize),major=gridLine(vWorld.xy,uGridSize*uMajorEvery);float dist=distance(vWorld.xy,uEye.xy);float fade=1.0-smoothstep(uFadeStart,uFadeEnd,dist);if(uScenePresetMode==0){vec3 base=uFloorColor;vec3 minorColor=mix(base,uFloorEdgeColor,0.42);vec3 majorColor=mix(base,uFloorEdgeColor,0.68);vec3 c=mix(base,minorColor,minor*.38*fade);c=mix(c,majorColor,major*.5*fade);float sheen=pow(max(0.0,1.0-abs(normalize(uEye-vWorld).z)),2.0);c+=uFloorEdgeColor*.08*sheen;float edge=smoothstep(uFadeStart*.68,uFadeEnd*.96,dist);c=mix(c,uFloorEdgeColor,edge);outColor=vec4(c,.92);return;}vec3 base=uFloorColor;vec3 lineColor=max(base-vec3(.075),vec3(0.0));vec3 c=mix(base,lineColor,minor*.08*uGridStrength*fade);c=mix(c,lineColor,major*.12*uGridStrength*fade);float radius=distance(vWorld.xy,uCenter.xy),ringWidth=max(fwidth(radius)*1.5,uGridSize*.018),ring=1.0-smoothstep(ringWidth,ringWidth*2.2,abs(radius-uRingRadius));c=mix(c,lineColor,ring*.28*fade);float sheen=pow(max(0.0,1.0-abs(normalize(uEye-vWorld).z)),3.0);c+=vec3(.035)*sheen;float edge=smoothstep(uFadeStart*.74,uFadeEnd*.98,dist);c=mix(c,uFloorEdgeColor,edge*.55);outColor=vec4(c,.97);}`);
const meshLoc={mvp:gl.getUniformLocation(meshProgram,"uMVP"),model:gl.getUniformLocation(meshProgram,"uModel"),lightVP:gl.getUniformLocation(meshProgram,"uLightVP"),color:gl.getUniformLocation(meshProgram,"uColor"),eye:gl.getUniformLocation(meshProgram,"uEye"),fogColor:gl.getUniformLocation(meshProgram,"uFogColor"),fogNear:gl.getUniformLocation(meshProgram,"uFogNear"),fogFar:gl.getUniformLocation(meshProgram,"uFogFar"),metallic:gl.getUniformLocation(meshProgram,"uMetallic"),roughness:gl.getUniformLocation(meshProgram,"uRoughness"),specular:gl.getUniformLocation(meshProgram,"uSpecular"),clearcoat:gl.getUniformLocation(meshProgram,"uClearcoat"),clearcoatRoughness:gl.getUniformLocation(meshProgram,"uClearcoatRoughness"),env:gl.getUniformLocation(meshProgram,"uEnvStrength"),quality:gl.getUniformLocation(meshProgram,"uQuality"),textureScale:gl.getUniformLocation(meshProgram,"uTextureScaleMm"),textureRepeat:gl.getUniformLocation(meshProgram,"uTextureScale"),textureRotation:gl.getUniformLocation(meshProgram,"uTextureRotation"),normalStrength:gl.getUniformLocation(meshProgram,"uNormalStrength"),aoStrength:gl.getUniformLocation(meshProgram,"uAoStrength"),exposure:gl.getUniformLocation(meshProgram,"uExposure"),envRotation:gl.getUniformLocation(meshProgram,"uEnvRotation"),shadowStrength:gl.getUniformLocation(meshProgram,"uShadowStrength"),shadowTexel:gl.getUniformLocation(meshProgram,"uShadowTexel"),keyLightDir:gl.getUniformLocation(meshProgram,"uKeyLightDir"),keyLightColor:gl.getUniformLocation(meshProgram,"uKeyLightColor"),hasBase:gl.getUniformLocation(meshProgram,"uHasBaseMap"),hasNormal:gl.getUniformLocation(meshProgram,"uHasNormalMap"),hasRoughness:gl.getUniformLocation(meshProgram,"uHasRoughnessMap"),hasMetallic:gl.getUniformLocation(meshProgram,"uHasMetallicMap"),hasAo:gl.getUniformLocation(meshProgram,"uHasAoMap"),hasEnvironment:gl.getUniformLocation(meshProgram,"uHasEnvironment"),shadowEnabled:gl.getUniformLocation(meshProgram,"uShadowEnabled"),scenePresetMode:gl.getUniformLocation(meshProgram,"uScenePresetMode"),baseMap:gl.getUniformLocation(meshProgram,"uBaseMap"),normalMap:gl.getUniformLocation(meshProgram,"uNormalMap"),roughnessMap:gl.getUniformLocation(meshProgram,"uRoughnessMap"),metallicMap:gl.getUniformLocation(meshProgram,"uMetallicMap"),aoMap:gl.getUniformLocation(meshProgram,"uAoMap"),environmentMap:gl.getUniformLocation(meshProgram,"uEnvironmentMap"),shadowMap:gl.getUniformLocation(meshProgram,"uShadowMap")};
const shadowLoc={mvp:gl.getUniformLocation(shadowProgram,"uMVP")};
const lineLoc={vp:gl.getUniformLocation(lineProgram,"uVP"),color:gl.getUniformLocation(lineProgram,"uColor")};
const backgroundLoc={floorEdgeColor:gl.getUniformLocation(backgroundProgram,"uFloorEdgeColor"),backgroundTop:gl.getUniformLocation(backgroundProgram,"uBackgroundTop"),backgroundMid:gl.getUniformLocation(backgroundProgram,"uBackgroundMid"),backgroundHorizon:gl.getUniformLocation(backgroundProgram,"uBackgroundHorizon"),scenePresetMode:gl.getUniformLocation(backgroundProgram,"uScenePresetMode")};
const floorLoc={vp:gl.getUniformLocation(floorProgram,"uVP"),center:gl.getUniformLocation(floorProgram,"uCenter"),floorZ:gl.getUniformLocation(floorProgram,"uFloorZ"),size:gl.getUniformLocation(floorProgram,"uSize"),eye:gl.getUniformLocation(floorProgram,"uEye"),fogColor:gl.getUniformLocation(floorProgram,"uFogColor"),floorEdgeColor:gl.getUniformLocation(floorProgram,"uFloorEdgeColor"),floorColor:gl.getUniformLocation(floorProgram,"uFloorColor"),gridSize:gl.getUniformLocation(floorProgram,"uGridSize"),majorEvery:gl.getUniformLocation(floorProgram,"uMajorEvery"),fadeStart:gl.getUniformLocation(floorProgram,"uFadeStart"),fadeEnd:gl.getUniformLocation(floorProgram,"uFadeEnd"),gridStrength:gl.getUniformLocation(floorProgram,"uGridStrength"),ringRadius:gl.getUniformLocation(floorProgram,"uRingRadius"),scenePresetMode:gl.getUniformLocation(floorProgram,"uScenePresetMode")};
const environmentVao=gl.createVertexArray();
const gpuMeshes=DATA.meshes.map(item=>{const pos=decodeB64(item.positions,Float32Array),norm=decodeB64(item.normals,Float32Array),idx=decodeB64(item.indices,Uint32Array),vao=gl.createVertexArray();gl.bindVertexArray(vao);const pb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,pb);gl.bufferData(gl.ARRAY_BUFFER,pos,gl.STATIC_DRAW);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,0,0);const nb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,nb);gl.bufferData(gl.ARRAY_BUFFER,norm,gl.STATIC_DRAW);gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,3,gl.FLOAT,false,0,0);const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,idx,gl.STATIC_DRAW);gl.bindVertexArray(null);return{vao,count:idx.length}});
const QUALITY=String(DATA.renderProfile?.quality||"fast"),PERFECT_QUALITY=QUALITY==="perfect",QUALITY_LEVEL=PERFECT_QUALITY?2:0;
const RENDER_SCENE={scene_preset:"bright_studio",environment_map:"",environment_intensity:1.28,environment_rotation_deg:0,exposure:1.16,shadow_strength:.72,shadow_softness:1.5,directional_light_intensity:1.55,directional_light_yaw_deg:-52,directional_light_pitch_deg:54,...(DATA.renderScene||{})};
const SCENE_PRESETS={
  classic:{mode:0,backgroundTop:[.72,.75,.78],backgroundMid:[.66,.69,.72],backgroundHorizon:[.58,.61,.64],floorColor:[.48,.51,.54],floorEdgeColor:[.68,.71,.74],fogColor:[.66,.69,.72],reflectionStrength:.12,reflectionTint:[.90,.92,.94],gridStrength:.34,ringRadiusScale:2.8,exposureBias:1.08,shadowStrengthScale:.80,shadowSoftnessScale:1.25},
  bright_studio:{mode:1,backgroundTop:[.965,.968,.972],backgroundMid:[.935,.94,.945],backgroundHorizon:[.885,.89,.895],floorColor:[.86,.865,.87],floorEdgeColor:[.89,.895,.90],fogColor:[.89,.895,.90],reflectionStrength:.11,reflectionTint:[.95,.955,.96],gridStrength:.12,ringRadiusScale:2.65,exposureBias:1.16,shadowStrengthScale:.62,shadowSoftnessScale:2.1},
  automotive_interior:{mode:2,backgroundTop:[.16,.17,.18],backgroundMid:[.20,.215,.23],backgroundHorizon:[.27,.285,.30],floorColor:[.16,.17,.18],floorEdgeColor:[.25,.26,.275],fogColor:[.22,.23,.245],reflectionStrength:.055,reflectionTint:[.74,.76,.79],gridStrength:.04,ringRadiusScale:2.55,exposureBias:1.12,shadowStrengthScale:.72,shadowSoftnessScale:2.4}
};
const scenePreset=SCENE_PRESETS[String(RENDER_SCENE.scene_preset||"classic")]||SCENE_PRESETS.classic;
function directionalFromScene(scene){const yaw=Number(scene.directional_light_yaw_deg??-52)*Math.PI/180,pitch=Number(scene.directional_light_pitch_deg??54)*Math.PI/180,cp=Math.cos(pitch);return [cp*Math.cos(yaw),cp*Math.sin(yaw),Math.sin(pitch)];}
function directionalColor(scene,preset){const intensity=Math.max(0,Math.min(4,Number(scene.directional_light_intensity??1.55))),presetBoost=preset.mode===1?1.0:preset.mode===2?0.92:1.08,base=(1.75+1.55*intensity)*presetBoost;return preset.mode===2?[base*1.02,base*.99,base*.95]:preset.mode===0?[base*.98,base*.98,base*1.02]:[base,base,base*.99];}
const KEY_LIGHT_DIR=directionalFromScene(RENDER_SCENE);
const KEY_LIGHT_COLOR=directionalColor(RENDER_SCENE,scenePreset);
const ASSET_TEXTURES=(DATA.renderAssets&&DATA.renderAssets.textures)||{},ASSET_ENVIRONMENTS=(DATA.renderAssets&&DATA.renderAssets.environments)||{};
function solidTexture(r,g,b,a=255){const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array([r,g,b,a]));gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.REPEAT);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.REPEAT);return tex}
const fallbackWhite=solidTexture(255,255,255),fallbackNormal=solidTexture(128,128,255),fallbackBlack=solidTexture(0,0,0),textureCache=new Map();
function textureFromAsset(name,kind="textures"){const key=`${kind}:${name}`;if(textureCache.has(key))return textureCache.get(key);const source=(kind==="environments"?ASSET_ENVIRONMENTS:ASSET_TEXTURES)[name];const tex=solidTexture(255,255,255);textureCache.set(key,tex);if(!source)return tex;const img=new Image();img.onload=()=>{gl.bindTexture(gl.TEXTURE_2D,tex);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,img);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.REPEAT);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,kind==="environments"?gl.CLAMP_TO_EDGE:gl.REPEAT);gl.generateMipmap(gl.TEXTURE_2D)};img.onerror=()=>console.warn("VZ render texture failed",name);img.src=source;return tex}
const environmentName=String(RENDER_SCENE.environment_map||""),environmentAvailable=Boolean(environmentName&&ASSET_ENVIRONMENTS[environmentName]),environmentTexture=environmentAvailable?textureFromAsset(environmentName,"environments"):fallbackWhite;
const SHADOW_SIZE=PERFECT_QUALITY?Math.max(1024,Math.min(4096,Number(DATA.renderProfile?.shadowSize)||4096)):0;let shadowFramebuffer=null,shadowTexture=null,shadowReady=false;if(SHADOW_SIZE){shadowTexture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,shadowTexture);gl.texImage2D(gl.TEXTURE_2D,0,gl.DEPTH_COMPONENT24,SHADOW_SIZE,SHADOW_SIZE,0,gl.DEPTH_COMPONENT,gl.UNSIGNED_INT,null);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);shadowFramebuffer=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,shadowFramebuffer);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.TEXTURE_2D,shadowTexture,0);gl.drawBuffers([gl.NONE]);gl.readBuffer(gl.NONE);shadowReady=gl.checkFramebufferStatus(gl.FRAMEBUFFER)===gl.FRAMEBUFFER_COMPLETE;gl.bindFramebuffer(gl.FRAMEBUFFER,null);if(!shadowReady)console.warn("VZ perfect shadow framebuffer unavailable")}
function bindUnit(unit,texture,location){gl.activeTexture(gl.TEXTURE0+unit);gl.bindTexture(gl.TEXTURE_2D,texture);gl.uniform1i(location,unit)}
function applyMaterial(geom,reflection=false){const m=geom.material||{},baseName=String(m.base_color_map||""),normalName=String(m.normal_map||""),roughName=String(m.roughness_map||""),metalName=String(m.metallic_map||""),aoName=String(m.ao_map||"");const hasBase=Boolean(baseName&&ASSET_TEXTURES[baseName]),hasNormal=Boolean(normalName&&ASSET_TEXTURES[normalName]),hasRough=Boolean(roughName&&ASSET_TEXTURES[roughName]),hasMetal=Boolean(metalName&&ASSET_TEXTURES[metalName]),hasAo=Boolean(aoName&&ASSET_TEXTURES[aoName]);gl.uniform1f(meshLoc.metallic,Math.max(0,Math.min(1,Number(m.metallic??.15))));gl.uniform1f(meshLoc.roughness,Math.max(.045,Math.min(1,Number(m.roughness??.38))));gl.uniform1f(meshLoc.specular,Math.max(0,Math.min(1,Number(m.specular??.55))));gl.uniform1f(meshLoc.clearcoat,reflection?0:Math.max(0,Math.min(1,Number(m.clearcoat??.18))));gl.uniform1f(meshLoc.clearcoatRoughness,Math.max(.03,Math.min(1,Number(m.clearcoat_roughness??.12))));gl.uniform1f(meshLoc.env,Math.max(0,Math.min(4,Number(m.environment_strength??1)))*Math.max(0,Math.min(4,Number(RENDER_SCENE.environment_intensity??1))));gl.uniform1f(meshLoc.quality,QUALITY_LEVEL);gl.uniform1f(meshLoc.textureScale,Math.max(.1,Number(m.texture_scale_mm??120)));gl.uniform1f(meshLoc.textureRepeat,Math.max(.1,Math.min(20,Number(m.texture_scale??1))));gl.uniform1f(meshLoc.textureRotation,Number(m.texture_rotation_deg??0));gl.uniform1f(meshLoc.normalStrength,reflection?0:Math.max(0,Math.min(4,Number(m.normal_strength??1))));gl.uniform1f(meshLoc.aoStrength,Math.max(0,Math.min(4,Number(m.ao_strength??1))));gl.uniform1f(meshLoc.exposure,Math.max(.05,Math.min(8,Number(RENDER_SCENE.exposure??1)))*scenePreset.exposureBias);gl.uniform1f(meshLoc.envRotation,Number(RENDER_SCENE.environment_rotation_deg??0));gl.uniform1f(meshLoc.shadowStrength,reflection?0:Math.max(0,Math.min(1,Number(RENDER_SCENE.shadow_strength??.82)))*scenePreset.shadowStrengthScale);gl.uniform1f(meshLoc.shadowTexel,SHADOW_SIZE?Math.max(.5,Number(RENDER_SCENE.shadow_softness??1))*scenePreset.shadowSoftnessScale/SHADOW_SIZE:0);gl.uniform3fv(meshLoc.keyLightDir,KEY_LIGHT_DIR);gl.uniform3fv(meshLoc.keyLightColor,KEY_LIGHT_COLOR);gl.uniform1i(meshLoc.hasBase,hasBase?1:0);gl.uniform1i(meshLoc.hasNormal,hasNormal&&!reflection?1:0);gl.uniform1i(meshLoc.hasRoughness,hasRough?1:0);gl.uniform1i(meshLoc.hasMetallic,hasMetal?1:0);gl.uniform1i(meshLoc.hasAo,hasAo?1:0);gl.uniform1i(meshLoc.hasEnvironment,environmentAvailable?1:0);gl.uniform1i(meshLoc.shadowEnabled,shadowReady&&!reflection?1:0);gl.uniform1i(meshLoc.scenePresetMode,scenePreset.mode);bindUnit(0,hasBase?textureFromAsset(baseName):fallbackWhite,meshLoc.baseMap);bindUnit(1,hasNormal?textureFromAsset(normalName):fallbackNormal,meshLoc.normalMap);bindUnit(2,hasRough?textureFromAsset(roughName):fallbackWhite,meshLoc.roughnessMap);bindUnit(3,hasMetal?textureFromAsset(metalName):fallbackWhite,meshLoc.metallicMap);bindUnit(4,hasAo?textureFromAsset(aoName):fallbackWhite,meshLoc.aoMap);bindUnit(5,environmentTexture,meshLoc.environmentMap);bindUnit(6,shadowReady?shadowTexture:fallbackWhite,meshLoc.shadowMap)}
function createWatermarkMesh(config){if(!config||!String(config.text||"").trim())return null;const fontPx=72,pad=5,source=document.createElement("canvas"),ctx=source.getContext("2d",{willReadFrequently:true});ctx.font=`700 ${fontPx}px "Microsoft YaHei","Noto Sans CJK SC","PingFang SC",sans-serif`;source.width=Math.max(16,Math.ceil(ctx.measureText(String(config.text)).width)+pad*2);source.height=fontPx+pad*2+8;const draw=source.getContext("2d",{willReadFrequently:true});draw.clearRect(0,0,source.width,source.height);draw.fillStyle="#fff";draw.font=`700 ${fontPx}px "Microsoft YaHei","Noto Sans CJK SC","PingFang SC",sans-serif`;draw.textBaseline="top";draw.fillText(String(config.text),pad,pad);const pixels=draw.getImageData(0,0,source.width,source.height).data,solid=(x,y)=>x>=0&&y>=0&&x<source.width&&y<source.height&&pixels[(y*source.width+x)*4+3]>64;let minX=source.width,minY=source.height,maxX=-1,maxY=-1;for(let y=0;y<source.height;y++)for(let x=0;x<source.width;x++)if(solid(x,y)){minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y)}if(maxX<minX||maxY<minY)return null;const height=Math.max(Number(config.height)||.3,1e-6),thickness=Math.max(Number(config.thickness)||.01,1e-6),origin=Array.isArray(config.position)?config.position:[0,0,0],scale=height/Math.max(1,maxY-minY+1),cx=(minX+maxX+1)/2,cy=(minY+maxY+1)/2,z0=Number(origin[2])||0,z1=z0+thickness,X=x=>(Number(origin[0])||0)+(x-cx)*scale,Y=y=>(Number(origin[1])||0)+(cy-y)*scale,positions=[],normals=[],indices=[];function quad(a,b,c,d,n){const base=positions.length/3;positions.push(...a,...b,...c,...d);for(let i=0;i<4;i++)normals.push(...n);indices.push(base,base+1,base+2,base,base+2,base+3)}for(let y=minY;y<=maxY;y++){let x=minX;while(x<=maxX){while(x<=maxX&&!solid(x,y))x++;if(x>maxX)break;const start=x;while(x<=maxX&&solid(x,y))x++;const end=x;quad([X(start),Y(y+1),z1],[X(end),Y(y+1),z1],[X(end),Y(y),z1],[X(start),Y(y),z1],[0,0,1]);quad([X(start),Y(y),z0],[X(end),Y(y),z0],[X(end),Y(y+1),z0],[X(start),Y(y+1),z0],[0,0,-1])}}for(let y=minY;y<=maxY;y++)for(let x=minX;x<=maxX;x++){if(!solid(x,y))continue;if(!solid(x-1,y))quad([X(x),Y(y),z0],[X(x),Y(y+1),z0],[X(x),Y(y+1),z1],[X(x),Y(y),z1],[-1,0,0]);if(!solid(x+1,y))quad([X(x+1),Y(y+1),z0],[X(x+1),Y(y),z0],[X(x+1),Y(y),z1],[X(x+1),Y(y+1),z1],[1,0,0]);if(!solid(x,y-1))quad([X(x+1),Y(y),z0],[X(x),Y(y),z0],[X(x),Y(y),z1],[X(x+1),Y(y),z1],[0,1,0]);if(!solid(x,y+1))quad([X(x),Y(y+1),z0],[X(x+1),Y(y+1),z0],[X(x+1),Y(y+1),z1],[X(x),Y(y+1),z1],[0,-1,0])}const vao=gl.createVertexArray();gl.bindVertexArray(vao);const pb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,pb);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(positions),gl.STATIC_DRAW);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,0,0);const nb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,nb);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(normals),gl.STATIC_DRAW);gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,3,gl.FLOAT,false,0,0);const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(indices),gl.STATIC_DRAW);gl.bindVertexArray(null);return{vao,count:indices.length,color:Array.isArray(config.color)?config.color:[.18,.56,.92,1]}}
const watermarkMesh=createWatermarkMesh(DATA.watermark);
const lineVao=gl.createVertexArray(),lineBuffer=gl.createBuffer();gl.bindVertexArray(lineVao);gl.bindBuffer(gl.ARRAY_BUFFER,lineBuffer);gl.bufferData(gl.ARRAY_BUFFER,Math.max(24,DATA.pairCount*6*4),gl.DYNAMIC_DRAW);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,0,0);gl.bindVertexArray(null);
function mat4(){return new Float32Array(16)}
function multiply(o,a,b){const a00=a[0],a01=a[1],a02=a[2],a03=a[3],a10=a[4],a11=a[5],a12=a[6],a13=a[7],a20=a[8],a21=a[9],a22=a[10],a23=a[11],a30=a[12],a31=a[13],a32=a[14],a33=a[15];let b0=b[0],b1=b[1],b2=b[2],b3=b[3];o[0]=b0*a00+b1*a10+b2*a20+b3*a30;o[1]=b0*a01+b1*a11+b2*a21+b3*a31;o[2]=b0*a02+b1*a12+b2*a22+b3*a32;o[3]=b0*a03+b1*a13+b2*a23+b3*a33;b0=b[4];b1=b[5];b2=b[6];b3=b[7];o[4]=b0*a00+b1*a10+b2*a20+b3*a30;o[5]=b0*a01+b1*a11+b2*a21+b3*a31;o[6]=b0*a02+b1*a12+b2*a22+b3*a32;o[7]=b0*a03+b1*a13+b2*a23+b3*a33;b0=b[8];b1=b[9];b2=b[10];b3=b[11];o[8]=b0*a00+b1*a10+b2*a20+b3*a30;o[9]=b0*a01+b1*a11+b2*a21+b3*a31;o[10]=b0*a02+b1*a12+b2*a22+b3*a32;o[11]=b0*a03+b1*a13+b2*a23+b3*a33;b0=b[12];b1=b[13];b2=b[14];b3=b[15];o[12]=b0*a00+b1*a10+b2*a20+b3*a30;o[13]=b0*a01+b1*a11+b2*a21+b3*a31;o[14]=b0*a02+b1*a12+b2*a22+b3*a32;o[15]=b0*a03+b1*a13+b2*a23+b3*a33;return o}
function perspective(o,fovy,aspect,near,far){const f=1/Math.tan(fovy/2),nf=1/(near-far);o.fill(0);o[0]=f/aspect;o[5]=f;o[10]=(far+near)*nf;o[11]=-1;o[14]=2*far*near*nf;return o}
function orthographic(o,left,right,bottom,top,near,far){const lr=1/(left-right),bt=1/(bottom-top),nf=1/(near-far);o.fill(0);o[0]=-2*lr;o[5]=-2*bt;o[10]=2*nf;o[12]=(left+right)*lr;o[13]=(top+bottom)*bt;o[14]=(far+near)*nf;o[15]=1;return o}
function lookAt(o,eye,center,up){let zx=eye[0]-center[0],zy=eye[1]-center[1],zz=eye[2]-center[2],len=Math.hypot(zx,zy,zz)||1;zx/=len;zy/=len;zz/=len;let xx=up[1]*zz-up[2]*zy,xy=up[2]*zx-up[0]*zz,xz=up[0]*zy-up[1]*zx;len=Math.hypot(xx,xy,xz)||1;xx/=len;xy/=len;xz/=len;const yx=zy*xz-zz*xy,yy=zz*xx-zx*xz,yz=zx*xy-zy*xx;o[0]=xx;o[1]=yx;o[2]=zx;o[3]=0;o[4]=xy;o[5]=yy;o[6]=zy;o[7]=0;o[8]=xz;o[9]=yz;o[10]=zz;o[11]=0;o[12]=-(xx*eye[0]+xy*eye[1]+xz*eye[2]);o[13]=-(yx*eye[0]+yy*eye[1]+yz*eye[2]);o[14]=-(zx*eye[0]+zy*eye[1]+zz*eye[2]);o[15]=1;return o}
function fromQuatPos(o,q,p){const x=q[0],y=q[1],z=q[2],w=q[3],x2=x+x,y2=y+y,z2=z+z,xx=x*x2,xy=x*y2,xz=x*z2,yy=y*y2,yz=y*z2,zz=z*z2,wx=w*x2,wy=w*y2,wz=w*z2;o[0]=1-(yy+zz);o[1]=xy+wz;o[2]=xz-wy;o[3]=0;o[4]=xy-wz;o[5]=1-(xx+zz);o[6]=yz+wx;o[7]=0;o[8]=xz+wy;o[9]=yz-wx;o[10]=1-(xx+yy);o[11]=0;o[12]=p[0];o[13]=p[1];o[14]=p[2];o[15]=1;return o}
function transform4(m,p){const x=p[0],y=p[1],z=p[2],w=m[3]*x+m[7]*y+m[11]*z+m[15];return[(m[0]*x+m[4]*y+m[8]*z+m[12])/w,(m[1]*x+m[5]*y+m[9]*z+m[13])/w,(m[2]*x+m[6]*y+m[10]*z+m[14])/w]}
const proj=mat4(),view=mat4(),vp=mat4(),modelM=mat4(),mvp=mat4(),reflectionM=mat4(),reflectionModel=mat4(),lightProj=mat4(),lightView=mat4(),lightVP=mat4(),shadowMVP=mat4();
const initialCenter=DATA.bounds.center.slice(),center=initialCenter.slice(),radius=Math.max(DATA.bounds.radius,0.05),floorZ=initialCenter[2]-radius*1.08,environmentSize=radius*18,gridSize=Math.max(radius*.22,.02),floorEdgeColor=scenePreset.floorEdgeColor.slice(),fogColor=scenePreset.fogColor.slice(),floorColor=scenePreset.floorColor.slice();const keyLightDir=KEY_LIGHT_DIR,lightEye=[initialCenter[0]+keyLightDir[0]*radius*6,initialCenter[1]+keyLightDir[1]*radius*6,initialCenter[2]+keyLightDir[2]*radius*6];lookAt(lightView,lightEye,initialCenter,[0,0,1]);orthographic(lightProj,-radius*2.6,radius*2.6,-radius*2.6,radius*2.6,Math.max(radius*.05,.0001),radius*14);multiply(lightVP,lightProj,lightView);let yaw=-1.0,pitch=.45,distance=radius*2.8,orthographicCamera=true,playing=false,playDirection=1,current=DATA.start,lastTick=performance.now(),speed=1,adaptiveVisibility=true,showPairNames=false,showPairBorders=false,labelSmoothingReset=true;
const LABEL_SMOOTHING_RATE=7,LABEL_DEAD_ZONE_PX=4,LABEL_MAX_SPEED_PX=600,LABEL_NORMAL_OFFSET_PX=42,LABEL_POINT_SWITCH_JUMP_PX=14,LABEL_POINT_SWITCH_HOLD_MS=220,LABEL_PENDING_BLEND=.25;
function updateTransportState(){const replay=!playing&&current>=DATA.end-1e-6;playButton.classList.toggle("active",playing&&playDirection>0);reverseButton.classList.toggle("active",playing&&playDirection<0);playButton.textContent=replay?"↻":"▶";playButton.setAttribute("aria-label",replay?"重播":"正向播放");playButton.title=replay?"重播":"正向播放"}
function pausePlayback(){playing=false;updateTransportState()}
function cameraState(){const position=[center[0]+distance*Math.cos(pitch)*Math.cos(yaw),center[1]+distance*Math.cos(pitch)*Math.sin(yaw),center[2]+distance*Math.sin(pitch)],look=[center[0]-position[0],center[1]-position[1],center[2]-position[2]],n=Math.hypot(...look)||1;return{position,target:center.slice(),look_direction:look.map(v=>v/n),orthographic:Boolean(orthographicCamera)}}
function emitCameraState(){try{parent.postMessage({type:"vz-camera-state",model_id:MODEL_ID,camera:cameraState()},"*")}catch(_){}}
function applyCameraState(saved){if(!saved||!Array.isArray(saved.position)||saved.position.length!==3)return false;const target=Array.isArray(saved.target)&&saved.target.length===3?saved.target:(Array.isArray(saved.look_direction)&&saved.look_direction.length===3?saved.position.map((v,i)=>Number(v)+Number(saved.look_direction[i])):null);if(!target)return false;const position=saved.position.map(Number),aim=target.map(Number);if(!position.every(Number.isFinite)||!aim.every(Number.isFinite))return false;center.splice(0,3,...aim);const dx=position[0]-aim[0],dy=position[1]-aim[1],dz=position[2]-aim[2],d=Math.hypot(dx,dy,dz);if(!(d>1e-9))return false;distance=d;yaw=Math.atan2(dy,dx);pitch=Math.asin(Math.max(-1,Math.min(1,dz/d)));orthographicCamera=saved.orthographic!==false;$("perspectiveToggle").checked=!orthographicCamera;return true}
function setCameraPreset(name,notify=true){distance=radius*2.8;center.splice(0,3,...initialCenter);orthographicCamera=true;$("perspectiveToggle").checked=false;if(name==="front"){yaw=-Math.PI/2;pitch=0}else if(name==="side"){yaw=0;pitch=0}else if(name==="pov"){yaw=0;pitch=Math.atan2(.439,.898)}resetLabelSmoothing();if(notify)emitCameraState()}
let initialCameraApplied=false;try{const raw=QUERY.get("camera");if(raw)initialCameraApplied=applyCameraState(JSON.parse(raw))}catch(error){console.warn("初始视角解析失败",error)}if(!initialCameraApplied){const initialView=QUERY.get("view")||"front";distance=radius*2.8;center.splice(0,3,...initialCenter);orthographicCamera=true;$("perspectiveToggle").checked=false;if(initialView==="side"){yaw=0;pitch=0}else if(initialView==="pov"){yaw=0;pitch=Math.atan2(.439,.898)}else{yaw=-Math.PI/2;pitch=0}}
$("perspectiveToggle").addEventListener("change",event=>{orthographicCamera=!event.currentTarget.checked;resetLabelSmoothing();emitCameraState()});$("frontView").addEventListener("click",()=>setCameraPreset("front"));$("sideView").addEventListener("click",()=>setCameraPreset("side"));$("povView").addEventListener("click",()=>setCameraPreset("pov"));
window.addEventListener("message",event=>{if(event.data?.type==="vz-camera-request")emitCameraState();if(event.data?.type==="vz-camera-restore"&&applyCameraState(event.data.camera)){resetLabelSmoothing();emitCameraState()}});
function frameInfo(t){if(DATA.frameCount<=1)return[0,0,0];const f=Math.max(0,Math.min(DATA.frameCount-1,(t-DATA.start)*DATA.fps)),i0=Math.floor(f),i1=Math.min(DATA.frameCount-1,i0+1);return[i0,i1,f-i0]}
function nlerp(out,a,b,t){let bx=b[0],by=b[1],bz=b[2],bw=b[3];if(a[0]*bx+a[1]*by+a[2]*bz+a[3]*bw<0){bx=-bx;by=-by;bz=-bz;bw=-bw}out[0]=a[0]+(bx-a[0])*t;out[1]=a[1]+(by-a[1])*t;out[2]=a[2]+(bz-a[2])*t;out[3]=a[3]+(bw-a[3])*t;const n=Math.hypot(...out)||1;out[0]/=n;out[1]/=n;out[2]/=n;out[3]/=n;return out}
const q=[0,0,0,1],qa=[0,0,0,1],qb=[0,0,0,1],p=[0,0,0];
const pairEnabled=DATA.pairs.map(()=>true),pairLabels=[];
function resetLabelSmoothing(){labelSmoothingReset=true;pairLabels.forEach(item=>{item.screenX=NaN;item.screenY=NaN;item.normalX=NaN;item.normalY=NaN;item.rawX=NaN;item.rawY=NaN;item.pendingX=NaN;item.pendingY=NaN;item.pendingUntil=0})}
function hidePairLabel(item){item.floating.style.display="none";item.screenX=NaN;item.screenY=NaN;item.rawX=NaN;item.rawY=NaN;item.pendingX=NaN;item.pendingY=NaN;item.pendingUntil=0}
function debouncePairLabelTarget(item,targetX,targetY,now,forceReset){if(forceReset||!Number.isFinite(item.rawX)||!Number.isFinite(item.rawY)){item.rawX=targetX;item.rawY=targetY;item.pendingX=NaN;item.pendingY=NaN;item.pendingUntil=0;return[targetX,targetY]}const jump=Math.hypot(targetX-item.rawX,targetY-item.rawY);item.rawX=targetX;item.rawY=targetY;if(jump>=LABEL_POINT_SWITCH_JUMP_PX){item.pendingX=targetX;item.pendingY=targetY;item.pendingUntil=now+LABEL_POINT_SWITCH_HOLD_MS}else if(item.pendingUntil>now){item.pendingX+=((targetX-item.pendingX)*LABEL_PENDING_BLEND);item.pendingY+=((targetY-item.pendingY)*LABEL_PENDING_BLEND)}if(item.pendingUntil>now&&Number.isFinite(item.screenX)&&Number.isFinite(item.screenY))return[item.screenX,item.screenY];if(item.pendingUntil>0){const acceptedX=Number.isFinite(item.pendingX)?item.pendingX:targetX,acceptedY=Number.isFinite(item.pendingY)?item.pendingY:targetY;item.pendingUntil=0;item.pendingX=NaN;item.pendingY=NaN;return[acceptedX,acceptedY]}return[targetX,targetY]}
function updatePairLabelPosition(item,targetX,targetY,dt,forceReset){if(forceReset||!Number.isFinite(item.screenX)||!Number.isFinite(item.screenY)){item.screenX=targetX;item.screenY=targetY}else{const dx=targetX-item.screenX,dy=targetY-item.screenY,delta=Math.hypot(dx,dy);if(delta>LABEL_DEAD_ZONE_PX){const safeDt=Math.max(1/240,Math.min(dt,.1)),emaStep=delta*(1-Math.exp(-LABEL_SMOOTHING_RATE*safeDt)),step=Math.min(delta,emaStep,LABEL_MAX_SPEED_PX*safeDt);item.screenX+=dx/delta*step;item.screenY+=dy/delta*step}}item.floating.style.left=`${item.screenX}px`;item.floating.style.top=`${item.screenY}px`}
function syncSelectAllPairs(){const selectAll=$("selectAllPairs"),enabledCount=pairEnabled.filter(Boolean).length;selectAll.checked=pairEnabled.length>0&&enabledCount===pairEnabled.length;selectAll.indeterminate=enabledCount>0&&enabledCount<pairEnabled.length}
if(DATA.pairs.length===0){pairList.innerHTML='<div class="empty">当前项目没有有效测距对。</div>';$("selectAllPairs").checked=false;$("selectAllPairs").disabled=true}else DATA.pairs.forEach((pair,index)=>{const row=document.createElement("label");row.className="pair";const check=document.createElement("input");check.type="checkbox";check.checked=true;check.addEventListener("change",()=>{pairEnabled[index]=check.checked;syncSelectAllPairs()});const name=document.createElement("span");name.className="pair-name";name.textContent=pair.name;const value=document.createElement("span");value.className="pair-value";value.textContent="—";row.append(check,name,value);pairList.appendChild(row);const floating=document.createElement("div");floating.className="distance-label";floating.dataset.pairBorderColor=`rgba(${pair.color.slice(0,3).map(v=>Math.round(v*255)).join(",")},.7)`;floating.style.display="none";labelLayer.appendChild(floating);pairLabels.push({row,value,floating,check,screenX:NaN,screenY:NaN,normalX:NaN,normalY:NaN,rawX:NaN,rawY:NaN,pendingX:NaN,pendingY:NaN,pendingUntil:0})});
$("selectAllPairs").addEventListener("change",event=>{const checked=Boolean(event.target.checked);pairEnabled.fill(checked);pairLabels.forEach(item=>item.check.checked=checked);event.target.indeterminate=false});
$("adaptiveVisibility").addEventListener("change",event=>{adaptiveVisibility=Boolean(event.target.checked)});$("showPairNames").addEventListener("change",event=>{showPairNames=Boolean(event.target.checked)});$("showPairBorders").addEventListener("change",event=>{showPairBorders=Boolean(event.target.checked);pairLabels.forEach(item=>item.floating.style.borderColor=showPairBorders?item.floating.dataset.pairBorderColor:"transparent")});$("togglePanel").addEventListener("click",()=>{$("pairPanel").style.display=$("pairPanel").style.display==="none"?"block":"none"});
function setCurrent(value,stop=true){current=Math.max(DATA.start,Math.min(DATA.end,Number(value)||0));timeline.value=String(current);ganttTimeline.value=String(current);resetLabelSmoothing();if(stop)pausePlayback()}
playButton.addEventListener("click",()=>{if(playing&&playDirection>0){pausePlayback();return}if(current>=DATA.end-1e-6)setCurrent(DATA.start);playDirection=1;playing=true;lastTick=performance.now();updateTransportState()});
reverseButton.addEventListener("click",()=>{if(playing&&playDirection<0){pausePlayback();return}playDirection=-1;playing=true;lastTick=performance.now();updateTransportState()});
timeline.addEventListener("input",()=>setCurrent(timeline.value));ganttTimeline.addEventListener("input",()=>setCurrent(ganttTimeline.value));
let drag=false,dragButton=-1,lastX=0,lastY=0;function panCamera(dx,dy){const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch),right=[-sy,cy,0],up=[-sp*cy,-sp*sy,cp],scale=Math.max(radius*.00045,distance*.0011);center[0]+=(-dx*right[0]+dy*up[0])*scale;center[1]+=(-dx*right[1]+dy*up[1])*scale;center[2]+=(-dx*right[2]+dy*up[2])*scale}canvas.addEventListener("contextmenu",e=>e.preventDefault());canvas.addEventListener("pointerdown",e=>{if(e.button!==0&&e.button!==2)return;e.preventDefault();drag=true;dragButton=e.button;lastX=e.clientX;lastY=e.clientY;canvas.setPointerCapture(e.pointerId)});canvas.addEventListener("pointermove",e=>{if(!drag)return;const dx=e.clientX-lastX,dy=e.clientY-lastY;lastX=e.clientX;lastY=e.clientY;if(dragButton===2)panCamera(dx,dy);else{yaw-=dx*.006;pitch=Math.max(-1.45,Math.min(1.45,pitch+dy*.006))}});canvas.addEventListener("pointerup",()=>{drag=false;dragButton=-1;emitCameraState()});canvas.addEventListener("pointercancel",()=>{drag=false;dragButton=-1});let wheelSaveTimer=0;canvas.addEventListener("wheel",e=>{e.preventDefault();distance=Math.max(radius*.2,Math.min(radius*20,distance*Math.exp(e.deltaY*.001)));clearTimeout(wheelSaveTimer);wheelSaveTimer=setTimeout(emitCameraState,120)},{passive:false});
let pinchDistance=0;canvas.addEventListener("touchmove",e=>{if(e.touches.length===2){const dx=e.touches[0].clientX-e.touches[1].clientX,dy=e.touches[0].clientY-e.touches[1].clientY,d=Math.hypot(dx,dy);if(pinchDistance>0)distance=Math.max(radius*.2,Math.min(radius*20,distance*pinchDistance/d));pinchDistance=d;e.preventDefault()}},{passive:false});canvas.addEventListener("touchend",()=>{pinchDistance=0;emitCameraState()});
function resize(){const dpr=Math.min(devicePixelRatio||1,Number(DATA.renderProfile?.pixelRatioCap)||2),w=Math.max(1,Math.floor(canvas.clientWidth*dpr)),h=Math.max(1,Math.floor(canvas.clientHeight*dpr));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);resetLabelSmoothing()}}
function sampledDriveValue(driveIndex,t){if(driveIndex<0||driveIndex>=DATA.driveCount||driveValues.length===0)return NaN;const [i0,i1,mix]=frameInfo(t),a=driveValues[i0*DATA.driveCount+driveIndex],b=driveValues[i1*DATA.driveCount+driveIndex];if(!Number.isFinite(a))return b;if(!Number.isFinite(b))return a;return a+(b-a)*mix}
const driveStatusRows=(DATA.drives||[]).map((drive,index)=>{const row=document.createElement("div");row.className="drive-status-row";const name=document.createElement("span");name.className="drive-status-name";name.textContent=drive.name||`驱动${index+1}`;const motion=document.createElement("span");motion.className="drive-status-motion";motion.textContent="静止";const value=document.createElement("span");value.className="drive-status-value";row.append(name,motion,value);driveStatusList?.appendChild(row);return{drive,index,motion,value}});if(driveStatusList&&driveStatusRows.length===0)driveStatusList.innerHTML='<div class="empty">当前模型没有启用的驱动。</div>';
function drivePercent(drive,value){const p0=Number(drive.position0),p100=Number(drive.position100),span=p100-p0;if(!Number.isFinite(value)||!Number.isFinite(span)||Math.abs(span)<1e-12)return NaN;return Math.max(0,Math.min(100,(value-p0)/span*100))}
let lastDrivePositionEmit=0;
function emitDrivePositions(t,force=false){const now=performance.now();if(!force&&now-lastDrivePositionEmit<50)return;lastDrivePositionEmit=now;const positions={};driveStatusRows.forEach(item=>{const value=sampledDriveValue(item.index,t);if(item.drive.id&&Number.isFinite(value))positions[item.drive.id]=value});try{parent.postMessage({type:"vz-drive-positions",model_id:MODEL_ID,time:t,positions},"*")}catch(_){}}
function updateDriveStatus(t){driveStatusRows.forEach(item=>{const value=sampledDriveValue(item.index,t),unit=String(item.drive.unit||"").replace(/deg/g,"°"),active=(item.drive.segments||[]).find(seg=>t>=Number(seg.start)-1e-9&&t<Number(seg.end)-1e-9&&Number(seg.end)>Number(seg.start));item.motion.textContent=active?.name||"静止";const pct=drivePercent(item.drive,value);item.value.innerHTML=Number.isFinite(value)?`${value.toFixed(3)} ${unit}<b>${Number.isFinite(pct)?pct.toFixed(1)+"%":"—"}</b>`:"—"});emitDrivePositions(t)}
const ganttWidgets=[];let ganttAxisCursor=null;
function timeFromGanttTrack(track,clientX){const rect=track.getBoundingClientRect(),progress=Math.max(0,Math.min(1,(clientX-rect.left)/Math.max(rect.width,1)));return DATA.start+progress*(DATA.end-DATA.start)}
function enableGanttCursorDrag(cursor,track){cursor.title="拖动游标控制动画进度";cursor.addEventListener("pointerdown",event=>{if(event.button!==0)return;event.preventDefault();event.stopPropagation();pausePlayback();cursor.classList.add("dragging");cursor.setPointerCapture(event.pointerId);const apply=e=>{setCurrent(timeFromGanttTrack(track,e.clientX),true);updateGantt(current)};apply(event);const end=e=>{cursor.classList.remove("dragging");cursor.removeEventListener("pointermove",apply);cursor.removeEventListener("pointerup",end);cursor.removeEventListener("pointercancel",end);try{cursor.releasePointerCapture(e.pointerId)}catch(_){}};cursor.addEventListener("pointermove",apply);cursor.addEventListener("pointerup",end);cursor.addEventListener("pointercancel",end)})}
let imageGanttReady=false,imageGanttDragging=false;
function sampleMetadataSeries(series,t){const times=Array.isArray(series&&series.times)?series.times:[],values=Array.isArray(series&&series.values)?series.values:[],n=Math.min(times.length,values.length);if(!n)return NaN;if(t<=Number(times[0]))return Number(values[0]);if(t>=Number(times[n-1]))return Number(values[n-1]);let lo=0,hi=n-1;while(hi-lo>1){const mid=(lo+hi)>>1;if(Number(times[mid])<=t)lo=mid;else hi=mid}const t0=Number(times[lo]),t1=Number(times[hi]),v0=Number(values[lo]),v1=Number(values[hi]);if(!Number.isFinite(t0+t1+v0+v1))return NaN;const mix=t1===t0?0:(t-t0)/(t1-t0);return v0+(v1-v0)*mix}
function imageGanttLayout(){const meta=DATA.ganttMetadata||{},iw=Math.max(Number(meta.image_width)||ganttImage.naturalWidth||1,1),ih=Math.max(Number(meta.image_height)||ganttImage.naturalHeight||1,1),sw=Math.max(ganttImageStage.clientWidth,1),sh=Math.max(ganttImageStage.clientHeight,1),scale=Math.min(sw/iw,sh/ih),width=iw*scale,height=ih*scale;return{x:(sw-width)/2,y:(sh-height)/2,width,height,scale,iw,ih}}
function resizeGanttOverlay(){if(!imageGanttReady)return;const dpr=Math.min(window.devicePixelRatio||1,2),w=Math.max(1,ganttImageStage.clientWidth),h=Math.max(1,ganttImageStage.clientHeight);if(ganttOverlay.width!==Math.round(w*dpr)||ganttOverlay.height!==Math.round(h*dpr)){ganttOverlay.width=Math.round(w*dpr);ganttOverlay.height=Math.round(h*dpr)}const ctx=ganttOverlay.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0)}
function drawImageGantt(t){if(!imageGanttReady)return false;resizeGanttOverlay();const ctx=ganttOverlay.getContext("2d"),meta=DATA.ganttMetadata||{},layout=imageGanttLayout(),axisMin=Number(meta.axis_min)||0,axisMax=Number(meta.axis_max)||axisMin+1,chartLeft=Number(meta.chart_left)||0,chartRight=Number(meta.chart_right)||layout.iw,chartTop=Number(meta.chart_top)||0,chartBottom=Number(meta.chart_bottom)||layout.ih,timeOffset=Number(meta.simulation_time_offset)||0,ganttTime=t-timeOffset,ratio=Math.max(0,Math.min(1,(ganttTime-axisMin)/Math.max(axisMax-axisMin,1e-12))),x0=layout.x+chartLeft*layout.scale,x1=layout.x+chartRight*layout.scale,y0=layout.y+chartTop*layout.scale,y1=layout.y+chartBottom*layout.scale,cursorX=x0+ratio*(x1-x0);ctx.clearRect(0,0,ganttImageStage.clientWidth,ganttImageStage.clientHeight);ctx.fillStyle="rgba(56,189,248,.11)";ctx.fillRect(x0,y0,Math.max(0,cursorX-x0),Math.max(0,y1-y0));const valuePanelLeft=x1+2;ctx.fillStyle="rgba(251,252,253,.94)";ctx.fillRect(valuePanelLeft,layout.y,Math.max(0,layout.x+layout.width-valuePanelLeft),layout.height);for(const row of Array.isArray(meta.rows)?meta.rows:[]){const rowTop=layout.y+(Number(row.top)||0)*layout.scale,rowBottom=layout.y+(Number(row.bottom)||0)*layout.scale,rowCenter=layout.y+(Number(row.center)||0)*layout.scale;let active=false;for(const segment of Array.isArray(row.segments)?row.segments:[]){const start=Number(segment.start)||0,end=Number(segment.end)||0,isActive=ganttTime>=start-1e-9&&ganttTime<=end+1e-9&&end>start;if(isActive){active=true;const sx=x0+(start-axisMin)/Math.max(axisMax-axisMin,1e-12)*(x1-x0),ex=x0+(end-axisMin)/Math.max(axisMax-axisMin,1e-12)*(x1-x0);ctx.fillStyle="rgba(220,38,38,.46)";ctx.fillRect(Math.max(x0,sx),rowTop,Math.max(1,Math.min(x1,ex)-Math.max(x0,sx)),Math.max(1,rowBottom-rowTop))}}const parts=[];for(const series of Array.isArray(row.value_series)?row.value_series:[]){const value=sampleMetadataSeries(series,t);if(!Number.isFinite(value))continue;const unit=String(series.unit||"").replace(/deg/g,"°");parts.push(`${value.toFixed(3)}${unit?` ${unit}`:""}`)}if(parts.length){ctx.save();ctx.font=`${active?"700":"500"} 12px system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif`;ctx.textAlign="right";ctx.textBaseline="middle";ctx.fillStyle=active?"#dc2626":"#000000";ctx.fillText(parts.join(" / "),layout.x+layout.width-8,rowCenter);ctx.restore()}}ctx.strokeStyle="#0284c7";ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(cursorX,y0);ctx.lineTo(cursorX,y1);ctx.stroke();ctx.save();ctx.font='700 12px system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif';ctx.textAlign="right";ctx.textBaseline="bottom";ctx.fillStyle="#111827";ctx.fillText(`时间：${t.toFixed(3)}s`,layout.x+layout.width-8,layout.y+layout.height-7);ctx.restore();return true}
function setTimeFromImageGanttX(clientX){if(!imageGanttReady)return;const rect=ganttImageStage.getBoundingClientRect(),layout=imageGanttLayout(),meta=DATA.ganttMetadata||{},left=layout.x+(Number(meta.chart_left)||0)*layout.scale,right=layout.x+(Number(meta.chart_right)||layout.iw)*layout.scale,ratio=Math.max(0,Math.min(1,(clientX-rect.left-left)/Math.max(right-left,1e-12))),axisMin=Number(meta.axis_min)||0,axisMax=Number(meta.axis_max)||axisMin+1,timeOffset=Number(meta.simulation_time_offset)||0;setCurrent(axisMin+ratio*(axisMax-axisMin)+timeOffset);drawImageGantt(current)}
function buildImageGantt(){if(!DATA.ganttImage||!DATA.ganttMetadata)return false;ganttFallback.hidden=true;ganttImageStage.hidden=false;ganttImage.src=DATA.ganttImage;ganttImage.onload=()=>{imageGanttReady=true;drawImageGantt(current)};ganttImage.onerror=()=>{imageGanttReady=false;ganttImageStage.hidden=true;ganttFallback.hidden=false;buildGanttFallback()};ganttOverlay.addEventListener("pointerdown",event=>{if(event.button!==0)return;event.preventDefault();imageGanttDragging=true;ganttOverlay.setPointerCapture(event.pointerId);setTimeFromImageGanttX(event.clientX)});ganttOverlay.addEventListener("pointermove",event=>{if(imageGanttDragging)setTimeFromImageGanttX(event.clientX)});const stop=event=>{imageGanttDragging=false;try{ganttOverlay.releasePointerCapture(event.pointerId)}catch(_){}};ganttOverlay.addEventListener("pointerup",stop);ganttOverlay.addEventListener("pointercancel",stop);$("openGantt").disabled=false;return true}
function buildGanttFallback(){const chart=$("ganttChart");chart.textContent="";ganttWidgets.length=0;ganttAxisCursor=null;if(!DATA.ganttRows||DATA.ganttRows.length===0){chart.innerHTML='<div class="empty">当前导出文件没有可显示的驱动时序。</div>';$("openGantt").disabled=true;return}const duration=Math.max(DATA.end-DATA.start,1e-9),secondStep=Math.min(100,100/duration);chart.style.setProperty("--gantt-second-step",`${secondStep}%`);const axis=document.createElement("div");axis.className="gantt-axis";const axisLabel=document.createElement("div");axisLabel.className="gantt-axis-label";axisLabel.textContent="驱动";const axisTrack=document.createElement("div");axisTrack.className="gantt-axis-track";const wholeSeconds=Math.floor(duration+1e-9);for(let offset=0;offset<=wholeSeconds;offset++){const tick=document.createElement("div");tick.className="gantt-tick";tick.style.left=`${offset/duration*100}%`;const label=document.createElement("span"),tickTime=DATA.start+offset;label.textContent=`${Number.isInteger(tickTime)?tickTime.toFixed(0):tickTime.toFixed(3)} s`;tick.appendChild(label);axisTrack.appendChild(tick)}ganttAxisCursor=document.createElement("div");ganttAxisCursor.className="gantt-cursor gantt-axis-cursor";axisTrack.appendChild(ganttAxisCursor);enableGanttCursorDrag(ganttAxisCursor,axisTrack);const axisValue=document.createElement("div");axisValue.className="gantt-axis-value";axisValue.textContent="实时值";axis.append(axisLabel,axisTrack,axisValue);chart.appendChild(axis);DATA.ganttRows.forEach(row=>{const rowEl=document.createElement("div");rowEl.className="gantt-row";const rowLabel=document.createElement("div");rowLabel.className="gantt-row-label";rowLabel.textContent=row.name;rowLabel.title=row.name;const track=document.createElement("div");track.className="gantt-track";const segmentWidgets=[];(row.segments||[]).forEach(segment=>{const start=Math.max(DATA.start,Math.min(DATA.end,Number(segment.start))),end=Math.max(start,Math.min(DATA.end,Number(segment.end))),left=(start-DATA.start)/duration*100,width=Math.max(.35,(end-start)/duration*100);const el=document.createElement("div");el.className="gantt-segment";el.style.left=`${left}%`;el.style.width=`${width}%`;el.textContent=segment.name||"运动段";el.title=`${segment.name||"运动段"}\n${start.toFixed(3)} s → ${end.toFixed(3)} s`;track.appendChild(el);segmentWidgets.push({el,start,end})});const mask=document.createElement("div");mask.className="gantt-mask";const cursor=document.createElement("div");cursor.className="gantt-cursor";track.append(mask,cursor);enableGanttCursorDrag(cursor,track);const valueNumber=document.createElement("div");valueNumber.className="gantt-row-value zero";valueNumber.textContent="—";rowEl.append(rowLabel,track,valueNumber);chart.appendChild(rowEl);ganttWidgets.push({row,rowEl,mask,cursor,segmentWidgets,valueNumber})})}
function updateGantt(t){ganttTimeline.value=String(t);ganttTime.textContent=`${t.toFixed(3)} s`;if(drawImageGantt(t))return;if(!DATA.ganttRows||DATA.ganttRows.length===0)return;const duration=Math.max(DATA.end-DATA.start,1e-9),progress=Math.max(0,Math.min(1,(t-DATA.start)/duration));if(ganttAxisCursor)ganttAxisCursor.style.left=`${progress*100}%`;ganttWidgets.forEach(widget=>{widget.mask.style.width=`${progress*100}%`;widget.cursor.style.left=`${progress*100}%`;let active=false;widget.segmentWidgets.forEach(segment=>{const isActive=t>=segment.start&&t<segment.end&&segment.end>segment.start;const completed=t>segment.end;segment.el.classList.toggle("active",isActive);segment.el.classList.toggle("completed",completed&&!isActive);active=active||isActive});const value=sampledDriveValue(widget.row.driveIndex,t),unit=String(widget.row.unit||"").replace(/deg/g,"°");widget.valueNumber.textContent=Number.isFinite(value)?`${value.toFixed(3)} ${unit}`:"—";widget.valueNumber.classList.toggle("active",active);widget.valueNumber.classList.toggle("positive",!active&&Number.isFinite(value)&&value>1e-9);widget.valueNumber.classList.toggle("negative",!active&&Number.isFinite(value)&&value<-1e-9);widget.valueNumber.classList.toggle("zero",!active&&(!Number.isFinite(value)||Math.abs(value)<=1e-9))})}
let ganttWindowInitialized=false;
function appRect(){return $("app").getBoundingClientRect()}
function setGanttGeometry(left,top,width,height){const bounds=appRect(),margin=8,maxWidth=Math.max(240,bounds.width-margin*2),maxHeight=Math.max(180,bounds.height-margin*2),minWidth=Math.min(320,maxWidth),minHeight=Math.min(220,maxHeight),safeWidth=Math.max(minWidth,Math.min(maxWidth,width)),safeHeight=Math.max(minHeight,Math.min(maxHeight,height)),maxLeft=Math.max(margin,bounds.width-safeWidth-margin),maxTop=Math.max(margin,bounds.height-safeHeight-margin);ganttWindow.style.width=`${safeWidth}px`;ganttWindow.style.height=`${safeHeight}px`;ganttWindow.style.left=`${Math.max(margin,Math.min(maxLeft,left))}px`;ganttWindow.style.top=`${Math.max(margin,Math.min(maxTop,top))}px`}
function initializeGanttWindow(){if(ganttWindowInitialized)return;const bounds=appRect(),width=Math.min(900,Math.max(360,bounds.width*.72)),height=Math.min(520,Math.max(260,bounds.height*.58));setGanttGeometry(Math.max(12,(bounds.width-width)/2),Math.max(56,Math.min(92,bounds.height-height-12)),width,height);ganttWindowInitialized=true}
function constrainGanttWindow(){if(!ganttWindowInitialized)return;const rect=ganttWindow.getBoundingClientRect(),bounds=appRect();setGanttGeometry(rect.left-bounds.left,rect.top-bounds.top,rect.width,rect.height)}
function enableGanttDrag(){ganttDragHandle.addEventListener("pointerdown",event=>{if(event.button!==0||event.target.closest("button"))return;event.preventDefault();initializeGanttWindow();const bounds=appRect(),rect=ganttWindow.getBoundingClientRect(),startX=event.clientX,startY=event.clientY,startLeft=rect.left-bounds.left,startTop=rect.top-bounds.top,width=rect.width,height=rect.height;ganttDragHandle.setPointerCapture(event.pointerId);const move=e=>setGanttGeometry(startLeft+e.clientX-startX,startTop+e.clientY-startY,width,height);const end=e=>{ganttDragHandle.removeEventListener("pointermove",move);ganttDragHandle.removeEventListener("pointerup",end);ganttDragHandle.removeEventListener("pointercancel",end);try{ganttDragHandle.releasePointerCapture(e.pointerId)}catch(_){}};ganttDragHandle.addEventListener("pointermove",move);ganttDragHandle.addEventListener("pointerup",end);ganttDragHandle.addEventListener("pointercancel",end)})}
function enableGanttResize(){ganttResizeHandle.addEventListener("pointerdown",event=>{if(event.button!==0)return;event.preventDefault();event.stopPropagation();initializeGanttWindow();const bounds=appRect(),rect=ganttWindow.getBoundingClientRect(),startX=event.clientX,startY=event.clientY,startLeft=rect.left-bounds.left,startTop=rect.top-bounds.top,startWidth=rect.width,startHeight=rect.height;ganttResizeHandle.setPointerCapture(event.pointerId);const move=e=>setGanttGeometry(startLeft,startTop,startWidth+e.clientX-startX,startHeight+e.clientY-startY);const end=e=>{ganttResizeHandle.removeEventListener("pointermove",move);ganttResizeHandle.removeEventListener("pointerup",end);ganttResizeHandle.removeEventListener("pointercancel",end);try{ganttResizeHandle.releasePointerCapture(e.pointerId)}catch(_){}};ganttResizeHandle.addEventListener("pointermove",move);ganttResizeHandle.addEventListener("pointerup",end);ganttResizeHandle.addEventListener("pointercancel",end)})}
function ganttPngBlob(){if(!DATA.ganttImage)return null;const comma=DATA.ganttImage.indexOf(","),binary=atob(comma>=0?DATA.ganttImage.slice(comma+1):DATA.ganttImage),bytes=new Uint8Array(binary.length);for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);return new Blob([bytes],{type:"image/png"})}
async function animationHtmlBlob(){try{if(location.protocol==="http:"||location.protocol==="https:"){const response=await fetch(location.href,{cache:"no-store"});if(response.ok)return await response.blob()}}catch(error){console.warn("读取原始动画 HTML 失败，改用当前文档快照",error)}return new Blob(["<!doctype html>\n"+document.documentElement.outerHTML],{type:"text/html;charset=utf-8"})}
async function downloadAnimationHtml(){const safeBase=MODEL_DISPLAY_NAME.replace(/[\\/:*?"<>|]+/g,"_").replace(/^\.+|\.+$/g,"")||"模型",safeMode=RENDER_MODE_LABEL.replace(/[\\/:*?"<>|]+/g,"_")||"渲染",suggestedName=`${safeBase}_${safeMode}.html`;let handle=null;try{if(typeof window.showSaveFilePicker==="function")handle=await window.showSaveFilePicker({suggestedName,types:[{description:"VZ 离线动画 HTML",accept:{"text/html":[".html"]}}]})}catch(error){if(error&&error.name==="AbortError")return;console.warn("文件选择器不可用，改用浏览器下载",error)}const blob=await animationHtmlBlob();if(handle){const writable=await handle.createWritable();await writable.write(blob);await writable.close();return}const link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download=suggestedName;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(link.href),1200)}
$("downloadAnimation").addEventListener("click",downloadAnimationHtml);
async function exportGanttPng(){const blob=ganttPngBlob();if(!blob)return;const base=String(DATA.title||"模型").replace(/[\\/:*?"<>|]+/g,"_").replace(/^\.+|\.+$/g,"")||"模型",suggestedName=`${base}_甘特图.png`;try{if(typeof window.showSaveFilePicker==="function"){const handle=await window.showSaveFilePicker({suggestedName,types:[{description:"PNG 图片",accept:{"image/png":[".png"]}}]});const writable=await handle.createWritable();await writable.write(blob);await writable.close();return}}catch(error){if(error&&error.name==="AbortError")return;console.warn("文件选择保存失败，改用浏览器下载",error)}const link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download=suggestedName;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(link.href),1000)}
function buildGantt(){if(buildImageGantt())return;ganttImageStage.hidden=true;ganttFallback.hidden=false;buildGanttFallback()}
buildGantt();$("exportGanttPng").disabled=!DATA.ganttImage;$("exportGanttPng").addEventListener("click",exportGanttPng);enableGanttDrag();enableGanttResize();$("openGantt").addEventListener("click",()=>{ganttWindow.hidden=false;initializeGanttWindow();updateGantt(current)});$("closeGantt").addEventListener("click",()=>ganttWindow.hidden=true);document.addEventListener("keydown",event=>{if(event.key==="Escape")ganttWindow.hidden=true});window.addEventListener("resize",()=>{constrainGanttWindow();drawImageGantt(current)});
function render(now){resize();const dt=Math.min((now-lastTick)/1000,.1);lastTick=now;if(playing){current+=dt*speed*playDirection;if(current>=DATA.end&&playDirection>0){current=DATA.end;pausePlayback()}if(current<=DATA.start&&playDirection<0){current=DATA.start;pausePlayback()}timeline.value=String(current);ganttTimeline.value=String(current)}const resetLabels=labelSmoothingReset;labelSmoothingReset=false;timeText.textContent=`${current.toFixed(3)} s / ${DATA.end.toFixed(3)} s`;updateDriveStatus(current);if(!ganttWindow.hidden)updateGantt(current);const eye=[center[0]+distance*Math.cos(pitch)*Math.cos(yaw),center[1]+distance*Math.cos(pitch)*Math.sin(yaw),center[2]+distance*Math.sin(pitch)];const aspect=canvas.width/canvas.height,near=Math.max(radius*.002,.0001),far=radius*50+distance;if(orthographicCamera){const halfHeight=Math.max(radius*.08,distance*.42),halfWidth=halfHeight*aspect;orthographic(proj,-halfWidth,halfWidth,-halfHeight,halfHeight,-far,far)}else perspective(proj,45*Math.PI/180,aspect,near,far);lookAt(view,eye,center,[0,0,1]);multiply(vp,proj,view);const [i0,i1,mix]=frameInfo(current);if(shadowReady){gl.bindFramebuffer(gl.FRAMEBUFFER,shadowFramebuffer);gl.viewport(0,0,SHADOW_SIZE,SHADOW_SIZE);gl.colorMask(false,false,false,false);gl.clearDepth(1);gl.clear(gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);gl.enable(gl.CULL_FACE);gl.cullFace(gl.FRONT);gl.useProgram(shadowProgram);for(let g=0;g<DATA.geomCount;g++){const a=(i0*DATA.geomCount+g)*7,b=(i1*DATA.geomCount+g)*7;p[0]=transforms[a]+(transforms[b]-transforms[a])*mix;p[1]=transforms[a+1]+(transforms[b+1]-transforms[a+1])*mix;p[2]=transforms[a+2]+(transforms[b+2]-transforms[a+2])*mix;qa[0]=transforms[a+3];qa[1]=transforms[a+4];qa[2]=transforms[a+5];qa[3]=transforms[a+6];qb[0]=transforms[b+3];qb[1]=transforms[b+4];qb[2]=transforms[b+5];qb[3]=transforms[b+6];nlerp(q,qa,qb,mix);fromQuatPos(modelM,q,p);multiply(shadowMVP,lightVP,modelM);gl.uniformMatrix4fv(shadowLoc.mvp,false,shadowMVP);const mesh=gpuMeshes[DATA.geoms[g].mesh];gl.bindVertexArray(mesh.vao);gl.drawElements(gl.TRIANGLES,mesh.count,gl.UNSIGNED_INT,0)}gl.disable(gl.CULL_FACE);gl.colorMask(true,true,true,true);gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,canvas.width,canvas.height)}gl.clearColor(floorEdgeColor[0],floorEdgeColor[1],floorEdgeColor[2],1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.disable(gl.DEPTH_TEST);gl.disable(gl.BLEND);gl.useProgram(backgroundProgram);gl.uniform3fv(backgroundLoc.floorEdgeColor,floorEdgeColor);gl.uniform3fv(backgroundLoc.backgroundTop,scenePreset.backgroundTop);gl.uniform3fv(backgroundLoc.backgroundMid,scenePreset.backgroundMid);gl.uniform3fv(backgroundLoc.backgroundHorizon,scenePreset.backgroundHorizon);gl.uniform1i(backgroundLoc.scenePresetMode,scenePreset.mode);gl.bindVertexArray(environmentVao);gl.drawArrays(gl.TRIANGLES,0,3);gl.enable(gl.DEPTH_TEST);gl.disable(gl.CULL_FACE);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);const fogNear=Math.max(radius*4,distance*1.5),fogFar=Math.max(radius*14,distance*5);reflectionM.fill(0);reflectionM[0]=1;reflectionM[5]=1;reflectionM[10]=-1;reflectionM[14]=2*floorZ;reflectionM[15]=1;gl.useProgram(meshProgram);gl.uniformMatrix4fv(meshLoc.lightVP,false,lightVP);gl.uniform3fv(meshLoc.eye,eye);gl.uniform3fv(meshLoc.fogColor,fogColor);gl.uniform1f(meshLoc.fogNear,fogNear);gl.uniform1f(meshLoc.fogFar,fogFar);gl.depthMask(false);for(let g=0;g<DATA.geomCount;g++){const a=(i0*DATA.geomCount+g)*7,b=(i1*DATA.geomCount+g)*7;p[0]=transforms[a]+(transforms[b]-transforms[a])*mix;p[1]=transforms[a+1]+(transforms[b+1]-transforms[a+1])*mix;p[2]=transforms[a+2]+(transforms[b+2]-transforms[a+2])*mix;qa[0]=transforms[a+3];qa[1]=transforms[a+4];qa[2]=transforms[a+5];qa[3]=transforms[a+6];qb[0]=transforms[b+3];qb[1]=transforms[b+4];qb[2]=transforms[b+5];qb[3]=transforms[b+6];nlerp(q,qa,qb,mix);fromQuatPos(modelM,q,p);multiply(reflectionModel,reflectionM,modelM);multiply(mvp,vp,reflectionModel);const geom=DATA.geoms[g],color=geom.color,reflectionColor=[color[0]*scenePreset.reflectionTint[0],color[1]*scenePreset.reflectionTint[1],color[2]*scenePreset.reflectionTint[2],Math.min(scenePreset.mode===0?.2:.12,color[3]*scenePreset.reflectionStrength)];gl.uniformMatrix4fv(meshLoc.mvp,false,mvp);gl.uniformMatrix4fv(meshLoc.model,false,reflectionModel);gl.uniform4fv(meshLoc.color,reflectionColor);applyMaterial(geom,true);const mesh=gpuMeshes[geom.mesh];gl.bindVertexArray(mesh.vao);gl.drawElements(gl.TRIANGLES,mesh.count,gl.UNSIGNED_INT,0)}gl.depthMask(true);gl.useProgram(floorProgram);gl.uniformMatrix4fv(floorLoc.vp,false,vp);gl.uniform3fv(floorLoc.center,[center[0],center[1],floorZ]);gl.uniform1f(floorLoc.floorZ,floorZ);gl.uniform1f(floorLoc.size,environmentSize);gl.uniform3fv(floorLoc.eye,eye);gl.uniform3fv(floorLoc.fogColor,fogColor);gl.uniform3fv(floorLoc.floorEdgeColor,floorEdgeColor);gl.uniform3fv(floorLoc.floorColor,floorColor);gl.uniform1f(floorLoc.gridSize,gridSize);gl.uniform1f(floorLoc.majorEvery,5);gl.uniform1f(floorLoc.fadeStart,environmentSize*.32);gl.uniform1f(floorLoc.fadeEnd,environmentSize*.82);gl.uniform1f(floorLoc.gridStrength,scenePreset.gridStrength);gl.uniform1f(floorLoc.ringRadius,radius*scenePreset.ringRadiusScale);gl.uniform1i(floorLoc.scenePresetMode,scenePreset.mode);gl.bindVertexArray(environmentVao);gl.drawArrays(gl.TRIANGLES,0,6);gl.useProgram(meshProgram);gl.uniformMatrix4fv(meshLoc.lightVP,false,lightVP);gl.uniform3fv(meshLoc.eye,eye);gl.uniform3fv(meshLoc.fogColor,fogColor);gl.uniform1f(meshLoc.fogNear,fogNear);gl.uniform1f(meshLoc.fogFar,fogFar);for(let g=0;g<DATA.geomCount;g++){const a=(i0*DATA.geomCount+g)*7,b=(i1*DATA.geomCount+g)*7;p[0]=transforms[a]+(transforms[b]-transforms[a])*mix;p[1]=transforms[a+1]+(transforms[b+1]-transforms[a+1])*mix;p[2]=transforms[a+2]+(transforms[b+2]-transforms[a+2])*mix;qa[0]=transforms[a+3];qa[1]=transforms[a+4];qa[2]=transforms[a+5];qa[3]=transforms[a+6];qb[0]=transforms[b+3];qb[1]=transforms[b+4];qb[2]=transforms[b+5];qb[3]=transforms[b+6];nlerp(q,qa,qb,mix);fromQuatPos(modelM,q,p);multiply(mvp,vp,modelM);const geom=DATA.geoms[g],color=geom.color;gl.uniformMatrix4fv(meshLoc.mvp,false,mvp);gl.uniformMatrix4fv(meshLoc.model,false,modelM);gl.uniform4fv(meshLoc.color,color);applyMaterial(geom,false);gl.depthMask(color[3]>=.995);const mesh=gpuMeshes[geom.mesh];gl.bindVertexArray(mesh.vao);gl.drawElements(gl.TRIANGLES,mesh.count,gl.UNSIGNED_INT,0)}gl.depthMask(true);if(watermarkMesh){fromQuatPos(modelM,[0,0,0,1],[0,0,0]);multiply(mvp,vp,modelM);gl.uniformMatrix4fv(meshLoc.mvp,false,mvp);gl.uniformMatrix4fv(meshLoc.model,false,modelM);gl.uniform4fv(meshLoc.color,watermarkMesh.color);applyMaterial({material:{metallic:.05,roughness:.5,specular:.35,clearcoat:.1,environment_strength:1}},false);gl.bindVertexArray(watermarkMesh.vao);gl.drawElements(gl.TRIANGLES,watermarkMesh.count,gl.UNSIGNED_INT,0)}gl.useProgram(lineProgram);gl.uniformMatrix4fv(lineLoc.vp,false,vp);gl.bindVertexArray(lineVao);for(let j=0;j<DATA.pairCount;j++){const base0=(i0*DATA.pairCount+j)*7,base1=(i1*DATA.pairCount+j)*7;const dist=measurementValues[base0]+(measurementValues[base1]-measurementValues[base0])*mix,coords=[];for(let k=1;k<7;k++)coords.push(measurementValues[base0+k]+(measurementValues[base1+k]-measurementValues[base0+k])*mix);const valid=Number.isFinite(dist)&&coords.every(Number.isFinite),enabled=pairEnabled[j],withinThreshold=Number.isFinite(dist)&&dist*1000<25,visible=valid&&enabled&&(!adaptiveVisibility||withinThreshold);pairLabels[j].value.textContent=Number.isFinite(dist)?`${(dist*1000).toFixed(3)} mm`:"—";pairLabels[j].row.classList.toggle("filtered",valid&&enabled&&adaptiveVisibility&&!withinThreshold);if(!visible){hidePairLabel(pairLabels[j]);continue}const color=dist<0?[1,.25,.3,1]:DATA.pairs[j].color;gl.uniform4fv(lineLoc.color,color);gl.bindBuffer(gl.ARRAY_BUFFER,lineBuffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,new Float32Array(coords));gl.lineWidth(2);gl.drawArrays(gl.LINES,0,2);const mid=[(coords[0]+coords[3])/2,(coords[1]+coords[4])/2,(coords[2]+coords[5])/2],clip=transform4(vp,mid);if(clip[2]>=-1&&clip[2]<=1){const item=pairLabels[j],clipA=transform4(vp,[coords[0],coords[1],coords[2]]),clipB=transform4(vp,[coords[3],coords[4],coords[5]]),ax=(clipA[0]*.5+.5)*canvas.clientWidth,ay=(-clipA[1]*.5+.5)*canvas.clientHeight,bx=(clipB[0]*.5+.5)*canvas.clientWidth,by=(-clipB[1]*.5+.5)*canvas.clientHeight;let nx=-(by-ay),ny=bx-ax,nlen=Math.hypot(nx,ny);if(nlen<1e-6){nx=0;ny=-1}else{nx/=nlen;ny/=nlen}if(Number.isFinite(item.normalX)&&Number.isFinite(item.normalY)){if(nx*item.normalX+ny*item.normalY<0){nx=-nx;ny=-ny}}else if(ny>0){nx=-nx;ny=-ny}item.normalX=nx;item.normalY=ny;const targetX=(clip[0]*.5+.5)*canvas.clientWidth+nx*LABEL_NORMAL_OFFSET_PX,targetY=(-clip[1]*.5+.5)*canvas.clientHeight+ny*LABEL_NORMAL_OFFSET_PX;item.floating.style.display="block";const stableTarget=debouncePairLabelTarget(item,targetX,targetY,now,resetLabels);updatePairLabelPosition(item,stableTarget[0],stableTarget[1],dt,resetLabels);pairLabels[j].floating.textContent=showPairNames?`${DATA.pairs[j].name}: ${(dist*1000).toFixed(3)} mm`:`${(dist*1000).toFixed(3)} mm`;pairLabels[j].floating.style.color=dist<0?"#ff9da3":"#fff"}else hidePairLabel(pairLabels[j])}gl.bindVertexArray(null);loading.style.display="none";requestAnimationFrame(render)}
updateTransportState();updateDriveStatus(current);emitDrivePositions(current,true);if(QUERY.get("autoplay")==="1"&&DATA.end>DATA.start+1e-6){current=DATA.start;timeline.value=String(current);ganttTimeline.value=String(current);playDirection=1;playing=true;lastTick=performance.now();updateTransportState()}try{parent.postMessage({type:"vz-animation-ready",model_id:MODEL_ID},"*")}catch(_){}requestAnimationFrame(render);
</script>
</body>
</html>'''
    return template.replace("__TITLE__", safe_title).replace("__DATA_JSON__", data_json)

def export_interactive_animation_html(
    scene_path: str | Path,
    drives_path: str | Path,
    output_path: str | Path,
    *,
    fps: int = DEFAULT_EXPORT_FPS,
    max_faces_per_mesh: int = DEFAULT_MAX_FACES_PER_MESH,
    schedule_resolver: Callable[[Any], Any],
    offset_resolver: Callable[[Any, float], tuple[Mapping[str, float], Sequence[tuple[int, float]]]],
    qpos_resolver: Callable[[float], Any] | None = None,
    geom_to_file_builder: Callable[[Any, Mapping[str, str]], Mapping[str, Sequence[int]]],
    group_runtime_builder: Callable[..., Mapping[str, Any]],
    world_group_points: Callable[..., Any],
    progress_callback: Callable[[str, float], None] | None = None,
    gantt_snapshot_loader: Callable[[], tuple[str, dict[str, Any]]] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    measurement_pair_builder: Callable[[Any, Any, Mapping[str, Any]], Sequence[dict[str, Any]]] | None = None,
    measurement_pair_evaluator: Callable[[Any, Any, Any, dict[str, Any]], tuple[float, Any]] | None = None,
) -> dict[str, Any]:
    """Export a generated MuJoCo scene to one offline interactive HTML file."""
    import numpy as np

    try:
        import mujoco
    except Exception as exc:  # pragma: no cover - depends on delivery environment
        raise AnimationHtmlExportError(f"无法加载 MuJoCo，不能导出动画 HTML：{exc}") from exc

    scene = Path(scene_path).expanduser().resolve()
    drives_file = Path(drives_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if not scene.is_file():
        raise AnimationHtmlExportError(f"场景文件不存在：{scene}")
    if not drives_file.is_file():
        raise AnimationHtmlExportError(f"驱动配置不存在：{drives_file}")
    fps = max(1, min(int(fps), 120))
    max_faces_per_mesh = max(1_000, int(max_faces_per_mesh))

    _report(progress_callback, "读取 MuJoCo 场景", 0.02)
    payload = json.loads(drives_file.read_text(encoding="utf-8"))
    model = mujoco.MjModel.from_xml_path(str(scene))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    base_qpos = data.qpos.copy()
    drives = schedule_resolver(copy.deepcopy(payload.get("drives", [])))

    targets = []
    for drive in list(drives or []):
        joint_name = str(drive.get("joint_name", "") or "")
        if not joint_name:
            continue
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        if joint_id >= 0:
            targets.append((drive, int(model.jnt_qposadr[joint_id])))
    target_drives = [drive for drive, _qadr in targets]
    drive_records = [
        {
            "id": str(drive.get("id", "") or f"drive_{index + 1}"),
            "name": str(drive.get("name", "") or f"驱动{index + 1}"),
            "unit": _drive_display_unit(drive.get("joint_type", "")),
            "jointType": str(drive.get("joint_type", "") or ""),
            "position0": _finite_float(drive.get("position_0_percent", 0.0), 0.0),
            "position100": _finite_float(drive.get("position_100_percent", 100.0), 100.0),
            "segments": [{"name": str(seg.get("name", "") or "运动"), "start": _finite_float(seg.get("_start", 0.0), 0.0), "end": _finite_float(seg.get("_end", seg.get("_start", 0.0)), 0.0)} for seg in drive.get("segments", [])],
        }
        for index, drive in enumerate(target_drives)
    ]

    _report(progress_callback, "整理浏览器三维网格", 0.08)
    mesh_records: list[dict[str, Any]] = []
    mesh_index_by_key: dict[str, int] = {}
    geom_records: list[dict[str, Any]] = []
    geom_ids: list[int] = []
    mesh_radii: list[float] = []
    warnings: list[str] = [str(item) for item in (payload.get("render_asset_warnings") or []) if str(item)]

    render_quality = str(payload.get("render_quality", "fast") or "fast").lower()
    preview_mode = render_quality == "preview"
    fast_mode = render_quality == "fast"
    lightweight_mesh_mode = preview_mode or fast_mode
    preview_cache_hits = 0
    preview_cache_misses = 0
    render_configs = payload.get("render_configs", {}) if isinstance(payload.get("render_configs"), dict) else {}
    material_defaults = {
        "normal_mode": "crease", "crease_angle_deg": 35.0, "material": "painted_metal",
        "metallic": 0.15, "roughness": 0.38, "specular": 0.55, "clearcoat": 0.18,
        "clearcoat_roughness": 0.12, "environment_strength": 1.0,
        "base_color_map": "", "normal_map": "", "roughness_map": "", "metallic_map": "", "ao_map": "",
        "texture_scale_mm": 120.0, "texture_scale": 1.0, "texture_rotation_deg": 0.0, "normal_strength": 1.0, "ao_strength": 1.0,
    }
    for geom_id in range(int(model.ngeom)):
        rgba = [float(v) for v in np.asarray(model.geom_rgba[geom_id], dtype=float).reshape(4)]
        if rgba[3] <= 0.001:
            continue
        geom_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id) or f"geom_{geom_id}"
        material = {**material_defaults, **(render_configs.get(str(geom_name), {}) if isinstance(render_configs.get(str(geom_name), {}), dict) else {})}
        # Preview and Fast Render are both interactive feedback paths. Use the
        # vectorized smooth-normal path so the engineer-side fast export has the
        # same low-latency geometry preparation behavior as the client preview.
        normal_mode = "smooth" if lightweight_mesh_mode else str(material.get("normal_mode", "crease"))
        crease_angle = _finite_float(material.get("crease_angle_deg", 35.0), 35.0)
        key, vertices, faces, simplified = _mesh_from_geom(model, geom_id, mujoco, max_faces_per_mesh)
        if len(vertices) == 0 or len(faces) == 0:
            continue
        keyed = f"{key}|{normal_mode}|{crease_angle:.4f}"
        if keyed not in mesh_index_by_key:
            cached_record = None
            cache_key = ""
            if lightweight_mesh_mode:
                cache_key = _preview_mesh_cache_key(vertices, faces)
                cached_record = _preview_mesh_cache_get(cache_key)
            if cached_record is not None:
                preview_cache_hits += 1
                mesh_record = cached_record
            else:
                if lightweight_mesh_mode:
                    preview_cache_misses += 1
                if normal_mode == "smooth":
                    normals = _compute_vertex_normals(vertices, faces)
                else:
                    vertices, normals, faces = _compute_creased_mesh(vertices, faces, crease_angle, flat=normal_mode == "flat")
                vertices = np.asarray(vertices, dtype=np.float32)
                normals = np.asarray(normals, dtype=np.float32)
                faces = np.asarray(faces, dtype=np.uint32)
                radius = float(np.max(np.linalg.norm(vertices, axis=1))) if len(vertices) else 0.01
                mesh_record = {
                    "positions": _b64_f32(vertices),
                    "normals": _b64_f32(normals),
                    "indices": _b64_u32(faces),
                    "vertexCount": int(len(vertices)),
                    "faceCount": int(len(faces)),
                    "radius": radius,
                    "normalMode": normal_mode,
                    "creaseAngleDeg": crease_angle,
                }
                if lightweight_mesh_mode and cache_key:
                    _preview_mesh_cache_put(cache_key, mesh_record)
            mesh_index_by_key[keyed] = len(mesh_records)
            mesh_records.append(mesh_record)
            if simplified:
                warnings.append(f"网格 {key} 已自动简化为 {int(mesh_record['faceCount'])} 个三角面")
        mesh_index = mesh_index_by_key[keyed]
        geom_records.append({"name": str(geom_name), "mesh": int(mesh_index), "color": rgba, "material": material})
        geom_ids.append(int(geom_id))
        is_plane = int(model.geom_type[geom_id]) == int(mujoco.mjtGeom.mjGEOM_PLANE)
        mesh_radii.append(0.0 if is_plane else float(mesh_records[mesh_index]["radius"]))

    if not geom_records:
        raise AnimationHtmlExportError("场景中没有可导出的可见几何体。")

    start_time = float(payload.get("sim_start_time", 0.0) or 0.0)
    end_time = float(payload.get("sim_end_time", start_time) or start_time)
    if end_time < start_time:
        start_time, end_time = end_time, start_time
    duration = max(0.0, end_time - start_time)
    requested_fps = int(fps)
    if duration > 0.0 and int(math.ceil(duration * fps - 1e-9)) + 1 > MAX_EXPORT_FRAMES:
        fps = max(1, int(math.floor((MAX_EXPORT_FRAMES - 1) / duration)))
        warnings.append(f"动画时长较长，导出帧率已从 {requested_fps} FPS 自动调整为 {fps} FPS")
    frame_count = max(1, int(math.ceil(duration * fps - 1e-9)) + 1)
    times = np.linspace(start_time, end_time, frame_count, dtype=np.float64) if frame_count > 1 else np.asarray([start_time], dtype=np.float64)

    _report(progress_callback, "准备测距对采样", 0.14)
    pair_records: list[dict[str, Any]] = []
    pair_runtimes: list[dict[str, Any]] = []
    geom_to_file = geom_to_file_builder(model, payload.get("mesh_manifest", {}) or {})
    palette = [
        [0.20, 0.72, 1.00, 1.0], [1.00, 0.72, 0.18, 1.0], [0.40, 0.90, 0.45, 1.0],
        [0.92, 0.42, 1.00, 1.0], [1.00, 0.42, 0.42, 1.0], [0.22, 0.92, 0.88, 1.0],
    ]
    global_strategy = bool(payload.get("single_distance_strategy_enabled", True))
    global_precise = bool(payload.get("single_distance_precise_enabled", True))
    global_negative = bool(payload.get("single_distance_interference_enabled", False))

    if measurement_pair_builder is not None and measurement_pair_evaluator is not None:
        built_pairs = list(measurement_pair_builder(mujoco, model, payload) or [])
        for pair_runtime in built_pairs:
            if not pair_runtime.get("group_a") or not pair_runtime.get("group_b"):
                continue
            name = str(pair_runtime.get("name", "") or "").strip() or f"测距对{len(pair_records) + 1}"
            pair_records.append({"name": name, "color": palette[len(pair_records) % len(palette)]})
            pair_runtimes.append(dict(pair_runtime))
    else:
        for pair in list(payload.get("pairs", []) or []):
            name = str(pair.get("name", "") or "").strip() or f"测距对{len(pair_records) + 1}"
            strategy_mode = pair.get("strategy_density_mode", pair.get("density_mode", "spacing_mm"))
            strategy_value = pair.get("strategy_density_value", pair.get("density_value", "5"))
            precise_mode = pair.get("precise_density_mode", pair.get("density_mode", "spacing_mm"))
            precise_value = pair.get("precise_density_value", pair.get("density_value", "5"))
            precise_enabled = bool(pair.get("precise_enabled", False)) and global_precise
            group_a = group_runtime_builder(
                pair.get("objects_a", []), geom_to_file, model,
                strategy_mode, strategy_value, precise_mode, precise_value, precise_enabled,
            )
            group_b = group_runtime_builder(
                pair.get("objects_b", []), geom_to_file, model,
                strategy_mode, strategy_value, precise_mode, precise_value, precise_enabled,
            )
            if not group_a.get("items") or not group_b.get("items"):
                warnings.append(f"测距对“{name}”未找到有效几何体，已跳过")
                continue
            pair_records.append({"name": name, "color": palette[len(pair_records) % len(palette)]})
            pair_runtimes.append(
                {
                    "name": name,
                    "group_a": group_a,
                    "group_b": group_b,
                    "precise_enabled": precise_enabled,
                    "distmax": float(pair.get("distmax", 0.1) or 0.1),
                }
            )

    transforms = np.empty((frame_count, len(geom_ids), 7), dtype=np.float32)
    measurements = np.full((frame_count, len(pair_runtimes), 7), np.nan, dtype=np.float32)
    drive_values = np.full((frame_count, len(target_drives)), np.nan, dtype=np.float32)
    previous_quaternions: list[np.ndarray | None] = [None] * len(geom_ids)

    _report(progress_callback, "自动采样动画与测距", 0.17)
    for frame_index, time_value in enumerate(times):
        if should_cancel is not None and should_cancel():
            raise InterruptedError("动画 HTML 导出已取消")
        sampled_drive_values, offsets = offset_resolver(targets, float(time_value))
        for drive_index, drive in enumerate(target_drives):
            drive_name = str(drive.get("name", "") or "")
            raw_value = sampled_drive_values.get(drive_name, float("nan"))
            drive_values[frame_index, drive_index] = _drive_value_to_display(drive.get("joint_type", ""), raw_value)
        if qpos_resolver is not None:
            resolved_qpos = np.asarray(qpos_resolver(float(time_value)), dtype=float).reshape(-1)
            if resolved_qpos.shape != (int(model.nq),):
                raise AnimationHtmlExportError(
                    f"动画轨迹 qpos 与当前模型 nq 不一致：trajectory={resolved_qpos.shape}, model=({int(model.nq)},)"
                )
            data.qpos[:] = resolved_qpos
        else:
            data.qpos[:] = base_qpos
            for qpos_address, offset in offsets:
                data.qpos[int(qpos_address)] = base_qpos[int(qpos_address)] + float(offset)
        mujoco.mj_forward(model, data)

        for local_index, geom_id in enumerate(geom_ids):
            pos = np.asarray(data.geom_xpos[geom_id], dtype=float).reshape(3)
            quat = np.asarray(_matrix_to_quaternion_xyzw(data.geom_xmat[geom_id]), dtype=float)
            previous = previous_quaternions[local_index]
            if previous is not None and float(np.dot(previous, quat)) < 0.0:
                quat = -quat
            previous_quaternions[local_index] = quat
            transforms[frame_index, local_index, :3] = pos
            transforms[frame_index, local_index, 3:] = quat

        for pair_index, pair_runtime in enumerate(pair_runtimes):
            if measurement_pair_evaluator is not None:
                distance, line = measurement_pair_evaluator(mujoco, model, data, pair_runtime)
                if not math.isfinite(float(distance)) or line is None:
                    continue
            else:
                native_distance, native_line = _native_pair_distance(
                    mujoco, model, data,
                    pair_runtime["group_a"], pair_runtime["group_b"], pair_runtime["distmax"],
                )
                use_precise = bool(pair_runtime.get("precise_enabled", False))
                points_a = world_group_points(pair_runtime["group_a"], data, use_precise=use_precise)
                points_b = world_group_points(pair_runtime["group_b"], data, use_precise=use_precise)
                point_distance, point_line = _nearest_points(points_a, points_b) if global_strategy or use_precise else (float("inf"), None)

                if global_negative and math.isfinite(native_distance) and native_distance < 0.0 and native_line is not None:
                    distance, line = native_distance, native_line
                elif math.isfinite(point_distance) and point_line is not None:
                    distance, line = point_distance, point_line
                elif math.isfinite(native_distance) and native_line is not None:
                    # Unsigned mode must remain non-negative even when surface
                    # sampling is unavailable and native MuJoCo reports overlap.
                    distance, line = max(native_distance, 0.0), native_line
                else:
                    continue
            measurements[frame_index, pair_index, 0] = float(distance)
            measurements[frame_index, pair_index, 1:] = np.asarray(line, dtype=np.float32)

        if frame_index == 0 or frame_index == frame_count - 1 or frame_index % max(1, frame_count // 80) == 0:
            fraction = 0.17 + 0.70 * ((frame_index + 1) / frame_count)
            _report(progress_callback, f"采样动画 {frame_index + 1}/{frame_count} 帧", fraction)

    first_positions = transforms[0, :, :3].astype(float)
    center = np.mean(first_positions, axis=0) if len(first_positions) else np.zeros(3, dtype=float)
    scene_radius = 0.05
    for position, local_radius in zip(first_positions, mesh_radii):
        scene_radius = max(scene_radius, float(np.linalg.norm(position - center)) + float(local_radius))
    if not math.isfinite(scene_radius) or scene_radius <= 0:
        scene_radius = max(float(getattr(model.stat, "extent", 1.0)), 1.0)

    gantt_rows = _build_gantt_rows(target_drives, start_time, end_time)
    gantt_image, gantt_metadata = (
        gantt_snapshot_loader() if gantt_snapshot_loader is not None
        else _load_latest_qt_gantt_snapshot()
    )
    if not gantt_image:
        warnings.append("未找到最新 Qt 甘特图 PNG 缓存，HTML 将使用兼容时序图。")
    # The default watermark must match the actual plane material exported to
    # WebGL, not a stale hard-coded preference.  This also preserves a custom
    # user color when one was explicitly stored in the payload.
    floor_color = "#B3B3B3"
    try:
        plane_index = next(
            index for index, geom_id in enumerate(geom_ids)
            if int(model.geom_type[geom_id]) == int(mujoco.mjtGeom.mjGEOM_PLANE)
        )
        rgba = geom_records[plane_index]["color"]
        floor_color = "#" + "".join(
            f"{max(0, min(255, int(round(float(channel) * 255)))):02X}"
            for channel in rgba[:3]
        )
    except (StopIteration, KeyError, TypeError, ValueError, IndexError):
        pass
    render_scene = payload.get("render_scene", {}) if isinstance(payload.get("render_scene"), dict) else {}
    watermark_default_color = "#8F969E" if str(render_scene.get("scene_preset", "classic") or "classic") in {"bright_studio", "automotive_interior"} else floor_color
    watermark = _animation_watermark_config(payload, default_color=watermark_default_color)

    _report(progress_callback, "生成离线 WebGL 播放器", 0.91)
    export_payload = {
        "version": V21_EXPORT_VERSION,
        "title": destination.stem,
        "modelName": str(payload.get("model_name", "") or destination.stem),
        "start": float(start_time),
        "end": float(end_time),
        "fps": int(fps),
        "frameCount": int(frame_count),
        "geomCount": int(len(geom_records)),
        "pairCount": int(len(pair_records)),
        "driveCount": int(len(drive_records)),
        "times": _b64_f32(times),
        "transforms": _b64_f32(transforms),
        "measurements": _b64_f32(measurements),
        "driveValues": _b64_f32(drive_values),
        "meshes": mesh_records,
        "geoms": geom_records,
        "pairs": pair_records,
        "drives": drive_records,
        "ganttRows": gantt_rows,
        "ganttImage": gantt_image,
        "ganttMetadata": gantt_metadata,
        "watermark": watermark,
        "renderAssets": payload.get("render_assets", {}) if isinstance(payload.get("render_assets"), dict) else {},
        "renderScene": payload.get("render_scene", {}) if isinstance(payload.get("render_scene"), dict) else {},
        "renderProfile": {
            "quality": render_quality,
            "label": "高质量渲染" if render_quality == "perfect" else "快速渲染",
            "pixelRatioCap": 1.35 if preview_mode else 1.5 if fast_mode else 2.0 if render_quality == "perfect" else 1.5,
            "shadowSize": 2048 if render_quality == "perfect" else 0,
        },
        "bounds": {"center": [float(v) for v in center], "radius": float(scene_radius)},
        "warnings": warnings,
        "previewCache": {"hits": int(preview_cache_hits), "misses": int(preview_cache_misses)} if preview_mode else {},
    }
    html_text = _build_html_document(destination.stem, export_payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html_text, encoding="utf-8")
    _report(progress_callback, "动画 HTML 导出完成", 1.0)

    return {
        "path": str(destination),
        "frame_count": int(frame_count),
        "geom_count": int(len(geom_records)),
        "pair_count": int(len(pair_records)),
        "drive_count": int(len(drive_records)),
        "mesh_count": int(len(mesh_records)),
        "file_size": int(destination.stat().st_size),
        "warnings": warnings,
        "preview_cache_hits": int(preview_cache_hits),
        "preview_cache_misses": int(preview_cache_misses),
    }
