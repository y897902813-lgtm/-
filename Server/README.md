# MuJoCo Studio Server V2.16.11.6
### V2.16.11.6 动画正交视角 cam_fovy 范围

动画播放的原生 MuJoCo 控制窗口：勾选“开启正交视角”后，`cam_fovy` 控件取值范围为 **0.05–2.0**，步长 `0.05`、默认值 `0.8`；滑块值直接用于当前正交渲染全局/固定相机参数。透视状态下的默认全局视场角不变。此操作属于 Viewer 会话 UI，不更改 ProjectSpec、冻结模型或仿真精度。详情与测试边界参见 CHANGELOG 与独立开发证据包。

### V2.16.11.5 Hub 基线关键数据气泡修复

创建基线时会在完整冻结项目和历史记录成功保存后，预生成其冻结关键数据气泡快照。历史基线如缺少 `core/hub_critical_data.json`，Hub 列表首屏仍优先返回，后台按基线 ID + 冻结时间有界重建；缓存为可删除的 L3 派生文件，不是新 ProjectSpec 字段。首次冷缓存可在有界短间隔的轻量 summary 补查中恢复；正常 Hub 自动刷新不会再用临时 `pending` 抹除同一冻结身份已验证的气泡，选中基线的完整 preview 会恢复 ◆ 冻结标志。不同基线/归档身份不混用数值。后台失败会写日志并退避，不触碰冻结模型数据。详细检测见独立开发证据包。

### V2.16.11.4 坐标系工具栏

结果查看 → 坐标系的“布局 / 后处理”始终同一行；后处理主区仅保留“导出NX脚本”，CSV、表格、坐标系高度和游标位于“更多”。布局自适应、增删布局和跨模型导入位于“布局管理”；窄编辑区会把同一个布局切换、命名和增加坐标系控件移进该菜单。没有更改任何导出 API、坐标系 ProjectSpec、测距缓存或权限规则。完整回归清单在独立开发证据包中。



## SSH 启动、查询与一键停止（新增）

在 `Server` 目录内：

```bash
python run.py           # 启动 Hub + 集成 VZ
python run.py status    # 查看本次部署受管 Hub/VZ 的 PID 与端口
python run.py stop      # 从任意另一个 SSH 终端安全停止这套受管服务
python run.py stop --legacy-vz  # Linux：仅一次性回收确认属于本源码的旧版 VZ 监听进程
```

原 SSH 终端按 **Ctrl+C**，`run.py` 会在离开 Uvicorn 后清理其独立进程组中的 VZ 子进程。断线 SIGHUP/SIGTERM 同样执行回收；如果被 `kill -9` 强制结束（不可拦截），下次 `python run.py stop` 或 `start` 会依据仅运行时的 PID/出生时间/脚本身份记录恢复被遗留的受管 VZ 进程。进程记录：`<DATA_ROOT>/.runtime/studio_launcher.json`；文件锁：`studio_launcher.lock`，**不要手动删除运行中的锁文件**。

**不会盲目 `kill -9` 所有监听端口的 PID。** 如果升级前的旧版 VZ（没有新进程记录）仍占用端口 8877，新的启动会明确拒绝复用。Linux 下可先执行 `python run.py stop --legacy-vz`：工具会严格比对 **8877 端口实际监听 socket + VZ run.py 脚本真实路径 + PID/启动标识**；若属于其他程序，则拒绝操作。也可以手工检查：

```bash
ss -ltnp '( sport = :8877 )'
PID=12345              # 用上一命令查得的真实 PID 替换示例数字
ps -fp "$PID"
kill -TERM "$PID"       # 只有确认确实是旧 VZ 后执行
```

若端口已从 `ports.json` 改为非默认值，请将 `8877` 换成实际 `vz` 值；不要误杀系统服务。若服务通过 **Docker** 运行，请使用 `python docker_ports.py down`（而不是在宿主机上 `python run.py stop`）。**Client 的 `client` 端口是每台用户电脑本地的 `127.0.0.1` 桥，不能从远程服务器统一杀掉；用户在本机结束 Client 即可。** 不改变 `server_ip/hub/client/vz` 的统一配置或原权限/数据协议。

# MuJoCo Studio Server 2.16.11.1

## 部署端口统一配置（V2.16.11.1 维护补丁，无版本号变更）

Client 连接服务器的 IP 与三个 HTTP 端口统一在 **`Server/ports.json`** 中调整，然后重启相关服务：

```json
{"server_ip": "10.13.90.107", "hub": 8765, "client": 8766, "vz": 8877}
```

- `server_ip`：Client 需要连接的 Hub 服务器 IP（默认 `10.13.90.107`）；不是 Server 监听地址，也不是 Client 本机的监听地址。
- `hub`：Server/Studio/Lab 网页与 API，浏览器访问 `http://服务器IP:hub`。
- `client`：每台用户电脑上的本地 Viewer 桥，**始终监听 `127.0.0.1`**，不能开放到 `0.0.0.0`。
- `vz`：Server 随 Hub 启动的 VZ 工程师/用户应用。

直接运行 `cd Server && python run.py`：Hub、集成 VZ、Viewer 内部回调会读取这三个值；浏览器通过已有 `/api/health.network_ports` 接收 VZ / Client 端口，不再写死。完整集成源码内执行 `python Client/main.py` 也读取同一个文件，Client 0.3.9 / VZ 0.3.2.1 协议版本不变。**在独立电脑安装 Client 时**，它无法直接读取服务器磁盘，应把同一份 `Server/ports.json` 复制到远端 `Client/ports.json` 后重启 Client；远端 Client 也从复制的 `Client/ports.json.server_ip` 获取服务器 IP（环境变量 `MUJOCO_STUDIO_SERVER_IP` 仍可覆盖），不再要求修改 `Client/main.py`。变更服务器端口还需修改防火墙、反向代理或负载均衡器的外部映射。

Docker Compose 使用 `cd Server && python docker_ports.py up --build -d`，包装器根据同一文件设置 Hub 端口映射和容器实际端口。直接执行原生 `docker compose` 时，只会使用 Compose 环境变量/默认映射，**不会自动读取 JSON**；VZ 未授权，不默认向公网映射 VZ 端口；Client 本地端口也不会映射到 Docker 容器。已有环境变量 `MUJOCO_STUDIO_PORT`、`MUJOCO_STUDIO_CLIENT_PORT`、`VZ_PORT` 若显式设置，将覆盖 JSON 值；删除或更新这些变量后才能保证只编辑一处。

端口检查严格拒绝 0、65536、浮点、字符串或三端口重复。`ports.json` 为部署配置，不写入 ProjectSpec、基线或历史归档。Lab UDP 接收端口属于另一套可配置 UDP 目的地，**不在这三个 HTTP 端口之内**。


## V2.16.11.1 — 基线复用资产选择与交付刷新

- 使用基线时弹出数模资产处理对话框，**默认绑定现有公共数模文件夹，不复制冻结数模**；明确切换“复制冻结数模”才生成新公共目录。Hub 首选基线原资产引用；其他选择须由用户显式确认。后端验证类别与文件存在性，不满足时不给创建半成品模型。
- 新 POST `/api/projects/{id}/delivery-files/refresh` 在既有 heavy 后台 Job 中重生 **NX AFU、甘特图 PNG、模型 JSON 和仿真 XML**；保留动画 HTML、表格 CSV/TSV 和时序库。权限遵循旧交付 API，冻结基线与访客禁止写入。
- 动画生成后台任务提示移至 body 层，浮于坐标系和顶部工具栏上方。全屏阻断 overlay 仍是最高优先级。
- 旧同步 `/fork` 未指定资产策略时仍复制数模；Client 0.3.9、VZ 0.3.2.1 不变，Lab 历史消息兼容保留。测试结果见独立开发证据包；真实 Windows/MuJoCo/多用户 I/O 性能未验收。

## V2.16.11 — 基线复用后台任务化与 Hub 项目列表首屏独立恢复

- **现象与风险**：使用较大基线时，同步复制数模/交付/结果会长时间占用请求；Hub 原本需等待项目列表、模型类型、回收站等多个请求，还会递归扫描所有模型资产，造成约 30 秒“卡住、空白、掉线”的现场症状。该时间为用户报告，非当前测试环境复测值。
- **任务分离**：Hub 的“使用基线版本”改为 `POST /api/projects/{id}/fork?background=true`，受理返回 `202 + job_id`，复用现有 JobManager heavy lane、用户任务上限及任务进度/取消接口。省略参数的同步旧 API 原样保留。相同模型、账号、租约、资产文件夹的同时重复提交通过原任务表 + 原子提交锁复用同一 Job。
- **发布安全**：完成所有表格、数模、运动时序、交付资产复制并通过交付完整性检验后才发布新模型；复制期间的 `.baseline_fork_pending` 仅用于 L3 可见性门禁，严禁迁移到交付资产。失败、取消或租约失效按现有模型/资产所有权回滚，不碰原冻结基线。
- **Hub 首屏**：项目目录扫描使用模型根 `project.json` 定向裁剪，不遍历该模型的 STL/结果/交付子树；`detail=summary` 只读取可验证的已有关键数据缓存，未缓存时以待加载状态显示，不阻塞项目卡片。模型类型、回收站与预览数据不阻塞首轮目录显示；失败提示并有限频自动重试，不伪造空项目。
- **诊断/兼容**：后端记录慢 catalog 与 fork 阶段/总耗时，不声明固定延迟缩短幅度。Server/Studio/Lab 2.16.11；Lab 白名单保留 2.16.10.2；Client 0.3.9 与 VZ 0.3.2.1 不变，无新增业务工具、依赖、模型持久字段。独立开发证据包含合成压力/回归；Windows 原生模型、真实生产服务与浏览器端到端需现场验收。


