# Fusion 0.3.0 本机安装记录

2026-10-08。已完成官方 CLI 市场注册、插件安装和本项目插件启用；真实 Codex 设置页及会话面板显示仍待人工打开后核验。

## 已完成

- `plugin marketplace add /Users/kola/codex-fusion --json` 返回 `fusion-local`、`alreadyAdded=false`。
- `plugin add fusion-minimal@fusion-local --json` 成功安装 0.3.0，缓存位于 `/Users/kola/.codex/plugins/cache/fusion-local/fusion-minimal/0.3.0`，逐文件与批准的源码一致。
- CLI 安装清单显示 `installed=true`、`enabled=true`；项目 `.codex/config.toml` 只将此插件的 enabled 从 false 改为 true，agents 仍禁用，Hooks 仍关闭。
- 从真实缓存的 `mcp.json` 展开启动命令，用官方 MCP SDK 启动本地 stdio 进程，完成握手、7 个工具发现、结构化设置和 HTML 资源读取。临时将 worker 改为 Luna/low，成功读回，随后恢复原始 selection.json 的逐字节内容。测试进程完成后已关闭；这不证明桌面后台已经动态连接它。
- 全局变更仅限 CLI 的插件/市场注册记录；全局模型及所有非插件/市场配置的归一化哈希保持不变。原有 34 项插件版本与启用状态未变。没有真实模型任务、Hooks 信任、应用重启或发布。

相关证据：`before.json`、`installed.json`、`installed-mcp-check.json`、`plugins-before.json`、`plugins-after.json`。原项目配置和模型配置分别备份为 `project-config-before.toml`、`selection-before.json`。

## 尚未完成的界面验收

Computer Use 返回明确限制：不允许操作 `com.openai.codex`。未尝试用其他自动化技术绕过。专用 MCP Apps 后端可以访问当前任务已打开的 App，但本次列表为空。当前任务也未暴露 Fusion 原生工具。只读 app-server 探针在 initialize 超时，未读取宿主插件元数据；见 `app-server-probe.json`。

因此不能声称已看到原生设置、侧栏、权限提示或取得原生截图；没有用上一轮测试宿主截图充当安装证据。电脑仍可执行 CLI，此问题不是整个本机断连。

下一步请用户在 **Codex 插件目录搜索并打开 Fusion Minimal**，检查是否出现 **Fusion · 新任务默认配置**，点击 **打开模型面板**，并在本任务侧栏保留该 App。设置字段名和按钮名来自实际 MCP 响应；插件目录的具体菜单层级尚未通过主界面核验。App 打开后可用受支持的 MCP Apps 后端继续检查保存恢复与截图，无需再申请安装批准。

如果入口未出现，需先取得用户界面反馈，再确认宿主刷新/新任务等支持路径；不自行重启应用或创建额外模型任务。

## 可恢复操作（仅记录，未执行）

如用户要求撤销：用本机 CLI 执行 `plugin remove fusion-minimal@fusion-local --json`，再执行 `plugin marketplace remove fusion-local --json`；只把项目此插件开关恢复为 false。不要用整份旧配置覆盖用户后续修改。模型配置已经原样恢复，无需再写入。插件源码和 0.3.0 归档保留在项目。

先前 `tools/validate_static.py` 的预安装断言要求插件禁用和全局配置哈希不变，因此不适用于当前已批准的安装状态；本记录改以安装结果、缓存一致性、非插件全局配置哈希以及服务读写恢复进行核验。历史静态测试记录保持原样。
