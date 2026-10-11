# 原普通聊天唤醒：只读连接预检结论

2026-10-11 · 项目 `/Users/kola/codex-duo` · 指定目标 `01a129b2-b37e-7613-8603-2521e4b042f7`

**结论：未建立插件可用、属于原桌面宿主的官方连接；不能可信绑定指定聊天，后台唤醒预检不通过。** 结论限于本次可见进程、公开入口及授权范围；不否定其他通路或原 Planner/Worker 验收。

| 分类 | 本次确认 |
|---|---|
| **已支持：协议原语** | `proxy --sock`、显式 `--remote`、stdio/Unix/WS 有官方定义；`thread/read` 可指定 ID，`turn/start` 有 `threadId + toolOutput`。不等于本机已连通；WS 仍属实验性、不支持生产负载。[依据](SOURCES.md) |
| **当前不可用：连接** | CLI `0.162.0-alpha.17.2` 的 `daemon version`、显式默认路径 proxy 均 exit 1、ENOENT。08:53 UTC 最终复核仍相同，默认目录不存在；此次 shell 未设 CODEX_HOME。源码确认 proxy 取显式／默认路径，不自动发现桌面实例。[最终回执](final-readonly-recheck.json) |
| **新增实证：宿主进程** | 桌面 PID 45746 的 Codex 子进程 46222、46809 通过匿名标准输入输出 socket 对通信；另两核心进程使用管道。四个核心进程均未见命名 Unix socket；它们、桌面及 Code Mode host 均未见 TCP LISTEN。桌面私有 IPC 仅查看元数据，未连接。[记录](socket-metadata-bounded.json) |
| **未知：指定聊天绑定** | 未确认目标的宿主、cwd/projectId 或上一轮 completed。`region11` 仅为父端背景，不证明目标不存在。schema 的 codexHome／版本／平台及 sessionId／originator 不足以单独证明当前桌面 owner；连接门未过，未读取聊天。[类型校对](schema-generation.json) |
| **不支持／不等价** | Duo 仍为 `wake_supported=false`；`ui/message` active/new 无任意原 threadId。原生等待和工具返回继续**当前轮**，子任务 completed 不证明**父轮结束后唤醒**。前台 View 发消息依赖实例并提交用户消息。独立 app-server 读到相同 ID 也不证明原桌面恢复。 |

**下一步最小信息**：宿主／官方需提供管理此原聊天的现有公开入口：传输、socket 路径或无凭据 URL、实例归属及与指定 ID／项目的绑定依据。不需要再次提供 ID、密钥或聊天内容。入口存在且已授权后，可仅握手和 `thread/read(includeTurns:false)`，**0 模型、不启服务、不 resume**；notLoaded 或归属不明即停止。

若需 start/bootstrap、新增 listen、启用 remote-control 或改设置，会新增服务／监听，可能安装组件或写持久配置；重启可能影响会话，仍不能保证原宿主绑定。**这些动作本次不可执行。** 真正 turn/start／发消息会改变聊天并消耗模型，需另行授权；两轮 Sol/high 建议未执行。

**边界**：本预检新增模型／消息／服务／resume/create／UI 操作均 0；仅在本目录保存证据，无源码、配置、偏好、任务状态或 Git 历史修改。08:34 UTC 的 [验证快照](verification.json)确认 119 个基线文件和目录外 Git 状态不变；该快照不保证其他任务随后没有改动共享工作树。未运行产品测试／构建。[逐项命令](CHECKS.md) · [机器可读结论](preflight-result.json)。
