# coordinator_required 排查与修复

本轮修复已完成并通过官方插件命令更新到 **Codex Duo 0.9.1**。真实 Worker、Planner 和其他模型调用均为 **0**；未进行 UI 操作，未验证普通聊天的真实 Worker 执行。未 commit、push、pull、reset 或新建分支。

## 根因与实际配置

实际旧交接为 `adc353d146c57d7d82382a14`，任务为 `worker-acceptance-0692d4d119e248a193ef05825db2470d`。安装版 0.9.0 的只读状态检查返回 `approval_required`；其 `codex_duo_plan` 返回 `coordinator_required`，没有建立派发账本。[复现](reproduction-before.json)

项目有效设置为 `automatic_project / current_thread`、Worker `gpt-6.1-sol / high`、总轮数 10、并行数 1、Planner disabled。项目旧配置省略的可选字段按默认值补齐。全局主控方式也为 `current_thread`；全局 Planner 为 Astra/xhigh/1，但项目覆盖优先。项目保存的 Astra/xhigh 主控模型在 current_thread 模式不生效。故本次错误不是 Astra 与 Sol 不匹配。[有效设置](defaults-before.json)

代码路径如下：

- [service.prepare](../../plugins/codex-duo/skills/workflow/scripts/codex_duo_service.py:128) 调用 `prepare_handoff` 时不传 workflow；这是保留旧式声明交接的兼容接口。实际旧交接确实没有 workflow。
- [service.begin](../../plugins/codex-duo/skills/workflow/scripts/codex_duo_service.py:107) 解析项目覆盖/全局默认并把 workflow 写入新快照。
- [execution_plan](../../plugins/codex-duo/skills/workflow/scripts/codex_duo_service.py:271) 对 current_thread 快照返回 `ready_for_native_worker`，对 selected_model 返回 `new_coordinator_required`；无 workflow 的旧交接返回 `approval_required`。
- [parallel 的检查](../../plugins/codex-duo/skills/workflow/scripts/codex_duo_service.py:302) 只接受 `ready_for_native_worker`。旧 prepare → plan 因此应当被拒绝。

缺陷是旧入口说明和通用错误信息不足以指导聊天选对路线；此外 selected_model 状态仍提示 next_tool=plan，会误导继续调用必然失败的入口。`execution_plan` 是只读资格检查；`plan` 是建立持久工作流与容量计划；两者均不是 Planner 模型推理。

## 修复范围与兼容性

保留原有校验与错误码，不自动修改快照、偏好或预算。prepare 响应现在明确标记 `legacy_declarative`，指出当前聊天应使用 begin。execution_plan 区分交接种类，selected_model 不再返回 plan 作为下一工具。plan 拒绝时分别解释旧交接缺 workflow 与 selected_model 两种原因。同步更新 MCP 描述、Skill、README、安装说明和版本。[本轮补丁](task-change.patch)；[修改清单](changed-files.json)

begin 请求仍不接受 `coordinator_mode`、主控模型或 thread_id 覆盖。selected_model 仍不可由当前线程适配器直接派发；另开聊天本身不会改变旧快照的资格。MCP 没有可信宿主线程身份绑定，所以 current_thread 表达保存的策略，不证明聊天实际使用的模型。跨项目隔离和账本限制由离线测试覆盖，不将其表述为真实跨线程执行验证。

旧交接文件继续完整保留，可读、可审计，但不能直接用于 plan/reserve。同一 task_id 只找到该旧交接，保留/派发数为 0。[账本检查](matching-task-ledgers.json)

因此原普通对话可在再次确认零派发后，原样复用旧 `task.json` 的 task 与 task_id，经 begin 建立含 workflow 的合法快照。workflow 参与内容哈希，新 handoff_id 合理且预期；不可编辑旧哈希、改 task_id、清空账本或据此重试已消耗调用。该恢复仅适用于当前已证实零派发的任务。

## 验证与安装

| 检查 | 结果 | 证据 |
|---|---|---|
| Python 全量 | 200 通过，56.993 秒 | [日志](python-tests.log) |
| 新增路由回归 | 8 通过 | [日志](routing-tests.log)、[测试](../../tests/test_coordinator_routing.py) |
| MCP SDK | 协议与离线流程通过，模型调用 0 | [日志](sdk-tests.log) |
| 静态检查 | 36 通过 | [日志](static-tests.log) |
| macOS release 构建 | 通过 | [日志](macos-build.log) |
| 严格签名验证 | 通过 | [日志](signature.log) |
| 官方插件更新 | codex-duo@codex-duo-local，0.9.1 | [回执](plugin-update.json) |
| 安装缓存 | 38 个维护文件 SHA-256 与源码一致，仅排除生成的 __pycache__ | [哈希](cache-verification.json) |
| 保护基线 | 325 个文件内容完全相同 | [结果](protected-after.json) |

Python 使用 `/opt/homebrew/bin/python3.11 -B -m unittest discover -s tests -v`（项目要求的命令，以 Python 3.11 执行）。新增回归覆盖旧入口→begin、缺省字段、selected_model、禁止请求参数覆盖、全局/项目优先级、不可变旧快照、重复 begin/独立客户端共享预算，以及跨项目拒绝。所有模型行为均为离线夹具；没有真实模型派发。

安装目录：`/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.9.1`。本轮没有修改共享面板源码；未重新进行 UI 访问或界面验收。安装后对旧交接的只读/拒绝路径再次检查，错误信息已更新，旧交接内容和零派发状态不变。[安装版结果](reproduction-after.json)

保护范围包括项目与全局偏好、全局 config.toml、旧交接、既有预算/派发与规划记录、临时目标文件。临时目标 `value.txt` 仍为精确字节 `before`。原任务断言仅作语法编译检查，未执行。既有用户修改未回退。

## 聊天入口状态与下一步

本 delegated Local 会话实际工具目录中匹配 Codex Duo/Fusion 的工具为 0，原生 spawn schema 也没有 agent_type。此事实只描述本会话，不能推断用户普通会话工具不可见。用户提供的普通会话信息显示支持 `agent_type=codex_duo_worker / model=gpt-6.1-sol / reasoning_effort=high / fork_turns=none`；本轮未独立重跑该入口。

安装版声明 21 个工具，其中 16 个标为 model 可见；[完整工具定义](tools-after.json) 来自本地安装版检查，不等同于普通聊天实际加载清单。MCP dispatcher 和 SDK 测试不能证明聊天入口能运行 Worker。

原普通对话所需的完整最小步骤在 [NEXT-STEP.txt](NEXT-STEP.txt)：读取 defaults 和原 task，确认同 task_id 零保留/派发及目标 before → begin → plan(capacity=1) → reserve 恰好一次 → 原生 codex_duo_worker Sol/high → 独立验收及 complete/verify。即使保存总轮数为 10，此次用户授权仍最多一次，失败或未知结果不得重试。此前单次真实 Worker 授权尚未消耗；本轮按要求没有使用它。

可粘贴回原普通对话：

> 请按 `/Users/kola/codex-duo/evidence/coordinator-required/NEXT-STEP.txt` 继续此前已批准且未消耗的单次原生 Worker 验收。固定项目目录，原样复用旧 task/task_id，确认零派发后用 codex_duo_begin 替代 prepare；只允许 codex_duo_worker / gpt-6.1-sol / high / fork_turns=none 一次，失败不重试，不改偏好，不再请求相同授权。若真实宿主工具不支持则停止并报告。

本轮未验证真实 Worker、普通聊天新工具加载或自动唤醒。Computer Use 授权提示不属于这次路由修复的模型授权；没有再次访问 UI 或要求扩大持久权限。
