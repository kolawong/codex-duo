# 手动继续验收实现报告

日期：2026-10-11。工作目录：`/Users/kola/codex-duo`，分支 `main`。

## 交付结果

已在现有 0.9.1 工作区基础上接续完成可选 `completion_mode=manual_review`，官方本地插件更新结果为 **0.9.2**。默认仍为 `return`，没有替用户启用新模式。

开始时发现上一轮已有未完成的 Python/Web/schema/bridge 雏形；未把它当作完成。保留原有大量未提交修复，读取 AGENTS.md、已安装和本地 Codex Duo 技能、git status/diff、相关完成代码。`.agents` 只有 marketplace 元数据，没有额外项目技能。Swift 修改遵循 SwiftUI Expert 技能。本轮未启动、委派额外模型。

- 共用服务从原 Worker/Planner 账本投影真实状态，展示任务 ID、运行/失败/阻塞/取消/未知/过期/证据不可用、待验收或主控记录的通过/不通过结论。无有效完成证据不启用复制。
- 复制提示包含规范化项目路径、原任务 ID、结果版本与哈希、原契约/账本/结果路径或 JSON pointer。只验收，不重派、不重置预算、不修改代码、不自动批准后续修改；明确 Planner 只审阅已有计划。
- 复制端不写结论、不发送消息、不派发模型。重复点击、并发双击、重新打开、错误与剪贴板失败有处理。Web 的剪贴板失败显示选中文本，Swift 显示可手动选择的提示。
- 新 Worker 账本持久绑定项目；旧 return 记录缺字段仍兼容且不自动写入。旧 manual Worker 记录缺项目绑定时显示未知、不可复制；显式针对原任务选择 manual_review 后才绑定所在项目。复制 payload 的项目/结果版本不得跨项目复用。
- `review_record` 仅记录主控实际验收结论，按结果 token 和结论 revision 检查幂等/冲突；Worker passed 还须通过原 `verify` 的父任务整合证据校验。新修正或证据变化使旧结论失效。原 complete/verify、取消完成先后顺序与预算计数保留。
- Swift、Web 和设置 schema 使用相同模式；保留旧 wake_on_completion 的不可用语义。新增本地 helper 的 review_inbox/review_prompt/review_record 入口。更新 `$codex-duo` 指令：manual 模式在结果就绪处等待用户提交验收提示；return 保留原验收流程。

没有原聊天直达链接、后台回传或点击即启动模型验收的实现/声明。未使用伪造 chat ID。复制不包含模型摘要、原始回执或任意结果正文，避免把它们转成用户授权或带出凭据。

## 用户入口

1. 用户自行打开新构建的 `macos/dist/Codex Duo.app`，或从 Codex Duo 菜单栏双环图标打开设置；已运行的旧应用需自行重新打开新产物。本轮没有启动应用。
2. 高级设置 →「完成后如何继续」→「结果就绪后，手动继续验收」→ 保存。设置只影响之后的新任务。既有 return 偏好没有改变。
3. 选择「当前项目」，在面板下方 **完成列表 · 手动验收** 点击刷新。Web/MCP 面板提供同一列表；原聊天可请求“打开 Codex Duo 当前项目完成列表”，工具入口为 `codex_duo_open`，显式传实际 project_root 与 scope=project。
4. 对结果就绪项点 **复制验收提示**，自己回到发起该任务的原项目聊天粘贴发送。复制本身不启动任务；用户提交后，验收会消耗模型用量。任务归属无法核对时提示要求停止。

列表有界扫描最近 50 个持久记录，最多展示 20 条手动记录。当前真实项目只读检查为 0 条手动记录，因为没有改动原 return 偏好、没有创建真实测试任务。为旧任务显式选择新模式可使用 completion 的原 project_root/kind/task_id/mode；不创建替代任务。

## 离线验证与命令结果

