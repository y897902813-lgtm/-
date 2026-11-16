from __future__ import annotations

import json
import copy
import hashlib
import hmac
import math
import os
import queue
import csv
import io
import logging
import re
import shutil
import subprocess
import sys
import threading
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
import http.client
import zipfile
from xml.etree import ElementTree as ET
from collections import OrderedDict
from contextlib import contextmanager
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import (
    DATA_ROOT,
    DESKTOP_ENABLED,
    FRONTEND_ROOT,
    INTERACTION_COMMIT_DEBOUNCE_MS,
    LOGIN_LOCK_SECONDS,
    LOGIN_MAX_FAILURES,
    LEASE_SWEEP_SECONDS,
    LEASE_TTL_SECONDS,
    EDIT_IDLE_CHECKIN_SECONDS,
    PENDING_CHECKIN_MAX_RETRY,
    RUNTIME_STATE_DIR,
    JOB_MAX_PER_USER,
    JOB_MAX_RECORDS,
    JOB_RETENTION_SECONDS,
    JOB_TIMEOUT_SECONDS,
    JOB_CANCEL_GRACE_SECONDS,
    JOB_RESULT_KEEP,
    JOB_WORKERS,
    MAX_ARCHIVE_VERSIONS,
    TRASH_RETENTION_DAYS,
    ORPHAN_WORKSPACE_TTL_HOURS,
    ORPHAN_RECLAIM_INTERVAL_SECONDS,
    FSYNC_ENABLED,
    SECURE_COOKIE,
    SESSION_COOKIE_NAME,
    SESSION_TTL_HOURS,
    SINGLE_USER,
)
from .storage_config import load_storage_location, probe_storage_location, save_storage_location
from .auth import (
    AuthService, Identity, active_identity, require_project_access,
    reset_active_identity, set_active_identity,
)
from .core.api import create_core_router
from .core.atomic_io import atomic_replace, atomic_write_text
from .core.manager import KernelCapacityError, KernelManager
from .domain.agent import AgentContext, AgentRunner, SkillDefinition, SkillStore
from .domain.auth_store import AuthStore, AuthStoreError, BUILTIN_ADMIN_USERNAME
from .domain.animation_export import _safe_filename, export_project_animation_html
from .domain.lab_protocol import (
    align_timeline_to_samples,
    DEFAULT_CONFIG as LAB_DEFAULT_CONFIG, LAB_VERSION, LabSession, SampledAnimation,
    build_timeline, canonical_bytes, project_message, send_udp, sequence_identity,
    validated_config,
)
from .domain.client_bridge import ClientTicketError, ClientTicketStore
from .domain.client_bundle import build_client_bundle
from .domain.nx_afu_export import axes_from_result_layout, export_project_nx_afu_script
from .domain.llm import ConversationStore, LLMCredentialStore, chat_completion, chat_completion_stream
from .domain.jobs import JobLimitError, JobManager, TERMINAL_STATUSES
from .domain.job_workspace import JobWorkspaceManager
from .domain.mesh_library import (
    SUPPORTED_MESH_EXTENSIONS,
    adaptive_add,
    list_mesh_files,
    repair_mesh_references,
)
from .domain.modeling_exchange import (
    export_modeling_exchange,
    import_modeling_exchange,
    is_modeling_exchange,
)
from .domain.migration import is_legacy_project, legacy_ui_state, migrate_legacy_project
from .domain.models import DriveSpec, ProjectSpec, new_id
from .domain.motion import (
    ScheduleResolutionError,
    drive_positions,
    joint_positions,
    latest_drive_stop_time,
    mapping_gantt_blocks,
    external_motion_summary,
    normalize_external_motion_points,
    parse_external_motion_csv,
    parse_mapping_csv,
    resolve_schedule,
)
from .domain.optimization import apply_quick_results, run_optimization, run_quick_optimization
from .domain.parameters import apply_parameter_values, parameter_catalog
from .domain.project_store import ProjectStore
from .domain.project_bundle import (
    ARCHIVE_DIR as PROJECT_BUNDLE_ARCHIVE_DIR,
    ASSETS_DIR as PROJECT_BUNDLE_ASSETS_DIR,
    BUNDLE_FORMAT as PROJECT_BUNDLE_FORMAT,
    BUNDLE_FORMAT_VERSION as PROJECT_BUNDLE_FORMAT_VERSION,
    DELIVERY_DIR as PROJECT_BUNDLE_DELIVERY_DIR,
    TIME_SERIES_DIR as PROJECT_BUNDLE_TIME_SERIES_DIR,
    MANIFEST_NAME as PROJECT_BUNDLE_MANIFEST_NAME,
    MODEL_JSON_PATH as PROJECT_BUNDLE_MODEL_JSON_PATH,
    ProjectBundleError,
    clear_environment_local_project_metadata,
    copy_tree_snapshot,
    extract_bundle_zip,
    load_manifest as load_project_bundle_manifest,
    tree_inventory as project_bundle_inventory,
    strip_environment_local_metadata,
    verify_manifest_inventory as verify_project_bundle_inventory,
    write_bundle_zip,
)
from .domain.time_series_library import (
    parse_exported_timing,TIME_SERIES_SCHEMA_VERSION, TSJSON_SCHEMA, DELIVERY_TABLE_FOLDER,
    build_time_series_bundle, build_tsjson_bundle, build_merged_axes_csv,
    is_mapping_table_name, parse_time_series_csv, parse_tsjson, safe_csv_stem)
from .domain.result_provenance import (
    engine_identity, freshness, input_fingerprint, legacy_v2571_project_digests,
    read_provenance, write_provenance, solver_project_digest,
)
from .domain.references import cascade_renamed_references, repair_joint_references
from .domain.simulation import run_project_simulation, compute_selected_viewer_distance_curve, compute_viewer_distance_curves
from .domain.simulation_process import run_project_simulation_isolated
from .domain.scratch import scratch_project
from .domain.validation import validate_project
from .domain.viewer_launcher import ViewerLaunchError, launch_project_viewer, viewer_process_status
from .domain.viewer_registry import VIEWER_REGISTRY

LOGGER = logging.getLogger(__name__)
LOCAL_ADMIN_VIEWER_ENABLED = os.getenv("MUJOCO_STUDIO_LOCAL_ADMIN_VIEWER", "1").lower() in {"1", "true", "yes"}
from .domain.xml_generator import generate_project, load_with_mujoco


app = FastAPI(
    title="MuJoCo Studio API",
    version=__version__,
    description="API-first mechanism modeling, simulation, optimization and agent service.",
)


@app.exception_handler(KernelCapacityError)
async def _kernel_capacity_handler(_request: Request, exc: KernelCapacityError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "code": exc.code,
                "message": "服务器同时打开的模型内核已达上限",
                "field": None,
                "hint": "请稍后重试，或关闭部分模型分页",
            }
        },
    )
store = ProjectStore(DATA_ROOT)
core = KernelManager(store)
jobs = JobManager(
    max_workers=JOB_WORKERS,
    max_records=JOB_MAX_RECORDS,
    retention_seconds=JOB_RETENTION_SECONDS,
    # Reserve at least half the worker slots for other accounts. A single
    # checkout must not fill all Job workers and stall unrelated sessions.
    max_per_user=min(JOB_MAX_PER_USER, max(1, JOB_WORKERS // 2)),
    default_timeout_seconds=JOB_TIMEOUT_SECONDS,
    cancel_grace_seconds=JOB_CANCEL_GRACE_SECONDS,
)
job_workspaces = JobWorkspaceManager(completed_keep=JOB_RESULT_KEEP)
skills = SkillStore(DATA_ROOT / "skills")
llm_credentials = LLMCredentialStore(DATA_ROOT / "private" / "llm_credentials.json")
agent = AgentRunner(skills, llm_credentials)
auth_store = AuthStore(DATA_ROOT / "auth")
auth = AuthService(auth_store, SESSION_TTL_HOURS, LOGIN_MAX_FAILURES, LOGIN_LOCK_SECONDS, LEASE_TTL_SECONDS)
client_tickets = ClientTicketStore(ttl_seconds=60, maximum=512)
SCENE_LIBRARY_ROOT = DATA_ROOT / "scenes"
MAX_SCENE_XML_BYTES = 10 * 1024 * 1024
LEGACY_DEFAULT_SCENE_NAME = "default_scene.xml"
LEGACY_DEFAULT_SCENE_XML = """<mujoco model="legacy_default_scene">
  <option gravity="0 0 0" integrator="implicitfast" cone="elliptic" impratio="10"/>
  <statistic center="1 -0.8 1.1" extent=".35"/>
  <visual><headlight diffuse="0.6 0.6 0.6" ambient="0.1 0.1 0.1" specular="0.9 0.9 0.9"/><rgba haze="0.15 0.25 0.35 1"/><global azimuth="140" elevation="-20"/></visual>
  <asset>
    <texture type="skybox" builtin="gradient" rgb1="0.3 0.5 0.7" rgb2="0 0 0" width="512" height="3072"/>
    <texture type="2d" name="legacy_groundplane_texture" builtin="checker" mark="edge" rgb1="0.2 0.3 0.4" rgb2="0.1 0.2 0.3" markrgb="0.8 0.8 0.8" width="300" height="300"/>
    <material name="legacy_groundplane_material" texture="legacy_groundplane_texture" texuniform="true" texrepeat="5 5" reflectance="0.1"/>
  </asset>
  <worldbody>
    <geom name="legacy_floor" size="0 0 0.05" type="plane" material="legacy_groundplane_material"/>
    <camera mode="fixed" name="Customizedview" pos="0.35 -0.2 0.6" quat="-0.5 -0.5 0.5 0.5"/>
    <camera mode="fixed" name="front_view" pos="0.8 -1 0.6" xyaxes="1 0 0 0 0 1" projection="orthographic" fovy="1.5"/>
    <camera mode="fixed" name="side_view" pos="1.5 -0.405 0.8" xyaxes="0 1 0 0 0 1" projection="orthographic" fovy="1.5"/>
    <camera mode="fixed" name="pov_view" pos="1.4 -0.405 0.97" xyaxes="0 1 0 -0.439 0 0.898" projection="orthographic" fovy="1.5"/>
    <light diffuse=".9 .9 .9" pos="1.6 -0.5 5" dir="0 0 -4"/>
  </worldbody>
</mujoco>\n"""


def _ensure_legacy_default_scene() -> Path:
    """Install the V1 visual scene as a self-contained, mergeable V2 template."""
    SCENE_LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    target = SCENE_LIBRARY_ROOT / LEGACY_DEFAULT_SCENE_NAME
    if target.is_file():
        return target
    staged = SCENE_LIBRARY_ROOT / f".{LEGACY_DEFAULT_SCENE_NAME}.{uuid4().hex}.staged"
    try:
        staged.write_text(LEGACY_DEFAULT_SCENE_XML, encoding="utf-8")
        atomic_replace(staged, target)
    finally:
        staged.unlink(missing_ok=True)
    return target


def _mesh_root_path(project_id: str, project: ProjectSpec | None = None, *, create: bool = False) -> Path:
    current = project or store.get(project_id)
    try:
        return store.resolve_mesh_root(project_id, current.mesh_root, create=create)
    except (KeyError, ValueError, OSError) as exc:
        raise HTTPException(status_code=409, detail="当前数模目录无效；请通过 Web 上传重新建立项目托管资产") from exc


def _runtime_project(project_id: str, project: ProjectSpec | None = None) -> ProjectSpec:
    current = project or get_project(project_id)
    runtime = ProjectSpec.model_validate(copy.deepcopy(current.model_dump()))
    runtime.mesh_root = str(_mesh_root_path(project_id, current))

    # V2.8.7: runtime scene ownership remains intentionally singular. Generation,
    # simulation and baseline jobs always consume the server-managed default
    # scene at DATA_ROOT/scenes/default_scene.xml. Historical/custom
    # ProjectSpec.template_scene values remain readable for project-file
    # compatibility, but they no longer participate in runtime path lookup.
    scene = _ensure_legacy_default_scene().resolve()
    runtime.template_scene = str(scene)
    return runtime


def _submit_project_job(project_id: str, kind: str, task, *, timeout_seconds: float | None = None) -> str:
    """Submit a project job with lease pinning and anti-duplicate submission.

    V2.8.15 dedup: for long-running heavy kinds (``simulation``,
    ``animation_html_export`` and ``web_viewer_export``), if the caller's
    owner+lease already owns a queued or running job of the **same kind** on
    the **same project**, return the in-flight ``job_id`` instead of creating
    a duplicate.  This eliminates UI-side double-click "重复加载刷新" races
    where rapid clicks spin up two workers and both attempt the atomic
    publish to the same results folder.
    """
    identity = active_identity()
    # ---- dedup gate (no IO / checkout wasted if duplicate) -----------------
    dedup_kinds = {"simulation", "animation_html_export", "web_viewer_export", "lab_animation_export", "native_viewer_launch", "delivery_refresh"}
    if kind in dedup_kinds or kind.startswith(("distance_curve:", "baseline_fork:")):
        for existing in jobs.list(50):
            if (
                str(existing.get("project_id", "")) == str(project_id)
                and str(existing.get("kind", "")) == str(kind)
                and str(existing.get("owner", "")).casefold() == identity.username.casefold()
                and str(existing.get("owner_lease_id", "")) == identity.lease_id
                and str(existing.get("status", "")) not in TERMINAL_STATUSES
            ):
                # Reuse the in-flight job transparently to the caller.
                return str(existing["id"])
    # ------------------------------------------------------------------------
    job_id = uuid4().hex
    # A background job crosses a thread boundary, so a normal with/acquire scope
    # cannot cover its lifetime. Pin explicitly and release in the worker finally.
    instance = core._checkout(project_id)
    try:
        workspace_root = instance.project_dir / "core" / "job_workspaces"
        workspace = job_workspaces.allocate(workspace_root, kind, job_id)
    except Exception:
        core._checkin(project_id, instance)
        raise

    def isolated_task(progress, cancelled):
        try:
            result = task(progress, cancelled, workspace, job_id)
            if cancelled():
                raise InterruptedError("Cancellation requested before artifact publication")
            return result
        finally:
            job_workspaces.discard(workspace)
            core._checkin(project_id, instance)

    try:
        return jobs.submit(
            kind, isolated_task, project_id=project_id, owner=identity.username,
            owner_lease_id=identity.lease_id, job_id=job_id, workspace=str(workspace),
            timeout_seconds=timeout_seconds,
        )
    except JobLimitError as exc:
        job_workspaces.discard(workspace)
        core._checkin(project_id, instance)
        raise HTTPException(status_code=429, detail={"message": str(exc), "retry_after": 5}) from exc
    except Exception:
        job_workspaces.discard(workspace)
        core._checkin(project_id, instance)
        raise


def _result_base(project_id: str) -> Path:
    return (core.get(project_id).project_dir / "results") if core.is_ephemeral(project_id) else store.results(project_id)


def _fingerprint(project_id: str, project: ProjectSpec) -> dict[str, Any]:
    return input_fingerprint(project, [_mesh_root_path(project_id, project)])


def _rewrite_workspace_paths(value: Any, source: Path, destination: Path) -> Any:
    if isinstance(value, str):
        return value.replace(str(source), str(destination))
    if isinstance(value, list):
        return [_rewrite_workspace_paths(item, source, destination) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_workspace_paths(item, source, destination) for key, item in value.items()}
    return value


def _latest_simulation_record(project_id: str) -> tuple[dict[str, Any] | None, Path | None]:
    root = _result_base(project_id)
    if not root.is_dir():
        return None, None
    for candidate in sorted(root.glob("simulation_*/simulation_result.json"), reverse=True):
        try:
            payload = json.loads(candidate.read_text("utf-8"))
            if isinstance(payload, dict):
                return payload, candidate.parent
        except (OSError, ValueError):
            continue
    return None, None


def _current_simulation_trajectory(project_id: str, project: ProjectSpec) -> tuple[Path | None, list[str]]:
    """Return the newest reusable simulation trajectory plus explicit degradation warnings.

    Tier 1 reuses a current fingerprint silently. Tier 2 permits a trajectory with
    identical physical assets but stale project parameters, and makes that degraded
    truth source visible to the caller. Asset changes reject reuse and fall back to a
    fresh solve.
    """
    latest, latest_dir = _latest_simulation_record(project_id)
    if not latest or latest_dir is None:
        return None, []
    candidate = latest_dir / str(latest.get("trajectory_file", "trajectory.npz"))
    if not candidate.is_file():
        return None, []
    try:
        provenance = read_provenance(latest_dir)
        current_fingerprint = _fingerprint(project_id, project)
        current = freshness(provenance, current_fingerprint)
        if current.get("status") == "current":
            return candidate, []
        recorded = provenance.get("input_fingerprint", {}) if isinstance(provenance, dict) else {}
        if recorded.get("assets") != current_fingerprint.get("assets"):
            return None, []
        # V2.5.7.1 migration: delivery filename metadata used to participate in
        # the project digest. That exact legacy digest is content-current and
        # remains a silent compatibility reuse.
        if recorded.get("project") in legacy_v2571_project_digests(project):
            return candidate, []
        # Physical assets may be unchanged while drives, timing, solver settings,
        # masses or constraints have changed. Reusing that qpos trajectory would
        # make a newly generated HTML animation disagree with the current project
        # and native Viewer semantics. Force a fresh L3 solve instead.
        return None, ["trajectory_stale_parameters_recomputed"]
    except Exception:
        return None, []


def _animation_preview_directory(project_id: str) -> Path:
    directory = core.get(project_id).project_dir / "core" / "artifacts" / "animation_preview"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _latest_animation_preview(project_id: str) -> tuple[Path | None, dict[str, Any]]:
    directory = _animation_preview_directory(project_id)
    metadata_path = directory / "latest.json"
    metadata: dict[str, Any] = {}
    try:
        metadata = json.loads(metadata_path.read_text("utf-8")) if metadata_path.is_file() else {}
    except (OSError, ValueError, TypeError):
        metadata = {}
    named = directory / str(metadata.get("filename", "")) if metadata.get("filename") else None
    if named is not None and named.is_file():
        return named, metadata
    candidates = sorted(directory.glob("*_anim.html"), key=lambda path: path.stat().st_mtime, reverse=True)
    return (candidates[0] if candidates else None), metadata


def _publish_result_directory(
    *, project_id: str, project: ProjectSpec, kind: str, job_id: str,
    workspace: Path, result: Any, parameters: dict[str, Any], fingerprint: dict[str, Any],
) -> dict[str, Any]:
    provenance = write_provenance(
        workspace,
        job_id=job_id,
        kind=kind,
        application_version=__version__,
        fingerprint=fingerprint,
        parameters=parameters,
        ephemeral=core.is_ephemeral(project_id),
    )
    if kind == "simulation":
        # A derived provenance hint is minted BEFORE immutable publication.
        # No ProjectSpec, simulation_result.json, frozen trajectory or legacy
        # protocol receives a new field. Old provenance remains readable.
        provenance["solver_project_digest"] = solver_project_digest(project)
        atomic_write_text(workspace / "provenance.json", json.dumps(
            provenance, ensure_ascii=False, indent=2, sort_keys=True))
    if isinstance(result, dict):
        result_metadata = {
            key: result.get(key) for key in ("gantt_source", "trajectory_reused", "warnings")
            if key in result
        }
        if result_metadata:
            provenance["result_metadata"] = result_metadata
            atomic_write_text(
                workspace / "provenance.json",
                json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True),
            )
    destination = _result_base(project_id) / workspace.name
    job_workspaces.publish_directory(workspace, destination)
    if kind == "simulation":
        simulation_result = destination / "simulation_result.json"
        if simulation_result.is_file():
            # Stable derived snapshot: reopening a model can render curves without
            # another solve. Baseline creation recursively freezes the results tree,
            # so this same artifact becomes immutable baseline curve data.
            atomic_write_text(
                destination.parent / "latest_simulation.json",
                simulation_result.read_text("utf-8"),
            )
    job_workspaces.prune(destination.parent)
    if kind == "simulation" and not core.is_ephemeral(project_id) and project.lifecycle.status != "baseline":
        # A refreshed simulation must never appear successful while its newest
        # actual MJCF was silently omitted from delivery.
        try:
            _publish_latest_simulation_xml(project, destination)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"仿真结果已生成，但最新仿真 XML 交付保存失败：{exc}") from exc
    payload = _rewrite_workspace_paths(result, workspace, destination)
    if not isinstance(payload, dict):
        payload = {"value": payload}
    if kind == "simulation":
        payload["simulation_id"] = destination.name
    payload.update({
        "result_dir": str(destination),
        "provenance": provenance,
        "freshness": {"status": "current", "stale": False, "reasons": []},
    })
    return payload


def _job_payload_for(identity: Identity, job: dict[str, Any]) -> dict[str, Any]:
    payload = dict(job)
    payload.pop("owner_lease_id", None)
    if identity.role != "admin":
        payload.pop("workspace", None)
    if identity.role != "admin" and isinstance(payload.get("error"), dict):
        error = dict(payload["error"])
        error.pop("traceback", None)
        payload["error"] = error
    return payload


def _authorize_job(job: dict[str, Any], *, cancel: bool = False) -> Identity:
    identity = active_identity()
    project_id = str(job.get("project_id", ""))
    try:
        project = store.get(project_id)
        require_project_access(project, write=False)
    except (KeyError, ValueError, HTTPException) as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    if identity.role != "admin":
        if str(job.get("owner", "")).casefold() != identity.username.casefold():
            raise HTTPException(status_code=404, detail="Job not found")
        if str(job.get("owner_lease_id", "")) != identity.lease_id:
            raise HTTPException(status_code=404, detail="Job not found")
    return identity


def _websocket_identity(websocket):
    if SINGLE_USER:
        return Identity(BUILTIN_ADMIN_USERNAME, "admin", session_id="single-user", lease_id="single-user", single_user=True)
    return auth.sessions.get(websocket.cookies.get(SESSION_COOKIE_NAME, ""))


def _record_model_write_activity(project_id: str, identity: Identity, tool_id: str = "") -> None:
    """Reset only the model-edit idle clock after a successful real state mutation.

    Session and Lease clocks are intentionally handled elsewhere. UI-only writes do
    not keep a checked-out model alive.
    """
    if tool_id == "ui.set":
        return
    try:
        project = core.get(project_id).project()
    except (KeyError, ValueError):
        return
    if (project.lifecycle.status == "checked_out"
            and project.lifecycle.lease_id == identity.lease_id):
        _schedule_idle_check_in(project_id, identity)


def _lease_has_checkout(lease_id: str) -> bool:
    value = str(lease_id or "")
    if not value:
        return False
    return any(
        str(item.get("lifecycle_status", "")) == "checked_out"
        and str(item.get("lease_id", "")) == value
        for item in store.list()
    )


def _coordinate_lifecycle_transition(
    project_id: str, action: str, identity: Identity, *, client: str = "human_ui",
    force: bool = False, intent: str | None = None, archive_log: str = "",
    archive_check_in: bool = True, archive_name: str = "", overwrite_version_id: str = "",
) -> tuple[ProjectSpec, dict[str, Any]]:
    """One lifecycle coordinator for UI, generic commands, logout and sweeper paths."""
    if action not in {"check_in", "check_out"}:
        raise HTTPException(status_code=422, detail="action 必须是 check_in 或 check_out")
    # A browser-initiated *manual* check-in may omit an archive. Automatic idle,
    # logout, force, baseline repair and script/system check-ins are safety paths:
    # they ALWAYS archive, even when a legacy caller supplies archive=False.
    archive_check_in = bool(archive_check_in) if (
        action == "check_in" and client == "human_ui" and not force and not intent
    ) else True
    if core.is_ephemeral(project_id):
        core.end_ephemeral_edit(project_id)
        core.drop(project_id)
    with core.acquire(project_id) as instance:
        project = instance.project()
        lifecycle = project.lifecycle
        same_owner_checkout = (
            action == "check_out"
            and lifecycle.status == "checked_out"
            and str(lifecycle.checked_out_by or "").casefold() == identity.username.casefold()
        )
        if same_owner_checkout:
            if identity.role not in {"engineer", "admin"}:
                raise HTTPException(403, "当前账号无项目写入权限")
        else:
            require_project_access(project, write=True)
        previous_lease_id = str(lifecycle.lease_id or "")
        if action == "check_in" and lifecycle.status == "checked_in":
            with _PENDING_CHECKIN_LOCK:
                _PENDING_CHECKINS.pop(project_id, None)
            _persist_pending_checkins()
            core.end_authoritative_edit(project_id)
            return instance.project(), {"ok": True, "output": {"idempotent": True, "status": "checked_in"}}
        if action == "check_out" and lifecycle.status == "checked_out":
            if not same_owner_checkout:
                raise HTTPException(status_code=409, detail=f"模型已由 {lifecycle.checked_out_by or '其他会话'} 签出")
            reacquired = previous_lease_id != identity.lease_id
            if reacquired and _has_live_session_lease(previous_lease_id):
                raise HTTPException(409, "同一账号的另一个浏览器仍持有有效编辑租约，不能抢占其编辑权")
            if reacquired:
                result = instance.bus.dispatch({
                    "tool_id": "project.lifecycle",
                    "params": {
                        "action": "check_out",
                        "actor": identity.username,
                        "lease_id": identity.lease_id,
                        "reacquire": True,
                        **({"intent": intent} if intent else {}),
                    },
                    "actor": identity.username,
                    "client": client,
                })
                if not result.ok:
                    raise HTTPException(status_code=409, detail=result.errors)
                core.end_lease(previous_lease_id)
                if previous_lease_id:
                    auth.sessions.deactivate_lease_id(previous_lease_id, reason="revoked")
            if not identity.single_user:
                auth.sessions.activate_lease(identity.session_id)
            deadline = _ensure_idle_check_in(project_id, identity)
            return instance.project(), {
                "ok": True,
                "output": {
                    "idempotent": not reacquired,
                    "reacquired": reacquired,
                    "status": "checked_out",
                    "idle_check_in_deadline": deadline,
                },
            }
        if action == "check_in":
            if archive_check_in and overwrite_version_id:
                try:
                    store._overwrite_target(project_id, overwrite_version_id)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
            if not archive_check_in and (archive_name or overwrite_version_id):
                raise HTTPException(status_code=422, detail="不存档签入不能指定存档名称或覆盖目标")
            instance.prepare_next_check_in_archive(
                archive=archive_check_in,
                log=archive_log if archive_check_in else "",
                name=archive_name if archive_check_in else "",
                overwrite_version_id=overwrite_version_id if archive_check_in else "",
            )
        command = {
            "tool_id": "project.lifecycle",
            "params": {
                "action": action, "actor": identity.username, "lease_id": identity.lease_id,
                "force": bool(force), **({"intent": intent} if intent else {}),
                **({"log": archive_log} if action == "check_in" else {}),
            },
            "actor": identity.username, "client": client,
        }
        try:
            result = instance.bus.dispatch(command)
        finally:
            if action == "check_in":
                instance.clear_next_check_in_archive_policy()
        if not result.ok:
            raise HTTPException(status_code=409, detail=result.errors)
        updated = instance.project()
        if action == "check_out":
            if not identity.single_user:
                auth.sessions.activate_lease(identity.session_id)
            # Check-out only grants edit authority and never creates a lifecycle
            # version. History comes from explicit archive, every check-in, or baseline.
            _schedule_idle_check_in(project_id, identity)
        else:
            with _PENDING_CHECKIN_LOCK:
                _PENDING_CHECKINS.pop(project_id, None)
            _persist_pending_checkins()
            core.end_authoritative_edit(project_id)
            if previous_lease_id and not _lease_has_checkout(previous_lease_id):
                auth.sessions.deactivate_lease_id(previous_lease_id)
        return updated, result.to_dict()


def _core_lifecycle_handler(project_id: str, command: dict[str, Any], identity: Identity) -> dict[str, Any]:
    params = dict(command.get("params", {}))
    _project, result = _coordinate_lifecycle_transition(
        project_id, str(params.get("action", "")), identity,
        client=str(command.get("client", "script")), force=bool(params.get("force", False)),
        intent=str(params.get("intent", "")) or None, archive_log=str(params.get("log", "")),
        archive_check_in=bool(params.get("archive", True)),
        archive_name=str(params.get("archive_name", "")),
        overwrite_version_id=str(params.get("overwrite_version_id", "")),
    )
    return result


app.include_router(create_core_router(
    core, _websocket_identity, lifecycle_handler=_core_lifecycle_handler,
    write_activity=_record_model_write_activity,
))


class CreateProjectRequest(BaseModel):
    name: str = "New MuJoCo Project"
    demo: bool = True
    category: str | None = None
    source_project_id: str | None = None


class ReclassifyProjectRequest(BaseModel):
    category: str


class ProjectCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent: str = ""


class ModelTypeMoveRequest(BaseModel):
    target_parent: str = ""
    before: str = ""


class ModelTypeRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class DeliveryBindingRequest(BaseModel):
    path: str


class ProjectCloneRequest(BaseModel):
    # Empty names remain accepted for backwards-compatible auto naming.
    # mesh_folder_name is consumed only by baseline /fork; copy-version reuses the source public asset folder.
    # version_id is optional so existing copy-version clients keep their old behavior.
    mesh_folder_name: str = Field(default="", max_length=120)
    # Backwards-compatible omission continues copying; the V2.16.11.1 Hub UI
    # explicitly defaults to binding an existing model-type public mesh folder.
    mesh_asset_strategy: str = Field(default="copy_frozen", pattern=r"^(copy_frozen|bind_existing)$")
    mesh_asset_reference: str = Field(default="", max_length=400)
    model_name: str = Field(default="", max_length=160)
    version_id: str = Field(default="", pattern=r"^[A-Za-z0-9_-]*$", max_length=120)


class ProjectLifecycleRequest(BaseModel):
    action: str
    # Only explicit manual check-in may choose false; automatic and force paths archive.
    archive: bool = True
    log: str = Field(default="", max_length=2000)
    archive_name: str = Field(default="", max_length=160)
    overwrite_version_id: str = Field(default="", max_length=120)


class BaselineCreateRequest(BaseModel):
    # Transient create-time display name.  It is persisted only through the existing
    # ProjectSpec.name truth; no second baseline-name field is introduced.
    name: str = Field(default="", max_length=160)
    log: str = Field(default="", max_length=2000)
    # Browser Gantt refresh is optional.  When present, baseline verifies and reuses
    # that freshly rendered PNG; API-only callers fall back to the existing server renderer.
    gantt_saved_at: float | None = None


class HubProjectPropertiesRequest(BaseModel):
    """Narrow Hub mutation envelope; authoritative project data stays server-side."""
    name: str | None = Field(default=None, max_length=160)
    archive_order: list[str] | None = Field(default=None, max_length=1000)


class EditSessionLeaveRequest(BaseModel):
    project: ProjectSpec | None = None


class VersionSummaryRequest(BaseModel):
    feedback: str = ""
    archive: bool = False


class ArchiveVersionRequest(BaseModel):
    log: str = Field(default="", max_length=2000)
    archive_name: str = Field(default="", max_length=160)
    overwrite_version_id: str = Field(default="", max_length=120)


class TimeSeriesSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    overwrite_filename: str = ""


class QuickOptimizationRequest(BaseModel):
    step_ids: list[str] = Field(default_factory=list, max_length=500)


class WebViewerRequest(BaseModel):
    quick_results: dict[str, float] = Field(default_factory=dict)


class AgentRunRequest(BaseModel):
    skill_id: str
    goal: str = ""


class LLMConfigRequest(BaseModel):
    base_url: str = "https://yice.byd.com/ai-gate/v1/chat/completions"
    model: str = "DeepSeek-R1-Pro"
    context_rounds: int = Field(default=20, ge=1, le=100)
    include_operation_log: bool = True
    include_artifacts: bool = True
    include_variables: bool = True
    api_key: str | None = None


class LegacyImportRequest(BaseModel):
    data: dict[str, Any]


class ProjectImportRequest(BaseModel):
    data: dict[str, Any]
    target_category: str | None = Field(default=None, max_length=400)


class ModelingInfoImportRequest(BaseModel):
    data: dict[str, Any]
    import_measurements: bool = True


class MeshScanRequest(BaseModel):
    path: str


class AdminMeshSyncRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class AdaptiveMeshRequest(BaseModel):
    layer_id: str
    seed_filename: str


class ParameterApplyRequest(BaseModel):
    values: dict[str, Any]
    aliases: dict[str, str] | None = None


class ProjectCompareRequest(BaseModel):
    project_ids: list[str]
    variables: list[str] = Field(default_factory=list)
    skill_id: str = "compare-variable-sets"


class CsvExportItem(BaseModel):
    filename: str
    content: str
    # V2.16.10: stable axis identity independent of display filename.
    asset_key: str = ""


class BatchCsvExportRequest(BaseModel):
    directory: str = ""
    # V2.13.1: empty is valid for the compatibility ``delivery=true`` branch,
    # which now means "build the model time-series library" and ignores legacy
    # per-axis payloads.  The desktop folder branch still requires at least one file.
    files: list[CsvExportItem] = Field(default_factory=list, max_length=200)
    delivery: bool = False
    tables_only: bool = False  # Export ordinary axis CSV into delivery/表格文件夹 without TSJSON rewrite.


class TimeSeriesParseRequest(BaseModel):
    joint_mapping: dict[str, str] = Field(default_factory=dict)
    filename: str = ""
    content: str | None = None
    server_filename: str | None = None
    source_project_id: str | None = None  # Optional authorized read-only TSJSON source.


class AssistantStreamRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str


class ClientTicketRequest(BaseModel):
    purpose: str


class PasswordRequest(BaseModel):
    password: str


class ModelAssetFolderRequest(BaseModel):
    category: str = Field(min_length=1, max_length=400)
    name: str = Field(min_length=1, max_length=80)


class ModelAssetCopyRequest(BaseModel):
    category: str = Field(min_length=1, max_length=400)
    source: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)


class EditActivityRequest(BaseModel):
    open_project_ids: list[str] = Field(default_factory=list, max_length=32)
    recently_active: bool = False


class ProjectSceneRequest(BaseModel):
    scene: str = Field(default="", max_length=255)


COMPARISON_SKILLS = [{
    "id": "compare-variable-sets",
    "name": "Compare project variable sets",
    "description": "Compare selected resolved variables, structure counts and distance minima across projects.",
    "input": {"project_ids": "2-20 project ids", "variables": "optional variable names"},
}]

MODEL_ASSET_UPLOAD_EXTENSIONS = {
    ".stl", ".obj", ".mtl", ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".webp",
}
MAX_PROJECT_JSON_BYTES = 20 * 1024 * 1024
MAX_MODEL_ASSET_BYTES = 2 * 1024 * 1024 * 1024
MAX_MODEL_UPLOAD_BYTES = 8 * 1024 * 1024 * 1024
MAX_PROJECT_BUNDLE_FILES = 20000


def _require_model_asset_library_write() -> Identity:
    identity = active_identity()
    if identity.role not in {"engineer", "admin"}:
        raise HTTPException(403, "只有工程师或管理员可以维护数模资产")
    return identity


def _existing_model_asset_category(category: str) -> str:
    try:
        value = store.normalize_category(category)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    categories = store.categories()
    if value == "None":
        raise HTTPException(404, "模型类型不存在，不能建立数模资产库")
    if value not in set(categories):
        portable = [item for item in categories if item.casefold() == value.casefold()]
        if len(portable) != 1:
            raise HTTPException(404, "模型类型不存在，不能建立数模资产库")
        value = portable[0]
    return store.canonical_model_asset_category(value)


def _model_asset_usage(reference: str) -> list[dict[str, str]]:
    return [
        {
            "id": str(item.get("id", "")),
            "name": str(item.get("name", "")),
            "status": str(item.get("lifecycle_status", "checked_in")),
        }
        for item in store.list()
        if str(item.get("mesh_root", "")).casefold() == str(reference).casefold()
    ]


def _model_asset_library_payload(category: str, folder: str = "") -> dict[str, Any]:
    value = _existing_model_asset_category(category)
    identity = active_identity()
    folders: list[dict[str, Any]] = []
    for item in store.list_model_asset_folders(value):
        usage = _model_asset_usage(str(item["reference"]))
        folders.append({**item, "usage": usage, "usage_count": len(usage)})

    requested = str(folder or "").strip()
    selected = requested
    selection_state = "exact" if requested else "none"
    if requested and not any(item["name"] == requested for item in folders):
        portable = [
            str(item["name"]) for item in folders
            if str(item["name"]).casefold() == requested.casefold()
        ]
        if len(portable) == 1:
            selected = portable[0]
            selection_state = "casefold_repaired"
        else:
            # Cross-machine imports and reclassification can leave a source-server
            # @model_assets reference. Library reads must still open so the user
            # can bind an existing server folder instead of receiving a 404.
            selected = ""
            selection_state = "missing"

    files = store.model_asset_folder_inventory(value, selected) if selected else []
    if selected:
        for item in files:
            if item.get("kind") == "file":
                query = urlencode({"category": value, "folder": selected, "path": str(item.get("path", ""))})
                item["url"] = f"/api/model-asset-library/file?{query}"
    return {
        "category": value,
        "root": f"model_asset_libraries/{value}",
        "writable": identity.role in {"engineer", "admin"},
        "folders": folders,
        "selected": selected,
        "requested_folder": requested,
        "selection_state": selection_state,
        "files": files,
    }


async def _store_model_asset_uploads(
    files: list[UploadFile], requested_paths: list[Any], target_root: Path,
) -> tuple[list[str], list[str], list[str]]:
    """Write validated browser asset uploads into one managed version folder."""
    uploaded: list[str] = []
    uploaded_meshes: list[str] = []
    rejected: list[str] = []
    total_size = 0
    target_root = target_root.resolve()
    for index, upload in enumerate(files):
        supplied_name = str(requested_paths[index]) if index < len(requested_paths) else str(upload.filename or "")
        supplied_parts = supplied_name.replace("\\", "/").split("/")
        if any(part in {"..", ""} for part in supplied_parts) or supplied_name.startswith(("/", "\\")):
            rejected.append(supplied_name)
            continue
        raw_parts = [part for part in supplied_parts if part != "."]
        relative_parts = raw_parts[1:] if len(raw_parts) > 1 else raw_parts
        relative = Path(*relative_parts) if relative_parts else Path("")
        filename = relative.as_posix()
        if not filename or relative.suffix.lower() not in MODEL_ASSET_UPLOAD_EXTENSIONS:
            rejected.append(supplied_name)
            continue
        target = (target_root / relative).resolve()
        if target_root not in target.parents:
            rejected.append(supplied_name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        try:
            with target.open("wb") as stream:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    total_size += len(chunk)
                    if size > MAX_MODEL_ASSET_BYTES:
                        raise HTTPException(413, f"模型资产过大：{filename}")
                    if total_size > MAX_MODEL_UPLOAD_BYTES:
                        raise HTTPException(413, "本次模型资产上传总量不能超过 8 GiB")
                    stream.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        uploaded.append(filename)
        if relative.suffix.lower() in SUPPORTED_MESH_EXTENSIONS:
            uploaded_meshes.append(filename)
    return uploaded, uploaded_meshes, rejected


def _sample_curve(values: list[Any], maximum: int = 180) -> list[Any]:
    if len(values) <= maximum:
        return [_safe_json_number(value) for value in values]
    step = max(1, len(values) // maximum)
    sampled = values[::step]
    if sampled[-1] != values[-1]:
        sampled.append(values[-1])
    return [_safe_json_number(value) for value in sampled]


def _safe_json_number(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _baseline_seal(state: dict[str, Any]) -> str:
    canonical = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _apply_imported_ui(project_id: str, ui: dict[str, Any]) -> None:
    identity = active_identity()
    with core.acquire(project_id) as instance:
        for key, value in ui.items():
            result = instance.bus.dispatch({
                "tool_id": "ui.set", "params": {"path": f"ui.{key}", "value": value},
                "actor": identity.username, "client": "human_ui",
            })
            if not result.ok:
                raise ValueError(str(result.errors))


def _require_editable(project: ProjectSpec) -> None:
    require_project_access(project, write=True)
    if project.lifecycle.status != "checked_out" and not core.is_ephemeral(project.id):
        raise HTTPException(status_code=409, detail="项目处于只读状态，请先签出再修改配置")


def _latest_archive_version(project: ProjectSpec) -> dict[str, Any] | None:
    """Return the newest work archive; baselines intentionally have no archive property."""
    if project.lifecycle.status == "baseline":
        return None
    versions = store.list_versions(project.id)
    return versions[0] if versions else None


from .port_settings import load_ports as _load_deployment_ports

DEPLOYMENT_PORTS = _load_deployment_ports()
VZ_INTERNAL_PORT = DEPLOYMENT_PORTS["vz"]
VZ_INTERNAL_BASE_URL = os.getenv("MUJOCO_STUDIO_VZ_URL", f"http://127.0.0.1:{VZ_INTERNAL_PORT}").rstrip("/")
VZ_BRIDGE_TOKEN = os.getenv("MUJOCO_STUDIO_VZ_BRIDGE_TOKEN", "").strip()


class VZIntegrationError(RuntimeError):
    pass


def _vz_json(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None, allow_404: bool = False) -> dict[str, Any] | None:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(f"{VZ_INTERNAL_BASE_URL}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=8.0) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None
        try:
            body = json.loads(exc.read().decode("utf-8", errors="replace"))
            detail = body.get("error") or body.get("detail") or str(exc)
        except Exception:
            detail = str(exc)
        raise VZIntegrationError(f"VZ 服务返回 HTTP {exc.code}：{detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise VZIntegrationError(f"无法连接集成 VZ 服务（{VZ_INTERNAL_BASE_URL}）：{exc}") from exc
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise VZIntegrationError("VZ 服务返回了无法解析的数据") from exc
    return parsed if isinstance(parsed, dict) else {"data": parsed}


def _vz_upload_asset(model_id: str, source: Path, relative_name: str) -> None:
    parsed = urllib.parse.urlparse(VZ_INTERNAL_BASE_URL)
    if parsed.scheme not in {"http", "https"}:
        raise VZIntegrationError("VZ 服务地址必须使用 HTTP/HTTPS")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_cls(parsed.hostname, port, timeout=30)
    prefix = parsed.path.rstrip("/")
    query = urllib.parse.urlencode({"filename": source.name, "relative_path": f"hub/{relative_name}"})
    endpoint = f"{prefix}/api/models/{urllib.parse.quote(model_id)}/assets?{query}"
    size = source.stat().st_size
    try:
        connection.putrequest("POST", endpoint)
        connection.putheader("Content-Type", "application/octet-stream")
        connection.putheader("Content-Length", str(size))
        connection.putheader("Accept", "application/json")
        connection.endheaders()
        with source.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                connection.send(chunk)
        response = connection.getresponse()
        raw = response.read()
        if response.status >= 400:
            try:
                detail = json.loads(raw.decode("utf-8", errors="replace")).get("error", raw.decode("utf-8", errors="replace"))
            except Exception:
                detail = raw.decode("utf-8", errors="replace")
            raise VZIntegrationError(f"上传数模 {relative_name} 失败：HTTP {response.status} {detail}")
    except VZIntegrationError:
        raise
    except OSError as exc:
        raise VZIntegrationError(f"上传数模 {relative_name} 到 VZ 失败：{exc}") from exc
    finally:
        connection.close()


def _vz_upload_time_series_archive(model_id: str, payload: bytes) -> dict[str, Any]:
    """Atomically replace one VZ model's synchronized time-series library."""
    parsed = urllib.parse.urlparse(VZ_INTERNAL_BASE_URL)
    if parsed.scheme not in {"http", "https"}:
        raise VZIntegrationError("VZ 服务地址必须使用 HTTP/HTTPS")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_cls(parsed.hostname, port, timeout=45)
    prefix = parsed.path.rstrip("/")
    endpoint = f"{prefix}/api/models/{urllib.parse.quote(model_id)}/time-series-sync"
    try:
        connection.putrequest("POST", endpoint)
        connection.putheader("Content-Type", "application/zip")
        connection.putheader("Content-Length", str(len(payload)))
        connection.putheader("Accept", "application/json")
        connection.endheaders()
        if payload:
            connection.send(payload)
        response = connection.getresponse()
        raw = response.read()
        if response.status >= 400:
            try:
                detail = json.loads(raw.decode("utf-8", errors="replace")).get("error", raw.decode("utf-8", errors="replace"))
            except Exception:
                detail = raw.decode("utf-8", errors="replace")
            raise VZIntegrationError(f"同步时序库失败：HTTP {response.status} {detail}")
        parsed_body = json.loads(raw.decode("utf-8")) if raw else {}
        return parsed_body if isinstance(parsed_body, dict) else {"data": parsed_body}
    except VZIntegrationError:
        raise
    except (OSError, ValueError) as exc:
        raise VZIntegrationError(f"同步时序库到 VZ 失败：{exc}") from exc
    finally:
        connection.close()


def _vz_sync_time_series_library(project: ProjectSpec, *, model_id: str = "") -> dict[str, Any]:
    status = _vz_status_for_project(project)
    target_model_id = str(model_id or status.get("model_id", "") or "")
    if not target_model_id:
        return {"synced": False, "reason": "model_not_published"}
    library = store.time_series_directory(project, create=True)
    buffer = io.BytesIO()
    # VZ V0.3.2.1 accepts only VZ_TIME_SERIES CSV.  Encode the bridge CSV
    # in memory; Studio's physical time-series library is TSJSON-only.
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        documents = sorted(library.glob("*.tsjson"), key=lambda item: item.stat().st_mtime, reverse=True)
        for path in documents[:1]:
            if not path.is_file() or path.is_symlink():
                continue
            parsed = parse_tsjson(path.read_text("utf-8-sig"), project)
            working = ProjectSpec.model_validate(project.model_dump())
            working.drives = [DriveSpec.model_validate(row) for row in parsed["drives"]]
            legacy_name, legacy_content, mapping_files = build_time_series_bundle(working, parsed["channels"])
            archive.writestr(legacy_name, legacy_content.encode("utf-8"))
            for name, content in mapping_files:
                archive.writestr(name, content.encode("utf-8"))
    result = _vz_upload_time_series_archive(target_model_id, buffer.getvalue())
    result.setdefault("synced", True)
    result.setdefault("model_id", target_model_id)
    return result



def _vz_mesh_files(project: ProjectSpec) -> list[tuple[str, Path]]:
    references = sorted({str(mesh.filename or "").replace("\\", "/").strip() for layer in project.layers for mesh in layer.meshes if str(mesh.filename or "").strip()})
    if not references:
        return []
    root = store.resolve_mesh_root(project.id, project.mesh_root).resolve()
    result: list[tuple[str, Path]] = []
    missing: list[str] = []
    for relative in references:
        candidate = (root / Path(relative)).resolve()
        if candidate != root and root not in candidate.parents:
            raise VZIntegrationError(f"模型数模路径越界：{relative}")
        if candidate.suffix.lower() not in SUPPORTED_MESH_EXTENSIONS or not candidate.is_file():
            missing.append(relative)
            continue
        result.append((relative, candidate))
    if missing:
        raise VZIntegrationError("推送前请修复缺失数模引用：" + "、".join(missing[:12]) + ("…" if len(missing) > 12 else ""))
    return result


def _vz_version_tuple(value: Any) -> tuple[int, int, int]:
    parts = [int(item) for item in re.findall(r"\d+", str(value or ""))[:3]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _vz_drive_projection_sources(project: ProjectSpec) -> list[dict[str, Any]]:
    """Return Hub drive identities plus drives that only survive in Hub time-series CSVs.

    ProjectSpec remains authoritative for current drive identity.  The synchronized
    Hub time-series library is then scanned newest-first and contributes only drive
    ids that are not present in the current ProjectSpec.  This repairs legacy/model
    states where a valid sequence still references a drive that was not projected
    into ``project.drives`` without creating a second persisted drive table.
    """
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for drive in project.drives:
        if hasattr(drive, "model_dump"):
            payload = drive.model_dump(exclude={"segments"})
        elif hasattr(drive, "dict"):
            payload = drive.dict(exclude={"segments"})
        elif isinstance(drive, dict):
            payload = {key: copy.deepcopy(value) for key, value in drive.items() if key != "segments"}
        else:
            payload = {
                "id": getattr(drive, "id", ""), "name": getattr(drive, "name", ""),
                "joint_id": getattr(drive, "joint_id", ""), "role": getattr(drive, "role", ""),
                "enabled": getattr(drive, "enabled", True),
            }
        drive_id = str(payload.get("id") or "").strip()
        if not drive_id or drive_id in seen:
            continue
        seen.add(drive_id)
        sources.append(payload)

    try:
        root = store.time_series_directory(project, create=True)
        candidates = sorted(
            (path for path in root.glob("*.tsjson") if path.is_file() and not path.is_symlink()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except (OSError, ValueError):
        candidates = []
    for path in candidates:
        try:
            parsed = parse_tsjson(path.read_text("utf-8-sig"), project)
        except (OSError, UnicodeError, ValueError):
            continue
        for payload in parsed.get("drives", []) or []:
            if not isinstance(payload, dict):
                continue
            drive_id = str(payload.get("id") or "").strip()
            if not drive_id or drive_id in seen:
                continue
            seen.add(drive_id)
            sources.append({key: copy.deepcopy(value) for key, value in payload.items() if key != "segments"})
    return sources


def _vz_engineer_drive_settings(
    project: ProjectSpec,
    existing_model: dict[str, Any] | None = None,
    *,
    source_drives: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Project Hub/time-series drive identity into VZ engineer calibration rows.

    Timing remains exclusively in the synchronized time-series library.  The
    engineer page owns only drive identity, joint binding and VZ-local calibration.
    Current ProjectSpec drives are primary; valid Hub time-series CSVs may supply
    additional drive identities through ``source_drives``.  First publication uses
    0 -> 30 with speed 30.  Refreshes from V2.13.2+ preserve local calibration.
    """
    existing = existing_model if isinstance(existing_model, dict) else {}
    source_meta = existing.get("_hub_source") if isinstance(existing.get("_hub_source"), dict) else {}
    preserve_local = _vz_version_tuple(source_meta.get("source_version")) >= (2, 13, 2)
    previous: dict[str, dict[str, Any]] = {}
    if preserve_local:
        for part in existing.get("activity_parts", []) or []:
            if not isinstance(part, dict):
                continue
            for motion in part.get("motions", []) or []:
                if not isinstance(motion, dict):
                    continue
                drive_id = str(motion.get("exchange_drive_id") or "").strip()
                if drive_id and drive_id not in previous:
                    previous[drive_id] = motion

    drives = source_drives if source_drives is not None else list(project.drives)
    parts: list[dict[str, Any]] = []
    for drive in drives:
        if isinstance(drive, dict):
            drive_id = str(drive.get("id") or "").strip()
            drive_name = str(drive.get("name") or drive_id or "驱动")
            joint_id = str(drive.get("joint_id") or "")
            role = str(drive.get("role") or "")
            enabled = bool(drive.get("enabled", True))
        else:
            drive_id = str(getattr(drive, "id", "") or "").strip()
            drive_name = str(getattr(drive, "name", drive_id or "驱动"))
            joint_id = str(getattr(drive, "joint_id", "") or "")
            role = str(getattr(drive, "role", "") or "")
            enabled = bool(getattr(drive, "enabled", True))
        if not drive_id:
            continue
        old = previous.get(drive_id, {})
        p0 = float(old.get("position_0_percent", 0.0)) if old else 0.0
        p100 = float(old.get("position_100_percent", 30.0)) if old else 30.0
        if abs(p100 - p0) <= 1e-12:
            p100 = p0 + 30.0
        speed = float(old.get("rated_speed", 30.0)) if old else 30.0
        if not math.isfinite(speed) or speed <= 0:
            speed = 30.0
        mode = str(old.get("mode", "ease")) if old else "ease"
        motion = {
            "id": f"motion_{drive_id}",
            "name": drive_name,
            "joint_id": joint_id,
            "position_0_percent": p0,
            "position_100_percent": p100,
            "mode": mode,
            "rated_speed": speed,
            "enabled": enabled,
            "exchange_drive_id": drive_id,
            "exchange_drive_name": drive_name,
            "exchange_drive_role": role,
            # Do not embed exchange_segment here: Hub schedules belong to 时序库.
            "exchange_motion_snapshot": {
                "name": drive_name,
                "joint_id": joint_id,
                "position_0_percent": p0,
                "position_100_percent": p100,
                "mode": mode,
                "rated_speed": speed,
                "enabled": enabled,
            },
        }
        parts.append({
            "id": f"part_{drive_id}",
            "name": drive_name,
            "enabled": enabled,
            "motions": [motion],
        })
    return parts


def _vz_status_for_project(project: ProjectSpec) -> dict[str, Any]:
    raw = project.metadata.get("vz_push", {})
    if not isinstance(raw, dict) or str(raw.get("source_project_id", "")) != project.id:
        return {"enabled": False, "model_id": "", "original_name": project.name}
    return copy.deepcopy(raw)


def _vz_publish_project(project: ProjectSpec) -> dict[str, Any]:
    health = _vz_json("/api/health") or {}
    status = _vz_status_for_project(project)
    model_id = str(status.get("model_id", "") or "")
    model: dict[str, Any] | None = None
    created_new = False
    if model_id:
        existing = _vz_json(f"/api/models/{urllib.parse.quote(model_id)}", allow_404=True)
        if existing:
            model = existing.get("model") if isinstance(existing.get("model"), dict) else None

    exchange = export_modeling_exchange(project, __version__, include_measurements=True)
    mesh_files = _vz_mesh_files(project)
    if model is None:
        created = _vz_json(
            "/api/models/import-modeling-info", method="POST",
            payload={"data": exchange, "mode": "new", "import_measurements": True},
        ) or {}
        model = created.get("model") if isinstance(created.get("model"), dict) else None
        if not model or not model.get("id"):
            raise VZIntegrationError("VZ 未返回新建模型 ID")
        model_id = str(model["id"])
        created_new = True

    try:
        # An interrupted previous upload can leave metadata whose physical file is
        # gone. Repair first, then reconcile the Hub-owned manifest on every push.
        repaired = _vz_json(f"/api/models/{urllib.parse.quote(model_id)}/assets/repair", method="POST", payload={}) or {}
        if isinstance(repaired.get("model"), dict):
            model = repaired["model"]
        current_assets = list((model or {}).get("assets", []))
        desired = {relative.replace("\\", "/").strip().casefold(): (relative, source) for relative, source in mesh_files}
        kept: set[str] = set()
        for asset in current_assets:
            asset_id = str(asset.get("id", "") or "")
            source_path = str(asset.get("source_path", "") or asset.get("name", "") or "").replace("\\", "/").strip()
            key = source_path.casefold()
            target = desired.get(key)
            if target is None:
                # Hub-managed VZ models do not expose a separate asset-manager in
                # the integrated engineer surface; stale entries therefore belong
                # to an older Hub revision and must not shadow current selection.
                if asset_id:
                    _vz_json(f"/api/models/{urllib.parse.quote(model_id)}/assets/{urllib.parse.quote(asset_id)}", method="DELETE")
                continue
            relative, source = target
            expected_size = source.stat().st_size
            if key in kept or int(asset.get("size", -1) or -1) != expected_size:
                if asset_id:
                    _vz_json(f"/api/models/{urllib.parse.quote(model_id)}/assets/{urllib.parse.quote(asset_id)}", method="DELETE")
                continue
            kept.add(key)
        for key, (relative, source) in desired.items():
            if key not in kept:
                _vz_upload_asset(model_id, source, relative)

        previous_engineer_model = copy.deepcopy(model) if isinstance(model, dict) else None
        overwritten = _vz_json(
            "/api/models/import-modeling-info", method="POST",
            payload={"data": exchange, "mode": "overwrite", "model_id": model_id, "import_measurements": True},
        ) or {}
        if isinstance(overwritten.get("model"), dict):
            model = overwritten["model"]
        if isinstance(model, dict):
            model["activity_parts"] = _vz_engineer_drive_settings(
                project, previous_engineer_model, source_drives=_vz_drive_projection_sources(project)
            )
        expected_links = sum(1 for layer in project.layers for mesh in layer.meshes if str(mesh.filename or "").strip())
        relinked = int(overwritten.get("relinked_assets", 0) or 0)
        if relinked != expected_links:
            raise VZIntegrationError(f"VZ 数模同步后仍有未解析引用：期望 {expected_links} 个，已关联 {relinked} 个")
    except Exception:
        # Only a model created by this call is safe to roll back wholesale.  An
        # already-published engineer model may contain VZ-local configuration.
        if created_new:
            try:
                _vz_json(f"/api/models/{urllib.parse.quote(model_id)}", method="DELETE", allow_404=True)
            except Exception:
                pass
        raise

    if model is None:
        raise VZIntegrationError("VZ 模型同步后未返回模型数据")
    source_meta = model.get("_hub_source", {}) if isinstance(model.get("_hub_source"), dict) else {}
    source_meta.update({
        "project_id": project.id,
        "original_name": str(status.get("original_name") or project.name),
        "published": True,
        "source": "MuJoCo Studio Hub",
        "source_version": __version__,
    })
    model["_hub_source"] = source_meta
    saved = _vz_json(f"/api/models/{urllib.parse.quote(model_id)}", method="PUT", payload={"model": model}) or {}
    model = saved.get("model") if isinstance(saved.get("model"), dict) else model
    _vz_sync_time_series_library(project, model_id=model_id)
    now = datetime.now(timezone.utc).isoformat()
    next_status = {
        "enabled": True,
        "model_id": model_id,
        "source_project_id": project.id,
        "original_name": str(status.get("original_name") or project.name),
        "published_at": str(status.get("published_at") or now),
        "updated_at": now,
        "vz_version": str(health.get("version", "0.3.2.1")),
    }
    project.metadata["vz_push"] = next_status
    store.save(project, archive=False)
    core.drop(project.id)
    return next_status


def _vz_set_published(project: ProjectSpec, enabled: bool) -> dict[str, Any]:
    status = _vz_status_for_project(project)
    if enabled:
        return _vz_publish_project(project)
    model_id = str(status.get("model_id", "") or "")
    if model_id:
        existing = _vz_json(f"/api/models/{urllib.parse.quote(model_id)}", allow_404=True)
        if existing and isinstance(existing.get("model"), dict):
            model = existing["model"]
            source_meta = model.get("_hub_source", {}) if isinstance(model.get("_hub_source"), dict) else {}
            source_meta.update({
                "project_id": project.id,
                "original_name": str(status.get("original_name") or project.name),
                "published": False,
                "source": "MuJoCo Studio Hub",
                "source_version": __version__,
            })
            model["_hub_source"] = source_meta
            # Hub-side关闭推送只改变发布状态，不物理删除 VZ 模型目录。
            # VZ /api/models 会统一隐藏 published=false 的 Hub-managed 模型，
            # 因而用户/工程师模型库会立即同步移除；保留目录可让再次推送时
            # 继续复用工程师本地校准和 time_series_workspace。只有工程师
            # 显式“移除模型”才进入 VZ trash 并通过回调关闭 Hub 开关。
            _vz_json(f"/api/models/{urllib.parse.quote(model_id)}", method="PUT", payload={"model": model})
    next_status = {
        **status,
        "enabled": False,
        "source_project_id": project.id,
        "original_name": str(status.get("original_name") or project.name),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    project.metadata["vz_push"] = next_status
    store.save(project, archive=False)
    core.drop(project.id)
    return next_status


def _vz_disable_push_from_removed_model(project_id: str, model_id: str, *, reason: str) -> dict[str, Any]:
    """Mirror a VZ-side removal back into Hub without calling VZ again."""
    project = store.get(project_id)
    status = _vz_status_for_project(project)
    expected_model_id = str(status.get("model_id", "") or "")
    if expected_model_id and model_id and expected_model_id != model_id:
        return {"updated": False, "reason": "model_id_mismatch", "vz_push": status}
    now = datetime.now(timezone.utc).isoformat()
    next_status = {
        **status,
        "enabled": False,
        "model_id": expected_model_id or str(model_id or ""),
        "source_project_id": project.id,
        "original_name": str(status.get("original_name") or project.name),
        "updated_at": now,
        "removed_from_vz_at": now,
        "last_sync_reason": str(reason or "vz_model_removed"),
    }
    project.metadata["vz_push"] = next_status
    store.save(project, archive=False)
    core.drop(project.id)
    return {"updated": True, "reason": str(reason or "vz_model_removed"), "vz_push": next_status}


def _vz_reconcile_push_catalog(projects: list[dict[str, object]]) -> list[dict[str, object]]:
    """Repair stale Hub=true rows when their VZ projection no longer exists."""
    enabled = [item for item in projects if bool((item.get("vz_push") or {}).get("enabled"))]
    if not enabled:
        return projects
    try:
        payload = _vz_json("/api/models") or {}
    except VZIntegrationError as exc:
        LOGGER.warning("Unable to reconcile Hub/VZ push catalog: %s", exc)
        return projects
    models = payload.get("models", []) if isinstance(payload, dict) else []
    by_id = {str(item.get("id") or ""): item for item in models if isinstance(item, dict)}
    changed = False
    for item in enabled:
        project_id = str(item.get("id") or "")
        status = item.get("vz_push") if isinstance(item.get("vz_push"), dict) else {}
        model_id = str(status.get("model_id") or "")
        model = by_id.get(model_id)
        actual = bool(
            model
            and bool(model.get("hub_pushed"))
            and str(model.get("source_project_id") or "") == project_id
        )
        if actual:
            continue
        try:
            _vz_disable_push_from_removed_model(project_id, model_id, reason="vz_catalog_reconcile")
            changed = True
        except (KeyError, ValueError, OSError) as exc:
            LOGGER.warning("Unable to reconcile stale VZ push state for %s: %s", project_id, exc)
    return store.list() if changed else projects


def _project_preview(project: ProjectSpec, *, include_latest_result: bool = True) -> dict[str, Any]:
    schedule_error = ""
    try:
        resolved_variables, schedule = resolve_schedule(project)
    except ScheduleResolutionError as exc:
        resolved_variables, schedule = exc.partial_variables, exc.partial_schedule
        schedule_error = str(exc)
    except (ValueError, TypeError) as exc:
        resolved_variables, schedule = {}, []
        schedule_error = str(exc)
    end_time = latest_drive_stop_time(schedule, project.simulation.start_time)
    variables: dict[str, Any] = {**project.variables, **resolved_variables, "EndTime": end_time}
    latest, latest_dir = _latest_simulation_record(project.id) if include_latest_result else (None, None)
    latest_freshness = None
    if latest is not None:
        try:
            latest_freshness = freshness(read_provenance(latest_dir), _fingerprint(project.id, project))
        except Exception as exc:  # preview remains available when an asset cannot be hashed
            latest_freshness = {"status": "unknown", "stale": None, "reasons": ["fingerprint_error"], "message": str(exc)}
    distance_curves: list[dict[str, Any]] = []
    if latest:
        times = list(latest.get("times", []))
        for pair_id, curve in latest.get("distance_curves", {}).items():
            values = list(curve.get("values", []))
            distance_curves.append({
                "id": pair_id,
                "name": curve.get("name", pair_id),
                "unit": curve.get("unit", "mm"),
                "minimum_mm": _safe_json_number(curve.get("minimum_mm")),
                "minimum_time_s": curve.get("minimum_time_s"),
                "times": _sample_curve(times),
                "values": _sample_curve(values),
            })
    joint_lookup = {joint.id: joint for layer in project.layers for joint in layer.joints}
    segment_lookup = {segment.id: segment for drive in project.drives for segment in drive.segments}
    cumulative_by_drive: dict[str, float] = {}
    archive_lookup: dict[str, dict[str, Any]] = {}
    gantt = []
    position_cache: dict[float, tuple[dict[str, float], dict[str, float]]] = {}

    def preview_positions_at(time_s: float) -> tuple[dict[str, float], dict[str, float]]:
        key = float(time_s)
        if key not in position_cache:
            position_cache[key] = (drive_positions(schedule, key), joint_positions(schedule, key))
        return position_cache[key]
    for item in schedule:
        if item.profile == "mapping":
            joint = joint_lookup.get(item.joint_id)
            unit = "mm" if joint and joint.type == "translation" else "°"
            blocks = mapping_gantt_blocks(item, schedule)
            for block in blocks:
                block["travel_unit"] = unit
                gantt.append(block)
            travel_start = float(blocks[0].get("travel_start", 0.0)) if blocks else 0.0
            travel_end = float(blocks[-1].get("travel_end", travel_start + item.travel)) if blocks else travel_start + item.travel
            archive_lookup[f"{item.segment_id}:start"] = {"key": f"{item.segment_id}:start", "label": f"{item.drive_name}/{item.name} 起始位置", "value": travel_start, "unit": unit}
            archive_lookup[f"{item.segment_id}:end"] = {"key": f"{item.segment_id}:end", "label": f"{item.drive_name}/{item.name} 结束位置", "value": travel_end, "unit": unit}
            archive_lookup[f"{item.segment_id}:start_time"] = {"key": f"{item.segment_id}:start_time", "label": f"{item.drive_name}/{item.name} 起始时间", "value": item.start, "unit": "s"}
            archive_lookup[f"{item.segment_id}:motion_value"] = {"key": f"{item.segment_id}:motion_value", "label": f"{item.drive_name}/{item.name} 行程", "value": travel_end - travel_start, "unit": unit}
            source_segment = segment_lookup.get(item.segment_id)
            duration_mode = bool(source_segment and source_segment.mode == "duration")
            archive_lookup[f"{item.segment_id}:rate_value"] = {"key": f"{item.segment_id}:rate_value", "label": f"{item.drive_name}/{item.name} {'时长' if duration_mode else '速度'}", "value": item.duration if duration_mode else item.speed, "unit": "s" if duration_mode else f"{unit}/s"}
            continue
        travel_start = cumulative_by_drive.get(item.drive_id, 0.0)
        travel_end = travel_start + item.travel
        cumulative_by_drive[item.drive_id] = travel_end
        joint = joint_lookup.get(item.joint_id)
        unit = "mm" if joint and joint.type == "translation" else "°"
        drive_start_values, joint_start_values = preview_positions_at(item.start)
        drive_end_values, joint_end_values = preview_positions_at(item.end)
        gantt.append({
            "id": item.segment_id, "drive_id": item.drive_id, "drive_name": item.drive_name,
            "joint_id": item.joint_id, "name": item.name, "start": item.start, "end": item.end,
            "duration": item.duration, "travel": item.travel, "travel_start": travel_start,
            "travel_end": travel_end, "travel_unit": unit,
            # V2.6.2 transient projection for legacy-compatible source/companion
            # travel mapping. These are real positions at this segment's time
            # boundaries, unlike the historical simple list-order accumulator.
            "drive_position_start": float(drive_start_values.get(item.drive_id, 0.0)),
            "drive_position_end": float(drive_end_values.get(item.drive_id, 0.0)),
            "joint_position_start": float(joint_start_values.get(item.joint_id, 0.0)) if item.joint_id else 0.0,
            "joint_position_end": float(joint_end_values.get(item.joint_id, 0.0)) if item.joint_id else 0.0,
        })
        archive_lookup[f"{item.segment_id}:start"] = {"key": f"{item.segment_id}:start", "label": f"{item.drive_name}/{item.name} 起始位置", "value": travel_start, "unit": unit}
        archive_lookup[f"{item.segment_id}:end"] = {"key": f"{item.segment_id}:end", "label": f"{item.drive_name}/{item.name} 结束位置", "value": travel_end, "unit": unit}
        archive_lookup[f"{item.segment_id}:start_time"] = {"key": f"{item.segment_id}:start_time", "label": f"{item.drive_name}/{item.name} 起始时间", "value": item.start, "unit": "s"}
        archive_lookup[f"{item.segment_id}:motion_value"] = {"key": f"{item.segment_id}:motion_value", "label": f"{item.drive_name}/{item.name} 行程", "value": item.travel, "unit": unit}
        source_segment = segment_lookup.get(item.segment_id)
        duration_mode = bool(source_segment and source_segment.mode == "duration")
        archive_lookup[f"{item.segment_id}:rate_value"] = {"key": f"{item.segment_id}:rate_value", "label": f"{item.drive_name}/{item.name} {'时长' if duration_mode else '速度'}", "value": item.duration if duration_mode else item.speed, "unit": "s" if duration_mode else f"{unit}/s"}
    selected_archive = {"motion_time": {"key": "motion_time", "label": "运动时间", "value": end_time, "unit": "s"}}
    for drive in project.drives:
        for segment in drive.segments:
            if segment.archive_start and f"{segment.id}:start" in archive_lookup:
                selected_archive[f"{segment.id}:start"] = archive_lookup[f"{segment.id}:start"]
            if segment.archive_end and f"{segment.id}:end" in archive_lookup:
                selected_archive[f"{segment.id}:end"] = archive_lookup[f"{segment.id}:end"]
            if segment.archive_start_time and f"{segment.id}:start_time" in archive_lookup:
                selected_archive[f"{segment.id}:start_time"] = archive_lookup[f"{segment.id}:start_time"]
            if segment.archive_motion_value and f"{segment.id}:motion_value" in archive_lookup:
                item = archive_lookup[f"{segment.id}:motion_value"]
                if segment.gantt_travel_input_mode == "end_position":
                    item = {**item, "label": item["label"].replace("行程", "结束位置"), "value": archive_lookup[f"{segment.id}:end"]["value"]}
                selected_archive[f"{segment.id}:motion_value"] = item
            if segment.archive_rate_value and f"{segment.id}:rate_value" in archive_lookup:
                selected_archive[f"{segment.id}:rate_value"] = archive_lookup[f"{segment.id}:rate_value"]
    order = [key for key in project.archive_order if key in selected_archive]
    order += [key for key in selected_archive if key not in order]
    delivery = store.delivery_directory(project)
    mapping_tables = {
        item.segment_id: [list(point) for point in item.points]
        for item in schedule if item.profile == "mapping"
    }
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "category": project.category,
        "tags": project.tags,
        "mesh_root": project.mesh_root,
        "baseline_mesh_source_reference": str(project.metadata.get("baseline_model_asset_source_reference", "")),
        "updated_at": project.metadata.get("updated_at", ""),
        "version_summary": project.metadata.get("version_summary", ""),
        "version_summary_archived": project.metadata.get("version_summary_archived", False),
        "baseline_log": project.metadata.get("baseline_log", ""),
        "lifecycle_status": project.lifecycle.status,
        "lifecycle": project.lifecycle.model_dump(),
        "vz_push": _vz_status_for_project(project),
        "counts": {
            "layers": len(project.layers),
            "joints": sum(len(layer.joints) for layer in project.layers),
            "segments": sum(len(drive.segments) for drive in project.drives),
            "pairs": len(project.distance_pairs),
            "variables": len(variables),
            "parameters": len(parameter_catalog(project)),
        },
        "variables": variables,
        "gantt": gantt,
        "mapping_tables": mapping_tables,
        "schedule_error": schedule_error,
        "distance_curves": distance_curves,
        "latest_simulation": {
            "engine": latest.get("engine"),
            "end_time": latest.get("end_time"),
            "freshness": latest_freshness,
        } if latest else None,
        # Delivery files are already content-attested.  Do not scan/hash all
        # project artifacts just to populate the two Hub delivery links.
        "attachments": (_current_delivery_outputs(project) if include_latest_result else []),
        # These are optional fields used only to compose the managed model
        # name. They are not project version archives; V2.3.9.8 reserves
        # “归档数据” for the newest item in versions/.
        "archive_fields": [selected_archive[key] for key in order],
        "archive_order": order,
        "delivery_root": store.delivery_bindings().get(project.category, ""),
        "delivery_directory": str(delivery),
    }


def _archive_value_text(value: Any) -> str:
    number = float(value)
    return f"{number:.6f}".rstrip("0").rstrip(".") if math.isfinite(number) else ""


def _critical_data_text(item: dict[str, Any]) -> str:
    try:
        number = float(item.get("value"))
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    text = "0" if abs(number) < 1e-10 else f"{number:.2f}"
    if text.endswith(".00"):
        text = text[:-3]
    unit = str(item.get("unit", ""))
    return f"{text}{unit}"


CRITICAL_DATA_SEPARATOR = ","


def _critical_data_join(items: Any) -> str:
    return CRITICAL_DATA_SEPARATOR.join(str(item) for item in items if str(item))


def _version_display_entry(project_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    result = dict(entry)
    try:
        version = store.get_version(project_id, str(entry["id"]))
        critical_data = _project_preview(version, include_latest_result=False).get("archive_fields", [])
    except (KeyError, ValueError, OSError):
        critical_data = []
    suffix = _critical_data_join(_critical_data_text(item) for item in critical_data)
    result["critical_data"] = critical_data
    result["critical_data_text"] = suffix
    result["display_name"] = f"{result.get('label', '历史版本')}_{suffix}" if suffix else str(result.get("label", "历史版本"))
    return result


def _apply_archive_name(project: ProjectSpec, *, preview: dict[str, Any] | None = None) -> None:
    """Compute delivery suffix without mutating the authoritative model name."""
    if preview is None:
        try:
            preview = _project_preview(project, include_latest_result=False)
        except Exception:
            return
    if preview.get("schedule_error") and project.drives:
        return
    project.metadata.setdefault("archive_base_name", str(project.name))
    values = {str(item["key"]): item for item in preview.get("archive_fields", [])}
    order = [key for key in project.archive_order if key in values]
    order += [key for key in values if key not in order]
    suffixes = [_critical_data_text(values[key]) for key in order]
    project.metadata["delivery_name_suffix"] = _critical_data_join(suffixes)


def _delivery_stem(project: ProjectSpec) -> str:
    """Build the canonical delivery filename stem from model name and selected key-data values."""
    suffix = ""
    try:
        preview = _project_preview(project, include_latest_result=False)
        values = {str(item["key"]): item for item in preview.get("archive_fields", [])}
        order = [key for key in project.archive_order if key in values]
        order += [key for key in values if key not in order]
        suffix = _critical_data_join(_critical_data_text(values[key]) for key in order)
    except Exception:
        suffix = str(project.metadata.get("delivery_name_suffix", "")).strip("_,")
        suffix = _critical_data_join(part for part in re.split(r"[,_，]+", suffix) if part)
    label = f"{project.name}" + (f"_{suffix}" if suffix else "")
    return _safe_filename(label)


def _baseline_fork_checked_copy(should_cancel: Callable[[], bool] | None) -> Callable[[str, str], str]:
    """Keep full-fidelity copy semantics with cancellation between files."""
    def copy_file(source: str, destination: str) -> str:
        if should_cancel and should_cancel():
            raise RuntimeError("使用基线已取消；不会发布不完整的模型")
        result = shutil.copy2(source, destination)
        if should_cancel and should_cancel():
            raise RuntimeError("使用基线已取消；不会发布不完整的模型")
        return result
    return copy_file


def _clone_mesh_to_shared_pool(
    source: ProjectSpec, requested_name: str = "", *, source_mesh_path: Path | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[str, Path]:
    """Copy the selected mesh to a new public folder; clean partial data on any failure."""
    raw = str(requested_name or "").strip()
    if raw and ("/" in raw.replace("\\", "/") or raw in {".", ".."}):
        raise HTTPException(status_code=422, detail="数模资产文件夹名称只能是一层")
    base = re.sub(r'[<>:"|?*\\/\x00-\x1f]+', "_", raw or f"{source.name}_数模副本").strip(" .") or "数模副本"
    if raw:
        try:
            reference, target = store.create_model_asset_folder(source.category, base, uploaded_by=active_identity().username)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    else:
        folder, suffix = base, 2
        while True:
            try:
                reference, target = store.create_model_asset_folder(source.category, folder, uploaded_by=active_identity().username)
                break
            except ValueError as exc:
                if "已存在" not in str(exc):
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                folder = f"{base}_{suffix}"
                suffix += 1
    try:
        if should_cancel and should_cancel():
            raise InterruptedError("使用基线已取消")
        mesh_source = source_mesh_path or _mesh_root_path(source.id, source)
        if mesh_source.is_dir():
            shutil.copytree(mesh_source, target, dirs_exist_ok=True,
                            copy_function=_baseline_fork_checked_copy(should_cancel))
        if should_cancel and should_cancel():
            raise InterruptedError("使用基线已取消")
        store._write_model_asset_metadata(
            target, uploaded_by=active_identity().username, source_reference=str(source.mesh_root or "")
        )
        return reference, target
    except BaseException:
        # Previous versions leaked partially copied public mesh folders when
        # copytree raised before the caller received `target`.
        shutil.rmtree(target, ignore_errors=True)
        raise


def _existing_fork_mesh_asset_reference(source: ProjectSpec, requested: str) -> str:
    """Resolve an explicit, category-scoped existing public folder without creating it.

    A frozen baseline's mesh filenames are authoritative.  Binding a different
    folder with missing filenames must fail rather than silently removing mesh
    references or publishing an unusable work copy.
    """
    reference = str(requested or "").strip()
    prefix = f"@model_assets/{source.category}/"
    folder = reference[len(prefix):] if reference.startswith(prefix) else ""
    if not folder or "/" in folder or "\\" in folder or folder in {".", ".."}:
        raise HTTPException(status_code=422, detail="只能绑定当前模型类型中已有的数模资产文件夹")
    try:
        canonical = store.model_asset_reference(source.category, folder)
        root = store.resolve_model_asset_reference(reference)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"数模资产路径无效：{exc}") from exc
    if canonical.casefold() != reference.casefold() or not root.is_dir() or root.is_symlink():
        raise HTTPException(status_code=422, detail="所选数模资产文件夹不存在或已移动，请重新选择")
    missing: list[str] = []
    for layer in source.layers:
        for mesh in layer.meshes:
            relative = Path(str(mesh.filename))
            candidate = (root / relative).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                raise HTTPException(status_code=422, detail="模型的数模文件路径超出所选资产文件夹")
            if relative.is_absolute() or ".." in relative.parts or not candidate.is_file():
                missing.append(str(mesh.filename))
    if missing:
        names = "、".join(sorted(set(missing))[:5])
        raise HTTPException(status_code=409, detail=f"所选资产缺少模型引用的数模文件（{names}），请改选匹配的版本或复制冻结数模")
    return canonical


def _copy_model_payload(
    source: ProjectSpec, target: ProjectSpec, *, should_cancel: Callable[[], bool] | None = None,
) -> None:
    """Copy all non-authoritative owned files required by copy-version/use-baseline."""
    checked_copy = _baseline_fork_checked_copy(should_cancel)
    source_dir = store.project_directory(source.id)
    target_dir = store.project_directory(target.id)
    source_assets = source_dir / "assets"
    if source_assets.is_dir():
        ignore = shutil.ignore_patterns("baseline_mesh_snapshot") if source.lifecycle.status == "baseline" else None
        shutil.copytree(source_assets, target_dir / "assets", dirs_exist_ok=True,
                        copy_function=checked_copy, ignore=ignore)
    for relative in ("outputs", "results", "core/artifacts"):
        if should_cancel and should_cancel():
            raise InterruptedError("使用基线已取消")
        src, dst = source_dir / relative, target_dir / relative
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True, copy_function=checked_copy)
    source_delivery = store.delivery_directory(source, create=False)
    target_delivery = store.delivery_directory(target, create=True)
    if source_delivery.is_dir():
        store.copy_delivery_tree(source_delivery, target_delivery, should_cancel=should_cancel)
    source_time_series = store.time_series_directory(source, create=False)
    target_time_series = store.time_series_directory(target, create=True)
    if source_time_series.is_dir():
        shutil.copytree(source_time_series, target_time_series, dirs_exist_ok=True, copy_function=checked_copy)

def _require_mutable_delivery(project: ProjectSpec) -> None:
    identity = active_identity()
    require_project_access(project, write=False)
    if identity.role == "guest":
        raise HTTPException(status_code=403, detail="游客不能修改交付数据")
    if project.lifecycle.status == "baseline":
        raise HTTPException(status_code=409, detail="基线模型的数模与交付数据已冻结，只有删除基线模型时才会删除冻结文件夹")


def _require_mutable_mesh_assets(project: ProjectSpec) -> None:
    """Reject every physical mesh-tree mutation for an immutable baseline.

    Temporary baseline editing is intentionally allowed for ProjectSpec/UI state,
    but it must never leak into either the private frozen snapshot or a shared
    model-type mesh folder.  All physical mesh writers reuse this single guard.
    """
    require_project_access(project, write=True)
    if project.lifecycle.status == "baseline":
        raise HTTPException(status_code=409, detail="基线模型的数模与交付数据已冻结，只有删除基线模型时才会删除冻结文件夹")


def _identity_payload(identity: Identity) -> dict[str, Any]:
    return {
        "username": identity.username, "role": identity.role,
        "admin_mode": identity.admin_mode, "single_user": identity.single_user,
    }


@app.post("/api/auth/login")
def login(request: LoginRequest, response: Response) -> dict[str, Any]:
    if SINGLE_USER:
        return _identity_payload(Identity(BUILTIN_ADMIN_USERNAME, "admin", single_user=True))
    identity = auth.login(request.username, request.password)
    response.set_cookie(
        SESSION_COOKIE_NAME, identity.session_id, httponly=True, samesite="lax",
        secure=SECURE_COOKIE, max_age=int(SESSION_TTL_HOURS * 3600), path="/",
    )
    pending_failures = _pending_failures_for_username(identity.username)
    return {
        "username": identity.username, "role": identity.role,
        "pending_lifecycle_failures": pending_failures,
    }


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, Any]:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not token:
        return {"ok": True, "status": "complete", "checked_in_project_ids": [], "deferred_project_ids": [], "failures": []}
    identity = active_identity()
    result = _converge_browser_session(identity)
    if result["status"] in {"complete", "deferred"}:
        auth.sessions.delete(token)
        response.delete_cookie(SESSION_COOKIE_NAME, path="/", samesite="lax", secure=SECURE_COOKIE)
    # failed deliberately preserves both Session and cookie so the user can retry.
    return result


@app.get("/api/auth/me")
def auth_me() -> dict[str, Any]:
    return _identity_payload(active_identity())


@app.post("/api/auth/heartbeat")
def auth_heartbeat(_request: EditActivityRequest | None = None) -> dict[str, Any]:
    identity = active_identity()
    # Session sliding and Lease renewal remain orthogonal. The response projects
    # lease loss explicitly so the browser can recover without guessing from HTTP 200.
    if identity.single_user:
        renewed = True
        lost_reason = None
    else:
        renewed = auth.sessions.touch_lease(identity.session_id)
        _active, lost_reason = auth.sessions.lease_state(identity.session_id)
    checked_out_project_ids = [
        str(item.get("id", "")) for item in store.list()
        if str(item.get("lifecycle_status", "")) == "checked_out"
        and str(item.get("checked_out_by", "")).casefold() == identity.username.casefold()
        and str(item.get("id", ""))
    ]
    return {
        "ok": True,
        "lease_active": renewed,
        "lease_lost_reason": None if renewed else (lost_reason or "revoked"),
        "checked_out_project_ids": checked_out_project_ids,
        "lease_ttl_seconds": LEASE_TTL_SECONDS,
    }


class LeaseReacquireRequest(BaseModel):
    project_ids: list[str] = Field(default_factory=list, max_length=64)


@app.post("/api/auth/lease/reacquire")
def reacquire_edit_lease(request: LeaseReacquireRequest) -> dict[str, Any]:
    identity = active_identity()
    if identity.role not in {"engineer", "admin"}:
        raise HTTPException(403, "当前账号无项目编辑租约")
    if not identity.single_user:
        auth.sessions.activate_lease(identity.session_id)
    requested = list(dict.fromkeys(str(value).strip() for value in request.project_ids if str(value).strip()))
    reacquired: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for project_id in requested:
        try:
            project = store.get(project_id)
            if project.lifecycle.status != "checked_out":
                raise HTTPException(409, "模型当前未签出")
            if str(project.lifecycle.checked_out_by or "").casefold() != identity.username.casefold():
                raise HTTPException(409, f"模型已由 {project.lifecycle.checked_out_by or '其他用户'} 持有")
            updated, _result = _coordinate_lifecycle_transition(
                project_id, "check_out", identity, client="lease_reacquire",
                intent="编辑租约恢复；保持原模型 idle deadline",
            )
            deadline = _pending_deadline(project_id)
            reacquired.append({
                "project_id": project_id,
                "lifecycle_status": updated.lifecycle.status,
                "idle_check_in_deadline": deadline,
            })
        except HTTPException as exc:
            failures.append({"project_id": project_id, "error": str(exc.detail)})
        except Exception as exc:
            failures.append({"project_id": project_id, "error": str(exc)})
    return {"ok": not failures, "reacquired": reacquired, "failures": failures}


@app.post("/api/auth/leave")
async def leave_browser_session(request: Request) -> dict[str, Any]:
    """Persist a final snapshot and close Edit Session state without signing the model in."""
    identity = active_identity()
    saved_project_id = ""
    try:
        payload = await request.json()
    except (ValueError, json.JSONDecodeError):
        payload = {}
    if isinstance(payload, dict) and payload.get("project_id") and isinstance(payload.get("project"), dict):
        project_id = str(payload["project_id"])
        try:
            current = core.get(project_id).project()
            if (current.lifecycle.status == "checked_out"
                    and current.lifecycle.lease_id == identity.lease_id):
                update_project(project_id, ProjectSpec.model_validate(payload["project"]))
                _record_model_write_activity(project_id, identity, "project.replace")
                saved_project_id = project_id
        except (KeyError, ValueError, HTTPException) as exc:
            LOGGER.warning("final browser-leave snapshot rejected for project %s: %s", project_id, exc)
    # Page/Tab lifetime is not Lease lifetime. This only closes transient Edit Session state.
    core.end_lease(identity.lease_id)
    return {"ok": True, "status": "edit_session_closed", "saved_project_id": saved_project_id}


@app.get("/api/auth/users")
def list_accounts() -> dict[str, Any]:
    identity = active_identity()
    if identity.role != "admin" and not (identity.role == "engineer" and identity.admin_mode):
        raise HTTPException(403, "需要管理员或管理员模式权限")
    return {"users": auth_store.list_users()}


@app.post("/api/auth/users", status_code=201)
def create_account(request: UserCreateRequest) -> dict[str, Any]:
    identity = active_identity()
    if identity.role != "admin" and not (identity.role == "engineer" and identity.admin_mode):
        raise HTTPException(403, "需要管理员或管理员模式权限")
    if request.role not in {"guest", "engineer"}:
        raise HTTPException(422, "新增账号角色只能选择“游客”或“工程师”")
    try:
        return auth_store.create_user(request.username, request.password, request.role, created_by=identity.username)
    except AuthStoreError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.delete("/api/auth/users/{username}")
def delete_account(username: str) -> dict[str, Any]:
    identity = active_identity()
    if identity.role != "admin" and not (identity.role == "engineer" and identity.admin_mode):
        raise HTTPException(403, "需要管理员或管理员模式权限")
    if username.casefold() == identity.username.casefold():
        raise HTTPException(409, "不能删除当前登录账号")
    try:
        removed = auth_store.delete_user(username)
    except AuthStoreError as exc:
        raise HTTPException(409, str(exc)) from exc
    for revoked_identity in auth.sessions.identities_for_user(username):
        try:
            _converge_browser_session(revoked_identity)
        except Exception:
            LOGGER.exception("failed to converge revoked user session: user=%s", username)
    auth.sessions.revoke_user(username)
    return removed


@app.post("/api/auth/admin-mode")
def enter_admin_mode(request: PasswordRequest) -> dict[str, Any]:
    identity = active_identity()
    if identity.role != "engineer":
        raise HTTPException(403, "只有工程师可以进入管理员模式")
    key = f"admin-mode:{identity.username.casefold()}"
    retry = auth.limiter.retry_after(key)
    if retry:
        raise HTTPException(429, {"message": "尝试过多，请稍后重试", "retry_after": retry})
    valid, version = auth_store.verify_admin_mode_password(request.password)
    if not valid:
        retry = auth.limiter.failure(key)
        if retry:
            raise HTTPException(429, {"message": "尝试过多，请稍后重试", "retry_after": retry})
        raise HTTPException(401, "管理员模式密码错误或尚未设置")
    auth.limiter.success(key)
    return _identity_payload(auth.sessions.set_admin_mode(identity.session_id, True, version))


@app.delete("/api/auth/admin-mode")
def leave_admin_mode() -> dict[str, Any]:
    identity = active_identity()
    return _identity_payload(auth.sessions.set_admin_mode(identity.session_id, False))


@app.put("/api/auth/admin-mode-password")
def change_admin_mode_password(request: PasswordRequest) -> dict[str, bool]:
    identity = active_identity()
    if identity.role != "admin":
        raise HTTPException(403, "只有管理员可以设置管理员模式密码")
    try:
        auth_store.set_admin_mode_password(request.password, changed_by=identity.username)
    except AuthStoreError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True}


@app.get("/api/admin/storage-location")
def get_storage_location() -> dict[str, Any]:
    identity = active_identity()
    if identity.role != "admin":
        raise HTTPException(403, "只有管理员可以查看数据地址设置")
    location = load_storage_location()
    probe = probe_storage_location(
        ancestor_levels=location["ancestor_levels"], base_path=location.get("manual_base_path", "")
    )
    return {
        **probe,
        "active_data_root": str(DATA_ROOT),
        "environment_override": str(os.getenv("MUJOCO_STUDIO_DATA", "") or "").strip(),
        "restart_required": False,
    }


@app.post("/api/admin/storage-location/probe")
def probe_admin_storage_location(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    identity = active_identity()
    if identity.role != "admin":
        raise HTTPException(403, "只有管理员可以检测数据地址")
    return probe_storage_location(
        ancestor_levels=payload.get("ancestor_levels"), base_path=payload.get("base_path")
    )


@app.put("/api/admin/storage-location")
def update_storage_location(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    identity = active_identity()
    if identity.role != "admin":
        raise HTTPException(403, "只有管理员可以修改数据地址")
    if str(os.getenv("MUJOCO_STUDIO_DATA", "") or "").strip():
        raise HTTPException(409, "当前 MUJOCO_STUDIO_DATA 环境变量已锁定数据根，请先移除环境变量再修改管理员设置")
    try:
        saved = save_storage_location(
            ancestor_levels=payload.get("ancestor_levels"), base_path=str(payload.get("base_path", "") or "")
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**saved, "active_data_root": str(DATA_ROOT)}


@app.get("/api/health")
def health() -> dict[str, Any]:
    try:
        import mujoco  # type: ignore
        mujoco_available = True
        mujoco_version = getattr(mujoco, "__version__", "unknown")
    except ImportError:
        mujoco_available = False
        mujoco_version = None
    return {
        "status": "ok",
        "version": __version__,
        "time": datetime.now(timezone.utc).isoformat(),
        "mujoco_available": mujoco_available,
        "mujoco_version": mujoco_version,
        "project_storage": "server-managed",
        "data_root": str(DATA_ROOT),
        "network_ports": dict(DEPLOYMENT_PORTS),
        "max_archive_versions": MAX_ARCHIVE_VERSIONS,
        "trash_retention_days": TRASH_RETENTION_DAYS,
        "interaction_commit_debounce_ms": INTERACTION_COMMIT_DEBOUNCE_MS,
        "lease_ttl_seconds": LEASE_TTL_SECONDS,
        "kernel_inuse": sum(core._inuse.values()),
        "capabilities": {
            "desktop_enabled": DESKTOP_ENABLED,
            "native_viewer": DESKTOP_ENABLED,
            "server_file_dialogs": DESKTOP_ENABLED,
            "direct_downloads": sys.platform.startswith("linux"),
        },
    }


def _require_desktop_capability() -> None:
    if not DESKTOP_ENABLED:
        raise HTTPException(status_code=403, detail="当前服务器部署未启用桌面能力；请使用浏览器文件通道或 Web 回放")


@app.get("/api/viewers/{pid}/status")
def viewer_status(pid: int) -> dict[str, Any]:
    identity = active_identity()
    if identity.role != "admin" or not LOCAL_ADMIN_VIEWER_ENABLED:
        raise HTTPException(403, "只有管理员可以查看服务端本机 Viewer 状态")
    payload = viewer_process_status(pid)
    return {key: value for key, value in payload.items() if key not in {"log", "project_id"}}


@app.get("/api/projects/{project_id}/latest-simulation")
def latest_project_simulation(project_id: str) -> dict[str, Any]:
    project = store.get(project_id)
    require_project_access(project)
    result_root = store.results(project_id)
    stable = result_root / "latest_simulation.json"
    paths = [stable] if stable.is_file() else []
    if not paths and result_root.is_dir():
        paths = sorted(
            result_root.glob("simulation_*/simulation_result.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    if not paths:
        raise HTTPException(404, "当前项目还没有仿真结果")
    try:
        response = json.loads(paths[0].read_text("utf-8"))
        if paths[0].name == "latest_simulation.json":
            _, latest_dir = _latest_simulation_record(project_id)
            response["simulation_id"] = latest_dir.name if latest_dir else None
        else:
            response["simulation_id"] = paths[0].parent.name
        # Existing route, optional read-only derived bit; no new API endpoint.
        # A missing old-version digest defaults to recomputation, never a
        # guessed match. Read both frozen provenance and current asset hashes.
        _, frozen_dir = _latest_simulation_record(project_id)
        same_snapshot = bool(frozen_dir and response["simulation_id"] == frozen_dir.name)
        is_current = False
        if same_snapshot:
            try:
                proof = read_provenance(frozen_dir)
                current = _fingerprint(project_id, project)
                recorded = proof.get("input_fingerprint", {}) if isinstance(proof, dict) else {}
                assets_equal = recorded.get("assets") == current.get("assets")
                solver_equal = (proof.get("solver_project_digest") == solver_project_digest(project)
                                if isinstance(proof, dict) and proof.get("solver_project_digest")
                                else recorded.get("project") == current.get("project"))
                is_current = bool(assets_equal and solver_equal)
            except Exception:
                is_current = False
        return {"result": response, "path": str(paths[0]), "physical_input_current": is_current}
    except (OSError, ValueError) as exc:
        raise HTTPException(422, f"最新仿真结果无法读取：{exc}") from exc


# Slots cover both model generation and native-process spawn. They belong to
# runtime/Job state, not ProjectSpec, and never block the HTTP worker thread.
_viewer_launch_slots = threading.BoundedSemaphore(max(1, min(2, int(os.getenv("MUJOCO_STUDIO_VIEWER_LAUNCH_SLOTS", "2")))))


@app.post("/api/projects/{project_id}/local-viewer", status_code=202)
def launch_local_admin_viewer(project_id: str) -> dict[str, Any]:
    """Launch the native Viewer on the machine running the authenticated server."""
    identity = active_identity()
    if identity.role != "admin":
        raise HTTPException(403, "只有管理员可以直接启动服务端本机 MuJoCo")
    if not LOCAL_ADMIN_VIEWER_ENABLED:
        raise HTTPException(403, "当前部署已关闭管理员本机 MuJoCo；请设置 MUJOCO_STUDIO_LOCAL_ADMIN_VIEWER=1")
    # Authenticate *before* enqueue; expensive fingerprinting, XML generation
    # and native MuJoCo work run outside the HTTP request on the existing Job
    # pipeline. Response is 202 + job_id, never an HTTP request held until spawn.
    project = get_project(project_id)
    actor = identity.username

    def launch(progress, cancelled, _workspace, _job_id):
        progress(0.01, "等待独立 Viewer 启动槽")
        while not _viewer_launch_slots.acquire(timeout=0.25):
            if cancelled():
                raise InterruptedError("取消等待 Viewer 启动槽")
        try:
            if cancelled():
                raise InterruptedError("已取消 Viewer 启动")
            progress(0.1, "复用当前轨迹 / 准备独立 Viewer 子进程")
            trajectory, _warnings = _current_simulation_trajectory(project_id, project)
            launched = launch_project_viewer(
                _runtime_project(project_id, project),
                store._directory(project_id),
                check_files=True,
                actor=actor,
                trajectory_path=trajectory,
                should_cancel=cancelled,
            )
            if cancelled():
                record = VIEWER_REGISTRY.record(int(launched["pid"]))
                if record and record.process.poll() is None:
                    record.process.terminate()
                raise InterruptedError("取消已启动的 Viewer")
            progress(1.0, "Viewer 子进程已创建，窗口就绪由独立状态接口确认")
            return {**launched, "trajectory_reused": trajectory is not None}
        finally:
            _viewer_launch_slots.release()

    return {"job_id": _submit_project_job(project_id, "native_viewer_launch", launch, timeout_seconds=300)}


@app.get("/api/projects/{project_id}/local-viewer/{pid}/status")
def local_admin_viewer_status(project_id: str, pid: int) -> dict[str, Any]:
    """Return startup diagnostics for an administrator-launched local Viewer.

    This endpoint deliberately does not depend on the legacy desktop capability:
    ``run.py`` disables server-side file dialogs, while administrator local Viewer
    launch is controlled independently by ``LOCAL_ADMIN_VIEWER_ENABLED``.
    """
    identity = active_identity()
    if identity.role != "admin":
        raise HTTPException(403, "只有管理员可以查看服务端本机 MuJoCo 启动状态")
    if not LOCAL_ADMIN_VIEWER_ENABLED:
        raise HTTPException(403, "当前部署已关闭管理员本机 MuJoCo")
    get_project(project_id)
    payload = viewer_process_status(pid)
    if not payload.get("tracked") or payload.get("project_id") != project_id:
        raise HTTPException(404, {"code": "viewer_not_found", "message": "Viewer 启动记录不存在"})
    return payload


@app.post("/api/projects/{project_id}/local-viewer/{pid}/terminate")
def terminate_local_admin_viewer(project_id: str, pid: int) -> dict[str, Any]:
    identity = active_identity()
    if identity.role != "admin":
        raise HTTPException(403, "只有管理员可以终止服务端本机 MuJoCo")
    record = VIEWER_REGISTRY.record(pid)
    if record is None or record.project_id != project_id:
        raise HTTPException(404, "Viewer 启动记录不存在")
    if record.process.poll() is None:
        record.process.terminate()
    return {"pid": pid, "terminated": True}


@app.post("/api/dialogs/select-directory")
def select_directory(initial: str = "", title: str = "选择 STL / OBJ 文件夹") -> dict[str, str]:
    """Open the host desktop directory chooser without mutating project state."""
    _require_desktop_capability()
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        initial_path = Path(initial).expanduser() if initial else DATA_ROOT
        selected = filedialog.askdirectory(
            title=str(title or "选择文件夹")[:80],
            initialdir=str(initial_path if initial_path.is_dir() else DATA_ROOT if DATA_ROOT.is_dir() else Path.home()),
            mustexist=True,
        )
        root.destroy()
    except Exception as exc:  # noqa: BLE001 - desktop availability is environment-specific
        raise HTTPException(status_code=422, detail=f"当前桌面环境无法打开路径选择器：{exc}") from exc
    return {"path": str(Path(selected).resolve()) if selected else ""}


@app.post("/api/dialogs/select-project-json")
def select_project_json() -> dict[str, Any]:
    """Read a user-selected project JSON, starting in the configured project root."""
    _require_desktop_capability()
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="从项目目录导入 JSON",
            initialdir=str(DATA_ROOT if DATA_ROOT.is_dir() else Path.home()),
            filetypes=(("MuJoCo Studio JSON", "*.json"), ("所有文件", "*.*")),
        )
        root.destroy()
        if not selected:
            return {"path": "", "data": None}
        path = Path(selected).resolve()
        if path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("项目 JSON 不能超过 20 MiB")
        data = json.loads(path.read_text("utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("项目 JSON 顶层必须是对象")
        return {"path": str(path), "data": data}
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"项目 JSON 读取失败：{exc}") from exc
    except Exception as exc:  # noqa: BLE001 - desktop availability is environment-specific
        raise HTTPException(status_code=422, detail=f"当前桌面环境无法打开项目选择器：{exc}") from exc


@app.post("/api/projects/{project_id}/open-folder")
def open_project_folder(project_id: str) -> dict[str, str]:
    """Open the project's self-contained delivery directory on the host desktop."""
    _require_desktop_capability()
    get_project(project_id)
    directory = store.delivery_directory(get_project(project_id), create=True)
    try:
        if os.name == "nt":
            os.startfile(str(directory))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(directory)])
        else:
            subprocess.Popen(["xdg-open", str(directory)])
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"无法打开项目文件夹：{exc}") from exc
    return {"path": str(directory)}


@app.post("/api/projects/{project_id}/bind-delivery-folder")
def bind_project_delivery_folder(project_id: str, request: DeliveryBindingRequest) -> dict[str, str]:
    _require_desktop_capability()
    project = get_project(project_id)
    try:
        category_projects = [store.get(str(item["id"])) for item in store.list() if item.get("category") == project.category]
        previous_directories = {item.id: store.delivery_directory(item) for item in category_projects}
        root = store.bind_delivery_directory(project.category, request.path)
        directory = store.delivery_directory(project, create=True)
        for item in category_projects:
            target = store.delivery_directory(item, create=True)
            source = previous_directories[item.id]
            if source.is_dir() and source.resolve() != target.resolve():
                store.copy_delivery_tree(source, target)
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"category": project.category, "root": str(root), "path": str(directory)}


def _safe_axes_csv_filename(filename: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]+', "_", Path(str(filename or "")).name).strip(" .") or "axis.csv"
    if not safe.lower().endswith((".csv", ".tsv")):
        safe += ".csv"
    return safe


def _write_axes_csv_files(directory: Path, files: list[tuple[str, str]]) -> list[Path]:
    """Write collision-safe per-axis CSV into the delivered tables folder.

    The V2.15.5 library holds only TSJSON; every CSV is an auxiliary table.
    """
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    used: set[str] = set()
    for filename, content in files:
        safe = _safe_axes_csv_filename(filename)
        stem, suffix = Path(safe).stem, Path(safe).suffix or ".csv"
        candidate, serial = safe, 2
        while candidate.casefold() in used:
            candidate = f"{stem}_{serial}{suffix}"
            serial += 1
        used.add(candidate.casefold())
        target = (directory / candidate).resolve()
        if directory.resolve() not in target.parents:
            raise HTTPException(status_code=422, detail="CSV 文件名无效")
        atomic_write_text(target, "\ufeff" + str(content or "").lstrip("\ufeff"), encoding="utf-8")
        written.append(target)
    return written


def _write_result_table_assets(
    project: ProjectSpec, items: list[CsvExportItem], *, combined: bool = False,
) -> list[str]:
    """Atomic upsert into the model table-asset folder before delivery/download.

    The model's stable axis.id is passed by the new UI. Old clients default to
    normalized filenames for compatibility and remain deterministic for repeats.
    """
    written: list[str] = []
    seen: set[str] = set()
    for item in items:
        ext = Path(item.filename).suffix.lower()
        if ext not in {".csv", ".tsv"}:
            raise HTTPException(status_code=422, detail="只接受 CSV / TSV 表格")
        if len(item.content.encode("utf-8")) > 64 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="单个表格不得超过 64 MiB")
        kind = ("result_table_tsv" if ext == ".tsv" else
                "result_combined_csv" if combined else "result_axis_csv")
        identity = "all" if kind in {"result_table_tsv", "result_combined_csv"} else str(item.asset_key or _safe_axes_csv_filename(item.filename))
        if len(identity) > 300:
            raise HTTPException(status_code=422, detail="坐标系资产标识过长")
        filename = store.table_asset_filename(kind, identity)
        if filename in seen:
            raise HTTPException(status_code=422, detail="同一批导出包含重复坐标系资产身份")
        seen.add(filename)
        store.put_table_asset(project.id, kind, identity, ("\ufeff" + item.content.lstrip("\ufeff")).encode("utf-8"))
        written.append(filename)
    return written


def _table_files_directory(project: ProjectSpec, *, create: bool = True) -> Path:
    root = store.delivery_directory(project, create=create)
    folder = root / DELIVERY_TABLE_FOLDER
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def _migrate_legacy_time_series_tables(project: ProjectSpec) -> None:
    """Move old CSV sidecars to delivery without losing their contents.

    Frozen baselines are byte-immutable and deliberately never migrated in place.
    The migration is idempotent; collisions retain *both* file versions.
    """
    if project.lifecycle.status == "baseline":
        return
    root = store.time_series_directory(project, create=True)
    legacy = sorted(path for path in root.glob("*.csv") if path.is_file() and not path.is_symlink())
    if not legacy:
        return
    had_tsjson = any(path.is_file() for path in root.glob("*.tsjson"))
    if not had_tsjson:
        for main in sorted((path for path in legacy if not is_mapping_table_name(path.name)),
                           key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                content = main.read_text("utf-8-sig")
                decoded = parse_time_series_csv(content, project)
                clone = ProjectSpec.model_validate(project.model_dump())
                clone.drives = [DriveSpec.model_validate(row) for row in decoded["drives"]]
                rows = csv.reader(io.StringIO(content.lstrip("\ufeff")))
                by_name: dict[str, dict[str, Any]] = {}
                for row in rows:
                    if len(row) < 6 or row[0] != "RESULT":
                        continue
                    axis = by_name.setdefault(row[1], {"name": row[1], "times": [], "curves": []})
                    curve = next((c for c in axis["curves"] if c["label"] == row[3]), None)
                    if curve is None:
                        curve = {"label": row[3], "unit": row[5], "values": []}
                        axis["curves"].append(curve)
                    # Rebuild an independent axis grid from the recorded times.
                    if row[2] not in axis["times"]:
                        axis["times"].append(row[2])
                    curve.setdefault("samples", {})[row[2]] = row[4]
                axes = []
                for axis in by_name.values():
                    axis["times"] = sorted((float(t) for t in axis["times"]))
                    for curve in axis["curves"]:
                        samples = curve.pop("samples", {})
                        curve["values"] = [samples.get(str(t), samples.get(f"{t:g}", "")) for t in axis["times"]]
                    axes.append(axis)
                name, document = build_tsjson_bundle(clone, axes)
                atomic_write_text(root / name, document, encoding="utf-8")
                had_tsjson = True
                break
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                LOGGER.warning("legacy time-series migration parse failed: %s: %s", main, exc)
        if not had_tsjson:
            # Even an unparseable old CSV set must not leave the canonical
            # exchange library empty. Preserve current authoritative drives.
            name, document = build_tsjson_bundle(project, [])
            atomic_write_text(root / name, document, encoding="utf-8")
    destination = _table_files_directory(project)
    for source in legacy:
        target = destination / source.name
        if target.exists():
            try:
                if target.read_bytes() == source.read_bytes():
                    source.unlink()
                    continue
            except OSError:
                pass
            index = 2
            while (destination / f"{source.stem}_{index}{source.suffix}").exists():
                index += 1
            target = destination / f"{source.stem}_{index}{source.suffix}"
        # Copy first, then remove the old source, so failed disk writes never lose data.
        shutil.copy2(source, target)
        source.unlink()


def _time_series_library_items(project: ProjectSpec) -> list[dict[str, Any]]:
    _migrate_legacy_time_series_tables(project)
    root = store.time_series_directory(project, create=True)
    items: list[dict[str, Any]] = []
    for path in root.glob("*.tsjson"):
        if not path.is_file() or path.is_symlink():
            continue
        stat = path.stat()
        items.append({
            "name": path.name, "relative_path": path.name,
            "path": f"time-series/{path.name}", "kind": "tsjson",
            "size": stat.st_size, "modified": stat.st_mtime,
            "url": f"/api/projects/{project.id}/time-series/{urllib.parse.quote(path.name)}",
        })
    return sorted(items, key=lambda item: (-float(item["modified"]), str(item["name"]).casefold()))


def _write_time_series_library(project: ProjectSpec, *, merged_content: str = "") -> dict[str, Any]:
    """Persist TSJSON alone in the library, all auxiliary CSV in delivery/表格文件夹."""
    _migrate_legacy_time_series_tables(project)
    simulation, _simulation_dir = _latest_simulation_record(project.id)
    if not simulation:
        raise HTTPException(status_code=422, detail="尚无仿真结果，无法生成时序交换文件")
    try:
        axes = axes_from_result_layout(project, simulation)
        filename, document = build_tsjson_bundle(project, axes)
        legacy_name, legacy_content, mapping_files = build_time_series_bundle(project, axes)
        wide_content = merged_content or build_merged_axes_csv(axes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    library = store.time_series_directory(project, create=True)
    tables = _table_files_directory(project)
    wide_name = f"{safe_csv_stem(project.name, '模型')}--合并结果.csv"
    store.put_table_asset(project.id, "result_combined_csv", "all", ("\ufeff" + wide_content.lstrip("\ufeff")).encode("utf-8"))
    # Publish auxiliaries first: failing to write a table must never advertise
    # a partly generated canonical TSJSON as a complete exchange artifact.
    atomic_write_text(tables / wide_name, wide_content, encoding="utf-8")
    atomic_write_text(tables / legacy_name, legacy_content, encoding="utf-8")
    for mapping_name, mapping_content in mapping_files:
        atomic_write_text(tables / mapping_name, mapping_content, encoding="utf-8")
    atomic_write_text(library / filename, document, encoding="utf-8")
    _record_delivery_output(project, tables, "tables_folder", "表格文件夹")
    sync_result: dict[str, Any] = {"synced": False, "reason": "vz_push_disabled"}
    status = _vz_status_for_project(project)
    if bool(status.get("enabled")):
        try:
            sync_result = _vz_sync_time_series_library(project)
        except VZIntegrationError as exc:
            sync_result = {"synced": False, "error": str(exc)}
    return {
        "filename": filename, "merged_filename": wide_name, "legacy_filename": legacy_name,
        "mapping_files": [name for name, _ in mapping_files],
        "count": 1 + 2 + len(mapping_files), "vz_sync": sync_result,
        "table_folder": DELIVERY_TABLE_FOLDER,
    }


@app.post("/api/projects/{project_id}/export-axes-csv")
def export_axes_csv(project_id: str, request: BatchCsvExportRequest) -> dict[str, Any]:
    project = get_project(project_id)

    files = [(item.filename, item.content) for item in request.files]

    if request.delivery:
        # Studio's library is TSJSON-only. Ordinary tables have one canonical
        # delivery location and must not regenerate simulation-based TSJSON.
        _require_mutable_delivery(project)
        if core.is_ephemeral(project_id):
            raise HTTPException(status_code=409, detail="临时编辑不会写入正式交付目录；请先签出模型")
        if request.tables_only:
            if not files:
                raise HTTPException(status_code=422, detail="没有可保存的坐标系 CSV 文件")
            if any(len(content.encode("utf-8")) > 64 * 1024 * 1024 for _, content in files):
                raise HTTPException(status_code=413, detail="单个 CSV 文件不得超过 64 MiB")
            _write_result_table_assets(project, request.files)
            folder = _table_files_directory(project)
            written = _write_axes_csv_files(folder, files)
            _record_delivery_output(project, folder, "tables_folder", "表格文件夹")
            return {"count": len(written), "overwritten": True, "delivery": True,
                    "tables_only": True, "written": [path.name for path in written]}
        if files and (len(files) != 1 or not files[0][0].lower().endswith(".csv")):
            raise HTTPException(status_code=422, detail="合并导出仅接受一份 CSV")
        if files and len(files[0][1].encode("utf-8")) > 64 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="合并 CSV 不得超过 64 MiB")
        # Save a merged table asset before publishing its delivery/TSJSON mirror.
        if files:
            _write_result_table_assets(project, request.files, combined=True)
        time_series = _write_time_series_library(project, merged_content=files[0][1] if files else "")
        return {
            "count": int(time_series.get("count", 0)),
            "overwritten": False,
            "delivery": True,
            "time_series_only": False,
            "time_series": time_series,
        }

    _require_desktop_capability()
    if not files:
        raise HTTPException(status_code=422, detail="本地坐标系 CSV 导出没有可写文件")
    directory = Path(request.directory).expanduser().resolve()
    if not directory.is_dir():
        raise HTTPException(status_code=422, detail="导出目录不存在")
    written = _write_axes_csv_files(directory, files)
    return {"directory": str(directory), "written": [str(path) for path in written], "count": len(written), "overwritten": True, "delivery": False}


# V2.15.6/V2.16.11.5: derived Hub badge snapshots, never authoritative.
# Baseline identity is immutable even if the display name/metadata is edited.
_HUB_CRITICAL_LOCK = threading.RLock()
_HUB_CRITICAL_RAM: dict[str, tuple[str, list[dict[str, Any]]]] = {}
_HUB_CRITICAL_RAM_LIMIT = 256

# Missing historical baseline badges are rebuilt off-request.  This is one
# bounded, daemon-only L3 cache warmer, *not* a second user JobManager or API.
# It never owns a ProjectSpec and is never allowed to change frozen evidence.
_HUB_CRITICAL_REBUILD_QUEUE: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=32)
_HUB_CRITICAL_REBUILD_LOCK = threading.Lock()
_HUB_CRITICAL_REBUILD_PENDING: set[tuple[str, str]] = set()
_HUB_CRITICAL_REBUILD_RETRY_AT: dict[tuple[str, str], float] = {}
_HUB_CRITICAL_REBUILD_WORKER: threading.Thread | None = None


def _hub_critical_identity(item: dict[str, Any]) -> tuple[str, str, dict[str, Any] | None]:
    project_id = str(item["id"])
    status = str(item.get("lifecycle_status", ""))
    if status == "baseline":
        return "baseline", f"baseline:{project_id}:{item.get('baseline_created_at', '')}", None
    version_hint = store.latest_version_hint(project_id)
    if version_hint:
        return "archive", (f"archive:{version_hint['id']}:{version_hint['archived_at']}:"
                           f"{version_hint['mtime_ns']}:{version_hint['size']}"), version_hint
    return "current", f"current:{project_id}:{item.get('updated_at', '')}", None


def _hub_critical_valid_values(values: Any) -> bool:
    """Reject truncated or malformed derived data instead of pinning it as ready."""
    return isinstance(values, list) and len(values) <= 2048 and all(
        isinstance(value, dict) and isinstance(value.get("key"), str)
        and isinstance(value.get("label"), str)
        for value in values
    )


def _hub_critical_schedule_rebuild(project_id: str, token: str) -> None:
    """Enqueue only baseline cache misses; keep Hub summary latency bounded."""
    global _HUB_CRITICAL_REBUILD_WORKER
    key = (project_id, token)
    with _HUB_CRITICAL_REBUILD_LOCK:
        if key in _HUB_CRITICAL_REBUILD_PENDING:
            return
        now = time.monotonic()
        if now < _HUB_CRITICAL_REBUILD_RETRY_AT.get(key, 0.0):
            return
        # Limit failure-key memory in a long-lived server.
        if len(_HUB_CRITICAL_REBUILD_RETRY_AT) > 128:
            _HUB_CRITICAL_REBUILD_RETRY_AT.clear()
        try:
            _HUB_CRITICAL_REBUILD_QUEUE.put_nowait(key)
        except queue.Full:
            return
        _HUB_CRITICAL_REBUILD_PENDING.add(key)
        if _HUB_CRITICAL_REBUILD_WORKER is None or not _HUB_CRITICAL_REBUILD_WORKER.is_alive():
            _HUB_CRITICAL_REBUILD_WORKER = threading.Thread(
                target=_hub_critical_rebuild_loop, name="hub-baseline-badge-warm", daemon=True,
            )
            _HUB_CRITICAL_REBUILD_WORKER.start()


def _hub_critical_rebuild_loop() -> None:
    while True:
        project_id, expected_token = _HUB_CRITICAL_REBUILD_QUEUE.get()
        key = (project_id, expected_token)
        try:
            # Verify current frozen identity before doing potentially expensive
            # schedule resolution.  A removed/changed model is never republished.
            project = store.get(project_id)
            if project.lifecycle.status != "baseline":
                continue
            current = {
                "id": project.id, "lifecycle_status": "baseline",
                "baseline_created_at": (project.lifecycle.baseline_created_at
                                        or project.metadata.get("baseline_created_at", "")),
            }
            if _hub_critical_identity(current)[1] != expected_token:
                continue
            _hub_catalog_critical(current, quick_only=False)
            with _HUB_CRITICAL_REBUILD_LOCK:
                _HUB_CRITICAL_REBUILD_RETRY_AT.pop(key, None)
        except (OSError, KeyError, ValueError, TypeError) as exc:
            LOGGER.warning("Unable to rebuild frozen Hub badge %s: %s", project_id, exc)
            with _HUB_CRITICAL_REBUILD_LOCK:
                _HUB_CRITICAL_REBUILD_RETRY_AT[key] = time.monotonic() + 60.0
        except Exception:
            LOGGER.exception("Unexpected frozen Hub badge rebuild failure for %s", project_id)
            with _HUB_CRITICAL_REBUILD_LOCK:
                _HUB_CRITICAL_REBUILD_RETRY_AT[key] = time.monotonic() + 60.0
        finally:
            with _HUB_CRITICAL_REBUILD_LOCK:
                _HUB_CRITICAL_REBUILD_PENDING.discard(key)
            _HUB_CRITICAL_REBUILD_QUEUE.task_done()


def _hub_catalog_critical(
    item: dict[str, Any], *, quick_only: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """Version-checked Hub badge; quick lists never solve cold schedules.

    A baseline's token comes exclusively from its frozen identity/time, not
    mutable display names, working revisions, VZ or current simulation state.
    """
    project_id = str(item["id"])
    source, token, version_hint = _hub_critical_identity(item)
    item["critical_token"] = token  # read-only response metadata, never ProjectSpec
    root = store.project_directory(project_id)
    cache_id = str(root.resolve())
    cache_path = root / "core" / "hub_critical_data.json"
    with _HUB_CRITICAL_LOCK:
        in_memory = _HUB_CRITICAL_RAM.get(cache_id)
        if in_memory is not None and in_memory[0] == token and _hub_critical_valid_values(in_memory[1]):
            return copy.deepcopy(in_memory[1]), source
    try:
        if cache_path.is_file() and not cache_path.is_symlink() and cache_path.stat().st_size <= 512 * 1024:
            cached = json.loads(cache_path.read_text("utf-8"))
            if (isinstance(cached, dict) and cached.get("token") == token
                    and _hub_critical_valid_values(cached.get("critical_data"))):
                values = cached["critical_data"]
                with _HUB_CRITICAL_LOCK:
                    _HUB_CRITICAL_RAM[cache_id] = (token, copy.deepcopy(values))
                return copy.deepcopy(values), source
    except (OSError, ValueError, TypeError):
        pass

    if quick_only:
        if source == "baseline":
            _hub_critical_schedule_rebuild(project_id, token)
        return [], "pending"

    # Never hold the shared badge lock during schedule resolution or file IO.
    original = (store.get_version(project_id, str(version_hint["id"]))
                if source == "archive" and version_hint else store.get(project_id))
    values = _project_preview(original, include_latest_result=False).get("archive_fields", [])
    if not _hub_critical_valid_values(values):
        raise ValueError("Hub critical snapshot has an invalid archive_fields shape")
    with _HUB_CRITICAL_LOCK:
        _HUB_CRITICAL_RAM[cache_id] = (token, copy.deepcopy(values))
        if len(_HUB_CRITICAL_RAM) > _HUB_CRITICAL_RAM_LIMIT:
            _HUB_CRITICAL_RAM.pop(next(iter(_HUB_CRITICAL_RAM)))
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(cache_path, json.dumps({
            "schema": 1, "token": token, "source": source,
            "critical_data": values,
        }, ensure_ascii=False, separators=(",", ":")), sync_directory=False)
    except (OSError, ValueError, TypeError) as exc:
        LOGGER.warning("Hub critical L3 cache not persisted for %s: %s", project_id, exc)
    return copy.deepcopy(values), source

@app.get("/api/projects")
def list_projects(detail: str = "full") -> list[dict[str, object]]:
    """List projects; ``detail=summary`` skips archive/delivery filesystem hydration."""
    started_at = time.perf_counter()
    projects = store.list()
    summary_only = str(detail).casefold() in {"summary", "light", "catalog"}
    if active_identity().role == "guest":
        projects = [item for item in projects if item.get("lifecycle_status") == "baseline"]
    elif not summary_only:
        # Hub's startup catalog must never block on VZ's independent HTTP/IO.
        # /api/vz-push-status already performs the authorized reconciliation.
        projects = _vz_reconcile_push_catalog(projects)
    for item in projects:
        # Summary is now self-sufficient: the cost of each badge after its first
        # projection is a tiny derived snapshot, not a full preview request.
        try:
            values, source = _hub_catalog_critical(item, quick_only=summary_only)
            item["critical_data"] = values
            item["critical_source"] = source
        except (KeyError, ValueError, OSError, TypeError) as exc:
            LOGGER.warning("Hub critical data unavailable for %s: %s", item.get("id"), exc)
            item["critical_data"] = []
            item["critical_source"] = "unavailable"
        if summary_only:
            continue
        try:
            project = store.get(str(item["id"]))
            item["archive_data"] = _latest_archive_version(project)
            latest = item["archive_data"]
            # V2.10.2: a project cut from a baseline has no local archive yet.
            # Show the current authoritative key-data projection until its first
            # archive exists; once history exists, keep the historical rule that
            # the Hub bubble reflects the newest archived snapshot.
            # critical_data already came from the same baseline/archive/current
            # snapshot as the lightweight catalog; do not re-solve a preview.
            item["delivery_outputs"] = _current_delivery_outputs(project)
        except (KeyError, ValueError, OSError):
            item["archive_data"] = None
            # Delivery/secondary metadata failure is not a badge failure.
            item["delivery_outputs"] = []
    elapsed = time.perf_counter() - started_at
    if elapsed > 0.5:
        LOGGER.warning("hub_catalog_slow detail=%s count=%d seconds=%.3f", detail, len(projects), elapsed)
    return projects


@app.get("/api/project-categories")
def list_project_categories() -> dict[str, list[str]]:
    return {"categories": store.categories()}


@app.get("/api/model-types")
def list_model_types() -> dict[str, Any]:
    identity = active_identity()
    tree = store.model_type_tree()
    def annotate(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            owner = str(node.get("owner", ""))
            node["can_manage"] = bool(
                identity.role == "admin" or identity.admin_mode
                or (owner and owner.casefold() == identity.username.casefold())
            )
            annotate(node.get("children", []))
    annotate(tree)
    
    name_path = store.root / "project_root_name.txt"
    try:
        project_name = name_path.read_text("utf-8").strip() or "项目"
    except OSError:
        project_name = "项目"
    return {"tree": tree, "root": str(store.projects_root), "project_name": project_name}


@app.put("/api/project-root/name")
def rename_project_root_name(body: dict[str, Any] = Body(...)) -> dict[str, str]:
    identity = active_identity()
    if not (identity.role == "admin" or identity.admin_mode):
        raise HTTPException(403, "修改项目名称需要管理员权限/管理模式")
    name = str(body.get("name", "")).strip()
    if not name or len(name) > 80 or re.search(r'[<>:"|?*\x00-\x1f]', name):
        raise HTTPException(422, "项目名称不能为空、不能超过 80 字符且不能包含非法文件名字符")
    atomic_write_text(store.root / "project_root_name.txt", name)
    return {"name": name}


def _require_model_type_mutation(category: str) -> Identity:
    identity = active_identity()
    owner = store.model_type_owner(category)
    if identity.role == "admin" or identity.admin_mode:
        return identity
    if owner and owner.casefold() == identity.username.casefold():
        return identity
    raise HTTPException(status_code=403, detail="只有模型类型创建者可以移动、重命名或删除；请进入管理模式")


@app.post("/api/project-categories", status_code=201)
def add_project_category(request: ProjectCategoryRequest) -> dict[str, Any]:
    try:
        identity = active_identity()
        if not (identity.role == "admin" or identity.admin_mode):
            raise HTTPException(status_code=403, detail="新增模型类型需要管理员权限/管理模式")
        parent = request.parent.strip(" /\\")
        if parent in {"None", "未分类"} or parent.startswith("None/"):
            raise HTTPException(status_code=422, detail="None 未分类文件夹下面不能增加子分类")
        path = "/".join(filter(None, [parent, request.name.strip()]))
        categories = store.add_category(path, actor=identity.username)
        return {"categories": categories, "created": store.normalize_category(path),
                "tree": store.model_type_tree()}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/model-types/{category:path}/move")
def move_model_type(category: str, request: ModelTypeMoveRequest) -> dict[str, Any]:
    source = store.normalize_category(category)
    _require_model_type_mutation(source)
    affected = [str(item["id"]) for item in store.list() if (
        str(item.get("category", "")) == source or str(item.get("category", "")).startswith(source + "/")
    )]
    for project_id in affected:
        core.drop(project_id)
    try:
        return store.move_category(source, request.target_parent, request.before)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/model-types/{category:path}/name")
def rename_model_type(category: str, request: ModelTypeRenameRequest) -> dict[str, Any]:
    source = store.normalize_category(category)
    _require_model_type_mutation(source)
    affected = [str(item["id"]) for item in store.list() if (
        str(item.get("category", "")) == source or str(item.get("category", "")).startswith(source + "/")
    )]
    for project_id in affected:
        core.drop(project_id)
    try:
        return store.rename_category(source, request.name)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/model-types/{category:path}/archives")
def model_type_archives(category: str) -> dict[str, Any]:
    value = store.normalize_category(category)
    identity = active_identity()
    owner = store.model_type_owner(value)
    projects = [item for item in store.list() if (
        str(item.get("category", "")) == value or str(item.get("category", "")).startswith(value + "/")
    )]
    entries: list[dict[str, Any]] = []
    baselines = [item for item in projects if str(item.get("lifecycle_status", "")) == "baseline"]
    for item in baselines:
        project_id = str(item["id"])
        project = store.get(project_id)
        baseline_critical, _badge_source = _hub_catalog_critical(item)
        baseline_at = str(project.lifecycle.baseline_created_at or item.get("updated_at", ""))
        entries.append({
            "id": f"baseline:{project_id}", "project_id": project_id,
            "project_name": str(item.get("name", project_id)), "label": "基线",
            "reason": "baseline", "saved_at": baseline_at,
            "archived_at": baseline_at, "locked": True,
            "archive_data": None,
            "critical_data": baseline_critical,
            "delivery_outputs": _current_delivery_outputs(project),
            "version_summary": str(item.get("version_summary", "")),
            "baseline_log": str(project.metadata.get("baseline_log", "")),
        })
    entries.sort(key=lambda item: (str(item.get("archived_at", "")), str(item.get("id", ""))))
    return {
        "category": value, "name": value.split("/")[-1], "project_count": len(projects),
        "baseline_count": len(baselines), "entries": entries, "owner": owner,
        "can_manage": bool(identity.role == "admin" or identity.admin_mode or (
            owner and owner.casefold() == identity.username.casefold()
        )),
    }


@app.delete("/api/project-categories/{category:path}")
def delete_project_category(
    category: str,
    delete_projects: bool = Query(default=False),
) -> dict[str, Any]:
    identity = active_identity()
    if not (identity.role == "admin" or identity.admin_mode):
        raise HTTPException(403, "删除模型分类需要管理员权限/管理模式")
    try:
        if delete_projects:
            normalized = store.normalize_category(category)
            for item in store.list():
                item_category = str(item.get("category") or "None")
                if item_category == normalized or item_category.startswith(normalized + "/"):
                    core.drop(str(item["id"]))
        result = store.delete_category(category, delete_projects=delete_projects)
        for project_id in result["affected_project_ids"]:
            core.drop(project_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/model-asset-library")
def get_model_asset_library(
    category: str = Query(..., min_length=1, max_length=400),
    folder: str = Query(default="", max_length=80),
) -> dict[str, Any]:
    return _model_asset_library_payload(category, folder)


@app.post("/api/model-asset-library/folders", status_code=201)
def create_model_asset_library_folder(request: ModelAssetFolderRequest) -> dict[str, Any]:
    identity = _require_model_asset_library_write()
    category = _existing_model_asset_category(request.category)
    try:
        store.create_model_asset_folder(category, request.name.strip(), uploaded_by=identity.username)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _model_asset_library_payload(category, request.name.strip())


@app.put("/api/model-asset-library/folders")
def rename_model_asset_library_folder(request: ModelAssetCopyRequest) -> dict[str, Any]:
    _require_model_asset_library_write()
    category = _existing_model_asset_category(request.category)
    try:
        source_ref = store.model_asset_reference(category, request.source.strip())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    affected = [item["id"] for item in _model_asset_usage(source_ref)]
    for project_id in affected:
        core.drop(project_id)
    try:
        renamed = store.rename_model_asset_folder(category, request.source.strip(), request.name.strip())
    except (OSError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    payload = _model_asset_library_payload(category, request.name.strip())
    payload["rename"] = renamed
    return payload


@app.post("/api/model-asset-library/folders/copy", status_code=201)
def copy_model_asset_library_folder(request: ModelAssetCopyRequest) -> dict[str, Any]:
    identity = _require_model_asset_library_write()
    category = _existing_model_asset_category(request.category)
    try:
        store.copy_model_asset_folder(
            category, request.source.strip(), request.name.strip(),
            max_files=10000, max_bytes=MAX_MODEL_UPLOAD_BYTES, uploaded_by=identity.username,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return _model_asset_library_payload(category, request.name.strip())


@app.delete("/api/model-asset-library/folders")
def delete_model_asset_library_folder(
    category: str = Query(..., min_length=1, max_length=400),
    name: str = Query(..., min_length=1, max_length=80),
) -> dict[str, Any]:
    _require_model_asset_library_write()
    value = _existing_model_asset_category(category)
    try:
        reference = store.model_asset_reference(value, name.strip())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    usage = _model_asset_usage(reference)
    if usage:
        names = "、".join(item["name"] or item["id"] for item in usage[:5])
        suffix = "等" if len(usage) > 5 else ""
        raise HTTPException(409, f"该数模版本仍被 {len(usage)} 个模型使用：{names}{suffix}；请先切换这些模型的数模版本")
    try:
        store.delete_model_asset_folder(value, name.strip())
    except (OSError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return _model_asset_library_payload(value)


@app.delete("/api/model-asset-library/folders/contents")
def clear_model_asset_library_folder(
    category: str = Query(..., min_length=1, max_length=400),
    name: str = Query(..., min_length=1, max_length=80),
) -> dict[str, Any]:
    _require_model_asset_library_write()
    value = _existing_model_asset_category(category)
    try:
        result = store.clear_model_asset_folder(value, name.strip())
    except (OSError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    payload = _model_asset_library_payload(value, name.strip())
    payload.update(result)
    return payload


@app.post("/api/model-asset-library/upload")
async def upload_model_asset_library_files(
    files: list[UploadFile] = File(...),
    category: str = Form(...),
    folder: str = Form(...),
    relative_paths: str = Form("[]"),
) -> dict[str, Any]:
    identity = _require_model_asset_library_write()
    value = _existing_model_asset_category(category)
    try:
        requested_paths = json.loads(relative_paths)
        if not isinstance(requested_paths, list):
            requested_paths = []
    except ValueError:
        requested_paths = []
    try:
        reference = store.model_asset_reference(value, folder.strip())
        target_root = store.resolve_model_asset_reference(reference)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not target_root.is_dir():
        raise HTTPException(404, "数模版本文件夹不存在")
    metadata = store._read_model_asset_metadata(target_root)
    if not str(metadata.get("uploaded_by", "")).strip():
        store._write_model_asset_metadata(target_root, uploaded_by=identity.username)
    uploaded, uploaded_meshes, rejected = await _store_model_asset_uploads(files, requested_paths, target_root)
    if not uploaded:
        raise HTTPException(422, "没有可接受的数模资产文件；请检查路径和文件类型")
    if not uploaded_meshes and not list_mesh_files(target_root):
        raise HTTPException(422, "数模版本文件夹中至少需要一个 STL/OBJ 文件")
    payload = _model_asset_library_payload(value, folder.strip())
    payload.update({"uploaded": uploaded, "uploaded_meshes": uploaded_meshes, "rejected": rejected})
    return payload


@app.get("/api/model-asset-library/file")
def download_model_asset_library_file(
    category: str = Query(..., min_length=1, max_length=400),
    folder: str = Query(..., min_length=1, max_length=80),
    path: str = Query(..., min_length=1, max_length=1000),
):
    value = _existing_model_asset_category(category)
    try:
        root = store.resolve_model_asset_reference(store.model_asset_reference(value, folder.strip()))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    relative = Path(path.replace("\\", "/"))
    target = (root / relative).resolve()
    if root.resolve() not in target.parents or not target.is_file() or target.is_symlink():
        raise HTTPException(404, "数模资产文件不存在")
    if target.suffix.lower() not in MODEL_ASSET_UPLOAD_EXTENSIONS:
        raise HTTPException(422, "不支持下载该类型资产")
    return FileResponse(target, filename=target.name)


@app.delete("/api/model-asset-library/file")
def delete_model_asset_library_file(
    category: str = Query(..., min_length=1, max_length=400),
    folder: str = Query(..., min_length=1, max_length=80),
    path: str = Query(..., min_length=1, max_length=1000),
) -> dict[str, Any]:
    _require_model_asset_library_write()
    value = _existing_model_asset_category(category)
    if Path(path).suffix.lower() not in MODEL_ASSET_UPLOAD_EXTENSIONS:
        raise HTTPException(422, "不支持删除该类型资产")
    try:
        store.delete_model_asset_file(value, folder.strip(), path)
    except (OSError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return _model_asset_library_payload(value, folder.strip())


@app.post("/api/projects", status_code=201)
def create_project(request: CreateProjectRequest) -> ProjectSpec:
    if request.source_project_id:
        source = get_project(request.source_project_id)
        project = ProjectSpec.model_validate(source.model_dump())
        project.id = new_id("project")
        clear_environment_local_project_metadata(project)
    else:
        project = ProjectSpec.demo() if request.demo else ProjectSpec()
    category = (request.category or "").strip()
    identity = active_identity()
    # Ordinary uncategorized projects start checked-in: they are immediately
    # previewable/exportable and only acquire a write lease after explicit
    # checkout. Creating a managed version inside a category is different: it
    # is a new working revision and therefore starts checked-out for its creator.
    project.lifecycle.status = "checked_out" if category else "checked_in"
    project.lifecycle.checked_out_by = identity.username if category else ""
    project.lifecycle.lease_id = identity.lease_id if category else ""
    project.lifecycle.checked_out_session = ""
    project.lifecycle.source_project_id = request.source_project_id or ""
    project.lifecycle.checked_out_at = datetime.now(timezone.utc).isoformat() if category else ""
    project.lifecycle.checked_in_at = "" if category else datetime.now(timezone.utc).isoformat()
    if category:
        date_code, index, managed_name = store.next_version_identity(category)
        project.category = category
        project.name = managed_name
        project.metadata = {
            **project.metadata, "version_date": date_code, "version_index": index,
            "version_source_project_id": request.source_project_id or "",
            "version_summary": "新版本已建立，正在等待与前三个版本比对。",
            "version_summary_archived": False,
        }
        comparison, prior = _version_comparison_text(project)
        detail = comparison.splitlines()[1:9]
        project.metadata["version_summary"] = f"已自动比对之前 {len(prior)} 个版本。" + ("\n" + "\n".join(detail) if detail else "")
    else:
        project.name = request.name
    project.metadata["archive_base_name"] = project.name
    _apply_archive_name(project)
    created = store.create(project)
    if category:
        if not identity.single_user:
            auth.sessions.activate_lease(identity.session_id)
        _schedule_idle_check_in(created.id, identity)
    core.drop(created.id)
    return created


@app.post("/api/projects/import-legacy", status_code=201)
def import_legacy(request: LegacyImportRequest) -> ProjectSpec:
    try:
        identity = active_identity()
        project = migrate_legacy_project(request.data)
        project.lifecycle.status = "checked_out"
        project.lifecycle.checked_out_by = identity.username
        project.lifecycle.lease_id = identity.lease_id
        project.lifecycle.checked_out_at = datetime.now(timezone.utc).isoformat()
        project.lifecycle.checked_in_at = ""
        created = store.create(project)
        if not identity.single_user:
            auth.sessions.activate_lease(identity.session_id)
        _schedule_idle_check_in(created.id, identity)
        core.drop(created.id)
        return created
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _embed_csv_points_in_export_state(state: dict[str, Any]) -> dict[str, Any]:
    """Return a portable export copy whose CSV-driven segments are JSON-self-contained."""
    result = copy.deepcopy(state)
    project = result.get("project", {}) if isinstance(result, dict) else {}
    if isinstance(project, dict):
        # The same project-scoped resolver used by ProjectStore.get/save must
        # handle export snapshots. Never read a stale machine-absolute CSV.
        portable = ProjectSpec.model_validate(project)
        store.hydrate_legacy_csv_sources(portable, project_dir=store.project_directory(portable.id))
        project = portable.model_dump()
        result["project"] = project
    for drive in list(project.get("drives", []) or []):
        if not isinstance(drive, dict):
            continue
        for segment in list(drive.get("segments", []) or []):
            if not isinstance(segment, dict):
                continue
            profile = str(segment.get("profile", "") or "")
            if profile not in {"mapping", "external_csv"}:
                continue
            points: list[list[float]] = []
            for item in list(segment.get("points", []) or []):
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                try:
                    points.append([float(item[0]), float(item[1])])
                except (TypeError, ValueError):
                    continue
            source_path = str(segment.get("csv_path", "") or "")
            if profile == "mapping":
                if points:
                    segment["points"] = points
                    segment["mapping_point_count"] = len(points)
                if not str(segment.get("mapping_csv_name", "") or "").strip() and source_path:
                    segment["mapping_csv_name"] = re.split(r"[\\/]", source_path)[-1]
            else:
                if points:
                    normalized = normalize_external_motion_points(points)
                    points = [[x, y] for x, y in normalized]
                    segment["points"] = points
                    duration, travel, max_speed = external_motion_summary(points)
                    segment["duration"] = duration
                    segment["travel"] = travel
                    segment["speed"] = max_speed
                if not str(segment.get("external_csv_name", "") or "").strip() and source_path:
                    segment["external_csv_name"] = re.split(r"[\\/]", source_path)[-1]
            # Paths are machine-local provenance only; exported model JSON must not depend on them.
            segment["csv_path"] = ""
    return result


def _project_export_payload(project: ProjectSpec, state: dict[str, Any]) -> dict[str, Any]:
    """Build the single canonical project JSON export envelope used by downloads and delivery snapshots."""
    state = strip_environment_local_metadata(_embed_csv_points_in_export_state(state))
    payload: dict[str, Any] = {
        "format": "mujoco_studio_project",
        "format_version": 1,
        "application_version": __version__,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "export_mode": "baseline" if project.lifecycle.status == "baseline" else "checked_in",
        "state": state,
    }
    if project.lifecycle.status == "baseline":
        payload["baseline_seal"] = _baseline_seal(state)
    return payload


@app.get("/api/projects/{project_id}/export-json")
def export_project_json(project_id: str) -> Response:
    try:
        instance = core.get(project_id)
        project = instance.project()
        if project.lifecycle.status == "checked_out":
            raise HTTPException(status_code=409, detail="签出状态的项目不能导出，请先签入")
        state = instance.export_json()
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    payload = _project_export_payload(project, state)
    filename = f"{project_id}.mujoco-studio.json"
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/projects/{project_id}/export-modeling-info")
def export_project_modeling_info(project_id: str, include_measurements: bool = True) -> Response:
    try:
        project = core.get(project_id).project()
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    payload = export_modeling_exchange(project, __version__, include_measurements=include_measurements)
    filename = f"{project_id}_modeling_info.json"
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/projects/import-modeling-info", status_code=201)
def import_project_modeling_info(request: ModelingInfoImportRequest) -> dict[str, Any]:
    try:
        identity = active_identity()
        project = import_modeling_exchange(request.data, import_measurements=request.import_measurements)
        project.lifecycle.status = "checked_out"
        project.lifecycle.checked_out_by = identity.username
        project.lifecycle.lease_id = identity.lease_id
        project.lifecycle.checked_out_at = datetime.now(timezone.utc).isoformat()
        project.lifecycle.checked_in_at = ""
        repair = repair_joint_references(project)
        created = store.create(project)
        if not identity.single_user:
            auth.sessions.activate_lease(identity.session_id)
        _schedule_idle_check_in(created.id, identity)
        core.drop(created.id)
        return {
            "project": core.get(created.id).project().model_dump(),
            "repair": repair,
            "migration": {
                "source": "mujoco_modeling_exchange",
                "schema_version": str(request.data.get("schema_version", "1.0")),
                "preserved_source": True,
            },
        }
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid modeling info JSON: {exc}") from exc


def _import_target_category(requested: str | None, fallback: str) -> str:
    """Resolve an explicit Hub target folder without creating a new model type implicitly."""
    if requested is None:
        return store.normalize_category(fallback)
    value = store.normalize_category(requested)
    if value == "None":
        return value
    categories = store.categories()
    if value in categories:
        return value
    portable = [item for item in categories if item.casefold() == value.casefold()]
    if len(portable) == 1:
        return portable[0]
    raise ValueError("目标项目文件夹不存在，请刷新 Hub 后重试")


def _import_project_json_payload(
    data: dict[str, Any], *, target_category: str | None = None,
    baseline_mesh_root_override: str | None = None,
) -> dict[str, Any]:
    legacy = is_legacy_project(data)
    legacy_interop: dict[str, Any] = {}
    export_mode = str(data.get("export_mode", ""))
    if data.get("format") == "mujoco_studio_project":
        state = data.get("state", {})
    elif legacy:
        migrated = migrate_legacy_project(data)
        legacy_interop = dict(migrated.metadata.get("model_json_interop", {}) or {})
        state = {"project": migrated.model_dump(), "ui": legacy_ui_state(data)}
    elif is_modeling_exchange(data):
        # Deprecated UI format: keep a hidden reader so old files do not become dead ends.
        migrated = import_modeling_exchange(data, import_measurements=True)
        state = {"project": migrated.model_dump(), "ui": {}}
    elif "project" in data:
        state = data
    else:
        state = {"project": data, "ui": {}}

    if not isinstance(state, dict) or not isinstance(state.get("project"), dict):
        raise ValueError("state.project must be an object")
    ui = state.get("ui", {})
    if not isinstance(ui, dict):
        raise ValueError("state.ui must be an object")
    project = ProjectSpec.model_validate(state.get("project", {}))
    original_id = project.id
    resolved_category = _import_target_category(target_category, project.category)
    if export_mode == "baseline":
        if project.lifecycle.status != "baseline":
            raise ValueError("基线导出物的生命周期标记无效")
        seal = str(data.get("baseline_seal", ""))
        if not seal or seal != _baseline_seal(state):
            raise ValueError("基线导出物校验失败，文件可能已被修改")
        baseline = ProjectSpec.model_validate(copy.deepcopy(project.model_dump()))
        baseline.id = new_id("project")
        clear_environment_local_project_metadata(baseline)
        baseline.category = resolved_category
        if baseline_mesh_root_override is not None:
            baseline.mesh_root = baseline_mesh_root_override
        baseline.lifecycle.status = "baseline"
        baseline.lifecycle.checked_out_by = ""
        baseline.lifecycle.lease_id = ""
        baseline.lifecycle.checked_out_session = ""
        baseline.lifecycle.source_project_id = original_id
        baseline.metadata["imported_from_project_id"] = original_id
        repair = repair_joint_references(baseline)
        baseline_created = store.create(baseline)
        try:
            # Baselines are immutable snapshots and intentionally have no archive-data property.
            core.drop(baseline_created.id)
            _apply_imported_ui(baseline_created.id, ui)

            working = ProjectSpec.model_validate(copy.deepcopy(baseline.model_dump()))
            working.id = new_id("project")
            identity = active_identity()
            working.lifecycle.status = "checked_out"
            working.lifecycle.checked_out_by = identity.username
            working.lifecycle.lease_id = identity.lease_id
            working.lifecycle.checked_out_session = ""
            working.lifecycle.source_project_id = baseline_created.id
            working.lifecycle.baseline_created_at = ""
            working.lifecycle.checked_out_at = datetime.now(timezone.utc).isoformat()
            working.lifecycle.checked_in_at = ""
            date_code, index, managed_name = store.next_version_identity(working.category)
            working.name = managed_name
            working.metadata.update({
                "version_date": date_code, "version_index": index,
                "imported_from_baseline_id": baseline_created.id,
            })
            created = store.create(working)
            if not identity.single_user:
                auth.sessions.activate_lease(identity.session_id)
            _schedule_idle_check_in(created.id, identity)
            core.drop(created.id)
            _apply_imported_ui(created.id, ui)
        except Exception:
            core.drop(baseline_created.id)
            try:
                store.delete(baseline_created.id)
            except Exception:
                pass
            raise
        return {
            "project": core.get(created.id).project().model_dump(),
            "baseline_project": core.get(baseline_created.id).project().model_dump(),
            "repair": repair,
            "migration": {"legacy": False, "source": "mujoco_studio_baseline", "preserved_source": False},
        }

    project.id = new_id("project")
    clear_environment_local_project_metadata(project)
    project.category = resolved_category
    identity = active_identity()
    project.lifecycle.status = "checked_out"
    project.lifecycle.checked_out_by = identity.username
    project.lifecycle.lease_id = identity.lease_id
    project.lifecycle.checked_out_session = ""
    project.lifecycle.source_project_id = original_id
    project.lifecycle.baseline_created_at = ""
    project.lifecycle.checked_out_at = datetime.now(timezone.utc).isoformat()
    project.lifecycle.checked_in_at = ""
    project.metadata["imported_from_project_id"] = original_id
    repair = repair_joint_references(project)
    created = store.create(project)
    if not identity.single_user:
        auth.sessions.activate_lease(identity.session_id)
    _schedule_idle_check_in(created.id, identity)
    core.drop(created.id)
    _apply_imported_ui(created.id, ui)
    return {
        "project": core.get(created.id).project().model_dump(), "repair": repair,
        "migration": {
            "legacy": legacy,
            "source": "mujoco_xml_tool_v21_5_model_json" if legacy else ("mujoco_modeling_exchange_deprecated" if is_modeling_exchange(data) else "mujoco_studio"),
            "preserved_source": legacy,
            "warnings": list(legacy_interop.get("warnings", []) or []),
            "ignored_joint_types": list(legacy_interop.get("ignored_joint_types", []) or []),
            "ignored_motion_profiles": list(legacy_interop.get("ignored_motion_profiles", []) or []),
        },
    }


@app.post("/api/projects/import-json", status_code=201)
def import_project_json(request: ProjectImportRequest) -> dict[str, Any]:
    try:
        return _import_project_json_payload(request.data, target_category=request.target_category)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid project JSON: {exc}") from exc


def _require_project_bundle_access(project: ProjectSpec | None = None) -> Identity:
    identity = active_identity()
    if identity.role not in {"engineer", "admin"}:
        raise HTTPException(status_code=403, detail="只有工程师或管理员可以导入/导出完整压缩包")
    if project is not None:
        require_project_access(project, write=False)
    return identity


def _bundle_asset_snapshot_name(project: ProjectSpec) -> str:
    raw = str(project.mesh_root or "").replace("\\", "/").rstrip("/")
    base = raw.split("/")[-1] if raw else project.name
    clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", base).strip(" ._")
    return (clean or "model_assets")[:64]


def _unique_import_asset_name(category: str, preferred: str) -> str:
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", str(preferred or "model_assets")).strip(" ._") or "model_assets"
    base = base[:64]
    existing = {str(item.get("name", "")).casefold() for item in store.list_model_asset_folders(category)}
    candidate = f"{base}_导入"[:78]
    if candidate.casefold() not in existing:
        return candidate
    for index in range(2, 10000):
        suffix = f"_导入{index}"
        candidate = f"{base[:max(1, 80-len(suffix))]}{suffix}"
        if candidate.casefold() not in existing:
            return candidate
    raise ValueError("无法生成不冲突的数模资产文件夹名称")


def _set_imported_project_mesh_root(project_id: str, mesh_root: str, identity: Identity) -> tuple[ProjectSpec, dict[str, Any]]:
    project = store.get(project_id)
    project.mesh_root = mesh_root
    root = store.resolve_mesh_root(project_id, mesh_root)
    files = list_mesh_files(root) if root.is_dir() else []
    repair = repair_mesh_references(project, files)
    repair_joint_references(project)
    with core.acquire(project_id) as instance:
        result = instance.bus.dispatch({
            "tool_id": "project.asset_selection",
            "params": {
                "project": project.model_dump(),
                "asset_folder_path": mesh_root,
                "intent": "完整包导入：注入隔离数模快照并选择该资产",
            },
            "actor": identity.username,
            "client": "human_ui",
        })
        if not result.ok:
            raise ValueError(str(result.errors))
        project = instance.project()
    return project, repair


def _import_bundle_archive_history(source: Path, project_id: str, category: str, mesh_root: str) -> int:
    if not source.is_dir():
        return 0
    nested = [path for path in source.rglob("*") if path.is_file() and path.parent != source]
    if nested:
        raise ProjectBundleError("存档日志目录只允许直接包含版本 JSON 与 meta sidecar")
    target = store.project_directory(project_id) / "versions"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for version_path in sorted(source.glob("*.json"), key=lambda item: item.name):
        if version_path.name.endswith(".meta.json"):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.json", version_path.name):
            raise ProjectBundleError(f"存档版本文件名无效：{version_path.name}")
        snapshot = ProjectSpec.model_validate_json(version_path.read_text("utf-8"))
        snapshot.id = project_id
        snapshot.category = category
        snapshot.mesh_root = mesh_root
        snapshot.lifecycle.checked_out_session = ""
        atomic_write_text(target / version_path.name, snapshot.model_dump_json(indent=2), sync_directory=False)
        meta_path = version_path.with_name(f"{version_path.stem}.meta.json")
        if meta_path.is_file():
            try:
                metadata = json.loads(meta_path.read_text("utf-8"))
            except ValueError as exc:
                raise ProjectBundleError(f"存档 sidecar 无法解析：{meta_path.name}") from exc
            if not isinstance(metadata, dict):
                raise ProjectBundleError(f"存档 sidecar 必须是对象：{meta_path.name}")
            # A checked-in bundle does not carry separately linked baseline projects.
            # Preserve the old ID only as provenance and clear the live link so Hub
            # never points at an unrelated/nonexistent project after import.
            old_baseline_id = str(metadata.get("baseline_project_id", "") or "")
            if old_baseline_id:
                metadata["source_baseline_project_id"] = old_baseline_id
                metadata["baseline_project_id"] = ""
            atomic_write_text(
                target / meta_path.name,
                json.dumps(metadata, ensure_ascii=False, indent=2),
                sync_directory=False,
            )
        count += 1
    store.prune_versions(project_id, keep=MAX_ARCHIVE_VERSIONS, preserve_locked=False)
    return min(count, MAX_ARCHIVE_VERSIONS)


def _cleanup_failed_bundle_import(project_ids: list[str], asset_folder: tuple[str, str] | None) -> None:
    for project_id in reversed(project_ids):
        core.drop(project_id)
        try:
            store.delete(project_id)
        except Exception:
            pass
    if asset_folder:
        category, folder = asset_folder
        try:
            store.delete_model_asset_folder(category, folder)
        except Exception:
            pass


@app.get("/api/projects/{project_id}/export-bundle")
def export_project_bundle(project_id: str):
    try:
        instance = core.get(project_id)
        project = instance.project()
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    _require_project_bundle_access(project)
    if project.lifecycle.status == "checked_out":
        raise HTTPException(status_code=409, detail="签出状态的项目不能导出完整包，请先签入")

    state = instance.export_json()
    model_payload = _project_export_payload(project, state)
    fd, archive_name = tempfile.mkstemp(prefix=f"project_bundle_{project_id}_", suffix=".zip")
    os.close(fd)
    archive_path = Path(archive_name)
    try:
        with tempfile.TemporaryDirectory(prefix=f"project_bundle_stage_{project_id}_") as temporary:
            staging = Path(temporary)
            model_path = staging / PROJECT_BUNDLE_MODEL_JSON_PATH
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(json.dumps(model_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            assets_target = staging / PROJECT_BUNDLE_ASSETS_DIR
            delivery_target = staging / PROJECT_BUNDLE_DELIVERY_DIR
            time_series_target = staging / PROJECT_BUNDLE_TIME_SERIES_DIR
            archive_target = staging / PROJECT_BUNDLE_ARCHIVE_DIR

            asset_stats = {"files": 0, "bytes": 0}
            if str(project.mesh_root or "").strip():
                source_assets = store.resolve_mesh_root(project.id, project.mesh_root)
                if not source_assets.is_dir():
                    raise ProjectBundleError("当前模型数模根不存在，不能生成完整包")
                asset_stats = copy_tree_snapshot(
                    source_assets, assets_target, max_files=MAX_PROJECT_BUNDLE_FILES,
                    max_bytes=MAX_MODEL_UPLOAD_BYTES,
                    exclude_names={store.MODEL_ASSET_METADATA_NAME},
                )
            else:
                assets_target.mkdir(parents=True, exist_ok=True)

            source_delivery = store.delivery_directory(project, create=False)
            delivery_stats = copy_tree_snapshot(
                source_delivery, delivery_target, max_files=MAX_PROJECT_BUNDLE_FILES,
                max_bytes=MAX_MODEL_UPLOAD_BYTES,
            ) if source_delivery.is_dir() else {"files": 0, "bytes": 0}
            if not delivery_target.exists():
                delivery_target.mkdir(parents=True, exist_ok=True)

            source_time_series = store.time_series_directory(project, create=False)
            time_series_stats = copy_tree_snapshot(
                source_time_series, time_series_target, max_files=MAX_PROJECT_BUNDLE_FILES,
                max_bytes=MAX_MODEL_UPLOAD_BYTES,
            ) if source_time_series.is_dir() else {"files": 0, "bytes": 0}
            if not time_series_target.exists():
                time_series_target.mkdir(parents=True, exist_ok=True)

            archive_stats = {"files": 0, "bytes": 0}
            versions = store.project_directory(project.id) / "versions"
            if project.lifecycle.status != "baseline" and versions.is_dir():
                archive_stats = copy_tree_snapshot(
                    versions, archive_target, max_files=MAX_PROJECT_BUNDLE_FILES,
                    max_bytes=MAX_MODEL_UPLOAD_BYTES,
                )
            else:
                archive_target.mkdir(parents=True, exist_ok=True)

            inventory = project_bundle_inventory(staging)
            total_bytes = sum(int(item["size"]) for item in inventory)
            if len(inventory) > MAX_PROJECT_BUNDLE_FILES:
                raise ProjectBundleError(f"完整包文件数量不能超过 {MAX_PROJECT_BUNDLE_FILES}")
            if total_bytes > MAX_MODEL_UPLOAD_BYTES:
                raise ProjectBundleError("完整包展开数据不能超过 8 GiB")
            manifest = {
                "format": PROJECT_BUNDLE_FORMAT,
                "format_version": PROJECT_BUNDLE_FORMAT_VERSION,
                "application_version": __version__,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "export_mode": "baseline" if project.lifecycle.status == "baseline" else "checked_in",
                "source": {
                    "project_id": project.id,
                    "name": project.name,
                    "category": project.category,
                    "lifecycle": project.lifecycle.status,
                },
                "asset": {
                    "source_reference": project.mesh_root,
                    "snapshot_name": _bundle_asset_snapshot_name(project),
                    "mode": "baseline_frozen_snapshot" if project.lifecycle.status == "baseline" else (
                        "public_asset_save_as" if str(project.mesh_root).startswith("@model_assets/") else "project_asset_snapshot"
                    ),
                    "files": asset_stats["files"],
                    "bytes": asset_stats["bytes"],
                },
                "delivery": {"files": delivery_stats["files"], "bytes": delivery_stats["bytes"]},
                "time_series": {
                    "files": time_series_stats["files"], "bytes": time_series_stats["bytes"],
                    "portable_sidecar": True,
                },
                "archive_logs": {
                    "files": archive_stats["files"], "bytes": archive_stats["bytes"],
                    "versions": 0 if project.lifecycle.status == "baseline" else len(store.list_versions(project.id)),
                    "baseline_has_no_archive_property": project.lifecycle.status == "baseline",
                },
                "inventory": inventory,
            }
            (staging / PROJECT_BUNDLE_MANIFEST_NAME).write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
            )
            write_bundle_zip(staging, archive_path)
    except (OSError, ValueError, ProjectBundleError) as exc:
        archive_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"完整包导出失败：{exc}") from exc

    def stream_archive():
        try:
            with archive_path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    yield chunk
        finally:
            archive_path.unlink(missing_ok=True)

    safe_name = _safe_filename(project.name) or project.id
    encoded_name = urllib.parse.quote(f"{safe_name}_完整包.zip")
    return StreamingResponse(
        stream_archive(), media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@app.post("/api/projects/import-bundle", status_code=201)
async def import_project_bundle(
    file: UploadFile = File(...),
    target_category: str = Form("None"),
) -> dict[str, Any]:
    identity = _require_project_bundle_access()
    try:
        resolved_category = _import_target_category(target_category, "None")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    fd, upload_name = tempfile.mkstemp(prefix="project_bundle_upload_", suffix=".zip")
    os.close(fd)
    upload_path = Path(upload_name)
    uploaded_bytes = 0
    try:
        with upload_path.open("wb") as stream:
            while chunk := await file.read(1024 * 1024):
                uploaded_bytes += len(chunk)
                if uploaded_bytes > MAX_MODEL_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="完整包压缩文件不能超过 8 GiB")
                stream.write(chunk)
        if uploaded_bytes <= 0:
            raise HTTPException(status_code=422, detail="完整包为空")

        with tempfile.TemporaryDirectory(prefix="project_bundle_import_") as temporary:
            extracted = Path(temporary) / "bundle"
            extract_bundle_zip(
                upload_path, extracted, max_files=MAX_PROJECT_BUNDLE_FILES,
                max_file_bytes=MAX_MODEL_UPLOAD_BYTES, max_total_bytes=MAX_MODEL_UPLOAD_BYTES,
            )
            manifest_path = extracted / PROJECT_BUNDLE_MANIFEST_NAME
            if manifest_path.stat().st_size > MAX_PROJECT_JSON_BYTES:
                raise ProjectBundleError("完整包 manifest.json 超过 20 MiB")
            manifest = load_project_bundle_manifest(extracted)
            verify_project_bundle_inventory(extracted, manifest)
            model_path = extracted / PROJECT_BUNDLE_MODEL_JSON_PATH
            if model_path.stat().st_size > MAX_PROJECT_JSON_BYTES:
                raise ProjectBundleError("完整包内模型 JSON 超过 20 MiB")
            try:
                model_payload = json.loads(model_path.read_text("utf-8"))
            except ValueError as exc:
                raise ProjectBundleError("完整包内模型 JSON 无法解析") from exc
            if not isinstance(model_payload, dict) or model_payload.get("format") != "mujoco_studio_project":
                raise ProjectBundleError("完整包内模型 JSON 格式无效")
            export_mode = str(model_payload.get("export_mode", ""))
            if export_mode not in {"baseline", "checked_in"} or export_mode != str(manifest.get("export_mode", "")):
                raise ProjectBundleError("完整包 manifest 与模型生命周期不一致")

            created_ids: list[str] = []
            created_asset: tuple[str, str] | None = None
            try:
                result = _import_project_json_payload(
                    model_payload, target_category=resolved_category,
                    baseline_mesh_root_override="assets/baseline_mesh_snapshot" if export_mode == "baseline" else None,
                )
                working_id = str(result["project"]["id"])
                created_ids.append(working_id)
                baseline_id = str((result.get("baseline_project") or {}).get("id", ""))
                if baseline_id:
                    created_ids.insert(0, baseline_id)

                asset_source = extracted / PROJECT_BUNDLE_ASSETS_DIR
                asset_reference = ""
                asset_name = ""
                if export_mode == "baseline" and baseline_id:
                    baseline_project = store.get(baseline_id)
                    baseline_asset_root = store.resolve_mesh_root(baseline_id, baseline_project.mesh_root, create=True)
                    if asset_source.is_dir():
                        store.copy_delivery_tree(asset_source, baseline_asset_root)

                has_asset_payload = asset_source.is_dir() and any(path.is_file() for path in asset_source.rglob("*"))
                source_mesh_root = str((model_payload.get("state") or {}).get("project", {}).get("mesh_root", "") or "")
                if has_asset_payload or source_mesh_root:
                    preferred = str((manifest.get("asset") or {}).get("snapshot_name", "") or "model_assets")
                    asset_name = _unique_import_asset_name(resolved_category, preferred)
                    asset_reference, asset_target = store.create_model_asset_folder(
                        resolved_category, asset_name, uploaded_by=identity.username,
                    )
                    created_asset = (resolved_category, asset_name)
                    if asset_source.is_dir():
                        store.copy_delivery_tree(asset_source, asset_target)
                    updated, asset_repair = _set_imported_project_mesh_root(working_id, asset_reference, identity)
                    result["project"] = updated.model_dump()
                    result["asset_repair"] = asset_repair

                delivery_source = extracted / PROJECT_BUNDLE_DELIVERY_DIR
                delivery_targets: list[str] = []
                if delivery_source.is_dir():
                    if baseline_id:
                        baseline_delivery = store.delivery_directory(store.get(baseline_id), create=True)
                        store.copy_delivery_tree(delivery_source, baseline_delivery)
                        delivery_targets.append(baseline_id)
                    working_delivery = store.delivery_directory(store.get(working_id), create=True)
                    store.copy_delivery_tree(delivery_source, working_delivery)
                    delivery_targets.append(working_id)

                time_series_source = extracted / PROJECT_BUNDLE_TIME_SERIES_DIR
                time_series_targets: list[str] = []
                if time_series_source.is_dir():
                    if baseline_id:
                        baseline_time_series = store.time_series_directory(store.get(baseline_id), create=True)
                        store.copy_delivery_tree(time_series_source, baseline_time_series)
                        time_series_targets.append(baseline_id)
                    working_time_series = store.time_series_directory(store.get(working_id), create=True)
                    store.copy_delivery_tree(time_series_source, working_time_series)
                    time_series_targets.append(working_id)

                archive_count = 0
                archive_source = extracted / PROJECT_BUNDLE_ARCHIVE_DIR
                if export_mode == "checked_in":
                    current = store.get(working_id)
                    archive_count = _import_bundle_archive_history(
                        archive_source, working_id, current.category, current.mesh_root,
                    )
                elif archive_source.is_dir() and any(path.is_file() for path in archive_source.rglob("*")):
                    raise ProjectBundleError("基线完整包不应携带 baseline 本体的 versions 历史")

                result["bundle"] = {
                    "format_version": int(manifest.get("format_version", 0) or 0),
                    "current_format_version": PROJECT_BUNDLE_FORMAT_VERSION,
                    "target_category": resolved_category,
                    "asset_reference": asset_reference,
                    "asset_folder_name": asset_name,
                    "delivery_project_ids": delivery_targets,
                    "time_series_project_ids": time_series_targets,
                    "archive_versions_imported": archive_count,
                    "source_project_id": str((manifest.get("source") or {}).get("project_id", "")),
                }
                return result
            except Exception:
                _cleanup_failed_bundle_import(created_ids, created_asset)
                raise
    except HTTPException:
        raise
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ProjectBundleError) as exc:
        raise HTTPException(status_code=422, detail=f"完整包导入失败：{exc}") from exc
    finally:
        upload_path.unlink(missing_ok=True)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> ProjectSpec:
    try:
        project = core.get(project_id).project()
        require_project_access(project)
        return project
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.post("/api/projects/{project_id}/edit-session")
def begin_project_edit_session(project_id: str) -> dict[str, Any]:
    """Enter model editing; checked-in models use temporary state and baselines stay read-only."""
    try:
        project = store.get(project_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    identity = require_project_access(project, write=False)
    if project.lifecycle.status == "baseline":
        return {"mode": "readonly", "project": project.model_dump(), "archived": None}
    if project.lifecycle.status == "checked_in":
        if identity.role not in {"engineer", "admin"}:
            raise HTTPException(403, "当前账号无项目写入权限")
        instance = core.begin_ephemeral_edit(project_id)
        return {"mode": "temporary", "project": instance.project().model_dump(), "archived": None}
    if project.lifecycle.status != "checked_out":
        raise HTTPException(status_code=409, detail="未知模型生命周期状态")
    if project.lifecycle.checked_out_by and project.lifecycle.checked_out_by.casefold() != identity.username.casefold():
        raise HTTPException(status_code=403, detail=f"模型已由 {project.lifecycle.checked_out_by} 签出")
    # Opening a persistent Edit Session is an explicit request for edit authority.
    # Reuse the lifecycle coordinator so an expired/replaced browser lease is
    # rebound safely, while preserving the existing model-idle deadline.
    project, _transition = _coordinate_lifecycle_transition(
        project_id, "check_out", identity, client="human_ui",
        intent="edit_session_open：保持原模型 idle deadline",
    )
    core.begin_authoritative_edit(project_id)
    deadline = _pending_deadline(project_id) or _ensure_idle_check_in(project_id, identity)
    return {
        "mode": "persistent",
        "project": core.get(project_id).project().model_dump(),
        "archived": None,
        "idle_check_in_seconds": EDIT_IDLE_CHECKIN_SECONDS,
        "idle_check_in_deadline": deadline,
    }


def _finish_authoritative_edit(
    project_id: str, identity: Identity, *, auto_check_in: bool, intent: str | None = None,
) -> dict[str, Any]:
    """Close Edit Session; when requested, check in first so failures never half-converge."""
    with core.acquire(project_id) as instance:
        project = instance.project()
        require_project_access(project, write=True)
        archived = None
        previous_lease_id = str(project.lifecycle.lease_id or "")
        if auto_check_in and project.lifecycle.status == "checked_out":
            instance.prepare_next_check_in_archive(
                archive=True,
                log=f"系统自动签入：{intent}" if intent else "系统自动签入",
            )
            try:
                result = instance.bus.dispatch({
                    "tool_id": "project.lifecycle",
                    "params": {
                        "action": "check_in",
                        "actor": identity.username,
                        "lease_id": identity.lease_id,
                        **({"intent": intent} if intent else {}),
                    },
                    "actor": identity.username, "client": "human_ui",
                })
            finally:
                instance.clear_next_check_in_archive_policy()
            if not result.ok:
                raise HTTPException(status_code=409, detail=result.errors)
            with _PENDING_CHECKIN_LOCK:
                _PENDING_CHECKINS.pop(project_id, None)
            _persist_pending_checkins()
            if previous_lease_id and not _lease_has_checkout(previous_lease_id):
                auth.sessions.deactivate_lease_id(previous_lease_id)
        # Edit Session is transient. End it only after a requested lifecycle
        # check-in has succeeded, so failed logout/check-in remains retryable.
        core.end_authoritative_edit(project_id)
        return {"archived": archived, "project": instance.project()}


# Runtime coordination state. Lifecycle remains authoritative in ProjectSpec; this
# bounded file only persists when an already-checked-out project should next be
# auto-checked-in, so restart cannot collapse Lifecycle into the in-memory Session table.
_PENDING_CHECKINS: dict[str, dict[str, Any]] = {}
_PENDING_CHECKIN_LOCK = threading.RLock()
_PENDING_CHECKIN_PATH = RUNTIME_STATE_DIR / "pending_checkins.json"


def _pending_identity(record: dict[str, Any]) -> Identity:
    return Identity(
        username=str(record.get("username", "system")),
        role=str(record.get("role", "engineer")),
        session_id="",
        lease_id=str(record.get("lease_id", "")),
        single_user=True,
    )


def _pending_record(project_id: str, identity: Identity, deadline_epoch: float, reason: str, retry_count: int = 0) -> dict[str, Any]:
    return {
        "project_id": str(project_id),
        "lease_id": str(identity.lease_id or ""),
        "username": str(identity.username or ""),
        "role": str(identity.role or "engineer"),
        "deadline_epoch": float(deadline_epoch),
        "reason": str(reason or "idle"),
        "retry_count": max(0, int(retry_count)),
    }


def _persist_pending_checkins() -> None:
    with _PENDING_CHECKIN_LOCK:
        rows = [dict(value) for _key, value in sorted(_PENDING_CHECKINS.items())]
    atomic_write_text(
        _PENDING_CHECKIN_PATH,
        json.dumps({"version": 1, "records": rows}, ensure_ascii=False, indent=2),
    )


def _load_pending_checkins() -> int:
    loaded: dict[str, dict[str, Any]] = {}
    try:
        payload = json.loads(_PENDING_CHECKIN_PATH.read_text("utf-8"))
        rows = payload.get("records", []) if isinstance(payload, dict) else []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            project_id = str(raw.get("project_id", "")).strip()
            lease_id = str(raw.get("lease_id", "")).strip()
            username = str(raw.get("username", "")).strip()
            if not project_id or not lease_id or not username:
                continue
            deadline = float(raw.get("deadline_epoch", 0.0))
            if not math.isfinite(deadline) or deadline <= 0:
                continue
            loaded[project_id] = _pending_record(
                project_id,
                Identity(username, str(raw.get("role", "engineer")), lease_id=lease_id, single_user=True),
                deadline,
                str(raw.get("reason", "idle")),
                int(raw.get("retry_count", 0)),
            )
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError) as exc:
        LOGGER.error("failed to load pending check-ins: %s", exc)
    with _PENDING_CHECKIN_LOCK:
        _PENDING_CHECKINS.clear()
        _PENDING_CHECKINS.update(loaded)
    return len(loaded)


def _pending_deadline(project_id: str) -> float | None:
    with _PENDING_CHECKIN_LOCK:
        record = _PENDING_CHECKINS.get(project_id)
        return float(record["deadline_epoch"]) if record is not None else None


def _pending_failures_for_username(username: str) -> list[dict[str, Any]]:
    key = str(username or "").casefold()
    with _PENDING_CHECKIN_LOCK:
        return [
            {
                "project_id": str(record.get("project_id", "")),
                "reason": str(record.get("reason", "")),
                "retry_count": int(record.get("retry_count", 0)),
            }
            for record in _PENDING_CHECKINS.values()
            if str(record.get("username", "")).casefold() == key
            and str(record.get("reason", "")) == "failed_permanent"
        ]


def _schedule_idle_check_in(project_id: str, identity: Identity) -> float:
    """Start/reset the independent model-idle wall clock after checkout or a real model write."""
    deadline = time.time() + EDIT_IDLE_CHECKIN_SECONDS
    with _PENDING_CHECKIN_LOCK:
        _PENDING_CHECKINS[project_id] = _pending_record(project_id, identity, deadline, "idle")
    _persist_pending_checkins()
    return deadline


def _ensure_idle_check_in(project_id: str, identity: Identity) -> float:
    """Ensure an idle deadline exists without treating Edit Session open/close as model activity."""
    with _PENDING_CHECKIN_LOCK:
        current = _PENDING_CHECKINS.get(project_id)
        if current is not None and str(current.get("username", "")).casefold() == identity.username.casefold():
            if str(current.get("lease_id", "")) != identity.lease_id:
                current["lease_id"] = identity.lease_id
                current["role"] = identity.role
                _persist_pending_checkins()
            return float(current["deadline_epoch"])
    return _schedule_idle_check_in(project_id, identity)


def _schedule_idle_check_in_at(project_id: str, identity: Identity, deadline_epoch: float, reason: str = "idle") -> float:
    with _PENDING_CHECKIN_LOCK:
        _PENDING_CHECKINS[project_id] = _pending_record(project_id, identity, deadline_epoch, reason)
    _persist_pending_checkins()
    return float(deadline_epoch)


def _schedule_deferred_check_in(project_id: str, identity: Identity, reason: str, *, increment_retry: bool = False) -> float:
    """Retry check-in promptly after a blocking Job or a real lifecycle failure."""
    deadline = time.time() + max(1.0, float(LEASE_SWEEP_SECONDS))
    with _PENDING_CHECKIN_LOCK:
        previous = _PENDING_CHECKINS.get(project_id, {})
        retry_count = int(previous.get("retry_count", 0)) + (1 if increment_retry else 0)
        final_reason = "failed_permanent" if retry_count >= PENDING_CHECKIN_MAX_RETRY else reason
        final_deadline = deadline
        _PENDING_CHECKINS[project_id] = _pending_record(
            project_id, identity, final_deadline, final_reason, retry_count,
        )
    _persist_pending_checkins()
    if final_reason == "failed_permanent":
        LOGGER.error(
            "automatic check-in reached retry limit: project=%s retry_count=%s",
            project_id, retry_count,
        )
    return final_deadline


def _run_due_idle_checkins(now: float | None = None) -> int:
    current = time.time() if now is None else float(now)
    with _PENDING_CHECKIN_LOCK:
        due = [
            (project_id, dict(record))
            for project_id, record in _PENDING_CHECKINS.items()
            if str(record.get("reason", "")) != "failed_permanent"
            and float(record.get("deadline_epoch", float("inf"))) <= current
        ]
    completed = 0
    for project_id, record in due:
        identity = _pending_identity(record)
        reason = str(record.get("reason", "idle"))
        token = set_active_identity(identity)
        try:
            project = core.get(project_id).project()
            if project.lifecycle.status != "checked_out" or project.lifecycle.lease_id != identity.lease_id:
                with _PENDING_CHECKIN_LOCK:
                    _PENDING_CHECKINS.pop(project_id, None)
                _persist_pending_checkins()
                continue
            if jobs.has_active(project_id=project_id, owner_lease_id=identity.lease_id):
                _schedule_deferred_check_in(project_id, identity, reason if reason != "idle" else "idle_job")
                continue
            result = _finish_authoritative_edit(
                project_id, identity, auto_check_in=True, intent=f"idle_expired:{reason}",
            )
            completed += int(result["project"].lifecycle.status == "checked_in")
            _persist_pending_checkins()
        except Exception:
            _schedule_deferred_check_in(project_id, identity, f"retry:{reason}", increment_retry=True)
            LOGGER.exception("automatic check-in failed: project=%s reason=%s", project_id, reason)
        finally:
            reset_active_identity(token)
    return completed


def _converge_browser_session(identity: Identity) -> dict[str, Any]:
    """Converge an explicit logout into complete/deferred/failed lifecycle outcomes."""
    context_token = set_active_identity(identity)
    checked_in: list[str] = []
    deferred_projects: list[str] = []
    failures: list[dict[str, str]] = []
    try:
        candidates = set(core.authoritative_projects_for_lease(identity.lease_id))
        for item in store.list():
            if (str(item.get("lifecycle_status", "")) == "checked_out"
                    and str(item.get("lease_id", "")) == identity.lease_id):
                project_id = str(item.get("id", ""))
                if project_id:
                    candidates.add(project_id)
        for project_id in sorted(candidates):
            try:
                if jobs.has_active(project_id=project_id, owner_lease_id=identity.lease_id):
                    _finish_authoritative_edit(project_id, identity, auto_check_in=False)
                    _schedule_deferred_check_in(project_id, identity, "logout_job")
                    deferred_projects.append(project_id)
                    continue
                result = _finish_authoritative_edit(
                    project_id, identity, auto_check_in=True, intent="logout",
                )
                if result["project"].lifecycle.status == "checked_in":
                    checked_in.append(project_id)
            except Exception as exc:
                failures.append({"project_id": project_id, "error": str(exc)})
                LOGGER.exception("automatic check-in failed during logout convergence: project=%s", project_id)
        status = "failed" if failures else ("deferred" if deferred_projects else "complete")
        if status in {"complete", "deferred"}:
            core.end_lease(identity.lease_id)
        return {
            "ok": status != "failed",
            "status": status,
            "checked_in_project_ids": checked_in,
            "deferred_project_ids": deferred_projects,
            "failures": failures,
        }
    finally:
        reset_active_identity(context_token)


def _release_edit_authority(identity: Identity) -> dict[str, Any]:
    """Release transient edit authority without changing persistent Lifecycle."""
    released_projects = set(core.authoritative_projects_for_lease(identity.lease_id))
    core.end_lease(identity.lease_id)
    if identity.session_id:
        auth.sessions.deactivate_lease_id(identity.lease_id, reason="expired")
    return {"released_project_ids": sorted(released_projects)}


_SWEEPER_STOP = threading.Event()
_SWEEPER_THREAD: threading.Thread | None = None
_LAST_RECLAIM_MONO = 0.0


def _sweep_runtime_once() -> dict[str, int]:
    leases = auth.sessions.expired_active_leases()
    expired_sessions = auth.sessions.sweep_expired_sessions()
    released = 0
    session_ids: set[str] = set()
    for identity in [*leases, *expired_sessions]:
        if identity.session_id in session_ids:
            continue
        session_ids.add(identity.session_id)
        try:
            _release_edit_authority(identity)
            released += 1
            LOGGER.warning("released expired browser edit authority for %s", identity.username)
        except Exception:
            LOGGER.exception("failed to release expired browser edit authority for %s", identity.username)
            core.end_lease(identity.lease_id)
    idle_checked_in = _run_due_idle_checkins()
    jobs.prune()
    return {
        "leases": len(leases), "sessions": len(expired_sessions),
        "released": released, "converged": 0, "idle_checked_in": idle_checked_in,
    }


def _due_for_reclaim(now: float | None = None) -> bool:
    """Return whether the low-frequency filesystem maintenance interval elapsed."""
    current = time.monotonic() if now is None else float(now)
    return (current - _LAST_RECLAIM_MONO) >= ORPHAN_RECLAIM_INTERVAL_SECONDS


def _sweeper_loop() -> None:
    global _LAST_RECLAIM_MONO
    while not _SWEEPER_STOP.wait(LEASE_SWEEP_SECONDS):
        try:
            _sweep_runtime_once()
        except Exception:
            LOGGER.exception("runtime lease/session sweep failed; sweeper will continue")
        if not _due_for_reclaim():
            continue
        try:
            _reclaim_orphan_workspaces()
        except Exception:
            LOGGER.exception("periodic filesystem workspace reclaim failed; sweeper will continue")
        finally:
            _LAST_RECLAIM_MONO = time.monotonic()


def _has_live_session_lease(lease_id: str, now: float | None = None) -> bool:
    """Check the bounded in-memory session table without weakening lease isolation."""
    value = str(lease_id or "").strip()
    if not value:
        return False
    current = time.monotonic() if now is None else float(now)
    sessions = auth.sessions
    with sessions._lock:
        return any(
            item.identity.lease_id == value
            and item.expires_at > current
            and item.lease_active
            and item.lease_expires_at > current
            for item in sessions._items.values()
        )


def _directory_size(path: Path) -> int:
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file() and not item.is_symlink():
                try:
                    total += item.stat().st_size
                except OSError:
                    continue
    except OSError:
        return total
    return total


def _orphan_workspace_candidates() -> list[Path]:
    """Return only the three SPEC S1 temporary-directory classes."""
    candidates: list[Path] = []
    projects_root = DATA_ROOT / "projects"
    if projects_root.is_dir():
        for base in projects_root.rglob("job_workspaces"):
            if base.is_dir() and base.parent.name == "core":
                candidates.extend(path for path in base.iterdir() if path.is_dir() and not path.is_symlink())
        for base in projects_root.rglob("viewer"):
            if base.is_dir() and base.parent.name == "outputs":
                candidates.extend(path for path in base.iterdir() if path.is_dir() and not path.is_symlink())
    edit_root = DATA_ROOT / ".edit_sessions"
    if edit_root.is_dir():
        candidates.extend(path for path in edit_root.iterdir() if path.is_dir() and not path.is_symlink())
    return candidates


def _prune_existing_result_bases() -> int:
    """Apply the existing result-count policy to authoritative project result roots.

    Do not call ``_result_base`` here: that request-context helper may resolve to an
    ephemeral edit-session directory and ``store.results`` also creates missing
    directories. Periodic maintenance must be side-effect-free for projects that have
    never produced results and must only prune persistent project results.
    """
    removed = 0
    for item in store.list():
        project_id = str(item.get("id", "")).strip()
        if not project_id:
            continue
        try:
            results_base = store.project_directory(project_id) / "results"
            if results_base.is_dir():
                removed += len(job_workspaces.prune(results_base))
        except (KeyError, OSError, ValueError) as exc:
            LOGGER.warning("result retention prune skipped project %s: %s", project_id, exc)
    return removed


def _reclaim_orphan_workspaces() -> dict[str, Any]:
    """Delete expired, unowned S1 workspaces and retain a bounded audit trail."""
    cutoff = time.time() - ORPHAN_WORKSPACE_TTL_HOURS * 3600.0
    active_job_workspaces = {
        Path(str(item["workspace"])).resolve()
        for item in jobs.list(limit=jobs.max_records)
        if item.get("status") not in TERMINAL_STATUSES and item.get("workspace")
    }
    viewer_workspaces = {path.resolve() for path in VIEWER_REGISTRY.protected_workspaces()}
    ephemeral_workspaces = {Path(path).resolve() for path in core._ephemeral_dirs.values() if path}
    protected = active_job_workspaces | viewer_workspaces | ephemeral_workspaces

    removed: list[str] = []
    released_bytes = 0
    for path in _orphan_workspace_candidates():
        try:
            resolved = path.resolve()
            if resolved in protected or path.stat().st_mtime >= cutoff:
                continue
            size = _directory_size(path)
            shutil.rmtree(path)
            if not path.exists():
                removed.append(str(path))
                released_bytes += size
        except OSError as exc:
            LOGGER.warning("orphan workspace reclaim skipped %s: %s", path, exc)

    pruned_results = _prune_existing_result_bases()
    record = {
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "ttl_hours": ORPHAN_WORKSPACE_TTL_HOURS,
        "removed_count": len(removed),
        "released_bytes": released_bytes,
        "removed": removed,
        "pruned_result_directories": pruned_results,
    }
    audit_path = DATA_ROOT / "workspace_reclaim.json"
    history: list[dict[str, Any]] = []
    try:
        current = json.loads(audit_path.read_text("utf-8"))
        if isinstance(current, dict) and isinstance(current.get("records"), list):
            history = [item for item in current["records"] if isinstance(item, dict)]
        elif isinstance(current, list):
            history = [item for item in current if isinstance(item, dict)]
    except (OSError, ValueError):
        pass
    atomic_write_text(
        audit_path,
        json.dumps({"records": [*history, record][-20:]}, ensure_ascii=False, indent=2),
    )
    LOGGER.info("orphan workspace reclaim: removed=%d released_bytes=%d pruned_results=%d", len(removed), released_bytes, pruned_results)
    return record


def _checked_out_at_epoch(project: ProjectSpec) -> float | None:
    raw = str(project.lifecycle.checked_out_at or "").strip()
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    except ValueError:
        return None


def _recover_orphaned_checkouts() -> dict[str, Any]:
    """Restore idle timers across restart and recover only truly expired orphaned checkouts."""
    recovered: list[str] = []
    preserved: list[str] = []
    failures: list[dict[str, str]] = []
    now_epoch = time.time()
    for item in store.list():
        if str(item.get("lifecycle_status", "")) != "checked_out":
            continue
        project_id = str(item.get("id", ""))
        if not project_id:
            continue
        try:
            project = store.get(project_id)
            lease_id = str(project.lifecycle.lease_id or "")
            owner = str(project.lifecycle.checked_out_by or "system")
            # Internal baseline leases have their own strict one-shot startup
            # recovery. Never let the generic idle sweeper impersonate the
            # reserved actor, especially when its lease shape is suspicious.
            if owner == BASELINE_SYSTEM_ACTOR:
                preserved.append(project_id)
                continue
            with _PENDING_CHECKIN_LOCK:
                pending = dict(_PENDING_CHECKINS.get(project_id, {}))
            if pending and str(pending.get("lease_id", "")) != lease_id:
                pending = {}
            if pending:
                deadline = float(pending.get("deadline_epoch", 0.0))
                retry_reason = str(pending.get("reason", "idle"))
                recovery_intent = "restart_idle_expired"
            else:
                checked_out_at = _checked_out_at_epoch(project)
                # A missing/malformed checked_out_at is not proof that the idle TTL
                # already expired. Conservatively start one full window instead of
                # letting process restart itself become a lifecycle trigger.
                deadline = (
                    checked_out_at + EDIT_IDLE_CHECKIN_SECONDS
                    if checked_out_at is not None
                    else now_epoch + EDIT_IDLE_CHECKIN_SECONDS
                )
                retry_reason = "restart_orphan"
                recovery_intent = "restart_orphan"
                identity = Identity(owner, "engineer", lease_id=lease_id, single_user=True)
                _schedule_idle_check_in_at(project_id, identity, deadline, "idle")
            if retry_reason == "failed_permanent":
                preserved.append(project_id)
                continue
            expired = deadline <= now_epoch
            if not expired or _has_live_session_lease(lease_id):
                preserved.append(project_id)
                continue
            recovery_identity = Identity(owner, "engineer", lease_id=lease_id, single_user=True)
            token = set_active_identity(recovery_identity)
            try:
                result = _finish_authoritative_edit(
                    project_id, recovery_identity, auto_check_in=True, intent=recovery_intent,
                )
                if result["project"].lifecycle.status == "checked_in":
                    recovered.append(project_id)
                    LOGGER.warning(
                        "recovered expired orphan checkout after restart: project=%s owner=%s intent=%s",
                        project_id, owner, recovery_intent,
                    )
            finally:
                reset_active_identity(token)
        except Exception as exc:
            failures.append({"project_id": project_id, "error": str(exc)})
            LOGGER.exception("failed to recover orphaned checkout after restart: project=%s", project_id)
    _persist_pending_checkins()
    return {"recovered": recovered, "preserved": preserved, "failures": failures}


@app.on_event("startup")
def _start_runtime_sweeper() -> None:
    global _SWEEPER_THREAD, _LAST_RECLAIM_MONO
    _load_pending_checkins()
    # Restore V2.14.1 leaked system leases BEFORE normal idle recovery.
    _recover_abandoned_baseline_system_checkouts()
    _recover_orphaned_checkouts()
    _reclaim_orphan_workspaces()
    _LAST_RECLAIM_MONO = time.monotonic()
    if not FSYNC_ENABLED:
        LOGGER.warning("已禁用持久化同步，掉电可能丢失最后一次写入")
    if _SWEEPER_THREAD is not None and _SWEEPER_THREAD.is_alive():
        return
    _SWEEPER_STOP.clear()
    _SWEEPER_THREAD = threading.Thread(target=_sweeper_loop, name="mujoco-studio-lease-sweeper", daemon=True)
    _SWEEPER_THREAD.start()


@app.on_event("shutdown")
def _stop_runtime_sweeper() -> None:
    _SWEEPER_STOP.set()


@app.get("/api/admin/pending-checkins")
def admin_pending_checkins() -> dict[str, Any]:
    identity = active_identity()
    if identity.role != "admin":
        raise HTTPException(403, "只有管理员可以查看待签入队列")
    with _PENDING_CHECKIN_LOCK:
        rows = [
            {
                "project_id": str(record.get("project_id", "")),
                "username": str(record.get("username", "")),
                "reason": str(record.get("reason", "")),
                "deadline": None if not math.isfinite(float(record.get("deadline_epoch", float("inf")))) else float(record.get("deadline_epoch", 0.0)),
                "retry_count": int(record.get("retry_count", 0)),
            }
            for record in sorted(_PENDING_CHECKINS.values(), key=lambda item: str(item.get("project_id", "")))
        ]
    return {"pending_checkins": rows}


@app.delete("/api/projects/{project_id}/edit-session")
def end_project_edit_session(project_id: str) -> dict[str, Any]:
    identity = active_identity()
    if core.is_ephemeral(project_id):
        core.end_ephemeral_edit(project_id)
        project = store.get(project_id)
        return {"mode": "temporary", "discarded": True, "archived": None, "project": project.model_dump()}
    result = _finish_authoritative_edit(project_id, identity, auto_check_in=False)
    deadline = _ensure_idle_check_in(project_id, identity)
    return {
        "mode": "persistent", "discarded": False, "auto_checked_in": False,
        "idle_check_in_seconds": EDIT_IDLE_CHECKIN_SECONDS, "idle_check_in_deadline": deadline,
        "archived": result["archived"], "project": result["project"].model_dump(),
    }


@app.post("/api/projects/{project_id}/edit-session/leave")
def leave_project_edit_session(project_id: str, request: EditSessionLeaveRequest | None = None) -> dict[str, Any]:
    """Close one model Editor session; optionally persist its final authoritative snapshot."""
    identity = active_identity()
    if core.is_ephemeral(project_id):
        core.end_ephemeral_edit(project_id)
        project = store.get(project_id)
        return {"mode": "temporary", "discarded": True, "auto_checked_in": False, "project": project.model_dump()}
    project = core.get(project_id).project()
    if project.lifecycle.status != "checked_out":
        core.end_authoritative_edit(project_id)
        return {"mode": "persistent", "discarded": False, "auto_checked_in": False, "project": project.model_dump()}
    if request and request.project is not None:
        if project.lifecycle.lease_id == identity.lease_id:
            update_project(project_id, request.project)
            _record_model_write_activity(project_id, identity, "project.replace")
        else:
            LOGGER.warning("final editor-leave snapshot rejected for project %s: lease mismatch", project_id)
    result = _finish_authoritative_edit(project_id, identity, auto_check_in=False)
    deadline = _ensure_idle_check_in(project_id, identity)
    return {
        "mode": "persistent", "discarded": False, "auto_checked_in": False,
        "idle_check_in_seconds": EDIT_IDLE_CHECKIN_SECONDS, "idle_check_in_deadline": deadline,
        "archived": result["archived"], "project": result["project"].model_dump(),
    }


@app.post("/api/projects/{project_id}/lifecycle")
def transition_project_lifecycle(project_id: str, request: ProjectLifecycleRequest) -> ProjectSpec:
    identity = active_identity()
    updated, _result = _coordinate_lifecycle_transition(
        project_id, request.action, identity, client="human_ui",
        archive_log=request.log if request.action == "check_in" else "",
        archive_check_in=request.archive,
        archive_name=request.archive_name if request.action == "check_in" else "",
        overwrite_version_id=request.overwrite_version_id if request.action == "check_in" else "",
    )
    return updated


@app.post("/api/projects/{project_id}/force-check-in")
def force_check_in(project_id: str) -> ProjectSpec:
    identity = active_identity()
    if identity.role != "admin":
        raise HTTPException(403, "只有管理员可以强制签入")
    with core.acquire(project_id) as instance:
        project = instance.project()
        if project.lifecycle.status != "checked_out":
            raise HTTPException(409, "项目当前未被签出")
        previous_lease_id = str(project.lifecycle.lease_id or "")
        instance.prepare_next_check_in_archive(archive=True, log="管理员强制签入")
        try:
            result = instance.bus.dispatch({
                "tool_id": "project.lifecycle",
                "params": {"action": "check_in", "actor": identity.username, "lease_id": identity.lease_id, "force": True, "log": "管理员强制签入"},
                "actor": identity.username, "client": "human_ui",
            })
        finally:
            instance.clear_next_check_in_archive_policy()
        if not result.ok:
            raise HTTPException(409, result.errors)
        with _PENDING_CHECKIN_LOCK:
            _PENDING_CHECKINS.pop(project_id, None)
        _persist_pending_checkins()
        core.end_authoritative_edit(project_id)
        if previous_lease_id and not _lease_has_checkout(previous_lease_id):
            auth.sessions.deactivate_lease_id(previous_lease_id)
        return instance.project()




def _baseline_result_is_current(source: ProjectSpec) -> tuple[bool, dict[str, Any] | None, Path | None, str]:
    latest_sim, latest_dir = _latest_simulation_record(source.id)
    if latest_sim is None or latest_dir is None:
        return False, latest_sim, latest_dir, "missing"
    try:
        latest_state = freshness(read_provenance(latest_dir), _fingerprint(source.id, source))
    except Exception as exc:
        return False, latest_sim, latest_dir, f"fingerprint_error:{exc}"
    return latest_state.get("status") == "current", latest_sim, latest_dir, str(latest_state.get("status", "unknown"))


BASELINE_SYSTEM_ACTOR = "__baseline_system__"
BASELINE_SYSTEM_LEASE_PREFIX = "baseline_system_"


def _is_reserved_baseline_checkout(project: ProjectSpec) -> bool:
    """Recognize ONLY the system leases created by V2.13.6+ baseline repair."""
    lifecycle = project.lifecycle
    return (
        lifecycle.status == "checked_out"
        and lifecycle.checked_out_by == BASELINE_SYSTEM_ACTOR
        and re.fullmatch(r"baseline_system_[0-9a-f]{32}", str(lifecycle.lease_id or "")) is not None
    )


def _recover_abandoned_baseline_system_checkouts() -> dict[str, Any]:
    """Startup-only recovery of V2.14.1 stranded baseline-system checkouts.

    The bundled run.py uses one API process. Do not run this from an ordinary
    browser request while a baseline job may legitimately hold this lease.
    """
    recovered: list[str] = []
    failures: list[dict[str, str]] = []
    for item in store.list():
        if str(item.get("lifecycle_status", "")) != "checked_out":
            continue
        project_id = str(item.get("id", ""))
        if not project_id:
            continue
        try:
            project = store.get(project_id)
            if not _is_reserved_baseline_checkout(project):
                continue
            identity = Identity(
                BASELINE_SYSTEM_ACTOR, "engineer",
                lease_id=str(project.lifecycle.lease_id), single_user=True,
            )
            token = set_active_identity(identity)
            try:
                updated, _ = _coordinate_lifecycle_transition(
                    project_id, "check_in", identity, client="system",
                    intent="baseline_repair_restart_recovery",
                    archive_log="系统修复：恢复 V2.14.1 遗留基线签出租约",
                )
            finally:
                reset_active_identity(token)
            if updated.lifecycle.status != "checked_in":
                raise RuntimeError("系统租约恢复没有收敛到签入状态")
            recovered.append(project_id)
            LOGGER.warning("recovered orphaned baseline system checkout: project=%s", project_id)
        except Exception as exc:
            failures.append({"project_id": project_id, "error": str(exc)})
            LOGGER.exception("baseline system checkout recovery failed: project=%s", project_id)
    return {"recovered": recovered, "failures": failures}


def _repair_baseline_simulation_as_system(source: ProjectSpec) -> tuple[dict[str, Any], Path]:
    """Converge a checked-in model to a current simulation without user intervention.

    This is a narrow server-internal authority used only by baseline creation. It
    reuses project.lifecycle and the normal isolated simulation/publish pipeline;
    no browser session receives the system lease and no editable UI is exposed.
    """
    if source.lifecycle.status != "checked_in":
        raise HTTPException(status_code=409, detail="自动基线仿真修复只允许处理签入模型")
    system_actor = BASELINE_SYSTEM_ACTOR
    system_lease = f"{BASELINE_SYSTEM_LEASE_PREFIX}{uuid4().hex}"
    # Authorization reads task-local Identity, not the command actor string.
    # Switch before core.get (to avoid browser ephemeral kernels), and reset
    # even if simulation, publishing or check-in raises an exception.
    identity_token = set_active_identity(Identity(
        system_actor, "engineer", lease_id=system_lease, single_user=True,
    ))
    try:
        # Keep the authoritative kernel pinned for the entire repair.
        with core.acquire(source.id) as instance:
            checked_out = False
            workspace: Path | None = None
            try:
                result = instance.bus.dispatch({
                    "tool_id": "project.lifecycle",
                    "params": {"action": "check_out", "actor": system_actor, "lease_id": system_lease, "intent": "baseline_simulation_repair"},
                    "actor": system_actor, "client": "system",
                })
                if not result.ok:
                    raise RuntimeError(f"系统签出失败：{result.errors}")
                checked_out = True
                current = instance.project()
                fingerprint = _fingerprint(source.id, current)
                # Match /simulate: asset library references are NOT filesystem paths.
                # Passing raw @model_assets/... to isolated validation caused every
                # STL to be misreported as missing whenever baseline needs refresh.
                runtime = _runtime_project(source.id, current)
                job_id = f"baseline-repair-{uuid4().hex}"
                workspace = job_workspaces.allocate(instance.project_dir / "core" / "job_workspaces", "baseline_simulation_repair", job_id)
                simulation = run_project_simulation_isolated(runtime, workspace, progress=lambda *_args, **_kwargs: None, should_cancel=lambda: False)
                published = _publish_result_directory(
                    project_id=source.id, project=runtime, kind="simulation", job_id=job_id,
                    workspace=workspace, result=simulation, parameters={"system_baseline_repair": True}, fingerprint=fingerprint,
                )
                workspace = None  # publish moved the workspace atomically
                LOGGER.warning("baseline simulation repaired by system authority: project=%s result=%s", source.id, published.get("result_dir"))
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=409, detail=f"系统自动刷新基线仿真失败：{exc}") from exc
            finally:
                try:
                    if workspace is not None:
                        job_workspaces.discard(workspace)
                except Exception:
                    # Failed temporary-file cleanup must never strand a lifecycle lease.
                    LOGGER.exception("baseline repair workspace cleanup failed: project=%s", source.id)
                if checked_out:
                    try:
                        current = instance.project()
                        if current.lifecycle.status == "checked_out":
                            if current.lifecycle.lease_id != system_lease or current.lifecycle.checked_out_by != system_actor:
                                raise RuntimeError("内部基线租约已变化，拒绝释放其他会话的签出")
                            result = instance.bus.dispatch({
                                "tool_id": "project.lifecycle",
                                "params": {"action": "check_in", "actor": system_actor, "lease_id": system_lease, "intent": "baseline_simulation_repair_complete"},
                                "actor": system_actor, "client": "system",
                            })
                            if not result.ok:
                                raise RuntimeError(str(result.errors))
                    except Exception as exc:
                        LOGGER.exception("system baseline repair could not restore checked-in lifecycle: project=%s", source.id)
                        raise HTTPException(status_code=500, detail=f"系统自动仿真后签入失败：{exc}") from exc
            repaired = instance.project()
            if repaired.lifecycle.status != "checked_in":
                raise HTTPException(status_code=500, detail="基线修复结束后项目没有恢复签入状态")
            current, latest_sim, latest_dir, status = _baseline_result_is_current(repaired)
            if not current or latest_sim is None or latest_dir is None:
                raise HTTPException(status_code=409, detail=f"系统已自动仿真，但结果指纹仍未收敛（{status}）")
            return latest_sim, latest_dir
    finally:
        reset_active_identity(identity_token)


def _baseline_latest_simulation(source: ProjectSpec) -> tuple[dict[str, Any], Path]:
    current, latest_sim, latest_dir, _status = _baseline_result_is_current(source)
    if current and latest_sim is not None and latest_dir is not None:
        return latest_sim, latest_dir
    return _repair_baseline_simulation_as_system(source)


def _baseline_animation_html(source: ProjectSpec) -> Path:
    delivery = store.delivery_directory(source, create=True)
    _current_delivery_outputs(source)
    candidates = [
        path for path in delivery.iterdir()
        if path.is_file() and not path.is_symlink() and _delivery_kind_for_name(path.name) == "animation_html"
    ]
    if not candidates:
        raise HTTPException(
            status_code=409,
            detail="交付数据中没有动画 HTML。请让前端先提示用户并自动生成动画 HTML，再重新创建基线。",
        )
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def _baseline_gantt_png(source: ProjectSpec, stage_root: Path, expected_saved_at: float | None) -> tuple[Path, str]:
    """Return a freshly rendered Gantt PNG, preferring the browser's full Result/Gantt projection."""
    cache_dir, cache_png, cache_json = _gantt_cache_paths(source.id, create=True)
    if expected_saved_at is not None and cache_png.is_file() and cache_json.is_file():
        try:
            metadata = json.loads(cache_json.read_text(encoding="utf-8"))
            saved_at = float(metadata.get("saved_at") or 0.0)
            # The browser returns the exact saved_at produced by POST /gantt-cache.
            # Permit only tiny serialization/clock rounding; an older cache must not be frozen.
            if saved_at + 1e-3 >= float(expected_saved_at):
                target = stage_root / "latest_gantt.png"
                shutil.copy2(cache_png, target)
                return target, "browser_refreshed"
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    # API-only / browser-cache failure path: reuse the Viewer fallback renderer.
    # It is deliberately deterministic and has no dependency on a live canvas.
    try:
        _resolved, schedule = resolve_schedule(source)
        preview = _project_preview(source, include_latest_result=False)
        joint_lookup = {joint.id: joint for layer in source.layers for joint in layer.joints}
        drives = []
        for drive in source.drives:
            joint = joint_lookup.get(drive.joint_id)
            drives.append({
                "id": drive.id,
                "name": drive.name,
                "unit": "mm" if joint is not None and joint.type == "translation" else "°",
            })
        from .domain.viewer_runner import _write_legacy_gantt_cache
        fallback_dir = stage_root / "gantt_generated"
        start_time = float(source.simulation.start_time)
        end_time = max(
            float(source.simulation.end_time),
            float(latest_drive_stop_time(schedule, start_time)),
        )
        generated_png, _generated_json = _write_legacy_gantt_cache(
            list(preview.get("gantt", [])), drives, start_time, end_time, fallback_dir,
            runtime_segments=schedule,
        )
        target = stage_root / "latest_gantt.png"
        shutil.copy2(generated_png, target)
        return target, "server_regenerated"
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"打基线时甘特图 PNG 重新生成失败：{exc}") from exc


def _publish_latest_simulation_xml(project: ProjectSpec, simulation_dir: Path) -> Path:
    """Overwrite the latest generated MJCF in model delivery (never a stale source XML)."""
    source = Path(simulation_dir) / "generated" / "generated_model.xml"
    if not source.is_file():
        raise ValueError("仿真结果缺少 generated/generated_model.xml，请重新刷新仿真")
    delivery = store.delivery_directory(project, create=True)
    target = delivery / f"{_delivery_stem(project)}_仿真模型.xml"
    atomic_write_text(target, source.read_text(encoding="utf-8"), encoding="utf-8")
    _record_delivery_output(project, target, "simulation_xml", "最新仿真 XML")
    return target


def _refresh_baseline_delivery_outputs(
    source: ProjectSpec,
    state: dict[str, Any],
    *,
    gantt_saved_at: float | None = None,
    require_animation_html: bool = True,
    should_cancel: Callable[[], bool] | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Refresh managed NX/Gantt/JSON/XML without regenerating animation HTML.

    Reuse the existing animation HTML. Auxiliary CSV remains in the delivery
    tables folder, never the TSJSON-only time-series library. Stage expensive
    work before replacing managed deliverables.
    """
    delivery = store.delivery_directory(source, create=True).resolve()
    latest_sim, latest_dir = _baseline_latest_simulation(source)
    # Even when results were generated by an older build, freeze a real MJCF
    # from the same simulation provenance rather than a stale outputs/ XML.
    if should_cancel and should_cancel():
        raise InterruptedError("交付数据刷新已取消")
    animation_html = _baseline_animation_html(source) if require_animation_html else None

    stem = _delivery_stem(source)
    targets = {
        "simulation_xml": delivery / f"{stem}_仿真模型.xml",
        "nx_afu_script": delivery / f"{stem}_NX script.py",
        "gantt_png": delivery / f"{stem}_甘特图.png",
        "model_json": delivery / f"{stem}_模型.json",
    }
    stage_root = delivery / f".baseline_delivery_{uuid4().hex}.staging"
    stage_root.mkdir(parents=True, exist_ok=False)
    refreshed: list[str] = []
    try:
        source_xml = Path(latest_dir) / "generated" / "generated_model.xml"
        if not source_xml.is_file():
            raise HTTPException(status_code=409, detail="冻结仿真缺少生成的 XML；请先刷新仿真")
        stage_xml = stage_root / targets["simulation_xml"].name
        shutil.copy2(source_xml, stage_xml)
        if progress:
            progress(0.36, "正在生成 NX AFU 脚本")
        stage_nx = stage_root / targets["nx_afu_script"].name
        export_project_nx_afu_script(source, latest_sim, stage_nx)
        if should_cancel and should_cancel():
            raise InterruptedError("交付数据刷新已取消")
        if progress:
            progress(0.57, "正在生成模型 JSON 与甘特图 PNG")

        stage_model = stage_root / targets["model_json"].name
        stage_model.write_text(
            json.dumps(_project_export_payload(source, state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        generated_gantt, gantt_source = _baseline_gantt_png(source, stage_root, gantt_saved_at)
        stage_gantt = stage_root / targets["gantt_png"].name
        if generated_gantt.resolve() != stage_gantt.resolve():
            shutil.copy2(generated_gantt, stage_gantt)

        # Only publish after all outputs have been generated. HTML and the
        # existing CSV/TSV table folders are deliberately left untouched.
        if should_cancel and should_cancel():
            raise InterruptedError("交付数据刷新已取消")
        if progress:
            progress(0.83, "正在原位更新交付文件，动画 HTML 不变")
        for kind, label, staged in (
            ("simulation_xml", "最新仿真 XML", stage_xml),
            ("nx_afu_script", "NX AFU 脚本", stage_nx),
            ("gantt_png", "甘特图 PNG", stage_gantt),
            ("model_json", "模型 JSON", stage_model),
        ):
            target = targets[kind]
            if target.exists() or target.is_symlink():
                _remove_delivery_path(target)
            staged.replace(target)
            _record_delivery_output(source, target, kind, label)
            refreshed.append(kind)

        # Baseline creation still performs historical delivery reconciliation.
        # The standalone refresh must *not* traverse/prune animation variants
        # or migrate old CSVs: every HTML/table byte and filename stays intact.
        if require_animation_html:
            outputs = _current_delivery_outputs(source)
            output_kinds = {str(item.get("kind", "")) for item in outputs}
        else:
            output_kinds = {
                _delivery_kind_for_name(item.name) for item in delivery.iterdir()
                if not item.is_symlink() and (item.is_file() or item.is_dir())
            }
        required_kinds = {"nx_afu_script", "gantt_png", "model_json", "simulation_xml"}
        if require_animation_html:
            required_kinds.add("animation_html")
        missing_kinds = sorted(required_kinds - output_kinds)
        if missing_kinds:
            raise HTTPException(status_code=409, detail=f"基线交付数据未形成完整 5 类交付：缺少 {', '.join(missing_kinds)}")
        return {
            "refreshed": refreshed,
            "warnings": [],
            "animation_html": "reused_existing" if require_animation_html else "untouched",
            "animation_name": animation_html.name if animation_html is not None else "",
            "gantt_source": gantt_source,
            "reconciled_by_type": True,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"基线交付数据重新生成失败：{exc}") from exc
    finally:
        if stage_root.exists() or stage_root.is_symlink():
            _remove_delivery_path(stage_root)


@app.post("/api/projects/{project_id}/baseline", status_code=201)
def create_project_baseline(project_id: str, response: Response, request: BaselineCreateRequest | None = None) -> ProjectSpec:
    baseline_started = time.perf_counter()
    baseline_phase = baseline_started
    # The source kernel stays pinned while both project and UI snapshots are copied.
    identity = active_identity()
    with core.acquire(project_id) as source_instance:
        source = source_instance.project()
        if source.lifecycle.status != "checked_in":
            raise HTTPException(status_code=409, detail="只有签入状态的项目可以打基线")
        if not source.category.strip() or source.category == "None":
            raise HTTPException(status_code=409, detail="项目必须先归入一个分类才能打基线")
        # Normalize legacy sidecars *before* taking the immutable baseline copy;
        # otherwise the new baseline inherits old CSVs in its 时序库 forever.
        try:
            _migrate_legacy_time_series_tables(source)
            _current_delivery_outputs(source)
        except (OSError, ValueError, UnicodeError) as exc:
            raise HTTPException(status_code=409, detail=f"打基线前整理时序与表格归档失败：{exc}") from exc
        source_state = source_instance.export_json()
        source_ui = source_state.get("ui", {})
        delivery_refresh = _refresh_baseline_delivery_outputs(source, source_state, gantt_saved_at=request.gantt_saved_at if request else None)
        refresh_elapsed = time.perf_counter() - baseline_phase
        baseline_phase = time.perf_counter()
        baseline = ProjectSpec.model_validate(copy.deepcopy(source.model_dump()))
        baseline.id = new_id("project")
        clear_environment_local_project_metadata(baseline)
        index, baseline_name = store.next_baseline_identity(source.id, source.name, request.name if request else "")
        # V2.9.2: baseline names are per-source sequential snapshots and do not
        # embed the date. The timestamp remains authoritative in lifecycle/metadata.
        baseline.name = baseline_name
        baseline.metadata["archive_base_name"] = source.name
        baseline.metadata["baseline_version_label"] = baseline_name
        baseline.lifecycle.status = "baseline"
        baseline.lifecycle.checked_out_by = ""
        baseline.lifecycle.lease_id = ""
        baseline.lifecycle.checked_out_session = ""
        baseline.lifecycle.source_project_id = source.id
        baseline.lifecycle.baseline_created_at = datetime.now(timezone.utc).isoformat()
        baseline.lifecycle.checked_out_at = ""
        source_asset_uploaded_by = ""
        if str(source.mesh_root or "").startswith("@model_assets/"):
            try:
                source_asset_uploaded_by = str(store._read_model_asset_metadata(_mesh_root_path(source.id, source)).get("uploaded_by", "") or "")
            except (OSError, ValueError):
                source_asset_uploaded_by = ""
        baseline.metadata.update({
            "version_index": index,
            "baseline_source_project_id": source.id,
            "baseline_created_at": baseline.lifecycle.baseline_created_at,
            # Private project-owned frozen trees; independent from later public-library/delivery-root changes.
            "baseline_delivery_directory": "delivery",
            "baseline_model_asset_directory": "assets/baseline_mesh_snapshot",
            "baseline_model_asset_source_reference": str(source.mesh_root or ""),
            "baseline_model_asset_uploaded_by": source_asset_uploaded_by,
            "baseline_delivery_refresh": delivery_refresh,
            "baseline_log": str(request.log if request else "").strip()[:2000],
        })
        baseline.metadata.pop("version_date", None)
        _apply_archive_name(baseline)
        created = store.create(baseline)
        # V2.5.6.11 baseline freeze: ordinary models reference a model-type public
        # asset folder, while a baseline must own an immutable private snapshot.
        source_dir = store.project_directory(source.id)
        baseline_dir = store.project_directory(created.id)
        for relative in ("assets", "outputs", "results", "core/artifacts"):
            src = source_dir / relative
            dst = baseline_dir / relative
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
        selected_mesh_root = _mesh_root_path(source.id, source)
        frozen_mesh_root = baseline_dir / "assets" / "baseline_mesh_snapshot"
        if selected_mesh_root.is_dir():
            shutil.copytree(selected_mesh_root, frozen_mesh_root, dirs_exist_ok=True, copy_function=shutil.copy2)
        created.mesh_root = store.relative_mesh_root(created.id, frozen_mesh_root)
        # Delivery is a first-class model asset. Freeze the complete recursive tree.
        source_delivery = store.delivery_directory(source, create=True)
        baseline_delivery = store.delivery_directory(created, create=True)
        if source_delivery.is_dir():
            store.copy_delivery_tree(source_delivery, baseline_delivery)
        # V2.13.5: the Hub 时序库 is a first-class model sidecar. A baseline must
        # freeze it together with model JSON/assets/delivery or the baseline cannot
        # reproduce the published schedule library later.
        source_time_series = store.time_series_directory(source, create=True)
        baseline_time_series = store.time_series_directory(created, create=True)
        if source_time_series.is_dir():
            shutil.copytree(source_time_series, baseline_time_series, dirs_exist_ok=True, copy_function=shutil.copy2)
        # Freeze the exact selected assets as an auditable baseline manifest.
        asset_copy_elapsed = time.perf_counter() - baseline_phase
        baseline_phase = time.perf_counter()
        frozen_assets = []
        for layer in created.layers:
            for mesh in layer.meshes:
                frozen_assets.append({"layer_id": layer.id, "mesh_id": mesh.id, "filename": mesh.filename})
        created.metadata["baseline_frozen_assets"] = frozen_assets
        created.metadata["baseline_delivery_directory"] = "delivery"
        created.metadata["baseline_delivery_frozen"] = True
        store.save(created)

        # V2.6.1 freezes the already-refreshed source delivery folder as-is.
        # Animation HTML is never auto-generated by baseline creation.
        frozen_manifest = _read_delivery_manifest(created)
        frozen_manifest["fingerprint"] = _delivery_data_fingerprint(created)
        _write_delivery_manifest(created, frozen_manifest)
        # V2.9.5: baseline creation must not shrink the source model's archive history.
        # Manual and lifecycle archives share the same MAX_ARCHIVE_VERSIONS hard cap.
        core.drop(created.id)
        _apply_imported_ui(created.id, source_ui)
        created_project = core.get(created.id).project()

        # V2.9.6: a baseline is also visible in the source model's unified
        # version history. This is a history marker/snapshot only: it does not
        # mutate the source ProjectSpec and does not create an ordinary archive
        # in addition to the baseline entry.
        store.archive(
            source_instance.project(),
            reason="baseline",
            locked=True,
            actor=identity.username,
            log=str(request.log if request else "").strip(),
            baseline_project_id=created_project.id,
            baseline_name=created_project.name,
        )
        # Prewarm the *frozen* model's display-only L3 badge once, at creation.
        # No authoritative ProjectSpec/asset/delivery content is modified.
        # A failed cache write must not report a committed baseline as failed.
        badge_started = time.perf_counter()
        try:
            _hub_catalog_critical({
                "id": created_project.id,
                "lifecycle_status": "baseline",
                "baseline_created_at": created_project.lifecycle.baseline_created_at,
            }, quick_only=False)
            LOGGER.info("hub_baseline_badge_prewarm_seconds project=%s seconds=%.3f",
                        created_project.id, time.perf_counter() - badge_started)
        except Exception:
            LOGGER.exception("Baseline %s saved but Hub badge prewarm failed", created_project.id)
        LOGGER.info(
            "baseline_phase_seconds source=%s result_delivery=%.3f frozen_assets_and_copy=%.3f "
            "baseline_persistence=%.3f total=%.3f",
            project_id, refresh_elapsed, asset_copy_elapsed,
            time.perf_counter() - baseline_phase, time.perf_counter() - baseline_started,
        )
        return created_project


def _fork_project_impl(
    project_id: str, request: ProjectCloneRequest | None, *,
    identity: Identity, progress: Callable[[float, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ProjectSpec:
    """One authoritative copy implementation for legacy sync and new background mode.

    Never expose an unfinished working model in Hub.  An L3 marker hides it
    from the catalog until the full asset tree has been verified.  A failure or
    cancellation rolls back both the model and newly published public mesh tree.
    """
    update = progress or (lambda _fraction, _message: None)
    cancelled = should_cancel or (lambda: False)
    started_at = time.perf_counter()
    source_instance = core.get(project_id)
    source = source_instance.project()
    require_project_access(source, write=False)
    if identity.role == "guest":
        raise HTTPException(status_code=403, detail="游客不能使用基线创建可编辑模型")
    if cancelled():
        raise InterruptedError("使用基线已取消")
    update(0.05, "正在校验基线与新版本标识")
    working = ProjectSpec.model_validate(copy.deepcopy(source.model_dump()))
    working.id = new_id("project")
    clear_environment_local_project_metadata(working)
    date_code = str(source.metadata.get("version_date") or "") or None
    date_code, index, managed_name = store.next_version_identity(source.category, date_code)
    working.name = managed_name
    working.metadata["archive_base_name"] = managed_name
    working.lifecycle.status = "checked_out"
    working.lifecycle.source_project_id = source.id
    working.lifecycle.baseline_created_at = ""
    working.lifecycle.checked_out_at = datetime.now(timezone.utc).isoformat()
    working.lifecycle.checked_out_by = identity.username
    working.lifecycle.lease_id = identity.lease_id
    working.lifecycle.checked_out_session = ""
    working.lifecycle.checked_in_at = ""
    for key in ("baseline_delivery_directory", "baseline_delivery_frozen", "baseline_frozen_assets",
                "baseline_model_asset_directory", "baseline_model_asset_source_reference", "baseline_model_asset_uploaded_by", "baseline_delivery_refresh",
                "baseline_source_project_id", "baseline_created_at", "baseline_version_label"):
        working.metadata.pop(key, None)
    working.metadata.update({
        "forked_from_project_id": source.id, "version_date": date_code, "version_index": index,
    })
    _apply_archive_name(working)
    published_mesh_root: Path | None = None
    created: ProjectSpec | None = None
    marker = store._desired_directory(working.id, working.category) / ".baseline_fork_pending"
    stage = "mesh"
    try:
        mesh_strategy = str(request.mesh_asset_strategy if request else "copy_frozen")
        if mesh_strategy == "bind_existing":
            update(0.12, "正在验证现有数模资产文件及模型引用")
            reference = _existing_fork_mesh_asset_reference(
                source, request.mesh_asset_reference if request else "",
            )
            update(0.38, "现有数模资产校验通过；不复制冻结数模")
        elif mesh_strategy == "copy_frozen":
            update(0.12, "正在复制冻结数模到新的公共资产文件夹")
            reference, published_mesh_root = _clone_mesh_to_shared_pool(
                source, (request.mesh_folder_name if request else ""), should_cancel=cancelled,
            )
            update(0.38, "冻结数模复制完成，正在准备独立的工作模型")
        else:
            raise HTTPException(status_code=422, detail="未知的数模资产使用方式")
        if cancelled():
            raise InterruptedError("使用基线已取消")
        stage = "model"
        marker.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(marker, "pending", sync_directory=False)
        working.mesh_root = reference
        created = store.create(working)
        if cancelled():
            raise InterruptedError("使用基线已取消")
        stage = "payload"
        update(0.48, "正在复制交付、历史结果和表格资产")
        _copy_model_payload(source, created, should_cancel=cancelled)
        if cancelled():
            raise InterruptedError("使用基线已取消")
        stage = "session"
        update(0.90, "文件完整性校验完成，正在建立独立编辑状态")
        core.drop(created.id)
        _apply_imported_ui(created.id, source_instance.export_json().get("ui", {}))
        if cancelled():
            raise InterruptedError("使用基线已取消")
        result = core.get(created.id).project()
        if not identity.single_user:
            # A delayed background job must not publish a checked-out model
            # under a logged-out / revoked lease.  activate_lease rejects a
            # missing or expired Session without extending a new login.
            updated_identity = auth.sessions.activate_lease(identity.session_id)
            if updated_identity.lease_id != identity.lease_id or updated_identity.username.casefold() != identity.username.casefold():
                raise HTTPException(status_code=409, detail="基线复制期间身份租约发生变化")
        if cancelled():
            raise InterruptedError("使用基线已取消")
        # Keep the copy hidden until lifecycle scheduling is also complete.
        _schedule_idle_check_in(created.id, identity)
        marker.unlink(missing_ok=True)
        store.invalidate()
        update(0.99, "模型副本已完成，正在刷新 Hub")
        LOGGER.info("baseline_fork_completed source=%s destination=%s seconds=%.3f", project_id, result.id, time.perf_counter() - started_at)
        return result
    except Exception as exc:
        LOGGER.warning("baseline_fork_failed source=%s phase=%s elapsed=%.3f error=%s", project_id, stage, time.perf_counter() - started_at, exc)
        if created is not None:
            core.drop(created.id)
            try:
                store.delete(created.id)
            except Exception:
                LOGGER.exception("failed to roll back forked project %s", created.id)
        # No model JSON was ever written in failures before store.create.
        try:
            marker.unlink(missing_ok=True)
            if created is None and marker.parent.is_dir() and not (marker.parent / "project.json").exists():
                shutil.rmtree(marker.parent)
        except OSError:
            LOGGER.exception("unable to remove fork marker for %s", working.id)
        if published_mesh_root is not None and published_mesh_root.is_dir():
            shutil.rmtree(published_mesh_root, ignore_errors=True)
        store.invalidate()
        if cancelled():
            raise InterruptedError("使用基线已取消；未保留不完整的模型文件") from exc
        raise


_baseline_fork_submission_gate = threading.RLock()


@app.post("/api/projects/{project_id}/fork", status_code=201, response_model=None)
def fork_project(
    project_id: str, request: ProjectCloneRequest | None = None,
    background: bool = Query(default=False),
) -> ProjectSpec | Response:
    """Use a baseline to create an editable copy.

    ``?background=true`` uses the *existing* JobManager heavy lane and responds
    202/job_id promptly; POST without the flag retains the legacy ProjectSpec
    response contract for existing API clients.
    """
    identity = active_identity()
    source = core.get(project_id).project()
    require_project_access(source, write=False)
    if identity.role == "guest":
        raise HTTPException(status_code=403, detail="游客不能使用基线创建可编辑模型")
    if background:
        strategy = str(request.mesh_asset_strategy if request else "copy_frozen")
        folder = str(request.mesh_folder_name if request else "").strip()
        reference = str(request.mesh_asset_reference if request else "").strip()
        if strategy == "bind_existing" and not reference:
            raise HTTPException(status_code=422, detail="请先选择现有数模资产文件夹")
        stable_key = json.dumps([strategy, reference if strategy == "bind_existing" else folder], ensure_ascii=False)
        stable_kind = "baseline_fork:" + hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:16]
        def task(progress, cancelled, _workspace, _job_id):
            token = set_active_identity(identity)
            try:
                result = _fork_project_impl(
                    project_id, request, identity=identity, progress=progress, should_cancel=cancelled,
                )
                return {"project_id": result.id, "name": result.name, "category": result.category}
            finally:
                reset_active_identity(token)
        # An atomic gate avoids 8 simultaneous POSTs racing between the
        # existing JobManager scan and submit; never hold it during copying.
        with _baseline_fork_submission_gate:
            job_id = _submit_project_job(project_id, stable_kind, task, timeout_seconds=1800)
        return JSONResponse(status_code=202, content={"job_id": job_id, "status": "queued"})
    return _fork_project_impl(project_id, request, identity=identity)


@app.post("/api/projects/{project_id}/copy-version", status_code=201)
def copy_checked_in_project_version(project_id: str, request: ProjectCloneRequest | None = None) -> ProjectSpec:
    """Copy current checked-in state, or cut one archived snapshot out as an independent model."""
    identity = active_identity()
    if identity.role == "guest":
        raise HTTPException(status_code=403, detail="游客不能复制模型版本")
    requested_version_id = str(request.version_id if request else "").strip()
    with core.acquire(project_id) as source_instance:
        source = source_instance.project()
        require_project_access(source, write=False)
        historical = bool(requested_version_id)
        source_ui = source_instance.export_json().get("ui", {})
        if historical:
            try:
                snapshot = store.get_version(project_id, requested_version_id)
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=404, detail="Project version not found") from exc
            # Resolve the historical public mesh reference before normalizing its category.
            # If reclassification moved the shared folder, retry the same folder name
            # under the current model type so old archives stay portable.
            try:
                _mesh_root_path(project_id, snapshot)
            except HTTPException:
                raw_ref = str(snapshot.mesh_root or "")
                if not raw_ref.startswith("@model_assets/"):
                    raise
                folder_name = raw_ref.replace("\\", "/").split("/")[-1]
                snapshot.mesh_root = store.model_asset_reference(source.category, folder_name)
                _mesh_root_path(project_id, snapshot)
            snapshot.id = source.id
            snapshot.category = source.category
            copy_source = snapshot
        else:
            if source.lifecycle.status != "checked_in":
                raise HTTPException(status_code=409, detail="只有签入状态的模型可以复制当前版本")
            copy_source = source

        copied = ProjectSpec.model_validate(copy.deepcopy(copy_source.model_dump()))
        copied.id = new_id("project")
        clear_environment_local_project_metadata(copied)
        copied.category = source.category
        existing_names = {str(item.get("name", "")).casefold() for item in store.list() if item.get("category") == source.category}
        requested_name = str(request.model_name if request else "").strip()
        if requested_name:
            if requested_name.casefold() in existing_names:
                raise HTTPException(status_code=409, detail="当前模型类型中已存在同名模型，请修改复制模型名称")
            copied.name = requested_name
        else:
            base_name = f"{source.name}_{'存档切出' if historical else '副本'}"
            copied.name = base_name
            suffix = 2
            while copied.name.casefold() in existing_names:
                copied.name = f"{base_name}_{suffix}"
                suffix += 1
        copied.lifecycle.status = "checked_in"
        copied.lifecycle.checked_out_by = ""
        copied.lifecycle.lease_id = ""
        copied.lifecycle.checked_out_session = ""
        copied.lifecycle.checked_out_at = ""
        copied.lifecycle.checked_in_at = datetime.now(timezone.utc).isoformat()
        copied.lifecycle.baseline_created_at = ""
        copied.lifecycle.source_project_id = source.id
        for key in ("version_date", "version_index", "baseline_source_project_id", "baseline_created_at",
                    "baseline_delivery_directory", "baseline_delivery_frozen", "baseline_frozen_assets",
                    "baseline_model_asset_directory", "baseline_model_asset_source_reference", "baseline_model_asset_uploaded_by",
                    "baseline_delivery_refresh", "baseline_version_label"):
            copied.metadata.pop(key, None)
        copied.metadata.update({"archive_base_name": copied.name, "copied_from_project_id": source.id})
        if historical:
            copied.metadata["copied_from_version_id"] = requested_version_id
        _apply_archive_name(copied)
        # V2.9.5.1 copy semantics: a copied model keeps the source model's existing
        # public @model_assets reference.  Only baseline /fork creates a newly named
        # public mesh folder via the existing `_clone_mesh_to_shared_pool` helper.
        copied.mesh_root = str(copy_source.mesh_root or "")
        created: ProjectSpec | None = None
        try:
            created = store.create(copied)
            # Historical archives version ProjectSpec, not result/delivery payloads.
            # Do not mislabel the source model's current outputs as historical data.
            if not historical:
                _copy_model_payload(source, created)
            core.drop(created.id)
            _apply_imported_ui(created.id, source_ui)
            return core.get(created.id).project()
        except Exception:
            if created is not None:
                core.drop(created.id)
                try:
                    store.delete(created.id)
                except Exception:
                    LOGGER.exception("failed to roll back copied project %s", created.id)
            raise

@app.get("/api/recycle-bin")
def list_recycle_bin() -> list[dict[str, Any]]:
    identity = active_identity()
    if identity.role not in {"engineer", "admin"}:
        raise HTTPException(status_code=403, detail="只有管理员和工程师可以查看回收站")
    return store.list_trash()


@app.post("/api/recycle-bin/{trash_id}/restore")
def restore_recycle_bin_project(trash_id: str) -> ProjectSpec:
    identity = active_identity()
    if identity.role not in {"engineer", "admin"}:
        raise HTTPException(status_code=403, detail="只有管理员和工程师可以恢复回收站模型")
    try:
        restored = store.restore_trash(trash_id)
        core.drop(restored.id)
        return core.get(restored.id).project()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="回收站模型不存在或已超过保留期限") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/recycle-bin/{trash_id}", status_code=204)
def permanently_delete_recycle_bin_project(trash_id: str) -> Response:
    identity = active_identity()
    if identity.role not in {"engineer", "admin"}:
        raise HTTPException(status_code=403, detail="只有管理员和工程师可以永久删除回收站模型")
    try:
        store.delete_trash(trash_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="回收站模型不存在或已超过保留期限") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=204)


@app.post("/api/internal/vz/model-removed")
def internal_vz_model_removed(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    project_id = str(payload.get("project_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    if not project_id or not model_id:
        raise HTTPException(status_code=422, detail="project_id 和 model_id 不能为空")
    try:
        return _vz_disable_push_from_removed_model(project_id, model_id, reason="vz_engineer_remove")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Hub 源模型不存在") from exc


@app.get("/api/vz-push-status")
def list_vz_push_status() -> dict[str, Any]:
    # 轻量状态轮询同时做一次 VZ 目录对账：即使集成 VZ 是旧进程、
    # 本地 bridge token 不可用，工程师侧移除也会在下一次 2s 轮询时
    # 将 Hub 的 stale “已推送”状态修正为关闭。VZ 不可达时保持最后
    # 已知状态，禁止因瞬时网络错误误关用户的发布开关。
    projects = _vz_reconcile_push_catalog(store.list())
    return {
        "projects": [
            {"id": str(item.get("id") or ""), "vz_push": copy.deepcopy(item.get("vz_push") or {"enabled": False})}
            for item in projects
        ]
    }


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: str) -> Response:
    identity = active_identity()
    if identity.role not in {"engineer", "admin"}:
        raise HTTPException(status_code=403, detail="只有管理员和工程师可以删除模型")
    try:
        project = get_project(project_id)
        require_project_access(project, write=False)
        if _vz_status_for_project(project).get("enabled"):
            try:
                _vz_set_published(project, False)
            except VZIntegrationError as exc:
                LOGGER.warning("Unable to unpublish VZ model before Hub deletion %s: %s", project_id, exc)
        core.drop(project_id)
        store.trash_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=204)


@app.put("/api/projects/{project_id}/vz-push")
def set_project_vz_push(project_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    identity = active_identity()
    if identity.role not in {"engineer", "admin"}:
        raise HTTPException(status_code=403, detail="只有管理员和工程师可以推送模型")
    try:
        project = get_project(project_id)
        require_project_access(project, write=False)
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("enabled 必须是布尔值")
        return {"vz_push": _vz_set_published(project, enabled), "engineer_url": "/engineer", "client_url": "/client", "port": VZ_INTERNAL_PORT}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except VZIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (ValueError, TypeError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/projects/{project_id}")
def update_project(project_id: str, project: ProjectSpec) -> ProjectSpec:
    if project.id != project_id:
        raise HTTPException(status_code=409, detail="Project id in URL and payload must match")
    with core.acquire(project_id) as instance:
        current = instance.project()
        identity = require_project_access(current, write=True)

        # V2.11.7: baseline content remains frozen.  Reuse the existing project.replace
        # command/event seam, but project only the editable display name from the payload.
        # This prevents the Hub name editor from becoming a back door for layer/drive/UI
        # changes on a frozen baseline.
        if current.lifecycle.status == "baseline":
            requested_name = str(project.name or "").strip()
            try:
                final_name = store.unique_project_name(
                    current.category, requested_name, exclude_project_id=current.id,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            if final_name == current.name:
                return current
            renamed = ProjectSpec.model_validate(copy.deepcopy(current.model_dump()))
            renamed.name = final_name
            renamed.metadata["baseline_version_label"] = final_name
            result = instance.bus.dispatch({
                "tool_id": "project.replace", "params": {
                    "project": renamed.model_dump(),
                    "intent": "编辑冻结基线模型名称",
                },
                "actor": identity.username, "client": "human_ui",
            })
            if not result.ok:
                raise HTTPException(status_code=422, detail=result.errors)
            updated = instance.project()
            store.rename_baseline_history_reference(
                str(updated.lifecycle.source_project_id or ""), updated.id, updated.name,
            )
            return updated

        if project.category != current.category:
            raise HTTPException(status_code=409, detail="模型类型只能通过总览拖拽移动，以保证磁盘目录与状态一致")
        project.lifecycle = copy.deepcopy(current.lifecycle)
        project.mesh_root = current.mesh_root
        # Canonicalize imported/edited legacy CSV references BEFORE the
        # project.replace command captures its authoritative state mirror.
        store.hydrate_legacy_csv_sources(project, project_dir=store.project_directory(project_id))
        previous_delivery = store.delivery_directory(current)
        cascade_renamed_references(current, project)
        repair_joint_references(project)
        _apply_archive_name(project)
        next_delivery = store.delivery_directory(project)
        if previous_delivery != next_delivery and previous_delivery.is_dir():
            next_delivery.parent.mkdir(parents=True, exist_ok=True)
            store.move_delivery_tree(previous_delivery, next_delivery)
        if current.model_dump() == project.model_dump():
            return current
        result = instance.bus.dispatch({
            "tool_id": "project.replace", "params": {"project": project.model_dump()},
            "actor": identity.username, "client": "human_ui",
        })
        if not result.ok:
            raise HTTPException(status_code=422, detail=result.errors)
        return instance.project()


@app.patch("/api/projects/{project_id}/hub-properties")
def update_hub_project_properties(project_id: str, request: HubProjectPropertiesRequest) -> dict[str, Any]:
    """Update the small Hub-editable projection without a full project GET/PUT round trip."""
    if request.name is None and request.archive_order is None:
        raise HTTPException(status_code=422, detail="至少需要提交模型名称或关键数据顺序")
    with core.acquire(project_id) as instance:
        current = instance.project()
        identity = require_project_access(current, write=True)

        # Baseline remains frozen except for its display name, exactly matching
        # the long-standing full-project PUT contract.
        if current.lifecycle.status == "baseline":
            if request.archive_order is not None:
                raise HTTPException(status_code=409, detail="冻结基线不允许修改关键数据顺序")
            requested_name = str(request.name or "").strip()
            if not requested_name:
                raise HTTPException(status_code=422, detail="模型名称不能为空")
            try:
                final_name = store.unique_project_name(
                    current.category, requested_name, exclude_project_id=current.id,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            if final_name != current.name:
                renamed = ProjectSpec.model_validate(copy.deepcopy(current.model_dump()))
                renamed.name = final_name
                renamed.metadata["baseline_version_label"] = final_name
                result = instance.bus.dispatch({
                    "tool_id": "project.replace", "params": {
                        "project": renamed.model_dump(),
                        "intent": "Hub 快速编辑冻结基线模型名称",
                    },
                    "actor": identity.username, "client": "human_ui",
                })
                if not result.ok:
                    raise HTTPException(status_code=422, detail=result.errors)
                updated = instance.project()
                store.rename_baseline_history_reference(
                    str(updated.lifecycle.source_project_id or ""), updated.id, updated.name,
                )
            else:
                updated = current
            return {
                "id": updated.id, "name": updated.name,
                "archive_order": list(updated.archive_order),
                "updated_at": str(updated.metadata.get("updated_at", "")),
                "lifecycle_status": updated.lifecycle.status,
                "lifecycle": updated.lifecycle.model_dump(),
            }

        working = ProjectSpec.model_validate(copy.deepcopy(current.model_dump()))
        if request.name is not None:
            requested_name = str(request.name).strip()
            if not requested_name:
                raise HTTPException(status_code=422, detail="模型名称不能为空")
            if requested_name != working.name:
                working.name = requested_name
                working.metadata["archive_base_name"] = requested_name

        archive_preview: dict[str, Any] | None = None
        if request.archive_order is not None:
            if current.lifecycle.status != "checked_out":
                raise HTTPException(status_code=409, detail="只有签出模型可以调整关键数据顺序")
            normalized_order: list[str] = []
            seen: set[str] = set()
            for raw in request.archive_order:
                key = str(raw or "").strip()
                if key and key not in seen:
                    normalized_order.append(key)
                    seen.add(key)
            working.archive_order = normalized_order
            archive_preview = _project_preview(working, include_latest_result=False)
            working.archive_order = list(archive_preview.get("archive_order", normalized_order))

        if working.model_dump() == current.model_dump():
            updated = current
        else:
            previous_delivery = store.delivery_directory(current)
            _apply_archive_name(working, preview=archive_preview)
            next_delivery = store.delivery_directory(working)
            if previous_delivery != next_delivery and previous_delivery.is_dir():
                next_delivery.parent.mkdir(parents=True, exist_ok=True)
                store.move_delivery_tree(previous_delivery, next_delivery)
            result = instance.bus.dispatch({
                "tool_id": "project.replace", "params": {
                    "project": working.model_dump(),
                    "intent": "Hub 轻量属性编辑",
                },
                "actor": identity.username, "client": "human_ui",
            })
            if not result.ok:
                raise HTTPException(status_code=422, detail=result.errors)
            updated = instance.project()

        return {
            "id": updated.id, "name": updated.name,
            "archive_order": list(updated.archive_order),
            "updated_at": str(updated.metadata.get("updated_at", "")),
            "delivery_name_suffix": str(updated.metadata.get("delivery_name_suffix", "")),
            "lifecycle_status": updated.lifecycle.status,
            "lifecycle": updated.lifecycle.model_dump(),
        }


def _version_comparison_text(project: ProjectSpec) -> tuple[str, list[ProjectSpec]]:
    prior: list[ProjectSpec] = []
    for item in store.list():
        if item["id"] != project.id and item.get("category") == project.category:
            try: prior.append(store.get(str(item["id"])))
            except (KeyError, ValueError): pass
        if len(prior) == 3: break
    def rows(value: ProjectSpec) -> list[str]:
        result = []
        try:
            _, schedule = resolve_schedule(value)
            for seg in schedule:
                result.append(f"{seg.drive_name}/{seg.name}: 起始{seg.start:.4g}s, 结束{seg.end:.4g}s, 时长{seg.duration:.4g}s, 行程{seg.travel:.4g}")
        except (ValueError, TypeError) as exc:
            result.append(f"运动解算失败: {exc}")
        return result
    body = [f"当前版本 {project.name}", *rows(project)]
    for index, item in enumerate(prior, 1): body.extend([f"对比版本{index} {item.name}", *rows(item)])
    return "\n".join(body), prior


@app.post("/api/projects/{project_id}/version-summary")
def summarize_project_version(project_id: str, request: VersionSummaryRequest) -> dict[str, Any]:
    project = get_project(project_id)
    _require_editable(project)
    comparison, prior = _version_comparison_text(project)
    fallback = f"已对比之前 {len(prior)} 个版本。" + (f" 用户反馈：{request.feedback.strip()}。" if request.feedback.strip() else "")
    summary = fallback
    if llm_credentials.api_key():
        try:
            summary = chat_completion(project.agent_settings, llm_credentials.api_key(), [
                {"role":"system", "content":"你是机构运动版本审阅助手。精炼总结每个电机运动段的起止时间、时长、行程变化，指出风险和下一步；只输出中文归档正文。"},
                {"role":"user", "content": comparison + (f"\n用户反馈：{request.feedback}" if request.feedback else "")},
            ], timeout=25.0)
        except ValueError as exc:
            summary = f"{fallback} LLM 暂不可用：{exc}"
    else:
        current_lines = comparison.splitlines()[1:]
        summary = fallback + ("\n" + "\n".join(current_lines[:8]) if current_lines else "")
    project.metadata["version_summary"] = summary
    project.metadata["version_summary_archived"] = bool(request.archive)
    feedback = list(project.metadata.get("version_summary_feedback", []))
    if request.feedback.strip(): feedback.append(request.feedback.strip())
    project.metadata["version_summary_feedback"] = feedback[-20:]
    updated = update_project(project_id, project)
    return {"summary": updated.metadata.get("version_summary", ""), "archived": updated.metadata.get("version_summary_archived", False), "compared_project_ids": [item.id for item in prior]}


@app.post("/api/projects/{project_id}/reclassify")
def reclassify_project(project_id: str, request: ReclassifyProjectRequest) -> ProjectSpec:
    try:
        category = store.normalize_category(request.category)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not category:
        raise HTTPException(status_code=422, detail="项目类型不能为空")
    with core.acquire(project_id) as instance:
        if instance.project().lifecycle.status == "baseline":
            raise HTTPException(status_code=409, detail="基线项目不可重新分类")
        try:
            store.project_move_target(project_id, category)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=f"模型目录无法移动：{exc}") from exc
        previous_delivery = store.delivery_directory(instance.project())
        current = instance.project()
        managed_name = store.reclassified_project_name(current.name, current.category, category)
        identity = active_identity()
        result = instance.bus.dispatch({
            "tool_id": "project.reclassify",
            "params": {
                "category": category, "name": managed_name,
            },
            "actor": identity.username, "client": "human_ui",
        })
        if not result.ok:
            raise HTTPException(status_code=409, detail=result.errors)
        renamed = ProjectSpec.model_validate(instance.project().model_dump())
        renamed.metadata["archive_base_name"] = managed_name
        _apply_archive_name(renamed)
        replace = instance.bus.dispatch({
            "tool_id": "project.replace", "params": {"project": renamed.model_dump()},
            "actor": identity.username, "client": "human_ui",
        })
        if not replace.ok:
            raise HTTPException(status_code=409, detail=replace.errors)
        next_delivery = store.delivery_directory(instance.project())
        if previous_delivery != next_delivery and previous_delivery.is_dir():
            next_delivery.parent.mkdir(parents=True, exist_ok=True)
            store.move_delivery_tree(previous_delivery, next_delivery)
        try:
            store.move_project(project_id, category)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=f"模型目录移动失败：{exc}") from exc
        core.drop(project_id)
    return core.get(project_id).project()


# V2.16.10: table import and export reuse the existing mapping/external CSV
# parsers and project.replace. The sidecar is project-owned and never a runtime
# dependency; ProjectSpec.points remains the source of truth.
_MODEL_TABLE_ASSET_LOCK = threading.RLock()


def _segment_for_table(project: ProjectSpec, drive_id: str, segment_id: str):
    drive = next((item for item in project.drives if item.id == drive_id), None)
    segment = next((item for item in (drive.segments if drive else ()) if item.id == segment_id), None)
    if drive is None or segment is None:
        raise HTTPException(status_code=404, detail="驱动或运动段不存在")
    return drive, segment


def _save_imported_table_and_project(
    project: ProjectSpec, drive_id: str, segment_id: str, kind: str, content: bytes,
) -> ProjectSpec:
    """Write the backup first; roll it back if authoritative model import fails."""
    identity = store.segment_table_identity(drive_id, segment_id)
    target = store.table_asset_path(project.id, kind, identity, create=True)
    previous = target.read_bytes() if target.is_file() else None
    store.put_table_asset(project.id, kind, identity, content)
    try:
        return update_project(project.id, project)
    except BaseException:
        # Failed project persistence must not leave a false new backup. This
        # compensates the sidecar write, without touching any old project archive.
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            store.put_table_asset(project.id, kind, identity, previous)
        raise


def _csv_from_embedded_points(points: list[list[float]], *, header: tuple[str, str]) -> str:
    """Lossless IEEE-754 CSV serialization; preserve every mapping knot/order."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(header)
    valid_rows = 0
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise HTTPException(status_code=422, detail="运动段点表包含无效行")
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="运动段点表不是数值") from exc
        if not math.isfinite(x) or not math.isfinite(y):
            raise HTTPException(status_code=422, detail="运动段点表包含 NaN 或无穷值")
        writer.writerow([format(x, ".17g"), format(y, ".17g")])
        valid_rows += 1
    if valid_rows < 2:
        raise HTTPException(status_code=422, detail="运动段缺少有效的 CSV 数值点表")
    return "\ufeff" + stream.getvalue()


def _export_embedded_table(project_id: str, drive_id: str, segment_id: str, kind: str) -> dict[str, Any]:
    with _MODEL_TABLE_ASSET_LOCK:
        project = get_project(project_id)
        if active_identity().role == "guest":
            raise HTTPException(status_code=403, detail="访客不可导出模型私有表格资产")
        drive, segment = _segment_for_table(project, drive_id, segment_id)
        if segment.profile != ("mapping" if kind == "mapping" else "external_csv"):
            raise HTTPException(status_code=409, detail="运动段类型已改变，请刷新后重试")
        text = _csv_from_embedded_points(
            segment.points, header=("source", "target") if kind == "mapping" else ("time_s", "position"),
        )
        # read-only workspaces can download without bypassing frozen lifecycle
        # or writing into another user's checked-out project.
        editable = project.lifecycle.status == "checked_out" and not core.is_ephemeral(project_id)
        if editable:
            _require_editable(project)
            identity = store.segment_table_identity(drive_id, segment_id)
            store.put_table_asset(project_id, kind, identity, text.encode("utf-8"))
        safe_stem = safe_csv_stem(f"{drive.name}--{segment.name}", "运动段")
        suffix = "映射表格.csv" if kind == "mapping" else "外部运动位置表格.csv"
        return {
            "filename": f"{safe_stem}--{suffix}", "content": text,
            "count": len(segment.points), "backed_up": editable,
            "asset_name": store.table_asset_filename(kind, store.segment_table_identity(drive_id, segment_id)),
        }


@app.post("/api/projects/{project_id}/mapping-csv")
async def upload_mapping_csv(
    project_id: str, drive_id: str = Form(...), segment_id: str = Form(...), file: UploadFile = File(...),
) -> dict[str, Any]:
    if not str(file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="请选择 CSV 文件")
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="映射 CSV 不能超过 20 MiB")
    try:
        points = parse_mapping_csv(content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"映射 CSV 无效：{exc}") from exc
    with _MODEL_TABLE_ASSET_LOCK:
        project = get_project(project_id)
        _require_editable(project)
        if core.is_ephemeral(project_id):
            raise HTTPException(status_code=409, detail="临时编辑不能把映射表备份到正式表格资产；请先签出模型")
        _drive, segment = _segment_for_table(project, drive_id, segment_id)
        segment.profile = "mapping"; segment.csv_path = ""; segment.points = points
        segment.external_csv_name = ""; segment.external_csv_header = ""; segment.external_csv_source_metric = ""
        segment.mapping_point_count = len(points); segment.mapping_csv_name = str(file.filename).replace("\\", "/").split("/")[-1]
        updated = _save_imported_table_and_project(project, drive_id, segment_id, "mapping", content)
    return {"project": updated.model_dump(), "count": len(points), "filename": file.filename, "backed_up": True}


@app.post("/api/projects/{project_id}/mapping-csv/export")
def export_mapping_csv(project_id: str, drive_id: str = Body(..., embed=True), segment_id: str = Body(..., embed=True)) -> dict[str, Any]:
    return _export_embedded_table(project_id, drive_id, segment_id, "mapping")


@app.post("/api/projects/{project_id}/external-motion-csv")
async def upload_external_motion_csv(
    project_id: str, drive_id: str = Form(...), segment_id: str = Form(...), file: UploadFile = File(...),
) -> dict[str, Any]:
    if not str(file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="请选择 CSV 文件")
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="外部运动 CSV 不能超过 20 MiB")
    try:
        parsed = parse_external_motion_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"外部运动 CSV 无效：{exc}") from exc
    with _MODEL_TABLE_ASSET_LOCK:
        project = get_project(project_id)
        _require_editable(project)
        if core.is_ephemeral(project_id):
            raise HTTPException(status_code=409, detail="临时编辑不能把外部运动表备份到正式表格资产；请先签出模型")
        _drive, segment = _segment_for_table(project, drive_id, segment_id)
        segment.profile = "external_csv"
        segment.mode = "duration"
        segment.points = [[time_s, value] for time_s, value in parsed.points]
        segment.csv_path = ""
        segment.external_csv_name = str(file.filename).replace("\\", "/").split("/")[-1]
        segment.external_csv_header = parsed.header
        segment.external_csv_source_metric = parsed.source_metric
        segment.duration = parsed.duration
        segment.travel = parsed.travel
        segment.speed = parsed.max_speed
        segment.mapping_source_joint_id = ""
        segment.mapping_csv_name = ""
        segment.mapping_point_count = 0
        updated = _save_imported_table_and_project(project, drive_id, segment_id, "external_motion", content)
    return {
        "project": updated.model_dump(), "count": len(parsed.points), "filename": file.filename,
        "header": parsed.header, "source_metric": parsed.source_metric,
        "duration": parsed.duration, "travel": parsed.travel, "max_speed": parsed.max_speed,
        "backed_up": True,
    }


@app.post("/api/projects/{project_id}/external-motion-csv/export")
def export_external_motion_csv(project_id: str, drive_id: str = Body(..., embed=True), segment_id: str = Body(..., embed=True)) -> dict[str, Any]:
    return _export_embedded_table(project_id, drive_id, segment_id, "external_motion")


@app.get("/api/projects/{project_id}/parameters")
def project_parameters(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    return {"project_id": project.id, "aliases": project.parameter_aliases, "parameters": parameter_catalog(project)}


@app.post("/api/projects/{project_id}/parameters/apply")
def apply_project_parameters(project_id: str, request: ParameterApplyRequest) -> dict[str, Any]:
    project = get_project(project_id)
    _require_editable(project)
    try:
        updated = apply_parameter_values(project, request.values, request.aliases)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with core.acquire(project_id) as instance:
        result = instance.bus.dispatch({
            "tool_id": "project.replace", "params": {"project": updated.model_dump(),
            "intent": "批量应用参数目录值"}, "actor": active_identity().username, "client": "script",
        })
        if not result.ok:
            raise HTTPException(status_code=422, detail=result.errors)
    return {"project": updated.model_dump(), "parameters": parameter_catalog(updated)}


@app.get("/api/projects/{project_id}/versions")
def project_versions(project_id: str, detail: str = "full") -> list[dict[str, Any]]:
    project = get_project(project_id)
    if project.lifecycle.status == "baseline":
        return []
    versions = store.list_versions(project_id)
    # V2.16.1: check-in's history sidebar only needs metadata sidecars. Avoid
    # running _project_preview() on every historical snapshot during this
    # navigation action; leave the old full response 100% backward-compatible.
    if detail == "metadata":
        return versions
    return [_version_display_entry(project_id, item) for item in versions]


@app.post("/api/projects/{project_id}/archive", status_code=201)
def archive_project_version(project_id: str, request: ArchiveVersionRequest | None = None) -> dict[str, Any]:
    instance = core.get(project_id)
    project = instance.project()
    if core.is_ephemeral(project_id):
        raise HTTPException(status_code=409, detail="签入/基线临时编辑会话不能创建版本存档")
    _require_editable(project)
    return _version_display_entry(project_id, store.archive(
        project, reason="archive", actor=active_identity().username, log=request.log if request else "",
        archive_name=request.archive_name if request else "",
        overwrite_version_id=request.overwrite_version_id if request else "",
    ))


@app.get("/api/projects/{project_id}/versions/{version_id}")
def project_version(project_id: str, version_id: str) -> ProjectSpec:
    get_project(project_id)
    try:
        return store.get_version(project_id, version_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Project version not found") from exc


@app.delete("/api/projects/{project_id}/versions/{version_id}")
def delete_project_version(project_id: str, version_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    require_project_access(project, write=True)
    if project.lifecycle.status == "baseline":
        raise HTTPException(status_code=409, detail="基线模型没有可删除的原模型存档链")
    try:
        existing = next(
            item for item in store.list_versions(project_id)
            if str(item.get("id", "")) == str(version_id)
        )
        display = _version_display_entry(project_id, existing)
        store.delete_version(project_id, version_id)
        return {"deleted": True, "version": display}
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Project version not found") from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Project version not found") from exc


@app.get("/api/projects/{project_id}/versions/{version_id}/preview")
def project_version_preview(project_id: str, version_id: str) -> dict[str, Any]:
    version = project_version(project_id, version_id)
    preview = _project_preview(version, include_latest_result=False)
    preview["version_id"] = version_id
    return preview


@app.post("/api/projects/{project_id}/versions/{version_id}/restore")
def restore_project_version(project_id: str, version_id: str) -> ProjectSpec:
    if core.is_ephemeral(project_id):
        raise HTTPException(status_code=409, detail="临时编辑会话不能执行版本回退")
    with core.acquire(project_id) as instance:
        current = instance.project()
        identity = require_project_access(current, write=True)
        if current.lifecycle.status != "checked_out":
            raise HTTPException(status_code=409, detail="只有签出状态可以执行版本回退")
        try:
            restored = store.get_version(project_id, version_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Project version not found") from exc
        store.archive(current, reason="rollback_before", actor=identity.username)
        restored.id = current.id
        restored.category = current.category
        restored.lifecycle = current.lifecycle
        result = instance.bus.dispatch({
            "tool_id": "project.replace", "params": {"project": restored.model_dump(), "intent": f"回退到版本 {version_id}"},
            "actor": identity.username, "client": "human_ui",
        })
        if not result.ok:
            raise HTTPException(status_code=422, detail=result.errors)
        return instance.project()


@app.get("/api/projects/{project_id}/preview")
def project_preview(project_id: str, include_latest_result: bool = True) -> dict[str, Any]:
    return _project_preview(get_project(project_id), include_latest_result=include_latest_result)


# V2.16.2: read-only, draft-aware *schedule* preview. Do not persist a model,
# generate XML, read the last trajectory or submit a MuJoCo Job. This gives
# local-first Gantt edits an exact projection without Enter/server draft sync.
# Bound concurrent CPU preview work, rather than letting many browsers saturate
# FastAPI worker threads and delay health checks or another user's Viewer.
_drive_preview_slots = threading.BoundedSemaphore(max(1, min(4, int(os.getenv("MUJOCO_STUDIO_GANTT_PREVIEW_SLOTS", "2")))))


@app.post("/api/projects/{project_id}/preview", status_code=200)
def preview_unsaved_drive_schedule(project_id: str, draft: ProjectSpec) -> dict[str, Any]:
    authoritative = get_project(project_id)
    _require_editable(authoritative)
    if draft.id != project_id:
        raise HTTPException(status_code=422, detail="甘特图草稿模型 ID 与当前模型不一致")
    if not _drive_preview_slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="甘特图预览负载较高，请稍后自动重试")
    try:
        # A client-supplied lifecycle/mesh root cannot confer permission or
        # redirect file reads. Preview uses the authorised server-owned scope.
        draft.lifecycle = authoritative.lifecycle.model_copy(deep=True)
        draft.mesh_root = authoritative.mesh_root
        draft.category = authoritative.category
        draft.template_scene = authoritative.template_scene
        projected = _project_preview(draft, include_latest_result=False)
        return {
            "id": project_id, "gantt": projected["gantt"],
            "variables": projected["variables"], "mapping_tables": projected["mapping_tables"],
            "schedule_error": projected["schedule_error"],
        }
    finally:
        _drive_preview_slots.release()


def _validate_scene_template(path: Path) -> ET.Element:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise HTTPException(status_code=422, detail=f"XML 场景无法解析：{exc}") from exc
    if root.tag != "mujoco":
        raise HTTPException(status_code=422, detail="XML 场景根节点必须是 <mujoco>")
    if root.findall(".//include"):
        raise HTTPException(status_code=422, detail="场景模板暂不接受 <include>；请上传单文件、自包含 XML")
    external = sorted({str(node.get("file")) for node in root.iter() if node.get("file")})
    if external:
        raise HTTPException(status_code=422, detail={
            "code": "scene_external_asset_not_supported",
            "message": "场景模板必须自包含；外部资产请继续通过 STL/OBJ 数模通道管理",
            "files": external,
        })
    return root


@app.get("/api/scenes")
def list_server_scenes() -> dict[str, Any]:
    _ensure_legacy_default_scene()
    rows = []
    for path in sorted(SCENE_LIBRARY_ROOT.glob("*.xml"), key=lambda item: item.name.casefold()):
        try:
            _validate_scene_template(path)
        except HTTPException:
            continue
        rows.append({"name": path.name, "size": path.stat().st_size, "updated_at": path.stat().st_mtime})
    return {"scenes": rows, "maximum_bytes": MAX_SCENE_XML_BYTES}


@app.post("/api/scenes/upload", status_code=201)
async def upload_server_scene(file: UploadFile = File(...)) -> dict[str, Any]:
    identity = active_identity()
    if identity.role == "guest":
        raise HTTPException(status_code=403, detail="游客不能上传服务端场景")
    filename = Path(file.filename or "scene.xml").name
    if Path(filename).suffix.casefold() != ".xml":
        raise HTTPException(status_code=422, detail="只允许上传 .xml 场景")
    data = await file.read(MAX_SCENE_XML_BYTES + 1)
    if len(data) > MAX_SCENE_XML_BYTES:
        raise HTTPException(status_code=413, detail="XML 场景超过 10 MiB 上限")
    SCENE_LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    target = SCENE_LIBRARY_ROOT / filename
    staged = SCENE_LIBRARY_ROOT / f".{filename}.{uuid4().hex}.staged"
    try:
        staged.write_bytes(data)
        _validate_scene_template(staged)
        atomic_replace(staged, target)
    finally:
        staged.unlink(missing_ok=True)
    return {"name": target.name, "size": target.stat().st_size}


@app.put("/api/projects/{project_id}/scene")
def select_project_scene(project_id: str, request: ProjectSceneRequest) -> ProjectSpec:
    current = get_project(project_id)
    _require_editable(current)
    selected = Path(request.scene).name if request.scene else ""
    if selected:
        target = (SCENE_LIBRARY_ROOT / selected).resolve()
        if SCENE_LIBRARY_ROOT.resolve() not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="服务端场景不存在")
        _validate_scene_template(target)
    updated = ProjectSpec.model_validate(copy.deepcopy(current.model_dump()))
    updated.template_scene = selected
    return update_project(project_id, updated)


@app.get("/api/project-comparison-skills")
def list_project_comparison_skills() -> list[dict[str, Any]]:
    return COMPARISON_SKILLS


@app.post("/api/project-comparisons")
def compare_projects(request: ProjectCompareRequest) -> dict[str, Any]:
    if request.skill_id not in {skill["id"] for skill in COMPARISON_SKILLS}:
        raise HTTPException(status_code=404, detail="Project comparison skill not found")
    project_ids = list(dict.fromkeys(request.project_ids))
    if len(project_ids) < 2:
        raise HTTPException(status_code=422, detail="Select at least two projects")
    if len(project_ids) > 20:
        raise HTTPException(status_code=422, detail="A comparison supports at most 20 projects")
    previews: list[dict[str, Any]] = []
    for project_id in project_ids:
        try:
            previews.append(_project_preview(store.get(project_id)))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}") from exc
    requested_variables = request.variables or sorted({key for preview in previews for key in preview["variables"]})
    projects_payload = []
    for preview in previews:
        projects_payload.append({
            "id": preview["id"],
            "name": preview["name"],
            "category": preview["category"],
            "counts": preview["counts"],
            "variables": {key: preview["variables"].get(key) for key in requested_variables},
            "distance_minimums": {
                curve["name"]: curve["minimum_mm"] for curve in preview["distance_curves"]
            },
        })
    differences = []
    for variable in requested_variables:
        values = [project["variables"].get(variable) for project in projects_payload]
        numeric = [float(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
        differences.append({
            "variable": variable,
            "values": values,
            "minimum": min(numeric) if numeric else None,
            "maximum": max(numeric) if numeric else None,
            "spread": max(numeric) - min(numeric) if numeric else None,
            "changed": len({json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values}) > 1,
        })
    return {
        "skill_id": request.skill_id,
        "project_ids": project_ids,
        "variables": requested_variables,
        "projects": projects_payload,
        "differences": differences,
    }


@app.get("/api/projects/{project_id}/meshes")
def project_meshes(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    root = _mesh_root_path(project_id, project)
    return {"mesh_root": project.mesh_root, "files": list_mesh_files(root)}


@app.post("/api/projects/{project_id}/meshes/scan")
def scan_project_meshes(project_id: str, request: MeshScanRequest) -> dict[str, Any]:
    _require_desktop_capability()
    project = get_project(project_id)
    _require_editable(project)
    root = Path(os.path.expandvars(os.path.expanduser(request.path))).resolve()
    current_root = _mesh_root_path(project_id, project)
    if root != current_root:
        raise HTTPException(
            status_code=422,
            detail="桌面诊断扫描只能重扫当前项目已托管的数模根；新文件请通过 Web 上传通道导入",
        )
    if not root.is_dir():
        raise HTTPException(status_code=422, detail=f"Folder does not exist: {request.path}")
    files = list_mesh_files(root)
    if not files:
        raise HTTPException(status_code=422, detail="No STL or OBJ files were found in this folder")
    repaired = repair_mesh_references(project, files)
    project = update_project(project_id, project)
    return {"mesh_root": project.mesh_root, "files": files, "project": project.model_dump(), "repair": repaired}


@app.get("/api/projects/{project_id}/mesh-folders")
def list_project_mesh_folders(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    folders = store.list_model_asset_folders(project.category) if project.category != "None" else []
    return {"project_id": project_id, "category": project.category, "current": project.mesh_root, "folders": folders}


@app.post("/api/projects/{project_id}/mesh-folders", status_code=201)
def create_project_mesh_folder(project_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    project = get_project(project_id)
    _require_editable(project)
    _require_mutable_mesh_assets(project)
    try:
        reference, _path = store.create_model_asset_folder(project.category, str(body.get("name", "")).strip(), uploaded_by=active_identity().username)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with core.acquire(project_id) as instance:
        result = instance.bus.dispatch({
            "tool_id": "project.asset_selection",
            "params": {"project": project.model_dump(), "asset_folder_path": reference, "intent": "创建并选择模型类型公共数模资产文件夹"},
            "actor": active_identity().username, "client": "human_ui",
        })
        if not result.ok:
            raise HTTPException(422, result.errors)
        project = instance.project()
    return {"project": project.model_dump(), "current": project.mesh_root, "folders": store.list_model_asset_folders(project.category)}


@app.post("/api/projects/{project_id}/mesh-folders/select")
def select_project_mesh_folder(project_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    project = get_project(project_id)
    _require_editable(project)
    reference = str(body.get("reference", "")).strip()
    try:
        root = store.resolve_model_asset_reference(reference)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not root.is_dir() or not reference.startswith(f"@model_assets/{project.category}/"):
        raise HTTPException(422, "只能选择当前模型类型下已存在的数模资产文件夹")
    project.mesh_root = reference
    repaired = repair_mesh_references(project, list_mesh_files(root))
    repair_joint_references(project)
    with core.acquire(project_id) as instance:
        result = instance.bus.dispatch({
            "tool_id": "project.asset_selection",
            "params": {"project": project.model_dump(), "asset_folder_path": reference, "intent": "选择模型类型公共数模资产文件夹"},
            "actor": active_identity().username, "client": "human_ui",
        })
        if not result.ok:
            raise HTTPException(422, result.errors)
        project = instance.project()
    return {"project": project.model_dump(), "current": project.mesh_root, "files": list_mesh_files(root), "repair": repaired,
            "folders": store.list_model_asset_folders(project.category)}


@app.delete("/api/projects/{project_id}/mesh-folder-file/{asset_path:path}")
def delete_project_mesh_folder_file(project_id: str, asset_path: str) -> dict[str, Any]:
    project = get_project(project_id)
    _require_editable(project)
    _require_mutable_mesh_assets(project)
    if not str(project.mesh_root).startswith("@model_assets/"):
        raise HTTPException(409, "当前模型未选择公共数模资产文件夹")
    root = _mesh_root_path(project_id, project)
    relative = Path(asset_path.replace("\\", "/"))
    target = (root / relative).resolve()
    if root.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "数模资产文件不存在")
    if target.suffix.lower() not in MODEL_ASSET_UPLOAD_EXTENSIONS:
        raise HTTPException(422, "不支持删除该类型资产")
    target.unlink()
    for parent in target.parents:
        if parent == root:
            break
        try:
            parent.rmdir()
        except OSError:
            break
    files = list_mesh_files(root)
    repaired = repair_mesh_references(project, files)
    project = update_project(project_id, project)
    return {"project": project.model_dump(), "files": files, "repair": repaired,
            "folders": store.list_model_asset_folders(project.category)}


@app.post("/api/projects/{project_id}/meshes/rescan")
def rescan_project_meshes(project_id: str) -> dict[str, Any]:
    """Rescan only the project's already-uploaded server asset tree.

    Unlike the legacy ``/meshes/scan`` desktop path picker, this endpoint is
    safe for local and remote browsers alike: clients cannot select or probe an
    arbitrary path on the server.
    """
    project = get_project(project_id)
    _require_editable(project)
    root = _mesh_root_path(project_id, project)
    managed_root = (store._directory(project_id) / "assets").resolve()
    if not root.is_dir():
        raise HTTPException(status_code=422, detail="当前项目数模目录不存在，请先上传 STL/OBJ")
    files = list_mesh_files(root)
    repaired = repair_mesh_references(project, files)
    project = update_project(project_id, project)
    return {"mesh_root": project.mesh_root, "files": files, "project": project.model_dump(), "repair": repaired}


@app.get("/api/projects/{project_id}/meshes/file/{mesh_path:path}")
def project_mesh_file(project_id: str, mesh_path: str):
    project = get_project(project_id)
    root = _mesh_root_path(project_id, project)
    target = (root / mesh_path).resolve()
    if not root.is_dir() or root not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="Mesh file not found")
    if target.suffix.lower() not in SUPPORTED_MESH_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Unsupported mesh format")
    return FileResponse(target)


@app.post("/api/projects/{project_id}/meshes/upload")
async def upload_project_meshes(
    project_id: str,
    files: list[UploadFile] = File(...),
    relative_paths: str = Form("[]"),
) -> dict[str, Any]:
    project = get_project(project_id)
    _require_editable(project)
    _require_mutable_mesh_assets(project)
    try:
        requested_paths = json.loads(relative_paths)
        if not isinstance(requested_paths, list):
            requested_paths = []
    except ValueError:
        requested_paths = []
    if str(project.mesh_root).startswith("@model_assets/"):
        target_root = store.resolve_model_asset_reference(project.mesh_root, create=True)
    else:
        suggested = "默认数模资产"
        if requested_paths:
            parts = str(requested_paths[0] or "").replace("\\", "/").strip("/").split("/")
            if len(parts) > 1 and parts[0]:
                suggested = parts[0]
        base, suffix = suggested, 2
        while True:
            try:
                reference, target_root = store.create_model_asset_folder(project.category, suggested, uploaded_by=active_identity().username)
                break
            except ValueError as exc:
                if "已存在" not in str(exc):
                    raise HTTPException(422, str(exc)) from exc
                suggested = f"{base}_{suffix}"; suffix += 1
        project.mesh_root = reference
    uploaded, uploaded_meshes, rejected = await _store_model_asset_uploads(
        files, requested_paths, target_root
    )
    if not uploaded:
        raise HTTPException(422, "没有可接受的数模资产文件；请检查路径和文件类型")
    if not uploaded_meshes and not list_mesh_files(target_root):
        raise HTTPException(422, "数模资产文件夹中至少需要一个 STL/OBJ 文件")
    repaired = repair_mesh_references(project, list_mesh_files(target_root))
    repair_joint_references(project)
    with core.acquire(project_id) as instance:
        result = instance.bus.dispatch({
            "tool_id": "project.asset_selection",
            "params": {"project": project.model_dump(), "asset_folder_path": project.mesh_root, "intent": "维护模型类型公共数模资产文件夹"},
            "actor": active_identity().username, "client": "human_ui",
        })
        if not result.ok:
            raise HTTPException(422, result.errors)
        project = instance.project()
    return {"mesh_root": project.mesh_root, "uploaded": uploaded, "uploaded_meshes": uploaded_meshes, "rejected": rejected,
            "files": list_mesh_files(target_root), "project": project.model_dump(), "repair": repaired,
            "folders": store.list_model_asset_folders(project.category)}


@app.post("/api/projects/{project_id}/meshes/adaptive")
def adapt_project_mesh_family(project_id: str, request: AdaptiveMeshRequest) -> dict[str, Any]:
    project = get_project(project_id)
    _require_editable(project)
    result = adaptive_add(project, request.layer_id, request.seed_filename, list_mesh_files(_mesh_root_path(project_id, project)))
    saved = update_project(project_id, project)
    return {"project": saved.model_dump(), **result}


@app.post("/api/projects/{project_id}/meshes/repair")
def repair_project_meshes(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    _require_editable(project)
    result = repair_mesh_references(project, list_mesh_files(_mesh_root_path(project_id, project)))
    saved = update_project(project_id, project)
    return {"project": saved.model_dump(), **result}


@app.post("/api/projects/{project_id}/validate")
def project_validation(project_id: str, check_files: bool = True) -> list[dict[str, Any]]:
    project = get_project(project_id)
    return [issue.model_dump() for issue in validate_project(_runtime_project(project_id, project), check_files=check_files)]


@app.post("/api/projects/{project_id}/generate")
def project_generation(project_id: str, check_files: bool = True) -> dict[str, str]:
    project = get_project(project_id)
    try:
        return generate_project(_runtime_project(project_id, project), store.outputs(project_id), check_files=check_files)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/mujoco-check")
def project_mujoco_check(project_id: str) -> dict[str, object]:
    project_generation(project_id)
    try:
        return load_with_mujoco(str(store.outputs(project_id) / "generated_model.xml"))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/simulate", status_code=202)
def project_simulation(project_id: str) -> dict[str, str]:
    source_project = get_project(project_id)
    project = _runtime_project(project_id, source_project)
    fingerprint = _fingerprint(project_id, source_project)

    def simulate(progress, cancelled, workspace, job_id):
        result = run_project_simulation_isolated(project, workspace, progress=progress, should_cancel=cancelled)
        if cancelled():
            raise InterruptedError("仿真已取消，未发布部分结果")
        return _publish_result_directory(
            project_id=project_id, project=source_project, kind="simulation", job_id=job_id,
            workspace=workspace, result=result, parameters={}, fingerprint=fingerprint,
        )

    job_id = _submit_project_job(project_id, "simulation", simulate)
    return {"job_id": job_id}


# Viewer-equivalent distance curves are non-authoritative derived results.
# Never patch a frozen baseline, a simulation_result.json, or a model ProjectSpec.
_DISTANCE_CURVE_METHOD = "viewer_sampled_surface_v2_exact_all_samples"
_distance_cache_locks_guard = threading.Lock()
_distance_cache_locks: dict[str, threading.Lock] = {}
# At most two concurrent sampled-distance workers, so selecting many axes
# cannot monopolize the Server's shared JobManager or all CPU cores.
_distance_curve_slots = threading.Semaphore(2)
# Serialize only the brief accept/reuse check, never an entire KD calculation.
# Prevent two near-simultaneous POSTs (or a batch+single request) from each
# claiming a JobManager slot before the other becomes visible.
_distance_curve_submission_gate = threading.Lock()


# One JobManager job per (project, frozen snapshot, owner, lease).  The short
# submission gate protects only pending-wave ownership, never native KD work.
_distance_flights: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}


def _distance_batch_contexts(project_id: str, pair_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Verify one immutable snapshot and build stable, per-pair cache identities.

    The legacy no-argument API continues to select every frozen pair.  Reusing
    this builder for single and batch requests prevents divergent authorization
    and avoids N repeated mesh scans / generated JSON reads per HTTP poll.
    """
    snapshot_started = time.perf_counter()
    result, source_dir = _latest_simulation_record(project_id)
    if not isinstance(result, dict) or source_dir is None:
        raise HTTPException(404, "请先刷新坐标系，生成可回放的仿真轨迹")
    scene = source_dir / "generated" / "generated_model.xml"
    drives = source_dir / "generated" / "generated_drives.json"
    trajectory = source_dir / "trajectory.npz"
    if not all(path.is_file() for path in (scene, drives, trajectory)):
        raise HTTPException(409, "本次结果缺少 MuJoCo 场景/数模映射/轨迹，请重新刷新坐标系")
    try:
        spec = json.loads(drives.read_text("utf-8"))
    except (ValueError, OSError) as exc:
        raise HTTPException(422, "仿真数模映射文件损坏") from exc
    if not isinstance(spec, dict) or not isinstance(spec.get("distance_pairs"), list):
        raise HTTPException(422, "冻结测距配置结构无效")
    defined: dict[str, dict[str, Any]] = {}
    for pair in spec["distance_pairs"]:
        if not isinstance(pair, dict) or not isinstance(pair.get("id"), str) or not pair["id"]:
            raise HTTPException(422, "冻结测距对 ID 无效")
        if pair["id"] in defined:
            raise HTTPException(422, "冻结测距配置存在重复 ID")
        defined[pair["id"]] = pair
    if pair_ids is None:
        ids = list(defined)
    else:
        if (not isinstance(pair_ids, list) or not pair_ids or
                any(not isinstance(item, str) or not item.strip() for item in pair_ids)):
            raise HTTPException(422, "pair_ids 必须是非空字符串数组")
        ids = list(dict.fromkeys(pair_ids))
        if any(pair_id not in defined for pair_id in ids):
            raise HTTPException(404, "测距对不属于当前仿真；请先刷新坐标系")
    if not ids:
        raise HTTPException(422, "当前仿真未定义测距对")

    # All selected pairs share the same frozen scene/trajectory/mesh identity.
    # The generated/meshes tree is a snapshot, never the editable mesh_root.
    mesh_identities: dict[str, tuple[int, int]] = {}
    snapshot_root = source_dir / "generated" / "meshes"
    generated_config = source_dir / "generated" / "generated_config.json"
    if snapshot_root.is_dir():
        for asset in sorted(snapshot_root.rglob("*")):
            if asset.is_file():
                stat = asset.stat()
                mesh_identities[asset.relative_to(snapshot_root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
        if not mesh_identities:
            raise HTTPException(409, "本次仿真没有可用的冻结数模资产；请重新刷新坐标系")
    elif generated_config.is_file():
        try:
            config = json.loads(generated_config.read_text("utf-8"))
            raw_root = config.get("mesh_root") if isinstance(config, dict) else None
            if raw_root:
                mesh_root = Path(str(raw_root)).resolve()
                names = {str(filename) for pair in defined.values()
                         for side in ("objects_a", "objects_b") for filename in (pair.get(side) or ())}
                for filename in sorted(names):
                    mesh_path = (mesh_root / filename).resolve()
                    try:
                        mesh_path.relative_to(mesh_root)
                    except ValueError as exc:
                        raise HTTPException(422, "测距对包含不安全的数模资产相对路径") from exc
                    if not mesh_path.is_file():
                        raise HTTPException(409, f"仿真使用的数模文件已缺失：{filename}；请重新刷新坐标系")
                    stat = mesh_path.stat()
                    mesh_identities[filename] = (stat.st_size, stat.st_mtime_ns)
        except (OSError, ValueError, TypeError) as exc:
            raise HTTPException(422, "本次仿真保存的数模来源信息无效") from exc
    stat_identity = lambda path: (path.stat().st_size, path.stat().st_mtime_ns)
    identity = {"mesh_assets": mesh_identities, "schema": _DISTANCE_CURVE_METHOD,
                "simulation": source_dir.name, "scene": stat_identity(scene),
                "drives": stat_identity(drives), "trajectory": stat_identity(trajectory)}
    sampling = spec.get("distance_sampling", {})
    snapshot_key = hashlib.sha256(json.dumps({**identity, "sampling": sampling}, sort_keys=True,
                                              ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    times = result.get("times") if isinstance(result.get("times"), list) else None
    frame_count = len(times) if times else None
    cache_root = RUNTIME_STATE_DIR / "distance_curve_cache" / hashlib.sha256(project_id.encode("utf-8")).hexdigest()[:20]
    contexts = []
    for pair_id in ids:
        signature = {**identity, "pair": defined[pair_id], "sampling": sampling}
        key = hashlib.sha256(json.dumps(signature, sort_keys=True, ensure_ascii=False,
                                        allow_nan=False).encode("utf-8")).hexdigest()
        pair_digest = hashlib.sha256(pair_id.encode("utf-8")).hexdigest()[:16]
        cache_path = cache_root / f"{source_dir.name}_{pair_digest}_{key}.json"
        contexts.append({"simulation_id": source_dir.name, "pair_id": pair_id,
                         "cache_key": key, "cache_path": cache_path,
                         "partial_path": cache_path.with_suffix(".partial.json"),
                         "scene": scene, "drives": drives, "trajectory": trajectory,
                         "frame_count": frame_count, "times": times,
                         "snapshot_key": snapshot_key})
    context_seconds = round(time.perf_counter() - snapshot_started, 4)
    for context in contexts:
        context["snapshot_context_s"] = context_seconds
    return contexts


def _distance_curve_context(project_id: str, pair_id: str) -> dict[str, Any]:
    return _distance_batch_contexts(project_id, [pair_id])[0]


def _read_distance_curve_cache(
    path: Path, context: dict[str, Any], *, partial: bool = False,
) -> dict[str, Any] | None:
    """Never accept truncated/invalid files as ready; old V2.16.8 records work."""
    try:
        record = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if (not isinstance(record, dict) or record.get("pair_id") != context["pair_id"] or
            record.get("cache_key") != context["cache_key"] or
            (record.get("simulation_id") is not None and record["simulation_id"] != context["simulation_id"])):
        return None
    curve = record.get("curve")
    if not isinstance(curve, dict) or curve.get("viewer_query_mode") != "exact_all_samples" or curve.get("method") != "viewer_sampled_surface_v1":
        return None
    values = curve.get("values")
    total = curve.get("total_frames")
    completed = curve.get("completed_frames")
    expected = context.get("frame_count")
    if (not isinstance(values, list) or type(total) is not int or total < 1 or
            type(completed) is not int or not 0 < completed <= total or
            (expected is not None and total != expected) or len(values) != completed or
            (not partial and (completed != total or curve.get("status") != "ready")) or
            (partial and curve.get("status") != "partial")):
        return None
    if any(value is not None and (type(value) not in (int, float) or not math.isfinite(value)) for value in values):
        return None
    finite = [(index, float(value)) for index, value in enumerate(values) if value is not None]
    if finite:
        first_min, minimum = min(finite, key=lambda item: item[1])
        reported = curve.get("minimum_mm")
        if (type(reported) not in (int, float) or not math.isfinite(reported) or
                not math.isclose(reported, minimum, rel_tol=1e-12, abs_tol=1e-9)):
            return None
        times = context.get("times")
        reported_time = curve.get("minimum_time_s")
        if type(reported_time) not in (int, float) or not math.isfinite(reported_time):
            return None
        if times is not None and first_min < len(times) and not math.isclose(
                float(reported_time), float(times[first_min]), abs_tol=1e-9, rel_tol=1e-12):
            return None
    elif curve.get("minimum_mm") is not None or curve.get("minimum_time_s") is not None:
        return None
    if curve.get("invalid_frames") is not None and curve["invalid_frames"] != completed - len(finite):
        return None
    return record


def _curve_cache_response(context: dict[str, Any]) -> dict[str, Any]:
    for key, status in (("cache_path", "ready"), ("partial_path", "partial")):
        record = _read_distance_curve_cache(context[key], context, partial=status == "partial")
        if record:
            return {"status": status, "simulation_id": context["simulation_id"],
                    "pair_id": context["pair_id"], "cache_key": context["cache_key"],
                    "curve": record["curve"]}
    return {"status": "not_computed", "simulation_id": context["simulation_id"],
            "pair_id": context["pair_id"], "cache_key": context["cache_key"]}


def _distance_curve_lock(key: str) -> threading.Lock:
    stripe = str(hashlib.sha256(key.encode("utf-8")).digest()[0] % 64)
    with _distance_cache_locks_guard:
        return _distance_cache_locks.setdefault(stripe, threading.Lock())


@contextmanager
def _distance_compute_guard(lock, cancelled, progress=None):
    acquired = []
    queue_waits: dict[str, float] = {}
    try:
        for stage, resource in (("全局测距槽", _distance_curve_slots), ("冻结快照锁", lock)):
            waiting_at = time.monotonic()
            if progress:
                progress(0.0, f"等待{stage}（测距任务排队中）")
            while not resource.acquire(timeout=0.2):
                if cancelled():
                    raise InterruptedError("测距任务已取消")
            acquired.append(resource)
            if cancelled():
                raise InterruptedError("测距任务已取消")
            queue_waits[stage] = round(time.monotonic() - waiting_at, 4)
            LOGGER.debug("distance job waited %.3fs for %s", queue_waits[stage], stage)
        yield queue_waits
    finally:
        for resource in reversed(acquired):
            resource.release()


def _distance_batch_response(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [_curve_cache_response(context) for context in contexts]
    status = "ready" if all(row["status"] == "ready" for row in rows) else "partial" if any(row["status"] != "not_computed" for row in rows) else "not_computed"
    return {"status": status, "simulation_id": contexts[0]["simulation_id"],
            "pairs": {row["pair_id"]: row for row in rows}}


def _distance_flight_worker(flight: dict[str, Any], progress, cancelled) -> dict[str, Any]:
    """Atomically consume selection waves while one existing Job owns the slot."""
    scope = flight["scope"]
    prepared: dict[str, Any] = {}  # Job-local MuJoCo model, trajectory, immutable geom trees
    total_pairs = 0
    combined_timings: list[dict[str, Any]] = []
    all_contexts = flight["all_contexts"]
    started = time.perf_counter()
    queue_timings: dict[str, float] = {}
    try:
        with _distance_compute_guard(_distance_curve_lock(scope[-1]), cancelled, progress) as queue_timings:
            # Small coalescing window allows fast selection changes to share a
            # single wave/model/trajectory load without delaying HTTP 202.
            end = time.monotonic() + 0.15
            while time.monotonic() < end:
                if cancelled():
                    raise InterruptedError("测距任务已取消")
                time.sleep(min(0.02, max(0, end - time.monotonic())))
            while True:
                if cancelled():
                    raise InterruptedError("测距任务已取消")
                with _distance_curve_submission_gate:
                    wave = list(flight["pending"].values())
                    flight["pending"].clear()
                    if not wave:
                        flight["accepting"] = False
                        _distance_flights.pop(scope, None)
                        break
                missing = [context for context in wave if not _read_distance_curve_cache(context["cache_path"], context)]
                if not missing:
                    continue
                for context in missing:
                    context["cache_path"].parent.mkdir(parents=True, exist_ok=True)
                progress(0.01, f"已接收 {len(missing)} 条测距对，准备精确采样")
                def publish_partial(curves):
                    for context in missing:
                        if cancelled():
                            raise InterruptedError("测距任务已取消")
                        pair_id = context["pair_id"]
                        atomic_write_text(context["partial_path"], json.dumps({
                            "pair_id": pair_id, "cache_key": context["cache_key"],
                            "simulation_id": context["simulation_id"], "curve": curves[pair_id],
                        }, ensure_ascii=False, allow_nan=False))
                try:
                    active_jobs = sum(1 for job in jobs.list(250) if
                                      str(job.get("kind", "")).startswith("distance_curve:") and
                                      job.get("status") not in TERMINAL_STATUSES)
                    cpu = max(1, os.cpu_count() or 1)
                    budget = max(1, min(5, cpu // max(1, active_jobs)))
                    first = missing[0]
                    curves = compute_viewer_distance_curves(
                        first["scene"], first["drives"], first["trajectory"],
                        [context["pair_id"] for context in missing], progress=progress,
                        should_cancel=cancelled, partial=publish_partial,
                        pair_workers=budget, shared_context=prepared,
                    )
                    if cancelled():
                        raise InterruptedError("测距任务已取消")
                    persist_started = time.perf_counter()
                    for context in missing:
                        atomic_write_text(context["cache_path"], json.dumps({
                            "pair_id": context["pair_id"], "cache_key": context["cache_key"],
                            "simulation_id": context["simulation_id"],
                            "curve": curves[context["pair_id"]],
                        }, ensure_ascii=False, allow_nan=False))
                    total_pairs += len(missing)
                    wave_timing = dict(next(iter(curves.values()))["timings_seconds"])
                    wave_timing["snapshot_context_s"] = first["snapshot_context_s"]
                    wave_timing["cache_write_s"] = round(time.perf_counter() - persist_started, 4)
                    combined_timings.append(wave_timing)
                finally:
                    for context in missing:
                        context["partial_path"].unlink(missing_ok=True)
    finally:
        with _distance_curve_submission_gate:
            flight["accepting"] = False
            if _distance_flights.get(scope) is flight:
                _distance_flights.pop(scope, None)
        for context in all_contexts.values():
            context["partial_path"].unlink(missing_ok=True)
        prepared.clear()
    return {"simulation_id": scope[1], "pair_count": total_pairs,
            "cached": total_pairs == 0, "wave_count": len(combined_timings),
            "timings_seconds": {"total_s": round(time.perf_counter() - started, 4),
                                "queue_wait_s": round(sum(queue_timings.values()), 4),
                                "slot_wait_s": queue_timings.get("全局测距槽", 0.0),
                                "snapshot_lock_wait_s": queue_timings.get("冻结快照锁", 0.0),
                                "waves": combined_timings},
            **({"pair_id": next(iter(all_contexts)), "cache_key": next(iter(all_contexts.values()))["cache_key"]}
               if len(all_contexts) == 1 else {})}


def _submit_distance_curve_job(project_id: str, contexts: list[dict[str, Any]]) -> str:
    identity = active_identity()
    first = contexts[0]
    scope = (str(project_id), first["simulation_id"], identity.username.casefold(),
             identity.lease_id, first["snapshot_key"])
    with _distance_curve_submission_gate:
        for existing in jobs.list(250):
            if (str(existing.get("project_id", "")) != str(project_id) or
                not str(existing.get("kind", "")).startswith("distance_curve:") or
                existing.get("status") in TERMINAL_STATUSES):
                continue
            # An unrelated owner/lease/snapshot may not receive this Job ID.
            if (str(existing.get("owner", "")).casefold() != identity.username.casefold() or
                existing.get("owner_lease_id") != identity.lease_id or
                existing.get("kind") != f"distance_curve:{first['snapshot_key'][:32]}"):
                raise HTTPException(status_code=429, detail={
                    "code": "distance_curve_busy", "retry_after": 5,
                    "message": "当前模型已有测距计算进行中，将在任务空闲后自动重试",
                })
            flight = _distance_flights.get(scope)
            if flight and flight["accepting"]:
                for context in contexts:
                    pair_id = context["pair_id"]
                    if pair_id not in flight["all_contexts"]:
                        flight["all_contexts"][pair_id] = context
                        flight["pending"][pair_id] = context
                return str(existing["id"])
            # A flight finishing between closing its queue and Job terminal
            # state is NOT eligible for append; retry after terminal.
            raise HTTPException(status_code=429, detail={
                "code": "distance_curve_busy", "retry_after": 5,
                "message": "测距任务正在完成发布，请稍后重试",
            })
        # Purge flights whose queued jobs were cancelled/timed out before
        # running; those jobs never entered the worker's finally block.
        active_ids = {str(item["id"]) for item in jobs.list(250)
                      if item.get("status") not in TERMINAL_STATUSES}
        for stale_scope, stale in list(_distance_flights.items()):
            if stale.get("job_id") and stale["job_id"] not in active_ids:
                stale["accepting"] = False
                _distance_flights.pop(stale_scope, None)
        flight = {"scope": scope, "pending": OrderedDict((c["pair_id"], c) for c in contexts),
                  "all_contexts": {c["pair_id"]: c for c in contexts}, "accepting": True}
        _distance_flights[scope] = flight
        try:
            job_id = _submit_project_job(
                project_id, f"distance_curve:{first['snapshot_key'][:32]}",
                lambda progress, cancelled, _workspace, _job_id: _distance_flight_worker(flight, progress, cancelled),
                timeout_seconds=JOB_TIMEOUT_SECONDS,
            )
            flight["job_id"] = job_id
            return job_id
        except BaseException:
            _distance_flights.pop(scope, None)
            raise


@app.get("/api/projects/{project_id}/distance-curves")
def get_distance_curves(project_id: str, pair_id: list[str] | None = Query(default=None)) -> dict[str, Any]:
    project = get_project(project_id)
    require_project_access(project)
    return _distance_batch_response(_distance_batch_contexts(project_id, pair_id))


@app.post("/api/projects/{project_id}/distance-curves", status_code=202)
def compute_distance_curves(project_id: str, payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    project = get_project(project_id)
    require_project_access(project)
    if payload is not None and any(key != "pair_ids" for key in payload):
        raise HTTPException(422, "不支持的测距选择字段")
    pair_ids = payload.get("pair_ids") if payload is not None else None
    contexts = _distance_batch_contexts(project_id, pair_ids)
    response = _distance_batch_response(contexts)
    if response["status"] == "ready":
        return response
    missing = [context for context in contexts if
               not _read_distance_curve_cache(context["cache_path"], context)]
    job_id = _submit_distance_curve_job(project_id, missing)
    return {**response, "status": "computing", "job_id": job_id}


@app.get("/api/projects/{project_id}/distance-curves/{pair_id}")
def get_selected_distance_curve(project_id: str, pair_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    require_project_access(project)
    return _curve_cache_response(_distance_curve_context(project_id, pair_id))


@app.post("/api/projects/{project_id}/distance-curves/{pair_id}", status_code=202)
def compute_selected_distance_curve(project_id: str, pair_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    require_project_access(project)
    context = _distance_curve_context(project_id, pair_id)
    cached = _read_distance_curve_cache(context["cache_path"], context)
    if cached:
        return {"status": "ready", **_curve_cache_response(context)}
    job_id = _submit_distance_curve_job(project_id, [context])
    return {"status": "computing", "job_id": job_id, "pair_id": pair_id,
            "simulation_id": context["simulation_id"], "cache_key": context["cache_key"]}


def _simulation_with_cached_distance_curves(
    project_id: str, result: dict[str, Any], source_dir: Path | None,
) -> dict[str, Any]:
    """Supply finished Viewer measurements to downstream exports without rewriting simulation artifacts."""
    raw = result.get("distance_curves") if isinstance(result, dict) else None
    if not isinstance(raw, dict) or source_dir is None:
        return result
    enriched = dict(raw)
    any_updated = False
    for pair_id, original in raw.items():
        if not isinstance(original, dict) or original.get("status") != "not_computed":
            continue
        try:
            context = _distance_curve_context(project_id, str(pair_id))
        except HTTPException:
            continue
        if context["simulation_id"] != source_dir.name:
            continue
        cached = _read_distance_curve_cache(context["cache_path"], context)
        if cached and cached["curve"].get("method") == "viewer_sampled_surface_v1":
            enriched[pair_id] = {**original, **cached["curve"]}
            any_updated = True
    return {**result, "distance_curves": enriched} if any_updated else result


@app.post("/api/projects/{project_id}/web-viewer", status_code=202)
def project_web_viewer(project_id: str, request: WebViewerRequest | None = None) -> dict[str, str]:
    """Build an offline browser playback artifact from the current MuJoCo schedule.

    The returned HTML is deliberately not described as a live debugger: after the
    export job completes it no longer owns, nor talks to, a server-side MjData.
    """
    instance = core.get(project_id)
    project = scratch_project(_runtime_project(project_id, instance.project()))
    if request and request.quick_results:
        apply_quick_results(project, {str(key): float(value) for key, value in request.quick_results.items()})
    require_project_access(project)
    viewer_root = instance.project_dir / "core" / "web_viewer"
    destination = viewer_root / "index.html"
    fingerprint = _fingerprint(project_id, instance.project())

    def build(progress, cancelled, workspace, job_id):
        staged_html = workspace / "index.html"
        result = export_project_animation_html(
            project, workspace, destination=staged_html, progress=progress, should_cancel=cancelled,
            gantt_cache_dir=instance.project_dir / "core" / "artifacts" / "gantt_cache",
            gantt_fallback_dir=workspace / "gantt_fallback",
        )
        if cancelled():
            raise InterruptedError("Viewer 导出已取消，未发布部分结果")
        provenance = write_provenance(
            workspace, job_id=job_id, kind="web_viewer_export", application_version=__version__,
            fingerprint=fingerprint, parameters=request.model_dump() if request else {},
            ephemeral=core.is_ephemeral(project_id),
        )
        embedded = json.dumps(provenance, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
        with staged_html.open("a", encoding="utf-8") as handle:
            handle.write(f'\n<script type="application/json" id="mujoco-studio-provenance">{embedded}</script>\n')
        job_workspaces.publish_file(staged_html, destination)
        result["artifact"] = str(destination)
        result["artifact_relative"] = "core/web_viewer/index.html"
        result["provenance"] = provenance
        result["freshness"] = {"status": "current", "stale": False, "reasons": []}
        return {**result, "viewer_url": f"/api/projects/{project_id}/web-viewer"}

    return {"job_id": _submit_project_job(project_id, "web_viewer_export", build), "viewer_url": f"/api/projects/{project_id}/web-viewer"}


@app.get("/api/projects/{project_id}/web-viewer")
def get_project_web_viewer(project_id: str):
    instance = core.get(project_id)
    require_project_access(instance.project())
    path = instance.project_dir / "core" / "web_viewer" / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Web MuJoCo Viewer 尚未生成")
    return FileResponse(path, media_type="text/html", headers={"Cache-Control": "no-store"})


@app.post("/api/projects/{project_id}/export-animation-html", status_code=202)
def project_animation_html_export(
    project_id: str,
    save_delivery: bool = Query(True),
    baseline_prepare: bool = Query(False),
) -> dict[str, Any]:
    """Generate the animation once, publish it as the latest delivery, and let the browser download it.

    ``save_delivery`` is retained only for older clients; V2.9.4 always publishes the generated HTML
    into the model delivery folder so generation and delivery cannot drift apart.
    """
    authoritative_project = get_project(project_id)
    if authoritative_project.lifecycle.status == "checked_out":
        _require_editable(authoritative_project)
    elif baseline_prepare and authoritative_project.lifecycle.status == "checked_in":
        # V2.11.6: a baseline reuses animation HTML, but a missing HTML is repaired
        # automatically before baseline creation.  This one narrow checked-in writer
        # changes delivery artifacts only; it never mutates ProjectSpec/UI truth.
        _require_mutable_delivery(authoritative_project)
    else:
        raise HTTPException(
            status_code=409,
            detail="当前模型不是签出状态：动画 HTML 生成与交付写入已禁用；只有打基线前缺失动画时可自动后台补生成",
        )
    fingerprint = _fingerprint(project_id, authoritative_project)
    filename = f"{_delivery_stem(authoritative_project)}_anim.html"
    destination, artifact_relative, persistent = _delivery_export_target(project_id, authoritative_project, filename)
    project = _runtime_project(project_id, authoritative_project)
    trajectory_source, trajectory_warnings = _current_simulation_trajectory(project_id, authoritative_project)
    # The Lab uses this identical authoritative qpos format.  If there is no
    # current simulation result, reuse the locally verified Lab trajectory
    # instead of needlessly solving physics a second time in Results > Animation.
    if trajectory_source is None:
        trajectory_source = _lab_cached_trajectory(
            project_id, sequence_identity(authoritative_project, fingerprint)
        )
    gantt_cache_dir = core.get(project_id).project_dir / "core" / "artifacts" / "gantt_cache"

    def export_task(progress, cancelled, workspace, job_id):
        staged = workspace / filename
        result = export_project_animation_html(
            project,
            workspace,
            destination=staged,
            progress=progress,
            should_cancel=cancelled,
            gantt_cache_dir=gantt_cache_dir,
            gantt_fallback_dir=workspace / "gantt_fallback",
            trajectory_source=trajectory_source,
            trajectory_warnings=trajectory_warnings,
        )
        if cancelled():
            raise InterruptedError("动画导出已取消，未发布部分结果")
        published = _publish_result_directory(
            project_id=project_id, project=authoritative_project, kind="animation_html_export", job_id=job_id,
            workspace=workspace, result=result, parameters={"delivery": True}, fingerprint=fingerprint,
        )
        published_artifact = Path(published["result_dir"]) / filename
        job_workspaces.publish_file(published_artifact, destination)
        if persistent:
            _record_delivery_output(authoritative_project, destination, "animation_html", "动画 HTML")
        published["artifact"] = str(destination)
        published["artifact_relative"] = artifact_relative
        published["saved_delivery"] = persistent
        published["preview_only"] = False
        return published

    return {"job_id": _submit_project_job(project_id, "animation_html_export", export_task)}


@app.get("/api/projects/{project_id}/delivery-stem")
def project_delivery_stem(project_id: str) -> dict[str, str]:
    project = get_project(project_id)
    return {"stem": _delivery_stem(project)}


@app.post("/api/projects/{project_id}/export-nx-afu-script")
def project_nx_afu_export(project_id: str, save_delivery: bool = Query(True)) -> dict[str, Any]:
    project = get_project(project_id)
    simulation, simulation_dir = _latest_simulation_record(project_id)
    if not simulation:
        raise HTTPException(status_code=422, detail="尚无仿真结果，请先运行仿真")
    # V2.5.2: NX AFU is generated from the latest trajectory/layout. Asset
    # fingerprint drift alone must not block export. The hard prerequisite is
    # that every mesh referenced by the current hierarchy still exists.
    mesh_root = store.resolve_mesh_root(project.id, project.mesh_root) if project.mesh_root else store.mesh_directory(project.id)
    missing_meshes = sorted({
        mesh.filename for layer in project.layers for mesh in layer.meshes
        if mesh.filename and not (mesh_root / mesh.filename).is_file()
    })
    if missing_meshes:
        raise HTTPException(status_code=409, detail={
            "code": "mesh_asset_missing",
            "message": "层级树中存在缺失数模文件，修复引用后再生成 NX 脚本",
            "missing": missing_meshes,
        })
    filename = f"{_delivery_stem(project)}_NX script.py"
    # V2.9.4 merges generation and delivery. The query flag remains accepted for
    # compatibility, but every successful export replaces the latest delivery copy.
    destination, artifact_relative, persistent = _delivery_export_target(project_id, project, filename)
    staged = destination.parent / f".{destination.name}.{uuid4().hex}.staged"
    try:
        # NX reads the same completed selected-pair surface curves as Studio,
        # instead of permanently blank deferred slots in simulation_result.json.
        simulation_for_export = _simulation_with_cached_distance_curves(project_id, simulation, simulation_dir)
        # A deferred pair is not a zero-length engineering signal.  Refuse an
        # incomplete NX deliverable instead of silently exporting wrong axes.
        needed = {str(curve.source)[5:] for axis in project.result_layout.axes
                  for curve in axis.curves if str(curve.source).startswith("pair:")}
        for pair_id in needed:
            pair_curve = simulation_for_export.get("distance_curves", {}).get(pair_id, {})
            if len(pair_curve.get("values", ())) != len(simulation_for_export.get("times", ())) :
                raise HTTPException(409, f"测距对 {pair_curve.get('name', pair_id)} 尚未计算完成，请先在结果页选择该曲线完成后台测距")
        result = export_project_nx_afu_script(project, simulation_for_export, staged)
        job_workspaces.publish_file(staged, destination)
        result["artifact"] = str(destination)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        staged.unlink(missing_ok=True)
    if persistent:
        _record_delivery_output(project, destination, "nx_afu_script", "NX 脚本")
    result["artifact_relative"] = artifact_relative
    return result


@app.post("/api/projects/{project_id}/optimize", status_code=202)
def project_optimization(
    project_id: str,
    quick: bool = False,
    request: QuickOptimizationRequest | None = None,
) -> dict[str, str]:
    source_project = get_project(project_id)
    project = _runtime_project(project_id, source_project)
    fingerprint = _fingerprint(project_id, source_project)
    if quick:
        step_ids = list(dict.fromkeys((request.step_ids if request else [])))
        def quick_task(progress, cancelled, workspace, job_id):
            result = run_quick_optimization(
                project, workspace,
                step_ids=step_ids,
                progress=progress,
                should_cancel=cancelled,
            )
            if cancelled():
                raise InterruptedError("快速优化已取消，未发布部分结果")
            return _publish_result_directory(
                project_id=project_id, project=source_project, kind="quick_optimization", job_id=job_id,
                workspace=workspace, result=result, parameters={"step_ids": step_ids}, fingerprint=fingerprint,
            )
        job_id = _submit_project_job(project_id, "quick_optimization", quick_task)
        return {"job_id": job_id}
    def optimization_task(progress, cancelled, workspace, job_id):
        result = run_optimization(
            project, workspace,
            progress=progress,
            should_cancel=cancelled,
        )
        if cancelled():
            raise InterruptedError("优化已取消，未发布部分结果")
        return _publish_result_directory(
            project_id=project_id, project=source_project, kind="optimization", job_id=job_id,
            workspace=workspace, result=result, parameters={}, fingerprint=fingerprint,
        )
    job_id = _submit_project_job(project_id, "optimization", optimization_task)
    return {"job_id": job_id}


@app.get("/api/jobs")
def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    identity = active_identity()
    visible: list[dict[str, Any]] = []
    for job in jobs.list(min(max(limit, 1), 200)):
        try:
            _authorize_job(job)
        except HTTPException:
            continue
        visible.append(_job_payload_for(identity, job))
    return visible


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    try:
        job = jobs.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    identity = _authorize_job(job)
    return _job_payload_for(identity, job)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    try:
        job = jobs.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    identity = _authorize_job(job, cancel=True)
    try:
        cancelled_job = jobs.cancel(job_id)
        if str(job.get("kind", "")).startswith("distance_curve:"):
            with _distance_curve_submission_gate:
                for scope, flight in list(_distance_flights.items()):
                    if flight.get("job_id") == job_id:
                        flight["accepting"] = False
                        _distance_flights.pop(scope, None)
        return _job_payload_for(identity, cancelled_job)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


def _conversation(project_id: str) -> ConversationStore:
    return ConversationStore(store._directory(project_id) / "core" / "agent_conversation.jsonl")


def _operation_context(project_id: str, limit: int = 80) -> list[dict[str, Any]]:
    instance = core.get(project_id)
    return [
        {
            "seq": item.seq, "time": item.occurred_at, "client": item.client,
            "tool": item.tool_id, "semantic": item.semantic, "intent": item.intent,
            "paths": [diff.path for diff in item.path_diffs],
        }
        for item in instance.events.all()[-limit:]
    ]


def _download_artifacts(project_id: str, *, include_freshness: bool = True) -> list[dict[str, object]]:
    """List project artifacts, calculating expensive asset freshness only when requested.

    Hub file inventory only needs path/size metadata.  Avoiding provenance freshness
    there prevents every lifecycle refresh from hashing the complete mesh tree.
    """
    root = core.get(project_id).project_dir if core.is_ephemeral(project_id) else store._directory(project_id)
    items: list[dict[str, object]] = []
    if core.is_ephemeral(project_id):
        temporary = root / "outputs" / "temporary_delivery"
        if temporary.is_dir():
            for path in temporary.iterdir():
                if not path.is_file():
                    continue
                kind = "animation_html" if path.name.endswith("_anim.html") else (
                    "nx_afu_script" if path.name.endswith("_NX script.py") else "artifact"
                )
                stat = path.stat()
                items.append({
                    "path": f"temporary_delivery/{path.name}", "size": stat.st_size,
                    "modified": stat.st_mtime, "kind": kind,
                })
    project = get_project(project_id)
    current_fingerprint = None
    if include_freshness:
        try:
            current_fingerprint = _fingerprint(project_id, project)
        except Exception:
            pass
    result_freshness: dict[str, dict[str, Any]] = {}
    for relative_root in ("outputs", "results", "core/artifacts"):
        folder = root / relative_root
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.is_file():
                stat = path.stat()
                relative_path = str(path.relative_to(root)).replace("\\", "/")
                kind = "animation_html_preview" if path.name.endswith("_anim.html") else "artifact"
                item: dict[str, object] = {
                    "path": relative_path, "size": stat.st_size,
                    "modified": stat.st_mtime, "kind": kind,
                }
                if relative_root == "results" and include_freshness:
                    result_relative = path.relative_to(folder)
                    result_directory = folder / result_relative.parts[0]
                    result_key = str(result_directory)
                    cached = result_freshness.get(result_key)
                    if cached is None:
                        cached = (
                            freshness(read_provenance(result_directory), current_fingerprint)
                            if current_fingerprint is not None
                            else {"status": "unknown", "stale": None, "reasons": ["fingerprint_error"]}
                        )
                        result_freshness[result_key] = cached
                    item["freshness"] = cached
                items.append(item)
    delivery = store.delivery_directory(project, create=True)
    for entry in _current_delivery_outputs(project):
        items.append({
            "path": str(entry["path"]), "size": int(entry["size"]),
            "modified": float(entry["modified"]), "kind": str(entry["kind"]),
            "freshness": {"status": str(entry.get("freshness", "user")), "stale": entry.get("freshness") == "stale"},
        })
    return sorted(items, key=lambda item: float(item["modified"]), reverse=True)


DELIVERY_KIND_LABELS = {
    "animation_html": "动画 HTML",
    "nx_afu_script": "NX AFU 脚本",
    "gantt_png": "甘特图 PNG",
    "model_json": "模型 JSON",
    "simulation_xml": "最新仿真 XML",
    "tables_folder": "表格文件夹",
}
LEGACY_DELIVERY_KINDS = {"axes_csv_folder"}


def _delivery_data_fingerprint(project: ProjectSpec) -> str:
    """Fingerprint domain content while excluding collaboration/clock metadata."""
    data = project.model_dump()
    data.pop("lifecycle", None)
    data.pop("metadata", None)
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _delivery_kind_for_name(name: str) -> str:
    value = str(name or "")
    lower = value.casefold()
    if lower.endswith("_anim.html"):
        return "animation_html"
    if lower.endswith("_nx script.py") or lower.endswith("_nx_afu.py"):
        return "nx_afu_script"
    if value.endswith("_甘特图.png"):
        return "gantt_png"
    if value.endswith("_模型.json") or lower.endswith(".mujoco-studio.json"):
        return "model_json"
    if lower.endswith("_坐标系csv") or lower.endswith("_axes_csv"):
        return "axes_csv_folder"
    if value == DELIVERY_TABLE_FOLDER:
        return "tables_folder"
    if lower.endswith("_仿真模型.xml"):
        return "simulation_xml"
    return ""


def _delivery_manifest_path(project: ProjectSpec) -> Path:
    path = store.project_directory(project.id) / "core" / "artifacts" / "delivery_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_delivery_manifest(project: ProjectSpec) -> dict[str, Any]:
    delivery = store.delivery_directory(project, create=True)
    manifest_path = _delivery_manifest_path(project)
    legacy_candidates = (delivery / "delivery_manifest.json", delivery / "archive_manifest.json")
    for source in (manifest_path, *legacy_candidates):
        if not source.is_file():
            continue
        try:
            loaded = json.loads(source.read_text("utf-8"))
            if isinstance(loaded, dict):
                return loaded
        except (OSError, ValueError):
            continue
    return {"fingerprint": "", "outputs": {}}


def _write_delivery_manifest(project: ProjectSpec, manifest: dict[str, Any]) -> None:
    path = _delivery_manifest_path(project)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    temporary.replace(path)
    # V2.6.1: delivery folders are user payload only. Historical manifests are
    # migrated out of the folder so the directory contains only deliverables.
    delivery = store.delivery_directory(project, create=True)
    for legacy in (delivery / "delivery_manifest.json", delivery / "archive_manifest.json"):
        try:
            legacy.unlink(missing_ok=True)
        except OSError:
            pass


def _remove_delivery_path(path: Path) -> None:
    """Remove one managed delivery node without following directory symlinks."""
    target = Path(path)
    if target.is_symlink() or target.is_file():
        target.unlink(missing_ok=True)
    elif target.is_dir():
        shutil.rmtree(target)


def _delivery_path_size(path: Path) -> int:
    if path.is_file():
        return int(path.stat().st_size)
    if path.is_dir():
        return sum(int(child.stat().st_size) for child in path.rglob("*") if child.is_file() and not child.is_symlink())
    return 0


def _delivery_path_modified(path: Path) -> float:
    modified = float(path.stat().st_mtime)
    if path.is_dir():
        for child in path.rglob("*"):
            if child.is_file() and not child.is_symlink():
                try:
                    modified = max(modified, float(child.stat().st_mtime))
                except OSError:
                    continue
    return modified


def _remove_delivery_kind(project: ProjectSpec, kind: str) -> None:
    if kind not in DELIVERY_KIND_LABELS:
        return
    delivery = store.delivery_directory(project, create=True)
    for candidate in delivery.iterdir():
        if not candidate.is_symlink() and (candidate.is_file() or candidate.is_dir()) and _delivery_kind_for_name(candidate.name) == kind:
            _remove_delivery_path(candidate)
    manifest = _read_delivery_manifest(project)
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    outputs.pop(kind, None)
    manifest["outputs"] = outputs
    manifest["fingerprint"] = _delivery_data_fingerprint(project)
    _write_delivery_manifest(project, manifest)


def _record_delivery_output(project: ProjectSpec, path: Path, kind: str, label: str = "") -> None:
    """Record exactly one physical node (file or managed folder) for each supported delivery type."""
    if kind not in DELIVERY_KIND_LABELS:
        raise ValueError(f"不支持的交付数据类型: {kind}")
    delivery = store.delivery_directory(project, create=True).resolve()
    target = Path(path).resolve()
    if target.parent != delivery:
        raise ValueError("交付物必须直接位于当前模型交付数据文件夹")
    if kind in {"axes_csv_folder", "tables_folder"} and not target.is_dir():
        raise ValueError("表格交付物必须是文件夹")
    if kind not in {"axes_csv_folder", "tables_folder"} and not target.is_file():
        raise ValueError("该交付数据类型必须是文件")
    manifest = _read_delivery_manifest(project)
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    previous = outputs.get(kind) if isinstance(outputs.get(kind), dict) else {}
    previous_name = str(previous.get("name", "") or "")
    if previous_name and previous_name != target.name:
        previous_path = delivery / previous_name
        if previous_path.exists() or previous_path.is_symlink():
            _remove_delivery_path(previous_path)
    # V2.10.3: type is the overwrite key. This also repairs inherited/baseline
    # folders whose delivery manifest is missing or whose canonical filename changed.
    for candidate in list(delivery.iterdir()):
        if candidate.name == target.name or candidate.is_symlink():
            continue
        if (candidate.is_file() or candidate.is_dir()) and _delivery_kind_for_name(candidate.name) == kind:
            _remove_delivery_path(candidate)
    manifest["fingerprint"] = _delivery_data_fingerprint(project)
    outputs[kind] = {
        "name": target.name,
        "label": label or DELIVERY_KIND_LABELS[kind],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "node_type": "directory" if target.is_dir() else "file",
    }
    manifest["outputs"] = outputs
    _write_delivery_manifest(project, manifest)


def _delivery_export_target(project_id: str, project: ProjectSpec, filename: str) -> tuple[Path, str, bool]:
    """Keep temporary edit exports inside the disposable session workspace."""
    if project.lifecycle.status == "baseline" and not core.is_ephemeral(project_id):
        raise HTTPException(status_code=409, detail="基线交付数据已冻结，不能新增、覆盖或删除文件")
    if core.is_ephemeral(project_id):
        directory = core.get(project_id).project_dir / "outputs" / "temporary_delivery"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / filename, f"temporary_delivery/{filename}", False
    destination = store.delivery_directory(project, create=True) / filename
    return destination, f"delivery/{filename}", True


def _current_delivery_outputs(project: ProjectSpec) -> list[dict[str, object]]:
    """Project one newest physical deliverable per managed type; self-heal mutable legacy duplicates."""
    delivery = store.delivery_directory(project, create=True)
    fingerprint = _delivery_data_fingerprint(project)
    manifest = _read_delivery_manifest(project)
    manifest_fingerprint = str(manifest.get("fingerprint", ""))
    outputs = manifest.get("outputs", {}) if isinstance(manifest.get("outputs"), dict) else {}
    mutable = project.lifecycle.status != "baseline"
    manifest_changed = False
    if mutable:
        # Never delete a historical axis-CSV tree. Move it atomically into
        # delivery/表格文件夹, retaining filenames, hierarchy and bytes.
        for path in list(delivery.iterdir()):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                continue
            if _delivery_kind_for_name(path.name) in LEGACY_DELIVERY_KINDS:
                tables = _table_files_directory(project)
                target = tables / path.name
                suffix = 2
                while target.exists():
                    target = tables / f"{path.name}_{suffix}"
                    suffix += 1
                path.replace(target)
                manifest_changed = True
        for legacy_kind in LEGACY_DELIVERY_KINDS:
            if legacy_kind in outputs:
                outputs.pop(legacy_kind, None)
                manifest_changed = True
    # Compute after migration so the newly populated folder is visible now.
    candidates: dict[str, list[Path]] = {kind: [] for kind in DELIVERY_KIND_LABELS}
    for path in delivery.iterdir():
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            continue
        kind = _delivery_kind_for_name(path.name)
        if kind in candidates:
            candidates[kind].append(path)
    items: list[dict[str, object]] = []
    for kind, label in DELIVERY_KIND_LABELS.items():
        group = candidates.get(kind) or []
        record = outputs.get(kind) if isinstance(outputs.get(kind), dict) else {}
        if not group:
            if mutable and kind in outputs:
                outputs.pop(kind, None)
                manifest_changed = True
            continue
        # Physical modified time is the migration fallback when an inherited
        # delivery tree contains multiple same-type nodes without a usable manifest.
        chosen = max(group, key=lambda path: (_delivery_path_modified(path), path.name.casefold()))
        if mutable:
            for extra in group:
                if extra != chosen:
                    _remove_delivery_path(extra)
                    manifest_changed = True
            if str(record.get("name", "")) != chosen.name:
                outputs[kind] = {
                    "name": chosen.name, "label": label,
                    "generated_at": datetime.fromtimestamp(_delivery_path_modified(chosen), tz=timezone.utc).isoformat(),
                    "node_type": "directory" if chosen.is_dir() else "file",
                }
                record = outputs[kind]
                manifest_changed = True
        recorded_name = str(record.get("name", ""))
        recorded_label = str(record.get("label", "") or label)
        freshness_status = "current" if recorded_name == chosen.name and manifest_fingerprint == fingerprint else "stale"
        if kind == "animation_html" and not recorded_name:
            freshness_status = "user"
        items.append({
            "kind": kind, "label": recorded_label, "name": chosen.name,
            "path": f"delivery/{chosen.name}", "relative_path": chosen.name,
            "node_type": "directory" if chosen.is_dir() else "file",
            "file_count": sum(1 for child in chosen.rglob("*") if child.is_file()) if chosen.is_dir() else 1,
            "size": _delivery_path_size(chosen), "modified": _delivery_path_modified(chosen),
            "freshness": freshness_status,
        })
    if mutable and manifest_changed:
        manifest["outputs"] = outputs
        # Do not advance fingerprint while merely reconciling legacy files: an
        # inherited/stale deliverable must not become current just because we de-duplicated it.
        _write_delivery_manifest(project, manifest)
    return sorted(items, key=lambda item: str(item["relative_path"]).casefold())

def _model_table_assets_inventory(project: ProjectSpec) -> list[dict[str, Any]]:
    """Hub-only listing of one physical file per stable logical table identity."""
    folder = store.table_assets_directory(project.id)
    if not folder.is_dir():
        return []
    labels: dict[str, tuple[str, str]] = {}
    for drive in project.drives:
        for segment in drive.segments:
            identity = store.segment_table_identity(drive.id, segment.id)
            for kind, label in (("mapping", "映射表"), ("external_motion", "外部运动表")):
                name = store.table_asset_filename(kind, identity)
                labels[name] = (kind, f"{drive.name} / {segment.name} · {label}")
    for axis in project.result_layout.axes:
        name = store.table_asset_filename("result_axis_csv", str(axis.id))
        labels[name] = ("result_axis_csv", f"{axis.name} · 结果坐标系 CSV")
    for kind, label in (("result_combined_csv", "合并坐标系 CSV"), ("result_table_tsv", "合并坐标系 TSV 表格")):
        labels[store.table_asset_filename(kind, "all")] = (kind, label)
    items: list[dict[str, Any]] = []
    for path in folder.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        try:
            kind, _ = path.name.split("--", 1)
        except ValueError:
            continue
        if kind not in store.TABLE_ASSET_KINDS or path.suffix.lower() not in {".csv", ".tsv"}:
            continue
        if not re.fullmatch(r"[a-f0-9]{64}", path.stem.split("--", 1)[-1]):
            continue
        stat = path.stat()
        type_key, label = labels.get(path.name, (kind, "历史表格资产 · 原驱动/坐标系可能已删除"))
        items.append({
            "name": path.name, "label": label, "kind": type_key,
            "size": stat.st_size, "modified": stat.st_mtime,
            "url": f"/api/projects/{urllib.parse.quote(project.id)}/table-assets/{path.name}",
        })
    return sorted(items, key=lambda entry: (str(entry["kind"]), str(entry["label"]).casefold()))


def _model_file_inventory(project_id: str) -> dict[str, Any]:
    """Project a server-side model folder into the Hub user-facing groups."""
    project = get_project(project_id)
    model_root = store._directory(project_id).resolve()
    project_path = model_root / "project.json"
    assets: list[dict[str, Any]] = []
    assets_root = _mesh_root_path(project_id, project)
    if assets_root.is_dir():
        for path in assets_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in MODEL_ASSET_UPLOAD_EXTENSIONS:
                continue
            relative = path.relative_to(assets_root).as_posix()
            assets.append({
                "name": path.name, "path": relative, "extension": path.suffix.lower(),
                "size": path.stat().st_size, "modified": path.stat().st_mtime,
                "url": f"/api/projects/{project_id}/meshes/file/{relative}",
            })
    # Hub inventory renders names/sizes only; freshness is loaded by the
    # dedicated artifacts view.  Skipping it avoids mesh SHA-256 on every
    # check-in/check-out refresh.
    artifacts = _download_artifacts(project_id, include_freshness=False)
    delivery = _current_delivery_outputs(project)
    derived = [item for item in artifacts if item.get("kind") == "artifact"]
    inventory = {
        "project_id": project_id,
        "model_directory": str(model_root.relative_to(store.projects_root.resolve())),
        "project_json": {
            "name": "project.json", "path": "project.json", "size": project_path.stat().st_size,
            "modified": project_path.stat().st_mtime,
            "url": f"/api/projects/{project_id}/files/project-json",
        },
        "model_assets": sorted(assets, key=lambda item: str(item["path"]).casefold()),
        "time_series_library": _time_series_library_items(project),
        "table_assets": _model_table_assets_inventory(project),
        "table_assets_directory": "assets/tables",
        "time_series_directory": "时序库",
        "delivery_outputs": delivery,
        "delivery_directories": sorted([
            path.relative_to(store.delivery_directory(project, create=True)).as_posix()
            for path in store.delivery_directory(project, create=True).rglob("*") if path.is_dir()
        ], key=str.casefold),
        "derived_outputs": derived,
        "mesh_root": project.mesh_root,
        "server_managed_mesh_root": bool(str(project.mesh_root).strip()),
    }
    if active_identity().role == "guest":
        # Guest Hub needs only frozen baseline delivery metadata. Do not project
        # project.json, mesh assets or derived outputs into the guest surface.
        return {
            "project_id": project_id, "model_directory": "", "project_json": None,
            "model_assets": [], "time_series_library": [], "time_series_directory": "",
            "table_assets": [], "table_assets_directory": "",
            "delivery_outputs": delivery,
            "delivery_directories": inventory["delivery_directories"], "derived_outputs": [],
            "mesh_root": "", "server_managed_mesh_root": False,
        }
    return inventory


@app.get("/api/projects/{project_id}/files")
def list_project_files(project_id: str) -> dict[str, Any]:
    return _model_file_inventory(project_id)


@app.get("/api/projects/{project_id}/table-assets/{filename}")
def download_table_asset(project_id: str, filename: str):
    project = get_project(project_id)
    if active_identity().role == "guest":
        raise HTTPException(status_code=403, detail="表格资产仅供授权工程师和管理员查看")
    if not re.fullmatch(r"(?:mapping|external_motion|result_axis_csv|result_combined_csv|result_table_tsv)--[a-f0-9]{64}\.(?:csv|tsv)", filename):
        raise HTTPException(status_code=404, detail="表格资产不存在")
    folder = store.table_assets_directory(project_id)
    path = folder / filename
    if path.is_symlink() or not path.is_file() or path.resolve().parent != folder.resolve():
        raise HTTPException(status_code=404, detail="表格资产不存在")
    return FileResponse(path, filename=filename, media_type="text/tab-separated-values" if filename.endswith(".tsv") else "text/csv")


@app.post("/api/projects/{project_id}/time-series/save", status_code=201)
def save_named_time_series(project_id: str, request: TimeSeriesSaveRequest) -> dict[str, Any]:
    """Publish the current drive configuration as a TSJSON v2 snapshot.

    This intentionally works before any simulation result exists: channels=[]
    means no simulated curves were claimed. Reuse ProjectSpec, TSJSON codec and
    the model's existing library rather than adding a parallel time-series tool.
    """
    project = get_project(project_id)
    _require_editable(project)
    if core.is_ephemeral(project_id):
        raise HTTPException(status_code=409, detail="临时编辑不允许发布正式时序")
    if not project.drives:
        raise HTTPException(status_code=422, detail='当前模型尚无驱动，无法保存可切换的时序')
    label = request.name.strip()
    if not label or any(ord(char) < 32 for char in label):
        raise HTTPException(status_code=422, detail="请输入有效的时序名称")
    safe_stem = safe_csv_stem(label, "时序")
    # Respect filesystem byte limits for long CJK labels (NTFS/ext4 portable).
    prefix = ""
    for char in safe_stem:
        if len((prefix + char).encode("utf-8")) > 160:
            break
        prefix += char
    prefix = prefix.strip(" ._") or "时序"
    # Unique storage names protect earlier checkpoints; never silently overwrite.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{prefix}--{stamp}_{uuid4().hex[:6]}.tsjson"
    _, content = build_tsjson_bundle(project, [])
    library = store.time_series_directory(project, create=True).resolve()
    if request.overwrite_filename:
        selected = Path(request.overwrite_filename).name
        target = (library / selected).resolve()
        if (selected != request.overwrite_filename or target.parent != library
                or target.suffix.lower() != '.tsjson' or not target.is_file()):
            raise HTTPException(status_code=404, detail='指定覆盖的时序文件不存在')
        filename = selected
    atomic_write_text(library / filename, content, encoding="utf-8")
    vz_sync: dict[str, Any] = {"synced": False, "reason": "vz_push_disabled"}
    if bool(_vz_status_for_project(project).get("enabled")):
        try:
            vz_sync = _vz_sync_time_series_library(project)
        except VZIntegrationError as exc:
            vz_sync = {"synced": False, "error": str(exc)}
    return {"filename": filename, "name": label, "drive_count": len(project.drives),
            "url": f"/api/projects/{project.id}/time-series/{urllib.parse.quote(filename)}",
            "vz_sync": vz_sync}


@app.get("/api/projects/{project_id}/time-series/{filename}")
def download_time_series_file(project_id: str, filename: str):
    project = get_project(project_id)
    root = store.time_series_directory(project, create=True).resolve()
    safe_name = Path(filename).name
    target = (root / safe_name).resolve()
    if target.parent != root or target.suffix.lower() != ".tsjson" or not target.is_file():
        raise HTTPException(status_code=404, detail="时序库 TSJSON 不存在")
    return FileResponse(target, media_type="application/json; charset=utf-8", filename=target.name)


@app.delete("/api/projects/{project_id}/time-series/{filename}")
def delete_time_series_file(project_id: str, filename: str) -> dict[str, Any]:
    project = get_project(project_id)
    _require_mutable_delivery(project)
    root = store.time_series_directory(project, create=True).resolve()
    safe_name = Path(filename).name
    target = (root / safe_name).resolve()
    if target.parent != root or target.suffix.lower() != ".tsjson" or not target.is_file():
        raise HTTPException(status_code=404, detail="时序库 TSJSON 不存在")
    target.unlink()
    sync_result: dict[str, Any] = {"synced": False, "reason": "vz_push_disabled"}
    if bool(_vz_status_for_project(project).get("enabled")):
        try:
            sync_result = _vz_sync_time_series_library(project)
        except VZIntegrationError as exc:
            sync_result = {"synced": False, "error": str(exc)}
    return {"deleted": safe_name, "files": _model_file_inventory(project_id), "vz_sync": sync_result}


@app.post("/api/projects/{project_id}/time-series/parse")
def parse_time_series_for_project(project_id: str, request: TimeSeriesParseRequest) -> dict[str, Any]:
    project = get_project(project_id)
    content = request.content
    filename = str(request.filename or request.server_filename or "时序.csv")
    source_project = project
    if request.server_filename:
        source_id = str(request.source_project_id or project_id)
        # get_project invokes the original per-project read ACL, including
        # frozen baseline and lease isolation. Never trust a client-side list.
        source_project = project if source_id == project_id else get_project(source_id)
        root = store.time_series_directory(source_project, create=False).resolve()
        safe_name = Path(request.server_filename).name
        target = root / safe_name
        if (safe_name != request.server_filename or target.is_symlink() or
                target.suffix.lower() != ".tsjson" or not target.is_file() or
                target.resolve().parent != root):
            raise HTTPException(status_code=404, detail="所选服务端时序 TSJSON 不存在")
        if target.stat().st_size > 128 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="时序 TSJSON 不得超过 128 MiB")
        filename = target.name
        content = target.read_text("utf-8-sig")
    if content is None:
        raise HTTPException(status_code=422, detail="请选择本地 CSV 或服务端时序库 CSV")
    if len(content.encode("utf-8")) > 128 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="时序 CSV 不得超过 128 MiB")
    if is_mapping_table_name(filename):
        raise HTTPException(status_code=422, detail="映射表格是伴生文件，请选择 TSJSON 或主时序 CSV")
    if request.source_project_id and not request.server_filename:
        raise HTTPException(status_code=422, detail="跨模型时序必须从已授权的模型时序库选择文件")
    try:
        parsed = (parse_tsjson(content, project,
                    joint_mapping=request.joint_mapping,
                    require_joint_match=bool(request.server_filename and request.source_project_id and
                                             request.source_project_id != project_id),
                    source_joint_names={str(j.id): str(j.name) for layer in source_project.layers
                                        for j in layer.joints})
                  if filename.lower().endswith(".tsjson")
                  else parse_exported_timing(content, filename, project, request.joint_mapping) if filename.lower().endswith((".html", ".py"))
                  else parse_time_series_csv(content, project))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"filename": filename, **parsed}


@app.get("/api/projects/{project_id}/files/project-json")
def download_project_file(project_id: str):
    get_project(project_id)
    return FileResponse(
        store._directory(project_id) / "project.json", media_type="application/json",
        filename="project.json",
    )


@app.put("/api/projects/{project_id}/files/project-json")
async def replace_project_file(project_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    current = get_project(project_id)
    _require_editable(current)
    payload = await file.read(MAX_PROJECT_JSON_BYTES + 1)
    if len(payload) > MAX_PROJECT_JSON_BYTES:
        raise HTTPException(status_code=413, detail="project.json 不能超过 20 MiB")
    try:
        data = json.loads(payload.decode("utf-8-sig"))
        if isinstance(data, dict) and isinstance(data.get("state"), dict):
            data = data["state"].get("project", data["state"])
        incoming = ProjectSpec.model_validate(data)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"project.json 无效：{exc}") from exc
    if incoming.id != project_id:
        raise HTTPException(status_code=409, detail="上传文件中的模型 id 与当前模型不一致")
    # Folder placement and checkout ownership are server concerns and cannot be
    # forged by replacing a JSON document through the browser.
    incoming.category = current.category
    incoming.lifecycle = current.lifecycle
    incoming.mesh_root = current.mesh_root
    for key in ("version_date", "version_index", "version_source_project_id"):
        if key in current.metadata:
            incoming.metadata[key] = current.metadata[key]
    updated = update_project(project_id, incoming)
    return {"project": updated.model_dump(), "files": _model_file_inventory(project_id)}


@app.get("/api/projects/{project_id}/files/assets/{asset_path:path}")
def download_project_asset(project_id: str, asset_path: str):
    get_project(project_id)
    root = (store._directory(project_id) / "assets").resolve()
    target = (root / asset_path).resolve()
    if root not in target.parents or not target.is_file() or target.suffix.lower() not in MODEL_ASSET_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=404, detail="Model asset not found")
    return FileResponse(target, filename=target.name)


def _artifact_context(project_id: str, limit: int = 12, budget: int = 18_000) -> list[dict[str, Any]]:
    root = store._directory(project_id)
    output: list[dict[str, Any]] = []
    remaining = budget
    readable = {".json", ".csv", ".xml", ".txt", ".md", ".log"}
    for item in _download_artifacts(project_id)[:limit]:
        entry: dict[str, Any] = dict(item)
        path = root / str(item["path"])
        if remaining > 0 and path.suffix.lower() in readable:
            try:
                content = path.read_text("utf-8", errors="replace")[:min(4000, remaining)]
                entry["content_excerpt"] = content
                remaining -= len(content)
            except OSError:
                pass
        output.append(entry)
    return output


def _resolved_variable_context(project_id: str) -> dict[str, Any]:
    project = core.get(project_id).project()
    try:
        resolved, schedule = resolve_schedule(project)
        return {**project.variables, **resolved, "EndTime": latest_drive_stop_time(schedule, project.simulation.start_time)}
    except (ValueError, TypeError) as exc:
        return {**project.variables, "resolution_error": str(exc)}


def _assistant_variable_index(project_id: str) -> list[dict[str, Any]]:
    """Build a stable, searchable index over project and UI state."""
    instance = core.get(project_id)
    rows = [{**item, "path": f"project.{item['path']}"} for item in parameter_catalog(instance.project())]

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                token = f"@{child['id']}" if isinstance(child, dict) and isinstance(child.get("id"), str) else str(index)
                visit(child, f"{path}.{token}")
        else:
            rows.append({"path": path, "index_path": None, "value": value,
                         "type": type(value).__name__, "aliases": [], "writable": True})

    visit(instance.state.snapshot().get("ui", {}), "ui")
    return rows


def _search_assistant_variables(project_id: str, query: str = "", limit: int = 300) -> list[dict[str, Any]]:
    rows = _assistant_variable_index(project_id)
    terms = [item.lower() for item in re.findall(r"[\w\u4e00-\u9fff.-]+", query) if len(item) > 1]
    if terms:
        def rank(item: dict[str, Any]) -> tuple[int, str]:
            text = f"{item['path']} {item.get('value', '')} {' '.join(item.get('aliases', []))}".lower()
            return (-sum(term in text for term in terms), str(item["path"]))
        rows = sorted(rows, key=rank)
    return rows[:min(max(limit, 1), 2000)]


@app.get("/api/projects/{project_id}/assistant/variables")
def assistant_variables(project_id: str, q: str = "", limit: int = 300) -> dict[str, Any]:
    get_project(project_id)
    all_rows = _assistant_variable_index(project_id)
    return {"total": len(all_rows), "query": q, "items": _search_assistant_variables(project_id, q, limit)}


def _validated_assistant_proposal(project_id: str, raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("commands"), list):
        return None
    commands = []
    for item in raw["commands"][:20]:
        if not isinstance(item, dict) or item.get("tool_id") not in {"param.set", "ui.set"}:
            continue
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        path = str(params.get("path", ""))
        if item["tool_id"] == "param.set" and not path.startswith("project."):
            continue
        if item["tool_id"] == "ui.set" and not path.startswith("ui."):
            continue
        commands.append({"tool_id": item["tool_id"], "params": params, "client": "llm_agent"})
    if not commands:
        return None
    instance = core.get(project_id)
    changeset = instance.changesets.create(
        str(raw.get("title") or "LLM 操作建议")[:120], commands, "llm_agent", str(raw.get("rationale") or "")[:2000] or None,
    )
    return {"changeset": changeset.to_dict(), "dry_run": instance.changesets.dry_run(changeset.id, instance.bus)}


@app.post("/api/projects/{project_id}/assistant/stream")
def assistant_stream(project_id: str, request: AssistantStreamRequest) -> StreamingResponse:
    project = get_project(project_id)
    conversation = _conversation(project_id)
    history = conversation.context(project.agent_settings.context_rounds)
    user_message = request.message.strip()
    conversation.append("user", user_message, source="global_assistant")
    variables = _search_assistant_variables(project_id, user_message, 600)
    variable_text = json.dumps(variables, ensure_ascii=False, separators=(",", ":"), default=str)
    system = (
        "你是 MuJoCo Studio 全局工程助手。先用自然语言回答；若需要改变状态，不得声称已执行，"
        "只能在回答末尾输出一个 <proposal>{JSON}</proposal>。JSON 格式为"
        "{\"title\":\"...\",\"rationale\":\"...\",\"commands\":[{\"tool_id\":\"param.set|ui.set\","
        "\"params\":{\"path\":\"project.*|ui.*\",\"value\":...}}]}。param.set 仅改 project.*，ui.set 仅改 ui.*。"
        "必须使用索引中的稳定路径；不确定时先询问，不生成操作。用户必须审阅并点击执行后才会提交。\n"
        f"当前变量索引（总计 {len(_assistant_variable_index(project_id))} 项，已按问题检索）：{variable_text}"
    )
    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": user_message}]

    def event(payload: dict[str, Any]) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def generate():
        marker = "<proposal>"
        tail = ""
        proposal_text = ""
        visible_parts: list[str] = []
        in_proposal = False
        try:
            for chunk in chat_completion_stream(project.agent_settings, llm_credentials.api_key(), messages, timeout=120):
                if in_proposal:
                    proposal_text += chunk
                    continue
                tail += chunk
                position = tail.find(marker)
                if position >= 0:
                    visible = tail[:position]
                    if visible:
                        visible_parts.append(visible)
                        yield event({"type": "token", "text": visible})
                    proposal_text = tail[position + len(marker):]
                    tail = ""
                    in_proposal = True
                    continue
                safe_length = max(0, len(tail) - len(marker) + 1)
                if safe_length:
                    visible = tail[:safe_length]
                    tail = tail[safe_length:]
                    visible_parts.append(visible)
                    yield event({"type": "token", "text": visible})
            if not in_proposal and tail:
                visible_parts.append(tail)
                yield event({"type": "token", "text": tail})
            visible_answer = "".join(visible_parts).strip()
            if in_proposal:
                proposal_text = proposal_text.split("</proposal>", 1)[0].strip()
                try:
                    proposal = _validated_assistant_proposal(project_id, json.loads(proposal_text))
                    if proposal:
                        yield event({"type": "proposal", **proposal})
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    yield event({"type": "proposal_error", "message": f"操作建议无法校验：{exc}"})
            conversation.append("assistant", visible_answer, source="global_assistant")
            yield event({"type": "done"})
        except GeneratorExit:
            raise
        except Exception as exc:  # noqa: BLE001
            yield event({"type": "error", "message": str(exc)})

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/projects/{project_id}/llm-config")
def get_llm_config(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    return {**project.agent_settings.model_dump(), "credential": llm_credentials.status()}


@app.put("/api/projects/{project_id}/llm-config")
def update_llm_config(project_id: str, request: LLMConfigRequest) -> dict[str, Any]:
    with core.acquire(project_id) as instance:
        identity = require_project_access(instance.project(), write=True)
        settings = request.model_dump(exclude={"api_key"})
        result = instance.bus.dispatch({
            "tool_id": "param.set", "params": {
                "path": "project.agent_settings", "value": settings,
                "intent": "配置 OpenAI 兼容大模型与上下文范围",
            }, "actor": identity.username, "client": "human_ui",
        })
        if not result.ok:
            raise HTTPException(status_code=422, detail=result.errors)
        if request.api_key is not None:
            llm_credentials.save(request.api_key)
        return {**instance.project().agent_settings.model_dump(), "credential": llm_credentials.status()}


@app.post("/api/projects/{project_id}/llm-test")
def test_llm_connection(project_id: str) -> dict[str, Any]:
    settings = get_project(project_id).agent_settings
    try:
        content = chat_completion(settings, llm_credentials.api_key(), [
            {"role": "system", "content": "你是 MuJoCo Studio 连接测试助手。"},
            {"role": "user", "content": "请只回复：连接成功"},
        ], timeout=30)
        return {"ok": True, "model": settings.model, "response": content[:500]}
    except Exception as exc:  # noqa: BLE001 - expose a user-actionable connection error
        raise HTTPException(status_code=422, detail=f"大模型连接失败：{exc}") from exc


@app.get("/api/projects/{project_id}/agent-conversation")
def get_agent_conversation(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    items = _conversation(project_id).list()
    return {"context_rounds": project.agent_settings.context_rounds, "messages": items[-project.agent_settings.context_rounds * 2:]}


@app.get("/api/skills")
def list_skills() -> list[SkillDefinition]:
    return skills.list()


@app.post("/api/skills", status_code=201)
def create_skill(skill: SkillDefinition) -> SkillDefinition:
    try:
        return skills.save(skill)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/agent-runs", status_code=202)
def run_agent(project_id: str, request: AgentRunRequest) -> dict[str, str]:
    project = get_project(project_id)
    fingerprint = _fingerprint(project_id, project)
    try:
        skills.get(request.skill_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc

    def task(progress, cancelled, workspace, job_id):
        context = AgentContext(
            project=project,
            store=store,
            result_root=workspace,
            progress=progress,
            should_cancel=cancelled,
            current_project=lambda: core.get(project_id).project(),
            operation_log=lambda: _operation_context(project_id),
            artifact_context=lambda: _artifact_context(project_id),
            resolved_variables=lambda: _resolved_variable_context(project_id),
            conversation=_conversation(project_id),
        )
        result = agent.run(context, request.skill_id, request.goal)
        if cancelled():
            raise InterruptedError("Agent 运行已取消，未发布部分结果")
        published = _publish_result_directory(
            project_id=project_id, project=project, kind="agent", job_id=job_id,
            workspace=workspace, result=result,
            parameters={"skill_id": request.skill_id, "goal": request.goal}, fingerprint=fingerprint,
        )
        if not core.is_ephemeral(project_id):
            core.drop(project_id)
        return published

    return {"job_id": _submit_project_job(project_id, "agent", task)}


@app.get("/api/projects/{project_id}/artifacts")
def list_artifacts(project_id: str) -> list[dict[str, object]]:
    project = get_project(project_id)
    artifacts = _download_artifacts(project_id)
    if active_identity().role == "guest":
        html = [item for item in artifacts if str(item.get("path", "")).casefold().endswith(".html")]
        delivery_html = [
            item for item in _current_delivery_outputs(project)
            if str(item.get("kind", "")) == "animation_html"
        ]
        return [*html, *delivery_html]
    return artifacts


_delivery_refresh_submission_gate = threading.RLock()


@app.post("/api/projects/{project_id}/delivery-files/refresh", status_code=202)
def refresh_project_delivery_files(project_id: str) -> Response:
    """Rebuild four managed deliverables in the existing heavy JobManager lane.

    Animation HTML, model table assets, CSV/TSV and immutable baseline trees
    are never regenerated or overwritten by this action.  The Hub remains
    responsive even if a large Gantt/NX export must wait for native work.
    """
    identity = active_identity()
    source = get_project(project_id)
    require_project_access(source, write=True)
    _require_mutable_delivery(source)
    if core.is_ephemeral(project_id):
        raise HTTPException(status_code=409, detail="临时预览不能刷新正式交付目录")

    def task(progress, cancelled, _workspace, _job_id):
        token = set_active_identity(identity)
        try:
            progress(0.08, "正在读取当前模型与冻结仿真结果")
            with core.acquire(project_id) as instance:
                project = instance.project()
                require_project_access(project, write=True)
                _require_mutable_delivery(project)
                if cancelled():
                    raise InterruptedError("交付数据刷新已取消")
                result = _refresh_baseline_delivery_outputs(
                    project, instance.export_json(), require_animation_html=False,
                    should_cancel=cancelled, progress=progress,
                )
            progress(0.99, "交付数据已更新（动画 HTML 与表格未改动）")
            return {"project_id": project_id, **result}
        finally:
            reset_active_identity(token)

    with _delivery_refresh_submission_gate:
        job_id = _submit_project_job(project_id, "delivery_refresh", task, timeout_seconds=1800)
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "queued"})


@app.delete("/api/projects/{project_id}/delivery-files")
def clear_delivery_files(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    _require_mutable_delivery(project)
    delivery = store.delivery_directory(project, create=True).resolve()
    deleted = sum(1 for item in delivery.rglob("*") if item.is_file())
    for child in list(delivery.iterdir()):
        if child.is_symlink() or child.is_file():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            shutil.rmtree(child)
    return {"ok": True, "deleted": deleted}


@app.delete("/api/projects/{project_id}/delivery-files/{delivery_path:path}")
def delete_delivery_file(project_id: str, delivery_path: str) -> dict[str, Any]:
    project = get_project(project_id)
    _require_mutable_delivery(project)
    delivery = store.delivery_directory(project, create=True).resolve()
    raw = urllib.parse.unquote(str(delivery_path or "")).replace("\\", "/").removeprefix("delivery/")
    relative = Path(raw)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise HTTPException(status_code=422, detail="交付物路径无效")
    target = (delivery / relative).resolve()
    if delivery not in target.parents or not (target.is_file() or target.is_dir()):
        raise HTTPException(status_code=404, detail="交付物不存在")
    _remove_delivery_path(target)
    parent = target.parent
    while parent != delivery and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent
    manifest = _read_delivery_manifest(project)
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    for kind, record in list(outputs.items()):
        if isinstance(record, dict) and str(record.get("name", "")) == relative.parts[0]:
            outputs.pop(kind, None)
    manifest["outputs"] = outputs
    _write_delivery_manifest(project, manifest)
    return {"ok": True, "path": relative.as_posix()}


@app.get("/api/projects/{project_id}/delivery-folder.zip")
def download_delivery_folder(project_id: str, subdir: str = Query(default="")):
    """Package the complete delivery folder, or one managed delivery subfolder, as ZIP."""
    project = get_project(project_id)
    delivery = store.delivery_directory(project, create=True).resolve()
    source = delivery
    safe_name = _safe_filename(project.name) or project.id
    archive_name = f"{safe_name}_交付数据.zip"
    if subdir:
        raw = urllib.parse.unquote(str(subdir)).replace("\\", "/").removeprefix("delivery/")
        relative = Path(raw)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise HTTPException(status_code=422, detail="交付文件夹路径无效")
        candidate = (delivery / relative).resolve()
        if delivery not in candidate.parents or not candidate.is_dir():
            raise HTTPException(status_code=404, detail="交付文件夹不存在")
        source = candidate
        archive_name = f"{_safe_filename(candidate.name)}.zip"

    fd, temporary_name = tempfile.mkstemp(prefix=f"delivery_{project_id}_", suffix=".zip")
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for path in sorted(source.rglob("*"), key=lambda item: item.as_posix().casefold()):
                relative = path.relative_to(source)
                if path.is_dir():
                    if not any(path.iterdir()):
                        archive.writestr(relative.as_posix().rstrip("/") + "/", b"")
                    continue
                if path.is_file():
                    archive.write(path, relative.as_posix())
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    def stream_archive():
        try:
            with temporary.open("rb") as stream:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            temporary.unlink(missing_ok=True)

    encoded_name = urllib.parse.quote(archive_name)
    return StreamingResponse(
        stream_archive(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@app.get("/api/projects/{project_id}/artifacts/{artifact_path:path}")
def download_artifact(project_id: str, artifact_path: str):
    ephemeral = core.is_ephemeral(project_id)
    instance = core.get(project_id)
    root = store._directory(project_id)
    project = get_project(project_id)
    delivery = store.delivery_directory(project)
    if ephemeral and artifact_path.startswith("temporary_delivery/"):
        temporary_delivery = (instance.project_dir / "outputs" / "temporary_delivery").resolve()
        target = (temporary_delivery / artifact_path.removeprefix("temporary_delivery/")).resolve()
        if not (target.parent == temporary_delivery or temporary_delivery in target.parents) or not target.is_file():
            raise HTTPException(status_code=404, detail="Artifact not found")
        return FileResponse(target)
    target = (delivery / artifact_path.removeprefix("delivery/")).resolve() if artifact_path.startswith("delivery/") else (root / artifact_path).resolve()
    allowed_roots = [(root / name).resolve() for name in ("outputs", "results", "core/artifacts")]
    delivery_attachment = delivery in target.parents
    if active_identity().role == "guest" and not delivery_attachment and target.suffix.casefold() not in {".html", ".htm"}:
        raise HTTPException(status_code=403, detail="游客只能查看动画 HTML 或下载基线交付数据")
    if not (any(folder == target.parent or folder in target.parents for folder in allowed_roots) or delivery_attachment) or not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(target)


def _gantt_cache_paths(project_id: str, *, create: bool = False) -> tuple[Path, Path, Path]:
    root = store._directory(project_id)
    cache_dir = root / "core" / "artifacts" / "gantt_cache"
    if create:
        cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir, cache_dir / "latest_gantt.png", cache_dir / "latest_gantt.json"


class GanttCacheWriteRequest(BaseModel):
    image_data: str = Field(
        ...,
        max_length=20_971_520,
        description="Base64 encoded PNG bytes without data-uri prefix (maximum encoded size: 20 MiB)",
    )
    metadata: dict[str, Any] | None = None


@app.post("/api/projects/{project_id}/gantt-cache")
def write_gantt_cache(project_id: str, payload: GanttCacheWriteRequest):
    get_project(project_id)
    try:
        import base64
        png_bytes = base64.b64decode(payload.image_data, validate=True)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=f"Invalid PNG base64: {exc}") from None
    if not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=400, detail="Gantt cache must be a PNG image")
    if len(png_bytes) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Gantt cache PNG exceeds the 15 MiB limit")
    cache_dir, cache_png, cache_json = _gantt_cache_paths(project_id, create=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    temp_png = cache_dir / f".latest_gantt_{stamp}.png"
    temp_json = cache_dir / f".latest_gantt_{stamp}.json"
    try:
        temp_png.write_bytes(png_bytes)
        metadata = dict(payload.metadata or {})
        metadata.setdefault("format", "MUJOCO_STUDIO_GANTT_CACHE")
        metadata.setdefault("format_version", 1)
        metadata["saved_at"] = datetime.now().timestamp()
        metadata["image_width"] = metadata.get("scene_width") or metadata.get("image_width") or 0
        metadata["image_height"] = metadata.get("scene_height") or metadata.get("image_height") or 0
        temp_json.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        # V2.8.15: use atomic_replace so a transient Windows sharing hold
        # (AV / Explorer thumbnails / watchers) cannot kill the publish.
        atomic_replace(temp_png, cache_png)
        atomic_replace(temp_json, cache_json)
    finally:
        for p in (temp_png, temp_json):
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass
    return {
        "cache_png": f"core/artifacts/gantt_cache/latest_gantt.png",
        "cache_json": f"core/artifacts/gantt_cache/latest_gantt.json",
        "saved_at": metadata["saved_at"],
    }


@app.get("/api/projects/{project_id}/gantt-cache")
def read_gantt_cache(project_id: str):
    get_project(project_id)
    cache_dir, cache_png, cache_json = _gantt_cache_paths(project_id)
    if not cache_png.is_file():
        return {"png": None, "json": None, "saved_at": None}
    metadata: dict[str, Any] | None = None
    saved_at: float | None = None
    if cache_json.is_file():
        try:
            metadata = json.loads(cache_json.read_text(encoding="utf-8"))
            saved_at = float(metadata.get("saved_at") or 0) or None
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            metadata = None
    png_stat = cache_png.stat()
    return {
        "png": f"/api/projects/{project_id}/artifacts/core/artifacts/gantt_cache/latest_gantt.png",
        "json": metadata,
        "saved_at": saved_at or png_stat.st_mtime,
        "size": png_stat.st_size,
    }


def _client_ticket_header(request: Request) -> str:
    value = str(request.headers.get("X-MuJoCo-Client-Ticket", "")).strip()
    if not value:
        raise HTTPException(410, "客户端票据不存在、已使用或已过期")
    return value


def _ticket_identity(item: dict[str, Any]) -> Identity:
    return Identity(
        username=str(item["username"]),
        role=str(item["role"]),
        session_id=str(item.get("session_id", "client-ticket")),
        lease_id=str(item["lease_id"]),
    )


def _consume_client_ticket(request: Request, purpose: str) -> tuple[dict[str, Any], Identity]:
    try:
        item = client_tickets.consume(_client_ticket_header(request), purpose)
    except ClientTicketError as exc:
        raise HTTPException(410, str(exc)) from exc
    identity = _ticket_identity(item)
    _verify_ticket_context(item, identity)
    return item, identity


def _verify_ticket_context(item: dict[str, Any], identity: Identity) -> None:
    if not SINGLE_USER:
        live = auth.sessions.get(identity.session_id)
        if live is None or live.lease_id != identity.lease_id or live.username.casefold() != identity.username.casefold():
            raise HTTPException(410, {"code": "ticket_context_invalid", "reason": "session_expired"})


def _select_project_mesh_directory(project_id: str, project: ProjectSpec, target_root: Path) -> ProjectSpec:
    project.mesh_root = store.relative_mesh_root(project_id, target_root)
    repair_mesh_references(project, list_mesh_files(target_root))
    repair_joint_references(project)
    with core.acquire(project_id) as instance:
        result = instance.bus.dispatch({
            "tool_id": "project.asset_selection",
            "params": {
                "project": project.model_dump(),
                "selection_id": target_root.name,
                "intent": "本地客户端同步或回退服务端托管数模版本",
            },
            "actor": active_identity().username, "client": "script",
        })
        if not result.ok:
            raise HTTPException(422, result.errors)
        return instance.project()


def _copy_admin_mesh_directory(source_root: Path, target_root: Path) -> list[str]:
    """Copy one administrator-selected host folder into an isolated managed version."""
    if not source_root.is_dir():
        raise HTTPException(422, "所选本机数模路径不存在或不是文件夹")
    copied_meshes: list[str] = []
    copied_count = 0
    total_size = 0
    for source in source_root.rglob("*"):
        if source.is_symlink():
            raise HTTPException(422, "本机数模路径不能包含符号链接")
        if not source.is_file() or source.suffix.lower() not in MODEL_ASSET_UPLOAD_EXTENSIONS:
            continue
        copied_count += 1
        if copied_count > 10000:
            raise HTTPException(413, "本机数模文件数量不能超过 10000")
        file_size = source.stat().st_size
        if file_size > MAX_MODEL_ASSET_BYTES:
            raise HTTPException(413, f"模型资产过大：{source.name}")
        total_size += file_size
        if total_size > MAX_MODEL_UPLOAD_BYTES:
            raise HTTPException(413, "本次数模同步总量不能超过 8 GiB")
        relative = source.relative_to(source_root)
        destination = (target_root / relative).resolve()
        if target_root.resolve() not in destination.parents:
            raise HTTPException(422, "本机数模路径越界")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as input_stream, destination.open("wb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
        if source.suffix.lower() in SUPPORTED_MESH_EXTENSIONS:
            copied_meshes.append(relative.as_posix())
    if not copied_meshes:
        raise HTTPException(422, "本机路径中没有可同步的 STL 或 OBJ 文件")
    return copied_meshes


@app.post("/api/projects/{project_id}/admin-local-mesh-sync")
def admin_local_mesh_sync(project_id: str, request: AdminMeshSyncRequest) -> dict[str, Any]:
    """Let the built-in administrator import a host folder without the local client."""
    identity = active_identity()
    if identity.role != "admin":
        raise HTTPException(403, "只有管理员账号可以绕过客户端直接同步本机数模")
    project = get_project(project_id)
    _require_editable(project)
    _require_mutable_mesh_assets(project)
    source_root = Path(os.path.expandvars(os.path.expanduser(request.path))).resolve()
    if str(project.mesh_root).startswith("@model_assets/"):
        target_root = store.resolve_model_asset_reference(project.mesh_root, create=True)
    else:
        folder_name, suffix = source_root.name or "本地同步数模", 2
        while True:
            try:
                reference, target_root = store.create_model_asset_folder(project.category, folder_name)
                project.mesh_root = reference
                break
            except ValueError as exc:
                if "已存在" not in str(exc): raise HTTPException(422, str(exc)) from exc
                folder_name = f"{source_root.name or '本地同步数模'}_{suffix}"; suffix += 1
    copied_meshes = _copy_admin_mesh_directory(source_root, target_root)
    project.mesh_root = project.mesh_root if str(project.mesh_root).startswith("@model_assets/") else store.model_asset_reference(project.category, target_root.name)
    repair_mesh_references(project, list_mesh_files(target_root)); repair_joint_references(project)
    with core.acquire(project_id) as instance:
        result = instance.bus.dispatch({"tool_id":"project.asset_selection", "params":{"project":project.model_dump(), "asset_folder_path":project.mesh_root, "intent":"管理员同步到公共数模资产文件夹"}, "actor":identity.username, "client":"script"})
        if not result.ok: raise HTTPException(422, result.errors)
        project = instance.project()
    return {"ok": True, "source_path": str(source_root), "project": project.model_dump(),
            "files": list_mesh_files(target_root), "uploaded_meshes": copied_meshes,
            "folders": store.list_model_asset_folders(project.category)}


@app.post("/api/projects/{project_id}/client-ticket", status_code=201)
def issue_client_ticket(project_id: str, request: ClientTicketRequest) -> dict[str, Any]:
    identity = active_identity()
    if identity.role not in {"engineer", "admin"}:
        raise HTTPException(403, "无权限，请联系管理员开通权限")
    if request.purpose not in {"mesh_sync", "viewer_launch", "select_mesh_path"}:
        raise HTTPException(422, "不支持的客户端任务")
    project = get_project(project_id)
    if request.purpose == "mesh_sync":
        _require_editable(project)
        _require_mutable_mesh_assets(project)
    try:
        ticket = client_tickets.issue(
            project_id=project_id,
            purpose=request.purpose,
            username=identity.username,
            role=identity.role,
            lease_id=identity.lease_id,
            session_id=identity.session_id,
        )
    except ClientTicketError as exc:
        if str(exc) == "client_ticket_rate_limited":
            raise HTTPException(429, {"code": str(exc), "message": "客户端票据签发过于频繁", "retry_after": 60}) from exc
        raise HTTPException(422, str(exc)) from exc
    return {"ticket": ticket, "purpose": request.purpose, "expires_in_seconds": 60}


@app.post("/api/client/authorize")
async def authorize_client_action(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(422, {"code": "invalid_request", "message": "请求体必须是 JSON"}) from exc
    purpose = str(payload.get("purpose", ""))
    if purpose != "select_mesh_path":
        raise HTTPException(422, {"code": "purpose_mismatch", "message": "不支持的客户端授权用途"})
    item, _identity = _consume_client_ticket(request, purpose)
    return {"ok": True, "project_id": item["project_id"], "purpose": purpose}


@app.post("/api/client/mesh-sync")
async def client_mesh_sync(request: Request) -> dict[str, Any]:
    item, identity = _consume_client_ticket(request, "mesh_sync")
    token = set_active_identity(identity)
    target_root: Path | None = None
    upload_path: Path | None = None
    try:
        project_id = str(item["project_id"])
        project = get_project(project_id)
        require_project_access(project, write=True)
        _require_editable(project)
        _require_mutable_mesh_assets(project)
        if project.category == "None":
            raise HTTPException(409, "模型必须先归入一个模型类型才能同步公共数模资产")
        extract_root = store._directory(project_id) / "assets" / f".client-mesh-upload-{uuid4().hex}"
        extract_root.mkdir(parents=True, exist_ok=False)
        target_root = extract_root
        upload_path = extract_root.parent / f".{extract_root.name}.zip"
        total = 0
        with upload_path.open("wb") as stream:
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_MODEL_UPLOAD_BYTES:
                    raise HTTPException(413, "本次数模同步不能超过 8 GiB")
                stream.write(chunk)
        uploaded_meshes: list[str] = []
        with zipfile.ZipFile(upload_path) as archive:
            if len(archive.infolist()) > 10000:
                raise HTTPException(413, "数模压缩包文件数量过多")
            expanded = 0
            for info in archive.infolist():
                supplied = info.filename.replace("\\\\", "/")
                parts = [part for part in supplied.split("/") if part not in {"", "."}]
                mode = (info.external_attr >> 16) & 0o170000
                if info.is_dir():
                    continue
                if mode == 0o120000 or not parts or any(part == ".." for part in parts):
                    raise HTTPException(422, "数模压缩包包含非法路径或符号链接")
                relative = Path(*parts)
                if relative.suffix.lower() not in MODEL_ASSET_UPLOAD_EXTENSIONS:
                    continue
                expanded += int(info.file_size)
                if int(info.file_size) > MAX_MODEL_ASSET_BYTES or expanded > MAX_MODEL_UPLOAD_BYTES:
                    raise HTTPException(413, "数模压缩包解压后超过大小上限")
                destination = (target_root / relative).resolve()
                if target_root.resolve() not in destination.parents:
                    raise HTTPException(422, "数模压缩包路径越界")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                if relative.suffix.lower() in SUPPORTED_MESH_EXTENSIONS:
                    uploaded_meshes.append(relative.as_posix())
        if not uploaded_meshes:
            raise HTTPException(422, "本地路径中没有可同步的 STL 或 OBJ 文件")
        _verify_ticket_context(item, identity)
        project = get_project(project_id)
        require_project_access(project, write=True)
        _require_editable(project)
        _require_mutable_mesh_assets(project)
        if str(project.mesh_root).startswith("@model_assets/"):
            public_root = store.resolve_model_asset_reference(project.mesh_root, create=True)
        else:
            base = Path(urllib.parse.unquote(request.headers.get("X-MuJoCo-Source-Path", ""))).name or "客户端同步数模"
            folder_name, suffix = base, 2
            while True:
                try:
                    reference, public_root = store.create_model_asset_folder(project.category, folder_name)
                    project.mesh_root = reference
                    break
                except ValueError as exc:
                    if "已存在" not in str(exc): raise HTTPException(422, str(exc)) from exc
                    folder_name = f"{base}_{suffix}"; suffix += 1
        shutil.copytree(target_root, public_root, dirs_exist_ok=True, copy_function=shutil.copy2)
        repair_mesh_references(project, list_mesh_files(public_root)); repair_joint_references(project)
        with core.acquire(project_id) as instance:
            result = instance.bus.dispatch({"tool_id":"project.asset_selection", "params":{"project":project.model_dump(), "asset_folder_path":project.mesh_root, "intent":"客户端同步到公共数模资产文件夹"}, "actor":identity.username, "client":"script"})
            if not result.ok: raise HTTPException(422, result.errors)
            project = instance.project()
        return {"ok": True, "project": project.model_dump(), "files": list_mesh_files(public_root),
                "uploaded_meshes": uploaded_meshes, "folders": store.list_model_asset_folders(project.category)}
    except zipfile.BadZipFile as exc:
        raise HTTPException(422, "客户端上传的数模压缩包无效") from exc
    except Exception:
        if target_root is not None:
            shutil.rmtree(target_root, ignore_errors=True)
        raise
    finally:
        if upload_path is not None:
            upload_path.unlink(missing_ok=True)
        reset_active_identity(token)


# Viewer ZIP generation can copy gigabytes of CAD assets. Keep that workload
# bounded and off the event loop; refuse excess requests promptly instead of
# allowing one tenant to exhaust memory/threads for everybody else.
_client_viewer_bundle_slots = threading.BoundedSemaphore(2)


@app.post("/api/client/viewer-bundle")
def client_viewer_bundle(request: Request):
    match = re.search(r"MuJoCo-Studio-Client/(\d+\.\d+\.\d+)", request.headers.get("User-Agent", ""))
    client_version = tuple(int(part) for part in match.group(1).split(".")) if match else (0, 0, 0)
    if client_version < (0, 3, 9):
        raise HTTPException(426, {
            "code": "client_upgrade_required", "message": "请升级 MuJoCo Studio Client 至 V0.3.9 或更高版本，以同步 Viewer 甘特图缓存",
            "min_client_version": "0.3.9",
        })
    item, identity = _consume_client_ticket(request, "viewer_launch")
    if not _client_viewer_bundle_slots.acquire(blocking=False):
        raise HTTPException(429, {"code":"viewer_bundle_capacity", "message":"Viewer 打包繁忙，请稍后重试", "retry_after":3})
    token = set_active_identity(identity)
    try:
        project_id = str(item["project_id"])
        project = get_project(project_id)
        require_project_access(project, write=False)
        with tempfile.TemporaryDirectory(prefix="mujoco_client_bundle_") as temporary:
            runtime_project = _runtime_project(project_id, project)
            trajectory_source, _trajectory_warnings = _current_simulation_trajectory(project_id, project)
            bundle = build_client_bundle(
                runtime_project,
                Path(temporary),
                Path(__file__).resolve().parent / "domain" / "viewer_runner.py",
                server_version=__version__,
                trajectory_source=trajectory_source,
                gantt_cache_dir=store._directory(project_id) / "core" / "artifacts" / "gantt_cache",
            )
            payload = bundle.read_bytes()
        return Response(
            content=payload,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="mujoco_client_bundle.zip"'},
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        reset_active_identity(token)
        _client_viewer_bundle_slots.release()



# ----------------------- Lab V2.15.0 transport facade -----------------------
# External HTTP endpoints intentionally do not create Core business Tools.
# ProjectSpec and motion.resolve_schedule remain the sole authoritative plan.
_LAB_SESSIONS: dict[str, LabSession] = {}
_LAB_LOCK = threading.RLock()
_LAB_MAX_SESSIONS = 256
_LAB_SESSION_TTL_S = 60 * 60


def _lab_paths(project_id: str) -> dict[str, Path]:
    root = core.get(project_id).project_dir / "core" / "lab"
    return {
        "root": root, "viewer": root / "viewer.html", "manifest": root / "manifest.json",
        "config": root / "udp_settings.json", "trajectory": root / "trajectory.npz",
    }


def _lab_project(project_id: str, *, write: bool = False) -> ProjectSpec:
    project = get_project(project_id)
    # Lab routes have their own URL prefix, so their project-policy guard
    # must be invoked here rather than relying on /api/projects middleware.
    require_project_access(project, write=write)
    return project


def _lab_config(project_id: str) -> dict[str, Any]:
    path = _lab_paths(project_id)["config"]
    try:
        return validated_config(json.loads(path.read_text("utf-8")))
    except FileNotFoundError:
        return validated_config({})
    except (ValueError, OSError) as exc:
        raise HTTPException(409, f"保存的 Lab UDP 配置无效：{exc}") from exc


def _lab_json_payload(html_path: Path) -> dict[str, Any]:
    """Read exported first-party DATA object; never parse arbitrary user-provided HTML."""
    text = html_path.read_text("utf-8")
    index = text.find("const DATA=")
    if index < 0:
        raise ValueError("导出动画缺少 DATA 采样数据")
    value, _ = json.JSONDecoder().raw_decode(text[index + len("const DATA="):])
    if not isinstance(value, dict):
        raise ValueError("动画 DATA 必须是 JSON 对象")
    return value


def _lab_sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for part in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def _lab_cached_trajectory(project_id: str, identity: dict[str, str]) -> Path | None:
    """Reuse only a verified local Lab trajectory for the identical project/engine.

    A saved HTML is not proof of physics freshness.  This intentionally requires
    an explicit trajectory checksum, full content identity, and engine stamp.
    Older V2.15.2 manifests simply miss the cache instead of trusting stale data.
    """
    paths = _lab_paths(project_id)
    trajectory = paths.get("trajectory")
    if trajectory is None or not trajectory.is_file():
        return None
    try:
        manifest = json.loads(paths["manifest"].read_text("utf-8"))
        if manifest.get("identity") != identity:
            return None
        if manifest.get("trajectory_engine") != engine_identity(__version__):
            return None
        checksum = manifest.get("trajectory_sha256")
        if not isinstance(checksum, str) or len(checksum) != 64:
            return None
        return trajectory if _lab_sha256_file(trajectory) == checksum else None
    except (OSError, ValueError, TypeError):
        return None


def _lab_fresh_manifest(project_id: str, project: ProjectSpec, *, check_file: bool = True) -> tuple[dict[str, Any], dict[str, str]]:
    paths = _lab_paths(project_id)
    if not paths["manifest"].is_file() or not paths["viewer"].is_file():
        raise HTTPException(409, "尚未生成 Lab 动画，请先点击「重新生成动画」")
    try:
        manifest = json.loads(paths["manifest"].read_text("utf-8"))
        identity = sequence_identity(project, _fingerprint(project_id, project))
        if any(manifest.get("identity", {}).get(key) != identity[key] for key in identity):
            raise HTTPException(409, {"code": "lab_sequence_stale", "message": "时序或模型已修改：请重新生成动画后再部署"})
        if check_file:
            if _lab_sha256_file(paths["viewer"]) != manifest.get("html_sha256"):
                raise HTTPException(409, {"code": "lab_artifact_modified", "message": "动画 HTML 文件与采样清单不一致"})
            # Hashing the HTML alone does NOT prove that the separately stored
            # manifest samples came from that HTML. Compare the full encoded
            # motor, time and distance arrays before any new UDP deployment.
            html_data = _lab_json_payload(paths["viewer"])
            saved_samples = manifest.get("samples")
            required = ("labIdentity", "times", "drives", "pairs", "driveValues", "measurements")
            if not isinstance(saved_samples, dict) or any(
                html_data.get(key) != saved_samples.get(key) for key in required
            ):
                raise HTTPException(409, {"code": "lab_samples_mismatch", "message": "服务器采样清单与动画 HTML 内嵌采样不一致，请重新生成"})
        if manifest.get("protocol_version") != "1.0":
            raise HTTPException(409, "Lab 旧版清单不兼容，请重新生成")
        if not isinstance(manifest.get("samples"), dict) or manifest["samples"].get("labIdentity") != identity:
            raise HTTPException(409, {"code": "lab_samples_stale", "message": "采样数据身份与时序/动画清单不一致"})
        return manifest, identity
    except HTTPException:
        raise
    except (ValueError, KeyError, OSError, TypeError) as exc:
        raise HTTPException(409, {"code": "lab_manifest_invalid", "message": str(exc)}) from exc


def _lab_sample(manifest: dict[str, Any]) -> SampledAnimation:
    return SampledAnimation.from_payload(manifest["samples"])


def _lab_session(token: str, project_id: str, owner: str, identity: dict[str, str]) -> LabSession:
    with _LAB_LOCK:
        session = _LAB_SESSIONS.get(token)
    if not session or session.project_id != project_id or session.owner != owner:
        raise HTTPException(409, "Lab 已停止或会话不存在，请重新部署")
    if time.monotonic() - session.started_at >= _LAB_SESSION_TTL_S:
        with _LAB_LOCK:
            _LAB_SESSIONS.pop(token, None)
        raise HTTPException(409, "Lab 会话已过期，请重新部署")
    if session.identity != identity:
        raise HTTPException(409, "动画身份发生变化，必须重新部署")
    return session


@app.get("/api/lab/projects/{project_id}/overview")
def lab_overview(project_id: str) -> dict[str, Any]:
    project = _lab_project(project_id)
    identity = sequence_identity(project, _fingerprint(project_id, project))
    timeline = build_timeline(project, identity)
    ready, reason = False, ""
    try:
        manifest, _ = _lab_fresh_manifest(project_id, project)
        timeline = align_timeline_to_samples(timeline, _lab_sample(manifest),
                                             simulation_start_s=project.simulation.start_time)
        ready = True
    except HTTPException as exc:
        reason = str(exc.detail)
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        reason = f"动画采样与运动时序不一致：{exc}"
    return {
        "lab_version": LAB_VERSION, "project": {"id": project.id, "name": project.name,
            "lifecycle": project.lifecycle.status, "updated_at": project.metadata.get("updated_at")},
        "simulation_start_s": float(project.simulation.start_time), "identity": identity,
        "timeline": timeline, "ready": ready, "reason": reason,
        "config": _lab_config(project_id),
    }


@app.put("/api/lab/projects/{project_id}/segments/{drive_id}/{segment_id}")
def lab_update_segment(project_id: str, drive_id: str, segment_id: str,
                       payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Save Lab motion edits into canonical TSJSON and delivery-only CSV.

    ProjectSpec remains the one write authority; generated tables are projections.
    """
    expected_sequence = str(payload.get("expected_sequence_id") or "")
    expected_revision = str(payload.get("expected_updated_at") or "")
    if not expected_sequence or not expected_revision:
        raise HTTPException(428, "缺少时序版本或项目修改时间，请刷新 Lab 后重试")
    field_mapping = {"start_time_s": "start", "duration_s": "duration", "speed": "speed", "travel": "travel"}
    validated: dict[str, float] = {}
    for exposed in field_mapping:
        number = payload.get(exposed)
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(float(number)) or abs(float(number)) > 1e9:
            raise HTTPException(422, f"{exposed} 必须为有效且合理的有限数值")
        validated[exposed] = float(number)
    if validated["start_time_s"] < 0 or validated["duration_s"] <= 0:
        raise HTTPException(422, "运动起始时间不能为负，时长必须大于 0")

    with core.acquire(project_id) as instance, instance.bus._lock:
        current = instance.project()
        identity = require_project_access(current, write=True)
        if current.lifecycle.status != "checked_out":
            raise HTTPException(409, "只有正式签出的项目才能从 Lab 修改运动段")
        if str(current.metadata.get("updated_at") or "") != expected_revision:
            raise HTTPException(409, "项目已被其他页面修改，请刷新后重试")
        current_identity = sequence_identity(current, _fingerprint(project_id, current))
        if current_identity["sequence_id"] != expected_sequence:
            raise HTTPException(409, "时序身份已改变，请刷新后重试")
        candidate = ProjectSpec.model_validate(copy.deepcopy(current.model_dump()))
        target = next((drive for drive in candidate.drives if drive.id == drive_id), None)
        segment = next((part for part in target.segments if part.id == segment_id), None) if target else None
        if segment is None:
            raise HTTPException(404, "运动段不存在")
        if not target.enabled or segment.start_mode != "direct" or segment.profile not in {"s_curve", "smoothstep"} or segment.points or segment.mapping_source_joint_id:
            raise HTTPException(422, "Lab 只允许编辑启用电机的直接时间/内置曲线；映射及 CSV 时序请使用 Editor")
        # Exactly one driving parameter is authoritative. Unused speed/duration
        # values must not be overwritten with UI-derived read-only numbers.
        fields = ("start_time_s", "travel", "duration_s" if segment.mode == "duration" else "speed")
        if segment.mode == "speed" and validated["speed"] == 0:
            raise HTTPException(422, "速度模式要求非零速度")
        for exposed in fields:
            setattr(segment, field_mapping[exposed], validated[exposed])
        try:
            # Compile the full schedule before any write; malformed references
            # must fail rather than silently emit a corrupted sidecar.
            _variables, plan = resolve_schedule(candidate)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(422, f"时序求解未通过：{exc}") from exc
        csv_stream = io.StringIO(newline="")
        writer = csv.writer(csv_stream)
        writer.writerow(["电机", "运动段", "起始时间(s)", "时长(s)", "速度", "行程", "单位"])
        raw_drives = {drive.id: drive for drive in candidate.drives}
        joints = {joint.id: joint for layer in candidate.layers for joint in layer.joints}
        for item in sorted(plan, key=lambda entry: (entry.start, entry.drive_id, entry.segment_id)):
            drive = raw_drives[item.drive_id]
            joint = joints.get(drive.joint_id)
            writer.writerow([drive.name, item.name, item.start, item.duration, item.speed,
                             item.travel, "mm" if joint and joint.type == "translation" else "deg"])
        if current.model_dump() == candidate.model_dump():
            return {"changed": False, "sequence_id": expected_sequence}
        result = instance.bus.dispatch({
            "tool_id": "project.replace", "params": {
                "project": candidate.model_dump(), "intent": "MuJoCoLab 编辑电机时序段"
            }, "actor": identity.username, "client": "human_ui",
        })
        if not result.ok:
            raise HTTPException(422, result.errors)
        saved = instance.project()
        _record_model_write_activity(project_id, identity, "project.replace")
        # Lab updates are real exchange files too. Previous simulation channels
        # may be stale after drive edits, so this TSJSON intentionally has none.
        # Keep the human-readable schedule projection only in the delivery table folder.
        filename = f"{_safe_filename(saved.name) or saved.id}--Lab编辑时序.csv"
        tsjson_name, tsjson_content = build_tsjson_bundle(saved, [])
        try:
            _migrate_legacy_time_series_tables(saved)
            tables = _table_files_directory(saved)
            atomic_write_text(tables / filename, csv_stream.getvalue())
            atomic_write_text(store.time_series_directory(saved, create=True) / tsjson_name,
                              tsjson_content, encoding="utf-8")
            _record_delivery_output(saved, tables, "tables_folder", "表格文件夹")
        except OSError as exc:
            LOGGER.exception("Lab schedule saved but TSJSON/delivery sync failed: %s", saved.id)
            raise HTTPException(500, "项目时序已保存，但时序交换文件或交付表格保存失败，请检查磁盘权限") from exc
        return {"changed": True, "csv_name": filename, "tsjson_name": tsjson_name,
                "sequence_id": sequence_identity(saved, _fingerprint(project_id, saved))["sequence_id"]}


@app.put("/api/lab/projects/{project_id}/udp-config")
def lab_save_config(project_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _lab_project(project_id, write=True)
    try:
        validated = validated_config(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    dest = _lab_paths(project_id)["config"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(dest, json.dumps(validated, ensure_ascii=False, indent=2))
    # Running sessions are frozen against changed settings: explicit redeploy.
    return {"config": validated}


@app.post("/api/lab/projects/{project_id}/generate", status_code=202)
def lab_generate(project_id: str) -> dict[str, str]:
    project = _lab_project(project_id)
    if active_identity().role not in {"admin", "engineer"}:
        raise HTTPException(403, "只有工程师或管理员可以生成 Lab 动画")
    identity = sequence_identity(project, _fingerprint(project_id, project))
    source = _runtime_project(project_id, project)
    paths = _lab_paths(project_id)
    # Match the regular Studio result-viewer path: a current, provenance-checked
    # simulation takes priority.  Only if none exists may we reuse a Lab-owned
    # qpos trajectory with its own checksum + identity + engine checks.
    trajectory_source, trajectory_warnings = _current_simulation_trajectory(project_id, project)
    if trajectory_source is None:
        trajectory_source = _lab_cached_trajectory(project_id, identity)

    def build(progress, cancelled, workspace, job_id):
        html_file = workspace / "viewer.html"
        export = export_project_animation_html(
            source, workspace, destination=html_file, progress=progress,
            should_cancel=cancelled, lab_identity=identity,
            gantt_cache_dir=core.get(project_id).project_dir / "core" / "artifacts" / "gantt_cache",
            gantt_fallback_dir=workspace / "gantt_fallback",
            trajectory_source=trajectory_source,
            trajectory_warnings=trajectory_warnings,
        )
        if cancelled():
            raise InterruptedError("Lab 动画生成取消")
        payload = _lab_json_payload(html_file)
        samples = {key: payload[key] for key in ("labIdentity", "times", "drives", "pairs", "driveValues", "measurements")}
        sample = SampledAnimation.from_payload(samples)
        if sample.identity != identity:
            raise ValueError("动画源身份与时序源不一致，拒绝发布")
        current = core.get(project_id).project()
        current_identity = sequence_identity(current, _fingerprint(project_id, current))
        if current_identity != identity:
            raise ValueError("动画生成期间模型或时序发生修改；请重新生成")
        manifest = {"protocol_version": "1.0", "lab_version": LAB_VERSION,
            "identity": identity, "html_sha256": _lab_sha256_file(html_file),
            "samples": samples, "generated_at": datetime.now(timezone.utc).isoformat(),
            "motor_count": len(sample.drives), "pair_count": len(sample.pairs)}
        # A trajectory computed inside this Job would otherwise be deleted with
        # the private workspace.  Keep it under the existing Lab derived-artifact
        # folder so a second, unchanged generation need not solve MuJoCo again.
        # Reusing an external Studio result requires no duplicate file.
        cached_source = paths.get("trajectory")
        new_trajectory = Path(export["trajectory"])
        if not export["trajectory_reused"]:
            manifest["trajectory_sha256"] = _lab_sha256_file(new_trajectory)
            manifest["trajectory_engine"] = engine_identity(__version__)
            if cached_source is not None:
                job_workspaces.publish_file(new_trajectory, cached_source)
        elif cached_source is not None and trajectory_source == cached_source:
            # Verified by _lab_cached_trajectory before starting this Job.
            manifest["trajectory_sha256"] = _lab_sha256_file(cached_source)
            manifest["trajectory_engine"] = engine_identity(__version__)
        staged_manifest = workspace / "manifest.json"
        staged_manifest.write_text(json.dumps(manifest, ensure_ascii=False), "utf-8")
        # Publish manifest first. If interrupted, mismatched hashes fail closed.
        job_workspaces.publish_file(staged_manifest, paths["manifest"])
        job_workspaces.publish_file(html_file, paths["viewer"])
        return {"artifact": str(paths["viewer"]), "identity": identity,
                "preview_url": f"/api/lab/projects/{project_id}/viewer",
                "warnings": export.get("warnings", []), "motor_count": len(sample.drives),
                "pair_count": len(sample.pairs),
                "trajectory_reused": bool(export["trajectory_reused"]),
                "timings_seconds": export.get("timings_seconds", {})}

    return {"job_id": _submit_project_job(project_id, "lab_animation_export", build)}


@app.get("/api/lab/projects/{project_id}/viewer")
def lab_viewer(project_id: str):
    project = _lab_project(project_id)
    _lab_fresh_manifest(project_id, project)
    return FileResponse(_lab_paths(project_id)["viewer"], media_type="text/html",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@app.post("/api/lab/projects/{project_id}/deploy")
def lab_deploy(project_id: str) -> dict[str, Any]:
    project = _lab_project(project_id, write=True)
    manifest, identity = _lab_fresh_manifest(project_id, project)
    config = _lab_config(project_id)
    # Validate frozen real frame samples BEFORE any UDP datagram leaves the server.
    # A malformed/mismatched manifest must not transmit a plan without telemetry.
    try:
        sample = _lab_sample(manifest)
        if sample.identity != identity:
            raise ValueError("导出采样身份与模型/时序不一致")
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        raise HTTPException(409, f"Lab 采样清单损坏，拒绝部署：{exc}") from exc
    try:
        timeline = align_timeline_to_samples(build_timeline(project, identity), sample,
                                             simulation_start_s=project.simulation.start_time)
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise HTTPException(409, f"时序与动画轨迹未对齐，拒绝 UDP 部署：{exc}") from exc
    run_id = "run_" + uuid4().hex
    message = project_message(timeline, "timeline", config, run_id=run_id)
    try:
        sent = send_udp(message, config)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, f"发送完整时序失败：{exc}") from exc
    token = uuid4().hex
    session = LabSession(token, run_id, identity, manifest["html_sha256"], project_id,
                         active_identity().username, time.monotonic())
    session.config_digest = hashlib.sha256(canonical_bytes(config)).hexdigest()
    stat = _lab_paths(project_id)["viewer"].stat()
    session.viewer_stat = (stat.st_size, stat.st_mtime_ns)
    session.samples = sample
    with _LAB_LOCK:
        _LAB_SESSIONS[token] = session
        if len(_LAB_SESSIONS) > _LAB_MAX_SESSIONS:
            oldest = min(_LAB_SESSIONS, key=lambda key: _LAB_SESSIONS[key].started_at)
            _LAB_SESSIONS.pop(oldest, None)
    # Echo the exact server-built JSON that was successfully sent. The Lab UI
    # can retain it without guessing sampled motor initial positions. No extra
    # UDP packet, database write, or transport/tool is added by this response.
    return {"session_token": token, "run_id": run_id, "sequence_id": identity["sequence_id"],
            "timeline_datagrams": sent, "timeline_message": message,
            "destination": f"{config['remote_ip']}:{config['remote_port']}"}


@app.post("/api/lab/projects/{project_id}/state")
def lab_send_state(project_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    project = _lab_project(project_id, write=True)
    manifest, identity = _lab_fresh_manifest(project_id, project, check_file=False)
    token = str(payload.get("session_token", ""))
    session = _lab_session(token, project_id, active_identity().username, identity)
    if manifest.get("html_sha256") != session.html_sha256:
        raise HTTPException(409, "动画已经更换，先停止发送并重新部署")
    # First deploy verified the full SHA256. Per-frame stat check is cheap and
    # revokes the session if the trusted HTML is subsequently replaced/edited.
    try:
        viewer_stat = _lab_paths(project_id)["viewer"].stat()
    except OSError as exc:
        raise HTTPException(409, "已导出的动画文件不可用") from exc
    if session.viewer_stat != (viewer_stat.st_size, viewer_stat.st_mtime_ns):
        raise HTTPException(409, "动画文件已被修改，重新生成后才能继续发送")
    config = _lab_config(project_id)
    if hashlib.sha256(canonical_bytes(config)).hexdigest() != session.config_digest:
        raise HTTPException(409, "UDP 配置已变更，必须重新部署")
    try:
        t = float(payload.get("sim_time_s"))
        playback_state = str(payload.get("playback_state", ""))
        if session.samples is None:
            raise ValueError("Lab 会话缺少采样快照")
        state = session.samples.at(t, playback_state, run_id=session.run_id)
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(422, f"动画帧无效：{exc}") from exc
    with session.lock:
        current = time.monotonic()
        # This is a rate guard, not a timebase replacement. Never lie about t.
        if current - session.last_state_at < config["state_interval_ms"] / 1000.0 * .75 and playback_state == "playing":
            return {"status": "throttled", "packet_seq": session.sequence_number, "state": state}
        session.sequence_number += 1
        message = project_message(state, "state", config, run_id=session.run_id,
                                  packet_seq=session.sequence_number)
        try:
            sent = send_udp(message, config)
        except (OSError, ValueError) as exc:
            session.sequence_number -= 1
            raise HTTPException(422, f"实时 UDP 发送失败：{exc}") from exc
        session.last_state_at = current
    return {"status": "sent", "packet_seq": session.sequence_number, "datagrams": sent, "state": state}


@app.post("/api/lab/projects/{project_id}/stop")
def lab_stop(project_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    project = _lab_project(project_id, write=True)
    identity = sequence_identity(project, _fingerprint(project_id, project))
    token = str(payload.get("session_token", ""))
    session = _lab_session(token, project_id, active_identity().username, identity)
    with _LAB_LOCK:
        _LAB_SESSIONS.pop(token, None)
    return {"status": "stopped", "run_id": session.run_id}


if FRONTEND_ROOT.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_ROOT), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "lab":
            return FileResponse(FRONTEND_ROOT / "lab.html", headers={"Cache-Control": "no-store"})
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, {"code": "route_not_found", "message": "接口不存在"})
        requested = FRONTEND_ROOT / path
        if path and requested.is_file() and FRONTEND_ROOT in requested.resolve().parents:
            return FileResponse(requested)
        return FileResponse(FRONTEND_ROOT / "index.html")


@app.middleware("http")
async def prevent_stale_frontend_assets(request, call_next):
    """A release must never silently reuse HTML/CSS/JS from an older installation."""
    response = await call_next(request)
    path = request.url.path
    if path in {"/", "/hub", "/lab"} or path.startswith("/models/") or path.startswith("/assets/") or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.middleware("http")
async def authenticate_and_authorize(request: Request, call_next):
    """Default-deny every API route and project policy at one app boundary."""
    path = request.url.path
    client_public_paths = {"/api/client/mesh-sync", "/api/client/viewer-bundle", "/api/client/authorize"}
    if path.startswith("/api/internal/vz/"):
        provided = str(request.headers.get("X-VZ-Bridge-Token", "") or "")
        if not VZ_BRIDGE_TOKEN or not provided or not hmac.compare_digest(provided, VZ_BRIDGE_TOKEN):
            return JSONResponse({"detail": "VZ 内部同步令牌无效"}, status_code=403)
        return await call_next(request)
    if not path.startswith("/api/") or path in {"/api/health", "/api/auth/login"} or path in client_public_paths:
        return await call_next(request)
    identity: Identity | None
    session_token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if SINGLE_USER:
        identity = Identity(BUILTIN_ADMIN_USERNAME, "admin", session_id="single-user", lease_id="single-user", single_user=True)
    else:
        # Session TTL slides on authenticated user activity. Lease TTL does not.
        identity = auth.sessions.get(session_token, slide=True)
    if identity is None:
        return JSONResponse({"detail": "未认证或会话已过期"}, status_code=401)
    request.state.identity = identity
    token = set_active_identity(identity)
    try:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and path != "/api/auth/logout":
            if identity.role == "guest":
                return JSONResponse({"detail": "游客账号为只读权限"}, status_code=403)
        if identity.role == "guest" and path.startswith("/api/jobs"):
            return JSONResponse({"detail": "游客无权查看全局后台任务"}, status_code=403)
        if identity.role == "guest" and request.method == "GET":
            guest_global_reads = {"/api/auth/me", "/api/projects"}
            guest_project_read = re.match(r"^/api/projects/[^/]+(?P<suffix>/.*)?$", path)
            allowed_suffixes = {"", "/preview", "/latest-simulation", "/files", "/artifacts"}
            suffix = str(guest_project_read.group("suffix") or "") if guest_project_read else ""
            guest_project_allowed = bool(guest_project_read and (
                suffix in allowed_suffixes or suffix.startswith("/artifacts/")
            ))
            if path not in guest_global_reads and not guest_project_allowed:
                return JSONResponse({"detail": "游客只能查看基线模型的仿真结果与交付数据"}, status_code=403)
        if path.endswith("/llm-config") and request.method == "PUT" and identity.role != "admin":
            return JSONResponse({"detail": "只有管理员可以修改 LLM 凭证"}, status_code=403)
        desktop_only = (
            path.startswith("/api/dialogs/")
            or path.endswith("/open-folder") or path.endswith("/bind-delivery-folder")
            or path.endswith("/meshes/scan")
        )
        if desktop_only:
            if not DESKTOP_ENABLED:
                return JSONResponse({"detail": "当前服务器部署未启用桌面能力"}, status_code=403)
        match = re.match(r"^/api/projects/([^/]+)(?:/|$)", path)
        if match:
            try:
                project = core.get(match.group(1)).project()
                is_force_check_in = path.endswith("/force-check-in")
                is_read_only_action = (
                    path.endswith("/local-viewer")
                    or path.endswith("/client-ticket")
                    or path.endswith("/export-nx-afu-script")
                )
                write_request = (
                    request.method in {"POST", "PUT", "PATCH", "DELETE"}
                    and not is_force_check_in and not is_read_only_action
                )
                lease_coordination = (
                    path.endswith("/edit-session")
                    or path.endswith("/edit-session/leave")
                    or path.endswith("/lifecycle")
                    or is_force_check_in
                )
                # Lifecycle/Edit-Session coordinators perform their own write checks.
                # Let them inspect same-account stale lease ids so they can safely
                # rebind or reject instead of being pre-empted by generic middleware.
                require_project_access(project, write=write_request and not lease_coordination)
                if (
                    write_request and project.lifecycle.status == "checked_out"
                    and not identity.single_user and not lease_coordination
                ):
                    lease_active, lease_reason = auth.sessions.lease_state(session_token)
                    if not lease_active:
                        return JSONResponse({"detail": {
                            "code": "edit_lease_inactive",
                            "message": "编辑租约已失效；模型仍保持签出，请先恢复编辑租约",
                            "lease_lost_reason": lease_reason or "revoked",
                        }}, status_code=409)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            except KernelCapacityError as exc:
                return JSONResponse({"detail": {
                    "code": exc.code,
                    "message": "服务器同时打开的模型内核已达上限",
                    "field": None,
                    "hint": "请稍后重试，或关闭部分模型分页",
                }}, status_code=503)
            except (KeyError, ValueError):
                pass  # Endpoint retains its existing 404 response semantics.
        response = await call_next(request)
        if (match and request.method in {"POST", "PUT", "PATCH", "DELETE"}
                and 200 <= response.status_code < 300):
            project_id = match.group(1)
            coordination_suffixes = (
                "/edit-session", "/edit-session/leave", "/lifecycle", "/force-check-in",
                "/commands", "/undo", "/redo", "/changesets",
            )
            if not any(path.endswith(suffix) or f"{suffix}/" in path for suffix in coordination_suffixes):
                _record_model_write_activity(project_id, identity, "http.model_write")
        if not identity.single_user and path != "/api/auth/logout" and session_token:
            # Keep the browser cookie lifetime aligned with the sliding server Session TTL.
            response.set_cookie(
                SESSION_COOKIE_NAME, session_token, httponly=True, samesite="lax",
                secure=SECURE_COOKIE, max_age=int(SESSION_TTL_HOURS * 3600), path="/",
            )
        return response
    finally:
        reset_active_identity(token)
