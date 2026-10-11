# Return 流程清理交付

日期：2026-10-11。项目：`/Users/kola/codex-duo`，继续现有本地 `main` 工作树。

本轮按明确授权定向移除手动验收及无效唤醒流程，没有回滚到旧版本。已通过官方本地入口更新插件 **0.9.6**，构建并签名 App **0.9.6 / build 15**。主聊天按技能指引等待原生 Worker、记录真实回执、检查证据及独立验收，再向用户报告。独立 Planner 仍只读，计划回主聊天确认，不自动执行。

本轮真实 Worker、Planner、验收模型及额外模型调用 **0**。未使用 UI/CUA/浏览器操作，未打开或重启应用，未建立监听服务或 daemon，未改安全权限/凭据/本地记忆，未创建聊天、分支、commit/push/reset/pull。没有修改真实 failed run 或消费其剩余预算。

## 移除与保留

移除 `codex_duo_completion`、`codex_duo_review_prompt`、`codex_duo_review_record` 的工具定义和路由；移除对应 service 方法、CLI 专用命令、HTTP `/api/review-prompt`、Web transport 和 Swift bridge/client 的复制接口。当前 MCP 工具数为 **20**，旧入口明确不可用。

删除 `codex_duo_review.py` 的提示/结论/历史报告解析流程，删除 Swift `ReviewInboxView.swift` 和 `tests/test_manual_review.py`。Web/Swift 均不再提供完成模式选择、完成列表、复制提示或系统剪贴板操作。设置 schema/values 不再提供 completion_mode。删除不再适用的手动/唤醒文档和测试；历史证据与报告文件保留。

保留独立 Planner、原生 Worker、codex-duo 名称、共享总轮数与并发、prepare 旧入口说明与 begin 正确入口、任务范围和项目关联、取消确认及终态顺序、未知状态和幂等回执、父子证据验收、规范 diff 快照/生成/预检，以及先前界面头部修复。`codex_duo_completion.py` 仅保留通用账本事件和未确认状态投影，被 Worker/Planner 状态响应使用；已无模式选择、唤醒能力或手动分支。

旧配置的最小兼容方式：读原始配置和 immutable handoff 时允许识别两个旧值，但 `saved_workflow` 的有效值固定 return，不写回历史。旧 handoff 校验使用原始序列化，身份/hash 不变。新设置不能重新保存旧值；新账本不再写入专用完成模式字段。显式配置迁移仅面向 selection.json，带 revision 校验和原字节备份，不作用于任务或报告。

## 授权配置迁移

当前项目与全局原值均为 `manual_review`，已迁移为 **return**。`configuration-after.json` 对比起点文档，确认只有 `workflow.completion_mode` 改变，selection、Planner、轮数、并发、激活、项目覆盖、saved_at、catalog fingerprint 等其他字段逐项相同。

| 配置 | 原 revision | 新 revision |
| --- | --- | --- |
| 当前项目 `.codex-duo/selection.json` | `6226ef62e312ee777215528da1e015b381a9ddb259228f23dc7b48f741c5d84e` | `fdff92fa638e5494046b4adab310441dd665b7aa04caba229cefab2589897cf7` |
| 全局 `~/.codex/codex-duo/selection.json` | `60433cd6accc04925d1a3ec01a6eab75e460e6d5c4a50e13addacb325e2a785c` | `1900c32e3405535a2acc6cb11f88ac548cf57e70ab15c33e8bccf77f7a715a7c` |

原配置备份位于各自 `history/completion-return-<原revision>.json`，备份 hash 与原字节 hash 一致。迁移入口实际执行 `codex_duo_workflow.py migrate_completion --project-root /Users/kola/codex-duo --scope project|global --expected-revision <起点hash>`；两次 exit 0，回执分别见 `project-migration.json`、`global-migration.json`。

项目保留 Worker `gpt-6.1-sol/high`、当前聊天协调、10 总轮/1 并行、Planner disabled。全局保留 Astra/xhigh 的只读 Planner plan_only，以及保存的 Astra 协调偏好和 Sol/high Worker、原预算。没有启动这些模型或主动切换当前聊天模型。

## 离线回归