## V2.16.10.2 — 坐标系顶层工具栏区分与驱动双列竖向宽度拖拽

- 仿真结果坐标系工具栏添加醒目的浅色渐变底、左侧蓝色标识线、模块强调边框与阴影。保留布局/后处理两组与每个坐标系单行名称/曲线编辑，不增加可见标题。
- 驱动设置保持同一 `#driveList` 行优先排序；双列中间增加可拖动的竖向分隔条，实时按百分比调整左右栏宽；键盘左右箭头微调、Home/End 边界、双击恢复 50:50。调整不触发仿真、模型保存或驱动重排序。
- 两栏至少约 350px 的宽度保护；小屏幕及快速寻优分栏收窄时自动降单列，回到可用宽度自动恢复上一次会话比例。新比例仅在编辑会话内有效，不写入 ProjectSpec。
- Server/Studio/Lab 2.16.10.2；Lab 保留 2.16.10.1 消息兼容；Client 0.3.9、VZ 0.3.2.1 不变，无新增业务 Tool、HTTP API 或依赖。Chromium UI 和历史回归见独立证据包；Windows 原生 MuJoCo/WebGL2 全栈仍待现场验收。

## V2.16.10.1 — 甘特图运动段编辑弹窗 Enter 保存与下拉选项精简

- 仿真结果查看 → 甘特图双击色块：下拉选项改为「行程 / 结束位置」和「速度 / 时长」，只调整文案、不修改表达式计算能力与模型数据。
- Enter（文本输入框）与「保存」按钮统一触发原 `saveGanttSegmentDialog` 提交逻辑；「取消」和右上角关闭变为独立非提交按钮，Esc 取消。
- Enter 不触发页面级仿真快捷键；继续采用原权限、草稿更新与保存调度，无新增 HTTP API、Tool、ProjectSpec 字段或运行依赖。
- 版本：Server/Studio/Lab 2.16.10.1；Client 0.3.9、VZ 0.3.2.1 不变。原生 Chromium 独立弹窗交互、语法和回归测试见独立开发证据包；真实 Windows/MuJoCo/完整浏览器集成仍需现场验收。

## V2.16.10 — Hub 表格资产、映射表双向导入导出

- 模型属性新增表格资产（`assets/tables`）：映射/外部运动 CSV 导入先保存原始文件副本，再更新 JSON 内嵌点表；同一逻辑类型/驱动/运动段固定物理文件并原子覆盖。
- 映射电机与外部运动段新增 CSV 导出：以内嵌点表生成 float64 无损 CSV，更新资产后下载。外部运动导出统一是位置点表。
- 坐标系 CSV 与 TSV 导出同时按稳定轴 ID 归档进表格资产，现有交付数据表格文件夹仍保留；基线冻结和临时会话不得写正式资产。
- 不修改模型 JSON / V21.5 / Client / VZ 协议。详见架构第 121 节。

## V2.16.9.1 — 结果坐标系编辑与布局持久化

- 顶部工具栏分浅色“布局 / 后处理”两个模块：单/双列滑动切换、增删/重命名布局、增加坐标系、自适应坐标系、CSV、Excel 可读 TSV 和加宽的坐标系高度滑块。原 NX AFU/游标移入“更多”。
- 坐标系头部固定单行：名称与曲线对象并排；添加曲线/颜色/运算/删曲线折叠在“设置”。删除坐标系按钮只保留一处。
- 保留永久不可删的“测距对布局”：每次进入，按当前 `distance_pairs[].id/name` 自动补齐、更名、排序并删除失效默认轴；不改变原测距轨迹/采样或 API。
- 命名布局修改自动更新既有 `result_layout.presets[].axes` 快照，不需要额外点保存布局；按 Enter 的模型保存动作仍遵守租约/ACL 和物理输入 fingerprint。
- 表格导出为 Excel 可直接打开的 UTF-8 BOM `.tsv`，使用原合并 CSV 数据语义，并在测距未就绪时拒绝导出；保留旧 CSV 和 NX AFU 操作。
- 原生 Windows、真实 MuJoCo 模型、Chrome/Edge WebGL2 与租约集成仍需部署端回归验证。


## V2.16.9 — 所选测距对与共享几何索引

**发布说明**：正式源码部署 ZIP 按架构第三十三-A 部分只包含运行/部署源码与说明；`scripts/v2169_*_regression`、`scripts/v2169_distance_live_benchmark.py` 等验收脚本及开发报告在**独立 V2.16.9 开发证据包**中。要执行以下 `scripts/` 回归命令，请先将开发证据包内对应测试文件放回 `Server/scripts/`，不要将测试文件混入正式部署目录。

- 支持 `GET /api/projects/{project_id}/distance-curves?pair_id=A&pair_id=B`、`POST` JSON `{"pair_ids":["A","B"]}`；省略参数与旧单对路径均兼容。权限与冻结快照不改变。
- 同仿真同租约测距只用一个 Job（可动态追加待处理 wave），重型任务使用 JobManager heavy lane，真实轨迹帧与 Viewer `exact_all_samples` 不降采样。
- 自定义结果布局可选择 `pair:` 数据源；Enter 仅在服务器物理输入与资产指纹验证匹配后复用轨迹。
- 当前环境无法运行原生 Windows MuJoCo/WebGL2；请在相同硬件、同一 STL/OBJ 上运行 `python scripts/v2169_distance_live_benchmark.py --scene ... --drives ... --trajectory ...` 验证 1/2/5/10 对及实际 100 秒瓶颈。



## V2.16.8 — 完全精确测距加速 / 队列保护 / HTML 绿色加粗测距线

- **原因**：动画 HTML 是异步导出，并最多取 20 FPS；坐标系按轨迹 0.01s 间隔计算全帧与所有表面采样点。一条测距对若含多个 geom，会对几何组合进行大量 KD 树查询，100s 延迟取决于真实网格数量和CPU。
- **查询加速**：原 `viewer_runner._nearest_points_local_kd` 增加每个 geom 表面采样集的包围球保守距离下界、按下界排序、不可改进组合跳过、KD 最近距离上界。保留全部表面样本、逐帧输出与 Viewer 相同的计算口径；运动学同一 `qpos` 原样重复的帧复用上次精确测距结果。只加局部缓存，不改变采样精度、轨迹与 `ProjectSpec`。
- **并发去重**：保留原用户 JobManager 最多 2 个任务的配额。对同模型同租约同冻结轨迹进行原子提交去重，避免多次 Enter/刷新重复创建测距计算；已有不同测距任务时返回可重试 429，前端按 `retry_after` 自动排队、轮询，不再重复报错。
- **可测量**：完成的 `distance-curves` 数据增添 `timings_seconds` 非持久 API 诊断项，提供模型/轨迹读取、表面采样与 KD 构建、精确测距帧、总耗时、重复姿态帧数量和几何搜索数量，便于在真机判断瓶颈。
- **HTML 绿色线**：原生 Viewer 非碰撞线和新导出的 HTML 均使用 `(0.20,0.90,0.45,1.0)` 绿色；HTML WebGL2 改用 2 个三角形组成的 4px 屏幕空间线段，解决 `gl.lineWidth` 在浏览器常常受 1px 限制而无法加倍的问题。碰撞/无效值红色告警保持。**旧导出 HTML 不会被追溯改写，需重新导出。**
- **兼容与测试**：无新增业务 Tool、ProjectSpec 字段、API 路由、任务种类和生产依赖；沿用 `simulation.compute_viewer_distance_curves`、`_measure_pair`、`parallel_sampling.iter_frame_batches`、`jobs.list`、`requestSelectedDistanceCurves`、原 HTML exporter。Server/Studio/Lab = **2.16.8**，Client 0.3.9 / VZ 0.3.2.1 不变。运行 `python scripts/v2168_distance_precision_and_queue_regression.py`、`python scripts/v21664_animation_threshold_regression.py`、`node scripts/v2167_ui_layout_regression.cjs`；WebGL2 实机像素检查见 `scripts/v2168_html_green_browser_smoke.py`。详细门禁与限制见 `../development/V2.16.8/TEST_REPORT.md`、架构第 118 节。

---

## 历史：V2.16.7

## V2.16.7 — 测距选择滚动、紧凑坐标系与布局管理

- **对象 A/B 多选**：弹窗内连续单击选择不会滚回第一项；保留当前列表位置，选中状态与模型 JSON 仍由既有 `distance_pairs[].objects_a/objects_b` 保存。
- **坐标系按钮**：“当前曲线”和“原值 / 运算”下拉框、删除坐标系按钮不再位于折叠工具区；快速曲线编辑栏始终可用，整体控件与文字缩小一号，单双列及只读显示保持。
- **布局管理**：当坐标系和存档完全一致时只显示存档名，不出现“当前布局”；一旦新增、修改、删除曲线或调整坐标系则出现“当前布局（未保存）”。从该编辑状态切换其他布局必须先命名保存，取消不切换。“＋ 新建布局”创建可命名的空白工作布局。原先的自动 `syncActiveResultPreset` 覆盖行为已移除，避免模型提交把未显式保存的编辑偷偷写入旧布局。
- **升级范围**：继续使用 `ProjectSpec.result_layout.axes/presets/active_preset_id`、`state.project.distance_pairs`、`markDirty`/本地草稿/`project.replace` 与 `renderResultViewer`。无新增后端业务 Tool/路由/Job/schema 字段、无新依赖。Server / Studio / Lab 版本更新为 `2.16.7`；Client `0.3.9`、VZ `0.3.2.1` 保持不变。

