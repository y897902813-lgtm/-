"""param.set —— 通用参数写工具（write）。

对状态树上任意可写节点按稳定路径赋值。UI 上每个输入框、下拉、复选框
的交互，客户端都翻译成一条 param.set 命令下发，而不是直接改本地状态。
这是"赋值=操作、UI 是全局变量投射"（公理一+三）的落点。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...core.tool_base import ToolBase, ToolContext, ValidationResult, WriteResult

_READONLY_SUFFIX = (".id",)
_READONLY_PATHS = {"project.id", "project.schema_version", "project.metadata.updated_at"}


class ParamSetInput(BaseModel):
    path: str = Field(min_length=1, title="路径", description="稳定路径，如 project.layers.@layer_x.name")
    value: Any = Field(title="值", description="新值（数字、字符串、布尔、数组或对象）")
    intent: str | None = Field(default=None, title="意图", description="为什么这样改，供事件流学习")


class ParamSetTool(ToolBase):
    id = "param.set"
    name = "设置参数"
    version = "1.0.0"
    description = "按稳定路径给状态树任意可写节点赋值，如 project.layers.@LAYER_ID.name 或 ui.theme。所有 UI 输入都归约为本工具。"
    category = "core"
    effect = "write"
    input_model = ParamSetInput

    def input_schema(self) -> dict:
        return super().input_schema()

    def validate(self, payload: dict) -> ValidationResult:
        base = super().validate(payload)
        if not base.ok:
            return base
        path = payload.get("path")
        if not isinstance(path, str) or not path:
            return ValidationResult.fail("path 必须是非空字符串", field_name="path")
        if path in _READONLY_PATHS or path.endswith(_READONLY_SUFFIX):
            return ValidationResult.fail(f"路径只读，不可写: {path}", field_name="path")
        if not path.startswith(("project.", "ui.")):
            return ValidationResult.fail("路径必须位于 project.* 或 ui.*", field_name="path")
        return ValidationResult.success()

    def dry_run(self, payload: dict, ctx: ToolContext) -> dict:
        path = payload["path"]
        try:
            before = ctx.read_path(path)
        except Exception:  # noqa: BLE001
            before = None
        return {"path": path, "before": before, "after": payload["value"]}

    def run(self, payload: dict, ctx: ToolContext) -> WriteResult:
        path = payload["path"]
        value = payload["value"]
        try:
            before = ctx.read_path(path)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"路径不存在: {path}") from exc
        semantic = f"设置 {path}: {before!r} → {value!r}"
        return WriteResult([(path, value)], semantic=semantic, intent=payload.get("intent"))


TOOL = ParamSetTool()
