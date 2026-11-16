# VZ Studio 0.3.2.1

> **Integrated Server V2.13.5 iteration:** VZ runtime/protocol remains 0.3.2.1. Hub time-series authority/workspace semantics are unchanged; this Server iteration only makes the Hub time-series library a portable/frozen model sidecar and strips environment-local `vz_push` bindings when a new Hub project identity is created or exported. VZ `time_series_workspace/` remains local and is intentionally excluded from Hub project bundles. No VZ protocol field is added.

> **Integrated Server V2.13.4.1 iteration:** VZ runtime/protocol remains 0.3.2.1. This Server patch only adds drag-reorder handles for second-generation Hub distance-pair cards and persists the existing `ProjectSpec.distance_pairs` list order through the existing project replace chain. V2.13.4 Hub optimizations and the V2.13.3 Hub↔VZ push/time-series boundaries remain unchanged. No new VZ protocol field, business Tool, ProjectSpec authority field, Job or artifact kind is introduced.

> **Integrated Server V2.13.3 iteration:** VZ runtime/protocol remains 0.3.2.1. Hub/VZ model-library state is now closed-loop: Hub disable hides a Hub-managed model from both engineer/client catalogs while preserving its local calibration/workspace; an engineer-side remove moves it to VZ trash and reports back to Hub through a runtime bridge token, with Hub catalog reconciliation as fallback. Engineer drive projection remains ProjectSpec-first and additionally recovers drive identities that only survive in Hub `VZ_TIME_SERIES` CSVs. Hub `time_series_library/` remains read-only while VZ `time_series_workspace/` remains the editable local fork. No new business Tool, ProjectSpec field, Job, or VZ protocol version is introduced.

> **Integrated Server V2.12.2.1 iteration:** VZ runtime/protocol remains 0.3.2.1. VZ Fast/Perfect HTML now restores the original second-generation center 3D text through the existing watermark mesh pipeline, and the engineer HTML render-settings modal uses a compact three-column desktop grid. V2.12.1.1 startup diagnostics and V2.12.1 lighting/background/preview behavior remain intact. No three.js/Babylon/drei/model-viewer runtime is imported.

> **Integrated Server V2.12.1.1 hotfix:** VZ runtime/protocol remains 0.3.2.1. V2.12.1 lighting/background/preview behavior is retained, while the shared Fast/Perfect offline HTML renderer now emits its configurable directional-light bootstrap constants before first use. Startup errors also replace the loading overlay with a visible diagnostic instead of leaving “正在载入离线动画…” indefinitely. No three.js/Babylon/drei/model-viewer runtime is imported.

## V0.3.2.1 Modeling Import Hotfix / 建模信息导入热修复

- 修复导入二代/VZ 建模信息时，外部 `mesh.id` 含空格、点号、斜杠、中文等字符会报“mesh ID 非法”的问题。
- 保持 VZ 内部 ID 严格规则不变，仅在建模信息导入边界把第三方/旧版本 mesh ID 规范化为安全内部 ID。
- 规范化采用稳定摘要并做层内去重，避免不同外部 ID 清洗后发生碰撞。
- 导入时暂存原始 mesh ID，用它回填 `vz_extensions.mesh_rendering`，因此材质、贴图和 Material Slot 扩展不会因 ID 规范化而丢失。
- V0.3.2 的外部 CSV 表格控制功能保持不变。


## V0.3.2 External CSV Sequence Control / 外部 CSV 控制顺序

- 用户端顶部新增“外部表格”页签，可导入 CSV。首行自动作为表头；第一列固定解释为时间（秒），第二列起按动作名称、驱动名称或驱动 ID 自动匹配电机。
- CSV 数据支持多个电机按同一时间轴并行运动；相邻时间点之间采用线性插值，保证每个表格时间点精确到达对应角度/位移。
- 空白电机单元格表示保持上一位置；未匹配的额外列会提示并忽略。时间必须非负且严格递增，位置必须位于工程师配置的驱动限位内。
- 每个“动作”下拉菜单下方新增“表格 ↔ 手动”滑动开关，默认开启“手动”。关闭开关时使用已导入的表格数据，手动步骤输入会锁定；重新开启后恢复原手动控制顺序。
- 外部表格只保存在当前浏览器会话中，不写入模型长期数据。切换模型时恢复默认手动模式并清除已导入表格，避免跨模型误用列映射。

