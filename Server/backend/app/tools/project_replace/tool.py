"""Replace a complete project through the same command/event path used by all clients."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ...core.tool_base import ToolBase, ToolContext, ValidationResult, WriteResult
from ...domain.models import ProjectSpec


class ReplaceEnvelope(BaseModel):
    project: ProjectSpec
    intent: str | None = Field(default=None, title="变更原因")


class ProjectReplaceTool(ToolBase):
    id = "project.replace"
    name = "替换项目状态"
    version = "1.0.0"
    description = "校验并替换完整 project 子树；用于网页保存、JSON 导入和迁移。"
    category = "core"
    effect = "write"
    input_model = ReplaceEnvelope

    def input_schema(self) -> dict:
        return super().input_schema()

    def validate(self, payload: dict) -> ValidationResult:
        base = super().validate(payload)
        if not base.ok:
            return base
        try:
            ProjectSpec.model_validate(payload.get("project"))
        except Exception as exc:  # noqa: BLE001
            return ValidationResult.fail(str(exc), field_name="project")
        return ValidationResult.success()

    def dry_run(self, payload: dict, ctx: ToolContext) -> dict:
        current = ProjectSpec.model_validate(ctx.state["project"])
        incoming = ProjectSpec.model_validate(payload["project"])
        return {"project_id": incoming.id, "name": incoming.name,
                "counts_before": {"layers": len(current.layers), "drives": len(current.drives)},
                "counts_after": {"layers": len(incoming.layers), "drives": len(incoming.drives)}}

    def run(self, payload: dict, ctx: ToolContext) -> WriteResult:
        project = ProjectSpec.model_validate(payload["project"])
        # Preserve authoritative fields without cloning the whole state tree.
        project.lifecycle = type(project.lifecycle).model_validate(ctx.read_path("project.lifecycle"))
        project.category = str(ctx.read_path("project.category"))
        project.mesh_root = str(ctx.read_path("project.mesh_root"))
        return WriteResult([("project", project.model_dump())],
                           semantic=f"保存项目「{project.name}」", intent=payload.get("intent"))


TOOL = ProjectReplaceTool()
