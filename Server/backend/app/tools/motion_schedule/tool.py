"""motion.compute_schedule —— 解算驱动时间-位置曲线（read_only）。

复用领域运动学核心（含 S 曲线缓起缓停、参考起始、公式变量解析），
按仿真时间网格采样出每个运动副的位移曲线，存为机器可读 JSON 工件并返回 handle。

这是 Agent 闭环（§8.4）的计算侧："设某自变量 = 某值"→本工具跑出因变量曲线→
LLM 读回工件→按目标（最大/最小/逼近阈值）决定下一取值。variable_overrides 即
"注入的自变量"，无需改动状态即可探查一次取值的后果。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ...core.tool_base import ToolBase, ToolContext, ToolError
from ...domain.expressions import ExpressionError
from ...domain.models import ProjectSpec
from ...domain.motion import collect_boundaries, resolve_schedule, segment_value


class MotionScheduleInput(BaseModel):
    variable_overrides: dict[str, float] = Field(default_factory=dict, title="自变量覆盖",
        description="临时覆盖变量值，不修改项目状态")
    sample_step: float = Field(default=0.02, gt=0, le=60, title="采样步长 s")


class MotionScheduleTool(ToolBase):
    id = "motion.compute_schedule"
    name = "解算驱动曲线"
    version = "1.0.0"
    description = "按时间网格采样各运动副位移曲线，支持注入自变量覆盖（variable_overrides）以探查一次取值后果，结果存为工件供读回。"
    category = "simulation"
    effect = "read_only"
    input_model = MotionScheduleInput

    def input_schema(self) -> dict:
        return super().input_schema()

    def run(self, payload: dict, ctx: ToolContext) -> dict[str, Any]:
        project = ProjectSpec.model_validate(ctx.state["project"])
        overrides = {k: float(v) for k, v in (payload.get("variable_overrides") or {}).items()}
        try:
            variables, schedule = resolve_schedule(project, overrides)
        except ExpressionError as exc:
            raise ToolError(f"驱动解析失败（公式/循环依赖）: {exc}", hint="检查参考起始或公式引用")

        step = max(1e-4, float(payload.get("sample_step", 0.02)))
        boundaries = collect_boundaries(schedule)
        end_time = max(boundaries) if boundaries else float(project.simulation.end_time)
        start_time = min(boundaries) if boundaries else 0.0

        # 每个运动段的位移曲线
        curves: dict[str, list[list[float]]] = {}
        t = start_time
        times: list[float] = []
        while t <= end_time + 1e-9:
            times.append(round(t, 6))
            t += step
        for seg in schedule:
            key = f"{seg.drive_name}/{seg.name}"
            curves[key] = [[tt, round(segment_value(seg, tt), 6)] for tt in times]

        result = {
            "start_time": start_time,
            "end_time": end_time,
            "sample_step": step,
            "segment_count": len(schedule),
            "resolved_variables": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in variables.items()},
            "curves": curves,
        }
        artifact = ctx.put_artifact(result, kind="json", name="schedule.json")
        return {
            "summary": {
                "segment_count": len(schedule),
                "end_time": round(end_time, 4),
                "variables": result["resolved_variables"],
            },
            "artifact": artifact,   # LLM 可用 artifact.handle 读回完整曲线
        }


TOOL = MotionScheduleTool()