执行 `node scripts/v2167_ui_layout_regression.cjs`，复验 `node scripts/v2165_frontend_regression.cjs` 和 `node scripts/v21661_axes_layout_regression.cjs`；如环境已配备 Python Playwright 和 Chromium，可加跑 `python scripts/v2167_browser_smoke.py`（仅隔离界面测试、无新生产依赖）。完整服务端环境安装好 `Server/requirements.txt` 后再运行 `python scripts/self_check.py`。部署时备份数据根，停止旧服务后整体替换并强制刷新浏览器缓存。真实浏览器和 Windows MuJoCo 交互仍需部署端验证。架构第 117 节与 `../development/V2.16.7/` 记录本次实施。

---

## 历史：V2.16.6.4

## V2.16.6.4 — 动画 HTML 测距可见阈值

在“仿真结果 → 左侧动画 HTML 设置”新增“自适应测距显示阈值 mm”，默认 25，可提前设定任意正数（例如 8.5）。修改后点击“刷新动画”/“导出动画 HTML”，服务器将其与其它 `animation_html` 设置一起保存并写入新的离线 HTML；播放页测距对勾选“自适应显示”时，仅展示距离（单位 mm）严格小于该阈值的测距对，标签显示实际配置值。关闭自适应后仍可查看全部有效测距对。

仍使用原有项目模型保存、HTML 动画 Job、独立离线渲染器和 Client 0.3.9 / VZ 0.3.2.1。该设置不修改原生 MuJoCo View 的阈值。新增回归：`python scripts/v21664_animation_threshold_regression.py`、`node scripts/v21664_animation_threshold_ui_regression.cjs`。架构第 116 节，报告 `../development/V2.16.6.4/`。

---

## 历史：V2.16.6.3

## V2.16.6.3 — MuJoCo View 正交右键拖动约 6.67 倍增益

打开原生 MuJoCo View，启用“开启正交视角”，使用右键或 Shift+右键拖动时，平移灵敏度由原生（`mjv_moveCamera` 内置 0.15 缩放）补偿为约 **6.67 倍**，目标为鼠标每移动 1px，正交画面也约移动 1px。旧版 3x 补偿依赖 Viewer 私有 GLFWwindow（部分系统不提供）的问题已修复。默认 Windows 使用当前进程焦点 GLFW 窗口检测右键，其他无法读取按键状态的平台使用保守的连续相机平移判断。透视、旋转、滚轮缩放、相机预设不加速。

复用原有 `viewer_runner.py` 工具及相机锁，无额外安装依赖或新 API/ProjectSpec 字段。执行 `python scripts/v21663_orthographic_pan_regression.py`；实际 Windows GUI 和 DPI 验收仍需部署电脑完成。新增架构第 115 节，测试记录 `../development/V2.16.6.3/TEST_REPORT.md`。V2.16.6.2 Enter、V2.16.6.1 坐标系单／双列、V2.16.6 测距对并行保持。

---

## 历史：V2.16.6.2

## V2.16.6.2 — 编辑时序默认同步、主动切换才提示保存

编辑模式中按 Enter **不再弹出“保存当前时序”提示**，而是继续同步当前模型的驱动配置并刷新坐标系。时序选择弹窗中的“＋ 新建空白时序”、点击已有 TSJSON、导入 HTML/TSJSON/CSV/Python 时，才通过原快照保存选择保护正在编辑的时序；取消或无效文件不改写当前驱动。只有显式点击“保存为 TSJSON”才另存独立命名快照。编辑时的服务器同步依然需要有效签出权限。

保留 V2.16.6.1 的坐标系单／双列及折叠能力，V2.16.6 的轨迹测距加速不变；Client 0.3.9 和 VZ 0.3.2.1 不升级。执行 `node scripts/v21662_timeseries_enter_regression.cjs`，实际浏览器与服务器多账号验收见 `../development/V2.16.6.2/TEST_REPORT.md`。本版本未增加业务 Tool/API。

---

## 历史：V2.16.6.1

## V2.16.6.1 — 坐标系单／双列与顶部操作折叠（2026-11-06）

仿真结果的“坐标系”标签新增单列／双列排列切换；双列在较窄面板自动回退单列。每个坐标系的首行、曲线概况和曲线图始终可见，曲线编辑、运算、CSV 等两组操作默认收起，可独立展开。坐标系排序、命名布局、只读浏览与旧仿真结果格式保持原样。

代码复用已有 `renderResultViewer`、`drawResultAxes`、`uiSet`、`result_layouts.js` 和 CSS 网格；没有增加 API 或模型 schema 字段。请执行 `node scripts/v21661_axes_layout_regression.cjs`。变更与限制见 `../development/V2.16.6.1/`，架构规范见第 113 节。Client 0.3.9 / VZ 0.3.2.1 不升级。浏览器升级后建议强制刷新。

---

## 历史：V2.16.6

## V2.16.6 — 测距对轨迹并行加速（2026-11-06）

当前完整源码基于 V2.16.5 更新。**测距对以已完成的轨迹为输入**，不会并行执行互相依赖的 `mj_step`；相反，在线程私有 `MjData` 中独立重建各帧 geom 姿态，复用 Viewer 原有完全精确 KD 测距。

- `distance-curves` 批量及单对 API 复用现有 Job，最多 5 个并行工作线程。分块至多 500 帧、按负载自动细分；主线程按全局帧号合并，部分结果按连续前缀、至少 5 秒间隔发布。
- 跳过不需要的完整动力学 forward（测距帧只执行 `mj_kinematics`）；共享只读模型/采样点/KD 树，线程独立查询数组。离线任务不准备 Viewer 散点绘图缓冲，数据精度/帧数/单位/最小值保持不变。
- HTML 导出保持 50 帧/批，Viewer 交互保持完全精确默认；冻结仿真、缓存、角色权限、ProjectSpec、Client 0.3.9、VZ 0.3.2.1 不改。升级后请先备份服务端数据与历史版本，并硬刷新浏览器。
- 运行新增 `python scripts/v2166_distance_parallel_regression.py`，现有前端/时序回归及编译检查。原生 MuJoCo/Windows/大模型需现场检查 1501 帧准确性和 5 秒性能目标，不能用模拟引擎的速度替代真机结论。

专项设计、验收、修改清单和校验见 `../development/V2.16.6/`；总体架构第 112 部分。

---

## 历史：MuJoCo Studio Server 2.16.5

## V2.16.5 — 完全精确并行测距、中文 CSV 与动画分批导出（2026-11-03）

- 实际输入为 2.16.3 完整包；本轮重新补入历史 2.16.4 所述缺项，再统一升级 Server / Studio / Lab 至 2.16.5。Client 0.3.9、VZ 0.3.2.1 和 Viewer bundle 协议保持不变。
- Viewer 动画控制默认“完全精确”；曲线使用同一 `_measure_pair` 的全部既定采样点，不再套用 4096 点低延时查询预算。相同冻结模型、采样参数和 qpos 下保证同一数值口径，非连续三角面几何精度承诺。
- 测距对布局触发批量后台任务：每帧一次 `mj_forward`，各对使用独立缓冲并行求值，最多 5 个测距线程。按原轨迹顺序输出，5 秒发布/轮询进度，完成提示；旧低延时缓存隔离，冻结仿真与基线不被改写。
- 坐标系工具栏增加命名布局存档、默认测距对布局、删除存档；保存名称、曲线、顺序，支持拖拽及方向键排序，测距原值曲线标注最小点时间和数值。复用 result_layout/project.replace，旧项目兼容默认空布局库，存档上限 50。
- Enter 同步前复用时序保存保护，支持新建、覆盖、不保存、取消；保留已有 Hub 折叠记忆、静态旧 HTML/Python 时序导入。Python 导入仍只读取静态清单，不执行任意脚本。
- 映射 CSV 支持 UTF-8、GBK/GB18030、带 BOM 的 UTF-16/32；忽略开头中文/英文表头及说明，支持逗号、分号、Tab、空白。新上传对非法数据行/NaN/无穷值明确拒绝，不改变原坐标或做运动积分；历史文件恢复继续容忍坏行、保留有效点。
- 动画 HTML 按 50 帧/批、最多 5 线程准备姿态与测距数据；只读共享模型、各线程私有 mjData 和查询缓冲。按原帧号合并，全局修正四元数连续性；临时文件原子发布，取消/失败保留旧文件。物理轨迹积分仍按原求解器执行，浏览器 WebGL 负责播放渲染。
- 真实 MuJoCo、API、前端逻辑及兼容检查记录见 `development/V2.16.5/TEST_REPORT.md`。大型机构不保证五秒算完；Windows/OpenGL 现场验收及完整真实浏览器 E2E 尚待执行。升级前备份数据、停止旧服务、替换源码并硬刷新浏览器；不要同时运行两版写同一数据目录。

## 2.16.2 实时甘特图 / 坐标系计算隔离 / Viewer PNG 修复

