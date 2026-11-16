from __future__ import annotations

import copy
import os
import json
import re
import shutil
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse
import urllib.error
import urllib.request

from . import __version__
from .animation_export import export_animation_html
from .jobs import JobManager
from .models import new_id
from .modeling_exchange import export_modeling_exchange, import_modeling_exchange, is_modeling_exchange
from .mujoco_engine import MuJoCoUnavailable, build_mjcf, simulate, simulate_timeline
from .simulation import build_memory_jump_timeline, build_position_jump_timeline, build_table_timeline, build_timeline, timeline_values_at
from .scene_composition import compose_scene, compose_scene_timeline
from .store import MAX_MODEL_ASSET_BYTES, MAX_TIME_SERIES_ARCHIVE_BYTES, TRANSIENT_DATA_RETENTION_SECONDS, ModelStore


class VZApplication:
    def __init__(self, root: Path, data_root: Path | None = None):
        self.root = root.resolve()
        self.frontend = self.root / "frontend"
        self.store = ModelStore((data_root or (self.root / "data")).resolve())
        self.jobs = JobManager()
        self.hub_bridge_url = os.getenv("VZ_HUB_URL", "").strip().rstrip("/")
        self.hub_bridge_token = os.getenv("VZ_HUB_BRIDGE_TOKEN", "").strip()

    def notify_hub_model_removed(self, model: dict[str, Any]) -> dict[str, Any]:
        """Best-effort callback when an engineer removes a Hub-managed VZ model."""
        source = model.get("_hub_source") if isinstance(model.get("_hub_source"), dict) else {}
        project_id = str(source.get("project_id") or "").strip()
        model_id = str(model.get("id") or "").strip()
        if not project_id or not model_id or not bool(source.get("published", False)):
            return {"synced": False, "reason": "not_published_hub_model"}
        if not self.hub_bridge_url or not self.hub_bridge_token:
            return {"synced": False, "reason": "hub_bridge_disabled"}
        body = json.dumps({"project_id": project_id, "model_id": model_id}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.hub_bridge_url}/api/internal/vz/model-removed",
            data=body, method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
                "X-VZ-Bridge-Token": self.hub_bridge_token,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=3.0) as response:
                raw = response.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            return {"synced": True, "hub": payload}
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            return {"synced": False, "error": str(exc)}

    @staticmethod
    def _animation_filename(model: dict[str, Any], job_id: str, quality: str = "fast") -> str:
        safe = re.sub(r'[\\/:*?"<>|]+', "_", str(model.get("name", "模型"))).strip(" ._") or "模型"
        q = str(quality).lower()
        suffix = "HIGH_QUALITY" if q == "perfect" else "FAST"
        return f"{safe}_{suffix}_{job_id}.html"

    def _run_project_simulation_job(self, job_id: str, model_id: str, report: Any) -> dict[str, Any]:
        model = self.store.get(model_id)
        simulation_dir = self.store.mark_simulation_active(job_id)
        try:
            report(0.04, "正在生成 MuJoCo 轨迹")
            timeline = build_timeline(model, [])
            result = simulate_timeline(
                model,
                self.store._dir(model_id),
                simulation_dir,
                timeline,
                progress=lambda fraction, message: report(0.06 + 0.92 * fraction, message),
            )
        finally:
            self.store.mark_simulation_complete(job_id)
        return {
            "job_id": job_id,
            "summary": result["summary"],
            "schedule": result["schedule"],
            "result_url": f"/api/simulations/{job_id}/result.json",
            "xml_url": f"/api/simulations/{job_id}/model.xml",
        }

    def _run_project_job(self, job_id: str, model_id: str, quality: str, report: Any) -> dict[str, Any]:
        model = self.store.get(model_id)
        simulation_dir = self.store.mark_simulation_active(job_id)
        try:
            report(0.02, "正在生成 MuJoCo 轨迹")
            timeline = build_timeline(model, [])
            result = simulate_timeline(
                model,
                self.store._dir(model_id),
                simulation_dir,
                timeline,
                progress=lambda fraction, message: report(0.05 + 0.50 * fraction, message),
            )
            quality = str(quality).lower()
            if quality not in {"fast", "perfect"}:
                quality = "fast"
            filename = self._animation_filename(model, job_id, quality)
            target = self.store.animations_root / filename
            quality_label = "高质量渲染" if quality == "perfect" else "快速渲染"
            report(0.56, f"正在生成{quality_label} HTML")
            exported = export_animation_html(
                model,
                simulation_dir,
                target,
                quality=quality,
                render_assets_root=self.store.render_assets_root,
                progress=lambda fraction, message: report(0.56 + 0.43 * fraction, message),
            )
        finally:
            self.store.mark_simulation_complete(job_id)
        return {
            "job_id": job_id,
            "summary": result["summary"],
            "schedule": result["schedule"],
            "result_url": f"/api/simulations/{job_id}/result.json",
            "xml_url": f"/api/simulations/{job_id}/model.xml",
            "animation_url": f"/animations/{quote(filename)}",
            "animation_path": str(target),
            "animation": exported,
            "quality": quality,
        }

    def handler(self):
        application = self

        class Handler(BaseHTTPRequestHandler):
            server_version = f"VZStudio/{__version__}"

            def log_message(self, fmt: str, *args: Any) -> None:
                print(f"[{self.log_date_time_string()}] {fmt % args}")

            def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8", extra_headers: dict[str, str] | None = None) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' data: blob:; img-src 'self' data: blob:; connect-src 'self'")
                for name, value in (extra_headers or {}).items():
                    self.send_header(str(name), str(value))
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, payload: Any) -> None:
                self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

            def _body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 60 * 1024 * 1024:
                    raise ValueError("请求体过大")
                raw = self.rfile.read(length)
                value = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(value, dict):
                    raise ValueError("请求体必须是 JSON 对象")
                return value

            def _file(self, path: Path, content_type: str | None = None) -> None:
                if not path.is_file():
                    self._json(404, {"error": "资源不存在"})
                    return
                fixed_types = {
                    ".html": "text/html; charset=utf-8",
                    ".js": "text/javascript; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".json": "application/json; charset=utf-8",
                    ".svg": "image/svg+xml",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".stl": "model/stl",
                    ".obj": "text/plain; charset=utf-8",
                }
                mime = content_type or fixed_types.get(path.suffix.lower(), "application/octet-stream")
                self._send(200, path.read_bytes(), mime)

            def do_GET(self) -> None:  # noqa: N802
                try:
                    parsed = urlparse(self.path)
                    path = unquote(parsed.path)
                    if path in {"/", "/engineer", "/engineer/"}:
                        return self._file(application.frontend / "engineer.html", "text/html; charset=utf-8")
                    if path in {"/client", "/client/"}:
                        return self._file(application.frontend / "client.html", "text/html; charset=utf-8")
                    if path.startswith("/static/"):
                        target = (application.frontend / path.removeprefix("/static/")).resolve()
                        if target.parent != application.frontend:
                            return self._json(404, {"error": "资源不存在"})
                        return self._file(target)
                    if path == "/api/health":
                        return self._json(200, {"ok": True, "service": "VZ Studio", "version": __version__, "auth": False, "project_root": str(application.store.root)})
                    if path == "/api/render-assets":
                        assets = application.store.list_render_assets()
                        assets["root"] = str(application.store.render_assets_root)
                        return self._json(200, assets)
                    match = re.fullmatch(r"/render-assets/(textures|environments)/(.+)", path)
                    if match:
                        return self._file(application.store.render_asset_path(match.group(1), match.group(2)))
                    if path == "/api/model-library":
                        return self._json(200, application.store.get_model_library())
                    if path == "/api/control-graph":
                        return self._json(200, application.store.get_control_graph())
                    if path == "/api/models":
                        models = application.store.list()
                        # Hub-managed models with published=false are outside the
                        # shared push library and must disappear from both engineer
                        # and client catalogs. VZ-native/local copies are unaffected.
                        models = [item for item in models if not item.get("hub_managed") or item.get("hub_pushed")]
                        return self._json(200, {"models": models})
                    if path == "/api/user-settings":
                        return self._json(200, application.store.get_user_settings())
                    match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)", path)
                    if match:
                        return self._json(200, application.jobs.get(match.group(1)))
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/export-modeling-info", path)
                    if match:
                        model = application.store.get(match.group(1))
                        query = parse_qs(parsed.query)
                        include_measurements = str(query.get("include_measurements", ["true"])[0]).strip().lower() not in {"0", "false", "no", "off"}
                        return self._json(200, export_modeling_exchange(model, __version__, include_measurements=include_measurements))
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/preview\.png", path)
                    if match:
                        return self._file(application.store.model_preview_path(match.group(1)), "image/png")
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/time-series", path)
                    if match:
                        return self._json(200, application.store.time_series_manifest(match.group(1)))
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/time-series-editor", path)
                    if match:
                        return self._json(200, application.store.time_series_editor_manifest(match.group(1)))
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/time-series/(.+)", path)
                    if match:
                        return self._file(application.store.time_series_path(match.group(1), match.group(2)), "text/csv; charset=utf-8")
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)", path)
                    if match:
                        return self._json(200, {"model": application.store.get(match.group(1))})
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/assets/([^/]+)", path)
                    if match:
                        return self._file(application.store.asset_path(match.group(1), match.group(2)))
                    match = re.fullmatch(r"/animations/([^/]+\.html)", path)
                    if match:
                        name = Path(match.group(1)).name
                        target = (application.store.animations_root / name).resolve()
                        if target.parent != application.store.animations_root:
                            return self._json(404, {"error": "资源不存在"})
                        return self._file(target, "text/html; charset=utf-8")
                    match = re.fullmatch(r"/api/simulations/([A-Za-z0-9_-]+)/(model\.xml|result\.json|preview\.html)", path)
                    if match:
                        folder = application.store._simulation_dir(match.group(1))
                        name = match.group(2)
                        target = folder / ("generated/model.xml" if name == "model.xml" else name)
                        content_type = "application/xml; charset=utf-8" if name == "model.xml" else "text/html; charset=utf-8" if name == "preview.html" else "application/json; charset=utf-8"
                        return self._file(target, content_type)
                    self._json(404, {"error": "接口不存在"})
                except KeyError:
                    self._json(404, {"error": "模型、任务或资源不存在"})
                except Exception as exc:
                    self._json(400, {"error": str(exc)})

            def do_POST(self) -> None:  # noqa: N802
                try:
                    parsed = urlparse(self.path)
                    path = unquote(parsed.path)
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/time-series-sync", path)
                    if match and self.headers.get_content_type() != "application/json":
                        length = int(self.headers.get("Content-Length", "0"))
                        if length <= 0:
                            raise ValueError("时序库压缩包不能为空")
                        if length > MAX_TIME_SERIES_ARCHIVE_BYTES:
                            self._json(413, {"error": "时序库压缩包不得超过 256 MiB"})
                            return
                        payload_bytes = self.rfile.read(length)
                        manifest = application.store.replace_time_series_archive(match.group(1), payload_bytes)
                        return self._json(200, {"synced": True, **manifest})
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/assets", path)
                    if match and self.headers.get_content_type() != "application/json":
                        length = int(self.headers.get("Content-Length", "0"))
                        if length <= 0:
                            raise ValueError("数模文件不能为空")
                        if length > MAX_MODEL_ASSET_BYTES:
                            self._json(413, {"error": "数模文件不得超过 2 GiB"})
                            return
                        query = parse_qs(parsed.query)
                        filename = query.get("filename", [""])[0]
                        relative_path = query.get("relative_path", [""])[0] or None
                        if not filename:
                            raise ValueError("缺少数模文件名")
                        model = application.store.add_asset_stream(
                            match.group(1), filename, self.rfile, length, relative_path=relative_path
                        )
                        return self._json(201, {"model": model})

                    payload = self._body()
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/time-series-editor", path)
                    if match:
                        model_id = match.group(1)
                        action = str(payload.get("action", "") or "").strip().lower()
                        if action == "create":
                            result = application.store.create_time_series_copy(model_id, str(payload.get("name", "") or ""))
                        elif action == "copy":
                            result = application.store.copy_time_series(
                                model_id, str(payload.get("scope", "hub") or "hub"),
                                str(payload.get("name", "") or ""), str(payload.get("new_name", "") or ""),
                            )
                        elif action == "rename":
                            result = application.store.rename_time_series_copy(
                                model_id, str(payload.get("name", "") or ""), str(payload.get("new_name", "") or ""),
                            )
                        elif action == "delete":
                            result = application.store.delete_time_series_copy(model_id, str(payload.get("name", "") or ""))
                        elif action == "update_segment":
                            result = application.store.update_time_series_segment(
                                model_id, str(payload.get("name", "") or ""),
                                str(payload.get("drive_id", "") or ""), str(payload.get("segment_id", "") or ""),
                                payload.get("changes") if isinstance(payload.get("changes"), dict) else {},
                            )
                        else:
                            raise ValueError("未知时序库编辑动作")
                        return self._json(200, result)
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/assets/repair", path)
                    if match:
                        model, removed = application.store.repair_missing_assets(match.group(1))
                        return self._json(200, {"model": model, "removed": removed})
                    if path == "/api/models/import-modeling-info":
                        data = payload.get("data", payload)
                        if not is_modeling_exchange(data):
                            raise ValueError("所选 JSON 不是二代/VZ 建模信息（format 必须为 mujoco_modeling_exchange）")
                        mode = str(payload.get("mode", "new") or "new").strip().lower()
                        if mode not in {"new", "overwrite"}:
                            raise ValueError("建模信息导入模式必须为 new 或 overwrite")
                        import_measurements = bool(payload.get("import_measurements", True))
                        imported = import_modeling_exchange(data, import_measurements=import_measurements)
                        relinked_assets = 0
                        if mode == "overwrite":
                            model_id = str(payload.get("model_id", "") or "").strip()
                            if not model_id:
                                raise ValueError("覆盖导入必须指定当前模型 ID")
                            if not import_measurements:
                                current = application.store.get(model_id)
                                current_exchange = current.get("_modeling_exchange") if isinstance(current.get("_modeling_exchange"), dict) else {}
                                imported.setdefault("_modeling_exchange", {})["measurement_configuration"] = copy.deepcopy(
                                    current_exchange.get("measurement_configuration", {"pairs": []})
                                )
                            model, relinked_assets = application.store.overwrite_modeling_import(model_id, imported)
                            status = 200
                        else:
                            model = application.store.create(imported)
                            status = 201
                        return self._json(status, {
                            "model": model,
                            "import_mode": mode,
                            "relinked_assets": relinked_assets,
                            "migration": {
                                "source": "mujoco_modeling_exchange",
                                "schema_version": str(data.get("schema_version", "1.0")),
                            },
                        })
                    if path == "/api/models":
                        candidate = payload.get("model", payload)
                        if is_modeling_exchange(candidate):
                            raise ValueError("这是建模信息 JSON，请使用‘导入建模信息’入口")
                        model = payload.get("model") or {
                            "id": "temporary", "name": payload.get("name", "新模型"), "description": "",
                            "assets": [], "layers": [], "joints": [], "closures": [], "activity_parts": [], "drives": [], "presets": [], "memories": [],
                        }
                        return self._json(201, {"model": application.store.create(model)})
                    if path == "/api/undo":
                        return self._json(200, {"model": application.store.undo_delete(str(payload.get("token", "")))})
                    if path == "/api/user-settings":
                        return self._json(200, application.store.set_user_settings(payload))
                    if path == "/api/model-library/folders":
                        folder = application.store.create_library_folder(str(payload.get("name", "")), str(payload.get("parent_id", "root") or "root"))
                        return self._json(201, {"folder": folder, "library": application.store.get_model_library()})
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/preview", path)
                    if match:
                        preview = application.store.save_model_preview(
                            match.group(1), str(payload.get("data_url", "")), int(payload.get("revision", 0) or 0)
                        )
                        return self._json(201, {"preview": preview})
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/copy", path)
                    if match:
                        return self._json(201, {"model": application.store.copy(match.group(1), payload.get("name"))})
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/assets", path)
                    if match:
                        model = application.store.add_asset(match.group(1), str(payload.get("filename", "")), str(payload.get("data", "")))
                        return self._json(201, {"model": model})
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/mjcf", path)
                    if match:
                        model_id = match.group(1)
                        model = application.store.get(model_id)
                        job_id = new_id("mjcf")
                        simulation_dir = application.store.mark_simulation_active(job_id)
                        try:
                            generated = build_mjcf(model, application.store._dir(model_id), simulation_dir / "generated")
                        finally:
                            application.store.mark_simulation_complete(job_id)
                        return self._json(201, {"job_id": job_id, "xml": generated["xml"], "url": f"/api/simulations/{job_id}/model.xml"})
                    if path == "/api/fast-render-warmup":
                        model_id = str(payload.get("model_id", ""))
                        model = application.store.get(model_id)
                        benchmark_id = new_id("fastbench")
                        simulation_dir = application.store.mark_simulation_active(benchmark_id)
                        try:
                            timeline = build_timeline(model, [])
                            simulate_timeline(model, application.store._dir(model_id), simulation_dir, timeline)
                            (simulation_dir / "fast_benchmark.json").write_text(
                                json.dumps({"model_id": model_id, "warmup_renders": 0}, ensure_ascii=False), encoding="utf-8"
                            )
                        finally:
                            application.store.mark_simulation_complete(benchmark_id)
                        return self._json(201, {"benchmark_id": benchmark_id, "warmup_renders": 0})
                    if path == "/api/fast-render-benchmark":
                        model_id = str(payload.get("model_id", ""))
                        benchmark_id = str(payload.get("benchmark_id", ""))
                        model = application.store.get(model_id)
                        simulation_dir = application.store._simulation_dir(benchmark_id)
                        meta_path = simulation_dir / "fast_benchmark.json"
                        if not meta_path.is_file():
                            raise ValueError("快速渲染数据准备已失效，请重新点击快速渲染")
                        meta = json.loads(meta_path.read_text("utf-8"))
                        if str(meta.get("model_id", "")) != model_id:
                            raise ValueError("快速渲染模型不匹配")
                        application.store.mark_simulation_active(benchmark_id)
                        final_target = application.store.animations_root / application._animation_filename(model, benchmark_id, "fast")
                        try:
                            started = time.perf_counter()
                            export_animation_html(
                                model, simulation_dir, final_target, quality="fast",
                                render_assets_root=application.store.render_assets_root,
                            )
                            render_ms = (time.perf_counter() - started) * 1000.0
                        finally:
                            application.store.mark_simulation_complete(benchmark_id)
                        return self._send(
                            200, final_target.read_bytes(), "text/html; charset=utf-8",
                            {"X-VZ-Render-Samples": "1", "X-VZ-Warmup-Renders": "0", "X-VZ-Render-Time-Ms": f"{render_ms:.3f}"},
                        )
                    if path == "/api/export-animation":
                        model_id = str(payload.get("model_id", ""))
                        application.store.get(model_id)
                        quality = str(payload.get("quality", "fast")).lower()
                        if quality not in {"fast", "perfect"}:
                            raise ValueError("渲染模式必须是 fast 或 perfect")
                        kind = "animation_html_render_perfect" if quality == "perfect" else "animation_html_render_fast"
                        job_id = application.jobs.start(
                            kind,
                            lambda current_job_id, report: application._run_project_job(current_job_id, model_id, quality, report),
                        )
                        return self._json(202, {"job_id": job_id, "status_url": f"/api/jobs/{job_id}", "quality": quality})
                    if path == "/api/simulate":
                        scene_nodes = payload.get("scene_nodes")
                        if isinstance(scene_nodes, list) and scene_nodes:
                            if len(scene_nodes) > 50:
                                raise ValueError("联合仿真场景最多支持 50 个模型实例")
                            entries = []
                            for index, raw_node in enumerate(scene_nodes):
                                if not isinstance(raw_node, dict):
                                    raise ValueError(f"第 {index + 1} 个场景模型参数无效")
                                scene_model_id = str(raw_node.get("model_id", "") or "").strip()
                                if not scene_model_id:
                                    raise ValueError(f"第 {index + 1} 个场景模型缺少 model_id")
                                scene_model = application.store.get(scene_model_id)
                                schedule = None
                                series = raw_node.get("time_series") if isinstance(raw_node.get("time_series"), dict) else None
                                if series and str(series.get("name", "") or "").strip():
                                    schedule = application.store.time_series_schedule(
                                        scene_model_id, str(series.get("scope", "hub") or "hub"), str(series.get("name", "") or "")
                                    )
                                entries.append({
                                    "node": {
                                        "id": str(raw_node.get("id") or f"node_{index + 1}"),
                                        "model_id": scene_model_id,
                                        "transform_mm": raw_node.get("transform_mm", [0, 0, 0]),
                                    },
                                    "model": scene_model,
                                    "model_dir": application.store._dir(scene_model_id),
                                    "schedule": schedule,
                                })
                            composed = compose_scene(entries)
                            model = composed["model"]
                            timeline = compose_scene_timeline(model, composed["instances"])
                            job_id = new_id("sim")
                            simulation_dir = application.store.mark_simulation_active(job_id)
                            try:
                                source_dir = simulation_dir / "scene_source"
                                assets_dir = source_dir / "assets"
                                assets_dir.mkdir(parents=True, exist_ok=True)
                                for copy_plan in composed.get("asset_copies", []):
                                    source = Path(str(copy_plan.get("source", ""))).resolve()
                                    if not source.is_file():
                                        raise FileNotFoundError(f"联合仿真数模文件不存在：{source.name}")
                                    target = (assets_dir / Path(str(copy_plan.get("stored_name", ""))).name).resolve()
                                    if target.parent != assets_dir.resolve():
                                        raise ValueError("联合仿真数模目标路径越界")
                                    shutil.copy2(source, target)
                                result = simulate_timeline(model, source_dir, simulation_dir, timeline)
                                requested_quality = str(payload.get("render_quality", "preview") or "preview").lower()
                                if requested_quality == "fast":
                                    requested_quality = "preview"
                                if requested_quality not in {"preview", "perfect"}:
                                    raise ValueError("用户渲染模式必须是 preview 或 perfect")
                                target = simulation_dir / "preview.html"
                                export_animation_html(model, simulation_dir, target, quality=requested_quality, render_assets_root=application.store.render_assets_root)
                                final_positions = timeline_values_at(timeline, float(timeline.get("duration", 0.001)))
                            finally:
                                application.store.mark_simulation_complete(job_id)
                            return self._json(201, {
                                "job_id": job_id,
                                "summary": result["summary"],
                                "render_quality": requested_quality,
                                "url": f"/api/simulations/{quote(job_id)}/preview.html",
                                "final_positions": final_positions,
                                "scene": True,
                                "instance_count": len(entries),
                            })

                        model_id = str(payload.get("model_id", ""))
                        model = application.store.get(model_id)
                        if payload.get("use_project_schedule"):
                            job_id = application.jobs.start(
                                "simulation",
                                lambda current_job_id, report: application._run_project_simulation_job(current_job_id, model_id, report),
                            )
                            return self._json(202, {"job_id": job_id, "status_url": f"/api/jobs/{job_id}"})
                        steps = payload.get("steps", [])
                        if not isinstance(steps, list):
                            raise ValueError("控制步骤必须是列表")
                        memory_jump_id = str(payload.get("memory_jump_id", "") or "")
                        target_positions = payload.get("target_positions")
                        table_sequence = payload.get("table_sequence")
                        special_sources = int(bool(memory_jump_id)) + int(target_positions is not None) + int(table_sequence is not None)
                        if special_sources > 1:
                            raise ValueError("记忆位置、暂时记忆位置和外部表格控制不能同时提交")
                        if memory_jump_id:
                            timeline = build_memory_jump_timeline(model, memory_jump_id, payload.get("initial_positions"))
                        elif target_positions is not None:
                            timeline = build_position_jump_timeline(model, target_positions, payload.get("initial_positions"))
                        elif table_sequence is not None:
                            timeline = build_table_timeline(model, table_sequence, payload.get("initial_positions"))
                        else:
                            timeline = build_timeline(model, steps, payload.get("initial_positions"))
                        job_id = new_id("sim")
                        simulation_dir = application.store.mark_simulation_active(job_id)
                        try:
                            result = simulate_timeline(model, application.store._dir(model_id), simulation_dir, timeline)
                            requested_quality = str(payload.get("render_quality", "preview") or "preview").lower()
                            if requested_quality == "fast":
                                requested_quality = "preview"
                            if requested_quality not in {"preview", "perfect"}:
                                raise ValueError("用户渲染模式必须是 preview 或 perfect")
                            target = simulation_dir / "preview.html"
                            export_animation_html(model, simulation_dir, target, quality=requested_quality, render_assets_root=application.store.render_assets_root)
                            final_positions = timeline_values_at(timeline, float(timeline.get("duration", 0.001)))
                        finally:
                            application.store.mark_simulation_complete(job_id)
                        return self._json(201, {"job_id": job_id, "summary": result["summary"], "render_quality": requested_quality, "url": f"/api/simulations/{quote(job_id)}/preview.html", "final_positions": final_positions})
                    self._json(404, {"error": "接口不存在"})
                except MuJoCoUnavailable as exc:
                    self._json(503, {"error": str(exc)})
                except FileExistsError:
                    self._json(409, {"error": "目标已经存在"})
                except KeyError:
                    self._json(404, {"error": "模型或资源不存在"})
                except Exception as exc:
                    self._json(400, {"error": str(exc)})

            def do_PUT(self) -> None:  # noqa: N802
                try:
                    path = unquote(urlparse(self.path).path)
                    payload = self._body()
                    if path == "/api/control-graph":
                        return self._json(200, application.store.set_control_graph(payload.get("graph", payload)))
                    match = re.fullmatch(r"/api/model-library/folders/([A-Za-z0-9_-]+)", path)
                    if match:
                        folder = application.store.rename_library_folder(match.group(1), str(payload.get("name", "")))
                        return self._json(200, {"folder": folder, "library": application.store.get_model_library()})
                    match = re.fullmatch(r"/api/model-library/models/([A-Za-z0-9_-]+)", path)
                    if match:
                        moved = application.store.move_model_to_folder(match.group(1), str(payload.get("folder_id", "root") or "root"))
                        return self._json(200, {**moved, "library": application.store.get_model_library()})
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)", path)
                    if not match:
                        return self._json(404, {"error": "接口不存在"})
                    self._json(200, {"model": application.store.update(match.group(1), payload.get("model", payload))})
                except KeyError:
                    self._json(404, {"error": "模型、文件夹或资源不存在"})
                except Exception as exc:
                    self._json(400, {"error": str(exc)})

            def do_DELETE(self) -> None:  # noqa: N802
                try:
                    path = unquote(urlparse(self.path).path)
                    match = re.fullmatch(r"/api/model-library/folders/([A-Za-z0-9_-]+)", path)
                    if match:
                        deleted = application.store.delete_library_folder(match.group(1))
                        return self._json(200, {**deleted, "library": application.store.get_model_library()})
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/assets", path)
                    if match:
                        return self._json(200, {"model": application.store.clear_assets(match.group(1))})
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)/assets/([A-Za-z0-9_-]+)", path)
                    if match:
                        return self._json(200, {"model": application.store.delete_asset(match.group(1), match.group(2))})
                    match = re.fullmatch(r"/api/models/([A-Za-z0-9_-]+)", path)
                    if match:
                        model_id = match.group(1)
                        model = application.store.get(model_id)
                        undo_token = application.store.delete(model_id)
                        hub_sync = application.notify_hub_model_removed(model)
                        return self._json(200, {"undo_token": undo_token, "undo_seconds": 900, "hub_sync": hub_sync})
                    self._json(404, {"error": "接口不存在"})
                except KeyError:
                    self._json(404, {"error": "模型或资源不存在"})
                except Exception as exc:
                    self._json(400, {"error": str(exc)})

        return Handler


