# Fusion Minimal 0.3.2 本地更新

MCP 声明使用插件内可执行入口 `./mcp/launch.sh --project-root /Users/kola/codex-fusion`，工作目录仍为 `${PLUGIN_ROOT}`。宿主将相对命令解析为安装缓存中的路径。启动器由 `/bin/sh` 运行，首先检查 PATH 中的 Python，然后检查既有 `/opt/homebrew/bin/python3`、`/usr/local/bin/python3`、`/usr/bin/python3`；仅接受 Python 3.11+。没有安装依赖、加载 shell profile 或更改全局 PATH。

用户已授权本插件修复和本地重装。先运行回归测试和静态检查，再执行官方 `codex plugin add fusion-minimal@fusion-local --json`。不直接编辑安装缓存，不创建全局 MCP，不信任 Hooks，不启动模型。

验收必须区分安装成功、独立 MCP 握手、实际会话工具调用、面板资源和 UI 渲染。详见 [本轮报告](evidence/update-032/REPORT.md)。