## V0.2.16 Persistent-data Whitelist + Runtime Lifecycle / 长期数据白名单与运行数据生命周期

V0.2.16 将“工程长期数据”和“运行时临时数据”彻底分开。

### 长期保存

- `models/<model_id>/model.json`：模型层级建模、运动副/闭链、驱动与变量、记忆位置、控制顺序、材质设置、场景/渲染设置、仿真计算配置。
- `models/<model_id>/assets/`：层级建模引用的 STL/OBJ 原始数模资源。
- `render_assets/textures/`：材质设置引用的 PBR 纹理资源。
- `render_assets/environments/`：渲染设置引用的环境图资源。
- `user_settings.json`：仅保存用户网址的 `render_quality` 渲染质量偏好。

### 不长期保存

- `simulations/<job_id>/`：完整视为临时任务目录，包括 `result.json`、`preview.html`、`animation_export_input.json`、`generated/model.xml`、`metadata.json`、生成用 mesh 副本等。启动时删除上次运行遗留任务；当前运行的已完成任务保留最多 1 小时。
- `animations/*.html`：工程师快速/高质量渲染结果只作为预览/下载临时文件；启动时删除遗留 HTML，运行中最多保留 1 小时。
- `trash/undo_*`：仅用于模型删除后的 15 分钟撤销，过期后自动物理删除。
- 用户网址的当前相机视角和 3 步撤销快照：只存在浏览器当前页面会话，不写入后台。

### 用户网址视角规则

- 每次打开/刷新用户网址：第一个模型从正视图开始。
- 切换到任一模型：从正视图开始。
- 当前页面内手动旋转/平移/缩放后：控制仿真、记忆位置跳转和 `↶` 撤销继续保持当前视角。
- 关闭或刷新页面后：该浏览视角丢弃，不写入 `user_settings.json`。
- 升级到 V0.2.16 时会自动移除旧 `model_cameras` 和 `selected_model_id` 持久化字段，仅保留 `render_quality`。

## V0.2.15.1 Disposable HTML Lifecycle / 临时 HTML 生命周期

- 工程师快速/高质量渲染与用户仿真预览生成的 HTML 全部视为可下载的临时产物。
- 每次启动 VZ Studio 时，自动删除 `animations/` 与 `simulations/` 中上次运行遗留的生成 HTML。
- 当前运行中新生成的 HTML 保留 1 小时供用户/工程师下载；服务内部定期扫描，到期后自动删除。
- 清理范围严格限制在 `VZ_project/animations/**/*.html` 与 `VZ_project/simulations/**/*.html`，不会删除 `frontend/engineer.html`、`frontend/client.html` 等程序页面。
- 自动清理只删除 HTML，不删除 `result.json`、`model.xml`、模型、纹理、环境图或其它工程数据。
- 移除 V0.2.15 的 `.client_preview` 标记与“24 小时 / 最近 12 个”预览目录回收策略，统一为生成 HTML 生命周期管理。

## V0.2.15 Data Lifecycle + Three-step Pose Undo / 数据生命周期与三步位置撤销

- 工程师端左上角品牌副标题显示版本号。
- 闭链从动运动副选择器采用紧凑层级树，并支持逐层展开/收起。
- 用户端控制顺序栏新增蓝色 `↶`，控制仿真和记忆位置跳转前保存动作前姿态，最多连续撤销 3 步。
- 撤销沿用记忆位置跳转的额定速度运动规则，临时姿态仅保存在浏览器内存。
- 用户侧预览 HTML 存放于 `simulations/<job>/preview.html`，正式工程师导出位于 `animations/`。


## V0.2.13.3 同层数模唯一性

- 工程师网址中，同一个层级内，同一个数模库条目只能添加一次。
- 数模下拉菜单会禁用当前层级已经添加的条目，并显示“本层级已添加”。
- 前端选择与后端保存双重校验，避免通过接口或 DOM 绕过界面产生重复引用。
- 同一个数模仍可分别用于不同层级。
- 兼容旧项目：若历史数据同层已有重复引用，读取时保留第一条并忽略后续重复，下一次保存即可清理。

## V0.2.13.2 HTML 渲染设置与用户设置持久化

