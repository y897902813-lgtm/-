from __future__ import annotations

from pydantic import BaseModel

from ...core.tool_base import ToolBase, ToolContext
from ...domain.mass_properties import resolve_mass_properties
from ...domain.models import ProjectSpec


class MassPropertiesInput(BaseModel):
    pass


class MassPropertiesTool(ToolBase):
    id = "model.mass_properties"
    name = "计算质量与密度"
    version = "2.14.2"
    description = "解析层级/数模最终目标质量与参考密度；有目标 kg 时标记 direct_mass，生成 MJCF 直接写 mass。"
    category = "model"
    effect = "read_only"
    input_model = MassPropertiesInput

    def dry_run(self, payload: dict, ctx: ToolContext) -> dict:
        project = ProjectSpec.model_validate(ctx.state["project"])
        return {"layer_count": len(project.layers), "mesh_count": sum(len(item.meshes) for item in project.layers)}

    def run(self, payload: dict, ctx: ToolContext) -> dict:
        project = ProjectSpec.model_validate(ctx.state["project"])
        resolved_root = ctx.resolve_mesh_root(project.id, project.mesh_root) if project.mesh_root else None
        return resolve_mass_properties(project, mesh_root=resolved_root)


TOOL = MassPropertiesTool()
