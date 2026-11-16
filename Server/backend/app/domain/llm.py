"""OpenAI-compatible LLM transport, private credentials and conversation stream."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterator
from typing import Any

from .models import AgentSettings


def completion_url(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("大模型 API 地址不能为空")
    return value if value.endswith("/chat/completions") else f"{value}/chat/completions"


class LLMCredentialStore:
    """Keep API keys outside project snapshots, exports and the event stream."""

    def __init__(self, path: Path):
        self.path = path

    def api_key(self) -> str:
        environment = os.getenv("LLM_API_KEY", "").strip()
        if environment:
            return environment
        try:
            data = json.loads(self.path.read_text("utf-8"))
            return str(data.get("api_key", "")).strip()
        except (OSError, ValueError):
            return ""

    def status(self) -> dict[str, Any]:
        value = self.api_key()
        return {"configured": bool(value), "masked": f"••••{value[-4:]}" if len(value) >= 4 else ("••••" if value else "")}

    def save(self, api_key: str) -> dict[str, Any]:
        value = str(api_key).strip()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"api_key": value}, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.path)
        return self.status()


class ConversationStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        items = []
        for line in self.path.read_text("utf-8").splitlines():
            try:
                item = json.loads(line)
                if item.get("role") in {"user", "assistant", "system"}:
                    items.append(item)
            except ValueError:
                continue
        return items

    def append(self, role: str, content: str, **metadata: Any) -> dict[str, Any]:
        item = {"role": role, "content": str(content), "created_at": datetime.now(timezone.utc).isoformat(), **metadata}
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        return item

    def context(self, rounds: int) -> list[dict[str, str]]:
        messages = [item for item in self.list() if item.get("role") in {"user", "assistant"}]
        return [{"role": item["role"], "content": item["content"]} for item in messages[-max(1, rounds) * 2:]]


def chat_completion_stream(
    settings: AgentSettings, api_key: str, messages: list[dict[str, str]], *, timeout: float = 45.0,
) -> Iterator[str]:
    """Yield OpenAI-compatible SSE deltas; every LLM request uses streaming transport."""
    if not api_key:
        raise ValueError("尚未配置大模型 API 密钥")
    request = urllib.request.Request(
        completion_url(settings.base_url),
        data=json.dumps({"model": settings.model, "messages": messages, "stream": True, "temperature": 0}, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = str(response.headers.get("Content-Type", "")) if getattr(response, "headers", None) else ""
            if "text/event-stream" not in content_type:
                payload = json.loads(response.read().decode("utf-8"))
                content = payload["choices"][0]["message"]["content"]
                if content:
                    yield str(content)
                return
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                payload = json.loads(data)
                delta = payload.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield str(delta)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"大模型服务返回 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"无法连接大模型服务：{exc.reason}") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("大模型响应不符合 OpenAI chat/completions 格式") from exc


def chat_completion(settings: AgentSettings, api_key: str, messages: list[dict[str, str]], *, timeout: float = 45.0) -> str:
    return "".join(chat_completion_stream(settings, api_key, messages, timeout=timeout))


def parse_json_object(content: str) -> dict[str, Any]:
    text = str(content).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    try:
        value = json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("大模型未返回可解析的 JSON 计划")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("大模型计划必须是 JSON 对象")
    return value
