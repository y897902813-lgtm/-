"""Start, inspect, or stop the owned Hub + integrated VZ process pair.

`python run.py` / `python run.py start`: start the services.
`python run.py stop`: from any SSH terminal, safely stop this deployment.
`python run.py stop --legacy-vz`: opt-in Linux cleanup of a verified pre-upgrade VZ listener.
`python run.py status`: report owned processes without killing other listeners.
"""
from __future__ import annotations

import atexit
import os
import secrets
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from threading import Timer

ROOT = Path(__file__).resolve().parent
VZ_ROOT = ROOT / "integrations" / "VZ_Studio_V0.3.2.1"
sys.path.insert(0, str(ROOT / "backend"))

# `stop` must work even if the network JSON has accidentally become invalid.
from app.storage_config import resolved_data_root  # noqa: E402
from app.port_settings import ENV_KEYS, load_ports  # noqa: E402
from launcher_lifecycle import (  # noqa: E402
    LauncherLifecycle, managed_status, port_available, stop_managed, stop_legacy_vz,
)

DATA_ROOT = resolved_data_root(ROOT)
LAUNCHER_STATE_DIR = DATA_ROOT / ".runtime"


def configure_runtime() -> tuple[str, int]:
    """Configure one server shape for host and remote browser clients alike."""
    os.environ["MUJOCO_STUDIO_SINGLE_USER"] = "0"
    os.environ["MUJOCO_STUDIO_DESKTOP"] = "0"
    host = os.getenv("MUJOCO_STUDIO_HOST", "0.0.0.0")
    port = load_ports()["hub"]
    return host, port


def start_integrated_vz(lifecycle: LauncherLifecycle) -> subprocess.Popen[bytes] | None:
    if os.getenv("MUJOCO_STUDIO_VZ_ENABLED", "1").lower() in {"0", "false", "no", "off"}:
        print("集成 VZ 服务已禁用（MUJOCO_STUDIO_VZ_ENABLED=0）")
        return None
    if not (VZ_ROOT / "run.py").is_file():
        raise RuntimeError(f"未找到集成 VZ 0.3.2.1：{VZ_ROOT}")
    ports = load_ports()
    vz_port = ports["vz"]
    hub_port = ports["hub"]
    vz_host = os.getenv("VZ_HOST", "0.0.0.0")
    # A previous owner may just have been reaped by the manifest recovery.
    # The OS can take a short moment to retire its listening socket; never
    # adopt another listener merely because it answers a health probe.
    for _ in range(30):
        if port_available(vz_host, vz_port):
            break
        time.sleep(0.1)
    if not port_available(vz_host, vz_port):
        raise RuntimeError(
            f"VZ 端口 {vz_port} 已被占用；拒绝复用或结束未知进程。"
            f"请先运行 python run.py status / python run.py stop；"
            f"若仍占用，用 ss -ltnp '( sport = :{vz_port} )' 确认旧进程后人工处理。"
        )
    bridge_token = os.getenv("MUJOCO_STUDIO_VZ_BRIDGE_TOKEN", "").strip() or secrets.token_urlsafe(32)
    os.environ["MUJOCO_STUDIO_VZ_BRIDGE_TOKEN"] = bridge_token
    env = os.environ.copy()
    env.setdefault("VZ_HOST", "0.0.0.0")
    env["VZ_PORT"] = str(vz_port)
    env["VZ_NO_BROWSER"] = "1"
    env["VZ_SKIP_DEPENDENCY_INSTALL"] = "1"
    env["VZ_PROJECT_ROOT"] = str((DATA_ROOT / "vz").resolve())
    env["VZ_HUB_URL"] = os.getenv("MUJOCO_STUDIO_INTERNAL_URL", f"http://127.0.0.1:{hub_port}").rstrip("/")
    env["VZ_HUB_BRIDGE_TOKEN"] = bridge_token
    # POSIX: isolate VZ from the SSH terminal Ctrl+C group. The parent owns
    # explicit SIGTERM/SIGKILL escalation for the full VZ process group.
    process = subprocess.Popen(
        [sys.executable, str(VZ_ROOT / "run.py")], cwd=str(VZ_ROOT), env=env,
        start_new_session=(os.name != "nt"),
        creationflags=(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0),
    )
    lifecycle.attach_vz(process)
    print(f"已启动集成 VZ 0.3.2.1：工程师 http://127.0.0.1:{vz_port}/engineer · 用户 http://127.0.0.1:{vz_port}/client", flush=True)
    # Detect bind failures before reporting a successful launch; if the child
    # fails, `finally` still terminates/reaps it and clears the PID manifest.
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"集成 VZ 启动失败（exit={process.returncode}）；请检查 {vz_port} 端口与依赖")
        if not port_available(vz_host, vz_port):
            return process
        time.sleep(0.1)
    raise RuntimeError(f"集成 VZ 在 15s 内未监听 {vz_port}；已中止启动以避免孤儿进程")


