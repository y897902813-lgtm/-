# MuJoCo Studio API

服务启动后，交互式接口文档位于：

- Swagger UI：`http://127.0.0.1:8765/docs`
- OpenAPI JSON：`http://127.0.0.1:8765/openapi.json`

所有工程计算都通过 `/api` 暴露。Web UI 本身也是这些接口的客户端。

## 最短调用流程

### 1. 创建项目

```bash
curl -X POST http://127.0.0.1:8765/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"API demo","demo":true}'
```

响应中的 `id` 是后续请求使用的 `project_id`。

新建或导入的普通项目默认为 `checked_in`（签入）状态：可以预览、仿真和导出，
但配置只读。修改前必须显式签出；保存完成后再签入：

```bash
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/lifecycle \
  -H "Content-Type: application/json" -d '{"action":"check_out"}'

# 修改并保存项目……

curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/lifecycle \
  -H "Content-Type: application/json" -d '{"action":"check_in"}'
```

`checked_out`（签出）项目可持久修改但禁止导出；`checked_in`（签入）和 `baseline`（基线）
可通过 `/edit-session` 建立隔离临时编辑会话，临时会话可编辑和撤销但退出后全部丢弃。
基线的权威内容仍不可永久修改、签出或重新分类。

V2.9.7.1 起，每次 `check_in` 都会自动生成一条现有 `versions/` 存档；调用方不再需要选择是否存档。请求体中的 `archive` 字段仅为旧调用方 schema 兼容保留，即使显式传 `false`，`check_in` 仍会存档。需要审计说明时可继续传可选 `log`。`check_out` 不创建版本快照。

### 1.1 项目分类与基线

```bash
# 新增一个可为空的项目分类节点
curl -X POST http://127.0.0.1:8765/api/project-categories \
  -H "Content-Type: application/json" -d '{"name":"车门机构"}'

# 将普通项目移入分类；服务自动命名为 分类_YYYYMMDD_00i
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/reclassify \
  -H "Content-Type: application/json" -d '{"category":"车门机构"}'

# 仅签入且已有分类的项目可以打基线
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/baseline \
  -H "Content-Type: application/json" -d '{}'
```

导入基线导出物时，响应同时包含权威不可改写的 `baseline_project` 和一个新建的
`checked_in` 工作副本 `project`。基线封印校验失败时导入会被拒绝。

### 1.2 自描述工具、预演与命令

读取工具目录与 Pydantic 派生的输入 Schema：

```bash
curl http://127.0.0.1:8765/api/tools
curl http://127.0.0.1:8765/api/tools/param.set/schema
```

写入前先做零副作用预演：

```bash
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/tools/param.set/dry-run \
  -H "Content-Type: application/json" \
  -d '{"path":"project.variables.speed_scale","value":1.2}'
```

确认后发送统一命令信封。write 工具缺少 `confirmed:true` 会返回 409；
read_only 工具不需要确认：

```bash
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/commands \
  -H "Content-Type: application/json" \
  -d '{
    "confirmed":true,
    "command":{
      "command_id":"cmd-example-1",
      "tool_id":"param.set",
      "params":{"path":"project.variables.speed_scale","value":1.2},
      "client":"script",
      "correlation_id":"task-example"
    }
  }'
```

V2.4.5.1 起，成功写事件的信封包含 `actor`、`project_id` 与 `session_id`。这里的 `session_id` **不是登录 Cookie token**，而是服务端计算的 `sha256(会话标识)[:16]` 非敏感审计摘要；历史事件缺失该字段时读取为 `""`。客户端不得把此摘要当作认证凭据。

读取增量事件、全局状态镜像和撤销/重做：

```bash
curl "http://127.0.0.1:8765/api/projects/PROJECT_ID/events?since=0"
curl http://127.0.0.1:8765/api/projects/PROJECT_ID/state
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/undo \
  -H "Content-Type: application/json" -d '{"confirmed":true}'
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/redo \
  -H "Content-Type: application/json" -d '{"confirmed":true}'
```

