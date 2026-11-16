"""drive.add —— 添加电机驱动（write）。

对应旧版驱动设置界面：新增一个驱动，含一段默认运动。用领域模型
DriveSpec/DriveSegmentSpec 构造，保证字段一致。驱动/运动段带稳定 id，
其参数都是状态节点，可被优化设为自变量、可被公式引用。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ...core.tool_base import ToolBase, ToolContext, ValidationResult, WriteResult
from ...domain.models import DriveSegmentSpec, DriveSpec


class DriveAddInput(BaseModel):
    name: str | None = Field(default=None, title="驱动名", description="留空自动使用下一个可用 actN")
    joint_id: str = Field(min_length=1, title="运动副 id")
    mode: Literal["duration", "speed"] = Field(default="duration", title="模式")
    start: float = Field(default=0.0, title="起始时间 s")
    duration: float = Field(default=1.0, gt=0, title="时长 s")
    travel: float = Field(default=30.0, title="行程")
    intent: str | None = Field(default=None, title="意图")


class DriveAddTool(ToolBase):
    id = "drive.add"
    name = "添加驱动"
    version = "1.0.0"
    description = "新增一个电机驱动，绑定到指定运动副，含一段可配置运动（速度/时长模式、行程）。"
    category = "drive"
    effect = "write"
    input_model = DriveAddInput

    def input_schema(self) -> dict:
        return super().input_schema()

    def validate(self, payload: dict) -> ValidationResult:
        base = super().validate(payload)
        if not base.ok:
            return base
        if not str(payload.get("joint_id", "")).strip():
            return ValidationResult.fail("必须指定运动副 id", field_name="joint_id")
        return ValidationResult.success()

    def _build(self, ctx: ToolContext, payload: dict):
        drives = list(ctx.read_path("project.drives"))
        joint_ids = {joint.get("id") for layer in ctx.read_path("project.layers")
                     for joint in layer.get("joints", [])}
        if payload["joint_id"] not in joint_ids:
            raise ValueError(f"运动副不存在: {payload['joint_id']}")
        used_names = {item.get("name") for item in drives}
        index = 1
        while f"act{index}" in used_names:
            index += 1
        auto_name = payload.get("name") or f"act{index}"
        if auto_name in used_names:
            raise ValueError(f"驱动名称已存在: {auto_name}")
        segment = DriveSegmentSpec(
            name="seg1",
            mode=payload.get("mode", "duration"),
            start=payload.get("start", 0.0),
            duration=payload.get("duration", 1.0),
            travel=payload.get("travel", 30.0),
        )
        drive = DriveSpec(name=auto_name, joint_id=payload["joint_id"], segments=[segment]).model_dump()
        return drives + [drive], drive

    def dry_run(self, payload: dict, ctx: ToolContext) -> dict:
        _, drive = self._build(ctx, payload)
        return {"will_add": drive}

    def run(self, payload: dict, ctx: ToolContext) -> WriteResult:
        next_drives, drive = self._build(ctx, payload)
        return WriteResult(
            [("project.drives", next_drives)],
            semantic=f"添加驱动「{drive['name']}」→ 运动副 {drive['joint_id']}",
            intent=payload.get("intent"),
        )


TOOL = DriveAddTool()
