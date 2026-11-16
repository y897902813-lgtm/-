"""layer.add —— 添加层级（write）。

演示对列表节点的写入：读当前 project.layers → 追加 → 整体写回。
撤销时整体写回旧列表（公理二：逆放事件）。层级用领域模型 LayerSpec 构造，
保证字段/默认值与"唯一真相源"一致；带稳定 id，后续引用用 @id 寻址。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ...core.tool_base import ToolBase, ToolContext, ValidationResult, WriteResult
from ...domain.models import LayerSpec


class LayerAddInput(BaseModel):
    name: str = Field(default="layer", min_length=1, title="名称", description="层级名称，支持中文")
    parent_id: str = Field(default="root", title="父层级 id", description="root 表示根层级")
    intent: str | None = Field(default=None, title="意图")


class LayerAddTool(ToolBase):
    id = "layer.add"
    name = "添加层级"
    version = "1.0.0"
    description = "在层级树中新增一个层级，可指定父层级 id。对应旧版'在对象层级下添加子层级'。"
    category = "modeling"
    effect = "write"
    input_model = LayerAddInput

    def input_schema(self) -> dict:
        return super().input_schema()

    def validate(self, payload: dict) -> ValidationResult:
        base = super().validate(payload)
        if not base.ok:
            return base
        if not str(payload.get("name", "")).strip():
            return ValidationResult.fail("层级名称不能为空", field_name="name")
        return ValidationResult.success()

    def _next_layers(self, ctx: ToolContext, payload: dict):
        layers = list(ctx.read_path("project.layers"))
        parent_id = payload.get("parent_id", "root")
        if parent_id != "root" and parent_id not in {item.get("id") for item in layers}:
            raise ValueError(f"父层级不存在: {parent_id}")
        new_layer = LayerSpec(name=str(payload["name"]), parent_id=payload.get("parent_id", "root")).model_dump()
        return layers + [new_layer], new_layer

    def dry_run(self, payload: dict, ctx: ToolContext) -> dict:
        _, new_layer = self._next_layers(ctx, payload)
        return {"will_add": new_layer, "parent_id": new_layer["parent_id"]}

    def run(self, payload: dict, ctx: ToolContext) -> WriteResult:
        next_layers, new_layer = self._next_layers(ctx, payload)
        return WriteResult(
            [("project.layers", next_layers)],
            semantic=f"添加层级「{new_layer['name']}」（父层级 {new_layer['parent_id']}）",
            intent=payload.get("intent"),
        )


TOOL = LayerAddTool()
