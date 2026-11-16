"""Move a project to a category and assign its folder-prefixed name."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ...core.tool_base import ToolBase, ToolContext, WriteResult


class ReclassifyInput(BaseModel):
    category: str = Field(min_length=1, max_length=400, title="目标分类")
    name: str = Field(min_length=1, max_length=180, title="托管项目名")
    version_date: str | None = Field(default=None, pattern=r"^\d{8}$", title="兼容旧调用的版本日期")
    version_index: int | None = Field(default=None, ge=1, title="兼容旧调用的版本序号")


class ProjectReclassifyTool(ToolBase):
    id = "project.reclassify"
    name = "项目重新分类"
    version = "1.1.0"
    description = "将非基线项目拖入目标分类，并按目标文件夹前缀原子重命名。"
    category = "project"
    effect = "write"
    input_model = ReclassifyInput

    def dry_run(self, payload: dict, ctx: ToolContext) -> dict:
        project = ctx.state["project"]
        return {
            "category_before": project.get("category", "未分类"),
            "category_after": payload["category"],
            "name_before": project.get("name", ""),
            "name_after": payload["name"],
        }

    def run(self, payload: dict, ctx: ToolContext) -> WriteResult:
        metadata = dict(ctx.state["project"].get("metadata", {}))
        if payload.get("version_date") is not None:
            metadata["version_date"] = payload["version_date"]
        if payload.get("version_index") is not None:
            metadata["version_index"] = payload["version_index"]
        metadata["version_summary_archived"] = False
        return WriteResult([
            ("project.category", payload["category"]),
            ("project.name", payload["name"]),
            ("project.metadata", metadata),
        ], semantic=f"将项目归入「{payload['category']}」并重命名为 {payload['name']}")


TOOL = ProjectReclassifyTool()