- 层级树列宽固定为稳定布局，点击模型或层级不再触发内容测量和列宽写回。
- 当前层级数模使用明确的原生下拉菜单样式。
- 用户网址增加“保存设置”，当前模型与快速/高质量渲染模式写入工程数据根目录下的 `user_settings.json`；视角继续自动保存到同一文件。
- 工程师网址不再在页面底部显示“快速渲染已生成”的 JSON 结果面板。
- “完美渲染设置”更名为“HTML渲染设置”，分为快速渲染和高质量渲染两块。快速默认 10 FPS / 单网格 120000 面；高质量默认 10 FPS。

## V0.2.13.1 工程师页层级树与数模下拉修复

- 修复层级树在选择模型或层级后宽度逐次增长：宽度测量改为基于树项固有内容宽度，并统一按选中态字重测量，避免把当前列宽再次累加。
- 保留 0.2.13.0 的闭链名称自适应宽度能力；长层级/闭链名称仍可按内容扩展，并继续受视口 48% 上限保护。
- 当前层级“数模 → 文件”由 `input + datalist` 改为真正的 `select` 下拉菜单。
- 外部建模信息引用的缺失数模仍保留原文件名，并以“当前缺失”选项显示；选择库内数模后再写入新的 `asset_id`。

## V0.2.13.0 闭链交换/求解与层级树宽度修复

- 二代建模信息中的运动副点与闭链端点按所属层级局部坐标导入，在 VZ 内部转换为世界坐标，避免层级位移被重复扣减导致数百毫米初始残差。
- 闭链求解改为与二代软件一致的联合 DLS：多闭链同时堆叠求解、使用 `lambda^2 I` 正则、复用上一帧 qpos 并保持步长/限位约束。
- 左侧层级树会根据 `——闭链名称` 后缀的实际内容宽度自动扩展，不再被 190 px 固定列宽截断。


## V0.2.12 建模信息导入模式与数模引用修复

- 数模库缺失的外部数模不再被改名为“文件名（数模库缺失）”，也不会向候选列表伪造缺失项；界面始终保留建模信息中的原始文件名。
- 数模控件采用可编辑候选模式：数模库只提供候选值，外部原名可以独立存在；只有明确选择库内唯一匹配数模时才写入 `asset_id`。
- 导入建模信息新增“覆盖当前模型 / 新建模型”二选一。覆盖模式保留当前模型 ID、名称、描述与数模库，只替换导入的建模结构，并按原始文件名自动索引现有数模。
- 自动索引仅在路径或文件名能唯一定位数模时生效；缺失或重名歧义不会猜测绑定，仍保留原名并在仿真/MJCF/渲染实际使用时提示。

## V0.2.11.1 建模导入、闭链坐标与层级标识修复

- 外部建模信息导入后，即使数模库没有对应 STL/OBJ，层级数模下拉框仍保留导入文件名并标记“数模库缺失”；保存不会自动清空或改写该选择，只有仿真/MJCF/渲染使用时才提示缺失。
- 闭链端点和旋转副世界坐标在生成 MJCF 时转换为所属层级 body 的局部坐标，修复同一世界坐标被错误叠加层级位移、造成大残差不收敛的问题。
- 闭链坐标输入兼容 `Point(x, y, z)`、普通 `x,y,z`、中文逗号、分号和 `x=...` 标记形式；连续帧闭链求解复用上一帧结果作为初值。
- 左侧层级树中，作为闭链端点的两个层级名称后显示 `——闭链名称`；一个层级属于多个闭链时依次显示多个后缀。


## V0.2.11 二代结构建模互通修复

- 修复二代建模信息导入 VZ 时，`Point(...)`、数组、`{x,y,z}` 等不同坐标形态触发“世界坐标点必须包含三个数字”的问题。
- 建模信息交换改为结构模式：保留层级、数模引用、运动副、驱动名称及其绑定运动副；不交换驱动开始时间、持续时间、速度、行程、曲线点和映射时序。
- 新增统一 `drive_configuration.bindings`，同时保留旧版 `drives/latest_version/application_state` 入口但运动段固定为空，兼容旧读取链路。
- 新增统一 `kinematic_closure_configuration`，VZ 与二代软件双向保留闭链端点、从动运动副及求解参数。
- 导入旧的富驱动交换文件时，仅提取驱动名称与目标运动副；VZ 内部为了可编辑性生成本地默认动作壳，不继承源文件时序参数。

## V0.2.10.1 用户网址：分组控制顺序与折叠记忆位置

