# Fusion Minimal 0.3.1 修复与本地重装

2026-10-08（Asia/Taipei）。用户已批准本轮修复、补充校验、版本更新和本地重装。

## 结果

**源码已修复，0.3.1 已安装并启用；原生宿主工具和面板仍未验收。** 不把独立 MCP 握手当作桌面实际加载成功。

本机 CLI `plugin add fusion-minimal@fusion-local --json` 成功返回版本 0.3.1，缓存为 `/Users/kola/.codex/plugins/cache/fusion-local/fusion-minimal/0.3.1`。新缓存的 25 个文件与项目源码逐文件 SHA-256 一致。旧版证据及原文件备份保留。

## 修复内容

- 便携 `mcp.json` 及兼容 `.mcp.json` 的命令从绝对路径改为 `python3`；保留原启动参数、固定部署目录、传输和插件身份。
- 清单、MCP serverInfo 及界面客户端版本同步为 0.3.1；重新构建自包含 HTML，没有下载或升级依赖。
- 静态校验补上便携命令语义检查、MCP 服务版本一致性检查；增加已安装状态模式及明确的本轮全局配置基线，保留初始禁用状态的校验方式。
- 新增 5 个回归测试，覆盖旧绝对路径拒绝、合法命令、目录越界/非法值、符号链接越界及实际清单启动。
- SDK 测试改为读取清单中的启动声明，避免继续硬编码解释器而漏测声明。SDK 启动仍不等于宿主插件解析，因此另有静态规则校验。

## 检查结果

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 静态校验 | 36 项通过；规范项目安装后再次通过 | static-validation.json、canonical-static.log |
| Python 测试 | 共 68 项，61 通过；7 项旧 HTTP 测试因沙箱禁止绑定 loopback 端口报 PermissionError，未通过 | tests-031.log |
| 受影响的回归测试 | 5 项通过，包含按清单启动真实 stdio 子进程 | tests-031.log |
| 官方 MCP SDK 测试 | 8 类检查通过，使用临时项目；模型调用为 0 | sdk-client.json |
| 真实新缓存 | 返回 serverInfo 0.3.1、7 个工具；只读 settings_read 成功 | installed-handshake.json |
| 安装/启用 | 0.3.1，installed=true，enabled=true | plugin-list.json |
| 缓存一致性 | 25 文件与源码一致 | installed-cache.json |
| 配置保护 | 全局配置、项目配置、保存的模型选择字节哈希不变 | preservation.json |

7 项 HTTP 测试不涉及此次命令修复；没有为重跑这些测试扩大监听权限。不能将本轮说成全部 68 项测试通过。

## 原生宿主仍待完成

当前会话最终 Fusion 工具发现结果为 0。受支持的 MCP Apps 后端可用，但本任务的面板列表为空。CLI MCP 列表仍只显示旧的 `fusion-local` HTTP 条目；没有据此声称便携 MCP 已注册到当前会话。

旧 HTTP 条目仍维持原样，本轮没有修复或停用其先前的 502 故障。新插件命令规则缺陷已修正，但尚无桌面直接调用或面板渲染证据，不能断言没有其他加载问题。当前 shell 的 `python3` 指向 Homebrew Python；桌面子进程解释器选择尚未实测。

下一项最小人工操作：在**本会话**重新 @ Fusion Minimal，发送“打开模型面板，仅做只读检查”。这样可在下一轮观察插件是否重新提供工具，不另建模型任务、不改配置。若仍无工具，应继续核对宿主插件加载诊断；本轮没有获得新的重启授权，故未重启。不得绕过 Codex 主 UI 自动化限制。

## 交付文件与恢复

- 项目源码：`/Users/kola/codex-fusion`。
- 新插件包：`/Users/kola/codex-fusion/fusion-minimal-0.3.1.zip`，SHA-256 见 package.json。
- 原文件备份：本目录 `before-source/`，只备份此次改动的已存在文件。
- 改动清单和部署前源文件哈希：deploy-plan.json。
- 本轮脚本副本：deploy.py、verify_install.py；包含固定路径，不应在未审阅时重复执行。

若以后要求回退，应从 before-source 恢复本次文件，并审查新增测试文件后按旧版本重新安装；不要覆盖保存的模型选择或整份全局配置。本轮未执行回退。

未执行：额外模型或双模型任务、Hooks 安装/信任、全局模型修改、旧 HTTP 服务重配、应用重启/升级、推送或发布。
