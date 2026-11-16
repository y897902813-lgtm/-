from __future__ import annotations

import base64
import json
import math
import mimetypes
from pathlib import Path
from typing import Any, Callable

from .legacy_animation_html_export import export_interactive_animation_html
from .mujoco_engine import safe_name
from .simulation import timeline_values_at


Progress = Callable[[float, str], None]


def _drive_payload(model: dict[str, Any], metadata: dict[str, Any], timeline: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for drive in model.get("drives", []):
        joint_id = str(drive.get("joint_id", ""))
        if not drive.get("enabled", True) or joint_id not in metadata.get("joint_names", {}):
            continue
        segments = []
        for segment in timeline.get("segments", []):
            if str(segment.get("drive_id", "")) != str(drive.get("id", "")):
                continue
            segments.append({
                "name": next((item.get("name", "动作") for item in drive.get("segments", []) if item.get("id") == segment.get("action_id")), "动作"),
                "_start": float(segment.get("start_time", 0.0)),
                "_duration": float(segment.get("duration", 0.0)),
                "_end": float(segment.get("end_time", 0.0)),
                "travel": float(segment.get("end_value", 0.0)) - float(segment.get("start_value", 0.0)),
                "_travel_start": float(segment.get("start_value", 0.0)),
                "_travel_end": float(segment.get("end_value", 0.0)),
                "motion_profile": "drive_mapping" if segment.get("profile") == "mapping" else str(segment.get("profile", "s_curve")),
            })
        rows.append({
            "id": drive["id"],
            "name": drive.get("name", drive["id"]),
            "joint_id": joint_id,
            "joint_name": metadata["joint_names"][joint_id],
            "joint_type": metadata["joint_types"][joint_id],
            "position_0_percent": float(drive.get("position_0_percent", drive.get("initial_position", drive.get("reverse_limit", 0.0)))),
            "position_100_percent": float(drive.get("position_100_percent", next((item.get("target") for item in drive.get("actions", []) if item.get("target") is not None), drive.get("forward_limit", 100.0)))),
            "segments": segments,
        })
    return rows


def _safe_render_asset_path(root: Path, kind: str, name: str) -> Path:
    base = (root / kind).resolve()
    raw = str(name or "").replace("\\", "/").strip()
    parts = [part for part in raw.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"渲染素材路径非法：{name}")
    target = (base / Path(*parts)).resolve()
    if base not in target.parents or not target.is_file():
        raise FileNotFoundError(f"未找到渲染素材：{kind}/{name}")
    return target

def _render_asset_data_uri(root: Path, kind: str, name: str) -> str:
    path = _safe_render_asset_path(root, kind, name)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")

def _embed_render_assets(
    model: dict[str, Any],
    root: Path | None,
    *,
    environment_name: str = "",
    include_textures: bool = True,
) -> tuple[dict[str, dict[str, str]], list[str]]:
    embedded: dict[str, dict[str, str]] = {"textures": {}, "environments": {}}
    warnings: list[str] = []
    texture_fields = ("base_color_map", "normal_map", "roughness_map", "metallic_map", "ao_map")
    render_configs = [asset.get("render_config") or {} for asset in model.get("assets", [])]
    for layer in model.get("layers", []):
        for mesh in layer.get("meshes", []):
            slot0 = (mesh.get("material_slots") or {}).get("slot_0") if isinstance(mesh.get("material_slots"), dict) else None
            override = slot0 or mesh.get("render_config")
            if isinstance(override, dict):
                render_configs.append(override)
    texture_names = {str(config.get(field, "") or "") for config in render_configs for field in texture_fields} if include_textures else set()
    texture_names.discard("")
    environment_name = str(environment_name or "")
    if root is None and (texture_names or environment_name):
        warnings.append("已配置 PBR 渲染素材，但当前导出未提供后台 render_assets 目录；将使用程序材质回退。")
        return embedded, warnings
    if root is None:
        return embedded, warnings
    total_bytes = 0
    for kind, names in (("textures", sorted(texture_names)), ("environments", [environment_name] if environment_name else [])):
        for name in names:
            try:
                path = _safe_render_asset_path(root, kind, name)
                total_bytes += path.stat().st_size
                embedded[kind][name] = _render_asset_data_uri(root, kind, name)
            except (OSError, ValueError) as exc:
                warnings.append(str(exc))
    if total_bytes > 128 * 1024 * 1024:
        warnings.append(f"PBR 素材原始体积约 {total_bytes / 1024 / 1024:.1f} MiB，单文件 HTML 会明显增大。")
    return embedded, warnings

def export_animation_html(
    model: dict[str, Any],
    simulation_dir: Path,
    destination: Path,
    *,
    fps: int = 30,
    quality: str = "fast",
    render_assets_root: Path | None = None,
    progress: Progress | None = None,
) -> dict[str, Any]:
    simulation_dir = simulation_dir.resolve()
    generated_dir = simulation_dir / "generated"
    metadata = json.loads((generated_dir / "metadata.json").read_text("utf-8"))
    result = json.loads((simulation_dir / "result.json").read_text("utf-8"))
    timeline = result.get("timeline") or {"duration": float(result.get("summary", {}).get("duration_s", 0.001)), "initial": {}, "segments": []}
    drives = _drive_payload(model, metadata, timeline)
    quality = str(quality or "fast").lower()
    if quality not in {"preview", "fast", "perfect"}:
        raise ValueError("动画渲染质量必须是 preview、fast 或 perfect")
    assets = {str(item.get("id", "")): item for item in model.get("assets", [])}
    render_configs: dict[str, dict[str, Any]] = {}
    for layer in model.get("layers", []):
        for mesh in layer.get("meshes", []):
            asset = assets.get(str(mesh.get("asset_id", "")), {})
            slot0 = (mesh.get("material_slots") or {}).get("slot_0") if isinstance(mesh.get("material_slots"), dict) else None
            selected = slot0 or mesh.get("render_config") or asset.get("render_config") or {}
            render_configs[safe_name(f"geom_{mesh.get('id', '')}", "geom")] = dict(selected)
    scene = dict(model.get("render_scene") or {})
    if quality == "perfect":
        render_scene = scene
        environment_name = str(scene.get("environment_map", "") or "")
        render_assets, render_asset_warnings = _embed_render_assets(
            model, render_assets_root, environment_name=environment_name, include_textures=True
        )
    else:
        environment_name = str(scene.get("fast_environment_map", "") or "")
        render_scene = {
            # V2.13.0 user quick render deliberately defaults to the lighter
            # Classic scene. Perfect render still respects engineer scene settings.
            "scene_preset": "classic",
            "environment_map": environment_name,
            "environment_intensity": 1.0,
            "environment_rotation_deg": 0.0,
            "exposure": 1.0,
            "shadow_strength": 0.0,
            "shadow_softness": 1.0,
        }
        render_assets, render_asset_warnings = _embed_render_assets(
            model, render_assets_root, environment_name=environment_name, include_textures=False
        )
    payload = {
        "drives": drives,
        "mesh_manifest": {},
        "pairs": [],
        "sim_start_time": 0.0,
        "sim_end_time": float(timeline.get("duration", 0.001)),
        "single_distance_strategy_enabled": False,
        "single_distance_precise_enabled": False,
        "single_distance_interference_enabled": False,
        # V2.13.0 user page no longer renders the legacy center project watermark.
        "animation_watermark_text": "",
        "animation_watermark_position": "0, 0, 0",
        "animation_watermark_size_mm": 150,
        "animation_watermark_thickness_mm": 10,
        "animation_watermark_color": "#B3B3B3",
        "model_name": str(model.get("name", "模型") or "模型"),
        "render_quality": quality,
        "render_configs": render_configs,
        "render_scene": render_scene,
        "render_assets": render_assets,
        "render_asset_warnings": render_asset_warnings,
    }
    adapter_path = simulation_dir / "animation_export_input.json"
    adapter_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    import numpy as np

    times = np.asarray(result.get("times", []), dtype=float)
    qpos = np.asarray(result.get("qpos", []), dtype=float)
    if not len(times) or qpos.ndim != 2 or qpos.shape[0] != len(times):
        raise ValueError("MuJoCo 轨迹数据不完整，无法导出动画 HTML")

    def qpos_resolver(time_s: float) -> Any:
        if time_s <= times[0]:
            return qpos[0].copy()
        if time_s >= times[-1]:
            return qpos[-1].copy()
        right = int(np.searchsorted(times, time_s, side="right"))
        left = max(0, right - 1)
        right = min(right, len(times) - 1)
        span = float(times[right] - times[left])
        if span <= 1e-12:
            return qpos[left].copy()
        mix = (float(time_s) - float(times[left])) / span
        return qpos[left] + (qpos[right] - qpos[left]) * mix

    drive_by_id = {str(item["id"]): item for item in model.get("drives", [])}

    def offset_resolver(targets: Any, time_s: float) -> tuple[dict[str, float], list[tuple[int, float]]]:
        absolute = timeline_values_at(timeline, float(time_s))
        values: dict[str, float] = {}
        for drive, _address in targets:
            source = drive_by_id.get(str(drive.get("id", "")), {})
            raw = float(absolute.get(str(drive.get("id", "")), source.get("initial_position", 0.0)))
            if str(drive.get("joint_type", "")) in {"rotation", "hinge"}:
                raw = math.radians(raw)
            else:
                raw *= 0.001
            values[str(drive.get("name", ""))] = raw
        return values, []

    def legacy_progress(message: str, fraction: float) -> None:
        if progress:
            progress(float(fraction), str(message))

    # V0.2.7.1 quality profiles:
    # - preview/fast share the lightweight interactive mesh path. This keeps the
    #   engineer-side Fast Render aligned with the client preview instead of
    #   rebuilding expensive crease-normal meshes on every export.
    # - perfect keeps PBR/environment/shadows, but avoids pathological browser
    #   workloads (90 FPS + 2.5M faces + 3.5x DPR + 4096/25-tap shadows).
    if quality == "perfect":
        effective_fps = int(scene.get("perfect_fps", 10) or 10)
        max_faces = int(scene.get("perfect_max_faces_per_mesh", 120000) or 120000)
    else:
        effective_fps = int(scene.get("fast_fps", 10) or 10)
        max_faces = int(scene.get("fast_max_faces_per_mesh", 120000) or 120000)
    return export_interactive_animation_html(
        generated_dir / "model.xml",
        adapter_path,
        destination,
        fps=effective_fps,
        max_faces_per_mesh=max_faces,
        schedule_resolver=lambda rows: rows,
        offset_resolver=offset_resolver,
        qpos_resolver=qpos_resolver,
        geom_to_file_builder=lambda _mj_model, _manifest: {},
        group_runtime_builder=lambda *_args, **_kwargs: {"items": []},
        world_group_points=lambda *_args, **_kwargs: np.empty((0, 3), dtype=float),
        progress_callback=legacy_progress,
    )
