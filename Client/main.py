"""MuJoCo Studio lightweight localhost bridge.

The client owns no simulation policy. It only selects a local mesh directory,
redeems one-time server tickets, verifies the returned bundle, and launches
the server-supplied controller with the local MuJoCo installation.
"""
from __future__ import annotations

import hashlib
import http.client
import importlib.util
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any

from asset_binding import AssetBindingError, build_local_asset_map, rewrite_legacy_mesh_paths
from viewer_status import ViewerRegistry


ROOT = Path(__file__).resolve().parent

# The Hub's target IP and all three ports are configured in Server/ports.json
# for an integrated source tree, or in Client/ports.json for a standalone Client.
# MUJOCO_STUDIO_SERVER_IP and the three established port environment variables
# retain priority for existing managed deployments.
DEFAULT_SERVER_IP = "10.13.90.107"


def _server_host(value: object, description: str) -> str:
    """Validate a host only, never a scheme, port, path, or arbitrary URL."""
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 253:
        raise ValueError(f"{description} 必须是非空的 IP 地址或主机名")
    stripped = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    try:
        ip = ipaddress.ip_address(stripped)
    except ValueError:
        # Retain the legacy ability to target DNS names such as localhost.
        # Reject malformed numeric IPv4 instead of treating it as a DNS name.
        if re.fullmatch(r"[0-9.]+", value) or not all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part)
            for part in value.split(".")
        ):
            raise ValueError(f"{description} 不是有效 IP 地址或主机名：{value!r}")
        return value
    if ip.is_unspecified or ip.is_multicast:
        raise ValueError(f"{description} 不能是未指定或组播地址：{value!r}")
    return f"[{ip.compressed}]" if ip.version == 6 else str(ip)


def _deployment_settings() -> tuple[dict[str, int], str]:
    ports = {"hub": 8765, "client": 8766, "vz": 8877}
    shared_file = ROOT.parent / "Server" / "ports.json"
    local_file = ROOT / "ports.json"
    source = shared_file if shared_file.is_file() else local_file
    try:
        stored = json.loads(source.read_text("utf-8"))
    except FileNotFoundError:
        stored = {}
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError(f"无法读取 Client 网络配置 {source}：{exc}") from exc
    if not isinstance(stored, dict):
        raise ValueError(f"{source} 必须是 JSON 对象")
    for name in ports:
        if name in stored:
            value = stored[name]
            if type(value) is not int or not 1 <= value <= 65535:
                raise ValueError(f"{source} 中的 {name} 必须是 1-65535 的整数")
            ports[name] = value
    server_ip = _server_host(stored.get("server_ip", DEFAULT_SERVER_IP), f"{source} 中的 server_ip")
    for name, env_key in {"hub": "MUJOCO_STUDIO_PORT", "client": "MUJOCO_STUDIO_CLIENT_PORT", "vz": "VZ_PORT"}.items():
        configured = os.getenv(env_key, "").strip()
        if configured:
            try:
                port = int(configured)
            except ValueError as exc:
                raise ValueError(f"{env_key} 必须是数字端口") from exc
            if not 1 <= port <= 65535:
                raise ValueError(f"{env_key} 必须在 1-65535 之间")
            ports[name] = port
    if len(set(ports.values())) != 3:
        raise ValueError(f"Hub/Client/VZ 端口不能冲突：{ports}")
    env_server_ip = os.getenv("MUJOCO_STUDIO_SERVER_IP", "").strip()
    if env_server_ip:
        server_ip = _server_host(env_server_ip, "MUJOCO_STUDIO_SERVER_IP")
    return ports, server_ip


def _deployment_ports() -> dict[str, int]:
    """Backwards-compatible read of the port subset."""
    return _deployment_settings()[0]


