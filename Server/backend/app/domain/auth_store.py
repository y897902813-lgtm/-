"""Atomic file-backed accounts and administrator-mode credentials."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal

from passlib.hash import pbkdf2_sha256


logger = logging.getLogger(__name__)
Role = Literal["guest", "engineer", "admin"]
BUILTIN_ADMIN_USERNAME = "yu.weigang1"

# The source contains only a one-way hash.  Production server deployments
# inject the administrator password through MUJOCO_STUDIO_ADMIN_PASSWORD.
BUILTIN_ADMIN_PASSWORD_HASH = (
    "$pbkdf2-sha256$29000$NuY8p5SSUiplLCXEOGcM4Q$"
    "qqz38PyZZljlgwngwR4W5Ghp6GQLCe0QeOx8W6.uHnM"
)


class AuthStoreError(ValueError):
    """A user-facing account-store error."""


class AuthStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.users_path = self.root / "users.json"
        self.admin_mode_path = self.root / "admin_mode.json"
        self._lock = RLock()
        environment_password = os.getenv("MUJOCO_STUDIO_ADMIN_PASSWORD", "")
        self._admin_hash = (
            pbkdf2_sha256.hash(environment_password)
            if environment_password
            else BUILTIN_ADMIN_PASSWORD_HASH
        )
        self._migrate_extra_admins()
        self._ensure_admin_mode_password()

    @staticmethod
    def _key(username: str) -> str:
        return str(username).strip().casefold()

    def _read_users(self) -> list[dict]:
        try:
            value = json.loads(self.users_path.read_text("utf-8"))
            if not isinstance(value, list):
                raise ValueError("users root must be a list")
            return [item for item in value if isinstance(item, dict)]
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as exc:
            logger.error("unable to read auth users file; built-in admin remains available: %s", exc)
            return []

    @staticmethod
    def _public(item: dict) -> dict:
        return {key: item.get(key) for key in (
            "username", "role", "created_at", "created_by", "disabled",
        )}

    def list_users(self) -> list[dict]:
        with self._lock:
            return [
                {"username": BUILTIN_ADMIN_USERNAME, "role": "admin", "created_at": "", "created_by": "system",
                 "disabled": False, "built_in": True},
                *[{**self._public(item), "built_in": False} for item in self._read_users()],
            ]

    def _migrate_extra_admins(self) -> None:
        """The built-in account is the only administrator."""
        users = self._read_users()
        changed = False
        for item in users:
            if item.get("role") == "admin":
                item["role"] = "engineer"
                changed = True
                logger.warning("downgrading legacy extra administrator to engineer: %s", item.get("username", ""))
        if changed:
            self._atomic_write(self.users_path, users)

    def _atomic_write(self, path: Path, payload: dict | list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
            if os.name != "nt":
                try:
                    os.chmod(temporary, 0o600)
                except OSError as exc:
                    logger.warning("unable to set private permissions on %s: %s", temporary, exc)
            temporary.replace(path)
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning("unable to clean failed auth temporary file %s", temporary)
            raise

    def create_user(self, username: str, password: str, role: Role, *, created_by: str) -> dict:
        display = str(username).strip()
        if not display or self._key(display) == self._key(BUILTIN_ADMIN_USERNAME):
            raise AuthStoreError("用户名不可为空或使用内置管理员名称")
        if not password:
            raise AuthStoreError("密码不可为空")
        if role not in {"guest", "engineer"}:
            raise AuthStoreError("新增账号角色只能是游客或工程师")
        with self._lock:
            users = self._read_users()
            if any(self._key(item.get("username", "")) == self._key(display) for item in users):
                raise AuthStoreError("用户名已存在（大小写不敏感）")
            item = {
                "username": display,
                "password_hash": pbkdf2_sha256.hash(password),
                "role": role,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": str(created_by),
                "disabled": False,
            }
            self._atomic_write(self.users_path, [*users, item])
            return self._public(item)

    def delete_user(self, username: str) -> dict:
        key = self._key(username)
        if key == self._key(BUILTIN_ADMIN_USERNAME):
            raise AuthStoreError("内置管理员账号不可删除")
        with self._lock:
            users = self._read_users()
            remaining = [item for item in users if self._key(item.get("username", "")) != key]
            if len(remaining) == len(users):
                raise AuthStoreError("账号不存在")
            removed = next(item for item in users if self._key(item.get("username", "")) == key)
            self._atomic_write(self.users_path, remaining)
            return self._public(removed)

    def authenticate(self, username: str, password: str) -> dict | None:
        key = self._key(username)
        if not password:
            return None
        if key == self._key(BUILTIN_ADMIN_USERNAME):
            return ({"username": BUILTIN_ADMIN_USERNAME, "role": "admin", "disabled": False}
                    if pbkdf2_sha256.verify(password, self._admin_hash) else None)
        with self._lock:
            item = next((candidate for candidate in self._read_users()
                         if self._key(candidate.get("username", "")) == key), None)
        if not item or item.get("disabled", False):
            # Run one hash verification for unknown users to reduce enumeration
            # timing differences without exposing which branch was taken.
            pbkdf2_sha256.verify(password, BUILTIN_ADMIN_PASSWORD_HASH)
            return None
        try:
            valid = pbkdf2_sha256.verify(password, str(item.get("password_hash", "")))
        except (TypeError, ValueError):
            valid = False
        return self._public(item) if valid else None

    def _ensure_admin_mode_password(self) -> None:
        """Install the documented administrator-mode default once.

        Deployments may override the first-start default through
        ``MUJOCO_STUDIO_ADMIN_MODE_PASSWORD``.  The plaintext is never written
        to disk; after initialization only the PBKDF2 hash is persisted.
        """
        with self._lock:
            current = self._read_admin_mode()
            if str(current.get("password_hash", "")).strip():
                return
            password = os.getenv("MUJOCO_STUDIO_ADMIN_MODE_PASSWORD", "6870")
            self._atomic_write(self.admin_mode_path, {
                "password_hash": pbkdf2_sha256.hash(password),
                "version": max(1, int(current.get("version", 0) or 0)),
                "changed_at": datetime.now(timezone.utc).isoformat(),
                "changed_by": "system:default",
            })

    def set_admin_mode_password(self, password: str, *, changed_by: str) -> int:
        if not password:
            raise AuthStoreError("管理员模式密码不可为空")
        with self._lock:
            current = self._read_admin_mode()
            version = int(current.get("version", 0)) + 1
            self._atomic_write(self.admin_mode_path, {
                "password_hash": pbkdf2_sha256.hash(password),
                "version": version,
                "changed_at": datetime.now(timezone.utc).isoformat(),
                "changed_by": changed_by,
            })
            return version

    def _read_admin_mode(self) -> dict:
        try:
            value = json.loads(self.admin_mode_path.read_text("utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def verify_admin_mode_password(self, password: str) -> tuple[bool, int]:
        if not password:
            return False, 0
        with self._lock:
            data = self._read_admin_mode()
        password_hash = str(data.get("password_hash", ""))
        if not password_hash:
            return False, int(data.get("version", 0))
        try:
            return pbkdf2_sha256.verify(password, password_hash), int(data.get("version", 0))
        except (TypeError, ValueError):
            return False, int(data.get("version", 0))

    def admin_mode_version(self) -> int:
        with self._lock:
            return int(self._read_admin_mode().get("version", 0))
