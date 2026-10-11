# 0.9.2 手动继续验收接口验证

日期：2026-10-11。当前项目：`/Users/kola/codex-duo`。本轮是已批准的只读验证，不是实现任务。没有修改源码、用户新偏好或真实历史任务。

## 实际配置结论

用户的全局切换已保存：`completion_mode=manual_review`。本项目有旧项目覆盖，项目 workflow 未显式保存 completion_mode；已安装读取器按旧字段默认解析为 return。整体项目覆盖优先，因此本项目**实际有效模式仍为 return**，source=project。没有恢复上一轮快照、自动调整设置或清除覆盖。

| 范围 | 完成模式 | Planner | Worker | 来源/说明 |
|---|---|---|---|---|
| 最新全局已保存 | manual_review | plan_only / gpt-6-astra / xhigh / 1 turn | gpt-6.1-sol / high | 全局设置接口与面板 global state 均确认 |
| 当前项目解析后 | return | disabled | gpt-6.1-sol / high | 旧项目 selection.json 覆盖全局，缺失字段按默认解析 |
| 当前项目 effective/defaults | return | disabled | gpt-6.1-sol / high | source=project；10 总轮数、并行 1 |

全局 revision：`5b9cb831c9629df3c8f18fbc9ed48ecfe377f838398d3c6b8f0afed397ab4175`。项目 revision：`4ff4fef07b8fff93eb0a532f1a8b82401601a000405d99ccfddfe9d082909980`。完整最新配置与只读响应保存在 `real-summary.json`、`real-interface-receipts.json` 和 `native-packaged-bridge.json`。

## 已安装接口实测

- 安装缓存版本与运行时 server.VERSION：**0.9.2**，路径 `/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.9.2`。
- 实际从安装缓存加载 `MCPServer.dispatch`，通过真实 schema/dispatcher 调用 `codex_duo_state`（global/project）、`codex_duo_settings_read`、`codex_duo_defaults`、`codex_duo_completion`、`codex_duo_review_prompt`。未从源码 checkout 或假服务替代这些读路径。
- 另实际执行已安装 `codex_duo_workflow.py defaults/review_inbox --project-root /Users/kola/codex-duo`，结果一致。
- 实际执行已打包 `macos/dist/Codex Duo.app/Contents/Resources/bridge.py` 的一次性 JSON 进程，读取 global/project state 和真实记录的 review_prompt：版本 0.9.2，global manual_review / project return，复制拒绝 review_changed，结果一致。应用资源中的 11 个 service 脚本哈希与安装缓存相同。
- 采用进程内 MCP dispatcher 和一次性 bridge/helper；没有启动 daemon、监听服务器、app-server、Planner、Worker、额外验收模型或应用 UI。真实项目检查对所有 mutation/launch 方法设置了失败护栏；读路径仍为安装包的实际代码。读取前检查确认 migration guard 只校验、不自动迁移，真实项目 lock 已存在、获取锁不写账本。没有调用带 mode 参数的真实 completion，也没有真实 review_record。
- 当前聊天并未出现 codex_duo 工具目录；本报告证明本机安装接口与原生打包桥接，不宣称普通聊天工具重新加载或真实 UI 验收。本轮没有调查宿主连接。

## 使用的真实记录

Worker handoff ID：`65821f50c5f63f912d8574c7`。

- 原账本 mode=return、`dispatch-001` status=verified，完成接口映射 outcome=completed，无 pending dispatch。
- 原 `acceptance-report.json` 为 status=accepted、coordinator_review=completed，历史已有一次真实 Worker 及独立验收。**本轮没有把它当作新的待验收结果。**
- 派发数始终 **1**，账本上限 10，剩余总轮数计算始终 **9**。历史这次测试的用户授权最多一次已使用完；账本余量不是本轮重派授权。
- 当前完成列表 `items=[] / unavailable=0`。因为真实 Worker 与 3 条 Planner 原任务都保留 return，设置切换不会追溯修改这些任务模式。3 条 Planner 的 completion 只读返回 completed/return，也未列入手动列表。
- 多次读状态/完成、3 次尝试真实 Worker 提示生成：均拒绝 `review_changed`。原因是该原任务没有 manual_review token；没有人为改模式、绑定或写结论来让真实结果变成可复制。
- 不存在任务 ID 的 completion/prompt 重复请求拒绝 invalid_handoff；错误项目路径拒绝 project_mismatch（定根服务）或 invalid_handoff（无原任务的另一项目）。初次测试使用 /tmp 时因 macOS 符号链接而返回 invalid_project，改用规范目录 /private/tmp 后验证正确拒绝，属于测试参数修正，不是产品 bug。

真实提示**没有成功生成**。不能提供冒充真实结果的复制文本。

## 隔离 fixture 的已安装成功路径

真实记录不适合生成新验收提示，所以另在 `fixture-project` / `fixture-codex-home` 运行离线数据 fixture。使用相同已安装接口和真实本机模型目录，仅创建隔离的任务、预算/结果文件；没有原生模型派发。账本的 native_receipt 明确为 OFFLINE_FIXTURE_NO_NATIVE_WORKER。fixture 文件断言通过本地 Python 执行，结果不是模型输出。

