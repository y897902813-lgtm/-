# project.asset_selection

服务端托管数模选择切换工具。

- effect: `write`
- Schema SSOT: `schema.py::AssetSelectionInput`
- 只接受服务端生成的 32 位十六进制 `selection_id`
- 持久化值固定为 `assets/mesh_selections/<selection_id>`
- 保留服务器控制的 lifecycle/category
- Web 上传端点只负责文件校验/落盘；项目状态变更必须经本工具 → CommandBus → Event
- 工具返回项目变更，框架的结构化 diff 层负责展开为最深变更路径，避免整树事件体积膨胀。

示例见 `example.json`，独立测试见 `tests/test_tool.py`。