- 控制顺序中“控制对象 / 起始位置 / 结束位置”分别增加完整视觉边框，仍保持 V0.2.10.0 的紧凑四列三行语义。
- 记忆位置默认只显示名称、驱动数量、跳转和删除操作，不再在列表中平铺所有驱动数据。
- 双击任一记忆位置整卡可打开编辑弹窗；弹窗逐驱动以 0–100% 百分比编辑，并实时显示换算后的实际位置。
- 保存弹窗时按每个驱动的 0% / 100% 标定值自动换算并写回记忆位置，原有“跳转”逻辑继续读取实际位置。


## V0.2.9 二代建模信息 JSON 互通

- 原生支持二代 MuJoCo Studio 的 `mujoco_modeling_exchange` 2.0 建模信息格式。
- 层级、父子关系、STL/OBJ 文件名、颜色/透明度/碰撞、质量、运动副、变量、仿真时间与驱动配置可双向交换。
- 同时兼容 schema 1.0 / 2.x 输入，并输出二代所需的 `hierarchical_modeling`、`drive_configuration` 和旧版 `application_state` 快照。
- VZ 暂无界面的二代复杂运动段、测距配置、逻辑驱动等字段保存在 `_modeling_exchange` 兼容元数据中；未改动 VZ 活动部位时再次导出会保留这些内容。
- VZ 自有材质、Material Slot、渲染场景、闭链、活动部位、预设和记忆通过可忽略的 `vz_extensions` 扩展块保存；二代软件可安全忽略。
- 工程师页新增“导入建模信息 / 导出建模信息”按钮。
- 建模信息 JSON 不包含 STL/OBJ 二进制文件，跨电脑后仍需重新上传对应模型文件。


## V0.2.8.1 材质编辑器交互微调

- 双击对象后直接对对象本体做青色提亮/边缘高光，不再绘制包围盒。
- 左键轻点空白处取消当前选择；旋转拖动不会误触取消。
- 材质库缩略预览区最大纵向高度从 260 px 提升到 520 px。
- 材质核心参数与完美渲染共用 metallic / roughness / specular / clearcoat / PBR maps 配置；但编辑器仍采用轻量实时灯光/程序环境，因此不是像素级完全一致。

## V0.2.8 独立材质编辑器

- 工程师端新增独立“材质设置”窗口：完整场景 WebGL2 实时预览，双击对象选择、包围盒高亮、轨道旋转/缩放/平移与自动取景。
- 材质配置从“仅资产级默认值”扩展到 `layers[].meshes[].material_slots.slot_0`，同一个资产的不同场景实例可以拥有独立 PBR 材质。
- 高级参数恢复为默认可见，并加入纹理缩放与旋转；切换语义材质类型不再静默覆盖已调参数。
- 修复中文材质目录分类：0.2.7.x 的 ASCII token 化会让“皮革 / 哑光 / 塑料”等中文目录落入通用金属风格；0.2.8 直接保留 Unicode 目录名参与分类。
- 金属、皮革/哑光、塑料拥有明确分离的推荐值：裸金属 `metallic=1.0 / roughness=0.28`，皮革/哑光 `0 / 0.72`，工程塑料 `0 / 0.48`。未知材质回退为非金属哑光，而不是 painted-metal。
- 快速/高质量离线渲染读取 Mesh Slot 覆盖值，并支持 `texture_scale` / `texture_rotation_deg`。

## V0.2.5.3 动画地板颜色修正

- 以 V0.2.5.2.4 动画 HTML 原有地板 shader 色 `RGB ≈ (43, 59, 66)` / `vec3(.17,.23,.26)` 作为环境参考色。
- 动画 HTML 背景、clear color、fog 与地板边缘渐变统一使用该深青色。
- 地板主体在该深青色基础上再降低约 28% 亮度，形成更深的青色地面。
- 不再错误读取 MuJoCo plane 的默认灰色材质作为动画地板环境色。
- MuJoCo plane 原始材质不做额外改色，避免影响模型本身。


VZ Studio 是独立、无需账号的 MuJoCo 运动学网页平台。V0.2.7.5 强化材质设置弹窗：每个材质预览卡无须点击即可在预览图下方固定显示材质名称；取消材质库内部嵌套滚动，弹窗采用固定视口高度的三段式布局，中央内容区作为唯一主滚动面，可上下查看完整高级参数。V0.2.5.1 在 V0.2.5 的“快速导出 / 高保真导出”基础上新增 **“完美导出”**：把后台 PBR 素材库、逐数模 BaseColor/Normal/Roughness/Metallic/AO、真实物理贴图尺度、环境全景、曝光和动态软阴影打包进单文件离线 WebGL2 HTML。


