# 原普通聊天自动回传/唤醒：研究结论

**结论：有官方候选 API，但尚未证实 Codex Duo 能在后台恢复桌面原普通项目聊天。现在不应开启自动唤醒。** 最值得继续的是“连接同一宿主 app-server 后，向精确 threadId 提交 toolOutput”；当前缺少受支持的同宿主连接与可信原聊天绑定。UI 消息扩展可做“结果就绪，点击继续”的候选，不足以承诺关闭面板后自动唤醒。

本轮仅调查与离线 fixture：额外主控/Planner/Worker/验收模型 **0 次**，聊天消息发送 **0 次**，UI 操作 **0 次**。没有改现有执行流程、插件安装、偏好、权限、凭据、Git 历史或提交。

## 更新后的已知事实

普通聊天的真实 Worker 验收已经成功：[原始报告](../../.codex-duo/runs/65821f50c5f63f912d8574c7/acceptance-report.json)。原生标识 `/root/single_worker_acceptance`，role `codex_duo_worker`，成功请求参数 Sol/high、fork_turns=none；派发 0→1，无重试；before→after；Worker 和主控独立断言 exit 0；complete 成功、verify=evidence_valid；同回执再次提交未改变账本哈希。宿主未提供 runtime 模型字段，不能把请求参数说成额外运行时证明。单次授权已用完。这个结果证明 0.9.1 原执行路线在该普通聊天成功，不证明父轮结束后的自动恢复。

## 支持等级

| 路线 | 已证实支持的范围 | 对“原普通聊天在父轮结束后恢复”的判断 |
|---|---|---|
| 当前 turn 的工具结果 | 工具返回后当前主控继续 | 不是新一轮唤醒；不能作为成功证据 |
| 原生子代理完成事件 | 上述验收报告证明收到完成并验收 | 父轮已结束后是否重启主控未测；插件不能假定拥有宿主内部通知权限 |
| 独立 app-server 监听 | 官方 turn/completed 通知可报告其管理的 turn | 收到事件不等于桌面原聊天收到结果；独立 thread/start 不满足目标 |
| Extended message sending | S1–S4 定义已连接 MCP App→当前/新会话消息 | 页面实例内候选；没有任意原 threadId、关闭后存活或 busy 保证；本机 UI 能力未读取 |
| 同宿主 app-server turn/start | S5 及本机 schema 支持 threadId + toolOutput，发起模型轮；active 时可并入已有轮 | **最佳后台候选，但本机同宿主通道与原聊天绑定未证实** |
| MCP Tasks / 普通通知 | S7 定义异步任务取结果；progress/log/resource 更新各有自身用途 | 没有被证实的普通聊天唤醒契约；本插件当前没有声明 Tasks |
| MCP Events webhook | S8 文档支持订阅事件后触发 Work/Cloud、dots | 不能迁移推定到原 Local Codex 聊天；也引入托管订阅、网络和 secret，非本轮路线 |

明确不支持的具体范围：当前 `ui/message` schema 不支持指定任意原 threadId；`turn/steer` 不支持已结束的轮；`ui/update-model-context` 和 `thread/inject_items` 不负责启动新模型轮；当前 Codex Duo 0.9.1 的 completion 层明确关闭 wake。这里没有断言整个桌面产品永远不支持自动唤醒。

## Extended message sending 的精确边界

消息能力属于已初始化的 **MCP App View**，不是 Python MCP server 获得任意会话写入权限。`ui/initialize` 需实际宣告 `message.text` 及 `experimental["openai/message"]`；`OpenAIExtensions(app).message` 仍可能不存在。已安装 ext-apps 2.0.3，但本项目没有安装 `@openai/mcp-extensions`；本轮没有安装依赖。[SDK 与类型证据](SOURCES.md)

`_meta["openai/message"]` 仅有 `target: active|new`、`send: boolean`。`send:false` 在桌面仅填草稿，不能算唤醒；默认 send:true 会提交用户角色消息并可能启动模型，绝不是免费通知。没有模型/强度覆盖字段，测试须先确认测试主聊天的模型。必须事先明确授权自动生成这条消息，不能伪装成用户再次授权 Worker。

Thread entrypoint 是各聊天独立实例，能提供实例内隐式范围；global entrypoint 使用自己的聊天。公开 hostContext 没有规范化的原 threadId；toolInfo.id 是 RPC ID，project_root 也不能唯一标识聊天。不能把浏览器当前前台聊天或最近使用项目当原目标。

已连接并存活的 View 是必要依赖；**未证实必须前台可见，也未证实隐藏后一定存活**。文档没有给出必须 user gesture 的统一规则，标准允许宿主要求 consent；故不能宣称后台免手势、免确认一定可用。切换聊天、卸载 View、应用休眠/退出后，定时器和连接不能视为可靠后台服务。官方建议跨轮用 fullscreen 只说明 UI 设计，不是后台生命周期保证。消息接口也未给 busy 状态、原 turn completed 事件、精确一次投递或消息→新 turn 回执。

