"""MuJoCo Lab V2.16.11.6: immutable timeline identities and sampled-frame UDP protocol.

Reuses ProjectSpec/resolve_schedule.  No second project data store or business Tool.
The server, not arbitrary browser input, constructs UDP state from the same
baked animation sample arrays used by the offline HTML player.
"""
from __future__ import annotations

import base64
import bisect
import hashlib
import ipaddress
import json
import math
import socket
import struct
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from .models import ProjectSpec
from .motion import latest_drive_stop_time, resolve_schedule

PROTOCOL_VERSION = "1.0"
LAB_VERSION = "2.16.11.6"
REQUIRED_FIELDS = ("protocol_version", "object_id", "run_id", "sequence_id", "type")
STATE_OPTIONAL = ("is_moving", "playback_state", "motors", "distance_pairs")
TIMELINE_OPTIONAL = ("time_origin", "total_duration_s", "motors")
DEFAULT_CONFIG = {
    "remote_ip": "127.0.0.1", "remote_port": 9090, "local_ip": "0.0.0.0",
    "packet_size": 512, "packet_mode": "fragment", "state_interval_ms": 50,
    "state_fields": list(STATE_OPTIONAL), "timeline_fields": list(TIMELINE_OPTIONAL),
    "state_extra": {}, "timeline_extra": {},
}
MAX_FRAGMENTS = 1024
MAX_JSON_SIZE = 1024 * 1024


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sequence_identity(project: ProjectSpec, fingerprint: dict[str, Any]) -> dict[str, str]:
    """No wall-clock seed: identical project/asset + resolved motions => identical sequence ID."""
    _variables, segments = resolve_schedule(project)
    plan = [
        {
            "drive_id": item.drive_id, "segment_id": item.segment_id,
            "start": item.start, "duration": item.duration, "travel": item.travel,
            "speed": item.speed, "profile": item.profile,
            "ease_in": item.ease_in, "ease_out": item.ease_out,
            "points": item.points, "mapping_source_joint_id": item.mapping_source_joint_id,
        }
        for item in sorted(segments, key=lambda s: (s.drive_id, s.start, s.segment_id))
    ]
    current_fingerprint = str(fingerprint["combined"])
    payload = {"model_fingerprint": current_fingerprint, "plan": plan,
               "sim_start": project.simulation.start_time, "sim_end": project.simulation.end_time}
    return {
        "object_id": project.id,
        "sequence_id": "seq_" + hashlib.sha256(canonical_bytes(payload)).hexdigest()[:24],
        "model_fingerprint": current_fingerprint,
    }


def build_timeline(project: ProjectSpec, identity: dict[str, str]) -> dict[str, Any]:
    _variables, plan = resolve_schedule(project)
    source = {seg.id: seg for drive in project.drives for seg in drive.segments}
    joints = {joint.id: joint for layer in project.layers for joint in layer.joints}
    per_drive: dict[str, list[dict[str, Any]]] = {}
    for segment in plan:
        raw = source[segment.segment_id]
        points = [list(pair) for pair in segment.points]
        entry = {
            "segment_id": segment.segment_id, "name": segment.name,
            "start_time_s": segment.start, "mode": raw.mode,
            "duration_s": segment.duration, "speed": segment.speed,
            "travel": segment.travel, "profile": segment.profile,
            "ease_in": segment.ease_in, "ease_out": segment.ease_out,
        }
        if points:
            entry["points"] = points
        if segment.mapping_source_joint_id:
            entry["mapping_source_joint_id"] = segment.mapping_source_joint_id
        per_drive.setdefault(segment.drive_id, []).append(entry)
    motors = []
    for drive in project.drives:
        if not drive.enabled or drive.id not in per_drive:
            continue
        joint = joints.get(drive.joint_id)
        motors.append({
            "drive_id": drive.id, "name": drive.name,
            "unit": "mm" if joint and joint.type == "translation" else "deg",
            "initial_position": 0.0, "segments": per_drive[drive.id],
        })
    return {
        "protocol_version": PROTOCOL_VERSION, "object_id": identity["object_id"],
        "sequence_id": identity["sequence_id"], "type": "timeline",
        "time_origin": "simulation_start",
        "total_duration_s": max(float(project.simulation.end_time), latest_drive_stop_time(plan, project.simulation.start_time)) - float(project.simulation.start_time),
        "motors": motors,
    }


