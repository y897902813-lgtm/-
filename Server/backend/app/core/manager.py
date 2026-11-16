"""Lazy per-project kernel manager with in-use-aware LRU eviction."""
from __future__ import annotations

import os
import shutil
from collections import OrderedDict
from contextlib import contextmanager
from threading import RLock
from typing import Iterator
from uuid import uuid4

from ..auth import optional_active_identity
from ..config import MAX_AUTHORITATIVE_EDIT_SESSIONS, MAX_EPHEMERAL_EDIT_SESSIONS
from ..domain.project_store import ProjectStore
from .kernel import Kernel


MAX_LIVE = max(1, int(os.getenv("MUJOCO_STUDIO_MAX_LIVE_KERNELS", "8")))


class KernelCapacityError(RuntimeError):
    code = "kernel_capacity_reached"


class KernelManager:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self._kernels: OrderedDict[str, Kernel] = OrderedDict()
        self.max_live = MAX_LIVE
        self._lock = RLock()
        self._inuse: dict[str, int] = {}
        self._drop_pending: set[str] = set()
        self._ephemeral: dict[tuple[str, str], Kernel] = {}
        self._ephemeral_dirs: dict[tuple[str, str], str] = {}
        self._authoritative_edits: set[tuple[str, str]] = set()

    def _session_key(self, project_id: str) -> tuple[str, str] | None:
        identity = optional_active_identity()
        if identity is None or not identity.lease_id:
            return None
        return project_id, identity.lease_id

    @contextmanager
    def acquire(self, project_id: str) -> Iterator[Kernel]:
        """Pin one authoritative kernel for the duration of a request/operation."""
        instance = self._checkout(project_id)
        try:
            yield instance
        finally:
            self._checkin(project_id, instance)

    def _checkout(self, project_id: str) -> Kernel:
        with self._lock:
            key = self._session_key(project_id)
            if key is not None and key in self._ephemeral:
                instance = self._ephemeral[key]
                instance._refcount += 1
                return instance
            instance = self._kernels.get(project_id)
            if instance is None:
                self._evict_idle_locked(reserve=1)
                project = self.store.get(project_id)
                directory = self.store._directory(project_id)
                instance = Kernel(
                    project, directory, self.store.save,
                    resolve_mesh_root=lambda pid, root: self.store.resolve_mesh_root(pid, root),
                )
                self._kernels[project_id] = instance
            else:
                self._kernels.move_to_end(project_id)
            self._inuse[project_id] = self._inuse.get(project_id, 0) + 1
            instance._refcount += 1
            return instance

    def _checkin(self, project_id: str, instance: Kernel | None = None) -> None:
        with self._lock:
            if instance is not None and instance.ephemeral:
                instance._refcount = max(0, instance._refcount - 1)
                return
            current = self._kernels.get(project_id)
            if instance is not None and current is not instance:
                # A stale legacy object must never alter the live kernel's pin count.
                instance._refcount = max(0, instance._refcount - 1)
                return
            remaining = self._inuse.get(project_id, 0) - 1
            if remaining <= 0:
                self._inuse.pop(project_id, None)
                if current is not None:
                    current._refcount = 0
                if project_id in self._drop_pending:
                    self._drop_pending.discard(project_id)
                    self._kernels.pop(project_id, None)
            else:
                self._inuse[project_id] = remaining
                if current is not None:
                    current._refcount = remaining

    def _evict_idle_locked(self, *, reserve: int = 0) -> None:
        while len(self._kernels) + reserve > self.max_live:
            victim = next((key for key in self._kernels if self._inuse.get(key, 0) == 0), None)
            if victim is None:
                raise KernelCapacityError("服务器同时打开的模型内核已达上限，请稍后重试或关闭部分模型分页")
            self._kernels.pop(victim, None)
            self._drop_pending.discard(victim)

    def get(self, project_id: str) -> Kernel:
        """Legacy short-lived accessor; writes and long operations must use acquire()."""
        instance = self._checkout(project_id)
        self._checkin(project_id, instance)
        return instance

    def begin_ephemeral_edit(self, project_id: str) -> Kernel:
        key = self._session_key(project_id)
        if key is None:
            raise ValueError("临时编辑需要有效登录会话")
        with self._lock:
            existing = self._ephemeral.get(key)
            if existing is not None:
                return existing
            if len(self._ephemeral) >= MAX_EPHEMERAL_EDIT_SESSIONS:
                raise ValueError("临时编辑会话已达到服务器上限，请先退出其他编辑会话")
            project = self.store.get(project_id)
            if project.lifecycle.status not in {"checked_in", "baseline"}:
                raise ValueError("只有签入或基线模型使用临时编辑会话")
            root = self.store.root / ".edit_sessions" / f"{project_id}_{uuid4().hex}"
            root.mkdir(parents=True, exist_ok=False)
            # V2.10.5: ephemeral editing must inherit the authoritative UI projection.
            # Diagram node positions live in core/ui_state.json (UI-only state), so an
            # empty edit-session root would otherwise render a fresh fallback layout
            # until check-out. Copy only UI state; events/artifacts stay isolated.
            source_ui = self.store.project_directory(project_id) / "core" / "ui_state.json"
            if source_ui.is_file():
                target_core = root / "core"
                target_core.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_ui, target_core / "ui_state.json")
            kernel = Kernel(
                project, root, lambda *_args, **_kwargs: None, ephemeral=True,
                resolve_mesh_root=lambda pid, mesh_root: self.store.resolve_mesh_root(pid, mesh_root),
            )
            self._ephemeral[key] = kernel
            self._ephemeral_dirs[key] = str(root)
            return kernel

    def is_ephemeral(self, project_id: str) -> bool:
        key = self._session_key(project_id)
        with self._lock:
            return bool(key is not None and key in self._ephemeral)

    def end_ephemeral_edit(self, project_id: str) -> bool:
        key = self._session_key(project_id)
        if key is None:
            return False
        with self._lock:
            kernel = self._ephemeral.get(key)
            if kernel is not None and kernel._refcount:
                raise ValueError("临时编辑会话仍在使用中，请稍后重试")
            existed = self._ephemeral.pop(key, None) is not None
            directory = self._ephemeral_dirs.pop(key, "")
        if directory:
            shutil.rmtree(directory, ignore_errors=True)
        return existed

    def is_authoritative_edit(self, project_id: str) -> bool:
        key = self._session_key(project_id)
        with self._lock:
            return bool(key is not None and key in self._authoritative_edits)

    def begin_authoritative_edit(self, project_id: str) -> bool:
        key = self._session_key(project_id)
        if key is None:
            raise ValueError("编辑模式需要有效登录会话")
        with self._lock:
            if key in self._authoritative_edits:
                return False
            if len(self._authoritative_edits) >= MAX_AUTHORITATIVE_EDIT_SESSIONS:
                raise ValueError("持久编辑会话已达到服务器上限，请先退出其他编辑会话")
            self._authoritative_edits.add(key)
            return True

    def end_authoritative_edit(self, project_id: str) -> bool:
        key = self._session_key(project_id)
        if key is None:
            return False
        with self._lock:
            if key not in self._authoritative_edits:
                return False
            self._authoritative_edits.remove(key)
            return True

    def authoritative_projects_for_lease(self, lease_id: str) -> list[str]:
        with self._lock:
            return sorted({project_id for project_id, token in self._authoritative_edits if token == lease_id})

    def end_lease(self, lease_id: str) -> None:
        with self._lock:
            keys = [key for key in self._ephemeral if key[1] == lease_id]
            directories = []
            for key in keys:
                kernel = self._ephemeral.get(key)
                if kernel is not None and kernel._refcount:
                    continue
                directories.append(self._ephemeral_dirs.pop(key, ""))
                self._ephemeral.pop(key, None)
            self._authoritative_edits = {key for key in self._authoritative_edits if key[1] != lease_id}
        for directory in directories:
            if directory:
                shutil.rmtree(directory, ignore_errors=True)

    def drop(self, project_id: str) -> None:
        with self._lock:
            if self._inuse.get(project_id, 0) > 0:
                self._drop_pending.add(project_id)
            else:
                self._kernels.pop(project_id, None)
                self._drop_pending.discard(project_id)
            stale = [key for key in self._ephemeral if key[0] == project_id and self._ephemeral[key]._refcount == 0]
            self._authoritative_edits = {key for key in self._authoritative_edits if key[0] != project_id}
            directories = [self._ephemeral_dirs.pop(key, "") for key in stale]
            for key in stale:
                self._ephemeral.pop(key, None)
        for directory in directories:
            if directory:
                shutil.rmtree(directory, ignore_errors=True)
