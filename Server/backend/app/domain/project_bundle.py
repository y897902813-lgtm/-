from __future__ import annotations

import copy
import hashlib
import json
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


BUNDLE_FORMAT = "mujoco_studio_project_bundle"
BUNDLE_FORMAT_VERSION = 2
SUPPORTED_BUNDLE_FORMAT_VERSIONS = frozenset({1, 2})
MANIFEST_NAME = "manifest.json"
MODEL_JSON_PATH = "model/model.json"
ASSETS_DIR = "properties/model_assets"
DELIVERY_DIR = "properties/delivery"
ARCHIVE_DIR = "properties/archive_logs"
TIME_SERIES_DIR = "properties/time_series_library"
ENVIRONMENT_LOCAL_METADATA_KEYS = frozenset({"vz_push"})


class ProjectBundleError(ValueError):
    """Raised when a project bundle violates the portable package contract."""



def strip_environment_local_metadata(state: dict[str, Any]) -> dict[str, Any]:
    """Return a portable state copy without machine/integration-local bindings.

    `vz_push` identifies a projection in the current Hub/VZ deployment. Carrying
    that binding into an exported, cloned, or imported project can point a new
    project identity at another project's VZ model. It is therefore explicitly
    outside the portable model contract.
    """
    result = copy.deepcopy(state)
    project = result.get("project") if isinstance(result, dict) else None
    metadata = project.get("metadata") if isinstance(project, dict) else None
    if isinstance(metadata, dict):
        for key in ENVIRONMENT_LOCAL_METADATA_KEYS:
            metadata.pop(key, None)
    return result


def clear_environment_local_project_metadata(project: Any) -> None:
    """Remove environment-local metadata from a ProjectSpec-like object in place."""
    metadata = getattr(project, "metadata", None)
    if isinstance(metadata, dict):
        for key in ENVIRONMENT_LOCAL_METADATA_KEYS:
            metadata.pop(key, None)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_inventory(root: Path, *, exclude: Iterable[str] = ()) -> list[dict[str, Any]]:
    root = Path(root).resolve()
    excluded = {str(item).replace("\\", "/").strip("/") for item in exclude}
    result: list[dict[str, Any]] = []
    if not root.is_dir():
        return result
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise ProjectBundleError(f"目录包含符号链接，禁止打包：{path.name}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        result.append({"path": relative, "size": path.stat().st_size, "sha256": sha256_file(path)})
    return result


def copy_tree_snapshot(
    source: Path,
    target: Path,
    *,
    max_files: int,
    max_bytes: int,
    exclude_names: Iterable[str] = (),
) -> dict[str, int]:
    """Copy a directory to an isolated snapshot and verify the copied bytes.

    The source is never modified. A post-copy source/destination inventory comparison
    catches assets that changed while they were being copied instead of exporting a
    mixed-time snapshot silently.
    """
    source = Path(source).resolve()
    target = Path(target).resolve()
    excluded = {str(item) for item in exclude_names}
    if target.exists():
        raise ProjectBundleError("快照目标目录已存在")
    target.mkdir(parents=True, exist_ok=False)
    if not source.is_dir():
        return {"files": 0, "bytes": 0}

    file_count = 0
    total_bytes = 0
    try:
        for path in sorted(source.rglob("*"), key=lambda item: item.as_posix().casefold()):
            if path.is_symlink():
                raise ProjectBundleError(f"目录包含符号链接，禁止打包：{path.name}")
            relative = path.relative_to(source)
            if path.name in excluded:
                continue
            destination = target / relative
            if path.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if not path.is_file():
                continue
            file_count += 1
            size = path.stat().st_size
            total_bytes += size
            if file_count > max_files:
                raise ProjectBundleError(f"完整包文件数量不能超过 {max_files}")
            if total_bytes > max_bytes:
                raise ProjectBundleError("完整包展开数据超过大小上限")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)

        source_inventory = [
            item for item in tree_inventory(source)
            if Path(item["path"]).name not in excluded
        ]
        target_inventory = tree_inventory(target)
        source_index = {item["path"]: (item["size"], item["sha256"]) for item in source_inventory}
        target_index = {item["path"]: (item["size"], item["sha256"]) for item in target_inventory}
        if source_index != target_index:
            raise ProjectBundleError("源目录在打包快照期间发生变化，请重试导出")
        return {"files": file_count, "bytes": total_bytes}
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise


