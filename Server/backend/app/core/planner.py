"""Planner —— LLM 编排的确定性兜底实现（架构总纲 §8 / §12）。

把用户模糊指令解析为一个 ChangeSet（有序命令批次），默认不自动提交。
每条命令附参数来源说明（哪些来自用户明确描述、哪些是默认/推断）。
真实 LLM 规划器可实现相同签名替换：读注册表 → 生成命令 → 说明来源。
"""
from __future__ import annotations

import re
from typing import Any

from .state_tree import StateTree
from .tool_registry import ToolRegistry


_THEMES = {"深色": "carbon", "碳黑": "carbon", "浅色": "light", "蓝灰": "steel", "暖色": "warm"}


class Planner:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def plan(self, goal: str, state: StateTree) -> dict[str, Any]:
        commands: list[dict] = []
        notes: list[str] = []

        # 意图1：批量添加层级
        m = re.search(r"(\d+)\s*个?\s*(层级|图层|layer)", goal)
        if m:
            n = min(int(m.group(1)), 20)
            for i in range(n):
                commands.append({"tool_id": "layer.add", "params": {"name": f"层级{i + 1}", "parent_id": "root"},
                                 "client": "llm_agent"})
            notes.append(f"层级数量 {n} 来自用户明确描述；名称为默认推断（层级1..{n}）。")
        elif re.search(r"层级|layer", goal):
            commands.append({"tool_id": "layer.add", "params": {"name": "新层级", "parent_id": "root"},
                             "client": "llm_agent"})
            notes.append("默认添加 1 个层级；父层级默认 root（推断）。")

        # 意图2：添加驱动（绑定到状态中第一个运动副）
        if re.search(r"驱动|电机|act", goal):
            joint_id = self._first_joint_id(state)
            if joint_id:
                commands.append({"tool_id": "drive.add",
                                 "params": {"joint_id": joint_id, "mode": "duration", "duration": 2.0, "travel": 90.0},
                                 "client": "llm_agent"})
                notes.append(f"驱动绑定到已存在的运动副 {joint_id}（从当前状态推断）；时长/行程为默认值待确认。")
            else:
                notes.append("未找到可绑定的运动副，已跳过驱动创建——请先添加含运动副的层级。")

        # 意图3：切换主题（改 ui.* —— LLM 改 UI 即改状态）
        for zh, key in _THEMES.items():
            if zh in goal:
                commands.append({"tool_id": "ui.set", "params": {"path": "ui.theme", "value": key},
                                 "client": "llm_agent"})
                notes.append(f"主题 '{key}' 来自用户明确描述（{zh}）。")
                break

        if not commands:
            notes.append("未能从指令中解析出可执行意图。可尝试：'添加3个层级'、'加一个驱动'、'切换深色主题'。")

        rationale = " ".join(notes)
        return {"title": goal[:40] or "LLM 提案", "commands": commands, "rationale": rationale}

    @staticmethod
    def _first_joint_id(state: StateTree) -> str | None:
        for layer in state.get("project.layers"):
            joints = layer.get("joints") or []
            if joints:
                return joints[0]["id"]
        return None
