"""project.validate —— 校验项目（read_only）。

复用领域校验逻辑，返回结构化问题列表。LLM 可直接调用（read_only 无副作用），
据此在提交前自我修正。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ...core.tool_base import ToolBase, ToolContext
from ...domain.models import ProjectSpec
from ...domain.validation import validate_project


class ProjectValidateInput(BaseModel):
    check_files: bool = Field(default=False, title="检查文件存在", description="校验 STL/OBJ 引用")


class ProjectValidateTool(ToolBase):
    id = "project.validate"
    name = "校验项目"
    version = "1.0.0"
    description = "检查层级/运动副/驱动/公式/文件引用是否合法，返回结构化问题（不改状态）。"
    category = "core"
    effect = "read_only"
    input_model = ProjectValidateInput

    def input_schema(self) -> dict:
        return super().input_schema()

    def run(self, payload: dict, ctx: ToolContext) -> dict:
        project = ProjectSpec.model_validate(ctx.state["project"])
        issues = validate_project(project, check_files=bool(payload.get("check_files", False)))
        rows = [i.model_dump() for i in issues]
        errors = [r for r in rows if r.get("severity") == "error"]
        return {"ok": not errors, "issue_count": len(rows), "issues": rows}


TOOL = ProjectValidateTool()
