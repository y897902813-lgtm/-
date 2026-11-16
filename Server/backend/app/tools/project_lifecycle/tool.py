"""Teamcenter-style checked-in / checked-out lifecycle transitions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from ...core.tool_base import ToolBase, ToolContext, ValidationResult, WriteResult


class LifecycleInput(BaseModel):
    action: Literal["check_in", "check_out"] = Field(
        title="生命周期操作", description="签入项目使配置只读；签出项目后允许修改配置",
    )
    intent: str | None = Field(default=None, title="变更原因")
    log: str = Field(default="", max_length=2000, exclude=True)
    actor: str = Field(default="", exclude=True)
    lease_id: str = Field(default="", exclude=True)
    force: bool = Field(default=False, exclude=True)
    reacquire: bool = Field(default=False, exclude=True)


class ProjectLifecycleTool(ToolBase):
    id = "project.lifecycle"
    name = "项目签入签出"
    version = "1.0.0"
    description = "在签入（只读、可导出）与签出（可编辑、不可导出）之间切换；基线不可切换。"
    category = "project"
    effect = "write"
    input_model = LifecycleInput

    def validate(self, payload: dict) -> ValidationResult:
        return super().validate(payload)

    def dry_run(self, payload: dict, ctx: ToolContext) -> dict:
        current = str(ctx.state.get("project", {}).get("lifecycle", {}).get("status", "checked_in"))
        target = "checked_out" if payload["action"] == "check_out" else "checked_in"
        return {"before": current, "after": target, "configuration_editable": target == "checked_out"}

    def run(self, payload: dict, ctx: ToolContext) -> WriteResult:
        lifecycle = dict(ctx.state.get("project", {}).get("lifecycle", {}))
        current = str(lifecycle.get("status", "checked_in"))
        if current == "baseline":
            raise ValueError("基线生命周期被冻结，不能签入或签出")
        target = "checked_out" if payload["action"] == "check_out" else "checked_in"
        if current == target:
            if target == "checked_out" and bool(payload.get("reacquire")):
                lease_id = str(payload.get("lease_id", "")).strip()
                if not lease_id:
                    raise ValueError("租约恢复必须由服务端提供非空编辑租约")
                lifecycle["checked_out_by"] = str(payload.get("actor", lifecycle.get("checked_out_by", "")))
                lifecycle["lease_id"] = lease_id
                return WriteResult(
                    [("project.lifecycle", lifecycle)],
                    semantic="恢复同一账号对已签出项目的编辑租约，不改变签出时间",
                    intent=payload.get("intent"),
                )
            raise ValueError(f"项目已经处于{'签出' if target == 'checked_out' else '签入'}状态")
        now = datetime.now(timezone.utc).isoformat()
        lifecycle["status"] = target
        lifecycle["checked_out_at" if target == "checked_out" else "checked_in_at"] = now
        if target == "checked_out":
            lease_id = str(payload.get("lease_id", "")).strip()
            if not lease_id:
                raise ValueError("签出必须由服务端提供非空编辑租约")
            lifecycle["checked_out_by"] = str(payload.get("actor", ""))
            lifecycle["lease_id"] = lease_id
            lifecycle.pop("checked_out_session", None)
        else:
            lifecycle["checked_out_by"] = ""
            lifecycle["lease_id"] = ""
            lifecycle.pop("checked_out_session", None)
        semantic = f"将项目从{'签出' if current == 'checked_out' else '签入'}切换为{'签出' if target == 'checked_out' else '签入'}"
        return WriteResult([("project.lifecycle", lifecycle)], semantic=semantic, intent=payload.get("intent"))


TOOL = ProjectLifecycleTool()
