"""Build a bounded server-authoritative local MuJoCo launch bundle."""
from __future__ import annotations

import hashlib
import json
import shlex
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

from .models import ProjectSpec
from .xml_generator import generate_project
from .simulation_process import run_project_simulation_isolated


BUNDLE_ASSET_EXTENSIONS = {".stl", ".obj", ".mtl", ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".webp"}
MAX_BUNDLE_ASSET_FILES = 10_000
MAX_BUNDLE_ASSET_BYTES = 8 * 1024 * 1024 * 1024


def _optional_gantt_snapshot(gantt_cache_dir: Path | None) -> tuple[dict[str, bytes], dict[str, object]]:
    """Return an optional verified Gantt cache without blocking Viewer launch."""
    snapshot: dict[str, bytes] = {}
    manifest: dict[str, object] = {"included": False, "reason": "not_generated"}
    if gantt_cache_dir is None:
        return snapshot, manifest
    cache_root = Path(gantt_cache_dir).resolve()
    cache_png = cache_root / "latest_gantt.png"
    cache_json = cache_root / "latest_gantt.json"
    if not (cache_png.is_file() and cache_json.is_file()):
        if cache_png.exists() or cache_json.exists():
            manifest = {
                "included": False,
                "reason": "cache_incomplete",
                "warning": "Viewer 甘特图缓存不完整，已忽略并继续启动 Viewer",
            }
        return snapshot, manifest
    try:
        png_bytes = cache_png.read_bytes()
        json_bytes = cache_json.read_bytes()
        cache_meta = json.loads(json_bytes.decode("utf-8"))
        if not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("PNG 文件头无效")
        if str(cache_meta.get("format", "")) not in {"MUJOCO_XML_TOOL_GANTT_CACHE", "MUJOCO_STUDIO_GANTT_CACHE"}:
            raise ValueError("缓存格式不受支持")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return snapshot, {
            "included": False,
            "reason": "cache_invalid",
            "warning": f"Viewer 甘特图缓存不可用：{exc}",
        }
    snapshot = {
        "gantt_cache/latest_gantt.png": png_bytes,
        "gantt_cache/latest_gantt.json": json_bytes,
    }
    manifest = {
        "included": True,
        "png": "gantt_cache/latest_gantt.png",
        "json": "gantt_cache/latest_gantt.json",
        "png_sha256": hashlib.sha256(png_bytes).hexdigest(),
        "json_sha256": hashlib.sha256(json_bytes).hexdigest(),
        "saved_at": cache_meta.get("saved_at"),
        "source": "project_popup_cache",
    }
    return snapshot, manifest


def _safe_relative(value: str) -> PurePosixPath:
    text = str(value or "").replace("\\", "/").strip()
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or "\x00" in text:
        raise ValueError(f"不安全的数模资产相对路径：{value}")
    cleaned = path.as_posix().lstrip("./")
    if not cleaned:
        raise ValueError(f"不安全的数模资产相对路径：{value}")
    return PurePosixPath(cleaned)