class VZThreadingHTTPServer(ThreadingHTTPServer):
    """HTTP server with lifecycle cleanup for all disposable runtime data."""

    lifecycle_cleanup_sweep_seconds = 60.0

    def __init__(self, server_address: tuple[str, int], application: VZApplication):
        self.application = application
        self._next_lifecycle_cleanup_monotonic = time.monotonic() + self.lifecycle_cleanup_sweep_seconds
        super().__init__(server_address, application.handler())

    def service_actions(self) -> None:
        # BaseServer.serve_forever() calls service_actions regularly. A one-minute
        # sweep gives completed simulation jobs/generated HTML a one-hour download
        # window, and also physically expires 15-minute model-delete undo data.
        now = time.monotonic()
        if now < self._next_lifecycle_cleanup_monotonic:
            return
        self._next_lifecycle_cleanup_monotonic = now + self.lifecycle_cleanup_sweep_seconds
        self.application.store.cleanup_transient_data(max_age_seconds=TRANSIENT_DATA_RETENTION_SECONDS)
        self.application.store.cleanup_expired_trash()


def make_server(root: Path, host: str, port: int, data_root: Path | None = None) -> ThreadingHTTPServer:
    application = VZApplication(root, data_root=data_root)
    return VZThreadingHTTPServer((host, port), application)
