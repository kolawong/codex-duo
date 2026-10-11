# 官方独立只读 Planner 会话验收

日期 2026-10-11，项目 /Users/kola/codex-duo，HEAD main / 78f38bef638a7643c5dcfe46d8e19fe6694c469d。
用户明确批准将 plan_only 从必须选择原生自定义角色，调整为官方 app-server 独立 Local 会话。
原 Worker 链保持不变，当前聊天模型不切换，旧设置保持默认关闭，保存不启动模型。
真实验收仅获批准 gpt-6.1-sol / high 最多一次，读取 README.md、planner-host.md 与原生角色配置，
只生成接入验收计划，禁止写代码、测试/构建、外部工具或 Worker。此前额度尚未消耗。

## 实现

新 fusion_planner_session.py 通过官方 app-server 的 initialize/config/read/thread/start/turn/start
建立独立 ephemeral Planner，会话实际 readOnly、networkAccess=false、approvalPolicy=never，模型/强度精确匹配。
派发前禁用所有实际配置插件/MCP、apps/hooks/递归代理、远程插件、工具建议及记忆，禁 shell tool/login shell。
不修改全局配置/凭据，不开启 daemon 或重启 Codex/ChatGPT。实际配置/会话响应不匹配时模型前阻断。

planner_begin 可使用明确的本任务模型选择而不改保存设置；新 planner_run、planner_status、planner_stop
供当前聊天使用。父层自动准备契约，用户说「只规划：目标」即可，无需手工 JSON。
面板、原生窗口和技能说明均已更新；收费入口明确，设置保存不收费。

尝试 ID、预算、会话/turn 回执、有效权限和 turn 不可逆意图均落盘；共享预算由原状态机管理。
相同 attempt_id 重复/重启只查旧状态，唯一 owner claim 防止重复请求；turn 意图先于发送持久化。
超时、失联、停止后未确认终止等保持 reserved/uncertain，禁止自动重发或返还额度。
预检失败也保守占用尝试预算，turn_committed 可区分潜在计费请求。模型后失败仍占唯一额度。
独立结果 schema 严格校验身份/代码基线、摘要/步骤/风险/问题，建议测试只能 not_run。
没有批准、diff 或执行结果字段，不转换成 Worker。父层保存结果，模型不写状态文件。

旧 planner_reserve/complete 原生路径仍兼容，但不能伪造回执覆盖 managed session。
原 fusion_planner 模板保留；独立会话不再把它作为前置条件。

## 离线和本机验证

- Python unittest 163 项全部通过（python-unittest.log），包括 13 项新会话协议回归；fixture 零模型调用。
- Swift 18 项通过（swift-test.log）。release 构建和严格签名成功（macos-build.log）。
- 共用面板重建、HTTP/MCP controller、官方 SDK fixture 通过（web-build.log、web-controller.log、mcp-sdk.log）。
- 静态结构 36 项通过（static.log）；默认提示文案控制为 128 字符以内，不再被宿主忽略。
- 新适配器在实际官方 0.162.0-alpha.17.2 宿主预检成功（preflight.json），未发模型 turn。
- 官方 plugin add fusion-minimal@fusion-local --json 成功；36 个包文件与缓存一致，应用包含新模块（package-check.json）。
- 实际原生 fusion-settings-window 显示当前项目、Worker Sol/high、Planner 关闭、新正常使用/收费/停止说明。
  仅正常退出旧 Duo 并打开新构建应用，未保存设置、未操作禁止的 Codex 主界面。
- 先前 JSDOM 依赖下载连接被拒绝的环境边界仍存在；本次未重试网络安装，不能算 JSDOM 通过。

## 真实验收证据与保护

真实验收通过已安装 MCP 的 tools/call planner_begin/run/status，唯一 attempt_id=initial；
不是额外主控模型触发子代理。实际权限和模型回执由子适配器写入原 Planner 状态机。
本报告在代码基线冻结前写入，验收后不修改它，以免将协调者报告更新算作代码变化。
**真实调用最终结果以 acceptance.json、result.json、status.json 和 acceptance.log 为准。**
这些生成工件被 Git 忽略，不影响代码基线。完整 frozen worktree 哈希在 pre-model-files.json，
本轮开始时既有用户修改和保护配置基线在 baseline.json。源码修复仅本地未提交，禁止 commit/push。
全局安全配置、项目/global selection 的保护哈希应保持一致；零 Worker、无真实模型修改源码的核对
保存在 acceptance.json。成功必须为 awaiting_user_review、baseline_current=true，且有实际 session/turn
回执与 schema 校验结果；失败或不确定只报告实际状态，禁止再次调用模型。

官方协议依据：https://learn.chatgpt.com/docs/app-server 。
