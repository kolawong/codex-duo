# 本地插件安装缓存更新

按 `NATIVE-INSTALL.md` 的官方流程执行 `codex plugin add codex-duo@codex-duo-local --json`，退出码 0。原有 marketplace 已指向本项目，无需重新注册、迁移设置或直接编辑缓存。旧插件已备份为 `previous-plugin.zip`。

- 源码、官方已安装列表及新启动 MCP 握手版本均为 **0.9.8**。本次为同版本源码刷新。
- 安装路径：`/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.9.8`。
- 缓存全部 **50 个文件**与当前插件源码 SHA-256 一致，无缺失、额外或不同文件。
- 从已安装 `.mcp.json` 启动只读 stdio 检查：初始化成功，发现 20 个工具；`codex_duo_begin.worker_override` 含 model/effort；`codex_duo_complete.native_dispatch` 含 tool/agent_id/parameters/runtime，角色限定 codex_duo_worker，fork_turns 限定 none。
- 只调用 `codex_duo_defaults` 读取实际项目；默认仍为 **gpt-6.1-sol / high**，来源 project，Planner disabled，completion return。
- 全局/项目 selection.json 与两份 config.toml 均保持原字节；429 个项目任务状态文件、全部已跟踪源码、main 分支和 HEAD 均未改变。未提交或推送。
- Worker / Planner 派发次数均为 **0**，没有创建 begin/plan/reserve 记录；未进行真实模型验收。
- 未遇到依赖或权限阻塞。

## 需要重新加载的范围

当前聊天发现的 begin/complete 工具定义仍没有新参数，见 `loaded-chat-schema.json`；安装成功不代表当前聊天 schema 已刷新。

重新加载当前 Codex 聊天/会话，并重新发现工具。若当前宿主没有会话重载入口，或重载后仍是旧 schema，请完全退出并重开 Codex 桌面应用后再打开本项目聊天。若恢复同一旧聊天仍保留旧定义，需在本项目开启新聊天。无须重启 macOS、重新安装 Python 或修改保存偏好。

独立的菜单栏 Codex Duo.app 不在本次插件缓存更新范围。只为加载 MCP 新工具无需重开菜单栏应用；若要让正在运行的菜单栏应用显示前一轮构建的轻任务预设，则另行退出旧实例并打开 `macos/dist/Codex Duo.app`。

证据：`install-result.json`、`cache-comparison.json`、`installed-stdio.jsonl`、`installed-verification.json`、`preservation-final.json`。