def _install_early_shutdown_handlers() -> dict[int, object]:
    """Cover SIGHUP (SSH disconnect) and early SIGTERM before uvicorn starts.

    Uvicorn owns SIGINT/SIGTERM during active serving and restores our handlers
    afterward. `finally` handles orderly uvicorn exits.
    """
    previous: dict[int, object] = {}

    def _shutdown_on_signal(caught: int, _frame: object) -> None:
        raise SystemExit(128 + caught)

    for name in ("SIGHUP", "SIGTERM"):
        signum = getattr(signal, name, None)
        if signum is None:
            continue
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, _shutdown_on_signal)
    return previous


def main() -> None:
    if sys.version_info < (3, 10):
        raise SystemExit("MuJoCo Studio requires Python 3.10 or newer")
    # Keep `stop`/`status` working without importing uvicorn or the full app.
    command = sys.argv[1] if len(sys.argv) > 1 else "start"
    if command == "status" and len(sys.argv) == 2:
        info = managed_status(LAUNCHER_STATE_DIR, ROOT)
        print(f"Hub: {'运行中' if info['hub'] else '未由本启动器运行'} · VZ: {'运行中' if info['vz'] else '未由本启动器运行'}")
        if info["record"]:
            print(f"记录的 PID/端口: Hub={info['record'].get('parent')}, VZ={info['record'].get('vz')}, ports={info['record'].get('ports')}")
        print("提示：不会自动管理用户电脑上独立运行的 Client，也不会结束未知端口所有者。")
        return
    if command == "stop" and len(sys.argv) in {2, 3}:
        legacy = len(sys.argv) == 3 and sys.argv[2] == "--legacy-vz"
        if len(sys.argv) == 3 and not legacy:
            raise SystemExit("用法：python run.py stop [--legacy-vz]")
        ok = stop_managed(LAUNCHER_STATE_DIR, ROOT)
        if legacy:
            # Explicit opt-in: identify the exact integrated VZ script + TCP
            # listener inode before touching an old pre-2.16.11.3 process.
            ok = stop_legacy_vz(load_ports()["vz"], ROOT) and ok
        if not ok:
            raise SystemExit(1)
        return
    if command not in {"start"} or len(sys.argv) > 2:
        raise SystemExit("用法：python run.py [start|stop [--legacy-vz]|status]")

    import uvicorn
    host, port = configure_runtime()
    ports = load_ports()
    for name, env_key in ENV_KEYS.items():
        if os.getenv(env_key, "").strip():
            print(f"注意：环境变量 {env_key} 正在覆盖 ports.json 中的 {name} 端口。")
    os.environ.setdefault("MUJOCO_STUDIO_URL", f"http://127.0.0.1:{port}")
    print(f"部署端口：Hub {port} · Client (用户本机) {ports['client']} · VZ {ports['vz']}")

    lifecycle = LauncherLifecycle(LAUNCHER_STATE_DIR, ROOT, ports)
    lifecycle.acquire()
    atexit.register(lifecycle.close)
    early_handlers = _install_early_shutdown_handlers()
    browser_timer: Timer | None = None
    try:
        if not port_available(host, port):
            raise RuntimeError(f"Hub 端口 {port} 已被占用。请先运行 python run.py status / stop 并核对监听进程")
        start_integrated_vz(lifecycle)
        if os.getenv("MUJOCO_STUDIO_NO_BROWSER", "").lower() not in {"1", "true", "yes"}:
            browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
            browser_timer = Timer(1.2, lambda: webbrowser.open(f"http://{browser_host}:{port}"))
            browser_timer.daemon = True
            browser_timer.start()
        print("停止服务：在当前终端按 Ctrl+C，或从另一终端运行 python run.py stop", flush=True)
        uvicorn.run("app.main:app", host=host, port=port, app_dir=str(ROOT / "backend"), reload=False)
    except KeyboardInterrupt:
        print("收到 Ctrl+C，正在关闭 Hub 与受管 VZ……", flush=True)
    finally:
        if browser_timer is not None:
            browser_timer.cancel()
        lifecycle.close()
        for signum, previous in early_handlers.items():
            signal.signal(signum, previous)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        raise SystemExit(f"启动器错误：{exc}") from exc
