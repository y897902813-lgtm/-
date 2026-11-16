# V2.16.11.5 — 启动与关闭部署指引

- 在 `Server` 中启动：`python run.py`；主动停止（另一个 SSH 会话）：`python run.py stop`；查看进程：`python run.py status`。`Ctrl+C`、`SIGTERM` 和 SSH 的 `SIGHUP` 正常调用关闭回收路径。`kill -9` 不可捕获，但下次 `stop`/`start` 可恢复**受本启动器记录**的遗留 VZ。
- Hub/VZ 以 `Server/ports.json` 的实际端口运行。启动时会拒绝任何未知占用端口（不再静默复用 8877 上的旧 VZ）。若升级前的**无记录**旧进程占用 VZ 端口，Linux 可以显式执行 `python run.py stop --legacy-vz`：必须匹配内核监听 socket inode + 同一路径的集成 VZ run.py + PID/启动时间才结束进程，未知监听者拒绝操作；或先执行 `ss -ltnp '( sport = :8877 )'` 核实 PID 再手动终止；**不要按端口盲杀其他进程**。
- `MUJOCO_STUDIO_DATA` 或现有存储配置决定 `.runtime/studio_launcher.json` 的位置。多个不同存储目录的部署不相互持锁，但若监听端口重复，后启动的服务会明确失败。不要手动删除活动锁文件。
- Docker 应执行 `python docker_ports.py down` / `up --build -d`；`run.py stop` 只识别当前本机本次源码部署的受管进程，不负责清理其他容器或用户电脑的独立 Client 服务。
- Windows/Linux 通用配置 `Server/ports.json` 继续保留 `{server_ip, hub, client, vz}`；未新增 HTTP API、第三方依赖或工程资产字段。Linux 真实进程回归使用隔离 Hub 与真实 VZ；完整生产 Uvicorn、MuJoCo、本机/远端 Client 和 Docker 需现场验证。

## V2.16.11.5 更新说明

更新后执行 `python run.py stop` 停止上一版、部署完整源码、再 `python run.py` 启动。保持 `Server/ports.json` 与独立数据根原样，旧基线项目不需要迁移或手动改写任何模型 JSON。旧版 `core/hub_critical_data.json` 若 token 符合当前冻结身份可直接命中；缺失/损坏的气泡由一个有界后台 worker 按需补建，首页目录列表不会为此阻塞。强制刷新浏览器（Ctrl+Shift+R）以使用最新 `app.js?v=2.16.11.5`。若部分历史基线仍显示待加载，可查看服务端日志中 `Unable to rebuild frozen Hub badge`，确认旧模型原本是否存在无效时序配置；失败不会修改权威模型或写错气泡。Linux SSH 受管 Hub/VZ 停止流程不变。

--- 历史部署说明 ---

# MuJoCo Studio 服务端部署

## 统一设置 Client 目标服务器 IP 和三个端口

在整个集成源码包中，只需编辑 `Server/ports.json` 的 `server_ip` 和三个端口：

```json
{"server_ip": "10.13.90.107", "hub": 8765, "client": 8766, "vz": 8877}
```

`server_ip` 是 Client 访问 Hub 的目标 IP（默认 `10.13.90.107`），**不改变服务端的 0.0.0.0 监听或 Client 的 127.0.0.1 本地监听**。`hub` 为 Hub/Studio/Lab HTTP 服务端口，`vz` 为随 Hub 启动的 VZ 端口，`client` 为**每台用户电脑本地**监听的 Client 桥端口，非服务器第三个公共监听端口。改完重启 Server 与 VZ；如果 Client 独立部署在其他电脑，需将该文件复制到客户端 `Client/ports.json` 并重启 Client，浏览器 `/api/health.network_ports` 会自动更新本地桥探测与 VZ 跳转地址。环境变量 `MUJOCO_STUDIO_SERVER_IP`、`MUJOCO_STUDIO_PORT`、`VZ_PORT`、`MUJOCO_STUDIO_CLIENT_PORT` 可兼容旧自动化部署，但显式设置时优先级高于 JSON。

