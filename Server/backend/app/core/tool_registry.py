"""Tool Registry —— 架构总纲 §5.3。

启动时扫描 tools/ 目录自动注册。新增/删除/改一个工具只改它自己的文件夹，
主框架无需改动、无需加端点。注册表对 LLM 暴露为 function/tool 定义
（id / description / input_schema / effect），LLM 只读注册表即可选工具、
填参、编排 —— 这是"让 AI 能在代码上安全增删改查"的根本保证。
"""
from __future__ import annotations

import importlib
import pkgutil
from threading import RLock
from typing import Any

from .tool_base import ToolBase


_SHARED: dict[str, "ToolRegistry"] = {}
_SHARED_LOCK = RLock()


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolBase] = {}

    def register(self, tool: ToolBase) -> None:
        if not tool.id:
            raise ValueError("tool must declare a non-empty id")
        if tool.id in self._tools:
            raise ValueError(f"duplicate tool id: {tool.id}")
        self._tools[tool.id] = tool

    def discover(self, package_name: str) -> None:
        """扫描 tools 包下每个子模块，注册其中的 TOOL 实例。

        约定：每个工具目录的 tool.py 暴露模块级变量 TOOL = XxxTool()。
        """
        package = importlib.import_module(package_name)
        for module_info in pkgutil.iter_modules(package.__path__):
            if not module_info.ispkg:
                continue
            try:
                module = importlib.import_module(f"{package_name}.{module_info.name}.tool")
            except ModuleNotFoundError as exc:
                # Ignore only a missing tool module, never a broken dependency
                # imported from inside an existing tool.
                if exc.name == f"{package_name}.{module_info.name}.tool":
                    continue
                raise
            tool = getattr(module, "TOOL", None)
            if isinstance(tool, ToolBase):
                self.register(tool)

    def get(self, tool_id: str) -> ToolBase:
        if tool_id not in self._tools:
            raise KeyError(f"unknown tool: {tool_id}")
        return self._tools[tool_id]

    def all(self) -> list[ToolBase]:
        return list(self._tools.values())

    def catalog(self) -> list[dict[str, Any]]:
        return [t.as_registry_entry() for t in sorted(self._tools.values(), key=lambda item: item.id)]

    def llm_functions(self) -> list[dict[str, Any]]:
        """对 LLM function-calling 暴露的精简定义。"""
        return [
            {
                "name": t.id,
                "description": t.description,
                "effect": t.effect,
                "parameters": t.input_schema(),
            }
            for t in self._tools.values()
        ]


def shared_registry(package_name: str) -> ToolRegistry:
    """Return the process-wide immutable tool catalog for one package."""
    with _SHARED_LOCK:
        registry = _SHARED.get(package_name)
        if registry is None:
            registry = ToolRegistry()
            registry.discover(package_name)
            _SHARED[package_name] = registry
        return registry