| 命令/检查 | 结果 | 证据 |
|---|---|---|
| `PATH=/opt/homebrew/opt/python@3.14/libexec/bin:$PATH python3 -B -m unittest discover -s tests -v` | 216 项通过，0 失败 | `python-tests.log` |
| 新增 manual fixtures | 14 项通过；完整套件也覆盖 | `tests/test_manual_review.py`、`manual-tests.log` |
| `node native-build/test-panel.mjs` | Web HTTP/MCP 两套 VM DOM 控制器通过 | `panel-controller.log` |
| HTTP Handler 的内存请求/响应测试 | 9 项通过；不绑定 socket、不启动服务线程 | `http-handler.log` |
| `swift test --package-path macos --cache-path macos/.build/cache --manifest-cache local` | 22 项通过，0 失败 | `swift-tests.log` |
| `node native-build/build.mjs` | 共享 Web 源码重建成功 | `web-build.log` |
| 静态包验证，installed + 本任务开始时配置 hash | 36 项通过 | `static-checks.log`、`static-validation.json` |
| `bash macos/build.sh` | release 构建、资源打包、本地 ad-hoc 签名成功 | `macos-build.log` |
| `codesign --verify --deep --strict --verbose=2 'macos/dist/Codex Duo.app'` | valid on disk / satisfies Designated Requirement | `signature.log` |
| 官方 `codex plugin add codex-duo@codex-duo-local --json` | 确认安装 0.9.2 | `plugin-update.json` |
| 安装缓存对源码 SHA-256 | 39/39 相同 | `installed-hashes.json` |
| macOS 打包服务/bridge 对源码 SHA-256 | 12/12 相同 | `app-hashes.json` |
| 实际打包 HTML 静态检查 | 7 项通过，包含当前 controller、模式和复制 route | `panel-bundle-check.json` |
| `git diff --check` | 通过 | 命令退出 0 |

Swift 构建/测试设置 CLANG_MODULE_CACHE_PATH 与 SWIFTPM_MODULECACHE_OVERRIDE 到工作区 `macos/.build/ModuleCache`。受限执行器无法运行 SwiftPM 自身 sandbox，改为已批准的本地编译命令执行；没有禁用 sandbox、改变系统安全设置或申请打开应用。默认 Python 3.9 的首次尝试缺 tomllib，最终使用已有 Python 3.14。静态验证的初次参数不匹配旧历史基线，最终使用本任务开始时捕获的 hash；验证输出重定向到本报告目录，保留旧 evidence/current 文件。

测试覆盖默认/旧偏好不变、manual 保存重读、全局逐字段更新保护项目覆盖和模型、复制内容、重复/并发复制预算不变、重启、缺任务/坏结果、各非成功状态、跨项目和旧记录、结论幂等与冲突、证据篡改、取消与完成竞态、只读 Planner、原生 Worker 账本及 prepare/begin 诊断。所有模型协议与剪贴板行为均为离线 fixture/stub，不是实际模型或宿主 UI 验收。

## 安装与偏好保护

安装路径：`/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.9.2`。通过官方 CLI 更新，未直接改写缓存；无新 marketplace、凭据或监听设置。当前聊天工具未重新加载的情况不能由离线握手代替证明，用户现有聊天必要时自行重新加载。

以下 6 个文件在任务前后的 SHA-256 全部一致，详见 `preferences-before.json` / `preferences-after.json`：项目与全局 selection.json、项目与全局 config.toml、项目与全局 AGENTS.md。现有 Astra 规划偏好、Worker 组合及项目覆盖均未保存或重置；安装后 helper 对实际项目只读 defaults 仍返回 return（项目 Worker 为 gpt-6.1-sol/high，总轮数上限 10，并行 1）。真实历史预算未清除或重建。

**额外真实 Planner 0、Worker 0、验收模型 0。** 没有向普通聊天发送消息，没有跨线程发消息，没有 ComputerUse/浏览器 UI、没有启动 daemon/监听服务器。协议回归只使用临时文件、内存 HTTP 和一次性 stdio fixture。没有在本项目 reset、pull、新建分支、commit、push 或改写历史。

## 未测与剩余边界

- 没有实际点击宿主面板/系统剪贴板，没有实际回原聊天粘贴发送，没有新一轮真实模型验收；这三项明确未测。
- 没有本次实际视觉布局或原生宿主 UI 验收；检查的是重建后的真实包源码、VM DOM 控制器、Swift 控制器和签名资源，不能称作实际 UI 验收。
- Worker 状态仍依赖原生宿主终态回执由主控 complete 记录；未确认派发不会伪装完成。没有可信原聊天绑定/后台投递；本功能按已批准方案使用复制提示。
- 没有剩余代码或离线验证阻塞。

## 文件清单与既有改动

任务起点保存在 `baseline.tar.gz`、`baseline-hashes.json`、`git-status-before.txt`、`git-diff-before.patch`；本轮增量见 `implementation.diff`（为可读性不包含生成 HTML）及 `changed-files.json`。这份清单以本任务开始时为基线，未将已有未提交修复当作本轮新改动；原有 selection/schema/HTTP route/bridge 雏形经测试保留接续。

