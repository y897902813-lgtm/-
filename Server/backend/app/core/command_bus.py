"""Transactional command bus shared by UI, scripts and LLM clients."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable
from pathlib import Path
from uuid import uuid4

from ..auth import optional_active_identity
from .artifact_store import ArtifactStore
from .diffing import structural_diffs
from .event_store import Event, EventStore, PathDiff
from .state_tree import StateTree
from .tool_base import ToolContext, ToolError, WriteResult
from .tool_registry import ToolRegistry


class CommandResult:
    def __init__(self, ok: bool, *, event: Event | None = None, output: Any = None,
                 errors: list[dict[str, Any]] | None = None) -> None:
        self.ok = ok
        self.event = event
        self.output = output
        self.errors = errors or []

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "event": self.event.to_dict() if self.event else None,
                "output": self.output, "errors": self.errors}


class CommandBus:
    def __init__(self, state: StateTree, events: EventStore, registry: ToolRegistry,
                 artifacts: ArtifactStore, output_dir: str,
                 validate_state: Callable[[dict[str, Any]], None] | None = None,
                 on_state_change: Callable[[dict[str, Any]], None] | None = None,
                 authorize_write: Callable[[str, dict[str, Any]], None] | None = None,
                 resolve_mesh_root: Callable[[str, str], Path] | None = None,
                 *, project_id: str = "") -> None:
        self.state = state
        self.events = events
        self.registry = registry
        self.artifacts = artifacts
        self.output_dir = output_dir
        self.validate_state = validate_state
        self.on_state_change = on_state_change
        self.authorize_write = authorize_write
        self.resolve_mesh_root = resolve_mesh_root
        self.project_id = str(project_id)
        self._lock = RLock()

    def context(self, state: StateTree | None = None, *, dry_run: bool = False) -> ToolContext:
        tree = state or self.state
        context: ToolContext
        if dry_run:
            def put_artifact(content: Any, **kw: Any) -> dict[str, Any]:
                return {"handle": "dry-run", "kind": kw.get("kind", "json"),
                        "name": kw.get("name", "preview"), "bytes": 0}
        else:
            def put_artifact(content: Any, **kw: Any) -> dict[str, Any]:
                meta = self.artifacts.put(content, **kw)
                context.produced_handles.append(str(meta.get("handle", "")))
                return meta
        context = ToolContext(
            state_factory=tree.snapshot, read_path=tree.get, put_artifact=put_artifact,
            get_artifact=self.artifacts.get, output_dir=self.output_dir, dry_run=dry_run,
            resolve_mesh_root=self.resolve_mesh_root,
        )
        return context

    def normalize(self, command: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(command, dict) or not command.get("tool_id"):
            raise ToolError("command.tool_id is required", field_name="tool_id")
        client = command.get("client", "human_ui")
        if client not in {"human_ui", "llm_agent", "script", "system"}:
            raise ToolError("invalid command client", field_name="client")
        identity = optional_active_identity()
        return {
            "command_id": command.get("command_id") or f"cmd_{uuid4().hex[:12]}",
            "tool_id": command["tool_id"], "params": command.get("params", {}),
            "client": client,
            "actor": str(command.get("actor") or (identity.username if identity else "")),
            "project_id": str(command.get("project_id") or self.project_id),
            # session_id is deliberately a non-sensitive audit digest, never the cookie token.
            "session_id": str(command.get("session_id") or (identity.audit_id if identity else "")),
            "issued_at": command.get("issued_at") or datetime.now(timezone.utc).isoformat(),
            "correlation_id": command.get("correlation_id"),
            "causation_id": command.get("causation_id"),
        }

    def dry_run(self, command: dict[str, Any]) -> CommandResult:
        try:
            cmd = self.normalize(command)
            tool = self.registry.get(cmd["tool_id"])
            validation = tool.validate(cmd["params"])
            if not validation.ok:
                return CommandResult(False, errors=validation.errors)
            preview = tool.dry_run(cmd["params"], self.context(dry_run=True))
            return CommandResult(True, output={"effect": tool.effect, "preview": preview})
        except ToolError as exc:
            return CommandResult(False, errors=[exc.payload])
        except KeyError as exc:
            return CommandResult(False, errors=[{"code": "unknown_tool", "message": str(exc)}])
        except Exception as exc:  # noqa: BLE001
            return CommandResult(False, errors=[{"code": "dry_run_error", "message": str(exc)}])

    def dispatch(self, command: dict[str, Any]) -> CommandResult:
        with self._lock:
            context: ToolContext | None = None
            try:
                cmd = self.normalize(command)
                tool = self.registry.get(cmd["tool_id"])
                validation = tool.validate(cmd["params"])
                if not validation.ok:
                    return CommandResult(False, errors=validation.errors)
                if tool.effect != "write":
                    return CommandResult(True, output=tool.run(cmd["params"], self.context()))
                if self.authorize_write:
                    self.authorize_write(tool.id, cmd["params"])
                context = self.context()
                result = tool.run(cmd["params"], context)
                if not isinstance(result, WriteResult):
                    raise ToolError("write tool must return WriteResult")
                return self._commit_write(cmd, result, context.produced_handles)
            except ToolError as exc:
                if context is not None:
                    self.artifacts.discard(context.produced_handles)
                return CommandResult(False, errors=[exc.payload])
            except KeyError as exc:
                if context is not None:
                    self.artifacts.discard(context.produced_handles)
                return CommandResult(False, errors=[{"code": "unknown_tool", "message": str(exc)}])
            except Exception as exc:  # noqa: BLE001
                if context is not None:
                    self.artifacts.discard(context.produced_handles)
                return CommandResult(False, errors=[{"code": "runtime_error", "message": str(exc)}])

    def _commit_write(self, cmd: dict[str, Any], result: WriteResult,
                      produced_handles: list[str] | None = None) -> CommandResult:
        shadow = StateTree(self.state.snapshot())
        diffs = self._apply_to_tree(shadow, result)
        snapshot = shadow.root
        if self.validate_state:
            self.validate_state(snapshot)
        try:
            event = self.events.append_pending(
                command_id=cmd["command_id"], tool_id=cmd["tool_id"], client=cmd["client"],
                path_diffs=diffs, semantic=result.semantic, intent=result.intent,
                actor=cmd["actor"], project_id=cmd["project_id"], session_id=cmd["session_id"],
                correlation_id=cmd["correlation_id"], causation_id=cmd["causation_id"], kind="write",
            )
            if self.on_state_change:
                self.on_state_change(snapshot)
            self.events.commit_pending()
            self.state.adopt(snapshot)
            return CommandResult(True, event=event, output={"applied": len(diffs)})
        except Exception as exc:  # noqa: BLE001
            try:
                self.events.rollback_pending()
            finally:
                self.artifacts.discard(produced_handles or [])
            return CommandResult(False, errors=[{
                "code": "commit_rolled_back",
                "message": "状态提交失败，已回滚，未产生任何变更",
                "field": None,
                "hint": "请检查磁盘空间与数据目录权限后重试",
                "details": {"error": str(exc)},
            }])

    @staticmethod
    def _apply_to_tree(tree: StateTree, result: WriteResult) -> list[PathDiff]:
        diffs: list[PathDiff] = []
        for path, value in result.changes:
            missing = not tree.has(path)
            owned_value = copy.deepcopy(value)
            before = tree.set_owned(path, owned_value)
            if missing:
                diffs.append(PathDiff(path=path, before=None, after=copy.deepcopy(owned_value),
                                      before_missing=True))
                continue
            diffs.extend(structural_diffs(path, before, owned_value))
        return diffs

    def dispatch_batch(self, commands: list[dict[str, Any]], correlation_id: str) -> CommandResult:
        """Atomically apply a write-only command batch and persist once."""
        with self._lock:
            shadow = StateTree(self.state.snapshot())
            prepared: list[tuple[dict[str, Any], WriteResult, list[PathDiff]]] = []
            produced_handles: list[str] = []
            try:
                for raw in commands:
                    cmd = self.normalize({**raw, "correlation_id": correlation_id})
                    tool = self.registry.get(cmd["tool_id"])
                    if tool.id == "project.lifecycle":
                        raise ToolError("project.lifecycle cannot be batched because lifecycle has external lease/session side effects",
                                        field_name="tool_id", hint="Run project.lifecycle directly through /api/commands")
                    if tool.effect != "write":
                        raise ToolError("ChangeSet only accepts write tools", field_name="tool_id",
                                        hint="Run read_only tools directly through /api/commands")
                    if self.authorize_write:
                        self.authorize_write(tool.id, cmd["params"])
                    validation = tool.validate(cmd["params"])
                    if not validation.ok:
                        self.artifacts.discard(produced_handles)
                        return CommandResult(False, errors=validation.errors)
                    context = self.context(shadow, dry_run=False)
                    result = tool.run(cmd["params"], context)
                    produced_handles.extend(context.produced_handles)
                    if not isinstance(result, WriteResult):
                        raise ToolError("write tool must return WriteResult")
                    diffs = self._apply_to_tree(shadow, result)
                    prepared.append((cmd, result, diffs))
                snapshot = shadow.root
                if self.validate_state:
                    self.validate_state(snapshot)
                event_ids: list[str] = []
                for cmd, result, diffs in prepared:
                    event = self.events.append_pending(
                        command_id=cmd["command_id"], tool_id=cmd["tool_id"], client=cmd["client"],
                        path_diffs=diffs, semantic=result.semantic, intent=result.intent,
                        actor=cmd["actor"], project_id=cmd["project_id"], session_id=cmd["session_id"],
                        correlation_id=correlation_id, causation_id=cmd["causation_id"], kind="write",
                    )
                    event_ids.append(event.event_id)
                if self.on_state_change:
                    self.on_state_change(snapshot)
                self.events.commit_pending()
                self.state.adopt(snapshot)
                return CommandResult(True, output={"committed": event_ids,
                                                    "correlation_id": correlation_id})
            except ToolError as exc:
                self.events.rollback_pending()
                self.artifacts.discard(produced_handles)
                return CommandResult(False, errors=[exc.payload])
            except KeyError as exc:
                self.events.rollback_pending()
                self.artifacts.discard(produced_handles)
                return CommandResult(False, errors=[{"code": "unknown_tool", "message": str(exc)}])
            except Exception as exc:  # noqa: BLE001
                self.events.rollback_pending()
                self.artifacts.discard(produced_handles)
                return CommandResult(False, errors=[{
                    "code": "commit_rolled_back", "message": "状态提交失败，已回滚，未产生任何变更",
                    "field": None, "hint": "请检查磁盘空间与数据目录权限后重试",
                    "details": {"error": str(exc)},
                }])

    def _audit_fields(self) -> tuple[str, str]:
        identity = optional_active_identity()
        return ((identity.username if identity else ""), (identity.audit_id if identity else ""))

    def undo(self, *, client: str = "human_ui") -> CommandResult:
        with self._lock:
            try:
                if self.authorize_write:
                    self.authorize_write("history.undo", {})
            except Exception as exc:  # noqa: BLE001
                return CommandResult(False, errors=[{"code": "undo_forbidden", "message": str(exc)}])
            targets = self.events.last_undoable_group()
            if not targets:
                if self.events.at_undo_boundary():
                    return CommandResult(False, errors=[{"code": "undo_boundary", "message": "已到最早可撤销点"}])
                return CommandResult(False, errors=[{"code": "nothing_to_undo", "message": "无可撤销事件"}])
            shadow = StateTree(self.state.snapshot())
            reverse: list[PathDiff] = []
            try:
                for target in reversed(targets):
                    for diff in reversed(target.path_diffs):
                        current = shadow.get(diff.path)
                        if diff.before_missing:
                            shadow.delete(diff.path)
                        else:
                            shadow.set(diff.path, copy.deepcopy(diff.before))
                        reverse.append(PathDiff(diff.path, current, copy.deepcopy(diff.before), before_missing=False))
                snapshot = shadow.root
                if self.validate_state:
                    self.validate_state(snapshot)
                actor, session_id = self._audit_fields()
                event = self.events.append_pending(
                    command_id=f"undo_{uuid4().hex[:12]}",
                    tool_id="changeset.undo" if len(targets) > 1 else targets[-1].tool_id,
                    client=client, path_diffs=reverse,
                    semantic=(f"整批撤销 {len(targets)} 条命令" if len(targets) > 1 else f"撤销：{targets[-1].semantic}"),
                    actor=actor, project_id=self.project_id, session_id=session_id,
                    correlation_id=targets[-1].correlation_id, kind="undo",
                    target_event_ids=[target.event_id for target in targets],
                )
                if self.on_state_change:
                    self.on_state_change(snapshot)
                self.events.commit_pending()
                self.state.adopt(snapshot)
                return CommandResult(True, event=event)
            except Exception as exc:  # noqa: BLE001
                self.events.rollback_pending()
                return CommandResult(False, errors=[{"code": "undo_error", "message": str(exc)}])

    def redo(self, *, client: str = "human_ui") -> CommandResult:
        with self._lock:
            try:
                if self.authorize_write:
                    self.authorize_write("history.redo", {})
            except Exception as exc:  # noqa: BLE001
                return CommandResult(False, errors=[{"code": "redo_forbidden", "message": str(exc)}])
            targets = self.events.last_redoable_group()
            if not targets:
                return CommandResult(False, errors=[{"code": "nothing_to_redo", "message": "无可重做事件"}])
            shadow = StateTree(self.state.snapshot())
            diffs: list[PathDiff] = []
            try:
                for target in targets:
                    for diff in target.path_diffs:
                        missing = not shadow.has(diff.path)
                        before = shadow.set(diff.path, copy.deepcopy(diff.after))
                        diffs.append(PathDiff(diff.path, before, copy.deepcopy(diff.after), missing))
                snapshot = shadow.root
                if self.validate_state:
                    self.validate_state(snapshot)
                actor, session_id = self._audit_fields()
                event = self.events.append_pending(
                    command_id=f"redo_{uuid4().hex[:12]}",
                    tool_id="changeset.redo" if len(targets) > 1 else targets[-1].tool_id,
                    client=client, path_diffs=diffs,
                    semantic=(f"整批重做 {len(targets)} 条命令" if len(targets) > 1 else f"重做：{targets[-1].semantic}"),
                    actor=actor, project_id=self.project_id, session_id=session_id,
                    correlation_id=targets[-1].correlation_id, kind="redo",
                    target_event_ids=[target.event_id for target in targets],
                )
                if self.on_state_change:
                    self.on_state_change(snapshot)
                self.events.commit_pending()
                self.state.adopt(snapshot)
                return CommandResult(True, event=event)
            except Exception as exc:  # noqa: BLE001
                self.events.rollback_pending()
                return CommandResult(False, errors=[{"code": "redo_error", "message": str(exc)}])
