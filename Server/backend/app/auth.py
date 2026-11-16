"""Authentication, sessions, and server-side authorization policy."""
from __future__ import annotations

import hashlib
import secrets
import time
from contextvars import ContextVar
from dataclasses import dataclass, replace
from threading import RLock
from typing import Callable

from fastapi import HTTPException, Request

from .domain.auth_store import AuthStore


@dataclass(frozen=True)
class Identity:
    username: str
    role: str
    session_id: str = ""
    lease_id: str = ""
    admin_mode: bool = False
    single_user: bool = False

    @property
    def audit_id(self) -> str:
        """Non-sensitive stable audit identifier derived from the session token."""
        if not self.session_id:
            return ""
        return hashlib.sha256(self.session_id.encode("utf-8")).hexdigest()[:16]


@dataclass
class _Session:
    identity: Identity
    expires_at: float
    created_at: float = 0.0
    admin_mode_version: int = 0
    lease_active: bool = False
    lease_expires_at: float = 0.0
    lease_lost_reason: str | None = None


class SessionStore:
    def __init__(self, ttl_hours: float, admin_mode_version: Callable[[], int],
                 lease_ttl_seconds: float = 180.0, *, maximum: int = 512,
                 max_per_user: int = 8) -> None:
        self.ttl_seconds = max(1.0, ttl_hours * 3600)
        self.lease_ttl_seconds = max(30.0, float(lease_ttl_seconds))
        self._admin_mode_version = admin_mode_version
        self.maximum = max(16, int(maximum))
        self.max_per_user = max(1, int(max_per_user))
        self._items: dict[str, _Session] = {}
        self._expired_pending: list[Identity] = []
        self._lock = RLock()

    def create(self, username: str, role: str) -> Identity:
        token = secrets.token_urlsafe(32)
        identity = Identity(username=username, role=role, session_id=token, lease_id=f"lease_{secrets.token_urlsafe(18)}")
        with self._lock:
            now = time.monotonic()
            for expired in [key for key, item in self._items.items() if item.expires_at <= now]:
                stale = self._items.pop(expired, None)
                if stale is not None:
                    self._expired_pending.append(stale.identity)
            user_count = sum(1 for item in self._items.values()
                             if item.identity.username.casefold() == username.casefold())
            if user_count >= self.max_per_user:
                raise HTTPException(429, {"code": "session_user_limit", "message": "该账号登录会话已达上限"})
            if len(self._items) >= self.maximum:
                raise HTTPException(503, {"code": "session_capacity_reached", "message": "服务器登录会话已达容量上限"})
            self._items[token] = _Session(identity, now + self.ttl_seconds, created_at=now)
        return identity

    def get(self, token: str, *, slide: bool = True) -> Identity | None:
        """Return one authenticated browser session and optionally slide its TTL.

        Session activity is deliberately independent from the edit Lease heartbeat:
        ordinary authenticated requests keep the browser login alive, while only
        ``touch_lease`` renews edit ownership.
        """
        if not token:
            return None
        now = time.monotonic()
        with self._lock:
            session = self._items.get(token)
            if session is None:
                return None
            if session.expires_at <= now:
                stale = self._items.pop(token, None)
                if stale is not None:
                    self._expired_pending.append(stale.identity)
                return None
            if slide:
                session.expires_at = now + self.ttl_seconds
            if (session.identity.admin_mode
                    and session.admin_mode_version != self._admin_mode_version()):
                session.identity = replace(session.identity, admin_mode=False)
                session.admin_mode_version = 0
            return session.identity

    def touch_session(self, token: str) -> bool:
        """Slide only the account/browser Session TTL; never renew the edit Lease."""
        return self.get(token, slide=True) is not None

    def delete(self, token: str) -> None:
        with self._lock:
            self._items.pop(token, None)

    def revoke_user(self, username: str) -> None:
        key = username.casefold()
        with self._lock:
            for token in [token for token, item in self._items.items()
                          if item.identity.username.casefold() == key]:
                self._items.pop(token, None)

    def activate_lease(self, token: str) -> Identity:
        with self._lock:
            session = self._items.get(token)
            if session is None or session.expires_at <= time.monotonic():
                raise HTTPException(401, "会话已失效，请重新登录")
            session.lease_active = True
            session.lease_expires_at = time.monotonic() + self.lease_ttl_seconds
            session.lease_lost_reason = None
            return session.identity

    def touch_lease(self, token: str) -> bool:
        if not token:
            return False
        with self._lock:
            session = self._items.get(token)
            if session is None or not session.lease_active:
                return False
            now = time.monotonic()
            if session.lease_expires_at <= now:
                session.lease_active = False
                session.lease_expires_at = 0.0
                session.lease_lost_reason = "expired"
                return False
            session.lease_expires_at = now + self.lease_ttl_seconds
            session.lease_lost_reason = None
            return True

    def lease_state(self, token: str) -> tuple[bool, str | None]:
        if not token:
            return False, "no_session"
        with self._lock:
            session = self._items.get(token)
            if session is None:
                return False, "no_session"
            if session.lease_active and session.lease_expires_at <= time.monotonic():
                session.lease_active = False
                session.lease_expires_at = 0.0
                session.lease_lost_reason = "expired"
            if session.lease_active:
                return True, None
            return False, session.lease_lost_reason or "revoked"

    def deactivate_lease(self, token: str, *, reason: str = "revoked") -> bool:
        """End only edit-ownership renewal for one browser Session."""
        if not token:
            return False
        with self._lock:
            session = self._items.get(token)
            if session is None:
                return False
            was_active = session.lease_active
            session.lease_active = False
            session.lease_expires_at = 0.0
            session.lease_lost_reason = str(reason or "revoked")
            return was_active

    def deactivate_lease_id(self, lease_id: str, *, reason: str = "revoked") -> int:
        """Deactivate the Session-bound Lease by its non-secret ownership id."""
        value = str(lease_id or "")
        if not value:
            return 0
        changed = 0
        with self._lock:
            for session in self._items.values():
                if session.identity.lease_id == value and session.lease_active:
                    session.lease_active = False
                    session.lease_expires_at = 0.0
                    session.lease_lost_reason = str(reason or "revoked")
                    changed += 1
        return changed

    def expired_active_leases(self, now: float | None = None) -> list[Identity]:
        current = time.monotonic() if now is None else float(now)
        with self._lock:
            expired = [
                item.identity for item in self._items.values()
                if item.lease_active and item.lease_expires_at <= current
            ]
            for item in self._items.values():
                if item.lease_active and item.lease_expires_at <= current:
                    item.lease_active = False
                    item.lease_expires_at = 0.0
                    item.lease_lost_reason = "expired"
            return expired

    def sweep_expired_sessions(self, now: float | None = None) -> list[Identity]:
        current = time.monotonic() if now is None else float(now)
        with self._lock:
            tokens = [token for token, item in self._items.items() if item.expires_at <= current]
            identities = list(self._expired_pending) + [self._items[token].identity for token in tokens]
            self._expired_pending.clear()
            for token in tokens:
                self._items.pop(token, None)
            deduped: list[Identity] = []
            seen: set[str] = set()
            for identity in identities:
                key = identity.session_id or identity.lease_id
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                deduped.append(identity)
            return deduped

    def identities_for_user(self, username: str) -> list[Identity]:
        key = username.casefold()
        with self._lock:
            return [
                item.identity for item in self._items.values()
                if item.identity.username.casefold() == key
            ]

    def set_admin_mode(self, token: str, enabled: bool, version: int = 0) -> Identity:
        with self._lock:
            session = self._items.get(token)
            if session is None:
                raise HTTPException(401, "会话已失效，请重新登录")
            session.identity = replace(session.identity, admin_mode=enabled)
            session.admin_mode_version = version if enabled else 0
            return session.identity


