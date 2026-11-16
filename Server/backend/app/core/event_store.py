"""Durable event store for the state/command core."""
from __future__ import annotations

import copy
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..config import FSYNC_ENABLED, MAX_UNDO_EVENTS
from .atomic_io import atomic_write_text


LOGGER = logging.getLogger(__name__)
TAIL_BYTES = max(64 * 1024, int(os.getenv("MUJOCO_STUDIO_EVENT_TAIL_BYTES", str(2 * 1024 * 1024))))
COMPACT_MULTIPLIER = max(2, int(os.getenv("MUJOCO_STUDIO_EVENT_COMPACT_MULTIPLIER", "3")))

# Lifecycle transitions carry lease/session side effects outside the pure project state tree.
# Replaying them through generic history undo/redo would mutate project.lifecycle without
# activating/releasing the corresponding lease or edit-session state. Keep them auditable
# events, but exclude them from the generic history stack.
NON_UNDOABLE_TOOL_IDS = frozenset({"project.lifecycle"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PathDiff:
    path: str
    before: Any
    after: Any
    before_missing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "before": self.before, "after": self.after,
                "before_missing": self.before_missing}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PathDiff":
        return cls(path=data["path"], before=data.get("before"), after=data.get("after"),
                   before_missing=bool(data.get("before_missing", False)))


@dataclass
class Event:
    event_id: str
    command_id: str
    tool_id: str
    client: str
    path_diffs: list[PathDiff]
    semantic: str
    actor: str = ""
    project_id: str = ""
    session_id: str = ""
    intent: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    occurred_at: str = field(default_factory=_now)
    seq: int = 0
    kind: str = "write"
    target_event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "command_id": self.command_id,
            "tool_id": self.tool_id,
            "client": self.client,
            "actor": self.actor,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "path_diffs": [d.to_dict() for d in self.path_diffs],
            "semantic": self.semantic,
            "intent": self.intent,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "occurred_at": self.occurred_at,
            "seq": self.seq,
            "kind": self.kind,
            "target_event_ids": self.target_event_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        return cls(
            event_id=data["event_id"], command_id=data["command_id"],
            tool_id=data["tool_id"], client=data.get("client", "system"),
            path_diffs=[PathDiff.from_dict(item) for item in data.get("path_diffs", [])],
            semantic=data.get("semantic", ""), intent=data.get("intent"),
            actor=str(data.get("actor", "")), project_id=str(data.get("project_id", "")),
            session_id=str(data.get("session_id", "")),
            correlation_id=data.get("correlation_id"), causation_id=data.get("causation_id"),
            occurred_at=data.get("occurred_at", _now()), seq=int(data.get("seq", 0)),
            kind=data.get("kind", "write"),
            target_event_ids=data.get("target_event_ids") or
                ([data["target_event_id"]] if data.get("target_event_id") else []),
        )


class EventStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self._events: list[Event] = []
        self._base = 0
        self._disk_lines = 0
        self._undone_ids: set[str] = set()
        self._redo_stack: list[list[str]] = []
        self._pending: dict[str, Any] | None = None
        self.path = Path(path) if path else None
        if self.path and self.path.is_file():
            self._load()

    def append(self, **kwargs: Any) -> Event:
        """Append one immediately committed event."""
        try:
            event = self.append_pending(**kwargs)
            self.commit_pending()
            return event
        except BaseException:
            self.rollback_pending()
            raise

    def append_pending(
        self,
        *,
        command_id: str,
        tool_id: str,
        client: str,
        path_diffs: list[PathDiff],
        semantic: str,
        actor: str = "",
        project_id: str = "",
        session_id: str = "",
        intent: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        kind: str = "write",
        target_event_ids: list[str] | None = None,
    ) -> Event:
        """Append an event to a transaction that can still be truncated back."""
        if self._pending is None:
            existed = bool(self.path and self.path.exists())
            size = self.path.stat().st_size if existed and self.path else 0
            self._pending = {
                "file_existed": existed,
                "file_size": size,
                "events": list(self._events),
                "base": self._base,
                "disk_lines": self._disk_lines,
                "undone_ids": set(self._undone_ids),
                "redo_stack": copy.deepcopy(self._redo_stack),
            }
        event = Event(
            event_id=f"evt_{uuid4().hex[:12]}", command_id=command_id, tool_id=tool_id,
            client=client, path_diffs=path_diffs, semantic=semantic, actor=actor,
            project_id=project_id, session_id=session_id, intent=intent,
            correlation_id=correlation_id, causation_id=causation_id,
            seq=self.cursor(), kind=kind, target_event_ids=target_event_ids or [],
        )
        self._events.append(event)
        self._apply_control(event)
        try:
            self._persist(event)
        except BaseException:
            self.rollback_pending()
            raise
        return event

    def commit_pending(self) -> None:
        if self._pending is None:
            return
        self._pending = None
        self._trim_memory()
        if self.path and self._disk_lines > COMPACT_MULTIPLIER * MAX_UNDO_EVENTS:
            self._compact()

    def rollback_pending(self) -> None:
        pending = self._pending
        if pending is None:
            return
        self._pending = None
        self._events = pending["events"]
        self._base = pending["base"]
        self._disk_lines = pending["disk_lines"]
        self._undone_ids = pending["undone_ids"]
        self._redo_stack = pending["redo_stack"]
        if self.path is None:
            return
        try:
            if pending["file_existed"]:
                if self.path.exists():
                    with self.path.open("r+b") as stream:
                        stream.truncate(pending["file_size"])
                        stream.flush()
                        if FSYNC_ENABLED:
                            os.fsync(stream.fileno())
            else:
                self.path.unlink(missing_ok=True)
        except OSError:
            LOGGER.exception("failed to rollback pending event stream")
            raise

    def _apply_control(self, event: Event) -> None:
        if event.kind == "write":
            self._redo_stack.clear()
        elif event.kind == "undo" and event.target_event_ids:
            self._undone_ids.update(event.target_event_ids)
            self._redo_stack.append(list(event.target_event_ids))
        elif event.kind == "redo" and event.target_event_ids:
            self._undone_ids.difference_update(event.target_event_ids)
            if self._redo_stack and self._redo_stack[-1] == event.target_event_ids:
                self._redo_stack.pop()

    def _persist(self, event: Event) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
            stream.flush()
            if FSYNC_ENABLED:
                os.fsync(stream.fileno())
        self._disk_lines += 1

    def _load(self) -> None:
        assert self.path is not None
        size = self.path.stat().st_size
        skipped_lines = 0
        with self.path.open("rb") as stream:
            if size > TAIL_BYTES:
                target = size - TAIL_BYTES
                stream.seek(target)
                stream.readline()
                data_start = stream.tell()
                skipped_lines = self._count_newlines(stream, data_start)
                stream.seek(data_start)
            for raw_line in stream:
                if not raw_line.strip():
                    continue
                event = Event.from_dict(json.loads(raw_line.decode("utf-8")))
                self._events.append(event)
                self._apply_control(event)
        if self._events:
            stored_base = max(0, int(self._events[0].seq))
            self._base = max(skipped_lines, stored_base)
            for offset, event in enumerate(self._events):
                event.seq = self._base + offset
        else:
            self._base = skipped_lines
        self._disk_lines = skipped_lines + len(self._events)
        if skipped_lines:
            LOGGER.info("loaded event tail: skipped %d historical lines", skipped_lines)
        self._trim_memory()
        if self._disk_lines > COMPACT_MULTIPLIER * MAX_UNDO_EVENTS:
            self._compact()

    @staticmethod
    def _count_newlines(stream: Any, stop: int) -> int:
        stream.seek(0)
        remaining = stop
        count = 0
        while remaining:
            block = stream.read(min(1024 * 1024, remaining))
            if not block:
                break
            count += block.count(b"\n")
            remaining -= len(block)
        return count

    def _trim_memory(self) -> None:
        if self._redo_stack:
            return
        excess = len(self._events) - MAX_UNDO_EVENTS
        if excess <= 0:
            return
        self._events = self._events[excess:]
        self._base = self._events[0].seq if self._events else self._base + excess
        retained_ids = {event.event_id for event in self._events}
        self._undone_ids.intersection_update(retained_ids)
        self._redo_stack = [
            [event_id for event_id in group if event_id in retained_ids]
            for group in self._redo_stack
        ]
        self._redo_stack = [group for group in self._redo_stack if group]

    def _compact(self) -> bool:
        assert self.path is not None
        if self._pending is not None:
            raise AssertionError("event compaction cannot run during a pending transaction")
        payload = "".join(json.dumps(event.to_dict(), ensure_ascii=False) + "\n" for event in self._events)
        try:
            atomic_write_text(self.path, payload)
        except OSError:
            LOGGER.exception("event compaction failed; original stream retained")
            return False
        LOGGER.info("compacted event stream from %d to %d lines", self._disk_lines, len(self._events))
        self._disk_lines = len(self._events)
        return True

    def at_undo_boundary(self) -> bool:
        return self._base > 0 and self.last_undoable() is None

    def since(self, cursor: int) -> list[Event]:
        return [e for e in self._events if e.seq >= cursor]

    def cursor(self) -> int:
        return self._events[-1].seq + 1 if self._events else self._base

    def all(self) -> list[Event]:
        return list(self._events)

    def last_undoable(self) -> Event | None:
        for event in reversed(self._events):
            if (event.kind == "write" and event.event_id not in self._undone_ids
                    and event.tool_id not in NON_UNDOABLE_TOOL_IDS):
                return event
        return None

    def last_undoable_group(self) -> list[Event]:
        target = self.last_undoable()
        if target is None:
            return []
        if not target.correlation_id:
            return [target]
        return [event for event in self._events
                if event.kind == "write" and event.correlation_id == target.correlation_id
                and event.event_id not in self._undone_ids
                and event.tool_id not in NON_UNDOABLE_TOOL_IDS]

    def last_redoable(self) -> Event | None:
        group = self.last_redoable_group()
        return group[-1] if group else None

    def last_redoable_group(self) -> list[Event]:
        if not self._redo_stack:
            return []
        target_ids = self._redo_stack[-1]
        by_id = {event.event_id: event for event in self._events}
        return [by_id[target_id] for target_id in target_ids if target_id in by_id]

    def is_undone(self, event_id: str) -> bool:
        return event_id in self._undone_ids