## V0.2.5.2.4 天空背景亮度优化

- 动画 HTML 的天空渐变统一混入约 22% 黑色，保留原有灰蓝层次，但明显降低整体发白感。
- 同步将 WebGL 清屏色、远景雾色和 Canvas 初始底色压暗，避免天空变暗后远景/加载阶段仍出现亮灰跳变。
- 仅调整背景与雾色，不改变模型 PBR 材质、灯光强度、阴影参数以及快速/高质量渲染档位。

## V0.2.5.2 渲染交互与用户播放器优化

- 工程师端仅保留“快速渲染 / 高质量渲染”，移除旧高保真模式和正视图截图预览。
- 两种工程师渲染均在当前页弹窗播放，弹窗右上角支持“另存为”下载离线 HTML。
- 用户端“发送并仿真”左侧新增渲染质量滑动开关，默认快速渲染；高质量渲染映射 Perfect/PBR 链路。
- 离线播放器新增动画下载按钮，并调整标题、进度条、位置面板与开发支持署名 UI。

## V0.2.5.1.1 用户预览性能修复

- 用户端“发送并仿真”改走内部 `preview` 渲染档，不再执行正式 FAST 导出的 crease 硬边重建；预览统一使用 NumPy 向量化 smooth normals，恢复接近 V0.2.4.2 的快速刷新特性。
- 新增 64 MiB 有界 LRU 预览网格缓存，以网格内容哈希为键复用 positions / normals / indices 的 Base64 结果；模型网格不变时，连续仿真不再重复静态网格编码。
- 工程师端 FAST / HQ / PERFECT 三种正式导出完全不变，仍保留硬边法线、PBR 和完美模式能力。
- 预览像素比上限降为 1.5，优先保证交互反馈速度；正式导出不受影响。

## V0.2.5.1 完美导出

- **第三条独立导出路线**：工程师端新增“◆ 完美导出”，与快速/高保真模式并存。完美模式至少 90 FPS、每数模最高 250 万三角面、DPR 上限 3.5。
- **后台渲染素材库**：程序自动维护 `render_assets/textures/` 与 `render_assets/environments/`；UI 通过 `/api/render-assets` 枚举素材，不把本机绝对路径写进模型。
- **完整 PBR 贴图槽**：每个数模支持 BaseColor、Normal、Roughness、Metallic、AO，另有 metallic/roughness/specular/clearcoat/clearcoat roughness、法线强度、AO 强度和贴图实际尺寸。
- **STL/OBJ 无 UV 兼容**：V0.2.5.1 的通用材质贴图采用世界/模型空间三平面（triplanar）投射，避免 STL 没有 UV 时贴图完全不可用，并尽量减少明显拉伸。Logo、丝印、铭牌等需要精确定位的图案仍建议使用独立几何或后续 UV/GLB 工作流。
- **环境与色彩**：支持 2:1 全景 JPG/PNG/WebP 环境图、环境强度/旋转、曝光，并在 Shader 内执行线性光照、PBR BRDF、Fresnel 与 ACES 风格色调映射。
- **动态软阴影**：完美模式创建最高 4096×4096 深度阴影图，并使用 5×5 PCF 采样；快速/高保真模式不承担这部分额外成本。
- **真正单文件离线**：完美模式只嵌入当前模型实际引用的贴图/环境图，并使用 Base64 封装进导出 HTML，运行时不需要 CDN、素材服务器或网络连接。

详细素材制作规范见 [`PBR_ASSET_GUIDE.md`](PBR_ASSET_GUIDE.md)。

## V0.2.5 渲染升级

- **快速导出增强版**：继续使用单文件离线 WebGL2，保持 30 FPS / 每数模约 12 万三角面上限的效率策略，同时不再对所有共享顶点做无条件平均法线。默认使用 35° 硬边阈值，机械件折边、棱角和倒角更稳定。
- **高保真导出**：提高到至少 60 FPS、每数模最高 100 万三角面，并把浏览器像素比上限提高到 2.5；启用额外补光和更完整的材质 BRDF。
- **每数模渲染配置**：数模库齿轮按钮与资产管理器均可设置法线策略（硬边夹角 / 全平滑 / 全硬边）、材质预设、金属度、粗糙度、高光、清漆层和环境光强度。
- **材质与光照**：离线播放器加入金属度/粗糙度驱动的 PBR-lite 高光、Fresnel、环境项、ACES 风格色调映射，以及高保真模式的多方向补光。
- **仿真与渲染隔离**：渲染配置仅进入 HTML 导出适配层，不写入 MuJoCo 动力学/运动学配置；顶部“MuJoCo 仿真”“快速导出”“高保真导出”分别执行。


