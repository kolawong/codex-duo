# Codex Duo 0.5.0 本地更新

继续使用 `fusion-minimal@fusion-local` 插件身份和既有启用状态。通过受支持入口更新源码包，
不直接改缓存、不改全局配置、不安装 Hooks：

```sh
/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex plugin add fusion-minimal@fusion-local --json
bash macos/build.sh
open "macos/dist/Codex Duo.app"
```

canonical 技能为 `codex-duo`，`fusion` 是兼容别名；辅助脚本继续位于 `skills/fusion/scripts`。
更新不迁移或覆盖已有 `.fusion/selection.json`。菜单选择属于本地设置应用，各聊天仍从自己的项目
cwd 显式调用工具。MCP 启动参数固定路径仅作旧无 root 调用兼容，不是新聊天的自动路由。

在新项目选择「本项目自动」并明确保存，会保留现有 `AGENTS.md` 并添加有界指令块；
无需更改全局配置或创建项目 `.codex/config.toml`。读取/切换/普通兼容保存不会写指令。
新项目复制只带模型选择，初始模式为手动。手动保存后即使保留指令块，技能也读取模式后停止自动派发。
符号链接或损坏管理块会阻止启用，配置保存失败会回滚指令；界面保留草稿并报告错误。

已有聊天可能需要一次明确 `$codex-duo` 或重新加载项目指令/工具；新版本安装回执不证明旧聊天
立即更新。不要为此自动创建聊天或重启 Codex。主线程复核 diff、测试和实际 UI 后再验收。

---

以下为历史版本记录。

# 0.4.0 更新：持久默认配置与项目自动流程

沿用 `fusion-minimal@fusion-local` 插件身份和 `.fusion/selection.json`。更新前备份源码、项目配置和选择文件；原模型组合不变，新增 workflow 配置（项目自动使用、当前聊天主控、最多 3 轮）。项目 `AGENTS.md` 负责自动入口，`.codex/config.toml` 只启用本项目原生子代理；全局设置与 Hooks 不变。

通过已有官方入口更新：

```sh
/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex plugin add fusion-minimal@fusion-local --json
```

发布包和安装缓存为 0.4.0。不要直接编辑缓存。新工具为 `fusion.defaults`、`fusion.begin`；旧交接工具保留兼容。通过全新 stdio 服务确认安装不等于当前聊天已刷新，旧聊天需要重新加载工具（通常新聊天即可）。不要为刷新而自动创建用户聊天或重启应用。

保存配置不执行模型；在用户实际开发任务中按已保存默认配置使用宿主原生子代理，并遵守范围和轮数限制。技能无可用执行工具时必须报告，不得使用隐式 CLI 模型进程替代。

---

以下为旧版本安装记录。

# Fusion Minimal 0.3.3 本地更新

MCP 声明使用插件内可执行入口 `./mcp/launch.sh --project-root /Users/kola/codex-fusion`，工作目录仍为 `${PLUGIN_ROOT}`。宿主将相对命令解析为安装缓存中的路径。启动器由 `/bin/sh` 运行，首先检查 PATH 中的 Python，然后检查既有 `/opt/homebrew/bin/python3`、`/usr/local/bin/python3`、`/usr/bin/python3`；仅接受 Python 3.11+。没有安装依赖、加载 shell profile 或更改全局 PATH。

用户已授权本插件修复和本地重装。先运行回归测试和静态检查，再执行官方 `codex plugin add fusion-minimal@fusion-local --json`。不直接编辑安装缓存，不创建全局 MCP，不信任 Hooks，不启动模型。

验收必须区分安装成功、独立 MCP 握手、实际会话工具调用、面板资源和 UI 渲染。详见 [本轮报告](evidence/update-033/REPORT.md)。

启动器为本进程及子进程追加 `/usr/bin:/bin:/usr/sbin:/sbin`，使内置 CLI 的 shell 包装器也能在受限 PATH 环境中使用系统工具。全局配置和宿主环境保持不变。
