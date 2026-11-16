"""Persistent, editable and atomically committed ChangeSets."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .command_bus import CommandBus
from .state_tree import StateTree
from .tool_base import WriteResult


def _reject_lifecycle_commands(commands: list[dict[str, Any]]) -> None:
    """Lifecycle commands have lease/session/archive side effects and are never batchable."""
    if any(str(item.get("tool_id", "")) == "project.lifecycle" for item in commands if isinstance(item, dict)):
        raise ValueError("project.lifecycle cannot be placed in a ChangeSet; execute the lifecycle command directly")
from .tool_registry import ToolRegistry


class ChangeSet:
    def __init__(self, title: str, commands: list[dict[str, Any]], source: str = "llm_agent",
                 rationale: str | None = None, *, change_id: str | None = None,
                 status: str = "draft") -> None:
        self.id = change_id or f"cs_{uuid4().hex[:12]}"
        self.title = title
        self.commands = copy.deepcopy(commands)
        self.source = source
        self.rationale = rationale
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "commands": copy.deepcopy(self.commands),
                "source": self.source, "rationale": self.rationale, "status": self.status}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChangeSet":
        return cls(data["title"], data.get("commands", []), data.get("source", "llm_agent"),
                   data.get("rationale"), change_id=data["id"], status=data.get("status", "draft"))


class ChangeSetStore:
    def __init__(self, registry: ToolRegistry, path: str | Path | None = None) -> None:
        self.registry = registry
        self.path = Path(path) if path else None
        self._store: dict[str, ChangeSet] = {}
        if self.path and self.path.is_file():
            for item in json.loads(self.path.read_text("utf-8")):
                cs = ChangeSet.from_dict(item)
                self._store[cs.id] = cs

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.list(), ensure_ascii=False, indent=2), "utf-8")
        temporary.replace(self.path)

    def create(self, title: str, commands: list[dict[str, Any]], source: str = "llm_agent",
               rationale: str | None = None) -> ChangeSet:
        _reject_lifecycle_commands(commands)
        cs = ChangeSet(title, commands, source, rationale)
        self._store[cs.id] = cs
        self._save()
        return cs

    def get(self, change_id: str) -> ChangeSet:
        if change_id not in self._store:
            raise KeyError(f"unknown changeset: {change_id}")
        return self._store[change_id]

    def update_commands(self, change_id: str, commands: list[dict[str, Any]]) -> ChangeSet:
        cs = self.get(change_id)
        if cs.status != "draft":
            raise ValueError("cannot edit a committed changeset")
        _reject_lifecycle_commands(commands)
        cs.commands = copy.deepcopy(commands)
        self._save()
        return cs

    def list(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._store.values()]

    def dry_run(self, change_id: str, bus: CommandBus) -> dict[str, Any]:
        shadow = StateTree.from_dict(bus.state.snapshot())
        per_command: list[dict[str, Any]] = []
        touched: dict[str, Any] = {}
        ok = True
        for raw in self.get(change_id).commands:
            try:
                cmd = bus.normalize(raw)
                tool = self.registry.get(cmd["tool_id"])
                if tool.id == "project.lifecycle":
                    raise ValueError("project.lifecycle cannot be placed in a ChangeSet; execute it directly")
                validation = tool.validate(cmd["params"])
                if not validation.ok:
                    ok = False
                    per_command.append({"tool_id": tool.id, "ok": False,
                                        "errors": validation.errors, "preview": {}})
                    continue
                if tool.effect != "write":
                    raise ValueError("ChangeSet only accepts write tools")
                context = bus.context(shadow, dry_run=True)
                preview = tool.dry_run(cmd["params"], context)
                result = tool.run(cmd["params"], context)
                if not isinstance(result, WriteResult):
                    raise ValueError("write tool must return WriteResult")
                diffs = bus._apply_to_tree(shadow, result)  # internal transaction preview
                for diff in diffs:
                    touched[diff.path] = diff.after
                if bus.validate_state:
                    bus.validate_state(shadow.snapshot())
                per_command.append({"tool_id": tool.id, "ok": True, "errors": [],
                                    "preview": preview})
            except Exception as exc:  # noqa: BLE001
                ok = False
                per_command.append({"tool_id": raw.get("tool_id", ""), "ok": False,
                                    "errors": [{"code": "dry_run_error", "message": str(exc)}],
                                    "preview": {}})
        return {"ok": ok, "per_command": per_command, "touched_paths": sorted(touched),
                "backfill_values": touched}

    def commit(self, change_id: str, bus: CommandBus) -> dict[str, Any]:
        cs = self.get(change_id)
        if cs.status != "draft":
            raise ValueError("changeset already committed")
        result = bus.dispatch_batch(cs.commands, cs.id)
        if not result.ok:
            return result.to_dict()
        cs.status = "committed"
        self._save()
        return {"ok": True, **(result.output or {})}