- 安装接口显示 ready、待验收、can_copy=true，并在隔离项目完成列表中返回正确项。
- 3 次提示生成 + 重建服务对象后的第 4 次生成返回相同 payload。
- 复制前后 fixture 账本和结果文件哈希完全相同；派发数 1、余量 1 不变；review_state 未因复制改变。payload 均 model_calls=0、message_sent=false、review_started=false。
- 单独为 fixture 写入明确的离线 passed 结论后，安装接口显示 passed/can_copy=false，再生成提示拒绝 review_not_ready。只有隔离 fixture 写了模拟验收记录，真实记录没有任何变化。

下面是**实际从安装接口生成的隔离 fixture 提示摘录**，不是上述真实 Worker 的提示，也没有发送到聊天或系统剪贴板：

> 请仅验收 Codex Duo 的已有结果，不重新派发 Worker/Planner，不重置预算，不执行修改。
> 此请求应提交到发起任务的原 Codex 项目聊天。请先核对本聊天的项目和原任务记录；若无法确认原任务归属，停止，不创建新聊天或恢复其他会话。

完整 fixture payload 与身份/路径/哈希保存在 `fixture-summary.json`；隔离任务已标记 passed，不能伪装成真实结果待验收。

## 发现的旧验收兼容性缺陷（本轮不修复）

已安装通用完成事件为旧 Worker 返回 `review_state=pending`，但独立历史验收报告是 accepted/completed。当前真实 mode=return，所以它没有在手动列表伪装成待验收，也没有成功生成提示。

在 `legacy-copy-project` 中复制该旧 handoff/run 的证据作诊断，只有隔离副本显式选择 manual_review。安装接口随后显示 **ready / 结果就绪 · 待验收 / review_outcome=pending / can_copy=true** 并允许生成提示，虽然副本的旧验收报告仍为 accepted/completed。这确认 0.9.2 没有把旧独立验收结论接入新 manual_review 状态投影。隔离副本是复制的诊断资料，绝不是新真实任务或验收；原账本仍 return，所有原 run 文件哈希不变。

原因：`codex_duo_review.projection` 只消费账本 value.manual_review（result_token/outcome）；没有检查原 acceptance-report/coordinator-review。`codex_duo_completion.completion_view` 则统一写 review_state=pending。

最小修复建议：对旧结论先核验 task/result 身份及证据关联后映射，或将存在历史验收证据但缺新结论的旧任务显示为「历史验收状态待确认」并禁用复制，直到明确完成兼容确认。不要仅凭模型输出/报告文字直接批准或默默改写历史。**本轮未获源码修改授权，未修复、未更新版本。** 复现和源码位置见 `legacy-compatibility.json`、`legacy-check.log`。

## 不变证据及通过/失败/未测

共 **536 个**真实受保护文件前后 SHA-256 一致：项目历史任务/结果/预算账本、项目与全局配置和偏好、插件源码/安装缓存、Web/Swift 源码及现有测试。清单见 `protected-before.json` / `protected-after.json`；`unchanged-check.json` changes={}。真实派发账本 SHA-256 前后均为：

`938df22401f0e3beb594c7a32fb42ed2b84fbc06992078511b25ada577b0cc96`

通过：最新全局保存读取、项目覆盖优先、实际安装包/原生打包桥接读接口、真实完成/已有验收证据读取、旧 return 不被自动更改、不存在/跨项目错误拒绝、重复操作预算/状态/源码/新偏好不变、安装接口隔离成功复制、已记录 passed 的 fixture 禁止复制。

失败：旧独立验收报告与新手动列表的结论兼容，已在隔离副本复现。真实记录仍安全保留 return，不建议拿该历史已验收 Worker 改模式后重验。

未测：真实宿主按钮点击、系统剪贴板写入、原聊天粘贴发送、真实手动验收模型调用。这些按任务限制未执行。没有 ComputerUse/浏览器 UI、权限弹窗、聊天发送、daemon/server、安全设置变更、新凭据、额外模型/子任务、commit/push。

## 用户最后一步

若想让本项目以新模式工作，在设置的「当前项目」范围单独选择「结果就绪后，手动继续验收」并保存；本轮没有替用户修改。仅改全局默认不会覆盖现有项目选择。保存后模式适用于后续新任务，旧任务不会自动切换。

对之后经正常授权并在 manual_review 模式完成的任务，在「当前项目 → 完成列表 · 手动验收」实际点击「复制验收提示」，确认提示仍写明尚未开始验收，然后自己回原任务聊天粘贴。**提交会产生验收模型用量**；本轮没有提交。不要用本报告中的隔离 fixture/旧已验收任务来触发真实验收。

验证入口脚本 `check_installed.py`、`check_legacy_copy.py` 仅存于独立 evidence 目录；fixture 目录保留便于检查，不是用户项目任务。脚本会写隔离数据，不应不加区分重复运行；现有报告和原记录无需再写入。