WebSocket 增量订阅地址为：

```text
ws://127.0.0.1:8765/api/events/stream?project_id=PROJECT_ID&since=0
```

### 1.3 LLM ChangeSet 提案

LLM 或脚本先创建可编辑提案，再预演，最后由人确认提交：

```bash
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/changesets \
  -H "Content-Type: application/json" \
  -d '{
    "title":"添加两个层级",
    "source":"llm_agent",
    "rationale":"数量来自用户；名称为待确认推断",
    "commands":[
      {"tool_id":"layer.add","params":{"name":"层级甲"},"client":"llm_agent"},
      {"tool_id":"layer.add","params":{"name":"层级乙"},"client":"llm_agent"}
    ]
  }'

curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/changesets/CHANGESET_ID/dry-run
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/changesets/CHANGESET_ID/commit \
  -H "Content-Type: application/json" -d '{"confirmed":true}'
```

整批提交是原子的；任一命令失败都不会产生部分状态。提交成功后，一次
undo 会撤销整批命令。

### 2. 获取和修改项目

```bash
curl http://127.0.0.1:8765/api/projects/PROJECT_ID
```

修改 JSON 后使用 PUT 保存：

```bash
curl -X PUT http://127.0.0.1:8765/api/projects/PROJECT_ID \
  -H "Content-Type: application/json" \
  --data-binary @project.json
```

PUT、`param.set`、ChangeSet 以及模型/测距等配置写入都受同一生命周期权限
边界约束；项目未签出时会被拒绝。`ui.*` 仅是视图投影状态，仍允许保存。

### 2.1 导出和导入完整项目状态

导出包含 `project` 与 `ui` 的可移植状态树 JSON：

```bash
curl -o project.mujoco-studio.json \
  http://127.0.0.1:8765/api/projects/PROJECT_ID/export-json
```

签出状态不能导出。普通签入导出物导入为新的签入项目；基线导出物会保留
基线只读属性，并额外生成一个可继续签出的工作副本。

导入时把文件内容放入 `data`。Hub 会同时传 `target_category`，因此导入默认落到当前选中的项目文件夹；未传该字段的旧 API 调用继续保留源分类。服务会创建新的项目 ID，避免覆盖现有项目：

```bash
curl -X POST http://127.0.0.1:8765/api/projects/import-json \
  -H "Content-Type: application/json" \
  -d '{"data":{"format":"mujoco_studio_project","format_version":1,"state":{"project":{},"ui":{}}},"target_category":"机械臂/夹爪"}'
```

模型二进制不嵌入**模型 JSON**。模型 JSON/完整包导出还会剥离仅属于当前部署环境的 `metadata.vz_push`。完整压缩包交换可一起携带数模、交付数据、Hub 时序库与适用的存档日志。

### 2.1.1 导出 / 导入完整压缩包

只有工程师/管理员可使用完整包；签出模型必须先签入。导出：

```bash
curl -o project.mujoco-project.zip \
  http://127.0.0.1:8765/api/projects/PROJECT_ID/export-bundle
```

导入使用 multipart，并显式指定当前 Hub 文件夹：

```bash
curl -X POST http://127.0.0.1:8765/api/projects/import-bundle \
  -F 'target_category=机械臂/夹爪' \
  -F 'file=@project.mujoco-project.zip;type=application/zip'
```

V2.13.5 写出的完整包 format 为 `mujoco_studio_project_bundle` v2，包含 `model/model.json`、`properties/model_assets/`、`properties/delivery/`、`properties/time_series_library/`、`properties/archive_logs/` 及带 SHA-256 inventory 的 `manifest.json`。导入器同时支持旧 v1 与新 v2；未知更高版本会拒绝。checked-in 模型导出时先把公共资产和 Hub 时序 sidecar 复制到隔离快照再压缩，不写源目录；导入时为目标分类创建不冲突的新公共资产文件夹并恢复时序库。baseline 会冻结私有数模、交付数据和 Hub 时序库，本体不携带普通 versions 历史；导入时同时生成可编辑工作副本并恢复对应 sidecar。VZ 本地 `time_series_workspace/` 不属于 Hub 完整包。