def _has_symlink_component(root: Path, path: Path) -> bool:
    """Reject a file reached through a symlink anywhere below the asset root."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _resolve_project_asset(root: Path, requested: str, *, preferred: Path | None = None) -> Path | None:
    relative = _safe_relative(requested)
    candidates: list[Path] = []
    if preferred is not None:
        candidates.append(preferred / Path(*relative.parts))
    candidates.append(root / Path(*relative.parts))

    for raw in candidates:
        try:
            candidate = raw.resolve(strict=True)
        except (FileNotFoundError, OSError):
            continue
        if not candidate.is_file() or (candidate != root and root not in candidate.parents):
            continue
        if _has_symlink_component(root, raw.absolute()):
            continue
        return candidate

    # Compatibility with historical projects that only retained a basename or
    # whose path casing changed.  Accept the fallback only when it is unique.
    matches: list[Path] = []
    wanted_name = relative.name.casefold()
    try:
        for item in root.rglob("*"):
            if not item.is_file() or item.name.casefold() != wanted_name:
                continue
            if _has_symlink_component(root, item.absolute()):
                continue
            try:
                resolved = item.resolve(strict=True)
            except (FileNotFoundError, OSError):
                continue
            if resolved == root or root in resolved.parents:
                matches.append(resolved)
    except OSError:
        return None
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None


def _obj_material_names(path: Path) -> list[str]:
    values: list[str] = []
    for raw in path.read_text("utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) == 2 and parts[0].casefold() == "mtllib":
            values.extend(shlex.split(parts[1], posix=True))
    return values


def _mtl_texture_names(path: Path) -> list[str]:
    values: list[str] = []
    for raw in path.read_text("utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = shlex.split(stripped, posix=True)
        if len(parts) >= 2 and (parts[0].casefold().startswith("map_") or parts[0].casefold() == "bump"):
            values.append(parts[-1])
    return values


def _server_asset_snapshot(project: ProjectSpec, required_assets: list[dict[str, str]]) -> list[tuple[Path, str]]:
    """Freeze only assets reachable from the generated XML, including OBJ dependencies."""
    raw_root = str(project.mesh_root or "").strip()
    if not raw_root:
        if required_assets:
            raise ValueError("项目没有服务端数模目录，无法构建 Viewer 数模快照")
        return []
    root_input = Path(raw_root).expanduser()
    if root_input.is_symlink():
        raise ValueError(f"服务端数模目录不允许使用符号链接：{root_input}")
    try:
        root = root_input.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise ValueError(f"服务端数模目录不存在：{raw_root}") from exc
    if not root.is_dir():
        raise ValueError(f"服务端数模目录不可用：{root}")

    selected: dict[Path, str] = {}
    queue: list[tuple[str, Path | None, bool]] = [
        (str(item.get("file", "")), None, True) for item in required_assets if str(item.get("file", "")).strip()
    ]
    missing_required: list[str] = []
    total_bytes = 0

    while queue:
        requested, preferred, required = queue.pop(0)
        source = _resolve_project_asset(root, requested, preferred=preferred)
        if source is None:
            if required:
                missing_required.append(requested)
            continue
        if source.suffix.casefold() not in BUNDLE_ASSET_EXTENSIONS:
            if required:
                missing_required.append(requested)
            continue
        if source in selected:
            continue

        try:
            size = source.stat().st_size
            relative = source.relative_to(root).as_posix()
        except (OSError, ValueError) as exc:
            raise ValueError(f"无法读取服务端数模资产：{source}") from exc
        selected[source] = relative
        total_bytes += size
        if len(selected) > MAX_BUNDLE_ASSET_FILES:
            raise ValueError(f"服务端 Viewer 数模依赖超过文件数上限 {MAX_BUNDLE_ASSET_FILES}")
        if total_bytes > MAX_BUNDLE_ASSET_BYTES:
            raise ValueError("服务端 Viewer 数模依赖总大小超过 8 GiB 上限")

        try:
            if source.suffix.casefold() == ".obj":
                queue.extend((name, source.parent, False) for name in _obj_material_names(source))
            elif source.suffix.casefold() == ".mtl":
                queue.extend((name, source.parent, False) for name in _mtl_texture_names(source))
        except OSError as exc:
            raise ValueError(f"无法读取数模依赖文件：{source}") from exc

    if missing_required:
        unique = sorted(set(missing_required), key=str.casefold)
        raise ValueError("服务端数模快照缺少生成 XML 直接引用资产：" + "、".join(unique[:20]))
    return sorted(selected.items(), key=lambda item: item[1].casefold())


def build_client_bundle(
    project: ProjectSpec, workspace: Path, controller_path: Path, *, server_version: str,
    trajectory_source: Path | None = None, gantt_cache_dir: Path | None = None,
) -> Path:
    workspace = Path(workspace)
    controller_path = Path(controller_path)
    closure_solver_path = controller_path.with_name("kinematic_closure.py")
    if not closure_solver_path.is_file():
        raise ValueError("Viewer bundle 缺少权威运动学闭链求解模块 kinematic_closure.py")
    closure_solver_bytes = closure_solver_path.read_bytes()
    mapping_curve_path = controller_path.with_name("mapping_curve.py")
    if not mapping_curve_path.is_file():
        raise ValueError("Viewer bundle 缺少权威最小 jerk 映射模块 mapping_curve.py")
    mapping_curve_bytes = mapping_curve_path.read_bytes()
    generated = workspace / "generated"
    artifacts = generate_project(project, generated, check_files=True)
    trajectory_path: Path | None = None
    simulation_meta: dict[str, object] = {}
    if trajectory_source is not None and Path(trajectory_source).is_file():
        trajectory_path = Path(trajectory_source)
        simulation_meta = {"source": "latest_simulation"}
    else:
        # Viewer is a pure trajectory player. If the user has not run a current
        # background simulation yet, precompute one on the server before bundling.
        runtime = ProjectSpec.model_validate(project.model_dump())
        runtime.simulation.engine = "mujoco"
        result = run_project_simulation_isolated(
            runtime, workspace / "viewer_simulation", max_wall_seconds=120,
        )
        candidate = Path(str(result.get("artifacts", {}).get("trajectory", "")))
        if candidate.is_file():
            trajectory_path = candidate
        simulation_meta = {"source": "bundle_precompute", "solver_mode": runtime.solver_mode}
    if trajectory_path is None:
        raise ValueError("Viewer 需要完整 trajectory.npz；请先运行 MuJoCo 后台仿真")
    tree = ET.parse(artifacts["scene"])
    compiler = tree.find("compiler")
    meshdir = str(compiler.get("meshdir", "")) if compiler is not None else ""
    required_assets: list[dict[str, str]] = []
    for kind, xpath in (("mesh", ".//asset/mesh"), ("texture", ".//asset/texture")):
        for node in tree.findall(xpath):
            filename = str(node.get("file", ""))
            if not filename:
                continue
            key = (PurePosixPath(meshdir) / filename).as_posix() if kind == "mesh" and meshdir else filename
            required_assets.append({"vfs_key": key, "file": filename, "kind": kind})
    required_assets.sort(key=lambda item: (item["kind"], item["vfs_key"]))
    # V2.5.0 generator intentionally assigns ASCII runtime aliases to CAD assets
    # so Chinese STL/OBJ names remain a UI concern only. Bundle the generated
    # mesh snapshot rather than resolving those aliases back through mesh_root.
    generated_mesh_root = Path(artifacts["directory"]) / "meshes"
    server_assets: list[tuple[Path, str]] = []
    if generated_mesh_root.is_dir():
        for source in sorted((item for item in generated_mesh_root.rglob("*") if item.is_file()), key=lambda item: item.as_posix().casefold()):
            relative = (PurePosixPath(meshdir) / source.relative_to(generated_mesh_root).as_posix()).as_posix() if meshdir else source.relative_to(generated_mesh_root).as_posix()
            server_assets.append((source, relative))
    required_files = {str(item.get("vfs_key", "")) for item in required_assets}
    bundled_files = {relative for _source, relative in server_assets}
    missing = sorted(required_files - bundled_files, key=str.casefold)
    if missing:
        raise ValueError("Viewer bundle 缺少生成 XML 直接引用资产：" + "、".join(missing[:20]))
    server_asset_bytes = sum(path.stat().st_size for path, _ in server_assets)

    # V2.11.7 inherits: Gantt is optional Viewer presentation data, never a launch gate.
    # Carry a complete verified popup cache when present; otherwise record why
    # it was omitted and keep the trajectory/controller bundle fully runnable.
    gantt_snapshot, gantt_manifest = _optional_gantt_snapshot(gantt_cache_dir)

    manifest = {
        "schema_version": 4,
        "server_version": server_version,
        "min_client_version": "0.3.9",
        "asset_source": "generated_ascii_snapshot",
        "server_assets_root": "server_assets",
        "server_asset_count": len(server_assets),
        "server_asset_bytes": server_asset_bytes,
        "project_id": project.id,
        "project_name": project.name,
        "meshdir": meshdir,
        "required_assets": required_assets,
        "controller_sha256": hashlib.sha256(controller_path.read_bytes()).hexdigest(),
        "controller_entrypoint": "run_viewer",
        "controller_signature_version": 4,
        "kinematic_closure": {
            "file": "kinematic_closure.py",
            "sha256": hashlib.sha256(closure_solver_bytes).hexdigest(),
            "source": "server_authoritative_domain_module",
        },
        "mapping_curve": {
            "file": "mapping_curve.py",
            "sha256": hashlib.sha256(mapping_curve_bytes).hexdigest(),
            "source": "server_authoritative_domain_module",
            "interpolation": "minimum_jerk_quintic",
        },
        "gantt_cache": gantt_manifest,
        "solver_mode": project.solver_mode,
        "trajectory_file": "trajectory.npz",
        "trajectory_meta": simulation_meta,
    }
    bundle = Path(workspace) / "mujoco_client_bundle.zip"
    # Viewer launch latency is more important than maximum archive ratio on the LAN.
    # compresslevel=1 substantially reduces synchronous bundle-build CPU time while
    # retaining DEFLATE compatibility with existing ZIP/DEFLATE implementations.
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        archive.write(artifacts["scene"], "generated_scene.xml")
        archive.write(artifacts["drives"], "generated_drives.json")
        archive.write(trajectory_path, "trajectory.npz")
        archive.write(controller_path, "server_controller.py")
        archive.writestr("kinematic_closure.py", closure_solver_bytes)
        archive.writestr("mapping_curve.py", mapping_curve_bytes)
        for arcname, payload in gantt_snapshot.items():
            archive.writestr(arcname, payload)
        # Keep the directory even for asset-free projects so schema-3 clients
        # can bind against one deterministic server-authoritative root.
        archive.writestr("server_assets/", b"")
        for source, relative in server_assets:
            archive.write(source, f"server_assets/{relative}")
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return bundle
