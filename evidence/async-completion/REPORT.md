# Codex Duo 0.9.0：完成模式与派发路径审计

本轮实现了默认关闭的完成模式偏好、原账本上的可恢复完成记录，以及 Planner/Worker 回归修复。
**真正的后台自动唤醒仍不可用，未伪装为已实现。新增真实 Planner、Worker、验收模型调用均为 0。**
没有新开聊天、切换编码主控、commit/push、reset/pull、建分支或更新本机 memory。
本地仍为 `main`，HEAD `78f38bef638a7643c5dcfe46d8e19fe6694c469d`。

## 实际架构与宿主边界

- Planner：`begin` 固定请求、模型和代码基线；`run` 先持久保留额度与 attempt_id，
  再由独立 Python 进程连接官方 app-server。非模型代码监听 `turn/completed`，保存回执和结果。
  显式 readonly、禁网、approval never，并检查实际配置与返回的模型/强度。
  外部 MCP/apps、hooks、递归代理和模型 fallback 继续禁用；没有放宽任何权限。
- Worker：当前聊天协调原生工具。`begin/prepare → plan → reserve → native spawn → complete → verify`。
  `reserve` 先消耗原父任务总预算；服务不执行原生 spawn，也无法独立订阅 native Worker 生命周期。
  完成前仅有保留记录时，状态明确为 `dispatch_unconfirmed`，不能据此宣称模型已运行。
- 回传：官方 UI `ui/message` 只有 active/new 目标，内容角色为 user；它不提供插件后台所需的
  原聊天持久绑定、忙碌时安全排队与幂等确认。当前聊天能看到的跨线程工具由模型调用，不能
  作为 MCP 后台持久投递接口，本轮也未使用。
- 本机官方 CLI 生成的 schema 包含实验性 `thread/queue/*`，但接口名存在不能证明插件有
  连接原聊天所有者的受信通道。未尝试底层队列、turn/start、UI 发消息或调度模型来模拟唤醒。

