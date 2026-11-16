from __future__ import annotations

import os
import sys
from pathlib import Path

from .storage_config import resolved_data_root
from .port_settings import load_ports


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


def default_data_root(platform: str | None = None) -> Path:
    """Return the deployment data root resolved from the V2_projec location config.

    ``platform`` remains accepted for backward-compatible tests/callers; V2.11.7
    deliberately uses the same ancestor-based rule on every platform.
    """
    _ = platform
    return resolved_data_root(PROJECT_ROOT)


DEFAULT_DATA_ROOT = default_data_root()
DATA_ROOT = DEFAULT_DATA_ROOT
RUNTIME_STATE_DIR = DATA_ROOT / ".runtime"
HOST = os.getenv("MUJOCO_STUDIO_HOST", "0.0.0.0")
PORT = load_ports()["hub"]

# Three-layer lifecycle boundaries (SPEC A). These remain configurable so a
# deployment can tune retention without changing persisted schemas.
MAX_UNDO_EVENTS = int(os.getenv("MUJOCO_STUDIO_MAX_EVENTS", "100"))
MAX_ARCHIVE_VERSIONS = int(os.getenv("MUJOCO_STUDIO_MAX_VERSIONS", "20"))
TRASH_RETENTION_DAYS = max(1, int(os.getenv("MUJOCO_STUDIO_TRASH_RETENTION_DAYS", "7")))
INTERACTION_COMMIT_DEBOUNCE_MS = 400

# Deployment/authentication boundaries (SPEC B). ``run.py`` deliberately uses
# the same authenticated server shape for local and remote browser clients.
SINGLE_USER = os.getenv("MUJOCO_STUDIO_SINGLE_USER", "0").lower() in {"1", "true", "yes"}
SECURE_COOKIE = os.getenv("MUJOCO_STUDIO_SECURE_COOKIE", "0").lower() in {"1", "true", "yes"}
DESKTOP_ENABLED = os.getenv("MUJOCO_STUDIO_DESKTOP", "0").lower() in {"1", "true", "yes"}
SESSION_TTL_HOURS = float(os.getenv("MUJOCO_STUDIO_SESSION_TTL_HOURS", "12"))
LEASE_TTL_SECONDS = max(30, int(os.getenv("MUJOCO_STUDIO_LEASE_TTL_SECONDS", "180")))
EDIT_IDLE_CHECKIN_SECONDS = max(60, int(os.getenv("MUJOCO_STUDIO_EDIT_IDLE_CHECKIN_SECONDS", "3600")))
PENDING_CHECKIN_MAX_RETRY = max(1, int(os.getenv("MUJOCO_STUDIO_PENDING_CHECKIN_MAX_RETRY", "10")))
LEASE_SWEEP_SECONDS = max(5, int(os.getenv("MUJOCO_STUDIO_LEASE_SWEEP_SECONDS", "15")))
MAX_EPHEMERAL_EDIT_SESSIONS = max(1, int(os.getenv("MUJOCO_STUDIO_MAX_EPHEMERAL_EDITS", "32")))
MAX_AUTHORITATIVE_EDIT_SESSIONS = max(1, int(os.getenv("MUJOCO_STUDIO_MAX_AUTHORITATIVE_EDITS", "16")))
JOB_MAX_RECORDS = max(10, int(os.getenv("MUJOCO_STUDIO_JOB_MAX_RECORDS", "200")))
JOB_RETENTION_SECONDS = max(60, int(os.getenv("MUJOCO_STUDIO_JOB_RETENTION_SECONDS", "1800")))
JOB_MAX_PER_USER = max(1, int(os.getenv("MUJOCO_STUDIO_JOB_MAX_PER_USER", "4")))
JOB_WORKERS = max(1, int(os.getenv("MUJOCO_STUDIO_JOB_WORKERS", "4")))
JOB_TIMEOUT_SECONDS = max(1.0, float(os.getenv("MUJOCO_STUDIO_JOB_TIMEOUT_SECONDS", "900")))
JOB_CANCEL_GRACE_SECONDS = max(0.0, float(os.getenv("MUJOCO_STUDIO_JOB_CANCEL_GRACE_SECONDS", "5")))
JOB_RESULT_KEEP = max(1, int(os.getenv("MUJOCO_STUDIO_JOB_RESULT_KEEP", "20")))
ORPHAN_WORKSPACE_TTL_HOURS = max(1.0, float(os.getenv("MUJOCO_STUDIO_ORPHAN_WORKSPACE_TTL_HOURS", "24")))
ORPHAN_RECLAIM_INTERVAL_SECONDS = max(60, int(os.getenv("MUJOCO_STUDIO_ORPHAN_RECLAIM_INTERVAL_SECONDS", "3600")))
FSYNC_ENABLED = os.getenv("MUJOCO_STUDIO_FSYNC", "1").lower() in {"1", "true", "yes"}
LOGIN_MAX_FAILURES = int(os.getenv("MUJOCO_STUDIO_LOGIN_MAX_FAILURES", "5"))
LOGIN_LOCK_SECONDS = int(os.getenv("MUJOCO_STUDIO_LOGIN_LOCK_SECONDS", "60"))
SESSION_COOKIE_NAME = "mujoco_studio_session"
