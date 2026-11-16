"""Resolve server-declared MuJoCo assets to local files without rewriting XML."""
from __future__ import annotations

import json
import shlex
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET


ASSET_EXTENSIONS = {".stl", ".obj", ".mtl", ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".webp"}


class AssetBindingError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _clean_relative(value: str) -> str:
    path = PurePosixPath(str(value).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise AssetBindingError("local_asset_invalid", f"资产引用不是安全相对路径：{value}")
    return path.as_posix().lstrip("./")


def _vfs_join(base: str, value: str) -> str:
    clean = _clean_relative(value)
    return (PurePosixPath(_clean_relative(base)) / clean).as_posix() if base else clean


class _LocalIndex:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise AssetBindingError("mesh_path_missing", "请先通过“本地数模路径选择”设置数模目录")
        files = [p.resolve() for p in self.root.rglob("*") if p.is_file() and p.suffix.lower() in ASSET_EXTENSIONS]
        self.exact = {p.relative_to(self.root).as_posix(): p for p in files}
        self.folded: dict[str, list[Path]] = {}
        self.basename: dict[str, list[Path]] = {}
        for relative, path in self.exact.items():
            self.folded.setdefault(relative.casefold(), []).append(path)
            self.basename.setdefault(path.name.casefold(), []).append(path)

    def resolve(self, relative: str, *, preferred: Path | None = None) -> Path | None:
        relative = _clean_relative(relative)
        if preferred is not None:
            candidate = (preferred / relative).resolve()
            if candidate.is_file() and (candidate == self.root or self.root in candidate.parents):
                return candidate
        exact = self.exact.get(relative)
        if exact is not None:
            return exact
        matches = self.folded.get(relative.casefold(), [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AssetBindingError(
                "local_asset_ambiguous", f"本地资产存在大小写歧义：{relative}",
                details={"file": relative, "candidates": [str(p) for p in matches]},
            )
        matches = self.basename.get(PurePosixPath(relative).name.casefold(), [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AssetBindingError(
                "local_asset_ambiguous", f"本地资产存在重名文件：{relative}",
                details={"file": relative, "candidates": [str(p) for p in matches]},
            )
        return None


def _mtl_names(path: Path) -> list[str]:
    values: list[str] = []
    for raw in path.read_text("utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) == 2 and parts[0].casefold() == "mtllib":
            values.extend(shlex.split(parts[1], posix=True))
    return values


def _texture_names(path: Path) -> list[str]:
    values: list[str] = []
    for raw in path.read_text("utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = shlex.split(stripped, posix=True)
        if len(parts) >= 2 and (parts[0].casefold().startswith("map_") or parts[0].casefold() == "bump"):
            values.append(parts[-1])
    return values


def build_local_asset_map(scene_path: Path, mesh_root: Path, destination: Path) -> dict[str, Any]:
    """Create a VFS-key -> absolute local path manifest and leave XML unchanged."""
    scene = Path(scene_path)
    tree = ET.parse(scene)
    compiler = tree.find("compiler")
    meshdir = _clean_relative(compiler.get("meshdir", "")) if compiler is not None else ""
    index = _LocalIndex(mesh_root)
    assets: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    missing: list[str] = []

    explicit: list[tuple[str, str]] = []
    for node in tree.findall(".//asset/mesh"):
        if node.get("file"):
            explicit.append((_vfs_join(meshdir, node.get("file", "")), node.get("file", "")))
    for node in tree.findall(".//asset/texture"):
        if node.get("file"):
            explicit.append((_clean_relative(node.get("file", "")), node.get("file", "")))

    resolved: list[tuple[str, Path]] = []
    for vfs_key, requested in explicit:
        candidate = index.resolve(requested)
        if candidate is None:
            missing.append(requested)
        else:
            assets[vfs_key] = str(candidate)
            resolved.append((vfs_key, candidate))
    if missing:
        unique = sorted(set(missing))
        raise AssetBindingError(
            "local_asset_missing", "本地数模路径缺少服务端模型所需文件",
            details={"missing": unique},
        )

    for obj_key, obj_path in [item for item in resolved if item[1].suffix.casefold() == ".obj"]:
        try:
            names = _mtl_names(obj_path)
        except OSError as exc:
            raise AssetBindingError("local_asset_unreadable", f"无法读取本地 OBJ：{obj_path}：{exc}") from exc
        for name in names:
            mtl_path = index.resolve(name, preferred=obj_path.parent)
            mtl_key = _vfs_join(str(PurePosixPath(obj_key).parent), name)
            if mtl_path is None:
                warnings.append({"code": "material_missing", "file": mtl_key})
                continue
            assets[mtl_key] = str(mtl_path)
            try:
                textures = _texture_names(mtl_path)
            except OSError as exc:
                warnings.append({"code": "material_unreadable", "file": mtl_key, "message": str(exc)})
                continue
            for texture in textures:
                texture_path = index.resolve(texture, preferred=mtl_path.parent)
                texture_key = _vfs_join(str(PurePosixPath(mtl_key).parent), texture)
                if texture_path is None:
                    warnings.append({"code": "texture_missing", "file": texture_key})
                else:
                    assets[texture_key] = str(texture_path)

    payload = {"schema_version": 1, "meshdir": meshdir, "assets": assets, "warnings": warnings}
    destination = Path(destination)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    return payload


def rewrite_legacy_mesh_paths(scene_path: Path, mesh_root: Path) -> list[str]:
    """Compatibility only for manifest v1 controllers that cannot accept a VFS map."""
    tree = ET.parse(scene_path)
    index = _LocalIndex(mesh_root)
    matched: list[str] = []
    missing: list[str] = []
    for node in tree.findall(".//asset/mesh"):
        requested = str(node.get("file", ""))
        candidate = index.resolve(requested)
        if candidate is None:
            missing.append(requested)
        else:
            node.set("file", str(candidate))
            matched.append(str(candidate))
    if missing:
        raise AssetBindingError("local_asset_missing", "本地数模路径缺少服务端模型所需文件",
                                details={"missing": sorted(set(missing))})
    compiler = tree.find("compiler")
    if compiler is not None:
        compiler.attrib.pop("meshdir", None)
    tree.write(scene_path, encoding="utf-8", xml_declaration=True)
    return matched