**Docker Compose** 请改用 `python docker_ports.py up --build -d`，它会把 JSON 中 Hub 端口映射到容器端口。直接 `docker compose up` 仍使用旧默认或外部环境变量，不能实现单文件配置。Docker 不公开无登录 VZ 端口和本地 Client 桥；如需公网访问 VZ，建议按组织安全策略配置认证代理。原生启动执行 `python run.py` 不需要额外步骤。请同步检查防火墙、Nginx/Caddy 及浏览器 URL，避免路由到已更换的旧端口。Lab UDP 端口不属于这三个 HTTP 端口。


## 安全前提

所有通过 `run.py` 的启动默认监听 `0.0.0.0:<hub>`（未改端口时为 `8765`） 并要求登录，内置管理员账号为
`yu.weigang1`，不可删除。源码只包含
默认密码的不可逆 PBKDF2 哈希，不包含管理员明文密码。生产环境仍建议用
`MUJOCO_STUDIO_ADMIN_PASSWORD` 从密钥管理器覆盖默认密码，不要把明文写入仓库或 Compose 文件。

推荐拓扑是：浏览器 → HTTPS 反向代理 → 单个 Studio 进程 → 持久化 `/data` 卷。当前会话位于进程
内存，因此不要在无粘性会话的情况下横向启动多个应用进程；进程重启后用户需要重新登录。

## Docker Compose 从零启动

1. 为 `/data` 所在宿主目录建立定期、可恢复验证的备份。
2. 设置环境变量：

   ```bash
   export MUJOCO_STUDIO_ADMIN_PASSWORD='从密钥管理器读取的强密码'
   export MUJOCO_STUDIO_SECURE_COOKIE=0
   python docker_ports.py up --build -d
   ```

3. 首次仅在受信网络通过 `http://127.0.0.1:<ports.json 中的 hub 端口>` 验证内置管理员登录。
4. 配置 Nginx、Caddy 或组织网关终止 HTTPS，并把请求反向代理到 `ports.json` 中的 `hub` 端口；随后将
   `MUJOCO_STUDIO_SECURE_COOKIE=1` 并重启服务。代理必须保留 Cookie 与 WebSocket 升级头。
5. 确认 `GET /api/health` 可达、未登录业务 API 返回 401、登录后 `/api/auth/me` 返回 admin 角色。

Compose 明确设置 `MUJOCO_STUDIO_DATA=/data`、`MUJOCO_STUDIO_SINGLE_USER=0` 和
`MUJOCO_STUDIO_DESKTOP=0`。服务器不会调用 tkinter、文件夹打开器或扫描任意宿主路径；这些端点
会返回说明明确的 403。浏览器上传文件仍可使用。

V2.3.9.4 的模型类型直接对应 `/data/projects/` 下的真实目录。浏览器上传 STL/OBJ 后，文件写入
对应模型目录的 `assets/mesh_selections/`，因此 `/data` 必须有足够容量并纳入备份。若通过 Nginx
等反向代理上传大模型，需要同步配置请求体上限和读取超时；应用自身限制为单文件 2 GiB、单次
8 GiB，代理可以设置得更严格。Web 文件视图只访问模型目录内的白名单文件，不开放任意宿主路径。

## 直接运行统一服务端

直接执行 `python run.py`。启动器强制设置 `MUJOCO_STUDIO_SINGLE_USER=0` 和
`MUJOCO_STUDIO_DESKTOP=0`，并默认监听所有网络接口。运行进程的电脑是服务端，不是特殊客户端：
它自己通过 `http://127.0.0.1:<hub>` 登录，局域网其他电脑通过
`http://服务器局域网IP:<hub>` 登录，两者使用完全相同的 API、会话和权限链。

关闭桌面能力意味着 tkinter 路径选择、打开服务器文件夹和原生 Viewer 等“操作服务器桌面”的端点
对所有账号一致拒绝；浏览器文件上传、建模、仿真、优化及导出下载不受影响。若其他电脑无法连接，
需要在服务器操作系统防火墙中允许 TCP `<hub>`（未改时 8765）。固定默认密码仅适合受信局域网；跨网段或公网部署
必须使用 HTTPS 反向代理并通过环境变量覆盖为强密码。

## 备份与恢复

停写后备份完整 `/data`，尤其是 `projects/`、`auth/`、项目版本与结果目录。`auth/users.json` 和
`auth/admin_mode.json` 权限应为 `0600`。恢复演练需验证项目、版本、账号登录与管理员模式密码；
内存会话不属于备份内容。


## V2.4.5.1 持久化同步与临时目录回收

