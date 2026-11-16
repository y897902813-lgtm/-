"""Tool / Skill 契约 —— 架构总纲 §5。

一个工具 = 一个独立目录 = 一个"用户或 LLM 会单独想调用的能力"。
可单独导入、校验、运行、测试，不依赖前端、不依赖全局可变状态
（状态经 ctx 只读注入；write 工具通过返回 PathDiff 声明变更，由内核落库）。

三段式分工（复述检验点）：
  validate = 只查结构合法性，最便宜，不执行；
  dry_run  = 跑但零副作用，返回"会发生什么"的预览；
  run      = 真正执行；write 工具的结果由命令总线转成事件、可撤销。

effect 分级：
  read_only = 扫描/取值/算曲线/生成产物，不改状态权威区，LLM 可直接执行；
  write     = 改状态树、产生事件、可撤销，必须走 dry_run→测试回填→人工确认。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import inspect
import json
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError


@dataclass
class ValidationResult:
    ok: bool
    errors: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def success(cls) -> "ValidationResult":
        return cls(ok=True)

    @classmethod
    def fail(cls, message: str, field_name: str | None = None, hint: str | None = None) -> "ValidationResult":
        # 结构化错误（§5.2 硬约束）：禁止只回 traceback。
        return cls(ok=False, errors=[{"code": "invalid", "message": message, "field": field_name, "hint": hint}])


class ToolError(Exception):
    def __init__(self, message: str, field_name: str | None = None, hint: str | None = None) -> None:
        super().__init__(message)
        self.payload = {"code": "tool_error", "message": message, "field": field_name, "hint": hint}


class ToolContext:
    """注入给 run/dry_run 的上下文，使工具保持近纯函数。"""

    def __init__(self, *, read_path: Callable[[str], Any], put_artifact: Callable[..., dict],
                 get_artifact: Callable[[str], Any], output_dir: str, dry_run: bool = False,
                 state: dict[str, Any] | None = None,
                 state_factory: Callable[[], dict[str, Any]] | None = None,
                 resolve_mesh_root: Callable[[str, str], Path] | None = None) -> None:
        self.read_path = read_path
        self.put_artifact = put_artifact
        self.get_artifact = get_artifact
        self.output_dir = output_dir
        self.dry_run = dry_run
        self._state = state
        self._state_factory = state_factory
        self._resolve_mesh_root = resolve_mesh_root
        self.produced_handles: list[str] = []

    def resolve_mesh_root(self, project_id: str, mesh_root: str) -> Path:
        if self._resolve_mesh_root is None:
            raise RuntimeError("mesh root resolver is unavailable in this tool context")
        return Path(self._resolve_mesh_root(str(project_id), str(mesh_root)))

    @property
    def state(self) -> dict[str, Any]:
        if self._state is None:
            if self._state_factory is None:
                raise RuntimeError("state snapshot is unavailable")
            self._state = self._state_factory()
        return self._state


class WriteResult:
    """write 工具的返回：一组 (path, new_value) 与语义标注。

    命令总线据此写状态树、计算 before、生成事件（含 inverse）。
    工具本身不直接改状态，保证事件流不失真、撤销/学习不失效。
    """

    def __init__(self, changes: list[tuple[str, Any]], semantic: str, intent: str | None = None,
                 creates: list[str] | None = None) -> None:
        self.changes = changes            # [(path, new_value), ...]
        self.semantic = semantic
        self.intent = intent
        self.creates = creates or []      # 需要在父容器新建的路径（列表 append 前缀），可空


class ToolBase:
    id: str = ""              # 全局唯一，如 "layer.add"
    name: str = ""
    version: str = "1.0.0"
    description: str = ""     # 给 LLM 看：做什么、何时用、关键参数含义
    category: str = "misc"    # 前端导航 + LLM 检索分组
    effect: str = "read_only"  # "read_only" | "write"
    input_model: type[BaseModel] | None = None

    def input_schema(self) -> dict:
        if self.input_model is None:
            return {"type": "object", "properties": {}}
        if hasattr(self.input_model, "model_json_schema"):
            return self.input_model.model_json_schema()
        return self.input_model.schema()

    def output_schema(self) -> dict:
        return {"type": "object"}

    def ui_schema(self) -> dict:
        path = Path(inspect.getfile(self.__class__)).with_name("ui_schema.json")
        if not path.is_file():
            return {}
        return json.loads(path.read_text("utf-8"))

    def validate(self, payload: dict) -> ValidationResult:  # 廉价结构校验，不执行
        if self.input_model is not None:
            try:
                if hasattr(self.input_model, "model_validate"):
                    self.input_model.model_validate(payload)
                else:
                    self.input_model.parse_obj(payload)
            except ValidationError as exc:
                errors = []
                for item in exc.errors():
                    errors.append({"code": item.get("type", "invalid"),
                                   "message": item.get("msg", "invalid value"),
                                   "field": ".".join(str(part) for part in item.get("loc", [])),
                                   "hint": None})
                return ValidationResult(ok=False, errors=errors)
        return ValidationResult.success()

    def dry_run(self, payload: dict, ctx: ToolContext) -> dict:  # 无副作用预演
        return {"preview": "no preview implemented", "payload": payload}

    def run(self, payload: dict, ctx: ToolContext) -> Any:  # 真正执行
        raise NotImplementedError

    def as_registry_entry(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "effect": self.effect,
            "input_schema": self.input_schema(),
            "output_schema": self.output_schema(),
            "ui_schema": self.ui_schema(),
        }
