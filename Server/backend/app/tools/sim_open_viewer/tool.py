"""sim.open_viewer — launch the replaceable native MuJoCo visualization service."""
from __future__ import annotations

import importlib.util

from pydantic import BaseModel, Field

from ...config import DESKTOP_ENABLED
from ...core.tool_base import ToolBase, ToolContext, ToolError
from ...domain.models import ProjectSpec
from ...domain.optimization import apply_quick_results
from ...domain.scratch import scratch_project
from ...domain.validation import validate_project
from ...domain.viewer_launcher import ViewerLaunchError, launch_project_viewer


class OpenViewerInput(BaseModel):
    check_files: bool = Field(default=True, title="检查网格文件", description="启动前确认引用的 STL/OBJ 文件存在。")
    loop: bool = Field(default=False, title="循环播放", description="到达仿真结束时间后从头继续播放。")
    playback_speed: float = Field(
        default=1.0, ge=0.1, le=2.0, title="播放倍速", description="Viewer 初始播放倍速，范围 0.1x-2.0x；启动后可在动画控制窗口调整。"
    )
    quick_results: dict[str, float] = Field(
        default_factory=dict,
        title="快速寻优预览值",
        description="按寻优步骤 id 提供候选结果；仅用于本次 Viewer，不写回项目状态。",
    )


class OpenViewerTool(ToolBase):
    id = "sim.open_viewer"
    name = "打开 MuJoCo Viewer"
    version = "2.3.7.5"
    description = "打开可由 project.viewer_control 与统一命令总线托管的 Viewer，支持测距标签、质心轨迹及跟随图表。"
    category = "simulation"
    effect = "read_only"
    input_model = OpenViewerInput

    def output_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "status": {"type": "string"}, "pid": {"type": "integer"},
                "scene": {"type": "string"}, "drives": {"type": "string"},
                "log": {"type": "string"},
            },
        }

    def dry_run(self, payload: dict, ctx: ToolContext) -> dict:
        project = ProjectSpec.model_validate(ctx.state["project"])
        issues = validate_project(project, check_files=bool(payload.get("check_files", True)))
        errors = [issue.model_dump() for issue in issues if issue.severity == "error"]
        installed = importlib.util.find_spec("mujoco") is not None
        return {
            "can_launch": not errors and installed and DESKTOP_ENABLED, "mujoco_installed": installed,
            "validation_errors": errors,
            "will_generate": ["generated_model.xml", "generated_scene.xml", "generated_drives.json"],
            "will_open_native_window": True, "loop": bool(payload.get("loop", False)),
            "playback_speed": float(payload.get("playback_speed", 1.0)),
        }

    def run(self, payload: dict, ctx: ToolContext) -> dict:
        if not DESKTOP_ENABLED:
            raise ToolError("服务器模式禁止启动宿主机原生窗口", hint="浏览器客户端请使用 /api/projects/{id}/web-viewer。")
        project = scratch_project(ProjectSpec.model_validate(ctx.state["project"]))
        quick_results = {str(key): float(value) for key, value in payload.get("quick_results", {}).items()}
        if quick_results:
            apply_quick_results(project, quick_results)
        try:
            return launch_project_viewer(
                project, ctx.output_dir, check_files=bool(payload.get("check_files", True)),
                loop=bool(payload.get("loop", False)), speed=float(payload.get("playback_speed", 1.0)),
            )
        except ViewerLaunchError as exc:
            raise ToolError(str(exc), hint="查看 outputs/viewer/<launch_id>/viewer.log 获取 Viewer 子进程日志。") from exc


TOOL = OpenViewerTool()