- 双击 Web 甘特图运动段修改后，无需按 Enter；简单数值先在浏览器立即绘制，170ms 防抖后通过只读草稿 `/preview` 获取权威时序（**不调用 `/simulate`，不上传为正式 ProjectSpec**）。复杂公式及映射以服务端投影为准。
- Enter 仍负责浏览器草稿提交与坐标系任务；重仿真 Job 进入独立计算通道，单进程至多 2 个 MuJoCo 计算子进程，用户并发限制保持有效，计算子进程仍可终止。
- 驱动曲线生成从“每驱动 × 每帧重复解析整份 schedule”改为“每帧一次解析，各驱动复用结果”，避免多驱动计算随驱动数量额外放大；旧数值精度不变。
- 闭链求解完成后的重复 `mj_forward` 移除；XML 生成、模型加载、闭链/轨迹、序列化的分阶段 `timings_seconds` 仍可用于现场测量瓶颈。
- MuJoCo Viewer 在启动前优先准备模型专属 `latest_gantt.png` + `latest_gantt.json`，没有该缓存时不使用风格不同的兼容 Gantt 替代品；Client 0.3.9 不安装 Pillow 也可通过 Tk 内置 PNG 解码显示图片。
- **兼容**：Server / Studio / Lab 2.16.2；Client 0.3.9、VZ 0.3.2.1、ProjectSpec、Bundle v2、Viewer schema 4 不变。部署前备份数据和版本历史目录，刷新 Web 静态缓存。未进行 Windows+MuJoCo 双账号 GPU 实测。

详见根目录 `V2.16.2_IMPLEMENTATION_AND_TEST_REPORT.md` 与 `Server/architecture_master_prompt.md` 第 110 节。

---

# 历史：MuJoCo Studio Server 2.16.1

## 2.16.1 操作与升级

- **编辑器进入**：双击打开已签出模型后直接读取权限并进入编辑器，无额外确认/成功提示。可选布局接口超时不会再遮挡编辑；真实错误会提示。符合租约与服务端基线的浏览器草稿会自动恢复，冲突草稿仍保留但不能覆盖服务器数据。
- **签入与版本历史**：始终保存当前最新模型。可选“保存到版本历史”，选择“新建历史版本”，或点击右侧列表中的普通历史版本后“覆盖已有历史版本”；右侧展示存档日志文件夹中的版本名称、时间、作者和备注。基线/锁定版不能覆盖，覆盖需不可撤销确认。
- **轻量接口**：`GET /api/projects/<id>/versions?detail=metadata` 返回存档元数据；旧 `/versions` 默认仍带关键数据。签入仍用原 `/lifecycle` + `overwrite_version_id`；不迁移 ProjectSpec 或已有版本日志。
- **部署与防冲突**：备份原服务端数据目录、配置和 `versions/` 日志，停止旧 Server/VZ，整体解压新包并按原单进程 `python run.py` 启动，浏览器强制刷新 JS/CSS。覆盖历史是不可撤销操作，建议先导出完整压缩包或另建历史版本，不要直接测试生产唯一备份。仍不建议擅自启用多 Uvicorn worker。
- **版本**：Server / Studio / Lab 2.16.1；Client 0.3.9、VZ 0.3.2.1 不变；旧版 Lab 帧继续兼容。
- **回归**：在 `Server` 目录运行 `node scripts/v2161_entry_notification_regression.cjs`、`node scripts/v2161_checkin_dialog_regression.cjs`、`python scripts/v2161_versions_http_regression.py`，再运行已有 `v2160_*` 等回归。完整 Windows MuJoCo/OpenGL、真实多账号与网络异常 E2E 仍需现场验证。

---

# 历史：MuJoCo Studio Server 2.16.0

## V2.16.0 操作及部署说明

**工作版本**：浏览器 IndexedDB 持久化当前签出模型草稿，编辑器按 Enter 将草稿写回服务器并提交坐标系后台仿真，动画 HTML 继续手动刷新。普通操作优先本地，不需要手动点击“同步草稿”；清理浏览器网站数据可能删除尚未同步的更改。

**驱动时序**：“驱动与时间曲线”→“时序选择”，可浏览该模型的 TSJSON 时序，确认后替换驱动，也可输入名称保存当前驱动到模型时序库；配置快照不包含新仿真结果。

**层级**：在层级属性顶部点击“添加子层级”，即可在当前层级下新建子节点，受编辑权限限制。

**签入**：默认“保存最新并签入”，不另建历史锚点。可勾选“同时创建历史版本锚点”并命名；或在编辑中单独点击“创建版本锚点”。不建档不意味着删除当前模型。自动/强制签入仍保留原安全快照规则。

**部署**：先备份服务端数据根和配置、停止旧 Server/VZ，再整体替换源码，按原单进程方式在 `Server` 内运行 `python run.py`。升级后硬刷新浏览器资源。不要直接改成多 Uvicorn worker，当前租约与 Job 仍包含进程内状态。

**兼容**：Server / Studio / Lab 2.16.0；Client 0.3.9、VZ 0.3.2.1、ProjectSpec、历史归档结构和 Viewer 协议不升级。

专项测试（在 `Server` 目录执行）：

```bash
python scripts/v2160_tsjson_anchor_http_regression.py
node scripts/v2160_frontend_interaction_regression.cjs
python scripts/v2155_delivery_archive_baseline_regression.py
python scripts/v21511_http_integration.py
node scripts/v21511_localdraft_browser_regression.cjs
```

原生 Windows MuJoCo / 多账号并发 / 浏览器端到端仍需在目标机器实测。

---

# 历史升级说明：MuJoCo Studio Server 2.15.11

## V2.15.11 多用户 Viewer / 浏览器本地草稿（升级须知）

- **部署：**先停止原 V2.15.10 Server 与 VZ 子进程，备份配置的数据目录与 `project.json` 后替换整套源代码；沿用 `python run.py` 单进程启动。**不要简单改成多个 `uvicorn --workers`**：内存中的 Job/租约协调器尚不是跨进程共享数据库。
- **兼容：**Server / Studio / Lab 为 V2.15.11；本机 Client 保持 V0.3.9，集成 VZ 保持 V0.3.2.1；既有 JSON、版本存档、基线、Client Bundle 协议不迁移。首次访问请硬刷新浏览器缓存。
- **操作：**已签出且本人拥有权限的模型默认在浏览器 IndexedDB 保留本地草稿。普通输入/拖拽/游标不自动 PUT；撤销历史在内存中最多 32 帧，IndexedDB 在预算允许时持久化基线与最近最多 7 帧；“⇧ 同步草稿”、仿真/动画/导出/签入会按现有授权协议同步；跨设备**不会**自动复制本地草稿，未经过服务器验证的旧租约草稿不会覆盖模型。
- **Viewer：**管理员本机 Viewer 的启动请求返回后台 Job ID，后台状态栏可见；工程师本机 Client 不强制额外 `/simulate`，Bundle 复用当前轨迹或隔离补算。新增 `MUJOCO_STUDIO_VIEWER_LAUNCH_SLOTS` 默认 2（最大 2）和 `MUJOCO_STUDIO_CHILD_THREADS` 默认 1（最大 4）；新增账号 Job 配额和 Viewer 预计算总时限。
- **专项测试：**进入 `Server` 后运行 `python scripts/v21511_concurrency_localdraft_regression.py`、`python scripts/v21511_http_integration.py`、`node scripts/v21511_localdraft_browser_regression.cjs`；无需原生 MuJoCo/GPU。Chromium 浏览器自动化、Windows 原生 Viewer、多用户资源/延迟压测仍需要在目标环境复验。
- **隐私/恢复：**IndexedDB 为当前浏览器配置文件的本地存储，不是加密云备份。共用电脑应使用独立浏览器配置文件；清除网站数据或无痕退出可能删除未同步草稿。服务端租约、正式版本及权限始终保持权威。



## V2.15.7 动画 HTML 测距/电机 UI 防重叠

- 导出器复用原 `legacy_animation_html_export._build_html_document`，将测距对与当前动画帧电机位置置于 `right-info-stack` 纵向布局。
- 两个面板统一采用半透明深色背景/边框/圆角；电机面板标题 11px、时刻 13px、数值 10px，并置于测距对下方，长内容独立滚动。
- 保留嵌入 Lab 时的悬停 `i` 信息按钮及旧动画播放器通信协议的兼容读取；不改变求解、采样、测距、WebGL 画面或播放逻辑。

## V2.15.6 Hub 关键数据气泡与轨迹/动画性能

- Hub `detail=summary` 直接返回每个模型的 `critical_data` 和 `critical_source`；基线关键数据作为冻结锚点，普通模型继续遵守最近存档（或没有存档时读取当前模型）的既有规则。读数依靠 RAM 与 `core/hub_critical_data.json` 派生快照，后续刷新无需先点开模型。
- Hub 可见时每 25 秒仅轮询轻量目录，10 分钟才按原有流程刷新类型树/回收站等元数据；首屏保留轻量列表/独立 preview 分支，后台失败保留旧读数。
- 动力学步进复用关节字典/锁力参数/下一物理步的驱动时序；运动学每采样帧同样复用关节字典；已验证轨迹动画输出不再浪费算力求未使用的时序 offset。
- 新增仿真分阶段 `timings_seconds`（场景初始化、求解/步进、闭链、测距、结果输出）；保留旧轨迹校验、原生测距、精确步长与动画输出。无本地 MuJoCo 时只做离线逻辑回归，现场性能以真实模型为准。
- 不增加新业务 API/Job/ProjectSpec 权威字段；Client 0.3.9、VZ 0.3.2.1 保持不变。详见 `architecture_master_prompt.md` 第一百零三部分与 `scripts/v2156_hub_performance_regression.py`。

