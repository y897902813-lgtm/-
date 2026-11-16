from __future__ import annotations

import base64
import csv
import io
import json
import math
import os
import re
import shutil
import tempfile
import threading
import time
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from .models import MESH_EXTENSIONS, RENDER_IMAGE_EXTENSIONS, default_render_config, new_id, validate_model
from .material_presets import discover_material_presets, is_preview_file


MAX_MODEL_ASSET_BYTES = 2 * 1024 * 1024 * 1024
TRANSIENT_DATA_RETENTION_SECONDS = 60 * 60
TRASH_RETENTION_SECONDS = 15 * 60
MAX_MODEL_PREVIEW_BYTES = 8 * 1024 * 1024
MAX_TIME_SERIES_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_TIME_SERIES_UNPACKED_BYTES = 512 * 1024 * 1024
MAX_TIME_SERIES_FILES = 500


class ModelStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.models_root = self.root / "models"
        self.trash_root = self.root / "trash"
        self.animations_root = self.root / "animations"
        self.simulations_root = self.root / "simulations"
        self.render_assets_root = self.root / "render_assets"
        self.render_textures_root = self.render_assets_root / "textures"
        self.render_environments_root = self.render_assets_root / "environments"
        self._lock = threading.RLock()
        for folder in (self.models_root, self.trash_root, self.animations_root, self.simulations_root, self.render_textures_root, self.render_environments_root):
            folder.mkdir(parents=True, exist_ok=True)
        self._sanitize_user_settings_on_startup()
        # Runtime outputs are disposable.  A new VZ process starts with no old
        # simulation jobs or generated animation HTML; users who need an HTML
        # keep it through the existing download action.  Expired model-delete
        # undo folders are also physically removed here.
        self.cleanup_transient_data(max_age_seconds=None)
        self.cleanup_expired_trash()

    def time_series_directory(self, model_id: str, *, create: bool = False) -> Path:
        base = self._dir(model_id)
        target = (base / "time_series_library").resolve()
        if target.parent != base:
            raise ValueError("时序库路径越界")
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    def time_series_path(self, model_id: str, filename: str) -> Path:
        root = self.time_series_directory(model_id, create=True)
        safe_name = Path(str(filename or "")).name
        target = (root / safe_name).resolve()
        if target.parent != root or target.suffix.lower() != ".csv" or not target.is_file():
            raise KeyError(filename)
        return target

    def time_series_workspace_directory(self, model_id: str, *, create: bool = False) -> Path:
        """VZ-only editable copies, intentionally outside the Hub-synced library.

        ``replace_time_series_archive`` swaps only ``time_series_library``.  Keeping
        engineer edits in this sibling directory makes Hub refreshes incapable of
        overwriting VZ-local experiments and keeps the Hub source read-only by design.
        """
        base = self._dir(model_id)
        target = (base / "time_series_workspace").resolve()
        if target.parent != base:
            raise ValueError("VZ 时序工作区路径越界")
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _safe_time_series_name(value: str, fallback: str = "时序") -> str:
        stem = Path(str(value or "")).stem
        stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", stem).strip(" ._")[:96] or fallback
        return f"{stem}.csv"

    def _workspace_time_series_path(self, model_id: str, filename: str, *, must_exist: bool = True) -> Path:
        root = self.time_series_workspace_directory(model_id, create=True)
        safe_name = Path(str(filename or "")).name
        target = (root / safe_name).resolve()
        if target.parent != root or target.suffix.lower() != ".csv":
            raise ValueError("VZ 时序副本文件名无效")
        if must_exist and not target.is_file():
            raise KeyError(filename)
        return target

    @staticmethod
    def _number(value: Any, fallback: float = 0.0) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            result = float(fallback)
        return result if math.isfinite(result) else float(fallback)

    def _unique_workspace_time_series_path(self, model_id: str, requested: str, *, exclude: Path | None = None) -> Path:
        root = self.time_series_workspace_directory(model_id, create=True)
        safe = self._safe_time_series_name(requested)
        stem = Path(safe).stem
        candidate = (root / safe).resolve()
        serial = 2
        while candidate.exists() and (exclude is None or candidate != exclude):
            candidate = (root / f"{stem}_{serial}.csv").resolve()
            serial += 1
        return candidate

    @staticmethod
    def _write_csv_rows_atomic(path: Path, rows: list[list[str]]) -> None:
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        writer.writerows(rows)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text("\ufeff" + stream.getvalue(), encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def create_time_series_copy(self, model_id: str, requested_name: str = "") -> dict[str, Any]:
        """Create one editable VZ sequence from the model's current drive configuration."""
        model = self.get(model_id)
        requested = requested_name or f"{model.get('name') or '模型'}--VZ时序"
        target = self._unique_workspace_time_series_path(model_id, requested)
        rows: list[list[str]] = [
            ["VZ_TIME_SERIES", "1.0", "schema", "vz_time_series_library"],
            ["META", "model_id", str(model_id), "model_name", str(model.get("name") or model_id), "source", "vz_local"],
            ["COLUMNS", "record_type", "human_fields...", "json_payload"],
        ]
        for drive in model.get("drives", []) or []:
            if not isinstance(drive, dict):
                continue
            drive_id = str(drive.get("id") or new_id("drive"))
            drive_payload = {key: deepcopy(value) for key, value in drive.items() if key != "segments"}
            drive_payload["id"] = drive_id
            rows.append(["DRIVE", drive_id, str(drive.get("name") or drive_id), str(drive.get("joint_id") or ""), "", json.dumps(drive_payload, ensure_ascii=False, separators=(",", ":"))])
            for index, segment in enumerate(drive.get("segments", []) or []):
                if not isinstance(segment, dict):
                    continue
                payload = deepcopy(segment)
                segment_id = str(payload.get("id") or new_id("seg"))
                payload["id"] = segment_id
                payload.setdefault("name", f"运动段{index + 1}")
                payload.setdefault("profile", "s_curve")
                payload.setdefault("mode", "duration")
                start = self._number(payload.get("start"), 0.0)
                duration = max(0.0, self._number(payload.get("duration"), 1.0))
                speed = self._number(payload.get("speed"), 0.0)
                travel = self._number(payload.get("travel"), 0.0)
                if str(payload.get("mode")) == "speed" and abs(speed) > 1e-12:
                    duration = abs(travel / speed)
                end = start + duration
                rows.append(["SEGMENT", drive_id, segment_id, str(payload.get("name")), str(payload.get("profile")), str(start), str(end), "", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))])
                point_kind = "MAPPING_POINT" if str(payload.get("profile")) == "mapping" else "POINT"
                for point_index, point in enumerate(payload.get("points", []) or []):
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        rows.append([point_kind, drive_id, segment_id, str(point_index), str(point[0]), str(point[1])])
        rows.append(["RESULT_HEADER", "coordinate_system", "time_s", "curve", "value", "unit"])
        self._write_csv_rows_atomic(target, rows)
        return self.time_series_editor_manifest(model_id)

    def time_series_editor_manifest(self, model_id: str) -> dict[str, Any]:
        """Project Hub-synced sequences as read-only plus VZ-local editable copies."""
        self.get(model_id)
        items: list[dict[str, Any]] = []
        for scope, root, readonly in (
            ("hub", self.time_series_directory(model_id, create=True), True),
            ("local", self.time_series_workspace_directory(model_id, create=True), False),
        ):
            for path in sorted(root.glob("*.csv"), key=lambda item: item.name.casefold()):
                if not path.is_file() or path.is_symlink():
                    continue
                schedule = self._time_series_schedule(path)
                if schedule is None:
                    continue
                stat = path.stat()
                items.append({
                    "name": path.name, "scope": scope, "readonly": readonly,
                    "size": stat.st_size, "modified": stat.st_mtime, **schedule,
                })
        items.sort(key=lambda item: (0 if item["scope"] == "hub" else 1, -float(item["modified"]), str(item["name"]).casefold()))
        return {
            "items": items,
            "hub_count": sum(1 for item in items if item["scope"] == "hub"),
            "local_count": sum(1 for item in items if item["scope"] == "local"),
        }

    def copy_time_series(self, model_id: str, source_scope: str, filename: str, requested_name: str = "") -> dict[str, Any]:
        scope = str(source_scope or "hub").strip().lower()
        if scope == "hub":
            source = self.time_series_path(model_id, filename)
        elif scope == "local":
            source = self._workspace_time_series_path(model_id, filename)
        else:
            raise ValueError("时序来源只能是 hub 或 local")
        if self._time_series_schedule(source) is None:
            raise ValueError("只能复制主时序 CSV，映射表不能作为独立时序")
        requested = requested_name or f"{source.stem}--副本"
        target = self._unique_workspace_time_series_path(model_id, requested)
        shutil.copy2(source, target)
        return self.time_series_editor_manifest(model_id)

    def rename_time_series_copy(self, model_id: str, filename: str, requested_name: str) -> dict[str, Any]:
        source = self._workspace_time_series_path(model_id, filename)
        if self._time_series_schedule(source) is None:
            raise ValueError("只能重命名主时序副本")
        target = self._unique_workspace_time_series_path(model_id, requested_name, exclude=source)
        if target != source:
            source.replace(target)
        return self.time_series_editor_manifest(model_id)

    def delete_time_series_copy(self, model_id: str, filename: str) -> dict[str, Any]:
        source = self._workspace_time_series_path(model_id, filename)
        source.unlink()
        return self.time_series_editor_manifest(model_id)

    def update_time_series_segment(self, model_id: str, filename: str, drive_id: str, segment_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        path = self._workspace_time_series_path(model_id, filename)
        try:
            rows = list(csv.reader(io.StringIO(path.read_text("utf-8-sig"))))
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ValueError("VZ 时序副本无法读取") from exc
        if not rows or not rows[0] or rows[0][0] != "VZ_TIME_SERIES":
            raise ValueError("所选文件不是可编辑主时序 CSV")
        updated = False
        for row in rows:
            if len(row) < 9 or row[0] != "SEGMENT" or str(row[1]) != str(drive_id) or str(row[2]) != str(segment_id):
                continue
            try:
                payload = json.loads(row[8])
            except (TypeError, ValueError):
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            start = max(0.0, self._number(changes.get("start", row[5]), self._number(row[5], 0.0)))
            mode = str(changes.get("mode", payload.get("mode", "duration")) or "duration").strip().lower()
            if mode not in {"duration", "speed"}:
                raise ValueError("运动段模式必须是 duration 或 speed")
            duration_fallback = payload.get("duration", self._number(row[6], start) - start)
            duration = max(0.000001, self._number(changes.get("duration", duration_fallback), 1.0))
            speed = self._number(changes.get("speed", payload.get("speed", 0.0)), 0.0)
            travel = self._number(changes.get("travel", payload.get("travel", 0.0)), 0.0)
            if mode == "speed":
                if abs(speed) <= 1e-12:
                    raise ValueError("速度模式的速度不能为 0")
                duration = max(0.000001, abs(travel / speed))
            end = start + duration
            payload.update({"start_mode":"direct", "start":start, "mode":mode, "duration":duration, "speed":speed, "travel":travel})
            row[5] = f"{start:.12g}"
            row[6] = f"{end:.12g}"
            row[8] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            updated = True
            break
        if not updated:
            raise KeyError(f"{drive_id}/{segment_id}")
        self._write_csv_rows_atomic(path, rows)
        return self.time_series_editor_manifest(model_id)

    @staticmethod
    def _time_series_schedule(path: Path) -> dict[str, Any] | None:
        try:
            rows = list(csv.reader(io.StringIO(path.read_text("utf-8-sig"))))
        except (OSError, UnicodeError, csv.Error):
            return None
        if not rows or len(rows[0]) < 2 or rows[0][0] != "VZ_TIME_SERIES":
            return None
        drives: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for row in rows[1:]:
            if not row:
                continue
            kind = str(row[0]).strip()
            if kind == "DRIVE" and len(row) >= 6:
                drive_id = str(row[1]).strip()
                try:
                    payload = json.loads(row[5])
                except (ValueError, TypeError):
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                item = {
                    "id": drive_id,
                    "name": str(row[2] or payload.get("name") or drive_id),
                    "joint_id": str(row[3] or payload.get("joint_id") or ""),
                    "joint_name": str(row[4] or ""),
                    "enabled": bool(payload.get("enabled", True)),
                    "segments": [],
                }
                drives[drive_id] = item
                order.append(drive_id)
            elif kind == "SEGMENT" and len(row) >= 9:
                drive_id = str(row[1]).strip()
                drive = drives.get(drive_id)
                if drive is None:
                    continue
                try:
                    payload = json.loads(row[8])
                except (ValueError, TypeError):
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                def number(value: Any, fallback: Any = 0.0) -> float:
                    try:
                        result = float(value)
                    except (TypeError, ValueError):
                        try:
                            result = float(fallback)
                        except (TypeError, ValueError):
                            return 0.0
                    return result if math.isfinite(result) else 0.0
                start = number(row[5], payload.get("start", 0.0))
                end = number(row[6], start + number(payload.get("duration", 0.0)))
                if end < start:
                    start, end = end, start
                profile = str(row[4] or payload.get("profile") or "s_curve")
                drive["segments"].append({
                    "id": str(row[2] or payload.get("id") or ""),
                    "name": str(row[3] or payload.get("name") or "运动段"),
                    "profile": profile,
                    "start": start,
                    "end": end,
                    "duration": max(0.0, end - start),
                    "mode": str(payload.get("mode", "duration") or "duration"),
                    "speed": number(payload.get("speed", ""), 0.0),
                    "travel": number(payload.get("travel", ""), 0.0),
                    "variable_speed": profile in {"mapping", "points", "external_csv"},
                })
        # Project the same cumulative position information shown by Studio's
        # result Gantt so engineer/user WEB Gantts do not lose motion context.
        for drive in drives.values():
            position = 0.0
            ordered_segments = sorted(drive.get("segments", []), key=lambda item: (float(item.get("start", 0.0)), float(item.get("end", 0.0)), str(item.get("id", ""))))
            for segment in ordered_segments:
                travel = number(segment.get("travel", 0.0), 0.0)
                segment["position_start"] = position
                position += travel
                segment["position_end"] = position
            drive["segments"] = ordered_segments
        return {"schema_version": str(rows[0][1]), "drives": [drives[key] for key in order if key in drives]}

    def time_series_schedule(self, model_id: str, scope: str, filename: str) -> dict[str, Any]:
        """Return one parsed main time-series schedule from Hub or VZ workspace."""
        self.get(model_id)
        normalized_scope = str(scope or "hub").strip().lower()
        if normalized_scope == "hub":
            path = self.time_series_path(model_id, filename)
        elif normalized_scope == "local":
            path = self._workspace_time_series_path(model_id, filename)
        else:
            raise ValueError("时序来源只能是 hub 或 local")
        schedule = self._time_series_schedule(path)
        if schedule is None:
            raise ValueError("所选 CSV 不是可执行主时序")
        return schedule

    def time_series_manifest(self, model_id: str) -> dict[str, Any]:
        self.get(model_id)
        root = self.time_series_directory(model_id, create=True)
        files: list[dict[str, Any]] = []
        latest: dict[str, Any] | None = None
        latest_modified = -1.0
        series: list[dict[str, Any]] = []
        for path in sorted(root.glob("*.csv"), key=lambda item: item.name.casefold()):
            if not path.is_file() or path.is_symlink():
                continue
            stat = path.stat()
            schedule = self._time_series_schedule(path)
            kind = "combined" if schedule is not None else "mapping" if path.name.endswith("映射表格.csv") else "csv"
            files.append({"name": path.name, "size": stat.st_size, "modified": stat.st_mtime, "kind": kind})
            if schedule is not None:
                item = {"name": path.name, "scope": "hub", "readonly": True, "modified": stat.st_mtime, **schedule}
                series.append(item)
                if stat.st_mtime >= latest_modified:
                    latest_modified = stat.st_mtime
                    latest = item
        local_root = self.time_series_workspace_directory(model_id, create=True)
        for path in sorted(local_root.glob("*.csv"), key=lambda item: item.name.casefold()):
            if not path.is_file() or path.is_symlink():
                continue
            schedule = self._time_series_schedule(path)
            if schedule is None:
                continue
            stat = path.stat()
            series.append({"name": path.name, "scope": "local", "readonly": False, "modified": stat.st_mtime, **schedule})
        series.sort(key=lambda item: (-float(item.get("modified", 0.0)), str(item.get("name", "")).casefold()))
        return {"files": files, "count": len(files), "latest": latest, "series": series}

    def replace_time_series_archive(self, model_id: str, payload: bytes) -> dict[str, Any]:
        self.get(model_id)
        if len(payload) > MAX_TIME_SERIES_ARCHIVE_BYTES:
            raise ValueError("时序库压缩包不得超过 256 MiB")
        root = self.time_series_directory(model_id, create=True)
        staging = (root.parent / f".time_series_{uuid4().hex}.staging").resolve()
        backup = (root.parent / f".time_series_{uuid4().hex}.backup").resolve()
        staging.mkdir(parents=True, exist_ok=False)
        try:
            with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
                entries = [entry for entry in archive.infolist() if not entry.is_dir()]
                if len(entries) > MAX_TIME_SERIES_FILES:
                    raise ValueError("时序库 CSV 数量超过 500")
                total = sum(max(0, int(entry.file_size)) for entry in entries)
                if total > MAX_TIME_SERIES_UNPACKED_BYTES:
                    raise ValueError("时序库解压后不得超过 512 MiB")
                used: set[str] = set()
                for entry in entries:
                    raw_name = str(entry.filename or "").replace("\\", "/")
                    name = Path(raw_name).name
                    unix_mode = (int(entry.external_attr) >> 16) & 0o170000
                    if (
                        not name
                        or raw_name != name
                        or name in {".", ".."}
                        or Path(name).suffix.lower() != ".csv"
                        or name.casefold() in used
                        or unix_mode == 0o120000
                    ):
                        raise ValueError("时序库压缩包只能包含唯一的顶层普通 CSV 文件")
                    used.add(name.casefold())
                    data = archive.read(entry)
                    (staging / name).write_bytes(data)
            if root.exists():
                root.replace(backup)
            staging.replace(root)
            if backup.exists():
                shutil.rmtree(backup)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            if backup.exists() and not root.exists():
                backup.replace(root)
            raise
        return self.time_series_manifest(model_id)

    def _simulation_dir(self, job_id: str) -> Path:
        candidate = (self.simulations_root / str(job_id)).resolve()
        if candidate.parent != self.simulations_root:
            raise ValueError("仿真任务 ID 非法")
        return candidate

    def mark_simulation_active(self, job_id: str) -> Path:
        """Create/protect one transient simulation directory while it is in use."""
        folder = self._simulation_dir(job_id)
        with self._lock:
            folder.mkdir(parents=True, exist_ok=True)
            marker = folder / ".vz_active"
            marker.write_text(str(time.time()), encoding="utf-8")
        return folder

    def mark_simulation_complete(self, job_id: str) -> None:
        """Release a simulation directory and start its one-hour retention clock."""
        folder = self._simulation_dir(job_id)
        with self._lock:
            (folder / ".vz_active").unlink(missing_ok=True)
            if folder.exists():
                try:
                    os.utime(folder, None)
                except OSError:
                    pass

    def cleanup_transient_data(self, *, max_age_seconds: float | None = TRANSIENT_DATA_RETENTION_SECONDS) -> dict[str, int]:
        """Remove disposable runtime outputs while preserving all project data.

        Startup passes ``None`` and removes every leftover simulation entry and
        generated animation HTML. Runtime sweeps pass one hour. A simulation
        directory carrying ``.vz_active`` is never removed, which prevents a
        long-running request/job from racing with the periodic cleanup.
        """
        now = time.time()
        removed = {"simulations": 0, "animations": 0}
        with self._lock:
            for entry in list(self.simulations_root.iterdir()):
                try:
                    if entry.is_dir() and not entry.is_symlink() and (entry / ".vz_active").is_file():
                        continue
                    if max_age_seconds is not None:
                        age = now - entry.stat().st_mtime
                        if age < float(max_age_seconds):
                            continue
                    if entry.is_dir() and not entry.is_symlink():
                        shutil.rmtree(entry)
                    else:
                        entry.unlink(missing_ok=True)
                    removed["simulations"] += 1
                except FileNotFoundError:
                    continue
                except OSError:
                    # Busy/locked output is retried on the next sweep. Cleanup
                    # must never make the editor unavailable.
                    continue

            for path in list(self.animations_root.rglob("*.html")):
                if not path.is_file():
                    continue
                try:
                    if max_age_seconds is not None and now - path.stat().st_mtime < float(max_age_seconds):
                        continue
                    path.unlink()
                    removed["animations"] += 1
                except FileNotFoundError:
                    continue
                except OSError:
                    continue
        return removed

    def cleanup_expired_trash(self, *, now: float | None = None) -> int:
        """Physically remove model-delete undo folders after their 15-minute TTL."""
        current = time.time() if now is None else float(now)
        removed = 0
        with self._lock:
            for entry in list(self.trash_root.iterdir()):
                try:
                    if not entry.is_dir() or entry.is_symlink() or not entry.name.startswith("undo_"):
                        continue
                    meta_path = entry / "undo.json"
                    expires_at = 0.0
                    if meta_path.is_file():
                        try:
                            meta = json.loads(meta_path.read_text("utf-8"))
                            expires_at = float(meta.get("expires_at", 0) or 0)
                        except (OSError, ValueError, TypeError):
                            expires_at = 0.0
                    # Malformed orphaned undo folders receive the same 15-minute
                    # grace period based on directory mtime instead of living forever.
                    expired = expires_at <= current if expires_at > 0 else current - entry.stat().st_mtime >= TRASH_RETENTION_SECONDS
                    if not expired:
                        continue
                    shutil.rmtree(entry)
                    removed += 1
                except FileNotFoundError:
                    continue
                except OSError:
                    continue
        return removed

    def _dir(self, model_id: str) -> Path:
        candidate = (self.models_root / model_id).resolve()
        if candidate.parent != self.models_root:
            raise ValueError("模型 ID 非法")
        return candidate

    def _json(self, model_id: str) -> Path:
        return self._dir(model_id) / "model.json"

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    @staticmethod
    def _atomic_bytes(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    def model_preview_path(self, model_id: str) -> Path:
        return self._dir(model_id) / "derived" / "front_preview.png"

    def model_preview_meta_path(self, model_id: str) -> Path:
        return self._dir(model_id) / "derived" / "front_preview.json"

    def _preview_info_unlocked(self, model_id: str, revision: int | None = None) -> dict[str, Any]:
        image = self.model_preview_path(model_id)
        meta_path = self.model_preview_meta_path(model_id)
        if not image.is_file():
            return {"preview_url": "", "preview_revision": 0, "preview_stale": True, "preview_generated_at": 0}
        try:
            meta = json.loads(meta_path.read_text("utf-8")) if meta_path.is_file() else {}
        except (OSError, ValueError):
            meta = {}
        preview_revision = max(0, int(meta.get("revision", 0) or 0))
        current_revision = preview_revision if revision is None else int(revision)
        return {
            "preview_url": f"/api/models/{model_id}/preview.png",
            "preview_revision": preview_revision,
            "preview_stale": preview_revision != current_revision,
            "preview_generated_at": float(meta.get("generated_at", 0) or 0),
        }

    def save_model_preview(self, model_id: str, data_url: str, revision: int) -> dict[str, Any]:
        with self._lock:
            current = self.get(model_id)
            current_revision = int(current.get("revision", 1))
            if int(revision) != current_revision:
                raise ValueError("模型修订已变化，请按最新版本重新生成预览图")
            raw = str(data_url or "")
            prefix = "data:image/png;base64,"
            if not raw.startswith(prefix):
                raise ValueError("预览图必须是 PNG data URL")
            try:
                png = base64.b64decode(raw[len(prefix):], validate=True)
            except Exception as exc:
                raise ValueError("预览图 PNG 数据无效") from exc
            if not png or len(png) > MAX_MODEL_PREVIEW_BYTES:
                raise ValueError("预览图不得超过 8 MiB")
            if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) < 24 or png[12:16] != b"IHDR":
                raise ValueError("预览图 PNG 文件头无效")
            width = int.from_bytes(png[16:20], "big")
            height = int.from_bytes(png[20:24], "big")
            if width < 2 or height < 2 or width > 4096 or height > 4096:
                raise ValueError("预览图尺寸必须在 2–4096 像素范围内")
            self._atomic_bytes(self.model_preview_path(model_id), png)
            self._atomic_json(self.model_preview_meta_path(model_id), {
                "schema_version": 1, "model_id": model_id, "revision": current_revision,
                "view": "front", "horizontal_axis": "X", "vertical_axis": "Z", "depth_axis": "Y",
                "width": width, "height": height, "generated_at": time.time(),
            })
            return self._preview_info_unlocked(model_id, current_revision)


    @property
    def user_settings_path(self) -> Path:
        return self.root / "user_settings.json"

    def _read_user_settings_unlocked(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.user_settings_path.read_text("utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _render_quality_from_user_settings(payload: dict[str, Any]) -> str:
        client = payload.get("client", {}) if isinstance(payload.get("client", {}), dict) else {}
        quality = str(client.get("render_quality", "preview") or "preview").lower()
        return quality if quality in {"preview", "perfect"} else "preview"

    def _sanitize_user_settings_on_startup(self) -> None:
        """Migrate 0.2.15.x ephemeral browser state out of persistent storage.

        User-site camera and last-selected-model are session/navigation state, not
        project data.  V0.2.16 persists only the user's render-quality preference
        here; engineer render/camera configuration remains inside each model.
        """
        if not self.user_settings_path.exists():
            return
        with self._lock:
            payload = self._read_user_settings_unlocked()
            clean = {"client": {"render_quality": self._render_quality_from_user_settings(payload)}}
            if payload != clean:
                self._atomic_json(self.user_settings_path, clean)

    def get_user_settings(self) -> dict[str, Any]:
        with self._lock:
            payload = self._read_user_settings_unlocked()
            return {"render_quality": self._render_quality_from_user_settings(payload)}

    def set_user_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(settings, dict):
            raise ValueError("用户设置格式无效")
        render_quality = str(settings.get("render_quality", "preview") or "preview").lower()
        if render_quality not in {"preview", "perfect"}:
            raise ValueError("用户渲染模式必须是 preview 或 perfect")
        saved = {"render_quality": render_quality}
        with self._lock:
            # Write the complete allowed payload so legacy camera/model-selection
            # keys cannot survive an upgrade or an old browser request.
            self._atomic_json(self.user_settings_path, {"client": deepcopy(saved)})
        return deepcopy(saved)


    @property
    def model_library_path(self) -> Path:
        return self.root / "model_library.json"

    @property
    def control_graph_path(self) -> Path:
        return self.root / "control_graph.json"

    @staticmethod
    def _library_default() -> dict[str, Any]:
        return {"schema_version": 1, "folders": [], "model_folders": {}}

    def _read_model_library_unlocked(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.model_library_path.read_text("utf-8"))
            return payload if isinstance(payload, dict) else self._library_default()
        except (OSError, ValueError):
            return self._library_default()

    def _sanitize_model_library_unlocked(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        source = payload if isinstance(payload, dict) else self._read_model_library_unlocked()
        raw_folders = source.get("folders", []) if isinstance(source.get("folders"), list) else []
        folders: list[dict[str, Any]] = []
        ids: set[str] = set()
        for index, item in enumerate(raw_folders):
            if not isinstance(item, dict):
                continue
            folder_id = str(item.get("id", "")).strip()
            name = str(item.get("name", "")).strip()[:80]
            if not folder_id or not re.fullmatch(r"[A-Za-z0-9_-]+", folder_id) or folder_id in ids or not name:
                continue
            parent_id = str(item.get("parent_id", "root") or "root")
            try:
                order = int(item.get("order", index) or index)
            except (TypeError, ValueError):
                order = index
            folders.append({"id": folder_id, "name": name, "parent_id": parent_id, "order": order})
            ids.add(folder_id)
        by_id = {item["id"]: item for item in folders}
        clean_folders: list[dict[str, Any]] = []
        for item in folders:
            parent_id = item["parent_id"]
            if parent_id != "root" and parent_id not in by_id:
                item["parent_id"] = "root"
            elif parent_id != "root" and by_id[parent_id].get("parent_id", "root") != "root":
                # Fail closed on legacy/deep nesting by lifting to root instead of
                # retaining an unsupported third level.
                item["parent_id"] = "root"
            clean_folders.append(item)
        current_models = {path.parent.name for path in self.models_root.glob("*/model.json")}
        mappings = source.get("model_folders", {}) if isinstance(source.get("model_folders"), dict) else {}
        clean_map = {
            str(model_id): str(folder_id)
            for model_id, folder_id in mappings.items()
            if str(model_id) in current_models and str(folder_id) in by_id
        }
        return {"schema_version": 1, "folders": sorted(clean_folders, key=lambda x: (int(x.get("order", 0)), x["name"].casefold())), "model_folders": clean_map}

    def get_model_library(self) -> dict[str, Any]:
        with self._lock:
            raw = self._read_model_library_unlocked()
            clean = self._sanitize_model_library_unlocked(raw)
            if clean != raw:
                self._atomic_json(self.model_library_path, clean)
            return deepcopy(clean)

    def create_library_folder(self, name: str, parent_id: str = "root") -> dict[str, Any]:
        folder_name = str(name or "").strip()
        if not folder_name:
            raise ValueError("文件夹名称不能为空")
        if len(folder_name) > 80:
            raise ValueError("文件夹名称最长 80 个字符")
        with self._lock:
            library = self._sanitize_model_library_unlocked()
            parent_id = str(parent_id or "root")
            if parent_id != "root":
                parent = next((item for item in library["folders"] if item["id"] == parent_id), None)
                if parent is None:
                    raise KeyError(parent_id)
                if parent.get("parent_id", "root") != "root":
                    raise ValueError("模型文件夹最多支持两级分类")
            siblings = [item for item in library["folders"] if item.get("parent_id", "root") == parent_id]
            if any(item["name"].casefold() == folder_name.casefold() for item in siblings):
                raise ValueError("同级已存在同名文件夹")
            folder = {"id": new_id("folder"), "name": folder_name, "parent_id": parent_id, "order": len(siblings)}
            library["folders"].append(folder)
            self._atomic_json(self.model_library_path, library)
            return deepcopy(folder)

    def rename_library_folder(self, folder_id: str, name: str) -> dict[str, Any]:
        folder_name = str(name or "").strip()
        if not folder_name or len(folder_name) > 80:
            raise ValueError("文件夹名称必须为 1–80 个字符")
        with self._lock:
            library = self._sanitize_model_library_unlocked()
            folder = next((item for item in library["folders"] if item["id"] == folder_id), None)
            if folder is None:
                raise KeyError(folder_id)
            if any(item["id"] != folder_id and item.get("parent_id", "root") == folder.get("parent_id", "root") and item["name"].casefold() == folder_name.casefold() for item in library["folders"]):
                raise ValueError("同级已存在同名文件夹")
            folder["name"] = folder_name
            self._atomic_json(self.model_library_path, library)
            return deepcopy(folder)

    def delete_library_folder(self, folder_id: str) -> dict[str, Any]:
        with self._lock:
            library = self._sanitize_model_library_unlocked()
            if not any(item["id"] == folder_id for item in library["folders"]):
                raise KeyError(folder_id)
            if any(item.get("parent_id") == folder_id for item in library["folders"]):
                raise ValueError("请先删除或移动该文件夹下的子文件夹")
            if folder_id in set(library["model_folders"].values()):
                raise ValueError("请先把该文件夹内的模型移动到其他位置")
            library["folders"] = [item for item in library["folders"] if item["id"] != folder_id]
            self._atomic_json(self.model_library_path, library)
            return {"deleted": folder_id}

    def move_model_to_folder(self, model_id: str, folder_id: str = "root") -> dict[str, Any]:
        with self._lock:
            self.get(model_id)
            library = self._sanitize_model_library_unlocked()
            folder_id = str(folder_id or "root")
            if folder_id != "root" and not any(item["id"] == folder_id for item in library["folders"]):
                raise KeyError(folder_id)
            if folder_id == "root":
                library["model_folders"].pop(model_id, None)
            else:
                library["model_folders"][model_id] = folder_id
            self._atomic_json(self.model_library_path, library)
            return {"model_id": model_id, "folder_id": folder_id}

    @staticmethod
    def _graph_default() -> dict[str, Any]:
        return {"schema_version": 1, "nodes": [], "edges": [], "viewport": {"x": 0.0, "y": 0.0, "scale": 1.0}}

    @staticmethod
    def _finite_number(value: Any, default: float = 0.0) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            result = float(default)
        return result if math.isfinite(result) else float(default)

    def _sanitize_control_graph_unlocked(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {}
        raw_nodes = payload.get("nodes", []) if isinstance(payload.get("nodes"), list) else []
        if len(raw_nodes) > 200:
            raise ValueError("控制画布节点不得超过 200 个")
        nodes: list[dict[str, Any]] = []
        node_ids: set[str] = set()
        for item in raw_nodes:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("id", "")).strip()
            model_id = str(item.get("model_id", "")).strip()
            if not node_id or not re.fullmatch(r"[A-Za-z0-9_-]+", node_id) or node_id in node_ids:
                raise ValueError("控制画布节点 ID 非法或重复")
            if not model_id or not (self._dir(model_id) / "model.json").is_file():
                continue
            transform = item.get("transform_mm", [0, 0, 0])
            if not isinstance(transform, (list, tuple)) or len(transform) != 3:
                transform = [0, 0, 0]
            nodes.append({
                "id": node_id, "model_id": model_id,
                "x": self._finite_number(item.get("x"), 0), "y": self._finite_number(item.get("y"), 0),
                "w": max(150.0, min(560.0, self._finite_number(item.get("w"), 220))),
                "h": max(90.0, min(360.0, self._finite_number(item.get("h"), 132))),
                "preset_id": str(item.get("preset_id", "") or "")[:100],
                "transform_mm": [self._finite_number(value, 0) for value in transform],
                "alignment_reference": str(item.get("alignment_reference", "") or "") if str(item.get("alignment_reference", "") or "") in {"hard_point", "h_point"} else "",
            })
            node_ids.add(node_id)
        raw_edges = payload.get("edges", []) if isinstance(payload.get("edges"), list) else []
        if len(raw_edges) > 400:
            raise ValueError("控制画布连线不得超过 400 条")
        edges: list[dict[str, Any]] = []
        edge_ids: set[str] = set()
        pairs: set[tuple[str, str]] = set()
        for item in raw_edges:
            if not isinstance(item, dict):
                continue
            edge_id = str(item.get("id", "")).strip()
            source = str(item.get("source", "")).strip()
            target = str(item.get("target", "")).strip()
            if not edge_id or not re.fullmatch(r"[A-Za-z0-9_-]+", edge_id) or edge_id in edge_ids:
                raise ValueError("控制画布连线 ID 非法或重复")
            if source not in node_ids or target not in node_ids or source == target:
                continue
            if (source, target) in pairs:
                continue
            edges.append({"id": edge_id, "source": source, "target": target, "bend": self._finite_number(item.get("bend"), 0)})
            edge_ids.add(edge_id); pairs.add((source, target))
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        for edge in edges:
            adjacency[edge["source"]].append(edge["target"])
        visiting: set[str] = set(); visited: set[str] = set()
        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("控制画布连线不能形成循环")
            if node_id in visited:
                return
            visiting.add(node_id)
            for target in adjacency.get(node_id, []):
                visit(target)
            visiting.remove(node_id); visited.add(node_id)
        for node_id in node_ids:
            visit(node_id)
        viewport = payload.get("viewport", {}) if isinstance(payload.get("viewport"), dict) else {}
        scale = max(0.25, min(2.5, self._finite_number(viewport.get("scale"), 1)))
        return {"schema_version": 1, "nodes": nodes, "edges": edges, "viewport": {"x": self._finite_number(viewport.get("x"), 0), "y": self._finite_number(viewport.get("y"), 0), "scale": scale}}

    def get_control_graph(self) -> dict[str, Any]:
        with self._lock:
            try:
                raw = json.loads(self.control_graph_path.read_text("utf-8"))
            except (OSError, ValueError):
                raw = self._graph_default()
            clean = self._sanitize_control_graph_unlocked(raw)
            if raw != clean:
                self._atomic_json(self.control_graph_path, clean)
            return deepcopy(clean)

    def set_control_graph(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            clean = self._sanitize_control_graph_unlocked(payload)
            self._atomic_json(self.control_graph_path, clean)
            return deepcopy(clean)


    @staticmethod
    def _render_asset_relative(name: str) -> Path:
        raw = str(name or "").replace("\\", "/").strip()
        if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
            raise ValueError("渲染素材路径非法")
        parts = [part for part in raw.split("/") if part not in {"", "."}]
        if not parts or any(part == ".." for part in parts):
            raise ValueError("渲染素材路径非法")
        relative = Path(*parts)
        if relative.suffix.lower() not in RENDER_IMAGE_EXTENSIONS:
            raise ValueError("渲染素材仅支持 PNG/JPG/JPEG/WebP")
        return relative

    def render_asset_path(self, kind: str, name: str) -> Path:
        root = self.render_textures_root if kind == "textures" else self.render_environments_root if kind == "environments" else None
        if root is None:
            raise ValueError("渲染素材类型无效")
        relative = self._render_asset_relative(name)
        target = (root / relative).resolve()
        if root.resolve() not in target.parents:
            raise ValueError("渲染素材路径非法")
        if not target.is_file():
            raise FileNotFoundError(str(relative).replace("\\", "/"))
        return target

    def list_render_assets(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {"textures": [], "environments": []}
        for kind, root in (("textures", self.render_textures_root), ("environments", self.render_environments_root)):
            root.mkdir(parents=True, exist_ok=True)
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in RENDER_IMAGE_EXTENSIONS:
                    continue
                if kind == "textures" and is_preview_file(path):
                    continue
                rel = path.relative_to(root).as_posix()
                result[kind].append({"name": rel, "size": path.stat().st_size, "format": path.suffix.lower().lstrip(".")})
        result["material_presets"] = discover_material_presets(self.render_textures_root)
        return result

    def list(self) -> list[dict[str, Any]]:
        result = []
        with self._lock:
            for path in sorted(self.models_root.glob("*/model.json")):
                try:
                    model = json.loads(path.read_text("utf-8"))
                    source = model.get("_hub_source", {}) if isinstance(model.get("_hub_source"), dict) else {}
                    revision = int(model.get("revision", 1))
                    result.append({
                        "id": model["id"], "name": model["name"],
                        "description": model.get("description", ""),
                        "revision": revision,
                        "asset_count": len(model.get("assets", [])),
                        "drive_count": len(model.get("drives", [])),
                        "time_series_count": len(list(self.time_series_directory(str(model["id"]), create=True).glob("*.csv"))),
                        "source_name": str(source.get("original_name", "") or ""),
                        "source_project_id": str(source.get("project_id", "") or ""),
                        "hub_pushed": bool(source.get("published", False)),
                        "hub_managed": bool(source),
                        **self._preview_info_unlocked(str(model["id"]), revision),
                    })
                except (OSError, ValueError, KeyError):
                    continue
        return result

    def get(self, model_id: str) -> dict[str, Any]:
        with self._lock:
            path = self._json(model_id)
            if not path.is_file():
                raise KeyError(model_id)
            raw = json.loads(path.read_text("utf-8"))
            return validate_model(raw, expected_id=model_id, deduplicate_layer_assets=True)

    def create(self, payload: dict[str, Any], *, preserve_id: bool = False) -> dict[str, Any]:
        with self._lock:
            draft = deepcopy(payload)
            if not preserve_id:
                draft["id"] = new_id("model")
            draft["revision"] = 1
            model = validate_model(draft)
            folder = self._dir(model["id"])
            if folder.exists():
                raise FileExistsError(model["id"])
            (folder / "assets").mkdir(parents=True)
            self._atomic_json(folder / "model.json", model)
            return model

    def update(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = self.get(model_id)
            draft = deepcopy(payload)
            draft["revision"] = int(current.get("revision", 1)) + 1
            model = validate_model(draft, expected_id=model_id)
            self._atomic_json(self._json(model_id), model)
            return model

    @staticmethod
    def _asset_lookup_key(value: Any) -> str:
        return str(value or "").replace("\\", "/").strip().casefold()

    @classmethod
    def _relink_imported_meshes(cls, model: dict[str, Any], assets: list[dict[str, Any]]) -> int:
        """Bind imported mesh filenames to uniquely matching current-library assets.

        Modeling exchange files intentionally carry the original mesh filename rather
        than VZ's internal asset id.  Overwrite-import therefore keeps the current
        asset registry and resolves a mesh only when its path/name identifies exactly
        one asset.  Ambiguous or missing names remain untouched and asset_id stays
        empty so execution can report the missing reference later.
        """
        by_source: dict[str, list[dict[str, Any]]] = {}
        by_name: dict[str, list[dict[str, Any]]] = {}
        for asset in assets:
            source_key = cls._asset_lookup_key(asset.get("source_path"))
            name_key = cls._asset_lookup_key(asset.get("name"))
            if source_key:
                by_source.setdefault(source_key, []).append(asset)
            if name_key:
                by_name.setdefault(name_key, []).append(asset)

        relinked = 0
        for layer in model.get("layers", []):
            for mesh in layer.get("meshes", []):
                original = str(mesh.get("filename", "") or "").strip()
                mesh["asset_id"] = ""
                mesh["filename"] = original
                if not original:
                    continue
                full_key = cls._asset_lookup_key(original)
                basename_key = cls._asset_lookup_key(original.replace("\\", "/").rsplit("/", 1)[-1])
                candidates = by_source.get(full_key, [])
                if len(candidates) != 1:
                    candidates = by_name.get(basename_key, [])
                if len(candidates) != 1:
                    continue
                asset = candidates[0]
                mesh["asset_id"] = str(asset.get("id", ""))
                mesh["filename"] = str(asset.get("name", original))
                relinked += 1
        return relinked

    def overwrite_modeling_import(self, model_id: str, imported: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """Replace a model's modeling data while preserving its asset library."""
        with self._lock:
            current = self.get(model_id)
            draft = deepcopy(imported)
            # Overwrite keeps the current project identity and asset registry; only
            # the imported modeling payload replaces structural/modeling content.
            draft["id"] = model_id
            draft["name"] = current.get("name", draft.get("name", "导入建模信息"))
            draft["description"] = current.get("description", draft.get("description", ""))
            draft["assets"] = deepcopy(current.get("assets", []))
            # Hub refresh owns modeling structure and mesh membership, while these
            # values are maintained by the VZ engineer/user surfaces. Preserve
            # them across overwrite import so publishing a new Hub revision does
            # not erase local render/control reference data.
            for key in ("scene_coordinates", "render_scene", "presets", "memories"):
                if key in current:
                    draft[key] = deepcopy(current[key])
            relinked = self._relink_imported_meshes(draft, draft["assets"])
            return self.update(model_id, draft), relinked

    def copy(self, model_id: str, name: str | None = None) -> dict[str, Any]:
        with self._lock:
            source = self.get(model_id)
            clone = deepcopy(source)
            clone["id"] = new_id("model")
            clone["name"] = (name or f"{source['name']} - 副本").strip()
            clone["revision"] = 1
            clone.pop("_hub_source", None)
            clone = validate_model(clone)
            destination = self._dir(clone["id"])
            shutil.copytree(self._dir(model_id), destination)
            self._atomic_json(destination / "model.json", clone)
            return clone

    def delete(self, model_id: str) -> str:
        with self._lock:
            source = self._dir(model_id)
            if not (source / "model.json").is_file():
                raise KeyError(model_id)
            token = f"undo_{uuid4().hex}"
            destination = self.trash_root / token
            os.replace(source, destination)
            deleted_at = time.time()
            meta = {"model_id": model_id, "deleted_at": deleted_at, "expires_at": deleted_at + TRASH_RETENTION_SECONDS}
            self._atomic_json(destination / "undo.json", meta)
            library = self._sanitize_model_library_unlocked()
            library["model_folders"].pop(model_id, None)
            self._atomic_json(self.model_library_path, library)
            try:
                raw_graph = json.loads(self.control_graph_path.read_text("utf-8"))
            except (OSError, ValueError):
                raw_graph = self._graph_default()
            self._atomic_json(self.control_graph_path, self._sanitize_control_graph_unlocked(raw_graph))
            return token

    def undo_delete(self, token: str) -> dict[str, Any]:
        with self._lock:
            source = (self.trash_root / token).resolve()
            if source.parent != self.trash_root or not (source / "undo.json").is_file():
                raise KeyError(token)
            meta = json.loads((source / "undo.json").read_text("utf-8"))
            if float(meta.get("expires_at", 0)) < time.time():
                shutil.rmtree(source, ignore_errors=True)
                raise ValueError("撤销期限已过")
            destination = self._dir(str(meta["model_id"]))
            if destination.exists():
                raise FileExistsError(destination.name)
            (source / "undo.json").unlink(missing_ok=True)
            os.replace(source, destination)
            return self.get(destination.name)

    @staticmethod
    def _asset_suffix(filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix not in MESH_EXTENSIONS:
            raise ValueError("仅支持 STL 或 OBJ 数模")
        return suffix

    @staticmethod
    def _asset_source_path(filename: str, relative_path: str | None = None) -> str:
        """Normalize browser folder paths for display without trusting them as disk paths."""
        raw = str(relative_path or filename).replace("\\", "/").strip()
        if not raw:
            raise ValueError("缺少数模文件名")
        if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
            raise ValueError("数模相对路径非法")
        parts = [part for part in raw.split("/") if part not in {"", "."}]
        if not parts or any(part == ".." for part in parts):
            raise ValueError("数模相对路径非法")
        # webkitRelativePath starts with the selected folder.  Match the
        # second-generation Studio by keeping paths below that selected root.
        if relative_path and len(parts) > 1:
            parts = parts[1:]
        normalized = "/".join(parts)
        if Path(normalized).suffix.lower() not in MESH_EXTENSIONS:
            raise ValueError("仅支持 STL 或 OBJ 数模")
        return normalized[:512]

    @staticmethod
    def _detach_asset_references(model: dict[str, Any], asset_ids: set[str], asset_names: dict[str, str] | None = None) -> int:
        """Detach library IDs without deleting the layer's selected mesh filename.

        The mesh library is an option/source registry. A layer selection may outlive
        that registry entry (for example after external modeling-info import or a
        library cleanup), so removing an asset must turn the selection into a
        deliberate "missing" reference instead of silently deleting it.
        """
        if not asset_ids:
            return 0
        names = asset_names or {}
        detached = 0
        for layer in model.get("layers", []):
            for mesh in layer.get("meshes", []):
                asset_id = str(mesh.get("asset_id", ""))
                if asset_id not in asset_ids:
                    continue
                if not str(mesh.get("filename", "") or "").strip() and names.get(asset_id):
                    mesh["filename"] = names[asset_id]
                mesh["asset_id"] = ""
                detached += 1
            if str(layer.get("asset_id", "")) in asset_ids:
                layer.pop("asset_id", None)
        return detached

    def _prune_missing_asset_records(self, model_id: str, model: dict[str, Any]) -> list[str]:
        """Remove stale library metadata while preserving layer mesh selections."""
        assets_dir = (self._dir(model_id) / "assets").resolve()
        assets_dir.mkdir(parents=True, exist_ok=True)
        kept: list[dict[str, Any]] = []
        missing_ids: set[str] = set()
        missing_names: dict[str, str] = {}
        removed_names: list[str] = []
        for asset in model.get("assets", []):
            stored_name = Path(str(asset.get("stored_name", ""))).name
            candidate = (assets_dir / stored_name).resolve()
            if stored_name and candidate.parent == assets_dir and candidate.is_file():
                kept.append(asset)
            else:
                asset_id = str(asset.get("id", ""))
                missing_ids.add(asset_id)
                missing_names[asset_id] = str(asset.get("name") or stored_name)
                removed_names.append(str(asset.get("source_path") or asset.get("name") or stored_name))
        if missing_ids:
            model["assets"] = kept
            self._detach_asset_references(model, missing_ids, missing_names)
        return removed_names

    def repair_missing_assets(self, model_id: str) -> tuple[dict[str, Any], list[str]]:
        with self._lock:
            model = self.get(model_id)
            removed = self._prune_missing_asset_records(model_id, model)
            if removed:
                model = self.update(model_id, model)
            return model, removed

    def add_asset_stream(
        self,
        model_id: str,
        filename: str,
        stream: BinaryIO,
        length: int,
        *,
        relative_path: str | None = None,
    ) -> dict[str, Any]:
        """Store a browser-uploaded mesh as a verified binary file.

        The browser sends the original bytes directly, so large meshes do not
        suffer Base64 expansion. Folder uploads may additionally provide
        ``webkitRelativePath``; VZ stores that as metadata while keeping the
        actual on-disk filename generated by the server. This prevents duplicate
        names and path traversal while retaining the folder context in the UI.
        """
        suffix = self._asset_suffix(filename)
        source_path = self._asset_source_path(filename, relative_path)
        if length <= 0:
            raise ValueError("数模文件不能为空")
        if length > MAX_MODEL_ASSET_BYTES:
            raise ValueError("数模文件不得超过 2 GiB")
        with self._lock:
            model = self.get(model_id)
            asset_id = new_id("asset")
            safe_name = f"{asset_id}{suffix}"
            assets_dir = (self._dir(model_id) / "assets").resolve()
            assets_dir.mkdir(parents=True, exist_ok=True)
            target = (assets_dir / safe_name).resolve()
            if target.parent != assets_dir:
                raise ValueError("数模存储路径非法")
            temporary = assets_dir / f".{safe_name}.upload"
            remaining = length
            written = 0
            try:
                with temporary.open("wb") as handle:
                    while remaining:
                        chunk = stream.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError("上传中断：收到的文件内容不完整")
                        handle.write(chunk)
                        written += len(chunk)
                        remaining -= len(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())

                # A removable/mapped Windows drive can momentarily lose a child
                # directory. Recreate the destination once before surfacing a
                # storage error; the already-written temp file remains intact.
                try:
                    os.replace(temporary, target)
                except FileNotFoundError:
                    assets_dir.mkdir(parents=True, exist_ok=True)
                    if not temporary.is_file():
                        raise FileNotFoundError(f"数模上传临时文件丢失：{temporary}")
                    os.replace(temporary, target)

                if not target.is_file():
                    raise FileNotFoundError(f"数模写入后未找到目标文件：{target}")
                actual_size = target.stat().st_size
                if actual_size != written or written != length:
                    raise OSError(f"数模写入校验失败：期望 {length} 字节，实际 {actual_size} 字节")

                # A previous interrupted/older upload may have left metadata
                # pointing at a file that no longer exists. Once this write has
                # proven the storage root is healthy, prune those stale records
                # before saving the newly uploaded asset.
                self._prune_missing_asset_records(model_id, model)
                asset = {
                    "id": asset_id,
                    "name": Path(filename).name[:160],
                    "source_path": source_path,
                    "stored_name": safe_name,
                    "size": written,
                    "format": suffix[1:],
                    "render_config": default_render_config(),
                }
                model.setdefault("assets", []).append(asset)
                try:
                    return self.update(model_id, model)
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
            finally:
                temporary.unlink(missing_ok=True)

    def add_asset(self, model_id: str, filename: str, data_url: str) -> dict[str, Any]:
        """Backward-compatible Base64 upload path for older 0.2.x clients."""
        suffix = self._asset_suffix(filename)
        if "," not in data_url:
            raise ValueError("上传内容格式无效")
        try:
            raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("上传内容格式无效") from exc
        if not raw:
            raise ValueError("数模文件不能为空")
        if len(raw) > MAX_MODEL_ASSET_BYTES:
            raise ValueError("数模文件不得超过 2 GiB")
        from io import BytesIO
        return self.add_asset_stream(model_id, filename, BytesIO(raw), len(raw))

    def delete_asset(self, model_id: str, asset_id: str) -> dict[str, Any]:
        with self._lock:
            model = self.get(model_id)
            asset = next((item for item in model.get("assets", []) if item["id"] == asset_id), None)
            if not asset:
                raise KeyError(asset_id)
            self._detach_asset_references(model, {asset_id}, {asset_id: str(asset.get("name", ""))})
            model["assets"] = [item for item in model["assets"] if item["id"] != asset_id]
            result = self.update(model_id, model)
            (self._dir(model_id) / "assets" / asset["stored_name"]).unlink(missing_ok=True)
            return result

    def clear_assets(self, model_id: str) -> dict[str, Any]:
        """Clear the managed library while keeping layer selections as missing refs."""
        with self._lock:
            model = self.get(model_id)
            assets = list(model.get("assets", []))
            asset_ids = {str(asset.get("id", "")) for asset in assets}
            names = {str(asset.get("id", "")): str(asset.get("name", "")) for asset in assets}
            self._detach_asset_references(model, asset_ids, names)
            model["assets"] = []
            result = self.update(model_id, model)
            assets_dir = self._dir(model_id) / "assets"
            for asset in assets:
                (assets_dir / Path(str(asset.get("stored_name", ""))).name).unlink(missing_ok=True)
            return result

    def asset_path(self, model_id: str, stored_name: str) -> Path:
        base = (self._dir(model_id) / "assets").resolve()
        candidate = (base / Path(stored_name).name).resolve()
        if candidate.parent != base or not candidate.is_file():
            raise KeyError(stored_name)
        return candidate
