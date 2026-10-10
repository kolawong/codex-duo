# Fusion 模型面板验收记录

2026-10-08；项目 `/Users/kola/codex-fusion`；版本 0.2.0。

已实现主控和执行模型分别选择、各自推理强度、三个受目录支持的预设、原子保存、磁盘恢复、任务交接快照和 CLI 联动。完整日志保存在项目内，不回灌主线程。

承载结论：本机 Codex 内置浏览器实际打开并操作成功。本次交付为独立 localhost 网页。官方 MCP Apps 扩展支持桌面侧栏承载，但需要 MCP 资源、opener 工具和连接；没有安装或注册这些组件，不能宣称原生插件面板已经接通。依据：[OpenAI MCP extensions](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md)。

本机桌面版本 26.1002.52244（13536），内置 CLI 0.162.0-alpha.2。模型目录来自本机 CLI 的 `debug models --bundled`，过滤 hidden 后 8 个模型，见 `model-catalog.json`。目录与账号权限、实际模型路由分开表述。

最终验证：44 项自动化测试、27 项静态检查通过；浏览器已验证保存、恢复、重载、预设脏状态、强度纠正、无效任务反馈与恢复、重复交接去重。1032px 桌面和 390px 窄屏均无水平溢出。浏览器控制台检查无警告或错误。截图见 `panel-desktop.jpg` 和 `panel-mobile.jpg`。

浏览器保存的候选组合为 Astra/high 主控、Luna/high 执行。生成的交接包为 `.fusion/handoffs/70748ae865db95a47afd861f/`。真实 CLI prepare 复用同一包，返回 `created=false`、`execution_started=false`。保存和生成均不会启动任务，也不会改变当前会话模型。

验收期间没有启动额外模型任务，没有安装插件、信任 Hooks、修改全局配置、重启、推送或发布。项目 `.codex/`、`.agents/` 及历史证据哈希保持不变，详见 `acceptance.json`。插件归档与当前源码逐文件核对一致。

实际启动新的双模型任务、注册安装插件或接入 MCP App 面板仍需另行明确批准；当前面板和离线交接功能无需这些操作即可使用。命名 TOML 自动发现仍未验证，早期 app-server 初始化超时不作为不支持的证据。

启动：在项目目录运行 `python3 -B panel/server.py`，打开 `http://127.0.0.1:8765`；Ctrl+C 停止。默认状态只写入本项目 `.fusion/`。
