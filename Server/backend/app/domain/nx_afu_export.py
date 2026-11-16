#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Build a self-contained NX journal that creates and binds AFU functions."""

from __future__ import annotations

import base64
import json
import zlib
from datetime import datetime
from pathlib import Path

PAYLOAD_MARKER = "__MUJOCO_XML_TOOL_V20_4_PAYLOAD_B64__"
FORMAT_NAME = "MUJOCO_XML_TOOL_NX_AFU"
FORMAT_VERSION = 1


def _normalize_curve(curve, index):
    name = str((curve or {}).get("name", "") or "").strip()
    if not name:
        raise ValueError(f"第 {index + 1} 个坐标系没有名称")

    raw_times = list((curve or {}).get("times", []) or [])
    raw_values = list((curve or {}).get("values", []) or [])
    usable = min(len(raw_times), len(raw_values))
    if usable < 2:
        raise ValueError(f"坐标系 [{name}] 的有效数据不足 2 个点")

    times = []
    values = []
    previous = None
    for point_index in range(usable):
        try:
            time_value = float(raw_times[point_index])
            curve_value = float(raw_values[point_index])
        except Exception as ex:
            raise ValueError(
                f"坐标系 [{name}] 第 {point_index + 1} 个数据点不是有效数字"
            ) from ex
        if previous is not None and time_value <= previous:
            raise ValueError(f"坐标系 [{name}] 的时间序列必须严格递增")
        if not (-float("inf") < time_value < float("inf")):
            raise ValueError(f"坐标系 [{name}] 包含无效时间值")
        if not (-float("inf") < curve_value < float("inf")):
            raise ValueError(f"坐标系 [{name}] 包含无效曲线值")
        times.append(time_value)
        values.append(curve_value)
        previous = time_value

    return {
        "name": name,
        "source_label": str((curve or {}).get("source_label", "") or ""),
        "unit": str((curve or {}).get("unit", "") or ""),
        "times": times,
        "values": values,
    }


def build_nx_afu_script(curves):
    """Return a standalone UTF-8 NXOpen journal with embedded curve data."""

    normalized = [
        _normalize_curve(curve, index)
        for index, curve in enumerate(list(curves or []))
    ]
    if not normalized:
        raise ValueError("当前没有可导出的驱动/关节坐标曲线")

    payload = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "source_version": "V20.4",
        "curves": normalized,
    }
    payload_json = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    payload_b64 = base64.b64encode(zlib.compress(payload_json, 9)).decode("ascii")

    template_path = Path(__file__).resolve().parents[1] / "templates" / "nx_afu_runtime.py.txt"
    if not template_path.is_file():
        raise RuntimeError(f"缺少 NX AFU 脚本模板：{template_path}")
    template = template_path.read_text(encoding="utf-8")
    if template.count(PAYLOAD_MARKER) != 1:
        raise RuntimeError("NX AFU 脚本模板中的数据占位符无效")

    script = template.replace(PAYLOAD_MARKER, payload_b64)
    compile(script, "<generated_nx_afu_script>", "exec")
    return script


def _derivative(values, times):
    output = []
    for index in range(len(values)):
        if len(values) < 2:
            output.append(0.0)
            continue
        left = max(0, index - 1)
        right = min(len(values) - 1, index + 1)
        delta = float(times[right]) - float(times[left])
        output.append((float(values[right]) - float(values[left])) / delta if delta else 0.0)
    return output


def _transform(values, times, operation):
    result = [float(value) for value in values]
    if operation == "integral":
        integrated = [0.0]
        for index in range(1, len(result)):
            delta = float(times[index]) - float(times[index - 1])
            integrated.append(integrated[-1] + 0.5 * (result[index - 1] + result[index]) * delta)
        return integrated
    for _ in range({"d1": 1, "d2": 2, "d3": 3}.get(str(operation), 0)):
        result = _derivative(result, times)
    return result


def _source_catalog(simulation, project=None):
    """Return the canonical result-object catalog shared by NX and CSV projections.

    ``project`` is optional so older internal callers can keep the historical labels.
    When available, joint labels match the Result Viewer (``layer / joint``).
    """
    catalog = {}
    joint_layers = {}
    if project is not None:
        for layer in getattr(project, "layers", []):
            for joint in getattr(layer, "joints", []):
                joint_layers[str(joint.id)] = str(layer.name or "未分层")
    for key, curve in dict(simulation.get("curves", {})).items():
        name = str(curve.get("name", key))
        label = f"{joint_layers.get(str(key), '未分层')} / {name}" if project is not None else name
        catalog[f"joint:{key}"] = {
            "label": label, "unit": str(curve.get("unit", "")),
            "values": list(curve.get("position", [])),
        }
    for key, curve in dict(simulation.get("drive_curves", {})).items():
        catalog[f"drive:{key}"] = {
            "label": str(curve.get("name", key)), "unit": str(curve.get("unit", "")),
            "values": list(curve.get("position", [])),
        }
    for key, curve in dict(simulation.get("distance_curves", {})).items():
        catalog[f"pair:{key}"] = {
            "label": str(curve.get("name", key)), "unit": str(curve.get("unit", "mm")),
            "values": list(curve.get("values", [])),
        }
    return catalog


