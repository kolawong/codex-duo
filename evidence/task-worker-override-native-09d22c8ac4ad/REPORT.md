# 任务级 Worker 覆盖真实验收

日期：2026-10-11（Asia/Taipei）。项目 `/Users/kola/codex-duo`。

任务级覆盖已在 begin/reserve 解析和原生派发参数中生效；完整验收失败。宿主没有返回运行时模型或推理强度，不能据此认证实际运行的是 Luna low。

- 新 schema：begin.worker_override、complete.native_dispatch 均已加载；缓存 server/service/worker/skill/contract 与当前源码 SHA-256 一致。
- 初始项目与全局 Worker 均为 gpt-6.1-sol / high。项目/全局主控保存值均为 gpt-6-astra / xhigh，但 coordinator_mode=current_thread；这些保存值不证明当前聊天模型。项目 Planner disabled；全局 Planner plan_only，gpt-6-astra / xhigh。共同预算 10、并行 1、return。本次未启动 Planner。
- 测试 handoff：5a3846e71fe41b701da52a2b；dispatch-001。begin 显式 worker_override=gpt-6-luna / low，两字段来源 task_override。
- 原生调用：collaboration.spawn_agent，agent_type=codex_duo_worker，model=gpt-6-luna，reasoning_effort=low，fork_turns=none。
- 宿主实际返回：task_name=/root/worker_override_once；只读代理清单返回同一 agent_name，已收到该代理终态结果。宿主没有提供独立 UUID、运行时 model 或 reasoning_effort。回执使用宿主返回的可寻址代理标识，未伪造字段。
- 累计 reserve 1、原生派发 1、疑似派发 0、重试/追加派发 0、Planner 调用 0。MCP 本身不启动模型，其 model_calls=0 不能替代实际原生派发计数。
- Worker 改前快照与规范 diff 成功，唯一任务文件从 before\n 改为 after\n。Worker 测试日志记录 SyntaxError，退出 1；预检拒绝 worker did not complete，退出 1。未改写该失败 result.json/diff/log 或重新生成证据。
- complete：outcome=failed 被接受，dispatch_count=1，剩余保存预算 9；已记录 successful_dispatch 参数，runtime 两字段均 not_provided。
- verify：evidence_rejected / workstream not verified: main。没有伪造 parent completed 结果或修复终态回执。
- 主控独立复验：读取不可变 task.json 的原始 argv，subprocess.run(argv) 执行，退出 0；最终文件十六进制为 61667465720a，即 after 加真实 LF。该独立成功不覆盖 Worker 的失败证据。
- 下一任务仅 begin，无 worker_override：handoff=1ccc58068601d6c77fc73aa9，Worker=gpt-6.1-sol / high，来源 project，execution_started=false。未 plan/reserve/spawn，不用于绕过原任务预算。
- 保存偏好：项目和全局 selection.json、config.toml 的存在状态、大小及 SHA-256 与开始前一致；末次复核仍一致。128 个已跟踪文件与开始前字节哈希一致，未改业务源码。没有提交、推送、创建分支或修改设置。

请求和派发参数有证据；实际宿主运行时模型身份未提供。完整 Worker 快照/diff/断言/预检/complete/verify 成功链未通过，失败后未重试。

证据：baseline.json、native-call.json、workflow-records.json、independent-checks.json、independent-assertion.log。Worker 原证据位于 `.codex-duo/runs/5a3846e71fe41b701da52a2b/workers/main/dispatch-001/`。
