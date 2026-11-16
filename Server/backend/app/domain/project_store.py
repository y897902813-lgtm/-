from __future__ import annotations

import json
import math
import hashlib
import logging
import re
import shutil
import copy
import os
from threading import RLock
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from ..config import MAX_ARCHIVE_VERSIONS, TRASH_RETENTION_DAYS
from ..core.atomic_io import atomic_write_text, atomic_write_bytes
from .models import ProjectSpec
from .motion import _load_csv_points, external_motion_summary, parse_external_motion_csv
from .expressions import ExpressionError


LOGGER = logging.getLogger(__name__)


class ProjectStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache_lock = RLock()
        self._list_cache: tuple[tuple[int, int], list[dict[str, object]]] | None = None
        self._path_cache: dict[str, Path] = {}
        self._migrate_legacy_unclassified_category()
        self._migrate_flat_project_layout()
        self._migrate_security_boundaries()

    @property
    def projects_root(self) -> Path:
        return self.root / "projects"

    @staticmethod
    def _atomic_json_write(path: Path, data: Any, *, sync_directory: bool = True) -> None:
        atomic_write_text(
            path, json.dumps(data, ensure_ascii=False, indent=2), sync_directory=sync_directory,
        )

    @staticmethod
    def _atomic_text_write(path: Path, text: str) -> None:
        atomic_write_text(path, text)

    @classmethod
    def _redact_legacy_credentials(cls, value: Any) -> tuple[Any, bool]:
        """Remove legacy cookie fields, including event path-diff records."""
        changed = False
        if isinstance(value, dict):
            if str(value.get("path", "")).endswith(("checked_out_session", "session_id")):
                return None, True
            cleaned: dict[str, Any] = {}
            for key, child in value.items():
                if key in {"checked_out_session", "session_id"}:
                    changed = True
                    continue
                redacted, child_changed = cls._redact_legacy_credentials(child)
                cleaned[key] = redacted
                changed = changed or child_changed
            return cleaned, changed
        if isinstance(value, list):
            cleaned_list: list[Any] = []
            for child in value:
                redacted, child_changed = cls._redact_legacy_credentials(child)
                changed = changed or child_changed
                if redacted is not None:
                    cleaned_list.append(redacted)
            return cleaned_list, changed
        return value, False

    def _migrate_security_boundaries(self) -> None:
        """Scrub legacy cookie tokens and normalize managed mesh roots."""
        if not self.projects_root.is_dir():
            return
        changed_items: list[dict[str, str]] = []
        for path in self.projects_root.rglob("*.json"):
            if path.name != "project.json" and path.parent.name != "versions":
                continue
            try:
                data = json.loads(path.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            changed = False
            data, credentials_changed = self._redact_legacy_credentials(data)
            if credentials_changed:
                LOGGER.warning("scrubbing legacy browser session token from %s", path)
                changed = True

            project_dir = path.parent if path.name == "project.json" else path.parent.parent
            assets_root = (project_dir / "assets").resolve()
            raw_mesh_root = str(data.get("mesh_root", "") or "").strip()
            if raw_mesh_root and not raw_mesh_root.startswith("@model_assets/"):
                candidate = Path(raw_mesh_root).expanduser()
                if candidate.is_absolute():
                    resolved = candidate.resolve()
                    if resolved == assets_root or assets_root in resolved.parents:
                        data["mesh_root"] = resolved.relative_to(project_dir.resolve()).as_posix()
                    else:
                        LOGGER.warning("invalidating legacy external mesh_root in %s: %s", path, raw_mesh_root)
                        data["mesh_root"] = ""
                    changed = True
                else:
                    resolved = (project_dir / candidate).resolve()
                    if resolved != assets_root and assets_root not in resolved.parents:
                        LOGGER.warning("invalidating escaping mesh_root in %s: %s", path, raw_mesh_root)
                        data["mesh_root"] = ""
                        changed = True
            if changed:
                try:
                    self._atomic_json_write(path, data)
                    changed_items.append({"path": str(path.relative_to(self.root)), "reason": "project/version security normalization"})
                except OSError as exc:
                    LOGGER.error("security migration failed for %s: %s", path, exc)
        for events_path in self.projects_root.rglob("core/events.jsonl"):
            output: list[str] = []
            changed = False
            try:
                for line in events_path.read_text("utf-8").splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        output.append(line)
                        continue
                    event, event_changed = self._redact_legacy_credentials(event)
                    changed = changed or event_changed
                    output.append(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
                if changed:
                    self._atomic_text_write(events_path, "\n".join(output) + ("\n" if output else ""))
                    changed_items.append({"path": str(events_path.relative_to(self.root)), "reason": "event credential redaction"})
            except OSError as exc:
                LOGGER.error("event security migration failed for %s: %s", events_path, exc)
        if changed_items:
            audit = {
                "migration": "2.3.9.8.2-security-boundaries",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "items": changed_items,
            }
            self._atomic_json_write(self.root / "security_migration_2.3.9.8.2.json", audit)
            LOGGER.warning("security migration updated %d project/version/event files", len(changed_items))

    def _migrate_legacy_unclassified_category(self) -> None:
        """Hide and merge the legacy visible ``未分类`` model-type alias.

        ``None`` remains the internal compatibility sentinel for uncategorized
        projects, but neither spelling is a real model type.  Older Windows and
        Linux data roots may still contain ``projects/未分类`` or catalog metadata
        entries for it; merge project directories into ``projects/None`` and
        remove the alias from model-type metadata without deleting unknown files.
        """
        legacy_dir = self.projects_root / "未分类"
        canonical_dir = self.projects_root / "None"
        migrated: list[dict[str, str]] = []
        if legacy_dir.is_dir():
            canonical_dir.mkdir(parents=True, exist_ok=True)
            for project_path in list(legacy_dir.rglob("project.json")):
                try:
                    data = json.loads(project_path.read_text("utf-8"))
                    project_id = str(data.get("id") or project_path.parent.name)
                    if not re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
                        LOGGER.error("legacy unclassified model has invalid id: %s", project_path)
                        continue
                    target = (canonical_dir / project_id).resolve()
                    if target.exists() and target != project_path.parent.resolve():
                        LOGGER.error("legacy unclassified migration target exists: %s", target)
                        continue
                    data["category"] = "None"
                    self._atomic_json_write(project_path, data)
                    source = project_path.parent.resolve()
                    source.replace(target)
                    migrated.append({"project_id": project_id, "from": str(source), "to": str(target)})
                except (OSError, ValueError, TypeError) as exc:
                    LOGGER.error("unable to migrate legacy unclassified project %s: %s", project_path, exc)
            # Remove now-empty legacy directory levels only.  Unknown files are
            # preserved rather than being silently deleted.
            for directory in sorted((path for path in legacy_dir.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            try:
                legacy_dir.rmdir()
            except OSError:
                pass

        category_path = self.root / "project_categories.json"
        try:
            raw_categories = json.loads(category_path.read_text("utf-8"))
        except (OSError, ValueError):
            raw_categories = None
        if isinstance(raw_categories, list):
            cleaned = [str(item).strip() for item in raw_categories if str(item).strip() not in {"None", "未分类"}]
            if cleaned != raw_categories:
                self._atomic_json_write(category_path, cleaned)

        order = self._model_type_order()
        changed_order = False
        if "" in order:
            cleaned_root = [name for name in order[""] if name not in {"None", "未分类"}]
            if cleaned_root != order[""]:
                changed_order = True
                if cleaned_root:
                    order[""] = cleaned_root
                else:
                    order.pop("", None)
        for parent in list(order):
            if parent in {"None", "未分类"} or parent.startswith("未分类/"):
                order.pop(parent, None)
                changed_order = True
        if changed_order:
            self._save_model_type_order(order)

        owners = self._model_type_owners()
        cleaned_owners = {
            path: owner for path, owner in owners.items()
            if path not in {"None", "未分类"} and not path.startswith("未分类/")
        }
        if cleaned_owners != owners:
            self._save_model_type_owners(cleaned_owners)

        if migrated:
            self._atomic_json_write(self.root / "layout_migration_2.9.2.1_unclassified.json", {
                "migrated_at": datetime.now(timezone.utc).isoformat(),
                "items": migrated,
            })

    @property
    def model_asset_libraries_root(self) -> Path:
        return (self.root / "model_asset_libraries").resolve()

    @staticmethod
    def _casefold_directory_child(parent: Path, name: str) -> Path | None:
        """Return one existing directory child with portable case matching.

        Exact spelling always wins. If it does not exist, a single casefold
        match is accepted so references exported on Windows remain usable on
        Linux. Ambiguous Linux-only duplicates are never guessed.
        """
        exact = parent / name
        if exact.is_dir() and not exact.is_symlink():
            return exact
        if not parent.is_dir():
            return None
        matches = [
            child for child in parent.iterdir()
            if child.is_dir() and not child.is_symlink()
            and child.name.casefold() == name.casefold()
        ]
        return matches[0] if len(matches) == 1 else None

    def canonical_model_asset_category(self, category: str) -> str:
        """Use existing on-disk category spelling when it differs only by case."""
        parts = self._category_parts(self.normalize_category(category))
        current = self.model_asset_libraries_root
        actual: list[str] = []
        for part in parts:
            child = self._casefold_directory_child(current, part)
            if child is None:
                return "/".join(parts)
            actual.append(child.name)
            current = child
        return "/".join(actual)

    def model_asset_library_root(self, category: str, *, create: bool = False) -> Path:
        value = self.canonical_model_asset_category(category)
        root = self.model_asset_libraries_root.joinpath(*self._category_parts(value)).resolve()
        if self.model_asset_libraries_root not in root.parents and root != self.model_asset_libraries_root:
            raise ValueError("模型类型数模资产库路径越界")
        if create:
            root.mkdir(parents=True, exist_ok=True)
        return root

    def canonical_model_asset_folder_name(self, category: str, folder_name: str) -> str:
        clean = self._category_parts(folder_name)[-1]
        if "/" in str(folder_name).replace("\\", "/"):
            raise ValueError("数模资产文件夹名称只能是一层")
        root = self.model_asset_library_root(category)
        existing = self._casefold_directory_child(root, clean)
        return existing.name if existing is not None else clean

    def model_asset_reference(self, category: str, folder_name: str) -> str:
        value = self.canonical_model_asset_category(category)
        clean = self.canonical_model_asset_folder_name(value, folder_name)
        return f"@model_assets/{value}/{clean}"

    def resolve_model_asset_reference(self, reference: str, *, create: bool = False) -> Path:
        raw = str(reference or "").strip()
        prefix = "@model_assets/"
        if not raw.startswith(prefix):
            raise ValueError("不是模型类型公共数模资产路径")
        parts = self._category_parts(raw[len(prefix):])
        if len(parts) < 2:
            raise ValueError("公共数模资产路径缺少文件夹")
        category, folder = "/".join(parts[:-1]), parts[-1]
        category = self.canonical_model_asset_category(category)
        root = self.model_asset_library_root(category, create=create)
        existing = self._casefold_directory_child(root, folder)
        resolved = (existing if existing is not None else root / folder).resolve()
        if resolved.parent != root:
            raise ValueError("公共数模资产文件夹路径越界")
        if create:
            resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    MODEL_ASSET_METADATA_NAME = ".mujoco_asset_meta.json"

    @classmethod
    def _model_asset_metadata_path(cls, folder: Path) -> Path:
        return folder / cls.MODEL_ASSET_METADATA_NAME

    @classmethod
    def _read_model_asset_metadata(cls, folder: Path) -> dict[str, Any]:
        path = cls._model_asset_metadata_path(folder)
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text("utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @classmethod
    def _write_model_asset_metadata(cls, folder: Path, **updates: Any) -> dict[str, Any]:
        current = cls._read_model_asset_metadata(folder)
        now = datetime.now(timezone.utc).isoformat()
        current.update({key: value for key, value in updates.items() if value is not None})
        current.setdefault("created_at", now)
        current["updated_at"] = now
        cls._atomic_json_write(cls._model_asset_metadata_path(folder), current)
        return current

    def list_model_asset_folders(self, category: str) -> list[dict[str, Any]]:
        # A read must never create a second differently-cased directory on Linux.
        root = self.model_asset_library_root(category)
        if not root.is_dir():
            return []
        result = []
        for folder in sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink()), key=lambda p: p.name.casefold()):
            files = [p for p in folder.rglob("*") if p.is_file() and not p.is_symlink() and p.name != self.MODEL_ASSET_METADATA_NAME]
            meshes = [p for p in files if p.suffix.lower() in {".stl", ".obj"}]
            metadata = self._read_model_asset_metadata(folder)
            result.append({
                "name": folder.name,
                "reference": self.model_asset_reference(category, folder.name),
                "file_count": len(files),
                "mesh_count": len(meshes),
                "size_bytes": sum(p.stat().st_size for p in files),
                "modified": max([folder.stat().st_mtime, *[p.stat().st_mtime for p in files]]),
                "uploaded_by": str(metadata.get("uploaded_by", "") or ""),
                "created_at": str(metadata.get("created_at", "") or ""),
                "updated_at": str(metadata.get("updated_at", "") or ""),
            })
        return result

    def model_asset_folder_inventory(self, category: str, folder_name: str) -> list[dict[str, Any]]:
        reference = self.model_asset_reference(category, folder_name)
        root = self.resolve_model_asset_reference(reference)
        if not root.is_dir():
            raise ValueError("数模版本文件夹不存在")
        items: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
            if path.is_symlink() or path.name == self.MODEL_ASSET_METADATA_NAME:
                continue
            relative = path.relative_to(root).as_posix()
            if path.is_dir():
                items.append({"path": relative, "name": path.name, "kind": "folder"})
            elif path.is_file():
                stat = path.stat()
                items.append({
                    "path": relative, "name": path.name, "kind": "file",
                    "extension": path.suffix.lower(), "size": stat.st_size, "modified": stat.st_mtime,
                })
        return items

    def create_model_asset_folder(self, category: str, folder_name: str, *, uploaded_by: str = "") -> tuple[str, Path]:
        reference = self.model_asset_reference(category, folder_name)
        path = self.resolve_model_asset_reference(reference)
        if path.exists():
            raise ValueError("同名数模资产文件夹已存在")
        path.mkdir(parents=True)
        self._write_model_asset_metadata(path, uploaded_by=str(uploaded_by or ""))
        return reference, path

    def copy_model_asset_folder(
        self, category: str, source_name: str, target_name: str, *,
        max_files: int = 10000, max_bytes: int = 8 * 1024**3, uploaded_by: str = "",
    ) -> tuple[str, Path]:
        source_ref = self.model_asset_reference(category, source_name)
        source = self.resolve_model_asset_reference(source_ref)
        if not source.is_dir():
            raise ValueError("源数模版本文件夹不存在")
        target_ref = self.model_asset_reference(category, target_name)
        target = self.resolve_model_asset_reference(target_ref)
        if target.exists():
            raise ValueError("同名数模资产文件夹已存在")
        file_count = 0
        total_bytes = 0
        for path in source.rglob("*"):
            if path.is_symlink():
                raise ValueError("数模版本包含符号链接，禁止复制")
            if not path.is_file():
                continue
            file_count += 1
            total_bytes += path.stat().st_size
            if file_count > max_files:
                raise ValueError(f"数模版本文件数量不能超过 {max_files}")
            if total_bytes > max_bytes:
                raise ValueError("数模版本总大小超过复制上限")
        try:
            shutil.copytree(source, target, copy_function=shutil.copy2)
            self._write_model_asset_metadata(
                target,
                uploaded_by=str(uploaded_by or self._read_model_asset_metadata(source).get("uploaded_by", "") or ""),
                source_reference=source_ref,
            )
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return target_ref, target

    def rename_model_asset_folder(self, category: str, source_name: str, target_name: str) -> dict[str, Any]:
        """Rename one public mesh folder and migrate every live project reference atomically.

        This follows the same ownership/cascade pattern already used by model-type
        rename/move: the shared directory moves once, all authoritative project.json
        references are rewritten, and any partial failure restores both sides.
        """
        source_name = str(source_name or "").strip()
        target_name = str(target_name or "").strip()
        if not source_name or not target_name:
            raise ValueError("数模资产文件夹名称不能为空")
        value = self.canonical_model_asset_category(category)
        source_ref = self.model_asset_reference(value, source_name)
        source = self.resolve_model_asset_reference(source_ref)
        if not source.is_dir() or source.is_symlink():
            raise ValueError("源数模版本文件夹不存在")
        clean = self._category_parts(target_name)[-1]
        if "/" in str(target_name).replace("\\", "/"):
            raise ValueError("数模资产文件夹名称只能是一层")
        root = self.model_asset_library_root(value)
        target = (root / clean).resolve()
        if target.parent != root:
            raise ValueError("公共数模资产文件夹路径越界")
        if source.name == clean:
            return {"source": source_ref, "target": source_ref, "affected_project_ids": []}
        conflicting = self._casefold_directory_child(root, clean)
        if conflicting is not None and conflicting.resolve() != source.resolve():
            raise ValueError("同名数模资产文件夹已存在")

        target_ref = f"@model_assets/{value}/{clean}"
        documents: list[tuple[Path, str, dict[str, Any]]] = []
        for item in self.list():
            project_id = str(item.get("id", ""))
            if not project_id or str(item.get("mesh_root", "")).casefold() != source_ref.casefold():
                continue
            project_path = self._directory(project_id) / "project.json"
            original = project_path.read_text("utf-8")
            documents.append((project_path, original, json.loads(original)))

        temporary: Path | None = None
        moved = False
        try:
            if source.name.casefold() == clean.casefold():
                temporary = root / f".rename_{hashlib.sha256(source.name.encode('utf-8')).hexdigest()[:12]}"
                if temporary.exists():
                    raise ValueError("数模资产重命名临时路径冲突")
                source.replace(temporary)
                temporary.replace(target)
            else:
                if target.exists():
                    raise ValueError("同名数模资产文件夹已存在")
                source.replace(target)
            moved = True
            affected: list[str] = []
            for project_path, _original, data in documents:
                if str(data.get("mesh_root", "")).casefold() != source_ref.casefold():
                    continue
                data["mesh_root"] = target_ref
                self._atomic_json_write(project_path, data)
                affected.append(str(data.get("id", project_path.parent.name)))
        except Exception:
            for project_path, original, _data in documents:
                try:
                    atomic_write_text(project_path, original)
                except OSError:
                    LOGGER.exception("failed to rollback mesh-root reference in %s", project_path)
            try:
                if moved and target.exists():
                    target.replace(source)
                elif temporary is not None and temporary.exists():
                    temporary.replace(source)
            except OSError:
                LOGGER.exception("failed to rollback model asset folder rename %s -> %s", source, target)
            raise
        self.invalidate()
        return {"source": source_ref, "target": target_ref, "affected_project_ids": affected}

    def delete_model_asset_folder(self, category: str, folder_name: str) -> str:
        reference = self.model_asset_reference(category, folder_name)
        path = self.resolve_model_asset_reference(reference)
        if not path.is_dir():
            raise ValueError("数模版本文件夹不存在")
        if path.is_symlink():
            raise ValueError("拒绝删除符号链接数模目录")
        shutil.rmtree(path)
        return reference

    def clear_model_asset_folder(self, category: str, folder_name: str) -> dict[str, int]:
        root = self.resolve_model_asset_reference(self.model_asset_reference(category, folder_name))
        if not root.is_dir():
            raise ValueError("数模版本文件夹不存在")
        if root.is_symlink():
            raise ValueError("拒绝清空符号链接数模目录")
        children = [child for child in root.iterdir() if child.name != self.MODEL_ASSET_METADATA_NAME]
        for child in children:
            if child.is_symlink():
                raise ValueError("数模版本包含符号链接，拒绝清空")
            if child.is_dir() and any(path.is_symlink() for path in child.rglob("*")):
                raise ValueError("数模版本包含符号链接，拒绝清空")
        deleted_files = 0
        deleted_directories = 0
        for child in children:
            if child.is_dir():
                descendants = list(child.rglob("*"))
                deleted_files += sum(1 for path in descendants if path.is_file())
                deleted_directories += 1 + sum(1 for path in descendants if path.is_dir())
                shutil.rmtree(child)
            elif child.is_file():
                child.unlink()
                deleted_files += 1
        self._write_model_asset_metadata(root)
        return {"deleted_files": deleted_files, "deleted_directories": deleted_directories}

    def delete_model_asset_file(self, category: str, folder_name: str, asset_path: str) -> Path:
        root = self.resolve_model_asset_reference(self.model_asset_reference(category, folder_name))
        relative = Path(str(asset_path).replace("\\", "/"))
        if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("数模文件路径无效")
        target = (root / relative).resolve()
        if root.resolve() not in target.parents or not target.is_file() or target.is_symlink():
            raise ValueError("数模文件不存在")
        target.unlink()
        for parent in target.parents:
            if parent == root:
                break
            try:
                parent.rmdir()
            except OSError:
                break
        return target

    def resolve_mesh_root(self, project_id: str, mesh_root: str, *, create: bool = False) -> Path:
        project_dir = self._directory(project_id).resolve()
        assets_root = (project_dir / "assets").resolve()
        raw = str(mesh_root or "").strip()
        if raw.startswith("@model_assets/"):
            return self.resolve_model_asset_reference(raw, create=create)
        candidate = Path(raw) if raw else Path("assets")
        if candidate.is_absolute():
            resolved = candidate.expanduser().resolve()
        else:
            if any(part in {"..", ""} for part in candidate.parts):
                raise ValueError("mesh_root 必须是项目 assets/ 下的相对路径或模型类型公共资产路径")
            resolved = (project_dir / candidate).resolve()
        if resolved != assets_root and assets_root not in resolved.parents:
            raise ValueError("mesh_root 超出当前项目 assets/ 所有权边界")
        if create:
            resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    def relative_mesh_root(self, project_id: str, path: str | Path) -> str:
        project_dir = self._directory(project_id).resolve()
        assets_root = (project_dir / "assets").resolve()
        resolved = Path(path).expanduser().resolve()
        if resolved != assets_root and assets_root not in resolved.parents:
            raise ValueError("mesh_root 超出当前项目 assets/ 所有权边界")
        return resolved.relative_to(project_dir).as_posix()

    def normalize_mesh_root(self, project: ProjectSpec) -> None:
        raw = str(project.mesh_root or "").strip()
        if not raw:
            project.mesh_root = ""
            return
        try:
            resolved = self.resolve_mesh_root(project.id, raw)
            project.mesh_root = raw if raw.startswith("@model_assets/") else self.relative_mesh_root(project.id, resolved)
        except (KeyError, ValueError, OSError):
            project.mesh_root = ""

    @staticmethod
    def _category_parts(category: str) -> list[str]:
        value = str(category or "None").replace("\\", "/").strip(" /") or "None"
        if value == "未分类":
            value = "None"
        parts = [part.strip() for part in value.split("/")]
        if any(not part or part in {".", ".."} or re.search(r'[<>:"|?*\x00-\x1f]', part) for part in parts):
            raise ValueError("模型类型路径包含非法字符")
        return parts

    @classmethod
    def normalize_category(cls, category: str) -> str:
        return "/".join(cls._category_parts(category))

    def _desired_directory(self, project_id: str, category: str) -> Path:
        return self.projects_root.joinpath(*self._category_parts(category), project_id).resolve()

    @property
    def _model_type_order_path(self) -> Path:
        return self.root / "model_type_order.json"

    @property
    def _model_type_owners_path(self) -> Path:
        return self.root / "model_type_owners.json"

    def _model_type_owners(self) -> dict[str, str]:
        try:
            value = json.loads(self._model_type_owners_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}
        return {
            self.normalize_category(str(path)): str(owner).strip()
            for path, owner in value.items()
            if str(path).strip() and str(owner).strip()
        } if isinstance(value, dict) else {}

    def _save_model_type_owners(self, value: dict[str, str]) -> None:
        self._atomic_json_write(self._model_type_owners_path, value)

    def model_type_owner(self, category: str) -> str:
        return self._model_type_owners().get(self.normalize_category(category), "")

    def _model_type_order(self) -> dict[str, list[str]]:
        try:
            value = json.loads(self._model_type_order_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(value, dict):
            return {}
        return {
            str(parent): [str(name) for name in names if str(name).strip()]
            for parent, names in value.items() if isinstance(names, list)
        }

    def _save_model_type_order(self, value: dict[str, list[str]]) -> None:
        self._atomic_json_write(self._model_type_order_path, value)

    def _remember_model_type(self, category: str) -> None:
        value = self.normalize_category(category)
        parts = value.split("/")
        order = self._model_type_order()
        for index, name in enumerate(parts):
            parent = "/".join(parts[:index])
            siblings = order.setdefault(parent, [])
            if name not in siblings:
                siblings.append(name)
        self._save_model_type_order(order)

    def _iter_project_documents(self) -> Iterator[Path]:
        """Visit model-type directories, never recursively walk model payloads.

        A project root owns potentially huge assets/results/delivery trees.  A
        ``projects_root.rglob('project.json')`` descends into *all* of them on
        every Hub refresh or baseline fork.  Prune immediately after finding
        the authoritative project.json, while retaining arbitrarily nested
        model-type folders and avoiding directory symlinks.
        """
        if not self.projects_root.is_dir():
            return
        for parent, directories, filenames in os.walk(self.projects_root, topdown=True, followlinks=False):
            directory = Path(parent)
            directories[:] = [name for name in directories
                              if not name.startswith(".") and not (directory / name).is_symlink()]
            if "project.json" not in filenames:
                continue
            document = directory / "project.json"
            directories.clear()  # No traversal of assets/, results/, delivery/, versions/.
            if not document.is_symlink():
                yield document

    def _scan_project_paths(self) -> dict[str, Path]:
        result: dict[str, Path] = {}
        for path in self._iter_project_documents():
            project_id = path.parent.name
            if re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
                result.setdefault(project_id, path.parent.resolve())
        self._path_cache = result
        return result

    def _migrate_flat_project_layout(self) -> None:
        """Idempotently place legacy flat model folders under real type folders."""
        if not self.projects_root.is_dir():
            return
        migrated: list[dict[str, str]] = []
        for directory in list(self.projects_root.iterdir()):
            project_path = directory / "project.json"
            if not directory.is_dir() or not project_path.is_file():
                continue
            try:
                data = json.loads(project_path.read_text("utf-8"))
                category = self.normalize_category(str(data.get("category", "None")))
                target = self._desired_directory(str(data.get("id", directory.name)), category)
                if target == directory.resolve():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    LOGGER.error("legacy model migration target already exists: %s", target)
                    continue
                directory.replace(target)
                migrated.append({"project_id": target.name, "from": str(directory), "to": str(target)})
            except (OSError, ValueError, TypeError) as exc:
                LOGGER.error("unable to migrate legacy model directory %s: %s", directory, exc)
        if migrated:
            path = self.root / "layout_migration_2.3.9.4.json"
            self._atomic_json_write(path, {
                "migrated_at": datetime.now(timezone.utc).isoformat(), "items": migrated,
            })
        self._scan_project_paths()

    def _directory(self, project_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
            raise ValueError("invalid project id")
        target = self._path_cache.get(project_id)
        if target is None or not (target / "project.json").is_file():
            target = self._scan_project_paths().get(project_id)
        if target is None:
            # Compatibility for callers preparing a directory before project.json
            # exists; new models created through save() use their real type path.
            target = (self.projects_root / "None" / project_id).resolve()
        if self.root not in target.parents:
            raise ValueError("project path escapes data directory")
        return target

    @staticmethod
    def _local_legacy_csv(project_dir: Path, profile: str, csv_path: str, source_name: str) -> tuple[Path | None, str]:
        """Rebase *only* project-owned CSV assets after moving the Hub data root.

        Never open a stale absolute path, even when it still happens to exist on
        the server: the original path may belong to another user or project.
        The replacement must live under this project's assets directory.
        """
        original = str(csv_path or "").strip().replace("\\", "/")
        named = str(source_name or "").strip().replace("\\", "/")
        if ".." in original.split("/") or ".." in named.split("/"):
            return None, ""
        basename = original.rstrip("/").split("/")[-1] if original else named.split("/")[-1]
        if not basename or basename in {".", ".."} or "\x00" in basename or not basename.lower().endswith(".csv"):
            return None, ""

        # Existing relative references and absolute legacy references that
        # contain assets/... are both anchored at the CURRENT project directory.
        # Prefer the recorded nested asset path; use the legacy mapping folder
        # as a compatibility fallback when only a basename survived.
        pieces = [part for part in original.split("/") if part and part != "."]
        candidates: list[Path] = []
        if "assets" in pieces:
            tail = pieces[len(pieces) - 1 - pieces[::-1].index("assets") + 1:]
            if tail and all(part not in {"", ".", ".."} for part in tail):
                candidates.append(Path("assets").joinpath(*tail))
        if profile == "mapping":
            candidates.append(Path("assets") / "mappings" / basename)
        elif not candidates:
            candidates.append(Path("assets") / "external_motion" / basename)

        assets_root = (project_dir / "assets").resolve()
        safe_candidates: list[tuple[Path, str]] = []
        for relative in candidates:
            try:
                candidate = (project_dir / relative).resolve()
            except (ValueError, OSError):
                continue
            if candidate != assets_root and assets_root not in candidate.parents:
                continue
            # Do not turn a mapping segment into a reference to an unrelated
            # asset, even if an old absolute path points at such a file.
            if profile == "mapping" and (assets_root / "mappings") not in candidate.parents:
                continue
            portable = candidate.relative_to(project_dir.resolve()).as_posix()
            if (candidate, portable) not in safe_candidates:
                safe_candidates.append((candidate, portable))
        for candidate, portable in safe_candidates:
            if candidate.is_file() and not candidate.is_symlink():
                return candidate, portable
        # A missing file is not silently claimed to have been repaired.  Keep
        # its intended portable location so an operator can restore this CSV.
        return (None, safe_candidates[0][1]) if safe_candidates else (None, "")

    def hydrate_legacy_csv_sources(self, project: ProjectSpec, *, project_dir: Path | None = None) -> bool:
        """Embed legacy mapping/motion CSV data and replace machine-local paths.

        New imports already own embedded points; this is an idempotent repair
        for projects whose CSV sidecar moved together with their database.
        It uses no new ProjectSpec fields, tool, API, or storage directory.
        """
        directory = (project_dir or self._directory(project.id)).resolve()
        modified = False
        for drive in project.drives:
            for segment in drive.segments:
                if segment.profile not in {"mapping", "external_csv"}:
                    continue
                before = segment.model_dump()
                profile = segment.profile
                source_name = segment.mapping_csv_name if profile == "mapping" else segment.external_csv_name
                source_path = str(segment.csv_path or "")
                csv_file, portable = self._local_legacy_csv(directory, profile, source_path, source_name)
                if profile == "mapping":
                    if len(segment.points) < 2 and csv_file is not None:
                        try:
                            if csv_file.stat().st_size <= 20 * 1024 * 1024:
                                rows = [(x, y) for x, y in _load_csv_points(str(csv_file)) if math.isfinite(x) and math.isfinite(y)]
                                if len(rows) >= 2:
                                    segment.points = [[x, y] for x, y in rows]
                        except (OSError, UnicodeError, ValueError, ExpressionError) as exc:
                            LOGGER.warning("legacy mapping CSV %s cannot be embedded: %s", portable, exc)
                    if len(segment.points) >= 2:
                        segment.mapping_point_count = len(segment.points)
                    if not segment.mapping_csv_name and source_path and ".." not in source_path.replace("\\", "/").split("/"):
                        segment.mapping_csv_name = source_path.replace("\\", "/").rstrip("/").split("/")[-1]
                else:
                    if not segment.points and csv_file is not None:
                        try:
                            if csv_file.stat().st_size <= 20 * 1024 * 1024:
                                parsed = parse_external_motion_csv(csv_file.read_bytes())
                                segment.points = [[x, y] for x, y in parsed.points]
                                segment.external_csv_header = segment.external_csv_header or parsed.header
                                segment.external_csv_source_metric = segment.external_csv_source_metric or parsed.source_metric
                                segment.duration, segment.travel, segment.speed = external_motion_summary(segment.points)
                        except (OSError, UnicodeError, ValueError) as exc:
                            LOGGER.warning("legacy external CSV %s cannot be embedded: %s", portable, exc)
                    if not segment.external_csv_name and source_path and ".." not in source_path.replace("\\", "/").split("/"):
                        segment.external_csv_name = source_path.replace("\\", "/").rstrip("/").split("/")[-1]
                # Embedded points take precedence even if the optional sidecar
                # disappears; keep only paths relative to this model's assets.
                segment.csv_path = portable if csv_file is not None or not segment.points else ""
                modified = modified or segment.model_dump() != before
        return modified

    def save(self, project: ProjectSpec, *, archive: bool = False, reason: str = "manual",
             actor: str = "", log: str = "", archive_name: str = "",
             overwrite_version_id: str = "") -> ProjectSpec:
        self._normalize_segment_names(project)
        self.normalize_mesh_root(project)
        project.lifecycle.checked_out_session = ""
        with self._cache_lock:
            known = self._path_cache.get(project.id)
            desired = self._desired_directory(project.id, project.category)
            directory = known or desired
            directory.mkdir(parents=True, exist_ok=True)
            self.hydrate_legacy_csv_sources(project, project_dir=directory)
            path = directory / "project.json"
            project.metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
            atomic_write_text(path, project.model_dump_json(indent=2))
            self._path_cache[project.id] = directory.resolve()
        # V2.13.0 guarantees the model-owned time-series folder exists even
        # before the first result export; it remains filesystem state, not ProjectSpec.
        self.time_series_directory(project, create=True)
        if archive:
            self.archive(project, reason=reason, actor=actor, log=log,
                         archive_name=archive_name, overwrite_version_id=overwrite_version_id)
        self.invalidate()
        return project

    def move_project(self, project_id: str, category: str) -> Path:
        normalized = self.normalize_category(category)
        source = self._directory(project_id)
        target = self._desired_directory(project_id, normalized)
        if source == target:
            return target
        if target.exists():
            raise ValueError("目标模型类型中已存在同一模型目录")
        with self._cache_lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
            self._path_cache[project_id] = target
        self.invalidate()
        return target

    def project_move_target(self, project_id: str, category: str) -> Path:
        """Validate a physical model move before mutating its project state."""
        source = self._directory(project_id)
        target = self._desired_directory(project_id, self.normalize_category(category))
        if target != source and target.exists():
            raise ValueError("目标模型类型中已存在同一模型目录")
        return target

    @staticmethod
    def _version_files(versions: Path) -> list[Path]:
        return sorted(path for path in versions.glob("*.json") if not path.name.endswith(".meta.json"))

    @staticmethod
    def _version_meta_path(version_path: Path) -> Path:
        return version_path.with_name(f"{version_path.stem}.meta.json")

    def _overwrite_target(self, project_id: str, version_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", str(version_id or "")):
            raise ValueError("覆盖存档 ID 无效")
        root = self._directory(project_id) / "versions"
        target = root / f"{version_id}.json"
        if not target.is_file() or target.is_symlink():
            raise ValueError("要覆盖的存档版本已不存在")
        meta = self._read_version_meta(target)
        if meta.get("version_kind") == "baseline" or meta.get("reason") == "baseline" or bool(meta.get("locked")):
            raise ValueError("不能覆盖基线版本或锁定存档")
        return target

    def archive(self, project: ProjectSpec, *, reason: str = "archive", locked: bool = False,
                actor: str = "", log: str = "", baseline_project_id: str = "",
                baseline_name: str = "", archive_name: str = "",
                overwrite_version_id: str = "") -> dict[str, Any]:
        if project.lifecycle.status == "baseline":
            raise ValueError("baseline projects do not have archive data")
        if reason not in {"archive", "baseline", "manual", "check_in", "check_out", "edit_start", "edit_end", "rollback_before"}:
            raise ValueError("unsupported archive reason")
        versions = self._directory(project.id) / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        archived_at = datetime.now(timezone.utc).isoformat()
        payload = project.model_dump_json(indent=2)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        version_path = (self._overwrite_target(project.id, overwrite_version_id)
                        if overwrite_version_id else versions / f"{stamp}_{digest}.json")
        if overwrite_version_id and reason not in {"archive", "check_in", "manual"}:
            raise ValueError("只有普通存档允许覆盖")
        archive_name = str(archive_name or "").strip()
        if len(archive_name) > 160 or any(ord(ch) < 32 for ch in archive_name):
            raise ValueError("存档名称无效：长度不能超过 160 且不得含控制字符")
        # V2.9.6 keeps exactly one physical history stream. Old lifecycle/manual
        # reasons remain readable, but every non-baseline entry projects as a
        # “存档版本”; baseline creation adds one “基线版本” marker to the same stream.
        is_baseline = reason == "baseline"
        label = "基线版本" if is_baseline else "存档版本"
        version_kind = "baseline" if is_baseline else "archive"
        meta = {
            "archived_at": archived_at, "reason": reason, "version_kind": version_kind,
            "label": label, "locked": bool(locked), "actor": str(actor),
            "log": str(log or "").strip()[:2000], "archive_name": archive_name,
        }
        if is_baseline:
            meta["baseline_project_id"] = str(baseline_project_id or "")
            meta["baseline_name"] = str(baseline_name or "")
        meta_path = self._version_meta_path(version_path)
        # For overwrite, remember the old bytes so a sidecar-write failure does
        # not leave a mismatched snapshot/name/log pair.
        previous_payload = version_path.read_bytes() if overwrite_version_id else None
        previous_meta = meta_path.read_bytes() if overwrite_version_id and meta_path.is_file() else None
        try:
            atomic_write_text(version_path, payload, sync_directory=False)
            self._atomic_json_write(meta_path, meta)
        except Exception:
            if previous_payload is not None:
                atomic_write_text(version_path, previous_payload.decode("utf-8"), sync_directory=False)
                if previous_meta is None:
                    meta_path.unlink(missing_ok=True)
                else:
                    atomic_write_text(meta_path, previous_meta.decode("utf-8"))
            else:
                version_path.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
            raise
        self._prune_versions(self._directory(project.id), keep=MAX_ARCHIVE_VERSIONS, preserve_locked=False)
        return {
            "id": version_path.stem, "name": project.name, "saved_at": archived_at,
            "size": len(payload.encode("utf-8")), "archived_at": archived_at,
            "reason": reason, "label": label, "version_kind": version_kind,
            "locked": bool(locked), "actor": str(actor), "log": str(log or "").strip()[:2000],
            "archive_name": archive_name, "overwritten": bool(overwrite_version_id),
            "baseline_project_id": str(baseline_project_id or "") if is_baseline else "",
            "baseline_name": str(baseline_name or "") if is_baseline else "",
        }

    def prune_versions(self, project_id: str, *, keep: int, preserve_locked: bool = False) -> list[str]:
        """Keep only the newest ``keep`` archives for one project.

        V2.9.5 retention is a hard total-count cap. ``preserve_locked`` remains only as
        an explicit migration/maintenance escape hatch for old data; normal archive writes
        prune legacy locked sidecars as ordinary history. Baseline creation no longer invokes
        this method to compact the source model to a smaller secondary quota.
        """
        return self._prune_versions(self._directory(project_id), keep=keep, preserve_locked=preserve_locked)

    def _prune_versions(self, directory: Path, keep: int = MAX_ARCHIVE_VERSIONS, *, preserve_locked: bool = False) -> list[str]:
        versions = directory / "versions"
        if not versions.is_dir():
            return []
        version_files = self._version_files(versions)
        # No unlocked archive can exceed the limit while the total archive
        # count is still within it. Avoid opening every sidecar on the common
        # signing path, especially when DATA_ROOT is on network storage.
        if len(version_files) <= max(1, keep):
            return []
        # Sidecar metadata can live on a high-latency/network filesystem.
        # Read each file once instead of once for filtering and again for sort.
        records = [(path, self._read_version_meta(path)) for path in version_files]
        candidates = (
            [(path, meta) for path, meta in records if not bool(meta.get("locked", False))]
            if preserve_locked else records
        )
        candidates.sort(key=lambda item: (str(item[1].get("archived_at", "")), item[0].name))
        removed: list[str] = []
        for stale, _meta in candidates[:-max(1, keep)]:
            LOGGER.warning("pruning old project archive: %s", stale.name)
            stale.unlink(missing_ok=True)
            self._version_meta_path(stale).unlink(missing_ok=True)
            removed.append(stale.name)
        return removed

    def _read_version_meta(self, version_path: Path) -> dict[str, Any]:
        meta_path = self._version_meta_path(version_path)
        if meta_path.is_file():
            try:
                data = json.loads(meta_path.read_text("utf-8"))
                if isinstance(data, dict):
                    return data
            except (OSError, ValueError):
                # A corrupt optional sidecar must not hide a valid legacy snapshot.
                LOGGER.warning("invalid archive metadata ignored: %s", meta_path.name)
        try:
            archived_at = datetime.fromtimestamp(version_path.stat().st_mtime, timezone.utc).isoformat()
        except OSError:
            archived_at = ""
        return {"archived_at": archived_at, "reason": "legacy", "version_kind": "archive", "label": "存档版本", "locked": False, "actor": "", "log": ""}

    def _version_entry(self, path: Path) -> dict[str, Any]:
        data = json.loads(path.read_text("utf-8"))
        meta = self._read_version_meta(path)
        archived_at = str(meta.get("archived_at") or data.get("metadata", {}).get("updated_at", ""))
        reason = str(meta.get("reason", "legacy"))
        is_baseline = reason == "baseline" or str(meta.get("version_kind", "")) == "baseline"
        return {
            "id": path.stem,
            "name": data.get("name", path.parent.parent.name),
            "saved_at": archived_at,
            "size": path.stat().st_size,
            "archived_at": archived_at,
            "reason": reason,
            "label": "基线版本" if is_baseline else "存档版本",
            "version_kind": "baseline" if is_baseline else "archive",
            "locked": bool(meta.get("locked", False)),
            "actor": str(meta.get("actor", "")),
            "log": str(meta.get("log", "")),
            "archive_name": str(meta.get("archive_name", "")),
            "baseline_project_id": str(meta.get("baseline_project_id", "")) if is_baseline else "",
            "baseline_name": str(meta.get("baseline_name", "")) if is_baseline else "",
        }

    def invalidate(self) -> None:
        with self._cache_lock:
            self._list_cache = None

    def _catalog_fingerprint(self) -> tuple[int, int]:
        projects = self.projects_root
        categories = self.root / "project_categories.json"
        try:
            projects_mtime = projects.stat().st_mtime_ns
        except OSError:
            projects_mtime = 0
        try:
            categories_mtime = categories.stat().st_mtime_ns
        except OSError:
            categories_mtime = 0
        return projects_mtime, categories_mtime

    def create(self, project: ProjectSpec | None = None) -> ProjectSpec:
        return self.save(project or ProjectSpec.demo())


    @property
    def trash_root(self) -> Path:
        path = self.root / ".trash" / "projects"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _parse_utc(value: str) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _trash_metadata(self, entry: Path) -> dict[str, Any] | None:
        path = entry / "metadata.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def purge_expired_trash(self, *, now: datetime | None = None) -> list[str]:
        """Physically remove recycle-bin entries after the configured retention window."""
        current = now or datetime.now(timezone.utc)
        removed: list[str] = []
        root = self.trash_root
        for entry in list(root.iterdir()):
            if not entry.is_dir():
                continue
            metadata = self._trash_metadata(entry)
            expires = self._parse_utc(str((metadata or {}).get("expires_at", "")))
            if expires is None:
                # Fail closed for malformed metadata: do not destroy potentially recoverable data.
                continue
            if expires > current:
                continue
            shutil.rmtree(entry, ignore_errors=True)
            removed.append(entry.name)
        return removed

    def list_trash(self) -> list[dict[str, Any]]:
        self.purge_expired_trash()
        items: list[dict[str, Any]] = []
        for entry in self.trash_root.iterdir():
            if not entry.is_dir():
                continue
            metadata = self._trash_metadata(entry)
            if not metadata:
                continue
            project_payload = entry / "project"
            if not (project_payload / "project.json").is_file():
                continue
            item = dict(metadata)
            item["trash_id"] = entry.name
            items.append(item)
        items.sort(key=lambda item: str(item.get("deleted_at", "")), reverse=True)
        return items

    def trash_project(self, project_id: str) -> dict[str, Any]:
        """Move a user-deleted model and its owned external delivery tree into the recycle bin."""
        self.purge_expired_trash()
        directory = self._directory(project_id).resolve()
        if not (directory / "project.json").is_file():
            raise KeyError(project_id)
        project = self.get(project_id)
        delivery = self.delivery_directory(project).resolve()
        project_root = directory
        external_delivery = delivery != project_root and project_root not in delivery.parents
        delivery_binding_root = str(self.delivery_bindings().get(project.category, "") or "") if external_delivery else ""
        now = datetime.now(timezone.utc)
        trash_id = f"{project_id}__{now.strftime('%Y%m%dT%H%M%S%fZ')}"
        entry = self.trash_root / trash_id
        if entry.exists():
            raise ValueError("回收站目标已存在")
        entry.mkdir(parents=True, exist_ok=False)
        saved_external = False
        try:
            if external_delivery and delivery.is_dir():
                shutil.move(str(delivery), str(entry / "external_delivery"))
                saved_external = True
            shutil.move(str(directory), str(entry / "project"))
            metadata = {
                "project_id": project.id,
                "name": project.name,
                "category": project.category,
                "deleted_at": now.isoformat(),
                "expires_at": (now + timedelta(days=TRASH_RETENTION_DAYS)).isoformat(),
                "retention_days": TRASH_RETENTION_DAYS,
                "original_project_relative": directory.relative_to(self.root).as_posix(),
                "external_delivery_original": str(delivery) if external_delivery else "",
                "external_delivery_saved": saved_external,
                "delivery_binding_category": project.category if delivery_binding_root else "",
                "delivery_binding_root": delivery_binding_root,
            }
            self._atomic_json_write(entry / "metadata.json", metadata)
        except Exception:
            # Best-effort rollback keeps the project available if the recycle move cannot complete.
            payload = entry / "project"
            if payload.exists() and not directory.exists():
                directory.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(payload), str(directory))
            external_payload = entry / "external_delivery"
            if external_payload.exists() and not delivery.exists():
                delivery.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(external_payload), str(delivery))
            shutil.rmtree(entry, ignore_errors=True)
            raise
        self._path_cache.pop(project_id, None)
        self.invalidate()
        return {"trash_id": trash_id, **metadata}

    def _trash_entry(self, trash_id: str) -> Path:
        """Resolve one recycle-bin entry without allowing path escape or malformed IDs."""
        if not re.fullmatch(r"[A-Za-z0-9_-]+__\d{8}T\d{12,}Z", str(trash_id or "")):
            raise ValueError("invalid trash id")
        self.purge_expired_trash()
        trash_root = self.trash_root.resolve()
        entry = (trash_root / trash_id).resolve()
        if trash_root not in entry.parents or not entry.is_dir():
            raise KeyError(trash_id)
        return entry

    def delete_trash(self, trash_id: str) -> dict[str, Any]:
        """Permanently remove one valid recycle-bin entry selected by a user."""
        entry = self._trash_entry(trash_id)
        metadata = self._trash_metadata(entry)
        if not metadata or not (entry / "project" / "project.json").is_file():
            # Explicit hard-delete is fail-closed for damaged/unlisted entries.
            raise ValueError("回收站模型数据不完整，拒绝永久删除")
        shutil.rmtree(entry)
        return {"trash_id": trash_id, **metadata}

    def restore_trash(self, trash_id: str) -> ProjectSpec:
        entry = self._trash_entry(trash_id)
        metadata = self._trash_metadata(entry)
        if not metadata:
            raise ValueError("回收站元数据损坏")
        project_id = str(metadata.get("project_id", ""))
        payload = entry / "project"
        if not project_id or not (payload / "project.json").is_file():
            raise ValueError("回收站模型数据不完整")
        relative = Path(str(metadata.get("original_project_relative", "")))
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("回收站原始路径无效")
        target = (self.root / relative).resolve()
        if self.root not in target.parents:
            raise ValueError("回收站恢复路径超出数据根目录")
        if target.exists() or any(str(item.get("id", "")) == project_id for item in self.list()):
            raise FileExistsError("原模型位置或同 ID 模型已存在，拒绝覆盖恢复")
        external_original = str(metadata.get("external_delivery_original", "") or "").strip()
        external_payload = entry / "external_delivery"
        external_target = Path(external_original).expanduser().resolve() if external_original else None
        if external_payload.exists() and (external_target is None or external_target.exists()):
            raise FileExistsError("原交付数据位置已存在，拒绝覆盖恢复")
        binding_category = str(metadata.get("delivery_binding_category", "") or "").strip()
        binding_root_raw = str(metadata.get("delivery_binding_root", "") or "").strip()
        binding_root = Path(binding_root_raw).expanduser().resolve() if binding_root_raw else None
        current_binding = self.delivery_bindings().get(binding_category) if binding_category else None
        if binding_root is not None and current_binding:
            if Path(current_binding).expanduser().resolve() != binding_root:
                raise FileExistsError("原模型类型已绑定到不同交付目录，拒绝覆盖绑定恢复")
        restored_external = False
        binding_added = False
        try:
            if external_payload.exists() and external_target is not None:
                external_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(external_payload), str(external_target))
                restored_external = True
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(payload), str(target))
            if binding_root is not None and binding_category and not current_binding:
                self.bind_delivery_directory(binding_category, binding_root)
                binding_added = True
        except Exception:
            if binding_added:
                try:
                    bindings = self.delivery_bindings()
                    bindings.pop(binding_category, None)
                    self._atomic_json_write(self.root / "project_delivery_bindings.json", bindings)
                except Exception:
                    pass
            if target.exists() and not payload.exists():
                shutil.move(str(target), str(payload))
            if restored_external and external_target is not None and external_target.exists() and not external_payload.exists():
                shutil.move(str(external_target), str(external_payload))
            raise
        shutil.rmtree(entry, ignore_errors=True)
        self._path_cache[project_id] = target
        self.invalidate()
        return self.get(project_id)

    def delete(self, project_id: str) -> None:
        directory = self._directory(project_id)
        if not (directory / "project.json").is_file():
            raise KeyError(project_id)
        project = self.get(project_id)
        delivery = self.delivery_directory(project).resolve()
        project_root = directory.resolve()
        external_delivery = delivery != project_root and project_root not in delivery.parents
        shutil.rmtree(directory)
        if external_delivery and delivery.is_dir():
            # Every model owns a unique delivery tree. Deleting the model is the
            # only operation allowed to remove a frozen baseline delivery tree.
            shutil.rmtree(delivery)
        self._path_cache.pop(project_id, None)
        self.invalidate()

    def categories(self) -> list[str]:
        configured: list[str] = []
        path = self.root / "project_categories.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text("utf-8"))
                if isinstance(data, list):
                    for item in data:
                        try:
                            configured.append(self.normalize_category(str(item)))
                        except ValueError:
                            continue
            except (OSError, ValueError):
                pass
        physical: list[str] = []
        if self.projects_root.is_dir():
            for current, dirs, files in os.walk(self.projects_root):
                if "project.json" in files:
                    dirs[:] = []
                    continue
                relative = Path(current).relative_to(self.projects_root)
                if relative.parts:
                    try:
                        physical.append(self.normalize_category(relative.as_posix()))
                    except ValueError:
                        continue
        derived: list[str] = []
        for item in self.list():
            try:
                derived.append(self.normalize_category(str(item.get("category") or "None")))
            except ValueError:
                continue
        real_categories = sorted(
            {value for value in [*configured, *physical, *derived] if value != "None"},
            key=lambda item: item.casefold(),
        )
        return ["None", *real_categories]

    def add_category(self, name: str, *, actor: str = "") -> list[str]:
        value = self.normalize_category(name)
        if value.startswith("None/"):
            raise ValueError("None 未分类文件夹下面不能增加子分类")
        if not value:
            raise ValueError("项目分类名称不能为空")
        if len(value) > 400 or any(len(part) > 80 for part in value.split("/")):
            raise ValueError("模型类型路径过长（每级最多 80 个字符）")
        (self.projects_root / Path(value)).mkdir(parents=True, exist_ok=True)
        owners = self._model_type_owners()
        if actor and value not in owners:
            owners[value] = str(actor)
            self._save_model_type_owners(owners)
        self._remember_model_type(value)
        categories = sorted(set([*self.categories(), value]), key=lambda item: item.casefold())
        path = self.root / "project_categories.json"
        self._atomic_json_write(path, categories)
        events = self.root / "project_catalog_events.jsonl"
        with events.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "event": "category.added", "category": value,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "semantic": f"添加项目分类「{value}」",
            }, ensure_ascii=False) + "\n")
        self.invalidate()
        return categories

    def model_type_tree(self) -> list[dict[str, Any]]:
        # ``None`` is only an internal uncategorized sentinel; it must never be
        # projected as a deletable/reorderable model-type folder.
        categories = [category for category in self.categories() if category != "None"]
        # Folder badges are recursive totals: a parent folder must include every
        # model stored in its descendant folders, not only direct children.
        counts = {category: 0 for category in categories}
        for item in self.list():
            category = str(item.get("category") or "None")
            if category == "None":
                continue
            parts = category.split("/")
            for index in range(1, len(parts) + 1):
                ancestor = "/".join(parts[:index])
                if ancestor in counts:
                    counts[ancestor] += 1
        nodes: dict[str, dict[str, Any]] = {}
        order = self._model_type_order()
        for path in sorted(categories, key=lambda value: (value.count("/"), value.casefold())):
            parts = path.split("/")
            parent = "/".join(parts[:-1])
            nodes[path] = {"path": path, "name": parts[-1], "parent": parent,
                           "owner": self.model_type_owner(path),
                           "count": counts.get(path, 0), "children": []}
        roots: list[dict[str, Any]] = []
        for path, node in nodes.items():
            if node["parent"] and node["parent"] in nodes:
                nodes[node["parent"]]["children"].append(node)
            else:
                roots.append(node)
        def ordered(parent: str, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
            preferred = {name: index for index, name in enumerate(order.get(parent, []))}
            values.sort(key=lambda item: (preferred.get(str(item["name"]), 10**9), str(item["name"]).casefold()))
            for item in values:
                ordered(str(item["path"]), item["children"])
            return values
        ordered("", roots)
        return roots

    def move_category(self, source: str, target_parent: str = "", before: str = "") -> dict[str, Any]:
        source_value = self.normalize_category(source)
        if source_value == "None":
            raise ValueError("None 不能移动")
        parent_value = "" if not str(target_parent).strip(" /\\") else self.normalize_category(target_parent)
        if parent_value == source_value or parent_value.startswith(source_value + "/"):
            raise ValueError("模型类型不能移动到自身或其子类型下")
        source_dir = (self.projects_root / Path(source_value)).resolve()
        if not source_dir.is_dir():
            raise ValueError("模型类型不存在")
        target_dir = (self.projects_root / Path(parent_value) / source_dir.name).resolve()
        if target_dir == source_dir:
            order = self._model_type_order()
            names = order.setdefault(parent_value, [])
            while source_dir.name in names:
                names.remove(source_dir.name)
            before_name = str(before).split("/")[-1] if str(before).strip() else ""
            if before_name and before_name in names:
                names.insert(names.index(before_name), source_dir.name)
            else:
                names.append(source_dir.name)
            self._save_model_type_order(order)
            affected = [
                str(item["id"]) for item in self.list()
                if str(item.get("category", "")) == source_value
                or str(item.get("category", "")).startswith(source_value + "/")
            ]
            self.invalidate()
            return {"source": source_value, "target": source_value,
                    "affected_project_ids": affected, "tree": self.model_type_tree()}
        if target_dir.exists():
            raise ValueError("目标位置存在同名模型类型")
        documents: list[tuple[Path, str, dict[str, Any]]] = []
        for project_path in source_dir.rglob("project.json"):
            original = project_path.read_text("utf-8")
            data = json.loads(original)
            documents.append((project_path.relative_to(source_dir), original, data))
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        source_dir.replace(target_dir)
        target_value = "/".join(filter(None, [parent_value, source_dir.name]))
        source_library = self.model_asset_library_root(source_value)
        target_library = self.model_asset_library_root(target_value)
        library_moved = False
        if source_library.is_dir():
            target_library.parent.mkdir(parents=True, exist_ok=True)
            if target_library.exists():
                target_dir.replace(source_dir)
                raise ValueError("目标模型类型已存在数模资产库")
            source_library.replace(target_library)
            library_moved = True
        affected: list[str] = []
        try:
            for relative, _, data in documents:
                project_path = target_dir / relative
                old = str(data.get("category", "None"))
                suffix = old[len(source_value):].lstrip("/") if old.startswith(source_value) else ""
                data["category"] = "/".join(filter(None, [target_value, suffix]))
                mesh_root = str(data.get("mesh_root", ""))
                old_prefix = f"@model_assets/{source_value}/"
                if mesh_root.startswith(old_prefix):
                    data["mesh_root"] = f"@model_assets/{target_value}/" + mesh_root[len(old_prefix):]
                self._atomic_json_write(project_path, data)
                affected.append(str(data.get("id", project_path.parent.name)))
        except (OSError, ValueError, TypeError):
            for relative, original, _ in documents:
                atomic_write_text(target_dir / relative, original)
            target_dir.replace(source_dir)
            if library_moved and target_library.exists():
                target_library.replace(source_library)
            raise
        order = self._model_type_order()
        old_parent = "/".join(source_value.split("/")[:-1])
        for names in (order.get(old_parent, []), order.setdefault(parent_value, [])):
            while source_dir.name in names:
                names.remove(source_dir.name)
        target_names = order.setdefault(parent_value, [])
        before_name = str(before).split("/")[-1] if str(before).strip() else ""
        if before_name and before_name in target_names:
            target_names.insert(target_names.index(before_name), source_dir.name)
        else:
            target_names.append(source_dir.name)
        rewritten: dict[str, list[str]] = {}
        for parent, names in order.items():
            next_parent = parent
            if parent == source_value or parent.startswith(source_value + "/"):
                next_parent = target_value + parent[len(source_value):]
            rewritten[next_parent] = names
        self._save_model_type_order(rewritten)
        owners = self._model_type_owners()
        rewritten_owners: dict[str, str] = {}
        for path, owner in owners.items():
            next_path = target_value + path[len(source_value):] if path == source_value or path.startswith(source_value + "/") else path
            rewritten_owners[next_path] = owner
        self._save_model_type_owners(rewritten_owners)
        category_path = self.root / "project_categories.json"
        configured = []
        try:
            raw = json.loads(category_path.read_text("utf-8"))
            configured = [str(item) for item in raw] if isinstance(raw, list) else []
        except (OSError, ValueError):
            pass
        configured = [
            target_value + item[len(source_value):]
            if item == source_value or item.startswith(source_value + "/") else item
            for item in configured
        ]
        self._atomic_json_write(category_path, sorted(set(configured), key=str.casefold))
        events = self.root / "project_catalog_events.jsonl"
        with events.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "event": "model_type.moved", "source": source_value, "target": target_value,
                "project_ids": affected, "occurred_at": datetime.now(timezone.utc).isoformat(),
                "semantic": f"移动模型类型文件夹「{source_value}」到「{target_value}」",
            }, ensure_ascii=False) + "\n")
        self._scan_project_paths()
        self.invalidate()
        return {"source": source_value, "target": target_value, "affected_project_ids": affected,
                "tree": self.model_type_tree()}

    def rename_category(self, source: str, new_name: str) -> dict[str, Any]:
        """Rename one real model-type folder while preserving its subtree and order."""
        source_value = self.normalize_category(source)
        clean_name = self._category_parts(new_name)[-1]
        if "/" in str(new_name).replace("\\", "/"):
            raise ValueError("模型类型名称只能修改当前这一层")
        if source_value == "None":
            raise ValueError("None 不能重命名")
        parent = "/".join(source_value.split("/")[:-1])
        old_name = source_value.split("/")[-1]
        target_value = "/".join(filter(None, [parent, clean_name]))
        if target_value == source_value:
            return {"source": source_value, "target": target_value, "affected_project_ids": [], "tree": self.model_type_tree()}
        source_dir = (self.projects_root / Path(source_value)).resolve()
        target_dir = (self.projects_root / Path(target_value)).resolve()
        if not source_dir.is_dir():
            raise ValueError("模型类型不存在")
        if target_dir.exists():
            raise ValueError("同级已有同名模型类型")
        documents: list[tuple[Path, str, dict[str, Any]]] = []
        for project_path in source_dir.rglob("project.json"):
            original = project_path.read_text("utf-8")
            documents.append((project_path.relative_to(source_dir), original, json.loads(original)))
        source_dir.replace(target_dir)
        source_library = self.model_asset_library_root(source_value)
        target_library = self.model_asset_library_root(target_value)
        library_moved = False
        if source_library.is_dir():
            target_library.parent.mkdir(parents=True, exist_ok=True)
            if target_library.exists():
                target_dir.replace(source_dir)
                raise ValueError("同级同名模型类型已存在数模资产库")
            source_library.replace(target_library)
            library_moved = True
        affected: list[str] = []
        try:
            for relative, _original, data in documents:
                old_category = str(data.get("category", "None"))
                suffix = old_category[len(source_value):] if old_category.startswith(source_value) else ""
                data["category"] = target_value + suffix
                mesh_root = str(data.get("mesh_root", ""))
                old_prefix = f"@model_assets/{source_value}/"
                if mesh_root.startswith(old_prefix):
                    data["mesh_root"] = f"@model_assets/{target_value}/" + mesh_root[len(old_prefix):]
                path = target_dir / relative
                self._atomic_json_write(path, data)
                affected.append(str(data.get("id", path.parent.name)))
        except Exception:
            for relative, original, _data in documents:
                atomic_write_text(target_dir / relative, original)
            target_dir.replace(source_dir)
            if library_moved and target_library.exists():
                target_library.replace(source_library)
            raise
        order = self._model_type_order()
        siblings = order.setdefault(parent, [])
        if old_name in siblings:
            siblings[siblings.index(old_name)] = clean_name
        rewritten: dict[str, list[str]] = {}
        for order_parent, names in order.items():
            next_parent = order_parent
            if order_parent == source_value or order_parent.startswith(source_value + "/"):
                next_parent = target_value + order_parent[len(source_value):]
            rewritten[next_parent] = names
        self._save_model_type_order(rewritten)
        owners = self._model_type_owners()
        rewritten_owners: dict[str, str] = {}
        for path, owner in owners.items():
            next_path = target_value + path[len(source_value):] if path == source_value or path.startswith(source_value + "/") else path
            rewritten_owners[next_path] = owner
        self._save_model_type_owners(rewritten_owners)
        category_path = self.root / "project_categories.json"
        try:
            configured = json.loads(category_path.read_text("utf-8"))
        except (OSError, ValueError):
            configured = []
        configured = [
            target_value + str(item)[len(source_value):]
            if str(item) == source_value or str(item).startswith(source_value + "/") else str(item)
            for item in configured if str(item).strip()
        ]
        self._atomic_json_write(category_path, sorted(set(configured), key=str.casefold))
        self._scan_project_paths()
        self.invalidate()
        return {"source": source_value, "target": target_value, "affected_project_ids": affected,
                "tree": self.model_type_tree()}

    def delete_category(self, name: str, *, delete_projects: bool = False) -> dict[str, Any]:
        """Delete a configured category and either delete or unclassify its projects."""
        value = self.normalize_category(name)
        if not value:
            raise ValueError("模型类型不能为空")
        if value == "None" and not delete_projects:
            raise ValueError("删除 None 时必须同时删除其中模型")
        affected = [item for item in self.list() if (
            str(item.get("category") or "None") == value
            or str(item.get("category") or "None").startswith(value + "/")
        )]
        affected_ids = [str(item["id"]) for item in affected]
        deleted_asset_prefix = f"@model_assets/{value}/"
        if delete_projects:
            # Category deletion also counts as model deletion.  Freeze each selected
            # shared mesh folder into the project before trashing it, because the
            # category-wide public asset library is removed below.  This makes every
            # recycled model independently restorable.
            prepared: list[tuple[str, str, Path]] = []
            recycled: list[str] = []
            try:
                for project_id in affected_ids:
                    project = self.get(project_id)
                    mesh_root = str(project.mesh_root or "")
                    if not mesh_root.startswith(deleted_asset_prefix):
                        continue
                    source_assets = self.resolve_model_asset_reference(mesh_root)
                    if not source_assets.is_dir():
                        raise ValueError(f"模型 {project.name} 的数模资产不存在，拒绝删除模型类型以避免不可恢复")
                    snapshot = self._directory(project_id) / "assets" / "category_delete_recycle_snapshot"
                    if snapshot.exists():
                        shutil.rmtree(snapshot)
                    shutil.copytree(source_assets, snapshot, copy_function=shutil.copy2)
                    original_mesh_root = project.mesh_root
                    project.mesh_root = self.relative_mesh_root(project_id, snapshot)
                    self.save(project)
                    prepared.append((project_id, original_mesh_root, snapshot))
                for project_id in affected_ids:
                    recycled.append(str(self.trash_project(project_id)["trash_id"]))
            except Exception:
                # Restore already-moved projects in reverse order, then put any
                # temporarily frozen shared-mesh references back exactly as they were.
                for trash_id in reversed(recycled):
                    try:
                        self.restore_trash(trash_id)
                    except Exception:
                        pass
                for project_id, original_mesh_root, snapshot in prepared:
                    try:
                        project = self.get(project_id)
                        project.mesh_root = original_mesh_root
                        self.save(project)
                        if snapshot.exists():
                            shutil.rmtree(snapshot)
                    except Exception:
                        pass
                raise
        else:
            for project_id in affected_ids:
                project = self.get(project_id)
                mesh_root = str(project.mesh_root or "")
                if mesh_root.startswith(deleted_asset_prefix):
                    # The category asset library is deleted below. Preserve models that
                    # are intentionally moved to None by freezing their selected public
                    # asset version into a project-owned private snapshot first.
                    snapshot = self._directory(project_id) / "assets" / "category_delete_snapshot"
                    try:
                        source_assets = self.resolve_model_asset_reference(mesh_root)
                        if source_assets.is_dir():
                            shutil.copytree(source_assets, snapshot, dirs_exist_ok=True, copy_function=shutil.copy2)
                            project.mesh_root = self.relative_mesh_root(project_id, snapshot)
                        else:
                            project.mesh_root = ""
                    except (OSError, ValueError):
                        project.mesh_root = ""
                project.category = "None"
                self.save(project)
                self.move_project(project_id, "None")

        physical = (self.projects_root / Path(value)).resolve()
        if physical.is_dir():
            shutil.rmtree(physical)
        asset_library = self.model_asset_library_root(value)
        if asset_library.is_dir():
            shutil.rmtree(asset_library)
        order = self._model_type_order()
        parent = "/".join(value.split("/")[:-1])
        leaf = value.split("/")[-1]
        cleaned_order: dict[str, list[str]] = {}
        for order_parent, names in order.items():
            if order_parent == value or order_parent.startswith(value + "/"):
                continue
            next_names = [name for name in names if not (order_parent == parent and name == leaf)]
            if next_names:
                cleaned_order[order_parent] = next_names
        self._save_model_type_order(cleaned_order)

        owners = {
            path: owner for path, owner in self._model_type_owners().items()
            if path != value and not path.startswith(value + "/")
        }
        self._save_model_type_owners(owners)

        categories = [item for item in self.categories() if item != value and not item.startswith(value + "/")]
        path = self.root / "project_categories.json"
        self._atomic_json_write(path, categories)

        bindings = {
            path: directory for path, directory in self.delivery_bindings().items()
            if path != value and not path.startswith(value + "/")
        }
        binding_path = self.root / "project_delivery_bindings.json"
        self._atomic_json_write(binding_path, bindings)

        events = self.root / "project_catalog_events.jsonl"
        with events.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "event": "category.deleted", "category": value,
                "delete_projects": bool(delete_projects), "project_ids": affected_ids,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "semantic": f"删除项目分类「{value}」" + ("及其中项目" if delete_projects else "，项目转为 None"),
            }, ensure_ascii=False) + "\n")
        self.invalidate()
        return {
            "categories": self.categories(), "deleted": value,
            "delete_projects": bool(delete_projects), "affected_project_ids": affected_ids,
            "tree": self.model_type_tree(),
        }

    def delivery_bindings(self) -> dict[str, str]:
        path = self.root / "project_delivery_bindings.json"
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text("utf-8"))
            return {str(key): str(value) for key, value in data.items() if str(key).strip() and str(value).strip()} if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def bind_delivery_directory(self, category: str, directory: str | Path) -> Path:
        category = str(category).strip() or "None"
        target = Path(directory).expanduser().resolve()
        if not target.is_dir():
            raise ValueError("绑定文件夹不存在")
        bindings = self.delivery_bindings()
        bindings[category] = str(target)
        path = self.root / "project_delivery_bindings.json"
        self._atomic_json_write(path, bindings)
        return target

    @staticmethod
    def _safe_delivery_name(value: str) -> str:
        return re.sub(r'[\\/:*?"<>|]+', "_", value).strip(" .") or "project"

    @staticmethod
    def _delivery_tree_inventory(directory: Path, *, should_cancel: Callable[[], bool] | None = None) -> dict[str, tuple[int, str]]:
        result: dict[str, tuple[int, str]] = {}
        if not directory.is_dir():
            return result
        for path in directory.rglob("*"):
            if should_cancel and should_cancel():
                raise InterruptedError("Baseline fork cancelled during delivery verification")
            if not path.is_file():
                continue
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    if should_cancel and should_cancel():
                        raise InterruptedError("Baseline fork cancelled during delivery verification")
                    digest.update(chunk)
            result[path.relative_to(directory).as_posix()] = (path.stat().st_size, digest.hexdigest())
        return result

    @classmethod
    def copy_delivery_tree(cls, source: Path, target: Path, *, should_cancel: Callable[[], bool] | None = None) -> None:
        source, target = Path(source).resolve(), Path(target).resolve()
        if source == target:
            target.mkdir(parents=True, exist_ok=True)
            return
        target.mkdir(parents=True, exist_ok=True)
        if not source.is_dir():
            return
        def checked_copy(src: str, dst: str) -> str:
            if should_cancel and should_cancel():
                raise RuntimeError("Baseline fork cancelled during delivery copy")
            copied = shutil.copy2(src, dst)
            if should_cancel and should_cancel():
                raise RuntimeError("Baseline fork cancelled during delivery copy")
            return copied

        shutil.copytree(source, target, dirs_exist_ok=True, copy_function=checked_copy)
        src_inventory = cls._delivery_tree_inventory(source, should_cancel=should_cancel)
        dst_inventory = cls._delivery_tree_inventory(target, should_cancel=should_cancel)
        missing = {key: value for key, value in src_inventory.items() if dst_inventory.get(key) != value}
        if missing:
            raise OSError(f"交付数据递归复制校验失败，共 {len(missing)} 个文件未完整复制")

    @classmethod
    def move_delivery_tree(cls, source: Path, target: Path) -> None:
        """Move delivery data cheaply on one filesystem, verify-copy only when required."""
        source, target = Path(source).resolve(), Path(target).resolve()
        if source == target:
            target.mkdir(parents=True, exist_ok=True)
            return
        if not source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            try:
                # Reclassification normally changes only the parent/name on the
                # same disk.  A directory rename is O(1) and preserves the exact
                # tree; the old copy+double-SHA walk made every drag scale with
                # delivery size.  Cross-volume/locked-path failures fall back to
                # the existing verified copy semantics below.
                source.replace(target)
                return
            except OSError as exc:
                LOGGER.info(
                    "delivery atomic move unavailable; falling back to verified copy: %s -> %s: %s",
                    source, target, exc,
                )
        cls.copy_delivery_tree(source, target)
        shutil.rmtree(source)

    def _legacy_delivery_directory(self, project: ProjectSpec) -> Path:
        root = self.delivery_bindings().get(project.category)
        if root:
            return Path(root).expanduser().resolve() / f"{self._safe_delivery_name(project.name)}_时序"
        return self._directory(project.id)

    def _migrate_legacy_delivery(self, project: ProjectSpec, target: Path) -> None:
        legacy = self._legacy_delivery_directory(project).resolve()
        target = target.resolve()
        if legacy == target or not legacy.is_dir():
            return
        if self.delivery_bindings().get(project.category):
            self.copy_delivery_tree(legacy, target)
            return
        managed_names = {
            "project.json", "assets", "core", "outputs", "results", "versions",
            "events.jsonl", "operation_events.jsonl", "ui.json", "project.lock", "时序库",
            ".baseline_fork_pending",  # L3 publish gate, never a deliverable asset.
        }
        for child in legacy.iterdir():
            if child.name in managed_names or child == target:
                continue
            destination = target / child.name
            if child.is_dir():
                shutil.copytree(child, destination, dirs_exist_ok=True, copy_function=shutil.copy2)
            elif child.is_file():
                shutil.copy2(child, destination)

    def time_series_directory(self, project: ProjectSpec, *, create: bool = False) -> Path:
        """Return the model-owned V2.13.0 time-series library directory.

        The library is a filesystem projection next to ``project.json`` rather
        than a second ProjectSpec truth source.  CSV files remain portable model
        artifacts and can be synchronized independently to VZ.
        """
        target = (self._directory(project.id).resolve() / "时序库").resolve()
        project_root = self._directory(project.id).resolve()
        if target.parent != project_root:
            raise ValueError("时序库路径越界")
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    def delivery_directory(self, project: ProjectSpec, *, create: bool = False) -> Path:
        """Return this model's unique complete delivery folder.

        Baselines pin their delivery tree at creation time so later model-type
        delivery-root rebinding cannot move, replace or silently thaw it.
        """
        project_root = self._directory(project.id).resolve()
        frozen = str(project.metadata.get("baseline_delivery_directory", "") or "").strip()
        if project.lifecycle.status == "baseline" and frozen:
            candidate = Path(frozen).expanduser()
            target = candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()
            inside_project = target == project_root or project_root in target.parents
            legacy_owned_external = target.name.endswith(f"__{project.id}")
            if not inside_project and not legacy_owned_external:
                raise ValueError("基线冻结交付目录不属于该模型")
        elif project.lifecycle.status == "baseline":
            target = project_root / "delivery"
        else:
            root = self.delivery_bindings().get(project.category)
            if root:
                target = Path(root).expanduser().resolve() / f"{self._safe_delivery_name(project.name)}_时序__{project.id}"
            else:
                target = project_root / "delivery"
        if create:
            existed = target.is_dir()
            target.mkdir(parents=True, exist_ok=True)
            if not existed and project.lifecycle.status != "baseline":
                self._migrate_legacy_delivery(project, target)
        return target

    def next_version_identity(self, category: str, date_code: str | None = None) -> tuple[str, int, str]:
        value = self.normalize_category(category)
        date_value = date_code or datetime.now().strftime("%Y%m%d")
        siblings = [
            item for item in self.list()
            if item.get("category") == value and item.get("version_date") == date_value
        ]
        index = max([int(item.get("version_index") or 0) for item in siblings] or [0]) + 1
        return date_value, index, f"{value.split('/')[-1]}_{date_value}_{index:03d}"

    def unique_project_name(self, category: str, preferred_name: str, *, exclude_project_id: str = "") -> str:
        """Return a case-insensitively unique model name inside one exact project folder.

        Baseline names are user-editable in V2.11.7.  Name uniqueness is a Hub
        presentation/catalog concern only: project ids and physical directories remain
        authoritative identities.  When a requested name already exists, append the
        stable ``_00i`` family (``_001``, ``_002``...) without mutating any other model.
        """
        clean_name = str(preferred_name or "").strip()
        if not clean_name:
            raise ValueError("模型名称不能为空")
        if len(clean_name) > 160:
            raise ValueError("模型名称不能超过 160 个字符")
        category_value = self.normalize_category(category)
        occupied = {
            str(item.get("name", "")).strip().casefold()
            for item in self.list()
            if str(item.get("id", "")) != str(exclude_project_id or "")
            and str(item.get("category", "None")) == category_value
            and str(item.get("name", "")).strip()
        }
        if clean_name.casefold() not in occupied:
            return clean_name
        index = 1
        while True:
            suffix = f"_{index:03d}"
            candidate = f"{clean_name[:max(0, 160 - len(suffix))]}{suffix}"
            if candidate.casefold() not in occupied:
                return candidate
            index += 1

    def next_baseline_identity(self, source_project_id: str, source_name: str, requested_name: str = "") -> tuple[int, str]:
        """Return the next source sequence plus the requested/auto-disambiguated baseline name."""
        clean_source_name = str(source_name or "").strip()
        if not clean_source_name:
            raise ValueError("基线源模型名称不能为空")
        indices: list[int] = []
        pattern = re.compile(rf"^{re.escape(clean_source_name)}_(\d{{3,}})$")
        projects = self.list()
        for item in projects:
            if str(item.get("lifecycle_status", "")) != "baseline":
                continue
            if str(item.get("baseline_source_project_id", "")) != str(source_project_id):
                continue
            # From V2.11.7 onward display names are editable, so the persisted
            # version_index must win.  Name parsing is only a legacy fallback for
            # snapshots created before that metadata was guaranteed.
            persisted_index = int(item.get("version_index") or 0)
            if persisted_index > 0:
                indices.append(persisted_index)
                continue
            match = pattern.fullmatch(str(item.get("name", "")))
            if match:
                indices.append(int(match.group(1)))
        index = max(indices or [0]) + 1
        source_category = next(
            (str(item.get("category", "None")) for item in projects if str(item.get("id", "")) == str(source_project_id)),
            "",
        )
        if not source_category:
            source_category = self.get(source_project_id).category
        preferred = str(requested_name or "").strip() or clean_source_name
        return index, self.unique_project_name(source_category, preferred)

    def rename_baseline_history_reference(self, source_project_id: str, baseline_project_id: str, baseline_name: str) -> bool:
        """Keep the source unified-history marker aligned after a baseline display-name edit."""
        if not source_project_id or not baseline_project_id:
            return False
        versions = self._directory(source_project_id) / "versions"
        if not versions.is_dir():
            return False
        updated = False
        for meta_path in versions.glob("*.meta.json"):
            try:
                meta = json.loads(meta_path.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            if str(meta.get("version_kind", "")) != "baseline":
                continue
            if str(meta.get("baseline_project_id", "")) != str(baseline_project_id):
                continue
            if str(meta.get("baseline_name", "")) == str(baseline_name):
                return True
            meta["baseline_name"] = str(baseline_name)
            self._atomic_json_write(meta_path, meta)
            updated = True
        return updated

    @staticmethod
    def reclassified_project_name(source_name: str, source_category: str, target_category: str) -> str:
        """Apply only the target leaf prefix and avoid stacking the previous folder prefix."""
        current_name = str(source_name or "").strip()
        source_value = str(source_category or "None")
        target_value = str(target_category or "None")
        if target_value == source_value:
            return current_name
        base_name = current_name
        if source_value != "None":
            source_leaf = source_value.split("/")[-1]
            source_prefix = f"{source_leaf}_"
            if base_name.startswith(source_prefix) and len(base_name) > len(source_prefix):
                base_name = base_name[len(source_prefix):]
        if target_value == "None":
            return base_name
        return f"{target_value.split('/')[-1]}_{base_name}"


    def get(self, project_id: str) -> ProjectSpec:
        path = self._directory(project_id) / "project.json"
        with self._cache_lock:
            if not path.is_file():
                raise KeyError(project_id)
            project = ProjectSpec.model_validate_json(path.read_text("utf-8"))
            self._normalize_segment_names(project)
            if self.hydrate_legacy_csv_sources(project, project_dir=path.parent):
                if project.lifecycle.status == "baseline":
                    # Frozen baselines may be hydrated for runtime but their
                    # authoritative snapshot must never be silently rewritten.
                    LOGGER.info("legacy baseline CSV hydrated in memory: %s", project_id)
                else:
                    try:
                        self._atomic_json_write(path, project.model_dump())
                    except OSError as exc:
                        LOGGER.warning("legacy CSV data hydrated but not persisted for %s: %s", project_id, exc)
            return project

    @staticmethod
    def _normalize_segment_names(project: ProjectSpec) -> None:
        """Keep segment identity positional while preserving cross-drive references."""
        for drive in project.drives:
            renamed = {segment.name: f"seg{index}" for index, segment in enumerate(drive.segments, 1)}
            for candidate in project.drives:
                for segment in candidate.segments:
                    reference_drive, separator, reference_segment = segment.reference.partition("/")
                    if separator and reference_drive == drive.name and reference_segment in renamed:
                        segment.reference = f"{reference_drive}/{renamed[reference_segment]}"
            for index, segment in enumerate(drive.segments, 1):
                segment.name = f"seg{index}"

    def list(self) -> list[dict[str, object]]:
        fingerprint = self._catalog_fingerprint()
        with self._cache_lock:
            if self._list_cache and self._list_cache[0] == fingerprint:
                return copy.deepcopy(self._list_cache[1])
        projects: list[dict[str, object]] = []
        base = self.root / "projects"
        if not base.is_dir():
            with self._cache_lock:
                self._list_cache = (fingerprint, projects)
            return []
        for path in self._iter_project_documents():
            # An in-progress baseline fork is not a usable model.  Its marker
            # is transient L3 state and is always removed on commit/rollback.
            if (path.parent / ".baseline_fork_pending").exists():
                continue
            try:
                data = json.loads(path.read_text("utf-8"))
                model_dir = path.parent.resolve()
                self._path_cache[str(data["id"])] = model_dir
                projects.append({
                    "id": data["id"],
                    "name": data.get("name", data["id"]),
                    "description": data.get("description", ""),
                    "category": data.get("category", "None"),
                    "tags": data.get("tags", []),
                    "mesh_root": data.get("mesh_root", ""),
                    "counts": {
                        "layers": len(data.get("layers", [])),
                        "joints": sum(len(layer.get("joints", [])) for layer in data.get("layers", [])),
                        "segments": sum(len(drive.get("segments", [])) for drive in data.get("drives", [])),
                        "pairs": len(data.get("distance_pairs", [])),
                        "variables": len(data.get("variables", {})),
                    },
                    "updated_at": data.get("metadata", {}).get("updated_at", ""),
                    "baseline_created_at": data.get("lifecycle", {}).get("baseline_created_at", "")
                    or data.get("metadata", {}).get("baseline_created_at", ""),
                    "version_index": data.get("metadata", {}).get("version_index"),
                    "version_date": data.get("metadata", {}).get("version_date", ""),
                    "version_summary": data.get("metadata", {}).get("version_summary", ""),
                    "version_summary_archived": data.get("metadata", {}).get("version_summary_archived", False),
                    "vz_push": (copy.deepcopy(data.get("metadata", {}).get("vz_push", {})) if str(data.get("metadata", {}).get("vz_push", {}).get("source_project_id", "")) == str(data.get("id", "")) else {"enabled": False}),
                    "lifecycle_status": data.get("lifecycle", {}).get("status", "checked_in"),
                    "checked_out_by": data.get("lifecycle", {}).get("checked_out_by", ""),
                    "lease_id": data.get("lifecycle", {}).get("lease_id", ""),
                    "baseline_source_project_id": data.get("lifecycle", {}).get("source_project_id", ""),
                    "model_directory": str(model_dir.relative_to(self.projects_root.resolve())),
                })
            except (OSError, ValueError, KeyError):
                continue
        projects.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        projects.sort(key=lambda item: item.get("lifecycle_status") == "baseline")
        with self._cache_lock:
            self._list_cache = (fingerprint, copy.deepcopy(projects))
        return projects

    def outputs(self, project_id: str) -> Path:
        path = self._directory(project_id) / "outputs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def results(self, project_id: str) -> Path:
        path = self._directory(project_id) / "results"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def project_directory(self, project_id: str) -> Path:
        """Return the owned project directory for internal artifact/asset freezing."""
        return self._directory(project_id)

    def mesh_directory(self, project_id: str) -> Path:
        path = self._directory(project_id) / "assets" / "meshes"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # V2.16.10: project-owned, non-authoritative table sidecars.  Never expose
    # client filenames as physical paths; ProjectSpec.points remains authoritative.
    TABLE_ASSET_KINDS = frozenset({
        "mapping", "external_motion", "result_axis_csv", "result_combined_csv", "result_table_tsv",
    })

    @classmethod
    def table_asset_filename(cls, kind: str, identity: str) -> str:
        if kind not in cls.TABLE_ASSET_KINDS or not isinstance(identity, str) or not identity:
            raise ValueError("表格资产类型或对象身份无效")
        token = hashlib.sha256((kind + "\x00" + identity).encode("utf-8")).hexdigest()
        ext = ".tsv" if kind == "result_table_tsv" else ".csv"
        return f"{kind}--{token}{ext}"

    @staticmethod
    def segment_table_identity(drive_id: str, segment_id: str) -> str:
        if not drive_id or not segment_id:
            raise ValueError("映射表所属驱动或运动段无效")
        return json.dumps([str(drive_id), str(segment_id)], ensure_ascii=False, separators=(",", ":"))

    def table_assets_directory(self, project_id: str, *, create: bool = False) -> Path:
        parent = self._directory(project_id) / "assets"
        root = parent / "tables"
        # Both directory and pre-existing file must be safe; reject symlink
        # substitution rather than writing through it across project boundaries.
        if parent.is_symlink() or root.is_symlink():
            raise ValueError("表格资产路径不能是符号链接")
        if create:
            root.mkdir(parents=True, exist_ok=True)
        return root

    def table_asset_path(self, project_id: str, kind: str, identity: str, *, create: bool = False) -> Path:
        root = self.table_assets_directory(project_id, create=create)
        target = root / self.table_asset_filename(kind, identity)
        if target.is_symlink() or root.resolve() != target.parent.resolve():
            raise ValueError("表格资产路径无效或不安全")
        return target

    def put_table_asset(self, project_id: str, kind: str, identity: str, content: bytes) -> Path:
        if len(content) > 64 * 1024 * 1024:
            raise ValueError("单个表格资产不能超过 64 MiB")
        target = self.table_asset_path(project_id, kind, identity, create=True)
        atomic_write_bytes(target, content)
        return target

    def mapping_directory(self, project_id: str) -> Path:
        path = self._directory(project_id) / "assets" / "mappings"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def latest_version_hint(self, project_id: str) -> dict[str, Any] | None:
        """Latest archive identity without parsing every historical ProjectSpec.

        The Hub catalog needs only this version's id and stamp; detailed history
        still uses list_versions/get_version. Legacy sidecars are supported by
        the existing _read_version_meta fallback to the snapshot's mtime.
        """
        versions = self._directory(project_id) / "versions"
        if not versions.is_dir():
            return None
        newest: tuple[str, str] | None = None
        newest_hint: dict[str, Any] | None = None
        for path in self._version_files(versions):
            try:
                info = path.stat()
                meta = self._read_version_meta(path)
                archived_at = str(meta.get("archived_at") or "")
                key = (archived_at, path.stem)
                if newest is None or key > newest:
                    newest = key
                    newest_hint = {
                        "id": path.stem, "archived_at": archived_at,
                        "mtime_ns": int(info.st_mtime_ns), "size": int(info.st_size),
                    }
            except (OSError, ValueError, TypeError):
                continue
        return newest_hint

    def list_versions(self, project_id: str) -> list[dict[str, Any]]:
        versions = self._directory(project_id) / "versions"
        items: list[dict[str, Any]] = []
        if not versions.is_dir():
            return items
        for path in self._version_files(versions):
            try:
                items.append(self._version_entry(path))
            except (OSError, ValueError):
                continue
        return sorted(items, key=lambda item: (str(item["archived_at"]), str(item["id"])), reverse=True)

    def get_version(self, project_id: str, version_id: str) -> ProjectSpec:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", version_id):
            raise ValueError("invalid version id")
        path = self._directory(project_id) / "versions" / f"{version_id}.json"
        if not path.is_file():
            raise KeyError(version_id)
        return ProjectSpec.model_validate_json(path.read_text("utf-8"))

    def delete_version(self, project_id: str, version_id: str) -> dict[str, Any]:
        """Delete exactly one history snapshot and its metadata sidecar."""
        if not re.fullmatch(r"[A-Za-z0-9_-]+", version_id):
            raise ValueError("invalid version id")
        path = self._directory(project_id) / "versions" / f"{version_id}.json"
        if not path.is_file():
            raise KeyError(version_id)
        entry = self._version_entry(path)
        path.unlink()
        self._version_meta_path(path).unlink(missing_ok=True)
        return entry

    def latest_simulation_result(self, project_id: str) -> dict[str, Any] | None:
        root = self._directory(project_id) / "results"
        stable = root / "latest_simulation.json"
        paths = [stable] if stable.is_file() else []
        if not paths and root.is_dir():
            paths = [
                directory / "simulation_result.json"
                for directory in sorted(root.iterdir(), reverse=True) if directory.is_dir()
            ]
        for path in paths:
            try:
                return json.loads(path.read_text("utf-8"))
            except (OSError, ValueError):
                continue
        return None
