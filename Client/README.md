# MuJoCo Studio 轻量客户端 V0.3.9（V2.11.7 配套）

配套 Server V2.11.7；Client 运行版本仍为 V0.3.9 / WindowsFix。V2.11.7 的项目文件夹属性、基线名称编辑/去重与冻结时间展示全部位于 Server/Web 现有 seam，不改变 Client-native Viewer 协议：bundle schema 仍为 4、controller signature 仍为 4、`run_viewer()` 调用参数不变。V2.11.6 的目录穿透、基线日志预填和企微封存继续继承，因此无需提升 Client runtime；V2.11.3.x 的低延时电机、闭链与 mapping-family 行为继续由 Server-supplied controller 获得。

## 服务端地址与 Client 端口（统一部署配置）

- 新增 `Server/ports.json`：`server_ip` 是 Client 要连接的 Hub 服务器 IP，`hub` 对应 Server 网页/API，`client` 对应本机 Viewer 桥，`vz` 对应集成 VZ。完整源码目录中直接运行 `Client/main.py` 会自动读取 `../Server/ports.json` 中的 `server_ip` / `hub` / `client`，无需再改 `SERVER_PORT` / `PORT` 数字。
- Client 独立安装在其他电脑时，需将服务器使用的同一个 `ports.json` 文件**复制到该电脑 `Client/ports.json`**（配置副本；远端不会自动同步服务器本地文件）。修改后重启 Client。若未提供配置则沿用默认 `server_ip=10.13.90.107, hub=8765, client=8766, vz=8877`。
- `SERVER_IP` 现在由 `ports.json` 的 `server_ip` 派生，默认 `10.13.90.107`；修改 IP/端口只改 JSON，不必修改 `main.py`。已部署的 `MUJOCO_STUDIO_SERVER_IP` 环境变量仍可覆盖配置文件。
- 本地桥始终绑定 `127.0.0.1`；浏览器 Origin 必须严格等于配置的 `http://SERVER_IP:hub`，未更改票据、认证和 Viewer 运行协议。
- `client_config.json` 只保存 `mesh_path` 等本地运行状态，不持久化或覆盖 `server_url`。Client 仍为 **0.3.9**，保持 bundle/controller schema 不变。

## Viewer 状态与 runtime 生命周期

- Viewer 子进程继续使用 `python -u`，stdout 逐行读取。
- `ViewerRegistry` 保存当前 Client 进程创建且仍存活的 Viewer，并可返回其受保护 bundle 目录。
- Client 启动时仅白名单清扫 `RUNTIME_ROOT` 下超 TTL 的 `viewer_*` 目录与 `mesh_sync_*.zip`；日志、配置、页面、符号链接和其它文件不参与清扫。
- TTL 默认 24 小时，可由 `MUJOCO_STUDIO_CLIENT_ORPHAN_TTL_HOURS` 配置。
- `runner.py` 在 Viewer 存活期间每 60 秒刷新 bundle 目录 mtime。这样 Client 自身重启、内存 Registry 丢失后，仍在运行的 detached Viewer 不会仅因“新 Registry 不认识它”而被当作超期孤儿删除。
- Viewer 正常退出仍删除自身 bundle；启动失败仍沿用既有清理路径。
- `log_tail` 保留用于诊断与旧服务端兼容；Viewer Bundle schema 1/2/3/4 保持兼容，轨迹播放与数模资产绑定语义不变。

运行方式与 V0.3.6 相同；依赖仍以项目内 requirements / 启动脚本为准。
