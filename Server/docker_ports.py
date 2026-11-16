"""Run docker compose using the single ports.json config for port mappings.

Example: python docker_ports.py up --build -d
Never publishes the unauthenticated VZ listener or localhost-only Client bridge.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
from app.port_settings import ENV_KEYS, load_ports  # noqa: E402


def main() -> int:
    ports = load_ports()
    env = os.environ.copy()
    for name, key in ENV_KEYS.items():
        env[key] = str(ports[name])
    return subprocess.call(["docker", "compose", *sys.argv[1:]], cwd=str(ROOT), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