### 2.2 导出和导入建模信息

建模信息使用与 MuJoCo XML Tool V21.4.3 兼容的
`mujoco_modeling_exchange` 2.0 格式，不包含项目生命周期和 UI 状态：

```bash
curl -o modeling_info.json \
  http://127.0.0.1:8765/api/projects/PROJECT_ID/export-modeling-info

curl -X POST http://127.0.0.1:8765/api/projects/import-modeling-info \
  -H "Content-Type: application/json" \
  -d '{"data":{"format":"mujoco_modeling_exchange","schema_version":"2.0"}}'
```

导入会建立一个新的签入项目。接口同时兼容旧版 schema 1.0；完整项目导入口
会拒绝建模信息文件，避免两种 JSON 类型混用。

### 3. 验证与生成

```bash
curl -X POST "http://127.0.0.1:8765/api/projects/PROJECT_ID/validate?check_files=true"
curl -X POST "http://127.0.0.1:8765/api/projects/PROJECT_ID/generate?check_files=true"
```

### 3.1 重扫或上传 STL/OBJ

统一服务器模式下，重新扫描当前项目已经托管的模型资产（本机和远程浏览器行为一致）：

```bash
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/meshes/rescan
```

兼容端点 `/meshes/scan` 允许显式服务器路径，仅在部署启用桌面能力时开放；远程 Web 工作流不得依赖它。

上传模型到项目的便携资产目录：

```bash
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/meshes/upload \
  -F "files=@part.stl" \
  -F 'relative_paths=["part.stl"]'
```

读取模型文件清单：

```bash
curl http://127.0.0.1:8765/api/projects/PROJECT_ID/meshes
```

### 3.2 让 LLM 读取并修改任意输入参数

先读取稳定参数路径目录。返回值中的 `path` 是基于实体 ID 的稳定路径，`index_path` 是兼容旧客户端的序号路径：

```bash
curl http://127.0.0.1:8765/api/projects/PROJECT_ID/parameters
```

局部写入时不需要回传整个项目。下面同时给参数路径建立别名，并让 LLM 修改层级名称、旋转轴与变量：

```bash
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/parameters/apply \
  -H "Content-Type: application/json" \
  -d '{
    "aliases":{"arm_name":"layers.@LAYER_ID.name"},
    "values":{
      "arm_name":"rotating_arm_v2",
      "layers.@LAYER_ID.joints.@JOINT_ID.axis":"0, 1, 0",
      "variables.speed_scale":1.2
    }
  }'
```

接口会拒绝不存在的路径、项目 ID 和实体 ID 等只读字段，并把写入记录为可撤销事件；普通写入不会自动生成版本存档。ID 路径不会因为在列表前方插入或删除其他实体而改变；`layers.0.name` 这类旧路径继续可用。

### 3.3 项目 Hub、历史版本与项目对比

```bash
curl http://127.0.0.1:8765/api/projects/PROJECT_ID/preview
curl http://127.0.0.1:8765/api/projects/PROJECT_ID/versions
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/archive
```

`POST /archive` 显式生成一个全量版本；V2.9.7.1 起**每次签入**也会进入同一存档链，而签出不创建版本。默认硬上限为最近 20 个版本，手动存档与签入版本合计计数；创建基线不会再把源模型历史额外压缩到 3 个。基线模型本身仍不暴露普通存档链。

回收站资源沿用 7 天保留/恢复语义；管理员和工程师还可以永久删除一个已经在回收站中的有效条目：

```bash
curl http://127.0.0.1:8765/api/recycle-bin
curl -X POST http://127.0.0.1:8765/api/recycle-bin/TRASH_ID/restore
curl -X DELETE http://127.0.0.1:8765/api/recycle-bin/TRASH_ID
```