_NETWORK_PORTS, SERVER_IP = _deployment_settings()
SERVER_PORT = _NETWORK_PORTS["hub"]
SERVER_URL = f"http://{SERVER_IP}:{SERVER_PORT}"
# Security: the Client Viewer bridge always binds localhost, not SERVER_IP.
HOST = "127.0.0.1"
PORT = _NETWORK_PORTS["client"]
CLIENT_VERSION = "0.3.9"
CONFIG_PATH = ROOT / "client_config.json"
RUNTIME_ROOT = Path(os.getenv("MUJOCO_STUDIO_CLIENT_DATA", str(Path.home() / ".mujoco_studio_client"))).expanduser()
ASSET_EXTENSIONS = {".stl", ".obj", ".mtl", ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".webp"}
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024 * 1024
CLIENT_ORPHAN_TTL_HOURS = max(1.0, float(os.getenv("MUJOCO_STUDIO_CLIENT_ORPHAN_TTL_HOURS", "24")))


class ClientError(ValueError):
    def __init__(self, message: str, *, code: str = "client_error", details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(value).split("."))
    except ValueError:
        return (0,)


def _reclaim_client_runtime(root: Path, live_bundles: set[Path], ttl_hours: float) -> dict[str, int]:
    """Delete only expired client runtime bundles/mesh-sync archives.

    The runner refreshes the bundle directory mtime while a Viewer is alive, so a
    Viewer that survives a client restart remains protected even though the new
    in-memory registry cannot reconstruct the old Popen object.
    """
    root = Path(root)
    if not root.is_dir():
        return {"bundles": 0, "mesh_sync_archives": 0}
    cutoff = time.time() - max(1.0, float(ttl_hours)) * 3600.0
    protected = {Path(path).resolve() for path in live_bundles}
    removed_bundles = 0
    removed_archives = 0
    for path in root.iterdir():
        try:
            if path.is_symlink():
                continue
            is_bundle = path.is_dir() and path.name.startswith("viewer_")
            is_archive = path.is_file() and path.name.startswith("mesh_sync_") and path.suffix == ".zip"
            if not (is_bundle or is_archive):
                continue
            if is_bundle and path.resolve() in protected:
                continue
            if path.stat().st_mtime >= cutoff:
                continue
            if is_bundle:
                shutil.rmtree(path)
                removed_bundles += int(not path.exists())
            else:
                path.unlink(missing_ok=True)
                removed_archives += int(not path.exists())
        except OSError:
            continue
    return {"bundles": removed_bundles, "mesh_sync_archives": removed_archives}


def _origin(url: str) -> str:
    parsed = urllib.parse.urlsplit(str(url))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ClientError("服务端网址必须是 http 或 https 地址")
    return f"{parsed.scheme}://{parsed.netloc}"