依据：[官方 app-server 协议](https://learn.chatgpt.com/docs/app-server)、
[官方 MCP UI message 扩展](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md#uimessage-extensions)。
本机 schema 摘录为 `official-host-schema-excerpts.json`；生成过程不执行模型。
实现前的设计与红灯证据见 `DESIGN.md`、`repro-planner.log`、`repro-worker.log`。

## 本轮实现

1. 新增 `completion_mode`，缺省 `return`。`wake_on_completion` 只保存请求偏好，当前返回
   `effective_mode=return, wake_supported=false, delivery_state=capability_unavailable`。
   原生设置、共享 Web 面板、Swift 面板和 skill 都明确提示宿主暂不支持自动唤醒。
   保存设置不启动模型，也不修改用户原有模型偏好。
2. 新工具 `codex_duo_completion` 接收明确 project_root、kind、原任务 task_id；不传 mode 时
   只读，传 mode 时只修改原任务通知偏好。它直接使用同一派发账本，不创建第二个任务或预算。
   事件 ID 由项目、任务和派发身份稳定生成，重连读取同一终态。没有伪造已发送、已唤醒或验收通过。
3. Planner 修复同线程不同 turn 的消息污染。item 事件必须同时匹配 threadId/turnId；
   终态里的工具执行记录也被拒绝。停止请求等待真实 interrupted 终态；停止确认先于或晚于
   完成事件都能处理。单纯 interrupt ACK、连接丢失、超时、过期 owner 仍保留不确定状态与额度。
   不重启丢失的 ephemeral 会话、不重发 turn。完成记录始终要求主控审阅，计划不授权执行。
4. Worker 修复重复完成回执报错：相同 receipt/outcome/evidence 幂等；冲突、修改后的证据拒绝。
   已验证子任务的证据在重复提交时仍重校验。新增明确 cancelled 终态，失败/取消仍消耗原预算。
5. 现有 begin/prepare、项目覆盖、模型/强度、原生容量与共享总轮数约束保持。
   旧序列化缺少新字段时只在读取视图补默认值，不改不可变快照哈希。

`completion.events` 是原持久账本的确定性视图，不是已投递队列。
重启能恢复终态记录，不能恢复已经丢失的 ephemeral host session。
尚无 Worker 独立后台监听器，也没有原聊天自动验收通道；这两点仍是能力缺口。

## 标识、迁移及安装

活动身份继续统一为品牌 Codex Duo、插件 `codex-duo@codex-duo-local`、MCP `codex-duo`、
工具 `codex_duo_*`、角色 `codex_duo_planner` / `codex_duo_worker`。本轮版本为 **0.9.0**。
旧 Fusion 名仅保留在只读迁移识别、防止旧目录重建的 tombstone、不可变旧契约校验和历史证据。
没有恢复旧插件或旧全局 MCP 注册。详见 `runtime-identity.json`。

通过官方 `codex plugin add codex-duo@codex-duo-local --json` 更新，安装路径：
`/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.9.0`。
38 个受维护包文件逐文件 SHA-256 与源码匹配，详见 `cache-verification.json`。
Python 运行生成的字节码不计入包源码匹配，另行记录于 `runtime-bytecode-inventory.json`。
未直接编辑安装缓存；官方插件目录确认 installed/enabled。

项目、全局 selection.json 原字节哈希不变（`preferences-before.json` / `preferences-after.json`）：
项目仍是 Worker Sol/high、总次数10、并行1、Planner disabled；全局 Astra/xhigh/1 未改。
官方更新前后全局 config.toml 字节与语义哈希一致，见 `config-*-install.json`。
原迁移账本的两份 Planner 记录通过校验，仍各一条 completed 派发；没有退款、清空或重试。
证据：`legacy-ledger-validation.json`、`existing-ledger-hashes-after.json`。
原有未提交工作已保存在内部 `before/` 与 `baseline-git.patch`；本轮差异为 `task-change.patch`。

## 检查结果

| 检查 | 结果 | 证据 |
|---|---|---|
| Python 全量 | 192 项通过 | python-tests.log |
| 新完成模式与事件顺序 | 11 项离线回归通过，包含在全量内 | completion-tests.log |
| Planner 关联/权限/未知状态 | 14 项离线回归通过，包含在全量内 | planner-final-tests.log |
| 首次 plan_only 空组合逐字段保存 | 全量内通过，保存不派发 | tests/test_planner_settings.py |
| 迁移重复、冲突、中断与旧快照 | 全量内通过 | tests/test_migration.py |
| Swift | 19 项通过 | swift-tests.log |
| 静态结构 | 36 项通过 | static-tests.log |
| 共享面板构建、行为 | 通过 | panel-build.log、panel-tests.log |
| MCP SDK/实际启动器离线协议 | 通过 | mcp-sdk-tests.log、package-tests.log |
| macOS release 构建与 ad-hoc 签名 | 通过 | macos-build.log、signature-verification.log |
| 实际 UI | 未完成，停止重试 | ui-check.txt |

初轮失败保留作证据：HTTP 回环监听受沙箱限制、工具数量/设置字段断言需要随新增接口更新；
一个测试过宽拦截所有 subprocess，误拦截只读 Git 基线检查，已改为拦截模型派发入口。
最终全量使用项目要求的 unittest 命令与 Python 3.11；未安装额外依赖。
离线协议和签名检查均不证明真实模型、普通聊天加载或 UI 外观。

## 用户看到的授权弹窗

Computer Use 打开本机构建应用时触发独立的应用控制许可并超时。用户询问为何反复请求后，
已解释并停止全部 UI 重试；没有换 AppleScript、shell UI 或其他技术绕过限制，也未扩大持久权限。
终端隔离放行只用于已授权的回环 HTTP 测试、Swift 缓存写入及官方插件缓存更新；最后相关操作已合并。
这些都不是新的模型调用授权。本轮没有请求或执行真实 Planner、Worker、验收模型调用。

## 当前实际加载与真实运行证据

- 当前是 delegated Local 执行环境，其实际工具目录中未发现 `mcp__codex_duo__` 或 Fusion 工具。
  可见通用 collaboration 原生工具，以及宿主跨线程消息/等待工具；均未用于新增模型或进度发送。
  该结论不能外推到用户普通聊天。详见 `chat-tool-inventory.json`。
- 0.9.0 包声明 **21 个工具，16 个 model-visible**，比 0.8.0 多 `codex_duo_completion`。
  全清单及可见性见 `package-tool-inventory.json`；这是包声明，不是本聊天实测加载清单。
- 用户提供的普通新聊天 0.8.0 收据：15 个 `mcp__codex_duo__` 工具、两个新角色、无 Fusion；
  Planner Sol/high session `01a129b7-583f-7b30-89f7-058ba5065801`，
  turn `01a129b7-5953-7cc1-81a5-dc25f3061221`，completed / awaiting_user_review。
  这是用户提供的先前证据，本轮未独立读取原聊天或再次执行，不能作为 0.9.0 Worker/唤醒验证。
- **本轮真实新增调用：Planner 0、Worker 0、验收模型 0。** 没有新 session/turn/计划输出。
  普通聊天加载、原生 Worker 执行与自动唤醒均未在本轮验收。

## 最小下一步与阻塞

1. 在已有普通项目聊天重新加载插件，通过正常工具入口只读确认 0.9.0 的 completion 工具与能力提示。
   该检查不需要启动独立 Planner/Worker，也不能用底层握手替代。
2. 自动唤醒需要宿主提供可验证的原聊天持久绑定、忙碌安全投递和幂等确认接口。
   仅增加模型授权、打开另一个聊天或拥有 UI 发消息接口不能补齐该能力。
3. 若之后需要真实 Worker 验证，应另行取得授权：目的为原生 dispatch→receipt→complete→verify
   的完整链路；模型使用用户届时确认的保存配置（当前项目 Sol/high），最多 1 次，失败不重试；
   风险为模型计费及明确隔离测试文件范围内的写入。该提案没有执行，也不消耗旧 Planner 额度。
   在可靠后台投递接口存在前，不建议为“自动唤醒验收”另花一次模型额度。
