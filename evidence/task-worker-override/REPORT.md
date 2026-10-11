# 轻任务预设与任务级 Worker 覆盖验证记录

日期：2026-10-11（Asia/Taipei）。项目 `/Users/kola/codex-duo`，main，基线/当前 HEAD `cf04199`。

实现和离线检查完成。真实 Worker 验收在当前会话工具加载门禁处停止；没有创建真实验收任务、reserve、启动代理或 Planner。

## 实现

- 保留原有三个预设及默认选择，追加轻任务 `gpt-6-luna / low`。Web 与 SwiftUI 设置界面复用现有表单，预设只填写草稿；轻任务仅修改 Worker，不改变主控、Planner、启用方式或预算，不自动保存。
- 实际 MCP `codex_duo_begin` 新增可选 `worker_override={model?,reasoning_effort?}`。CLI 同步支持 `--worker-model` / `--worker-effort`。字段按本次覆盖、项目配置、全局默认合并，然后校验最终组合；不自动调整模型或强度。被替代的非法 Worker 默认不影响合法覆盖；损坏文件或非法其他设置仍拒绝。
- 不可变 handoff 保存有效组合、显式覆盖和逐字段来源。按同一 task_id 查找并验证历史快照，相同参数复用；冲突拒绝。后来保存偏好、服务重启、重复 begin/plan 均不重建已有任务预算；旧记录不改写。
- plan/reserve 使用固定任务模型，reserve 明确实际角色 `codex_duo_worker`、fresh context、证据命令；保留 return、共享预算、原路径边界及 diff 快照/预检。
- 新增 `worker_summary` / `dispatch_summaries`，区分 requested、successful_dispatch 和 runtime。complete 的可选 native_dispatch 记录实际成功调用参数、工具及代理 ID，runtime 仅可转录宿主实际返回字段。缺失字段为 not_provided；运行时不一致明确标识。MCP 只校验主控转录的一致性，不独立认证宿主身份。
- 技能、交接契约、Worker 指令及 README 更新了实际参数用法；没有增加新控制面板、自动难度判断、模型升降级或 Planner 调用。

## 离线检查

| 检查 | 结果 | 记录 |
| --- | --- | --- |
| 完整 Python unittest | 243 项通过，无跳过 | `python-full.log` |
| 新增任务覆盖回归 | 19 项，包含在完整套件内 | `tests/test_worker_override.py` |
| 完整 Swift 测试 | 25 项通过 | `swift.log` |
| macOS release 构建、资源打包、签名 | 通过，包含新的 codex_duo_worker.py | `macos-build.log` |
| 共享面板构建 | `node native-build/build.mjs` 通过 | 生成 `plugins/codex-duo/ui/model-desk.html` |
| MCP / HTTP 面板行为 | 通过，含预设仅写草稿及摘要不声称运行时身份 | `panel.log` |
| jsdom 面板回归 | 通过 | `panel-dom.log` |
| 官方 MCP SDK stdio 协议 | 通过，含 schema、覆盖、重复/冲突、reserve/complete 回执及下一任务恢复默认 | `mcp-protocol.log` |
| 包/配置静态检查 | 35 项通过 | `static.log` |
| 实际浏览器面板 | 在仅使用临时状态的 MCP 测试宿主中操作并查看布局；选择轻任务后为 Luna low、未保存，保存后显示默认来源；Planner 保持关闭 | 当前聊天 CUA 操作记录 |

覆盖场景：无覆盖、完整和单字段覆盖、最终非法组合派发前拒绝、非法 Worker 默认被合法完整覆盖、下一新任务恢复默认、并发任务隔离、同 ID 并发冲突、独立服务/进程重启快照不变、重复及冲突请求、消耗预算不可重置、项目/全局保存文件逐字节不变、缺少宿主字段时不伪造身份、部分运行时字段和不一致报告、终态回执不可更换、旧快照兼容。

首轮回归有一个旧路由测试把同一 task_id 当作新任务使用；已改为按新任务 ID 验证新配置，另有测试确认旧任务保持原模型与预算，最终完整套件通过。