## V2.15.5 时序文件归档、基线资源路径与签入版本锚点

- Studio/ Lab 时序库目录只保留 `.tsjson`；完整驱动和运动段配置以 TSJSON schema v2 为交换标准。旧版 VZ CSV 仍支持导入、VZ 推送时临时在内存转换，不再混放在本模型的时序库。
- 坐标系合并结果 CSV 为 `time,坐标系1,坐标系2,...` 宽表，缺失采样留空；单轴 CSV、旧主时序 CSV、映射表及 Lab 日程 CSV 全部归入 `交付数据/表格文件夹/`；旧时序库 CSV 会迁移到该目录。历史坐标系 CSV 文件夹整体搬迁并保留所有内容。
- 自动基线刷新复用普通仿真的 `_runtime_project()` 完整解析 `@model_assets/...` 公共数模资源路径，避免有效 STL 被误报不存在；每次成功刷新仿真并正式发布结果后将 `generated/generated_model.xml` 覆盖保存到交付数据。
- 签入按「分页关闭提醒 → 存档/不存档 → 版本新建或覆盖 + 自定义名称/日志」执行。覆盖只允许普通非锁定存档版本，不能覆盖基线。日志/版本名保存在原历史快照元信息，已有回档入口继续可用。
- 兼容约束：Client 0.3.9、VZ 0.3.2.1、项目 bundle v2 不改；Lab/Studio 版本 2.15.5。基线交付仍不可变更。本包以 V2.15.3 附件为物理修改基底，补齐此前讨论过的 V2.15.4 TSJSON、合并 CSV 与 XML 功能后再实施上述新变更。

测试：`python scripts/v2155_delivery_archive_baseline_regression.py`（离线业务/接口回归），已有 Lab/基线兼容回归见测试报告。


## V2.14.1 手动签入 / 甘特图 / 原生 Viewer / 页面布局 / 历史模型兼容

- Hub 与独立 Editor 的手动签入先确认关闭编辑分页，再询问是否创建存档；选择不存档仍可正常签入。服务端仅允许显式人工签入跳过 archive；自动空闲、退出/强制收敛、系统操作仍强制存档。
- 甘特图弹窗每次打开自动执行已有“恢复默认”缩放；结果甘特图顶部新增默认 11px（原 16px）字号数值输入，复用 `ui.results.gantt_font_size`。
- 原生 MuJoCo Viewer 正交视角在右键拖动时额外放大 native 平移增量至三倍，保持原有旋转/缩放输入与透视视角速度。
- Hub 在文件夹/项目切换、宽窄视口保持项目列表自定义宽度和右侧检视器；层级建模/仿真结果去除固定居中留白，测距恢复桌面三列，坐标系 Canvas 高度变化不再反向影响父容器宽度。
- 项目加载/仿真 worker 复用 Pydantic ProjectSpec 现有模型校验，在 `mode=before` 小范围修复旧数据空配置/空占位项；无效非空数据照常抛错。
- 回归：`scripts/v2141_regression.py`、`scripts/v2141_responsive_regression.py`；MuJoCo native/OpenGL 仍需目标主机人工验收。完整数据根和 V2.14.0 映射迁移规则不变。

## V2.14.0 映射 CSV 数据库迁移兼容

已部署的数据根目录继续由 `backend/app/storage_config.py` 统一选定，不把运行期映射文件保存在源码树。Linux 未配置时默认取 Server 向上两级下的 `V2_projec`；Windows 默认向上四级，且管理员 `storage_location.json` 或 `MUJOCO_STUDIO_DATA` 设置优先。

旧模型中的 `drives[].segments[].csv_path` 原本可能是来源机器绝对路径。首次打开项目时，Server 按**当前项目目录**重定位到 `assets/mappings/<文件名>.csv`，使用已有 CSV 解析器恢复映射点进 `segment.points`，并仅保存项目根相对路径。之后即使 CSV 文件被删除，已恢复的模型仍可运行；新上传仍直接内嵌数值点，不产生必须携带的 CSV 运行依赖。冻结 baseline 只做内存兼容恢复，不写入已封存的 project.json。

如迁移后的 `assets/mappings/` 中确实没有 CSV，且模型 JSON 也没有内嵌点，服务端继续拒绝仿真；应将原 CSV 放回对应项目的 `assets/mappings/` 或通过“导入 CSV”重新上传，**不能**将不存在的数据视为修复成功。

针对性回归：`python scripts/v2140_mapping_portability_regression.py`；协议保持 Client 0.3.9、VZ 0.3.2.1、Viewer 4、完整包 v2 不变。

## V2.13.6.1

V2.13.6.1 收口 V2.13.0～V2.13.4.1 连续扩展后暴露的“文件侧车生命周期”边界：Hub `时序库/` 继续保持文件系统单一真相，不强行塞回 ProjectSpec，但它现在被明确视为模型一等 sidecar。创建 baseline 会冻结该目录；完整项目包升级到 `mujoco_studio_project_bundle` format v2，并把它放在 `properties/time_series_library/` 中参与 manifest inventory / SHA-256 校验。V2.13.6.1 导入器同时支持 v1/v2，因此旧包仍可导入；v1 本身没有时序侧车时保持为空。

同时把 `project.metadata["vz_push"]` 正式定义为部署环境绑定，不属于模型可移植语义。模型 JSON/完整包导出会移除它；复制、fork、baseline、导入产生新的 project id 时也会清理。再次推送必须由新项目显式建立自己的 VZ 关系。VZ `time_series_workspace/` 仍是 VZ 本地实验副本，不进入 Hub 包。

本版不新增业务 Tool/API/Job/ProjectSpec 权威字段，也不改变 Client/VZ/Viewer 协议；但架构要求不再把“字段数量必须为 0”当作目标，而是以单一真相、生命周期完整和可移植性决定是否需要最小 schema。Server 2.13.6.1；Client 0.3.9；Viewer schema/controller 4；VZ 0.3.2.1。


## V2.13.4.1

V2.13.4.1 在 V2.13.4 测距对紧凑卡片基础上增加人工拖拽排序。每张测距对卡片左侧使用独立拖拽柄，拖拽 payload 使用稳定 `pair.id`，目标卡片上/下半区分别表示插入到目标前/后；drop 后直接重排现有 `ProjectSpec.distance_pairs`，并复用 `markDirty()`、`renderPairs()`、`commitCurrentStep()` / `project.replace` 权威保存链。刷新页面后顺序由原有数组序恢复。

本版不增加 `sort_index` 或第二套排序状态，不新增 API、业务 Tool、Job 或 ProjectSpec 权威字段；对象 A/B、多选 overlay、高级设置和测距/结果消费链全部保持 V2.13.4 行为。Server 2.13.4.1；Client 0.3.9；Viewer schema/controller 4；VZ 0.3.2.1。


## V2.13.4

V2.13.4 优化 Hub 高频交互但不改变项目权威 schema。所有 toast 最终固定到右上角。模型列表首屏只读 summary，选择模型后立即显示 summary preview，并只对当前模型加载完整 preview；versions/files 转为二级异步元数据，不再启动后把所有模型完整详情重新 hydrate 一遍。

关键数据顺序改为拖拽结束时一次提交最终顺序，并新增窄 `PATCH /api/projects/{id}/hub-properties`。该路由在服务端锁内读取最新 ProjectSpec、校验生命周期，最后仍复用 `project.replace`；前端不再为名称/顺序做完整 ProjectSpec GET/PUT。搜索框右侧只保留基线冻结时间早/晚切换，签入和签出模型永远排在 baseline 之前。

测距对 UI 按新草图重排为大名称、名称输入、对象 A/B、折叠高级设置；高级设置显示精确撒点间隙和寻优边界，新建默认分别为 2mm 和 8mm（animation spacing 继续以 2mm 存在于兼容 schema 中）。新增业务 Tool、ProjectSpec 权威字段和 Job 均为 0。Server 2.13.4；Client 0.3.9；Viewer schema/controller 4；VZ 0.3.2.1。


## V2.13.3

V2.13.3 收口 Hub↔VZ 共享推送库状态，不新增业务 Tool、ProjectSpec 权威字段或 Job。Hub→VZ 发布仍复用 `_vz_publish_project()`；VZ 工程师删除一个当前已发布的 Hub 模型时，VZ 先进入自身 trash，再通过运行时 bridge token 回传 Hub，把对应 `metadata.vz_push.enabled` 关闭。Hub 页面每 2 秒只轮询轻量推送状态，并在模型名称行右侧显示 `【已推送】`；如果即时回传不可用，状态接口会对 VZ catalog 做 reconcile，在 VZ 可达且确认模型缺失时修正 stale Hub=true。

Hub 主动关闭推送时只把 VZ `_hub_source.published` 设为 false，VZ 的工程师/用户 `/api/models` 都过滤未发布 Hub 模型，因此共享模型库同步消失，但不会物理删除 VZ 模型目录。这样再次推送可继续复用工程师已经调过的 0%/100%/速度/模式，以及 VZ 自有 `time_series_workspace/`。工程师显式“移除模型”才进入 VZ trash。

