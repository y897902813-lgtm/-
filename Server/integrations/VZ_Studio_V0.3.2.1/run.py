from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from threading import Timer

from vz import __version__
from vz.server import make_server


ROOT = Path(__file__).resolve().parent


def resolve_project_root() -> Path:
    override = os.getenv("VZ_PROJECT_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform.startswith("linux"):
        return ROOT / "VZ_project"
    if os.name == "nt":
        return Path("E:/VZ_project")
    return ROOT / "VZ_project"


def prepare_project_root() -> Path:
    target = resolve_project_root()
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".vz_storage_probe"
        probe.write_bytes(b"VZ")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise SystemExit(
            f"VZ_project 工程目录不可用：{target}\n"
            f"请确认目标磁盘存在且当前用户有读写权限。系统错误：{exc}"
        ) from exc
    # Upgrade convenience: copy one legacy VZ root only when the unified target
    # does not already contain model data.  Integrated Server V2.12.0 normally
    # supplies VZ_PROJECT_ROOT=<V2_projec>/vz, so this path is migration-only.
    legacy_candidates = [ROOT / "VZ_project", ROOT / "data"]
    if os.name == "nt":
        legacy_candidates.append(Path("E:/VZ_project"))
    if not (target / "models").exists():
        for legacy in legacy_candidates:
            try:
                if legacy.resolve() == target:
                    continue
            except OSError:
                pass
            if legacy.is_dir() and (legacy / "models").is_dir():
                shutil.copytree(legacy, target, dirs_exist_ok=True)
                break
    return target


def ensure_dependencies() -> None:
    if os.getenv("VZ_SKIP_DEPENDENCY_INSTALL", "").lower() in {"1", "true", "yes"}:
        return
    try:
        import mujoco  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        print("首次运行：正在安装 MuJoCo 动画仿真依赖，请保持网络连接……")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "numpy>=1.24,<3", "mujoco>=3.1,<4",
            ])
            print("MuJoCo 仿真依赖安装完成。")
        except Exception as exc:
            print(f"警告：MuJoCo 自动安装失败（建模功能仍可使用）：{exc}")
            print('可稍后执行：python -m pip install "numpy>=1.24,<3" "mujoco>=3.1,<4"')


def main() -> None:
    if sys.version_info < (3, 10):
        raise SystemExit("VZ Studio 需要 Python 3.10 或更新版本")
    ensure_dependencies()
    project_root = prepare_project_root()
    host = os.getenv("VZ_HOST", "0.0.0.0")
    # Running via Server/run.py supplies VZ_PORT; standalone integrated VZ
    # reads the same Server/ports.json instead of retaining an unrelated default.
    ports_file = ROOT.parents[1] / "ports.json"
    configured = 8877
    try:
        parsed_ports = json.loads(ports_file.read_text(encoding="utf-8"))
        configured = parsed_ports.get("vz", configured)
    except FileNotFoundError:
        pass
    except (OSError, UnicodeError, ValueError) as exc:
        raise SystemExit(f"无法读取统一端口配置 {ports_file}：{exc}") from exc
    if type(configured) is not int or not 1 <= configured <= 65535:
        raise SystemExit(f"ports.json 中的 vz 端口无效：{configured!r}")
    try:
        port = int(os.getenv("VZ_PORT", "").strip() or configured)
    except ValueError as exc:
        raise SystemExit("VZ_PORT 环境变量不是有效数字") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("VZ_PORT 必须在 1 到 65535 之间")
    server = make_server(ROOT, host, port, data_root=project_root)
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    engineer_url = f"http://{browser_host}:{port}/engineer"
    client_url = f"http://{browser_host}:{port}/client"
    print(f"VZ Studio {__version__} 已启动（无需账号）")
    print(f"工程目录:   {project_root}")
    print(f"工程师网址: {engineer_url}")
    print(f"用户网址:   {client_url}")
    if os.getenv("VZ_NO_BROWSER", "").lower() not in {"1", "true", "yes"}:
        Timer(0.8, lambda: webbrowser.open(engineer_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
