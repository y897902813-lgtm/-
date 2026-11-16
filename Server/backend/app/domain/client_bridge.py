"""One-time client tickets and a bounded server-side mesh-version stack."""
from __future__ import annotations

import json
import secrets
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


class ClientTicketError(ValueError):
    pass


class ClientTicketStore:
    def __init__(self, ttl_seconds: float = 60.0, maximum: int = 512) -> None:
        self.ttl_seconds = max(5.0, float(ttl_seconds))
        self.maximum = max(16, int(maximum))
        self._items: dict[str, dict[str, Any]] = {}
        self._issued_by_session: dict[str, list[float]] = {}
        self._lock = RLock()

    def issue(self, *, project_id: str, purpose: str, username: str, role: str, lease_id: str,
              session_id: str = "") -> str:
        if purpose not in {"mesh_sync", "viewer_launch", "select_mesh_path"}:
            raise ClientTicketError("不支持的客户端任务")
        now = time.monotonic()
        ticket = secrets.token_urlsafe(32)
        with self._lock:
            self._prune(now)
            session_key = str(session_id or lease_id)
            recent = [stamp for stamp in self._issued_by_session.get(session_key, []) if now - stamp < 60.0]
            if len(recent) >= 10:
                raise ClientTicketError("client_ticket_rate_limited")
            recent.append(now)
            self._issued_by_session[session_key] = recent
            if len(self._items) >= self.maximum:
                oldest = min(self._items, key=lambda key: self._items[key]["created_at"])
                self._items.pop(oldest, None)
            self._items[ticket] = {
                "project_id": str(project_id),
                "purpose": purpose,
                "username": str(username),
                "role": str(role),
                "lease_id": str(lease_id),
                "session_id": str(session_id),
                "created_at": now,
                "expires_at": now + self.ttl_seconds,
            }
        return ticket

    def consume(self, ticket: str, purpose: str) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            item = self._items.pop(str(ticket), None)
        if item is None:
            raise ClientTicketError("客户端票据不存在、已使用或已过期")
        if item["purpose"] != purpose:
            raise ClientTicketError("客户端票据用途不匹配")
        return dict(item)

    def _prune(self, now: float) -> None:
        for key in [key for key, item in self._items.items() if item["expires_at"] <= now]:
            self._items.pop(key, None)
        for key, values in list(self._issued_by_session.items()):
            recent = [stamp for stamp in values if now - stamp < 60.0]
            if recent:
                self._issued_by_session[key] = recent
            else:
                self._issued_by_session.pop(key, None)
