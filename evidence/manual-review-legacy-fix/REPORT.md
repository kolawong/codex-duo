# 0.9.3 旧验收结论兼容修复

日期：2026-10-11。项目：`/Users/kola/codex-duo`，原 `main`。本轮接续已批准的最小实现与离线验证；不重新调查自动唤醒或宿主 UI。没有额外 Planner、Worker、验收模型或子代理调用，没有跨线程发送消息，没有 commit/push/reset/pull/新分支。

## 交付结果

已实现、构建、签名，并通过官方本地插件命令更新安装缓存到 **0.9.3**。macOS 构建为 **0.9.3 / build 12**。

原来的可选 `manual_review` 完成列表及「复制验收提示」保留，默认仍为 `return`。新增旧单 Worker 独立验收报告的保守兼容投影，不迁移账本、不补写历史结论、不修补旧哈希、不更改预算。

- 当前有效的新 `manual_review` 结论优先。过期或无效的新记录不会复活旧结论。
- 旧 `acceptance-report.json`、`coordinator-review.json`、`ledger-before-replay.json` 必须同时存在并关联一致：task ID、handoff ID、单一原 native receipt、完成标记、派发数、原绝对账本路径和原字节哈希。
- 当前子结果及父整合证据必须重新验证，且与旧 `plugin_verify` 一致。旧摘要不含父结果哈希，因此父 diff、测试引用、改动范围、blockers 必须与原账本锁定的子结果完全一致；替换父证据后重新计算哈希也不能继承旧验收结论。
- 可充分关联的 accepted/rejected 映射为历史验收通过/不通过。只读输出 `review_source=legacy_report_verified`，使用固定说明，不把报告或模型输出中的文字当作新授权。
- 旧报告缺失、损坏、超限、符号链接、跨项目/跨 run、receipt 冲突、证据变化、账本哈希不符或其他不能证明的格式，显示 **「历史验收状态待确认」**、`review_outcome=unknown`、`can_copy=false`。没有任何旧验收文件的新任务保持正常待验收路径。
- 失败、取消、阻塞和运行中仍保留原任务状态，不因历史结论冒称完成或通过。
- 原 `return` 任务只读增加 `historical_review` 与真实 `review_state`，不变更模式、不进入手动完成列表、不启用复制。显式修改旧模式会改变原账本快照，不能自动继承修改前的旧验收结论。

这是针对已知旧单 Worker 报告家族的有限兼容。其他历史报告结构或父/子整合证据不同的记录采取待确认状态，不猜测通过，不自动重验。

## 修改清单

任务增量相对于本轮开始的脏工作区，共 16 个已有源码/文档文件；详见 `source-changes.json` 和 `task-increment.patch`，没有把既有未提交修复算作本轮新改动。

| 文件 | 本轮修改 |
|---|---|
| `plugins/codex-duo/skills/workflow/scripts/codex_duo_review.py` | 旧报告只读关联核验、历史未知状态、新旧结论优先与复制门禁 |
| `plugins/codex-duo/skills/workflow/scripts/codex_duo_service.py` | manual 和 return 共用兼容投影；return 仅暴露历史结论 |
| `tests/test_manual_review.py` | 增加 10 项旧记录关联、缺失/坏文件、跨项目/run、冲突、证据变化、重复操作及终态回归 |
| `native-build/test-panel.mjs` | Web/MCP 与 HTTP 控制器模拟覆盖历史未知禁用复制 |
| `macos/Tests/CodexDuoMenuTests/CodexDuoMenuTests.swift` | Swift 解码及控制器覆盖历史未知、复制禁用 |
| `plugins/codex-duo/plugin.json`、`.codex-plugin/plugin.json`、`mcp/server.py`、`native-build/bridge.js`、`tests/test_native.py`、`macos/build.sh` | 版本统一为 0.9.3，应用 build 12 |
| `plugins/codex-duo/ui/model-desk.html` | 从共享面板源重建打包视图 |
| `README.md`、`NATIVE-INSTALL.md`、`macos/README.md`、`plugins/codex-duo/skills/codex-duo/SKILL.md` | 用户入口、版本与保守兼容规则 |

Web 和 Swift 现有产品 UI 直接消费共享服务的 label/can_copy；不需要重写界面或改变设置 schema。新增报告、隔离 fixture 和验证脚本仅在本 evidence 目录，前两轮报告完整保留。

## 命令及结果

所有最终命令退出码为 0。系统 Python 3.9 不适用 tomllib；Python 回归使用已有 Homebrew 3.14，命令前缀为 `PATH=/opt/homebrew/opt/python@3.14/libexec/bin:$PATH`。