def validated_config(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("UDP 配置必须为 JSON 对象")
    if set(payload) - set(DEFAULT_CONFIG):
        raise ValueError("UDP 配置包含未知字段")
    settings = {**DEFAULT_CONFIG, **payload}
    for key in ("remote_ip", "local_ip"):
        try:
            ip = ipaddress.IPv4Address(settings[key])
        except (ipaddress.AddressValueError, TypeError) as exc:
            raise ValueError(f"{key} 必须为 IPv4 地址") from exc
        if key == "remote_ip" and (ip.is_multicast or ip.is_unspecified or ip == ipaddress.IPv4Address("255.255.255.255")):
            raise ValueError("目标地址不能是多播、广播或 0.0.0.0")
        settings[key] = str(ip)
    for key, low, high in (("remote_port", 1, 65535), ("packet_size", 256, 65507), ("state_interval_ms", 20, 1000)):
        number = settings[key]
        if isinstance(number, bool) or not isinstance(number, int) or not low <= number <= high:
            raise ValueError(f"{key} 必须是 {low} 至 {high} 的整数")
    if settings["packet_mode"] not in {"fragment", "strict"}:
        raise ValueError("packet_mode 必须是 fragment 或 strict")
    for key, allowed in (("state_fields", STATE_OPTIONAL), ("timeline_fields", TIMELINE_OPTIONAL)):
        fields = settings[key]
        if not isinstance(fields, list) or not all(isinstance(s, str) and s in allowed for s in fields) or len(set(fields)) != len(fields):
            raise ValueError(f"{key} 字段选择无效")
        settings[key] = list(fields)
    for key in ("state_extra", "timeline_extra"):
        extra = settings[key]
        if not isinstance(extra, dict):
            raise ValueError(f"{key} 必须为 JSON 对象")
        if set(extra) & (set(REQUIRED_FIELDS) | set(STATE_OPTIONAL) | set(TIMELINE_OPTIONAL) | {"packet_seq", "model_fingerprint"}):
            raise ValueError(f"{key} 不能覆盖系统协议字段")
        if len(canonical_bytes(extra)) > 8192:
            raise ValueError(f"{key} 自定义字段过长")
    return settings


def project_message(payload: dict[str, Any], kind: str, config: dict[str, Any], *, run_id: str, packet_seq: int = 0) -> dict[str, Any]:
    optional = STATE_OPTIONAL if kind == "state" else TIMELINE_OPTIONAL
    chosen = config[f"{kind}_fields"]
    output = {key: payload[key] for key in REQUIRED_FIELDS if key in payload}
    output["run_id"] = run_id
    if kind == "state":
        output["sim_time_s"] = payload["sim_time_s"]  # required common timebase
        output["packet_seq"] = packet_seq
    for key in chosen:
        if key in payload:
            output[key] = payload[key]
    output.update(config[f"{kind}_extra"])
    return output


def from_base64_f32(encoded: str) -> list[float]:
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) % 4:
        raise ValueError("Float32 长度不完整")
    return [pair[0] for pair in struct.iter_unpack("<f", raw)]