class ClientConfig:
    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self.last_error: str | None = None

    def read(self) -> dict[str, Any]:
        with self._lock:
            try:
                value = json.loads(self.path.read_text("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("配置根节点必须是对象")
                self.last_error = None
            except FileNotFoundError:
                value = {}
                self.last_error = None
            except (OSError, ValueError) as exc:
                value = {}
                self.last_error = str(exc)
            return {
                "server_url": SERVER_URL,
                "mesh_path": str(value.get("mesh_path", "")),
            }

    def write(self, value: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # server_url is derived from ports.json server_ip + hub (with optional env overrides).
            # client_config.json only stores local runtime settings, never an old origin.
            stored = dict(value)
            stored.pop("server_url", None)
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=2), "utf-8")
            temporary.replace(self.path)

    def allowed_origin(self) -> str:
        return _origin(self.read()["server_url"])

    def select_mesh_path(self) -> str:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            current = Path(self.read()["mesh_path"]).expanduser()
            selected = filedialog.askdirectory(
                title="选择本机 STL / OBJ 数模路径",
                initialdir=str(current if current.is_dir() else Path.home()),
                mustexist=True,
            )
            root.destroy()
        except Exception as exc:
            raise ClientError(f"无法打开本地路径选择器：{exc}") from exc
        if not selected:
            return ""
        path = Path(selected).resolve()
        if not any(item.is_file() and item.suffix.lower() in {".stl", ".obj"} for item in path.rglob("*")):
            raise ClientError("所选路径中没有 STL 或 OBJ 文件")
        config = self.read()
        config["mesh_path"] = str(path)
        self.write(config)
        return str(path)


def _server_request(server_url: str, path: str, ticket: str, *, body: bytes | None = None,
                    content_type: str = "application/json", timeout: float = 120.0) -> bytes:
    url = f"{server_url.rstrip('/')}{path}"
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "X-MuJoCo-Client-Ticket": ticket,
            "Content-Type": content_type,
            "User-Agent": f"MuJoCo-Studio-Client/{CLIENT_VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raw_detail = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw_detail)
            detail = parsed.get("detail", parsed)
        except ValueError:
            detail = raw_detail
        if isinstance(detail, dict):
            raise ClientError(
                str(detail.get("message", detail)), code=str(detail.get("code", "server_rejected")),
                details=detail,
            ) from exc
        raise ClientError(f"服务端拒绝客户端任务：{detail}") from exc
    except urllib.error.URLError as exc:
        raise ClientError(f"无法连接服务端：{exc.reason}") from exc


def _server_upload_file(server_url: str, path: str, ticket: str, source: Path,
                        *, source_path: str = "", timeout: float = 600.0) -> bytes:
    """Stream a potentially multi-gigabyte archive without loading it into RAM."""
    parsed = urllib.parse.urlsplit(server_url)
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout)
    target = f"{parsed.path.rstrip('/')}{path}" or "/"
    try:
        connection.putrequest("POST", target)
        connection.putheader("X-MuJoCo-Client-Ticket", ticket)
        connection.putheader("Content-Type", "application/zip")
        connection.putheader("Content-Length", str(source.stat().st_size))
        connection.putheader("User-Agent", f"MuJoCo-Studio-Client/{CLIENT_VERSION}")
        if source_path:
            connection.putheader("X-MuJoCo-Source-Path", urllib.parse.quote(source_path[:2048], safe=""))
        connection.endheaders()
        with source.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                connection.send(chunk)
        response = connection.getresponse()
        payload = response.read()
        if response.status >= 400:
            detail = payload.decode("utf-8", "replace")
            try:
                detail = str(json.loads(detail).get("detail", detail))
            except ValueError:
                pass
            raise ClientError(f"服务端拒绝客户端任务：{detail}")
        return payload
    except OSError as exc:
        raise ClientError(f"无法连接服务端：{exc}") from exc
    finally:
        connection.close()


def create_mesh_archive(mesh_path: Path, destination: Path) -> int:
    mesh_path = Path(mesh_path).resolve()
    if not mesh_path.is_dir():
        raise ClientError("请先选择有效的本地数模路径")
    files = [
        path for path in mesh_path.rglob("*")
        if path.is_file() and path.suffix.lower() in ASSET_EXTENSIONS
    ]
    if not any(path.suffix.lower() in {".stl", ".obj"} for path in files):
        raise ClientError("本地数模路径中没有 STL 或 OBJ 文件")
    total = sum(path.stat().st_size for path in files)
    if total > MAX_ARCHIVE_BYTES:
        raise ClientError("本次数模同步超过 8 GiB 上限")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(mesh_path).as_posix())
    return len(files)