兼容 `window.openai.sendFollowUpMessage({prompt,scrollToBottom})` 也属于组件运行时，未提供任意原聊天 ID；不能靠切换别名补上后台绑定缺口。[S9](SOURCES.md)

## app-server：可用原语与缺口

本机公开 CLI 为 0.162.0-alpha.17.2，可离线生成带版本的 schema。稳定输出有：

- `thread/read({threadId, includeTurns})` 读取；`thread/resume({threadId,...})` 加载旧线程。resume 本身不启动模型，但会改变运行态，本轮没有调用。
- `turn/start({threadId, input:[], toolOutput:{name,namespace,output}})` 将完成数据保持为工具输出并启动一轮，优于伪装新的用户授权。模型和 effort 覆盖在 schema 中是 sticky，测试只能使用隔离测试主聊天，不能顺便覆盖用户原偏好。
- `turn/steer({threadId, expectedTurnId, input})` 只针对活动轮；不能恢复已结束轮。`thread/inject_items` 只追加历史而不启动轮，也不符合唤醒成功标准。
- `turn/completed` 包含 threadId 与 turn；ThreadStatus 可为 active/idle/notLoaded/systemError。schema 中 clientUserMessageId 的存在不证明服务端 exactly-once；toolOutput 自身没有 eventId/幂等字段。

`turn/start` 遇 active 时可能向已有轮追加，特别是 toolOutput 会排给当前轮。即使先读到 idle，读与写之间仍有竞争；没有公开的 expected-idle/expected-last-turn 参数可原子锁定。因此首个实测必须保证测试聊天期间无用户并发输入；一旦忙碌，客户端只保留结果，不立即发送。不能擅自以 turn/steer 改变用户进行中的工作。

`thread/queue/add`、`thread/queue/start` 和 MCP event stream 出现在 **experimental** schema；其字段不足以证明自动启动、失败恢复和去重语义。本轮没有调用，不能作为现成稳定方案。

官方 CLI 有 proxy/control socket 路线，但 `daemon version` 检查默认 socket 不存在。[原始输出](daemon-version.stderr) 证明这条默认入口当前不可用；不是桌面内部实现不存在的证明。启动另一个 daemon/app-server 再 resume 相同存储 ID，也不能证明同一宿主的运行态/忙碌状态/桌面 UI 更新，更可能引入双 owner 竞争。必须先获得官方支持的桌面宿主连接方式和宿主绑定；不得扫描/复用私有端点、凭据或内部认证。

## 候选方案与最小依赖

| 候选 | 最小依赖 | 风险与当前决策 |
|---|---|---|
| 同宿主后台 dispatcher + toolOutput | 官方连接句柄；宿主提供的精确原 threadId/host/project 绑定；持久事件 ID；busy/unknown 保守处理；明确一次模型授权 | 条件未满足，暂不实施；目标最匹配 |
| 原聊天 View 保持挂载，结果就绪后用户点击继续 | 该实例消息 capability；用户明确点击；本地持久结果；原目标可确认 | 最小降级候选；用户重新进入原聊天后再操作，不宣称后台自动唤醒 |
| View 定时器自动发 active 消息 | 同上，另需父轮终止与生命周期证明 | 仍依赖 UI；可能误并入忙碌轮或丢失，不建议当前实施 |
| MCP Tasks、Events 或当前平台跨线程工具 | 用户插件实际被授予相应宿主能力及目标绑定 | 当前平台的 cloud_threads/Codex app 工具不属于插件可移植 API，不借用作验收 |

若无法补齐官方连接与目标绑定，诚实保留“结果已就绪，点击继续验收”，或让当前主控保留宿主等待。两者都不应标为父轮结束后的自动唤醒。

## 下一步

见 [MINIMAL-TEST.md](MINIMAL-TEST.md)：先做 **0 模型的能力/绑定预检**；当前默认 socket 缺失，预检不能通过时直接停止。只有路线成立并取得单独授权，才在一个普通项目测试主聊天内做 **最多 2 个 Sol/high 主控轮次**（初始化 1、父轮结束后恢复 1），0 Worker/Planner。busy 实机覆盖是另行批准的最多 2 轮，不能偷算进原已消耗的 Worker 额度。

本轮 [offline_fixture.py](offline_fixture.py) 只检查人工构造的时序证据是否满足验收定义；[fixture-result.json](fixture-result.json) 的通过不证明真实宿主能力。生产保护基线与最终检查见 [protected-after.json](protected-after.json)。

最终检查：12 个纯离线 fixture 案例通过；510 个保护文件 SHA-256 不变；Git 状态仅增加本研究目录，既有脏文件状态全部保留；git diff --check 通过。没有修改生产源码，因此未重跑产品全量测试或构建，也未宣称 UI/模型集成通过。