def _canonical_source_key(source):
    value = str(source or "")
    if value.startswith("joint:") and value.rsplit(":", 1)[-1] in {"position", "velocity", "acceleration"}:
        return value.rsplit(":", 1)[0]
    return value


def _transformed_unit(unit, operation):
    value = str(unit or "").replace("deg", "°")
    if operation == "integral":
        return f"{value}·s" if value else "s"
    order = {"d1": 1, "d2": 2, "d3": 3}.get(str(operation), 0)
    if order and value:
        return f"{value}/s{'^' + str(order) if order > 1 else ''}"
    return value


def axes_from_result_layout(project, simulation):
    """Project the visible Result Viewer axes from one simulation result.

    This is the server-side counterpart of ``resolvedAxisCurves``.  Baseline CSV,
    delivery CSV, and NX export must derive from the same persisted result-layout
    truth instead of inventing independent curve-selection rules.
    """
    times = [float(value) for value in simulation.get("times", [])]
    if len(times) < 1:
        raise ValueError("最新仿真结果没有时间点，请先运行仿真")
    catalog = _source_catalog(simulation, project)
    output = []
    for axis_index, axis in enumerate(project.result_layout.axes):
        ordinary = []
        legacy_sum = False
        for curve in axis.curves:
            if curve.operation == "sum":
                legacy_sum = True
                continue
            source_key = _canonical_source_key(curve.source)
            source = catalog.get(source_key)
            if source is None:
                continue
            ordinary.append({
                "label": source["label"],
                "unit": _transformed_unit(source["unit"], curve.operation),
                "color": str(curve.color or "#2563eb"),
                "values": _transform(source["values"], times, curve.operation),
            })
        combine = str(axis.combine or ("sum" if legacy_sum else "none"))
        combined = None
        visible = list(ordinary)
        if ordinary and combine in {"sum", "difference"}:
            length = max((len(item["values"]) for item in ordinary), default=0)
            values = []
            for point_index in range(length):
                def point(item):
                    return float(item["values"][point_index]) if point_index < len(item["values"]) else 0.0
                if combine == "sum":
                    values.append(sum(point(item) for item in ordinary))
                else:
                    values.append(point(ordinary[0]) - sum(point(item) for item in ordinary[1:]))
            same_unit = all(item["unit"] == ordinary[0]["unit"] for item in ordinary)
            combined = {
                "label": f"{axis.name or f'坐标系{axis_index + 1}'} · {'求和' if combine == 'sum' else '求差'}",
                "unit": ordinary[0]["unit"] if same_unit else "",
                "color": "#253247",
                "values": values,
            }
            visible = [*ordinary, combined] if axis.keep_operands else [combined]
        output.append({
            "id": str(axis.id),
            "name": str(axis.name or f"坐标系{axis_index + 1}"),
            "index": axis_index,
            "combine": combine,
            "add_to_gantt": bool(axis.add_to_gantt),
            "times": times,
            "ordinary_curves": ordinary,
            "combined_curve": combined,
            "curves": visible,
        })
    return output


def curves_from_result_layout(project, simulation):
    """Build the AFU curve set from the visible Studio result axes."""
    curves = []
    for axis in axes_from_result_layout(project, simulation):
        selected = axis["combined_curve"] if axis["combine"] in {"sum", "difference"} else (axis["ordinary_curves"][0] if axis["ordinary_curves"] else None)
        if selected is None:
            continue
        usable = min(len(axis["times"]), len(selected["values"]))
        if usable < 2:
            continue
        curves.append({
            "name": axis["name"],
            "source_label": selected["label"], "unit": selected["unit"],
            "times": axis["times"][:usable], "values": selected["values"][:usable],
        })
    if not curves:
        raise ValueError("当前坐标系没有可导出的曲线，请先添加坐标系和曲线并运行仿真")
    return curves

def export_project_nx_afu_script(project, simulation, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    curves = curves_from_result_layout(project, simulation)
    destination.write_text(build_nx_afu_script(curves), encoding="utf-8", newline="\n")
    return {"artifact": str(destination), "curve_count": len(curves)}