class LoginLimiter:
    def __init__(self, maximum: int, lock_seconds: int) -> None:
        self.maximum = max(1, maximum)
        self.lock_seconds = max(1, lock_seconds)
        self._attempts: dict[str, tuple[int, float]] = {}
        self._lock = RLock()

    def retry_after(self, key: str) -> int:
        with self._lock:
            count, locked_until = self._attempts.get(key.casefold(), (0, 0.0))
            remaining = locked_until - time.monotonic()
            if remaining <= 0:
                if locked_until:
                    self._attempts.pop(key.casefold(), None)
                return 0
            return max(1, int(remaining + 0.999))

    def failure(self, key: str) -> int:
        folded = key.casefold()
        with self._lock:
            count, locked_until = self._attempts.get(folded, (0, 0.0))
            now = time.monotonic()
            if locked_until > now:
                return max(1, int(locked_until - now + 0.999))
            count += 1
            if count >= self.maximum:
                locked_until = now + self.lock_seconds
            self._attempts[folded] = (count, locked_until)
            return max(0, int(locked_until - now + 0.999))

    def success(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key.casefold(), None)


class AuthService:
    def __init__(self, store: AuthStore, ttl_hours: float, maximum: int, lock_seconds: int,
                 lease_ttl_seconds: float = 180.0) -> None:
        self.store = store
        self.sessions = SessionStore(ttl_hours, store.admin_mode_version, lease_ttl_seconds)
        self.limiter = LoginLimiter(maximum, lock_seconds)

    def login(self, username: str, password: str) -> Identity:
        key = f"login:{username.strip().casefold()}"
        retry = self.limiter.retry_after(key)
        if retry:
            raise HTTPException(429, {"message": "登录尝试过多，请稍后重试", "retry_after": retry})
        account = self.store.authenticate(username, password)
        if account is None:
            retry = self.limiter.failure(key)
            if retry:
                raise HTTPException(429, {"message": "登录尝试过多，请稍后重试", "retry_after": retry})
            raise HTTPException(401, "用户名或密码错误")
        self.limiter.success(key)
        return self.sessions.create(str(account["username"]), str(account["role"]))


