"""Generic process runner for a verified server-supplied controller."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import threading
from pathlib import Path


VIEWER_BUNDLE_HEARTBEAT_SECONDS = 60.0


def _heartbeat_bundle(bundle: Path, stop: threading.Event) -> None:
    """Keep bundle directory mtime fresh while the detached Viewer is alive."""
    while not stop.is_set():
        try:
            os.utime(bundle, None)
        except OSError:
            pass
        stop.wait(VIEWER_BUNDLE_HEARTBEAT_SECONDS)


def main() -> int:
    bundle = Path(sys.argv[1]).resolve()
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat_bundle, args=(bundle, heartbeat_stop), daemon=True, name="viewer-bundle-heartbeat"
    )
    heartbeat.start()
    try:
        manifest = json.loads((bundle / "manifest.json").read_text("utf-8"))
        controller_path = bundle / "server_controller.py"
        digest = hashlib.sha256(controller_path.read_bytes()).hexdigest()
        if digest != manifest.get("controller_sha256"):
            raise RuntimeError("服务端控制器完整性校验失败")
        spec = importlib.util.spec_from_file_location("mujoco_studio_server_controller", controller_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载服务端控制器")
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        arguments = [str(bundle / "generated_scene.xml"), str(bundle / "generated_drives.json")]
        signature = int(manifest.get("controller_signature_version", 1))
        if signature >= 4:
            controller.run_viewer(
                *arguments,
                trajectory_path=str(bundle / "trajectory.npz"),
                asset_map_path=str(bundle / "local_assets.json"),
                gantt_cache_path=str(bundle / "gantt_cache"),
            )
        elif signature >= 3:
            controller.run_viewer(*arguments, trajectory_path=str(bundle / "trajectory.npz"), asset_map_path=str(bundle / "local_assets.json"))
        elif signature >= 2:
            controller.run_viewer(*arguments, asset_map_path=str(bundle / "local_assets.json"))
        else:
            controller.run_viewer(*arguments)
    finally:
        heartbeat_stop.set()
        shutil.rmtree(bundle, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