`DELETE /api/recycle-bin/{trash_id}` 是不可逆物理删除。服务端会校验受控 trash id、路径边界、metadata 与 `project/project.json`，损坏或越界条目会 fail-closed 拒绝；Guest 无权调用。Hub 的多选/全选只是把多个已确认 trash id 逐条调用该接口。

调用预设的 `compare-variable-sets` 对比 Skill：

```bash
curl -X POST http://127.0.0.1:8765/api/project-comparisons \
  -H "Content-Type: application/json" \
  -d '{
    "project_ids":["PROJECT_A","PROJECT_B"],
    "variables":["speed_scale","EndTime"],
    "skill_id":"compare-variable-sets"
  }'
```

响应包含各项目的变量、层级/运动副/驱动段/测距对计数、测距最小值以及数值变量的最小值、最大值和跨度，适合作为 LLM 对比工具的结构化输入。

### 4. 提交仿真并等待

```bash
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/simulate
curl http://127.0.0.1:8765/api/jobs/JOB_ID
```

任务状态依次为 `queued`、`running`、`completed`。失败时为 `failed`，用户停止后为 `cancelled`。

### 4.1 打开原生 MuJoCo Viewer

Viewer 是 `read_only` 工具，通过统一命令端点调用，不需要 `confirmed`：

```bash
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/commands \
  -H "Content-Type: application/json" \
  -d '{
    "command":{
      "tool_id":"sim.open_viewer",
      "params":{"check_files":true,"loop":false,"playback_speed":1.0},
      "client":"script"
    }
  }'
```

成功响应包含独立 Viewer 进程的 PID、生成场景/驱动文件和日志路径。原生窗口显示在运行后端的本机桌面，而不是发起 HTTP 请求的远程电脑。

V2.9.7 起，本机 Viewer 以生成工作区为 `cwd`，同工作区 scene/drives/Gantt/trajectory 参数优先使用相对路径；后端仿真/寻优加载生成 XML 则统一经过既有 Unicode/VFS 兼容层，避免 Windows 中文/UTF-8 项目目录把绝对路径直接交给 MuJoCo parser。远程 Windows Client 仍使用 Server 下发的 Viewer bundle，不直接读取 Linux 服务器文件系统。

### 4.2 Viewer 后端赋值控制

已打开的 Viewer 每 250 ms 投射 `project.viewer_control`。人类在原生控制窗中的操作也通过同一个 `param.set` 命令回写，因此可追溯、可撤销，并可由 LLM 托管。常用路径：

| 路径 | 含义 |
|---|---|
| `project.viewer_control.time_s` | 动画时间与进度条定位 |
| `playing` / `direction` / `speed` | 暂停/播放、正倒放、0.1x–2.0x |
| `show_scatter` / `show_distance_lines` / `show_distance_labels` | 撒点、胶囊线、间距标签 |
| `motor_mode` / `motor_values` / `decoupled_drive_ids` | 电机模式、目标值与解耦集合 |
| `trajectory.selected_meshes` | 单选或多选 STL 整体质心目标 |
| `trajectory.recording` / `sample_hz` / `point_size` / `color` | 轨迹录制配置 |
| `trajectory.clear_revision` / `centroid_probe_revision` | 删除轨迹、刷新质心坐标的动作序号 |
| `axes_enabled` / `gantt_enabled` / `active_panel` | 跟随图表开关与导航页 |

例如把 Viewer 定位到 3.5 秒：

```json
{
  "command": {
    "tool_id": "param.set",
    "params": {
      "path": "project.viewer_control.time_s",
      "value": 3.5,
      "intent": "检查 3.5 秒时的机构姿态"
    },
    "client": "llm_agent"
  },
  "confirmed": true
}
```

### 5. 启动优化

```bash
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/optimize
```

优化范围、次数、筛选条件和目标都保存在项目的 `optimization` 字段中。

### 6. 调用智能体 Skill

```bash
curl -X POST http://127.0.0.1:8765/api/projects/PROJECT_ID/agent-runs \
  -H "Content-Type: application/json" \
  -d '{"skill_id":"simulate-report","goal":"检查、生成并仿真当前项目"}'
```

