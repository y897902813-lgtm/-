"""One deployment-level source for Hub, local Client bridge and integrated VZ ports.

Server/ports.json is intentionally outside ProjectSpec and all frozen assets.
Environment overrides are supported only for existing deployment integrations.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping


PORTS_FILE = Path(__file__).resolve().parents[2] / "ports.json"
DEFAULT_PORTS = {"hub": 8765, "client": 8766, "vz": 8877}
ENV_KEYS = {
    "hub": "MUJOCO_STUDIO_PORT",
    "client": "MUJOCO_STUDIO_CLIENT_PORT",
    "vz": "VZ_PORT",
}


def _valid_port(value: object, description: str) -> int:
    if type(value) is not int or not 1 <= value <= 65535:
        raise ValueError(f"{description} 必须是 1 到 65535 的整数（不能为 bool/字符串）")
    return value


def load_ports(*, path: Path | None = None, environ: Mapping[str, str] | None = None) -> dict[str, int]:
    """Load, validate and de-duplicate all three ports at process startup.

    File defaults keep pre-existing unpacked deployments working. A supplied
    non-empty environment override takes precedence for compatibility.
    """
    location = PORTS_FILE if path is None else Path(path)
    ports = DEFAULT_PORTS.copy()
    try:
        contents = json.loads(location.read_text(encoding="utf-8"))
    except FileNotFoundError:
        contents = {}
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"无法读取统一端口配置 {location}：{exc}") from exc
    if not isinstance(contents, dict):
        raise ValueError(f"{location} 必须是包含 hub/client/vz 的 JSON 对象")
    for name in ports:
        if name in contents:
            ports[name] = _valid_port(contents[name], f"{location} 中的 {name}")
    env = os.environ if environ is None else environ
    for name, env_key in ENV_KEYS.items():
        value = str(env.get(env_key, "")).strip()
        if value:
            try:
                ports[name] = _valid_port(int(value), env_key)
            except ValueError as exc:
                raise ValueError(f"无效端口环境变量 {env_key}={value!r}") from exc
    if len(set(ports.values())) != len(ports):
        raise ValueError(f"Hub / Client / VZ 三个端口不能相同：{ports}")
    return ports
