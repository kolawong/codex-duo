# Codex Duo 0.9.9 本地插件更新验收

用户已授权本机官方本地插件刷新。本轮只更新插件包与版本元数据，没有启动 Worker/Planner 或修改保存偏好。

- 官方 CLI `codex plugin add codex-duo@codex-duo-local --json` 成功。安装版本 **0.9.9**，实际缓存路径 `/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.9.9`。官方 `plugin list --json` 显示已安装、启用，来源仍是当前本地项目。
- 同步 `.codex-plugin/plugin.json`、`plugin.json`、MCP `server.py` 版本和 `tests/test_native.py` 版本断言为 0.9.9。更新说明在 NATIVE-INSTALL.md。
- 安装缓存与源码逐文件 SHA-256 对照：51/51 文件一致，没有缺项、额外文件或不同哈希；集合哈希 `4726a495e11ea0ffcd2e45d2484198450e97f38a14cabaf7cde6a921fc014441`。安装目录的 MCP stdio 服务握手回报 0.9.9，发现 20 个工具。
- 从已安装服务工具定义确认 `codex_duo_begin.worker_override` 有 model/reasoning_effort 两个字段；`codex_duo_complete.native_dispatch` 含 tool、agent_id、parameters、runtime，且参数 schema 限定 `agent_type=codex_duo_worker`、`fork_turns=none`。只调用只读 `codex_duo_defaults`：项目 Worker 仍 gpt-6.1-sol/high、预算 10、并行 1、Planner disabled、return，execution_started=false。
- 缓存中的 `assert_bytes.py` 与源码包含在完整包逐文件哈希匹配内。已安装缓存脚本用 Python 3.11 对临时路径（含空格、反斜杠和引号）执行 hex `61667465720a`，exit 0。
- 偏好与配置文件哈希前后相同；`.codex-duo` 中 458 个已有 runs/handoffs 文件哈希和数量前后相同。派发 0，设置写入 0。细节见 preservation-final.json。
- 本轮未执行完整单元测试；版本、安装路径、缓存内容、MCP tools/list schema 与只读 defaults 已直接核验。没有重建或启动菜单栏 App。

## 新聊天加载要求

官方缓存已安装，但当前聊天的原生工具 schema 不会因安装自动刷新。重开 Codex 聊天/会话并在本项目新开一个普通 Codex 聊天，使其加载当前插件版本与本项目指令。重载后的普通 Codex 新聊天可使用以下最小真实验收提示；本轮没有调用它：

> 使用当前插件和项目默认设置，仅在新临时 probe 文件中写入 UTF-8 字节 `after` 加 LF。派发一次原生 codex_duo_worker；Worker 对已授权文件直接运行 argv `["python3", "-B", "plugins/codex-duo/skills/workflow/scripts/assert_bytes.py", "<probe路径>", "61667465720a"]`，禁止 shell 与二次解码。按现有快照、diff、result、preflight 和 complete 流程记录真实 argv 与退出码。只允许一次 Worker 派发，不调用 Planner，不修改偏好；如 schema 未加载或预检失败则停止并如实报告。

这个提示须由用户另行在普通 Codex 新聊天发起，作为新任务产生一次真实 Worker 执行。本次安装和离线探测都不证明 Worker 的运行时模型身份，也不证明当前聊天 schema 已热更新。