## 主要接口

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | 服务与 MuJoCo 环境状态 |
| GET/POST | `/api/projects` | 项目列表/创建 |
| GET | `/api/recycle-bin` | 列出当前有效回收站项目 |
| POST | `/api/recycle-bin/{trash_id}/restore` | 恢复一条回收站项目 |
| DELETE | `/api/recycle-bin/{trash_id}` | 永久删除一条有效回收站项目（管理员/工程师，不可逆） |
| GET | `/api/tools` | 自描述工具注册表与 LLM function 定义 |
| POST | `/api/projects/{id}/tools/{tool}/dry-run` | 零副作用工具预演 |
| POST | `/api/projects/{id}/commands` | 统一命令入口 |
| GET | `/api/projects/{id}/state` | 权威状态树镜像 |
| GET | `/api/projects/{id}/events` | 增量语义事件流 |
| WS | `/api/events/stream` | 实时事件订阅 |
| POST | `/api/projects/{id}/undo`、`redo` | 撤销/重做 |
| GET/POST | `/api/projects/{id}/changesets` | 持久化提案列表/创建 |
| POST | `/api/projects/{id}/changesets/{cs}/dry-run` | 批次预演与 UI 回填值 |
| POST | `/api/projects/{id}/changesets/{cs}/commit` | 人工确认后原子提交 |
| POST | `/api/projects/{id}/diff` | watched paths 版本差异 |
| GET | `/api/projects/{id}/core-artifacts` | 内容寻址工件列表/读回 |
| GET/PUT | `/api/projects/{id}` | 读取/保存完整项目 |
| GET | `/api/projects/{id}/export-bundle` | 导出模型 JSON + 数模资产 + 交付数据 + 可用存档日志完整包 |
| POST | `/api/projects/import-bundle` | 安全导入完整包到指定 Hub 分类并注入公共数模资产 |
| POST | `/api/projects/{id}/external-motion-csv` | 导入 V21.5 兼容外部运动 CSV；将时间-位置点表内嵌到目标驱动段 |
| POST | `/api/projects/{id}/mapping-csv` | 导入驱动映射 CSV；将映射点表内嵌到目标驱动段 |
| GET | `/api/projects/{id}/preview` | Hub 全局预览、变量、甘特和测距摘要 |
| GET | `/api/projects/{id}/versions` | 显式存档、每次签入存档与基线历史 |
| POST | `/api/projects/{id}/archive` | 生成一个全量版本存档 |
| GET | `/api/projects/{id}/parameters` | 全部可 API 化标量参数目录 |
| POST | `/api/projects/{id}/parameters/apply` | 使用路径或别名批量写入参数 |
| POST | `/api/project-comparisons` | 预设 Skill 批量对比项目变量与指标 |
| GET | `/api/project-comparison-skills` | 列出项目对比 Skill 及输入约定 |
| POST | `/api/projects/import-legacy` | 迁移旧版 JSON |
| POST | `/api/projects/{id}/validate` | 全链路验证 |
| POST | `/api/projects/{id}/generate` | 生成模型和驱动产物 |
| GET | `/api/projects/{id}/meshes` | 模型文件清单 |
| POST | `/api/projects/{id}/meshes/rescan` | 重扫当前项目已托管资产；无需桌面能力 |
| POST | `/api/projects/{id}/meshes/scan` | 兼容：扫描服务器显式路径（桌面能力） |
| POST | `/api/projects/{id}/meshes/upload` | 上传 STL/OBJ 到项目 |
| POST | `/api/projects/{id}/meshes/adaptive` | 自适应添加同前缀文件族 |
| POST | `/api/projects/{id}/meshes/repair` | 删除失效引用并校正大小写 |
| POST | `/api/projects/{id}/mujoco-check` | 使用 MuJoCo 加载模型 |
| POST | `/api/projects/{id}/simulate` | 提交轨迹仿真 |
| POST | `/api/projects/{id}/optimize` | 提交批量优化 |
| GET/POST | `/api/skills` | 列出/创建 Skill |
| POST | `/api/projects/{id}/agent-runs` | 运行智能体工作流 |
| GET/PUT | `/api/projects/{id}/llm-config` | 读取/修改非敏感 LLM 配置并单独保存密钥 |
| POST | `/api/projects/{id}/llm-test` | 测试 OpenAI-compatible 对话接口 |
| GET | `/api/projects/{id}/agent-conversation` | 获取项目最近的智能体对话窗口 |
| POST | `/api/dialogs/select-directory` | 打开后端桌面 STL/OBJ 路径选择器（只读选择） |
| POST | `/api/dialogs/select-project-json` | 从默认项目目录选择并读取项目 JSON |
| GET/POST | `/api/jobs/{id}` | 查询/停止任务 |
| GET | `/api/projects/{id}/artifacts` | 列出生成物 |
| GET | `/api/model-types` | 返回与服务端真实目录对应的嵌套模型类型树 |
| POST | `/api/model-types/{path}/move` | 移动模型类型目录或调整同级顺序 |
| GET | `/api/projects/{id}/files` | 返回 project.json、模型资产、交付与派生产物四组文件清单 |
| GET/PUT | `/api/projects/{id}/files/project-json` | 下载或经校验替换当前模型 project.json |
| GET | `/api/projects/{id}/files/assets/{path}` | 下载当前模型目录内的白名单资产 |