_active_identity: ContextVar[Identity | None] = ContextVar("active_identity", default=None)


def active_identity() -> Identity:
    identity = _active_identity.get()
    if identity is None:
        raise HTTPException(401, "未认证")
    return identity


def optional_active_identity() -> Identity | None:
    return _active_identity.get()


def current_user(request: Request) -> Identity:
    identity = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(401, "未认证")
    return identity


def require_role(*roles: str):
    def dependency(request: Request) -> Identity:
        identity = current_user(request)
        if identity.role not in roles:
            raise HTTPException(403, "当前账号无权执行此操作")
        return identity
    return dependency


def require_project_access(project, *, write: bool = False) -> Identity:
    """Authorize a loaded ProjectSpec; callers remain responsible for 404s."""
    identity = active_identity()
    if identity.role == "guest":
        if write:
            raise HTTPException(403, "游客账号为只读权限")
        if project.lifecycle.status != "baseline":
            raise HTTPException(403, "游客只能访问基线项目")
    if write:
        if identity.role not in {"engineer", "admin"}:
            raise HTTPException(403, "当前账号无项目写入权限")
        owner = project.lifecycle.checked_out_by
        if project.lifecycle.status == "checked_out":
            if owner and owner.casefold() != identity.username.casefold():
                raise HTTPException(403, f"项目已由 {owner} 签出，当前仅可只读访问")
            lease_id = str(getattr(project.lifecycle, "lease_id", "") or "")
            if lease_id and lease_id != identity.lease_id:
                raise HTTPException(403, "项目由同账号的另一个登录会话持有签出租约")
    return identity


def set_active_identity(identity: Identity):
    return _active_identity.set(identity)


def reset_active_identity(token) -> None:
    _active_identity.reset(token)
