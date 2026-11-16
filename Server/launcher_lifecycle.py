"""Local, ownership-checked Hub/VZ launcher lifecycle; no global port-based kills.

The runtime manifest is L3 deployment state, *not* a model/ProjectSpec artifact.
On Linux a PID is trusted only if its /proc start time AND run.py command
match the recorded instance. `run.py stop` cannot stop unrelated listeners.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


LAUNCHER_FILE = "studio_launcher.json"
LAUNCHER_LOCK = "studio_launcher.lock"


def process_birth(pid: int) -> str | None:
    """A PID-reuse-resistant OS process start marker (no new dependency)."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    if sys.platform.startswith("linux"):
        try:
            entry = Path(f"/proc/{pid}")
            if hasattr(os, "geteuid") and os.geteuid() != 0 and entry.stat().st_uid != os.geteuid():
                return None
            raw = (entry / "stat").read_text("utf-8")
            # Field 2 (comm) may contain spaces or ')'; field 3 follows final ') '.
            fields = raw.rsplit(") ", 1)[1].split()
            return "linux:" + fields[19]  # field 22: starttime clock ticks
        except (OSError, ValueError, IndexError):
            return None
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.windll.kernel32
            kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
            kernel.GetProcessTimes.restype = wintypes.BOOL
            handle = kernel.OpenProcess(0x1000, False, pid)  # query-limited information
            if not handle:
                return None
            try:
                creation = wintypes.FILETIME()
                exit_time, kernel_time, user_time = (wintypes.FILETIME() for _ in range(3))
                if not kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time),
                                              ctypes.byref(kernel_time), ctypes.byref(user_time)):
                    return None
                return f"windows:{(creation.dwHighDateTime << 32) | creation.dwLowDateTime}"
            finally:
                kernel.CloseHandle(handle)
        except (OSError, AttributeError):
            return None
    # macOS/BSD: ps start date is the best portable stdlib-only discriminator;
    # command-path verification below is also mandatory.
    try:
        result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="],
                                capture_output=True, text=True, timeout=2, check=False)
        value = result.stdout.strip()
        return "ps:" + value if result.returncode == 0 and value else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _matches_script(pid: int, script: Path) -> bool:
    if sys.platform.startswith("linux"):
        try:
            args = [value.decode("utf-8", "surrogateescape") for value in
                    (Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")) if value]
            cwd = Path(f"/proc/{pid}/cwd").resolve()
            return any((cwd / value).resolve() == script.resolve() for value in args if value.endswith("run.py"))
        except (OSError, RuntimeError, ValueError):
            return False
    # On other platforms birth time is checked; process executable path checks
    # are not reliably available in the stdlib without privileges. Only process
    # IDs written by this exact launcher into its private directory are eligible.
    return True


def verified_alive(entry: object, script: Path) -> bool:
    if not isinstance(entry, dict):
        return False
    pid = entry.get("pid")
    marker = entry.get("birth")
    return (type(pid) is int and isinstance(marker, str) and bool(marker)
            and process_birth(pid) == marker and _matches_script(pid, script))


def port_available(host: str, port: int) -> bool:
    """Check actual bind semantics, not just a localhost TCP health endpoint."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return True
    except OSError:
        return False


def _signal_pid(pid: int, sig: int) -> bool:
    try:
        os.kill(pid, sig)
        return True
    except (OSError, ValueError):
        return False


def _signal_vz(entry: dict[str, Any], sig: int) -> bool:
    pid = entry["pid"]
    if os.name != "nt" and entry.get("own_group"):
        try:
            # Never send a signal to a process group we did not create.
            if os.getpgid(pid) == pid:
                os.killpg(pid, sig)
                return True
        except (OSError, ProcessLookupError):
            return False
    return _signal_pid(pid, sig)


def _wait_dead(entry: dict[str, Any], script: Path, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not verified_alive(entry, script):
            return True
        time.sleep(0.05)
    return not verified_alive(entry, script)


def stop_vz_entry(entry: object, vz_script: Path, *, grace: float = 3.0) -> bool:
    """Kill only the recorded VZ child; TERM then bounded KILL escalation."""
    if not verified_alive(entry, vz_script):
        return True
    assert isinstance(entry, dict)
    _signal_vz(entry, signal.SIGTERM)
    if _wait_dead(entry, vz_script, grace):
        return True
    if verified_alive(entry, vz_script):
        if os.name == "nt":
            # A verified VZ instance might have spawned transient descendants.
            subprocess.run(["taskkill", "/PID", str(entry["pid"]), "/T", "/F"],
                           capture_output=True, check=False, timeout=3)
        else:
            _signal_vz(entry, signal.SIGKILL)
    return _wait_dead(entry, vz_script, 2.0)


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        record = json.loads(path.read_text("utf-8"))
        return record if isinstance(record, dict) else None
    except (FileNotFoundError, OSError, ValueError, UnicodeError):
        return None


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tempname = tempfile.mkstemp(prefix=".studio_launcher.", suffix=".tmp", dir=path.parent)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tempname, path)
    finally:
        Path(tempname).unlink(missing_ok=True)


def _lock_file(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        if not handle.read(1):
            handle.write(b"1")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("已有 run.py 正在管理本服务器（请使用 python run.py status）") from exc
    else:
        import fcntl
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("已有 run.py 正在管理本服务器（请使用 python run.py status）") from exc


def _unlock_file(handle: Any) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


class LauncherLifecycle:
    """One launcher per data-root; its VZ group and Hub are managed together."""

    def __init__(self, state_dir: Path, server_root: Path, ports: dict[str, int]):
        self.state_dir = Path(state_dir)
        self.server_root = Path(server_root).resolve()
        self.manifest = self.state_dir / LAUNCHER_FILE
        self.lock_path = self.state_dir / LAUNCHER_LOCK
        self.vz_script = self.server_root / "integrations" / "VZ_Studio_V0.3.2.1" / "run.py"
        self.token = uuid.uuid4().hex
        self.record: dict[str, Any] = {
            "schema": 1, "token": self.token, "server_root": str(self.server_root),
            "parent": {"pid": os.getpid(), "birth": process_birth(os.getpid())},
            "vz": None, "ports": dict(ports), "created_at": time.time(),
        }
        self._lock_handle: Any = None
        self._process: subprocess.Popen[Any] | None = None
        self._closed = False

    def acquire(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+b")
        locked = False
        try:
            _lock_file(handle)
            locked = True
            old = _read_manifest(self.manifest)
            if old and old.get("server_root") == str(self.server_root):
                if verified_alive(old.get("parent"), self.server_root / "run.py"):
                    raise RuntimeError("检测到旧 Hub 进程仍然运行；拒绝覆盖其进程记录。请先使用 python run.py stop")
                if verified_alive(old.get("vz"), self.vz_script):
                    print("检测到上次启动遗留的受管 VZ 子进程，正在安全回收……", flush=True)
                    if not stop_vz_entry(old["vz"], self.vz_script):
                        raise RuntimeError("遗留受管 VZ 无法终止，请检查权限与日志")
            _atomic_write(self.manifest, self.record)
            self._lock_handle = handle
        except BaseException:
            if locked:
                _unlock_file(handle)
            else:
                handle.close()
            raise

    def attach_vz(self, process: subprocess.Popen[Any]) -> None:
        self._process = process
        self.record["vz"] = {"pid": process.pid, "birth": process_birth(process.pid),
                             "own_group": True}
        _atomic_write(self.manifest, self.record)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        child = self._process
        if child is not None:
            try:
                stop_vz_entry(self.record.get("vz"), self.vz_script)
                if child.poll() is None:
                    # Emergency fallback, no group signal unless the child is verified.
                    child.terminate()
                    try:
                        child.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        child.kill()
                child.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired) as exc:
                print(f"警告：VZ 关闭后清理失败：{exc}", file=sys.stderr, flush=True)
        if self._lock_handle is not None:
            try:
                if (_read_manifest(self.manifest) or {}).get("token") == self.token:
                    self.manifest.unlink(missing_ok=True)
            finally:
                _unlock_file(self._lock_handle)
                self._lock_handle = None


def _state_paths(state_dir: Path) -> tuple[Path, Path]:
    location = Path(state_dir)
    return location / LAUNCHER_FILE, location / LAUNCHER_LOCK


def managed_status(state_dir: Path, server_root: Path) -> dict[str, Any]:
    path, _ = _state_paths(state_dir)
    record = _read_manifest(path)
    root = Path(server_root).resolve()
    if not record or record.get("server_root") != str(root):
        return {"tracked": False, "hub": False, "vz": False, "record": None}
    vz_script = root / "integrations" / "VZ_Studio_V0.3.2.1" / "run.py"
    return {
        "tracked": True,
        "hub": verified_alive(record.get("parent"), root / "run.py"),
        "vz": verified_alive(record.get("vz"), vz_script),
        "record": record,
    }


def stop_managed(state_dir: Path, server_root: Path, *, grace: float = 8.0) -> bool:
    """Stop only PID/birth/script-verified processes from our own manifest.

    Does not kill arbitrary port owners, standalone VZ, or remote/local Client.
    """
    info = managed_status(state_dir, server_root)
    if not info["tracked"]:
        print("没有找到此部署的受管 Hub/VZ 进程记录；不会按端口盲目结束其他服务。")
        return True
    record = info["record"]
    assert isinstance(record, dict)
    root = Path(server_root).resolve()
    hub_script = root / "run.py"
    vz_script = root / "integrations" / "VZ_Studio_V0.3.2.1" / "run.py"
    parent = record.get("parent")
    vz = record.get("vz")
    if verified_alive(parent, hub_script):
        pid = parent["pid"]
        print(f"正在停止 Hub PID {pid}（由 Hub 清理 VZ）……", flush=True)
        _signal_pid(pid, signal.SIGTERM)
        if not _wait_dead(parent, hub_script, grace):
            print(f"Hub PID {pid} 未在 {grace:.1f}s 内退出，正在强制终止已验证进程。", flush=True)
            if verified_alive(parent, hub_script):
                _signal_pid(pid, signal.SIGKILL if os.name != "nt" else signal.SIGTERM)
            _wait_dead(parent, hub_script, 2.0)
    if verified_alive(vz, vz_script):
        print(f"正在清理 VZ PID {vz['pid']}……", flush=True)
        stop_vz_entry(vz, vz_script)
    remains = verified_alive(parent, hub_script) or verified_alive(vz, vz_script)
    if not remains:
        path, _ = _state_paths(state_dir)
        # If a new launcher has replaced the record, never erase its manifest.
        if (_read_manifest(path) or {}).get("token") == record.get("token"):
            path.unlink(missing_ok=True)
        print("受管 Hub/VZ 已停止。独立 Client 应在用户自己的电脑停止。", flush=True)
    else:
        print("有受管进程尚未退出；请运行 python run.py status 检查。", file=sys.stderr, flush=True)
    return not remains


def _linux_listening_socket_inodes(port: int) -> set[str]:
    """Kernel TCP LISTEN socket inodes for one local port (Linux only)."""
    found: set[str] = set()
    for filename in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(filename).read_text("ascii").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            values = line.split()
            if len(values) > 9 and values[3] == "0A":
                try:
                    if int(values[1].rsplit(":", 1)[-1], 16) == port:
                        found.add(values[9])
                except (ValueError, IndexError):
                    pass
    return found


def _linux_legacy_vz_owners(port: int, vz_script: Path) -> list[dict[str, Any]]:
    """Match an actual listener by socket inode AND exact VZ script (no port kills)."""
    if not sys.platform.startswith("linux"):
        return []
    inodes = _linux_listening_socket_inodes(port)
    if not inodes:
        return []
    owners = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        pid = int(entry.name)
        birth = process_birth(pid)
        if not birth or not _matches_script(pid, vz_script):
            continue
        try:
            matches = any(
                os.readlink(fd) in {f"socket:[{inode}]" for inode in inodes}
                for fd in (entry / "fd").iterdir()
            )
        except (OSError, PermissionError):
            continue
        if matches:
            owners.append({"pid": pid, "birth": birth})
    return owners


def stop_legacy_vz(port: int, server_root: Path) -> bool:
    """Opt-in migration of a pre-manifest VZ listener, never a blind fuser kill.

    Only supported on Linux (the requested VS Code SSH deployment). Port must
    belong to the exact integrated VZ run.py script under this source tree.
    """
    vz_script = Path(server_root).resolve() / "integrations" / "VZ_Studio_V0.3.2.1" / "run.py"
    if not sys.platform.startswith("linux"):
        print("--legacy-vz 仅支持 Linux /proc 的监听 socket 归属校验；其他系统请人工核实 PID。", file=sys.stderr)
        return False
    owners = _linux_legacy_vz_owners(port, vz_script)
    if not owners:
        if _linux_listening_socket_inodes(port):
            print(f"端口 {port} 已被占用，但不是本源码的集成 VZ run.py；不会结束该进程。", file=sys.stderr)
            return False
        print(f"端口 {port} 没有需要回收的旧版 VZ 监听进程。")
        return True
    for entry in owners:
        if not verified_alive(entry, vz_script):
            continue
        # Recheck port ownership immediately before the destructive action.
        if not any(item["pid"] == entry["pid"] and item["birth"] == entry["birth"]
                   for item in _linux_legacy_vz_owners(port, vz_script)):
            continue
        print(f"确认旧版 VZ 进程 PID={entry['pid']} 正在监听端口 {port}；尝试温和终止……", flush=True)
        _signal_pid(entry["pid"], signal.SIGTERM)
        if not _wait_dead(entry, vz_script, 4.0) and verified_alive(entry, vz_script):
            _signal_pid(entry["pid"], signal.SIGKILL)
            _wait_dead(entry, vz_script, 2.0)
    # Do not call this a success if an unrelated listener took over the port.
    time.sleep(0.1)
    if _linux_listening_socket_inodes(port):
        print(f"端口 {port} 仍有监听者；请用 ss -ltnp 核实，不会继续盲杀。", file=sys.stderr)
        return False
    print(f"旧版受验证 VZ 端口 {port} 已释放。", flush=True)
    return True