| 命令/检查 | 结果 |
| --- | --- |
| `PATH=/opt/homebrew/opt/python@3.14/libexec/bin:$PATH python3 -B -m unittest discover -s tests -v` | **224/224 通过**，`python-tests.log` |
| 新 `test_return_flow.py` 专项 | **7/7 通过**，`return-tests.log`；亦含于全量 |
| 保留的 `test_completion.py` 终态/协议专项 | **11/11 通过**，`completion-tests.log`；亦含于全量 |
| `swift test --package-path macos --cache-path macos/.build/cache --manifest-cache local`，使用项目内两项 ModuleCache 环境变量 | **24/24 通过**，`swift-tests.log` |
| `node native-build/test-panel.mjs` | MCP/HTTP 面板控制器全部通过，含旧值读取、保存不带模式、删除入口断言，`panel-tests.log` |
| `node native-build/test-client.mjs` | 官方 MCP SDK 离线 stdio/工具/schema/设置/项目隔离/派发账本/证据验收回归通过，`client-tests.log`，model_calls=0 |
| `node native-build/build.mjs` | exit 0，`web-build.log`；重建自包含面板 |
| 同样 ModuleCache 设置的 `bash macos/build.sh` | exit 0，`macos-build.log` |
| `codesign --verify --deep --strict --verbose=2` | exit 0，ad hoc 签名有效，`codesign.log` |
| `audit.py` 中结构检查 | **36 项通过**，`static-validation.json`、`audit.log` |
| Python AST 源码解析、`GIT_OPTIONAL_LOCKS=0 git diff --check` | 通过 |

新增与保留覆盖：旧 manual/wake 配置有效 return 且读取不写盘；项目/全局迁移仅改变模式并可重复执行；stale revision、坏配置、symlink 拒绝；旧值无法重新启用；专用工具、HTTP 路由和设置不可用；旧 handoff/hash 和旧 ledger 原样读取；return 派发、重复 complete、父任务 verify 保持单次预算；Planner 只读/官方协议/独立会话模拟、取消确认顺序、丢失/未知状态；完整 diff 格式和 byte fixture 回归。Swift 同样确认旧字段被忽略且不会编码回保存请求，保留四项界面头部 offscreen 回归。

首次 Python 全量发现三处旧工具数量断言仍为 23，已改为实际 20。面板回归发现移除复制代码时同一行的加载状态赋值被误删，已恢复并重新通过控制器测试。初次 compileall 尝试被系统外部缓存写权限拒绝，改用无缓存写入的 AST 解析；最终完整测试、构建均通过。没有把中间失败计为通过。

## 安装与历史保护

官方更新命令 `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex plugin add codex-duo@codex-duo-local --json` exit 0；`plugin-update.json` 确认 **0.9.6** 缓存路径 `/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.9.6`。没有手动覆盖缓存或清除旧版本/用户证据。

源码与缓存 **38 个文件逐个 hash 相同**；App 内 **10 个共享服务脚本**和 bridge 与源码匹配，已无 review 模块。App binary SHA-256：`c8a09fe0028997b6dbe0e4e2b80d7f16dca2b141ca94c86d3a720ecf770eef07`。详见 `package-hashes.json`。

保护起点共 1562 个文件，除 Git index 细节外 **1561 个逐字节 hash 不变**，包含既有 `.codex-duo` 历史任务/账本/预算、全部既有证据和报告、AGENTS、全局和项目 config.toml、marketplace、Git HEAD。两份获准迁移的 selection 单独对比，不列入不变文件。`protected-after.json` 列出完整 hash。

Git index 的 byte hash 在只读 Git 检查期间从 `a66c962c2a135c6342bdbc132d805f3bf1b5bb7ebdde25270b805939da631170` 变成 `1dd677df2e60efdca6347f6e87001f079d4bb340544a2508755eac08462840c2`；起点状态无暂存项，最终 cached diff 亦为空、HEAD hash 不变。没有执行 git add、提交、还原 index 或历史操作；未将此文件算作字节不变，也未为恢复 hash 而覆盖它。

安装模块的进程内只读核验禁止 save/migrate/begin/prepare/plan/reserve/complete 和会话启动。原 handoff `72f92a80e6c7b4155fcd4b45` 仍可按原字节校验，其运行时返回流程为 return；实际原 ledger 仍 **failed**、dispatch_count=1、remaining_worker_turns=9。原无前缀 diff 仍被拒绝。三个历史 Planner 记录只读保持 stale、各剩余 0，没有重开、清预算或写状态。详见 `installed-read-only.json`。

本轮源代码范围为修改 35 个、删除 3 个、新增 `tests/test_return_flow.py` 1 个；详细清单见 `changed-files.json`，本轮增量见 `increment.diff`，起点源文件归档见 `source-before.tar.gz`。它们按本轮起点比较，避免把既有大范围脏修改当成新改动。没有删除任何用户证据目录或旧报告。

## 使用和剩余边界

用户无需再选择完成模式或复制提示。使用已保存的项目设置提出开发任务，由主对话等待 Worker 回执并继续验收；“只规划”仍使用原独立 Planner 入口。已运行的旧 App/已加载旧工具需用户自行重开或重新加载；本轮未操作实际应用，不能证明旧运行进程已加载 0.9.6。

没有真实 Worker/Planner 或验收模型试跑，没有实际菜单点击或宿主 UI 验收；离线 DOM/Swift offscreen 和安装 hash 不代表真实模型链已测。此前 0.9.5 的真实 manual 成功链没有验证过，本报告没有将其标为成功。当前无代码、安装或权限阻塞。