| 文件 | 本轮变化 |
|---|---|
| `plugins/codex-duo/plugin.json` | 修改/接续 |
| `plugins/codex-duo/ui/model-desk.html` | 修改/接续 |
| `plugins/codex-duo/mcp/server.py` | 修改/接续 |
| `plugins/codex-duo/skills/codex-duo/SKILL.md` | 修改/接续 |
| `plugins/codex-duo/skills/workflow/scripts/codex_duo_completion.py` | 修改/接续 |
| `plugins/codex-duo/skills/workflow/scripts/codex_duo_service.py` | 修改/接续 |
| `plugins/codex-duo/skills/workflow/scripts/codex_duo_parallel.py` | 修改/接续 |
| `plugins/codex-duo/skills/workflow/scripts/codex_duo_workflow.py` | 修改/接续 |
| `plugins/codex-duo/skills/workflow/scripts/codex_duo_review.py` | 修改/接续 |
| `plugins/codex-duo/.codex-plugin/plugin.json` | 修改/接续 |
| `macos/Sources/CodexDuoMenu/SettingsView.swift` | 修改/接续 |
| `macos/Sources/CodexDuoMenu/CodexDuoClient.swift` | 修改/接续 |
| `macos/Sources/CodexDuoMenu/Models.swift` | 修改/接续 |
| `macos/Sources/CodexDuoMenu/SettingsStore.swift` | 修改/接续 |
| `macos/Tests/CodexDuoMenuTests/CodexDuoMenuTests.swift` | 修改/接续 |
| `panel/static/index.html` | 修改/接续 |
| `panel/static/app.js` | 修改/接续 |
| `tests/test_package_command.py` | 修改/接续 |
| `tests/test_panel_http.py` | 修改/接续 |
| `tests/test_native.py` | 修改/接续 |
| `tests/test_planner_settings.py` | 修改/接续 |
| `native-build/bridge.js` | 修改/接续 |
| `native-build/test-client.mjs` | 修改/接续 |
| `native-build/test-panel.mjs` | 修改/接续 |
| `README.md` | 修改/接续 |
| `NATIVE-INSTALL.md` | 修改/接续 |
| `macos/README.md` | 修改/接续 |
| `macos/build.sh` | 修改/接续 |
| `tests/test_manual_review.py` | 新增 |
| `macos/Sources/CodexDuoMenu/ReviewInboxView.swift` | 新增 |


## 2026-10-11 当前工作区复核：用户确认保留 return-only

本节是后续复核，保留上文历史交付记录。manual 曾于 0.9.2 交付，随后依据用户授权在 0.9.6 定向移除，详见 evidence/return-flow-cleanup/REPORT.md。本次原委派仍引用 0.9.1，与当前工作区不一致。核对后用户明确答复：“保留后来授权的 return-only 流程”。因此不重新引入 manual。

读取 AGENTS.md、本地 Codex Duo SKILL.md、.agents 文件清单、git status/diff、完成模式代码及历史报告。当前 main HEAD 为 cf04199；源码及实际安装缓存 plugin.json 均为 0.9.8，两者 SHA-256 相同。当前没有完成列表或复制验收提示入口，上文 0.9.2 的入口不是当前可用功能。

只读 defaults 为 return、Worker gpt-6.1-sol/high、10 轮、并行 1、Planner disabled。项目及全局 selection.json 复核前后 hash 不变，见 current-return-preferences.json。未修改实现源码、模型偏好、任务记录或预算；保留全部既有未提交改动，包括 Worker override。

运行 PATH=/opt/homebrew/opt/python@3.14/libexec/bin:$PATH python3 -B -m unittest discover -s tests -v：243 项通过，退出码 0，56.453 秒，见 current-return-regression.log。覆盖旧 manual/wake 配置只读兼容、禁止重新启用已移除模式、专用工具/schema 不再提供、旧记录不改写及 complete/verify 预算幂等。

本次仅新增日志/hash 证据并追加报告。没有安装更新、构建、真实 Planner/Worker/验收模型调用、跨聊天消息、ComputerUse/浏览器操作、打开应用、监听服务或 commit/push/reset/pull/新分支。额外真实模型 0。实际 UI、剪贴板及原聊天粘贴未测。按最新决定，manual 不再是本轮交付目标，无待实现阻塞。追加报告的首次命令因默认解释器编码错误未执行，改用明确 Python 3.14 后成功。
