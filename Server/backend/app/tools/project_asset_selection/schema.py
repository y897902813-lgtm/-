"""Pydantic input schema for project.asset_selection."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ...domain.models import ProjectSpec


class AssetSelectionInput(BaseModel):
    project: ProjectSpec
    selection_id: str = Field(
        default="",
        max_length=32,
        title="兼容托管资产选择 ID",
        description="旧版项目 assets/mesh_selections 下的 32 位选择 ID；仅用于兼容旧调用。",
    )
    asset_folder_path: str = Field(
        default="",
        max_length=1024,
        title="模型类型公共数模资产文件夹路径",
        description="V2.5.6.11 使用 @model_assets/<模型类型>/<文件夹> 保存公共数模资产引用。",
    )
    intent: str | None = Field(default=None, title="变更原因")