驱动设置初始化同时修复历史兼容：当前 `ProjectSpec.drives` 仍是首要权威，发布时会复用 `parse_time_series_csv()` 扫描 Hub `时序库/` 的主 `VZ_TIME_SERIES`，按 drive id 补齐只存在于原模型时序中的 drive；同 id 永远以 ProjectSpec 为准，不写回第二份驱动表。补齐驱动继续使用首次 0%=0、100%=30、速度=30 的 VZ 校准默认。Hub 时序源仍只读同步到 VZ `time_series_library/`，VZ 本地副本仍只在 `time_series_workspace/`，Hub ZIP 刷新不会覆盖本地副本。Server 2.13.3；Client 0.3.9；Viewer schema/controller 4；VZ 0.3.2.1。




## V2.13.2

V2.13.2 继续以 V2.13.1 的“Hub 主时序只读 / VZ 本地副本可编辑 / CSV 只属于时序库”为边界，不新增业务 Tool 或 ProjectSpec 持久字段。Hub→VZ 发布补齐驱动设置身份投射：驱动名称、对应运动副和 exchange drive id 一起同步；首次校准默认 0%=0、100%=30、速度=30，后续 Hub 刷新只更新身份/绑定并保留 VZ 工程师本地校准。Hub 运动段仍不进入工程师驱动设置页，真实 start/duration/travel/mapping 继续只由时序库投射。

VZ 用户页新增多模型联合仿真。右侧模型卡片拖进场景后仍写既有 control graph node；一次 `/api/simulate` 请求内用 runtime-only `scene_composition.py` 把每个源模型子树挂到 synthetic root，并按 `_a/_b/...` 对 Layer、运动副、闭链、驱动和 mesh/asset 做确定性 namespace，同时重写所有 parent/closure/drive/time-series 引用。联合时序按原时间轴并行，源模型 JSON/Hub 时序/VZ 本地副本均不被 composite 回写。用户看板每个模型只显示一个绿色全驱动时序总包络，1 秒主刻度，可切换 `时序1/时序2/...` 并进入用户时序编辑；双击只改 start/travel，速度固定读取工程师 rated speed。工程师与用户详细甘特图均显示 start–end 和累计位置。

二代结果查看删除结果页 MuJoCo View 与“一键导出动画 HTML”，原后台仿真改名“刷新结果”；坐标系高度与 ±游标迁到右侧导航并压缩 axis header，折叠 summary 统一风格。动画导航增加“重新生成”，复用现有 export job 生成/覆盖最新 HTML，但不自动下载。Server 2.13.2；Client 0.3.9；Viewer schema/controller 4；VZ 0.3.2.1。


## V2.13.1

V2.13.1 在 V2.13.0 时序库单一真值链上继续扩展，不新增业务 Tool 或 ProjectSpec 持久字段。VZ 工程师页新增“时序库”导航：Hub 同步主表只读，编辑前必须复制到 VZ `time_series_workspace/`；本地副本可改名、删除，并可在黄色/蓝色双分类甘特图中双击运动段修改起始时间、速度/时长和行程。甘特图显示层复用二代 WEB 甘特图的横/纵缩放、游标、时间排序/倒序、倒放行、驱动显隐/显示名/拖拽顺序、画布平移和放大/还原，仅保存为 VZ 浏览器显示偏好。Hub 再同步只替换 `time_series_library/`，不会覆盖工程师的 VZ 副本。

VZ 用户页下方增加时序分页，可切换当前模型的多个主时序；动画 transport/progress 缩小并把背景透明度降到 0.20，硬点/H 点坐标改为左下角透明白字。二代结果查看增加“自适应坐标系”（按全部驱动补齐同名轴）以及坐标系名称右侧“自适应”（从当前所选曲线识别名称）。

CSV 语义在本版收敛：合并 CSV 是 VZ/二代共用的特殊时序文件，只保存到模型 `时序库/`（并允许浏览器下载一份），不再写交付数据；baseline managed delivery 现为 NX AFU、甘特图 PNG、模型 JSON、动画 HTML 四类，历史 `axes_csv_folder` 仅作兼容识别。Server 2.13.1；Client 0.3.9；Viewer schema/controller 4；VZ 0.3.2.1。

## V2.13.0

V2.13.0 重构 Hub/VZ 用户界面的时序交互，同时严格复用既有结果曲线、驱动 schema、Hub 文件检视与 VZ 发布链：不新增业务 Tool 目录、不新增 ProjectSpec 持久字段。每个模型目录新增物理 `时序库/`，结果查看合并导出 CSV 时同步生成可恢复驱动的主时序表；伴生 mapping 点既嵌入主表，也另存 `<驱动>--<运动段>映射表格.csv`。

驱动设置顶部新增“导入CSV”，本地文件夹与服务端 `项目/模型/时序库` 两种来源统一进入服务端 parser，恢复 `DriveSpec/DriveSegmentSpec` 和 mapping points 后仍通过既有 Editor 保存链提交。Hub 推送 VZ 时用模型级 ZIP 原子同步时序库，后续 Hub 更新/删除会刷新 VZ；VZ 用户控制板按“驱动 → 多运动段色块”展示真实时序，变速段从时序库投射。

VZ 用户页改为中间场景 + 右侧只读模型库双栏；左侧可见 UI 和模型库管理按钮移除。工程师缩略图生成入口移到模型行；快速渲染固定使用更浅的 Classic 场景，用户动画移除中心项目组水印，顶部视图按钮整体缩小。Server 2.13.0；Client 0.3.9；Viewer schema/controller 4；VZ 0.3.2.1。


## V2.12.2.1

V2.12.2.1 只迭代伴生 mapping 数学，不改变 ProjectSpec、Hub、层级建模、数模库或 Client/VZ 协议。V2.12.2 的 2049 点阈值、运行时降采样/低通和 natural-cubic 分支被移除；归一化后的每一个 mapping 节点都保持原 target 值，并统一由全局五次 Minimum-Jerk 曲线连接。

Server motion 与 Native Viewer 复用 `backend/app/domain/mapping_curve.py`；Viewer 离线包携带同一 helper 并在 manifest 校验 SHA-256。浏览器 `mapping_math.js` 实现同一 2×2 block-tridiagonal 求解和五次系数。这样位置仍严格穿过映射节点，同时节点处的 acceleration/jerk 连续，并在严格穿点约束下最小化 integrated squared jerk。1/2 点映射保持常值/线性。

需要注意：若原始映射节点本身含高频测量噪声，在“源头绝对匀速 + 每个原始节点绝对穿过”的条件下，任何插值器都不可能把真实伴生加速度完全压平；本版不伪造平滑数据，也不通过输出限幅制造位置误差。后续若允许位置误差包络或源速度 time-scaling，可在此统一 mapping 核心上继续扩展。

新增持久字段 **0**，新增业务 Tool/API/Job **0**。Server 2.12.2.1；Client 0.3.9；Viewer schema/controller 4；VZ 0.3.2.1。

## V2.12.2

V2.12.2 继续复用现有 ProjectSpec、层级建模、`/meshes/adaptive`、公共 `model-asset-library` 与 Hub 属性链，不新增平行 Tool。高密伴生映射在运行时执行固定空间尺度重采样、轻量去噪和 C2 样条求值，原始 CSV/模型 JSON 点表保持不变；Dynamic 结果曲线优先直接使用 MuJoCo qvel/qacc。

层级“自适应”和“全部数模自适应”继续共用一个自适应入口，现升级为同族双向同步，可新增、删除库中已不存在的同族数模并校正大小写。Hub 刷新后不再自动沿用首个模型或旧属性：没有显式选择时模型属性与数模检视器保持空态；项目文件夹属性只显示名称输入/保存，异步甘特图返回也不得重新显示。公共数模文件夹新增重命名，复用现有资产库资源与 `ModelAssetCopyRequest`，并级联迁移所有当前模型 `mesh_root` 引用。

新增 ProjectSpec/L1/L2/L3/Session/Job 持久字段 **0**，新增 Tool/Job/artifact/tool directory **0**；仅在现有 `model-asset-library/folders` 资源上新增一个 PUT rename API。Client runtime/protocol 仍为 0.3.9，Viewer schema/controller 4、VZ runtime/protocol 0.3.2.1 不变。

## V2.12.1.5

本版修复质量定义主链路。此前 `MeshSpec.mass_kg / LayerSpec.mass_kg` 虽被解析成目标质量，但当 Studio 能读取 mesh 体积时，XML 生成优先写 `density=target_mass/Studio_volume`，MuJoCo 随后又按自己的 mesh shape/volume 重新推导 mass。复杂、非凸、薄壳、开口或体积算法不一致的 CAD 因此可能出现“自定义 kg 很小，实际动力学仍像巨大质量”的现象。

V2.12.1.5 规则：
- `resolved_mass_kg` 来自数模目标质量或 Layer 总质量分配时，MJCF 直接写 `<geom mass="...">`，不再同时写 density；
- 完全没有目标质量时继续走默认 `density=1000 kg/m³`；
- `density_kg_m3` 对 direct-mass 数模只作为 Studio 参考诊断，不再决定最终 kg；
- `model.mass_properties` 增加非持久派生字段 `mass_application = direct_mass | density`；
- Web 质量区显示“最终解析质量 + MJCF 直接质量/默认密度”，原“启用质量 / 逆求密度”改为“显示 / 编辑质量”。