def safe_extract_bundle(payload: bytes, destination: Path) -> dict[str, Any]:
    archive_path = destination / "bundle.zip"
    archive_path.write_bytes(payload)
    archive_infos: tuple[zipfile.ZipInfo, ...] = ()
    with zipfile.ZipFile(archive_path) as archive:
        archive_infos = tuple(archive.infolist())
        names = {info.filename for info in archive_infos}
        required = {"generated_scene.xml", "generated_drives.json", "server_controller.py", "manifest.json"}
        # Schema 4 adds the server-precomputed trajectory consumed by the pure playback Viewer.
        if "manifest.json" in names:
            pass
        if not required <= names:
            raise ClientError("服务端仿真包缺少必要文件", code="bundle_integrity_failed")
        for info in archive_infos:
            target = (destination / info.filename).resolve()
            if destination.resolve() not in target.parents:
                raise ClientError("服务端仿真包包含越界路径", code="bundle_integrity_failed")
        archive.extractall(destination)
    manifest = json.loads((destination / "manifest.json").read_text("utf-8"))
    schema = int(manifest.get("schema_version", 1))
    if schema not in {1, 2, 3, 4}:
        raise ClientError("服务端 bundle 格式不受当前客户端支持", code="bundle_schema_unsupported",
                          details={"schema_version": schema, "supported": [1, 2, 3, 4]})
    if schema >= 4 and not (destination / "trajectory.npz").is_file():
        raise ClientError("Schema 4 Viewer bundle 缺少 trajectory.npz", code="bundle_integrity_failed")
    minimum = str(manifest.get("min_client_version", "0.1.0"))
    if _version_tuple(CLIENT_VERSION) < _version_tuple(minimum):
        raise ClientError(f"当前客户端版本过低，需要至少 V{minimum}", code="client_upgrade_required",
                          details={"client_version": CLIENT_VERSION, "min_client_version": minimum})
    actual = hashlib.sha256((destination / "server_controller.py").read_bytes()).hexdigest()
    if actual != str(manifest.get("controller_sha256", "")):
        raise ClientError("服务端控制脚本完整性校验失败", code="bundle_integrity_failed")
    mapping_curve = manifest.get("mapping_curve", {})
    if isinstance(mapping_curve, dict) and mapping_curve:
        relative = str(mapping_curve.get("file", "mapping_curve.py")).replace("\\", "/").strip("/")
        pure = PurePosixPath(relative)
        if not relative or pure.is_absolute() or ".." in pure.parts:
            raise ClientError("服务端映射模块路径不安全", code="bundle_integrity_failed")
        helper = (destination / Path(*pure.parts)).resolve()
        if destination.resolve() not in helper.parents or not helper.is_file():
            raise ClientError("服务端仿真包缺少映射模块", code="bundle_integrity_failed")
        expected = str(mapping_curve.get("sha256", "")).strip().lower()
        if expected and hashlib.sha256(helper.read_bytes()).hexdigest() != expected:
            raise ClientError("服务端映射模块完整性校验失败", code="bundle_integrity_failed")
    gantt_manifest = manifest.get("gantt_cache", {})
    if isinstance(gantt_manifest, dict) and bool(gantt_manifest.get("included", False)):
        for key, digest_key in (("png", "png_sha256"), ("json", "json_sha256")):
            relative = str(gantt_manifest.get(key, "")).replace("\\", "/").strip("/")
            pure = PurePosixPath(relative)
            if not relative or pure.is_absolute() or ".." in pure.parts:
                raise ClientError("服务端甘特图缓存路径不安全", code="bundle_integrity_failed")
            target = (destination / Path(*pure.parts)).resolve()
            if destination.resolve() not in target.parents or not target.is_file():
                raise ClientError("服务端仿真包缺少甘特图缓存文件", code="bundle_integrity_failed")
            expected = str(gantt_manifest.get(digest_key, ""))
            if expected and hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ClientError("服务端甘特图缓存完整性校验失败", code="bundle_integrity_failed")
    if schema >= 3:
        root_name = str(manifest.get("server_assets_root", "server_assets") or "server_assets").replace("\\", "/").strip("/")
        root_parts = PurePosixPath(root_name)
        if not root_name or root_parts.is_absolute() or ".." in root_parts.parts:
            raise ClientError("服务端仿真包的数模根目录声明不安全", code="bundle_integrity_failed")
        asset_root = (destination / Path(*root_parts.parts)).resolve()
        if destination.resolve() not in asset_root.parents:
            raise ClientError("服务端仿真包的数模根目录越界", code="bundle_integrity_failed")
        declared_count = int(manifest.get("server_asset_count", manifest.get("bundled_asset_count", 0)) or 0)
        if not asset_root.exists() and declared_count == 0:
            asset_root.mkdir(parents=True, exist_ok=True)
        asset_prefix = root_name.rstrip("/") + "/"
        actual_count = sum(
            1
            for info in archive_infos
            if not info.is_dir()
            and info.filename.replace("\\", "/").startswith(asset_prefix)
            and PurePosixPath(info.filename).suffix.casefold() in ASSET_EXTENSIONS
        )
        if not asset_root.is_dir() or actual_count != declared_count:
            raise ClientError(
                "服务端仿真包的数模资产快照数量与清单不一致", code="bundle_integrity_failed",
                details={"declared": declared_count, "actual": actual_count},
            )
        manifest["server_assets_root"] = root_name
        manifest["server_asset_count"] = declared_count
    return manifest