def write_bundle_zip(staging_root: Path, destination: Path) -> None:
    staging_root = Path(staging_root).resolve()
    destination = Path(destination).resolve()
    if not (staging_root / MANIFEST_NAME).is_file():
        raise ProjectBundleError("完整包缺少 manifest.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for path in sorted(staging_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
                if path.is_symlink():
                    raise ProjectBundleError(f"完整包暂存目录包含符号链接：{path.name}")
                relative = path.relative_to(staging_root).as_posix()
                if path.is_dir():
                    if not any(path.iterdir()):
                        archive.writestr(relative.rstrip("/") + "/", b"")
                    continue
                if path.is_file():
                    archive.write(path, relative)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _safe_member_name(name: str) -> str:
    normalized = str(name or "").replace("\\", "/")
    pure = PurePosixPath(normalized)
    if not normalized or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ProjectBundleError(f"压缩包包含非法路径：{name!r}")
    if pure.parts and ":" in pure.parts[0]:
        raise ProjectBundleError(f"压缩包包含盘符路径：{name!r}")
    return pure.as_posix()


def extract_bundle_zip(
    archive_path: Path,
    target_root: Path,
    *,
    max_files: int,
    max_file_bytes: int,
    max_total_bytes: int,
) -> dict[str, int]:
    archive_path = Path(archive_path).resolve()
    target_root = Path(target_root).resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    file_count = 0
    expanded = 0
    actual_expanded = 0
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                safe_name = _safe_member_name(info.filename)
                if safe_name.rstrip("/") in seen:
                    raise ProjectBundleError(f"压缩包包含重复路径：{safe_name}")
                seen.add(safe_name.rstrip("/"))
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise ProjectBundleError(f"压缩包包含符号链接：{safe_name}")
                destination = (target_root / Path(*PurePosixPath(safe_name).parts)).resolve()
                if destination != target_root and target_root not in destination.parents:
                    raise ProjectBundleError(f"压缩包路径越界：{safe_name}")
                if info.is_dir() or safe_name.endswith("/"):
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                file_count += 1
                if file_count > max_files:
                    raise ProjectBundleError(f"完整包文件数量不能超过 {max_files}")
                if int(info.file_size) > max_file_bytes:
                    raise ProjectBundleError(f"完整包单文件超过大小上限：{safe_name}")
                expanded += int(info.file_size)
                if expanded > max_total_bytes:
                    raise ProjectBundleError("完整包展开数据超过大小上限")
                destination.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with archive.open(info) as source, destination.open("wb") as stream:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        written += len(chunk)
                        actual_expanded += len(chunk)
                        if written > max_file_bytes:
                            raise ProjectBundleError(f"完整包单文件超过大小上限：{safe_name}")
                        if actual_expanded > max_total_bytes:
                            raise ProjectBundleError("完整包实际展开数据超过大小上限")
                        stream.write(chunk)
                if written != int(info.file_size):
                    raise ProjectBundleError(f"完整包文件展开大小校验失败：{safe_name}")
    except Exception:
        shutil.rmtree(target_root, ignore_errors=True)
        raise
    return {"files": file_count, "bytes": actual_expanded}


def load_manifest(root: Path) -> dict[str, Any]:
    path = Path(root) / MANIFEST_NAME
    if not path.is_file():
        raise ProjectBundleError("完整包缺少 manifest.json")
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectBundleError("完整包 manifest.json 无法读取") from exc
    if not isinstance(value, dict):
        raise ProjectBundleError("完整包 manifest.json 必须是对象")
    try:
        format_version = int(value.get("format_version", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ProjectBundleError("完整包 format_version 无效") from exc
    if value.get("format") != BUNDLE_FORMAT or format_version not in SUPPORTED_BUNDLE_FORMAT_VERSIONS:
        raise ProjectBundleError("不是受支持的 MuJoCo Studio 完整包")
    if not (Path(root) / MODEL_JSON_PATH).is_file():
        raise ProjectBundleError("完整包缺少 model/model.json")
    return value


def verify_manifest_inventory(root: Path, manifest: dict[str, Any]) -> None:
    root = Path(root).resolve()
    expected_items = manifest.get("inventory", [])
    if not isinstance(expected_items, list):
        raise ProjectBundleError("完整包 inventory 格式无效")
    expected: dict[str, tuple[int, str]] = {}
    for item in expected_items:
        if not isinstance(item, dict):
            raise ProjectBundleError("完整包 inventory 条目无效")
        path = _safe_member_name(str(item.get("path", "")))
        if path == MANIFEST_NAME:
            raise ProjectBundleError("manifest 不应自校验")
        if path in expected:
            raise ProjectBundleError(f"完整包 inventory 路径重复：{path}")
        try:
            size = int(item.get("size", -1))
        except (TypeError, ValueError) as exc:
            raise ProjectBundleError(f"完整包 inventory 大小无效：{path}") from exc
        digest = str(item.get("sha256", "")).lower()
        if size < 0 or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ProjectBundleError(f"完整包 inventory 校验字段无效：{path}")
        expected[path] = (size, digest)

    actual_items = tree_inventory(root, exclude={MANIFEST_NAME})
    actual = {item["path"]: (item["size"], item["sha256"]) for item in actual_items}
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        unexpected = sorted(set(actual) - set(expected))
        mismatched = sorted(path for path in set(actual) & set(expected) if actual[path] != expected[path])
        details = []
        if missing:
            details.append(f"缺失 {len(missing)} 项")
        if unexpected:
            details.append(f"多出 {len(unexpected)} 项")
        if mismatched:
            details.append(f"校验不一致 {len(mismatched)} 项")
        raise ProjectBundleError("完整包内容校验失败：" + "，".join(details or ["未知差异"]))
