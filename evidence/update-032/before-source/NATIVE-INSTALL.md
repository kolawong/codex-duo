# Fusion Minimal 0.3.1 本地更新

用户已批准修正命令声明、增加校验、更新版本并本地重装。沿用 `fusion-local` 市场和 `fusion-minimal` 身份，不另建全局 MCP 条目。

- 启动声明：`python3 -B ${PLUGIN_ROOT}/mcp/server.py --project-root /Users/kola/codex-fusion`，工作目录 `${PLUGIN_ROOT}`。
- Python 必须能够运行本包；本轮 shell 解析到既有 Homebrew Python 3.14.7。桌面子进程解析仍须宿主实测。
- 从源码按版本安装，不直接编辑缓存。0.3.0 的历史证据和安装记录保留。
- 读取插件文件、项目 `.fusion/` 和内置模型目录；仅按已有功能写项目选择及交接。无任意命令/路径接口。
- 更新不改变全局模型、其他插件、旧 `fusion-local` HTTP 服务或 Hook 信任，不创建模型任务、不重启、不升级或发布。
- 本机进程权限维持原安装范围，代码约束不等于操作系统强制沙箱。

先验证命令规则及清单启动，再用本机 CLI 执行 `plugin add fusion-minimal@fusion-local --json`。安装后分别核对缓存版本、实际宿主工具发现和面板。需要额外刷新、重启或权限时先报告，不能把独立握手当成原生界面验收。

结果及未通过项见 [更新报告](evidence/update-031/REPORT.md)。旧版检查见 [0.3.0 安装记录](evidence/install-001/REPORT.md)。