不新增 ProjectSpec 权威字段、Tool、API 或 Job。Server 版本升级为 2.12.1.5；Client 0.3.9、Viewer schema/controller 4、VZ 0.3.2.1 不变。


## V2.12.1.4

本版针对“座椅机构本身动力学正常，但在坐垫上增加物体并通过旋转副连接后承载链塌落”的路径，修正两类问题：

- `JointSpec.point` 在 Studio UI 中是世界坐标点（mm），而 MJCF `joint pos` 必须是所属 body 的局部坐标。本版在 qpos0 参考构型按 Layer 父子静态平移累加世界原点，再执行 `world point - child body world origin` 后写入 MJCF。
- 一个 `LayerSpec` 严格对应一个 MuJoCo body；该 Layer 下所有 `meshes[]` 属于同一刚体，`joints[]` 作用于整个 Layer，而不是某一个 mesh。若附加物体要相对坐垫旋转，应把附加物体建为坐垫的 child Layer，并把 rotation joint 放在 child Layer。
- Dynamic 运动副属性增加“已驱动 / 被动自由度”提示；被动自由度仍遵循 Pure Dynamic 物理语义，不会被隐藏驱动或隐藏锁强行固定。
- 多 mesh Layer 新增运动副时增加刚体作用域确认；服务端 validation 同时给出非阻断 `layer_joint_applies_to_all_meshes` 诊断。
- V2.12.1.3 的 `dynamic_lock_force`、Hub Linux=2 / Windows=4 默认数据根层级保持不变。
- Server 版本升级为 2.12.1.4；Client runtime/protocol 0.3.9、Viewer Schema/Controller 4、VZ 0.3.2.1 不变。


## V2.12.1.3

本版严格复用现有 Hub storage、`DriveSpec`、`param.set`、XML 生成和 Pure Dynamic simulation 链路，没有新增平行业务 Tool/API/Job。

- Hub 未配置时按平台选择默认数据根搜索深度：Linux 向上 2 级、Windows 向上 4 级；已经持久化的管理员设置继续优先。
- `DriveSpec.dynamic_lock_force` 默认 2000。驱动目标静止时作为有界自锁/制动力接合，目标开始变化前自动释放回 `JointSpec.frictionloss`。
- Dynamic 驱动卡片公开“自锁力 / Kp / Kv”参数，其中 rotation 的自锁单位为 N·m，translation/crank 为 N，0 表示关闭附加自锁。
- 版本号从 2.12.1.2 严格更新为 2.12.1.3；Client 0.3.9、VZ 0.3.2.1 协议与运行时不变。


V2.12.1.2 is a focused VZ presentation iteration built on V2.12.1.1. It restores the original second-generation animation HTML center 3D text through the already-vendored watermark mesh pipeline, and compacts the engineer HTML render-settings modal to three inputs per desktop row. The main Server business Tool pool remains unchanged. VZ keeps runtime/protocol 0.3.2.1 and reuses the existing ModelStore, shared Fast/Perfect HTML exporter, watermark mesh renderer and render-settings DOM/CSS seams rather than introducing a parallel rendering/tool stack.

The VZ engineer page now uses one Fast HTML render sample only and reports that single render time; material selection is a screen-space silhouette outline that does not alter PBR material preview; front-view model PNGs are generated/cached from the engineer page in the background and reused by the user URL; the engineer Explorer removes local “new/copy model” actions, exposes Hub-like folders with inline rename, and changes model deletion wording to VZ “remove/unpush”. Front preview orientation follows the second-generation diagram thumbnail convention: X horizontal, Z vertical, Y depth.

V2.11.7 Hub folder properties, editable baseline names and frozen-time behavior remain inherited unchanged, as do V2.11.6 recursive folder counts and V2.11.5 five-artifact baseline/automotive rendering contracts. Client runtime/protocol stays 0.3.9, Viewer bundle schema/controller signature stay 4, and integrated VZ runtime/protocol stays 0.3.2.1. V2.12.1.2 contracts are in `architecture_master_prompt.md` section 80; the V2.12.1.1 startup hotfix remains in section 79 and V2.12.1 rendering contracts remain in section 78.

V2.10.6.1 is retained as a focused hierarchy-diagram closure-coordinate bug fix. It reuses the existing `kinematic_closures[].endpoint_a/endpoint_b.point_mm`, compact diagram closure properties, project commit chain, and XML generator; no new ProjectSpec field, API, Job, or parallel site model is introduced.

When a dashed closure/site edge is selected in diagram mode, its single lower-property coordinate is now labeled **“闭链坐标”**. Editing it writes the same mm vector to both endpoint A and endpoint B, using separate array copies. The existing XML generator then emits both closure sites from those synchronized endpoint values, fixing the prior result where only one site's `pos` changed and the peer site remained `0 0 0`. Root/hierarchy advanced closure properties continue to support independent A/B endpoint editing.

V2.10.5 is retained as the preceding hierarchy-diagram correctness/semantics patch. It reuses the existing DOM/SVG/WebGL editor, `layers[].parent_id`, `layers[].joints[]`, `kinematic_closures[]`, `drives[]`, `uiSet/ui.set`, and the shared thumbnail renderer; no parallel graph model or new runtime node-editor dependency is introduced.

Mesh-library drag-to-canvas now names the created layer from the mesh basename. Parent-link gestures that would make a hierarchy cycle are represented as the existing dashed closure/site edge instead of an illegal tree cycle. Diagram entry no longer writes auto-layout: saved manual `ui.model.diagram.nodes` remains authoritative, while old projects with missing geometry receive only a stable non-persisted grid. `KernelManager.begin_ephemeral_edit()` copies the authoritative `core/ui_state.json` into the isolated temporary edit root before constructing the ephemeral Kernel, so checked-in/baseline edits immediately inherit the last manual diagram layout.

Adding a joint to a selected parent/child line defaults its name to `parent——>child`. Closure passive joints are derived from the closure tree path with the diagram line as the driven/passive unit: if any joint on a path line has a drive binding, that whole line is excluded; manual correction is performed by clicking the closure-path line itself. Any tree edge with a bound drive receives a 36px Figure-1 marker that follows the same cubic Bezier line, exactly twice the existing 18px joint marker. Translation joints use the packaged Figure-2 asset. Closure colors intentionally exclude red and stay in saturated green/blue/purple/orange families; path tree edges remain solid and only the explicit closure/site line is dashed.

For selected diagram nodes, the entire lower property viewport is a mesh-drop target. Multi-mesh chips are approximately doubled in text/padding size. These are UI/projection changes only: no ProjectSpec/L1/L2/L3/Session/Job authoritative field and no new business Tool/API/Job/artifact/tool-directory is added.

V2.10.4 is retained as the Delete/left-button-lasso/density patch: node/tree-edge/closure-edge Delete semantics, left-button blank-pane lasso, expanded multi-mesh property section, 13px diagram titles, 18px edge headers and 3600ms undo feedback remain unchanged.

V2.10.2 is retained as the Hub critical-data hydration and lightweight diagram interaction patch: baseline-derived projects without a local archive show current critical data immediately, and the diagram uses compact properties, four handles, cubic Bezier bending, middle-button pan and Ctrl+wheel zoom.

V2.10.1 is retained as the hierarchy-diagram correctness/layout patch. Inactive layers lock diagram-side mutation paths and auto-arrange packs the hierarchy using each node’s actual saved width/height, depth-column maximum widths and recursive subtree heights.

V2.10.0 introduced the diagram-canvas projection to hierarchy modeling. The tree and diagram edit the same `layers[].parent_id`, child-layer joints and `kinematic_closures`; diagram-only geometry and body-mesh preview choices stay in existing `ui.model.*`.

V2.9.8 integrates VZ Studio V0.3.2.1 into MuJoCoHub: the Hub adds “工程师界面” and per-model “推送模型”, while the integrated VZ engineer UI removes hierarchy modeling and redundant modeling/import/export controls. Drive settings occupy the former hierarchy-modeling workspace; renamed VZ models retain the original Hub model name, and high-quality render defaults to 120000 faces per mesh.

V2.9.7.1 is a focused lifecycle/Hub patch on the V2.9.7 architecture. The Hub recycle bin now supports checkbox multi-selection, select-all for the current filtered list, and irreversible deletion of selected recycle entries. Every authoritative check-in now creates an archive version through the existing lifecycle/Kernel archive path; manual check-in no longer asks whether archiving is needed, but still accepts an optional archive log. The top redo control is displayed as “前进” while the internal redo command and shortcuts remain unchanged.

V2.9.7 retained the Hub and hierarchy-modeling workflow without adding parallel project state. The Hub starts with all nested folders collapsed, provides a one-click collapse/expand-all control, and searches projects across every category level. JSON import and complete ZIP import both target the currently selected Hub folder.

The complete project bundle now writes `mujoco_studio_project_bundle` v2 and exports the canonical model JSON together with mesh assets, delivery data, the Hub time-series sidecar and applicable archive logs. The V2.13.6.1 importer accepts both v1 and v2. Checked-in public assets are first copied to an isolated verified snapshot so export never writes into the source asset library; import creates a conflict-free public asset folder in the selected category (including root `None`). Baselines keep their immutable private mesh snapshot, delivery data and frozen Hub time-series library while the imported working copy uses the newly injected public asset folder. Environment-local `vz_push` bindings are not portable and are stripped from exported/new-identity projects.

