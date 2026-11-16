"""Single audited entry point for detached L3 project state."""
from __future__ import annotations

from .models import ProjectSpec


def scratch_project(project: ProjectSpec) -> ProjectSpec:
    """派生一份完全脱离状态树的私有副本，用于寻优/批量仿真/预览等高频临时计算。

    契约：
      1. 返回值与状态树无任何共享引用；
      2. 对返回值的修改不产生事件、不落盘 project.json、不进入版本流；
      3. 调用方负责通过正常命令通道回写需要保留的结论。
    """
    return ProjectSpec.model_validate(project.model_dump(mode="python"))
