"""xml.generate —— 生成 MuJoCo XML（read_only，产出工件）。

复用领域 XML 生成器。read_only 工具不改状态权威区，但可产出工件：
生成的 XML 与 drives JSON 内容寻址存储，返回可 fetch 的 handle。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from ...core.tool_base import ToolBase, ToolContext, ToolError
from ...domain.models import ProjectSpec
from ...domain.xml_generator import generate_project


class XmlGenerateInput(BaseModel):
    check_files: bool = Field(default=False, title="检查网格文件存在")


class XmlGenerateTool(ToolBase):
    id = "xml.generate"
    name = "生成XML"
    version = "1.0.0"
    description = "根据当前状态生成 MuJoCo 模型 XML 与 drives JSON，作为工件返回（内容寻址，可读回）。"
    category = "simulation"
    effect = "read_only"
    input_model = XmlGenerateInput

    def input_schema(self) -> dict:
        return super().input_schema()

    def run(self, payload: dict, ctx: ToolContext) -> dict:
        project = ProjectSpec.model_validate(ctx.state["project"])
        with tempfile.TemporaryDirectory() as tmp:
            try:
                outputs = generate_project(project, Path(tmp), check_files=bool(payload.get("check_files", False)))
            except Exception as exc:  # noqa: BLE001
                raise ToolError(f"XML 生成失败: {exc}")
            artifacts = {}
            for label, path in outputs.items():
                p = Path(path)
                if not p.exists():
                    continue
                kind = "xml" if p.suffix == ".xml" else ("json" if p.suffix == ".json" else "txt")
                content = p.read_text(encoding="utf-8")
                stored = ctx.put_artifact(content if kind != "json" else __import__("json").loads(content),
                                          kind=kind, name=p.name)
                artifacts[label] = stored
        return {"generated": list(artifacts.keys()), "artifacts": artifacts}


TOOL = XmlGenerateTool()
