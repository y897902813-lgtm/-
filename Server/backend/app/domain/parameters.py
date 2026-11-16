from __future__ import annotations

from typing import Any

from .models import ProjectSpec


def parameter_catalog(project: ProjectSpec) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def visit(value: Any, path: str, index_path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if not path and key in {"metadata", "parameter_aliases"}:
                    continue
                next_path = f"{path}.{key}" if path else str(key)
                next_index_path = f"{index_path}.{key}" if index_path else str(key)
                visit(child, next_path, next_index_path)
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                stable_token = f"@{child['id']}" if isinstance(child, dict) and isinstance(child.get("id"), str) else str(index)
                visit(child, f"{path}.{stable_token}", f"{index_path}.{index}")
            return
        compatible_paths = {path, index_path}
        rows.append({
            "path": path,
            "index_path": index_path if index_path != path else None,
            "value": value,
            "type": _value_type(value),
            "aliases": sorted(alias for alias, target in project.parameter_aliases.items() if target in compatible_paths),
            "writable": path not in {"id", "schema_version"} and not path.endswith(".id"),
        })

    visit(project.model_dump(), "", "")
    return rows


def apply_parameter_values(project: ProjectSpec, values: dict[str, Any], aliases: dict[str, str] | None = None) -> ProjectSpec:
    known_paths = {
        candidate
        for item in parameter_catalog(project)
        if item["writable"]
        for candidate in (item["path"], item.get("index_path"))
        if candidate
    }
    if aliases:
        invalid_aliases = {alias: path for alias, path in aliases.items() if path not in known_paths}
        if invalid_aliases:
            alias, path = next(iter(invalid_aliases.items()))
            raise ValueError(f"alias {alias} points to an unknown or read-only parameter: {path}")
        project.parameter_aliases.update(aliases)
    payload = project.model_dump()
    for supplied_key, value in values.items():
        path = project.parameter_aliases.get(supplied_key, supplied_key)
        if path not in known_paths:
            raise ValueError(f"unknown or read-only parameter: {supplied_key}")
        _set_path(payload, path, value)
    payload["parameter_aliases"] = project.parameter_aliases
    return ProjectSpec.model_validate(payload)


def _set_path(root: Any, path: str, value: Any) -> None:
    parts = path.split(".")
    current = root
    for part in parts[:-1]:
        current = _list_item(current, part) if isinstance(current, list) else current[part]
    final = parts[-1]
    if isinstance(current, list):
        if final.startswith("@"):
            index = _list_index(current, final)
            current[index] = value
        else:
            current[int(final)] = value
    else:
        current[final] = value


def _list_item(items: list[Any], token: str) -> Any:
    return items[_list_index(items, token)] if token.startswith("@") else items[int(token)]


def _list_index(items: list[Any], token: str) -> int:
    entity_id = token[1:]
    for index, item in enumerate(items):
        if isinstance(item, dict) and item.get("id") == entity_id:
            return index
    raise KeyError(f"entity not found in parameter path: {entity_id}")


def _value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if value is None:
        return "null"
    return "string"
