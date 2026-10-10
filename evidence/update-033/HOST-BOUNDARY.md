# 有界宿主诊断结论

**停止继续修插件。当前能证明本机安装服务可用、此 durable 会话 MCP 启动失败；不能证明确切的跨文件系统映射，也不能断言所有委派会话都不支持 repo-scoped MCP。**

## 已证实的两条执行链

| 层 | 证据 | 能证明什么 |
|---|---|---|
| 本机 CLI / 进程 | resolved-mcp.json 与 installed-readonly.json：0.3.3 绝对 launch.sh、cwd、PLUGIN_ROOT，26 文件一致，7 工具及只读调用通过 | 安装声明解析和本机子进程有效 |
| 当前对话宿主 | 同线程 VM lifecycle 为 environment_connected、hostId=durable；随后 Fusion starting → failed；实际资源接口报 exec-server ENOENT | 当前会话连接已尝试启动 Fusion，但失败 |

同一任务的 shell 可访问本机项目，不足以证明 MCP 的 spawn 也落在该 shell 执行环境。hostId=durable 是日志标签，本轮没有把它自行解释成具体远程机器或容器地址。

## 官方支持范围

1. [MCP 官方文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) 的 Local computer access with Work Cloud 说明：本地 MCP 服务和传输在云端可能不可用，需分别验证连接和认证。它同时说明 STDIO 本地进程，以及 experimental_environment=remote 可在可用的远程执行环境启动。**这证明存在执行环境边界，并非此任务必然不支持的保证。**
2. [插件打包文档](https://developers.openai.com/plugins/build/plugins) 说明本地 / 仓库市场与公共目录不同，其可用性随 surface 而异。没有找到针对本任务 durable 委派形态的更精确公开支持矩阵。
3. [App Server 文档](https://learn.chatgpt.com/docs/app-server) 提供按线程查 MCP 状态和调用工具的方法。当前会话没有暴露这些管理工具；官方默认本机控制 socket 不存在，未尝试猜其他 socket 或附着内部端点。

## 可观测性缺口（本轮终点）

本机版本导出的官方 MCP status 与 startup-notification schema 不返回 spawn command、argv、cwd、PLUGIN_ROOT、执行器文件系统映射。桌面日志也只返回通用失败，failureReason=null。因而缺少：

- 会话启动时真正使用的声明及插件版本（是否确实为 0.3.3）；
- exec-server 收到的 command/argv、cwd、PLUGIN_ROOT；
- exec-server 的执行目标和该目标对上述路径的可见性；
- ENOENT 对应的具体路径。

没有这些证据，继续换 Python、重装或重启无法区分插件故障与宿主边界。本轮未再运行启动探针、修改插件、重新安装、重启、启动额外模型或改环境配置。

## 最小可复现材料

同一个已启用 repo 插件，先用本机官方 CLI `mcp get fusion --json` 获得缓存启动声明，并对其独立只读调用成功；该委派会话的实际工具目录无 Fusion，resources/list 与 resources/templates/list 返回 exec-server ENOENT。对应线程 ID、日志行、启动状态、官方 schema 字段、已解析配置见 host-boundary.json；实际会话调用证据见 session-recheck.json。

## 唯一建议的对照（需用户手动，不自动建任务）

在 Codex 桌面直接打开 /Users/kola/codex-fusion 项目，创建一个明确选择本机 Local 的普通会话，避免从父对话委派、Work Cloud 或 fork 当前 durable 会话。先用 /mcp 查看连接；需要只读工具实测时发送：

> 只读验证 Fusion Minimal：先查看实际工具目录；若 fusion.open 可调用，调用一次并读取面板资源，核对执行环境。不要修改文件、保存设置、安装、重启或运行模型工作者。若无工具或仍报错，报告准确结果并停止。

此对照只改变宿主形态，沿用同一插件版本和文件。若普通 Local 会话能发现并调用 Fusion，而本任务不能，便能定位为宿主 / 会话类型差异；若仍失败，不能接受该假设，应将现有复现材料交给产品侧排查启动映射。没有承诺对照一定成功，也未要求重复 @ 插件。
