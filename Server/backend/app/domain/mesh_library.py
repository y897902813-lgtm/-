from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import MeshSpec, ProjectSpec


SUPPORTED_MESH_EXTENSIONS = {".stl", ".obj"}


def list_mesh_files(root: str | Path) -> list[dict[str, Any]]:
    base = Path(root)
    if not base.is_dir():
        return []
    items: list[dict[str, Any]] = []
    # Preserve nested OBJ/STL folder layouts selected by a browser upload.
    for path in base.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_MESH_EXTENSIONS:
            continue
        stat = path.stat()
        items.append({
            "filename": path.relative_to(base).as_posix(),
            "basename": path.name,
            "extension": path.suffix.lower(),
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })
    return sorted(items, key=lambda item: natural_mesh_key(str(item["filename"])))


def natural_mesh_key(filename: str) -> tuple[Any, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", filename))


def family_key(filename: str) -> tuple[str, str]:
    path = Path(filename)
    stem = re.sub(r"\.\d+$", "", path.stem)
    parent = path.parent.as_posix()
    return (f"{parent}/{stem}" if parent not in {"", "."} else stem).casefold(), path.suffix.lower()


def is_ancillary_family_mesh(filename: str) -> bool:
    """Ancillary family meshes are exactly numeric suffixes .001 through .009."""
    suffix = re.search(r"\.(\d+)$", Path(filename).stem)
    return bool(suffix and 1 <= int(suffix.group(1)) <= 9)


def family_members(files: list[dict[str, Any]], seed_filename: str) -> list[str]:
    seed_family, seed_extension = family_key(seed_filename)
    candidates = [
        str(item["filename"])
        for item in files
        if family_key(str(item["filename"])) == (seed_family, seed_extension)
    ]
    def family_order(filename: str) -> tuple[int, int, tuple[Any, ...]]:
        suffix = re.search(r"\.(\d+)$", Path(filename).stem)
        return (1, int(suffix.group(1)), natural_mesh_key(filename)) if suffix else (0, -1, natural_mesh_key(filename))

    return sorted(candidates, key=family_order)


def adaptive_add(project: ProjectSpec, layer_id: str, seed_filename: str, available: list[dict[str, Any]]) -> dict[str, Any]:
    """Synchronize one mesh family in one hierarchy layer with the library.

    The existing adaptive endpoint is deliberately reused for both single-layer
    and all-layer workflows.  A family is now a bidirectional sync: missing
    library members are removed, case-only names are normalized, new members are
    added, and ancillary .001-.009 meshes keep the existing zero-opacity rule.
    """
    layer = next((item for item in project.layers if item.id == layer_id), None)
    if layer is None:
        raise ValueError("target layer does not exist")

    target_family = family_key(seed_filename)
    members = family_members(available, seed_filename)
    actual_by_name = {filename.casefold(): filename for filename in members}
    template = next((mesh for mesh in layer.meshes if family_key(mesh.filename) == target_family), None)

    removed: list[str] = []
    normalized: list[dict[str, str]] = []
    kept: list[MeshSpec] = []
    for mesh in layer.meshes:
        if family_key(mesh.filename) != target_family:
            kept.append(mesh)
            continue
        real_name = actual_by_name.get(mesh.filename.casefold())
        if real_name is None:
            removed.append(mesh.filename)
            continue
        if mesh.filename != real_name:
            normalized.append({"from": mesh.filename, "to": real_name})
            mesh.filename = real_name
        kept.append(mesh)
    layer.meshes = kept

    existing_by_name = {mesh.filename.casefold(): mesh for mesh in layer.meshes}
    added: list[str] = []
    opacity_zeroed: list[str] = []
    for filename in members:
        existing = existing_by_name.get(filename.casefold())
        if existing is not None:
            if is_ancillary_family_mesh(filename) and existing.opacity != 0.0:
                existing.opacity = 0.0
                opacity_zeroed.append(filename)
            continue
        opacity = 0.0 if is_ancillary_family_mesh(filename) else (template.opacity if template else 1.0)
        created = MeshSpec(
            filename=filename,
            collision=template.collision if template else False,
            rgba=template.rgba if template else "",
            opacity=opacity,
        )
        layer.meshes.append(created)
        existing_by_name[filename.casefold()] = created
        added.append(filename)
        if opacity == 0.0 and is_ancillary_family_mesh(filename):
            opacity_zeroed.append(filename)
    return {
        "family": target_family[0], "members": members, "added": added,
        "removed": removed, "normalized": normalized, "opacity_zeroed": opacity_zeroed,
    }


def repair_mesh_references(project: ProjectSpec, available: list[dict[str, Any]]) -> dict[str, Any]:
    actual = {str(item["filename"]).casefold(): str(item["filename"]) for item in available}
    removed: list[dict[str, str]] = []
    normalized: list[dict[str, str]] = []
    for layer in project.layers:
        kept = []
        for mesh in layer.meshes:
            key = mesh.filename.casefold()
            if key not in actual:
                removed.append({"layer": layer.name, "filename": mesh.filename})
                continue
            real_name = actual[key]
            if mesh.filename != real_name:
                normalized.append({"layer": layer.name, "from": mesh.filename, "to": real_name})
                mesh.filename = real_name
            kept.append(mesh)
        layer.meshes = kept

    for pair in project.distance_pairs:
        for side in ("objects_a", "objects_b"):
            kept_names: list[str] = []
            for filename in getattr(pair, side):
                key = filename.casefold()
                if key not in actual:
                    removed.append({"pair": pair.name, "side": side, "filename": filename})
                    continue
                real_name = actual[key]
                if filename != real_name:
                    normalized.append({"pair": pair.name, "side": side, "from": filename, "to": real_name})
                kept_names.append(real_name)
            setattr(pair, side, kept_names)
    return {"removed": removed, "normalized": normalized}