原锁文件的 rrweb-cssom@0.9.0 tarball 返回 404，完整 npm ci 未成功。运行依赖按原锁文件恢复；DOM 检查在隔离目录安装项目已声明的 jsdom@26.1.0 后通过，未改 package.json / package-lock.json。安装日志见 `npm-ci.log`、`npm-production.log`、`npm-dom.log`。这是测试环境依赖限制，不是 Worker 执行证据。

`git diff --check` 的唯一全局提示是开始前已有的 README 第 3 行 Markdown 双空格换行；未更改该行。排除此文件的改动检查通过，新增 README 段落无尾随空格。

## 真实验收门禁与状态

| 阶段 | 状态 |
| --- | --- |
| 宿主原生 schema | 声明支持 collaboration.spawn_agent、agent_type=codex_duo_worker、gpt-6-luna / low、fork_turns=none；仅为工具定义证据 |
| 当前聊天 MCP schema | **旧接口**：begin 没有 worker_override，complete 没有 native_dispatch |
| 已安装代码 | 0.9.8 缓存的 server/service/skill 与源码 hash 不同，缓存缺少新 worker 模块 |
| 真实 begin / plan / reserve | 未进行 |
| 原生 Worker | 未派发；真实代理标识：无 |
| 临时文件 before → after、Worker 快照/diff/测试/预检 | 未进行真实 Worker 验收 |
| complete / verify / 主控独立真实断言 | 未进行 |
| 下一任务恢复默认 | 已有离线验证；新普通聊天工具入口仍待新会话验收 |

本次请求的真实验收组合：`gpt-6-luna / low`；来源应为 task_override。成功派发参数：无。宿主运行时模型/强度：未提供。累计派发 **0**，疑似派发 **0**，Planner 调用 **0**。未用 task_name 冒充角色，未做额外可用性模型探测，未重试或修补旧失败记录。

门禁记录：`session-gate.json`、`installed-code-comparison.json`。离线 fixture、模型目录、工具 schema、构建和本地面板都不证明真实模型运行成功。

## 配置与本地工作保留

真实项目 `.codex-duo/selection.json`、全局 `~/.codex/codex-duo/selection.json`、项目和全局 config.toml 全部与开始前 SHA-256 一致。当前生效 Worker 仍为项目默认 `gpt-6.1-sol / high`，预算 10，Planner disabled，return。

原 README 本地改写完整保留（去掉本次新增段落后 hash 与开始前相同）；原 `.codex/config.toml`、`tools/validate_static.py` 改动逐字节未改。本地旧任务记录未动。未创建分支，未提交、推送或改写历史。参见 `baseline.json`、`preservation-final.json`。

## 后续加载与唯一一次真实验收

按用户要求在旧接口门禁处停止，未自动更新已安装插件或重开聊天。后续需：

1. 从本地 marketplace 更新插件：`/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex plugin add codex-duo@codex-duo-local --json`，核对缓存代码与源码，不直接编辑缓存。
2. 重新打开当前项目的聊天，使插件 MCP、技能和原生角色重新加载；确认 begin 暴露 worker_override、complete 暴露 native_dispatch，且缓存是本次代码。菜单栏应用新构建位于 `macos/dist/Codex Duo.app`，尚未替换运行中的应用。
3. 保持原有最多一次授权：通过新 begin 实参使用 Luna low，实际角色为 codex_duo_worker、fork_turns=none。仅在新建临时测试文件执行 before → after，原样执行 reserve 的改前快照、改后规范 diff、真实测试日志和预检，再 complete/verify；主控独立复跑并核对设置、摘要来源与下一个新任务默认。任何已派发或疑似派发之后都不得再派第二次。

仍未验证：新普通聊天工具入口的真实模型运行、宿主真实运行时字段、真实 Worker 修改及完整验收证据链，以及新 macOS 应用的实际原生窗口交互。Swift 构建/单测和浏览器面板验证不替代这些阶段。