@dataclass
class SampledAnimation:
    """Derived from trusted export payload, never from web client's claimed positions."""
    identity: dict[str, str]
    times: list[float]
    drives: list[dict[str, Any]]
    pairs: list[dict[str, Any]]
    drive_values: list[float]
    measurements: list[float]
    motor_ranges: list[tuple[float, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.motor_ranges:
            stride = len(self.drives)
            for idx in range(stride):
                values = [self.drive_values[frame*stride+idx] for frame in range(len(self.times))]
                valid = [v for v in values if math.isfinite(v)]
                self.motor_ranges.append((min(valid), max(valid)) if valid else (0.0, 0.0))

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SampledAnimation":
        identity = payload.get("labIdentity")
        if not isinstance(identity, dict) or not all(identity.get(k) for k in ("object_id", "sequence_id", "model_fingerprint")):
            raise ValueError("动画 HTML 缺少有效的 Lab 身份")
        times = from_base64_f32(payload["times"])
        drives = payload["drives"]
        pairs = payload["pairs"]
        values = from_base64_f32(payload["driveValues"])
        measurements = from_base64_f32(payload["measurements"])
        if not times or len(values) != len(times) * len(drives) or len(measurements) != len(times) * len(pairs) * 7:
            raise ValueError("动画采样数量不匹配")
        if not all(math.isfinite(v) for v in times) or any(a >= b for a, b in zip(times, times[1:])):
            raise ValueError("动画时间轴非严格递增")
        for row in drives:
            if not row.get("id") or not row.get("name"):
                raise ValueError("电机缺少稳定 id 或名称")
        for row in pairs:
            if not row.get("id"):
                raise ValueError("测距对缺少稳定 id")
        for kind, rows in (("drive", drives), ("pair", pairs)):
            ids = [str(row["id"]) for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError(f"动画包含重复的 {kind} ID，无法对照项目")
        return cls(identity, times, drives, pairs, values, measurements)

    def at(self, time_s: float, playback_state: str, *, run_id: str) -> dict[str, Any]:
        if playback_state not in {"playing", "paused", "stopped", "completed"}:
            raise ValueError("播放状态不合法")
        if not math.isfinite(time_s) or time_s < self.times[0] - 0.001 or time_s > self.times[-1] + 0.001:
            raise ValueError("仿真时间超出导出动画范围")
        t = max(self.times[0], min(self.times[-1], time_s))
        index = min(max(bisect.bisect_right(self.times, t) - 1, 0), len(self.times) - 1)
        later = min(index + 1, len(self.times) - 1)
        weight = (t - self.times[index]) / (self.times[later] - self.times[index]) if later > index else 0.0
        def interp(a: float, b: float) -> float | None:
            if not math.isfinite(a) or not math.isfinite(b):
                return None
            return float(a + (b-a)*weight)
        motors: list[dict[str, Any]] = []
        moving = False
        for idx, drive in enumerate(self.drives):
            stride = len(self.drives)
            position = interp(self.drive_values[index*stride+idx], self.drive_values[later*stride+idx])
            lo, hi = self.motor_ranges[idx]
            percent = (position - lo) / (hi - lo) * 100.0 if position is not None and hi > lo else (0.0 if position is not None else None)
            if playback_state == "playing" and position is not None and later > index:
                v0, v1 = self.drive_values[index*stride+idx], self.drive_values[later*stride+idx]
                moving |= math.isfinite(v0) and math.isfinite(v1) and abs(v1-v0) > 0.0001
            motors.append({"drive_id": drive["id"], "name": drive["name"], "position": position,
                           "unit": "deg" if drive["unit"] in {"°", "deg"} else "mm",
                           "percent": percent, "valid": position is not None,
                           "source": drive.get("source", "unknown")})
        pairs: list[dict[str, Any]] = []
        for idx, pair in enumerate(self.pairs):
            stride = len(self.pairs) * 7
            meter_value = interp(self.measurements[index*stride+idx*7], self.measurements[later*stride+idx*7])
            pairs.append({"pair_id": pair["id"], "name": pair["name"],
                          "distance_mm": float(meter_value * 1000) if meter_value is not None else None,
                          "valid": meter_value is not None})
        return {"protocol_version": PROTOCOL_VERSION, "object_id": self.identity["object_id"],
                "sequence_id": self.identity["sequence_id"], "run_id": run_id, "type": "state",
                "sim_time_s": t, "is_moving": bool(moving), "playback_state": playback_state,
                "motors": motors, "distance_pairs": pairs}



def align_timeline_to_samples(timeline: dict[str, Any], samples: SampledAnimation, *, simulation_start_s: float) -> dict[str, Any]:
    """Verify that each scheduled drive has actual HTML frame telemetry.

    The exported first-frame qpos is the physical origin of `initial_position`.
    Never silently replace a missing sampled drive with a planned zero angle.
    Mutates only the newly built per-request timeline dictionary.
    """
    if abs(samples.times[0] - float(simulation_start_s)) > 0.002:
        raise ValueError("动画起始时刻与模型仿真时间不匹配")
    if float(simulation_start_s) + timeline["total_duration_s"] > samples.times[-1] + 0.002:
        raise ValueError("动画总时长未覆盖全部运动时序，请在 Editor 调整仿真结束时间并重新生成")
    frame = samples.at(samples.times[0], "paused", run_id="alignment_only")
    actual = {motor["drive_id"]: motor for motor in frame["motors"]}
    for motor in timeline["motors"]:
        matched = actual.get(motor["drive_id"])
        if matched is None:
            raise ValueError(f"时序驱动 {motor['drive_id']} 未出现在动画采样中，拒绝发送不一致数据")
        if matched["unit"] != motor["unit"]:
            raise ValueError(f"时序驱动 {motor['drive_id']} 的单位与动画采样不一致")
        motor["initial_position"] = matched["position"]
    return timeline


def encode_datagrams(message: dict[str, Any], *, packet_size: int, mode: str = "fragment") -> list[bytes]:
    payload = canonical_bytes(message)
    if len(payload) > MAX_JSON_SIZE:
        raise ValueError("JSON 内容超过 1 MiB 限制")
    if len(payload) <= packet_size:
        return [payload]
    if mode == "strict":
        raise ValueError(f"JSON 共 {len(payload)} 字节，超过 {packet_size}，请减少字段或开启分片")
    if mode != "fragment":
        raise ValueError("UDP 包模式无效")
    message_id = uuid.uuid4().hex[:16]
    digest = hashlib.sha256(payload).hexdigest()[:16]
    size = max(1, int((packet_size - 140) * 0.70))
    while size > 0:
        parts = [payload[p:p+size] for p in range(0, len(payload), size)]
        if len(parts) > MAX_FRAGMENTS:
            raise ValueError("UDP 分片数量超出上限")
        datagrams = [canonical_bytes({"p": "ML1", "id": message_id, "index": i, "total": len(parts),
                                       "sha": digest, "data": base64.b64encode(part).decode("ascii")})
                     for i, part in enumerate(parts)]
        if all(len(block) <= packet_size for block in datagrams):
            return datagrams
        size -= max(1, (max(len(block) for block in datagrams) - packet_size + 3) * 3 // 4)
    raise ValueError("UDP 包长不足以封装分片头")


def reassemble_datagrams(datagrams: list[bytes]) -> dict[str, Any]:
    if not datagrams:
        raise ValueError("缺少 UDP 数据报")
    if len(datagrams) == 1:
        payload = json.loads(datagrams[0]);
        if payload.get("p") != "ML1":
            return payload
    fragments = [json.loads(item) for item in datagrams]
    expected = fragments[0]
    total = expected["total"]
    if len(fragments) != total or total > MAX_FRAGMENTS or {f["index"] for f in fragments} != set(range(total)):
        raise ValueError("分片缺失或重复")
    if any(any(f.get(k) != expected[k] for k in ("p", "id", "total", "sha")) for f in fragments):
        raise ValueError("分片头不一致")
    decoded = b"".join(base64.b64decode(f["data"], validate=True) for f in sorted(fragments, key=lambda f:f["index"]))
    if hashlib.sha256(decoded).hexdigest()[:16] != expected["sha"]:
        raise ValueError("分片校验失败")
    return json.loads(decoded)


def send_udp(message: dict[str, Any], config: dict[str, Any]) -> int:
    packets = encode_datagrams(message, packet_size=config["packet_size"], mode=config["packet_mode"])
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.bind((config["local_ip"], 0))
        for packet in packets:
            udp.sendto(packet, (config["remote_ip"], config["remote_port"]))
    return len(packets)


@dataclass
class LabSession:
    token: str
    run_id: str
    identity: dict[str, str]
    html_sha256: str
    project_id: str
    owner: str
    started_at: float
    sequence_number: int = 0
    last_state_at: float = 0.0
    lock: threading.RLock = field(default_factory=threading.RLock)
    config_digest: str = ""
    viewer_stat: tuple[int, int] | None = None
    samples: SampledAnimation | None = None
