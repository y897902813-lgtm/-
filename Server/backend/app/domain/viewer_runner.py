"""Standalone native MuJoCo viewer and legacy-style playback controller.

Human interaction is session-local: timeline, camera, chart and manual motor
values live only in this process.  The Studio state tree remains authoritative
for automation and can drive the running viewer through the read-only polling
channel.
"""
from __future__ import annotations

from contextlib import nullcontext

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import math
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

try:
    from .simulation import load_qpos_trajectory, sample_qpos_trajectory
except ImportError:
    # The Server sends this file verbatim as a standalone Client controller.
    # Keep trajectory loading self-contained when there is no package context.
    def load_qpos_trajectory(
        path: str | Path, *, expected_nq: int | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        with np.load(Path(path), allow_pickle=False) as trajectory:
            times = np.asarray(trajectory["times"], dtype=float)
            qpos = np.asarray(trajectory["qpos"], dtype=float)
        if times.ndim != 1 or qpos.ndim != 2 or len(times) != len(qpos):
            raise ValueError("trajectory.npz 的 times/qpos 维度或帧数不一致")
        if expected_nq is not None and qpos.shape[1] != int(expected_nq):
            raise ValueError(
                f"trajectory.npz 与当前模型 nq 不一致：trajectory={qpos.shape[1]}, model={int(expected_nq)}"
            )
        if len(times) > 1 and np.any(np.diff(times) < 0.0):
            raise ValueError("trajectory.npz 的 times 必须单调递增")
        return times, qpos

    def sample_qpos_trajectory(
        times: np.ndarray, qpos: np.ndarray, time_s: float,
    ) -> np.ndarray | None:
        sample_times = np.asarray(times, dtype=float).reshape(-1)
        frames = np.asarray(qpos, dtype=float)
        if frames.ndim != 2 or not len(sample_times) or len(sample_times) != len(frames):
            return None
        if float(time_s) <= float(sample_times[0]):
            return frames[0].copy()
        if float(time_s) >= float(sample_times[-1]):
            return frames[-1].copy()
        right = int(np.searchsorted(sample_times, float(time_s), side="right"))
        left = max(0, right - 1)
        right = min(right, len(sample_times) - 1)
        t0, t1 = float(sample_times[left]), float(sample_times[right])
        if right == left or t1 <= t0:
            return frames[left].copy()
        alpha = (float(time_s) - t0) / (t1 - t0)
        return frames[left] * (1.0 - alpha) + frames[right] * alpha


def _load_mapping_curve_helpers() -> tuple[Any, Any]:
    """Load the one authoritative minimum-jerk mapping evaluator.

    The Viewer controller is also shipped standalone, so the same dependency-free
    module is copied beside it and hash-checked through the bundle manifest.
    """
    try:
        from .mapping_curve import mapping_value, inverse_mapping_value
        return mapping_value, inverse_mapping_value
    except ImportError as package_error:
        helper_path = Path(__file__).resolve().with_name("mapping_curve.py")
        if not helper_path.is_file():
            raise RuntimeError("Viewer 缺少权威映射模块 mapping_curve.py") from package_error

        manifest_path = helper_path.with_name("manifest.json")
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text("utf-8"))
                metadata = dict(manifest.get("mapping_curve", {}) or {})
                expected = str(metadata.get("sha256", "")).strip().lower()
                if expected:
                    actual = hashlib.sha256(helper_path.read_bytes()).hexdigest()
                    if actual != expected:
                        raise RuntimeError("Viewer 映射模块完整性校验失败")
            except RuntimeError:
                raise
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Viewer 映射模块清单无效：{exc}") from exc

        spec = importlib.util.spec_from_file_location("mujoco_studio_mapping_curve", helper_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Viewer 无法加载映射模块 mapping_curve.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.mapping_value, module.inverse_mapping_value


_MAPPING_CURVE_VALUE, _MAPPING_CURVE_INVERSE = _load_mapping_curve_helpers()


# Native animation controller: use one range for both the slider and MuJoCo
# camera parameter clamp, including the standalone Client viewer bundle.
_ORTHOGRAPHIC_FOVY_MIN = 0.05
_ORTHOGRAPHIC_FOVY_MAX = 2.0
_ORTHOGRAPHIC_FOVY_STEP = 0.05


def _strict_result_time_grid(start_time: float, end_time: float, timestep: float) -> np.ndarray:
    """Return the Viewer/result chart grid on exact integer timestep ticks.

    This intentionally mirrors ``simulation.build_time_grid`` instead of importing it:
    ``viewer_runner.py`` is also delivered verbatim as a standalone Client controller.
    Keeping the helper local preserves that deployment seam while ensuring chart curves,
    derivatives and visible x-axis samples cannot drift onto an arbitrary linspace grid.
    """
    start = float(start_time)
    end = float(end_time)
    step = float(timestep)
    if not math.isfinite(start) or not math.isfinite(end) or not math.isfinite(step) or step <= 0.0:
        raise ValueError("Viewer 仿真时间范围和步长必须是有限数值，且步长必须大于 0")
    if end < start:
        raise ValueError("Viewer end_time 不能早于 start_time")
    span = end - start
    tick_count = int(math.floor(span / step + 1e-10))
    values = np.round(start + np.arange(tick_count + 1, dtype=float) * step, 12)
    return values[values <= end + 1e-10]


def _load_kinematic_closure_helpers() -> tuple[Any, Any]:
    """Load the one authoritative closure solver in Server or standalone Client mode.

    ``viewer_runner.py`` is shipped verbatim as ``server_controller.py``.  In the Server
    package we use the normal relative import; in a remote Client bundle the same source
    module is shipped beside the controller and loaded from that exact file.  The bundle
    manifest digest is checked when present, so the deployment seam does not create a
    second closure-solving implementation.
    """
    try:
        from .kinematic_closure import build_closure_runtime, solve_kinematic_closure
        return build_closure_runtime, solve_kinematic_closure
    except ImportError as package_error:
        helper_path = Path(__file__).resolve().with_name("kinematic_closure.py")
        if not helper_path.is_file():
            raise RuntimeError("Viewer 缺少运动学闭链求解模块 kinematic_closure.py") from package_error

        manifest_path = helper_path.with_name("manifest.json")
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text("utf-8"))
                metadata = dict(manifest.get("kinematic_closure", {}) or {})
                expected = str(metadata.get("sha256", "")).strip().lower()
                if expected:
                    actual = hashlib.sha256(helper_path.read_bytes()).hexdigest()
                    if actual != expected:
                        raise RuntimeError("Viewer 闭链求解模块完整性校验失败")
            except RuntimeError:
                raise
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Viewer 闭链求解模块清单无效：{exc}") from exc

        spec = importlib.util.spec_from_file_location("mujoco_studio_kinematic_closure", helper_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Viewer 无法加载运动学闭链求解模块")
        module = importlib.util.module_from_spec(spec)
        _sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            _sys.modules.pop(spec.name, None)
            raise
        build = getattr(module, "build_closure_runtime", None)
        solve = getattr(module, "solve_kinematic_closure", None)
        if not callable(build) or not callable(solve):
            raise RuntimeError("Viewer 闭链求解模块接口不完整")
        return build, solve


def _enforce_viewer_kinematic_closure(
    mujoco: Any, model: Any, data: Any, runtime: Any, solver: Any,
    *, driven_joint_ids: set[str], previous_qpos: np.ndarray | None,
    previous_time_s: float | None, time_s: float, timestep: float,
) -> tuple[np.ndarray | None, float | None, str]:
    """Project the current Viewer qpos onto the kinematic closure manifold.

    The server trajectory is a good seed but interpolation and manual motor overrides can
    leave the nonlinear closed-chain manifold.  This policy runs the shared DLS solver
    after *all* qpos writes, warm-starts nearby frames, and fails closed by holding the
    last valid pose when the requested configuration becomes singular or unreachable.
    """
    if runtime is None or not bool(getattr(runtime, "enabled", False)):
        return previous_qpos, previous_time_s, ""
    if not callable(solver):
        raise RuntimeError("运动学闭链求解器未初始化")

    warm_start = previous_qpos
    jump_threshold_s = max(abs(float(timestep)) * 5.0, 0.05)
    if previous_time_s is None or abs(float(time_s) - float(previous_time_s)) > jump_threshold_s:
        warm_start = None
    solved = solver(
        mujoco, model, data, runtime,
        driven_joint_ids=driven_joint_ids,
        previous_qpos=warm_start,
        kinematics_only=True,
    )
    if bool(getattr(solved, "converged", False)):
        return data.qpos.copy(), float(time_s), ""

    residual_mm = float(getattr(solved, "residual_mm", math.inf))
    reason = str(getattr(solved, "reason", "kinematic_closure_nonconvergence"))
    if previous_qpos is None:
        raise RuntimeError(f"运动学闭链求解失败：{reason}，残差 {residual_mm:.6g} mm")
    data.qpos[:] = previous_qpos
    return previous_qpos, previous_time_s, f" | 闭链保持上一有效姿态（残差 {residual_mm:.3g} mm）"


# ---------------------------------------------------------------------------
# Windows transient-share atomic replace retry.  Mirrors
# ``core.atomic_io.atomic_replace`` so viewer_runner keeps its standalone-file
# delivery property (no Server import dependencies when shipped to Client).
# ---------------------------------------------------------------------------
import sys as _sys
import time as _time

_VIEWER_ATOMIC_MAX_ATTEMPTS = 6
_VIEWER_ATOMIC_BASE_BACKOFF_S = 0.05


def _atomic_replace(src: Path, dst: Path) -> None:
    last_error: BaseException | None = None
    for attempt in range(_VIEWER_ATOMIC_MAX_ATTEMPTS):
        try:
            os.replace(Path(src), Path(dst))
            return
        except PermissionError as exc:
            last_error = exc
            if _sys.platform != "win32" or attempt == _VIEWER_ATOMIC_MAX_ATTEMPTS - 1:
                raise
            _time.sleep(_VIEWER_ATOMIC_BASE_BACKOFF_S * (attempt + 1))
    if last_error is not None:  # pragma: no cover - defensive guard
        raise last_error


_DISTANCE_SITE_PREFIX = "__mjs_distance_site_"
_DISTANCE_SITE_RADIUS_M = 0.00125
_DISTANCE_SITE_ALPHA = 0.78
_DISTANCE_SITE_COLOR_A = (1.0, 0.25, 0.2)
_DISTANCE_SITE_COLOR_B = (0.15, 0.65, 1.0)


def _gantt_cache_pair_exists(cache_dir: str | Path) -> bool:
    root = Path(cache_dir)
    return all((root / filename).is_file() for filename in ("latest_gantt.png", "latest_gantt.json"))


def _gantt_cache_signature(cache_dir: str | Path) -> tuple[object, ...] | None:
    """Return a cheap change signature for the exact PNG+JSON cache pair.

    Atomic replacement can change either member independently.  Tracking both
    files (mtime, size and inode where available) prevents a PNG-only refresh
    from being missed and also distinguishes a newly published pair whose
    timestamp happens to collide on a coarse filesystem.
    """
    root = Path(cache_dir)
    try:
        png = (root / "latest_gantt.png").stat()
        meta = (root / "latest_gantt.json").stat()
    except OSError:
        return None
    return (
        str(root),
        int(getattr(png, "st_mtime_ns", int(png.st_mtime * 1e9))), int(png.st_size), int(getattr(png, "st_ino", 0)),
        int(getattr(meta, "st_mtime_ns", int(meta.st_mtime * 1e9))), int(meta.st_size), int(getattr(meta, "st_ino", 0)),
    )


def _select_gantt_cache_source(primary_dir: str | Path, fallback_dir: str | Path) -> tuple[Path, str]:
    """Return *only* the Web popup's PNG+JSON pair.

    Keep the fallback argument for older callers and compatibility tests, but
    never silently substitute an independently rendered Gantt. Missing cache
    is shown as a readable placeholder until the authoritative PNG arrives.
    """
    primary = Path(primary_dir)
    if _gantt_cache_pair_exists(primary):
        return primary, "project_popup_cache"
    return primary, "missing_project_popup_cache"


# Diagnostic delivery profile.  Each test package changes only this mapping;
# the instrumentation and execution paths remain byte-for-byte identical.
_VIEWER_PERF_PROFILE: dict[str, Any] = {
    "name": "v2113_motor_coalesced_kinematic_closure",
    "viewer_ready_before_sampling": True,
    "startup_distance_backend": "vectorized_cache",
    "target_fps": 60.0,
    "correct_frame_pacing": True,
    "disable_measurement": False,
    "measurement_hz": 20.0,
    "measurement_async": True,
    # Fully exact queries are the default everywhere. The optional low-latency
    # mode alone applies the bounded realtime query budget.
    "measurement_low_latency": False,
    "measurement_query_budget_per_pair": 4096,
    "measurement_total_query_budget": 20000,
    "measurement_pair_workers": 4,
    "remote_poll_async": True,
    "remote_poll_interval_s": 0.25,
    "forward_hz": 0.0,              # 0 = every rendered frame
    "sync_hz": 0.0,                 # 0 = every rendered frame
    "ui_hz": 0.0,                   # 0 = every rendered frame
    "motor_ui_hz": 30.0,             # non-decoupled slider projection; drag input itself remains native-rate
    "require_scipy": True,
}


class _ViewerPerfMeter:
    """Low-overhead one-second Viewer timing report for field comparison."""

    def __init__(self, profile_name: str) -> None:
        self.profile_name = profile_name
        self.started = time.perf_counter()
        self.frames = 0
        self.totals: dict[str, float] = {}
        self.calls: dict[str, int] = {}

    def add(self, name: str, seconds: float) -> None:
        self.totals[name] = self.totals.get(name, 0.0) + max(float(seconds), 0.0)
        self.calls[name] = self.calls.get(name, 0) + 1

    def frame(self, now: float) -> None:
        self.frames += 1
        elapsed = now - self.started
        if elapsed < 1.0:
            return
        parts = [
            "VIEWER_PERF",
            f"profile={self.profile_name}",
            f"fps={self.frames / max(elapsed, 1e-9):.2f}",
        ]
        for name in ("frame", "ui", "poll", "motor_apply", "closure", "forward", "measure", "overlay", "sync", "sleep"):
            calls = self.calls.get(name, 0)
            average_ms = self.totals.get(name, 0.0) * 1000.0 / max(calls, 1)
            parts.append(f"{name}_ms={average_ms:.3f}")
            if name in {"poll", "measure", "forward", "sync"}:
                parts.append(f"{name}_calls={calls}")
        print("[" + " | ".join(parts) + "]", flush=True)
        self.started = now
        self.frames = 0
        self.totals.clear()
        self.calls.clear()


class _RemoteControlPoller:
    """Run the blocking HTTP automation poll outside the render/UI thread."""

    def __init__(self, fetch: Any, interval_s: float) -> None:
        self.fetch = fetch
        self.interval_s = max(float(interval_s), 0.05)
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.latest: dict[str, Any] | None = None
        self.revision = 0
        self.thread = threading.Thread(target=self._run, name="viewer-remote-poll", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            incoming = self.fetch()
            if incoming is not None:
                with self.lock:
                    self.latest = incoming
                    self.revision += 1
            self.stop_event.wait(self.interval_s)

    def snapshot(self, seen_revision: int) -> tuple[dict[str, Any] | None, int]:
        with self.lock:
            if self.revision == seen_revision:
                return None, seen_revision
            return (dict(self.latest) if self.latest is not None else None), self.revision

    def close(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=0.7)


class _AsyncDistanceWorker:
    """Measure on a private MjData; the render thread only submits latest qpos."""

    def __init__(
        self, mujoco: Any, model: Any, pairs: list[dict[str, Any]], *,
        low_latency: bool = False, query_budget_per_pair: int = 4096,
        total_query_budget: int = 20000, pair_workers: int = 4,
    ) -> None:
        self.mujoco = mujoco
        self.model = model
        self.pairs = []
        effective_pair_budget = min(
            max(512, int(query_budget_per_pair)),
            max(1024, int(total_query_budget) // max(1, len(pairs))),
        )
        for source in pairs:
            item = dict(source)
            item.pop("_distance_runtime", None)
            item["_distance_low_latency"] = bool(low_latency)
            item["_distance_query_budget"] = effective_pair_budget
            item = _clone_distance_pair(item)
            self.pairs.append(item)
        worker_count = min(
            max(1, int(pair_workers)), max(1, len(self.pairs)), max(1, os.cpu_count() or 1),
        )
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=worker_count, thread_name_prefix="viewer-distance-pair",
        )
        self.worker_count = worker_count
        self.event = threading.Event()
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.requested_low_latency = bool(low_latency)
        self.pending_qpos: tuple[np.ndarray, float] | None = None
        self.result: list[tuple[float, np.ndarray | None, np.ndarray | None, np.ndarray | None]] | None = None
        self.result_revision = 0
        self.result_seconds = 0.0
        self.result_source_time = 0.0
        self.result_completed_time = 0.0
        self.thread = threading.Thread(target=self._run, name="viewer-distance", daemon=True)
        self.thread.start()

    def set_low_latency(self, enabled: bool) -> None:
        """Switch modes without touching the render thread or queuing work."""
        with self.lock:
            self.requested_low_latency = bool(enabled)

    def submit(self, qpos: Any) -> None:
        with self.lock:
            # One overwrite-only slot: motor dragging can never create a queue.
            self.pending_qpos = (np.asarray(qpos, dtype=float).copy(), time.perf_counter())
        self.event.set()

    def snapshot(self, seen_revision: int) -> tuple[Any, int, float, float]:
        with self.lock:
            age = (
                max(time.perf_counter() - self.result_source_time, 0.0)
                if self.result_source_time > 0.0 else 0.0
            )
            if self.result_revision == seen_revision:
                return None, seen_revision, 0.0, age
            return self.result, self.result_revision, self.result_seconds, age

    def _run(self) -> None:
        data = self.mujoco.MjData(self.model)
        while not self.stop_event.is_set():
            self.event.wait(0.1)
            self.event.clear()
            with self.lock:
                pending = self.pending_qpos
                self.pending_qpos = None
                requested_low_latency = self.requested_low_latency
            if pending is None:
                continue
            qpos, source_time = pending
            started = time.perf_counter()
            for pair in self.pairs:
                if pair.get("_distance_low_latency") is requested_low_latency:
                    continue
                pair["_distance_low_latency"] = requested_low_latency
                runtime = pair.get("_distance_runtime")
                if isinstance(runtime, dict):
                    runtime["last_pose"] = None
                    runtime["last_measurement"] = None
            data.qpos[:] = qpos
            self.mujoco.mj_forward(self.model, data)
            measured: list[tuple[float, np.ndarray | None, np.ndarray | None, np.ndarray | None]] = []
            pair_results = list(self.executor.map(
                lambda pair: _measure_pair(self.mujoco, self.model, data, pair), self.pairs,
            ))
            for pair, (value, fromto) in zip(self.pairs, pair_results):
                runtime = pair.get("_distance_runtime", {})
                points_a = runtime.get("points_a")
                points_b = runtime.get("points_b")
                measured.append((
                    value,
                    None if fromto is None else np.asarray(fromto, dtype=float).copy(),
                    None if points_a is None else np.asarray(points_a[::max(1, int(math.ceil(len(points_a) / 2500)))], dtype=float).copy(),
                    None if points_b is None else np.asarray(points_b[::max(1, int(math.ceil(len(points_b) / 2500)))], dtype=float).copy(),
                ))
            with self.lock:
                self.result = measured
                self.result_seconds = time.perf_counter() - started
                self.result_source_time = source_time
                self.result_completed_time = time.perf_counter()
                self.result_revision += 1

    def close(self) -> None:
        self.stop_event.set()
        self.event.set()
        self.thread.join(timeout=1.0)
        self.executor.shutdown(wait=False, cancel_futures=True)


def _smoothstep(value: float) -> float:
    value = min(max(float(value), 0.0), 1.0)
    return 10 * value**3 - 15 * value**4 + 6 * value**5


def _integral_s(value: float) -> float:
    return 2.5 * value**4 - 3 * value**5 + value**6


def _s_curve_progress(segment: dict[str, Any], elapsed: float) -> float:
    duration = max(float(segment.get("duration", 0.0)), 1e-12)
    acceleration = float(segment.get("acceleration_time", 0.0))
    rise = min(float(segment.get("ease_in_time", acceleration)) if segment.get("ease_in", True) else 0.0, duration)
    fall = min(float(segment.get("ease_out_time", acceleration)) if segment.get("ease_out", True) else 0.0, duration)
    if rise + fall > duration:
        scale = duration / max(rise + fall, 1e-12)
        rise *= scale
        fall *= scale
    constant = duration - rise - fall
    peak = 1.0 / max(constant + 0.5 * (rise + fall), 1e-12)
    elapsed = min(max(elapsed, 0.0), duration)
    if rise and elapsed < rise:
        return peak * rise * _integral_s(elapsed / rise)
    accumulated = 0.5 * peak * rise
    if elapsed <= rise + constant:
        return accumulated + peak * (elapsed - rise)
    accumulated += peak * constant
    if fall:
        value = (elapsed - rise - constant) / fall
        return accumulated + peak * fall * (value - _integral_s(value))
    return 1.0


def _point_progress(segment: dict[str, Any], elapsed: float) -> float:
    duration = max(float(segment.get("duration", 0.0)), 1e-12)
    travel = float(segment.get("travel", 0.0))
    points = sorted((float(item[0]), float(item[1])) for item in segment.get("points", []) if len(item) >= 2)
    if not points:
        return _smoothstep(elapsed / duration)
    max_x = max(points[-1][0], 1e-12)
    phase = min(max(elapsed / duration, 0.0), 1.0)
    normalized = [(x / max_x if max_x > 1 else x, y) for x, y in points]
    if normalized[0][0] > 0:
        normalized.insert(0, (0.0, 0.0))
    if normalized[-1][0] < 1:
        normalized.append((1.0, travel))
    for left, right in zip(normalized, normalized[1:]):
        if left[0] <= phase <= right[0]:
            ratio = (phase - left[0]) / max(right[0] - left[0], 1e-12)
            value = left[1] + ratio * (right[1] - left[1])
            return value / travel if abs(travel) > 1e-12 else 0.0
    return 1.0


def _external_csv_value(segment: dict[str, Any], elapsed: float) -> float:
    points = sorted(
        (float(item[0]), float(item[1]))
        for item in segment.get("points", [])
        if isinstance(item, (list, tuple)) and len(item) >= 2
    )
    if not points:
        return 0.0
    local_time = max(float(elapsed), 0.0)
    if local_time <= points[0][0]:
        return points[0][1]
    if local_time >= points[-1][0]:
        return points[-1][1]
    for left, right in zip(points, points[1:]):
        if left[0] <= local_time <= right[0]:
            ratio = (local_time - left[0]) / max(right[0] - left[0], 1e-12)
            return left[1] + ratio * (right[1] - left[1])
    return points[-1][1]


def segment_value(segment: dict[str, Any], time_s: float) -> float:
    start = float(segment.get("start", 0.0))
    duration = max(float(segment.get("duration", 0.0)), 1e-12)
    travel = float(segment.get("travel", 0.0))
    profile = segment.get("profile", "s_curve")
    if profile == "mapping":
        return 0.0
    if profile == "external_csv":
        if time_s < start:
            return 0.0
        return _external_csv_value(segment, time_s - start)
    if time_s <= start:
        return 0.0
    if time_s >= start + duration:
        return travel
    elapsed = time_s - start
    if profile == "smoothstep":
        progress = _smoothstep(elapsed / duration)
    elif profile == "points":
        progress = _point_progress(segment, elapsed)
    else:
        progress = _s_curve_progress(segment, elapsed)
    return travel * progress


def _mapping_source_drive_id(reference: str) -> str:
    value = str(reference or "").strip()
    return value[6:] if value.startswith("drive:") else ""


def _mapping_points(segment: dict[str, Any]) -> list[tuple[float, float]]:
    """Standalone copy of the Server's V21-compatible mapping normalization."""
    dedup: dict[float, tuple[float, float]] = {}
    for point in segment.get("points", []) or []:
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        dedup[round(x, 9)] = (x, y)
    points = [dedup[key] for key in sorted(dedup)]
    if points and (points[0][0] > 1e-12 or points[-1][0] < -1e-12):
        points.append((0.0, 0.0))
        points.sort(key=lambda item: item[0])
    return points


def _mapping_value(segment: dict[str, Any], source: float) -> float:
    points = tuple(_mapping_points(segment))
    return float(_MAPPING_CURVE_VALUE(points, float(source))) if points else 0.0


def _inverse_mapping_value(segment: dict[str, Any], target: float, preferred_source: float = 0.0) -> float:
    """Invert the exact same minimum-jerk curve used for forward Viewer mapping."""
    points = tuple(_mapping_points(segment))
    if not points:
        return float(preferred_source)
    return float(_MAPPING_CURVE_INVERSE(points, float(target), float(preferred_source)))


def _viewer_mapping_source_drive_id(
    target_drive_id: str,
    mapping_segments_by_drive: dict[str, dict[str, Any]],
    drive_by_id: dict[str, dict[str, Any]],
    drives_by_joint: dict[str, list[str]],
) -> str:
    """Resolve the immediate source drive used by one Viewer mapping target."""
    segment = mapping_segments_by_drive.get(str(target_drive_id))
    if not segment:
        return ""
    source_ref = str(segment.get("mapping_source_joint_id", ""))
    direct = _mapping_source_drive_id(source_ref)
    if direct in drive_by_id:
        return direct
    candidates = drives_by_joint.get(source_ref, [])
    return candidates[0] if candidates else ""


def _viewer_root_mapping_source(
    drive_id: str,
    mapping_segments_by_drive: dict[str, dict[str, Any]],
    drive_by_id: dict[str, dict[str, Any]],
    drives_by_joint: dict[str, list[str]],
    target_value: float | None = None,
    current_values: dict[str, float] | None = None,
) -> tuple[str, float | None]:
    """Walk target→source mappings and inverse-map a manual follower command."""
    current_id, desired = str(drive_id), target_value
    seen: set[str] = set()
    while current_id in mapping_segments_by_drive and current_id not in seen:
        seen.add(current_id)
        segment = mapping_segments_by_drive[current_id]
        source_id = _viewer_mapping_source_drive_id(
            current_id, mapping_segments_by_drive, drive_by_id, drives_by_joint,
        )
        if not source_id:
            break
        if desired is not None:
            preferred = float((current_values or {}).get(source_id, 0.0))
            desired = _inverse_mapping_value(segment, float(desired), preferred)
        current_id = source_id
    return current_id, desired


def _viewer_mapping_topology(
    mapping_segments_by_drive: dict[str, dict[str, Any]],
    drive_by_id: dict[str, dict[str, Any]],
    drives_by_joint: dict[str, list[str]],
) -> tuple[dict[str, str], dict[str, frozenset[str]]]:
    """Return canonical root and linked mapping family for every enabled Viewer drive.

    A mapping family is one manual-control unit: the root is authoritative and all
    descendants are deterministic projections of that root.  This is deliberately
    transient Viewer topology; it does not add a persisted schema or second drive model.
    """
    root_by_drive: dict[str, str] = {}
    members_by_root: dict[str, set[str]] = {}
    for drive_id in drive_by_id:
        root_id, _ = _viewer_root_mapping_source(
            drive_id, mapping_segments_by_drive, drive_by_id, drives_by_joint,
        )
        root_id = root_id or drive_id
        root_by_drive[drive_id] = root_id
        members_by_root.setdefault(root_id, set()).add(drive_id)
        members_by_root[root_id].add(root_id)
    family_by_drive: dict[str, frozenset[str]] = {}
    for drive_id, root_id in root_by_drive.items():
        family_by_drive[drive_id] = frozenset(members_by_root.get(root_id, {drive_id}))
    return root_by_drive, family_by_drive


def _viewer_apply_mapping_overrides(
    values: dict[str, float],
    mapping_segments_by_drive: dict[str, dict[str, Any]],
    drive_by_id: dict[str, dict[str, Any]],
    drives_by_joint: dict[str, list[str]],
) -> dict[str, float]:
    """Forward-project all mapping followers from the current source/root values."""
    result = dict(values)
    for _ in range(len(mapping_segments_by_drive) + 1):
        changed = False
        for target_id, segment in mapping_segments_by_drive.items():
            source_ref = str(segment.get("mapping_source_joint_id", ""))
            source_drive = _mapping_source_drive_id(source_ref)
            if source_drive:
                if source_drive not in result:
                    continue
                source_value = float(result[source_drive])
            else:
                candidates = drives_by_joint.get(source_ref, [])
                source_value = sum(float(result.get(item, 0.0)) for item in candidates)
            mapped = _mapping_value(segment, source_value)
            if abs(float(result.get(target_id, 0.0)) - mapped) > 1e-12:
                result[target_id] = mapped
                changed = True
        if not changed:
            break
    return result


def _resolved_positions(segments: list[dict[str, Any]], time_s: float) -> tuple[dict[str, float], dict[str, float]]:
    joints: dict[str, float] = {}; drives: dict[str, float] = {}; pending = []
    for segment in segments:
        if segment.get("profile") == "mapping": pending.append(segment); continue
        value = segment_value(segment, time_s)
        jid, did = str(segment.get("joint_id", "")), str(segment.get("drive_id", ""))
        if jid: joints[jid] = joints.get(jid, 0.0) + value
        if did: drives[did] = drives.get(did, 0.0) + value
    target_joints = {str(item.get("joint_id", "")) for item in pending if item.get("joint_id")}
    target_drives = {str(item.get("drive_id", "")) for item in pending if item.get("drive_id")}
    for _ in range(len(pending) + 1):
        progress = False
        for segment in list(pending):
            source = str(segment.get("mapping_source_joint_id", ""))
            source_drive = _mapping_source_drive_id(source)
            if not source:
                continue
            if source_drive:
                if source_drive in target_drives and source_drive not in drives:
                    continue
                source_value = float(drives.get(source_drive, 0.0))
            else:
                if source in target_joints and source not in joints:
                    continue
                source_value = float(joints.get(source, 0.0))
            value = _mapping_value(segment, source_value)
            jid, did = str(segment.get("joint_id", "")), str(segment.get("drive_id", ""))
            if jid: joints[jid] = joints.get(jid, 0.0) + value
            if did: drives[did] = drives.get(did, 0.0) + value
            pending.remove(segment); progress = True
        if not progress: break
    for segment in pending:
        did, jid = str(segment.get("drive_id", "")), str(segment.get("joint_id", ""))
        if did: drives.setdefault(did, 0.0)
        if jid: joints.setdefault(jid, 0.0)
    return drives, joints


def joint_positions(segments: list[dict[str, Any]], time_s: float) -> dict[str, float]:
    return _resolved_positions(segments, time_s)[1]


def drive_positions(segments: list[dict[str, Any]], time_s: float) -> dict[str, float]:
    return _resolved_positions(segments, time_s)[0]


def _mapping_gantt_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace synthetic full-span mapping rows with their source blocks."""
    result = [dict(item) for item in segments if item.get("profile") != "mapping"]

    def source_blocks(reference: str, seen: set[str]) -> list[dict[str, Any]]:
        if not reference or reference in seen:
            return []
        next_seen = {*seen, reference}
        source_drive = _mapping_source_drive_id(reference)
        blocks: list[dict[str, Any]] = []
        for item in segments:
            if source_drive:
                if str(item.get("drive_id", "")) != source_drive:
                    continue
            elif str(item.get("joint_id", "")) != reference:
                continue
            if item.get("profile") == "mapping":
                blocks.extend(source_blocks(str(item.get("mapping_source_joint_id", "")), next_seen))
            else:
                blocks.append(item)
        return blocks

    def _source_is_nested(reference: str) -> bool:
        reference = str(reference or "").strip()
        if not reference:
            return False
        source_drive = _mapping_source_drive_id(reference)
        for item in segments:
            if item.get("profile") != "mapping":
                continue
            if source_drive:
                if str(item.get("drive_id", "")) == source_drive:
                    return True
            elif str(item.get("joint_id", "")) == reference:
                return True
        return False

    for mapping in (item for item in segments if item.get("profile") == "mapping"):
        target_joint = str(mapping.get("joint_id", ""))
        mapping_reference = str(mapping.get("mapping_source_joint_id", ""))
        sources = sorted(
            source_blocks(mapping_reference, {target_joint, f"drive:{mapping.get('drive_id', '')}"}),
            key=lambda item: (float(item.get("start", 0.0)), float(item.get("end", 0.0)), str(item.get("segment_id", ""))),
        )
        # V2.6.4 fix — mirror motion.mapping_gantt_blocks: derive companion
        # breakpoints from the source's own cumulative per-block travel mapped
        # through the mapping curve, instead of sampling the follower joint at
        # source block boundary times. The time sample is the superposition of
        # every source segment active at that instant, so overlapping source
        # segments smeared companion blocks off the mapping breakpoints. Nested
        # mapping sources keep the historical time sample.
        nested_source = _source_is_nested(mapping_reference)
        cumulative_source = 0.0
        for index, source in enumerate(sources):
            start = float(source.get("start", 0.0))
            end = float(source.get("end", start))
            if nested_source:
                start_value = float(joint_positions(segments, start).get(target_joint, 0.0))
                end_value = float(joint_positions(segments, end).get(target_joint, start_value))
            else:
                source_start = cumulative_source
                source_end = cumulative_source + float(source.get("travel", 0.0) or 0.0)
                cumulative_source = source_end
                start_value = float(_mapping_value(mapping, source_start))
                end_value = float(_mapping_value(mapping, source_end))
            block = dict(mapping)
            block.update({
                "segment_id": f"{mapping.get('segment_id', 'mapping')}--source--{source.get('segment_id', index)}--{index}",
                "name": f"{mapping.get('name', '映射')} ← {source.get('drive_name', '源电机')}/{source.get('name', '运动段')}",
                "start": start, "end": end, "duration": max(0.0, end - start),
                "travel": end_value - start_value,
                "travel_start": start_value, "travel_end": end_value,
                "source_drive_id": str(source.get("drive_id", "")),
                "source_drive_name": str(source.get("drive_name", "")),
                "source_segment_id": str(source.get("segment_id", "")),
                "source_segment_name": str(source.get("name", "")),
                "mapping_segment_id": str(mapping.get("segment_id", "")),
            })
            result.append(block)
    return result


def _crank_displacement(meta: dict[str, Any], angle_degrees: float) -> float:
    phi = float(meta["initial_angle_rad"]) + math.radians(float(angle_degrees))
    radius, rod = float(meta["crank_length"]), float(meta["rod_length"])
    offset, origin = float(meta["slider_offset"]), float(meta["slider_coord0"])
    sign = 1.0 if float(meta.get("branch_sign", 1.0)) >= 0 else -1.0
    x, y = radius * math.cos(phi), radius * math.sin(phi)
    inside = rod * rod - (offset - y) * (offset - y)
    if inside < -1e-6:
        raise ValueError("当前角位移超出曲柄滑块机构可达范围")
    return x + sign * math.sqrt(max(inside, 0.0)) - origin


def _launch_passive(mujoco: Any, model: Any, data: Any) -> Any:
    error: Exception | None = None
    original_backend = os.environ.get("MUJOCO_GL")
    attempts = [original_backend, "angle"] if os.name == "nt" else [original_backend]
    for backend in dict.fromkeys(attempts):
        try:
            if backend:
                os.environ["MUJOCO_GL"] = backend
            elif "MUJOCO_GL" in os.environ:
                del os.environ["MUJOCO_GL"]
            # Match the legacy viewer: both native sidebars start hidden.
            # MuJoCo keeps its built-in Tab / Shift+Tab toggles available.
            return mujoco.viewer.launch_passive(model, data, show_left_ui=False, show_right_ui=False)
        except Exception as exc:  # noqa: BLE001
            error = exc
    raise RuntimeError(
        "MuJoCo Viewer 创建失败。请在本机桌面环境运行并检查 OpenGL/显卡驱动；"
        f"底层错误：{error or 'unknown graphics error'}"
    )



# MuJoCo's mjv_moveCamera scales orthographic lookat translation by 0.15.
# Undo that native slowdown to approach a one-screen-pixel pan for one mouse
# pixel while keeping the native camera gesture/zoom/rotation code intact.
_ORTHOGRAPHIC_PAN_PIXEL_GAIN = 1.0 / 0.15


def _camera_pan_signature(camera: Any) -> tuple[int, int, int, float, float, float, int]:
    """Camera properties native right-pan MUST leave unchanged.

    A pan changes only lookat. Rotation, zoom, switching camera mode,
    resetting a preset and changing projection do not qualify as pan.
    """
    return (
        int(getattr(camera, "type", -1)),
        int(getattr(camera, "fixedcamid", -1)),
        int(getattr(camera, "trackbodyid", -1)),
        float(getattr(camera, "azimuth", float("nan"))),
        float(getattr(camera, "elevation", float("nan"))),
        float(getattr(camera, "distance", float("nan"))),
        int(getattr(camera, "orthographic", 1)),
    )


def _classify_orthographic_pan(
    camera: Any, previous_lookat: Any, previous_pose: Any, *,
    right_button: bool | None, inferred_streak: int,
    free_camera_type: int,
) -> tuple[bool, int]:
    """Gate extra pan against native camera motion, without GLFW callbacks.

    ``right_button`` is None if the passive Viewer does not expose input state.
    In that case only the second and later small, consecutive lookat-only
    movements are amplified. This suppresses isolated double-click recentering.
    """
    if previous_lookat is None or previous_pose is None or right_button is False:
        return False, 0
    try:
        pose = _camera_pan_signature(camera)
        if pose[0] != int(free_camera_type) or pose[6] != 1 or pose[:3] != previous_pose[:3]:
            return False, 0
        if not np.allclose(pose[3:6], previous_pose[3:6], rtol=1e-11, atol=1e-11):
            return False, 0
        current = np.asarray(camera.lookat, dtype=float)
        delta = current - np.asarray(previous_lookat, dtype=float)
        distance = float(pose[5])
        if not (np.all(np.isfinite(delta)) and np.all(np.isfinite(current))
                and math.isfinite(distance) and distance > 0):
            return False, 0
        native_movement = float(np.linalg.norm(delta))
        # A very large lookat jump is a preset/center action, not a mouse pan.
        if native_movement <= 1e-12 or native_movement > max(1e-7, distance * 0.20):
            return False, 0
        if right_button is True:
            return True, 0
        streak = min(2, max(0, int(inferred_streak)) + 1)
        return streak >= 2, streak
    except (TypeError, ValueError, OverflowError, AttributeError):
        return False, 0


def _win32_viewer_right_mouse_pressed() -> bool | None:
    """Use the focused MuJoCo GLFW window when Handle has no GLFW pointer.

    GLFW's window is private in the official passive `viewer.Handle`. On
    Windows, GetAsyncKeyState is safe only after checking that the focused
    top-level HWND belongs to *this* process and is a GLFW window, not the
    sibling Tk playback controller or another application. Other platforms
    return None and use the conservative camera-motion fallback instead.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
        )
        user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
        user32.GetAsyncKeyState.restype = ctypes.c_short
        foreground = user32.GetForegroundWindow()
        if not foreground:
            return False
        owner_pid = wintypes.DWORD()
        if not user32.GetWindowThreadProcessId(foreground, ctypes.byref(owner_pid)):
            return None
        if owner_pid.value != os.getpid():
            return False
        class_buffer = ctypes.create_unicode_buffer(128)
        if not user32.GetClassNameW(foreground, class_buffer, len(class_buffer)):
            return None
        if not class_buffer.value.startswith("GLFW"):
            return False
        # VK_RBUTTON = 0x02; bit 15 is the currently-held state.
        return bool(int(user32.GetAsyncKeyState(0x02)) & 0x8000)
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _viewer_right_mouse_pressed(glfw_module: Any, window: Any) -> bool | None:
    """Prefer a real GLFW window; otherwise ask Win32 or infer camera pan."""
    if glfw_module is not None and window is not None:
        try:
            get_attrib = getattr(glfw_module, "get_window_attrib", None)
            if callable(get_attrib) and not get_attrib(window, glfw_module.FOCUSED):
                return False
            return glfw_module.get_mouse_button(
                window, glfw_module.MOUSE_BUTTON_RIGHT,
            ) == glfw_module.PRESS
        except (AttributeError, RuntimeError, ValueError, TypeError):
            pass
    return _win32_viewer_right_mouse_pressed()


def _amplify_orthographic_pan(camera: Any, previous: Any, *, active: bool,
                               factor: float = 3.0) -> np.ndarray:
    """Amplify only an already-applied native right-button camera translation.

    Native MuJoCo continues owning cursor callbacks, rotation and zoom. Each
    right-drag frame adds ``factor - 1`` times the *native* look-at delta. The
    returned sample includes that correction, so subsequent frames do not
    amplify an earlier correction twice. No mouse capture or extra Tool.
    """
    current = np.asarray(camera.lookat, dtype=float).copy()
    if active and previous is not None:
        before = np.asarray(previous, dtype=float)
        delta = current - before
        if np.all(np.isfinite(delta)) and np.all(np.isfinite(current)):
            current = before + float(factor) * delta
            camera.lookat[:] = current
    return current


def _prime_passive_viewer(viewer: Any) -> None:
    """Synchronize/present the first passive-Viewer frame before declaring READY.

    ``launch_passive`` starts the native render loop asynchronously.  Returning
    a handle means the viewer thread exists, but on large models Windows may
    still need a scheduling turn before the first frame/window is presented.
    Keep this bounded and cheap: sync the already-built model, briefly release
    the Python GIL to the native GUI/render thread, then sync once more.
    """
    sync = getattr(viewer, "sync", None)
    is_running = getattr(viewer, "is_running", None)
    if callable(is_running) and not bool(is_running()):
        raise RuntimeError("MuJoCo Viewer 在首帧呈现前已退出")
    if callable(sync):
        sync()
    for _ in range(3):
        time.sleep(0.01)
        if callable(is_running) and not bool(is_running()):
            raise RuntimeError("MuJoCo Viewer 在首帧呈现前已退出")
    if callable(sync):
        sync()


def _mesh_collection_center(model: Any, data: Any, mesh_geom_type: int) -> np.ndarray:
    """Return the world-space AABB center of every instantiated mesh geom.

    MuJoCo's free camera rotates around ``cam.lookat``.  ``model.stat.center``
    is a useful fallback, but may include non-mesh scene geometry.  The Studio
    viewer therefore derives the pivot from the actual mesh instances that the
    user sees in the hierarchy.
    """
    lower = np.full(3, np.inf, dtype=float)
    upper = np.full(3, -np.inf, dtype=float)
    for geom_id in range(int(getattr(model, "ngeom", 0) or 0)):
        if int(model.geom_type[geom_id]) != int(mesh_geom_type):
            continue
        mesh_id = int(model.geom_dataid[geom_id])
        if mesh_id < 0:
            continue
        vertex_start = int(model.mesh_vertadr[mesh_id])
        vertex_count = int(model.mesh_vertnum[mesh_id])
        vertices = np.asarray(
            model.mesh_vert[vertex_start:vertex_start + vertex_count], dtype=float,
        )
        if not len(vertices):
            continue
        rotation = np.asarray(data.geom_xmat[geom_id], dtype=float).reshape(3, 3)
        position = np.asarray(data.geom_xpos[geom_id], dtype=float)
        world_vertices = vertices @ rotation.T + position
        finite = world_vertices[np.all(np.isfinite(world_vertices), axis=1)]
        if not len(finite):
            continue
        lower = np.minimum(lower, np.min(finite, axis=0))
        upper = np.maximum(upper, np.max(finite, axis=0))
    if np.all(np.isfinite(lower)) and np.all(np.isfinite(upper)):
        return (lower + upper) * 0.5
    fallback = np.asarray(model.stat.center, dtype=float)
    return fallback if fallback.shape == (3,) and np.all(np.isfinite(fallback)) else np.zeros(3, dtype=float)


def _mesh_surface_points(
    model: Any, geom_id: int, spacing_mm: float, max_points: int = 400,
    corner_angle_degrees: float = 25.0,
) -> np.ndarray:
    """Fast curvature-ranked surface sampling for large distance point sets.

    V2.5.3 deliberately avoids Python-level Poisson dart throwing.  Sharp
    vertices are ranked by dihedral curvature (largest first), then the
    remaining budget is filled by vectorized area-weighted barycentric
    samples.  This keeps high-curvature locations represented without letting
    corner processing dominate 10k+ point workloads.
    """
    point_limit = max(16, int(max_points))
    mesh_id = int(model.geom_dataid[geom_id])
    if mesh_id < 0:
        return np.empty((0, 3), dtype=float)
    vertex_start = int(model.mesh_vertadr[mesh_id])
    vertex_count = int(model.mesh_vertnum[mesh_id])
    face_start = int(model.mesh_faceadr[mesh_id])
    face_count = int(model.mesh_facenum[mesh_id])
    vertices = np.asarray(model.mesh_vert[vertex_start:vertex_start + vertex_count], dtype=float)
    faces = np.asarray(model.mesh_face[face_start:face_start + face_count], dtype=int)
    if not len(vertices):
        return np.empty((0, 3), dtype=float)
    if not len(faces):
        if len(vertices) <= point_limit:
            return vertices.copy()
        indexes = np.linspace(0, len(vertices) - 1, point_limit, dtype=int)
        return vertices[indexes]

    triangles = vertices[faces]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    norm = np.linalg.norm(cross, axis=1)
    valid = norm > 1e-15
    if not np.any(valid):
        return vertices[:point_limit].copy()
    normals = np.zeros_like(cross)
    normals[valid] = cross[valid] / norm[valid, None]
    areas = norm * 0.5
    total_area = float(np.sum(areas))

    # Curvature budget is intentionally bounded: users asked that sudden
    # curvature points be preferred, but not at the expense of startup time.
    # Rank by local normal disagreement and consume from highest curvature down.
    curvature_budget = min(point_limit // 8, 2048)
    priority = np.empty((0, 3), dtype=float)
    if curvature_budget and len(faces):
        flat_vertices = faces.reshape(-1)
        face_normals = np.repeat(normals, 3, axis=0)
        normal_sum = np.zeros((len(vertices), 3), dtype=float)
        normal_count = np.zeros(len(vertices), dtype=np.int32)
        np.add.at(normal_sum, flat_vertices, face_normals)
        np.add.at(normal_count, flat_vertices, 1)
        mean_norm = normal_sum / np.maximum(normal_count[:, None], 1)
        mean_len = np.linalg.norm(mean_norm, axis=1)
        # 1-|mean normal| is a fast proxy for angular variation/curvature.
        curvature = 1.0 - np.clip(mean_len, 0.0, 1.0)
        threshold = max(0.0, 1.0 - math.cos(math.radians(float(corner_angle_degrees))))
        # Boundary vertices are always geometric corners for sampling purposes
        # even when a single adjacent face gives them zero normal disagreement.
        edge_rows = np.sort(np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
        unique_edges, edge_counts = np.unique(edge_rows, axis=0, return_counts=True)
        boundary_vertices = np.unique(unique_edges[edge_counts == 1].reshape(-1)) if len(unique_edges) else np.asarray([], dtype=int)
        curvature_vertices = np.flatnonzero(curvature >= threshold)
        candidates = np.unique(np.concatenate([boundary_vertices, curvature_vertices]))
        if len(candidates):
            take = min(curvature_budget, len(candidates))
            # Boundary vertices receive a small deterministic boost so sharp
            # mesh silhouettes survive the bounded point budget.
            score = curvature[candidates] + np.isin(candidates, boundary_vertices).astype(float)
            order = candidates[np.argpartition(score, -take)[-take:]]
            order = order[np.argsort(score[np.searchsorted(candidates, order)])[::-1]]
            priority = vertices[order]

    remaining = point_limit - len(priority)
    if remaining <= 0:
        return np.asarray(priority[:point_limit], dtype=float)
    probabilities = areas / max(total_area, 1e-15)
    rng = np.random.default_rng(7919 + int(round(float(spacing_mm) * 1000)))
    # Oversample slightly, then quantize/deduplicate in one vectorized pass.
    draw_count = max(remaining, int(remaining * 1.12))
    face_indexes = rng.choice(len(triangles), size=draw_count, replace=True, p=probabilities)
    selected = triangles[face_indexes]
    r1 = np.sqrt(rng.random(draw_count))
    r2 = rng.random(draw_count)
    sampled = ((1.0-r1)[:,None]*selected[:,0] +
               (r1*(1.0-r2))[:,None]*selected[:,1] +
               (r1*r2)[:,None]*selected[:,2])
    spacing_m = max(float(spacing_mm) * 0.001, 1e-6)
    quantum = max(spacing_m * 0.20, 1e-7)
    keys = np.round(sampled / quantum).astype(np.int64)
    _, unique_index = np.unique(keys, axis=0, return_index=True)
    sampled = sampled[np.sort(unique_index)]
    if len(sampled) < remaining:
        # No expensive rejection loop: fill the rare shortfall with another
        # vectorized batch and allow very close points rather than stalling.
        short = remaining - len(sampled)
        fi = rng.choice(len(triangles), size=short, replace=True, p=probabilities)
        tri = triangles[fi]
        a = np.sqrt(rng.random(short)); b = rng.random(short)
        extra = ((1-a)[:,None]*tri[:,0] + (a*(1-b))[:,None]*tri[:,1] + (a*b)[:,None]*tri[:,2])
        sampled = np.vstack([sampled, extra])
    result = np.vstack([priority, sampled[:remaining]]) if len(priority) else sampled[:remaining]
    return np.asarray(result[:point_limit], dtype=float)


def _world_points(
    local: np.ndarray, geom_id: int, data: Any, *, out: np.ndarray | None = None,
) -> np.ndarray:
    """Transform local samples, optionally reusing a caller-owned output buffer."""
    local_points = np.asarray(local, dtype=float).reshape(-1, 3)
    if out is None:
        if not len(local_points):
            return local_points
        position = np.asarray(data.geom_xpos[geom_id], dtype=float)
        rotation = np.asarray(data.geom_xmat[geom_id], dtype=float).reshape(3, 3)
        return local_points @ rotation.T + position
    if out.shape != local_points.shape:
        raise ValueError("world-point output buffer shape does not match local points")
    if not len(local_points):
        return out
    position = np.asarray(data.geom_xpos[geom_id], dtype=float)
    rotation = np.asarray(data.geom_xmat[geom_id], dtype=float).reshape(3, 3)
    np.matmul(local_points, rotation.T, out=out)
    out += position
    return out


def _nearest_points(points_a: Any, points_b: Any) -> tuple[float, np.ndarray | None]:
    """Exact sampled-point nearest pair shared by Viewer and offline export.

    SciPy remains optional.  The NumPy fallback extends the project's former
    chunked exact search, but uses a bounded N x M squared-distance matrix
    instead of allocating an N x M x 3 broadcast temporary.
    """
    a = np.asarray(points_a, dtype=float).reshape(-1, 3)
    b = np.asarray(points_b, dtype=float).reshape(-1, 3)
    if not len(a) or not len(b):
        return float("inf"), None
    try:
        from scipy.spatial import cKDTree
        if len(a) <= len(b):
            tree = cKDTree(a); distances, indexes = tree.query(b, k=1)
            pos = int(np.argmin(distances)); pa = a[int(indexes[pos])]; pb = b[pos]
            distance = float(distances[pos])
        else:
            tree = cKDTree(b); distances, indexes = tree.query(a, k=1)
            pos = int(np.argmin(distances)); pa = a[pos]; pb = b[int(indexes[pos])]
            distance = float(distances[pos])
        return distance, np.concatenate([pa, pb])
    except ImportError:
        pass

    # Client V0.3.2 intentionally requires only NumPy + MuJoCo, so keep this
    # exact fallback fast without adding SciPy as a new runtime dependency.
    origin = b[0]
    centered_b = b - origin
    b_squared = np.einsum("ij,ij->i", centered_b, centered_b)
    matrix_elements = max(1, (8 * 1024 * 1024) // np.dtype(float).itemsize)
    chunk_rows = max(1, min(1024, matrix_elements // max(len(b), 1)))
    best_squared = float("inf")
    best_a_index = best_b_index = 0
    eps = np.finfo(float).eps
    for start in range(0, len(a), chunk_rows):
        chunk = a[start:start + chunk_rows]
        centered_a = chunk - origin
        a_squared = np.einsum("ij,ij->i", centered_a, centered_a)
        squared = centered_a @ centered_b.T
        squared *= -2.0
        squared += a_squared[:, None]
        squared += b_squared[None, :]
        np.maximum(squared, 0.0, out=squared)

        approximate_min = float(np.min(squared))
        scale = max(
            float(np.max(a_squared, initial=0.0)),
            float(np.max(b_squared, initial=0.0)),
            abs(approximate_min),
            np.finfo(float).tiny,
        )
        candidate_flat = np.flatnonzero(squared <= approximate_min + 32.0 * eps * scale)
        rows, columns = np.divmod(candidate_flat, len(b))
        deltas = chunk[rows] - b[columns]
        exact_squared = np.einsum("ij,ij->i", deltas, deltas)
        candidate_pos = int(np.argmin(exact_squared))
        value = float(exact_squared[candidate_pos])
        if value < best_squared:
            best_squared = value
            best_a_index = start + int(rows[candidate_pos])
            best_b_index = int(columns[candidate_pos])
    return math.sqrt(best_squared), np.concatenate([a[best_a_index], b[best_b_index]])


def _transform_between_geoms(
    local: np.ndarray, source_geom: int, target_geom: int, data: Any,
    *, out: np.ndarray,
) -> np.ndarray:
    """Transform source-geom local points directly into target-geom coordinates."""
    source_rotation = np.asarray(data.geom_xmat[source_geom], dtype=float).reshape(3, 3)
    target_rotation = np.asarray(data.geom_xmat[target_geom], dtype=float).reshape(3, 3)
    relative_rotation = source_rotation.T @ target_rotation
    relative_translation = (
        np.asarray(data.geom_xpos[source_geom], dtype=float)
        - np.asarray(data.geom_xpos[target_geom], dtype=float)
    ) @ target_rotation
    np.matmul(local, relative_rotation, out=out)
    out += relative_translation
    return out


def _point_in_world(local: np.ndarray, geom_id: int, data: Any) -> np.ndarray:
    rotation = np.asarray(data.geom_xmat[geom_id], dtype=float).reshape(3, 3)
    return np.asarray(local, dtype=float) @ rotation.T + np.asarray(data.geom_xpos[geom_id], dtype=float)


def _representative_realtime_points(points: np.ndarray, limit: int) -> np.ndarray:
    """Return a deterministic, bounded surface subset for low-latency display.

    Mesh sampling stores curvature/boundary candidates first, followed by
    area-distributed samples. Keep part of that priority prefix and stratify
    the remaining indices so a small realtime budget still covers the surface.
    """
    source = np.asarray(points, dtype=float).reshape(-1, 3)
    budget = min(max(int(limit), 1), len(source))
    if budget >= len(source):
        return source
    priority_count = min(256, max(1, budget // 4), len(source))
    priority = np.arange(priority_count, dtype=int)
    remaining = budget - priority_count
    if remaining <= 0 or priority_count >= len(source):
        return source[priority]
    distributed = np.linspace(priority_count, len(source) - 1, remaining, dtype=int)
    indexes = np.unique(np.concatenate([priority, distributed]))
    if len(indexes) < budget:
        missing = np.setdiff1d(np.arange(len(source), dtype=int), indexes, assume_unique=True)
        indexes = np.concatenate([indexes, missing[:budget - len(indexes)]])
    return np.ascontiguousarray(source[indexes[:budget]])


def _make_local_kdtree_runtime(
    pair: dict[str, Any], *, local_indexes: dict[int, dict[str, Any]] | None = None,
    geometry_index_pool: dict[tuple[Any, ...], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Share read-only geom-local KD trees, never share query/output buffers.

    Offline trajectory workers are each given their own runtime, but their
    sampled points and KD indexes depend only on the frozen scene.  Construct
    those trees once and reuse them across worker threads.
    """
    if local_indexes is None:
        from scipy.spatial import cKDTree

        samples = pair.get("samples", {})
        indexes: dict[int, dict[str, Any]] = {}
        for geom_id in dict.fromkeys([*pair.get("group_a", ()), *pair.get("group_b", ())]):
            # A geom identity alone is insufficient: spacing/point budget/corner
            # angle determine the exact sampled-surface set.
            pool_key = (int(geom_id), *pair.get("_distance_sampling_signature", (
                float(pair.get("animation_spacing_mm", 2.0)),
                int(pair.get("max_points_per_object", 400)), 25.0)), "sampled_surface_v1")
            if geometry_index_pool is not None and pool_key in geometry_index_pool:
                indexes[int(geom_id)] = geometry_index_pool[pool_key]
                continue
            points = np.asarray(samples.get(geom_id, np.empty((0, 3))), dtype=float).reshape(-1, 3)
            if geometry_index_pool is not None:
                points.setflags(write=False)  # shared only as an immutable cKDTree input
            # Immutable enclosing spheres enable exact broad-phase rejection
            # without reducing the Viewer surface-sample set (V2.16.8).
            center = (np.min(points, axis=0) + np.max(points, axis=0)) * 0.5 if len(points) else np.zeros(3)
            radius = float(np.max(np.linalg.norm(points - center, axis=1))) if len(points) else 0.0
            if geometry_index_pool is not None:
                center.setflags(write=False)
            indexes[int(geom_id)] = {
                "points": points,
                "tree": cKDTree(points, compact_nodes=True, balanced_tree=True) if len(points) else None,
                "bounds_center": center, "bounds_radius": radius,
            }
            if geometry_index_pool is not None:
                geometry_index_pool[pool_key] = indexes[int(geom_id)]
    else:
        indexes = local_indexes

    search_specs: list[dict[str, Any]] = []
    for geom_a in pair.get("group_a", ()):
        points_a = indexes[int(geom_a)]["points"]
        for geom_b in pair.get("group_b", ()):
            points_b = indexes[int(geom_b)]["points"]
            if not len(points_a) or not len(points_b):
                continue
            if len(points_a) <= len(points_b):
                search_specs.append({
                    "source_side": "a", "source_geom": int(geom_a), "target_geom": int(geom_b),
                    "source_points": points_a, "target_points": points_b,
                    "target_tree": indexes[int(geom_b)]["tree"], "query": np.empty_like(points_a),
                    "source_center": indexes[int(geom_a)].get("bounds_center"),
                    "target_center": indexes[int(geom_b)].get("bounds_center"),
                    "source_radius": indexes[int(geom_a)].get("bounds_radius", float("inf")),
                    "target_radius": indexes[int(geom_b)].get("bounds_radius", float("inf")),
                })
            else:
                search_specs.append({
                    "source_side": "b", "source_geom": int(geom_b), "target_geom": int(geom_a),
                    "source_points": points_b, "target_points": points_a,
                    "target_tree": indexes[int(geom_a)]["tree"], "query": np.empty_like(points_b),
                    "source_center": indexes[int(geom_b)].get("bounds_center"),
                    "target_center": indexes[int(geom_a)].get("bounds_center"),
                    "source_radius": indexes[int(geom_b)].get("bounds_radius", float("inf")),
                    "target_radius": indexes[int(geom_a)].get("bounds_radius", float("inf")),
                })

    total_source_points = sum(len(search["source_points"]) for search in search_specs)
    pair_budget = max(512, int(pair.get("_distance_query_budget", 4096)))
    minimum_per_search = min(64, max(1, pair_budget // max(1, len(search_specs))))
    proportional_budget = max(0, pair_budget - minimum_per_search * len(search_specs))
    searches: list[dict[str, Any]] = []
    for search in search_specs:
        full_source = search["source_points"]
        proportional = int(
            proportional_budget * len(full_source) / max(total_source_points, 1)
        )
        realtime_limit = min(len(full_source), minimum_per_search + proportional)
        realtime_source = _representative_realtime_points(full_source, realtime_limit)
        search["realtime_source_points"] = realtime_source
        search["realtime_query"] = np.empty_like(realtime_source)
        searches.append(search)

    # Offline curve jobs need the exact nearest-point distance and its segment,
    # not the additional thousands of world-space scatter points used by Viewer.
    # Keep the normal display buffers untouched for interactive Viewer paths.
    display_views: dict[str, list[tuple[int, np.ndarray, np.ndarray]]] = {"a": [], "b": []}
    display_buffers: dict[str, np.ndarray] = {
        "a": np.empty((0, 3), dtype=float), "b": np.empty((0, 3), dtype=float),
    }
    if not pair.get("_distance_skip_display_points", False):
        for side, group in (("a", pair.get("group_a", ())), ("b", pair.get("group_b", ()))):
            per_geom = max(1, 2500 // max(len(group), 1))
            selected: list[tuple[int, np.ndarray]] = []
            for geom_id in group:
                raw = indexes[int(geom_id)]["points"]
                step = max(1, int(math.ceil(len(raw) / per_geom)))
                selected.append((int(geom_id), raw[::step][:per_geom]))
            buffer = np.empty((sum(len(points) for _, points in selected), 3), dtype=float)
            offset = 0
            for geom_id, local in selected:
                target = buffer[offset:offset + len(local)]
                display_views[side].append((geom_id, local, target))
                offset += len(local)
            display_buffers[side] = buffer
    return {
        "geom_ids": tuple(dict.fromkeys([*pair.get("group_a", ()), *pair.get("group_b", ())])),
        "last_pose": None,
        "last_measurement": None,
        "last_low_latency": None,
        "local_indexes": indexes, "local_searches": searches,
        "realtime_query_points": sum(len(search["realtime_source_points"]) for search in searches),
        "exact_query_points": total_source_points,
        "points_a": display_buffers["a"], "points_b": display_buffers["b"],
        "display_views_a": display_views["a"], "display_views_b": display_views["b"],
    }


def _nearest_points_local_kd(
    data: Any, searches: list[dict[str, Any]], *, low_latency: bool = False,
) -> tuple[float, np.ndarray | None]:
    """Nearest sampled pair using fixed trees and exact or bounded queries."""
    best_distance = float("inf")
    best_fromto: np.ndarray | None = None
    # Sort geom combinations by a *conservative* lower bound of the actual
    # sampled surface distance. Only a bound strictly above the best answer is
    # omitted; no point is sampled less densely, so this is still exact KD.
    # A one-geom pair takes the original direct path without broad-phase cost.
    candidates = list(enumerate(searches))
    if len(searches) > 1 and all(search.get("source_center") is not None and
                                    search.get("target_center") is not None for search in searches):
        world_centers = {}
        def world_center(gid, local_center):
            key = int(gid)
            if key not in world_centers:
                rotation = np.asarray(data.geom_xmat[key], dtype=float).reshape(3, 3)
                world_centers[key] = local_center @ rotation.T + data.geom_xpos[key]
            return world_centers[key]
        bounds = []
        for index, search in candidates:
            a = world_center(search["source_geom"], search["source_center"])
            b = world_center(search["target_geom"], search["target_center"])
            # Conservative subtraction includes transform/center rounding.
            # Scale the slack with world coordinates: a fixed 1e-12 is not
            # sufficient for models positioned very far from the origin.
            magnitude = max(1.0, float(np.max(np.abs(a))), float(np.max(np.abs(b))))
            slack = max(1e-12, 32.0 * np.finfo(float).eps * magnitude)
            lower = max(0.0, float(np.linalg.norm(a-b)) - search["source_radius"]
                        - search["target_radius"] - slack)
            bounds.append((lower, index, search))
        bounds.sort(key=lambda item: (item[0], item[1]))
    else:
        bounds = [(0.0, index, search) for index, search in candidates]
    best_index = len(searches)
    for lower, search_index, search in bounds:
        if lower > best_distance:
            continue
        source_points = (
            search["realtime_source_points"] if low_latency else search["source_points"]
        )
        query_buffer = search["realtime_query"] if low_latency else search["query"]
        query = _transform_between_geoms(
            source_points, search["source_geom"], search["target_geom"], data,
            out=query_buffer,
        )
        # An exact upper bound lets cKDTree eliminate far nodes too. In equal
        # ties preserve the original geom-combination order, including the
        # closest segment returned by the pre-2.16.8 implementation.
        bound = (best_distance + 1e-12 if search_index < best_index else best_distance)
        # No unbounded threadpool: workers=1 remains vital on Windows.
        distances, indexes = search["target_tree"].query(
            query, k=1, workers=1, distance_upper_bound=bound,
        )
        position = int(np.argmin(distances))
        distance = float(distances[position])
        if not math.isfinite(distance) or distance > best_distance or (distance == best_distance and search_index >= best_index):
            continue
        source_local = source_points[position]
        target_local = search["target_points"][int(indexes[position])]
        source_world = _point_in_world(source_local, search["source_geom"], data)
        target_world = _point_in_world(target_local, search["target_geom"], data)
        if search["source_side"] == "a":
            best_fromto = np.concatenate([source_world, target_world])
        else:
            best_fromto = np.concatenate([target_world, source_world])
        best_distance = distance
        best_index = search_index
    return best_distance, best_fromto


def _reserved_distance_site_group(mujoco: Any, model: Any) -> int | None:
    """Return an unused site group for Studio runtime sampling sites, if one exists."""
    group_count = max(1, int(getattr(mujoco, "mjNGROUP", 6)))
    used = {int(value) for value in np.asarray(getattr(model, "site_group", ()), dtype=int).reshape(-1)}
    # Prefer groups hidden by MuJoCo's default visualizer options (3+), then
    # fall back to any other unused group. If all groups are occupied we use
    # alpha-only visibility so existing model sites are never affected.
    order = [*range(group_count - 1, 2, -1), *range(min(2, group_count - 1), -1, -1)]
    return next((group for group in order if group not in used), None)


def _geom_samples_in_body_frame(mujoco: Any, model: Any, geom_id: int, local: np.ndarray) -> np.ndarray:
    """Convert compiled geom-local mesh samples to the owning body's local frame."""
    points = np.asarray(local, dtype=float).reshape(-1, 3)
    if not len(points):
        return points
    matrix = np.empty(9, dtype=float)
    mujoco.mju_quat2Mat(matrix, np.asarray(model.geom_quat[geom_id], dtype=float))
    rotation = matrix.reshape(3, 3)
    return points @ rotation.T + np.asarray(model.geom_pos[geom_id], dtype=float)


def _spec_body_for_geom(mujoco: Any, spec: Any, model: Any, geom_id: int) -> Any:
    body_id = int(model.geom_bodyid[geom_id])
    if body_id == 0:
        return spec.worldbody
    body_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
    body = spec.body(str(body_name)) if body_name else None
    if body is None:
        raise ValueError(f"distance_site_body_missing: geom={geom_id} body={body_name or body_id}")
    return body


def _bind_distance_site_ids(mujoco: Any, model: Any, pairs: list[dict[str, Any]]) -> int:
    """Resolve runtime site IDs after the augmented MjSpec has been compiled."""
    bound = 0
    for pair in pairs:
        names_a = list(pair.get("site_names_a", ()))
        names_b = list(pair.get("site_names_b", ()))
        if not names_a or not names_b:
            pair["site_backend"] = False
            continue
        ids_a = np.asarray([
            int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, name)) for name in names_a
        ], dtype=int)
        ids_b = np.asarray([
            int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, name)) for name in names_b
        ], dtype=int)
        if np.any(ids_a < 0) or np.any(ids_b < 0):
            pair["site_backend"] = False
            continue
        pair["site_ids_a"] = ids_a
        pair["site_ids_b"] = ids_b
        pair["site_ids_all"] = np.concatenate([ids_a, ids_b])
        pair["site_backend"] = True
        pair["_site_visible"] = None
        bound += len(ids_a) + len(ids_b)
    return bound


def _set_distance_site_visibility(model: Any, pair: dict[str, Any], visible: bool) -> None:
    """Change injected-site alpha only when a pair's effective visibility changes."""
    if not pair.get("site_backend"):
        return
    desired = bool(visible)
    if pair.get("_site_visible") is desired:
        return
    ids = np.asarray(pair.get("site_ids_all", ()), dtype=int)
    if len(ids):
        model.site_rgba[ids, 3] = _DISTANCE_SITE_ALPHA if desired else 0.0
    pair["_site_visible"] = desired


def _set_viewer_site_group(viewer: Any, group: int | None, visible: bool) -> None:
    """Toggle only the reserved Studio site group; leave user groups untouched."""
    if group is None:
        return
    lock = getattr(viewer, "lock", None)
    if callable(lock):
        with lock():
            viewer.opt.sitegroup[int(group)] = int(bool(visible))
    else:
        viewer.opt.sitegroup[int(group)] = int(bool(visible))


def _add_points(
    mujoco: Any, scene: Any, points: np.ndarray, rgba: tuple[float, ...], radius: float = 0.00125,
) -> None:
    if not len(points) or scene.ngeom >= scene.maxgeom:
        return
    draw_points = np.asarray(points, dtype=np.float32)
    size = np.asarray([max(radius, 0.0001), 0.0, 0.0], dtype=np.float32)
    rotation = np.eye(3, dtype=np.float32).reshape(-1)
    color = np.asarray(rgba, dtype=np.float32)
    for point in draw_points:
        if scene.ngeom >= scene.maxgeom:
            return
        geom = scene.geoms[scene.ngeom]
        mujoco.mjv_initGeom(geom, mujoco.mjtGeom.mjGEOM_SPHERE, size, point, rotation, color)
        scene.ngeom += 1


_DISTANCE_LINE_RGBA_NORMAL = (0.20, 0.90, 0.45, 1.0)


def _add_capsule(mujoco: Any, scene: Any, fromto: np.ndarray, collision: bool = False) -> None:
    if fromto is None or len(fromto) != 6 or scene.ngeom >= scene.maxgeom:
        return
    start, end = np.asarray(fromto[:3], dtype=float), np.asarray(fromto[3:], dtype=float)
    if not np.all(np.isfinite(fromto)) or np.linalg.norm(end - start) <= 1e-12:
        return
    width = 0.0021 if collision else 0.00115
    # V2.16.8: same vivid green as the standalone HTML overlay.
    color = (1.0, 0.08, 0.08, 1.0) if collision else _DISTANCE_LINE_RGBA_NORMAL
    geom = scene.geoms[scene.ngeom]
    mujoco.mjv_initGeom(
        geom, mujoco.mjtGeom.mjGEOM_CAPSULE,
        np.asarray([width, 0.0, 0.0], dtype=np.float32), np.zeros(3, dtype=np.float32),
        np.eye(3, dtype=np.float32).reshape(-1), np.asarray(color, dtype=np.float32),
    )
    mujoco.mjv_connector(
        geom, mujoco.mjtGeom.mjGEOM_CAPSULE, width,
        np.asarray(start, dtype=np.float64), np.asarray(end, dtype=np.float64),
    )
    scene.ngeom += 1


def _add_label(mujoco: Any, scene: Any, fromto: np.ndarray, text: str) -> None:
    if fromto is None or len(fromto) != 6 or scene.ngeom >= scene.maxgeom:
        return
    midpoint = (np.asarray(fromto[:3], dtype=float) + np.asarray(fromto[3:], dtype=float)) * 0.5
    midpoint[2] += 0.004
    geom = scene.geoms[scene.ngeom]
    try:
        mujoco.mjv_initGeom(
            geom, mujoco.mjtGeom.mjGEOM_LABEL, np.ones(3, dtype=np.float32),
            np.asarray(midpoint, dtype=np.float32), np.eye(3, dtype=np.float32).reshape(-1),
            np.asarray([1.0, 1.0, 0.88, 1.0], dtype=np.float32),
        )
        geom.label = str(text)
        scene.ngeom += 1
    except Exception:
        return


def _hex_rgba(value: str) -> tuple[float, float, float, float]:
    raw = str(value or "#018c94").strip().lstrip("#")
    try:
        if len(raw) == 6:
            return tuple(int(raw[index:index + 2], 16) / 255.0 for index in (0, 2, 4)) + (0.95,)
    except ValueError:
        pass
    return (0.004, 0.55, 0.58, 0.95)


def _append_trajectory_point(points: list[np.ndarray], point: np.ndarray, sample_hz: float, now: float) -> None:
    interval = 1.0 / max(float(sample_hz), 0.1)
    if points and now - float(points[-1][3]) < interval:
        return
    points.append(np.asarray([float(point[0]), float(point[1]), float(point[2]), now]))
    if len(points) > 12_000:
        del points[:len(points) - 12_000]


def _selected_centroid(
    model: Any, data: Any, geom_ids: list[int], geom_masses: dict[int, float] | None = None,
) -> np.ndarray | None:
    if not geom_ids:
        return None
    positions = np.asarray([data.geom_xpos[geom_id] for geom_id in geom_ids], dtype=float)
    weights = []
    counts: dict[int, int] = {}
    for geom_id in geom_ids:
        body_id = int(model.geom_bodyid[geom_id])
        counts[body_id] = counts.get(body_id, 0) + 1
    for geom_id in geom_ids:
        body_id = int(model.geom_bodyid[geom_id])
        configured_mass = (geom_masses or {}).get(geom_id)
        if configured_mass is not None and configured_mass > 0:
            weights.append(configured_mass)
        else:
            body_mass = max(float(model.body_mass[body_id]), 1e-9)
            weights.append(body_mass / counts[body_id])
    return np.average(positions, axis=0, weights=np.asarray(weights, dtype=float))


def _build_distance_pairs(
    mujoco: Any, model: Any, payload: dict[str, Any], *, spec: Any | None = None,
    site_group: int | None = None, progress: Any | None = None,
    geometry_sample_pool: dict[tuple[Any, ...], np.ndarray] | None = None,
) -> list[dict[str, Any]]:
    """Create sampled distance pairs and optionally inject samples as MjSpec sites."""
    manifest = payload.get("mesh_manifest", {})
    filename_geoms: dict[str, list[int]] = {}
    for filename, geom_names in manifest.items():
        for name in geom_names:
            geom_id = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, str(name)))
            if geom_id >= 0:
                filename_geoms.setdefault(str(filename), []).append(geom_id)
    runtime: list[dict[str, Any]] = []
    sampling = payload.get("distance_sampling", {})
    point_limit = max(16, int(sampling.get("max_points_per_object", 400)))
    corner_angle = float(sampling.get("corner_angle_degrees", 25.0))
    all_pairs = list(payload.get("distance_pairs", []))
    total_objects = 0
    prepared_pairs: list[tuple[dict[str, Any], list[int], list[int]]] = []
    for pair in all_pairs:
        group_a = [gid for name in pair.get("objects_a", []) for gid in filename_geoms.get(str(name), [])]
        group_b = [gid for name in pair.get("objects_b", []) for gid in filename_geoms.get(str(name), [])]
        if group_a and group_b:
            prepared_pairs.append((pair, group_a, group_b))
            total_objects += len(set(group_a + group_b))
    completed_objects = 0
    sampled_total = 0
    # Several distance pairs may reference the same model geometry with the
    # same surface-sampling settings.  Sampling depends only on these inputs;
    # share the immutable point cloud within this one runtime build instead of
    # repeating the most expensive mesh traversal for every pair.
    sampled_geometries: dict[tuple[Any, ...], np.ndarray] = (geometry_sample_pool
        if geometry_sample_pool is not None else {})
    for pair_index, (pair, group_a, group_b) in enumerate(prepared_pairs):
        spacing = max(float(pair.get("animation_spacing_mm", 2.0)), 0.1)
        samples: dict[int, np.ndarray] = {}
        for gid in dict.fromkeys(group_a + group_b):
            sample_key = (int(gid), spacing, point_limit, corner_angle, "sampled_surface_v1")
            if sample_key not in sampled_geometries:
                sampled_geometries[sample_key] = _mesh_surface_points(
                    model, gid, spacing, point_limit, corner_angle,
                )
            samples[gid] = sampled_geometries[sample_key]
            completed_objects += 1
            sampled_total += len(samples[gid])
            if callable(progress):
                progress(completed_objects, max(total_objects, 1), sampled_total)
        item: dict[str, Any] = {
            # The ProjectSpec ID is the only valid Lab/UDP identity.  Do not
            # synthesize a new ID or derive one from display names/order.
            "id": str(pair.get("id", "")),
            "name": str(pair.get("name", "distance")), "group_a": group_a, "group_b": group_b,
            "samples": samples, "distmax": max(float(pair.get("distmax_m", 0.1)), 0.001),
            "animation_spacing_mm": spacing,
            "max_points_per_object": point_limit,
            "_distance_sampling_signature": (spacing, point_limit, corner_angle),
            "site_group": site_group,
            "site_backend": False,
        }
        # V2.5.2: MjSpec compilation becomes super-linear with many injected sites.
        # For large point sets keep the vectorized legacy buffer backend instead of
        # creating 10k+ site objects; this preserves distance semantics and avoids
        # the historical >30 minute / apparent-hang path.
        total_sample_count = sum(len(points) for points in samples.values())
        use_site_backend = spec is not None and total_sample_count <= 4000
        item["sample_count"] = total_sample_count
        item["site_backend_skipped_for_scale"] = bool(spec is not None and not use_site_backend)
        if use_site_backend:
            names: dict[str, list[str]] = {"a": [], "b": []}
            for side, geom_ids, color in (
                ("a", group_a, _DISTANCE_SITE_COLOR_A),
                ("b", group_b, _DISTANCE_SITE_COLOR_B),
            ):
                for geom_id in geom_ids:
                    body = _spec_body_for_geom(mujoco, spec, model, geom_id)
                    body_points = _geom_samples_in_body_frame(mujoco, model, geom_id, samples.get(geom_id, ()))
                    for sample_index, point in enumerate(body_points):
                        name = f"{_DISTANCE_SITE_PREFIX}{pair_index}_{side}_{geom_id}_{sample_index}"
                        if spec.site(name) is not None:
                            raise ValueError(f"distance_site_name_conflict: {name}")
                        body.add_site(
                            name=name,
                            pos=np.asarray(point, dtype=float).tolist(),
                            type=mujoco.mjtGeom.mjGEOM_SPHERE,
                            size=[_DISTANCE_SITE_RADIUS_M],
                            group=int(site_group if site_group is not None else 0),
                            rgba=[*color, 0.0],
                        )
                        names[side].append(name)
            item["site_names_a"] = names["a"]
            item["site_names_b"] = names["b"]
        runtime.append(item)
    return runtime


def _clone_distance_pair(
    source: dict[str, Any], *, share_trees: bool = False,
    geometry_index_pool: dict[tuple[Any, ...], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Share surface samples and optionally KD trees; isolate every mutable buffer.

    `share_trees` is used only by offline parallel evaluation after building an
    immutable source runtime. Interactive Viewer callers retain their existing
    independent runtime construction by default.
    """
    item = dict(source)
    previous = item.pop("_distance_runtime", None) if share_trees else None
    local_indexes = previous.get("local_indexes") if isinstance(previous, dict) else None
    if not item.get("site_backend"):
        item["_distance_runtime"] = _make_local_kdtree_runtime(
            item, local_indexes=local_indexes, geometry_index_pool=geometry_index_pool,
        )
    return item


def _measure_pair(
    mujoco: Any, model: Any, data: Any, pair: dict[str, Any],
) -> tuple[float, np.ndarray | None]:
    # ``pair`` is process-local. Site-backed pairs avoid all per-frame point
    # transforms; legacy pairs retain the V2.4.5.x buffer path for MuJoCo 3.1.
    runtime = pair.get("_distance_runtime")
    if not isinstance(runtime, dict):
        runtime = {
            "geom_ids": tuple(dict.fromkeys([*pair.get("group_a", ()), *pair.get("group_b", ())])),
            "last_pose": None,
            "last_measurement": None,
        }
        if not pair.get("site_backend"):
            runtime.update(_make_local_kdtree_runtime(pair))
        pair["_distance_runtime"] = runtime

    last_pose = runtime.get("last_pose")
    last_measurement = runtime.get("last_measurement")
    low_latency = bool(pair.get("_distance_low_latency", False))
    pose_matches = (
        last_pose is not None and last_measurement is not None
        and runtime.get("last_low_latency") is low_latency
        and hasattr(data, "geom_xpos") and hasattr(data, "geom_xmat")
    )
    if pose_matches:
        for index, geom_id in enumerate(runtime["geom_ids"]):
            if (
                not np.array_equal(last_pose[index, :3], data.geom_xpos[geom_id])
                or not np.array_equal(
                    last_pose[index, 3:], np.asarray(data.geom_xmat[geom_id]).reshape(-1),
                )
            ):
                pose_matches = False
                break
    if pose_matches:
        return last_measurement

    if pair.get("site_backend"):
        ids_a = np.asarray(pair.get("site_ids_a", ()), dtype=int)
        ids_b = np.asarray(pair.get("site_ids_b", ()), dtype=int)
        points_a = np.asarray(data.site_xpos[ids_a], dtype=float) if len(ids_a) else np.empty((0, 3))
        points_b = np.asarray(data.site_xpos[ids_b], dtype=float) if len(ids_b) else np.empty((0, 3))
    else:
        if not pair.get("_distance_skip_display_points", False):
            for key in ("display_views_a", "display_views_b"):
                for geom_id, local, target in runtime[key]:
                    _world_points(local, geom_id, data, out=target)
        points_a = runtime["points_a"]
        points_b = runtime["points_b"]

    if not pair.get("site_backend") and runtime.get("local_searches"):
        measured, fromto = _nearest_points_local_kd(
            data, runtime["local_searches"], low_latency=low_latency,
        )
    elif len(points_a) and len(points_b):
        measured, fromto = _nearest_points(points_a, points_b)
    else:
        native_best = float("inf")
        native_fromto: np.ndarray | None = None
        for geom_a in pair["group_a"]:
            for geom_b in pair["group_b"]:
                fromto_native = np.zeros(6, dtype=float)
                try:
                    value = float(
                        mujoco.mj_geomDistance(
                            model, data, geom_a, geom_b, pair["distmax"], fromto_native,
                        )
                    )
                except Exception:
                    continue
                if value < native_best:
                    native_best, native_fromto = value, fromto_native.copy()
        if math.isfinite(native_best):
            measured, fromto = max(native_best, 0.0), native_fromto
        else:
            measured, fromto = float("inf"), None

    geom_ids = runtime["geom_ids"]
    if geom_ids and hasattr(data, "geom_xpos") and hasattr(data, "geom_xmat"):
        pose = runtime.get("last_pose")
        if pose is None or pose.shape != (len(geom_ids), 12):
            pose = np.empty((len(geom_ids), 12), dtype=float)
            runtime["last_pose"] = pose
        for index, geom_id in enumerate(geom_ids):
            pose[index, :3] = data.geom_xpos[geom_id]
            pose[index, 3:] = np.asarray(data.geom_xmat[geom_id], dtype=float).reshape(-1)
    else:
        runtime["last_pose"] = None
    runtime["last_measurement"] = (measured, fromto)
    runtime["last_low_latency"] = low_latency
    return measured, fromto


def _drive_ranges(
    drives: list[dict[str, Any]], segments: list[dict[str, Any]], start: float, end: float,
) -> dict[str, tuple[float, float]]:
    times = np.linspace(start, end, 241) if end > start else np.asarray([start])
    values: dict[str, list[float]] = {str(drive.get("id", "")): [0.0] for drive in drives}
    for sample_time in times:
        for drive_id, value in drive_positions(segments, float(sample_time)).items():
            values.setdefault(drive_id, [0.0]).append(float(value))
    result = {}
    for drive_id, samples in values.items():
        low, high = min(samples), max(samples)
        margin = max((high - low) * 0.05, 1.0)
        result[drive_id] = (low - margin, high + margin)
    return result


def _session_defaults(start_time: float, end_time: float, playback_speed: float) -> dict[str, Any]:
    """Return a fresh, isolated controller state for every viewer process."""
    zero_time = min(max(0.0, float(start_time)), float(end_time))
    return {
        "time_s": zero_time,
        "playing": False,
        "direction": 1.0,
        "speed": min(max(float(playback_speed), 0.1), 2.0),
        "show_scatter": False,
        "show_distance_lines": True,
        "show_distance_labels": True,
        "adaptive_display": True,
        "adaptive_threshold_mm": 25.0,
        "motor_mode": False,
        "motor_values": {},
        "decoupled_drive_ids": [],
        "gantt_enabled": False,
        "orthographic_view": True,
        "trajectory": {
            "expanded": False,
            "selected_meshes": [],
            "recording": False,
            "sample_hz": 20.0,
            "point_size": 1.0,
            "color": "#018c94",
            "clear_revision": 0,
            "centroid_probe_revision": 0,
        },
    }


def _cache_value(target: dict[str, Any], path: str, value: Any) -> None:
    """Assign a dotted viewer path in the process cache without backend writes."""
    parts = [part for part in str(path).split(".") if part]
    cursor = target
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            child = {}
            cursor[part] = child
        cursor = child
    if parts:
        cursor[parts[-1]] = value


CAMERA_DEFAULTS: dict[str, dict[str, list[float]]] = {
    "front_view": {"pos": [0.8, -1.0, 0.6], "direction": [0.0, 1.0, 0.0]},
    "side_view": {"pos": [1.5, -0.405, 0.8], "direction": [-1.0, 0.0, 0.0]},
    "pov_view": {"pos": [1.4, -0.405, 0.97], "direction": [-0.898, 0.0, -0.439]},
    "initial_free_view": {"pos": [0.8, -1.5, 0.6], "direction": [0.0, 1.0, 0.0]},
}


def _camera_settings(raw: Any) -> dict[str, dict[str, list[float]]]:
    """Decode the four legacy camera configurations from one compatible field."""
    result = json.loads(json.dumps(CAMERA_DEFAULTS))
    text = str(raw or "").strip()
    if not text:
        return result
    try:
        decoded = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        # Backward compatibility with the former px,py,pz,dx,dy,dz (mm) field.
        try:
            values = [float(value) for value in text.replace("；", ",").replace(";", ",").split(",") if value.strip()]
        except ValueError:
            return result
        if len(values) == 6:
            result["initial_free_view"] = {
                "pos": [value * 0.001 for value in values[:3]],
                "direction": values[3:],
            }
        return result
    if not isinstance(decoded, dict):
        return result
    cameras = decoded.get("cameras", decoded)
    if not isinstance(cameras, dict):
        return result
    for name in result:
        item = cameras.get(name)
        if not isinstance(item, dict):
            continue
        try:
            position = [float(value) for value in item.get("pos", [])]
            direction = [float(value) for value in item.get("direction", [])]
        except (TypeError, ValueError):
            continue
        if len(position) == 3 and len(direction) == 3 and np.linalg.norm(direction) > 1e-12:
            result[name] = {"pos": position, "direction": direction}
    return result


def _write_legacy_gantt_cache(
    segments: list[dict[str, Any]],
    drives: list[dict[str, Any]],
    start_time: float,
    end_time: float,
    cache_dir: Path,
    *,
    runtime_segments: list[dict[str, Any]] | None = None,
) -> tuple[Path, Path]:
    """Generate the PNG/JSON cache pair consumed by the legacy animation Gantt."""
    from PIL import Image, ImageDraw, ImageFont

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_png = cache_dir / "latest_gantt.png"
    cache_json = cache_dir / "latest_gantt.json"
    rows: dict[str, list[dict[str, Any]]] = {}
    drive_by_id = {str(item.get("id", "")): item for item in drives}
    for segment in segments:
        rows.setdefault(str(segment.get("drive_name", "drive")), []).append(segment)
    top_margin = 78
    bottom_margin = 38
    right_margin = 12
    bar_height = 19
    lane_gap = 4
    lane_height = bar_height + lane_gap
    row_gap = 5

    def assign_lanes(items: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int]]:
        lane_ends: list[float] = []
        assignments: list[tuple[dict[str, Any], int]] = []
        for item in sorted(items, key=lambda entry: (float(entry.get("start", 0.0)), float(entry.get("end", 0.0)))):
            start = float(item.get("start", 0.0))
            lane = next((index for index, lane_end in enumerate(lane_ends) if start >= lane_end), len(lane_ends))
            if lane == len(lane_ends):
                lane_ends.append(float(item.get("end", start)))
            else:
                lane_ends[lane] = float(item.get("end", start))
            assignments.append((item, lane))
        return assignments

    lane_rows = [(name, assign_lanes(items)) for name, items in rows.items()]
    row_heights = [((max((lane for _, lane in assignments), default=0) + 1) * lane_height + row_gap) for _, assignments in lane_rows]
    content_height = sum(row_heights)
    height = max(180, top_margin + content_height + bottom_margin)
    def font(size: int, *, bold: bool = False):
        candidates = [
            "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
        return ImageFont.load_default()

    tick_font = font(13)
    row_font = font(25, bold=True)
    bar_font = font(12, bold=True)
    measure_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1), "#FBFCFD"))
    widest_name = max(
        (measure_draw.textbbox((0, 0), name, font=row_font)[2] for name in rows),
        default=0,
    )
    left_margin = max(10, int(math.ceil(widest_name)) + 10)
    chart_width = 960
    width = left_margin + chart_width + right_margin
    chart_right = left_margin + chart_width
    image = Image.new("RGBA", (width, height), "#FBFCFD")
    draw = ImageDraw.Draw(image)
    span = max(float(end_time) - float(start_time), 1e-12)
    tick_step = 0.5 if span <= 10.0 else 1.0
    axis_min = math.floor(float(start_time) / tick_step) * tick_step
    axis_max = math.ceil(float(end_time) / tick_step) * tick_step
    axis_span = max(tick_step, axis_max - axis_min)
    axis_y = top_margin - 26
    draw.line((left_margin, axis_y, chart_right, axis_y), fill="#94A2AC", width=1)
    tick_count = max(1, int(round(axis_span / tick_step)))
    for tick in range(tick_count + 1):
        value = axis_min + tick * tick_step
        ratio = (value - axis_min) / axis_span
        x = left_margin + (chart_right - left_margin) * ratio
        draw.line((x, top_margin - 4, x, top_margin + content_height), fill="#E7ECF1", width=1)
        draw.line((x, axis_y - 4, x, axis_y + 4), fill="#94A2AC", width=1)
        text = f"{value:.3f}".rstrip("0").rstrip(".")
        box = draw.textbbox((0, 0), text, font=tick_font)
        draw.text((x - (box[2] - box[0]) / 2, axis_y - 30), text, fill="#000000", font=tick_font)

    times = np.linspace(float(start_time), float(end_time), 241) if end_time > start_time else np.asarray([start_time])
    drive_series: dict[str, list[float]] = {str(item.get("id", "")): [] for item in drives}
    for sample_time in times:
        values = drive_positions(runtime_segments or segments, float(sample_time))
        for drive_id in drive_series:
            drive_series[drive_id].append(float(values.get(drive_id, 0.0)))

    metadata_rows = []
    current_y = top_margin
    for (drive_name, assignments), row_height in zip(lane_rows, row_heights):
        items = [item for item, _ in assignments]
        top = current_y
        bottom = top + row_height - row_gap
        center = (top + bottom) / 2.0
        label_box = draw.textbbox((0, 0), drive_name, font=row_font)
        draw.text((left_margin - (label_box[2] - label_box[0]) - 10, center - (label_box[3] - label_box[1]) / 2), drive_name, fill="#000000", font=row_font)
        lane_count = max((lane for _, lane in assignments), default=0) + 1
        for lane in range(lane_count):
            track_top = top + lane * lane_height
            draw.rounded_rectangle((left_margin, track_top, chart_right, track_top + bar_height), radius=5, fill="#F3F6F9", outline="#E4E9EE", width=1)
        for item, lane in assignments:
            left = left_margin + (chart_right - left_margin) * (float(item.get("start", axis_min)) - axis_min) / axis_span
            right = left_margin + (chart_right - left_margin) * (float(item.get("end", axis_min)) - axis_min) / axis_span
            right = max(right, left + 3)
            bar_top, bar_bottom = top + lane * lane_height, top + lane * lane_height + bar_height
            color = str(item.get("color", "") or "#018C94")
            draw.rounded_rectangle((left, bar_top, right, bar_bottom), radius=5, fill=color, outline="#35414A", width=1)
            time_text = f"{float(item.get('start', 0.0)):.2f}s → {float(item.get('end', 0.0)):.2f}s"
            unit = str(drive_by_id.get(str(item.get("drive_id", "")), {}).get("unit", "") or "").replace("deg", "°")
            travel_text = f"{float(item.get('travel_start', 0.0)):.2f}{unit} → {float(item.get('travel_end', 0.0)):.2f}{unit}"
            draw.text((left + 5, bar_top - 17), time_text, fill="#000000", font=bar_font)
            draw.text((left + 5, bar_bottom + 1), travel_text, fill="#000000", font=bar_font)
        drive_ids = list(dict.fromkeys(str(item.get("drive_id", "")) for item in items if str(item.get("drive_id", ""))))
        value_series = []
        for drive_id in drive_ids:
            drive = drive_by_id.get(drive_id, {})
            value_series.append({
                "name": str(drive.get("name", drive_name)),
                "unit": str(drive.get("unit", "") or ""),
                "times": [float(value) for value in times],
                "values": drive_series.get(drive_id, [0.0] * len(times)),
            })
        metadata_rows.append({
            "name": drive_name,
            "top": float(top),
            "bottom": float(bottom),
            "center": float(center),
            "segments": [
                {"start": float(item.get("start", 0.0)), "end": float(item.get("end", 0.0))}
                for item in items
            ],
            "value_series": value_series,
        })
        draw.line((left_margin, top + row_height - row_gap / 2, chart_right, top + row_height - row_gap / 2), fill="#EAEEF2", width=1)
        current_y += row_height
    if not rows:
        draw.text((width / 2 - 120, height / 2), "暂无驱动时序数据", fill="#20292F", font=row_font)
    metadata = {
        "format": "MUJOCO_XML_TOOL_GANTT_CACHE",
        "format_version": 1,
        "axis_min": float(axis_min),
        "axis_max": float(axis_max),
        "chart_left": float(left_margin),
        "chart_right": float(chart_right),
        "chart_top": float(top_margin),
        "chart_bottom": float(top_margin + content_height),
        "scene_width": float(width),
        "scene_height": float(height),
        "simulation_time_offset": 0.0,
        "rows": metadata_rows,
        "image_width": int(width),
        "image_height": int(height),
        "saved_at": float(time.time()),
    }
    png_handle = tempfile.NamedTemporaryFile(prefix=".latest_gantt_", suffix=".png", dir=cache_dir, delete=False)
    json_handle = tempfile.NamedTemporaryFile(prefix=".latest_gantt_", suffix=".json", dir=cache_dir, delete=False)
    png_temp, json_temp = Path(png_handle.name), Path(json_handle.name)
    png_handle.close(); json_handle.close()
    try:
        image.save(png_temp, "PNG")
        json_temp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        # V2.8.15: atomic-replace retry.  Same transient Windows share race
        # applies on exported PNG/JSON artifacts produced inside the viewer.
        _atomic_replace(png_temp, cache_png)
        _atomic_replace(json_temp, cache_json)
    finally:
        for path in (png_temp, json_temp):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    return cache_png, cache_json


def _attach_runtime_gantt_values(
    metadata: dict[str, Any], segments: list[dict[str, Any]], drives: list[dict[str, Any]],
    start_time: float, end_time: float, image_size: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Attach live interpolation series without modifying the exported cache."""
    result = dict(metadata)
    image_width = int(image_size[0]) if image_size else int(result.get("image_width", 0) or 0)
    image_height = int(image_size[1]) if image_size else int(result.get("image_height", 0) or 0)
    scene_width = max(float(result.get("scene_width", image_width) or image_width or 1), 1.0)
    scene_height = max(float(result.get("scene_height", image_height) or image_height or 1), 1.0)
    scale_x = image_width / scene_width if image_width else 1.0
    scale_y = image_height / scene_height if image_height else 1.0
    result["image_width"], result["image_height"] = image_width, image_height
    result.setdefault("axis_min", float(start_time))
    result.setdefault("axis_max", float(end_time))
    # Caches written by 2.3.7.5.2.2 contained only scene dimensions.  Recover
    # that exporter geometry so its PNG remains usable without re-exporting.
    result.setdefault("chart_left", min(215.0, scene_width * 0.35) * scale_x)
    result.setdefault("chart_right", max(float(result["chart_left"]) + 1.0, (scene_width - 220.0) * scale_x))
    result.setdefault("chart_top", 78.0 * scale_y)
    result.setdefault("chart_bottom", max(float(result["chart_top"]) + 1.0, (scene_height - 38.0) * scale_y))
    times = np.linspace(float(start_time), float(end_time), 241) if end_time > start_time else np.asarray([start_time])
    drive_by_id = {str(item.get("id", "")): item for item in drives}
    values_by_id = {drive_id: [] for drive_id in drive_by_id}
    for sample_time in times:
        positions = drive_positions(segments, float(sample_time))
        for drive_id in values_by_id:
            values_by_id[drive_id].append(float(positions.get(drive_id, 0.0)))
    source_rows = list(metadata.get("rows", []) or [])
    if not source_rows:
        row_order: list[tuple[str, str]] = []
        for segment in segments:
            pair = (str(segment.get("drive_id", "")), str(segment.get("drive_name", "drive")))
            if pair not in row_order:
                row_order.append(pair)
        content_top, content_bottom = float(result["chart_top"]), float(result["chart_bottom"])
        row_height = (content_bottom - content_top) / max(len(row_order), 1)
        source_rows = [{
            "name": name, "drive_id": drive_id,
            "top": content_top + index * row_height,
            "bottom": content_top + (index + 1) * row_height,
            "center": content_top + (index + 0.5) * row_height,
            "segments": [
                {"start": float(item.get("start", 0.0)), "end": float(item.get("end", 0.0))}
                for item in segments if str(item.get("drive_id", "")) == drive_id
            ],
        } for index, (drive_id, name) in enumerate(row_order)]
    rows = []
    for source_row in source_rows:
        row = dict(source_row)
        drive_id = str(row.get("drive_id", "") or "")
        if drive_id not in drive_by_id:
            row_name = str(row.get("name", "") or "")
            drive_id = next(
                (key for key, drive in drive_by_id.items() if str(drive.get("name", "") or "") == row_name),
                "",
            )
        if drive_id in drive_by_id:
            drive = drive_by_id[drive_id]
            row["value_series"] = [{
                "name": str(drive.get("name", row.get("name", ""))),
                "unit": str(drive.get("unit", "") or ""),
                "times": [float(value) for value in times],
                "values": values_by_id[drive_id],
            }]
        rows.append(row)
    result["rows"] = rows
    return result


def _viewer_model_source(
    scene_path: str | Path, *, asset_map: dict[str, str] | None = None,
    max_asset_bytes: int | None = None,
) -> tuple[Path, bool, str | None, dict[str, bytes]]:
    """Resolve the existing Unicode/VFS model-loading contract once for model and spec loaders."""
    scene = Path(scene_path).resolve()
    maximum = max_asset_bytes
    if maximum is None:
        maximum = int(os.getenv("MUJOCO_STUDIO_VFS_MAX_BYTES", str(2 * 1024**3)))
    paths: dict[str, Path] = {}
    if asset_map is not None:
        for key, value in asset_map.items():
            normalized = Path(str(key).replace("\\", "/"))
            if normalized.is_absolute() or ".." in normalized.parts:
                raise ValueError(f"local_asset_invalid: VFS key 必须是安全相对路径：{key}")
            paths[normalized.as_posix()] = Path(value).resolve()
    else:
        mesh_dir = scene.parent / "meshes"
        if mesh_dir.is_dir():
            for asset_path in mesh_dir.rglob("*"):
                if asset_path.is_file():
                    paths[asset_path.relative_to(scene.parent).as_posix()] = asset_path.resolve()

    use_vfs = asset_map is not None or any(
        any(ord(character) >= 128 for character in str(path))
        for path in [scene, *paths.values()]
    )
    if not use_vfs:
        return scene, False, None, {}

    try:
        sizes = {key: path.stat().st_size for key, path in paths.items()}
    except OSError as exc:
        raise ValueError(f"local_asset_unreadable: 无法检查本地资产：{exc}") from exc
    total = sum(sizes.values())
    if total > maximum:
        raise ValueError(f"viewer_assets_too_large: 本地资产共 {total} 字节，超过上限 {maximum} 字节")
    assets: dict[str, bytes] = {}
    byte_cache: dict[Path, bytes] = {}
    for key, path in paths.items():
        try:
            raw = byte_cache.get(path)
            if raw is None:
                raw = path.read_bytes()
                byte_cache[path] = raw
        except OSError as exc:
            raise ValueError(f"local_asset_unreadable: 无法读取本地资产 {path}：{exc}") from exc
        assets[key] = raw
    try:
        xml_text = scene.read_text("utf-8")
    except OSError as exc:
        raise ValueError(f"无法读取 Viewer XML：{scene}：{exc}") from exc
    return scene, True, xml_text, assets


_VIEWER_VFS_SCENE_NAME = "__mujoco_studio_scene__.xml"


def _populate_mujoco_vfs(mujoco_module: Any, xml_text: str, assets: dict[str, bytes]) -> Any:
    """Build an MjVfs for one Viewer load while retaining pre-3.8 compatibility elsewhere."""
    vfs = mujoco_module.MjVfs()
    try:
        vfs[_VIEWER_VFS_SCENE_NAME] = xml_text.encode("utf-8")
        for key, raw in assets.items():
            vfs[key] = raw
    except Exception:
        close = getattr(vfs, "close", None)
        if callable(close):
            close()
        raise
    return vfs


def load_mujoco_model(
    scene_path: str | Path,
    mujoco_module: Any,
    *,
    asset_map: dict[str, str] | None = None,
    max_asset_bytes: int | None = None,
) -> Any:
    """Load a generated scene while preserving the Unicode/VFS compatibility path."""
    requested_scene = Path(scene_path)
    scene, use_vfs, xml_text, assets = _viewer_model_source(
        scene_path, asset_map=asset_map, max_asset_bytes=max_asset_bytes,
    )
    if not use_vfs:
        load_path = requested_scene if not requested_scene.is_absolute() else scene
        return mujoco_module.MjModel.from_xml_path(str(load_path))
    if hasattr(mujoco_module, "MjVfs"):
        vfs = _populate_mujoco_vfs(mujoco_module, str(xml_text), assets)
        try:
            return mujoco_module.MjModel.from_xml_path(_VIEWER_VFS_SCENE_NAME, vfs=vfs)
        finally:
            close = getattr(vfs, "close", None)
            if callable(close):
                close()
    # MuJoCo < 3.8.1 has no Python MjVfs binding. Retain the existing asset
    # dictionary path only for those installations.
    return mujoco_module.MjModel.from_xml_string(str(xml_text), assets=assets)


def load_mujoco_spec(
    scene_path: str | Path,
    mujoco_module: Any,
    *,
    asset_map: dict[str, str] | None = None,
    max_asset_bytes: int | None = None,
) -> tuple[Any, Any | None]:
    """Parse Viewer MjSpec and return the VFS whose lifetime must span both compiles."""
    if not hasattr(mujoco_module, "MjSpec"):
        raise RuntimeError("mjspec_unavailable")
    requested_scene = Path(scene_path)
    scene, use_vfs, xml_text, assets = _viewer_model_source(
        scene_path, asset_map=asset_map, max_asset_bytes=max_asset_bytes,
    )
    if not use_vfs:
        load_path = requested_scene if not requested_scene.is_absolute() else scene
        return mujoco_module.MjSpec.from_file(str(load_path)), None
    if hasattr(mujoco_module, "MjVfs"):
        vfs = _populate_mujoco_vfs(mujoco_module, str(xml_text), assets)
        try:
            spec = mujoco_module.MjSpec.from_file(_VIEWER_VFS_SCENE_NAME, vfs=vfs)
        except Exception:
            close = getattr(vfs, "close", None)
            if callable(close):
                close()
            raise
        return spec, vfs
    # Compatibility for MuJoCo 3.2.x-3.8.0. Current MuJoCo deprecates this
    # form, but older runtimes do not expose MjVfs and still require it.
    return mujoco_module.MjSpec.from_string(str(xml_text), assets=assets), None


def _compile_mujoco_spec(spec: Any, vfs: Any | None) -> Any:
    return spec.compile(vfs=vfs) if vfs is not None else spec.compile()


def run_viewer(
    scene_path: str, drives_path: str, *, loop: bool = False, playback_speed: float = 1.0,
    gantt_cache_path: str | Path | None = None, asset_map_path: str | Path | None = None,
    trajectory_path: str | Path | None = None,
) -> None:
    import tkinter as tk
    from tkinter import ttk
    import mujoco  # type: ignore
    import mujoco.viewer  # type: ignore

    profile = dict(_VIEWER_PERF_PROFILE)
    print(
        "MUJOCO_STUDIO_VIEWER_PROFILE "
        + json.dumps(profile, ensure_ascii=False, sort_keys=True),
        flush=True,
    )
    if bool(profile.get("require_scipy", False)):
        try:
            from scipy.spatial import cKDTree as _required_ckdtree  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "此诊断版本要求 SciPy/cKDTree；请在 Client 目录重新执行 pip install -r requirements.txt"
            ) from exc

    scene = Path(scene_path).resolve()
    payload = json.loads(Path(drives_path).resolve().read_text("utf-8"))
    asset_map = None
    if asset_map_path is not None:
        asset_payload = json.loads(Path(asset_map_path).resolve().read_text("utf-8"))
        asset_map = {str(key): str(value) for key, value in dict(asset_payload.get("assets", {})).items()}
    # V2.8.14 startup contract: compile the immutable Viewer model once, show the
    # native window immediately, then prepare distance sampling.  The existing
    # vectorized/cache measurement path is reused deliberately: injecting MjSpec
    # sites would require a second compile and would make the model held by an
    # already-running passive Viewer stale.
    model = load_mujoco_model(scene, mujoco, asset_map=asset_map)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    viewer = _launch_passive(mujoco, model, data)
    # V2.8.14: ``launch_passive`` starts the native render loop asynchronously.
    # Prime/present the first frame and release the GIL briefly before READY;
    # otherwise large post-launch Python work can make the progress overlay end
    # while the actual native window is still not visible.
    _prime_passive_viewer(viewer)
    print("MUJOCO_STUDIO_VIEWER_READY", flush=True)
    # V2.8.14: camera helper work is not required to create the native window.
    # Keep it after READY so large mesh collections cannot delay the UI launch signal.
    scene_mesh_center = _mesh_collection_center(
        model, data, int(mujoco.mjtGeom.mjGEOM_MESH),
    )

    distance_pairs: list[dict[str, Any]] = []
    distance_site_group: int | None = None
    sampling_cfg = payload.get("distance_sampling", {})
    requested_points = max(16, int(sampling_cfg.get("max_points_per_object", 400)))

    def report_sampling(done: int, total: int, sampled: int) -> None:
        print(f"MUJOCO_STUDIO_SAMPLING_PROGRESS {done}/{total} {sampled}", flush=True)

    print("MUJOCO_STUDIO_SAMPLING_PROGRESS 0/1 0", flush=True)
    distance_backend = "vectorized-cache"
    distance_backend_warning = ""
    if payload.get("distance_pairs"):
        distance_backend_warning = "V2.14.2 Viewer 已优先打开；测距采样使用向量化缓存后端，跳过 MjSpec site 二次编译"
    distance_pairs = _build_distance_pairs(mujoco, model, payload, progress=report_sampling)
    base_qpos = data.qpos.copy()
    trajectory_times = np.asarray([], dtype=float)
    trajectory_qpos: np.ndarray | None = None
    if trajectory_path is not None and Path(trajectory_path).is_file():
        trajectory_times, trajectory_qpos = load_qpos_trajectory(
            trajectory_path, expected_nq=int(model.nq),
        )

    def sample_trajectory(time_s: float) -> np.ndarray | None:
        if trajectory_qpos is None:
            return None
        return sample_qpos_trajectory(trajectory_times, trajectory_qpos, time_s)

    joint_map = {str(key): str(value) for key, value in payload.get("joint_map", {}).items()}
    segments = list(payload.get("segments", []))
    cumulative_travel: dict[str, float] = {}
    for segment in sorted(segments, key=lambda item: (str(item.get("drive_id", "")), float(item.get("start", 0.0)))):
        drive_id = str(segment.get("drive_id", ""))
        segment["travel_start"] = cumulative_travel.get(drive_id, 0.0)
        segment["travel_end"] = float(segment["travel_start"]) + float(segment.get("travel", 0.0))
        cumulative_travel[drive_id] = float(segment["travel_end"])
    gantt_segments = _mapping_gantt_segments(segments)
    drives = [item for item in payload.get("drives", []) if item.get("enabled", True)]
    automation_control = dict(payload.get("viewer_control", {}))
    project_id = str(payload.get("project_id", ""))
    api_base = os.environ.get("MUJOCO_STUDIO_URL", f"http://127.0.0.1:{os.environ.get('MUJOCO_STUDIO_PORT', '8765')}").rstrip("/")
    settings = payload.get("simulation", {})
    start_time = float(settings.get("start_time", 0.0))
    end_time = float(settings.get("end_time", 12.0))
    timestep = float(settings.get("timestep", 0.01))
    addresses: dict[str, tuple[int, bool]] = {}
    for joint_id, name in joint_map.items():
        joint_mj_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint_mj_id >= 0:
            address = int(model.jnt_qposadr[joint_mj_id])
            slide = int(model.jnt_type[joint_mj_id]) == int(mujoco.mjtJoint.mjJNT_SLIDE)
            addresses[joint_id] = (address, slide)

    ranges = _drive_ranges(drives, segments, start_time, end_time)
    drive_by_id = {str(item.get("id", "")): item for item in drives}
    drives_by_joint: dict[str, list[str]] = {}
    for drive_id, drive in drive_by_id.items():
        joint_id = str(drive.get("joint_id", ""))
        if joint_id:
            drives_by_joint.setdefault(joint_id, []).append(drive_id)
    mapping_segments_by_drive = {
        str(segment.get("drive_id", "")): segment
        for segment in segments if segment.get("profile") == "mapping" and segment.get("drive_id")
    }
    mapping_drive_ids = set(mapping_segments_by_drive)
    mapping_root_by_drive, mapping_family_by_drive = _viewer_mapping_topology(
        mapping_segments_by_drive, drive_by_id, drives_by_joint,
    )
    linked_mapping_drive_ids = {
        drive_id for drive_id, family in mapping_family_by_drive.items() if len(family) > 1
    }

    solver_mode = str(payload.get("solver_mode", "kinematic") or "kinematic").strip().lower()
    closure_runtime = None
    closure_solver = None
    closure_previous_qpos: dict[str, np.ndarray | None] = {"value": None}
    closure_previous_time_s: dict[str, float | None] = {"value": None}
    closure_runtime_status = {"value": ""}
    active_drive_joint_ids = {
        str(item.get("joint_id", "")) for item in drives if str(item.get("joint_id", "")).strip()
    }
    enabled_closures = [
        item for item in list(payload.get("kinematic_closures", []) or [])
        if isinstance(item, dict) and bool(item.get("enabled", True))
    ]
    if solver_mode == "kinematic" and enabled_closures:
        build_closure_runtime, closure_solver = _load_kinematic_closure_helpers()
        closure_runtime = build_closure_runtime(mujoco, model, payload)
        if bool(getattr(closure_runtime, "enabled", False)):
            passive_ids = set(getattr(closure_runtime, "joints", {}))
            conflicts = sorted(active_drive_joint_ids.intersection(passive_ids))
            if conflicts:
                raise RuntimeError(
                    "运动学闭链从动运动副与启用驱动冲突：" + ", ".join(conflicts)
                )
            print(
                "MUJOCO_STUDIO_KINEMATIC_CLOSURE "
                f"constraints={len(getattr(closure_runtime, 'constraints', []))} "
                f"passive_joints={len(passive_ids)}",
                flush=True,
            )

    gantt_cache_dir = (
        Path(gantt_cache_path).resolve()
        if gantt_cache_path is not None
        else Path(tempfile.gettempdir()) / "mujoco_xml_tool_v20_7"
    )
    # V2.16.6: do not generate an incompatible generic Gantt from drive data
    # in the native window. The cached Web PNG is the sole presentation source.
    gantt_fallback_dir = gantt_cache_dir.parent / "gantt_fallback"  # legacy arg, never read
    gantt_cache_error = "请在 Web 端刷新并保存甘特图 PNG 缓存；不再使用样式不一致的兜底图"
    filename_geoms: dict[str, list[int]] = {}
    for filename, geom_names in payload.get("mesh_manifest", {}).items():
        for geom_name in geom_names:
            geom_id = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, str(geom_name)))
            if geom_id >= 0:
                filename_geoms.setdefault(str(filename), []).append(geom_id)
    geom_masses: dict[int, float] = {}
    for geom_name, item in payload.get("mesh_mass_manifest", {}).items():
        geom_id = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, str(geom_name)))
        mass = item.get("mass_kg") if isinstance(item, dict) else None
        if geom_id >= 0 and mass is not None and float(mass) > 0:
            geom_masses[geom_id] = float(mass)

    root = tk.Tk()
    root.title(f"MuJoCo 动画控制 · V2.16.11.6 · 测距 {distance_backend}")
    root.geometry("1060x570")
    root.minsize(780, 390)
    # Controls expand inside a vertically scrolling region; never resize the user's
    # custom window every time motor mode is entered or exited.
    alive = {"value": True}
    control = _session_defaults(start_time, end_time, playback_speed)
    camera_settings = _camera_settings(automation_control.get("camera_initial_pose", ""))
    playing = {"value": False, "direction": 1.0}
    dragging = {"value": False}
    motor_mode = {"value": False}
    syncing = {"value": False}
    current = tk.DoubleVar(value=float(control["time_s"]))
    speed = tk.DoubleVar(value=float(control["speed"]))
    scatter = tk.BooleanVar(value=bool(control.get("show_scatter", True)))
    show_lines = tk.BooleanVar(value=bool(control.get("show_distance_lines", True)))
    show_labels = tk.BooleanVar(value=bool(control.get("show_distance_labels", True)))
    adaptive = tk.BooleanVar(value=bool(control.get("adaptive_display", True)))
    adaptive_mm = tk.DoubleVar(value=float(control.get("adaptive_threshold_mm", 25.0)))
    measurement_mode_var = tk.StringVar(
        value="低延时20Hz" if bool(profile.get("measurement_low_latency", False)) else "完全精确",
    )
    measurement_actual_var = tk.StringVar(value="实际：等待测量")
    status_suffix = f" | {distance_backend_warning}" if distance_backend_warning else ""
    status = tk.StringVar(value=f"已暂停在动画起点{status_suffix}")
    viewer_ref: dict[str, Any] = {"value": viewer}
    orthographic = {"value": True}
    # Only live Viewer gesture bookkeeping; no project/UI persistence.
    camera_pan_state = {"rebase": True}
    orthographic_fovy = tk.DoubleVar(value=0.8)
    gantt_enabled = tk.BooleanVar(value=False)
    pair_vars = {pair["name"]: tk.StringVar(value=f"{pair['name']}: --") for pair in distance_pairs}
    manual_values: dict[str, float] = {}
    manual_vars: dict[str, tk.DoubleVar] = {}
    manual_labels: dict[str, tk.StringVar] = {}
    manual_resolutions: dict[str, float] = {}
    manual_display_values: dict[str, float] = {}
    pending_manual_inputs: dict[str, float] = {}
    manual_dragging: set[str] = set()
    last_motor_ui_sync = {"value": 0.0}
    decoupled: set[str] = set(control.get("decoupled_drive_ids", []))
    if decoupled:
        expanded_decoupled: set[str] = set()
        for drive_id in decoupled:
            expanded_decoupled.update(mapping_family_by_drive.get(drive_id, frozenset({drive_id})))
        decoupled = expanded_decoupled
        control["decoupled_drive_ids"] = sorted(decoupled)
    # Baseline the polling channel without importing its persisted UI state.
    # Only a later backend change is considered an automation command.
    remote_control = automation_control
    last_remote_poll = {"value": 0.0}
    trajectory_points: list[np.ndarray] = []
    last_clear_revision = {"value": int(control.get("trajectory", {}).get("clear_revision", 0))}
    last_probe_revision = {"value": int(control.get("trajectory", {}).get("centroid_probe_revision", 0))}

    def assign_control(path: str, value: Any) -> None:
        """Cache a human UI change locally; never mutate the project variable pool."""
        _cache_value(control, path, value)

    # V2.15.10: the original urllib call to /state did not carry a browser
    # Session cookie. In multi-user deployments it triggered an endless 401
    # storm at 4 requests/second per Viewer. A server-launched Viewer reads
    # only its own model's local JSON and uses stat() to avoid redundant JSON
    # decoding. A remote client without this local file does NOT poll /state.
    project_json_raw = os.environ.get("MUJOCO_STUDIO_VIEWER_PROJECT_JSON", "").strip()
    project_json_path = Path(project_json_raw).resolve() if project_json_raw else None
    remote_cache: dict[str, Any] = {"signature": None, "control": None}

    def fetch_remote_control() -> dict[str, Any] | None:
        if project_json_path is None:
            return None
        try:
            info = project_json_path.stat()
            signature = (info.st_mtime_ns, info.st_size)
            if signature == remote_cache["signature"]:
                return None
            payload = json.loads(project_json_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return None
            control_snapshot = payload.get("viewer_control", {})
            if not isinstance(control_snapshot, dict):
                return None
            remote_cache["signature"] = signature
            remote_cache["control"] = control_snapshot
            return dict(control_snapshot)
        except (OSError, ValueError, TypeError):
            return None

    remote_poller = (
        _RemoteControlPoller(fetch_remote_control, float(profile.get("remote_poll_interval_s", 0.25)))
        if project_json_path is not None and bool(profile.get("remote_poll_async", False)) else None
    )
    remote_poll_revision = 0

    def close_controller() -> None:
        alive["value"] = False

    root.protocol("WM_DELETE_WINDOW", close_controller)
    timeline = ttk.Frame(root, padding=(10, 7, 10, 2))
    timeline.pack(fill="x")
    time_label = ttk.Label(timeline, text=f"{start_time:.3f}s")
    time_label.pack(side="left")
    scale = ttk.Scale(timeline, variable=current, from_=start_time, to=end_time)
    scale.pack(side="left", fill="x", expand=True, padx=8)
    scale.bind("<ButtonPress-1>", lambda _event: dragging.__setitem__("value", True))
    scale.bind("<ButtonRelease-1>", lambda _event: (
        dragging.__setitem__("value", False), assign_control("time_s", float(current.get()))
    ))
    end_label = ttk.Label(timeline, text=f"{end_time:.3f}s")
    end_label.pack(side="left")

    controls = ttk.Frame(root, padding=(10, 2, 10, 3))
    controls.pack(fill="x")

    def refresh_buttons() -> None:
        forward.configure(text="||" if playing["value"] and playing["direction"] > 0 else ">")
        reverse.configure(text="||" if playing["value"] and playing["direction"] < 0 else "<")

    def toggle(direction: float) -> None:
        if playing["value"] and playing["direction"] == direction:
            playing["value"] = False
        else:
            playing.update(value=True, direction=direction)
        assign_control("direction", int(direction))
        assign_control("playing", playing["value"])
        refresh_buttons()

    def reset_time(value: float) -> None:
        playing["value"] = False
        current.set(value)
        assign_control("playing", False)
        assign_control("time_s", float(value))
        refresh_buttons()

    ttk.Button(controls, text="<<", width=4, command=lambda: reset_time(start_time)).pack(side="left", padx=2)
    reverse = ttk.Button(controls, text="<", width=4, command=lambda: toggle(-1.0))
    reverse.pack(side="left", padx=2)
    forward = ttk.Button(controls, text=">", width=4, command=lambda: toggle(1.0))
    forward.pack(side="left", padx=2)
    ttk.Button(controls, text=">>", width=4, command=lambda: reset_time(end_time)).pack(side="left", padx=2)
    motor_button = ttk.Button(controls, text="▤ 电机控制")
    motor_button.pack(side="left", padx=(9, 2))

    try:
        default_global_fovy = float(model.vis.global_.fovy)
    except Exception:
        default_global_fovy = 45.0

    def set_orthographic(enabled: bool, *, persist: bool = True) -> None:
        """Switch MuJoCo's actual render projection, including fixed cameras."""
        viewer_instance = viewer_ref["value"]
        orthographic["value"] = bool(enabled)
        camera_pan_state["rebase"] = True
        fovy = min(max(float(orthographic_fovy.get()), _ORTHOGRAPHIC_FOVY_MIN), _ORTHOGRAPHIC_FOVY_MAX)
        if hasattr(model.vis.global_, "orthographic"):
            model.vis.global_.orthographic = 1 if enabled else 0
        model.vis.global_.fovy = fovy if enabled else default_global_fovy
        camera_flags = getattr(model, "cam_orthographic", None)
        for camera_id in range(int(getattr(model, "ncam", 0) or 0)):
            if camera_flags is not None:
                camera_flags[camera_id] = 1 if enabled else 0
            if enabled:
                model.cam_fovy[camera_id] = fovy
        if viewer_instance is not None:
            try:
                if hasattr(viewer_instance.cam, "orthographic"):
                    viewer_instance.cam.orthographic = 1 if enabled else 0
                viewer_instance.sync()
            except Exception:
                pass
        if persist:
            assign_control("orthographic_view", bool(enabled))

    def update_orthographic_fovy(_value: Any = None) -> None:
        if orthographic["value"]:
            set_orthographic(True)

    def set_view_preset(name: str) -> None:
        viewer_instance = viewer_ref["value"]
        if viewer_instance is None:
            return
        camera = camera_settings.get(name, CAMERA_DEFAULTS["initial_free_view"])
        position = np.asarray(camera["pos"], dtype=float)
        direction = np.asarray(camera["direction"], dtype=float)
        direction /= max(float(np.linalg.norm(direction)), 1e-12)
        distance = max(float(model.stat.extent) * 2.2, 0.5)
        viewer_instance.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        viewer_instance.cam.fixedcamid = -1
        if hasattr(viewer_instance.cam, "trackbodyid"):
            viewer_instance.cam.trackbodyid = -1
        viewer_instance.cam.lookat[:] = scene_mesh_center.tolist()
        viewer_instance.cam.distance = distance
        viewer_instance.cam.azimuth = math.degrees(math.atan2(float(direction[1]), float(direction[0])))
        viewer_instance.cam.elevation = math.degrees(math.asin(min(max(float(direction[2]), -1.0), 1.0)))
        camera_pan_state["rebase"] = True
        viewer_instance.sync()

    ttk.Label(controls, text="动画倍速").pack(side="left", padx=(10, 2))
    speed_entry = ttk.Entry(controls, textvariable=speed, width=7)
    speed_entry.pack(side="left")

    def playback_speed_value() -> float:
        try:
            return min(max(float(speed.get()), 0.1), 2.0)
        except (ValueError, tk.TclError):
            return 1.0

    def confirm_playback_speed(_event: Any = None) -> None:
        value = playback_speed_value()
        speed.set(value)
        assign_control("speed", value)

    speed_entry.bind("<Return>", confirm_playback_speed)
    ttk.Label(controls, text="x").pack(side="left", padx=(2, 3))

    def save_viewer_screenshot() -> None:
        """Capture only the active native MuJoCo GLFW window to a user-selected PNG."""
        from tkinter import filedialog, messagebox

        target = filedialog.asksaveasfilename(
            parent=root,
            title="保存 MuJoCo Viewer 截图",
            defaultextension=".png",
            filetypes=[("PNG 图片", "*.png"), ("JPEG 图片", "*.jpg;*.jpeg")],
            initialfile=f"mujoco_viewer_{time.strftime('%Y%m%d_%H%M%S')}.png",
        )
        if not target:
            return
        viewer_instance = viewer_ref["value"]
        if viewer_instance is None:
            messagebox.showerror("截图失败", "MuJoCo Viewer 窗口尚未就绪。", parent=root)
            return
        try:
            import glfw  # type: ignore
            from PIL import ImageGrab

            viewer_instance.sync()
            window = getattr(viewer_instance, "_window", None)
            sim_ref = getattr(viewer_instance, "_sim", None)
            sim = sim_ref() if callable(sim_ref) else sim_ref
            if window is None:
                window = getattr(sim, "_window", None)
            bbox: tuple[int, int, int, int] | None = None
            if window is not None:
                x, y = glfw.get_window_pos(window)
                width, height = glfw.get_window_size(window)
                bbox = (int(x), int(y), int(x + width), int(y + height))
            elif os.name == "nt":
                import ctypes
                from ctypes import wintypes

                candidates: list[tuple[int, tuple[int, int, int, int], str]] = []
                user32 = ctypes.windll.user32
                process_id = os.getpid()

                @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                def collect_window(hwnd, _lparam):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value != process_id or not user32.IsWindowVisible(hwnd):
                        return True
                    rect = wintypes.RECT()
                    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                        return True
                    length = user32.GetWindowTextLengthW(hwnd)
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    title = buffer.value
                    width, height = rect.right - rect.left, rect.bottom - rect.top
                    if width > 200 and height > 150 and "Playback Controller" not in title and "实时甘特图" not in title:
                        candidates.append((width * height, (rect.left, rect.top, rect.right, rect.bottom), title))
                    return True

                user32.EnumWindows(collect_window, 0)
                mujoco_windows = [item for item in candidates if "mujoco" in item[2].lower()]
                pool = mujoco_windows or candidates
                if pool:
                    bbox = max(pool, key=lambda item: item[0])[1]
            if bbox is None:
                from PIL import Image

                width = max(640, int(getattr(model.vis.global_, "offwidth", 640)))
                height = max(480, int(getattr(model.vis.global_, "offheight", 480)))
                renderer = mujoco.Renderer(model, height=height, width=width)
                try:
                    renderer.update_scene(data, camera=viewer_instance.cam)
                    Image.fromarray(renderer.render()).save(target)
                finally:
                    renderer.close()
                status.set(f"截图已保存：{target}")
                return
            x, y, right, bottom = bbox
            width, height = right - x, bottom - y
            if width <= 0 or height <= 0:
                raise RuntimeError("Viewer 窗口当前已最小化或尺寸无效")
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
            image.save(target)
            status.set(f"截图已保存：{target}")
        except Exception as exc:
            messagebox.showerror("截图失败", f"无法截取 MuJoCo Viewer 窗口：\n{exc}", parent=root)

    jump_var = tk.StringVar(value="")

    def jump_to_time(_event: Any = None) -> None:
        try:
            value = min(max(float(jump_var.get()), start_time), end_time)
        except ValueError:
            status.set("定位时间请输入有效数值")
            return
        reset_time(value)

    ttk.Checkbutton(
        controls, text="打开甘特图", variable=gantt_enabled,
        command=lambda: toggle_gantt(),
    ).pack(side="left", padx=(5, 0))
    ttk.Button(controls, text="截图", command=save_viewer_screenshot).pack(side="left", padx=(6, 0))
    ttk.Label(controls, text="定位时间(s)").pack(side="left", padx=(10, 2))
    jump_entry = ttk.Entry(controls, textvariable=jump_var, width=12)
    jump_entry.pack(side="left", padx=(0, 4))
    jump_entry.bind("<Return>", jump_to_time)

    view_row = ttk.Frame(root, padding=(10, 0, 10, 3))
    view_row.pack(fill="x")
    ttk.Label(view_row, text="视图：").pack(side="left")
    ttk.Button(view_row, text="正视图", command=lambda: set_view_preset("front_view")).pack(side="left", padx=4)
    ttk.Button(view_row, text="侧视图", command=lambda: set_view_preset("side_view")).pack(side="left", padx=4)
    ttk.Button(view_row, text="POV视图", command=lambda: set_view_preset("pov_view")).pack(side="left", padx=4)
    ttk.Button(view_row, text="初始自由相机", command=lambda: set_view_preset("initial_free_view")).pack(side="left", padx=4)
    orthographic_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        view_row, text="开启正交视角", variable=orthographic_var,
        command=lambda: set_orthographic(bool(orthographic_var.get())),
    ).pack(side="left", padx=(12, 4))
    ttk.Label(view_row, text="cam_fovy").pack(side="left")
    tk.Scale(
        view_row, variable=orthographic_fovy, from_=_ORTHOGRAPHIC_FOVY_MIN,
        to=_ORTHOGRAPHIC_FOVY_MAX, resolution=_ORTHOGRAPHIC_FOVY_STEP,
        orient="horizontal", length=170, showvalue=True, command=update_orthographic_fovy,
    ).pack(side="left")

    options = ttk.Frame(root, padding=(10, 0, 10, 4))
    options.pack(fill="x")
    ttk.Checkbutton(
        options, text="撒点可视化（动画间距）", variable=scatter,
        command=lambda: assign_control("show_scatter", bool(scatter.get())),
    ).pack(side="left", padx=2)
    ttk.Checkbutton(
        options, text="显示测距胶囊线", variable=show_lines,
        command=lambda: assign_control("show_distance_lines", bool(show_lines.get())),
    ).pack(side="left", padx=7)
    ttk.Checkbutton(
        options, text="线段数值", variable=show_labels,
        command=lambda: assign_control("show_distance_labels", bool(show_labels.get())),
    ).pack(side="left", padx=7)
    ttk.Checkbutton(
        options, text="自适应显示", variable=adaptive,
        command=lambda: assign_control("adaptive_display", bool(adaptive.get())),
    ).pack(side="left", padx=7)
    ttk.Label(options, text="距离 ≤").pack(side="left")
    adaptive_spin = ttk.Spinbox(
        options, textvariable=adaptive_mm, from_=0.1, to=100000, increment=1, width=7,
    )
    adaptive_spin.pack(side="left", padx=2)
    adaptive_spin.bind("<Return>", lambda _event: assign_control(
        "adaptive_threshold_mm", float(adaptive_mm.get())
    ))
    ttk.Label(options, text="mm").pack(side="left")

    measurement_mode_row = ttk.Frame(root, padding=(10, 0, 10, 4))
    measurement_mode_row.pack(fill="x")
    ttk.Label(measurement_mode_row, text="测距模式：").pack(side="left")
    measurement_mode_combo = ttk.Combobox(
        measurement_mode_row,
        textvariable=measurement_mode_var,
        values=("低延时20Hz", "完全精确"),
        state="readonly",
        width=11,
    )
    measurement_mode_combo.pack(side="left")
    ttk.Label(measurement_mode_row, textvariable=measurement_actual_var).pack(side="left", padx=(12, 0))
    ttk.Label(
        measurement_mode_row,
        text="（后台只处理最新姿态，不积压）",
        foreground="#666",
    ).pack(side="left", padx=(8, 0))

    def apply_measurement_mode(_event: Any = None) -> None:
        enabled = measurement_mode_var.get() != "完全精确"
        profile["measurement_low_latency"] = enabled
        if distance_worker is not None:
            distance_worker.set_low_latency(enabled)
        print(
            "MUJOCO_STUDIO_MEASUREMENT_MODE " + ("low_latency" if enabled else "exact"),
            flush=True,
        )

    measurement_mode_combo.bind("<<ComboboxSelected>>", apply_measurement_mode)

    distance_expanded = tk.BooleanVar(value=False)
    distance_toggle = ttk.Button(root, text=f"▸ 测距结果 · {len(distance_pairs)} 组", takefocus=False)
    distance_toggle.pack(anchor="w", padx=10, pady=(2, 0))
    distance_box = ttk.LabelFrame(root, text="测距结果", padding=(8, 4))

    def toggle_distance() -> None:
        distance_expanded.set(not distance_expanded.get())
        distance_toggle.configure(text=("▾ 展开中" if distance_expanded.get() else "▸ 展开") + f" · 测距结果 {len(distance_pairs)} 组")
        if distance_expanded.get():
            distance_box.pack(fill="x", padx=10, pady=(2, 4), after=distance_toggle)
        else:
            distance_box.pack_forget()

    distance_toggle.configure(command=toggle_distance)
    if distance_pairs:
        for pair in distance_pairs:
            ttk.Label(distance_box, textvariable=pair_vars[pair["name"]], anchor="w").pack(fill="x")
    else:
        ttk.Label(
            distance_box, text="没有有效测距对（请检查 A/B 对象选择）",
        ).pack(anchor="w")

    trajectory_cfg = dict(control.get("trajectory", {}))
    trajectory_body = ttk.LabelFrame(root, text="STL / 多选整体质心轨迹", padding=(8, 4))
    trajectory_expanded = tk.BooleanVar(value=False)
    trajectory_toggle = ttk.Button(root, text="▸ STL 轨迹录制 · 点击展开", takefocus=False)
    trajectory_toggle.pack(anchor="w", padx=10, pady=(2, 0))
    def toggle_trajectory() -> None:
        trajectory_expanded.set(not trajectory_expanded.get())
        trajectory_toggle.configure(text="▾ STL 轨迹录制 · 点击收起" if trajectory_expanded.get() else "▸ STL 轨迹录制 · 点击展开")
        if trajectory_expanded.get():
            trajectory_body.pack(fill="x", padx=10, pady=3, after=trajectory_toggle)
        else:
            trajectory_body.pack_forget()
        assign_control("trajectory.expanded", bool(trajectory_expanded.get()))
    trajectory_toggle.configure(command=toggle_trajectory)
    trajectory_row = ttk.Frame(trajectory_body)
    trajectory_row.pack(fill="x")
    mesh_list = tk.Listbox(
        trajectory_row, selectmode="extended", exportselection=False, height=3, width=38,
    )
    for filename in filename_geoms:
        mesh_list.insert("end", filename)
    for index, filename in enumerate(filename_geoms):
        if filename in trajectory_cfg.get("selected_meshes", []):
            mesh_list.selection_set(index)
    mesh_list.pack(side="left", fill="x", expand=True)
    track_controls = ttk.Frame(trajectory_row)
    track_controls.pack(side="left", padx=6)
    frequency = tk.DoubleVar(value=float(trajectory_cfg.get("sample_hz", 20.0)))
    point_size = tk.DoubleVar(value=float(trajectory_cfg.get("point_size", 1.0)))
    track_color = tk.StringVar(value=str(trajectory_cfg.get("color", "#018c94")))
    centroid_text = tk.StringVar(value="质心坐标：--")

    def selected_mesh_names() -> list[str]:
        return [str(mesh_list.get(index)) for index in mesh_list.curselection()]

    def selected_geom_ids() -> list[int]:
        return [geom_id for name in selected_mesh_names() for geom_id in filename_geoms.get(name, [])]

    def selected_meshes_changed(_event: Any = None) -> None:
        if not syncing["value"]:
            assign_control("trajectory.selected_meshes", selected_mesh_names())

    mesh_list.bind("<<ListboxSelect>>", selected_meshes_changed)

    def start_recording() -> None:
        names = selected_mesh_names()
        if not names:
            status.set("请至少选择一个 STL/OBJ 对象")
            return
        assign_control("trajectory.selected_meshes", names)
        assign_control("trajectory.sample_hz", float(frequency.get()))
        assign_control("trajectory.point_size", float(point_size.get()))
        assign_control("trajectory.color", track_color.get())
        assign_control("trajectory.recording", True)
        control.setdefault("trajectory", {})["recording"] = True

    def pause_recording() -> None:
        assign_control("trajectory.recording", False)
        control.setdefault("trajectory", {})["recording"] = False

    def clear_recording() -> None:
        trajectory_points.clear()
        revision = last_clear_revision["value"] + 1
        last_clear_revision["value"] = revision
        assign_control("trajectory.clear_revision", revision)

    def probe_centroid() -> None:
        centroid = _selected_centroid(model, data, selected_geom_ids(), geom_masses)
        if centroid is None:
            centroid_text.set("质心坐标：请先选择对象")
            return
        centroid_text.set(
            f"整体质心：X {centroid[0] * 1000:.3f} / Y {centroid[1] * 1000:.3f} / "
            f"Z {centroid[2] * 1000:.3f} mm"
        )
        revision = last_probe_revision["value"] + 1
        last_probe_revision["value"] = revision
        assign_control("trajectory.centroid_probe_revision", revision)

    ttk.Button(track_controls, text="录制", command=start_recording).grid(row=0, column=0, padx=2)
    ttk.Button(track_controls, text="暂停", command=pause_recording).grid(row=0, column=1, padx=2)
    ttk.Button(track_controls, text="删除轨迹", command=clear_recording).grid(row=0, column=2, padx=2)
    ttk.Button(track_controls, text="显示质心坐标", command=probe_centroid).grid(row=0, column=3, padx=2)
    ttk.Label(track_controls, text="频率 Hz").grid(row=1, column=0)
    frequency_entry = ttk.Entry(track_controls, textvariable=frequency, width=7)
    frequency_entry.grid(row=1, column=1)
    ttk.Label(track_controls, text="小球大小").grid(row=1, column=2)
    point_size_entry = ttk.Entry(track_controls, textvariable=point_size, width=7)
    point_size_entry.grid(row=1, column=3)
    ttk.Label(track_controls, text="颜色").grid(row=2, column=0)
    color_entry = ttk.Entry(track_controls, textvariable=track_color, width=9)
    color_entry.grid(row=2, column=1)
    frequency_entry.bind("<Return>", lambda _event: assign_control(
        "trajectory.sample_hz", float(frequency.get())
    ))
    point_size_entry.bind("<Return>", lambda _event: assign_control(
        "trajectory.point_size", float(point_size.get())
    ))
    color_entry.bind("<Return>", lambda _event: assign_control("trajectory.color", track_color.get()))
    ttk.Label(trajectory_body, textvariable=centroid_text, anchor="w").pack(fill="x")

    motor_box = ttk.LabelFrame(root, text=f"电机控制 · {len(drives)} 个驱动", padding=(10, 6))
    motor_help = ttk.Label(
        motor_box,
        text="拖动滑条调整电机；滚轮 / 右侧滚动条查看更多驱动。重新耦合可恢复时间轴控制。",
        foreground="#66717d", anchor="w",
    )
    motor_help.pack(fill="x", pady=(0, 5))
    # Scrollable viewport is essential for 15+ motors. Scroll container owns the
    # height, not the N motor row widgets; the outer playback window stays stable.
    motor_scroller = ttk.Frame(motor_box)
    motor_scroller.pack(fill="both", expand=True)
    motor_canvas = tk.Canvas(
        motor_scroller, height=185, highlightthickness=0, borderwidth=0,
        background="#f5f7f9", yscrollincrement=22,
    )
    motor_scrollbar = ttk.Scrollbar(motor_scroller, orient="vertical", command=motor_canvas.yview)
    motor_canvas.configure(yscrollcommand=motor_scrollbar.set)
    motor_scrollbar.pack(side="right", fill="y")
    motor_canvas.pack(side="left", fill="both", expand=True)
    motor_inner = ttk.Frame(motor_canvas)
    motor_canvas_window = motor_canvas.create_window((0, 0), window=motor_inner, anchor="nw")

    def update_motor_scrollregion(_event: Any = None) -> None:
        motor_canvas.configure(scrollregion=motor_canvas.bbox("all"))

    def resize_motor_content(event: Any) -> None:
        motor_canvas.itemconfigure(motor_canvas_window, width=max(0, event.width))

    motor_inner.bind("<Configure>", update_motor_scrollregion)
    motor_canvas.bind("<Configure>", resize_motor_content)

    def motor_wheel(event: Any) -> None:
        if not motor_mode["value"]:
            return
        # Only scroll while the pointer is inside the motor viewport. Never
        # swallow wheel actions on the time slider or other playback controls.
        hovered = root.winfo_containing(event.x_root, event.y_root)
        while hovered is not None:
            if hovered is motor_scroller or hovered is motor_canvas:
                break
            hovered = hovered.master
        if hovered is None:
            return
        if getattr(event, "num", 0) in (4, 5):
            direction = 1 if event.num == 5 else -1
        else:
            delta = int(getattr(event, "delta", 0))
            if not delta:
                return
            direction = (-1 if delta > 0 else 1) * max(1, round(abs(delta) / 120))
        motor_canvas.yview_scroll(direction, "units")
        return "break"

    # Bind on the controller root, not bind_all: unrelated Tk windows should
    # never receive our motor-wheel handler. Linux uses Button-4/5.
    root.bind("<MouseWheel>", motor_wheel, add="+")
    root.bind("<Button-4>", motor_wheel, add="+")
    root.bind("<Button-5>", motor_wheel, add="+")

    def mapping_label(drive_id: str) -> str:
        family = mapping_family_by_drive.get(drive_id, frozenset({drive_id}))
        root_id = mapping_root_by_drive.get(drive_id, drive_id)
        if len(family) > 1:
            root_name = str(drive_by_id.get(root_id, {}).get("name", root_id or "源驱动"))
            if drive_id in decoupled:
                return f"手动联动 ↔ {root_name}"
            if drive_id in mapping_drive_ids:
                return f"映射联动 ↔ {root_name}"
            return "映射源（跟随时间轴）"
        return "已解耦" if drive_id in decoupled else "跟随时间轴"

    def refresh_motor_label(drive_id: str) -> None:
        label = manual_labels.get(drive_id)
        if label is not None:
            label.set(mapping_label(drive_id))

    def refresh_motor_labels() -> None:
        for key in manual_labels:
            refresh_motor_label(key)

    def motor_changed(drive_id: str, raw: str) -> None:
        """Publish one latest motor value without doing mapping/render work in the event path."""
        if syncing["value"]:
            return
        try:
            pending_manual_inputs[drive_id] = float(raw)
        except (TypeError, ValueError):
            return

    def begin_motor_drag(drive_id: str) -> None:
        """Let Tk own pointer motion; the render loop samples the DoubleVar once per frame."""
        manual_dragging.add(drive_id)

    def finish_motor_drag(drive_id: str) -> None:
        variable = manual_vars.get(drive_id)
        if variable is not None and not syncing["value"]:
            motor_changed(drive_id, str(variable.get()))
        manual_dragging.discard(drive_id)

    def apply_pending_motor_inputs() -> bool:
        """Resolve moved sliders into one canonical manual command per mapping family.

        Mapping descendants are not independent manual degrees of freedom. Dragging any
        family member inverse-maps the request to the root source, then the normal forward
        mapping projects every companion. The whole family enters manual/decoupled mode
        together so physical follower joints are written on the very first source drag.
        """
        if not pending_manual_inputs:
            return False
        latest = dict(pending_manual_inputs)
        pending_manual_inputs.clear()
        motor_values = control.get("motor_values")
        if not isinstance(motor_values, dict):
            motor_values = {}
            control["motor_values"] = motor_values
        changed_labels: set[str] = set()
        decoupled_changed = False
        for drive_id, requested in latest.items():
            root_id, root_value = _viewer_root_mapping_source(
                drive_id, mapping_segments_by_drive, drive_by_id, drives_by_joint,
                target_value=requested, current_values=manual_values,
            )
            root_id = root_id or drive_id
            target_value = float(root_value if root_value is not None else requested)
            low_value, high_value = ranges.get(root_id, (-1.0, 1.0))
            resolved = min(max(target_value, low_value), high_value)
            manual_values[root_id] = resolved
            motor_values[root_id] = resolved

            family = set(mapping_family_by_drive.get(drive_id, frozenset({root_id})))
            family.add(root_id)
            new_members = family.difference(decoupled)
            if new_members:
                decoupled.update(new_members)
                decoupled_changed = True
                changed_labels.update(family)
        if decoupled_changed:
            control["decoupled_drive_ids"] = sorted(decoupled)
        for changed_drive_id in changed_labels:
            refresh_motor_label(changed_drive_id)
        return True

    def recouple(drive_id: str) -> None:
        family = set(mapping_family_by_drive.get(drive_id, frozenset({drive_id})))
        family.add(mapping_root_by_drive.get(drive_id, drive_id))
        for member_id in family:
            pending_manual_inputs.pop(member_id, None)
            manual_dragging.discard(member_id)
            decoupled.discard(member_id)
        assign_control("decoupled_drive_ids", sorted(decoupled))
        for member_id in family:
            refresh_motor_label(member_id)

    for drive in drives:
        drive_id = str(drive.get("id", ""))
        row = ttk.Frame(motor_inner)
        row.pack(fill="x", pady=1)
        ttk.Label(row, text=str(drive.get("name", drive_id)), width=18).pack(side="left")
        low, high = ranges.get(drive_id, (-1.0, 1.0))
        initial_motor_value = float(control.get("motor_values", {}).get(drive_id, 0.0))
        variable = tk.DoubleVar(value=initial_motor_value)
        manual_vars[drive_id] = variable
        manual_values[drive_id] = initial_motor_value
        manual_display_values[drive_id] = initial_motor_value
        slider_resolution = max((high - low) / 1000.0, 0.001)
        manual_resolutions[drive_id] = slider_resolution
        motor_scale = tk.Scale(
            row, variable=variable, from_=low, to=high, resolution=slider_resolution,
            orient="horizontal", length=420, showvalue=True,
        )
        # Do not cross the Python/Tk command bridge on every pointer-motion event.
        # Tk updates ``variable`` natively; the render loop samples active drags once/frame,
        # while release/keyboard events publish a final value for lossless completion.
        motor_scale.bind("<ButtonPress-1>", lambda _event, key=drive_id: begin_motor_drag(key), add="+")
        motor_scale.bind("<ButtonRelease-1>", lambda _event, key=drive_id: finish_motor_drag(key), add="+")
        motor_scale.bind(
            "<KeyRelease>",
            lambda _event, key=drive_id, var=variable: motor_changed(key, str(var.get())),
            add="+",
        )
        motor_scale.pack(side="left", fill="x", expand=True)
        label = tk.StringVar(value=mapping_label(drive_id))
        manual_labels[drive_id] = label
        ttk.Label(row, textvariable=label, width=12).pack(side="left", padx=5)
        recouple_button = ttk.Button(
            row,
            text="重新耦合",
            command=lambda key=drive_id: recouple(key),
        )
        recouple_button.pack(side="left")
        target_var = tk.StringVar(value="")
        target_entry = ttk.Entry(row, textvariable=target_var, width=9)
        target_entry.pack(side="left", padx=(5, 0))

        def locate_motor(_event: Any = None, key: str = drive_id, raw_var: Any = target_var) -> None:
            try:
                value = float(raw_var.get())
            except ValueError:
                status.set("电机定位请输入有效数值")
                return
            low_value, high_value = ranges.get(key, (-1.0, 1.0))
            resolved = min(max(value, low_value), high_value)
            manual_vars[key].set(resolved)
            motor_changed(key, str(resolved))

        target_entry.bind("<Return>", locate_motor)
    if not drives:
        ttk.Label(motor_inner, text="当前没有启用的驱动").pack(anchor="w")

    def set_motor_mode(enabled: bool, *, persist: bool = True) -> None:
        old_value = bool(motor_mode["value"])
        motor_mode["value"] = bool(enabled)
        if persist and old_value != motor_mode["value"]:
            assign_control("motor_mode", motor_mode["value"])
        if enabled:
            motor_box.pack(fill="both", expand=True, padx=10, pady=(4, 7))
            motor_button.configure(text="▴ 收起电机控制")
            motor_canvas.yview_moveto(0.0)
            # A small window would otherwise hide the frame and scrolling bar.
            # Widening is not necessary; users keep their chosen window size.
            if root.winfo_height() < 560:
                root.geometry(f"{max(root.winfo_width(), 980)}x620")
            status.set(f"电机控制已展开 · {len(drives)} 个驱动 · 可滚动查看全部滑条")
        else:
            motor_box.pack_forget()
            motor_button.configure(text="▤ 电机控制")
            if persist and old_value:
                pending_manual_inputs.clear()
                manual_dragging.clear()
                decoupled.clear()
                assign_control("decoupled_drive_ids", [])
                refresh_motor_labels()
                status.set("已收起电机控制，恢复跟随时间轴")

    def toggle_motor_mode() -> None:
        set_motor_mode(not motor_mode["value"])

    motor_button.configure(command=toggle_motor_mode)
    if motor_mode["value"]:
        set_motor_mode(True, persist=False)
    ttk.Label(root, textvariable=status, anchor="w", padding=(10, 2)).pack(fill="x")

    gantt_reverse = tk.BooleanVar(value=False)
    gantt_topmost = tk.BooleanVar(value=True)

    gantt_popup = tk.Toplevel(root)
    gantt_popup.title("实时甘特图 · V2.14.2")
    gantt_popup.geometry("1100x620")
    gantt_popup.minsize(320, 1)
    gantt_popup.configure(background="#FBFCFD")
    gantt_popup.withdraw()
    gantt_toolbar = ttk.Frame(gantt_popup)
    gantt_toolbar.pack(fill="x", padx=6, pady=(5, 2))
    ttk.Label(gantt_toolbar, text="实时甘特图（窗口高度可自由缩放）").pack(side="left", padx=(4, 8))
    gantt_direction_button = ttk.Button(gantt_toolbar, text="游标：正放")
    gantt_direction_button.pack(side="right", padx=4)
    gantt_topmost_button = ttk.Button(gantt_toolbar, text="取消置顶")
    gantt_topmost_button.pack(side="right", padx=4)
    gantt_canvas = tk.Canvas(gantt_popup, background="#FBFCFD", highlightthickness=0)
    gantt_canvas.pack(fill="both", expand=True)
    gantt_cache = {
        "metadata": None,
        "source_image": None,
        "photo": None,
        "mask_photo": None,
        "draw_x": 0.0,
        "draw_y": 0.0,
        "draw_width": 1.0,
        "draw_height": 1.0,
        "signature": None,
        "source": "",
        "path": "",
        "next_poll": 0.0,
    }

    def series_value_at_time(series: dict[str, Any], sim_time: float) -> float | None:
        times = list(series.get("times", []) or [])
        values = list(series.get("values", []) or [])
        count = min(len(times), len(values))
        if count <= 0:
            return None
        try:
            time_values = np.asarray(times[:count], dtype=float)
            value_values = np.asarray(values[:count], dtype=float)
        except (TypeError, ValueError):
            return None
        finite = np.isfinite(time_values) & np.isfinite(value_values)
        if not np.any(finite):
            return None
        time_values, value_values = time_values[finite], value_values[finite]
        order = np.argsort(time_values)
        return float(np.interp(float(sim_time), time_values[order], value_values[order]))

    def redraw_cached_gantt() -> None:
        metadata = gantt_cache["metadata"]
        source_image = gantt_cache["source_image"]
        if metadata is None or source_image is None:
            gantt_canvas.delete("all")
            detail = gantt_cache_error or "latest_gantt.png / latest_gantt.json 不存在或无效"
            gantt_canvas.create_text(
                max(gantt_canvas.winfo_width(), 320) / 2,
                max(gantt_canvas.winfo_height(), 180) / 2,
                text=f"甘特图缓存生成失败\n{detail}", fill="#B91C1C",
                justify="center", font=("Microsoft YaHei", 12, "bold"),
            )
            return
        try:
            canvas_width = max(1, int(gantt_canvas.winfo_width()))
            canvas_height = max(1, int(gantt_canvas.winfo_height()))
            is_tk_png = isinstance(source_image, tk.PhotoImage)
            if is_tk_png:
                image_width, image_height = source_image.width(), source_image.height()
            else:
                from PIL import Image, ImageTk
                image_width, image_height = source_image.size
            # Enough for "***.***mm" and "时间：12.345s", without a wide gutter.
            value_column_width = 100
            image_area_width = max(1, canvas_width - value_column_width)
            factor = min(image_area_width / max(image_width, 1), canvas_height / max(image_height, 1))
            draw_width = max(1, int(round(image_width * factor)))
            draw_height = max(1, int(round(image_height * factor)))
            if is_tk_png:
                # Tk includes a native PNG decoder; Client 0.3.9 does not
                # require Pillow. Integer subsample is safe, with a slightly
                # less smooth preview than Pillow's LANCZOS renderer.
                scale = max(1, math.ceil(image_width / image_area_width), math.ceil(image_height / canvas_height))
                photo = source_image.subsample(scale)
                draw_width, draw_height = photo.width(), photo.height()
            else:
                resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                photo = ImageTk.PhotoImage(source_image.resize((draw_width, draw_height), resampling))
            draw_x = max(0.0, image_area_width - draw_width)
            draw_y = (canvas_height - draw_height) / 2.0
            gantt_canvas.delete("all")
            gantt_canvas.create_rectangle(
                image_area_width, 0, canvas_width, canvas_height,
                fill="#FBFCFD", outline="", tags="gantt_value_column",
            )
            gantt_canvas.create_image(draw_x, draw_y, image=photo, anchor="nw", tags="gantt_cache_image")
            gantt_cache.update(
                photo=photo, draw_x=draw_x, draw_y=draw_y,
                draw_width=float(draw_width), draw_height=float(draw_height),
            )
            update_gantt_overlay(float(current.get()))
        except Exception as exc:
            gantt_cache["metadata"] = None
            gantt_cache["source_image"] = None
            status.set(f"甘特图缓存读取失败：{exc}")
            redraw_cached_gantt()

    def load_latest_gantt_cache(*, force: bool = False) -> None:
        now_perf = time.perf_counter()
        if not force and now_perf < float(gantt_cache["next_poll"]):
            return
        gantt_cache["next_poll"] = now_perf + 0.5
        display_dir, cache_source = _select_gantt_cache_source(gantt_cache_dir, gantt_fallback_dir)
        signature = _gantt_cache_signature(display_dir)
        if signature is None:
            if force or gantt_cache.get("signature") is not None:
                gantt_cache.update(metadata=None, source_image=None, signature=None, source=cache_source, path=str(display_dir))
                redraw_cached_gantt()
            return
        if not force and signature == gantt_cache.get("signature"):
            return
        gantt_cache_png = display_dir / "latest_gantt.png"
        gantt_cache_json = display_dir / "latest_gantt.json"
        try:
            metadata = json.loads(gantt_cache_json.read_text("utf-8"))
            if metadata.get("format") not in {"MUJOCO_XML_TOOL_GANTT_CACHE", "MUJOCO_STUDIO_GANTT_CACHE"}:
                raise ValueError("甘特图缓存格式不匹配")
            try:
                from PIL import Image
            except ImportError:
                # An untouched local Client needs no third-party image package
                # to display the server's authoritative cached PNG.
                source_image = tk.PhotoImage(file=str(gantt_cache_png))
                png_size = (source_image.width(), source_image.height())
            else:
                with Image.open(gantt_cache_png) as image:
                    source_image = image.convert("RGBA").copy()
                png_size = source_image.size
            metadata = _attach_runtime_gantt_values(
                metadata, segments, drives, start_time, end_time, png_size,
            )
            gantt_cache.update(
                metadata=metadata, source_image=source_image, signature=signature,
                source=cache_source, path=str(display_dir),
            )
            print(
                "MUJOCO_STUDIO_GANTT_CACHE "
                + json.dumps({
                    "source": cache_source, "path": str(display_dir),
                    "saved_at": metadata.get("saved_at"),
                    "segment_count": metadata.get("segment_count"),
                }, ensure_ascii=False, sort_keys=True),
                flush=True,
            )
            redraw_cached_gantt()
        except Exception as exc:
            gantt_cache["metadata"] = None
            gantt_cache["source_image"] = None
            gantt_cache["signature"] = None
            gantt_cache["source"] = cache_source
            gantt_cache["path"] = str(display_dir)
            status.set(f"甘特图缓存无效：{exc}")
            redraw_cached_gantt()

    def update_gantt_overlay(sim_time: float) -> None:
        metadata = gantt_cache["metadata"]
        if metadata is None:
            return
        gantt_canvas.delete("gantt_overlay")
        image_width = max(float(metadata.get("image_width", 1.0) or 1.0), 1.0)
        image_height = max(float(metadata.get("image_height", 1.0) or 1.0), 1.0)
        draw_x, draw_y = float(gantt_cache["draw_x"]), float(gantt_cache["draw_y"])
        draw_width, draw_height = float(gantt_cache["draw_width"]), float(gantt_cache["draw_height"])
        scale_x, scale_y = draw_width / image_width, draw_height / image_height
        axis_min = float(metadata.get("axis_min", 0.0) or 0.0)
        axis_max = float(metadata.get("axis_max", axis_min + 1.0) or axis_min + 1.0)
        chart_left = float(metadata.get("chart_left", 0.0) or 0.0)
        chart_right = float(metadata.get("chart_right", image_width) or image_width)
        chart_top = float(metadata.get("chart_top", 0.0) or 0.0)
        chart_bottom = float(metadata.get("chart_bottom", image_height) or image_height)
        time_offset = float(metadata.get("simulation_time_offset", 0.0) or 0.0)
        gantt_time = float(sim_time) - time_offset
        ratio = min(max((gantt_time - axis_min) / max(axis_max - axis_min, 1e-12), 0.0), 1.0)
        if gantt_reverse.get():
            ratio = 1.0 - ratio
        cursor_x = draw_x + (chart_left + ratio * (chart_right - chart_left)) * scale_x
        mask_left = draw_x + chart_left * scale_x
        mask_top = draw_y + chart_top * scale_y
        mask_bottom = draw_y + chart_bottom * scale_y
        mask_width = max(0, int(round(cursor_x - mask_left)))
        mask_height = max(0, int(round(mask_bottom - mask_top)))
        if mask_width > 0 and mask_height > 0:
            try:
                from PIL import Image, ImageTk
                mask_image = Image.new("RGBA", (mask_width, mask_height), (56, 189, 248, 26))
                mask_photo = ImageTk.PhotoImage(mask_image)
                gantt_cache["mask_photo"] = mask_photo
                gantt_canvas.create_image(
                    mask_left, mask_top, image=mask_photo, anchor="nw", tags="gantt_overlay",
                )
            except Exception:
                gantt_canvas.create_rectangle(
                    mask_left, mask_top, cursor_x, mask_bottom,
                    fill="#38BDF8", stipple="gray12", outline="", tags="gantt_overlay",
                )
        gantt_canvas.create_line(
            cursor_x, mask_top, cursor_x, mask_bottom,
            fill="#0284C7", width=2, tags="gantt_overlay",
        )
        value_x = min(float(gantt_canvas.winfo_width()) - 6, draw_x + draw_width + 94)
        for row in list(metadata.get("rows", []) or []):
            row_y = draw_y + float(row.get("center", 0.0) or 0.0) * scale_y
            active = any(
                float(segment.get("start", 0.0) or 0.0) - 1e-9 <= gantt_time
                <= float(segment.get("end", 0.0) or 0.0) + 1e-9
                for segment in list(row.get("segments", []) or [])
            )
            values = []
            for series in list(row.get("value_series", []) or []):
                value = series_value_at_time(series, float(sim_time))
                if value is not None:
                    unit = str(series.get("unit", "") or "").replace("deg", "°")
                    values.append(f"{value:.3f}{unit}")
            if values:
                gantt_canvas.create_text(
                    value_x, row_y, text=" / ".join(values), anchor="e",
                    fill="#DC2626" if active else "#000000",
                    font=("Microsoft YaHei", 11, "bold" if active else "normal"),
                    tags="gantt_overlay",
                )
        gantt_canvas.create_text(
            value_x, draw_y + draw_height - 8, text=f"时间：{float(sim_time):.3f}s",
            anchor="se", fill="#111827", font=("Microsoft YaHei", 12, "bold"),
            tags="gantt_overlay",
        )

    def set_gantt_topmost() -> None:
        gantt_topmost.set(not gantt_topmost.get())
        gantt_popup.attributes("-topmost", bool(gantt_topmost.get()))
        gantt_topmost_button.configure(text="取消置顶" if gantt_topmost.get() else "窗口置顶")

    def toggle_gantt_direction() -> None:
        gantt_reverse.set(not gantt_reverse.get())
        gantt_direction_button.configure(text="游标：倒放" if gantt_reverse.get() else "游标：正放")
        if gantt_cache["metadata"] is not None:
            update_gantt_overlay(float(current.get()))

    def toggle_gantt() -> None:
        assign_control("gantt_enabled", bool(gantt_enabled.get()))
        if gantt_enabled.get():
            gantt_popup.deiconify()
            gantt_popup.attributes("-topmost", bool(gantt_topmost.get()))
            gantt_popup.lift()
            gantt_popup.after_idle(lambda: load_latest_gantt_cache(force=True))
        else:
            gantt_popup.withdraw()

    def close_gantt() -> None:
        gantt_enabled.set(False)
        gantt_popup.withdraw()
        assign_control("gantt_enabled", False)

    def set_time_from_gantt(event: Any) -> None:
        metadata = gantt_cache["metadata"]
        if metadata is not None:
            image_width = max(float(metadata.get("image_width", 1.0) or 1.0), 1.0)
            chart_left = float(metadata.get("chart_left", 0.0) or 0.0)
            chart_right = float(metadata.get("chart_right", image_width) or image_width)
            scale_x = float(gantt_cache["draw_width"]) / image_width
            plot_left = float(gantt_cache["draw_x"]) + chart_left * scale_x
            plot_right = float(gantt_cache["draw_x"]) + chart_right * scale_x
            axis_min = float(metadata.get("axis_min", 0.0) or 0.0)
            axis_max = float(metadata.get("axis_max", axis_min + 1.0) or axis_min + 1.0)
            time_offset = float(metadata.get("simulation_time_offset", 0.0) or 0.0)
        else:
            width = max(gantt_canvas.winfo_width(), 320)
            plot_left, plot_right = 120.0, float(width - 20)
            axis_min, axis_max, time_offset = start_time, end_time, 0.0
        ratio = min(max((float(event.x) - plot_left) / max(plot_right - plot_left, 1.0), 0.0), 1.0)
        if gantt_reverse.get():
            ratio = 1.0 - ratio
        current.set(min(max(axis_min + ratio * (axis_max - axis_min) + time_offset, start_time), end_time))
        if metadata is not None:
            update_gantt_overlay(float(current.get()))

    gantt_topmost_button.configure(command=set_gantt_topmost)
    gantt_direction_button.configure(command=toggle_gantt_direction)
    gantt_popup.protocol("WM_DELETE_WINDOW", close_gantt)
    gantt_canvas.bind("<ButtonPress-1>", set_time_from_gantt)
    gantt_canvas.bind("<B1-Motion>", set_time_from_gantt)
    gantt_canvas.bind("<Configure>", lambda _event: redraw_cached_gantt())

    chart_times = _strict_result_time_grid(start_time, end_time, timestep)
    drive_series = {drive_id: [] for drive_id in drive_by_id}
    joint_series = {joint_id: [] for joint_id in addresses}
    crank_by_joint = {str(item.get("joint_id", "")): item.get("crank_meta") for item in drives if item.get("crank_meta")}
    for sample_time in chart_times:
        drive_sample = drive_positions(segments, float(sample_time))
        joint_sample = joint_positions(segments, float(sample_time))
        joint_sample = {joint_id:_crank_displacement(crank_by_joint[joint_id], value) if joint_id in crank_by_joint else value for joint_id,value in joint_sample.items()}
        for drive_id in drive_series:
            drive_series[drive_id].append(float(drive_sample.get(drive_id, 0.0)))
        for joint_id in joint_series:
            joint_series[joint_id].append(float(joint_sample.get(joint_id, 0.0)))

    def transform_series(values: list[float], operation: str) -> np.ndarray:
        result = np.asarray(values, dtype=float)
        if operation == "integral":
            delta = np.diff(chart_times, prepend=chart_times[0])
            return np.cumsum(result * delta)
        order = {"d1": 1, "d2": 2, "d3": 3}.get(operation, 0)
        if order and len(chart_times) < 2:
            return np.zeros_like(result)
        for _index in range(order):
            result = np.gradient(result, chart_times)
        return result

    def axis_curve_data() -> list[tuple[str, list[tuple[str, str, np.ndarray]]]]:
        output = []
        for axis in payload.get("result_layout", {}).get("axes", []):
            curves = []
            for curve in axis.get("curves", []):
                source = str(curve.get("source", ""))
                source_values = drive_series.get(source.removeprefix("drive:")) if source.startswith("drive:") else None
                if source.startswith("joint:"):
                    source_values = joint_series.get(source.removeprefix("joint:"))
                if source_values is not None:
                    curves.append((
                        str(curve.get("label", source)), str(curve.get("color", "#018c94")),
                        transform_series(source_values, str(curve.get("operation", "raw"))),
                    ))
            combine = str(axis.get("combine", "none"))
            if curves and combine in {"sum", "difference"}:
                combined = curves[0][2].copy()
                for _label, _color, values in curves[1:]:
                    combined = combined + values if combine == "sum" else combined - values
                combined_curve = (
                    f"{axis.get('name', '坐标系')} · {'求和' if combine == 'sum' else '求差'}",
                    "#C73849", combined,
                )
                curves = [*curves, combined_curve] if axis.get("keep_operands", False) else [combined_curve]
            output.append((str(axis.get("name", "坐标系")), curves))
        return output

    def draw_axes_panel(time_s: float) -> None:
        canvas = axes_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 800)
        height = max(canvas.winfo_height(), 220)
        data_sets = axis_curve_data()
        if not data_sets:
            canvas.create_text(18, 18, anchor="nw", text="请先在仿真结果查看中预设坐标系和曲线", fill="#555")
            return
        row_height = height / len(data_sets)
        plot_left, plot_right = 74, width - 18
        center_x = (plot_left + plot_right) / 2
        cursor_base = plot_left + (plot_right - plot_left) * (time_s - start_time) / max(end_time - start_time, 1e-12)
        cursor_x = center_x + (cursor_base - center_x) * float(axes_scale_x.get())
        sample_index = int(np.argmin(np.abs(chart_times - time_s)))
        for row_index, (axis_name, curves) in enumerate(data_sets):
            top = row_index * row_height
            canvas.create_text(8, top + 8, anchor="nw", text=axis_name, font=("Microsoft YaHei", axes_font.get(), "bold"), fill="#111")
            values = np.concatenate([curve[2] for curve in curves]) if curves else np.asarray([])
            if not len(values):
                continue
            low, high = float(np.min(values)), float(np.max(values))
            span = max(high - low, 1e-12)
            plot_top, plot_bottom = top + 30, top + row_height - 30
            for tick in range(5):
                x = plot_left + (plot_right - plot_left) * tick / 4
                tick_time = start_time + (end_time - start_time) * tick / 4
                canvas.create_line(x, plot_top, x, plot_bottom, fill="#e2e5e9")
                canvas.create_text(x, plot_bottom + 7, anchor="n", text=f"{tick_time:.2f}", font=("Microsoft YaHei", max(6, axes_font.get() - 2)), fill="#555")
            for tick in range(3):
                y = plot_bottom - (plot_bottom - plot_top) * tick / 2
                tick_value = low + span * tick / 2
                canvas.create_line(plot_left, y, plot_right, y, fill="#e2e5e9")
                canvas.create_text(plot_left - 5, y, anchor="e", text=f"{tick_value:.3g}", font=("Microsoft YaHei", max(6, axes_font.get() - 2)), fill="#555")
            canvas.create_line(plot_left, plot_bottom, plot_right, plot_bottom, fill="#30343a", width=1)
            canvas.create_line(plot_left, plot_top, plot_left, plot_bottom, fill="#30343a", width=1)
            canvas.create_text((plot_left + plot_right) / 2, plot_bottom + 22, text="时间 (s)", font=("Microsoft YaHei", max(6, axes_font.get() - 1), "bold"), fill="#333")
            canvas.create_text(7, (plot_top + plot_bottom) / 2, anchor="w", text="数值", font=("Microsoft YaHei", max(6, axes_font.get() - 1), "bold"), fill="#333")
            for curve_index, (label, color, series) in enumerate(curves):
                points = []
                for index, value in enumerate(series):
                    base_x = plot_left + (plot_right - plot_left) * index / max(len(series) - 1, 1)
                    x = center_x + (base_x - center_x) * float(axes_scale_x.get())
                    base_y = plot_bottom - (plot_bottom - plot_top) * (float(value) - low) / span
                    center_y = (plot_top + plot_bottom) / 2
                    y = center_y + (base_y - center_y) * float(axes_scale_y.get())
                    points.extend((x, y))
                if len(points) >= 4:
                    canvas.create_line(*points, fill=color, width=2)
                canvas.create_text(
                    min(cursor_x + 5, width - 190), plot_top + 3 + curve_index * 14,
                    anchor="nw", text=f"{label}: {float(series[sample_index]):.3f}",
                    font=("Microsoft YaHei", axes_font.get(), "bold"), fill="#d12b3f",
                )
            canvas.create_line(cursor_x, plot_top, cursor_x, plot_bottom, fill="#d12b3f", width=2)
            canvas.create_text(min(cursor_x + 4, width - 85), plot_bottom - 3, anchor="sw", text=f"{time_s:.3f}s", font=("Microsoft YaHei", axes_font.get(), "bold"), fill="#d12b3f")

    perf = _ViewerPerfMeter(str(profile.get("name", "unknown")))
    distance_worker = (
        _AsyncDistanceWorker(
            mujoco, model, distance_pairs,
            low_latency=bool(profile.get("measurement_low_latency", False)),
            query_budget_per_pair=int(profile.get("measurement_query_budget_per_pair", 4096)),
            total_query_budget=int(profile.get("measurement_total_query_budget", 20000)),
            pair_workers=int(profile.get("measurement_pair_workers", 4)),
        )
        if bool(profile.get("measurement_async", False)) and distance_pairs else None
    )
    pair_results: list[tuple[float, np.ndarray | None]] = [
        (float("inf"), None) for _pair in distance_pairs
    ]
    distance_revision = 0
    measurement_age_seconds = 0.0
    measurement_compute_seconds = 0.0
    last_measure_submit = 0.0
    measurement_rate_started = time.perf_counter()
    measurement_completed = 0
    last_forward = 0.0
    last_sync = 0.0
    last_ui = 0.0
    site_group_visible = {"value": None}
    if distance_site_group is not None:
        _set_viewer_site_group(viewer, distance_site_group, bool(scatter.get()))
        site_group_visible["value"] = bool(scatter.get())
    clean_shutdown = False
    # The native GLFW window is owned by the existing passive Viewer; do not
    # replace its callbacks (which would break rotation, zoom and other controls).
    # Some platform builds do not expose the window: in that case stay native.
    try:
        import glfw as _viewer_glfw  # type: ignore
    except ImportError:
        _viewer_glfw = None
    _viewer_window = getattr(viewer, "_window", None)
    if _viewer_window is None:
        _viewer_sim_ref = getattr(viewer, "_sim", None)
        _viewer_sim = _viewer_sim_ref() if callable(_viewer_sim_ref) else _viewer_sim_ref
        _viewer_window = getattr(_viewer_sim, "_window", None)
    previous_camera_lookat = None
    previous_camera_pose = None
    inferred_pan_streak = 0
    try:
        try:
            center = scene_mesh_center
            viewer.cam.lookat[:] = [float(center[0]), float(center[1]), float(center[2])]
            viewer.cam.distance = max(float(model.stat.extent) * 2.2, 0.5)
            viewer.cam.azimuth = 140.0
            viewer.cam.elevation = -20.0
            pose = [float(value) for value in str(control.get("camera_initial_pose", "")).replace("；", ",").replace(";", ",").split(",") if value.strip()]
            if len(pose) == 6:
                position = np.asarray(pose[:3], dtype=float) * 0.001
                direction = np.asarray(pose[3:], dtype=float)
                direction /= max(float(np.linalg.norm(direction)), 1e-12)
                viewer.cam.lookat[:] = position + direction * float(viewer.cam.distance)
                viewer.cam.azimuth = math.degrees(math.atan2(-direction[1], -direction[0]))
                viewer.cam.elevation = math.degrees(math.asin(min(max(-direction[2], -1.0), 1.0)))
            set_view_preset("front_view")
            # Camera preset synchronization can rebuild MuJoCo's render camera.
            # Apply projection afterwards and once more after the first sync so
            # the checked state and the actual first rendered frame agree.
            set_orthographic(bool(orthographic_var.get()), persist=False)
            viewer.sync()
            set_orthographic(bool(orthographic_var.get()), persist=False)
            model.vis.quality.shadowsize = 0
        except Exception:
            pass
        last_tick = time.perf_counter()
        last_text = 0.0
        while viewer.is_running() and alive["value"]:
            frame_started = time.perf_counter()
            ui_started = frame_started
            ui_hz = float(profile.get("ui_hz", 0.0))
            if ui_hz <= 0.0 or frame_started - last_ui >= 1.0 / ui_hz:
                try:
                    root.update_idletasks()
                    root.update()
                except tk.TclError:
                    break
                last_ui = frame_started
                perf.add("ui", time.perf_counter() - ui_started)
            now = time.perf_counter()
            delta = now - last_tick
            last_tick = now
            poll_started = time.perf_counter()
            if project_json_path is not None and (remote_poller is not None or now - last_remote_poll["value"] >= float(profile.get("remote_poll_interval_s", 0.25))):
                if remote_poller is not None:
                    incoming, remote_poll_revision = remote_poller.snapshot(remote_poll_revision)
                else:
                    incoming = fetch_remote_control()
                    last_remote_poll["value"] = now
                perf.add("poll", time.perf_counter() - poll_started)
                if incoming is not None:
                    if incoming.get("time_s") != remote_control.get("time_s") and not dragging["value"]:
                        current.set(min(max(float(incoming.get("time_s", start_time)), start_time), end_time))
                    if incoming.get("playing") != remote_control.get("playing"):
                        playing["value"] = bool(incoming.get("playing"))
                    if incoming.get("direction") != remote_control.get("direction"):
                        playing["direction"] = float(incoming.get("direction", 1))
                    if incoming.get("speed") != remote_control.get("speed"):
                        syncing["value"] = True
                        speed.set(float(incoming.get("speed", 1.0)))
                        syncing["value"] = False
                    mapping = [
                        ("show_scatter", scatter), ("show_distance_lines", show_lines),
                        ("show_distance_labels", show_labels), ("adaptive_display", adaptive),
                    ]
                    for field, variable in mapping:
                        if incoming.get(field) != remote_control.get(field):
                            variable.set(bool(incoming.get(field)))
                    if incoming.get("adaptive_threshold_mm") != remote_control.get("adaptive_threshold_mm"):
                        adaptive_mm.set(float(incoming.get("adaptive_threshold_mm", 25.0)))
                    if incoming.get("motor_mode") != remote_control.get("motor_mode"):
                        set_motor_mode(bool(incoming.get("motor_mode")), persist=False)
                    if incoming.get("orthographic_view") != remote_control.get("orthographic_view"):
                        orthographic_var.set(bool(incoming.get("orthographic_view", False)))
                        set_orthographic(bool(orthographic_var.get()), persist=False)
                    incoming_decoupled = set(incoming.get("decoupled_drive_ids", []))
                    if incoming_decoupled != set(remote_control.get("decoupled_drive_ids", [])):
                        expanded_incoming: set[str] = set()
                        for drive_id in incoming_decoupled:
                            expanded_incoming.update(
                                mapping_family_by_drive.get(drive_id, frozenset({drive_id}))
                            )
                        decoupled.clear(); decoupled.update(expanded_incoming)
                        control["decoupled_drive_ids"] = sorted(decoupled)
                        for drive_id, label in manual_labels.items():
                            label.set(mapping_label(drive_id))
                    for drive_id, value in incoming.get("motor_values", {}).items():
                        old_value = remote_control.get("motor_values", {}).get(drive_id)
                        if value != old_value and drive_id in manual_vars:
                            manual_values[drive_id] = float(value)
                            syncing["value"] = True; manual_vars[drive_id].set(float(value)); syncing["value"] = False
                    incoming_trajectory = dict(incoming.get("trajectory", {}))
                    old_trajectory = dict(remote_control.get("trajectory", {}))
                    if incoming_trajectory != old_trajectory:
                        control["trajectory"] = incoming_trajectory
                    if incoming_trajectory.get("sample_hz") != old_trajectory.get("sample_hz"):
                        frequency.set(float(incoming_trajectory.get("sample_hz", 20.0)))
                    if incoming_trajectory.get("point_size") != old_trajectory.get("point_size"):
                        point_size.set(float(incoming_trajectory.get("point_size", 1.0)))
                    if incoming_trajectory.get("color") != old_trajectory.get("color"):
                        track_color.set(str(incoming_trajectory.get("color", "#018c94")))
                    if incoming_trajectory.get("selected_meshes") != old_trajectory.get("selected_meshes"):
                        syncing["value"] = True
                        mesh_list.selection_clear(0, "end")
                        for index, filename in enumerate(filename_geoms):
                            if filename in incoming_trajectory.get("selected_meshes", []):
                                mesh_list.selection_set(index)
                        syncing["value"] = False
                    clear_revision = int(incoming_trajectory.get("clear_revision", 0))
                    if clear_revision != last_clear_revision["value"]:
                        trajectory_points.clear(); last_clear_revision["value"] = clear_revision
                    probe_revision = int(incoming_trajectory.get("centroid_probe_revision", 0))
                    if probe_revision != last_probe_revision["value"]:
                        centroid = _selected_centroid(model, data, selected_geom_ids(), geom_masses)
                        if centroid is not None:
                            centroid_text.set(
                                f"整体质心：X {centroid[0] * 1000:.3f} / Y {centroid[1] * 1000:.3f} / "
                                f"Z {centroid[2] * 1000:.3f} mm"
                            )
                        last_probe_revision["value"] = probe_revision
                    if incoming.get("gantt_enabled") != remote_control.get("gantt_enabled"):
                        gantt_enabled.set(bool(incoming.get("gantt_enabled", False)))
                        toggle_gantt()
                    remote_control = incoming
                    refresh_buttons()
            time_s = float(current.get())
            if playing["value"] and not dragging["value"]:
                time_s += delta * playing["direction"] * playback_speed_value()
                if time_s > end_time:
                    if loop and end_time > start_time:
                        time_s = start_time
                    else:
                        time_s, playing["value"] = end_time, False
                elif time_s < start_time:
                    if loop and end_time > start_time:
                        time_s = end_time
                    else:
                        time_s, playing["value"] = start_time, False
                current.set(time_s)
                refresh_buttons()

            motor_apply_started = time.perf_counter()
            if motor_mode["value"]:
                # Pointer motion stays entirely inside Tk.  Sampling active DoubleVars once
                # per rendered frame bounds Python work even if the OS emits hundreds of
                # mouse-motion events between two frames.
                for drive_id in tuple(manual_dragging):
                    variable = manual_vars.get(drive_id)
                    if variable is not None:
                        motor_changed(drive_id, str(variable.get()))
                apply_pending_motor_inputs()
            if not motor_mode["value"] and pending_manual_inputs:
                pending_manual_inputs.clear()
            perf.add("motor_apply", time.perf_counter() - motor_apply_started)

            timeline_drives = drive_positions(segments, time_s)
            contributions = dict(timeline_drives)
            if motor_mode["value"] and decoupled:
                # One mapping family has one manual degree of freedom: its root source.
                # Followers are deterministic projections, never independent stale overrides.
                manual_roots = {mapping_root_by_drive.get(drive_id, drive_id) for drive_id in decoupled}
                for root_id in manual_roots:
                    contributions[root_id] = manual_values.get(
                        root_id, contributions.get(root_id, 0.0),
                    )
                contributions = _viewer_apply_mapping_overrides(
                    contributions, mapping_segments_by_drive, drive_by_id, drives_by_joint,
                )
                motor_values = control.get("motor_values")
                if not isinstance(motor_values, dict):
                    motor_values = {}
                    control["motor_values"] = motor_values
                # Keep both source and companion UI/session values coherent with the
                # projected physical command. This is in-place and only touches active
                # linked members; it does not reintroduce the old whole-dict copy path.
                for drive_id in decoupled.intersection(linked_mapping_drive_ids):
                    if drive_id in contributions:
                        linked_value = float(contributions[drive_id])
                        manual_values[drive_id] = linked_value
                        motor_values[drive_id] = linked_value

            # The native Tk Scale already follows the pointer while it is being dragged.
            # Project only non-decoupled follower values back into widgets at a bounded
            # UI rate and only when the displayed value materially changed.  This avoids
            # repainting every motor scale on every 60 Hz render frame.
            motor_ui_hz = min(max(float(profile.get("motor_ui_hz", 30.0)), 1.0), 60.0)
            motor_ui_due = (
                motor_mode["value"]
                and now - last_motor_ui_sync["value"] >= 1.0 / motor_ui_hz
            )
            if motor_ui_due:
                syncing["value"] = True
                try:
                    for drive_id, variable in manual_vars.items():
                        if drive_id in pending_manual_inputs or drive_id in manual_dragging:
                            continue
                        if drive_id in decoupled and drive_id not in linked_mapping_drive_ids:
                            continue
                        value = float(contributions.get(drive_id, 0.0))
                        manual_values[drive_id] = value
                        previous_display = manual_display_values.get(drive_id)
                        threshold = max(float(manual_resolutions.get(drive_id, 0.001)) * 0.25, 1e-12)
                        if previous_display is None or abs(value - previous_display) >= threshold:
                            variable.set(value)
                            manual_display_values[drive_id] = value
                finally:
                    syncing["value"] = False
                last_motor_ui_sync["value"] = now

            trajectory_frame = sample_trajectory(time_s)
            if trajectory_frame is not None:
                # V2.5.0 Viewer is a trajectory player: normal playback never calls mj_step
                # and never recomputes dynamics. Decoupled motors are the only intentional
                # position-level override and remain pure kinematic control.
                data.qpos[:] = trajectory_frame
                if motor_mode["value"] and decoupled:
                    for drive_id in decoupled:
                        drive = drive_by_id.get(drive_id)
                        if not drive:
                            continue
                        joint_id = str(drive.get("joint_id", ""))
                        target = addresses.get(joint_id)
                        if not target:
                            continue
                        display_value = float(contributions.get(drive_id, 0.0))
                        if joint_id in crank_by_joint:
                            display_value = _crank_displacement(crank_by_joint[joint_id], display_value)
                        address, slide = target
                        offset = display_value * 0.001 if slide else math.radians(display_value)
                        data.qpos[address] = base_qpos[address] + offset
            else:
                # Compatibility with schema 1-3 bundles. Schema 4 always supplies trajectory.npz.
                joint_values: dict[str, float] = {}
                for drive_id, value in contributions.items():
                    drive = drive_by_id.get(drive_id)
                    if drive:
                        joint_id = str(drive.get("joint_id", ""))
                        if joint_id:
                            joint_values[joint_id] = joint_values.get(joint_id, 0.0) + value
                joint_values = {joint_id:_crank_displacement(crank_by_joint[joint_id], value) if joint_id in crank_by_joint else value for joint_id,value in joint_values.items()}
                data.qpos[:] = base_qpos
                for joint_id, display_value in joint_values.items():
                    target = addresses.get(joint_id)
                    if target:
                        address, slide = target
                        offset = display_value * 0.001 if slide else math.radians(display_value)
                        data.qpos[address] = base_qpos[address] + offset
            if closure_runtime is not None and bool(getattr(closure_runtime, "enabled", False)):
                closure_started = time.perf_counter()
                (
                    closure_previous_qpos["value"],
                    closure_previous_time_s["value"],
                    closure_runtime_status["value"],
                ) = _enforce_viewer_kinematic_closure(
                    mujoco, model, data, closure_runtime, closure_solver,
                    driven_joint_ids=active_drive_joint_ids,
                    previous_qpos=closure_previous_qpos["value"],
                    previous_time_s=closure_previous_time_s["value"],
                    time_s=time_s, timestep=timestep,
                )
                perf.add("closure", time.perf_counter() - closure_started)

            forward_hz = float(profile.get("forward_hz", 0.0))
            if forward_hz <= 0.0 or now - last_forward >= 1.0 / forward_hz:
                forward_started = time.perf_counter()
                mujoco.mj_forward(model, data)
                perf.add("forward", time.perf_counter() - forward_started)
                last_forward = now

            try:
                measurement_hz = min(max(float(profile.get("measurement_hz", 20.0)), 1.0), 60.0)
            except (TypeError, ValueError):
                measurement_hz = 20.0
            measurement_due = measurement_hz <= 0.0 or now - last_measure_submit >= 1.0 / measurement_hz
            if bool(profile.get("disable_measurement", False)):
                pair_results = [(float("inf"), None) for _pair in distance_pairs]
            elif distance_worker is not None:
                if measurement_due:
                    distance_worker.submit(data.qpos)
                    last_measure_submit = now
                async_result, distance_revision, async_measure_seconds, measurement_age_seconds = distance_worker.snapshot(distance_revision)
                if async_result is not None:
                    measurement_completed += 1
                    measurement_compute_seconds = async_measure_seconds
                    perf.add("measure", async_measure_seconds)
                    for pair_index, (measured, fromto, points_a, points_b) in enumerate(async_result):
                        pair_results[pair_index] = (measured, fromto)
                        if points_a is not None:
                            distance_pairs[pair_index]["_async_display_points_a"] = points_a
                        if points_b is not None:
                            distance_pairs[pair_index]["_async_display_points_b"] = points_b
            elif measurement_due:
                measure_started = time.perf_counter()
                pair_results = [
                    _measure_pair(mujoco, model, data, pair) for pair in distance_pairs
                ]
                perf.add("measure", time.perf_counter() - measure_started)
                last_measure_submit = now
                measurement_completed += 1

            measurement_rate_elapsed = now - measurement_rate_started
            if measurement_rate_elapsed >= 1.0:
                actual_hz = measurement_completed / max(measurement_rate_elapsed, 1e-9)
                measurement_actual_var.set(
                    f"实际：{actual_hz:.1f} Hz / 计算：{measurement_compute_seconds * 1000.0:.0f} ms / "
                    f"延迟：{measurement_age_seconds * 1000.0:.0f} ms"
                )
                measurement_rate_started = now
                measurement_completed = 0

            overlay_started = time.perf_counter()
            desired_scatter = bool(scatter.get())
            if distance_site_group is not None and site_group_visible["value"] != desired_scatter:
                _set_viewer_site_group(viewer, distance_site_group, desired_scatter)
                site_group_visible["value"] = desired_scatter
            overlay_scene = viewer.user_scn
            overlay_scene.ngeom = 0
            pair_text: list[str] = []
            for pair_index, pair in enumerate(distance_pairs):
                measured, fromto = pair_results[pair_index]
                finite = math.isfinite(measured)
                threshold = max(float(adaptive_mm.get()), 0.1)
                visible = finite and (not adaptive.get() or measured * 1000.0 <= threshold)
                if pair.get("site_backend"):
                    # Adaptive visibility is pair-specific. Global scatter uses
                    # the reserved site group when available; otherwise alpha
                    # also carries the global show/hide state.
                    site_visible = visible if distance_site_group is not None else (bool(scatter.get()) and visible)
                    _set_distance_site_visibility(model, pair, site_visible)
                elif scatter.get() and visible:
                    runtime = pair.get("_distance_runtime", {})
                    # Measurement keeps the complete sampled cloud (up to the
                    # configured 20k/object), but visualization uses a stable
                    # cached subset. Recreating 10k+ mjvGeom spheres every 60 Hz
                    # was the source of the apparent animation freeze.
                    points_a = pair.get("_async_display_points_a") if distance_worker is not None else runtime.get("display_points_a")
                    points_b = pair.get("_async_display_points_b") if distance_worker is not None else runtime.get("display_points_b")
                    if points_a is None:
                        raw = np.asarray(runtime.get("points_a", np.empty((0, 3))), dtype=float)
                        step = max(1, int(math.ceil(len(raw) / 2500)))
                        points_a = raw[::step]
                        runtime["display_points_a"] = points_a
                    if points_b is None:
                        raw = np.asarray(runtime.get("points_b", np.empty((0, 3))), dtype=float)
                        step = max(1, int(math.ceil(len(raw) / 2500)))
                        points_b = raw[::step]
                        runtime["display_points_b"] = points_b
                    _add_points(mujoco, overlay_scene, points_a, (*_DISTANCE_SITE_COLOR_A, _DISTANCE_SITE_ALPHA))
                    _add_points(mujoco, overlay_scene, points_b, (*_DISTANCE_SITE_COLOR_B, _DISTANCE_SITE_ALPHA))
                if show_lines.get() and visible and fromto is not None:
                    _add_capsule(mujoco, overlay_scene, fromto, measured < 0.0)
                value_text = (
                    f"{measured * 1000.0:.3f} mm"
                    if finite else f"> {pair['distmax'] * 1000.0:.1f} mm"
                )
                if show_labels.get() and visible and fromto is not None:
                    _add_label(mujoco, overlay_scene, fromto, value_text)
                pair_text.append(f"{pair['name']}: {value_text}")
                if now - last_text >= 0.08:
                    pair_vars[pair["name"]].set(
                        f"{pair['name']}: {value_text}  |  动画撒点间距 {pair['animation_spacing_mm']:.3g} mm"
                    )
            trajectory_cfg = dict(control.get("trajectory", {}))
            centroid = _selected_centroid(model, data, selected_geom_ids(), geom_masses)
            if bool(trajectory_cfg.get("recording", False)) and centroid is not None:
                _append_trajectory_point(
                    trajectory_points, centroid, float(trajectory_cfg.get("sample_hz", frequency.get())), now,
                )
            if trajectory_points:
                color = _hex_rgba(str(trajectory_cfg.get("color", track_color.get())))
                radius = max(float(trajectory_cfg.get("point_size", point_size.get())) * 0.0015, 0.00015)
                points = np.asarray([point[:3] for point in trajectory_points], dtype=float)
                _add_points(mujoco, overlay_scene, points, color, radius=radius)
            if gantt_enabled.get():
                load_latest_gantt_cache()
                if gantt_cache["metadata"] is not None:
                    update_gantt_overlay(time_s)
            perf.add("overlay", time.perf_counter() - overlay_started)
            sync_hz = float(profile.get("sync_hz", 0.0))
            if sync_hz <= 0.0 or now - last_sync >= 1.0 / sync_hz:
                sync_started = time.perf_counter()
                viewer.sync()
                perf.add("sync", time.perf_counter() - sync_started)
                last_sync = now
            # V2.16.7: 6.67x the *native* lookat delta in orthographic mode.
            # Native MuJoCo scales this motion by 0.15. Do not rely on the
            # private `_window` property existing: official passive Viewer
            # exposes cam/lock/sync but not a public GLFW window handle.
            # Windows can detect a right-press on the focused native GLFW HWND;
            # other platforms infer continuous lookat-only drag conservatively.
            right_pan_button = (
                _viewer_right_mouse_pressed(_viewer_glfw, _viewer_window)
                if orthographic["value"] else False
            )
            camera_lock = getattr(viewer, "lock", None)
            with (camera_lock() if callable(camera_lock) else nullcontext()):
                if camera_pan_state["rebase"]:
                    previous_camera_lookat = None
                    previous_camera_pose = None
                    inferred_pan_streak = 0
                    camera_pan_state["rebase"] = False
                active_pan, inferred_pan_streak = _classify_orthographic_pan(
                    viewer.cam, previous_camera_lookat, previous_camera_pose,
                    right_button=right_pan_button,
                    inferred_streak=inferred_pan_streak,
                    free_camera_type=int(mujoco.mjtCamera.mjCAMERA_FREE),
                )
                previous_camera_lookat = _amplify_orthographic_pan(
                    viewer.cam, previous_camera_lookat,
                    active=bool(orthographic["value"] and active_pan),
                    factor=_ORTHOGRAPHIC_PAN_PIXEL_GAIN,
                )
                previous_camera_pose = _camera_pan_signature(viewer.cam)
            if now - last_text >= 0.08:
                mode = "电机控制" if motor_mode["value"] else ("播放" if playing["value"] else "暂停")
                status.set(
                    f"{mode} | {time_s:.3f} / {end_time:.3f} s | {playback_speed_value():.1f}x"
                    + status_suffix + closure_runtime_status["value"]
                )
                time_label.configure(text=f"{time_s:.3f}s")
                try:
                    if hasattr(viewer, "add_overlay"):
                        overlay_text = "\n".join([f"Time {time_s:.3f}s", *pair_text])
                        viewer.add_overlay("topright", "V2.14.2", overlay_text)
                except Exception:
                    pass
                last_text = now
            before_sleep = time.perf_counter()
            target_frame = 1.0 / max(float(profile.get("target_fps", 60.0)), 1.0)
            if bool(profile.get("correct_frame_pacing", False)):
                sleep_seconds = max(0.0, target_frame - (before_sleep - frame_started))
            else:
                sleep_seconds = target_frame
            if sleep_seconds > 0.0:
                time.sleep(sleep_seconds)
            frame_finished = time.perf_counter()
            perf.add("sleep", frame_finished - before_sleep)
            perf.add("frame", frame_finished - frame_started)
            perf.frame(frame_finished)
        clean_shutdown = True
    finally:
        if distance_worker is not None:
            distance_worker.close()
        if remote_poller is not None:
            remote_poller.close()
        if clean_shutdown:
            print("MUJOCO_STUDIO_VIEWER_CLEAN_SHUTDOWN", flush=True)
        try:
            root.destroy()
        except Exception:
            pass
        # Closing an already closed GLFW window can double-destroy native
        # resources on Windows and return 0xC0000005 after a normal user exit.
        try:
            if not clean_shutdown or viewer.is_running():
                viewer.close()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MuJoCo Studio native viewer runner")
    parser.add_argument("scene")
    parser.add_argument("drives")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--trajectory", default="")
    parser.add_argument("--gantt-cache-dir")
    parser.add_argument("--asset-map")
    args = parser.parse_args(argv)
    run_viewer(
        args.scene, args.drives, loop=args.loop, playback_speed=args.speed, trajectory_path=(args.trajectory or None),
        gantt_cache_path=args.gantt_cache_dir, asset_map_path=args.asset_map,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