## 启动

需要 Python 3.10 或更高版本。双击 `run.py`，或执行：

```bash
python run.py
```

首次运行时会自动安装 `numpy` 与 `mujoco`。安装完成后自动启动：

- 工程师网址：`http://127.0.0.1:8877/engineer`
- 用户网址：`http://127.0.0.1:8877/client`

整合部署优先编辑 `Server/ports.json` 的 `vz`；独立执行此目录 run.py 时也会读取该文件（若存在）。端口也可通过 `VZ_PORT` 显式覆盖；设置 `VZ_NO_BROWSER=1` 可禁止自动打开浏览器。若所在网络不允许自动安装，可先执行 `python -m pip install -r requirements.txt`。

## VZ_project 存储目录

程序代码与用户项目数据分离：

- Windows：默认使用 `E:\VZ_project`，不存在时自动创建。
- Linux：默认在 `run.py` 同级创建 `VZ_project/`。
- 其他系统：默认也使用 `run.py` 同级的 `VZ_project/`。
- 可用环境变量 `VZ_PROJECT_ROOT` 显式覆盖项目目录。

模型 JSON、上传的 STL/OBJ、MuJoCo MJCF、仿真结果和导出的动画 HTML 均写入该项目根目录。首次升级时，如果程序包内存在旧版 `data/` 且新目录尚无模型，会自动迁移旧数据。

## 工程师端

- 层级建模顶部新增模型名称输入框，并支持打开模型整体的正视图渲染截图。
- 层级建模继续使用层级树、层级属性/运动副/闭链、数模库结构。
- 支持层级父子树、启用状态、颜色、STL/OBJ 绑定、旋转副、移动副、特殊副和闭链约束。
- 驱动设置采用“活动部位 → 动作”两级流程；动作仍设置运动副、电机 0%/100% 位置和缓起缓停/映射模式。
- 每个动作新增“动作速度”。驱动统一为速度模式，动作持续时间由 `|结束位置 - 起始位置| / 速度` 自动计算，不再让用户设置时长。
- 点击顶部“MuJoCo 仿真”只执行 MuJoCo 轨迹任务；“快速导出”“高保真导出”和“完美导出”独立生成离线动画 HTML。

## 用户端

- 用户只配置动作的起始位置、结束位置/动作目标；不再暴露速度输入框。
- 执行速度读取工程师端该驱动的 `rated_speed`。
- 连续动作按顺序执行，每一段时长都由距离和工程师速度计算。

## MuJoCo 与动画 HTML

- 由层级、数模、运动副和闭链生成独立 MJCF；STL/OBJ 坐标按 mm → m 缩放。
- 仿真使用真实 `mujoco.MjModel.from_xml_path`、`MjData` 与 `mj_forward`，闭链继续使用 Jacobian/DLS 位置求解。
- 继续复用并升级内置离线动画 HTML 核心导出器 `legacy_animation_html_export.py`：MuJoCo 逐帧采样几何与位姿 → 根据数模渲染配置生成硬边/材质数据 → 嵌入单文件 WebGL2 HTML → 浏览器离线回放。
- 离线播放器保留二代的正视图、侧视图、POV 视图、播放/暂停、时间轴、相机交互等逻辑。
- 工程师仿真产物位于 `VZ_project/simulations/<job>/`；离线动画位于 `VZ_project/animations/`。

