# V2.16.11.6 — 动画播放窗口正交视角 cam_fovy 下限优化（2026-11-13）

- 原生 MuJoCo 动画控制窗口的“开启正交视角” `cam_fovy` 滑块最小值由 `0.2` 降至 **`0.05`**，最大值保持 `2.0`，初始化默认值仍为 `0.8`。
- 滑块步长调整为 `0.05`，确保实际可选择并显示 `0.05`；`set_orthographic()` 将写入 MuJoCo `model.vis.global_.fovy` 与固定相机 `model.cam_fovy` 的钳制下限同步改为 `0.05`，避免 UI 与实际渲染参数不一致。
- 保持透视模式原始 `fovy`、正交开关、预设相机、手动电机、轨迹采样、测距计算及场景/模型 JSON 不变；无新增接口、依赖或字段。
- Server / Studio / Lab 升级至 **2.16.11.6**，Lab 继续允许 2.16.11.5 及全部历史兼容版本。Client 0.3.9 与 VZ 0.3.2.1 保持不变，统一 IP/端口配置与 SSH 进程清理不变。
- 通过静态、独立逻辑与语法回归；真实 Windows 原生 MuJoCo Viewer GUI 的鼠标操作与渲染结果仍需现场验证。

# V2.16.11.5 — Hub 基线气泡冻结身份与冷缓存恢复（2026-11-13）

- **创建基线即预生成气泡缓存**：基线及源历史存档成功落盘后，原 `_hub_catalog_critical` 复用冻结 ProjectSpec 的 `archive_fields` 生成 L3 `core/hub_critical_data.json`；失败仅记录日志，不回写冻结模型/物理数据。
- **兼容历史基线**：旧基线无缓存时，轻量 Hub summary 仍立即返回 `pending`，后台通过单 daemon 线程/有界队列按冻结 ID + 时间身份重建，任务去重且失败有退避；没有另建用户 JobManager、工具或 HTTP API。
- **消除空白/标识丢失**：Hub 全量加载及定时 summary 在同一冻结 token 下保留已验证的基线气泡和 `◆` 来源标识；历史冷缓存有限次数加快轻量列表补查，预览补齐时同时修复 `critical_source=baseline`；不跨不同冻结时间或 archive token 沿用旧值。目录辅助 IO 失败不再抹除已投射气泡。
- **兼容与数据边界**：仅返回只读派生字段 `critical_token` 辅助前端验证；ProjectSpec、冻结资产、数值精度、测距、结果布局、统一 IP/端口与 SSH 停止流程不变。Server/Studio/Lab 2.16.11.5；Lab 保留 2.16.11.4 及旧白名单；Client 0.3.9、VZ 0.3.2.1 不变。
- **测试说明**：隔离的服务端 AST/线程并发验证、Node.js 函数交互与历史回归不等同于完整 Windows/MuJoCo/WebGL2 + 生产磁盘的现场验收，详见单独开发证据包。

# V2.16.11.4 — 结果坐标系单行工具栏与折叠后处理（2026-11-12）

- **修复顶部两行 UI**：顶部布局和后处理采用不可换行的双模块单行布局，清理 V2.16.9.1 时代遗留的 flex-wrap 样式冲突；继续保留 V2.16.10.2 的浅色模块区分。
- **后处理简化**：外侧直接显示唯一的导出动作“导出NX脚本”；“更多”内折叠原有导出 CSV、合并 TSV 表格、坐标系高度滑块和增删游标，保持原按钮 ID、事件、下载和权限语义不变。
- **布局操作可达**：保留单双列、当前/命名/默认测距布局选择、命名保存、新增坐标系；自适应、增删命名布局、跨模型导入放入“布局管理”。结果面板极窄时将原有同一组控件移动进菜单，避免与 NX 导出按钮重叠；不复制事件处理器或数据源。
- **向后兼容**：Server / Studio / Lab 升级为 2.16.11.4；Lab 在历史白名单上追加 2.16.11.4。Client 0.3.9、VZ 0.3.2.1、统一 IP/端口配置、进程清理、ProjectSpec、模型数据及测距算法均不改动。
- **测试边界**：Chromium 隔离片段验证多宽度与菜单交互，Python/Node 语法及旧版静态/合成回归不等于生产环境完整 Studio+WebGL2 原生验收；真实部署仍需验证。

# V2.16.11.3 — Hub 签出置顶、跨模型时序及坐标系布局导入（2026-11-12）

- **Hub 签出模型置顶**：优先显示当前选中已签出模型，其次其他签出模型；签出成功将列表滚动到顶部，普通选中不打乱已签入模型原有修改时间排序。
- **驱动设置/时序库跨模型选择**：时序弹窗可通过模型下拉框选择其他模型的 TSJSON；继续使用原 `GET /files` 清单与目标模型 `POST /time-series/parse`，可选 `source_project_id` 原地扩展，不新增时序数据库或持久字段。服务端对来源模型执行原读取 ACL，并核对 TSJSON 路径/大小；跨模型驱动及映射运动副按名称唯一匹配或提示用户选择，避免残留错误 Joint ID。
- **坐标系当前布局一键命名**：可直接点击顶部“自定义布局名称”把未命名坐标系完整保留并新建命名布局；原布局重命名/测距默认布局保护与 50 条上限仍有效。
- **跨模型导入布局**：新增“导入布局”弹窗，可从同一 Hub 项目目录中的其他模型选择命名布局或未命名当前布局；不会更改源模型。导入到目标模型形成新的自定义布局，驱动/关节/测距对数据源按唯一身份/名称匹配，不匹配留空并提示，坐标系和曲线得到新 ID；不修改项目 JSON schema。
- **兼容**：Server/Studio/Lab **2.16.11.3**；Lab 接收 2.16.11.2 及历史版本。Client **0.3.9**、集成 VZ **0.3.2.1**、`Server/ports.json` 和启动/停止语义保持不变。完整源码包保留全部上一版文件，测试证据独立归档。
- **验收限制**：代码/浏览器隔离测试与合成回归不代替原生 Windows MuJoCo、完整真实登录权限及生产跨模型数据测试；未执行项明确记录在开发证据包。

# V2.16.11.2 — SSH / Ctrl+C 统一回收 Hub 与集成 VZ（2026-11-12）

- `Server/run.py` 新增 `start|stop|status` 命令（无参数仍启动），SSH 当前终端 Ctrl+C、SIGTERM、SIGHUP 均走 `finally` 回收集成 VZ；POSIX VZ 在独立进程组中启动，SIGTERM 有界等待后升级到 SIGKILL。浏览器启动 Timer 为 daemon，不拖延停机。
- 受管服务进程 PID、Linux `/proc` 启动标识、运行目录与子进程组信息原子写入 `DATA_ROOT/.runtime/studio_launcher.json`；启动器持有文件锁禁止重复运行。`python run.py stop` 可在第二个 SSH 终端安全停止同一部署，正常退出清理记录，SIGKILL 之后下次 `stop`/`start` 按身份回收受管遗留 VZ。
- 不再默默复用任何监听 8877 的其他 VZ/未知进程：端口占用时明确失败，避免新 Hub 看似启动成功、实际复用旧进程的假象。可显式运行 `python run.py stop --legacy-vz`，在 Linux 同时核对监听 socket inode 和当前源码中的集成 VZ run.py 路径后，定向清理升级前无记录的旧版 VZ；对其他端口监听者拒绝终止。独立部署的 `Client`（默认 8766）必须在 Client 所在电脑停止；Docker 由 `docker compose down` / `docker_ports.py down` 管理。
- 继续复用 `Server/ports.json` 四项 `server_ip/hub/client/vz`，默认 10.13.90.107 / 8765 / 8766 / 8877；无新 API、业务 Tool、依赖、ProjectSpec/资产/Viewer 数据协议。Server / Studio / Lab 更新至 2.16.11.2 并保留 Lab 2.16.11.1 兼容；Client 0.3.9、VZ 0.3.2.1 不变。
- Linux 环回测试实启原集成 VZ，Hub 使用隔离替身（无本地原生 MuJoCo/auth）；验证 Ctrl+C/SIGTERM/SIGHUP、stop、重复启动、SIGKILL 后孤儿恢复和未知监听不受损。完整 Windows / 原生 MuJoCo / Docker / SSH 真机仍需部署端验收。

## V2.16.11.1 — Client Server-IP unified configuration maintenance (version unchanged)

- Client now reads `server_ip` from the existing `Server/ports.json` or the standalone `Client/ports.json`, defaulting to `10.13.90.107`; edit this same file to change destination IP and all three ports. No `Client/main.py` edits are necessary.
- Explicit `MUJOCO_STUDIO_SERVER_IP` retains higher priority for compatibility. Invalid host, port-in-IP, URL, missing/incorrect type are rejected rather than silently weakening Client origin checks.
- Client bridge still binds strictly to `127.0.0.1`; only Hub destination / origin is updated. No Client 0.3.9, VZ 0.3.2.1 or Server/Studio/Lab 2.16.11.1 protocol/version change.

# V2.16.11.1 — 部署端口单文件配置维护补丁（版本号不变）

- 对 `Server/ports.json` 设置三个 HTTP 端口：Hub `hub`、用户电脑本地 Client `client`、集成 VZ `vz`。不用再分别改 run.py、app.js、Client/main.py 中的数字。
- `run.py`、现有 `/api/health.network_ports`、Viewer 回调、VZ 启动、浏览器跳转与本地 Client 桥复用同一配置；独立电脑的 Client 需复制配置文件到 Client/ports.json。保留旧环境变量优先级，避免静默改变现有部署。
- `docker_ports.py` 包装 Compose，把 JSON 中的 Hub 端口同步给容器端口和宿主端口；不公开未授权 VZ 和 Client 本地桥。Lab UDP 端口不受影响。
- 不修改 Server / Studio / Lab 2.16.11.1、Client 0.3.9、VZ 0.3.2.1 标识及模型/Viewer/测距协议；部署端口变更需要重启，并更新防火墙、代理和分布式 Client 本机的配置副本。

# V2.16.11.1 — 基线数模绑定选择、动画任务顶层进度与交付数据刷新（2026-11-10）

- **基线使用资产选择**：Hub “使用版本”前弹出数模所有权对话框，默认只绑定现有模型类型资产库中的指定文件夹，不复制冻结数模；如需独立资产，用户可主动选择复制冻结数模。API 可显式传 `mesh_asset_strategy=bind_existing` 与 `mesh_asset_reference`；服务端验证模型类型、路径和每个引用的 STL/OBJ 文件，缺失时拒绝发布。旧 API 省略新字段仍按旧版复制行为运行。Job 键加入资产使用方式与身份，保留 heavy lane 和复制回滚、并发上限。
- **刷新动画进度**：将 `#activeJob` 从 Sticky 仿真面板挂到 `document.body`，用页面级固定定位和显式层级高于结果坐标系工具栏；阻断式全屏 Loading 仍可正常覆盖后台提示。
- **交付数据一键刷新**：Hub 交付数据检视器右上角新增“↻ 刷新”；使用既有 JobManager heavy 池后台更新 NX AFU 脚本、甘特图 PNG、模型 JSON、最新仿真 XML，不再同步卡住 Hub。动画 HTML、模型表格资产、交付 CSV/TSV、时序库不重生成/不覆盖；冻结基线、访客、临时预览受原权限保护。同快照同租约重复刷新复用已有 Job。
- **版本及边界**：Server/Studio/Lab 2.16.11.1，Lab 历史兼容值包括 2.16.11；Client 0.3.9、VZ 0.3.2.1、模型 JSON/V21.5 和测距算法均不变。静态/合成/Chromium 独立测试不替代 Windows 原生 MuJoCo 与真实服务器多用户压力验收。开发日志与哈希不进入正式源码 ZIP。

# V2.16.11 — 基线加载后台处理、Hub 项目列表阻塞与掉线恢复（2026-11-10）

- **故障治理**：Hub “使用基线版本”通过现有 JobManager heavy lane 执行高成本数模/表格/交付/历史结果复制，HTTP 即时返回 `202 + job_id` 并轮询显示状态；保留无 `background` 参数的原同步 fork API 与权限。对相同模型、用户、租约与请求资产名并发幂等提交，继续执行原每用户 Job 限额。
- **复制完整性**：新工作模型以 L3 pending 标记隐藏，直到全部所有权校验、文件复制、交付数据校验和合法会话租约检查通过才发布；取消/异常回滚新模型与新公共数模文件夹。防止 pending 临时标记误当作交付文件迁移。未引入新的 ProjectSpec 字段、数据迁移或 DB。
- **目录/绘制性能**：项目目录扫描只向模型类型目录遍历，找到权威 `project.json` 即裁剪大资产子树。Hub summary 冷缓存关键徽章按需加载，不同步做全部模型的存档解析和求解；分离可选 VZ 对账。网页收到项目列表即显示卡片，不再等模型类型/回收站加载，加载失败时明确提示并采用有限频的自动重试。
- **验收边界**：定向合成测试覆盖连续/并行重复提交、后台执行期间项目列表、复制/取消/回滚、表格及交付文件保留、前端首屏和重试。没有原生 Windows MuJoCo、真实大模型/生产网络或完整浏览器登录验收，不能认定已实测解决用户所述 30 秒等待。
- **版本**：Server / Studio / Lab 2.16.11；Lab 追加接受 2.16.11 消息且继续接受历史版本；Client 0.3.9、VZ 0.3.2.1 保持不变。完整源码 ZIP 与开发证据 ZIP 分离。

---

# V2.16.10.2 — 坐标系工具栏视觉分层与驱动双列可调宽度（2026-11-10）

- **坐标系顶部**：保留 V2.16.9.1 的布局/后处理模块与单行坐标系名称/曲线栏；顶层统一增加浅色渐变、蓝色侧边强调线、细描边和轻投影，后处理模块用独立灰紫色块区分，下方坐标系改为清晰白底卡片。
- **驱动双列**：继续在原 `driveList` 行优先显示驱动，不复制卡片；新增居中的竖向拖拽条，实时调整左右列比例，支持鼠标/触控、键盘、双击复位。保留编辑内容和卡片顺序，调整宽度不调用模型保存/仿真。
- **响应式**：分栏上下限受编辑区真实宽度约束；窄窗口或快速寻优收窄编辑区时自动单列并隐藏分隔条，返回宽屏后恢复会话偏好。
- **兼容**：Server/Studio/Lab 升级 2.16.10.2、Lab 历史 2.16.10.1 消息继续接受；Client 0.3.9、VZ 0.3.2.1 不变。未新增工具、HTTP API、持久 ProjectSpec 字段或运行依赖。独立 Chromium 多宽度检查及回归见开发证据包；Windows 原生 MuJoCo/WebGL2 全栈未运行。

---

# V2.16.10.1 — 甘特图色块编辑弹窗文案与 Enter 保存（2026-11-10）

- **下拉文案**：「行程 / 表达式」调整为「行程」、「速度 / 表达式」调整为「速度」，同一速度菜单的「时长 / 表达式」调整为「时长」；保留「结束位置」，保留原有表达式求值和驱动结构。
- **Enter 保存**：色块双击弹窗的文本输入框按 Enter 与点击「保存」走同一原生表单提交事件和 `saveGanttSegmentDialog` 处理函数；仅保存成功才关闭。无效结束位置继续报错并留在弹窗。
- **取消保护**：顶部 ×、下方「取消」不再抢占表单默认提交按钮；Esc 继续关闭，均不修改运动段；关闭时及时清理编辑目标，避免旧目标残留。下拉选择与颜色控件的 Enter 保留原生交互；页面级 Enter 仿真不受影响。
- **版本与兼容**：Server/Studio/Lab 统一 V2.16.10.1，Lab 接受旧 V2.16.10 帧；Client 0.3.9、VZ 0.3.2.1 不变。不新增 Tool、HTTP API、数据库、模型 JSON 字段或第三方依赖。独立 Chromium 弹窗测试及源代码核验见开发证据包；Windows/MuJoCo 真机集成仍待现场验证。

---

# V2.16.10 — Hub 表格资产、映射电机 CSV 导出与唯一覆盖（2026-11-10）

- **模型表格资产**：Hub 模型属性新增“表格资产”，保存在各模型私有 `assets/tables/`；展示类型、驱动/运动段、大小及更新时间，可下载；与公用数模资产、时序 TSJSON 和交付数据的表格文件夹各自独立。
- **自动备份与唯一覆盖**：映射 CSV、外部运动 CSV 导入先校验、原子覆盖与对象 ID/类型绑定的表格资产，再更新 `segment.points`；若模型更新失败，恢复旧资产。同一模型/驱动/段/类型重复操作仅保留单个资产，不以导入文件名生成新版本。
- **导出完整实现**：映射电机新增“导出 CSV”，外部运动 CSV 同步支持导出；以模型 JSON 的当前内嵌数值点产生无损 CSV，先更新模型表格资产再下载。原 CSV 丢失仍可导出并重新导入；外部运动导出为时间/位置点，不伪装原速度/加速度文件。只读模型只能无副作用导出。
- **结果表格归档**：原结果坐标系单张 CSV、批量 CSV、合并 CSV、Excel 可读 TSV 导出也先按坐标系稳定 ID 备份进表格资产，之后继续写交付数据 / 浏览器下载；保留原测距精度门禁。
- **权限与版本**：不修改 ProjectSpec/V21.5、Client 0.3.9、VZ 0.3.2.1 或原仿真计算；Server/Studio/Lab 升级 **2.16.10**，Lab 继续兼容 2.16.9.1 历史消息。参考架构第 121 节与独立开发测试证据包。

---

# V2.16.9.1 — 结果坐标系单行编辑、模块化工具栏与测距布局自动同步（2026-11-09）

- **坐标系 UI**：每张坐标系的名称输入框与曲线对象选择框位于同一行；其它曲线配置（添加、颜色、运算、删曲线）默认折叠，消除易与删曲线混淆的重复删除按钮。多曲线窄宽度时仅行内横向滚动。
- **顶部工具栏**：移除“仿真结果坐标系 / 最新结果”等可见标题，保留隐藏状态供无障碍使用；浅色背景模块区分“布局”与“后处理”，用滑动开关切换单/双列。高度滑块由 92px 增至 190px；CSV 与 Excel 可打开的 TSV 表格独立导出。NX AFU 和游标在“更多”中保持可用。
- **默认测距布局**：`__distance__` 永久出现在下拉菜单，不能删除；每次进入根据最新 `distance_pairs[].id/name` 自动补齐/更名/排序/清理对应坐标系，保留有效匹配的原色和轴 ID。旧版已达 50 布局上限时仍可使用虚拟默认选项，避免破坏 ProjectSpec 限制。
- **布局自动存档**：不再设置“保存布局”按钮，命名布局的现有 `axes` 改动自动同步到对应 `presets[].axes` 快照，按 Enter 使用既有模型提交路径；新建仅命名一次，支持增删/重命名。已有未命名坐标系切换前自动归档，空间不足则安全阻止切换。
- **兼容/版本**：Server / Studio / Lab 升级为 **2.16.9.1**，Lab 保留 `2.16.9` 历史消息白名单；Client **0.3.9** / VZ **0.3.2.1** 不变，无新后端路由、业务 Tool、数据库字段或运行依赖。参见架构第 120 节与独立开发证据包。实际 Windows MuJoCo/Chrome WebGL2 交互需现场验证。

---

# V2.16.9 — 所选坐标系精确测距、共享几何和安全 Enter 复用（2026-11-09）

- **按需测距**：任意坐标系只计算所选 `pair:<id>`，支持原 GET 重复 `pair_id` 与 POST `pair_ids`，单对和无参旧接口保持兼容。
- **任务与计算**：同一冻结快照、用户与租约使用一个 heavy-lane 测距 Job；运行中追加测距对合并为顺序 wave。跨 wave 复用冻结驱动、MjModel、轨迹、点云和只读 KD 索引，每线程 MjData 与查询缓冲独立，全部轨迹帧/表面采样精度和 2 任务配额不变。
- **显示与 Enter**：一次批量响应最多一次 Canvas 重绘；首次计算只确认当前所选对；429 继续自动重试。最新模拟由服务器现有 provenance 物理指纹与资产哈希验证：仅布局变更复用冻结轨迹，真实机构/驱动/数模/测距参数修改仍重新仿真。
- **测试事实**：Python/Node 语法检查、旧版逐帧 SciPy 合成精度/队列回归、新增 selected API/geometry pool/UI 定向测试在开发环境执行；原生 Windows MuJoCo、真实网格 1/2/5/10 对 p50/p95、浏览器 WebGL2 与完整跨租约 HTTP 实机压力尚待现场验收，不宣称固定倍数提速。
- **兼容与交付**：Server / Studio / Lab **2.16.9**；Client **0.3.9**、VZ **0.3.2.1** 不变。不新增业务 Tool、HTTP 路由、ProjectSpec 字段或运行依赖。见架构第 119 节及独立开发归档。

# V2.16.8 — 精确测距性能、重复任务去重和 HTML 绿色加粗（2026-11-09）

- **逐帧精确测距**：针对已采样几何增加保守包围球筛选、KD 查询上界与独立线程相同 qpos 重复帧缓存，仍在 0.01s 采样点上逐帧输出完整测距结果；不降低精度、不重做物理积分。处理同一模型多 geom 的重复最近点搜索是本次主要加速路径。
- **为什么比动画慢**：HTML 动画只需最高 20 FPS 的运动/测距帧并使用 WebGL 插值播放，而且导出 POST 先返回异步任务号；曲线对 0.01s 轨迹进行 100Hz 全点精确 KD，15 秒即 1501 帧，另外可能有多个 geom 组合。不能从导出任务 ID 的返回速度推断完成耗时。
- **重复 Enter/并发**：复用已有 JobManager 和测距批量接口，添加原子提交复用，前端遇到 429 按后台提供的 `retry_after` 自动排队，保持用户并发上限 2 以免过载。服务器输出测距阶段计时，允许在真实项目中找出额外瓶颈。
- **HTML 测距线**：与同步改为绿色的原生 Viewer 非碰撞线统一为 RGBA 0.20/0.90/0.45/1；离线 HTML 改为 4px WebGL 三角形线带，取代可能被锁为 1px 的旧 `gl.LINES`，旧已导出 HTML 保持原样。
- **验证**：新建 `scripts/v2168_distance_precision_and_queue_regression.py` 对照原全几何 KD 算法复核距离和线段，含重复姿态、8 并发任务去重；老 1501 帧精确回归保持。静态 HTML/JS 验证通过。原生 MuJoCo 与完整 WebGL2 图形环境不可用时，按 `development/V2.16.8/TEST_REPORT.md` 说明，不承诺所有模型都能在某秒数完成。
- **发布**：Server/Studio/Lab **2.16.8**；Client **0.3.9**、VZ **0.3.2.1** 不变。原有数据、API URL、导出 schema 和工具目录不变；新增业务 Tool、路由、持久变量及第三方依赖均为 **0**。架构第 118 节。

# V2.16.7 — 测距多选滚动稳定、坐标系操作精简与布局草稿保护（2026-11-09）

- **测距对象选择**：对象 A/B 多选列表选中第二项及后续项目时保持原滚动位置。拦截原生选项点击后用 `focus({preventScroll:true})`，同步及下一动画帧恢复下拉列表的滚动偏移，不更改已选资产或测距精度。
- **坐标系 UI**：曲线对象、原值/积分/导数运算选择及删除坐标系按钮移出折叠面板，始终可见；曲线颜色/新增删除曲线也置于紧凑快速编辑栏；高级运算、Gantt、CSV 继续可折叠。整体减小间距、字体和按钮尺寸，单双列/窄屏兼容不变。
- **布局生命周期**：保存后不再显示“当前布局”；仅当 `result_layout.axes` 与当前命名存档不同或尚无活动存档时，显示“当前布局（未保存）”。编辑中的坐标系不再自动改写保存的布局快照，切换离开前需命名保存；取消则保留编辑内容。增加“＋ 新建布局”，从空白开始，并支持显式保存、重名覆盖确认、50 条上限及只读保护。
- **复用架构**：仅扩展 `result_layouts.js`、`app.js`、现有 HTML/CSS 与本地草稿/`project.replace` 链路。新增业务 Tool/API/Job/ProjectSpec 字段及第三方依赖均为 **0**。`Client 0.3.9`、VZ `0.3.2.1` 不升级。
- **验证**：新增 `scripts/v2167_ui_layout_regression.cjs`，同步更新被新规则替代的旧布局回归；版本 Server / Studio / Lab 提升为 **2.16.7**，Lab 接收旧帧。规格和测试见 `development/V2.16.7/`，架构第 117 节。
- **真实浏览器检查**：Chromium 144 无服务器隔离页面验证长列表三次原生点击不回滚、快捷工具可见、字体实际缩到 11px，并验证布局保存/新建 UI；服务端综合自检因本地缺少 `passlib`、`mujoco` 未运行完毕，环境限制详见报告。

# V2.16.6.4 — 动画 HTML 自适应测距阈值可预设（2026-11-06）

- 仿真结果查看页左侧“动画 HTML 设置”新增“自适应测距显示阈值 mm”输入框，默认 25 mm，支持任意正数（可含小数）；原 `animation_html` 项目设置保存与导出 Job/API 复用。
- 修复离线 HTML 代码中固定 `dist*1000<25` 的问题：将 `ProjectSpec.animation_html.adaptive_threshold_mm` 经既有 exporter adapter 写进 `DATA.adaptiveThresholdMm`，播放器按用户的导出阈值过滤并动态显示“小于 XX mm”，仍用严格 `<` 与原来的“自适应”复选框。
- 原有 MuJoCo Viewer 的 `viewer_control.adaptive_threshold_mm`、测距计算/动画采样/时序同步均不改变；旧项目缺字段时保持 25 mm，既有旧版 HTML 不受影响。无新增业务 Tool、服务 API 或依赖。
- 增加 `scripts/v21664_animation_threshold_regression.py` 和 `scripts/v21664_animation_threshold_ui_regression.cjs`，架构第 116 节；测试记录与 SHA-256 在 `development/V2.16.6.4/`。
- Server / Studio / Lab **2.16.6.4**；Client **0.3.9**、VZ **0.3.2.1** 未升级，Lab 继续兼容全部旧版帧。

# V2.16.6.3 — MuJoCo View 正交相机右键拖动响应优化（2026-11-06）

- 发现 MuJoCo 原生 `mjv_moveCamera` 正交平移存在 `0.15` 缩放系数；历史 V2.14.1 仅叠加 3x，且依赖不保证公开的 `_window` 属性，某些环境根本不生效。
- 复用原生 passive Viewer 相机与锁，将正交自由相机的右键平移改为 **约 6.67 倍 native pan**，理论上恢复屏幕鼠标像素到图像拖动像素接近 1:1 的手感。不调整透视、旋转和缩放。
- Windows 私有 GLFWwindow 不可见时，通过当前进程聚焦 GLFW 窗口的 Win32 按键状态捕获右键；其它平台保守推断连续的 native lookat-only 位移。不覆盖鼠标回调、不新建业务 Tool/API/数据库或第三方依赖。
- 实现代码 `Server/backend/app/domain/viewer_runner.py`；新增 `Server/scripts/v21663_orthographic_pan_regression.py`；架构文档新增第 115 节；测试及限制 `development/V2.16.6.3/TEST_REPORT.md`。
- Server/Studio/Lab **2.16.6.3**；Client **0.3.9** 与 VZ **0.3.2.1** 未升级；兼容旧 Lab 消息，项目和时序格式不变。

# V2.16.6.2 — 编辑时序直接同步，切换时才提示备份（2026-11-06）

- 修复在编辑模式按 Enter 时强制弹出“保存当前时序”窗口的问题。现在 Enter 继续将当前 `ProjectSpec.drives` 通过原 `flushInteractionCommit → syncLocalDraft` 可靠同步到服务器，随后刷新坐标系；失败时保留本地草稿并阻止错误仿真。
- “保存为新 TSJSON / 覆盖 / 跳过 / 取消”仅在**时序选择弹窗主动导入/切换/新建**时调用。普通编辑、回车、甘特图编辑均不再触发这组确认。
- 时序弹窗增加“新建空白时序”；使用既有 project PUT 保存空白工作时序，原项目数据权限、旧时序库及命名快照不变。另存 TSJSON 按钮继续作为单独明确操作。
- 解析外部 HTML、PY、CSV、TSJSON 文件及完成替换预览后才询问是否保存原时序；取消、无效文件或异步切项目不能更换当前驱动。
- Server / Studio / Lab **2.16.6.2**；Client **0.3.9**、VZ **0.3.2.1** 保持，Lab 对 2.16.6.1 旧消息继续兼容。无新增 API、业务 Tool、ProjectSpec 字段、计算路径、第三方依赖。
- 测试：`node scripts/v21662_timeseries_enter_regression.cjs`；设计、执行报告、文件清单和 SHA-256 见 `development/V2.16.6.2/`；架构第 114 节。

# V2.16.6.1 — 仿真结果坐标系单双列切换与顶部控制区折叠（2026-11-06）

- **排列切换**：在“仿真结果 → 坐标系”增加“单列 / 双列”按钮；支持响应式回退单列。选择结果通过现有 `uiSet` 保留为 UI 偏好，不写入模型的坐标系配置。
- **紧凑顶部**：每个坐标系默认仅展示名称、曲线摘要、测距状态和“展开设置”；点击后显示可换行的曲线编辑与运算操作两组，下方绘图区始终保持可见。
- **交互完整性**：独立折叠、ARIA 状态、可读权限、曲线数据绑定、CSV、拖拽排序和命名布局保持；重绘与排序时保留每张图的展开状态，切换模型后恢复折叠。
- **画布重绘**：变更列数或容器宽度后，基于父卡片最新宽度重绘 Canvas；不重新启动仿真与测距任务，不改变时间采样或精度。
- **版本与兼容**：Server / Studio / Lab **2.16.6 → 2.16.6.1**，Client **0.3.9**、VZ **0.3.2.1** 保持不变；Lab 接收既有 `2.16.6` 消息。
- **验收**：新增 Node UI 回归、既有前端回归、Python 编译及 CSS 解析测试；当前容器的 Chromium 无法正常启动，真实浏览器像素级验收待目标机器完成。详情见 `development/V2.16.6.1/TEST_REPORT.md`。

# V2.16.6 — 冻结轨迹测距对按帧分块并行（2026-11-06）

- **计算链路**：原 V2.16.5 只按“单帧内多个测距对”分线程，因此单对和帧数很大时无法充分利用多核。新版本在已完成仿真的 `trajectory.npz` 上按互不重叠的帧区间分发任务（每块最多 500 帧，动态缩小以避免负载不均），最多 5 线程；不并行执行有时间依赖的物理积分。
- **姿态更新**：离线曲线每帧只运行 `mj_kinematics` 刷新 geom 位置/方向，不再重复完整 `mj_forward` 的约束和动力学阶段；距离仍由 Viewer 原 `_measure_pair` 的全部表面采样点查询计算，`exact_all_samples`、单位 mm、最小值和时间规则不变。
- **线程与内存**：共享只读 MuJoCo 模型、表面采样点及 KD 树；每线程单独分配 `MjData`、KD 查询数组和缓存。离线模式省去仅用于 Viewer 散点显示的世界坐标转换。复用 `parallel_sampling.iter_frame_batches`，动画 HTML 原 50 帧/批默认行为不变。
- **有序与任务安全**：按全局帧号合并完成块，按真实连续前缀每隔至少 5 秒发布可用部分数据；进度、取消、异常清理、单对 API、批量 API、Job 槽位、冻结仿真和缓存身份均延续原合同。没有增加工具目录、数据库表、ProjectSpec 字段或第三方依赖。
- **版本**：Server/Studio/Lab **2.16.5 → 2.16.6**，Client 保持 **0.3.9**、集成 VZ 保持 **0.3.2.1**；Lab 继续接收旧版帧，当前帧版本更新为 2.16.6。
- **核验与目标**：`scripts/v2166_distance_parallel_regression.py` 实施 1501 帧与真实 SciPy KD 查询的合成运动学基准，检查与串行参考结果逐帧相等、线程隔离、部分结果、取消及异常。当前构建环境缺少原生 MuJoCo，不可视为 Windows 实机测出 5 秒 SLA。建议在实际模型上测预处理 + 曲线计算总时间；目标为 15 秒、0.01s 间隔的测距对在 5 秒内完成，但大型 STL、测距对数量、核数和任务排队会影响结果。

# V2.16.5 — 完全精确并行测距、中文 CSV 与动画分批导出（2026-11-03）

- 实际输入为 2.16.3 完整包；本轮重新补入历史 2.16.4 所述缺项，再统一升级 Server / Studio / Lab 至 2.16.5。Client 0.3.9、VZ 0.3.2.1 和 Viewer bundle 协议保持不变。
- Viewer 动画控制默认“完全精确”；曲线使用同一 `_measure_pair` 的全部既定采样点，不再套用 4096 点低延时查询预算。相同冻结模型、采样参数和 qpos 下保证同一数值口径，非连续三角面几何精度承诺。
- 测距对布局触发批量后台任务：每帧一次 `mj_forward`，各对使用独立缓冲并行求值，最多 5 个测距线程。按原轨迹顺序输出，5 秒发布/轮询进度，完成提示；旧低延时缓存隔离，冻结仿真与基线不被改写。
- 坐标系工具栏增加命名布局存档、默认测距对布局、删除存档；保存名称、曲线、顺序，支持拖拽及方向键排序，测距原值曲线标注最小点时间和数值。复用 result_layout/project.replace，旧项目兼容默认空布局库，存档上限 50。
- Enter 同步前复用时序保存保护，支持新建、覆盖、不保存、取消；保留已有 Hub 折叠记忆、静态旧 HTML/Python 时序导入。Python 导入仍只读取静态清单，不执行任意脚本。
- 映射 CSV 支持 UTF-8、GBK/GB18030、带 BOM 的 UTF-16/32；忽略开头中文/英文表头及说明，支持逗号、分号、Tab、空白。新上传对非法数据行/NaN/无穷值明确拒绝，不改变原坐标或做运动积分；历史文件恢复继续容忍坏行、保留有效点。
- 动画 HTML 按 50 帧/批、最多 5 线程准备姿态与测距数据；只读共享模型、各线程私有 mjData 和查询缓冲。按原帧号合并，全局修正四元数连续性；临时文件原子发布，取消/失败保留旧文件。物理轨迹积分仍按原求解器执行，浏览器 WebGL 负责播放渲染。
- 真实 MuJoCo、API、前端逻辑及兼容检查记录见 `development/V2.16.5/TEST_REPORT.md`。大型机构不保证五秒算完；Windows/OpenGL 现场验收及完整真实浏览器 E2E 尚待执行。升级前备份数据、停止旧服务、替换源码并硬刷新浏览器；不要同时运行两版写同一数据目录。

# V2.16.2 — Web 甘特图即时刷新、MuJoCo 任务隔离与 Viewer PNG 修复（2026-10-27）

- **时序预览解耦**：增加既有 `/preview` 的草稿只读 POST 扩展及包含结果信息的可选 GET 开关；前端数值即时绘制 + 最新输入防抖刷新，当前模型草稿无需 Enter 即更新 Web 甘特图，仿真结果与项目正式保存保持独立。
- **驱动曲线预计算**：逐帧统一求一次完整 schedule，分发到每个驱动；不再逐驱动为相同时间重复求解。
- **坐标系求解**：复用现有进程隔离和 JobManager；原生重计算独立任务池/容量门禁避免抢占 Hub 请求线程；闭链求解避免相同状态的重复原生 forward；输出各阶段耗时用于实际瓶颈分析。
- **Viewer 甘特图**：启动前检测/更新模型专属浏览器甘特 PNG+JSON；Viewer 不再读取/生成风格不同的旧兼容图；Tk PNG fallback 修复 Client 0.3.9 未安装 Pillow 时缓存读取失败的情况。
- **升级**：Server / Studio / Lab 2.16.1 → **2.16.2**，Client 0.3.9 和 VZ 0.3.2.1 保持不变；架构第 110 节 + 回归脚本。仅作无 GPU 的协议、源码、HTTP/模拟运行自检；Windows 多用户/真机性能待验收。

# V2.16.1 — 编辑器提示降噪与签入版本历史（2026-10-27）

- 修复双击进入已签出模型时的多重确认和“正在打开/已进入”重复 Toast；可选 UI 布局读取失败静默退化，租约恢复成功不重复弹提示。相同账号、租约、服务端基线的 IndexedDB 草稿安全静默恢复；失效租约或不同服务器版本不得自动恢复，数据冲突继续可见报错。原 Toast 增加去重和数量上限。
- 签入弹窗改名为“保存并签入模型 / 保存到版本历史（可选）”，左侧可选新建或覆盖已有普通历史版本，右侧实时读取当前模型 `versions/*.json`/`.meta.json` 的历史名称、创建时间、作者、备注，基线/锁定照常显示但不能选中覆盖。选择普通版本后自动填入历史名称、说明和原 ID，覆盖需二次确认。
- 复用已有 `ProjectStore.archive`、`ProjectStore._overwrite_target` 和 lifecycle 的 `overwrite_version_id`，原服务器强制拒绝锁定/基线/不存在版本；历史目标被刷新删除后不自动改成新建。当前最新 `project.json` 始终保留；默认人工签入不另建档；自动/系统签入的安全存档不改。
- 原 `GET /api/projects/{id}/versions` 新增可选 `detail=metadata` 轻量模式，只读侧车与基本字段，不再在签入弹窗为每个历史快照计算派生预览；旧 URL 响应保持不变，不增加业务 Tool/模型 schema/数据库。
- Server / Studio / Lab **2.16.0 → 2.16.1**；Client 0.3.9、VZ 0.3.2.1、Project Bundle v2、Viewer schema 4、Lab UDP 1.0 保持兼容。架构总纲追加第 109 部分；新增签入前端/后端和编辑器通知专项回归。未声明 Windows/MuJoCo 真机多用户已验收。

# V2.16.0 — 时序库、Enter 同步刷新、层级子级与历史版本锚点（2026-10-27）

- 驱动页新增“时序选择”：读取**当前模型**时序库，选择 TSJSON 替换当前驱动，支持自定义名称将当前驱动存为独立 `.tsjson` 文件。复用 TSJSON v2 序列化和原解析/鉴权接口，不运行额外仿真，不假造结果曲线。同名保存生成独立文件。
- 层级树及框图的层级属性顶部新增“＋ 添加子层级”，沿用现有 `newLayer`、父节点 `parent_id`、本地历史与模型权限。
- 在持久签出 Editor 按 Enter：提交字段变更，先完成已有本地草稿同步，再提交 `/simulate` Job 刷新坐标系；失败时保留草稿且不使用错误模型求解。已有仿真运行时最多排队一次。弹窗/按钮/文本域的 Enter 不触发仿真。
- “同步草稿”和“刷新坐标系”按钮隐藏，保留内部钩子；“刷新动画”仍独立。结果页左栏压缩输入框与垂直间距，四个折叠标题统一为 32px 的样式。
- **签入总会保存最新版本**，默认不额外创建历史检查点；需要时勾选“同时创建历史版本锚点”并命名。编辑过程中仍可主动新建/高级覆盖普通版本锚点，不能覆盖基线；自动/强制签入原有保护性存档仍保留。
- Server / Studio / Lab **2.15.11 → 2.16.0**；Client 0.3.9、VZ 0.3.2.1、ProjectSpec、Viewer 4、Bundle v2、Lab UDP 1.0 不变。架构总纲增加第 108 节；不增加业务 Tool 或业务数据库。
- V2.16.0 FastAPI TestClient 与 Node VM 交互回归、V2.15.5/6/7/10/11 兼容回归和 Lab 协议回归通过。真实 Windows/MuJoCo 多用户与浏览器 E2E 仍待现场验证。

# V2.15.11 — 多用户 Viewer 启动隔离、本地草稿与连接恢复（2026-10-26）

- 管理员服务端 Viewer 由同步 HTTP 调用改成 202 Job；按账号跨会话实施 Job 配额；复用最新指纹一致轨迹，避免刷新坐标系后重复求解；新鲜轨迹不存在时使用可终止独立仿真子进程。两个 Viewer 启动槽、最多六个服务端原生 Viewer、每用户两个，同时限制子进程数值库线程。
- 工程师 Viewer 不再预提交 `/simulate`，Bundle 的 `run_project_simulation` 同步 fallback 改为 `run_project_simulation_isolated`，并发打包上限 2，繁忙时明确 429；Server/Client Viewer 预计算分别限制 240s/120s。Viewer 启动不再强制等待甘特图 PNG；启动任务及窗口就绪检测不再占用全网页阻塞遮罩。
- 浏览器新增 IndexedDB 本地草稿（同账号/同项目/同签出租约/同服务端基线校验，14 天/16 份/8MiB 上限）和最多 32 帧本地 ProjectSpec 撤销（刷新后尽量恢复最近最多 8 帧）；普通字段/UI 调整与拖动排序、游标、甘特图修改先保留浏览器，显式“同步草稿”、仿真/导出/签入前再使用现有 Server Tool 写路径。导入/其它遗留动作仍按原协议同步，不宣称无网完全独立运行。
- Hub 列表有认证后短期缓存和离线退化显示；Editor 免等待 Hub 全量目录，直接对目标模型鉴权进入、取消全屏拦截遮罩；租约 heartbeat 连续三次失败才提醒，后台 Job 空闲降频减少多用户短轮询冲击。
- 版本号：Server/Studio/Lab **2.15.11**（由 2.15.10 更新）；Client **0.3.9**、VZ **0.3.2.1**、Viewer Schema **4** 保持兼容不升版。部署前停旧进程，强制刷新浏览器 JS/CSS 缓存，不要与之前的 V2.15.9 独立分支直接混覆盖。
- 本包附完整修改源码、新增专项离线回归；无目标服务器日志和 Windows MuJoCo 实机，尚未证明彻底消除所有白屏/Native Crash 或达成特定 p95 SLA。

# V2.15.10 — Viewer 同口径测距对曲线按需计算（2026-10-20）

- 仿真“刷新坐标系”仅计算/保存机构轨迹；不再逐帧调用 `mj_geomDistance()` 并截负值成 0。测距对暂记 `not_computed`/空值，CSV 空字段不写假零。
- 只在用户选择测距对时，后台复用 Viewer 表面撒点 + SciPy cKDTree，采样/建树一次、每帧计算相同 qpos；按进度显示、并行上限 2、计算完成持久缓存。再选相同曲线直接读缓存。
- 恢复缺失值断线、派生与多曲线运算不补 0；界面状态和 CSV/NX 工程导出拒绝未完成的派生曲线；只读基线和模型 JSON 结构不变。
- 按运行/配置/被引用数模变化自动隔离/失效缓存。增加两个专项离线回归脚本；SciPy 升级为 Server 必装依赖。
- 完整源代码**基于本轮可读 V2.15.8 集成包**实现，统一可执行版本 2.15.10；**未合并之前不可读取的 V2.15.9 编辑器启动优化**。升级正在运行的 2.15.9 前，请先进行三方合并；VZ 0.3.2.1、Client 0.3.9 不变。
- 无真实 MuJoCo/STL 大模型环境，未进行现场精度与实际延时认证。

# V2.15.8 — 连接与等待体验、独立坐标系/动画刷新、原生 Viewer 电机滚动（2026-10-20）

- 浏览器 `/state` 与 `/events` 同源 Cookie 鉴权；401 暂停轮询并重登，临时网络失败的 Job 查询使用单飞/退避；原生 Viewer 不再匿名 4Hz 请求需认证的 `/state`。
- Editor 初次加载复用 `/edit-session` 项目 JSON，UI 状态使用轻量 `/state?detail=ui`，其余模型预览/资产列表在首次渲染后加载；UI 状态偶发失败不会挡住模型编辑。
- 仿真结果页拆为“刷新坐标系”/“刷新动画”两个独立后台任务，无默认级联；等待面板显示真实秒数、阶段和网络状态，签入异常后核对实际生命周期。
- 确认普通历史存档始终只是 `versions/*.json` + `*.meta.json`，复用数模资产；基线继续冻结 STL/交付资产。Viewer Tk 控制面板新增可滚动电机列表与更清晰的折叠交互。
- 服务端基线耗时拆阶段记录便于现场调优；离线 27/27 回归通过，原生 MuJoCo 与实际 STL 高负载仍需现场测量。
- Server/Studio/Lab 2.15.8；Client 0.3.9、VZ 0.3.2.1 不变；架构新增第一百零五部分。

# V2.15.7 — 离线 HTML 测距与电机位置面板防重叠（2026-10-19）

- 右上角测距对/电机面板统一纵向流、9px 间距及深色半透明背景，电机字号缩小一级；窄屏与 Lab 嵌入保留滚动/悬停交互；无物理数值变更。

# V2.15.6 — Hub 气泡首屏可见、基线冻结锚点及轨迹/动画无损提效（2026-10-16）

- Hub 轻量目录接口主动携带模型关键数据：基线固定锚点，工作模型按最新存档/当前项目取数；RAM + `core/hub_critical_data.json` 派生缓存让点击模型不再是气泡刷新的必要条件，覆盖或删除存档可自动失效。
- Hub 每 25 秒仅刷新轻量目录，可见时增量更新；10 分钟复用旧流程刷新分类树与回收站。空闲标签页不轮询，不因未选中模型发起详情请求。
- MuJoCo 动力学步进共享每步驱动计划/锁力/关节字典；运动学复用关节索引；动画已验证轨迹模式不再计算未被使用的 offset。保留物理算法、测距精度、时间步长、帧数及溯源校验。
- 模型初始化、采样/步进、闭链求解、测距和序列化提供耗时字段；本机缺原生 MuJoCo，无法保证任意工程的实际提速倍数。
- Server/Studio/Lab 2.15.6，Client 0.3.9 和 VZ 0.3.2.1 原样保留；原架构新增第一百零三部分及离线专项回归。

# V2.15.5 — Studio/Lab 时序归档与基线修复

- Server/Studio/Lab 统一版本号 2.15.5，Client 0.3.9 和 VZ 0.3.2.1 不变。
- 时序库仅保存 `.tsjson`；映射 CSV、单轴 CSV、合并 CSV、Lab 运动段 CSV 与旧版主时序 CSV 统一归入交付数据的 `表格文件夹`。
- 修复参数更新后基线自动刷新时，未解析公共数模 `@model_assets/` 导致的 STL 假性缺失；成功仿真 XML 进入交付数据。
- 签入三段式对话框：分页提醒、存档/不存档、命名并新建/覆盖版本与填写日志；保留回档保护和基线不可覆盖规则。
- 物理基底来自本次 V2.15.3 工程包：此前 V2.15.4 的三项功能已按需求复现并与 V2.15.5 合并，非从缺失的 V2.15.4 ZIP 做二进制补丁。

# V2.15.1 — MuJoCoLab 紧凑单屏布局与右侧上下可调高度（2026-10-13）

- 保留 Server V2.14.2 内部基线签入身份作用域修复及启动历史系统锁恢复；在此代码基线上移植 V2.15 Lab UDP/身份校验模块。
- Lab 采用一行紧凑顶栏、主动画占满左侧、右侧时序甘特图与通信 JSON 上下堆叠；删除占高度的副标题、说明面板和多余底栏。
- 甘特图每电机一行，运动色块按时间轴对齐，多个运动段在同行展示，细节悬停查看；右侧分隔条支持指针、键盘、双击复位并保存比例。
- 隐藏编辑入口保留通过 project.replace 写入 ProjectSpec 的授权路径，支持安全的内置曲线直接时序段，写入模型时序库侧车 CSV，修改后动画强制失效。
- 嵌入 Lab 的 Viewer 顶部工具与电机位置浮层默认收起、悬停显示；独立 HTML Viewer 不变。Client / VZ / protocol schema 不变。
- 浏览器桌面/移动/7 电机、业务 API、协议、历史基线锁回归必须通过；原生 MuJoCo+Simulink 需要生产环境验收。

# MuJoCo Studio Changelog
> 本文件是正式交付包中唯一的版本演进索引。V2.8.14 及更早内容由 V2.8.14 包内分散的 `CHANGELOG_*` / `RELEASE_NOTES_*` 去重归并而来；同一版本若存在多份说明，只保留信息量更完整的一份。版本化 SPEC、TEST_REPORT、MODIFIED_FILES、PACKAGE_HASHES 等详细研发证据不随正式 ZIP 发布，继续属于开发归档。

> 从 V2.8.16 起：每个新版本只在这里追加一条版本记录；`architecture_master_prompt.md` 只维护当前有效架构规则和长期约束，不再复制完整历史日志。

## 当前交付

- Server：`2.15.6`
- Client runtime：`0.3.9`
- Client distribution label：`V0.3.9 WindowsFix`
- Minimum compatible Client protocol for Viewer launch：`0.3.9`
- 整理日期：`2026-10-16`

# Server version history

## V2.15.3 — Lab 测距对 ID 恢复与动画 HTML 导出加速（2026-10-13）

- 修复测距对在 `_build_distance_pairs` 运行时丢失原始 `id`，导致 Lab 在动画导出后的采样验证中抛出“测距对缺少稳定 id”。测距 ID 全程沿用 ProjectSpec，空/重复仍严格拒绝。
- 复用已有 `_current_simulation_trajectory` 指纹新鲜度判定；Lab 自生成有效轨迹按哈希/引擎签名缓存，Studio 结果页可安全复用 Lab 轨迹；所有变更或污染缓存均降级为重新求解。
- HTML 共享导出器同一 MuJoCo 网格实例避免重复解析/简化/编码；Viewer 重复测距对象共享表面撒点，同时保留实际采样值与帧率设置。新增场景、轨迹、网格、测距与编码分阶段耗时。
- 新增 v2153 离线专项测试并继续通过既有业务/Chromium 回归。无新增业务 Tool/API/Job、UDP 版本、ProjectSpec 权威字段；Client 0.3.9、VZ 0.3.2.1 不变。原生 MuJoCo 速度对照需生产环境验收。

## V2.15.2 — UDP JSON 完整时序 / 实时状态独立观测（2026-10-13）

- Lab 右下角新增 TIMELINE / STATE 小型切换标签，保留 V2.15.1 单屏、上下分隔条和动画主区域；完整时序不再被实时状态覆盖。
- deploy 成功后 HTTP 回显同一份已发送 UDP 逻辑 JSON，STATE 仅对发送成功帧刷新；配置/项目/时序失效安全清除快照，防止异步部署串项目。
- 新增浏览器与实 UDP socket 一致性回归，Lab 协议 1.0、VZ / Client / Project schema 不变。


## V2.14.2 — 基线系统租约修复与启动自愈（2026-10-13）

- 修复 V2.14.1 创建基线时，系统临时签出使用 `__baseline_system__`，但底层权限读取当前用户身份，导致签入失败并将模型遗留为系统签出状态的问题。内部身份作用域现在用 `set_active_identity` / `reset_active_identity` 全程闭合，操作结束无条件恢复原用户身份。
- 自动基线仿真全程保留权威 Kernel 引用；仿真/发布/临时工作区清理失败后仍尽力签入，内部租约变化时拒绝误放行其他用户。
- 服务启动时仅自动恢复匹配系统保留角色及完整 UUID 租约的 V2.14.1 遗留锁；普通签出、冻结基线、可疑租约均不触碰。恢复后模型回到签入状态，可重新签出；不直接改写用户 project.json。
- 新增真实 Kernel/ProjectStore 生命周期回归及启动自愈测试，兼容已有基线/Viewer/布局/CSV 回归。无新增业务 Tool、公开 API、Job 或 ProjectSpec 持久字段；Client/VZ/Viewer schema/完整包协议不变。


## V2.14.1 — 交互、响应式及历史模型兼容（2026-10-13）

- 手动签入复用既有生命周期 `project.lifecycle`，先提示强制关闭分页，再选择“生成存档 / 不生成存档”；仅显式人工签入允许跳过存档，后台挂机、会话收敛、强制签入和系统路径仍保留强制存档。失败时一次性存档策略回滚/清理。
- 甘特图弹窗打开时触发既有 `恢复默认`，无需再点一次；结果页甘特图“字号调整”初始 11px，复用 `ui.results.gantt_font_size`，旧人工偏好继续有效。
- 原生 Viewer 在正交视角右键拖拽时按 native `lookat` 变化增量叠加为 3 倍，使用原生 Viewer 锁，不替换 GLFW 鼠标回调；透视/其它按键行为不变。
- 修复 Hub 文件夹切换导致右侧属性检视器隐藏/下沉、项目列表宽度回退与拖拽条消失；桌面布局保持五列，读取既有 localStorage 宽度值。
- 层级建模、结果甘特图与动画页面宽度自动撑满；1080P/125% 缩放下测距页面桌面三列；坐标系高滑条改变 Canvas 时固定父容器计算宽度并稳定 scrollbar gutter。
- Pydantic ProjectSpec 迁移仅将历史 `null` 可选复合配置及空占位行还原为 schema 默认值，不吞噬非法非空内容，改善仿真 worker 的 `valid dictionary or object` 错误。
- 新增专项和多视口 Chromium 回归；Client 0.3.9、VZ 0.3.2.1、Viewer bundle schema/controller 4、完整包 v2 均不变；没有新增业务 API/Tool、Job 或权威字段。


## V2.14.0 — 映射 CSV 迁移路径兼容（2026-10-13）

- 修复旧项目的映射段仍保存旧机器绝对路径、在 `V2_projec` 随部署搬迁后无法校验/解析的 BUG：优先从当前 `ProjectStore` 项目根下的 `assets/mappings/` 查找迁移后的 CSV，成功后立即把数值表写入 `segment.points` 并把历史路径改为项目相对路径。
- `ProjectStore.get/create/save` 统一调用同一个兼容恢复入口；存量已签入/签出项目首次打开可自动无损落盘，新建/更新项目同样按该规则标准化。已冻结 baseline 仅内存补点，**不改写其权威 project.json**。
- 同一 resolver 覆盖模型 JSON/完整包的导出快照和外部运动 CSV 的兼容读取；有内嵌点而原 CSV 不存在时运行仍可用。缺失/损坏的 CSV 不伪造点，不尝试读取已经脱离当前项目资产根的旧绝对路径。
- 存储位置沿用 `storage_config.py` 的唯一 `V2_projec` 根：Linux 默认 Server 上两级，Windows 默认上四级；实际运行以管理员保存设置与 `MUJOCO_STUDIO_DATA` 为准。历史物理映射文件仍保存在 `<DATA_ROOT>/projects/<分类>/<项目ID>/assets/mappings/`；新导入映射仍以 JSON 内嵌为唯一运行真值，不额外复制原始 CSV。
- 业务 Tool、API、Job、新增 ProjectSpec 字段：**0**；Client 0.3.9，VZ 0.3.2.1，Viewer bundle schema/controller 4，完整项目包 v2 维持不变。


## V2.13.6

### Hub 可调项目列表、基线仿真自愈、游客纯净结果页与 Viewer 刷新
- Hub 左侧“项目列表”默认宽度由 186px 提升到 242px（约 +30%），新增可拖拽/键盘调整的分隔条并在浏览器本地保存宽度；不进入项目权威状态。
- Hub 右侧数模资产文件区移除“上传文件夹”按钮；同排“上传文件 / 批量下载 / 清空”按钮尺寸约增大 30%，既有资产 API 与其它兼容上传入口不变。
- 创建基线检测到最新仿真缺失或 provenance 指纹陈旧时，服务端使用窄范围内部 system actor 复用 `project.lifecycle` 和现有 isolated simulation/publish 链自动完成签出→仿真→签入→再校验；正常陈旧结果不再要求用户手动重新仿真。
- 游客 Hub 仍只返回 baseline；双击后直接进入纯净坐标系结果查看，隐藏仿真设置、甘特图/动画页签及修改/导出按钮，仅保留坐标系高度与 ±游标查看控制。
- 修复 500ms 自动提交竞态：authoritative mirror fence 新增编辑焦点 revision，旧字段延迟提交不再在用户刚进入新字段时重绘 DOM 并抢走焦点。
- 每次顶部 MuJoCo View 启动前先复用现有 `/simulate` Job 刷新当前结果，仿真失败则不启动 Viewer，确保 Viewer 与结果查看使用同一轮最新结果。
- 新增 ProjectSpec 权威字段 0；新增业务 Tool/API/Job kind 0。Server: 2.13.6；Client: 0.3.9；VZ: 0.3.2.1；Viewer schema/controller: 4；complete project bundle: 2（兼容导入 1/2）。


## V2.13.5

### 时序库可移植性、基线冻结与环境绑定状态收口
- 修复 V2.13.0 后“时序库是模型一等文件资产、但完整包与 baseline 冻结链没有完整携带”的生命周期缺口：baseline 现在冻结 Hub `时序库/`；完整项目包升级为 format v2，并新增 `properties/time_series_library/`。
- 完整包 v2 的 manifest/inventory 继续对全部文件做大小与 SHA-256 校验；V2.13.5 导入器同时接受旧 format v1 与新 v2。旧 v1 没有时序侧车时按“无时序库快照”兼容，不伪造数据。
- `project.metadata["vz_push"]` 明确归类为当前 Hub/VZ 部署的环境绑定状态，不属于可移植模型语义。模型 JSON/完整包导出会剥离该状态；创建新身份的复制、fork、baseline、导入也会清理它，避免新项目误指向源项目的 VZ model id。
- Hub `时序库/` 继续是 Hub 权威源，VZ `time_series_library/` 仍是只读投射，`time_series_workspace/` 仍是 VZ 本地 fork；VZ workspace 不进入 Hub 完整包，也不反向写 Hub。
- 需求治理调整：后续不再把“新增权威字段=0”当作独立成功指标；优先级改为“唯一真相 + 生命周期完整 + 可移植/可回放 + 最小必要 schema”。本版本仍无需新增 ProjectSpec 字段、业务 Tool、API、Job 或 VZ 协议字段。
- 回归门禁同步修正历史漂移：V2.13.0 已把 VZ “生成预览图”入口从顶栏移至模型行，并移除用户动画中心项目组水印；`self_check.py` 现校验现行模型行预览链和“用户链无水印 + 共享 watermark 渲染器仍保留”的真实合同，不恢复已废弃 UI/行为；Viewer mapping-family 逆映射数值回归容差由不现实的 `1e-12` 对齐到 `1e-9`，仍远小于 UI/模型精度且不改变映射算法。
- Server: 2.13.5；Client: 0.3.9；VZ: 0.3.2.1；Viewer schema/controller: 4；complete project bundle: 2（兼容导入 1/2）。


## V2.13.4.1

### 测距对拖拽排序
- 每个测距对卡片左侧新增独立拖拽柄，可直接调整 `ProjectSpec.distance_pairs` 的显示/执行顺序；落点按目标卡片上半区/下半区显示前插/后插提示。
- 拖拽身份使用稳定 `pair.id`，不依赖可能变化的数组 index；只读模型禁用拖拽。drop 后复用既有 `markDirty → renderPairs → commitCurrentStep/project.replace` 保存链，刷新后顺序保持。
- 不新增测距排序字段、不新增 API/业务 Tool/Job；原名称、对象 A/B、高级设置、测距计算和结果消费逻辑保持不变。
- 开工参考继续借鉴 SortableJS 的 `handle + data-id + onEnd/toArray()` 思路，但不引入第三方依赖。
- Server: 2.13.4.1；Client: 0.3.9；VZ: 0.3.2.1；Viewer schema/controller: 4。


## V2.13.4

### Hub 属性轻量刷新 + 关键数据顺序可靠保存 + 基线冻结时间排序 + 测距对 UI 优化
- Hub 全局提示统一固定到右上角，覆盖历史右下角 CSS；导入数模、保存、同步、错误等继续共用现有 toast，不增加通知系统。
- 修复关键数据拖拽后偶发不保存/刷新回旧顺序：拖拽期间只改临时 DOM，在 `dragend` 一次提交最终顺序；提交时本地即时重排，服务端返回 canonical order 后确认，失败才回读权威 preview。VZ 2 秒状态轮询在拖拽期间不重绘 Hub，避免中途替换 DOM。
- Hub 属性读取改为“summary 首屏 + 当前选中模型按需完整 preview + versions/files 二级异步元数据”的分层加载；移除启动后的全模型详细 hydration。名称/关键数据顺序增加窄 `PATCH /hub-properties`，服务端读取最新 ProjectSpec 后复用 `project.replace`，避免客户端完整 GET/PUT 带来的延迟和陈旧覆盖。
- 搜索框右侧删除旧“最近打开/名称”排序下拉，新增 `基线：早 → 晚 / 晚 → 早` 切换。签入/签出模型始终排在全部 baseline 之前；baseline 只按冻结时间方向排序。
- 测距对卡片按草图改为“大名称 + 名称输入 / 对象A / 对象B / 高级设置”；高级设置折叠显示精确撒点间隙和寻优边界。新建默认 precise=2mm、animation=2mm、boundary=8mm；旧项目显式值保持不变。
- 开工参考借鉴 SortableJS `onEnd`/Store 的“结束时提交最终顺序”和 toastr 的右上角统一通知定位；项目内部仍只复用已有 Tool/ProjectSpec/preview/data-bind。
- 新增业务 Tool 目录 **0**；新增 ProjectSpec/L1/L2/L3/Session/Job 权威持久字段 **0**；新增 Job/artifact kind **0**。仅新增请求级 Hub 小属性 envelope 与前端瞬态排序/拖拽状态。
- Server: 2.13.4；Client: 0.3.9；VZ: 0.3.2.1；Viewer schema/controller: 4。


## V2.13.3

### Hub/VZ 推送库闭环 + 工程师驱动时序补齐 + 时序单源复核
- 修复 VZ 工程师“移除模型”后 Hub 仍保持推送开启的问题：集成启动器为 Hub/VZ 注入一次性本地 bridge token；VZ 删除当前 `published=true` 的 Hub 模型后回传 Hub，实时把对应 `vz_push.enabled` 关闭。若 VZ 是旧进程或回调暂不可用，Hub 轻量状态接口会对 VZ catalog 做 reconcile 兜底。
- Hub 模型列表名称行右侧新增 `【已推送】`，只在当前状态为已发布时显示；Hub 页面每 2 秒只读取轻量推送状态，同步更新卡片和当前模型推送开关，不重复拉取完整模型详情。
- Hub 主动关闭推送时只把 VZ `_hub_source.published=false`；VZ 工程师/用户 `/api/models` 统一隐藏未发布 Hub 模型。VZ 模型目录不被物理删除，因此再次推送可保留工程师本地 0%/100%/速度/模式和 `time_series_workspace/`；只有工程师明确移除才进入 VZ trash。
- 修复工程师驱动设置初始化：发布时继续以 `ProjectSpec.drives` 为主，同时复用 `parse_time_series_csv()` 扫描 Hub `时序库/` 主表，按 drive id 补齐仍只存在于原模型时序中的驱动。补齐 drive 继承名称/运动副，首次校准仍为 0%=0、100%=30、速度=30；运动段依然只属于时序库。
- 复核 Hub/VZ 时序链：Hub `时序库/` 是唯一 Hub 权威源，VZ `time_series_library/` 只读同步；VZ `time_series_workspace/` 为独立可编辑副本。Hub ZIP 刷新只原子替换 source library，不覆盖 workspace。
- GitHub 开工参考记录采用 upstream/downstream 的单源投射边界与 reconcile/deletion 的显式状态思路；项目内部仍优先复用既有 `metadata.vz_push`、`_hub_source`、`ModelStore`、`activity_parts` 与时序 parser。
- 新增业务 Tool 目录 **0**；新增 ProjectSpec/L1/L2/L3/Session/Job 权威持久字段 **0**；新增 Job/artifact kind **0**。
- Server: 2.13.3；Client: 0.3.9；VZ: 0.3.2.1；Viewer schema/controller: 4。


## V2.13.2

### Hub 驱动校准投射 + VZ 多模型联合仿真 + 结果查看紧凑化
- Hub→VZ 发布链现在同步每个驱动的名称、`exchange_drive_id` 与绑定运动副。首次由 V2.13.2 投射时 VZ 工程师校准默认 0%=`0`、100%=`30`、速度=`30`；Hub 运动段仍只来自时序库，不写入驱动设置页。V2.13.2 之后再次刷新同一模型会更新驱动身份/运动副绑定，但保留工程师已经修改的 VZ 本地 0%/100%/速度/模式。
- VZ 用户页支持把右侧模型卡片直接拖入场景，多个模型在同一个运行时 composite 中联合仿真。各模型层级树统一挂到 synthetic root，并按 `_a/_b/...` 对 Layer、运动副、闭链、驱动、mesh/asset 做确定性命名空间化；parent、闭链端点/solve-joint、drive-joint、时序 drive_id 等跨引用同步重映射。场景组合仅存在于一次仿真 workspace，不回写源模型。
- 用户场景控制板改为“每模型一行 + 单绿色总包络”：色块覆盖该模型当前时序所有启用驱动/运动段的最早开始到最晚结束；时间轴为 1 s 主刻度，当前模型支持 `时序1/时序2/...` 切换，右侧“编辑”进入用户时序编辑页。用户双击运动段只改 start/travel；速度固定取工程师驱动额定速度，Hub 源时序第一次编辑时先复制为 VZ 本地副本。
- VZ 工程师/用户时序甘特图的运动段同时显示名称、start–end 与累计 position_start→position_end，补齐与二代 WEB 甘特图的信息差。
- 二代结果查看删除结果页 `MuJoCo View` 和“一键导出动画 HTML”，原“后台仿真”改为“刷新结果”；坐标系高度滑块和 ±游标迁移到右侧坐标系导航、各坐标系 header 纵向压缩、折叠 summary 风格统一。动画导航新增“重新生成”，复用原 HTML export job/甘特图快照并覆盖最新 HTML，但不打开保存选择器、不自动下载，完成后自动刷新 iframe。
- GitHub 开工参考：复用 `dm_control` Entity attach 的“独立子树挂到共同父场景”思路，以及 MuJoCo attach prefix/suffix 的确定性命名空间做法；项目内部仍优先复用既有 DriveSpec、control_graph、ModelStore、time-series 和 simulation/export 链。
- 新增业务 Tool 目录 **0**；新增 ProjectSpec/L1/L2/L3/Session/Job 权威持久字段 **0**；新增主 Job/artifact kind **0**。仅新增 VZ runtime-only `scene_composition.py` 纯组合 helper。
- Server: 2.13.2；Client: 0.3.9；VZ: 0.3.2.1；Viewer schema/controller: 4。


## V2.13.1

### VZ 时序库工程师甘特图 + 结果坐标系自适应 + CSV 交付边界修正
- VZ 工程师界面新增“时序库”导航：Hub 同步主时序只读；复制到 VZ 本地 workspace 后才允许重命名、删除和双击色块编辑起始时间、速度/时长、行程。Hub 后续刷新只替换同步源，不覆盖 VZ 副本。
- 时序甘特图按两类颜色显示：黄色为匀速/缓起缓停，蓝色为映射/点表/外部 CSV 变速；显示交互复用二代 WEB 甘特图的横/纵缩放、游标、时间排序/倒序、倒放行、驱动显隐/显示名/拖拽顺序、画布平移与放大/还原。VZ 用户控制板新增“时序1/时序2…”分页，分页跟随当前查看模型并可切换 Hub 主时序和 VZ 本地副本。
- 用户动画底部 transport/progress UI 约缩小到一半，背景 alpha 调到 0.20；硬点/H 点坐标改为左下角透明白字，与右下角“开发支持：喻惟刚”同类覆盖样式。
- 二代结果查看新增“自适应坐标系”，按当前模型每个驱动补齐同名坐标系；每个坐标系名称输入框右侧新增“自适应”，可根据所选曲线自动填入名称。
- V2.13.1 起 CSV 不再属于 managed delivery。合并 CSV 只生成/保存为模型 `时序库/` 的 `VZ_TIME_SERIES` 文件（同时允许本地下载），分别导出的普通 CSV 只做本地分析。baseline 交付完整性从历史 5 类改为 NX / 甘特图 / 模型 JSON / 动画 HTML 四类。
- 修复合并 CSV 在 Linux Server 被桌面能力中间件拦截的问题；`delivery=true` 旧线协议只作为“生成时序库”兼容开关，不再写交付目录。
- 新增业务 Tool 目录 0；新增 ProjectSpec/L1/L2/L3/Session/Job 持久字段 0；Client 0.3.9、Viewer schema/controller 4、VZ 0.3.2.1 不变。
- Server: 2.13.1；Client: 0.3.9；VZ: 0.3.2.1；Viewer schema/controller: 4。


## V2.13.0

### Hub 时序库 + VZ 用户页双栏时序控制
- 每个模型目录新增物理 `时序库/`，不增加 ProjectSpec 持久字段；结果查看合并导出继续复用既有坐标轴投射，同时写入可恢复驱动配置的主时序 CSV。
- mapping 点既嵌入主表，也按 `<驱动>--<运动段>映射表格.csv` 独立归档；驱动设置新增“导入CSV”，本地文件夹和服务端时序库统一进入同一服务端 parser。
- Hub 初次推送和时序库后续增删均通过模型级 ZIP 原子同步到 VZ；VZ 用户控制板按真实 drive/segment 时序展示多色块，打开页面会周期刷新时序 manifest。
- VZ 用户页移除可见左栏和右侧分类管理动作，仅保留中间场景/控制板 + 右侧只读模型库；工程师缩略图生成入口移动到模型行。
- 快速渲染固定使用更浅的 Classic 场景；用户动画移除中心项目组水印，顶部视图/下载/透视按钮整体缩小。
- 新增业务 Tool 目录 0；新增 ProjectSpec/L1/L2/L3/Session/Job 持久字段 0。Client 0.3.9、Viewer schema/controller 4、VZ 0.3.2.1 不变。
- Server: 2.13.0；Client: 0.3.9；VZ: 0.3.2.1；Viewer schema/controller: 4。





## V2.12.2.1

### 伴生驱动 Minimum-Jerk 映射热修复
- 删除 V2.12.2 的 2049 点阈值、运行时降采样、binomial 低通以及“低密线性 / 高密 natural cubic”双语义；归一化后的原始 mapping knot 全部保留为硬位置约束。
- 3 点及以上 mapping 统一改为全局 natural quintic / minimum-jerk 插值：每段五次 Hermite，多 knot 的速度/加速度通过 O(n) 的 2×2 block-tridiagonal 联立求解，使 `∫ jerk² dx` 在严格穿过所有映射节点的曲线中最小；1/2 点保持常值/线性兼容语义。
- 新增共享纯数学模块 `mapping_curve.py`，Server motion 与 Native Viewer 复用；standalone Viewer bundle 同步携带并校验 SHA-256。浏览器 `mapping_math.js` 使用同一方程，forward/inverse 不再分别使用 quintic/linear 两套曲线。
- 新增独立回归 `scripts/v21221_mapping_regression.py`：10001 个高密节点不降采样且节点误差 0；Python/Browser 位置与 1/2/3 阶导数对拍为 0；代表性平滑非线性表的 integrated squared jerk 约为旧 natural cubic 的 0.30%，内部 acceleration/jerk 连续。
- 本版不增加输出端 acceleration clamp，也不暗中偏移用户 mapping knot。若原始节点自身含高频噪声，在“源头严格匀速 + 每个节点必须绝对穿过”的双硬约束下，加速度仍受原始二阶几何决定；本版消除的是插值器制造的人工节点冲击并给出严格穿点条件下的最小 jerk 解。
- 新增 ProjectSpec/L1/L2/L3/Session/Job 持久字段 0；新增业务 Tool/API/Job 0。Client 0.3.9、Viewer schema/controller 4、VZ 0.3.2.1 不变。
- Server: 2.12.2.1；Client: 0.3.9；VZ: 0.3.2.1；Viewer schema/controller: 4。

## V2.12.2

### 伴生映射高密采样稳定化
- 保留模型 JSON / CSV 内嵌映射点为权威原始数据，不做破坏性降采样；仅运行时对超过阈值的高密点做固定空间尺度重采样与两次轻量 binomial 低通，消除“采样越密，量化/微噪声转成斜率纹波越强”的密度耦合。
- 后端 `motion.py` 与前端 `mapping_math.js` 使用同一 2049 阈值/结点合同；仅高密运行 knot 使用自然三次样条提供 C2 连续求值，低密映射继续保持既有分段线性求值语义，避免旧工程行为变化。
- Dynamic 仿真曲线优先使用 MuJoCo 原生 `qvel/qacc`，不再从 qpos 二次数值微分制造假性加速度尖峰；无原生通道时才回退 gradient。

### 数模自适应、Hub 空态与公共资产重命名
- 层级“自适应”和“全部数模自适应”确认共用 `adaptiveMeshFamiliesForLayer -> /meshes/adaptive -> mesh_library.adaptive_add` 单链路，没有重复 Tool；现有 family adaptive 从只 add 升级为 add/remove/case-normalize 双向同步。整个数模族从库中删除时，层级引用会在自适应时同步删除而不是报错。
- Hub 全量刷新不再自动选中项目列表第一项；没有显式模型选择时清空预览、版本、文件和数模检视上下文，模型属性与资产检视器显示明确空态，不再保留旧模型界面或无限 loading。
- 项目文件夹属性仍只显示名称；甘特图缓存异步返回新增当前选择校验，切到文件夹或其它模型后旧请求不能把甘特图重新显示。
- 公共数模资产库新增文件夹重命名：复用既有 `ModelAssetCopyRequest` 参数结构和 `model-asset-library` 资源，物理目录重命名与所有当前模型 `mesh_root` 引用原子迁移；失败时同时回滚目录与项目引用，支持 Linux 大小写重命名。
- 新增 ProjectSpec/L1/L2/L3/Session/Job 持久字段 0；新增 Tool/Job/artifact/tool directory 0；新增业务 API 1（`PUT /api/model-asset-library/folders`）。
- Server: 2.12.2；Client: 0.3.9；VZ: 0.3.2.1；Viewer schema/controller: 4。

## V2.12.1.5

### 登录完成后的 Hub 工业缩放转场
- entry4 将登录主体升级为真实 `login_mujoco_timeline.glb`：中心刚体/求解器核心、三条倾斜时序轨道、离散关键帧刻度与螺旋收敛轨迹共同表达 MuJoCo 动力学和时序优化；附 Blender 3.6+ 程序化建模源脚本。
- 使用项目内离线 WebGL2 GLB 加载器实时着色，不依赖 CDN、SVG 或位图缩放；近景由真实三角网格和法线重新光栅化。登录页鼠标驱动相机阻尼偏转，认证成功后相机推进并将对象快速扩展至穿过镜头，随后衔接 Hub。
- 登录界面从出现时即展示交错的宽幅金属带主体；矢量轮廓、暗面厚度、镜面分段高光与接缝参考目标效果重构，快速放大时仍保持清晰边缘。
- 登录界面中的桌面鼠标位置通过阻尼插值驱动金属主体轻微 X/Y 透视偏转与光源跟随；交互不再放在登录完成后的等待层。
- 用户名与密码验证成功后，登录卡立即淡出，金属主体保持当时的鼠标观察角度向镜头高速放大；认证刷新后只保留短暂连续性亮场并快速露出 Hub。
- 使用一次性会话标记跨越认证刷新，避免登录页与 Hub 之间闪白或跳切；GLB、加载器和着色器均随包离线交付，不新增运行依赖。
- 保持既有 `/api/auth/login`、`/api/auth/me`、会话与项目加载顺序不变；认证失败会恢复登录按钮，启动失败会释放遮罩并显示原有诊断。
- 支持窄屏布局与 `prefers-reduced-motion`，减少动态效果的用户会得到快速淡入版本。

### 目标质量直接落地
- 修复 `mass_kg -> Studio volume -> density -> MuJoCo volume -> compiled mass` 的二次换算漂移：有明确目标 kg 时，生成 MJCF 现在直接写 `geom mass`。
- MuJoCo `mass` 会覆盖 `density`，因此用户/Layer 指定的 kg 成为最终质量真值；MuJoCo 只利用实际 mesh shape 与该 mass 计算一致惯量。
- 无目标质量的模型保持默认 density 路径，不把所有 mesh 强制改成固定质量。
- `model.mass_properties` 输出新增 `mass_application` 派生诊断；Web 显示最终解析质量、MJCF 应用方式、参考密度和读取体积。
- 原“启用质量 / 逆求密度”更名为“显示 / 编辑质量”，因为该开关本来只控制 UI 展开，不启停物理质量。
- 新增显式 mesh mass、Layer 总质量分配、默认 density 三类永久回归。
- Server: 2.12.1.5；Client: 0.3.9；VZ: 0.3.2.1；Viewer schema/controller: 4。

## V2.12.1.4

### 旋转副世界坐标投射 + Layer 刚体边界防误建模
- 修复 rotation `JointSpec.point`：Studio 保存/显示的是世界坐标 mm；生成 MJCF 时先计算 child Layer 在参考构型的世界原点，再换算为 body-local `joint pos`。此前 Layer 或祖先 `position_mm != 0` 时会把世界点误当局部点，导致旋转中心和载荷力臂偏移。
- 明确一个 Layer 对应一个 MuJoCo body；同一 Layer 的全部 mesh 是同一刚体，Layer 的 joint 对全部 mesh 生效。多 mesh Layer 新增 joint 时 Web 会先确认这一作用域。
- Dynamic joint UI 显示“已驱动 / 被动自由度”。被动 joint 继续受重力、惯性与约束反力运动；若要刚性固定应移除 joint，若要保持位置应绑定 enabled drive 或显式设置 stiffness/frictionloss。
- 数模区域新增“拖到这里=同一刚体；相对运动请建 child Layer”的提示；服务端 validation 增加非阻断刚体作用域诊断。
- 新增世界→局部 anchor 两级嵌套回归；V2.12.1.3 自锁和 Hub 平台默认层级回归继续保留。
- Server: 2.12.1.4。Client 0.3.9、VZ 0.3.2.1、Viewer schema/controller 4 均不变。

## V2.12.1.3

### Hub 跨平台数据根 + Pure Dynamic 驱动静止自锁
- Hub 数据目录在无显式配置时自动识别部署系统：Linux 默认从 `Server` 向上 2 级，Windows 默认向上 4 级，其它系统回退 2 级；管理员已经保存的 `ancestor_levels` 和 `base_path` 继续优先。
- 复用现有 `DriveSpec` / `param.set` / XML 生成 / simulation 链路，未新增 Tool/API/Job。新增 `DriveSpec.dynamic_lock_force`，默认 `2000`；rotation 单位 N·m，translation/crank 单位 N，`0` 表示关闭驱动附加自锁。
- Pure Dynamic 在驱动目标静止时临时把对应 DOF 的 `frictionloss` 提升到 `max(JointSpec.frictionloss, dynamic_lock_force)`；一旦目标开始变化，在 `mj_step1` 前恢复关节原始 `frictionloss`，避免大自锁力妨碍正常运动。
- 驱动面板新增“自锁 / 动力学参数”入口，向用户公开自锁力、Kp 位置保持刚度和 Kv 速度阻尼，并显示自锁接合/释放语义和 N / N·m 单位。
- 新增跨平台默认层级与自锁运行时回归合同；Python 编译和前端语法检查纳入交付验证。Client runtime/protocol 仍为 `0.3.9`，VZ runtime/protocol 仍为 `0.3.2.1`。

## V2.12.1.2

### VZ 二代动画立体字与渲染设置紧凑化

- VZ Fast/Perfect 动画 HTML 恢复原二代软件中间的 3D 立体字 `C项目-时序仿真组`。直接复用已经 vendored 的 `_animation_watermark_config()` / `createWatermarkMesh()` / `DATA.watermark` 与现有 PBR mesh pass；V2.12.1.1 中将 `animation_watermark_text` 显式置空的适配层行为被取消。
- 立体字对 Classic、Bright Studio、Automotive Interior 统一生效，位置/大小/厚度继续使用二代默认值，并沿用现有场景相关颜色处理。
- 工程师 HTML 渲染设置桌面端改成 3 列输入布局，减少 section、grid 与输入框纵向间距；窄屏继续响应式退化。
- 新增 ProjectSpec/L1/L2/L3/Session/Job/VZ 持久字段 `0`；新增业务 Tool/API/Job/artifact/tool directory `0`。Server 版本提升至 `2.12.1.2`，Client runtime/protocol 仍为 `0.3.9`，VZ runtime/protocol 仍为 `0.3.2.1`。


## V2.12.1.1

### VZ 快速/高质量渲染离线动画启动热修复

- 修复 V2.12.1 中快速渲染和高质量渲染生成的离线 HTML 永久停留在“正在载入离线动画…”的问题。
- 根因是 V2.12.1 平行光改造引用了 `KEY_LIGHT_DIR` / `KEY_LIGHT_COLOR`，但共享 HTML 模板未实际生成这两个常量及其计算函数，初始化阶段 `ReferenceError` 阻止首帧 `requestAnimationFrame(render)` 启动。
- 在既有共享渲染器中补齐平行光方向/颜色计算，不拆分 Fast/Perfect 两套实现；并新增启动异常兜底，将无限 loading 改为可见错误提示。
- 新增 ProjectSpec/L1/L2/L3/Session/Job/VZ 持久字段 `0`；新增业务 Tool/API/Job/artifact/tool directory `0`。Server 版本提升至 `2.12.1.1`，Client runtime/protocol 仍为 `0.3.9`，VZ runtime/protocol 仍为 `0.3.2.1`。


## V2.12.1

### VZ 渲染光照、模型库与预览迭代

- 快速/高质量 HTML 渲染及材质场景整体提亮，并在既有 `render_scene` 中加入可配置主平行光强度、水平角和俯仰角；不引入点光作为主光。
- 工程师模型库宽度约缩小 1/3，文件夹图标改为黄色。
- 工程师自动预览继续复用既有正视图 capture 管线，单网格预览上限提升至 200000 面，背景调整为偏暗白色并改善照明。
- HTML 地板保留正面视觉效果，背面透明，避免下视图被地板遮挡。
- 该版本共享 HTML 渲染器存在平行光 bootstrap 常量缺失回归；已由 V2.12.1.1 修复。

## V2.11.7

### Hub 项目文件夹属性、可编辑基线名称与冻结时间展示

- 点击根项目文件夹或任意子文件夹时，右侧统一显示“项目文件夹属性”，只保留文件夹名称输入与保存按钮；不再展示模型/基线数量、创建者、基线清单、最新基线交付数据、文件夹甘特图或模型属性 Inspector。子文件夹继续复用既有 model-type rename，根文件夹继续复用 `/api/project-root/name`。
- 打基线确认框在继续预填最新普通存档日志的同时新增可编辑“基线模型名称”；默认使用 source 模型名。Server 在同一精确文件夹内做 case-insensitive 去重，重名时自动追加 `_001`、`_002`…，唯一自定义名保持原样。
- baseline 创建后，工程师/管理员可以直接编辑模型名称。继续复用 `PUT /api/projects/{id}` 与 `project.replace`，但 Server 对 baseline 强制只投影名称，冻结的 layers/drives/category/mesh_root/交付数据/数模快照不能通过该入口被修改；改名后同步 source unified-history marker 的 `baseline_name`。
- baseline 模型列表的小字改为“冻结时间”，使用 `baseline_created_at` 为权威时间；“冻结时间”加粗并放大。baseline 改名虽然会刷新 `updated_at`，但排序与后代 latest-baseline 穿透仍按冻结时间，不会因改名伪装成新冻结版本。
- 新增持久 ProjectSpec/L1/L2/L3/Session/Job/VZ 字段 `0`、新增业务 Tool/API/Job/artifact/tool directory `0`；仅新增 transient `BaselineCreateRequest.name`，并增加两个 ProjectStore 内部共享 helper。
- Server runtime/package/frontend cache-buster/Viewer/动画导出统一提升为 `2.11.7`；Client runtime/protocol 仍为 `0.3.9`，Viewer bundle schema/controller signature 仍为 `4`，VZ runtime/protocol 仍为 `0.3.2.1`。`architecture_master_prompt.md` 新增第 76 节。

## V2.11.6

### Hub 目录穿透、基线日志复用与企微封存

- Hub 模型类型计数改为递归累计：任意父文件夹的数量都包含其全部后代文件夹中的模型；根“项目”数量直接使用当前权限投影后的全部项目数量。
- 点击项目文件夹时继续显示该文件夹根层的全部直接模型，同时递归穿透后代文件夹；每个后代文件夹只补充其冻结时间最新的一条 baseline，后代 checked-in / checked-out 模型不穿透显示。最新 baseline 以 `baseline_created_at` 为第一排序依据，并以 `updated_at` / `id` 做稳定回退。
- 打基线日志编辑框在打开前刷新现有 `/api/projects/{id}/versions`，从按时间倒序的统一历史流中取最新 `version_kind=archive` 的 `log` 自动填入；baseline 历史标记不会覆盖这条“最新存档日志”。用户仍可在确认前编辑。
- 企微推送暂时封存：删除 Hub 顶部 Webhook 控件、基线弹框企微提示、本地 Webhook 设置、`BaselineCreateRequest.webhook_url` 请求字段、请求端 webhook 发送参数和基线成功/失败推送提示；Server 不再执行企业微信外呼或返回企微通知响应头。
- 继续复用现有 `ProjectStore.list()/model_type_tree()/list_versions()`、archive `log`、baseline `metadata.baseline_log` 与 `/baseline` 路由；新增 ProjectSpec/L1/L2/L3/Session/Job/VZ 持久字段 `0`，新增业务 Tool/API/Job/artifact/tool directory `0`。
- Server runtime/package/frontend cache-buster/Viewer/动画导出统一提升为 `2.11.6`；Client runtime/protocol 仍为 `0.3.9`，Viewer bundle schema/controller signature 仍为 `4`，VZ runtime/protocol 仍为 `0.3.2.1`。`architecture_master_prompt.md` 新增第 75 节。

## V2.11.5

### 基线交付五件套与汽车内饰高质量渲染

- 结果查看的“批量 CSV”现在在完成本地下载的同时，自动通过既有 `/export-axes-csv` 覆盖推送到项目交付数据；无论本地选择分文件或合并表，managed delivery 都保持稳定的“坐标系 CSV 文件夹 / 每坐标系一个 CSV”形状。
- 打基线前强制使用与当前模型/数模指纹一致的最新仿真结果，重新生成并覆盖 CSV 文件夹、NX AFU 脚本、甘特图 PNG、模型 JSON 四类交付；动画 HTML 优先复用已有交付文件，不重复生成。五类数据完整后才允许冻结基线。
- 若交付数据缺少动画 HTML，Hub 会先弹窗提示，然后复用现有动画导出 Job 自动后台生成并推送，完成后自动继续打基线；checked-in 下只开放这一窄的 delivery-only `baseline_prepare` 写入，不开放 ProjectSpec/UI 编辑。
- baseline 甘特图优先复用浏览器刚刚刷新、带 `saved_at` 证明的新缓存；浏览器刷新不可用时复用现有 Viewer legacy Gantt renderer 作为确定性 Server fallback。普通 MuJoCo Viewer 的甘特图 soft-dependency 规则保持不变。
- Server 新增共享 `axes_from_result_layout()` 投影，使基线 CSV/NX 从同一 `result_layout + latest simulation` 语义生成；不新增第二套曲线 schema、Tool、API、Job 或持久字段。
- VZ 高质量渲染新增 `automotive_interior` 场景预设，借鉴 three.js / Babylon.js / drei / model-viewer 的产品可视化思想，使用程序化摄影棚反射卡、roughness-aware IBL、specular occlusion、clearcoat、粗糙非金属轻量 grazing sheen、Perfect 5×5 PCF 与 neutral/PBR-neutral 风格 tone mapping；Fast 档继续保留 ACES + 3×3 PCF 以控制性能风险。
- 不引入 three.js/Babylon/React/model-viewer 等依赖；Client runtime/protocol 仍为 `0.3.9`，Viewer bundle schema/controller signature 仍为 `4`，VZ runtime/protocol 仍为 `0.3.2.1`。`architecture_master_prompt.md` 新增第 74 节，Server 正式版本提升为 `2.11.5`。

## V2.11.4

### 材质编辑器边界框选择与 MuJoCo Viewer 甘特图软依赖

- 工程师材质管理弹窗的双击选中效果从“修改选中数模着色/高光”改为独立 3D 边界框：PBR fragment shader 不再接收选中态颜色增强，选中只由已有 lineProgram/lineVao/lineBuffer 基于对象 bounds 绘制，不影响真实 base color、贴图、metallic、roughness、specular、clearcoat 等材质预览。
- MuJoCo Viewer 启动前的 Web 甘特图缓存预载改为 soft dependency：`refreshCache()` 异常会给出用户可见提示，但不会中断 local/admin 或轻量 Client Viewer 的后续启动。
- Viewer bundle 中甘特图缓存也改成非阻塞辅助资产：完整合法缓存照常携带并做 SHA-256；未生成、只有单文件或缓存损坏时记录 `reason/warning` 并省略，不再因甘特图问题让 scene + drives + trajectory + controller 主链路失败。
- 继续复用 V2.11.3.1 映射伴生 family、V2.11.3 latest-value 电机交互与运动学闭链常驻投影；Client runtime/protocol 仍为 `0.3.9`，Viewer bundle schema/controller signature 仍为 `4`，VZ runtime/protocol 仍为 `0.3.2.1`。
- `architecture_master_prompt.md` 新增第 73 节；ProjectSpec/L1/L2/L3/Session/Job/VZ 持久字段新增 `0`，业务 Tool/API/Job/artifact 新增 `0`。Server 正式版本提升为 `2.11.4`。

## V2.11.3.1

### Viewer 映射伴生驱动双向手动联动修复

- 修复电机控制模式中映射伴生驱动无法独立拖动的问题：伴生 slider 的人工输入不再作为独立 decoupled 值随后被 mapping 正向覆盖；任意伴生成员拖动都会先通过既有 mapping 反解得到 canonical root source 值，再从 root 正向投射整条 mapping family。
- 修复虚拟/无 joint 的源头驱动第一次拖动只动 slider、不动 STL/关节的问题：source/follower 映射链现在作为一个 manual-control family 同帧进入 decoupled，trajectory qpos 覆盖阶段会把 family 中所有具有真实 joint 的成员一起写入，因此无需先“碰一下伴生驱动”激活。
- source 与 follower 的 UI 值保持双向联动：拖动任意成员时，当前 slider 继续由 Tk 原生跟手，其他 mapping family slider 由 30 Hz 有界投射同步；松手后两者都回到 mapping 曲线的精确一致值。重新耦合、远端 decoupled 状态兼容也按整个 family 归一化。
- 复用既有 `_mapping_value()` / `_inverse_mapping_value()` 和 Viewer session-local `manual_values/decoupled`，只新增无持久化的 mapping topology/root/family helper；ProjectSpec/L1/L2/L3/Session/Job/VZ schema 新增字段 0，业务 Tool/API/Job/artifact 新增 0。
- Server 正式版本提升为 `2.11.3.1`。Client runtime/protocol 保持 `0.3.9`，Viewer bundle schema/controller signature 保持 `4`，VZ runtime/protocol 保持 `0.3.2.1`。`architecture_master_prompt.md` 新增第 72 节。

## V2.11.3

### Viewer 电机低延时解耦与运动学闭链常驻求解

- 定位 native Viewer 电机滑块卡顿的主要原因不是每个滑块 tick 向 Server 写变量：人类控制仍是 Viewer 进程内 session-local state；真正的热点是 `tk.Scale(command=...)` 高频回调里执行 mapping/整字典复制/全 label 刷新，以及主循环 60Hz 对全部 Scale 重复 `variable.set()`，造成 Tk 事件与重绘积压。
- 电机拖动改为 native-drag + latest-value coalescing：去掉 `tk.Scale(command=...)` 的逐 mouse-motion Python callback，Tk 原生更新 `DoubleVar`/knob，render loop 每帧最多采样一次 active drag 并消费最后值；复用既有 mapping/限幅/decouple 语义。已解耦/正在拖动的滑块不再被 render loop 回写，非解耦 follower 最多 30Hz 且仅在达到有效变化阈值时投射。
- 运动学 Viewer 在 `solver_mode=kinematic` 且存在 enabled closure 时，复用现有唯一 `kinematic_closure.py` DLS 位置级求解器。每个可见帧在 trajectory 插值和手工电机 qpos 覆盖之后、最终 `mj_forward()` 之前执行 closure projection，因此时间轴插值和电机解耦都不能再把机构临时变成开链。
- 闭链求解使用 `kinematics_only=True` 的 position-stage 刷新并对邻近帧 warm-start；大时间跳变重置 warm start。不可达/奇异时 fail-closed：有上一有效姿态则保持该完整闭链姿态并显示状态，首帧失败则显式报错；主动 drive 与 closure passive joint 冲突在 Viewer 启动时拒绝。
- 远端 Client 继续复用 server-supplied controller seam：bundle schema/controller signature 均保持 4，在 bundle 中附加 Server 权威 `kinematic_closure.py` 及 SHA-256 manifest 元数据，standalone controller 校验后加载。现有 Client V0.3.9 已安全抽取 schema-4 额外文件且调用签名不变，因此 Client runtime/protocol 不升级。
- `architecture_master_prompt.md` 新增第 71 节，固化 UI event coalescing、闭链 qpos post-write invariant、共享 solver、fail-closed、bundle 同源 helper 和 Client 升版判定规则。新增 ProjectSpec/L1/L2/L3/Session/Job/VZ 持久字段 0 个；新增业务 Tool/API/Job/artifact 0 个。

## V2.11.2

### V2.11.1 二次复核与低风险正确性加固

- 以 V2.11.1 为固定基线按“需求轴 / 工程轴”重新验收；V2_projec 数据根、376px 工程师 Explorer、120000 快速渲染、双场景坐标输入、用户场景看板等产品合同保持不变。
- 补齐结果采样旁路：native Viewer 结果曲线不再使用固定 241 点 `np.linspace`，而是读取 `simulation.timestep` 并使用整数 tick 严格时间网格；0..1 / 0.01 为 101 点，非网格 end 不强行插入。
- Viewer 单点结果的 d1/d2/d3 返回同 shape 零导数，避免 `numpy.gradient` 在只有一个时间点时异常。
- 修复 VZ `/api/models/<id>/export-modeling-info?...` GET 查询引用未初始化 `parsed` 导致 HTTP 400；`do_GET()` 统一只解析一次 URL 并复用 path/query。
- 活跃 VZ README 的快速渲染说明同步到单网格 120000 面；历史版本 checklist 仍保留历史值。
- `architecture_master_prompt.md` 新增第 70 节，吸收 mattpocock/skills 中适合本项目的需求/工程双轴复核、紧反馈回路、接口/seam 测试面、deep-module/locality、YAGNI 与最小纵向修补原则；不引入其运行时或第三方依赖。
- 新增 ProjectSpec/L1/L2/L3/Session/Job/VZ 持久字段 0 个；新增业务 Tool/API/Job/artifact 0 个。Server runtime/package/cache-buster/Viewer/动画导出统一为 `2.11.2`；Client 仍为 `0.3.9`，VZ runtime/protocol 仍为 `0.3.2.1`。

## V2.11.1

### 工程师 Explorer、用户场景看板与严格 0.01 s 结果采样

- 工程师左栏从 188px 扩为 376px，将项目/模型与一级/二级文件夹合并成一套 Hub 风格 Explorer；继续复用既有 VZ folder CRUD / model move API，仅新增浏览器瞬态折叠状态，不新增目录数据模型。
- 管理员数据地址设置去除重复常驻信息：默认层级、手工路径、选择/查找/保存保持在主行，Server 路径、候选数据根等移入折叠诊断；V2.11.0 的 `V2_projec` 解析和落盘合同不变。
- 快速渲染单 mesh 默认提高到 120000，前端/模型默认/fallback/动画导出 fallback 对齐；渲染完成不再在下方显示“渲染已生成”JSON UI。
- 场景坐标 UI 收敛为模型名称同行的硬点/H 点两个输入框；支持 `Point(x,y,z)`、英文逗号、中文逗号及中文括号，仍写入已有 `scene_coordinates.hard_point_mm` / `h_point_mm`。
- 用户站点按参考图重塑可见交互：取消可见控制画布，中央为动画 HTML + 可拖动水平分隔条 + 下方模型控制看板；右侧模型库用两行横向一级/二级文件夹切换和更大的正视缩略图。缩略图拖入场景继续复用 `control_graph.nodes`、`graphAlignmentForModel()` 和现有单模型控制详情；旧画布引擎保留为兼容代码但不渲染入口，本版不宣称完成新的多模型求解功能。
- 修复结果查看采样时间轴：结果时间只由 `start_time + n*timestep` 构成，不再把运动段边界或非网格 `end_time` 插入结果。步长 0.01 时相邻结果采样严格 0.01 s；优化器所需边界探针通过 `include_boundaries=True` 单独启用，不污染结果时间轴。
- 主 ProjectSpec/L1/L2/L3/Session/Job 新增权威字段 0 个，主业务 Tool/API/Job 新增 0 个。Server runtime/package/cache-buster/Viewer/动画导出统一为 `2.11.1`；Client 仍为 `0.3.9`，集成 VZ runtime/protocol 仍为 `0.3.2.1`。
- 二次复核补齐两个低风险旁路：native Viewer 结果曲线不再使用固定 241 点 `linspace`，而是读取仿真 `timestep` 并使用严格整数 tick；VZ `export-modeling-info` GET 查询统一复用已解析 URL，修复 `parsed` 未定义导致的 400。Viewer 单点结果的 d1/d2/d3 也改为零导数，避免 `numpy.gradient` 在只有一个时间点时异常。
- 活跃 VZ README 的快速渲染说明同步为单网格 120000 面；历史版本回归清单保持历史值，不作为当前合同。工程方法新增第 70 节：需求/工程双轴复核、先建立红绿反馈回路、deep-module/locality/seam/YAGNI 与最小纵向修补原则。

## V2.11.0

### 统一 V2_projec 数据根、VZ 两级模型库、场景参考坐标与用户控制画布

- 管理员账号管理窗新增项目数据地址设置：默认从 `Server` 向上两级定位 `V2_projec`，可调整 1..8 级或手动填写父目录/`V2_projec` 本身；保存前检测存在性和可写性，配置落在 `Server/.studio_config/storage_location.json`，重启后切换。环境变量 `MUJOCO_STUDIO_DATA` 继续拥有最高优先级。
- 主 Server 拉起集成 VZ 时把 `VZ_PROJECT_ROOT` 固定投射到 `<DATA_ROOT>/vz`，工程师/用户站点应用数据纳入同一 `V2_projec` 管理树；VZ 空库不再自动生成 demo 模型。
- 修复 Hub 已存在 VZ 模型时跳过资产刷新的缺口：每次推送都会 repair、比对 mesh manifest、删除失效/变化资产、补传缺失资产、overwrite modeling exchange 并验证全部 mesh 引用成功 relink；更新失败不会误删已有工程师模型。
- 工程师左侧模型库新增两级文件夹创建/重命名/删除与模型拖拽分类；删除非空文件夹 fail-closed。模型新增硬点/H 点三轴场景坐标，单位 mm。
- 用户“控制顺序”改为原生 DOM/SVG 持久化画布：右侧分类模型库提供正视图预览和拖入，节点支持拖动/resize、多选同移、source→target 连线、连线弯折、边/节点 Delete、左键框选、中键 pan、Ctrl+滚轮 zoom、显式自动排布，并在前后端双重拒绝环。原单模型控制逻辑、记忆位置、外部表格、步骤细节和右侧动画区域继续保留。
- 后续模型对齐按硬点优先、H 点回退计算 `transform_mm` 平移；单个参考点不足以唯一确定三维旋转，因此本版明确不生成虚构旋转。
- 主 ProjectSpec/L1/L2/L3/Session/Job 新增权威字段 0 个，主业务 Tool 新增 0 个。VZ 应用新增 `scene_coordinates`、`model_library.json`、`control_graph.json`。Server runtime/package/cache-buster/Viewer/动画导出统一为 `2.11.0`；Client 仍为 `0.3.9`，集成 VZ runtime/protocol 仍为 `0.3.2.1`。

## V2.10.6.1

### 框图闭链双端 Site 坐标同步

- 修复框图模式选择显式闭链/site 虚线后，紧凑属性视窗只修改 `endpoint_b.point_mm`、导致生成 XML 中另一端 site 仍为默认 `0 0 0` 的问题。
- 框图虚线属性中的单一坐标输入现在使用共享写入语义：一次修改同时把同一个三维 mm 坐标写入 `endpoint_a.point_mm` 与 `endpoint_b.point_mm`，两端使用独立数组副本，随后仍走既有 ProjectSpec 提交链；XML 生成器继续复用现有双 site 投射，不新增后端字段或第二套 closure 数据。
- 该共享语义只覆盖框图模式“选择一条闭链虚线后的紧凑属性输入”；原层级建模/root 闭链高级属性仍保留端点 A/B 独立编辑能力，避免破坏既有工程和导入模型的局部坐标语义。
- 紧凑属性标签从“site 坐标 mm”改为“闭链坐标”，输入提示明确单位仍为 mm 且同时作用于两端 site。
- 新增 ProjectSpec/L1/L2/L3/Session/Job 权威字段 0 个，新增业务 Tool/API/Job/artifact/tool-directory 0 个。Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一提升为 `2.10.6.1`；Client runtime 保持 `0.3.9`，Viewer bundle schema/controller signature 保持 4。

## V2.10.5

### 框图手工布局持久化、循环转闭链与驱动/从动语义自动化

- 数模库拖入画布创建层级时，框图名称默认取数模文件 basename（去掉 `.stl/.obj`），并复用 `uniqueName()` 处理重名。
- 手工建立父子线若会造成 `parent_id` 环路，不再报错后终止；该连接自动转成现有 `kinematic_closures[]` 闭链/site 虚线，避免在权威层级树中引入非法循环。
- 框图模式不再“首次进入自动排布”。保存过的 `ui.model.diagram.nodes` 始终优先；没有位置数据的旧项目只使用不落盘的稳定网格 fallback。签入/基线模型进入临时编辑时，会把权威项目 `core/ui_state.json` 复制到隔离 edit session，因此签入状态进入编辑也能立即看到上次手工布局。
- 在线段属性中新增运动副时，默认名称按 `父框图名称——>子框图名称` 生成；重复名继续使用既有 `uniqueName()` 后缀策略。
- 闭链从动运动副由闭链两端的树路径自动识别：路径内凡某条线段存在任一驱动绑定，则整条线段作为驱动侧排除；其余未绑定驱动线段中的非曲柄运动副自动写入 `solve_joint_ids`。手工修正改为直接点击闭环线段，而不是在节点上点运动副小按钮。
- 对绑定驱动的父子线新增 36×36 驱动标识，位置沿同一 Bezier 曲线跟随，尺寸严格为 18×18 运动副标识的 2 倍；驱动图标使用图1资源。滑动副继续强制使用图2资源。
- 闭链特殊色取消红色，限定在高饱和绿色、蓝色、紫色、橙色家族；普通闭链路径父子线仍为实线，只有显式 closure/site 线为虚线。
- 选中框图后，右侧数模可拖到整个下方属性视窗任意位置追加到该层级，不再要求命中“数模名称”区域；多个数模时 chip 字号/内边距约放大一倍。
- 新增 ProjectSpec/L1/L2/L3/Session/Job 权威字段 0 个，新增业务 Tool/API/Job/artifact/tool-directory 0 个。Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一提升为 `2.10.5`；Client runtime 保持 `0.3.9`，Viewer bundle schema/controller signature 保持 4。

## V2.10.4

### 框图 Delete 删除、左键框选与属性区密度修正

- 框图模式支持键盘 `Delete`：选中框图时复用既有层级删除语义，清理其运动副引用/端点闭链并把直接子层级提升到被删层级原父级；选中父子线时删除父子关系并把子层级提升为 root，选中闭链线时只删除对应 `kinematic_closures`。输入框/下拉框/contenteditable 获得焦点时不拦截 Delete，未激活端点相关连线继续遵守既有锁定合同。
- 删除顶部“＋ 层级”按钮，不新增第二套建层入口；框图层级继续通过右侧数模拖入画布创建。
- 框选由右键改为**左键拖动画布空白区域**；节点拖动、缩放、端口连线和边弯折保持更高交互优先级，中键平移保持不变，右键恢复浏览器常规上下文菜单。左键 lasso 完成后增加一次性 click suppression，避免 pointerup 后的 click 把刚形成的多选立即清空。
- 下方框图属性中，当层级包含多个数模时“数模 / 本体”区域改为非折叠的直接展开块；单/零数模仍保持紧凑折叠投射。框图浮动标题字号从 11px 提高到 13px。
- 父子线/闭链线属性视窗顶行从约 27px 压缩到 18px（约缩短 1/3），标题显式加粗；按钮/删除控件同步压缩，避免标题行反向撑高。
- 撤销成功 toast 的停留时间由 4800ms 缩短 1/4 至 3600ms，只作用于撤销反馈，不改变错误提示和其它一般通知的默认时长。
- 新增持久 ProjectSpec/L1/L2/L3/Session/Job 字段 0 个，新增业务 Tool/API/Job/artifact/tool-directory 0 个；仅新增运行时瞬时 `hierarchyDiagramSuppressPaneClick` 布尔标记。Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一提升为 `2.10.4`；Client runtime 保持 `0.3.9`，Viewer bundle schema/controller signature 保持 4。

## V2.10.3

### 框图交互精修、交付按类型覆盖与 CSV 文件夹交付物

- 修正旋转副/滑动副图标资源映射；框图缩略图新增横向、纵向及自由宽高缩放，预览 canvas 始终铺满缩略图边框，浮动标题字号提升到 11px。
- 闭链颜色切换为红/黄/橙/洋红等高饱和鲜艳调色板。只有显式 `kinematic_closures` site 连线使用虚线；参与同一闭环的普通父子树路径只继承同色，继续保持实线。
- 右键按住拖动新增矩形框选，多选节点可整体拖动；框图节点坐标不再受左上角原点夹取。下方属性视窗与右侧数模库新增可拖分隔条，默认数模库宽度约缩小 1/3。
- 右侧数模库除拖到画布建立层级外，也可拖入当前框图属性窗的“数模 / 本体”折叠区，为该既有层级追加多个 mesh；仍复用原 `addMeshFromLibrary` 与 ProjectSpec mesh 列表。
- 修复层级建模/框图建模以中等频率切换时偶发回撤：`ui.set` 请求统一进入单一 `uiCommitChain`，按用户动作顺序串行提交，并增加运行时 UI revision/ack fence，阻止后台旧 `/state` 镜像覆盖尚未确认的新视图；前端镜像仍即时切换。
- 交付覆盖键从“同名文件”提升为“受管交付类型”。`_record_delivery_output()` 同类型只允许一个物理文件或文件夹；mutable 项目读取交付目录时会对可明确分类的旧重复项选择最新修改项并清理其它同类型副本；创建 baseline 前会先在 source 上按类型去重，冻结后的 baseline 目录只读不自改。
- 在原四类交付物上新增第五类 `axes_csv_folder`：坐标系“分别导出”时，以 staging + replace 方式覆盖保存一个交付文件夹，内部每个坐标系一个 CSV；复用既有 `/export-axes-csv` 与 `/delivery-folder.zip`，未新增平行业务导出 Tool/Job。
- 新增持久状态仅为 UI-only `ui.model.diagram.layout={property_height,library_width}`；多选集合保持瞬时 `Set`。新增 ProjectSpec/L1/L2/L3/Session/Job 权威字段 0 个，新增业务 Tool/Job/tool-directory 0 个。
- Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一提升为 `2.10.3`。Client runtime 保持 `0.3.9`，Viewer bundle schema 4 / controller signature 4 不变。

## V2.10.2

### Hub 关键数据即时显示与轻量框图交互

- 修复基线派生工作项目在首次签入前 Hub 关键数据气泡为空的问题：完整项目目录水合在项目尚无本地 archive 时直接投射当前权威 `_project_preview(...).archive_fields`；一旦已有 archive，继续按最新 archive 展示，避免改变既有历史语义。
- 框图模式下方属性窗压缩为最高 205px 且无选择时为空。点击框图只显示名称、层级颜色、激活、本体数模；本体数模选择移入折叠区并默认第一个 mesh。点击父子线只显示运动副信息和闭链复选框。
- 框图本体改为 thumbnail，标题作为随 thumbnail 移动的浮动标签；新增上下连接口，与左右接口组成四向 handle。连线按节点相对位置自适应选择端口并使用 cubic Bezier，用户可拖线调整 bend 而保持两端固定。
- 新增中键拖动画布与 Ctrl+滚轮光标中心缩放，唯一新增持久 UI 状态为 `ui.model.diagram.viewport={pan_x,pan_y,zoom}`；不新增任何模型权威字段。
- 运动副类型在线段附近使用紧凑图标显示；闭链复选框移出线段。每个启用 closure 由两端点的树路径派生整套闭链，闭链所有线段同色虚线，不同闭链使用不同稳定调色板颜色。
- 保留 V2.10.1 inactive 锁定与尺寸感知自动排布；新增 ProjectSpec/L1/L2/L3/Session/Job 字段 0 个，新增业务 Tool/API/Job/artifact/tool-directory 0 个。
- Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一提升为 `2.10.2`。Client runtime 保持 `0.3.9`，Viewer bundle schema 4 / controller signature 4 不变。

## V2.10.1

### 框图锁定一致性与复杂层级排布修复

- 补齐 inactive 框图的画布锁定旁路：禁用层级不能再通过双击标题、本体数模下拉、数模拖入父节点、父子边闭链复选框或连线弯折 handle 改动框图/关系；节点和连线仍可被选中查看，重新激活入口不受影响。
- “从画布选择从动运动副”只投射 active 层级的非 crank 运动副，点击时再次校验 joint 所属层级；closure 端点下拉与原层级闭链设置复用同一 active-layer eligibility，已失活的当前端点以禁用项保留显示而不静默改绑。
- 自动排布改为尺寸感知的父子子树 packing：列间距按上一深度最大框图宽度推进，垂直位置按真实节点高度和子树占用计算；支持 154–420 × 116–340 的现有可调尺寸，不再依赖固定 286/184 网格，从而避免复杂多层模型自动排布后的节点重叠。
- 沿用 `layers[].parent_id / joints[] / kinematic_closures[] / ui.model.diagram.*` 和既有 `ui.set`/项目提交链；新增 ProjectSpec/L1/L2/L3/Session/Job 字段 0 个，新增业务 Tool/API/Job/artifact/tool-directory 0 个。
- Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一提升为 `2.10.1`。Client runtime 保持 `0.3.9`，Viewer bundle schema 4 / controller signature 4 不变。

## V2.10.0

### 层级框图建模

- 模型 Editor 新增“层级建模 ↔ 框图建模”双视图。框图与原层级树共同投射 `layers[].parent_id / joints[] / kinematic_closures[]`，没有新增第二份模型权威状态。
- 框图支持拖动位置、调整显示大小、双击标题重命名、自动排布，以及父子连线/闭链连线。父子箭头继续表示子层级的运动副属性；父子闭链以同一边的闭链线型投射，非父子闭链使用独立虚线。
- 右侧数模库可直接拖到画布：点选父框图后拖入会新建其子层级；直接落到某框图也以该框图为父层级；点击画布空白清除选择后拖入则新建顶层层级。每个框图默认使用该层级第一个 mesh 作为本体数模，并复用现有缩略图 WebGL 渲染器显示正视图；本体预览选择只属于 `ui.model.diagram.*`。
- 闭链属性支持从画布点击运动副写入既有 `solve_joint_ids`；禁用层级会灰显并锁定节点/相关连线，存在子层级时会询问是否同步禁用子层级。
- 新增 ProjectSpec/L1/L2/L3/Job 字段 0 个；新增业务 Tool/API/Job/artifact/tool-directory 0 个。框图位置/尺寸/预览数模/连线弯折量统一复用 `ui.set` 保存。
- Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一提升为 `2.10.0`。Client runtime 保持 `0.3.9`，Viewer bundle schema 4 / controller signature 4 不变。

## V2.9.8

### VZ Studio V0.3.2.1 集成

- MuJoCoHub 顶部新增“工程师界面”，跳转到集成后的 VZ 工程师界面。
- Hub 模型属性新增“推送模型”滑动开关；开启后模型发布到 VZ 用户模型库，关闭后仅取消用户侧可见性，不删除工程师侧模型及其驱动、材质和渲染设置。
- VZ 工程师界面移除层级建模以及生成 MJCF、MuJoCo 仿真、数模资产管理、修复失效引用、模型文件输入、导入/导出建模信息等集成后冗余入口；驱动设置替代原层级建模工作区。
- 工程师重命名模型时保留 Hub 原模型名称，并在模型列表中继续显示原名称；高质量渲染单网格最大面数默认值为 `120000`。
- Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一提升为 `2.9.8`。Client runtime 保持 `0.3.9`，Viewer bundle schema 4 / controller signature 4 不变。

## V2.9.7.1

### 回收站多选与永久删除

- Hub 回收站新增复选框、当前列表全选与“永久删除已选”按钮；选中状态只存在于当前页面瞬时 `Set`，搜索过滤会清理不可见选择，避免误删隐藏条目。
- 新增 `DELETE /api/recycle-bin/{trash_id}`，继续复用 `.trash/projects` 与 `ProjectStore` 回收站生命周期；只允许管理员/工程师。损坏或非法条目 fail-closed，不执行永久删除。
- 批量删除前只确认一次，随后逐条调用现有回收站资源删除；单项失败不会掩盖其它结果，前端会刷新权威列表并报告成功/失败数量。

### 签入默认存档 / 前进按钮

- Hub 与独立 Editor 的手动签入不再询问“是否需要存档”；每次权威 `check_in` 均通过既有 Kernel / `ProjectStore.archive()` 链生成一个存档版本。可继续填写本次签入存档日志，签入关闭分页确认仍保留。
- `ProjectLifecycleRequest.archive` 为旧调用方保留兼容字段，默认改为 `true`；V2.9.7.1 Server 对 `check_in` 强制 `archive_check_in=True`，因此旧前端即使显式发送 `archive=false` 也不会绕过存档。自动签入和管理员 force-check-in 的安全存档语义不变，check-out 仍不创建版本。
- 顶部 redo 按钮用户可见文本从“重做”改为“前进”；内部 `/redo`、Ctrl+Y 与 Ctrl+Shift+Z 行为保持不变。

### Architecture / Client / Version

- 新增 ProjectSpec/L1/L2/L3/Job 权威字段：0；新增业务 Tool/Job/artifact/tool-directory：0。新增 API 方法 1 个（现有 recycle-bin resource 的 DELETE）。
- `architecture_master_prompt.md` 新增 V2.9.7.1 长期合同，并覆盖 V2.9.6“手动签入可选择不存档”的旧规范。
- Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一提升为 `2.9.7.1`。Client runtime 保持 `0.3.9`，Viewer bundle schema 4 / controller signature 4 均未变化；正式包继续同时包含 `Client/` 与 `Server/`。

## V2.9.7

### Hub 文件夹与全层级搜索

- 项目列表标题新增一键“全部折叠 / 全部展开”按钮，复用同一 `hubCollapsedModelTypes` 瞬时状态；Hub 初次载入时所有含子目录的文件夹默认折叠。
- Hub 搜索在输入文字时不再被当前分类一层过滤截断，改为扫描完整项目集合，并匹配名称、描述、标签、数模引用和完整分类路径；搜索结果显示来源文件夹，清空搜索后恢复当前文件夹直接列表。
- 模型 JSON 导入与完整压缩包导入都显式传递当前 Hub 文件夹作为 `target_category`；Server 只接受已有分类（根 `None` 除外），不会静默创建新模型类型。

### 完整压缩包导入 / 导出

- 新增 `mujoco_studio_project_bundle` v1：`manifest.json` + `model/model.json` + `properties/model_assets/` + `properties/delivery/` + `properties/archive_logs/`，inventory 使用相对路径、大小和 SHA-256 验证内容完整性。
- 新增 `GET /api/projects/{id}/export-bundle` 与 `POST /api/projects/import-bundle`；仅工程师/管理员可用，签出模型须先签入。
- checked-in 模型导出公共数模时，先复制到隔离临时 snapshot 并对源/目标 inventory/hash 做一致性检查，再压缩临时副本；不会在公共源资产库写 manifest、中间文件或 ZIP。
- 导入时为当前目标分类生成不冲突的新公共 `@model_assets/<category>/<folder>`，包括根 `None`，并通过现有 `project.asset_selection` command bus 绑定到新模型。失败会清理本次创建的项目与公共资产目录。
- baseline 导出携带自己的私有冻结数模与交付数据；baseline 本体继续没有普通 versions 历史。baseline 导入先恢复 immutable baseline，再生成工作副本并把同一数模另行注入目标公共资产库。
- checked-in 包恢复存档时重写历史快照的 project id/category/mesh_root，最多保留既有 20 条；旧 baseline sidecar 链接只保留 provenance，不让导入后的 Hub 指向源服务器不存在的 baseline。
- ZIP 解包拒绝路径穿越、盘符绝对路径、符号链接、重复路径、inventory/hash 不一致，并设置文件数/单文件/总展开大小以及 manifest/model JSON 上限。

### 层级建模交互

- 每次重新进入 Editor，数模区和驱动区都从双列开始；用户本次会话可切单列，但不再把该选择跨编辑模式持久化。
- “范围”未勾选时隐藏范围数值输入；勾选后才显示既有 `joint.range`。反向箭头改为直角矩形，并在 reverse=true 时把轴/滑动轴输入投射成逐分量负值；canonical 存储轴不被同时翻转，避免与求解/XML 的 reverse 语义双重取负。
- 当前层级“总体适配”改名“自适应”；删除模型 A / 模型 B 预留分页，原位置改为“全部数模自适应”，按层级复用原 `/meshes/adaptive` 同族适配逻辑。

### Client / Architecture / Version

- `architecture_master_prompt.md` 新增长期 V2.9.7 合同：完整包结构、baseline/checked-in 分流、当前文件夹导入、Hub 深层搜索、瞬时双列/reverse 投射，以及后续正式包必须同时含 Client/Server 的发布门禁。
- 正式整合包从本版起同时包含 `Client/` 与 `Server/`。Client 继续使用 V0.3.9 / Viewer controller signature 4；本次审计确认 Server Viewer bundle schema 仍为 4，并修正 Client health 中 `supported_bundle_schemas` 的过时投射为 `[1,2,3,4]`，不改变 runtime/protocol。
- Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一为 `2.9.7`。新增持久 ProjectSpec/L1/L2/L3/Session/Job 字段：0；新增业务 Tool/Job/artifact/tool-directory：0；新增 domain helper 1 个、API 方法 2 个。

## V2.9.6.6

### Windows Viewer Unicode 路径与 Hub 拖拽性能

- 后台生成 XML 统一复用现有 Unicode/VFS MuJoCo loader；本机 Viewer 工作区优先传递相对 scene/drives/Gantt/trajectory 路径，避免中文/UTF-8 项目目录把绝对路径直接交给 Windows 原生 parser。
- 项目重分类的 delivery tree 同盘优先目录 rename，失败再回退原 verified copy/hash；Hub 拖拽分类与名称保存使用即时投射 + authoritative 响应合并，不同步全量刷新目录。
- Client runtime/protocol 保持 V0.3.9。

## V2.9.6.5

### 表达式除法与测距伪变量

- 修复 `40/tran*tz` 等 `/` 算术除法场景对普通自定义变量的识别，同时保留 `drive/duration1` 等 slash-qualified 兼容别名。
- `ProjectSpec` 及 V21.5 / modeling-exchange 导入边界清除与测距对同名的历史伪变量，真实自定义变量继续保留。

## V2.9.6.4

### 外部 CSV 驱动 / 模型 JSON 互通

- 新增 V21.5 兼容 external motion CSV 导入，统一内嵌时间-位置点表；速度/加速度输入按 V21.5 梯形积分语义转换。
- V21.5 ↔ Studio 完整模型 JSON 双向保留 `external_csv` 点表和来源元数据，运行时不依赖原 CSV 路径。

## V2.9.6.2

### 快速连续编辑竞态修复

- 修复短时间快速操作后最后几步偶发消失、视觉上类似“自动撤销”的问题。根因不是 400ms 防抖丢弃操作，而是 900ms 后台事件轮询可能在 editor clean 时启动 `/state` mirror；请求飞行期间用户产生新编辑后，旧实现仍会在 mirror 返回时无条件覆盖 `state.project`。
- 新增 authoritative project fence：异步 mirror 写回前同时校验 `projectId / projectLoadRevision / editRevision / dirty`。请求期间发生任意本地编辑、项目切换或重载时，迟到快照直接丢弃。
- 保留 400ms 连续交互防抖和串行 `saveChain`，不以高频 PUT 规避竞态。旧保存响应继续受 `editRevision` 保护。
- 补齐新增层级、驱动、测距对、自定义变量、优化变量、结果坐标系等直接按钮的 `scheduleInteractionCommit()`，避免“已 dirty 但最后一次没有启动自动提交计时器”。
- 大模型配置保存后的 `/state` mirror 同样复用 revision fence，防止该异步读取覆盖并行发生的模型编辑。

### Architecture / Version

- Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一为 `2.9.6.2`。Client runtime 与 Viewer 协议保持 `0.3.9` / signature 4，无 Client 代码协议升级。
- 无 ProjectSpec schema 迁移、无新增业务 API/Tool/Job/artifact type；只修正前端编辑一致性和自动提交覆盖面。

## V2.9.6.1

### Linux / 远程 Client Viewer 甘特图修复

- 修复 Linux/远程部署中动画 HTML 甘特图正确、但本地 MuJoCo Viewer 仍显示旧/兼容甘特图的问题。根因是 V2.9.6 的 Viewer bundle 未携带 Web 甘特图弹窗生成的 `latest_gantt.png` / `latest_gantt.json`，Client runner 也没有向独立 Viewer controller 传入甘特图缓存路径。
- Viewer bundle 继续使用 schema 4，但 controller signature 提升为 4；bundle 可携带权威甘特图 PNG/JSON 快照及 SHA-256，Client V0.3.9 校验后显式传入 `gantt_cache_path`。
- Server Viewer 启动最低 Client runtime 提升为 V0.3.9，旧 Client 明确提示升级，禁止“Viewer 启动成功但静默忽略甘特图参数”。
- Native Viewer 不再在启动时永久绑定 fallback；每次缓存轮询都重新优先选择正式 `gantt_cache`，正式缓存后出现时自动切换。变化签名同时覆盖 PNG 与 JSON 的路径/mtime/size/inode，PNG-only 更新也会重载。
- Viewer 日志新增 `MUJOCO_STUDIO_GANTT_CACHE` 来源/路径/saved_at 诊断；动画 HTML 仍读取同一工程权威缓存，因此两条显示链统一到同一真相源。

### Architecture / Version

- Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一为 `2.9.6.1`。
- Client runtime 更新为 `0.3.9`，WindowsFix 分发标签保持 `V0.3.9`；Viewer 启动最低兼容 Client 为 `0.3.9`。
- 无 ProjectSpec schema 迁移、无新增业务 Tool/Job/artifact/API；Viewer bundle schema 保持 4，仅 controller signature 从 3 提升为 4。

## V2.9.6

### 签入与存档语义
- 手动签入在确认关闭分页后，新增“本次是否需要存档”选择；选择“是”才生成一个 `存档版本` 并可填写存档日志，选择“否”只完成权威签入，不写 versions 快照。
- idle / logout / restart recovery 等自动签入继续生成安全存档；管理员 `force-check-in` 也保留安全存档。签出动作不再自动创建 lifecycle 版本，避免无意义占用存档容量。
- 新写入统一使用 archive/baseline 两类投射；旧 `manual/check_in/check_out/edit_*` 历史 sidecar 仍可读取，但前端统一显示为“存档版本”，不再出现“签入版本”。

### 基线进入原模型存档日志
- 打基线仍创建独立冻结 baseline 项目，数模/交付/工件冻结语义不变。
- baseline 成功后，在来源模型 `versions/` 中追加一条 `基线版本` 历史记录，记录 `baseline_project_id / baseline_name` 与基线日志；该记录保存来源模型当时快照，不改来源 ProjectSpec，也不会额外生成普通存档。
- 统一存档日志继续复用既有 `MAX_ARCHIVE_VERSIONS` / `MUJOCO_STUDIO_MAX_VERSIONS`，默认最多 20 条，存档版本与基线版本共用这一总量上限。
- Hub 中基线版本标题使用红色字体，便于与普通存档版本区分。

### 删除单个存档
- 扩展既有版本资源：新增 `DELETE /api/projects/{project_id}/versions/{version_id}`，仅删除指定版本 JSON 与 `.meta.json`，不修改当前模型。
- 每条版本卡在“切出为独立模型”左侧增加“删除存档”。删除基线版本记录只删除来源模型存档日志中的基线快照，不删除实际 baseline 项目。

### Architecture / Version
- 新增 ProjectSpec / L1 / L2 / L3 / Job 权威字段：0；新增业务 Tool / Job / artifact type / 工具目录：0。继续复用 `project.lifecycle`、Kernel 一次性签入归档策略、`ProjectStore.archive()` / `_prune_versions()` 与既有 `/versions` 资源。
- 新增 API：1 个版本删除方法；`ProjectLifecycleRequest.archive` 是一次请求级瞬时选择，不进入项目权威状态。
- Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一更新为 `2.9.6`；Client runtime 保持 `0.3.8`，WindowsFix 分发标签保持 `V0.3.9`，最低兼容 Client 协议保持 `0.3.6`。

## V2.9.5.2

### Hub 第一行 / Unity 风格微调
- 桌面 Hub 的 `hubTopControls` 从 `<main>` 第二行物理移动进顶部 `.sidebar`，与 `MuJoCoHub` 品牌标题处于同一条 52px 工具栏；原独立 Webhook/账号控制行不再占用 Hub 纵向空间。窄屏保留响应式换行兜底。
- Hub 范围内按钮、工具栏、面板做轻量 Unity Editor 风格收敛：2–3px 小圆角、克制渐变/边框、取消按钮 hover 上浮和缩放；不引入外部 UI 库，也不改其它编辑页视觉语义。
- 模型属性生命周期按钮文案由“复制版本 / 删除项目”缩短为“复制 / 删除”；继续复用原 `hub-copy-version` / `hub-delete-project` handler 与既有权限。

### Architecture / Version
- 新增 ProjectSpec / L1 / L2 / L3 / Job 权威字段：0；新增业务 Tool/API/Job/artifact/工具目录：0。继续复用 `wecomWebhookEnabled`、`wecomWebhookUrl`、账号显隐和 Hub lifecycle actions。
- Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一更新为 `2.9.5.2`；Client runtime 保持 `0.3.8`，WindowsFix 分发标签保持 `V0.3.9`，最低兼容 Client 协议保持 `0.3.6`。
- 验证：`node --check frontend/app.js`、Python `compileall` 与定向 DOM/CSS/版本门禁通过；正式 `self_check.py` 在当前打包环境缺少声明依赖 `passlib`，使用项目外临时 PBKDF2 兼容 shim 后 6/6 通过，shim 不进入交付包。容器 headless Chromium 因 DBus/zygote 环境限制超时，因此不把截图预览声明为浏览器 E2E。

## V2.9.5.1

### Hub / 生命周期 / 下载
- 签出标记恢复为历史版本的 `📩🧑‍💻`，由共享 `projectNameMarker()` 同时作用于 Hub 列表、模型属性和独立 Editor 标题；删除模型页左上角“跳转 Hub”按钮。
- Windows 与 Linux 的用户下载/导出统一直接交给浏览器默认下载目录，不再调用 `showSaveFilePicker()` / `showDirectoryPicker()`；批量数模、批量交付与分别导出 CSV 同步收敛。服务器管理性质的资产/目录绑定不受影响。
- 修复交付动画 HTML 已生成/下载后在结果页重新加载时报 `deliveryOnly is not defined`；重新加载成功直接投射“已从交付数据加载动画”。

### Hub 属性 / 页面密度
- 交付数据后缀输入单独一行，自动填入/批量下载/清空三动作位于下一行；交付目录小字只显示保存时间，不再附带路径与大小。
- 数模资产文件区四个按钮再缩小 2px，绑定到当前模型按钮宽度约增加 100%；回收站从模型类型树拆出并固定在项目列表最下方顶格显示。
- 企微 Webhook 增加滑动开关，只有开启时才显示并使用 URL；Webhook 与账号管理整体移动到 MuJoCoHub 标题同行，Hub 模式取消原第二行 topbar 占位。旧浏览器若已有保存 URL，会迁移为开启。
- 存档日志第一行只显示放大 2px 的关键数据内容，不显示“关键数据”字样；版本标签和时间移至第二行并保持原字号。

### 复制资产语义 / Architecture / Version
- 普通复制模型与存档切出不再新建公共数模资产文件夹，直接复用来源 `@model_assets` 引用；只有 baseline“使用版本”仍要求命名新资产文件夹并通过既有 `/fork` 克隆到公共资产库。
- 新增 ProjectSpec/L1/L2/L3 权威字段：0；新增业务 Tool/API/Job/artifact/工具目录：0。仅新增浏览器本地 Webhook enabled 开关；`ProjectCloneRequest.mesh_folder_name` 为兼容保留但 copy-version 不消费。
- Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一更新为 `2.9.5.1`；Client runtime 保持 `0.3.8`，WindowsFix 分发标签保持 `V0.3.9`，最低兼容 Client 协议保持 `0.3.6`。

## V2.9.5

### 存档容量 / 生命周期
- 普通模型存档默认硬上限由 10 调整为 20；手动“版本存档”和签入/签出生命周期版本继续共用同一个 `ProjectStore.archive()` / `_prune_versions()` 链，因此 20 是合计总量而不是两套配额。
- 创建基线后不再把源普通模型额外裁剪到 3 个历史版本；基线本体仍是冻结快照，不产生自己的普通存档链。旧项目无需 schema 迁移，已被旧版本删除的历史不会伪造恢复。

### Hub 紧凑视窗
- 桌面端属性检视器最大宽度收敛到模型属性列约 150%；模型属性的三个入口与下方关键数据容器强制同宽。
- 交付数据删除重复的 HTML/PY/JSON/PNG 快捷卡，仅保留真实目录；后缀、自动填入、批量下载和清空集中到顶部控制行，目录文字缩小一级。
- 数模资产下拉移动到检视器标题栏右上，按钮字号缩小 2px；数模版本路径与标题同一行，版本卡压成两行，文件名/大小同一行，下载和删除改为小图标按钮。
- 存档版本卡进一步纵向压缩：切出按钮和版本名同一行，关键数据单行省略，存档日志最多显示两行；日志原文仍完整保存。

### Architecture / Version
- 新增 ProjectSpec / L1 / L2 / L3 权威字段：0；新增业务 Tool/API/Job/工件/工具目录：0。继续复用现有生命周期 Tool、`ProjectStore` 存档链、health 上限投射与 Hub 属性检视器。
- Server runtime / package version 严格更新为 `2.9.5`；Client runtime 保持 `0.3.8`，WindowsFix 分发标签保持 `V0.3.9`，最低兼容 Client 协议保持 `0.3.6`。
- 验证：定向存档探针创建 25 个混合 manual/check_in/check_out 版本后保留最新 20、裁掉最早 5 个；baseline 静态门禁确认不再存在源模型 keep=3 裁剪；`node --check frontend/app.js`、Python `compileall` 通过。打包运行时缺少 `passlib`，使用项目外临时 PBKDF2 兼容 shim 后 `scripts/self_check.py` 6/6 通过（shim 未写入交付包）。

## V2.9.4

### Linux 下载 / 交付数据
- Linux 部署服务在所有用户侧导出入口统一使用浏览器直接下载，不再调用文件/目录路径选择器；覆盖项目 JSON、建模 JSON、单/批量交付文件、CSV、脚本、动画等现有下载链。服务端管理性质的目录绑定仍保持原语义，不把“服务器目录”误当成浏览器下载目标。
- “批量导出 CSV”点击后提供两种模式：每个坐标系单独一个 CSV；或全部坐标系合并为一个长表 CSV（`coordinate_system,time_s,curve,value,unit`）。
- “生成 NX AFU 脚本”改为“导出 NX AFU 脚本”；生成后自动覆盖同类型旧交付、写入交付数据并立即下载。动画页删除单独“保存交付”动作，“一键导出动画 HTML”同样改为生成即交付即下载，重新加载动画只读取交付数据中的最新动画 HTML。
- 继续复用既有 delivery manifest 的同类型淘汰机制：动画 HTML、NX AFU 脚本、甘特图 PNG、模型 JSON 四类均只保留各自最新版本。

### Hub 生命周期 / 复制
- 修复复制模型弹窗中的模型名称未生效：`copy-version` 现在接收并使用显式 `model_name`；若目标分类已有同名模型则返回 409，不再静默改成 `*_副本`。
- 新增模型回收站：用户删除不再立即物理删除，而是移动到数据根 `.trash/projects`。管理员和工程师可见并可恢复，默认保留 7 天（`MUJOCO_STUDIO_TRASH_RETENTION_DAYS`，最小 1 天）；过期项目在读取回收站时清理。
- 回收站记录原项目路径、删除/过期时间与外部交付路径。恢复时若原项目目录、项目 ID 或原外部交付目标已存在，明确拒绝并不覆盖；损坏元数据 fail-closed。内部创建/复制失败的事务回滚继续使用 `ProjectStore.delete()` 物理清理，不把半成品送入回收站。
- 删除整个模型类型并勾选同时删除模型时，同样逐模型进入回收站；删除类型公共数模库前会把各模型当前 `@model_assets` 选中版本冻结到项目私有 snapshot。外部交付绑定根也写入 trash metadata，恢复时可重建原绑定；若同名类型已经绑定到不同目录则冲突拒绝。

### 自适应 / UI
- 层级数模“总体适配”继续复用既有同族匹配；对附属后缀 `.001`–`.009` 自动设置 `opacity=0`，`.010` 及之后不视为附属，透明度保持原值。已经存在于层级中的同族附属数模也会被归零。
- “自适应添加驱动”改为按当前层级中未绑定关节生成驱动，驱动名称严格等于关节名称并写入对应 `joint_id`；空名、同批重复名或与其它关节已绑定同名驱动冲突时拒绝，避免错误绑定。
- 模型分页生命周期标题改用与 Hub 一致的图标（签入锁 / 签出解锁），不再显示 `【签入/签出】`；签入模型 temporary 编辑模式的灰色蒙版加深。

### Architecture / Version
- 新增 ProjectSpec / L1 / L2 / L3 权威字段：0；新增业务 Tool 目录：0。继续复用现有 `ProjectStore`、`sim.export_animation_html` Job、NX AFU 导出、交付 manifest、数模 adaptive 与项目保存链。
- 新增外部文件生命周期能力为回收站 metadata/API；新增前端能力投射 `direct_downloads` 与回收站列表均不属于 ProjectSpec 权威状态。新增 API：回收站列表、恢复；用户删除 API 语义由 hard delete 改为 trash move。
- Server runtime / package version 严格更新为 `2.9.4`；Client runtime 保持 `0.3.8`，WindowsFix 分发标签保持 `V0.3.9`，最低兼容 Client 协议保持 `0.3.6`。

## V2.9.3

### 驱动时序表达式解析
- 修复 `resolve_schedule()` 将运动段内部 `ExpressionError` 全部吞掉、最终统一报为 `unresolved or cyclic drive segments` 的问题。未解析运动段现在保留实际失败原因；例如 `4.78+tt-0.2+0.06` 在 `tt` 不存在时明确报告 `unknown variable: tt`。
- 对尚未生成的规范斜杠变量、历史点号变量或 Slash/CamelCase 兼容别名，失败信息会标明具体 `unresolved drive dependency`；真正依赖问题仍 fail-closed，不通过猜值规避校验。
- 继续保留 V2.3.8.2.1 的“先发布 duration/speed/stroke、再解 start boundary”分阶段语义，确保运动段可以引用自身 `durationN` 而不被误判。

### Preview / 当前变量值
- 新增领域内部 `ScheduleResolutionError`（仅异常载荷，不是 ProjectSpec/业务 Schema），携带安全的 `partial_variables` 与 `partial_schedule`。`/preview` 捕获该异常后继续投射已确定值和已完成段，同时保留 `schedule_error`。
- 因此某一段仅起始时间表达式失败时，该段已确定的 `duration/speed/stroke` 不再随整个 schedule 一起清空；`starttime/endtime` 仍保持未解析，校验、XML、仿真、Viewer 不会使用不完整段。

### Architecture / Version
- 新增 ProjectSpec / L1 / L2 / L3 权威字段：0；新增业务 Tool/API/Job/工件类型/工具目录：0。复用 `resolve_schedule()`、`project.validate`、`motion.compute_schedule`、XML/仿真/Viewer 既有链路。
- Server runtime / package version 严格更新为 `2.9.3`；Client runtime 保持 `0.3.8`，WindowsFix 分发标签保持 `V0.3.9`。

## V2.9.2.1

### Hub 项目类型树
- 修复历史 `未分类` / 内部 `None` 兼容目录被重新投影为可见模型类型、导致“删除后又出现”的问题。启动时会清理模型类型 metadata 中的 `None/未分类` 别名，并在无冲突时把历史 `projects/未分类/<project>` 合并到内部 `projects/None/<project>`；`model_type_tree()` 从此只返回真实模型类型。该修复对 Windows / Linux 使用同一逻辑。
- 文件夹行控制顺序改为“最左拖拽把手 → 折叠/展开 → 文件夹名 → 数量”，满足拖拽区最左、折叠键紧邻其右侧。
- 恢复文件夹层级拖拽，继续复用既有 `/api/model-types/{category}/move` + `ProjectStore.move_category()`：目标行上边缘为同层前插，中部为移入目标文件夹，下边缘为同层后插；拖到根“项目”提升为顶层。drop 后仍必须确认，确认后才写入并整页刷新；禁止移动到自身或其子树。

### 签入状态同步
- 修复从独立模型分页签入后 Hub 仍显示“签出”、必须手工刷新才正确的问题。Editor 收到 lifecycle 成功响应后立即更新本地 summary、失效 Hub preview cache，并向 opener Hub 发送生命周期更新；若 opener 关系丢失，再使用一次性同源 `localStorage` 事件通知其它 Hub 分页。
- Hub 收到通知后先即时投射返回状态，再调用现有 `loadProjects()` / preview 读取服务端权威数据，避免 10 分钟页面缓存继续展示旧签出状态。

### Architecture / Version
- 新增 ProjectSpec / L1 / L2 / L3 权威字段：0；新增业务 Tool：0；新增 API：0；新增 Job：0。仅扩展 `ProjectStore` 初始化兼容迁移、既有模型类型 move 前端语义和现有 Hub 生命周期缓存失效链路。
- 新增前端仅页面瞬时状态：`activeModelTypeDrag`；跨分页 `PROJECT_LIFECYCLE_SYNC_KEY` 只作为一次性通知键，写入后立即删除，不构成第二业务状态池。
- Server runtime / package version 更新为 `2.9.2.1`；Client runtime 保持 `0.3.8`，WindowsFix 分发标签保持 `V0.3.9`。

## V2.9.2

### Hub / 项目列表
- Hub 左侧“模型类型”改名为“项目列表”，桌面布局有效宽度增加 20%（155→186px；1300px 以下 150→180px）。`None/未分类` 不再作为用户可见文件夹：内部兼容哨兵 `None` 继续存在，但在 Hub 投影为根“项目”文件夹；点击根目录只显示未分类模型，点击具体模型类型只显示该类型模型。
- 模型类型行继续使用“名称 / 数量 / 折叠展开 / 最右侧拖拽把手”结构。文件夹拖拽只允许同父层级上下排序，不再提供层级迁移；drop 后必须二次确认，确认后才调用既有 move API，成功后自动刷新页面。
- 项目卡可拖回根“项目”取消分类；新增模型允许直接建立在根目录，新建模型类型时从根目录创建顶级类型。

### 自动命名 / 基线
- `project.reclassify` 复用并升级到 Tool V1.1.0：模型移动到目标文件夹后按目标末级文件夹增加前缀，例如 `dasifbiaw → 王朝/QA → QA_dasifbiaw`；再次跨类型移动时替换旧类型前缀，拖回根目录时移除该前缀，不再生成 `分类_日期_00i` 名称。
- 基线名称改为 `<当前模型名>_00i` 的源模型独立递增序号，例如 `dasifbiaw_001`、`dasifbiaw_002`；名称不再包含日期。基线创建时间继续写入 lifecycle/metadata 并在模型属性中展示；旧基线的 `version_index` 可用于新规则的序号连续性。

### 下载 / 编辑反馈 / 默认布局
- 浏览器不支持或无法调用 `showSaveFilePicker()` 时，不再报错中止；统一退回标准浏览器直接下载，文件进入浏览器默认下载目录。该方案兼容 Linux Server 跨机器部署，因为保存位置能力由客户端浏览器决定而不是由服务器操作系统决定。
- 签入模型以 temporary 模式进入 Editor 时，页面增加非阻塞灰色蒙版和“签入模型 · 临时编辑”标识；基线只读和正常签出编辑不使用该蒙版。
- 层级数模继续保持默认双列；驱动列表默认语义调整为同样的“未显式关闭即双列”。

### Architecture / Version
- 新增 ProjectSpec / L1 / L2 / L3 权威字段：0；新增 API：0；新增 Job：0；新增业务 Tool：0。仅扩展既有 `project.reclassify`、`ProjectStore` 与 Hub 前端投影/下载辅助逻辑。
- Server runtime / package version 更新为 `2.9.2`；Client runtime 保持 `0.3.8`，WindowsFix 分发标签保持 `V0.3.9`。

## V2.9.1

### Hub / 模型属性
- 模型属性关键数据不再单独按 1 位小数格式化；前端与服务端统一到 Web 技术甘特图的两位精度 metric 规则，整数 `.00` 仍按甘特图规则省略。
- Hub 模型类型文件夹新增独立折叠/展开按钮和最右侧拖拽把手；折叠状态仅保存在页面内存。文件夹拖拽只允许同一父层级内调整上下顺序，复用既有 `/api/model-types/{category}/move`，不再通过拖拽改变目录层级。

### 数模 / 动画
- 层级数模区删除每个数模后的“适配”按钮，只保留顶部“总体适配”，继续复用既有数模 adaptive API。
- 结果查看 → 动画页在“重新加载”同行增加 iframe 全屏展示。导出动画 HTML 删除“跟随阻尼 / 显示名称 / 彩色边框”UI 与名称/边框运行逻辑，仅保留“全选 / 小于25mm”复选框；测距面板标题、选项、名称、数值和空态字号整体下调 2px。导出配置中的 damping 真值仍可用于离线渲染平滑，不再在 HTML 中提供调节 UI。

### 驱动变量 / Architecture
- 新生成和对外展示的驱动派生变量统一为 `驱动名/starttime1`、`endtime1`、`duration1`、`speed1`、`stroke1` 的斜杠小写格式；旧 `驱动名.starttime1` 与斜杠 CamelCase 仅保留为求解期兼容别名，防止历史表达式失效。
- 新增 ProjectSpec / L1 / L2 / L3 权威字段：0；新增业务 Tool/API/Job：0。仅新增 Hub 页面瞬时折叠状态并扩展既有前端/域逻辑。
- Server runtime / package version 更新为 `2.9.1`；Client runtime 保持 `0.3.8`，WindowsFix 分发标签保持 `V0.3.9`。

## V2.9.0

### Hub UI / 属性检视器
- Hub 从“模型列表 → 模型属性”扩展为“模型列表 → 模型属性 → 属性检视器”的 selection-driven master-detail 交互；新增检视器不引入新的 ProjectSpec 权威字段。
- 移除顶部“数模资产管理”入口；模型属性不再显示低频 JSON / 派生产物入口，只保留数模资产、交付数据、存档日志三类可检视属性（游客仅显示交付数据）。关键数据和最新甘特图仍留在模型属性栏。
- 数模资产复用既有公共资产库 API：模型类型切换、新建/复制/删除文件夹、上传文件/文件夹、删除/清空、单文件/批量下载全部集成到检视器；文件夹与文件区支持可拖拽水平分隔条，文件默认双列。资产库维护仍按工程师/管理员权限，重新绑定模型仍要求模型处于签出状态，基线资产保持冻结。
- 交付数据检视器新增会话级文件名后缀与“自动填入关键数据”；四类常用交付文件（动画 HTML、Py 脚本、模型 JSON、甘特图 PNG）可直接选择本地保存路径。后缀仅影响本地建议文件名，不修改服务器交付文件。
- 存档日志改为最多 10 条卡片式历史记录；新增“切出为独立模型”，从指定存档的 ProjectSpec 与其引用的数模资产目录创建独立签入模型，不回退、不修改源模型，也不会把源模型当前 result/delivery 误标为历史产物。

### Architecture / API
- `POST /api/projects/{project_id}/copy-version` 复用原复制版本入口，`ProjectCloneRequest` 仅新增可选 `version_id`；未传时保持原“复制当前签入模型”行为，传入时切出指定存档。
- 新增持久业务字段：0；新增 Tool/Job：0。新增状态仅为 Hub 页面瞬时检视选择、分隔条比例和下载后缀。
- Server runtime / package version 更新为 `2.9.0`；Client runtime 仍为 `0.3.8`，WindowsFix 分发标签仍为 `V0.3.9`。

## V2.8.17

- 修复 Linux Server 上跨机器导入模型后“模型属性 → 数模资产”可能报“数模版本文件夹不存在”的问题。
- 根因包括：源环境 `@model_assets/...` 引用与 Linux 真实目录仅大小写不同、重新分类/跨服务器导入留下旧版本引用，以及旧读取路径会在 Linux 上创建大小写不同的影子空目录。
- 数模资产分类和版本目录改为“精确优先、唯一 casefold 匹配回退”；存在多个大小写变体时不猜测。
- 资产库读取改为无副作用：不存在的库返回空列表，不再由 GET/list 自动创建目录。
- 当前模型引用的数模版本确实不存在时，资产库弹窗仍正常打开，并提示选择服务器现有版本后“确认绑定”；不再以 404 阻断操作。
- 仅大小写不同且唯一匹配时，前端定位服务器真实目录名，并允许用户确认绑定以永久规范化 `mesh_root`。
- 建模信息导出在 `studio_extensions` 中保留 `project_category`；导入旧交换文件时，如果存在合法 `@model_assets/<分类>/<版本>` 引用，可推导项目分类。
- ProjectSpec / L1 / L2 / L3 新权威变量为 0；新增业务 Tool/API/Job 为 0。
- Server 为 `2.8.17`；Client runtime 保持 `0.3.8`，分发标签保持 `V0.3.9 WindowsFix`。

_来源：V2.8.17 `architecture_master_prompt.md` 当前版本契约。_

## V2.8.16

- 签入模型与基线模型不再允许生成或写入动画 HTML；“重新加载”只读取交付数据中的最新 animation HTML。
- 签出模型继续允许动画导出，并保持 preview 优先、交付 HTML 回退的既有读取语义。
- Hub 模型属性按 `project_id` 使用页面内存缓存，TTL 为 10 分钟；A → B → A 在 TTL 内不重复扫描 preview / versions / files。
- 生命周期切换、存档/回退、属性保存、数模/交付写入等显式写操作必须强制刷新权威数据；浏览器整页刷新天然清空缓存。
- ProjectSpec / L1 / L2 / L3 新权威变量为 0；新增业务 Tool/API/Job 为 0。
- Server 为 `2.8.16`；Client 运行版本保持 `0.3.8`，分发标签为 `V0.3.9 WindowsFix`。

_来源：V2.8.16 `architecture_master_prompt.md` 当前版本契约。_

## V2.8.15

- 后台仿真在 worker 启动前先写入 0% 初始状态，避免 UI 长时间只显示“任务已受理”而没有可诊断状态。
- 仿真进度看门狗固定为 10 分钟；首次无数值进展时自动终止并重载一次，再次无进展则返回结构化 `simulation_watchdog_stalled`。
- Windows 原子发布统一增强 `PermissionError / WinError 5` 的限定次数短退避重试，覆盖状态文件、结果目录、provenance、甘特图缓存等发布点。
- 对 `simulation / animation_html_export / web_viewer_export` 增加入途 Job 去重：同项目、同用户、同租约、同种重任务只保留一个在途 Job。
- ProjectSpec / L1 / L2 / L3 新权威变量为 0；不新增业务 Tool/API/Job；Client 协议保持 `0.3.8`。

_来源：V2.8.15 `architecture_master_prompt.md` 架构增量。_

## V2.8.14

### 后台仿真可终止性

- 修复后台仿真在 MuJoCo、模型加载、网格/原生计算等长时间 C 调用中可能无法响应“停止”的问题。
- 保留既有 `JobManager`、`/api/jobs/{job_id}/cancel`、Job workspace、权限和前端进度协议；不新增第二套 Job 系统。
- `/simulate` 的实际仿真计算改为 Job 私有 workspace 内的隔离子进程。父 Job 线程继续投射进度，并轮询既有取消标志。
- 用户取消或 Job 超时时，先请求终止子进程；短暂宽限后仍未退出则升级为强制 kill，从而不再依赖 MuJoCo 原生调用主动返回 Python 才能结束任务。
- 子进程控制文件位于 `.simulation_control`，成功后清理，不进入最终仿真工件。

### 兼容性

- ProjectSpec、DriveSpec、simulation result、trajectory、API 请求/响应 Schema 均不变。
- Client 版本保持 V0.3.8；Server 更新为 V2.8.14。

_归并来源：`RELEASE_NOTES_V2.8.14.md`。_

## V2.8.13

### 后台仿真性能优化

- 修复后台 MuJoCo 仿真在映射驱动、多运动段或测距配置下明显变慢的问题。
- 映射点 legacy normalization 改为 **256 项有界 LRU 缓存**，相同映射曲线不再在每个 physics step 反复去重、排序和标准化。
- 动态仿真复用采样时刻已经算出的驱动命令到紧邻的下一 fixed-step，避免同一时间戳重复执行完整 schedule/mapping 求值；`mj_step1 -> ctrl -> mj_step2` 控制时序不变。
- 测距 pair 的文件名→geom id 展开改为每个 simulation run 只绑定一次；每一帧仍执行原有全部 `mj_geomDistance()` 组合，不降低测距频率、不改变精度或结果语义。
- 不新增 ProjectSpec 变量、业务 Tool/API/Job、权限或 Client 协议；继续复用现有 simulation Job 与结果工件。

Server: 2.8.13  
Client: 0.3.8

_归并来源：`RELEASE_NOTES_V2.8.13.md`。_

## V2.8.12

### MuJoCo View 首帧启动修复

- 修复“启动进度已经结束，但 MuJoCo 原生窗口仍长时间不出现”的时序问题。
- 根因：`mujoco.viewer.launch_passive()` 返回的是已经建立的 passive Viewer handle，但原生 GUI/render loop 与 Python 调用侧异步协作；旧逻辑在 handle 返回后立即发送 `MUJOCO_STUDIO_VIEWER_READY`，随后马上执行较重的 mesh 扫描/测距准备，大模型下可能导致 READY 早于首帧真正呈现。
- 新增内部轻量 `_prime_passive_viewer()`：复用现有 `viewer.sync()` / `viewer.is_running()`，在 READY 前完成首帧同步并短暂释放 GIL，让原生 GUI/render 线程获得调度机会。
- READY 后仍继续延后执行 `_build_distance_pairs()`；不恢复 MjSpec site 二次编译，不改变测距精度/20 Hz 策略。
- 新增 ProjectSpec/L1/L2/L3/前端持久变量、业务 API/Job/工具目录均为 0。

Server: 2.8.12  
Client: 0.3.8

_归并来源：`RELEASE_NOTES_V2.8.12.md`。_

## V2.8.11

### 数模资产管理器

- 数模资产管理弹窗右下角新增“清空”按钮，位置紧邻“关闭”左侧。
- 清空保留当前数模版本文件夹及 `.mujoco_asset_meta.json`，删除其中其它文件/子目录；操作前二次确认。
- 继续复用既有资产库写权限；冻结基线不可清空。若文件夹被模型使用，确认框会明确提示清空后的影响。

### 驱动设置 UI

- 单列展示多个运动段时，共同字段顺序固定为“开始模式、开始/偏移、参数模式、时长/速度、行程”，相对时间专属参考字段后置。
- 为单列非映射段设置稳定宽度，使各运动段的“开始/偏移”输入框与“参数模式”下拉菜单上下左对齐。
- 双列模式、映射段、驱动数据模型和仿真语义保持不变。

### 架构与版本

- ProjectSpec/L1/L2/L3 新权威变量：0。
- 新业务 Tool/Job/工具目录：0；仅扩展现有资产库 Store/API。
- Server: 2.8.10 -> 2.8.11。
- Client: 0.3.8（保持）。

_归并来源：`RELEASE_NOTES_V2.8.11.md`。_

## V2.8.10

### Viewer 启动继续提速

- 在 V2.8.9 “Viewer 先于测距采样启动”的基础上，进一步把 `_mesh_collection_center()` 移到 `MUJOCO_STUDIO_VIEWER_READY` 之后；大规模 mesh 集合的相机中心扫描不再阻塞原生 Viewer 窗口就绪信号。
- Client Viewer bundle 改用 `ZIP_DEFLATED, compresslevel=1`。局域网场景优先降低服务端同步打包 CPU 时间，同时保持与 Client V0.3.8 的 ZIP 兼容。
- Client `safe_extract_bundle()` 复用 ZIP central directory 统计 `server_assets` 文件数，不再在解压完成后对整个资产目录执行一次额外 `rglob()` 递归扫描。
- 不修改 MuJoCo timestep、trajectory、测距采样精度、资产绑定语义和 Viewer 播放行为。

### Client 网络配置复核

- Client 版本保持 `0.3.8`。
- `Client/main.py` 默认 `SERVER_IP` 仍为 `10.13.90.107`，`SERVER_PORT = 8765`，即 `http://10.13.90.107:8765`。
- 本地桥接监听仍为 `127.0.0.1:8766`。
- `client_config.json` 仍不得持久化或覆盖 `server_url`，因此历史 JSON 配置不会改变当前服务端地址。

### 版本

- Server: 2.8.9 -> 2.8.10
- Client: 0.3.8（保持）

_归并来源：`RELEASE_NOTES_V2.8.10.md`。_

## V2.8.9

### Viewer 启动性能修复
- 修复点击右上角 MuJoCo View 后长时间处于加载状态、原生 MuJoCo Viewer 窗口迟迟不出现的问题。
- Viewer 启动主链改为：单次加载最终 `MjModel` → `MjData` / 首次 `mj_forward()` → 立即 `launch_passive()` → 立即输出 `MUJOCO_STUDIO_VIEWER_READY` → 再初始化测距采样和 Tk 控制器。
- 前端/Client 因此不再等待表面撒点和测距预处理完成后才认为 Viewer 已启动。

### 测距后端收敛
- 实时 Viewer 启动阶段不再使用 MjSpec site 注入与二次 compile，避免低点数配置反而触发昂贵的二次模型编译。
- 复用现有向量化/缓存测距路径、`_AsyncDistanceWorker` 和 `viewer.user_scn` overlay；距离语义、采样上限、20 Hz 实时测量配置保持不变。
- Passive Viewer、渲染线程和异步测距 worker 共享同一最终 `MjModel`，避免 Viewer 打开后替换 model 的一致性风险。

### 架构
- 新增 ProjectSpec / L1 / L2 / L3 权威持久变量：0。
- 新增前端持久变量：0。
- 新增业务 Tool / API / Job / 工具目录：0。
- 更新 `architecture_master_prompt.md`，新增 V2.8.9 Viewer 优先启动时序契约和回归门禁。

### 验证
- `viewer_runner.py` 与 V2.8.9 专项测试通过 Python 语法编译。
- 专项无依赖回归确认 `launch_passive` / READY 严格早于 `_build_distance_pairs()`，且 READY 前不存在 MjSpec compile 调用。
- 项目 pytest 在当前交付环境中测试主体通过，但 teardown 依赖 `passlib`；当前容器未安装该依赖且离线无法补装，因此完整 pytest 环境级收尾未执行成功。

### 版本
- Server: 2.8.8 -> 2.8.9
- Client: 保持 0.3.8

_归并来源：`RELEASE_NOTES_V2.8.9.md`。_

## V2.8.8

### 设定变更
- 层级建模 → 层级属性 → STL / OBJ 数模：未保存列模式时默认启用“双列”。
- 用户明确取消“双列”后仍保存为单列，不强制覆盖既有个人选择。

### 修复
- 修复数模“单列”显示失效：单列现在严格只有一个网格轨道，不再被历史 auto-fit 规则自动拆成多列。
- 修复数模“双列”卡片在半宽区域内透明度、碰撞等控件堆叠：双列卡片内部改为可收缩/可换行布局。

### UI 优化
- 驱动设置单列模式下，运动段参数改为基于真实 DOM 的自适应 Flex 布局，左右自动填充剩余宽度，空间不足时自然换行。
- 修正历史 V2.5.3 使用无效 `.drive-list/.two-column/.motion-segment-grid` 选择器导致的样式未生效问题。

### Client V0.3.8 网络配置
- 客户端服务端 IP 收口到 `Client/main.py` 顶部，默认 `SERVER_IP = "10.13.90.107"`、端口 `8765`。
- `client_config.json` 不再保存/覆盖 `server_url`，避免修改 `main.py` 后仍被旧 JSON 配置遮蔽。
- Client 本地桥继续只监听 `127.0.0.1:8766`，origin / ticket 安全边界不放宽。

### 架构
- 新增 ProjectSpec / L1 / L2 / L3 权威持久变量：0。
- 新增前端持久变量：0。
- 新增业务 Tool / API / Job / 工具目录：0。
- 继续复用 `uiSet()`、`state.ui.model.mesh_two_columns`、`state.ui.drives.two_columns`、`.mesh-grid-two`、`.drive-grid-two`。

### 版本
- Server: 2.8.7 -> 2.8.8
- Client: 0.3.7 -> 0.3.8

_归并来源：`RELEASE_NOTES_V2.8.8.md`。_

## V2.8.7

### 修复
- 修复 Linux 首次部署时出现大量历史模型、模型类型和数模资产的问题。
- 根因是 V2.8.6 发布 ZIP 本身携带了开发/测试运行态 `Server/V2_projec`，并非首次启动正常初始化。
- V2.8.7 发布包中的 `Server/V2_projec` 现在严格只包含 `scenes/default_scene.xml`。
- 不在启动时删除任何 `V2_projec` 数据，避免升级部署误删真实用户项目。

### 架构
- 新增 ProjectSpec 权威变量：0
- 新增业务 Tool/API/Job：0
- 继续复用既有 `DATA_ROOT`、`ProjectStore`、`SCENE_LIBRARY_ROOT` 和默认场景安装逻辑。
- 增加发布数据根防污染回归测试与 `.gitignore` 约束。

### 版本
- Server: 2.8.6 -> 2.8.7
- Client: 0.3.7（不变）

_归并来源：`RELEASE_NOTES_V2.8.7.md`。_

## V2.8.6

### 修复

- 运行时场景固定为 `DATA_ROOT/scenes/default_scene.xml`。Linux 使用 `Server/run.py` 且未覆盖 `MUJOCO_STUDIO_DATA` 时，对应 `Server/V2_projec/scenes/default_scene.xml`。
- 历史 `project.template_scene` 不再参与生成/仿真的场景路径查找，避免旧场景名或跨机器路径导致 409“XML 场景不存在”。
- 缺失 `default_scene.xml` 时继续复用既有原子安装逻辑自动创建。

### 兼容性

- Client 协议未改变，Client 版本保持 0.3.7。
- 自定义场景 API 暂保留兼容，但不再改变运行时场景来源。

_归并来源：`RELEASE_NOTES_V2.8.6.md`。_

## V2.8.5

### 企微 Webhook 基线通知修复
- 复用现有 `state.wecomWebhookUrl`、baseline API、`_baseline_wecom_message()` 与 `_post_wecom_text()`；未新增业务 Tool、API、Job 或 ProjectSpec 持久变量。
- 修复 V2.8.4 “只要填了 webhook 就提示已提交，但实际发送失败完全不可见”的问题。
- baseline 成功后，后端通过同一 HTTP 响应返回企微通知状态：`not_configured / sent / failed`。
- Hub 仅在企微真实成功时提示“企微机器人消息已发送”；失败时明确显示诊断原因，同时保持基线创建成功、不回滚。
- `architecture_master_prompt.md` 已追加 V2.8.5 架构增量。
- Server 严格升级到 2.8.5；Client 协议未变化，保持 0.3.7。

### 验证
- `node --check frontend/app.js`: PASS
- Python `compileall`: PASS
- 企微/Hub 定向回归: 9 passed
- 全量 pytest（同环境）：
  - 原始 V2.8.4：35 failed / 375 passed / 3 skipped
  - 修改 V2.8.5：34 failed / 378 passed / 3 skipped
  - 未新增全量测试失败；剩余失败为原包已有历史契约/环境测试问题。

_归并来源：`RELEASE_NOTES_V2.8.5.md`。_

## V2.8.4

### MuJoCoHub 顶栏 UI 收敛

- 企微 Webhook 配置只在 MuJoCoHub `/hub` 顶栏显示；进入独立模型 Editor 后统一隐藏，返回 Hub 自动恢复。
- 账号区域整体只在 MuJoCoHub 显示，包含既有身份徽标、账号管理和退出三个 UI；原角色、管理员模式和单用户权限逻辑保持不变。
- 企微 Webhook 控件与账号管理控件组统一为 35px 外框高度，解决顶栏纵向尺寸不一致。
- 不新增业务变量、Tool、API、Job 或项目持久字段；继续复用现有浏览器 localStorage Webhook 状态、账号管理对话框和 Hub/Editor 路由模式。
- Server 版本严格升级至 2.8.4；Client 保持 0.3.7。

_归并来源：`RELEASE_NOTES_V2.8.4.md`。_

## V2.8.2

### Baseline naming fix

- Baseline names now use exactly the same managed naming rule as checked-in models: `<model-type>_YYYYMMDD_00i`.
- Baseline naming is derived from the model category/type, not from the already-versioned checked-in model name.
- Baseline creation directly reuses `ProjectStore.next_version_identity(category)`.
- The V2.8.1 baseline-specific `next_baseline_identity()` helper is removed to avoid duplicate naming logic.
- Existing V2.8.1 delivery filename cleanup, canonical model JSON export behavior, WeCom notification behavior, and the empty Linux `projects/None` cache layout are preserved.

_归并来源：`RELEASE_NOTES_V2.8.2.md`。_

## V2.8.1

### Baseline date-sequence naming

- New baseline model names retain the checked-in source model name as the prefix.
- Every newly created baseline is named `<source-name>_YYYYMMDD_00i`, for example `RobotArm_20260901_001`.
- The suffix increments for the same source-name prefix on the same day; different prefixes may each start at `_001`.
- The original source model name remains in `metadata.archive_base_name` so previous-baseline lookup and audit history remain correct.
- Existing baseline API, freeze, delivery and WeCom notification flows are reused; no new business Tool/API/Job or ProjectSpec field is introduced.
- Server/product version is V2.8.2; Client remains V0.3.7.

- Delivery `.py`, model `.json`, and Gantt `.png` filenames no longer append the literal `关键数据`; selected key-data values remain in the canonical delivery stem.
- Delivery model JSON continues to use the same `_project_export_payload()` canonical export envelope as the top-right “导出模型” action.

_归并来源：`RELEASE_NOTES_V2.8.1.md`。_

## V2.8.0

### Baseline WeCom notification

- MuJoCoHub top bar now accepts a WeCom robot webhook URL, stored only in the current browser.
- Baseline creation opens an editable release-log confirmation dialog and warns that the log will be pushed to WeCom.
- After a baseline is successfully frozen, the server posts operator username, pure baseline model name, previous/current key data when available, update log when available, and a reserved empty simulation-result-link line.
- Notification failures never roll back an already-created baseline.
- Server/product version is V2.8.0; Client remains V0.3.7.

_归并来源：`RELEASE_NOTES_V2.8.0.md`。_

## V2.7.2

### Changes
- Server version advanced to **2.7.2**; Client remains **0.3.7**.
- Global toast/notification prompts now appear from the **bottom-right** instead of the top-right.
- Mobile toast layout is anchored to the bottom with 8 px side/bottom spacing.
- Preserves the STL default mass behavior: STL meshes with no explicit mass default to **0.01 kg**; explicit user values are not overwritten.

### Compatibility
No Viewer bundle or Client API protocol change is introduced by this increment.

_归并来源：`RELEASE_NOTES_V2.7.2.md`。_

## V2.7.0

- Removed the duplicate inner “模型属性” heading from the Hub property card while retaining the existing Hub section label.
- Tightened Guest to a baseline-only, result-view-only role: the project catalog is filtered to baselines, non-result editor routes are forced back to `simulation`, Guest does not open an edit session, global jobs/skills/edit helpers are not loaded, and Server API authorization remains default-deny.
- Guest baseline result viewing keeps the intended read-only interactions: reload existing animation HTML, choose result-curve sources locally for coordinate viewing, and open/zoom the Gantt popup. Mutating result, Gantt, export/save-delivery and model-edit actions are hidden or rejected.
- Guest file projection exposes only frozen baseline delivery data; project JSON, mesh assets and derived edit outputs are withheld. Delivery files can still be downloaded.
- Added a white translucent, property-card-scoped loading overlay/spinner while the lightweight Hub `/preview` request refreshes after model selection. Secondary version/file hydration no longer gates first property paint.
- Changed ordinary project archive retention to a hard latest-10 total cap, including legacy `locked` sidecars.
- On successful baseline creation, the source model is compacted to its newest 3 archives. A baseline is now the immutable snapshot itself and no longer owns or exposes archive data; its `/versions` projection is empty. Imported baselines follow the same no-archive rule.
- Added archive logs to check-in/manual archive flows and a baseline note to baseline creation. Check-in log is carried through the existing `project.lifecycle` command path into the existing archive metadata `log`; baseline note is stored as `metadata.baseline_log`. Hub displays the selected archive log above the archive dropdown and displays baseline notes without an archive dropdown.
- Added system audit text for automatic/forced check-in paths so non-interactive signing does not create an unexplained archive.
- No business Tool, Job, new ProjectSpec/L1/L2/L3 authoritative field, Client API field, or Viewer bundle schema was added. Server is 2.7.0; Client remains 0.3.7; minimum compatible Client protocol remains 0.3.6.

_归并来源：`CHANGELOG_2.7.0.md`。_

## V2.6.5

### Summary

V2.6.5 closes workspace/result retention gaps found in the V2.6.4 storage-lifecycle audit. The authoritative project/event storage model is unchanged; the release hardens background physical cleanup and Client runtime cleanup.

### What changed

- Server orphan workspace reclaim now runs at startup and periodically while the service remains up. The default interval is 3600 seconds and is independently configurable from the 15-second lease sweep.
- Filesystem-reclaim errors are isolated so the runtime sweeper remains alive.
- Existing persistent project `results/` roots periodically reuse the existing `JobWorkspaceManager.prune()` retention rule without creating directories for projects that have never produced results.
- Client V0.3.7 removes only expired `viewer_*` bundles and `mesh_sync_*.zip` archives at startup. Live bundles known to the registry are protected; the Viewer runner also refreshes bundle-directory mtime every 60 seconds to protect a Viewer that outlives a Client restart.
- Removed the unused `ProjectStore.new_mesh_selection_directory()` allocator.

### Planning-SPEC corrections

The incoming V2.6.5 SPEC was correct about the main lifecycle gaps, but two implementation details were unsafe to apply literally:

1. Periodic result maintenance must use the persistent project directory directly, not `_result_base(project_id)`, because `_result_base` is edit-session-context aware and may select an ephemeral tree.
2. `ViewerRegistry` cannot by itself prove liveness across Client restarts because it is in-memory while Viewer children are detached. The runner heartbeat supplies a process-independent freshness signal without adding another persistent state file.

### Compatibility

- Server: 2.6.5.
- Client runtime: 0.3.7.
- Minimum compatible Client protocol remains 0.3.6.
- No persistent ProjectSpec field, business Tool, Job type, API, or Viewer bundle schema change.

### Verification

See `Server/docs/TEST_REPORT_2.6.5.md`.

_归并来源：`RELEASE_NOTES_V2.6.5.md`。_

## V2.6.4

- Fixed the drive-mapping (companion) Gantt colour-block positions. Source rows were correct while companion blocks drifted off the mapping breakpoints (e.g. a source block spanning 107.42→381.88 rendered companion 15.0→106.5 instead of 15.0→100.01, and the neighbouring block started at 76.8 instead of 100.01).
- Root cause: the Gantt projection sampled the follower joint at each source block's boundary *time*. That time sample is the superposition of every source segment active at the instant, so overlapping source segments bled a neighbour's motion into the boundary. The source rows use a list-order accumulator and were therefore unaffected.
- The companion breakpoints are now derived from the source's own cumulative per-block travel mapped through the mapping curve — the same accumulator the source rows display — which is immune to time-overlap superposition and reproduces the drive-settings breakpoints exactly.
- Applied the identical fix to the animation-HTML fallback Gantt (`viewer_runner._mapping_gantt_segments`) so delivered animation and the preview agree.
- Nested mapping sources (a mapping whose source is another mapping) retain the historical time-sampled projection, guarded by a new internal `_reference_driven_by_mapping` / `_source_is_nested` predicate.
- No new persistent `ProjectSpec` field, business Tool, Job type, API, or Client protocol field. Reuses the existing `_interpolate_mapping` / `_mapping_value` interpolators.
- Added regression sentinel `tests/test_v264_mapping_gantt_overlap.py`, including overlap, sequential, scalar-source, nested-source, animation-fallback and version-boundary coverage.
- Updated all active Server version surfaces to 2.6.4: package metadata, tool metadata, generated animation provenance, Viewer titles/overlay, Web UI/cache keys and current-version regression contracts. Historical V2.6.3 comments and release records remain historical.
- Server version is 2.6.4. Client remains 0.3.6.

_归并来源：`CHANGELOG_2.6.4.md`。_

## V2.6.3

- Fixed Editor deep-link startup so `/models/{id}/editor/{page}` no longer waits for full Hub hydration before asking to enter editing.
- Added lightweight project-catalog and preview projections to reduce model-list/property blocking reads.
- Added explicit check-in from an active persistent Editor with the required close-page confirmation and final-save ordering.
- Preserved lease/network semantics: heartbeat transport failures retry and never directly sign in a model.
- Added `【签入】` / `【签出】` / `【基线】` prefixes to the independent Editor name/title.
- Removed Batch Optimization and Agent from top navigation; grouped account controls; removed auto-check-in countdown and EVENTS bubbles.
- Released the lifecycle blocking mask after lightweight preview; versions/files now hydrate in the background.
- Final check-in save waits for the active save chain and skips projections that would be discarded when the Editor closes.
- Guarded Hub preview hydration with a monotonic revision so stale metadata responses cannot overwrite the current selection.
- Added an archive-pruning fast path that avoids sidecar reads while the history count is within the retention limit.
- Server version is 2.6.3. Client remains 0.3.6.

_归并来源：`CHANGELOG_2.6.3.md`。_

## V2.6.2

- Restored V21-compatible source/companion motor travel mapping semantics.
- Source segment absolute start now comes from resolved time-position projection instead of naive preceding-travel accumulation when current preview data is available.
- Added polynomial-safe browser expression evaluation aligned with the Server safe evaluator (`**`, `%`, selected math functions/constants and resolved variables).
- Fixed root-level subtraction detection so unary negative exponents and internal polynomial subtraction are not mistaken for absolute endpoint pairs.
- Mapping rows now reject non-finite values, deduplicate equal source coordinates with last-row-wins semantics, and retain the implicit runtime origin behavior.
- Native Viewer mapping normalization and inverse branch selection are regression-locked to the same observable rules.
- Added no ProjectSpec field, business Tool, API, Job type, artifact type, or Client protocol field.
- Server/tool/export/viewer/cache-bust projection updated to 2.6.2; Client remains 0.3.6.

_归并来源：`CHANGELOG_2.6.2.md`。_

## V2.6.1

- Restricted managed delivery projection to animation HTML, NX AFU script, Gantt PNG and model JSON, with one current physical file per kind.
- Moved delivery manifest metadata from the user delivery folder to `core/artifacts/delivery_manifest.json`, while retaining migration reads for historical manifests.
- Baseline creation now refreshes model JSON, Gantt PNG and NX AFU before freezing; animation HTML is never auto-generated by baseline creation.
- Baselines copy the selected public model-asset folder to private `assets/baseline_mesh_snapshot` and copy delivery to a private frozen delivery tree.
- Fork/use-version republishes the frozen model asset into a new public asset folder and copies frozen delivery into the new working model.
- Added hidden public model-asset folder provenance metadata (`uploaded_by`, timestamps and source reference); usage names are derived from authoritative project references.
- Added guarded public model-asset file download endpoint.
- Unified model-property asset selection and top-level asset management into `modelAssetManagerDialog`, with explicit binding confirmation and a brown download-only frozen baseline mode.
- Added blocking loading around unified model-asset uploads.
- Reprojected closure selection as a compact hierarchy tree and retained dynamic solver green styling.
- Removed dead V2.6.0 in-app model-tab CSS and obsolete parallel model-property asset upload functions/controls.
- Updated Server/tool/export/viewer/cache-bust projection to 2.6.1; Client remains 0.3.6.

_归并来源：`CHANGELOG_2.6.1.md`。_

## V2.6.0

- Replaced in-page multi-model tabs with `/models/{project_id}/editor/{page}` deep links and one named browser context per model.
- Canonicalized the Hub at `/hub`; editor feature navigation now uses History API paths instead of shared `#model/#drives/...` hashes.
- Removed `openModelTabs`, `activeModelTabId`, `modelTabContexts` and the model tab strip UI.
- Added a compact Editor shell that removes the outer first row and returns the reclaimed vertical space to modeling/results UI.
- Reused the existing edit-session API and extended `/edit-session/leave` to accept the final dirty project snapshot for project-scoped page close convergence.
- Added a bounded browser-local editor registry so Hub lifecycle actions refuse to cross an editor that is still open.
- Deep Hub/Editor paths now receive the same no-cache frontend policy as `/` and `/assets`.
- Server/tool/export/viewer version projection updated to 2.6.0. Client remains 0.3.6.

_归并来源：`CHANGELOG_2.6.0.md`。_

## V2.5.11

### Fixed

- Critical-data `motion_time` now uses the latest concrete stop across all resolved drives. Mapping segments no longer leak their synthetic `simulation.end_time` carrier into key data, delivery naming, preview variables or optimization `EndTime`.
- Empty drive joint selection is now valid and generates an explicit tiny transparent, non-colliding Geom at world origin as the drive target artifact.
- Hierarchy modeling now displays translation joints as “滑动副”.

### Animation HTML

- Added `animation_html.distance_follow_damping` (default `0.35`, range `0..0.95`) and a live replay slider.
- Raw baked distance samples remain unchanged; only the rendered distance number and rendered line endpoints use time-based damping.
- Bottom playback panel alpha is `0.1` and its controls/typography/padding are compressed to approximately 70% of the previous size; developer-support text is reduced to 50%.
- Right measurement panel alpha is `0.2` without reducing child text opacity.
- Left title panel alpha is `0.2`, its visual scale is approximately 50%, and displayed titles strip literal `关键数据`.

### Architecture

- No new Tool/API/Job type. Existing animation export, motion resolution, XML generation and validation paths are extended in place.
- Client remains V0.3.6.

_归并来源：`CHANGELOG_2.5.11.md`。_

## V2.5.10

V2.5.10 focuses on server-side model-asset lifecycle and reproducible result review.

The overview now includes a dedicated digital-model asset manager. Assets remain shared by model type, with one folder representing one digital-model version. Engineers can create versions, copy a version folder, upload files/folders and delete unreferenced versions. Projects continue to store only `@model_assets/...` references, while baselines keep private frozen copies.

Model-type creation and deletion now require the administrator account or administrator mode, and the first-start administrator-mode password is `6870`. The deletion path has been hardened so category metadata and asset folders are actually removed; retained projects are protected from dangling shared-asset references.

Simulation curve review is now persistent: the latest successful result is mirrored to `results/latest_simulation.json`, reopened directly by the result viewer, and frozen with a baseline. Users no longer need to rerun simulation just to repopulate curve choices.

Client remains V0.3.6.

_归并来源：`RELEASE_NOTES_V2.5.10.md`。_

## V2.5.9.1

### Scope and reuse audit

V2.5.9.1 is a patch over V2.5.9. It implements the convergence items G1–G8 from the V2.5.9 audit while preserving the existing architecture.

- New ProjectSpec authoritative variables: **0**.
- New business Tools: **0**.
- Reused: `SessionStore`, `project.lifecycle`, `KernelManager` authoritative/ephemeral Edit Session, `_PENDING_CHECKINS`, `core.atomic_io`, `JobManager`, `sim.export_animation_html`, browser Gantt cache, existing Viewer/PIL fallback renderer, and delivery naming projection.
- Client remains V0.3.6; Viewer bundle/client protocol is unchanged.

### Gantt truth source and animation export

- Browser `__GanttPopup__.refreshCache(projectId)` is called before a Web animation export Job is submitted.
- `core/artifacts/gantt_cache/latest_gantt.png/json` is treated as the browser-popup cache; server fallback rendering no longer writes there.
- Cache-miss fallback is written only to the isolated Job/Viewer `gantt_fallback/` directory.
- Gantt snapshot failure is non-fatal. Animation export completes with `gantt_source="unavailable"` and warning `gantt_snapshot_unavailable`.
- Export results/provenance expose `gantt_source` (`popup_cache`, `fallback_render`, `unavailable`).

### Trajectory reuse and closure diagnostics

- Existing-current simulation trajectory is reused without warning.
- If physical assets are unchanged but project parameters/schedule have changed, the newest trajectory may be reused with warning `trajectory_reused_stale_parameters`.
- Reused qpos is checked against the generated scene `model.nq` before frame export; mismatch becomes structured `trajectory_nq_mismatch`.
- Kinematic closure non-convergence is converted to structured Job error `kinematic_closure_nonconvergence` with closure IDs, time, residual, iterations, and hint.
- The API remains the existing asynchronous `202 + Job` model; no incompatible synchronous HTTP 422 conversion was introduced.

### Session / Lease / Lifecycle convergence

- Lease heartbeat expiry and browser Session expiry release transient edit authority only. They do **not** directly change persistent `project.lifecycle.status`.
- Model Edit Idle continues independently and may check in the model after its deadline.
- `SessionStore.touch_lease()` now refuses to renew a Lease that has already expired, closing the sweeper/heartbeat race.
- `POST /api/auth/lease/reacquire` safely restores edit authority for models still checked out by the same username and preserves the existing idle deadline.
- Heartbeat response projects `lease_active`, `lease_lost_reason`, and `checked_out_project_ids`.
- The Web UI distinguishes network heartbeat failure from actual Lease loss, shows a persistent recovery banner, and renders the idle auto-check-in countdown.

### Restart-safe pending check-ins

- `_PENDING_CHECKINS` remains runtime coordination state, not ProjectSpec truth, but is now persisted to `DATA_ROOT/.runtime/pending_checkins.json` with atomic writes.
- Restart loads pending records before checkout recovery.
- A checked-out model still inside its idle window remains checked out after restart and its deadline is restored.
- If `checked_out_at` is missing/malformed and no pending deadline exists, restart conservatively grants a fresh idle window rather than treating process restart as a Lifecycle trigger.
- Deferred/failed automatic check-in retry is bounded by `MUJOCO_STUDIO_PENDING_CHECKIN_MAX_RETRY` (default 10). Exhaustion remains visible as `failed_permanent`.
- `GET /api/admin/pending-checkins` exposes pending records to administrators.
- Login identity projection exposes `pending_lifecycle_failures` for the current user.

### Naming and Viewer cleanup

- Critical-data names now use one `CRITICAL_DATA_SEPARATOR=","` and `_critical_data_join(...)` across archive/version/delivery projection.
- `GET /api/projects/{id}/delivery-stem` gives the Web Gantt PNG export the same delivery-stem naming contract.
- Viewer keeps the `测距模式` selector (D1-A) but removes the obsolete `measurement_hz_var`; sampling frequency is read directly from the existing runtime profile and clamped.
- Viewer fallback Gantt rendering uses the isolated `gantt_fallback` directory when popup cache is absent.

### Version

- Server: `2.5.9.1`.
- Client: `0.3.6`.
- No ProjectSpec schema migration.
- No Client protocol migration.

_归并来源：`CHANGELOG_2.5.9.1.md`。_

## V2.5.9

### Session / Lease / Lifecycle state machine

- Split the three timeout clocks: sliding browser Session TTL, heartbeat-only Lease TTL, and 1-hour model Edit Idle TTL.
- Lease heartbeat is Session/Lease scoped and no longer depends on browser tabs or recent pointer/keyboard activity.
- Check-out remains authoritative model ownership. Closing a Tab/Edit Session/page no longer performs implicit check-in.
- Every checked-out creation path activates the Session Lease and starts an independent idle deadline.
- Successful real model mutations reset model idle; heartbeat and UI-only activity do not.

### Logout semantics

- `/api/auth/logout` now returns `complete`, `deferred`, or `failed`.
- Background Jobs cause `deferred`: account logout completes and lifecycle check-in is retried after the Job ends.
- Real lifecycle failure causes `failed`: Session and cookie are preserved for retry.
- Authoritative Edit Session state is closed only after a requested lifecycle check-in succeeds.

### Lifecycle safety

- Generic `/api/commands` lifecycle operations use the same lifecycle coordinator as the dedicated lifecycle endpoint.
- `project.lifecycle` is rejected from ChangeSet create/update/dry-run/commit paths because it has external lease/session/archive side effects.
- Existing History safety remains: lifecycle events are auditable but not generic undo/redo targets.

### Compatibility

- Legacy heartbeat payload fields are still accepted but ignored.
- Client remains V0.3.6.

_归并来源：`CHANGELOG_2.5.9.md`。_

## V2.5.8

### Added / Changed

- 动画 HTML 改为“生成预览 → 动画页重新加载 → 保存交付”三段式，不再在一键导出时弹本地保存或自动下载。
- 新增 `core/artifacts/animation_preview/` 最新预览投射，并用模型指纹阻止过期动画被保存为交付。
- 动画 HTML 每次生成都由服务端复用 Viewer 甘特图渲染器刷新 `latest_gantt.png`，并把该 PNG 内嵌到单文件 HTML。
- 所有交付导出文件名统一包含 `关键数据`，各关键数据值使用英文逗号分隔。
- 模型属性“运动时间”固定按 `resolve_schedule()` 中最晚驱动结束时间计算。
- 动画导出优先复用当前 MuJoCo `trajectory.npz`，避免闭链机构为了 HTML 再次求解；baseline 动画冻结同样复用源轨迹。
- Viewer 删除测距刷新频率下拉菜单；定位时间输入框移到截图按钮右侧并改为 Enter 触发。

### Architecture

- 新增 ProjectSpec 权威变量：0。
- 新增业务 Tool：0。
- `delivery_name_suffix` 被明确视为导出展示元数据，不参与物理仿真指纹。
- Client 保持 0.3.6。

_归并来源：`CHANGELOG_2.5.8.md`。_

## V2.5.7.1

### Fixed

- Baseline temporary-edit sessions can no longer mutate any physical mesh asset tree. Existing mesh create/delete/upload/admin-sync/client-sync routes share one baseline freeze guard.
- Viewer launch readiness no longer depends on `MUJOCO_STUDIO_VIEWER_READY` remaining inside the last 80 log lines. Server/Client registries expose persistent `ready` and `sampling` status.
- Drive folded variables and Gantt now refresh through one atomic `/preview` projection. Project load no longer clears the just-fetched preview schedule, and current preview schedule wins over stale latest-simulation fallback.
- Delivery artifact URLs are encoded per path segment so special-character filenames remain downloadable/deletable.

### Confirmed existing V2.5.7 behavior

- Delivery UI names the action `全部批量下载`, uses `showDirectoryPicker()`, provides per-file delete and `清空文件`.
- Copy-version and use-baseline copy JSON state, full delivery tree, derived project-owned outputs, and create a user-named shared mesh folder under the same model type.
- Baseline prompt is `数模与交付数据将冻结，请确认交付数据和数模是否完整`; baseline owns private frozen mesh and delivery trees.

### Versions

- Server: 2.5.7.1
- Minimum Client: 0.3.6

_归并来源：`CHANGELOG_2.5.7.1.md`。_

## V2.5.7

- 交付数据：新增管理、单文件删除、清空与本地目录“全部批量下载”。
- 生命周期：复制版本/使用基线完整复制 JSON、交付数据、派生产物，并创建用户命名的新共享数模资产文件夹。
- 基线：数模与交付数据冻结到基线项目私有目录；冻结交付禁止修改，只能随基线项目删除。
- 驱动：保存后统一从 `/preview` 刷新驱动折叠变量与甘特图，修复双变量缓存漂移。
- Client 最低版本升级至 V0.3.5。

_归并来源：`CHANGELOG_2.5.7.md`。_

## V2.5.6.11.1

- Removed the legacy per-project mesh-version runtime store and `/mesh-versions` rollback APIs.
- Baseline “使用版本” now clones all frozen project-owned working folders (`assets` excluding the frozen mesh snapshot, `outputs`, `results`, `core/artifacts`, `delivery`) plus ProjectSpec/UI.
- Baseline frozen meshes are republished only to the model-type shared asset library; the new working project stores the shared `@model_assets/...` path and does not retain `assets/baseline_mesh_snapshot`.
- Added cleanup of the newly published shared mesh folder if fork creation fails.
- Updated mesh-sync UI wording to folder semantics and fixed the stale V2.5.6.10 version contract.

_归并来源：`CHANGELOG_2.5.6.11.1.md`。_

## V2.5.6.11

- Server version: 2.5.6.11. Client remains 0.3.4.
- Refactored mesh assets from per-model five-version history to a shared model-type asset-folder library.
- Checked-in/checked-out models store a shared asset-folder path; baselines freeze an independent mesh snapshot.
- Using a baseline publishes its frozen mesh folder back into the model-type shared library for reuse.
- Added folder create/select and in-folder asset add/delete flows while preserving legacy mesh-version APIs only for compatibility.

_归并来源：`CHANGELOG_2.5.6.11.md`。_

## V2.5.6.10

- Added “下载整个文件夹” to the model-properties delivery-data popup.
- The button recursively packages that model's unique complete `delivery_directory()` tree into one ZIP.
- Empty subdirectories are preserved in the ZIP.
- Local ZIP saving uses `showSaveFilePicker` before the request, so the user explicitly chooses the destination and the application does not fall back to the browser Downloads directory.
- Individual files in the delivery-data popup now also use the explicit save-path flow instead of `<a download>`.
- No new delivery directory or parallel storage mechanism was introduced; V2.5.6.9 per-model delivery identity remains authoritative.
- Server version: 2.5.6.10. Client remains 0.3.4.

_归并来源：`CHANGELOG_2.5.6.10.md`。_

## V2.5.6.9

- Delivery data is now one complete first-class folder owned by each model.
- Unbound models use `<project>/delivery/`; externally bound models use a project-id-qualified folder so same-name source/baseline models cannot alias.
- V2.5.6.8 delivery layouts migrate compatibly.
- Baseline creation and copy-version recursively preserve the entire delivery tree, including arbitrary nested user data.
- Rebinding, rename and reclassification reuse verified whole-tree copy/move helpers.
- Hub inventory scans the physical delivery folder recursively; manifest fingerprint only marks generated files current/stale and never hides physical files.
- Nested delivery files are downloadable through the existing artifact channel.
- Server 2.5.6.9; Client remains 0.3.4.

_归并来源：`CHANGELOG_2.5.6.9.md`。_

## V2.5.6.8

- Fixed Web Gantt segment editing forcing relative start mode back to absolute/direct mode.
- Fixed undo/redo refresh crash caused by stale `lifecycleStatus` reference.
- Motion segment expanded variable panel now shows resolved numeric values with schedule fallback.
- Local NX AFU and animation HTML export no longer auto-download to Downloads; users choose a save path through the browser file picker.
- Added “保存交付” beside NX AFU generation and animation reload, reusing the existing delivery folder and manifest flow.
- Reduced offline animation export workload/size by capping interpolated HTML sampling at 20 Hz and 2400 frames.
- Server version updated from 2.5.6.7 to 2.5.6.8; Client remains 0.3.4.

_归并来源：`CHANGELOG_2.5.6.8.md`。_

## V2.5.6.7

### Changed

- 结果查看的“曲线对象”中，每个关节只保留一个不带后缀的本体条目。
- 删除同一关节重复出现的“· 位移”“· 速度”“· 加速度”三个对象选项。
- 速度/加速度分析仍通过现有曲线“运算”下拉中的 `d1/d2/d3` 完成，不删除底层仿真数据。

### Compatibility

- V2.5.6.6 已保存的 `joint:<id>:position|velocity|acceleration` 在前端解析和 NX AFU 导出时统一兼容为 `joint:<id>`，避免升级后旧坐标系变空。

### Architecture

- 新增 ProjectSpec 字段：0。
- 新增前端持久变量：0。
- 新增 Tool/API/Job/工件类型：0。
- Server 2.5.6.7；Client 0.3.4。

_归并来源：`CHANGELOG_2.5.6.7.md`。_

## V2.5.6.6

### Fixed

- 修复后台仿真完成后曲线先出现、随后因 `latest-simulation` 瞬时读取失败而被清空的问题。
- 恢复 V2.5.3 的结果刷新语义：已有有效 `job.result` 时，刷新失败不得降级为无结果。
- 修复签出态因结果被清空而无法导出单轴/批量 CSV。
- 修复签入态 NX AFU 导出被中央项目写权限错误拦截。
- 修复签入态桌面批量 CSV 导出 POST 被中央项目写权限错误拦截。

### Architecture

- 新增 ProjectSpec 字段：0。
- 新增前端持久变量：0。
- 新增 Tool/API/Job/工件类型：0。
- 复用 `state.latestSimulation`、`latest-simulation`、现有 CSV/AFU 导出端点与 `temporary_delivery`。
- Server 2.5.6.6；Client 0.3.4。

_归并来源：`CHANGELOG_2.5.6.6.md`。_

## V2.5.6.5

### Fixed

- 修复 V2.5.6.4 中只读态曲线选择约一个事件轮询周期后被权威 `/state` 镜像覆盖，表现为曲线“出现一瞬间又消失”。
- 新增仅前端运行时的 result viewer curve override；后台事件刷新不再冲掉只读查看选择。
- 下拉、Canvas、结果甘特图和 CSV 统一通过有效曲线源解析入口，避免显示状态与绘图数据不一致。

### Architecture

- 新增 ProjectSpec 字段：0。
- 新增持久 UI 字段：0。
- 新增 Tool / API / Job / 工件：0。
- 新增前端临时变量池：`state.resultViewerCurveOverrides`。
- Server 2.5.6.5；Client 0.3.4。

_归并来源：`CHANGELOG_2.5.6.5.md`。_

## V2.5.6.4

### Fixed

- 修复仿真结果查看中坐标系“曲线对象”下拉受通用工程编辑权限门禁影响，导致曲线无法正常切换的问题。
- 签入/基线只读态现在允许本地切换结果曲线用于查看，不写回项目权威状态。
- 签出且拥有编辑权时，曲线选择继续复用现有 `result_layout` 持久化与交互提交链。

### Architecture

- 新增 ProjectSpec 变量：0。
- 新增 Tool / API / Job / 工件：0。
- 仅扩展现有前端结果查看权限投射，不建立平行结果状态。
- Server 升级至 2.5.6.4；Client 保持 0.3.4。

_归并来源：`CHANGELOG_2.5.6.4.md`。_

## V2.5.6.3

- 闭链设置移动到 `root` 层级属性页，普通层级仅保留自身建模属性。
- 从动运动副改为全屏层级树多选，带勾选反馈、关闭后的已选摘要，并增加自适应选择。
- 闭链两个端点对应 layer 在左侧层级树名称后显示 `——>闭链名称`。
- Pure Dynamic 模式扩大浅绿色视觉覆盖到层级建模与驱动设置的主要背景区域。
- 项目数据根目录增加部署平台判断：Windows 继续使用 `E:\\Mujoco_Project`；Linux 使用 `Server/run.py` 同目录下的 `V2_projec`。
- Server 版本升级到 2.5.6.3；Client 保持 0.3.4。

_归并来源：`CHANGELOG_2.5.6.3.md`。_

## V2.5.6.2

### Viewer 低延时测距

- 默认模式新增 `低延时20Hz`，每个测距对最多查询 4096 个代表性源点。
- 所有测距对共享约 20000 点实时总预算，测距对增多时自动降低单对预算，避免总耗时无限线性增长。
- 被查询一侧的 geom-local `cKDTree` 仍包含完整采样点；实时模式只限制主动查询点。
- 多个测距对使用有界线程池并行计算。
- 单个 KDTree 查询固定 `workers=1`，避免每个 geom 组合重复创建全核线程池。
- 保留 `完整精确` 模式；离线导出和同步调用默认仍走完整采样点精确路径。
- Viewer 分别显示实际完成频率、单轮计算耗时和结果姿态年龄。
- 后台仍使用单槽最新姿态覆盖，不积压旧请求。

### 兼容性

- Server：2.5.6.2。
- Client：0.3.4；Viewer Bundle Schema 4 不变。
- ProjectSpec、业务 API、权限、资产和电机控制协议均未改变。

_归并来源：`CHANGELOG_2.5.6.2.md`。_

## V2.5.6.1

### Viewer 实际测距吞吐优化

- 默认目标仍为 20 Hz；频率选择仍支持 `5 / 10 / 20 / 30 / 60 Hz`。
- 非 site 点云后端不再每轮将完整两侧点云变换到世界坐标，也不再每轮重建 `cKDTree`。
- 为每个 geom 在局部坐标系中建立一次固定 `cKDTree`；每轮仅计算 geom 相对变换并查询固定树。
- 多 geom 测距对逐 geom 组合搜索并取全局最小值，保持现有离散采样点精确最小距离语义。
- 点云显示使用每侧最多 2500 个稳定采样点；完整采样点仍参与测距，不降低测距点数。
- 后台线程继续使用单槽最新姿态覆盖机制，拖动电机时不会积压旧请求。
- Viewer 新增结果延迟显示：`实际 Hz / 设定 Hz / 延迟 ms`。

### 兼容性

- Server：2.5.6.1。
- Client：0.3.4；Viewer Bundle Schema 与现有协议不变。
- SciPy/cKDTree 仍为 Client 必需依赖。
- 无 ProjectSpec、业务 API、资产或电机控制协议变更。

_归并来源：`CHANGELOG_2.5.6.1.md`。_

## V2.5.6

### Viewer 测距刷新

- 保留 V2.5.5 推荐优化架构：测距在私有 `MjData` 后台线程执行，HTTP 控制轮询异步化，渲染主线程使用正确的 60 FPS 剩余时间限速。
- 默认测距提交频率从 10 Hz 提高到 20 Hz。
- Viewer 控制面板新增“测距刷新频率”入口，可选择 `5 / 10 / 20 / 30 / 60 Hz`，切换后立即生效。
- 控制面板同时显示设定频率与后台实际完成频率，便于判断机器是否能跟上 30/60 Hz。
- 后台工作线程保持单槽“最新姿态优先”语义；计算未完成时，新姿态覆盖旧的待处理姿态，不形成积压队列。
- `mj_forward()`、`viewer.sync()` 与动画时间轴继续按正常渲染帧运行，不通过降低姿态刷新率换取测距性能。

### 兼容性

- Server：2.5.6。
- Client：0.3.4，协议与 Viewer Bundle Schema 4 不变。
- Client 继续要求 SciPy/cKDTree，以避免大规模点云进入 NumPy `O(NM)` 精确回退。
- 无 ProjectSpec 字段、业务 API、Tool、Job 或资产生命周期变更；刷新频率是当前 Viewer 会话的本地设置。

_归并来源：`CHANGELOG_2.5.6.md`。_

## V2.5.5

### 生命周期 / 撤销 / 分页
- `project.lifecycle` 事件继续进入审计事件流，但从通用 undo/redo 候选中排除；签入签出必须通过显式生命周期命令，避免只逆放状态 diff 而遗漏租约/会话副作用。
- Hub 签入和签出都不能跨过仍打开的模型分页；关闭分页继续复用 `edit-session/leave` 完成保存、后台任务延迟签入和租约收敛。
- 权威事件刷新和撤销/重做后新增分页模式 reconciliation：若 persistent/temporary 与权威生命周期冲突，立即移除陈旧分页并回到 Hub。
- undo/redo 后使用 `/state` 返回的权威 cursor，并同步项目摘要、质量属性及 Hub 预览。

### 动力学 / 运动学 / 调试与寻优隔离
- 保持 `solver_mode` 作为 kinematic/dynamic 唯一权威分流，不新增平行仿真状态。
- 快速寻优与 Viewer quick-result preview 继续使用既有 L3 scratch。
- 标准批量优化入口补强为 `scratch_project(project)`。
- Viewer 人工电机 `manual_values/decoupled` 继续只在 Viewer 本地控制缓存中更新，不写 `project.variables`。

### Architecture
- 新增 ProjectSpec 变量：0。
- 新 Tool/API/Job：0。
- 复用 `project.lifecycle`、`EventStore/CommandBus`、`edit-session/leave`、`scratch_project()`、现有仿真/寻优/Viewer 通道。

### 版本
- Server/runtime/frontend/cache key/Viewer/animation export：2.5.5。
- Client：0.3.4（协议未变）。

_归并来源：`CHANGELOG_2.5.5.md`。_

## V2.5.4

### 本轮修复

- Viewer 撒点启动进度继续复用现有子进程日志投射，前端显示对象数、点数与百分比，并保留既有终止入口。
- 大规模撒点将“完整测距点云”和“60Hz 显示点云”分离。测距仍使用完整点集；Viewer 只绘制稳定缓存子集，避免 10,000 点规模在每帧重复构造全部 mjvGeom。
- 虚拟映射源驱动（`joint_id == ""`）不再被引用修复逻辑自动删除，即使暂时没有 follower 也会保留。
- Viewer 电机解耦模式允许映射源和映射伴生驱动分别进入独立 decoupled override，不再强制全部回溯到非映射根驱动。
- 结果查看的关节曲线源补充位移/速度/加速度选择，同时保留旧 `joint:<id>` 布局兼容键。
- 打基线不再篡改工程师可见的模型名称；基线身份由独立 project id、生命周期、source_project_id 和版本元数据区分。
- 打基线冻结当前 assets / outputs / results / core artifacts，并记录 `baseline_frozen_assets` 审计清单。
- 每个基线使用独立交付目录；打基线时复制甘特图 PNG，并尽可能自动生成/覆盖动画 HTML 与坐标系 Python（NX AFU）脚本。
- 动画导出工具、Web 静态资源缓存键、Viewer 标题和后端应用版本统一更新到 2.5.4。

### 验证

- Python `compileall`：通过。
- 前端 `node --check frontend/app.js`：通过。
- V2.5.4 版本号检查：通过。
- 基线创建不修改 `project.name` 静态检查：通过。
- 虚拟映射源无运动副保留逻辑：通过。
- 原测试集受当前构建环境缺少 `passlib` 影响；使用测试专用 PBKDF2 stub 后，定向 Viewer/映射/动画测试运行到 10 项通过、1 项失败。失败项是既有 Viewer 测试对两个平移后仍有重叠区域的随机表面点云断言“最近距离必须严格为 3mm”，与当前表面最近点语义不一致；未将该项记为通过。

_归并来源：`CHANGELOG_2.5.4.md`。_

## V2.5.3

### 大规模撒点 / Viewer 启动
- 重写距离表面撒点热点：删除 10k+ 点时昂贵的 Python 泊松拒绝循环，改为 NumPy 向量化面积加权重心撒点。
- 曲率突变点改为“曲率值从高到低”的有限预算优先采样，最高曲率先进入点集，再逐步覆盖次高曲率；避免拐角处理吞掉大规模撒点预算。
- 当每对象撒点上限 > 4000 时直接使用向量化缓存后端，跳过 MjSpec 大量 site 注入及第二次编译，消除 Viewer 启动的超线性等待。
- Viewer 子进程输出真实 `MUJOCO_STUDIO_SAMPLING_PROGRESS done/total points` 与 `MUJOCO_STUDIO_VIEWER_READY`。
- 前端进度条使用真实对象数/已撒点数；只有 READY（窗口进入可显示阶段）后才结束。
- 新增管理员本机 Viewer 和 Client Viewer 的“终止撒点 / Viewer 启动”。
- MuJoCo View 前自动刷新一次甘特图 PNG 缓存。

### 模型中心 / 生命周期
- 未分类统一显示/保存为 `None`，兼容读取旧 `未分类` 值。
- 禁止在 `None` 下创建子分类。
- 删除任意模型分类改为管理员权限/管理模式；`None` 可删除，但必须同时删除其中模型，随后自动恢复空的系统 None 桶。
- 顶层“全部模型”改为“项目”；管理员可点击项目名称修改显示名称。
- 生命周期切换前主动清理同会话残留的 ephemeral 临时编辑内核，修复退出签入模型临时编辑后无法签出的报错。
- 关键数据不再改写 `project.name`；只生成 `delivery_name_suffix`，动画 HTML 和 Python/NX 交付文件名才拼接关键数据。

### 结果查看
- 新增权威项目目录 `latest-simulation` 读取接口，签入模型临时编辑也读取真实后台仿真结果，不再因临时 workspace 为空导致曲线下拉无数据。

### UI
- 层级建模左上角去掉“层级树”标题，仅保留模式切换和“＋层级”。
- Kp/Kv 从驱动标题行移入“动力学控制参数”折叠区，并说明 Kp=位置误差比例增益、Kv=速度误差阻尼。
- 单列运动段参数改为自适应网格；映射按钮中间文案统一为“映射”，“伴生行程”标签缩小。
- 动力学模式在层级建模和驱动卡片加入克制的绿色边线/状态提示。
- 动画 HTML 导出前、MuJoCo View 前后台刷新甘特图 PNG 缓存。
- 仿真结果左侧设置压缩纵向空间，更多仿真参数/动画 HTML/甘特图折叠按钮统一为相机折叠样式。
- 多对象测距选择增加 focus/checked 高亮和边框反馈。

_归并来源：`CHANGELOG_2.5.3.md`。_

## V2.5.2

### UI / 总览
- 全局 checkbox 统一为方形；错误 Toast 提升到最高层并移至顶部。
- 模型属性按钮压缩为单行高度，数模资产去除第三行状态灯；关键数据下移，甘特图保留快速预览与放大。
- 模型名称标签和输入框同行；存档过程版本常规字重，签入版本加粗。
- 模型类型摘要优先选择时间最新的基线用于甘特图/交付预览。

### 层级建模
- STL/OBJ 文件下拉最小宽度缩短约 1/4，透明度最小宽度约减半，并增加碰撞控件间距。
- 曲柄特殊副改为单行横向滚动；矢量最小 10ch，其余主要字段最小 20ch。

### 驱动 / 测距
- 快速寻优工作流与步骤容器增加横向滚动；参数模式下拉显示宽度翻倍。
- 自定义变量移动到“驱动与时间曲线”标题区右侧；新增测距对不写入自定义变量。
- CSV 批量导出改为 UTF-8-SIG，兼容 Windows/Excel 中文内容。
- 测距字段单行横向布局；对象选择默认单击多选/反选并增强选中高亮。
- 大规模测距采样超过 4000 个采样点/对时不再注入海量 MjSpec sites，回退既有向量化 buffer 后端，避免 10000+ 点编译卡死。

### 结果 / Viewer
- “显示甘特图游标”移入甘特图折叠 UI。
- 仿真提交明确显示成功 Job ID 或失败原因，并复用顶部进度/停止任务控制。
- NX AFU 导出不再因仿真 provenance 与当前资产指纹漂移误判；仅在层级树实际引用数模文件缺失时阻止。
- Viewer 播放控制顺序统一为 `<< < > >>`。

### 基线冻结
- 打基线时冻结复制当前 assets、outputs、results、core/artifacts 到基线自有项目目录。
- 已生成动画 HTML / NX Python 脚本复制到基线独立交付目录；最新甘特图缓存同时固化为基线交付 PNG。
- 动画 HTML 继续沿用现有导出时自动写交付目录机制，后续同名覆盖；不同基线使用各自交付目录。

### Architecture
- 新增 ProjectSpec 变量：0。
- 新增业务 Tool/API/Job：0。
- 复用 simulation Job、统一 progress/cancel、animation_html_export、gantt-cache、result.get_latest、资产/交付目录机制。

_归并来源：`CHANGELOG_2.5.2.md`。_

## V2.5.1.4

- Animation HTML: stop reconstructing model pose from commanded drive/joint offsets. Export now generates the same MuJoCo `trajectory.npz` contract used by native Viewer and replays qpos from that trajectory.
- Dynamic replay: HTML now preserves gravity, contact, passive/free-joint motion and dynamic `equality/connect` closure effects, including natural leg droop.
- Kinematic replay: HTML now preserves closure-solved qpos rather than replaying only commanded joints.
- Distance parity: HTML reuses native Viewer's distance-pair surface sampler and `_measure_pair` nearest-point semantics, including the same animation spacing, bounded point budget and corner-angle settings.
- Measurement correctness: remove the 9-frame weighted smoothing of physical distance values/endpoints. Only floating label screen position remains visually smoothed.
- Trajectory interpolation: extract shared load/validate/sample helpers and use the same clamp + linear qpos interpolation in Viewer and HTML.
- Client remains V0.3.3; no ProjectSpec field, API, role, lease, asset-lifecycle or Viewer bundle schema change.

_归并来源：`CHANGELOG_2.5.1.4.md`。_

## V2.5.1.3

V2.5.1.3 针对“Pure Dynamic 看起来完全无驱动”补齐驱动运行时闭环与缓存失效契约。

- Dynamic 每个物理步使用 `mj_step1 -> Studio drive target 写入 data.ctrl -> mj_step2`，把驱动注入明确放在 MuJoCo actuation 计算之前。
- 控制索引严格使用编译后的 actuator id；joint/qpos/actuator 三个索引空间不混用。
- 新增完整 `run_dynamic_simulation()` Fake MuJoCo 端到端回归，不再只测试控制助手函数。
- Client Viewer Bundle 不再复用由旧 Server 版本生成、但项目 fingerprint 恰好仍相同的 simulation trajectory；跨版本自动重算。
- V2.5.1.2 closure、V2.5.1.1 range、V2.5.1 actuator range/unit/passive-DOF 语义全部保留。

Client 协议和 Viewer Bundle Schema 不变，Client 仍为 V0.3.3。

_归并来源：`RELEASE_NOTES_2.5.1.3.md`。_

## V2.5.1.2

- 修复 `kinematic_closure_missing_joint_map`：运动学闭链 runtime 不再把 inactive / 已删除 / 不支持的旧 `solve_joint_ids` 直接送入 MuJoCo joint binding。
- 新增闭链引用项目校验：enabled closure 的端点必须位于存在且 active 的层级；Pure Kinematic 至少需要一个 active 的 rotation/translation 从动运动副。
- stale / inactive / crank solver 引用在存在其他有效 solver joint 时降级为 warning，并在生成的 kinematic runtime payload 中剔除，禁止 Viewer 运行期才崩溃。
- Pure Dynamic 的 closure 继续编译为 MuJoCo `equality/connect`；`solve_joint_ids` 仅属于运动学 DLS solver，不作为 Dynamic 的阻断条件。
- 前端闭链“从动运动副”只展示 active layer 的 rotation/translation joint；层级取消激活或 joint 改为 crank 时同步清理失效闭链 solver 引用。
- Direct ProjectSpec fallback 与正式 XML generator 的 active-layer 语义统一，避免测试/兼容路径产生不存在于 MJCF 的 joint map。
- 新增 V2.5.1.2 定向回归；闭链 + V2.5.1.1 range + V2.5.1 dynamic + motion/legacy-closure 相关隔离回归 40/40 通过；Client V0.3.3 9/9 通过。

_归并来源：`CHANGELOG_2.5.1.2.md`。_

## V2.5.1.1

V2.5.1.1 修复一个会同时影响 Pure Kinematic 与 Pure Dynamic 的共用校验 bug。

### 修复内容

`validate_project()` 过去无条件要求所有 `JointSpec.range` 满足 `lower < upper`。这与 V2.5.1 已确立的 `limited` 契约不一致：当 `limited=false` 时，range 不进入 MJCF joint limit，也不进入 dynamic actuator ctrlrange，本应只是未启用的保存值。

现在：

- `limited=true`：range 必须是两个 finite 值且 lower < upper，否则继续阻断；
- `limited=false`：无效保存值仅产生 `inactive_joint_range` warning，不再阻断 Viewer/XML；
- Pure Dynamic unlimited actuator 继续明确使用 `ctrllimited=false`；
- Web 两个范围输入编辑期间的暂时无效状态不再被 autosave 持久化。

### 兼容性

- Project schema：不变；
- Tool/API/Job：不变；
- Viewer Bundle Schema：4，不变；
- Client：V0.3.3，不变；
- V2.5.1 dynamic actuator / passive DOF 行为：不变。

_归并来源：`RELEASE_NOTES_2.5.1.1.md`。_

## V2.5.1

### 定位

V2.5.1 是 V2.5.0 Pure Kinematic / Pure Dynamic 架构上的通用性修复版。重点不是新增第三种求解模式，而是消除 Pure Dynamic 对某个参考 XML 写法的隐式依赖，让运动副范围、驱动参数和无驱动自由度回到统一项目状态语义。

### 修复内容

- 运动副范围值在两种求解模式下始终可编辑；“范围”复选框只控制是否实际限位。
- 动力学生成器不再把示例 XML 中大量 `range="-1 1"` 和 `inheritrange="1"` 当成 Studio 规则。
- limited 动力学运动副的 position actuator 使用当前项目范围生成显式 `ctrlrange`；unlimited 运动副显式 `ctrllimited="false"`。
- 旋转副 MJCF joint range 保持 UI 的度制输入，但 actuator 控制边界按 MuJoCo 运行时弧度生成；移动副/曲柄生成的 slide 控制量继续使用米。
- Dynamic Kp/Kv 继续来自 `DriveSpec.dynamic_kp/dynamic_kv`，不会被参考 XML 的 `kp=100` / `dampratio=1` 固化。
- 动力学控制写入统一收敛到同一 helper，继续使用 `data.ctrl + mj_step()`；运行时不把目标位置直接写入 `qpos`。
- enabled 物理驱动若没有真正绑定到生成的 MuJoCo joint 或 actuator，会报 `dynamic_actuator_binding_failed`，不再静默无效。
- 无 enabled 驱动的动力学运动副不生成隐藏 actuator，继续允许重力、碰撞、惯性耦合及被动力驱动的自由运动。

### 架构与兼容性

- 不新增 ProjectSpec 字段。
- 不新增业务 Tool / API / Job。
- Project Schema 仍为 5。
- Viewer Bundle Schema 仍为 4。
- Client 仍为 V0.3.3，无需客户端迁移。
- 旧 V2.5.0 项目直接读取；没有数据迁移步骤。

### 关于参考 XML

用户提供的 QX XML 继续可作为 MuJoCo 功能参考，例如 hinge/slide、equality、position actuator、阻尼、摩擦和碰撞设置。V2.5.1 明确禁止把其中具体的 `range`、gravity、gain 或 `inheritrange` 写法提升为 Studio 的隐藏固定规则。

### 验证边界

本构建环境完成了生成器、单位转换、动态控制、绑定失败、前端编辑可见性、Python 编译和 JavaScript 语法的定向回归。构建环境未安装真实 `mujoco`/`passlib` 且无网络补装，因此真实 `mj_step()` 与完整认证 pytest 仍列为目标机放行项；详见 `docs/TEST_REPORT_2.5.1.md`。

_归并来源：`RELEASE_NOTES_2.5.1.md`。_

## V2.5.0

### 定位

V2.5.0 是基于 V2.4.6.0 重新建立的 **Pure Kinematic / Pure Dynamic 双模式架构版**。本版本号不继承历史 Hybrid Dynamics V2.5.0 的实现含义。

### 架构规则

- 项目级 `solver_mode`: `kinematic` / `dynamic`，同一项目不允许层级级 K/D 混合。
- 运动学模式：直接求关节位置，必要时运行 DLS 运动学闭链，只调用 `mj_forward()`，不考虑重力、惯性、摩擦与接触力。
- 动力学模式：驱动目标进入 MuJoCo `<position>` actuator，通过 `mjData.ctrl` + `mj_step()` 离线求解；求解循环不强制覆盖 `qpos`。
- 两种模式统一输出 `trajectory.npz`（`times/qpos/qvel/ctrl`）。
- Viewer Bundle Schema 4：Viewer 读取 trajectory，只设置 `qpos` + `mj_forward()`，正常播放不执行 `mj_step()`。
- 电机解耦控制保持纯运动学位置覆盖，不参与动力学求解。

### 建模与 XML

- 动力学模式使用完整 MuJoCo 父子刚体树，不生成 kinematic proxy / mocap target / Hybrid weld boundary。
- 运动副支持阻尼、干摩擦、刚度、自然位置。
- 驱动支持 Dynamic Kp / Kv。
- Collision 支持摩擦系数与 margin（UI 以 mm 表示）。
- 点闭链在运动学模式使用 DLS，在动力学模式生成 equality `connect site1/site2`。
- `Point(x,y,z)` 同时接受中文全角 `Point（x，y，z）`。
- CAD 顶层文件使用 ASCII runtime alias；UI/项目数据继续保留原中文 STL/OBJ 文件名。

### UI / 交互

- “+层级”左侧新增项目级“运动学 / 动力学”滑动开关。
- 删除/隐藏历史层级级“参与动力学”语义；不存在动力学继承复选框。
- 层级属性、闭链、运动副、数模区整体采用紧凑布局。
- 动力学参数只在动力学模式显示。
- 层级页旧“模型文件/扫描路径/场景”常驻工具行移出工作区；MuJoCo View 仍可从全局或仿真页启动。
- 总览删除项目统计条和“智能工作流”快捷按钮；模型导入/导出按钮默认显示文字，建模信息入口保持紧凑。
- 仿真面板默认只显示开始/结束，高级参数折叠。
- Toast 层级提高，不再被顶部导航遮挡。

### Client

- 配套 Client V0.3.3。
- 支持 Viewer bundle schema 4，仍兼容 schema 1/2/3。

_归并来源：`RELEASE_NOTES_2.5.0.md`。_

## V2.4.6.0

Date: 2026-08-14  
Client: V0.3.2 unchanged.

### Source baseline

The supplied archive is named `MuJoCo_Studio_V2.4.5.2_Client_V0.3.2.zip` (SHA-256 `38c709bde0b095d2d99b6a7f24bfd5471a29a4ea3254438b0e2c4097e6f526a8`), while its internal `Server/VERSION`, package hashes, source-zip name and architecture baseline identify Server **2.4.5.1**. V2.4.6.0 is built from the exact uploaded source contents, and this metadata mismatch is recorded rather than hidden.

### Viewer distance-site backend

- Distance surface samples are generated once during Viewer startup and injected into an in-memory `MjSpec` as sphere sites.
- The augmented spec is compiled into the Viewer-only model; the user's generated XML is never rewritten with debug sites.
- Moving bodies automatically move the samples through MuJoCo forward kinematics, and distance measurement reads `data.site_xpos`.
- The global scatter switch uses a reserved, previously-unused site group whenever possible.
- Adaptive per-pair visibility uses site alpha and only writes alpha when the effective visibility changes.
- Distance lines and labels remain in `viewer.user_scn`; the high-count sample spheres are removed from the per-frame decorative-geom loop.
- Existing `_mesh_surface_points`, `_nearest_points` and `_measure_pair` contracts are reused.
- If `MjSpec` is unavailable or augmentation fails, the V2.4.5.x sampled-buffer/decorative path remains available.

### Current MuJoCo asset loading

When installed MuJoCo exposes `MjVfs`, V2.4.6.0 uses it for runtime model/spec virtual assets and keeps the same VFS alive across MjSpec parsing and both compiles. Older MuJoCo installations retain the former asset-dictionary compatibility path.

### Compatibility

- Client remains V0.3.2.
- Viewer bundle Schema 3 remains unchanged.
- No new business API, Tool, Job, project Schema, permission or persistent state is introduced.
- No CUDA/MJWarp dependency is introduced.

### Validation summary

- Server full regression: 239 passed, 3 skipped.
- Viewer/VFS-focused regression: 28 passed, 2 skipped.
- Client V0.3.2 regression: 9 passed.
- Python compileall, frontend JavaScript syntax validation and standalone Schema 3 controller import passed.
- The execution container did not contain a real MuJoCo/OpenGL runtime and could not install one from the network; real Windows MjSpec/OpenGL frame-time acceptance remains a target-machine gate.

_归并来源：`RELEASE_NOTES_2.4.6.0.md`。_

## V2.4.5.1

Companion client: **V0.3.2 unchanged**. Stop the old server before starting this version; two server processes must never write the same data directory.

### What changed

V2.4.5.1 is an integrity patch. In-use project kernels can no longer be displaced by LRU pressure; writes are pinned through the operation or Job lifetime. State persistence and event append now converge as one rollback-capable transaction, and durable JSON writes use unique same-directory temporary files plus fsync/replace semantics. Read APIs no longer expose mutable references to authoritative state. ChangeSet-produced artifacts are real and rollback-cleaned.

Event records now include project and session audit context. The persisted `session_id` value is a 16-character SHA-256 digest of the server session identifier, not the login cookie/token. Historical events remain readable.

Startup now reclaims expired orphan Job, temporary-edit and Viewer workspaces after the configured TTL while protecting active resources. The health endpoint exposes `kernel_inuse`; self-check reports temporary workspace count/bytes/stale count.

### Configuration

- `MUJOCO_STUDIO_FSYNC=1` by default. Disabling it trades crash/power-loss durability for lower write latency and emits a startup warning.
- `MUJOCO_STUDIO_ORPHAN_WORKSPACE_TTL_HOURS=24` by default, minimum 1 hour.

### Known deployment boundary

Windows directory fsync is not reliably available through this implementation. File flush/fsync and atomic replacement still run, but directory-entry durability on sudden power loss is weaker than on POSIX filesystems that support directory fsync. Target-Windows S1-E1/E2/E3 must therefore be executed before production sign-off.

### Validation summary

Container regression: Server 233 passed / 3 skipped; Client V0.3.2 9 passed. The environment lacked real `passlib` and `mujoco`; a repository-external passlib compatibility shim was used only for server test collection. Real Windows/MuJoCo validation was not claimed.

_归并来源：`RELEASE_NOTES_2.4.5.1.md`。_

## V2.4.5.0

配套客户端：MuJoCo Studio Client V0.3.2。升级前必须停止旧服务，禁止两个版本同时写同一数据目录。

### 主要修复

- 工程师 Viewer bundle 升级为 schema 3，直接携带服务端当前 STL/OBJ/MTL/纹理快照，修复“管理员可仿真但工程师报本地数模缺失”。
- 数模资产弹窗改为灰白工业风；比对结果收敛到版本行小字；显示最近一次上传路径；长错误 toast 自适应换行/滚动。
- 顶部分页加入 🔒/✅，活动锁定页灰色、活动解锁页绿色、非活动页白色；只允许横向滚动；打开分页时禁止直接签入。
- 层级页“模型库”改“数模库”，hover 延时 0.6 s；删除层级页本地数模选择入口并补“修复失效引用”说明。
- 驱动区固定微软雅黑和灰白行；映射源可直接选择驱动。被引用的源驱动允许无运动副，并以虚拟标量参与映射，不生成隐藏几何。
- Viewer 恢复映射目标→源驱动逆向控制以及源→伴生正向联动。
- 结果坐标系名称/曲线控件同行，新建坐标系/曲线默认优先驱动曲线；动画 HTML 继续复用并内嵌现有甘特图 PNG。

### 兼容性

- 旧项目的真实 joint 映射无需迁移。新直接驱动映射使用现有 `mapping_source_joint_id` 的 `drive:<id>` 形式。
- Client V0.3.2 可读 schema 1/2/3；Server V2.4.5.0 的新 schema 3 Viewer bundle 要求 Client V0.3.2+。

_归并来源：`RELEASE_NOTES_2.4.5.0.md`。_

## V2.4.4.2

本版复用既有生命周期、资产选择、场景、仿真、甘特图缓存和项目更新工具，没有增加平行业务工具。

变量增量：

- 前端瞬时变量 `modelTabContexts`：按项目 ID 隔离层级选择、展开集合、结果和仿真缓存。
- 运动段字段 `archive_start_time`、`archive_motion_value`、`archive_rate_value`：逐字段关键数据开关。
- 运动段字段 `gantt_travel_input_mode`：记录甘特图使用行程或结束位置的输入偏好。

配置增量：

- `ResultLayout.height` 默认值 80 px，最小值 40 px。
- 服务端场景库首次读取时自动安装自包含的 `default_scene.xml`。

_归并来源：`RELEASE_NOTES_2.4.4.2.md`。_

## V2.4.4.1

- 总览刷新会在隐藏的甘特图弹窗中恢复默认视图后重建缓存。
- STL/OBJ 属性卡拆分“客户端已连接/未连接”和“数模”两个状态灯。
- 顶层模型分页保留编辑状态并支持同时打开多个模型；关闭网页时统一收敛。
- 自动签入改为后台任务安全：关页无任务立即签入，有任务延后；网页挂机 1 小时后签入。
- 新增服务端自包含 XML 场景列表、上传、选择和生成场景合并。
- 运动时间取解析后最晚驱动停止时间。
- 修复数模下拉、运动副方向控件、碰撞/透明度、驱动/运动段配色和结果 CSV 布局。

Client 协议未变化，继续使用 Client V0.3.1。

_归并来源：`RELEASE_NOTES_2.4.4.1.md`。_

## V2.4.4.0

服务端升级到 V2.4.4.0；轻量客户端升级到 V0.3.1。升级前必须停止旧服务，禁止两个版本同时写同一数据目录。

本版复用现有生命周期、`project.asset_selection`、`MeshVersionStore` 与后台 Job。资产名称比对为集合差；同名数模几何相似性建议未来通过可取消后台 Job、网格采样与指纹缓存实现，避免阻塞上传及 UI。

_归并来源：`RELEASE_NOTES_2.4.4.0.md`。_

## V2.4.3.0

- 原生 MuJoCo View 的旋转中心改为场景全部实例化数模的集合包围盒中心。
- 结果页曲线目录为空时，新增坐标系或曲线会自动提交后台仿真并弹窗提示。
- 坐标系右上角恢复旧版“加入甘特图”复选框；位移变化区间自动生成甘特图运动段。
- 导出动画 HTML 前自动在后台载入并刷新甘特图缓存，避免导出文件携带旧 PNG。
- Client 继续使用 V0.3.0，无协议变化。

_归并来源：`RELEASE_NOTES_2.4.3.0.md`。_

## V2.4.2.0

- 驱动工具栏新增“自适应添加”，自动补齐所有未绑定运动副；同层多运动副按“层级1、层级2”命名。
- 缓起缓停支持时间模式与加速度模式，缓起和缓停两侧可独立设置。
- 运动函数“S 曲线”显示名改为“缓起缓停”。
- 自定义变量输入增加字段说明，并压缩输入高度和字号。
- 开始模式改为“相对时间 / 绝对时间”，相对时间允许选择自身驱动，同时排除当前段自身以避免直接循环。
- 驱动卡片支持拖拽排序。
- 复刻 V21.4.6.1 的源头/伴生行程双向映射、说明文本和表达式回填；非单调映射优先最近分支。
- 参数模式及开始、时长、速度、行程输入的最小宽度缩短，并允许随可用宽度伸展。

Client 未修改，继续使用 V0.3.0。旧项目无需迁移；旧 `acceleration_time` 自动作为两侧时间回退值。升级前必须停止旧服务。

_归并来源：`RELEASE_NOTES_2.4.2.0.md`。_

## V2.4.1.1

### 修复与改进

- 缩小基线黑旗和总览模型行高。
- 基线稳定按旧到新排列，最新基线位于最后。
- 模型类型甘特图严格只读，不放大、不跳转。
- 新建模型自动使用当前模型分类。
- 签入模型新增“复制版本”，完整复制配置和项目资产到未分类新模型。
- OBJ/STL 资产弹窗关闭按钮改为 `×`。
- 数模颜色增加“跟随层级”按钮，跟随时禁用色盘并显示叉号。
- 进一步压缩普通轴矢量、世界坐标点和曲柄运动副矢量输入框。

### 兼容性

Client 未修改，继续使用 V0.3.0。旧项目无需迁移。复制版本不携带历史版本、结果或租约。升级前必须停止旧服务。

_归并来源：`RELEASE_NOTES_2.4.1.1.md`。_

## V2.4.1.0

### 变更

- 层级和运动副显示名支持中文；MuJoCo XML 自动使用稳定英文别名。
- 运动副类型改为中文显示，协议枚举保持兼容。
- 新增数模默认不设独立颜色，继承层级颜色；独立颜色优先且可一键清除。
- 压缩名称、坐标、轴矢量和曲柄输入区，并统一运动副/数模区域宽度。
- 双列数模左右等宽，窄屏自动回退单列。
- 层级树增加按顶层分支切换的页签，为后续双模型合并管理预留入口。

### 兼容性

Client 未修改，继续使用 V0.3.0。旧项目显式数模颜色保持原样；本版本不执行项目合并或 Schema 迁移。升级前必须停止旧服务，禁止两个版本同时写同一数据目录。

_归并来源：`RELEASE_NOTES_2.4.1.0.md`。_

## V2.4.0.1

- 修复管理员 STL/OBJ 本地同步仍依赖 Client 的问题。
- 管理员可通过服务端本机目录选择器选择路径，并强制同步为新的数模版本。
- 管理员总览与资产弹窗同步状态默认常绿，显示“管理员直连（无需客户端）”。
- 工程师继续使用 Client V0.3.0 的健康检查、单用途票据和上传流程，协议未变化。
- 直连复制保留 STL/OBJ 配套材质与纹理，并执行符号链接、文件数、单文件和总量限制。

管理员选择的“本机路径”是 Server 所在电脑的路径。远程或无桌面部署无法打开服务端目录选择器时，界面退回浏览器文件夹上传。

升级前必须停止旧服务，禁止两个版本同时写同一数据目录。

_归并来源：`RELEASE_NOTES_2.4.0.1.md`。_

## V2.4.0.0

- 模型类型增加创建者权限边界；其他工程师需进入管理模式才能移动、重命名或删除。
- 基线旗标改为纯黑；基线列表按旧到新排序。
- 取消“归档数据”栏，“名称后缀字段”统一为“关键数据”；时间、距离和角度分别显示 s、mm、°，数值保留一位小数。
- 版本统一为“签入版本 / 过程存档”；过程存档支持日志，版本名附关键数据。
- 总览模型气泡显示最新版本关键数据；模型类型属性显示基线名称+关键数据、最新基线甘特图与交付数据。
- 基线模型进入只读预览；三类模型双击提示按 V2.4 文案更新。
- STL/OBJ 弹窗默认进入最多 5 版的版本预览，提供左侧数模列表和右侧 WebGL 大图。
- Client V0.3.0 健康响应按需返回本地数模名称；总览刷新同时重建甘特图缓存并检测客户端/数模一致性。
- “本地同步”强制产生新资产版本；“比对数模”只报告本地比服务端多出的名称。
- 退出签出模型编辑后待机 180 秒；重新进入取消待机，到期或会话下线自动签入。

升级前必须停止旧服务，禁止两个版本同时写同一数据目录。

_归并来源：`RELEASE_NOTES_2.4.0.0.md`。_

## V2.3.9.10.4

本版本落实 V2.3.9 迭代诊断的阶段 2：可靠作业执行与结果可信链。Client 协议未改变，继续配套 Client V0.2.0。

### 已实现

- 修复 queued Job 已取消后仍会进入 runner 并覆盖为 completed 的竞态。
- Job 新增 `deadline_at`、`cancel_requested_at`、`workspace` 与 `timed_out` 终态；截止后先协作取消，宽限期后封存超时状态，迟到的线程结果不能覆盖终态。
- 仿真、完整优化、快速优化、动画 HTML、Web Viewer 与 Agent 全部复用统一私有 Job 工作区；失败、取消和超时的中间文件不进入正式结果目录。
- 结果目录以微秒 UTC 时间和 Job ID 组成，不再使用秒级共享命名；目录与稳定单文件采用同文件系统原子替换发布。
- 结果目录保留数默认有界为 20，可由 `MUJOCO_STUDIO_JOB_RESULT_KEEP` 调整。
- `provenance.json` 记录 Job、工具类型、应用/MuJoCo/Python 标识、参数摘要以及项目和资产 SHA-256 指纹。
- 指纹排除会话租约、生命周期时间和部署绝对路径；资产采用完整流式 SHA-256，并用有界 stat 缓存降低重复扫描成本。
- 项目预览返回最近仿真结果的 `current`、`stale` 或 `unknown` 状态。正式 NX AFU 导出拒绝旧版本无来源记录或与当前模型/资产不一致的仿真结果。
- 前端轮询识别 `timed_out`，正确解锁按钮、关闭预打开窗口并显示超时原因。

### 明确边界

- Python 原生线程不能被安全强杀。超时任务依赖领域循环检查 `should_cancel`；不响应取消的线程会被封存为 `timed_out`，但可能继续占用一个 worker 直到自行返回。
- V2.3.9.10.4 不改变优化算法、约束模式或快速优化工作流格式，这些属于后续阶段。
- 旧结果没有 `provenance.json` 时按 `unknown` 处理，不会伪装成当前可信结果；重新仿真即可升级结果链。

### 配置

- `MUJOCO_STUDIO_JOB_TIMEOUT_SECONDS`：默认 900 秒。
- `MUJOCO_STUDIO_JOB_CANCEL_GRACE_SECONDS`：默认 5 秒。
- `MUJOCO_STUDIO_JOB_RESULT_KEEP`：每个结果根目录默认保留 20 个目录。

_归并来源：`RELEASE_NOTES_2.3.9.10.4.md`。_

## V2.3.9.10.3

配套客户端：V0.2.0。

### 主要变化

- bundle manifest 升级到 v2，声明最低客户端版本、资产 VFS key 和控制器签名版本。
- 外部资产映射出现时强制使用 MuJoCo VFS；管理员本机 Viewer 的中文生成目录兼容保持不变。
- 管理员 Viewer 每次启动使用 `outputs/viewer/<launch_id>/` 私有快照和日志。
- 服务端 Viewer 注册表绑定 project/actor/launch，带全局和单 actor 上限。
- Viewer 状态端点校验管理员、功能开关与项目绑定；跨项目和不存在 PID 使用同一 404 语义。
- Client 票据绑定原登录 Session/lease，签发限速为每会话每分钟 10 次。
- `/api/client/*` 从前缀豁免改为三个显式票据端点白名单。
- 本地目录选择改用 `select_mesh_path` 专用票据。
- 未匹配 `/api/*` 不再由前端 catch-all 返回 HTML 200。
- SessionStore 增加总量 512、单用户 8 的容量边界。

### 兼容性

- Server V2.3.9.10.3 的 Viewer bundle 要求 Client V0.2.0 或更高版本；旧客户端获得 HTTP 426。
- Client V0.2.0 可读取旧 manifest v1，并使用旧控制器签名；该兼容模式会明确提示旧链路不保证中文资产绝对路径。
- 服务端与客户端版本独立，项目 Schema、角色、租约、存档 20 和资产历史 5 的语义未改变。

### 部署要求

升级前必须停止旧服务。不得让两个服务版本同时写同一项目数据目录。

_归并来源：`RELEASE_NOTES_2.3.9.10.3.md`。_

## V2.3.9.10.2.1

- 修复 Windows 下项目分类或目录含中文时，管理员 MuJoCo View 报 `ParseXML: Error opening file`。
- XML 和 STL/OBJ 资源在中文路径场景下通过 MuJoCo 虚拟文件系统加载，不要求用户重命名“未分类”“新类型”等目录。
- 纯英文路径继续使用原加载方式。
- V2.3.9.10.2 的 Viewer 错误回传、角色权限、数据格式和 Client V0.1.0 协议均不变。

_归并来源：`RELEASE_NOTES_2.3.9.10.2.1.md`。_

## V2.3.9.10.2

### 修复

- 修复管理员点击任一 MuJoCo View 按钮后，Viewer 在启动瞬间异常退出却没有页面提示的问题。
- 管理员启动后短时回查服务端本机 Viewer 进程；MuJoCo/OpenGL/XML/资源路径错误会显示退出原因和最多 80 行日志尾部。
- 实际被点击的三个入口按钮均在请求期间禁用，避免用户误认为未触发而重复点击。
- 状态接口只允许管理员访问；工程师仍通过 Client V0.1.0，游客仍无仿真权限。

### 兼容性

- 数据格式、Client V0.1.0 协议和 V2.3.9.10.1 租约恢复逻辑均不变。
- 升级前必须停止旧服务；禁止两个版本同时写同一数据目录。
- 服务端必须由交互式桌面会话启动才能直接显示本机窗口；无桌面服务器请使用工程师客户端。

_归并来源：`RELEASE_NOTES_2.3.9.10.2.md`。_

## V2.3.9.10.1

- 修复升级或重启后，同一账号因旧 `lease_id` 残留而无法进入编辑的问题。
- 服务启动时自动识别没有活跃 Session 对应的孤儿签出。
- 回收前建立保护存档，随后通过受审计生命周期命令自动签入。
- 保留同账号两个真实活跃登录会话之间的编辑隔离。
- Client V0.1.0 协议和代码版本不变。

升级时必须先停止旧服务进程，再启动 V2.3.9.10.1；禁止两个版本同时使用同一数据目录。

_归并来源：`RELEASE_NOTES_2.3.9.10.1.md`。_

## V2.3.9.10

- 管理员点击 MuJoCo View 时，直接启动运行服务端电脑上的本机 MuJoCo Viewer，无需 Client V0.1.0。
- 工程师维持 Client V0.1.0 本地桥接路径；客户端未启动时提示“本地客户端未启动”。
- 游客禁止 MuJoCo，且只能进入基线模型的只读编辑界面。
- 工程师通过管理员模式密码提权后，可以新增和删除游客/工程师账号，但不能修改管理员模式密码。
- 管理员本机 Viewer 默认启用；无桌面服务器可设置 `MUJOCO_STUDIO_LOCAL_ADMIN_VIEWER=0` 明确关闭，不会开放其他服务器桌面功能。
- Client V0.1.0 协议和版本不变。

_归并来源：`RELEASE_NOTES_2.3.9.10.md`。_

## V2.3.9.9

- Added the server-authoritative localhost client bridge.
- Added one-time task-scoped client tickets.
- Added a bounded five-version mesh stack and rollback-as-new-head behavior.
- Replaced browser playback entry points with local MuJoCo View launch.
- Restricted created accounts to guest and engineer roles.
- Fixed unreliable model-card double-click navigation.

_归并来源：`CHANGELOG_2.3.9.9.md`。_

## V2.3.9.8.2

- Merged the broader WP01–WP05 server deployment work.
- Enforced server-issued lifecycle leases at generic command boundaries.
- Enforced username and lease ownership in Kernel writes.
- Migrated legacy credential fields from project, version and event files.
- Rejected nonexistent managed asset selections.
- Added visible lease-heartbeat failure and recovery feedback.
- Added focused security and migration regression tests.

_归并来源：`CHANGELOG_2.3.9.8.2.md`。_

## V2.3.9.8.1

发布日期：2026-08-09

### 定位

V2.3.9.8.1 是 V2.3.9.8 的服务器安全与资源边界补丁，聚焦 Claude Server Adaptation SPEC 中已复核的 P0（WP-01～WP-05）。不包含巨型文件拆分、WebSocket 重构、容器基建等 P1/P2 大改。

### 主要更新

#### 1. 会话凭证不再进入业务数据

- Cookie `session_id` 与项目签出所有权彻底解耦。
- 新增非秘密 `lease_id`。
- `checked_out_session` 仅作为旧数据兼容字段，不序列化、不广播、不落新事件。
- 启动时自动清除旧项目/版本文件中遗留的 Cookie token，使用临时文件 + 原子替换。

#### 2. 签出租约有心跳与服务端回收

- 编辑/签出会话激活有限 TTL 租约。
- 新增 `/api/auth/heartbeat`。
- 浏览器编辑态自动心跳。
- 浏览器崩溃、断网、Session 过期后由服务端 sweeper 回收。
- 正式编辑复用原有 leave 收口：建立“编辑后的版本”并签入。
- 临时编辑直接销毁临时 Kernel/事件/目录，不污染权威项目。
- 账号删除前也会尽力收敛该账号现有编辑会话。

#### 3. Job 增加所有权和有界保留

- Job 绑定项目、用户名与登录租约。
- 普通用户无法读取或取消其他登录会话的 Job；返回 404 避免枚举。
- 管理员保留诊断能力。
- 增加每登录会话并发上限、全局记录上限、终态保留时间和淘汰。
- 普通用户不再收到服务端 traceback。

#### 4. `mesh_root` 变为服务器所有

- 持久态仅保存项目相对托管路径，如 `assets/mesh_selections/<id>`。
- 任意 PUT、`project.replace`、替换上传 project.json 都不能伪造服务器绝对路径。
- 新增 `project.asset_selection` write 工具；Web 上传后通过 CommandBus 改状态并产生事件。
- 下载/重扫统一验证路径仍在当前项目 `assets/` 所有权边界内。
- 客户端选择新资产统一走认证 Web 上传。

#### 5. 前端能力协商与服务器模式降级

`/api/health` 新增：

```json
{
  "project_storage": "server-managed",
  "lease_ttl_seconds": 180,
  "capabilities": {
    "desktop_enabled": false,
    "native_viewer": false,
    "server_file_dialogs": false
  }
}
```

公共 health 不再返回服务器 `data_root` 绝对路径。

无桌面环境下：

- JSON 导入使用浏览器 file input。
- 模型资产使用 Web upload。
- “打开文件夹”转为 Web 文件视图。
- 批量 CSV 转为浏览器下载。
- 交付文件通过 Web 文件区域查看/下载。
- 桌面端点即使被直接调用，也在最终执行边界拒绝。

### 新增配置

| 环境变量 | 默认 | 作用 |
|---|---:|---|
| `MUJOCO_STUDIO_LEASE_TTL_SECONDS` | 180 | 编辑租约 TTL |
| `MUJOCO_STUDIO_LEASE_SWEEP_SECONDS` | 15 | 回收扫描周期 |
| `MUJOCO_STUDIO_MAX_EPHEMERAL_EDITS` | 32 | 临时编辑会话上限 |
| `MUJOCO_STUDIO_MAX_AUTHORITATIVE_EDITS` | 16 | 正式编辑会话上限 |
| `MUJOCO_STUDIO_JOB_MAX_RECORDS` | 200 | Job 记录上限 |
| `MUJOCO_STUDIO_JOB_RETENTION_SECONDS` | 1800 | 终态 Job 保留 |
| `MUJOCO_STUDIO_JOB_MAX_PER_USER` | 4 | 每登录租约并发 Job |
| `MUJOCO_STUDIO_JOB_WORKERS` | 4 | Job worker 数 |

### 行为变化

- **同一账号的两个浏览器登录不再共享签出写权限。**
- 外部绝对 `mesh_root` 不再被信任；项目外路径会在迁移时失效，需要重新 Web 上传。
- `/api/projects/{id}/meshes/scan` 不再是“任意服务器目录选择器”，只保留显式桌面诊断语义。
- 服务器模式不再向浏览器暴露真实项目根绝对路径。

### 已知未完成项

WP-06～WP-13 仍属于后续 2.3.9.9 工程计划；详见 `SPEC_V2.3.9.8.1_TARGETED.md`。

_归并来源：`RELEASE_NOTES_2.3.9.8.1.md`。_

## V2.3.9.8

本版修复服务器形态下签出/临时编辑仿真回放与文件通道的实际故障，并纠正“存档数据 / 归档数据 / 交付数据”的产品语义。

### Web 回放与动画

- Web 回放不再让多个 Job 共用 `core/web_viewer/generated/`。每个 Job 在私有 `_builds/<id>/` 中生成 `generated_model.xml` / `generated_scene.xml` 等中间文件，成功后才原子发布稳定的 `core/web_viewer/index.html`。
- 因此签出态重复点击/并发生成不会再因为共享中间 XML 出现 `ParseXML: Error opening ... generated_scene.xml` 竞态。
- 签入/基线的临时编辑会话中生成的 HTML 会被 `/artifacts` 列表正确投射为 `temporary_delivery/...`，结果页可以发现、下载和嵌入加载；退出临时编辑后仍按会话规则删除。
- “一键导出动画 HTML”是纯服务器 Job，不属于桌面能力。

### 扫描路径

- Web UI 的“扫描路径”改为调用 `/meshes/rescan`，只重新扫描当前项目已经通过 Web 上传并托管的资产根。
- `/meshes/rescan` 不依赖服务器桌面能力；远程浏览器与服务端本机浏览器一致。
- 旧 `/meshes/scan` 仍作为受控桌面/兼容端点保留，远程客户端不能借新接口探测任意服务器绝对路径。
- 显式扫描继续强制重建当前数模缩略图；普通刷新保持增量缓存语义。

### 存档 / 归档 / 交付数据

- **存档数据**：`versions/` 中最近最多 20 条完整版本。
- **归档数据**：存档数据最新一条的投影，不是另一类文件。
- **基线归档**：创建基线时立即生成唯一、锁定的 `基线归档`；旧版无版本基线首次读取时兼容补建锁定归档，不修改权威 `project.json`。
- **交付数据**：HTML 动画、NX 脚本等。交付数据继续用模型内容指纹判断是否对应当前配置；单纯签入/签出不会让相同内容的交付文件失效。
- 原先用于模型自动命名的变量列表改称“名称后缀字段”，不再冒充存档数据。

### 验证边界

- JavaScript `node --check`：通过。
- Python `compileall`：通过。
- V2.3.9.8 源码契约覆盖：Job 私有构建目录/原子发布、服务器 rescan 权限边界、临时动画工件投射、存档/归档/交付术语和基线唯一归档。
- 当前交付环境未安装 FastAPI、Pydantic、Pytest，因此无法在此环境执行完整运行时 pytest/self-check；不把该项宣称为通过。

_归并来源：`RELEASE_NOTES_2.3.9.8.md`。_

## V2.3.9.7

V2.3.9.7 聚焦数模库的误操作防护与派生渲染成本，同时纠正 Web MuJoCo 可视化的能力边界。

### MuJoCo：结果回放不等于实时调试

- 原 `/web-viewer` 的实现会从当前模型与既定时序生成自包含 WebGL HTML；生成完成后，播放、暂停、倒放、时间轴和相机交互都在浏览器本地完成。
- 该 HTML 不持续持有服务端 `MjData`，因此本版把主 UI 文案明确改为“MuJoCo 回放”，不再称其为实时调试会话。
- 真正的动态调试必须独立建立有界服务端 `MjModel/MjData` 会话，并通过认证双向流把控制输入送到服务端、把 `qpos/qvel/contact` 等权威运行态返回浏览器。V2.3.9.7 将此写入顶层架构约束，但**没有用前端插值伪造 Live Debug**。

### 数模拖拽添加

- 右侧数模库的 STL/OBJ 卡片不再支持单击即加入层级。
- 只有把卡片拖到当前中间层级的“STL / OBJ 数模”区域才会添加；其他区域 drop 无副作用。
- 重复数模、目标层级未选中、当前模型不可编辑等情况均拒绝写入并提示。

### 缩略图增量索引

- 缩略图缓存键由“当前模型资产根 + 相对文件名 + size + modified”组成，避免不同模型目录同名文件串图。
- 会话内最多缓存 256 个已渲染缩略图，命中时直接投射，不再重新下载、解析并 WebGL 渲染 STL/OBJ。
- `renderAll()`、普通模型库刷新和“总体适配”只渲染新增/变化文件；只有显式“扫描路径”会强制重建当前全部缩略图。

### 数模卡片

- 默认高度收窄为 42 px，缩略图显示为 56×38 px。
- 指针连续悬停 1 秒后，卡片高度扩展为 84 px，缩略图扩展为 112×76 px；移出立即恢复。
- 文件名只显示一次；只有嵌套资产才额外显示父目录，修复同一名称重复两遍的问题。

### 验证边界

- `node --check frontend/app.js`：通过。
- Python `compileall`：通过。
- V2.3.9.7 数模拖拽、缩略图增量缓存、1 秒 2× 悬停和 Replay 文案源码契约：通过。
- 当前交付环境未安装 FastAPI、Pydantic、Pytest，因此本轮无法执行完整运行时 pytest/self-check；不把该项宣称为通过。

_归并来源：`RELEASE_NOTES_2.3.9.7.md`。_

## V2.3.9.6

V2.3.9.6 收紧 Hub 生命周期和“归档数据”语义，同时保留 V2.3.9.5 的统一服务器、认证、真实模型目录、编辑会话与 Web Viewer 架构。

### 生命周期

- 签入与基线统一使用会话级临时 Kernel：可编辑、撤销/重做，但不能建立永久版本；退出后临时状态和事件全部删除。
- 临时编辑中的仿真、优化、动画/NX 导出改写到会话临时工作区；不会覆盖正式归档文件，退出随会话清理。
- 签出模型进入编辑仍建立“编辑前初始版本”；退出编辑建立“编辑后的版本”，随后自动签入且不生成重复签入存档。
- 浏览器正常关闭/离开会调用会话收敛端点：该登录会话持有的所有签出都会自动签入；仅在 Hub 签出、未进入编辑的模型也包括在内。

### Hub

- 生命周期表情不再放在动作按钮上，也不写进模型名称：签出显示 `📩🧑‍💻`，基线显示大号 `⚑`。
- 模型名称后新增横向归档数据区，展示当前最新签入态的动画 HTML / NX 脚本。
- 点击模型类型时，右侧递归汇总该类型及子类型中当前所有基线模型的存档数据。

### “归档数据”与“存档”

- `versions/` 中的完整可回退快照继续称为“存档”。
- 动画 HTML、NX 脚本属于“归档数据”，只代表当前最新签入态。
- 签出后配置发生变化再签入时，旧交付文件不会继续冒充当前归档数据；必须针对最新签入态重新生成后才重新出现。

### 兼容性

- REST 项目、认证、真实文件夹和 V2.3.9.5 的 20 条版本上限保持兼容。
- `baseline` 仍不能签出、重分类或永久改写；新增的只是隔离临时编辑能力。

_归并来源：`RELEASE_NOTES_2.3.9.6.md`。_

## V2.3.9.5

### Hub 与编辑生命周期

- 总览升级为独立 MuJoCoHub；领域导航仅在双击模型进入编辑后显示。
- 签入模型使用当前登录会话独享的临时 Kernel：允许配置编辑与撤销，但不能创建版本；退出后临时状态与事件自动删除，不修改 `project.json`。
- 签出模型进入编辑自动存档“编辑前初始版本”，确认退出自动存档“编辑后的版本”。
- 新增版本恢复；回退前自动建立“回退前保护版本”。未锁定存档默认保留最新 20 条。

### Hub 信息架构

- 点击模型类型时右栏显示该真实目录及全部子类型的归档汇总，按时间从早到晚排列，并支持重命名真实文件夹。
- 点击模型时右栏显示模型属性、四类 Web 文件和生命周期操作。
- 登录表单支持 Enter 提交；“签出 🔓”“打基线 📌”恢复直观标识；移除顶部“检查项目”，EVENT 标志缩小。

### MuJoCo Viewer

- Web 端 `MuJoCo View` 不再走原生桌面 PID 通道，而是异步准备浏览器可访问的交互式 Viewer。
- 服务器模式在 `sim.open_viewer` 工具最终执行边界拒绝原生窗口，防止通用命令端点绕过桌面能力策略。
- 本机浏览器和远程浏览器使用完全相同的 Viewer、登录与权限语义。

### 架构

- 更新完整 `architecture_master_prompt_v2.md`，整合 V1/V2，并新增会话级临时编辑、Hub/编辑双层 IA、统一服务器客户端权限、Web 文件通道和远程 Viewer 硬约束与哨兵测试。

_归并来源：`RELEASE_NOTES_2.3.9.5.md`。_

## V2.3.9.4

### 交付目标

V2.3.9.4 把“总览分类”落实为服务端真实目录结构。运行 `run.py` 的电脑统一持有项目文件夹；无论浏览器位于该电脑还是其他电脑，都通过相同的登录、API 和 Web 文件通道访问。

磁盘结构为：

```text
DATA_ROOT/projects/
└── 模型类型/
    └── 子类型/
        └── project_<id>/
            ├── project.json
            ├── assets/
            ├── outputs/
            ├── results/
            ├── versions/
            └── core/
```

### 功能变化

- 左侧“项目分类”改为带文件夹图标的“模型类型”真实目录树。
- 支持创建任意层级子类型；拖拽文件夹可改变父级，也可调整同级显示顺序。
- 将模型拖到类型文件夹时，服务端移动完整模型目录，不只修改标签。
- 总览中的业务对象统一称为“模型”，右侧改为“模型属性”。
- 模型属性按四组展示：`project.json`、STL/OBJ 模型资产、交付产物、其他派生产物。
- 点击文件组打开统一 Web 文件视图；不依赖运行进程所在电脑的资源管理器。
- 新增鉴权保护的模型资产上传通道，支持 STL、OBJ、MTL 和常见纹理，并保留浏览器选择目录内的相对路径。
- 新增当前模型 `project.json` 的下载和替换通道。替换前执行 Schema 校验；模型 id、类型目录和签出所有权由服务器保留，不能由上传文件伪造。

### 迁移与兼容

- 首次启动会把旧的 `projects/<project_id>/project.json` 平铺目录迁移到 `projects/<category>/<project_id>/project.json`。
- 迁移采用同卷目录重命名且可重复执行；成功记录写入 `layout_migration_2.3.9.4.json`。
- 原模型 id、版本、事件、资产、结果和交付产物随整个目录移动，不重建、不丢弃。
- `project_categories.json` 继续作为兼容索引；真实目录是模型类型树的物理投射。

### 安全边界

- 所有新增 `/api/*` 文件端点继续经过统一默认拒绝鉴权中间件。
- 游客不能上传；工程师或管理员也必须先独占签出模型后才能替换 `project.json` 或上传资产。
- 文件名拒绝空段、绝对路径与 `..`；下载端点再次执行解析后路径归属检查。
- 单文件上限 2 GiB、单次资产上传总量上限 8 GiB、`project.json` 上限 20 MiB。
- 源码中仍不包含管理员明文密码，只包含 PBKDF2 哈希；内置管理员 `yu.weigang1` 不可删除。

### 验证

- Python 编译与 JavaScript 语法检查通过。
- 自动化测试覆盖：旧目录迁移、嵌套真实目录、物理移动、同级顺序持久化、非法路径拒绝、OBJ+MTL 上传、资产清单/下载、恶意相对路径拒绝、project.json 服务器字段保护。
- 完整回归：`149 passed`；另有 1 条来自 Python 3.12 `crypt` 模块弃用的第三方 `passlib` 警告，不影响功能或安全断言。
- `scripts/self_check.py` 五阶段自检通过：编译、Demo 校验、MuJoCo 产物生成、轨迹仿真、命令/事件/撤销核心。

### 已知部署边界

- 会话仍为单进程内存会话；进程重启后需重新登录，不支持无粘性多进程横向扩容。
- Web 文件视图提供服务器文件清单与下载，不暴露任意服务器路径，也不尝试打开服务器操作系统的文件管理器。
- 上传是完整请求，不是断点续传；超大资产应在稳定局域网或反向代理已调整请求体/超时限制的环境中上传。

_归并来源：`RELEASE_NOTES_2.3.9.4.md`。_

## V2.3.9.3

本版本在 `architecture_master_prompt_v2.md` 的单一状态权威、命令汇聚、默认拒绝与部署边界下完成
SPEC B（服务端部署与账号权限体系），并保留 2.3.9.1 已验证的事件尾部加载、Kernel LRU 与 SPEC A
生命周期边界。

### 主要改动

- 新增文件账号存储：PBKDF2、大小写不敏感用户名、原子替换、私有文件权限和不可删除的内置 admin。
- 新增内存会话、HttpOnly/SameSite Cookie、12 小时可配置 TTL、登录限流、即时会话吊销和统一 401。
- 所有 `/api/*` 业务端点在应用边界默认拒绝；WebSocket 事件流也独立验证会话。
- 后端完整落实 guest / engineer / engineer+ / admin 权限矩阵；游客列表只投射基线项目，LLM 凭证仅 admin 可改。
- 工程师管理员模式绑定当前会话；管理员修改模式密码后，既有提权会话在下一次请求时自动降级。
- 签出记录用户名与会话标识；不同用户不能覆写或撤销他人工作，同一用户名多标签页可协同。
- 强制签入仅 admin 可用，并先保存签入前版本；整项目写入继续由 CommandBus 锁串行化，避免字段交错。
- 单文件前端加入登录遮罩、统一 401 回登录、角色投射、账号入口与签出者提示，无新增前端依赖。
- `run.py` 在所有电脑上强制进入登录流程，默认监听 `0.0.0.0:8765`；服务端本机浏览器和远程浏览器走同一权限链。
- `run.py` 同时关闭服务器桌面能力，不根据请求来源提供特权；功能差异只由 guest / engineer / admin 账号角色决定。
- 内置管理员为 `yu.weigang1`，默认密码仅以 PBKDF2 哈希保存。
- Docker 明确进入服务器模式、挂载 `/data` 并隔离桌面能力。

### 安全确认与已知边界

- 源码中没有管理员明文密码；测试只使用明确标识的虚假凭证。
- 路由遍历测试确认没有未认证即可访问的 `/api/*` 业务 HTTP 端点。
- B5 独占编辑、强制签入前存档、同账号双会话与并发整项目写入均有自动化测试。
- 内存会话会在服务重启后失效，这是单进程部署的预期边界；当前版本不支持无粘性多进程会话共享。
- 内置管理员的默认凭证可由 `MUJOCO_STUDIO_ADMIN_PASSWORD` 安全覆盖；环境变量未设置时使用源码中的不可逆后备哈希。

_归并来源：`RELEASE_NOTES_2.3.9.3.md`。_

## V2.3.9.1

### 核心优化

- 全量项目替换会在命令总线框架层展开为最深安全叶子 diff；稳定实体列表使用 `@id` 路径，结构变化保守退化为容器 leaf，保持重放与逆放严格等价。
- 事件存储改为 2 MiB 二进制尾读、全局单调游标、默认 100 步撤销窗口及临时文件原子收敛；新增 `scripts/compact_events.py` 维护脚本。
- 工具注册表按 package 全进程共享；工具实例已审计为无项目级可变字段。
- `ToolContext.state` 惰性生成，StateTree 支持私有 shadow 所有权接管；典型 write 命令只做一次全树快照。
- STL/OBJ 体积以绝对路径、mtime_ns、size 为来源指纹缓存，默认最多 256 项并按 LRU 淘汰。
- 项目首屏渲染不再等待 mesh、质量属性、任务、工件、事件和对话刷新；延迟任务逐项隔离失败并用项目 id 与加载序号防止跨项目回写。
- 保存与签入/签出成功后局部更新 Hub 摘要，不再重拉项目与分类目录；失败时在服务器确认前不改变本地摘要。
- 项目列表扫描缓存由所有写路径统一失效；KernelManager 默认最多保留 8 个实例并采用线程安全 LRU。

### 生命周期边界治理（SPEC A）

- 普通 `PUT` 只提交状态树并产生事件，不再隐式生成版本；顶栏「版本存档」显式调用 `POST /api/projects/{id}/archive`，签入则自动补存最终只读快照。
- 版本默认保留最近 10 个**未锁定**存档；锁定版本不参与淘汰。存档元数据以同名 `.meta.json` sidecar 保存 `archived_at/reason/locked/actor`，旧全量 JSON 仍可直接读取。
- 「未存档」徽章与尚未落盘的本地编辑分离：自动提交成功后徽章仍保留，只有手工存档、签入补存档或切换项目才按语义清除。
- 静态字段按 `change` 自动提交，Enter 立即 flush，滑块只在松手 `change` 时提交；400ms 内连续交互合并，所有 PUT 继续经 `saveChain` 串行化。
- 自动提交失败会 toast，并保留本地状态供下一次交互完整重试；只读项目的控件和提交入口均由 `canEditProject()` 拦截。
- 优化与 Viewer 试算统一使用 `scratch_project()` 创建隔离副本，不写事件、版本或权威项目文件。

### 正确性修复

- 未显式选择归档变量时不再把默认运动时长拼入托管项目名。
- 签入项目允许由专用重分类流程更新 `name/category/metadata`，领域配置仍保持只读。
- 命令与事件信封补齐 `actor` 字段，旧事件缺失时兼容为空字符串。

### 数据增长边界

| 路径/结构 | 上限或保留策略 |
| --- | --- |
| `core/events.jsonl` | 默认 100 步窗口；超过 3 倍阈值原子收敛；活跃 redo 目标暂缓淘汰 |
| `versions/*.json` | 默认最新 10 个未锁定存档；锁定存档永久保留；可由 `MUJOCO_STUDIO_MAX_VERSIONS` 配置 |
| mesh volume cache | 进程内 256 项 LRU，来源指纹变化自动失效 |
| live kernels | 进程内 8 项 LRU |
| jobs/artifacts/results/exports | 沿用既有按项目目录管理；本次未改变其保留策略 |

### 兼容性

- REST 既有 URL、method、请求体和响应字段保持不变；只新增显式存档端点及带默认值的元数据/health 字段。
- 旧粗粒度 `path="project"` 事件仍可加载、撤销和重做。
- 不改变 `ProjectSpec`、工具 id、input schema、effect 或前端构建方式，也未新增第三方前端依赖。

_归并来源：`RELEASE_NOTES_2.3.9.1.md`。_

## V2.3.8.4.2

### 修复内容

- 映射电机的甘特图行按源头电机的每个真实色块展开，继承源色块的起止时间位置，并显示映射电机在该区间的起止位置值。
- 映射链会继续追溯到实际源电机色块；结果页、Viewer 甘特图缓存和导出动画 HTML 使用一致的数据规则。
- Viewer 启动时先初始化相机预设，再强制应用并同步正交投影，避免复选框已勾选但首帧仍为透视视角。
- Viewer 正常关窗后不再重复销毁已经关闭的 GLFW 窗口，降低 Windows 原生层 `0xC0000005` 退出风险。
- 若 Viewer 已完成正常退出流程但图形驱动在清理阶段仍返回 `3221225477`，状态接口会保留原生退出码用于诊断，同时不再弹出“异常退出”误报；真正的启动或运行崩溃仍会报告。

### 验证

- 覆盖两个源色块映射为两个目标色块及其起止值的回归检查。
- 覆盖 Viewer 甘特图和导出动画甘特图的数据一致性检查。
- 覆盖正交初始化调用顺序与 Windows 正常关闭退出码判定。
- 通过 Python 编译、JavaScript 语法检查和五项工程自检。

### 兼容性

2.3.8.4.1 的项目 JSON、建模信息 JSON、测距非负规则和既有操作流程保持兼容。

_归并来源：`RELEASE_NOTES_2.3.8.4.2.md`。_

## V2.3.8.4.1

### 紧急修复：动画测距负值

- 对齐一代 V21.4.4 默认行为：未提供“负干涉距离”开关时，动画测距不再显示 MuJoCo 原生负穿透值。
- 实时 Viewer 改用已生成的表面撒点计算非负最近距离与连线；撒点不可用时将原生负值安全归零。
- 导出动画 HTML 默认关闭负干涉模式，并修复撒点不可用时的负值回退。
- 仿真测距曲线、全程最小值、CSV 与快速寻优统一采用非负距离；干涉按 `0 mm` 处理，不会被误判为正间隙。
- 新增回归测试，覆盖干涉状态的撒点测距以及无撒点时的归零回退。

### 兼容性

2.3.8.4 的项目 JSON、建模信息 JSON 与既有操作流程保持兼容。

_归并来源：`RELEASE_NOTES_2.3.8.4.1.md`。_

## V2.3.8.4

### 新功能

- 导出动画 HTML 默认使用正交投影；右上角新增默认关闭的“近大远小”透视滑动开关。
- 原生动画控制窗口在“打开甘特图”右侧新增“截图”，可截取当前 MuJoCo Viewer 窗口并选择 PNG/JPEG 保存路径。
- 总览项目分类支持删除。保留项目时自动转入“未分类”；删除分类及项目时进行二次确认。
- 驱动设置右侧快速寻优工作流宽度缩窄 25%。

### 兼容与界面修复

- 移除对浏览器原生 `structuredClone` 的强依赖，并兼容缺少 `crypto.randomUUID` 的运行环境。
- HTML、CSS、JavaScript 增加版本缓存标识，服务端对前端资源禁用陈旧缓存，确保升级后加载新版附件 UI、白色缩略图和压缩后的驱动段 UI。
- 为不支持 `dvh` 的旧浏览器增加 `vh` 回退，恢复页面纵向滚动。
- 复选框勾选色改为兼容旧浏览器的固定颜色，不再依赖 `color-mix()`。
- 统一为浅色浏览器控件主题，移除依赖系统 emoji 的项目状态标记。
- 缩小右上角运行提示，去除多余留白并让“提示”与内容同行。
- 放大总览附件操作按钮并修复文字溢出。

_归并来源：`RELEASE_NOTES_2.3.8.4.md`。_

## V2.3.8.3

本版本严格基于 2.3.8.2.4 开发，不包含 2.3.8.2.5 的缩略图 Z 轴旋转。

- 项目类别可绑定统一交付根目录，每个项目使用“项目全名_时序”子目录保存动画 HTML 与 NX AFU 脚本。
- 结果查看新增“动画”页，进入该页后才流式加载动画，并显示加载进度。
- 甘特图运动段支持选择起始位置和结束位置作为存档数据；运动总时间默认存档。
- 总览显示可拖拽的存档数据顺序，项目全名自动附加相应值后缀。
- 基线项目固定排列在项目列表底部。
- 甘特图横向缩放下限调整为 30%，内容在可用宽度不足时才横向滚动。
- 甘特图缓存缩略图按图片实际宽高比展示。
- 数模库列表恢复纵向滚动；驱动运动段行压缩约四分之一；变量信息字号增大。
- 全局滚动条轨道背景改为白色。

_归并来源：`RELEASE_NOTES_2.3.8.3.md`。_

## V2.3.8.2.4

### 层级建模缩略图姿态

- 缩略图坐标约定明确采用 Blender 坐标系：Z 轴向上。
- Y 轴观察角设为正方向 `+45°`；从 `+Y` 朝原点观察时，画面表现为顺时针旋转。
- 旋转顺序为先完成 X 轴摆正，再绕摆正后的 Blender 世界 `+Y` 轴旋转。
- 新角度替换旧的约 `-38.4°` Y 轴观察角，不与旧角度叠加。
- WebGL2 实体渲染与二维实体回退继续共用同一姿态常量。

### 继承修复

- 保留 X 轴姿态校正、32,000 面全模型采样、驱动派生时长解析及精简后的运动段编辑行。

_归并来源：`RELEASE_NOTES_2.3.8.2.4.md`。_

## V2.3.8.2.3

### 驱动设置界面

- 移除每条运动段配置行前重复显示的“第 N 段”说明文字。
- 保留最左侧拖拽手柄，运动段仍可按原方式拖动排序。
- 删除文字后参数区域自动前移，单列、双列和窄屏布局不保留空白占位。

### 继承修复

- 保留驱动派生时长分阶段解析、实体数模缩略图、32,000 面全模型采样及 X 轴姿态校正。

_归并来源：`RELEASE_NOTES_2.3.8.2.3.md`。_

## V2.3.8.2.2

### 层级建模缩略图姿态

- 修复右侧模型库缩略图相对动画场景绕 X 轴偏转 90° 的问题。
- 在原始 CAD 网格进入缩略图观察矩阵时施加 `-90°` X 轴校正，再叠加原有的轻微俯视角。
- WebGL2 实体渲染与二维实体回退共用同一组姿态常量，避免不同浏览器显示方向不一致。

### 继承修复

- 保留最多 32,000 个全模型均匀采样三角面、实体光照、大尺寸缩略图以及驱动派生时长分阶段解析。

_归并来源：`RELEASE_NOTES_2.3.8.2.2.md`。_

## V2.3.8.2.1

### Viewer 生成修复

- 修复按速度计算的运动段在定位起始时间时引用自身 `DurationN` 被误判为循环依赖的问题。
- 时长、速度和行程现在会在起始边界解析前注册；因此
  `参考段/end + -驱动名/DurationN` 可以正确表示“在参考段结束时刻完成”。
- 点号别名与旧版斜杠别名继续同时支持。

### 回归覆盖

- 新增 `Fu_Yang`（负行程）与 `XU_NI`（正行程）等价场景，验证两段均可解析且结束时刻与参考段一致。
- 保留真正缺失引用和循环依赖的失败校验。

### 层级建模缩略图

- 数模库缩略图改为与离线动画播放器一致的 WebGL2 实体三角面、平滑法线和方向光渲染。
- 大型 STL/OBJ 从约 900 个碎片面提升到最多 32,000 个全模型均匀采样面，避免只显示文件开头或呈现为点云。
- 放大缩略图和右侧模型库宽度；无 WebGL2 时的二维回退取消三角网格描边，保持实体外观。

_归并来源：`RELEASE_NOTES_2.3.8.2.1.md`。_

## V2.3.8.2

### 项目交付

- 项目预览新增“项目附件”，集中展示动画 HTML 与 NX AFU 脚本。
- 附件固定写入项目目录，命名为 `<项目名>_anim.html` 与 `<项目名>_NX script.py`。
- 新增“打开所在文件夹”，可直接打开完整项目目录进行交付。

### 驱动设置

- 支持 `驱动名.starttime1`、`.endtime1`、`.duration1`、`.speed1`、`.stroke1` 派生变量，并保留旧版斜杠变量兼容。
- 中文驱动名可直接用于上述表达式变量。
- 运动段名称输入框取消；名称固定按当前顺序维护为 `seg1、seg2…`，拖拽、增加或删除后自动更新引用。

### 结果与建模界面

- 坐标系工具栏新增“生成 NX AFU 脚本”，复用 V21.4.4.3.3 的离线 NXOpen journal 模板。
- NX 脚本读取最新仿真结果与当前坐标系配置，支持原值、积分、导数、求和与求差。
- 模型库右侧缩略图改为偏白背景。

_归并来源：`RELEASE_NOTES_2.3.8.2.md`。_

## V2.3.8.1

### 动画 HTML 完整移植

- 将 `mujoco_xml_tool_v21_4_4_3_3_source/ui/animation_html_export.py` 的离线播放器完整引入新版领域层，并保留原始版本标识。
- 导出时自动生成当前 MuJoCo 场景，在后台 Job 中采样逐帧刚体位置/四元数、驱动值及所有有效测距对的最近点；测距同时保留 MuJoCo 原生距离和新版拐角优先表面采样，并在未安装 scipy 时使用分块精确最近点回退。
- 单个 HTML 内嵌网格、法线、索引、动画帧、测距数据、甘特图、水印、CSS 和 WebGL2 播放器，不依赖外网或服务器。
- 保留正放、暂停、倒放、倍速、时间轴、相机旋转/平移/缩放、正交视图、测距对筛选、标签开关、甘特图弹窗/拖动/缩放和甘特图 PNG 导出。
- 仿真页新增“一键导出动画 HTML”及 FPS、单网格最大面数和水印设置；完成后自动打开生成物，也可在“下载物”中再次获取。
- 新增自描述只读工具 `sim.export_animation_html`，HTTP 入口使用现有异步 Job、进度和取消机制。

### 模型库缩略图

- STL/OBJ 经过面拓扑解析、自动居中取景和平滑法线计算后，送入与旧版离线播放器相同的 WebGL2 顶点/片元光照套路。
- 使用共享离屏渲染器逐个真实渲染，再把渲染帧截图到模型卡片 Canvas；WebGL2 不可用时保留 Canvas 回退。
- 缩略图恢复为紧凑的 `76 × 56 px` 显示尺寸，内部以 `152 × 112 px` 渲染保证高 DPI 清晰度。

### 架构说明

- 动画导出读取 `ProjectSpec` 权威状态，不直接修改工程数据。
- 长耗时采样走统一 Job，不创建第二套任务系统；导出物位于项目 `results` 并进入现有下载物列表。
- 旧版代码作为明确隔离的兼容领域模块保留，新版适配集中在 `animation_export.py`，避免旧 Tk UI 状态渗入 Web 前端。

_归并来源：`RELEASE_NOTES_2.3.8.1.md`。_

## V2.3.8

### 快速寻优

- 测距配置的每个测距对增加“边界”字段，快速寻优严格按全程最小间隙大于边界判定。
- 驱动页增加“快速寻优”开关；双击开始/偏移、时长/速度或行程标题即可加入工作流，并高亮对应输入框。
- 时间默认以 0.05 s、平移速度/行程默认以 1 mm、旋转速度/行程默认以 0.1° 离散试探；速度支持减速或加速方向。
- 工作流支持单步执行、顺序执行、结果载入、候选动画预览、一键载入以及 JSON 导入导出。
- 快速寻优复用现有 MuJoCo 模型、测距计算、异步 Job 和 Viewer 工具；每帧从隔离的基线 qpos 赋值，不写回人工动画控制变量。
- 临界搜索返回的约束快照与最终可行结果严格对应；负速度减速在零点停止，不会跨零后反向试探。
- 层级建模模型库使用高分辨率 WebGL 实体缩略图，按 OBJ 面/STL 三角面进行平滑法线、透视投影、三点式灯光、镜面与轮廓光渲染，并提供工作台网格和软阴影；WebGL 不可用时自动回退到 Canvas 面片绘制。

### 兼容性

- 旧项目缺少边界与工作流字段时自动使用 `0 mm` 和空工作流默认值。
- 批量优化入口与原有项目 JSON 保持兼容。
- 合并来源、保留项与 `architecture_master_prompt.md` 逐条审计见 `MERGE_AND_ARCHITECTURE_AUDIT_2.3.8.md`。

_归并来源：`RELEASE_NOTES_2.3.8.md`。_

## V2.3.7.8

- 新建数模、从模型库添加数模以及无模板同族适配默认关闭碰撞；导入 JSON 明确设置的碰撞状态保持不变。
- 数模属性栏新增“总体适配”，按当前层级的数模族去重，并复用既有单族适配接口批量补齐模型。
- 删除“{ } 高级配置”导航和完整项目 JSON 页面，同时移除相关事件绑定。
- 结果坐标系纵轴标题由“值”改为当前坐标系名称。
- 游标数值移动到游标与各条曲线的交点附近，仅显示数值和单位；使用 12px 粗体并增加交点圆点。
- `deg` 及其导数单位显示为 `°`、`°/s` 等形式。
- 页面、API、Viewer 与甘特图弹窗版本统一更新为 `2.3.7.8`。

_归并来源：`RELEASE_NOTES_2.3.7.8.md`。_

## V2.3.7.7

- 层级建模中的运动副类型下拉菜单由 52px 加宽至 104px。
- 驱动段名称、开始模式、参考配置、开始/偏移、参数模式、时长/速度和行程保持在同一行，标签文本不再换行；宽度不足时横向滚动。
- 结果坐标系补齐横轴、纵轴、网格、时间刻度和数值刻度，曲线与游标使用同一绘图区坐标。
- 曲线对象下拉菜单不再在名称后追加“位移”，避免影响旧版 JSON 名称兼容。
- 仿真相机位置与朝向默认折叠；左侧相机和甘特图折叠标题增加常驻颜色背景与边框。
- 页面、API、Viewer 与甘特图弹窗版本统一更新为 `2.3.7.7`。

_归并来源：`RELEASE_NOTES_2.3.7.7.md`。_

## V2.3.7.6.3

- 修复总览项目属性中的甘特图缓存缩略图悬停无响应：悬停 200ms 后显示网页居中的放大预览。
- 放大预览从原缩略图位置移动并缩放到页面中心，过渡时间为 100ms。
- 修复 Web 甘特图色块文字的重复水平偏移，时间文本与行程文本现在始终相对色块左右居中。
- 页面、API、Viewer 与弹窗版本统一更新为 `2.3.7.6.3`。

_归并来源：`RELEASE_NOTES_2.3.7.6.3.md`。_

## V2.3.7.6.2

- 通用事件/撤销/重做/检查/Viewer/保存操作栏紧贴顶层导航，并在内容滚动时保持置顶，不再遮挡页面导航内容。
- 仿真结果页的设置栏与结果栏保持横向排列，甘特图和坐标系页签左右等宽，避免纵向拉伸。
- Web 甘特图和甘特图弹窗统一采用旧版正式软件的 8 色段序色板；历史项目中没有显式自定义标记的颜色自动按旧版色板重新映射。
- API、项目中心、Playback Controller、实时甘特图弹窗和 Viewer 覆盖层版本统一更新为 `2.3.7.6.2`。

_归并来源：`RELEASE_NOTES_2.3.7.6.2.md`。_

## V2.3.7.6.1

- 顶层事件、撤销/重做、检查、Viewer 与保存工具条上移并紧邻导航栏。
- 总览项目名称后恢复签出和基线图标；修复项目卡重绘导致双击无法载入项目的问题。
- 甘特图缓存预览增加 200ms 悬停延迟与 200ms 居中放大动画。
- 模型库缩略图移除 XYZ 坐标轴，仅保留数模实体截图。
- 运动副压缩为严格单行，标签与控件同行并缩短类型下拉框；STL 数模颜色与透明度控件移除可见文字。
- 驱动页保留并明确“双列”复选框；仿真结果的甘特图/坐标系页签改为左右等宽填充。

_归并来源：`RELEASE_NOTES_2.3.7.6.1.md`。_

## V2.3.7.6

### 总览

- 项目卡片仅保留名称/生命周期标识和上次修改时间；双击进入驱动设置。
- 属性即时保存，移除显式保存属性与跳转结果按钮；点击甘特图缓存预览直接进入结果页，悬停居中放大。
- 基线“使用版本”按分类、日期和三位序号生成下一项目名。

### 建模与测距

- 运动副表单改为自适应网格，消除字段堆叠；质量开关并入高级配置同一行。
- 数模选择框加宽，模型库使用带 XYZ 轴、实体三角面和明暗的 STL/OBJ 视图。
- 测距对支持一至两列卡片，对象 A/B 分行显示完整名称；撒点说明移入上限折叠区，删除自适应添加入口和前端调用逻辑。

### 仿真结果

- 普通仿真固定为轨迹快速计算，并保留独立 MuJoCo 接触/间隙验证动作。
- Web 甘特图使用旧版八色调色板、固定 16px 黑色越界文本、无周期竖线；缩放先适配容器，超宽后滚动，关闭游标时支持拖拽平移。
- 双击色块可编辑起始时间、结束行程、速度和颜色，不再提供显示文本输入框。
- 修复回车提交前重新渲染导致输入值回退的问题。

_归并来源：`RELEASE_NOTES_2.3.7.6.md`。_

## V2.3.7.5.2.4

### Viewer 甘特窗口

- 甘特窗口和缓存 PNG 统一使用 `#FBFCFD` 白色背景，消除图片周围的灰色区域。
- 右侧实时数值栏由自适应 120–220px 改为固定 100px，并紧贴缓存图片；数值使用 `***.***mm` 形式，不再在数值和单位间插入空格。
- 底部时间继续使用 `时间：12.345s` 格式，与 100px 数值栏共同约束布局。

### 结果页甘特设置

- 折叠入口删除驱动计数和说明文字，只显示“甘特图设置”。
- “按开始时间排序（未勾选时按本栏顺序）”精简为“按时间排序”，新项目默认勾选。
- 新增排序方向滑动开关，默认“早到晚”，可切换为“晚到早”；关闭按时间排序后仍使用左栏拖动顺序。

### 时间轴一致性

- 结果页甘特图和甘特弹窗的时间上限始终至少等于项目仿真结束时间。例如仿真设置为 12s、最后驱动在 5s 结束时，甘特图仍完整显示到 12s。
- 倒放映射同样以完整仿真时间为基准，不再以最后一个驱动段结束时间截断。

_归并来源：`RELEASE_NOTES_2.3.7.5.2.4.md`。_

## V2.3.7.5.2.3

### Viewer 甘特缓存修复

- Viewer 启动命令新增项目甘特缓存目录参数，直接读取网页甘特弹窗保存的 `latest_gantt.png/json`，不再用系统临时目录中的重新生成图片覆盖用户导出的缓存。
- “导出 PNG”恢复旧版联动：下载图片后同步更新动画窗口使用的项目缓存；“保存到缓存”继续使用同一生成函数和同一份元数据。
- 缓存元数据增加图表边界、逐行中心、运动区间和驱动 ID；Viewer 在内存中补充 241 点实时数值序列，不修改导出的 PNG 或 JSON。
- Viewer 将右侧实时数值放在 PNG 外的独立栏，缓存 PNG 左侧只保留驱动名称宽度和 10px 间隔，右侧只保留 12px 收边。

### 旧版默认预设

- 甘特弹窗顶部恢复“设置为默认”复选框。勾选后保存当前文本类别、字号、粗体、显示状态、文本内容、颜色和位置；取消勾选清除预设；当前配置偏离预设时自动取消。
- 时间文字、行程文字、驱动名称、坐标刻度以及导出 PNG 的文字默认统一为不透明黑色。

_归并来源：`RELEASE_NOTES_2.3.7.5.2.3.md`。_

## V2.3.7.5.2.2

### Viewer 甘特图补丁

- 补齐旧版甘特图缓存的生成端：每次启动 Viewer 都从本次仿真快照生成 `latest_gantt.png` 与 `latest_gantt.json`，通过同目录临时文件和原子替换避免读取半成品。
- 缓存图恢复旧版时间刻度、驱动名称、紧凑轨道、重叠运动段分 lane、色块时间/行程文本以及右侧 260px 实时数值预留区。
- JSON 同步写入逐驱动 241 点 `value_series`；播放、倒放和拖动时间轴时，右侧数值按当前时间插值刷新，活动行红色加粗。
- 甘特弹窗只使用缓存 PNG：在其上叠加蓝色已播放蒙版与游标线，并按缓存坐标完成拖动定位。缓存生成或读取失败时直接显示错误，不再静默回退到新版实时绘图。
- 版本号与 Viewer 窗口标题更新为 `2.3.7.5.2.2`。

_归并来源：`RELEASE_NOTES_2.3.7.5.2.2.md`。_

## V2.3.7.5.2.1

- 将 Viewer“打开甘特图”复选框移动到动画倍速输入框右侧。
- Viewer 甘特弹窗恢复旧版 `latest_gantt.png + latest_gantt.json` 缓存读取协议、等比缩放、蓝色已播放蒙版、游标线、右侧逐行数值和活动行高亮；缓存缺失时使用实时绘制降级。
- 仿真结果查看左栏恢复正视图、侧视图、POV、初始自由相机的位置与朝向配置，并兼容旧的自由相机六值格式。
- 新增 Pillow 运行依赖，用于高质量缩放缓存 PNG。

验证：Python/JavaScript 语法检查、项目五项自检和 Viewer 专项契约检查通过。

_归并来源：`RELEASE_NOTES_2.3.7.5.2.1.md`。_

## V2.3.7.5.2

- Viewer 控制窗口恢复旧版播放、折叠区、视角与实时甘特图交互。
- 删除动画坐标系入口，以及坐标/甘特缩放和字号交互控件。
- 重写正视图、侧视图、POV 与 MuJoCo 实际正交投影切换；原生左右侧栏默认隐藏。
- 人工 Viewer 操作改为进程内缓存，禁止反写变量池；后台变量变化仍可单向反控运行中的动画。
- 每次 Viewer 启动均从 0 秒、暂停、折叠的独立默认态开始。

验证：`scripts/self_check.py` 五项通过；Viewer 隔离与只读反控专项契约检查通过。

_归并来源：`RELEASE_NOTES_2.3.7.5.2.md`。_

## V2.3.7.5

### 建模信息 JSON 互通

- 总览右上角的项目导入/导出按钮下方新增次级“导入建模信息”和“导出建模信息”按钮。
- 新增独立接口：`GET /api/projects/{project_id}/export-modeling-info` 与 `POST /api/projects/import-modeling-info`。
- 使用 `mujoco_modeling_exchange` 2.0 格式，与 MuJoCo XML Tool V21.4.3 双向互通。
- 导出模型名称、STL/OBJ 文件夹、输出目录、层级父子关系、数模颜色/透明度/碰撞/质量、运动副参数、驱动运动段、变量及 latest 驱动包。
- 同时输出旧版 `application_state` 快照，旧版软件可通过其专用建模信息入口直接导入。
- 导入兼容旧版 schema 1.0 和 2.0；优先读取 latest 驱动版本，并保存原始交换文件及暂不支持的运动副字段，避免静默丢失。
- 完整项目导入口会拒绝建模信息文件并提示使用专用入口，防止两种 JSON 类型混用。

### 外观一致性

- 数模 RGBA 与透明度保持为独立字段，生成 MuJoCo XML 时只应用一次透明度，避免跨版本往返后透明度重复衰减。

### UI 密度与可读性

- 参考工业软件的信息密度，将输入框、下拉框、按钮等交互控件统一为 12px；说明文本统一收敛到 10–11px，页面主标题提升到 20px。
- 小型输入框与按钮改用 2px 近直角，大型面板和弹窗保留 8px 克制圆角，减少不必要的卡片化观感。
- 顶部导航、标题栏和面板填充整体压缩，并按动态视口高度约束总览与层级建模工作区，避免常见网页缩放比例下因固定最小高度产生额外纵向滚动。

_归并来源：`RELEASE_NOTES_2.3.7.5.md`。_

## V2.3.7.4

本版本以共同的 2.3.7 基线为参照，合并两条后续迭代分支中可复用的改进，并修正审查中发现的回归。

### 保留与合并

- 保留单一浅色工业主题、紧凑项目中心和简化后的主导航。
- 保留 2.3.7.3 的启动诊断、网络错误说明、甘特图驱动排序、独立甘特图弹窗、PNG 导出与项目缓存预览。
- 保留“使用版本”项目 fork 能力，并移除 fork 后重复加载项目和预览的请求。

### 修复

- UI 默认值现在在项目 UI 状态载入后应用，不再被项目镜像立即覆盖。
- 只有明确标记为 `transient` 的滑块/拖拽中间值不落盘；倒放、缩放和游标最终值会正确记录并持久化。
- 修复总览甘特图“跳到结果查看”使用不存在路由的问题。
- 项目卡双击只进入结果页，不再意外启动本机 MuJoCo Viewer。
- 删除无效的 `window.__renderHubPreview` 包装和从未成立的 `state.page` 事件分支。

### 安全与验证

- 甘特图缓存写入改为严格 Base64 校验、PNG 签名校验、20 MiB 编码上限和 15 MiB 解码后上限。
- 读取不存在的缓存不再创建目录。
- 补充项目 fork、缓存写入、非法数据拒绝与缓存下载回归测试。
- 发布包继续排除 `__pycache__`、`.pyc`、虚拟环境、项目运行数据和凭据。

_归并来源：`RELEASE_NOTES_2.3.7.4.md`。_

## V2.3.7.3

### 修复

- 修复甘特图倒放控件从 `ganttReverse` 迁移到 `ganttReverse2` 后，前端仍绑定旧 ID 而导致启动初始化中断的问题。
- 移除已不存在的旧控件双向同步逻辑，倒放选项现在直接写入 `ui.results.gantt_reverse`。
- 修正甘特图侧边设置栏的默认折叠状态；HTML 中不再使用无效的 `open="false"`。

### 发布整理

- 统一应用、API、Viewer 和 Python 包版本号为 `2.3.7.3`。
- 发布压缩包不包含 `__pycache__` 或 `.pyc` 运行缓存。

_归并来源：`RELEASE_NOTES_2.3.7.3.md`。_

## V2.3.7

### 项目中心

- 所有选中项目都显示“删除项目”按钮，不再只允许从属性区删除基线。
- 基线项目名称后显示 `🏴`，签出项目名称后显示 `📤`；签入项目保持无标志。标志仅是生命周期状态投影，不写入真实项目名。
- Hub 时序甘特图悬停时同时大幅增加横向和纵向空间；变量、曲线及上方项目工作区暂时压缩，为甘特图让出可视区域。

### 层级建模

- 普通运动副的名称、类型、轴矢量、世界坐标点、反向、范围和限制值固定投射为单行。
- 名称与类型宽度约缩短一半，轴矢量缩短至约三分之一；世界坐标点保留主要空间，反向和范围合并为同行复选组。
- STL 双列改为显式两列网格，去除旧版 520/720 px 最小宽度造成的强制单列；每个数模行按是否启用质量字段紧凑分配空间。
- 极窄窗口自动回退为单列，避免控件超出页面。

### 测距与结果

- 折叠后的对象 A、对象 B 改为上下单列摘要。
- 精确间距与动画间距输入进一步压缩，完整含义保留在悬停提示中。
- 撒点说明文字降为极小辅助标记，并保留完整 title 提示。
- 结果甘特图中的运动段和驱动行始终按最早开始时间排序；原排序复选框保留为固定状态提示，不再改变排序结果。

_归并来源：`RELEASE_NOTES_2.3.7.md`。_

## V2.3.6

### 项目中心与生命周期

- 新增持久化项目分类与分类栏内联“＋”按钮。
- 项目默认签入（只读、可预览/仿真/导出）；签出后允许配置写入和保存，但禁止导出。
- 新增 `project.lifecycle` 与 `project.reclassify` 命令工具；UI、脚本和 LLM 的写入都由同一内核权限检查保护。
- 签入且已分类的项目可“打基线”。基线复制原配置、永久只读，并可查看、仿真、导出和删除。
- 基线 JSON 带完整性校验；导入后同时创建永久只读基线和一个可继续签出的签入工作副本。
- 分类拖放统一使用 `分类_YYYYMMDD_00i` 命名。

### 高压缩自适应 UI

- 项目卡悬停改为扩展；甘特图与测距缩略图悬停通过重分配网格空间放大，邻栏自动收缩。
- STL 行按有无质量字段自适应重排；双列不再依赖固定最小宽度，碰撞与适配控件保持在页面内。
- 层级树按深度和名称动态加宽；运动副、数模和驱动段在窄窗口自动回流。
- 驱动段名称、开始模式、参数模式、速度、时长、行程与偏移输入按常用字符数压缩。
- 测距对象默认折叠为已选文件名；展开后使用全窗口双列表，对名称和间距字段做单行紧凑排布。
- 智能助手折叠柄更靠右；展开时顶部操作栏悬浮并向页面中部避让。

### 仿真与测距

- 零时长运动段定义为合法瞬时运动，不再报错。
- 坐标输入兼容 `Point(0, 0, 0)`（大小写不敏感）。
- 测距撒点改为锐边/拐角优先，剩余预算采用泊松盘面采样；每对象默认最多 400 点。
- 结果曲线默认使用深色并在白色画布显示；颜色、对象和原值控件与坐标系名称同栏，移除自定义曲线名输入。
- 甘特图缩放滑块移到左侧控制栏，游标默认隐藏且可显式开启；轨道空白区才响应游标拖动。
- 双击色块打开集中编辑弹窗，可修改起始时间、结束行程、色块颜色和纯显示文本；文本不写回驱动参数。

_归并来源：`RELEASE_NOTES_2.3.6.md`。_

## V2.3.5

### 建模与驱动界面

- 运动副和 STL/OBJ 数模采用等宽、单行、可水平自适应的布局，恢复数模双列复选框。
- 压缩数模文件下拉框和“适配”按钮，消除质量 UI 开启/关闭时的控件重叠。
- 输入框使用更浅底色和更大圆角，下拉菜单使用更深底色和更紧凑圆角。
- 驱动标题改为紧凑单行，运动函数显示在驱动图标右侧。
- 映射电机不再显示无意义的开始时间、时长和行程；映射源与 CSV 导入常驻主行。
- 拖拽调整运动段顺序后，原为 `segN` 的默认名称会自动按新顺序重编号。

### 测距与 CSV

- 表面撒点改为面积加权泊松盘（蓝噪声）分布，不设总点数上限。
- 边界边和法向突变特征边仍独立按间距加密，降低曲率突变处的碰撞漏检。
- 批量 CSV 导出只弹出一次目录选择，后端一次写入全部坐标系 CSV，并覆盖同名文件。

### 全局 LLM 助手

- 所有 OpenAI-compatible 请求都使用流式传输。
- 新增网页右侧可折叠的全局对话栏；回答期间禁用输入与发送，并提供终止按钮。
- 后端建立项目参数与 `ui.*` 状态的稳定路径索引，用于快速检索变量。
- LLM 只能返回 `param.set` / `ui.set` 操作建议。建议先转换为 ChangeSet 并 dry-run，用户点击“审阅后执行”才会经命令总线原子提交，且可撤销。

### Viewer 与甘特图

- 正交视角强制使用自由相机、固定为最近的 `±X/±Y` 方向并锁定仰角，避免鼠标交互后偏离正视/侧视。
- 后端跟踪 Viewer 子进程退出码和日志尾部；异常闪退时网页会显示 Python 错误或原生层退出提示。
- 甘特图游标拖拽忽略运动段色块，避免与双击反向编辑冲突。

### 验证

- Python 源码编译通过。
- JavaScript 语法检查通过。
- 53 项自动化测试通过。

_归并来源：`RELEASE_NOTES_2.3.5.md`。_

## V2.3.4

### 层级建模与驱动界面

- 每个 STL/OBJ 数模固定为一行并横向填满属性面板；窄窗口改为横向滚动，不再压成多行。
- 驱动卡、驱动头和运动段使用分层/交替底色，浅色主题下仍保持清晰边界。
- 运动段主行与高级折叠区分离，展开时主行位置和宽度不再跳动。
- 名称图标成为独立拖拽句柄，修复运动段排序失效。
- 变量信息在浅色主题下使用黑色文本，并明确允许鼠标划选复制。
- 修复运动函数下拉把中文标签写入枚举值造成的校验错误；后端也兼容修复已写入的中文值。

### CSV 映射电机

- 新建映射不再逐点显示或手工增加映射点。
- 从 CSV 导入映射：第一列为源运动副位置，第二列为映射驱动控制的位置；允许表头。
- 映射 CSV 进入项目资源目录，状态树保存文件引用、原文件名和点数；旧 JSON 内嵌映射点继续作为兼容回退。

### 测距与撒点

- 移除旧的 1200 点采样上限，动画间距成为优先保证的密度约束。
- 每个三角面按间距生成确定性网格点；边界边及相邻面法向变化超过 25° 的接缝额外独立加密。
- 新增自适应测距对：汇总无运动副层级作为周边件，排除其直系子层级，为其余有效运动层级自动建立到周边件的测距对。

### 甘特图与 Viewer

- 取消独立的甘特图驱动设置侧栏。双击驱动名称可重命名，输入“删除”只隐藏该驱动的甘特显示。
- 双击色块可编辑起始时间/表达式、行程/表达式和速度；系统切到速度模式逆算结束时间，并同步回驱动状态。
- 甘特游标改为画布内直接拖拽，并在每行显示时间戳及命中色块的插值位置。
- 短色块保持内部干净，只在外侧显示起止时间和位置。
- Viewer 新增“正交视角”，按当前自由相机方位吸附到最近的 ±X/±Y 方向并关闭透视。
- 仿真设置新增 `px,py,pz,dx,dy,dz` 自由相机初始位置/朝向，启动 Viewer 时应用。

所有项目/驱动/Viewer 持久变更仍通过统一命令产生事件，可撤销、重做和追踪。

_归并来源：`RELEASE_NOTES_2.3.4.md`。_

## V2.3.3

### 项目类型与版本

- 项目中心将“分类”作为项目类型，版本按 `项目类型_YYYYMMDD_i` 自动命名。
- 新建时可创建新类型，或从已有类型的当前版本复制为新版本。
- 项目卡可拖到左侧类型完成重分类和重新编号，不再手工填写分类。
- 每个版本可比对同类型前三个版本的电机段起止、时长和行程；配置 LLM 后生成智能总结，也支持用户反馈优化和归档。

### 建模与驱动

- 质量/逆求密度 UI 默认关闭，并收纳到层级折叠区；启用后才显示层级和数模质量字段。
- 映射电机按源运动副位置与映射点进行分段线性插值，进入仿真、结果曲线与原生 Viewer；映射驱动禁止解耦。
- 驱动和运动段重命名会按稳定 ID 级联修复名称型参考；运动段支持拖拽排序。
- 参考模式在主行内选择参考驱动、参考运动段边界。

### 甘特图、坐标系和 Viewer

- 结果页用导航标签互斥展示甘特图/坐标系。
- 甘特图支持横纵缩放、游标、全屏、隐藏/重命名驱动、拖拽排序和按开始时间自动排序。
- 项目中心甘特图和测距曲线自适应容器并在悬停时放大。
- Viewer 默认进入电机控制模式；质心轨迹默认折叠；坐标/甘特缩放控件默认隐藏，勾选后显示。
- 电机滑块先本地实时更新，再合并发送命令，避免网络写事件阻塞拖动；所有持久控制仍通过命令/事件进入全局状态并可撤销。

### 主题

- 补齐浅色主题下输入框、变量信息、坐标画布、子卡片、代码区和弹窗的背景/文字覆盖。
- 浅色交互文字提高字重和对比度。

_归并来源：`RELEASE_NOTES_2.3.3.md`。_

## V2.3.2

### 数模质量与密度逆求

- `MeshSpec.mass_kg` 与 `LayerSpec.mass_kg` 已进入项目状态树，支持保存、加载、版本对比、命令事件与撤销/重做。
- 数模可单独填写目标质量；系统读取封闭 STL/OBJ 体积，按 `density = mass / volume` 逆求 MuJoCo 密度。
- 层级可填写目标总质量。系统先扣除该层级中已单独设置的数模质量，再按其余数模体积分配剩余质量；源文件暂不可读时使用等质量回退，并在校验中提示。
- XML 生成器、动画 Viewer 和“显示质心坐标/质心轨迹”使用同一套解析质量。Viewer 改为按每个 geom 的实际质量加权，不再把同一 body 的质量平均分给多个数模。
- 新增只读工具 `model.mass_properties`，脚本和 LLM 可通过统一工具端点查询体积、解析质量、逆求密度及分配来源。

质量优先级：数模质量 > 层级质量分配 > 默认密度 `1000 kg/m³`。若层级质量小于数模显式质量之和，项目校验和 XML 生成会给出结构化错误。

### mujoco_xml_tool_v20_2 项目兼容

- 项目中心原有“导入项目”入口现在可直接选择 V20.2 JSON，无需预转换或重建模型。
- 已兼容 `root_id/stl_folder/template_scene_path/last_output_dir`、仿真区间、层级树、`file_name/color_text/opacity_text` 数模字段、运动副、驱动与运动段、测距对、自定义变量、优化变量/目标/筛选及旧结果坐标系。
- `target_joint_choice` 按“层级名/运动副名”解析为稳定 joint id；同名运动副不再错误串接。
- 根层级转换为 Studio 的隐式 `root`，避免重复 id；父子关系与激活状态保持不变。
- 全部未知旧字段、旧 UI 设置和驱动版本保存在 `metadata.legacy_source` 等元数据中，迁移不会丢弃原始信息。
- 标准 `/api/projects/import-json` 自动检测旧格式，并在响应的 `migration` 字段报告迁移来源。

### 验证

- 使用随需求提供的 `0720.json` 通过标准导入接口验证：4 个有效层级、6 个数模、5 个运动副、4 个驱动、2 个测距对全部保留。
- 自动化回归覆盖质量逆求、层级质量分配、XML 密度、per-geom 质心权重、V20.2 字段映射与标准导入接口。

_归并来源：`RELEASE_NOTES_2.3.2.md`。_

## V2.3.1

### 总览与项目目录

- 总览时序甘特图改为复用仿真结果查看的技术甘特组件，统一白底、浅灰驱动行、单色运动段及双行时间/位置文本。
- Windows 默认项目根目录改为 `E:\Mujoco_Project`，不存在时在启动阶段自动创建。
- 项目读取和保存使用该根目录；桌面 JSON 导入选择器也默认从该目录打开。
- 总览显示当前实际项目目录。
- 总览 STL 路径增加“选择路径”按钮；选择结果仍写回同一个 `project.mesh_root` 状态节点并通过既有保存命令提交。

### 动画控制窗口

- 甘特图改为接近 Web 技术甘特图的固定行高与色块比例，不再随少量驱动无限拉伸填满窗口。
- 新增“甘特横向宽度”和“甘特纵向行高”滑块，对应可由后端或 LLM 赋值的 `viewer_control` 状态。
- 甘特图支持横向、纵向滚动。
- 每个运动段固定显示开始/结束时间和开始/结束位置两行文本。
- 游标时间及当前驱动位置文本使用红色粗体。
- 跟随时间戳坐标系补齐时间横坐标、数值纵坐标、刻度、网格与红色粗体游标读数。

### 层级与结果交互

- 未激活层级在层级树中显示删除线；其属性区域使用灰色、低饱和度背景投射，但激活开关仍可操作。
- 结果坐标系画布可获得键盘焦点；选中游标后使用左右方向键按仿真采样点步进。
- 键盘步进仍通过项目状态保存产生可撤销事件。

_归并来源：`RELEASE_NOTES_2.3.1.md`。_

## V2.3.0

### 结果与产物重构

- 原“结果与产物”独立导航已移除，改名为“后台任务和下载物”。
- 该区域默认折叠在“智能体”页，减少普通建模流程的认知负担。
- 后台任务保留进度、完成、失败与取消记录；下载物只投射可交付的输出、结果和核心工件。
- 智能体可读取这些记录和文本型产物摘要，用于判断软件已执行的动作和现有结果。

### 中文 Skill

- 三个内置 Skill 改为“检查项目并生成模型”“运行仿真并整理结果”“优化驱动时序”。
- Skill 选择区同步展示中文简介和具体步骤，便于执行前理解其作用。

### LLM 集成

- 智能体页可编辑 OpenAI-compatible API 地址、API 密钥、模型和上下文轮数。
- 默认接口为 `https://yice.byd.com/ai-gate/v1/chat/completions`，默认模型为 `DeepSeek-R1-Pro`。
- 默认保留最近 20 轮用户/智能体对话。
- 可独立控制是否把实时解析变量、语义操作日志和生成产物摘要提供给 LLM。
- API 地址兼容填写根路径或完整 `/chat/completions` 路径，并提供连接测试。
- 未配置密钥或规划失败时自动回退到确定性 Skill 步骤。

### 安全与架构

- 非敏感 LLM 设置写入 `project.agent_settings`，通过统一命令总线产生可追踪变更。
- API 密钥独立存放在后端私有凭据文件中，读取接口只返回配置状态和掩码。
- API 密钥不进入项目 JSON、事件流、对话记录和可下载产物。
- LLM 只能从既有工程工具白名单中规划步骤，不能执行任意代码或直接绕过项目命令边界。

_归并来源：`RELEASE_NOTES_2.3.0.md`。_

## V2.2.1

### 总览与项目属性

- 当前项目名称、分类和 STL 文件夹路径可在项目右侧属性区直接编辑并保存。
- 双击项目卡片可直接打开所选项目。
- 属性修改仍通过项目替换命令进入事件流，不绕开状态树。

### 层级建模

- STL 数模列表支持状态化的单列/双列切换，并强化运动副区与数模区的背景分隔。
- 增加层级升级、降级；复制层级时明确询问是否递归复制子层级及父子关系。
- 运动副类型仅保留 `rotation`、`translation`、`crank`。
- 平移副隐藏无意义的坐标点；crank 显示曲柄旋转中心、曲柄末端、连杆末端和运动副矢量。
- crank 后端复刻旧版三点几何、运动平面校验、机构分支判定及角位移到滑块位移映射；驱动输入保持角度，物理关节输出为毫米。

### 驱动与结果查看

- 展开运动段后采用左右紧凑布局：左侧高级设置，右侧显示变量路径、表达式和当前解析值，并支持整块复制。
- 关节曲线选择项显示“层级名称 / 关节名称”，避免重名歧义。
- 修复高 DPI 画布在每次拖动游标时重复放大内部高度、最终导致纵轴空白的问题。
- 移除甘特图色块内两行文本之间的横向分隔线。

### Viewer

- 跟随时间的坐标系和甘特图改为独立白底弹窗，不再挤占动画控制窗口。
- 弹窗开关、活动面板和字号继续由 `project.viewer_control` 控制，支持后端、脚本和 LLM 赋值。
- Viewer 与批量/分析仿真共享同一 crank 映射。

_归并来源：`RELEASE_NOTES_2.2.1.md`。_

## V2.2.0

### 驱动与全局操作

- 驱动设置新增字体下拉，选择写入 `ui.drives.font_family`。
- 高频 `MuJoCo View` 按钮移动到顶栏“检查项目”和“保存更改”之间，所有导航页均可使用。

### 仿真结果查看

- 甘特图全部运动段使用同一颜色，默认 `#018c94`。
- 预设 `#018c94`、`#764D9C`、`#494C8C`、`#C73849`、`#078C03`、`#BFAAD2`、`#BFB304`。
- 每行驱动使用浅灰背景和独立边框。
- 曲线游标拖动使用 Pointer Capture 隔离，不再误触其它缩放交互。
- 游标同时显示时间及该时间点各曲线的纵坐标和单位。

### Viewer

- 胶囊线中点显示实时毫米间距数值。
- 增加时间定位输入；按 Enter 同步动画进度条。每个电机增加目标值输入，按 Enter 自动解耦定位。
- 支持单选或多选 STL/OBJ，按 MuJoCo body mass 权重计算整体质心并录制小球轨迹。
- 可设置录制频率、小球大小和颜色，支持暂停、删除、显示当前整体质心坐标。
- 增加跟随时间游标的预设坐标系和甘特图；通过控制/坐标系/甘特图导航切换，避免同时占用窗口空间。
- 甘特游标底部显示时间；经过色块时显示“驱动名称—当前段位移”。坐标系和甘特字号均可设置。

### 状态与智能体托管

- 新增强类型 `project.viewer_control` 状态模型。
- 原生窗口操作通过 `param.set` 统一命令回写；运行中的 Viewer 轮询权威状态并响应脚本或 LLM 赋值。
- 时间、播放方向、倍速、测距显示、电机解耦、轨迹配置、图表开关、导航页和字号均可通过后端变量控制。

_归并来源：`RELEASE_NOTES_2.2.0.md`。_

## V2.1.0

### 测距配置

- 测量间距保留为状态模型中的兼容字段，默认 12 mm，不再显示 UI 输入框。
- 精确间距用于批量仿真的精确复核；动画间距用于单次 Viewer 的表面撒点可视化。
- 测距卡片和页面提示明确说明三者边界，旧项目字段仍可无损加载。

### Viewer 测距

- Viewer 快照新增测距对和驱动元数据，不把运行结果写入项目权威状态。
- 控制窗逐对显示实时距离及动画撒点间距。
- 原生场景绘制最近距离胶囊线：正常为黄色，干涉为加粗红色。
- 支持按阈值自适应显示、独立开关胶囊线，以及按动画间距生成 A/B 对比色表面撒点。

### 动画与电机控制

- 紧凑控制窗支持进度拖动、正放/暂停、倒放、回到起点和跳至结束。
- 倍速可在 0.1x–2.0x 范围实时调整。
- 电机控制模式可与时间轴播放并行；拖动某个电机后该电机自动解耦，其他电机继续跟随策略。
- 支持单个电机重新耦合；退出电机控制模式后所有电机恢复当前时间点的策略姿态。

### 验证

- Python 源码静态编译通过。
- 前端 JavaScript 语法检查通过。
- 完整内置 self-check 通过。
- 新增 Viewer V2.1 快照契约回归测试；当前交付环境未预装 pytest/MuJoCo，因此未在该环境执行完整自动化测试集。

_归并来源：`RELEASE_NOTES_2.1.0.md`。_

## V2.0.3

### 总览与驱动设置

- 导入项目改为向下箭头，导出项目改为向上箭头。
- 驱动页新增“双列展示”，配置保存在 `ui.drives.two_columns`。
- 双列模式压缩驱动头、运动段和高级配置；窄屏自动回退单列。
- 展开运动段高级配置后可以修改运动段名称。

### 曲线对象与坐标系运算

- 曲线对象分为“关节类”和“驱动类”，两类基础数据均为线位移或角位移。
- 仿真结果新增独立 `drive_curves`，避免把同一运动副的合成位置误认为单个驱动输出。
- 速度、加速度分别通过一阶导和二阶导生成，并保留积分与三阶导。
- 求和/求差提升为坐标系级设置，对当前坐标系的全部参与曲线运算。
- “保留参与曲线”默认关闭，因此默认只显示和导出运算结果。
- 左侧坐标系高度滑块范围为 80–600 px。
- 支持最多五个共享时间游标；游标可直接在任意坐标系画布中拖动并保存。

### 技术文档甘特图

- 甘特图使用白色背景、深色文字，适合截图放入技术文档。
- 软件全局字体和甘特图默认字体均优先使用微软雅黑。
- 每个运动段色块固定显示两行：起止时间，以及起止位置和单位。
- 起止位置根据同一驱动的累计行程计算，而不是只显示单段行程。
- 可选择显示倒放行；倒放交换起止位置，并以实际运动终点为零点，自动去除起始空窗。
- 支持甘特图字体族和字号下拉设置，配置保存在 `ui.results.*`。

### 验证

- 36 项自动化测试通过。
- Python 静态检查、JavaScript 语法检查和完整自检通过。

_归并来源：`RELEASE_NOTES_2.0.3.md`。_

## V2.0.2

### 当前模型文件夹

- 每次从浏览器选择文件夹或模型文件，后端都会创建独立的模型选择目录。
- 模型库只投射当前 `project.mesh_root` 的直属 STL/OBJ 文件，不合并历史选择。
- 切换后自动执行失效模型引用修复；历史缓存不会重新进入当前模型库。

### 项目 JSON 移植

- 总览项目中心增加“导出项目”和“导入项目”。
- 导出内容是完整状态树快照，包含 `project` 领域状态与 `ui` 界面状态。
- 导入会生成新的项目 ID，避免覆盖本机同名或同 ID 项目，并清理失效运动副引用。
- STL/OBJ 二进制文件不写入 JSON；在另一台电脑导入后，应重新选择当地模型文件夹。

### MuJoCo Viewer

- 恢复旧版 CAD/STL 的毫米到米缩放：`scale="0.001 0.001 0.001"`。
- 不再写死场景 `statistic`，由 MuJoCo 根据实际模型范围计算镜头中心和尺度。
- 无网格层级不再生成可见 capsule 棒体；有运动副但无网格时仅写入不可见惯性。

### 引用完整性

- 删除运动副或其所属层级时，同步删除依赖该运动副的驱动。
- 映射运动段引用已删除运动副时自动清空映射来源。
- 后端完整项目保存和 JSON 导入也会执行同一引用修复，避免绕过网页后留下悬空 ID。

### 验证

- 35 项自动化测试通过。
- MuJoCo 实际加载测试覆盖自定义网格缩放、自动取景和无占位棒体。
- 前端 JavaScript 语法检查、Python 静态检查和完整自检通过。

_归并来源：`RELEASE_NOTES_2.0.2.md`。_

## V2.0.1

### Viewer 与模型库

- `generated_scene.xml` 使用旧版成熟的 Viewer 环境：零重力播放、渐变天空、棋盘地面、天光、雾化、相机和灯光。
- 层级建模的“模型文件”一行新增高频 MuJoCo View 按钮。
- 模型库只列出当前选定文件夹的直接子文件；重新扫描路径后自动修复失效层级/测距引用。
- STL/OBJ 由浏览器轻量解析并显示线框缩略图，不增加大型前端依赖。

### 驱动设置

- 自定义变量默认折叠，输入框缩小。
- 驱动名、目标运动副、启用状态、段计数、新增段和删除按钮位于同一标题行。
- 每段运动压缩为一行；段名称自动生成且只读。
- 时长/速度根据参数模式只显示一个；开始、时长/速度、行程使用三组强调色。
- 运动函数、加速时间、缓起/缓停和参考段设置默认折叠。

### 仿真结果查看

- 仿真设置改为单列紧凑侧栏，并加入驱动时序甘特图。
- 坐标系和曲线布局写入项目状态，可增删、命名并随项目保存。
- 曲线对象覆盖运动副位移/速度/加速度、测距曲线和接触数量。
- 支持积分、一阶/二阶/三阶导数，以及同一坐标系内曲线求和。
- 支持单坐标系 CSV 和当前界面全部坐标系批量 CSV 导出。

### 交互与错误

- API 结构化错误会提取实际原因，错误提示保留 12 秒并可手动关闭。
- 输入框失焦、下拉/复选框确认和增删按钮分别提交一个可撤销事件。
- 按回车会确认当前值、刷新 UI 投射并保存当前步骤。
- 删除总览页重复的“打开当前项目”，预览区统一为“打开所选项目”。

_归并来源：`RELEASE_NOTES_2.0.1.md`。_

## V2.0.0

### 原生 Viewer

- 仿真控制页新增“打开 MuJoCo Viewer”。
- 当前项目先生成稳定的 `generated_scene.xml` 与 `generated_drives.json` 快照，再启动独立进程。
- Viewer 按新版统一运动曲线驱动 MuJoCo `qpos`，正确处理旋转副的度/弧度与滑动副的毫米/米边界。
- 支持 `loop` 与 `playback_speed` 参数；默认单次 1x 播放，结束后保持最终姿态。
- Windows 启动失败时自动追加尝试 ANGLE 图形后端。
- Viewer 与 Web 服务进程隔离，关闭窗口不会关闭 Studio；启动信息与错误写入 `outputs/viewer/viewer.log`。

### 架构接入

功能注册为自动发现的 `sim.open_viewer` 只读工具，具备 Pydantic 输入 Schema、UI Schema、`validate / dry_run / run`、结构化错误和示例参数。Web UI 通过统一命令端点调用，不直接启动本地进程。

### 验证范围

- Python 编译和项目自检通过。
- 安装可选 MuJoCo 物理引擎后，30 项自动化测试全部通过。
- 新增测试覆盖时间轴值、中文/空格路径安全传参、独立运行器命令、工具注册与无副作用预演。

原生窗口需要运行后端的本机具有桌面显示与可用 OpenGL。无显示服务器、Docker 容器或受限远程桌面不能完成窗口目视验证。

_归并来源：`RELEASE_NOTES_2.0.0.md`。_

# Client runtime history

说明：V2.9.6.1 起 V0.3.9 WindowsFix 同时作为当前分发标签与运行时协议/源码版本。更早客户端历史来自既有 Client `CHANGELOG_*`。

## Client V0.3.9

- Viewer bundle controller signature 4：向 server-supplied controller 传递 `gantt_cache_path`。
- 校验 bundle 中权威甘特图 PNG/JSON 的 SHA-256，防止损坏/错配快照进入 Viewer。
- 配套 Server V2.9.6.1；Viewer 启动协议最低版本为 V0.3.9。

## Client V0.3.8

- 将服务端连接地址收口到 `main.py` 文件顶部的 `SERVER_IP` / `SERVER_PORT` / `SERVER_URL`，默认服务端 IP 为 `10.13.90.107`。
- `client_config.json` 不再保存或覆盖 `server_url`，仅保留本地运行状态（当前为 `mesh_path`）；修改服务端 IP 时只需改 `main.py` 顶部 `SERVER_IP`。
- 保持 Client 本地桥监听 `127.0.0.1:8766`，不扩大局域网暴露面。
- 服务端 origin 校验、单用途 ticket、同步、Viewer bundle 和现有 Client API 路由全部复用，协议字段与 bundle schema 不变。

_归并来源：`CHANGELOG_0.3.8.md`。_

## Client V0.3.7

- Added startup cleanup for expired runtime `viewer_*` directories and `mesh_sync_*.zip` archives under `RUNTIME_ROOT`.
- Cleanup is whitelist-only, skips symlinks and all unrelated files/directories, and protects live bundles known to `ViewerRegistry`.
- Added a 60-second Viewer bundle directory-mtime heartbeat in `runner.py` so a detached Viewer that survives a Client restart remains TTL-protected even though the new process cannot reconstruct the old in-memory registry.
- Added configurable `MUJOCO_STUDIO_CLIENT_ORPHAN_TTL_HOURS` (default 24 hours, minimum 1 hour).
- No Viewer bundle schema or Client API protocol change.

_归并来源：`CHANGELOG_0.3.7.md`。_

## Client V0.3.6

- Persist Viewer `ready` and sampling progress as structured registry state while stdout is pumped line-by-line.
- Keep `log_tail` only as diagnostics/backward compatibility, so a long-running Viewer cannot leave the Web loading overlay stuck merely because the READY line rolled out of the tail window.
- Client protocol otherwise remains compatible with V0.3.5 behavior.

_归并来源：`CHANGELOG_0.3.6.md`。_

## Client V0.3.5

- Viewer 子进程改用 `python -u` 无缓冲启动。
- Viewer 日志从固定 64 KiB 阻塞读取改为逐行实时泵送，`MUJOCO_STUDIO_VIEWER_READY` 在 Viewer 仍运行时即可被 Web 端观察到。
- 修复原生 Viewer 已打开但 Web “撒点/加载”弹窗持续显示直到 Viewer 关闭的问题。

_归并来源：`CHANGELOG_0.3.5.md`。_

## Client V0.3.4

- 新增 Viewer 启动/撒点终止接口 `POST /v1/viewer/{pid}/terminate`。
- Viewer 状态继续返回日志尾部，供 V2.5.3 实时显示真实撒点对象数与点数。
- 与 Server V2.5.3 的 Viewer READY 门控配套：窗口未进入可显示阶段时前端进度不结束。

_归并来源：`CHANGELOG_0.3.4.md`。_

## Client V0.3.3

- Supports Server V2.5.0 Viewer bundle schema 4.
- Adds `trajectory.npz` playback path.
- Schema 4 Viewer playback sets `qpos` and calls `mj_forward()` only; it does not step physics.
- Keeps schema 1/2/3 compatibility.
- Motor decoupled overrides remain kinematic position controls.

_归并来源：`CHANGELOG_0.3.3.md`。_

## Client V0.3.2

- Supports Viewer bundle schema 3 from Server V2.4.5.0.
- Uses bundled `server_assets/` for schema 3 Viewer VFS binding instead of requiring the configured local mesh directory.
- Keeps schema 1/2 compatibility and existing local mesh upload behavior.
- Reports supported bundle schemas `[1, 2, 3]`.
- Treats missing/incomplete schema 3 asset snapshots as bundle-integrity errors with structured details.

_归并来源：`CHANGELOG_0.3.2.md`。_

## Client V0.3.1

- 数模同步上传新增 `X-MuJoCo-Source-Path`，使用 URL 编码兼容中文本地路径。
- 不改变 Viewer bundle、VFS 绑定或 localhost API 的现有行为。

_归并来源：`CHANGELOG_0.3.1.md`。_

## Client V0.3.0

- `/v1/health` 增加 `mesh_files` 与 `mesh_scan_error`。
- 本地数模清单最多返回 10000 个 STL/OBJ 相对名称。
- 扫描仅由健康请求触发，不增加后台常驻轮询。

_归并来源：`CHANGELOG_0.3.0.md`。_

## Client V0.2.0

- 新增 manifest v2 与控制器签名版本协商。
- 新增 `local_assets.json`，保持服务端 XML 相对引用不变。
- 支持 OBJ→MTL→纹理依赖闭包及中文本地路径 VFS 加载。
- 新增有界 Viewer 进程注册表、独立日志和 `/v1/viewer/{pid}/status`。
- 健康响应报告依赖、配置状态、进程明细和支持的 bundle Schema。
- 收紧 Host/Origin；无 Origin 只允许健康检查。
- 选择本地目录改为一次性票据授权。
- 所有失败路径清理临时 bundle；日志最多 20 个、7 天、单文件 8 MiB。
- 保留 manifest v1 兼容路径，但旧服务端链路不承诺中文绝对资产路径可用。

_归并来源：`CHANGELOG_0.2.0.md`。_

## V2.10.6.1

- 修复框图建模线段图标资源投射：驱动标识不再错误复用旋转副图标，新增并启用独立驱动图标 `diagram_joint_drive.png`，继续沿曲线跟随运动副显示，尺寸保持运动副标识的 2 倍。
- 按用户补充上传的图 2 替换滑动副资源 `diagram_joint_translation.png`，所有平移/滑动副标识改为新样式。
- 不改变闭链、驱动、ProjectSpec、API、Job 或持久字段语义；本次为资源与前端引用修复。新增 ProjectSpec/L1/L2/L3/Session/Job 权威字段 0 个，新增业务 Tool/API/Job/artifact/tool-directory 0 个。Server runtime/package/frontend cache-buster/Viewer/动画导出版本统一提升为 `2.10.6.1`；Client runtime 保持 `0.3.9`，Viewer bundle schema/controller signature 保持 4。