Hierarchy modeling now resets mesh and drive lists to two-column layout whenever the Editor is re-entered, only shows joint range inputs after range limiting is enabled, projects reversed vectors with visible negative signs while retaining the canonical stored axis, and replaces the Model A/B placeholder with “全部数模自适应” using the existing adaptive-mesh endpoint.

Formal integrated deliveries continue to include both `Client/` and `Server/`. Client V0.3.9 has been audited for V2.9.7.1; Viewer bundle schema/controller signature are unchanged.

The V2.9.6.6 path/performance fixes retained in V2.9.7.1 cover Windows Viewer/generated-XML loading in Unicode project directories and removes the synchronous full-catalog refresh from Hub model reclassification/name refresh. Local Viewer subprocesses now use workspace-relative XML/data arguments when possible, while in-process MuJoCo loads reuse the existing Unicode/VFS loader. Same-filesystem delivery moves use an atomic directory rename with the existing verified-copy path retained as the fallback.

V2.9.6.5 fixes custom-variable division expressions such as `40/tran*tz` and makes distance-pair names a forbidden legacy alias in the custom-variable pool. V21.5 imports now remove measurement-pair variables before they can enter Studio runtime expressions.

V2.9.6.4 adds V21.5-compatible external motion CSV import to Studio 2.x and extends the V21.5 ↔ Studio complete-model JSON contract so `external_csv` motion remains self-contained and portable. Imported CSV data is stored as an embedded time/position point table; source file paths are provenance only and are not required at runtime or after moving the model to another machine.

V2.9.6.2 remains the rapid-edit consistency hotfix built on V2.9.6.1. V2.9.6.1 is the Viewer Gantt synchronization hotfix built on V2.9.6. V2.9.6 restructures model version history around two user-facing kinds only: **存档版本** and **基线版本**. V2.9.6 originally allowed manual check-in without an archive; V2.9.7.1 supersedes that choice so every check-in creates one archive version. Automatic check-in paths keep their safety archive, and check-out itself still does not create a lifecycle history version.

Creating a baseline still freezes the independent baseline model exactly as before, and now also appends one red-labeled baseline entry to the source model's version history. The source model is not rewritten or rolled back and no extra ordinary archive is created. The unified history remains capped by the existing `MAX_ARCHIVE_VERSIONS` / `MUJOCO_STUDIO_MAX_VERSIONS` value, default 20.

Every source-model history row now exposes “删除存档” immediately before “切出为独立模型”. Deleting a baseline history row removes only that source-history snapshot/metadata; it does **not** delete the actual frozen baseline model.

Architecture boundary:

## Retained V2.9.6.6 Windows Viewer path / Hub drag responsiveness

- Generated XML is no longer loaded by backend simulation/optimization/export code through ad-hoc absolute `MjModel.from_xml_path(...)` calls. All such loads reuse the existing Viewer Unicode/VFS compatibility loader, preventing Windows `ParseXML: Error opening file` failures caused by Chinese/UTF-8 project directories.
- The local Viewer subprocess runs with its output workspace as `cwd` and receives workspace-relative scene/drives/Gantt/trajectory arguments whenever the paths share that workspace. Cross-volume paths retain a safe absolute fallback.
- Reclassification keeps the existing `project.reclassify`/ProjectStore flow. Delivery directories now use same-filesystem `Path.replace()` first and fall back to the prior verified copy+hash path only when rename is unavailable.
- Hub drag/drop applies project category, managed name and model-type counts immediately, rolls back on API failure, and merges the returned authoritative ProjectSpec on success instead of synchronously rescanning the full project catalog. Hub name saves likewise merge the authoritative response directly.
- New ProjectSpec/L1/L2/L3/Job fields: 0. New business Tool/API/Job/artifact/tool-directory: 0.

## V2.9.6.5 expression / custom-variable hygiene

- Plain custom variables are now recognized after `/` when the slash is the arithmetic division operator, so expressions such as `40/tran*tz` resolve correctly. Slash-qualified drive variables such as `drive/duration1` retain their existing compatibility semantics.
- Distance-pair names are measurement identifiers, not user parameters. If a custom-variable name matches a distance-pair name after trimming whitespace, it is removed from `project.variables`.
- The invariant is enforced centrally by `ProjectSpec` and explicitly at both V21.5 complete-model and modeling-exchange import boundaries, so future project replacement/import paths inherit the same cleanup rule.
- `scripts/self_check.py` permanently covers both the division-expression regression and the distance-pair-variable cleanup invariant.

## V2.9.6.4 external CSV drive / model JSON interoperability

- Editor `external_csv` segments can upload a V21.5-style two-column CSV through the existing project-edit lifecycle.
- CSV decoding/delimiter handling follows V21.5: UTF-8/GBK/GB18030 and comma/semicolon/Tab/whitespace tables are supported.
- Position input is embedded directly; velocity input is trapezoid-integrated to position; acceleration input is integrated to velocity and then position, matching V21.5 semantics.
- `segment.points` is authoritative for runtime and export. Legacy `csv_path` is only a fallback for older projects and is cleared for new imports.
- Complete model JSON now supports `external_csv` in both V21.5 → Studio and Studio → V21.5 conversion, including embedded values, header/source metric, and portable source basename provenance.
- External motion playback uses the CSV sample times with linear interpolation and does not apply S-curve easing.


## V2.9.6.2 rapid-edit consistency

- Late background `/state` mirrors are revision-fenced and cannot overwrite edits made while the request is in flight.
- The 400 ms interaction debounce remains a coalescing window; it does not choose an older state over a newer one.
- Direct add buttons for layers, drives, distance pairs, variables, optimization ranges, and result axes now all enter the automatic commit path.
- Client runtime/protocol remains V0.3.9 / controller signature 4.

## V2.9.6.1 Viewer Gantt synchronization

- Linux/remote Client Viewer bundles now carry the exact `latest_gantt.png` + `latest_gantt.json` generated by the Web Gantt popup before launch.
- Client runtime V0.3.9 passes the bundled cache directory to the server-supplied Viewer controller and verifies both cache files by SHA-256.
- Native Viewer polls the authoritative cache source dynamically, switches away from compatibility fallback when the real cache appears, and reloads on PNG or JSON changes.
- Animation HTML continues to use the same project popup cache as before; Viewer and HTML therefore share one Gantt visual truth source.

- Server: 2.13.3
- Client runtime: 0.3.9
- Minimum compatible Client protocol for Viewer launch: 0.3.9
- Archive retention: default 20 unified source-history entries (archive + baseline); every check-in archives automatically, check-out creates no version
- Hub inspector: desktop inspector max width ~368px for a 245px model-property column; compact delivery/assets/archive projections
- Delivery generation: managed delivery assets are unique by **type** (model JSON, Gantt preview, NX AFU, animation HTML, coordinate-system CSV folder); a newer same-type output replaces/reconciles the older path even when its filename differs
- Coordinate-system batch CSV: separate files or one combined CSV; persistent non-baseline Editor batch export also refreshes the managed CSV-folder delivery
- Recycle bin: admin/engineer only, 7-day retention, conflict-safe restore, checkbox multi-select and irreversible selected deletion; normal user deletion is trash-move while internal rollback keeps hard-delete semantics
- Copy version: explicit `model_name` is authoritative; duplicate names fail with 409; copied models reuse the source public model-asset folder, while baseline `/fork` creates a newly named one
- Adaptive mesh: only same-family `.001`-`.009` ancillary files are forced to opacity 0; `.010+` keep their opacity
- Adaptive drives: exact joint name is used as drive name and the drive binds to that joint
- Hub root projection: internal `None` sentinel is hidden from the model-type tree; legacy `未分类` metadata/directory aliases are normalized
- Model-type drag: hierarchy + sibling ordering via existing move API; drag handle is leftmost, fold button immediately to its right; confirmation before write; reload after success
- Reclassify naming: target leaf prefix, no date-based rename
- Baseline naming: `<source-name>_00i`; timestamp remains property data
- User export policy: Windows and Linux both use direct browser download without file/directory path pickers
- Checked-in temporary Editor: darker gray non-blocking visual mask
- Editor check-in sync: opener/localStorage notification + Hub cache invalidation + authoritative refetch
- Mesh / drive layout: reset to two-column on each Editor entry; single-column toggles are session-only
- Hub attribute cache: page-memory, 10-minute TTL, force refresh after writes
- Drive variable canonical form: `drive/starttime1` slash/lowercase

- Model asset portability: exact case first; one unique case-insensitive on-disk match is accepted; ambiguous duplicates are never guessed.

## V2.10.6.1 patch note

This patch only fixes hierarchy-diagram icon resources and references: edge drives now use a dedicated drive badge asset instead of reusing the rotation-joint badge, and translation joints use the user-specified replacement icon. No ProjectSpec, API, or Job behavior changes are introduced.

### V2.16.11.4 Hub / 时序 / 布局

Hub 签出后当前模型优先置顶。驱动时序选择对话框新增来源模型下拉菜单，可读取有权限的其他模型 TSJSON 并显式映射不同运动副；来源不会更改。结果坐标系在“当前布局”下点击“自定义布局名称”可直接保存命名布局，新增“导入布局”可从同一 Hub 项目根目录其他模型复制布局到当前模型。无法唯一匹配的跨模型曲线源留空而不错误复用旧 ID。完整操作需要现有编辑权限与 Enter 保存流程。
