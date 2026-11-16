"""result.get_latest — read the newest simulation result as a derived view."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from ...core.tool_base import ToolBase, ToolContext, ToolError


class LatestResultInput(BaseModel):
    pass


class LatestResultTool(ToolBase):
    id = "result.get_latest"
    name = "读取最新仿真结果"
    version = "2.7.2"
    description = "读取当前项目最新的 simulation_result.json，供结果查看器、脚本或 LLM 派生曲线。"
    category = "simulation"
    effect = "read_only"
    input_model = LatestResultInput

    @staticmethod
    def _paths(ctx: ToolContext) -> list[Path]:
        root = Path(ctx.output_dir) / "results"
        stable = root / "latest_simulation.json"
        if stable.is_file():
            return [stable]
        return sorted(
            root.glob("simulation_*/simulation_result.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def dry_run(self, payload: dict, ctx: ToolContext) -> dict:
        paths = self._paths(ctx)
        return {"available": bool(paths), "path": str(paths[0]) if paths else None}

    def run(self, payload: dict, ctx: ToolContext) -> dict:
        paths = self._paths(ctx)
        if not paths:
            raise ToolError("当前项目还没有仿真结果", hint="先在仿真结果查看页运行一次后台仿真。")
        try:
            return {"path": str(paths[0]), "result": json.loads(paths[0].read_text("utf-8"))}
        except (OSError, ValueError) as exc:
            raise ToolError(f"最新仿真结果无法读取: {exc}") from exc


TOOL = LatestResultTool()