## 自检

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
node --check frontend/engineer.js
node --check frontend/client.js
node --check frontend/viewer.js
```

未安装 MuJoCo 时，真实 MJCF 编译与真实动画导出测试会标记为跳过；`run.py` 会在目标机器首次启动时安装依赖后执行真实仿真。

### STL/OBJ upload hotfix

The integrated 0.2.2 build uses direct binary streaming for STL/OBJ uploads. This avoids Base64 request-size expansion and supports individual model assets up to 2 GiB, matching the second-generation Studio upload ceiling. Existing 0.2.x Base64 clients remain accepted by the server for compatibility.

### STL/OBJ 路径与文件夹上传修复

- 修复 Windows `E:\VZ_project\models\<model>\assets\...` 偶发出现 `[Errno 2] No such file or directory` 后直接暴露系统异常的问题：写入前强制创建目录，临时文件完成后原子替换，若目标子目录瞬时丢失会重建并重试一次，随后校验文件存在且字节数完全一致。
- `run.py` 启动时会对 `VZ_project` 做真实写入探针；如果 E 盘不存在或没有读写权限，会在启动阶段给出明确错误，而不是到上传时才失败。
- 新上传成功后，会自动清理旧版本/中断上传遗留的“JSON 中存在、磁盘文件已丢失”的悬空数模记录及层级引用。
- “修复失效引用”按钮现在会由后端真实检查磁盘文件并修复悬空记录。
- 工程师页新增“上传 STL / OBJ 文件夹”。目录选择使用浏览器 `webkitdirectory`，递归上传其中全部 STL/OBJ；通过 `webkitRelativePath` 保存文件夹内的相对路径信息，数模库和层级选择器中可显示该路径。
- 文件夹相对路径经过服务端校验，拒绝绝对路径、盘符路径与 `..` 目录穿越；实际磁盘文件继续使用服务端唯一名保存，避免不同目录下同名 STL/OBJ 互相覆盖。
- 文件夹上传显示逐文件进度；如果当前模型有未保存修改，会先保存模型，避免上传响应覆盖本地编辑。

## V0.2.5.3.1
- 动画 HTML 背景、fog 和地板边缘渐变目标色在 V0.2.5.3 基础上轻微提亮为 `vec3(.184,.248,.281)`。
- 地板中心主体保持 V0.2.5.3 的深青色基准 `vec3(.1224,.1656,.1872)`，不会跟着整体变亮。

## V0.2.5.3.2
- 动画 HTML 背景、fog 和地板边缘渐变目标色在 V0.2.5.3.1 基础上再轻微提亮为 `vec3(.199,.268,.303)`。
- 地板中心主体继续保持 `vec3(.1224,.1656,.1872)`，仅环境与边缘更浅。

## V0.2.5.3.3
- 动画 HTML 背景、fog 和地板边缘渐变目标色在 V0.2.5.3.2 基础上明显再提亮一档为 `vec3(.225,.303,.342)`。
- 地板中心主体继续保持 `vec3(.1224,.1656,.1872)` 不变，仅环境与边缘更浅。
- 保留 `FRAMEWORK_PROMPT.md` 与发布包无缓存规则。

## V0.2.5.4
- 建模层级颜色与数模颜色采用“后设置覆盖前设置”。
- 设置层级颜色时，会同步覆盖该层级下现有全部数模的 `rgba`。
- 随后单独设置某个数模颜色时，该数模颜色覆盖层级颜色；之后若再次修改层级颜色，则再次覆盖全部数模。

## V0.2.5.4.1
- 当层级颜色最后覆盖数模颜色时，数模颜色设置框显示红色 × 与红色边框提示。
- 数模颜色重新设置后立即恢复“数模优先”，红色 × 自动消失。
- 新增 `color_source` 持久状态，保存/重载后仍能识别当前由层级还是数模颜色生效。
- 修复层级颜色变化后数模颜色设置框显示不刷新的问题，输入框颜色与实际生效颜色即时同步。

## V0.2.6
- 用户端左侧控制区宽度按原版缩小 30%（42% → 29.4%，最小宽度 390px → 273px），为右侧动画视图释放更多空间。
- 顶部页面名称/模型选择区域纵向高度约压缩 50%，同时压缩左侧上半区高度，让“控制顺序”获得更多纵向空间。
- “控制逻辑 / 记忆位置”上半区按钮与文字进一步小型化；“创建记忆位置”移动到记忆位置页签右上角。
- 每个记忆位置改为严格两行的紧凑表格：第一行显示可双击修改的名称和各驱动名称，第二行显示“跳转”按钮与记录的位置/百分比。
- 新增记忆位置“跳转”：以当前右侧动画的结束帧作为全部驱动起点，各驱动从 t=0 同时移动到记忆位置，分别使用工程师端设置的 `rated_speed`；动画总时长由最晚到达的驱动决定。
- `/api/simulate` 返回 `final_positions`，用户端据此持续跟踪当前动画结束帧；新增 `memory_jump_id` + `initial_positions` 跳转请求契约。