服务端默认启用 `MUJOCO_STUDIO_FSYNC=1`。项目 JSON、持久 UI 状态和事件压缩写入采用同目录唯一临时文件、flush/fsync、`os.replace`，并在平台支持时同步父目录。设置 `MUJOCO_STUDIO_FSYNC=0` 可降低慢盘写延迟，但服务启动会明确 WARNING：**已禁用持久化同步，掉电可能丢失最后一次写入**。生产数据盘建议保持默认开启。

Windows 上 Python 的普通目录句柄无法可靠执行 POSIX 风格 directory fsync；实现会在目录 fsync 不可用时安全降级，不让一次正常保存因此失败。文件本身仍会 flush/fsync 后再 `os.replace`，但突然掉电下对“目录项替换已持久化”的保证弱于支持目录 fsync 的 POSIX 文件系统。此边界不能用单元测试替代，发布前需在目标 Windows 磁盘执行 S1-E1/E2/E3。

`MUJOCO_STUDIO_ORPHAN_WORKSPACE_TTL_HOURS` 默认 `24`、最小 `1`。启动时只回收超过 TTL 且不受活动 Job、Viewer 或临时编辑会话保护的 `core/job_workspaces/*`、`.edit_sessions/*` 与 `outputs/viewer/*`。回收统计写入数据根目录 `workspace_reclaim.json`，最多保留 20 条；`scripts/self_check.py` 也会报告这三类临时目录的数量、字节数和超 TTL 数量。

## V2.9.4 Linux 浏览器下载与回收站

Linux 服务端会在 `/api/health` 投射 `capabilities.direct_downloads=true`。前端据此让用户侧导出直接交给浏览器下载，不再弹出本地文件/目录选择器；文件最终位置由访问该服务的浏览器下载设置决定，而不是服务器文件系统路径。服务器管理性质的交付目录绑定、资产目录维护不属于下载目标选择，继续按既有权限执行。

用户删除模型后，项目进入 `${MUJOCO_STUDIO_DATA}/.trash/projects/`，管理员和工程师可在 Hub 回收站恢复。默认保留 7 天；可用 `MUJOCO_STUDIO_TRASH_RETENTION_DAYS` 调整，最小 1 天。若项目使用由 Studio 管理的外部交付目录，该目录会随项目一起进入回收站并在恢复时回到原位置。生产备份应把 `.trash/` 一并纳入；恢复发生路径冲突时应用会拒绝覆盖，需要管理员先处理冲突对象。

## V2.9.5 存档容量

普通模型 `versions/` 默认保留最近 20 个统一历史版本，只有“存档版本 / 基线版本”两类投射并使用同一裁剪链。手动签入可选择是否存档，自动签入会自动存档，签出不再生成版本；创建基线会在来源模型历史中追加一条基线版本但不会改写来源模型当前状态。可通过 `MUJOCO_STUDIO_MAX_VERSIONS` 覆盖默认值，`/api/health.max_archive_versions` 会返回实际运行上限供前端同步显示。基线模型本身仍不暴露普通存档列表。


## V2.9.5.1 Windows / Linux 统一直接下载

从 V2.9.5.1 起，用户侧下载/导出不再按服务端操作系统分支：Windows 与 Linux 均直接触发浏览器下载，前端不再调用 `showSaveFilePicker()` / `showDirectoryPicker()` 让用户选择下载路径。最终落点由访问页面的浏览器下载设置决定。服务器管理性质的数模目录维护、交付目录绑定等操作不属于下载目标选择，仍保持原权限和路径语义。

### V2.16.11.4 维护说明

Hub 签出排序、跨模型 TSJSON 选择和坐标系布局导入不改变服务端监听端口；`ports.json`、`python run.py stop/status` 和 Client/VZ 版本兼容方式延续 V2.16.11.2。跨模型数据只从同一 Hub 数据根与授权模型读取，不需要部署新的数据目录或数据库。

### V2.16.11.4 更新注意

本次仅更新结果坐标系前端工具栏和 Server/Studio/Lab 版本标识，继续读取 `Server/ports.json`，使用 `python run.py` 启动 / `python run.py stop` 停止。部署后请强制刷新浏览器以加载新的 `styles.css?v=2.16.11.4`、`app.js?v=2.16.11.4`。旧项目布局和导出数据无需迁移。
