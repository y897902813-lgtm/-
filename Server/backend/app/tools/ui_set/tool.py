"""ui.set —— 修改界面状态（write）。

UI 本身也是状态：布局、折叠、主题、面板宽度都是 ui.* 子树上的节点。
LLM 改样式 = 写 ui.* 状态，与人类拖动分隔条走的是同一条命令总线、
同一条事件流、同样可撤销。这是公理三"LLM 改 UI = 改状态"的直接落点，
不另造机制（架构总纲 §7 UI 即 LLM 表达窗口）。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...core.tool_base import ToolBase, ToolContext, ValidationResult, WriteResult


class UiSetInput(BaseModel):
    path: str = Field(min_length=4, title="ui 路径", description="必须以 ui. 开头")
    value: Any = Field(title="值")


class UiSetTool(ToolBase):
    id = "ui.set"
    name = "设置界面状态"
    version = "1.0.0"
    description = "修改 ui.* 子树（主题、面板折叠、分隔条位置、变更高亮等）。LLM 可用它逐步样式化界面供用户审阅。"
    category = "core"
    effect = "write"
    input_model = UiSetInput

    def input_schema(self) -> dict:
        return super().input_schema()

    def validate(self, payload: dict) -> ValidationResult:
        base = super().validate(payload)
        if not base.ok:
            return base
        path = payload.get("path", "")
        if not isinstance(path, str) or not path.startswith("ui."):
            return ValidationResult.fail("ui.set 只能写 ui.* 路径", field_name="path", hint="改领域参数请用 param.set")
        return ValidationResult.success()

    def dry_run(self, payload: dict, ctx: ToolContext) -> dict:
        try:
            before = ctx.read_path(payload["path"])
        except Exception:  # noqa: BLE001
            before = None
        return {"path": payload["path"], "before": before, "after": payload["value"]}

    def run(self, payload: dict, ctx: ToolContext) -> WriteResult:
        path = payload["path"]
        return WriteResult([(path, payload["value"])], semantic=f"界面：设置 {path} = {payload['value']!r}")


TOOL = UiSetTool()