V2.3.9.4 中 `/meshes/upload` 也接收 OBJ 的 MTL 与常见纹理依赖；请求仍须至少包含一个
STL 或 OBJ。写端点要求工程师/管理员身份且当前模型已由该账号签出。上传相对路径与下载解析路径
都执行目录归属检查，不能用它们访问模型目录之外的文件。

## V2.3.1 可托管界面状态

项目名称、STL 路径和层级/运动副配置位于 `project.*`；数模双列显示位于
`ui.model.mesh_two_columns`。Viewer 坐标系与甘特图弹窗仍由
`project.viewer_control.axes_enabled`、`gantt_enabled`、`active_panel`、
`axes_font_size` 和 `gantt_font_size` 控制。人工操作、脚本和 LLM 均通过
统一命令入口赋值。

Viewer 甘特图尺寸继续收敛到 `project.viewer_control.gantt_width_px` 与
`gantt_row_height_px`。控制窗滑块和后端/LLM 参数赋值调用同一命令路径。
Windows 未设置 `MUJOCO_STUDIO_DATA` 时，项目根目录默认为 `E:\Mujoco_Project`；
`GET /api/health` 的 `data_root` 返回实际目录。

LLM 的 API 地址、模型、上下文轮数以及是否读取实时变量、操作日志和产物位于
`project.agent_settings`，因此人工 UI、脚本与智能体看到同一状态。默认上下文为 20 轮。
API 密钥是例外：它是凭据而非项目状态，只能通过 `PUT /llm-config` 写入后端私有凭据区，
读取接口仅返回是否已配置及掩码，不会返回明文，也不会进入事件流和下载产物。

## Python 调用示例

```python
import time
import httpx

base = "http://127.0.0.1:8765"
project = httpx.post(f"{base}/api/projects", json={"name": "Python demo", "demo": True}).json()

issues = httpx.post(f"{base}/api/projects/{project['id']}/validate").json()
assert not [item for item in issues if item["severity"] == "error"]

job_id = httpx.post(f"{base}/api/projects/{project['id']}/simulate").json()["job_id"]
while True:
    job = httpx.get(f"{base}/api/jobs/{job_id}").json()
    if job["status"] in {"completed", "failed", "cancelled"}:
        break
    time.sleep(0.25)

print(job["result"])
```

## Skill 安全模型

自定义 Skill 只能使用以下工具：

- `validate_project`
- `generate_project`
- `run_simulation`
- `run_optimization`
- `save_project`

即使配置了外部 LLM，LLM 也只能在这个白名单内规划步骤，不能执行命令、读取任意文件或绕过项目验证。
