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
fallback. The V2.16.8 offline player uses shared Viewer-green measurement
segments and a predictable four-device-pixel WebGL2 triangle strip.
"""
from __future__ import annotations

import base64
import copy
import html
import json
import math
import os
import threading
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .viewer_runner import (
    _DISTANCE_LINE_RGBA_NORMAL, _nearest_points, load_mujoco_model, _clone_distance_pair,
)
from .parallel_sampling import FRAME_BATCH_SIZE, frame_worker_count, iter_frame_batches


V21_EXPORT_VERSION = "21.4.4.3.3"
DEFAULT_EXPORT_FPS = 20
DEFAULT_MAX_FACES_PER_MESH = 120_000
MAX_EXPORT_FRAMES = 2_400


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
:root{color-scheme:dark;--bg:#0d1117;--panel:rgba(18,24,34,.94);--panel2:#111823;--line:#2b3442;--text:#edf2f8;--muted:#aab5c3;--accent:#4da3ff;--accent-soft:rgba(77,163,255,.24);--danger:#ff5f68;--active:#ffb454;--positive:#4ed6b3}*{box-sizing:border-box}html,body{width:100%;height:100%;margin:0;overflow:hidden;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}button,select,input{font:inherit}[hidden]{display:none!important}.app{position:relative;width:100%;height:100%}canvas{display:block;width:100%;height:100%;touch-action:none;background:radial-gradient(circle at 50% 35%,#202a38 0,#0d1117 70%)}.topbar{position:absolute;left:12px;right:12px;top:12px;display:flex;align-items:flex-start;gap:10px;pointer-events:none}.titlebox{pointer-events:auto;background:rgba(18,24,34,.2);border:1px solid var(--line);border-radius:6px;padding:4px 6px;backdrop-filter:blur(8px);max-width:min(24vw,310px)}.title{font-size:8px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.subtitle{font-size:6px;color:var(--muted);margin-top:1px}.top-actions{margin-left:auto;display:flex;flex-wrap:wrap;justify-content:flex-end;gap:7px;pointer-events:auto;max-width:58vw}.btn{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:10px;padding:8px 11px;cursor:pointer;white-space:nowrap}.btn:hover{border-color:var(--accent)}.btn.active{border-color:var(--accent);background:var(--accent-soft)}.btn:disabled{cursor:not-allowed;opacity:.45}.panel{position:absolute;right:12px;top:106px;width:min(340px,calc(100vw - 24px));max-height:calc(100vh - 210px);overflow:auto;background:rgba(18,24,34,.2);border:1px solid var(--line);border-radius:12px;padding:12px;backdrop-filter:blur(8px);color:var(--text)}.panel-head{display:flex;align-items:flex-start;gap:10px;justify-content:space-between;margin-bottom:6px}.panel-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 8px;align-items:center;min-width:150px}.panel-options .adaptive{justify-content:flex-start;text-align:left;white-space:nowrap}.panel h2{font-size:12px;margin:2px 0 0}.adaptive{display:flex;gap:6px;align-items:center;font-size:10px;color:var(--muted);cursor:pointer;text-align:right}.adaptive input,.pair input{accent-color:var(--accent)}.pair{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:8px;align-items:center;padding:7px 0;border-top:1px solid rgba(255,255,255,.07)}.pair:first-of-type{border-top:0}.pair.filtered{opacity:.45}.pair-name{font-size:11px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pair-value{font-variant-numeric:tabular-nums;font-size:10px;color:var(--muted)}.empty{font-size:11px;color:var(--muted);padding:8px 0}.controls{position:absolute;left:12px;right:12px;bottom:12px;background:rgba(18,24,34,.1);border:1px solid var(--line);border-radius:10px;padding:5px 8px;backdrop-filter:blur(9px)}.transport{display:grid;grid-template-columns:auto minmax(84px,1fr) auto auto;gap:7px;align-items:center}.transport-buttons{display:flex;gap:3px}.transport-button{min-width:28px;height:24px;padding:0 5px;font-size:10px}.timeline{width:100%;height:12px;accent-color:var(--accent)}.time{font-variant-numeric:tabular-nums;font-size:9px;white-space:nowrap}.speed{border:1px solid var(--line);background:var(--panel2);color:var(--text);border-radius:6px;padding:3px 4px;font-size:9px}.hint{font-size:8px;color:var(--muted);margin-top:3px;line-height:1.1}.developer-support{font-size:5px;color:var(--muted);margin-top:1px;text-align:right;line-height:1.1}.label-layer{position:absolute;inset:0;pointer-events:none;overflow:hidden}.distance-label{position:absolute;transform:translate(-50%,-50%);padding:3px 6px;border-radius:6px;background:transparent;text-shadow:0 1px 2px rgba(0,0,0,.85);font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}.warning{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);max-width:620px;padding:18px;background:#291f22;border:1px solid #704148;border-radius:12px;color:#ffd9dc;display:none}.loading{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);padding:14px 18px;background:var(--panel);border:1px solid var(--line);border-radius:12px;color:var(--muted)}
.gantt-window{position:absolute;z-index:20;left:24px;top:84px;width:900px;height:506px;min-width:320px;min-height:72px;display:flex;flex-direction:column;background:rgba(15,21,31,.97);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 18px 48px rgba(0,0,0,.42);backdrop-filter:blur(8px)}.gantt-header{display:flex;align-items:center;gap:10px;height:42px;padding:6px 8px 6px 12px;border-bottom:1px solid var(--line);cursor:move;touch-action:none;user-select:none}.gantt-header h2{font-size:14px;margin:0}.gantt-close{margin-left:auto;padding:5px 9px}.gantt-body{min-height:0;flex:1;overflow:hidden}.gantt-scroll{overflow-y:auto;overflow-x:hidden;width:100%;height:100%;padding:8px}.gantt-chart{--gantt-second-step:10%;width:100%;min-width:0}.gantt-axis,.gantt-row{display:grid;grid-template-columns:minmax(84px,22%) minmax(80px,1fr) minmax(78px,20%);align-items:stretch;width:100%;min-width:0}.gantt-axis-label,.gantt-row-label,.gantt-axis-value,.gantt-row-value{border-bottom:1px solid rgba(255,255,255,.07);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}.gantt-axis-label,.gantt-row-label{padding:0 10px;border-right:1px solid var(--line);display:flex;align-items:center}.gantt-axis-label,.gantt-axis-value{height:34px;color:var(--muted)}.gantt-axis-value,.gantt-row-value{padding:0 10px;border-left:1px solid var(--line);display:flex;align-items:center;justify-content:flex-end;font-variant-numeric:tabular-nums}.gantt-axis-track{height:34px;position:relative;border-bottom:1px solid var(--line);background-image:linear-gradient(to right,rgba(255,255,255,.10) 1px,transparent 1px);background-size:var(--gantt-second-step) 100%;min-width:0;overflow:visible}.gantt-tick{position:absolute;top:0;bottom:0;border-left:1px solid rgba(255,255,255,.18);pointer-events:none}.gantt-tick span{position:absolute;top:5px;left:5px;font-size:11px;color:var(--muted);white-space:nowrap}.gantt-row-label,.gantt-track,.gantt-row-value{height:44px}.gantt-track{position:relative;border-bottom:1px solid rgba(255,255,255,.07);background-color:rgba(255,255,255,.012);background-image:linear-gradient(to right,rgba(255,255,255,.07) 1px,transparent 1px);background-size:var(--gantt-second-step) 100%;min-width:0;overflow:visible}.gantt-segment{position:absolute;top:9px;height:26px;border-radius:6px;background:#6d7888;border:1px solid rgba(255,255,255,.22);padding:4px 7px;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;z-index:2;transition:background .12s,border-color .12s,filter .12s}.gantt-segment.completed{filter:saturate(.8);background:#496b91}.gantt-segment.active{background:var(--active);border-color:#ffd291;color:#1f1608;font-weight:650}.gantt-mask{position:absolute;left:0;top:0;bottom:0;width:0;background:rgba(50,139,255,.17);z-index:3;pointer-events:none}.gantt-cursor{position:absolute;top:0;bottom:0;width:16px;transform:translateX(-8px);background:transparent;z-index:5;cursor:ew-resize;touch-action:none;pointer-events:auto}.gantt-cursor::before{content:"";position:absolute;left:7px;top:0;bottom:0;width:2px;background:#64b5ff;box-shadow:0 0 0 1px rgba(0,0,0,.25)}.gantt-cursor:hover::before,.gantt-cursor.dragging::before{width:3px;left:6.5px;background:#9bd2ff}.gantt-axis-cursor{z-index:6}.gantt-row-value.active{color:var(--active);font-weight:650}.gantt-row-value.positive:not(.active){color:var(--positive)}.gantt-row-value.negative:not(.active){color:#ff858d}.gantt-row-value.zero{color:var(--muted)}.gantt-footer{height:44px;border-top:1px solid var(--line);padding:7px 12px;display:grid;grid-template-columns:minmax(120px,1fr) auto;gap:10px;align-items:center}.gantt-footer input{width:100%;accent-color:var(--accent)}.gantt-time{font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}.gantt-resize{position:absolute;right:0;bottom:0;width:22px;height:22px;cursor:nwse-resize;touch-action:none}.gantt-resize::before,.gantt-resize::after{content:"";position:absolute;right:4px;bottom:4px;border-right:2px solid rgba(255,255,255,.55);border-bottom:2px solid rgba(255,255,255,.55)}.gantt-resize::before{width:12px;height:12px}.gantt-resize::after{width:6px;height:6px}
@media(max-width:900px){.topbar{align-items:flex-start}.titlebox{max-width:42vw}.top-actions{max-width:58vw}.top-actions .btn{padding:7px 8px;font-size:12px}.panel{top:122px}.gantt-axis,.gantt-row{grid-template-columns:minmax(76px,24%) minmax(70px,1fr) minmax(72px,22%)}}@media(max-width:720px){.titlebox{max-width:52vw}.subtitle{display:none}.top-actions{max-width:48vw}.top-actions .view-secondary{display:none}.panel{top:102px;max-height:38vh;width:245px}.controls{padding:4px 6px}.transport{grid-template-columns:1fr}.transport-buttons{justify-content:center}.time{text-align:center}.speed{display:none}.hint{display:none}.gantt-axis,.gantt-row{grid-template-columns:minmax(68px,26%) minmax(60px,1fr) minmax(66px,24%)}.gantt-axis-label,.gantt-row-label,.gantt-axis-value,.gantt-row-value{font-size:11px;padding-left:6px;padding-right:6px}.gantt-footer{grid-template-columns:1fr}.gantt-time{text-align:center;display:none}}
.gantt-image-stage{position:relative;width:100%;height:100%;overflow:hidden;background:#fbfcfd;touch-action:none;cursor:ew-resize}.gantt-image-stage img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;user-select:none;pointer-events:none}.gantt-image-stage canvas{position:absolute;inset:0;width:100%;height:100%;background:transparent;touch-action:none}.gantt-fallback{width:100%;height:100%}
/* V2.15.7: keep the measurement and current-motor panels in one vertical flow.
   Both use the existing measurement-panel visual language, rather than
   independently positioned overlays that obscure one another. */
.right-info-stack{position:absolute;z-index:7;top:106px;right:12px;bottom:104px;width:min(340px,calc(100vw - 24px));display:flex;flex-direction:column;gap:9px;pointer-events:none}
.right-info-stack > .panel,.right-info-stack > .lab-live-telemetry{position:relative;top:auto;right:auto;width:100%;min-height:0;overflow:auto;background:rgba(12,16,22,.72);border:1px solid var(--line);border-radius:12px;padding:12px;backdrop-filter:blur(8px);color:var(--text);pointer-events:auto}
.right-info-stack > .panel{flex:0 1 auto;max-height:none}
.right-info-stack > .lab-live-telemetry{flex:0 0 auto;max-height:min(31vh,260px);font:11px/1.4 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;font-variant-numeric:tabular-nums}
.lab-live-telemetry strong{color:var(--text);font-size:11px;font-weight:650;letter-spacing:.02em}
.lab-live-time{font-weight:650;color:var(--muted);margin:4px 0 6px;font-size:13px}
.lab-live-line{display:flex;gap:9px;justify-content:space-between;padding:4px 0;border-top:1px solid rgba(255,255,255,.07)}
.lab-live-line span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)}
.lab-live-line b{flex-shrink:0;font-size:10px;font-variant-numeric:tabular-nums;color:var(--text)}
@media(max-width:900px){.right-info-stack{top:122px}}
@media(max-width:720px){.right-info-stack{top:102px;right:12px;bottom:112px;width:min(245px,calc(100vw - 24px))}.right-info-stack > .lab-live-telemetry{max-height:min(28vh,220px)}}
/* Embedded Lab player: preserve the existing compact hover/focus button.
   The stack has no box in this mode, so its anchored info button stays in the app. */
.lab-contained .right-info-stack{display:contents}
/* Standalone exported animations retain the visible, stacked panels. */
.lab-contained .topbar{pointer-events:auto;min-height:34px;z-index:7}
.lab-contained .topbar .titlebox{display:none!important}
.lab-contained #pairPanel{display:none}
.lab-contained .controls .hint,.lab-contained .controls .developer-support{display:none!important}
.lab-contained .topbar .top-actions{opacity:0;pointer-events:none;transition:opacity .15s}
.lab-contained .topbar:hover .top-actions,.lab-contained .topbar:focus-within .top-actions{opacity:1;pointer-events:auto}
.lab-contained .lab-live-telemetry{position:absolute;top:9px;right:9px;width:29px;height:28px;padding:0;overflow:hidden;pointer-events:auto;cursor:help;border-radius:6px;z-index:8;background:rgba(11,29,42,.82)}
.lab-contained .lab-live-telemetry::before{content:"i";position:absolute;top:2px;left:0;right:0;text-align:center;font:700 16px/23px system-ui;color:#8ae3df}
.lab-contained .lab-live-telemetry>*{visibility:hidden}
.lab-contained .lab-live-telemetry:hover,.lab-contained .lab-live-telemetry:focus-visible,.lab-contained .lab-live-telemetry:focus-within{width:min(265px,48vw);height:auto;max-height:55vh;padding:12px 14px;overflow:auto}
.lab-contained .lab-live-telemetry:hover::before,.lab-contained .lab-live-telemetry:focus-visible::before,.lab-contained .lab-live-telemetry:focus-within::before{display:none}
.lab-contained .lab-live-telemetry:hover>*,.lab-contained .lab-live-telemetry:focus-visible>*,.lab-contained .lab-live-telemetry:focus-within>*{visibility:visible}
@media(prefers-reduced-motion:reduce){.lab-contained .topbar .top-actions{transition:none}}
/* Keep the no-cache HTML renderer visually aligned with Qt's light gantt scene. */
.gantt-window{background:#eef1f5;color:#2b353c;border-color:#c8d1d9}.gantt-header{background:#017a81;color:#fff;border-bottom-color:#018c94}.gantt-header h2{color:#fff}.gantt-body,.gantt-scroll{background:#fbfcfd}.gantt-axis-label,.gantt-row-label,.gantt-axis-value,.gantt-row-value{color:#2b353c;border-color:#e4e9ee}.gantt-axis-label,.gantt-row-label{background:#fff}.gantt-axis-value,.gantt-row-value{background:#fff}.gantt-axis-track,.gantt-track{background-color:#fbfcfd;background-image:linear-gradient(to right,#e7ecf1 1px,transparent 1px);border-color:#e4e9ee}.gantt-tick{border-color:#94a2ac}.gantt-tick span{color:#687681}.gantt-segment{background:#f9b665;color:#2b353c;border-color:#e4e9ee}.gantt-segment.completed{background:#f9b665;filter:none}.gantt-segment.active{background:#018c94;border-color:#016e74;color:#fff}.gantt-mask{background:rgba(1,140,148,.15)}.gantt-cursor::before{background:#018c94;box-shadow:none}.gantt-cursor:hover::before,.gantt-cursor.dragging::before{background:#03a0a9}.gantt-row-value.active{color:#016e74}.gantt-row-value.positive:not(.active){color:#02787f}.gantt-row-value.negative:not(.active){color:#c33d32}.gantt-row-value.zero{color:#687681}.gantt-footer{background:#fff;border-top-color:#e4e9ee}.gantt-time{color:#687681}.perspective-switch{display:inline-flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid var(--line);border-radius:10px;background:var(--panel);color:var(--text);font-size:13px;cursor:pointer;white-space:nowrap}.perspective-switch input{position:absolute;opacity:0;pointer-events:none}.perspective-switch span{position:relative;width:32px;height:18px;border-radius:999px;background:#66717e;box-shadow:inset 0 0 0 1px rgba(255,255,255,.12)}.perspective-switch span::after{content:"";position:absolute;left:2px;top:2px;width:14px;height:14px;border-radius:50%;background:#fff;transition:transform .16s}.perspective-switch input:checked+span{background:var(--accent)}.perspective-switch input:checked+span::after{transform:translateX(14px)}.perspective-switch b{font-weight:500}</style>
</head>
<body>
<div class="app" id="app">
<canvas id="glcanvas" aria-label="MuJoCo 三维动画"></canvas>
<div class="label-layer" id="labelLayer"></div>
<div class="topbar">
  <div class="titlebox"><div class="title" id="title"></div><div class="subtitle" id="subtitle"></div></div>
  <div class="top-actions">
    <button class="btn" id="frontView">正视图</button>
    <button class="btn" id="sideView">侧视图</button>
    <button class="btn" id="povView">POV视图</button>
    <label class="perspective-switch view-secondary" title="开启透视后呈现近大远小效果"><input id="perspectiveToggle" type="checkbox"><span aria-hidden="true"></span><b>近大远小</b></label>
    <button class="btn" id="openGantt">甘特图</button>
    <button class="btn view-secondary" id="togglePanel">测距</button>
  </div>
</div>
<div class="right-info-stack" id="rightInfoStack">
  <section class="panel" id="pairPanel">
    <div class="panel-head"><h2>测距对</h2><div class="panel-options"><label class="adaptive"><input id="selectAllPairs" type="checkbox" checked>全选</label><label class="adaptive" title="仅显示小于 25 mm 的测距对"><input id="adaptiveVisibility" type="checkbox" checked><span id="adaptiveVisibilityLabel">小于25mm</span></label></div></div>
    <div id="pairList"></div>
  </section>
  <aside class="lab-live-telemetry" id="labLiveTelemetry" aria-live="off" tabindex="0" title="当前动画帧电机位置（嵌入 Lab 时悬停或聚焦查看）">
    <strong>当前动画帧 · 电机位置</strong><div class="lab-live-time" id="labLiveTime">0.000 s</div>
    <div class="lab-live-motors" id="labLiveMotors">读取采样中…</div>
  </aside>
</div>
<div class="controls">
  <div class="transport">
    <div class="transport-buttons">
      <button class="btn transport-button" id="goStart" aria-label="回到最开始" title="回到最开始">|◀</button>
      <button class="btn transport-button" id="reverseButton" aria-label="倒放" title="倒放">◀</button>
      <button class="btn transport-button" id="playButton" aria-label="正向播放" title="正向播放">▶</button>
      <button class="btn transport-button" id="goEnd" aria-label="回到最末尾" title="回到最末尾">▶|</button>
    </div>
    <input class="timeline" id="timeline" type="range">
    <div class="time" id="timeText">0.000 s</div>
    <select class="speed" id="speed"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select>
  </div>
  <div class="hint">鼠标左键/单指旋转 · 鼠标右键按住拖拽平移视角 · 滚轮/双指缩放 · 倒放/首尾跳转 · 拖动时间轴定位</div>
  <div class="developer-support">开发支持：喻惟刚</div>
</div>
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
const $=id=>document.getElementById(id);
const ADAPTIVE_THRESHOLD_MM=Number.isFinite(Number(DATA.adaptiveThresholdMm))&&Number(DATA.adaptiveThresholdMm)>0?Number(DATA.adaptiveThresholdMm):25;
$("adaptiveVisibilityLabel").textContent=`小于${ADAPTIVE_THRESHOLD_MM}mm`;
$("adaptiveVisibility").closest("label").title=`仅显示小于 ${ADAPTIVE_THRESHOLD_MM} mm 的测距对`;
const canvas=$("glcanvas"),loading=$("loading"),warning=$("warning"),timeline=$("timeline"),playButton=$("playButton"),reverseButton=$("reverseButton"),timeText=$("timeText"),speedSelect=$("speed"),pairList=$("pairList"),labelLayer=$("labelLayer"),ganttWindow=$("ganttWindow"),ganttDragHandle=$("ganttDragHandle"),ganttResizeHandle=$("ganttResizeHandle"),ganttTimeline=$("ganttTimeline"),ganttTime=$("ganttTime"),ganttImageStage=$("ganttImageStage"),ganttImage=$("ganttImage"),ganttOverlay=$("ganttOverlay"),ganttFallback=$("ganttFallback");
$("title").textContent=(DATA.title||"MuJoCo animation").replace(/_?关键数据/g,"");
$("subtitle").textContent=`V${DATA.version} · ${DATA.frameCount} 帧 · ${DATA.geomCount} 个几何体 · 单文件离线播放`;
timeline.min=String(DATA.start);timeline.max=String(DATA.end);timeline.step="0.001";timeline.value=String(DATA.start);
ganttTimeline.min=String(DATA.start);ganttTimeline.max=String(DATA.end);ganttTimeline.step="0.001";ganttTimeline.value=String(DATA.start);
function decodeB64(text,Type){const raw=atob(text||""),bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);return new Type(bytes.buffer)}
const times=decodeB64(DATA.times,Float32Array),transforms=decodeB64(DATA.transforms,Float32Array),measurements=decodeB64(DATA.measurements,Float32Array),driveValues=decodeB64(DATA.driveValues||"",Float32Array);
// Baked measurement samples stay authoritative. Damping is applied only to rendered values/endpoints in this offline HTML.
const measurementValues=measurements;
const gl=canvas.getContext("webgl2",{antialias:true,alpha:false,preserveDrawingBuffer:false});
if(!gl){loading.style.display="none";warning.style.display="block";warning.textContent="当前浏览器不支持 WebGL2。请使用最新版 Chrome、Edge、Firefox 或 Safari 打开。";throw new Error("WebGL2 unavailable")}
function compile(type,source){const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader)||"shader error");return shader}
function program(vs,fs){const p=gl.createProgram();gl.attachShader(p,compile(gl.VERTEX_SHADER,vs));gl.attachShader(p,compile(gl.FRAGMENT_SHADER,fs));gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(p)||"link error");return p}
const meshProgram=program(`#version 300 es
layout(location=0)in vec3 aPosition;layout(location=1)in vec3 aNormal;uniform mat4 uMVP;uniform mat4 uModel;out vec3 vNormal;void main(){gl_Position=uMVP*vec4(aPosition,1.0);vNormal=mat3(uModel)*aNormal;}`,`#version 300 es
precision highp float;in vec3 vNormal;uniform vec4 uColor;out vec4 outColor;void main(){vec3 n=normalize(vNormal);vec3 l=normalize(vec3(.45,-.55,.8));float d=max(dot(n,l),0.0);float light=.30+.70*d;outColor=vec4(uColor.rgb*light,uColor.a);}`);
// V2.16.8: WebGL lineWidth(2/4) is clamped to one pixel on many systems.
// Build a camera-facing 4-pixel segment from two triangles instead, so the
// HTML distance line is reliably twice the old nominal 2px thickness.
const lineProgram=program(`#version 300 es
precision highp float;
uniform mat4 uVP;uniform vec3 uStart;uniform vec3 uEnd;
uniform vec2 uViewport;uniform float uThicknessPx;
void main(){
  vec4 a=uVP*vec4(uStart,1.0), b=uVP*vec4(uEnd,1.0);
  vec2 delta=(b.xy/max(abs(b.w),1e-7)-a.xy/max(abs(a.w),1e-7))*uViewport;
  vec2 normal=length(delta)>1e-6?normalize(vec2(-delta.y,delta.x)):vec2(1.0,0.0);
  int vertex=gl_VertexID;
  bool atStart=(vertex==0||vertex==1||vertex==4);
  float side=(vertex==1||vertex==4||vertex==5)?1.0:-1.0;
  vec4 clip=atStart?a:b;
  clip.xy+=normal*side*(uThicknessPx/uViewport)*clip.w;
  gl_Position=clip;
}`,`#version 300 es
precision highp float;uniform vec4 uColor;out vec4 outColor;void main(){outColor=uColor;}`);
const meshLoc={mvp:gl.getUniformLocation(meshProgram,"uMVP"),model:gl.getUniformLocation(meshProgram,"uModel"),color:gl.getUniformLocation(meshProgram,"uColor")};
const lineLoc={vp:gl.getUniformLocation(lineProgram,"uVP"),color:gl.getUniformLocation(lineProgram,"uColor"),start:gl.getUniformLocation(lineProgram,"uStart"),end:gl.getUniformLocation(lineProgram,"uEnd"),viewport:gl.getUniformLocation(lineProgram,"uViewport"),thickness:gl.getUniformLocation(lineProgram,"uThicknessPx")};
const gpuMeshes=DATA.meshes.map(item=>{const pos=decodeB64(item.positions,Float32Array),norm=decodeB64(item.normals,Float32Array),idx=decodeB64(item.indices,Uint32Array),vao=gl.createVertexArray();gl.bindVertexArray(vao);const pb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,pb);gl.bufferData(gl.ARRAY_BUFFER,pos,gl.STATIC_DRAW);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,0,0);const nb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,nb);gl.bufferData(gl.ARRAY_BUFFER,norm,gl.STATIC_DRAW);gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,3,gl.FLOAT,false,0,0);const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,idx,gl.STATIC_DRAW);gl.bindVertexArray(null);return{vao,count:idx.length}});
function createWatermarkMesh(config){if(!config||!String(config.text||"").trim())return null;const fontPx=72,pad=5,source=document.createElement("canvas"),ctx=source.getContext("2d",{willReadFrequently:true});ctx.font=`700 ${fontPx}px "Microsoft YaHei","Noto Sans CJK SC","PingFang SC",sans-serif`;source.width=Math.max(16,Math.ceil(ctx.measureText(String(config.text)).width)+pad*2);source.height=fontPx+pad*2+8;const draw=source.getContext("2d",{willReadFrequently:true});draw.clearRect(0,0,source.width,source.height);draw.fillStyle="#fff";draw.font=`700 ${fontPx}px "Microsoft YaHei","Noto Sans CJK SC","PingFang SC",sans-serif`;draw.textBaseline="top";draw.fillText(String(config.text),pad,pad);const pixels=draw.getImageData(0,0,source.width,source.height).data,solid=(x,y)=>x>=0&&y>=0&&x<source.width&&y<source.height&&pixels[(y*source.width+x)*4+3]>64;let minX=source.width,minY=source.height,maxX=-1,maxY=-1;for(let y=0;y<source.height;y++)for(let x=0;x<source.width;x++)if(solid(x,y)){minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y)}if(maxX<minX||maxY<minY)return null;const height=Math.max(Number(config.height)||.3,1e-6),thickness=Math.max(Number(config.thickness)||.01,1e-6),origin=Array.isArray(config.position)?config.position:[0,0,0],scale=height/Math.max(1,maxY-minY+1),cx=(minX+maxX+1)/2,cy=(minY+maxY+1)/2,z0=Number(origin[2])||0,z1=z0+thickness,X=x=>(Number(origin[0])||0)+(x-cx)*scale,Y=y=>(Number(origin[1])||0)+(cy-y)*scale,positions=[],normals=[],indices=[];function quad(a,b,c,d,n){const base=positions.length/3;positions.push(...a,...b,...c,...d);for(let i=0;i<4;i++)normals.push(...n);indices.push(base,base+1,base+2,base,base+2,base+3)}for(let y=minY;y<=maxY;y++){let x=minX;while(x<=maxX){while(x<=maxX&&!solid(x,y))x++;if(x>maxX)break;const start=x;while(x<=maxX&&solid(x,y))x++;const end=x;quad([X(start),Y(y+1),z1],[X(end),Y(y+1),z1],[X(end),Y(y),z1],[X(start),Y(y),z1],[0,0,1]);quad([X(start),Y(y),z0],[X(end),Y(y),z0],[X(end),Y(y+1),z0],[X(start),Y(y+1),z0],[0,0,-1])}}for(let y=minY;y<=maxY;y++)for(let x=minX;x<=maxX;x++){if(!solid(x,y))continue;if(!solid(x-1,y))quad([X(x),Y(y),z0],[X(x),Y(y+1),z0],[X(x),Y(y+1),z1],[X(x),Y(y),z1],[-1,0,0]);if(!solid(x+1,y))quad([X(x+1),Y(y+1),z0],[X(x+1),Y(y),z0],[X(x+1),Y(y),z1],[X(x+1),Y(y+1),z1],[1,0,0]);if(!solid(x,y-1))quad([X(x+1),Y(y),z0],[X(x),Y(y),z0],[X(x),Y(y),z1],[X(x+1),Y(y),z1],[0,1,0]);if(!solid(x,y+1))quad([X(x),Y(y+1),z0],[X(x+1),Y(y+1),z0],[X(x+1),Y(y+1),z1],[X(x),Y(y+1),z1],[0,-1,0])}const vao=gl.createVertexArray();gl.bindVertexArray(vao);const pb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,pb);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(positions),gl.STATIC_DRAW);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,0,0);const nb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,nb);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(normals),gl.STATIC_DRAW);gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,3,gl.FLOAT,false,0,0);const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint32Array(indices),gl.STATIC_DRAW);gl.bindVertexArray(null);return{vao,count:indices.length,color:Array.isArray(config.color)?config.color:[.18,.56,.92,1]}}
const watermarkMesh=createWatermarkMesh(DATA.watermark);
// gl_VertexID produces both triangles: no per-frame bufferData/subData.
const lineVao=gl.createVertexArray();
function mat4(){return new Float32Array(16)}
function multiply(o,a,b){const a00=a[0],a01=a[1],a02=a[2],a03=a[3],a10=a[4],a11=a[5],a12=a[6],a13=a[7],a20=a[8],a21=a[9],a22=a[10],a23=a[11],a30=a[12],a31=a[13],a32=a[14],a33=a[15];let b0=b[0],b1=b[1],b2=b[2],b3=b[3];o[0]=b0*a00+b1*a10+b2*a20+b3*a30;o[1]=b0*a01+b1*a11+b2*a21+b3*a31;o[2]=b0*a02+b1*a12+b2*a22+b3*a32;o[3]=b0*a03+b1*a13+b2*a23+b3*a33;b0=b[4];b1=b[5];b2=b[6];b3=b[7];o[4]=b0*a00+b1*a10+b2*a20+b3*a30;o[5]=b0*a01+b1*a11+b2*a21+b3*a31;o[6]=b0*a02+b1*a12+b2*a22+b3*a32;o[7]=b0*a03+b1*a13+b2*a23+b3*a33;b0=b[8];b1=b[9];b2=b[10];b3=b[11];o[8]=b0*a00+b1*a10+b2*a20+b3*a30;o[9]=b0*a01+b1*a11+b2*a21+b3*a31;o[10]=b0*a02+b1*a12+b2*a22+b3*a32;o[11]=b0*a03+b1*a13+b2*a23+b3*a33;b0=b[12];b1=b[13];b2=b[14];b3=b[15];o[12]=b0*a00+b1*a10+b2*a20+b3*a30;o[13]=b0*a01+b1*a11+b2*a21+b3*a31;o[14]=b0*a02+b1*a12+b2*a22+b3*a32;o[15]=b0*a03+b1*a13+b2*a23+b3*a33;return o}
function perspective(o,fovy,aspect,near,far){const f=1/Math.tan(fovy/2),nf=1/(near-far);o.fill(0);o[0]=f/aspect;o[5]=f;o[10]=(far+near)*nf;o[11]=-1;o[14]=2*far*near*nf;return o}
function orthographic(o,left,right,bottom,top,near,far){const lr=1/(left-right),bt=1/(bottom-top),nf=1/(near-far);o.fill(0);o[0]=-2*lr;o[5]=-2*bt;o[10]=2*nf;o[12]=(left+right)*lr;o[13]=(top+bottom)*bt;o[14]=(far+near)*nf;o[15]=1;return o}
function lookAt(o,eye,center,up){let zx=eye[0]-center[0],zy=eye[1]-center[1],zz=eye[2]-center[2],len=Math.hypot(zx,zy,zz)||1;zx/=len;zy/=len;zz/=len;let xx=up[1]*zz-up[2]*zy,xy=up[2]*zx-up[0]*zz,xz=up[0]*zy-up[1]*zx;len=Math.hypot(xx,xy,xz)||1;xx/=len;xy/=len;xz/=len;const yx=zy*xz-zz*xy,yy=zz*xx-zx*xz,yz=zx*xy-zy*xx;o[0]=xx;o[1]=yx;o[2]=zx;o[3]=0;o[4]=xy;o[5]=yy;o[6]=zy;o[7]=0;o[8]=xz;o[9]=yz;o[10]=zz;o[11]=0;o[12]=-(xx*eye[0]+xy*eye[1]+xz*eye[2]);o[13]=-(yx*eye[0]+yy*eye[1]+yz*eye[2]);o[14]=-(zx*eye[0]+zy*eye[1]+zz*eye[2]);o[15]=1;return o}
function fromQuatPos(o,q,p){const x=q[0],y=q[1],z=q[2],w=q[3],x2=x+x,y2=y+y,z2=z+z,xx=x*x2,xy=x*y2,xz=x*z2,yy=y*y2,yz=y*z2,zz=z*z2,wx=w*x2,wy=w*y2,wz=w*z2;o[0]=1-(yy+zz);o[1]=xy+wz;o[2]=xz-wy;o[3]=0;o[4]=xy-wz;o[5]=1-(xx+zz);o[6]=yz+wx;o[7]=0;o[8]=xz+wy;o[9]=yz-wx;o[10]=1-(xx+yy);o[11]=0;o[12]=p[0];o[13]=p[1];o[14]=p[2];o[15]=1;return o}
function transform4(m,p){const x=p[0],y=p[1],z=p[2],w=m[3]*x+m[7]*y+m[11]*z+m[15];return[(m[0]*x+m[4]*y+m[8]*z+m[12])/w,(m[1]*x+m[5]*y+m[9]*z+m[13])/w,(m[2]*x+m[6]*y+m[10]*z+m[14])/w]}
const proj=mat4(),view=mat4(),vp=mat4(),modelM=mat4(),mvp=mat4();
const initialCenter=DATA.bounds.center.slice(),center=initialCenter.slice(),radius=Math.max(DATA.bounds.radius,0.05);let yaw=-1.0,pitch=.45,distance=radius*2.8,orthographicCamera=true,playing=false,playDirection=1,current=DATA.start,lastTick=performance.now(),speed=1,adaptiveVisibility=true,labelSmoothingReset=true,measurementFollowReset=true,distanceFollowDamping=Math.max(0,Math.min(.95,Number(DATA.distanceFollowDamping??.35)));
const LABEL_SMOOTHING_RATE=7,LABEL_DEAD_ZONE_PX=4,LABEL_MAX_SPEED_PX=600,LABEL_NORMAL_OFFSET_PX=42,LABEL_POINT_SWITCH_JUMP_PX=14,LABEL_POINT_SWITCH_HOLD_MS=220,LABEL_PENDING_BLEND=.25;
function updateTransportState(){playButton.classList.toggle("active",playing&&playDirection>0);reverseButton.classList.toggle("active",playing&&playDirection<0)}
function pausePlayback(){playing=false;updateTransportState()}
function setCameraPreset(name){distance=radius*2.8;orthographicCamera=true;$("perspectiveToggle").checked=false;if(name==="front"){yaw=-Math.PI/2;pitch=0}else if(name==="side"){yaw=0;pitch=0}else if(name==="pov"){yaw=0;pitch=Math.atan2(.439,.898)}resetLabelSmoothing()}
$("perspectiveToggle").addEventListener("change",event=>{orthographicCamera=!event.currentTarget.checked;resetLabelSmoothing()});$("frontView").addEventListener("click",()=>setCameraPreset("front"));$("sideView").addEventListener("click",()=>setCameraPreset("side"));$("povView").addEventListener("click",()=>setCameraPreset("pov"));
if(window.parent!==window&&location.origin!=='null'&&DATA.labIdentity?.sequence_id)document.documentElement.classList.add('lab-contained');
function frameInfo(t){if(DATA.frameCount<=1)return[0,0,0];if(t<=times[0])return[0,1,0];if(t>=times[times.length-1])return[times.length-1,times.length-1,0];let lo=0,hi=times.length-1;while(hi-lo>1){let mid=(lo+hi)>>1;if(times[mid]<=t)lo=mid;else hi=mid}return[lo,hi,(t-times[lo])/Math.max(times[hi]-times[lo],1e-12)]}
function nlerp(out,a,b,t){let bx=b[0],by=b[1],bz=b[2],bw=b[3];if(a[0]*bx+a[1]*by+a[2]*bz+a[3]*bw<0){bx=-bx;by=-by;bz=-bz;bw=-bw}out[0]=a[0]+(bx-a[0])*t;out[1]=a[1]+(by-a[1])*t;out[2]=a[2]+(bz-a[2])*t;out[3]=a[3]+(bw-a[3])*t;const n=Math.hypot(...out)||1;out[0]/=n;out[1]/=n;out[2]/=n;out[3]/=n;return out}
const q=[0,0,0,1],qa=[0,0,0,1],qb=[0,0,0,1],p=[0,0,0];
const pairEnabled=DATA.pairs.map(()=>true),pairLabels=[];
function resetLabelSmoothing(){labelSmoothingReset=true;pairLabels.forEach(item=>{item.screenX=NaN;item.screenY=NaN;item.normalX=NaN;item.normalY=NaN;item.rawX=NaN;item.rawY=NaN;item.pendingX=NaN;item.pendingY=NaN;item.pendingUntil=0})}
function hidePairLabel(item){item.floating.style.display="none";item.screenX=NaN;item.screenY=NaN;item.rawX=NaN;item.rawY=NaN;item.pendingX=NaN;item.pendingY=NaN;item.pendingUntil=0}
function resetPairMeasurementFollow(item){item.displayDist=NaN;item.displayCoords=null}
function dampedPairMeasurement(item,targetDist,targetCoords,dt,forceReset){if(forceReset||!Number.isFinite(item.displayDist)||!Array.isArray(item.displayCoords)||item.displayCoords.length!==6){item.displayDist=targetDist;item.displayCoords=targetCoords.slice();return[item.displayDist,item.displayCoords]}const safeDt=Math.max(1/240,Math.min(dt,.1)),tau=distanceFollowDamping<=0?0:distanceFollowDamping*.8,alpha=tau<=0?1:1-Math.exp(-safeDt/tau);item.displayDist+=(targetDist-item.displayDist)*alpha;for(let k=0;k<6;k++)item.displayCoords[k]+=(targetCoords[k]-item.displayCoords[k])*alpha;return[item.displayDist,item.displayCoords]}
function debouncePairLabelTarget(item,targetX,targetY,now,forceReset){if(forceReset||!Number.isFinite(item.rawX)||!Number.isFinite(item.rawY)){item.rawX=targetX;item.rawY=targetY;item.pendingX=NaN;item.pendingY=NaN;item.pendingUntil=0;return[targetX,targetY]}const jump=Math.hypot(targetX-item.rawX,targetY-item.rawY);item.rawX=targetX;item.rawY=targetY;if(jump>=LABEL_POINT_SWITCH_JUMP_PX){item.pendingX=targetX;item.pendingY=targetY;item.pendingUntil=now+LABEL_POINT_SWITCH_HOLD_MS}else if(item.pendingUntil>now){item.pendingX+=((targetX-item.pendingX)*LABEL_PENDING_BLEND);item.pendingY+=((targetY-item.pendingY)*LABEL_PENDING_BLEND)}if(item.pendingUntil>now&&Number.isFinite(item.screenX)&&Number.isFinite(item.screenY))return[item.screenX,item.screenY];if(item.pendingUntil>0){const acceptedX=Number.isFinite(item.pendingX)?item.pendingX:targetX,acceptedY=Number.isFinite(item.pendingY)?item.pendingY:targetY;item.pendingUntil=0;item.pendingX=NaN;item.pendingY=NaN;return[acceptedX,acceptedY]}return[targetX,targetY]}
function updatePairLabelPosition(item,targetX,targetY,dt,forceReset){if(forceReset||!Number.isFinite(item.screenX)||!Number.isFinite(item.screenY)){item.screenX=targetX;item.screenY=targetY}else{const dx=targetX-item.screenX,dy=targetY-item.screenY,delta=Math.hypot(dx,dy);if(delta>LABEL_DEAD_ZONE_PX){const safeDt=Math.max(1/240,Math.min(dt,.1)),emaStep=delta*(1-Math.exp(-LABEL_SMOOTHING_RATE*safeDt)),step=Math.min(delta,emaStep,LABEL_MAX_SPEED_PX*safeDt);item.screenX+=dx/delta*step;item.screenY+=dy/delta*step}}item.floating.style.left=`${item.screenX}px`;item.floating.style.top=`${item.screenY}px`}
function syncSelectAllPairs(){const selectAll=$("selectAllPairs"),enabledCount=pairEnabled.filter(Boolean).length;selectAll.checked=pairEnabled.length>0&&enabledCount===pairEnabled.length;selectAll.indeterminate=enabledCount>0&&enabledCount<pairEnabled.length}
if(DATA.pairs.length===0){pairList.innerHTML='<div class="empty">当前项目没有有效测距对。</div>';$("selectAllPairs").checked=false;$("selectAllPairs").disabled=true}else DATA.pairs.forEach((pair,index)=>{const row=document.createElement("label");row.className="pair";const check=document.createElement("input");check.type="checkbox";check.checked=true;check.addEventListener("change",()=>{pairEnabled[index]=check.checked;syncSelectAllPairs()});const name=document.createElement("span");name.className="pair-name";name.textContent=pair.name;const value=document.createElement("span");value.className="pair-value";value.textContent="—";row.append(check,name,value);pairList.appendChild(row);const floating=document.createElement("div");floating.className="distance-label";floating.style.display="none";labelLayer.appendChild(floating);pairLabels.push({row,value,floating,check,screenX:NaN,screenY:NaN,normalX:NaN,normalY:NaN,rawX:NaN,rawY:NaN,pendingX:NaN,pendingY:NaN,pendingUntil:0,displayDist:NaN,displayCoords:null})});
$("selectAllPairs").addEventListener("change",event=>{const checked=Boolean(event.target.checked);pairEnabled.fill(checked);pairLabels.forEach(item=>item.check.checked=checked);event.target.indeterminate=false});
$("adaptiveVisibility").addEventListener("change",event=>{adaptiveVisibility=Boolean(event.target.checked)});$("togglePanel").addEventListener("click",()=>{$("pairPanel").style.display=$("pairPanel").style.display==="none"?"block":"none"});
function setCurrent(value,stop=true){current=Math.max(DATA.start,Math.min(DATA.end,Number(value)||0));timeline.value=String(current);ganttTimeline.value=String(current);measurementFollowReset=true;resetLabelSmoothing();if(stop)pausePlayback()}
playButton.addEventListener("click",()=>{if(playing&&playDirection>0){pausePlayback();return}playDirection=1;playing=true;lastTick=performance.now();updateTransportState()});
reverseButton.addEventListener("click",()=>{if(playing&&playDirection<0){pausePlayback();return}playDirection=-1;playing=true;lastTick=performance.now();updateTransportState()});
$("goStart").addEventListener("click",()=>setCurrent(DATA.start));$("goEnd").addEventListener("click",()=>setCurrent(DATA.end));timeline.addEventListener("input",()=>setCurrent(timeline.value));ganttTimeline.addEventListener("input",()=>setCurrent(ganttTimeline.value));speedSelect.addEventListener("change",()=>speed=Number(speedSelect.value)||1);
let drag=false,dragButton=-1,lastX=0,lastY=0;function panCamera(dx,dy){const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch),right=[-sy,cy,0],up=[-sp*cy,-sp*sy,cp],scale=Math.max(radius*.00045,distance*.0011);center[0]+=(-dx*right[0]+dy*up[0])*scale;center[1]+=(-dx*right[1]+dy*up[1])*scale;center[2]+=(-dx*right[2]+dy*up[2])*scale}canvas.addEventListener("contextmenu",e=>e.preventDefault());canvas.addEventListener("pointerdown",e=>{if(e.button!==0&&e.button!==2)return;e.preventDefault();drag=true;dragButton=e.button;lastX=e.clientX;lastY=e.clientY;canvas.setPointerCapture(e.pointerId)});canvas.addEventListener("pointermove",e=>{if(!drag)return;const dx=e.clientX-lastX,dy=e.clientY-lastY;lastX=e.clientX;lastY=e.clientY;if(dragButton===2)panCamera(dx,dy);else{yaw-=dx*.006;pitch=Math.max(-1.45,Math.min(1.45,pitch+dy*.006))}});canvas.addEventListener("pointerup",()=>{drag=false;dragButton=-1});canvas.addEventListener("pointercancel",()=>{drag=false;dragButton=-1});canvas.addEventListener("wheel",e=>{e.preventDefault();distance=Math.max(radius*.2,Math.min(radius*20,distance*Math.exp(e.deltaY*.001)))},{passive:false});
let pinchDistance=0;canvas.addEventListener("touchmove",e=>{if(e.touches.length===2){const dx=e.touches[0].clientX-e.touches[1].clientX,dy=e.touches[0].clientY-e.touches[1].clientY,d=Math.hypot(dx,dy);if(pinchDistance>0)distance=Math.max(radius*.2,Math.min(radius*20,distance*pinchDistance/d));pinchDistance=d;e.preventDefault()}},{passive:false});canvas.addEventListener("touchend",()=>pinchDistance=0);
function resize(){const dpr=Math.min(devicePixelRatio||1,2),w=Math.max(1,Math.floor(canvas.clientWidth*dpr)),h=Math.max(1,Math.floor(canvas.clientHeight*dpr));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);resetLabelSmoothing()}}
function sampledDriveValue(driveIndex,t){if(driveIndex<0||driveIndex>=DATA.driveCount||driveValues.length===0)return NaN;const [i0,i1,mix]=frameInfo(t),a=driveValues[i0*DATA.driveCount+driveIndex],b=driveValues[i1*DATA.driveCount+driveIndex];if(!Number.isFinite(a)||!Number.isFinite(b))return NaN;return a+(b-a)*mix}
const labMotorRanges=DATA.drives.map((_drive,idx)=>{let lo=Infinity,hi=-Infinity;for(let f=0;f<DATA.frameCount;f++){const v=driveValues[f*DATA.driveCount+idx];if(Number.isFinite(v)){lo=Math.min(lo,v);hi=Math.max(hi,v)}}return[lo,hi]});
let lastLabFrameTick=-Infinity;
function reportLabFrame(now){
  if(now-lastLabFrameTick<48)return;
  lastLabFrameTick=now;
  const playback_state=playing?"playing":"paused";
  const motors=DATA.drives.map((drive,idx)=>{
    const position=sampledDriveValue(idx,current),bounds=labMotorRanges[idx];
    return {drive_id:drive.id,name:drive.name,position:Number.isFinite(position)?position:null,
      unit:drive.unit==='°'?'deg':'mm',source:drive.source||'unknown',
      percent:!Number.isFinite(position)?null:(bounds[1]>bounds[0]?100*(position-bounds[0])/(bounds[1]-bounds[0]):0)};
  });
  $("labLiveTime").textContent=`${current.toFixed(3)} s  ·  ${playback_state==='playing'?'播放中':'已暂停'}`;
  const panel=$("labLiveMotors");panel.replaceChildren();
  if(!motors.length)panel.textContent='无有效驱动电机';
  for(const motor of motors){const row=document.createElement('div');row.className='lab-live-line';
    const name=document.createElement('span'),value=document.createElement('b');
    name.textContent=motor.name;name.title=motor.name;
    value.textContent=motor.position===null?'— (不支持换算)':`${motor.position.toFixed(3)} ${motor.unit==='deg'?'°':'mm'}`;
    row.append(name,value);panel.append(row);
  }
  if(window.parent!==window&&location.origin!=='null'&&DATA.labIdentity&&DATA.labIdentity.sequence_id){
    window.parent.postMessage({type:'mujoco-lab-frame',lab_version:'2.16.11.6',identity:DATA.labIdentity,
      sim_time_s:current,playback_state,motors},location.origin);
  }
}
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
async function exportGanttPng(){const blob=ganttPngBlob();if(!blob)return;const base=String(DATA.title||"模型").replace(/[\\/:*?"<>|]+/g,"_").replace(/^\.+|\.+$/g,"")||"模型",suggestedName=`${base}_甘特图.png`,url=URL.createObjectURL(blob),anchor=document.createElement("a");anchor.href=url;anchor.download=suggestedName;anchor.style.display="none";document.body.appendChild(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function buildGantt(){if(buildImageGantt())return;ganttImageStage.hidden=true;ganttFallback.hidden=false;buildGanttFallback()}
buildGantt();$("exportGanttPng").disabled=!DATA.ganttImage;$("exportGanttPng").addEventListener("click",exportGanttPng);enableGanttDrag();enableGanttResize();$("openGantt").addEventListener("click",()=>{ganttWindow.hidden=false;initializeGanttWindow();updateGantt(current)});$("closeGantt").addEventListener("click",()=>ganttWindow.hidden=true);document.addEventListener("keydown",event=>{if(event.key==="Escape")ganttWindow.hidden=true});window.addEventListener("resize",()=>{constrainGanttWindow();drawImageGantt(current)});
function render(now){resize();const dt=Math.min((now-lastTick)/1000,.1);lastTick=now;if(playing){current+=dt*speed*playDirection;if(current>DATA.end){current=DATA.start;labelSmoothingReset=true;measurementFollowReset=true}if(current<DATA.start){current=DATA.end;labelSmoothingReset=true;measurementFollowReset=true}timeline.value=String(current);ganttTimeline.value=String(current)}const resetLabels=labelSmoothingReset,resetMeasurements=measurementFollowReset;labelSmoothingReset=false;measurementFollowReset=false;timeText.textContent=`${current.toFixed(3)} s / ${DATA.end.toFixed(3)} s`;reportLabFrame(now);if(!ganttWindow.hidden)updateGantt(current);const eye=[center[0]+distance*Math.cos(pitch)*Math.cos(yaw),center[1]+distance*Math.cos(pitch)*Math.sin(yaw),center[2]+distance*Math.sin(pitch)];const aspect=canvas.width/canvas.height,near=Math.max(radius*.002,.0001),far=radius*50+distance;if(orthographicCamera){const halfHeight=Math.max(radius*.08,distance*.42),halfWidth=halfHeight*aspect;orthographic(proj,-halfWidth,halfWidth,-halfHeight,halfHeight,-far,far)}else perspective(proj,45*Math.PI/180,aspect,near,far);lookAt(view,eye,center,[0,0,1]);multiply(vp,proj,view);gl.clearColor(.045,.06,.082,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);gl.disable(gl.CULL_FACE);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);const [i0,i1,mix]=frameInfo(current);gl.useProgram(meshProgram);for(let g=0;g<DATA.geomCount;g++){const a=(i0*DATA.geomCount+g)*7,b=(i1*DATA.geomCount+g)*7;p[0]=transforms[a]+(transforms[b]-transforms[a])*mix;p[1]=transforms[a+1]+(transforms[b+1]-transforms[a+1])*mix;p[2]=transforms[a+2]+(transforms[b+2]-transforms[a+2])*mix;qa[0]=transforms[a+3];qa[1]=transforms[a+4];qa[2]=transforms[a+5];qa[3]=transforms[a+6];qb[0]=transforms[b+3];qb[1]=transforms[b+4];qb[2]=transforms[b+5];qb[3]=transforms[b+6];nlerp(q,qa,qb,mix);fromQuatPos(modelM,q,p);multiply(mvp,vp,modelM);const geom=DATA.geoms[g],color=geom.color;gl.uniformMatrix4fv(meshLoc.mvp,false,mvp);gl.uniformMatrix4fv(meshLoc.model,false,modelM);gl.uniform4fv(meshLoc.color,color);gl.depthMask(color[3]>=.995);const mesh=gpuMeshes[geom.mesh];gl.bindVertexArray(mesh.vao);gl.drawElements(gl.TRIANGLES,mesh.count,gl.UNSIGNED_INT,0)}gl.depthMask(true);if(watermarkMesh){fromQuatPos(modelM,[0,0,0,1],[0,0,0]);multiply(mvp,vp,modelM);gl.uniformMatrix4fv(meshLoc.mvp,false,mvp);gl.uniformMatrix4fv(meshLoc.model,false,modelM);gl.uniform4fv(meshLoc.color,watermarkMesh.color);gl.bindVertexArray(watermarkMesh.vao);gl.drawElements(gl.TRIANGLES,watermarkMesh.count,gl.UNSIGNED_INT,0)}gl.useProgram(lineProgram);gl.uniformMatrix4fv(lineLoc.vp,false,vp);gl.uniform2f(lineLoc.viewport,canvas.width,canvas.height);gl.uniform1f(lineLoc.thickness,4);gl.bindVertexArray(lineVao);for(let j=0;j<DATA.pairCount;j++){
  const base0=(i0*DATA.pairCount+j)*7,base1=(i1*DATA.pairCount+j)*7,item=pairLabels[j];
  const targetDist=measurementValues[base0]+(measurementValues[base1]-measurementValues[base0])*mix,targetCoords=[];
  for(let k=1;k<7;k++)targetCoords.push(measurementValues[base0+k]+(measurementValues[base1+k]-measurementValues[base0+k])*mix);
  const rawValid=Number.isFinite(targetDist)&&targetCoords.every(Number.isFinite),enabled=pairEnabled[j];
  if(!rawValid){resetPairMeasurementFollow(item);item.value.textContent="—";item.row.classList.remove("filtered");hidePairLabel(item);continue}
  const followed=dampedPairMeasurement(item,targetDist,targetCoords,dt,resetMeasurements),dist=followed[0],coords=followed[1];
  const withinThreshold=dist*1000<ADAPTIVE_THRESHOLD_MM,visible=enabled&&(!adaptiveVisibility||withinThreshold);
  item.value.textContent=`${(dist*1000).toFixed(3)} mm`;
  item.row.classList.toggle("filtered",enabled&&adaptiveVisibility&&!withinThreshold);
  if(!visible){hidePairLabel(item);continue}
  const color=dist<0?[1,.25,.3,1]:DATA.pairs[j].color;
  gl.uniform4fv(lineLoc.color,color);gl.uniform3fv(lineLoc.start,coords.slice(0,3));gl.uniform3fv(lineLoc.end,coords.slice(3,6));gl.drawArrays(gl.TRIANGLES,0,6);
  const mid=[(coords[0]+coords[3])/2,(coords[1]+coords[4])/2,(coords[2]+coords[5])/2],clip=transform4(vp,mid);
  if(clip[2]>=-1&&clip[2]<=1){
    const clipA=transform4(vp,[coords[0],coords[1],coords[2]]),clipB=transform4(vp,[coords[3],coords[4],coords[5]]),ax=(clipA[0]*.5+.5)*canvas.clientWidth,ay=(-clipA[1]*.5+.5)*canvas.clientHeight,bx=(clipB[0]*.5+.5)*canvas.clientWidth,by=(-clipB[1]*.5+.5)*canvas.clientHeight;
    let nx=-(by-ay),ny=bx-ax,nlen=Math.hypot(nx,ny);if(nlen<1e-6){nx=0;ny=-1}else{nx/=nlen;ny/=nlen}if(Number.isFinite(item.normalX)&&Number.isFinite(item.normalY)){if(nx*item.normalX+ny*item.normalY<0){nx=-nx;ny=-ny}}else if(ny>0){nx=-nx;ny=-ny}item.normalX=nx;item.normalY=ny;
    const targetX=(clip[0]*.5+.5)*canvas.clientWidth+nx*LABEL_NORMAL_OFFSET_PX,targetY=(-clip[1]*.5+.5)*canvas.clientHeight+ny*LABEL_NORMAL_OFFSET_PX;item.floating.style.display="block";const stableTarget=debouncePairLabelTarget(item,targetX,targetY,now,resetLabels);updatePairLabelPosition(item,stableTarget[0],stableTarget[1],dt,resetLabels);item.floating.textContent=`${(dist*1000).toFixed(3)} mm`;item.floating.style.color=dist<0?"#ff9da3":"#fff"
  }else hidePairLabel(item)
}gl.bindVertexArray(null);loading.style.display="none";requestAnimationFrame(render)}
updateTransportState();requestAnimationFrame(render);
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
    started_at = time.perf_counter()

    _report(progress_callback, "读取 MuJoCo 场景", 0.02)
    payload = json.loads(drives_file.read_text(encoding="utf-8"))
    model = load_mujoco_model(scene, mujoco)
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
            "id": str(drive.get("id", "") or ""),
            "name": str(drive.get("name", "") or f"驱动{index + 1}"),
            "unit": _drive_display_unit(drive.get("joint_type", "")),
            "jointType": str(drive.get("joint_type", "") or ""),
            "source": "unsupported_crank_qpos" if str(drive.get("joint_type")) == "crank" else "trajectory_qpos",
        }
        for index, drive in enumerate(target_drives)
    ]

    _report(progress_callback, "整理浏览器三维网格", 0.08)
    scene_loaded_at = time.perf_counter()
    mesh_records: list[dict[str, Any]] = []
    mesh_index_by_key: dict[str, int] = {}
    # Repeated MuJoCo geoms often instantiate one mesh.  Avoid extracting and
    # (potentially) decimating the same high-poly STL for every instance.  The
    # individual geom transforms/colors are still exported one by one.
    mesh_index_by_source: dict[tuple[Any, ...], int] = {}
    geom_records: list[dict[str, Any]] = []
    geom_ids: list[int] = []
    mesh_radii: list[float] = []
    warnings: list[str] = []

    for geom_id in range(int(model.ngeom)):
        rgba = [float(v) for v in np.asarray(model.geom_rgba[geom_id], dtype=float).reshape(4)]
        if rgba[3] <= 0.001:
            continue
        geom_type = int(model.geom_type[geom_id])
        if geom_type == int(mujoco.mjtGeom.mjGEOM_MESH):
            source_id = int(model.geom_dataid[geom_id])
            source_key = ("mesh", source_id, int(max_faces_per_mesh)) if source_id >= 0 else ("missing", geom_id)
        else:
            source_key = ("primitive", geom_type, *map(float, np.asarray(model.geom_size[geom_id])[:3]))
        mesh_index = mesh_index_by_source.get(source_key)
        if mesh_index is None:
            key, vertices, faces, simplified = _mesh_from_geom(model, geom_id, mujoco, max_faces_per_mesh)
            if len(vertices) == 0 or len(faces) == 0:
                continue
            if key not in mesh_index_by_key:
                normals = _compute_vertex_normals(vertices, faces)
                vertices = np.asarray(vertices, dtype=np.float32)
                normals = np.asarray(normals, dtype=np.float32)
                faces = np.asarray(faces, dtype=np.uint32)
                radius = float(np.max(np.linalg.norm(vertices, axis=1))) if len(vertices) else 0.01
                mesh_index_by_key[key] = len(mesh_records)
                mesh_records.append(
                    {
                        "positions": _b64_f32(vertices),
                        "normals": _b64_f32(normals),
                        "indices": _b64_u32(faces),
                        "vertexCount": int(len(vertices)),
                        "faceCount": int(len(faces)),
                        "radius": radius,
                    }
                )
                if simplified:
                    warnings.append(f"网格 {key} 已自动简化为 {len(faces)} 个三角面")
            mesh_index = mesh_index_by_key[key]
            mesh_index_by_source[source_key] = mesh_index
        geom_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id) or f"geom_{geom_id}"
        geom_records.append({"name": str(geom_name), "mesh": int(mesh_index), "color": rgba})
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
    # Offline HTML interpolates transforms between samples, so 20 Hz preserves smooth playback
    # while avoiding the former 30-120 Hz duplication of geometry transforms/distance samples.
    if fps > 20:
        fps = 20
        warnings.append(f"动画 HTML 使用插值播放，采样帧率已从 {requested_fps} FPS 限制为 20 FPS 以缩短导出并减小文件")
    if duration > 0.0 and int(math.ceil(duration * fps - 1e-9)) + 1 > MAX_EXPORT_FRAMES:
        fps = max(1, int(math.floor((MAX_EXPORT_FRAMES - 1) / duration)))
        warnings.append(f"动画时长较长，导出帧率已从 {requested_fps} FPS 自动调整为 {fps} FPS")
    frame_count = max(1, int(math.ceil(duration * fps - 1e-9)) + 1)
    times = np.linspace(start_time, end_time, frame_count, dtype=np.float64) if frame_count > 1 else np.asarray([start_time], dtype=np.float64)

    _report(progress_callback, "准备测距对采样", 0.14)
    geometry_ready_at = time.perf_counter()
    pair_records: list[dict[str, Any]] = []
    pair_runtimes: list[dict[str, Any]] = []
    geom_to_file = geom_to_file_builder(model, payload.get("mesh_manifest", {}) or {})
    # Viewer and HTML use one color source; collisions still render red.
    from .viewer_runner import _DISTANCE_LINE_RGBA_NORMAL
    distance_line_green = list(_DISTANCE_LINE_RGBA_NORMAL)
    global_strategy = bool(payload.get("single_distance_strategy_enabled", True))
    global_precise = bool(payload.get("single_distance_precise_enabled", True))
    global_negative = bool(payload.get("single_distance_interference_enabled", False))

    if measurement_pair_builder is not None and measurement_pair_evaluator is not None:
        built_pairs = list(measurement_pair_builder(mujoco, model, payload) or [])
        for pair_runtime in built_pairs:
            if not pair_runtime.get("group_a") or not pair_runtime.get("group_b"):
                continue
            name = str(pair_runtime.get("name", "") or "").strip() or f"测距对{len(pair_records) + 1}"
            pair_records.append({"id": str(pair_runtime.get("id", "")), "name": name, "color": distance_line_green.copy()})
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
            pair_records.append({"id": str(pair.get("id", "")), "name": name, "color": distance_line_green.copy()})
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

    _report(progress_callback, "自动采样动画与测距", 0.17)
    pairs_ready_at = time.perf_counter()
    measurement_seconds = 0.0
    thread_state = threading.local()

    def sample_batch(start: int, stop: int, cancelled: Callable[[], bool]) -> float:
        if not hasattr(thread_state, "data"):
            thread_state.data = mujoco.MjData(model)
            # A worker reuses its own buffers across its 50-frame batches.
            # Surface samples are read-only and can be shared across workers.
            thread_state.pairs = [
                _clone_distance_pair(pair) if "samples" in pair else copy.deepcopy(pair)
                for pair in pair_runtimes
            ]
        frame_data = thread_state.data
        local_pairs = thread_state.pairs
        measurement_seconds = 0.0
        for frame_index in range(start, stop):
            time_value = times[frame_index]
            if cancelled():
                raise InterruptedError("动画 HTML 导出已取消")
            # With an authoritative trajectory, the old commanded offsets are not
            # applied or displayed; only qpos drives geom and motor readbacks.
            # Skipping this duplicate schedule evaluation preserves every frame.
            if qpos_resolver is None:
                _commanded_values, offsets = offset_resolver(targets, float(time_value))
            else:
                offsets = ()
            if qpos_resolver is not None:
                resolved_qpos = np.asarray(qpos_resolver(float(time_value)), dtype=float).reshape(-1)
                if not np.all(np.isfinite(resolved_qpos)):
                    raise AnimationHtmlExportError("动画轨迹 qpos 包含 NaN 或无穷值")
                if resolved_qpos.shape != (int(model.nq),):
                    raise AnimationHtmlExportError(
                        f"动画轨迹 qpos 与当前模型 nq 不一致：trajectory={resolved_qpos.shape}, model=({int(model.nq)},)"
                    )
                frame_data.qpos[:] = resolved_qpos
            else:
                frame_data.qpos[:] = base_qpos
                for qpos_address, offset in offsets:
                    frame_data.qpos[int(qpos_address)] = base_qpos[int(qpos_address)] + float(offset)
            frame_data.time = float(time_value)
            mujoco.mj_forward(model, frame_data)
            # The rendered qpos is the authoritative frame. Commanded time-series
            # offsets can differ in dynamic/contact/closed-loop models.
            for drive_index, (drive, qadr) in enumerate(targets):
                if str(drive.get("joint_type", "")) == "crank":
                    # A crank's MuJoCo qpos is a slider displacement; labelling it
                    # as an angular motor position would be fabricated telemetry.
                    continue
                # Absolute MuJoCo joint coordinate, not a commanded travel offset.
                # A hinge starting at -90 degrees must report -90 at its first
                # frame; the timeline initial_position is bound to that same
                # trusted frame by align_timeline_to_samples before deployment.
                raw_value = float(frame_data.qpos[qadr])
                drive_values[frame_index, drive_index] = _drive_value_to_display(drive.get("joint_type", ""), raw_value)

            for local_index, geom_id in enumerate(geom_ids):
                pos = np.asarray(frame_data.geom_xpos[geom_id], dtype=float).reshape(3)
                quat = np.asarray(_matrix_to_quaternion_xyzw(frame_data.geom_xmat[geom_id]), dtype=float)
                transforms[frame_index, local_index, :3] = pos
                transforms[frame_index, local_index, 3:] = quat

            measure_started_at = time.perf_counter() if pair_runtimes else 0.0
            for pair_index, pair_runtime in enumerate(local_pairs):
                if measurement_pair_evaluator is not None:
                    distance, line = measurement_pair_evaluator(mujoco, model, frame_data, pair_runtime)
                    if not math.isfinite(float(distance)) or line is None:
                        continue
                else:
                    native_distance, native_line = _native_pair_distance(
                        mujoco, model, frame_data,
                        pair_runtime["group_a"], pair_runtime["group_b"], pair_runtime["distmax"],
                    )
                    use_precise = bool(pair_runtime.get("precise_enabled", False))
                    points_a = world_group_points(pair_runtime["group_a"], frame_data, use_precise=use_precise)
                    points_b = world_group_points(pair_runtime["group_b"], frame_data, use_precise=use_precise)
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
            if pair_runtimes:
                measurement_seconds += time.perf_counter() - measure_started_at

        return measurement_seconds

    completed_frames = 0
    worker_count = frame_worker_count(frame_count)
    for start, stop, elapsed in iter_frame_batches(frame_count, sample_batch, should_cancel=should_cancel):
        completed_frames += stop - start
        measurement_seconds += elapsed
        _report(progress_callback, f"并行采样动画 {completed_frames}/{frame_count} 帧 · {worker_count} 线程 · 每批 {FRAME_BATCH_SIZE} 帧",
                0.17 + 0.70 * completed_frames / frame_count)

    # Completion order cannot determine quaternion signs. Resolve continuity
    # once, in global frame order, including every 50-frame batch boundary.
    for frame_index in range(1, frame_count):
        previous = transforms[frame_index - 1, :, 3:]
        current = transforms[frame_index, :, 3:]
        flip = np.einsum("ij,ij->i", previous, current) < 0.0
        current[flip] *= -1.0
    if should_cancel and should_cancel():
        raise InterruptedError("动画 HTML 导出已取消")

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
    watermark = _animation_watermark_config(payload, default_color=floor_color)
    try:
        distance_follow_damping = float(payload.get("animation_distance_follow_damping", 0.35))
    except (TypeError, ValueError):
        distance_follow_damping = 0.35
    if not math.isfinite(distance_follow_damping):
        distance_follow_damping = 0.35
    distance_follow_damping = min(0.95, max(0.0, distance_follow_damping))
    try:
        adaptive_threshold_mm = float(payload.get("animation_adaptive_threshold_mm", 25.0))
    except (TypeError, ValueError, OverflowError):
        adaptive_threshold_mm = 25.0
    if not math.isfinite(adaptive_threshold_mm) or adaptive_threshold_mm <= 0:
        adaptive_threshold_mm = 25.0

    _report(progress_callback, "生成离线 WebGL 播放器", 0.91)
    frames_ready_at = time.perf_counter()
    export_payload = {
        "version": V21_EXPORT_VERSION,
        "title": destination.stem,
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
        "labIdentity": dict(payload.get("lab_identity", {}) or {}),
        "meshes": mesh_records,
        "geoms": geom_records,
        "pairs": pair_records,
        "drives": drive_records,
        "ganttRows": gantt_rows,
        "ganttImage": gantt_image,
        "ganttMetadata": gantt_metadata,
        "distanceFollowDamping": distance_follow_damping,
        "adaptiveThresholdMm": adaptive_threshold_mm,
        "watermark": watermark,
        "bounds": {"center": [float(v) for v in center], "radius": float(scene_radius)},
        "warnings": warnings,
    }
    html_text = _build_html_document(destination.stem, export_payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Atomic publication: cancellation, worker/encoding errors and disk errors
    # must leave an existing animation intact.
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=".animation-", suffix=".tmp", delete=False) as handle:
            temporary_name = handle.name
            handle.write(html_text)
            handle.flush()
            os.fsync(handle.fileno())
        if should_cancel and should_cancel():
            raise InterruptedError("动画 HTML 导出已取消")
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    completed_at = time.perf_counter()
    _report(progress_callback, "动画 HTML 导出完成", 1.0)

    return {
        "path": str(destination),
        "frame_count": int(frame_count),
        "frame_batch_size": FRAME_BATCH_SIZE,
        "frame_workers": worker_count,
        "distance_query_mode": "exact_all_samples" if measurement_pair_evaluator is not None else "legacy",
        "geom_count": int(len(geom_records)),
        "pair_count": int(len(pair_records)),
        "drive_count": int(len(drive_records)),
        "mesh_count": int(len(mesh_records)),
        "file_size": int(destination.stat().st_size),
        "timings_seconds": {
            "scene_loading": round(scene_loaded_at - started_at, 3),
            "mesh_preparation": round(geometry_ready_at - scene_loaded_at, 3),
            "distance_preparation": round(pairs_ready_at - geometry_ready_at, 3),
            "frame_sampling": round(frames_ready_at - pairs_ready_at, 3),
            "distance_evaluation": round(measurement_seconds, 3),
            "html_encoding": round(completed_at - frames_ready_at, 3),
            "total": round(completed_at - started_at, 3),
        },
        "warnings": warnings,
    }
