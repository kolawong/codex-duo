# Codex Duo 0.7.0 本地更新

新增高级设置最大并行执行代理数 1 / 2 / 3（默认 1），总次数由整个任务和全部修正共享。
旧配置与旧交接快照保持可读，读取不会重写设置。宿主容量保持原样；本机仍可串行验证。

沿用 `fusion-minimal@fusion-local` 身份、既有启用状态、图标和应用偏好。验证后通过受支持入口更新：

```sh
/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex plugin add fusion-minimal@fusion-local --json
bash macos/build.sh
open "macos/dist/Codex Duo.app"
```

插件详情页编辑全局默认；面板明确选择全局默认或当前项目。实际 CODEX_HOME 下 `codex-duo/selection.json`
独立保存全局模型偏好，原有项目配置继续作为覆盖，更新不自动迁移或覆盖它们。
全局自动使用需用户授权安装全局 AGENTS.md 管理块，模板位于规范 codex-duo 技能。
保存设置不安装指令；项目仍可通过明确自动保存添加项目块。读取、切换、普通兼容保存不会写指令。
手动模式停止对应范围的自动派发；项目重置继承会备份原设置并检查两层版本。

聊天始终显式传真实 cwd；MCP 固定启动路径只兼容旧无 root 调用，不是全局项目选择。
已有聊天可能需要一次 `$codex-duo` 或重载工具/指令。不要为刷新自动创建聊天或重启 Codex。
主线程复核 diff、测试、已安装资源和实际 UI 后再验收。

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