| 命令 | 最终结果 | 证据 |
|---|---|---|
| `python3 -B -m unittest discover -s tests -v` | **226 tests / OK**，57.756s | `python-tests.log` |
| `python3 -B -m unittest discover -s tests -p test_manual_review.py -v` | **24 tests / OK**，7.448s | `focused-python.log` |
| `node native-build/test-panel.mjs` | Web/MCP、HTTP VM DOM 行为通过，未启动浏览器/监听服务器 | `panel-tests.log` |
| `node native-build/build.mjs` | self-contained MCP App 构建通过 | `web-build.log` |
| `swift test --package-path macos --cache-path macos/.build/cache --manifest-cache local` | **23 tests / 0 failures** | `swift-tests.log` |
| `bash macos/build.sh` | release 构建与 ad-hoc 签名通过 | `macos-build.log` |
| `codesign --verify --deep --strict --verbose=2 'macos/dist/Codex Duo.app'` | valid on disk / satisfies Designated Requirement | `codesign.log` |
| 官方 `codex plugin add codex-duo@codex-duo-local --json` | **version 0.9.3**，官方缓存路径确认 | `plugin-update.json` |
| `tools/validate_static.py --installed --global-config-sha256 <本轮开始真实配置哈希>` | **36 checks / passed**；输出重定向到本目录，未覆盖旧证据 | `static-validation.json` |
| `python3 -B evidence/manual-review-legacy-fix/check_installed_fix.py` | 安装包 MCP dispatcher、原生打包 bridge、真实/隔离记录、哈希一致 | `installed-check.log`、`installed-interface-receipts.json`、`packaged-bridge.json` |
| 已安装 helper `defaults` / `review_inbox --project-root /Users/kola/codex-duo` | project return、旧覆盖优先、完成列表为空 | `installed-defaults.json`、`installed-inbox.json` |
| `git diff --check` | 通过 | 本轮命令记录 |

Swift 构建/测试使用项目内 ModuleCache 环境变量，在批准的外层执行权限下运行 SwiftPM 自带沙箱，没有关闭沙箱或修改安全设置。安装只用官方命令，没有直接写缓存。

初次安装检查脚本错误地要求应用打包纯 CLI 的 `codex_duo_workflow.py`，在文件不存在处退出；这是验证脚本假设错误，非服务失败。修正为核对应用实际打包的 11 个服务脚本加 bridge 后通过，保留 `installed-check-first-attempt.log`。原隔离 fixture 重读复用，没有覆盖或伪造其旧报告/hash。

## 实际安装只读复核

安装缓存：`/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.9.3`。源码与缓存 **39 个文件 SHA-256 全匹配**；应用 **11 个服务脚本 + bridge 共 12 个文件**全匹配。详见 `cache-hashes.json`。

真实 Worker：`65821f50c5f63f912d8574c7`，仍为 `return`，dispatch 数 1；原账本上限 10，余量计算仍为 9，不是本轮派发授权。原 accepted/completed 报告经完整关联验证，返回 `historical_review.state=passed`、`review_state=passed`、`can_copy=false`。三次读取及提示请求不写任何真实记录；return 的提示请求仍拒绝 `review_changed`。

将原 handoff/run 原样复制到本 evidence 的另一个隔离项目，只在副本显式选择 manual_review：旧原项目绝对路径/hash 不能绑定新项目，因此显示 `legacy_unknown / 历史验收状态待确认 / can_copy=false`。三次提示请求均拒绝 `review_not_ready`，服务重建后响应一致；副本所有文件和派发数不变，旧 accepted 报告未被修改。这关闭了 0.9.2 中「复制旧已验收结果后错误展示为待验收」的路径。

原生应用的一次性打包 bridge 读取 global/project state 与该副本的列表/提示，也得到相同模式和禁用结果。没有运行应用 UI、daemon、app-server 或任何监听服务。

## 偏好与历史保护

**576 个**本轮受保护文件前后哈希一致，包括真实任务/结果/预算、项目/全局配置和偏好、AGENTS、前两轮完整 evidence、Git HEAD/index。清单：`protected-before.json`、`protected-after.json`；`unchanged-check.json` changes={}。

真实账本仍为：`938df22401f0e3beb594c7a32fb42ed2b84fbc06992078511b25ada577b0cc96`。

全局原保存为 manual_review，Planner Astra/xhigh、Worker 6.1 Sol/high；本项目旧覆盖解析后仍 return、Planner disabled、Worker 6.1 Sol/high。全局 revision `5b9cb831c9629df3c8f18fbc9ed48ecfe377f838398d3c6b8f0afed397ab4175`、项目 revision `4ff4fef07b8fff93eb0a532f1a8b82401601a000405d99ccfddfe9d082909980` 均不变。没有替用户清覆盖、改模型或重置预算。工作区既有未提交修复保留，基线与本轮增量分别存档。

## 用户入口与未测范围

需要后续新任务使用此模式时，由用户在设置的 **「当前项目」** 范围选择 **「结果就绪后，手动继续验收」** 并保存；本轮没有代改。仅保存全局默认不会覆盖现存项目设置。

在 Web/MCP 面板或 Swift 菜单设置的 **「当前项目 → 完成列表 · 手动验收」** 查看该模式下的原任务。仅可验收且关联可靠的结果启用 **「复制验收提示」**；用户自己回发起任务的原聊天粘贴发送。复制不派发、不增加预算、不写结论、不开始验收；提交后验收才消耗模型用量，不授权自动修改或重派。历史通过、未知及失败/取消/运行中记录不会冒称新的待验收结果。

**未测**：真实宿主按钮、系统剪贴板、原聊天粘贴发送、真实手动验收模型。Web/Swift 控制器使用离线模拟复制闭包，不声称真实 UI 验收。没有 ComputerUse、浏览器 UI、打开应用授权、凭据新增、安全/监听设置更改。额外真实模型调用 **0**。

实现无剩余阻塞。有限旧格式兼容及未测 UI 范围如上；没有伪造来源聊天 ID、自动唤醒链接或后台回传能力。
