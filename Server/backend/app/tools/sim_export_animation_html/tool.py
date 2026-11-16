"""sim.export_animation_html — reproduce the V21.4.4.3.3 offline player."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from ...core.tool_base import ToolBase, ToolContext, ToolError
from ...domain.animation_export import export_project_animation_html
from ...domain.models import ProjectSpec


class ExportAnimationHtmlInput(BaseModel):
    check_files: bool = Field(
        default=True,
        title="检查模型文件",
        description="导出前确认项目引用的 STL/OBJ 文件存在；正式导出建议保持开启。",
    )


class ExportAnimationHtmlTool(ToolBase):
    id = "sim.export_animation_html"
    name = "导出动画 HTML"
    version = "2.7.2"
    description = "导出与 MuJoCo View 共用权威 trajectory 和测距语义的单文件离线 WebGL 动画，包含模型、时序、测距、甘特图和水印。"
    category = "simulation"
    effect = "read_only"
    input_model = ExportAnimationHtmlInput

    def output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "artifact": {"type": "string"},
                "artifact_relative": {"type": "string"},
                "artifact_handle": {"type": "string"},
                "frame_count": {"type": "integer"},
                "geom_count": {"type": "integer"},
                "pair_count": {"type": "integer"},
                "drive_count": {"type": "integer"},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
        }

    def dry_run(self, payload: dict, ctx: ToolContext) -> dict:
        project = ProjectSpec.model_validate(ctx.state["project"])
        duration = max(0.0, project.simulation.end_time - project.simulation.start_time)
        requested = int(duration * project.animation_html.fps) + 1
        return {
            "will_export": True,
            "format": "single-file offline WebGL2 HTML",
            "requested_frames": requested,
            "fps": project.animation_html.fps,
            "max_faces_per_mesh": project.animation_html.max_faces_per_mesh,
        }

    def run(self, payload: dict, ctx: ToolContext) -> dict:
        options = ExportAnimationHtmlInput.model_validate(payload)
        project = ProjectSpec.model_validate(ctx.state["project"])
        destination = Path(ctx.output_dir) / "results" / f"animation_html_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            result = export_project_animation_html(project, destination, check_files=options.check_files)
            artifact_path = Path(result["artifact"])
            stored = ctx.put_artifact(
                artifact_path.read_text("utf-8"),
                kind="html",
                name=artifact_path.name,
            )
            result["artifact_handle"] = stored["handle"]
            result["artifact_store"] = stored
            return result
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"动画 HTML 导出失败：{exc}") from exc


TOOL = ExportAnimationHtmlTool()
