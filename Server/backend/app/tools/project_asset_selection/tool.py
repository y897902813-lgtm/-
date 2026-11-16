"""Select one server-managed model asset folder for a project."""
from __future__ import annotations

import re
from pathlib import Path
from ...core.tool_base import ToolBase, ToolContext, ValidationResult, WriteResult
from ...domain.models import ProjectSpec
from .schema import AssetSelectionInput


class ProjectAssetSelectionTool(ToolBase):
    id = "project.asset_selection"
    name = "切换项目数模资产文件夹"
    version = "2.0.0"
    description = "切换到模型类型公共数模资产文件夹；兼容旧项目私有 selection_id。"
    category = "project"
    effect = "write"
    input_model = AssetSelectionInput

    def validate(self, payload: dict) -> ValidationResult:
        base = super().validate(payload)
        if not base.ok:
            return base
        selection_id = str(payload.get("selection_id", ""))
        asset_folder_path = str(payload.get("asset_folder_path", ""))
        if bool(selection_id) == bool(asset_folder_path):
            return ValidationResult.fail("selection_id 与 asset_folder_path 必须且只能提供一个")
        if selection_id and not re.fullmatch(r"[0-9a-f]{32}", selection_id):
            return ValidationResult.fail("selection_id 必须是 32 位十六进制服务端选择 ID", field_name="selection_id")
        if asset_folder_path and not asset_folder_path.startswith("@model_assets/"):
            return ValidationResult.fail("asset_folder_path 必须是 @model_assets/ 开头的公共资产路径", field_name="asset_folder_path")
        return ValidationResult.success()

    @staticmethod
    def _data_root(output_dir: str | Path) -> Path:
        current = Path(output_dir).resolve()
        for parent in (current, *current.parents):
            if parent.name == "projects":
                return parent.parent
        raise ValueError("无法定位服务端项目根目录")

    def run(self, payload: dict, ctx: ToolContext) -> WriteResult:
        current = ProjectSpec.model_validate(ctx.state["project"])
        project = ProjectSpec.model_validate(payload["project"])
        selection_id = str(payload.get("selection_id", ""))
        asset_folder_path = str(payload.get("asset_folder_path", ""))
        if asset_folder_path:
            prefix = "@model_assets/"
            parts = [part for part in asset_folder_path[len(prefix):].replace("\\", "/").split("/") if part]
            if len(parts) < 2 or any(part in {".", ".."} for part in parts):
                raise ValueError("非法公共数模资产文件夹路径")
            category = "/".join(parts[:-1])
            if category.casefold() != current.category.casefold():
                raise ValueError("只能选择当前模型类型下的公共数模资产文件夹")
            selected = (self._data_root(ctx.output_dir) / "model_asset_libraries" / Path(*parts)).resolve()
            library_root = (self._data_root(ctx.output_dir) / "model_asset_libraries" / Path(*parts[:-1])).resolve()
            if selected.parent != library_root or not selected.is_dir():
                raise ValueError("公共数模资产文件夹不存在")
            mesh_root = asset_folder_path
            semantic = f"切换公共数模资产文件夹到 {parts[-1]}"
        else:
            if not re.fullmatch(r"[0-9a-f]{32}", selection_id):
                raise ValueError("非法托管资产选择 ID")
            assets_root = (Path(ctx.output_dir) / "assets" / "mesh_selections").resolve()
            selected = (assets_root / selection_id).resolve()
            if selected.parent != assets_root or not selected.is_dir():
                raise ValueError("托管资产选择不存在或尚未完成上传")
            mesh_root = f"assets/mesh_selections/{selection_id}"
            semantic = f"切换兼容项目托管数模资产到 {selection_id[:8]}"
        project.lifecycle = current.lifecycle.model_copy(deep=True)
        project.category = current.category
        project.mesh_root = mesh_root
        return WriteResult([("project", project.model_dump())], semantic=semantic, intent=payload.get("intent"))


TOOL = ProjectAssetSelectionTool()
