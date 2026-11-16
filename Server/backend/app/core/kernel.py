"""Per-project application kernel for the state/command/projection architecture."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..domain.models import ProjectSpec
from ..auth import optional_active_identity
from .artifact_store import ArtifactStore
from .atomic_io import atomic_write_text
from .changeset import ChangeSetStore
from .command_bus import CommandBus
from .event_store import EventStore
from .state_tree import StateTree
from .tool_registry import shared_registry


DEFAULT_UI = {
    "theme": "carbon",
    "layout": {"sidebar_collapsed": False, "modeling": {"tree_ratio": 0.25, "props_ratio": 0.5}},
    "highlight_paths": [],
    "active_view": "overview",
    "drives": {"font_family": "Microsoft YaHei", "two_columns": False, "expanded_segments": {}},
    "model": {"mesh_two_columns": False, "active_tree_tab": "all"},
    "results": {"gantt_color": "#018c94", "gantt_auto_sort": True, "gantt_sort_desc": False},
}


class Kernel:
    def __init__(self, project: ProjectSpec, project_dir: str | Path,
                 on_project_change: Callable[..., None],
                 tools_package: str = "app.tools", *, ephemeral: bool = False,
                 resolve_mesh_root: Callable[[str, str], Path] | None = None) -> None:
        self.project_id = project.id
        self.project_dir = Path(project_dir)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        core_dir = self.project_dir / "core"
        core_dir.mkdir(exist_ok=True)
        ui = dict(DEFAULT_UI)
        ui_path = core_dir / "ui_state.json"
        if ui_path.is_file():
            try:
                loaded = json.loads(ui_path.read_text("utf-8"))
                if isinstance(loaded, dict):
                    ui.update(loaded)
            except (OSError, ValueError):
                pass
        self._ui_path = ui_path
        self._on_project_change = on_project_change
        self.ephemeral = bool(ephemeral)
        self._suppress_next_check_in_archive = False
        self._next_check_in_archive_log = ""
        self._next_check_in_archive_name = ""
        self._next_check_in_overwrite_id = ""
        self._refcount = 0
        self.state = StateTree({"project": project.model_dump(), "ui": ui})
        self.events = EventStore(core_dir / "events.jsonl")
        self.artifacts = ArtifactStore(str(core_dir / "artifacts"))
        self.registry = shared_registry(tools_package)
        self.bus = CommandBus(
            self.state, self.events, self.registry, self.artifacts, str(self.project_dir),
            validate_state=self._validate_state, on_state_change=self._persist_state,
            authorize_write=self._authorize_write, resolve_mesh_root=resolve_mesh_root,
            project_id=self.project_id,
        )
        self.changesets = ChangeSetStore(self.registry, core_dir / "changesets.json")

    @staticmethod
    def _baseline_name_only_change(current_raw: dict[str, Any], after_raw: dict[str, Any]) -> bool:
        """Allow a frozen baseline to change only its display name projection.

        ``ProjectSpec.name`` is the authoritative display name and
        ``metadata.baseline_version_label`` mirrors that value for existing Hub/history
        presentation.  Every other baseline field must remain byte-for-structure equal.
        """
        current = ProjectSpec.model_validate(current_raw).model_dump()
        after = ProjectSpec.model_validate(after_raw).model_dump()
        after_name = str(after.get("name", ""))
        current.pop("name", None)
        after.pop("name", None)
        current_metadata = dict(current.get("metadata", {}))
        after_metadata = dict(after.get("metadata", {}))
        if str(after_metadata.get("baseline_version_label", "")) != after_name:
            return False
        current_metadata.pop("baseline_version_label", None)
        after_metadata.pop("baseline_version_label", None)
        current["metadata"] = current_metadata
        after["metadata"] = after_metadata
        return current == after

    def _validate_state(self, root: dict[str, Any]) -> None:
        current_raw = self.state.peek("project")
        after = root.get("project", {})
        if not isinstance(root.get("ui"), dict):
            raise ValueError("ui state must be an object")
        if current_raw == after:
            return
        project = ProjectSpec.model_validate(after)
        if project.id != self.project_id:
            raise ValueError("project.id is immutable")
        current = ProjectSpec.model_validate(current_raw)
        if not self.ephemeral and current.lifecycle.status == "baseline" and current_raw != after:
            if not self._baseline_name_only_change(current_raw, after):
                raise ValueError("基线权威内容不可持久改写；仅允许编辑基线模型名称")
        if not self.ephemeral and current.lifecycle.status == "checked_in" and current_raw != after:
            before_cmp = dict(current_raw)
            after_cmp = dict(after)
            for field in ("lifecycle", "name", "category", "metadata"):
                before_cmp.pop(field, None)
                after_cmp.pop(field, None)
            if before_cmp != after_cmp:
                raise ValueError("项目处于签入状态，请先签出再修改配置")

    def _authorize_write(self, tool_id: str, params: dict[str, Any]) -> None:
        lifecycle = self.project().lifecycle
        status = lifecycle.status
        identity = optional_active_identity()
        owner = lifecycle.checked_out_by
        force_admin = bool(params.get("force")) and identity is not None and identity.role == "admin"
        if status == "checked_out":
            if identity is None:
                raise ValueError("项目已签出，缺少当前写入身份")
            if owner.casefold() != identity.username.casefold() and not force_admin:
                raise ValueError(f"项目已由 {owner} 签出，当前账号不能写入或撤销其操作")
            lease_id = str(lifecycle.lease_id or "")
            same_owner_reacquire = (
                tool_id == "project.lifecycle"
                and str(params.get("action", "")) == "check_out"
                and bool(params.get("reacquire"))
            )
            if (not lease_id or lease_id != identity.lease_id) and not force_admin and not same_owner_reacquire:
                raise ValueError("项目由当前账号的另一登录会话持有编辑租约")
        if self.ephemeral and tool_id in {"project.lifecycle", "project.reclassify"}:
            raise ValueError("临时编辑会话不能改变模型生命周期或模型类型")
        if tool_id == "ui.set":
            return
        if tool_id == "project.lifecycle":
            if status == "baseline":
                raise ValueError("基线生命周期被冻结，不能签入或签出")
            return
        if tool_id == "project.reclassify":
            if status == "baseline":
                raise ValueError("基线项目不可重新分类")
            return
        if tool_id == "project.replace":
            incoming = ProjectSpec.model_validate(params.get("project", {}))
            if incoming.lifecycle.status != status:
                raise ValueError("生命周期不能通过项目保存接口变更")
            if status == "baseline":
                if self._baseline_name_only_change(self.project().model_dump(), incoming.model_dump()):
                    return
                raise ValueError("基线仅允许通过项目保存接口编辑模型名称")
            if status == "checked_in":
                current = self.project().model_dump()
                after = incoming.model_dump()
                for field in ("lifecycle", "name", "category", "metadata"):
                    current.pop(field, None)
                    after.pop(field, None)
                if current == after:
                    return
        if self.ephemeral and status in {"checked_in", "baseline"}:
            return
        if status != "checked_out":
            raise ValueError("项目处于只读状态，请先签出再修改配置")
        if tool_id == "param.set" and str(params.get("path", "")).startswith("project.lifecycle"):
            raise ValueError("生命周期只能通过 project.lifecycle 命令变更")

    @staticmethod
    def _restore_text_file(path: Path, existed: bool, previous: str) -> None:
        if existed:
            atomic_write_text(path, previous)
        else:
            path.unlink(missing_ok=True)

    def _persist_state(self, root: dict[str, Any]) -> None:
        before_project = self.state.peek("project")
        before_ui = self.state.peek("ui")
        after_project = root["project"]
        after_ui = root["ui"]
        project_changed = before_project != after_project
        ui_changed = before_ui != after_ui
        if not project_changed and not ui_changed:
            return

        project_path = self.project_dir / "project.json"
        project_existed = project_path.is_file()
        ui_existed = self._ui_path.is_file()
        previous_project = project_path.read_text("utf-8") if project_existed else ""
        previous_ui = self._ui_path.read_text("utf-8") if ui_existed else ""
        suppress_archive = self._suppress_next_check_in_archive
        pending_check_in_log = self._next_check_in_archive_log
        pending_archive_name = self._next_check_in_archive_name
        pending_overwrite_id = self._next_check_in_overwrite_id

        try:
            # Persist UI first when a batch changes both branches. If the
            # project callback then fails, the UI file can be restored to the
            # exact pre-transaction bytes before CommandBus rolls back events.
            if ui_changed:
                atomic_write_text(self._ui_path, json.dumps(after_ui, ensure_ascii=False, indent=2))
            if project_changed:
                project = ProjectSpec.model_validate(after_project)
                checked_in = (
                    str(before_project.get("lifecycle", {}).get("status", "")) != "checked_in"
                    and project.lifecycle.status == "checked_in"
                )
                archive = checked_in and not suppress_archive
                self._on_project_change(
                    project, archive=archive, reason="archive" if checked_in else "manual",
                    log=pending_check_in_log if checked_in else "",
                    archive_name=pending_archive_name if checked_in else "",
                    overwrite_version_id=pending_overwrite_id if checked_in else "",
                )
                self._suppress_next_check_in_archive = False
                if checked_in:
                    self._next_check_in_archive_log = ""
                    self._next_check_in_archive_name = ""
                    self._next_check_in_overwrite_id = ""
        except Exception:
            # Restore any authoritative file that may already have crossed its
            # atomic-replace boundary. EventStore.rollback_pending() is handled
            # by CommandBus, so this closes the state/event half-commit window.
            restore_errors: list[Exception] = []
            for path, existed, previous in (
                (project_path, project_existed, previous_project),
                (self._ui_path, ui_existed, previous_ui),
            ):
                try:
                    self._restore_text_file(path, existed, previous)
                except Exception as restore_exc:  # noqa: BLE001
                    restore_errors.append(restore_exc)
            self._suppress_next_check_in_archive = suppress_archive
            self._next_check_in_archive_log = pending_check_in_log
            self._next_check_in_archive_name = pending_archive_name
            self._next_check_in_overwrite_id = pending_overwrite_id
            if restore_errors:
                raise RuntimeError(
                    "state persistence failed and rollback restore also failed: "
                    + "; ".join(str(item) for item in restore_errors)
                )
            raise

    def project(self) -> ProjectSpec:
        return ProjectSpec.model_validate(self.state.peek("project"))

    def prepare_next_check_in_archive(self, *, archive: bool = True, log: str = "",
                                      name: str = "", overwrite_version_id: str = "") -> None:
        """Configure exactly one check-in snapshot; the lifecycle coordinator decides
        whether the caller may skip a manual archive. This flag is transient,
        is cleared after dispatch, and does not alter automatic-check-in policy.
        """
        self._suppress_next_check_in_archive = not bool(archive)
        self._next_check_in_archive_log = str(log or "").strip()[:2000]
        self._next_check_in_archive_name = str(name or "").strip()[:160] if archive else ""
        self._next_check_in_overwrite_id = str(overwrite_version_id or "") if archive else ""

    def clear_next_check_in_archive_policy(self) -> None:
        """Clear transient check-in archive controls after success or failed dispatch."""
        self._suppress_next_check_in_archive = False
        self._next_check_in_archive_log = ""
        self._next_check_in_archive_name = ""
        self._next_check_in_overwrite_id = ""

    def prepare_next_check_in_archive_log(self, log: str) -> None:
        """Backward-compatible wrapper: the next check-in must create an archive."""
        self.prepare_next_check_in_archive(archive=True, log=log)

    def suppress_next_check_in_archive(self) -> None:
        """Compatibility wrapper for a deliberate manual check-in without an archive."""
        self.prepare_next_check_in_archive(archive=False)

    def export_json(self) -> dict[str, Any]:
        return self.state.snapshot()