def bind_local_meshes(scene_path: Path, mesh_path: Path) -> list[str]:
    """Compatibility wrapper returning matched paths without mutating XML."""
    destination = Path(scene_path).with_name("local_assets.json")
    try:
        payload = build_local_asset_map(scene_path, mesh_path, destination)
    except AssetBindingError as exc:
        raise ClientError(str(exc), code=exc.code, details=exc.details) from exc
    return list(dict.fromkeys(payload["assets"].values()))


class ClientApplication:
    def __init__(self, config: ClientConfig | None = None) -> None:
        self.config = config or ClientConfig()
        self._lock = threading.RLock()
        self.viewers = ViewerRegistry(RUNTIME_ROOT / "logs")

    def validate_server(self, server_url: str) -> str:
        requested = _origin(server_url)
        if requested != self.config.allowed_origin():
            raise ClientError("请求来源与配置的 Server IP / Hub 端口不一致，请同步 Server/ports.json")
        return str(server_url).rstrip("/")

    def authorize(self, server_url: str, ticket: str, purpose: str) -> dict[str, Any]:
        server_url = self.validate_server(server_url)
        raw = _server_request(
            server_url, "/api/client/authorize", ticket,
            body=json.dumps({"purpose": purpose}).encode("utf-8"), timeout=30,
        )
        return json.loads(raw.decode("utf-8"))

    def sync(self, server_url: str, ticket: str) -> dict[str, Any]:
        server_url = self.validate_server(server_url)
        mesh_path = Path(self.config.read()["mesh_path"]).expanduser()
        RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="mesh_sync_", suffix=".zip", dir=RUNTIME_ROOT, delete=False) as stream:
            archive_path = Path(stream.name)
        try:
            file_count = create_mesh_archive(mesh_path, archive_path)
            result = _server_upload_file(
                server_url,
                "/api/client/mesh-sync",
                ticket,
                archive_path,
                source_path=str(mesh_path.resolve()),
                timeout=600,
            )
            payload = json.loads(result.decode("utf-8"))
            return {**payload, "local_file_count": file_count}
        finally:
            archive_path.unlink(missing_ok=True)

    def launch(self, server_url: str, ticket: str) -> dict[str, Any]:
        server_url = self.validate_server(server_url)
        mesh_path = Path(self.config.read()["mesh_path"]).expanduser()
        try:
            payload = _server_request(server_url, "/api/client/viewer-bundle", ticket, body=b"{}", timeout=180)
        except ClientError as exc:
            if exc.code in {"client_upgrade_required", "server_rejected"}:
                raise
            raise ClientError(str(exc), code="bundle_download_failed", details=exc.details) from exc
        RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
        bundle_dir = Path(tempfile.mkdtemp(prefix="viewer_", dir=RUNTIME_ROOT))
        launched = False
        try:
            manifest = safe_extract_bundle(payload, bundle_dir)
            schema_version = int(manifest.get("schema_version", 1))
            if schema_version == 1:
                matched = rewrite_legacy_mesh_paths(bundle_dir / "generated_scene.xml", mesh_path)
                warnings = [{"code": "legacy_bundle", "message": "旧服务端不支持 VFS 资产映射，中文资产路径可能不可用"}]
            else:
                asset_root = (bundle_dir / str(manifest.get("server_assets_root", "server_assets"))) if schema_version >= 3 else mesh_path
                try:
                    matched = bind_local_meshes(bundle_dir / "generated_scene.xml", asset_root)
                except ClientError as exc:
                    if schema_version >= 3 and exc.code in {"mesh_path_missing", "local_asset_missing"}:
                        raise ClientError("服务端仿真包的数模资产快照不完整", code="bundle_integrity_failed", details=exc.details) from exc
                    raise
                warnings = json.loads((bundle_dir / "local_assets.json").read_text("utf-8")).get("warnings", [])
                if schema_version >= 3:
                    warnings.append({"code":"server_asset_snapshot","message":"Viewer 使用服务端上传后冻结的数模资产快照；客户端本地数模目录仅用于上传兼容。"})
            env = dict(os.environ)
            env["MUJOCO_STUDIO_URL"] = server_url
            # Native BLAS/OpenMP threads belong to this viewer child only;
            # multiple users' CAD/MuJoCo jobs must not exhaust host cores.
            for thread_key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
                env[thread_key] = "1"
            record = self.viewers.launch(
                [sys.executable, "-u", str(ROOT / "runner.py"), str(bundle_dir)],
                project_id=str(manifest.get("project_id", "")), bundle_dir=bundle_dir,
                cwd=RUNTIME_ROOT, env=env,
            )
            launched = True
            return {"ok": True, "pid": record.pid, "launch_id": record.launch_id,
                    "project_id": manifest.get("project_id"), "matched_assets": len(matched),
                    "warnings": warnings}
        except RuntimeError as exc:
            code = str(exc) if str(exc) == "viewer_limit_reached" else "popen_failed"
            raise ClientError("本机 Viewer 运行数量已达上限" if code == "viewer_limit_reached" else f"Viewer 子进程启动失败：{exc}", code=code) from exc
        finally:
            if not launched:
                shutil.rmtree(bundle_dir, ignore_errors=True)

    def health(self) -> dict[str, Any]:
        config = self.config.read()
        viewers = self.viewers.list()
        missing_dependencies = [name for name in ("mujoco", "numpy") if importlib.util.find_spec(name) is None]
        mesh_root = Path(config["mesh_path"]).expanduser() if config["mesh_path"] else None
        mesh_files: list[str] = []
        mesh_scan_error = ""
        if mesh_root is not None and mesh_root.is_dir():
            try:
                mesh_files = sorted(
                    path.relative_to(mesh_root).as_posix()
                    for path in mesh_root.rglob("*")
                    if path.is_file() and path.suffix.lower() in {".stl", ".obj"}
                )[:10000]
            except OSError as exc:
                mesh_scan_error = str(exc)
        return {
            "status": "config_invalid" if self.config.last_error else "ok",
            "config_error": self.config.last_error,
            "client_version": CLIENT_VERSION,
            "server_origin": self.config.allowed_origin(),
            "mesh_path": config["mesh_path"],
            "mesh_path_ready": bool(mesh_root is not None and mesh_root.is_dir()),
            "mesh_files": mesh_files,
            "mesh_scan_error": mesh_scan_error,
            "viewer_processes": viewers,
            "viewer_limit": self.viewers.running_limit,
            "supported_bundle_schemas": [1, 2, 3, 4],
            "dependencies_ready": not missing_dependencies,
            "missing_dependencies": missing_dependencies,
        }


APP = ClientApplication()


class Handler(BaseHTTPRequestHandler):
    server_version = f"MuJoCoStudioClient/{CLIENT_VERSION}"

    def _allowed(self) -> bool:
        expected_hosts = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
        if str(self.headers.get("Host", "")).casefold() not in expected_hosts:
            return False
        origin = self.headers.get("Origin", "")
        if origin:
            return origin == APP.config.allowed_origin()
        return self.command == "GET" and urllib.parse.urlsplit(self.path).path == "/v1/health"

    def _headers(self, status: int, length: int) -> None:
        self.send_response(status)
        origin = self.headers.get("Origin", "")
        if origin and origin == APP.config.allowed_origin():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(length))
        self.end_headers()

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers(status, len(body))
        self.wfile.write(body)

    def _payload(self) -> dict[str, Any]:
        length = min(int(self.headers.get("Content-Length", "0") or 0), 1024 * 1024)
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def do_OPTIONS(self) -> None:
        if not self._allowed():
            self._json(403, {"detail": "来源未授权"})
            return
        self._headers(204, 0)

    def do_GET(self) -> None:
        if not self._allowed():
            self._json(403, {"detail": "来源未授权"})
        elif urllib.parse.urlsplit(self.path).path == "/v1/health":
            self._json(200, APP.health())
        elif urllib.parse.urlsplit(self.path).path.startswith("/v1/viewer/"):
            try:
                pid = int(urllib.parse.urlsplit(self.path).path.rsplit("/", 1)[-1])
            except ValueError:
                self._json(404, {"code": "route_not_found", "message": "接口不存在"})
                return
            self._json(200, APP.viewers.status(pid))
        else:
            self._json(404, {"code": "route_not_found", "message": "接口不存在"})

    def do_POST(self) -> None:
        if not self._allowed():
            self._json(403, {"detail": "来源未授权"})
            return
        try:
            payload = self._payload()
            if self.path == "/v1/select-mesh-path":
                APP.authorize(str(payload.get("server_url", "")), str(payload.get("ticket", "")), "select_mesh_path")
                self._json(200, {"path": APP.config.select_mesh_path()})
            elif self.path == "/v1/sync":
                self._json(200, APP.sync(str(payload.get("server_url", "")), str(payload.get("ticket", ""))))
            elif self.path == "/v1/launch":
                self._json(200, APP.launch(str(payload.get("server_url", "")), str(payload.get("ticket", ""))))
            elif urllib.parse.urlsplit(self.path).path.startswith("/v1/viewer/") and urllib.parse.urlsplit(self.path).path.endswith("/terminate"):
                parts = urllib.parse.urlsplit(self.path).path.strip("/").split("/")
                try:
                    pid = int(parts[-2])
                except (ValueError, IndexError):
                    self._json(404, {"code":"route_not_found","message":"接口不存在"}); return
                self._json(200, {"pid":pid, "terminated":APP.viewers.terminate(pid)})
            else:
                self._json(404, {"code": "route_not_found", "message": "接口不存在"})
        except (ClientError, ValueError, OSError, zipfile.BadZipFile) as exc:
            self._json(422, {
                "code": getattr(exc, "code", "client_error"), "message": str(exc),
                "details": getattr(exc, "details", {}),
            })

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[client] {self.address_string()} {fmt % args}")


def main() -> int:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    _reclaim_client_runtime(RUNTIME_ROOT, APP.viewers.protected_bundles(), CLIENT_ORPHAN_TTL_HOURS)
    config = APP.config.read()
    print(f"MuJoCo Studio 轻量客户端 V{CLIENT_VERSION}")
    print(f"监听地址：http://{HOST}:{PORT}")
    print(f"允许服务端：{APP.config.allowed_origin()}")
    print(f"本地数模路径：{config['mesh_path'] or '尚未选择'}")
    print("保持本窗口运行，然后在网页中点击“本地同步”或“MuJoCo View”。")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n客户端已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
