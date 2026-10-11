# Diff 证据契约修复交付

日期：2026-10-11。项目：`/Users/kola/codex-duo`，本地 `main`。

本轮完成代码、角色指引、文档、隔离 fixture、离线回归、构建签名与官方本地插件更新。已安装插件 **0.9.5**；本地 App 产物 **0.9.5 / build 14**。本轮真实额外模型调用 **0**，没有重新派发 Worker、Planner 或验收模型，没有向聊天发送消息，没有启动应用、监听服务或 daemon，没有 commit/push/reset/pull/新分支。

## 实际失败与根因

实际样例来自既有 `evidence/manual-review-smoke-20261011T102707Z-e657a820/coordinator-review.json`，handoff `72f92a80e6c7b4155fcd4b45`。原报告记录原生 Worker 的 before→after 修改及精确断言通过，但 `complete(completed)` 拒绝证据，随后已记录 failed。原 diff 是：

```diff
--- evidence/manual-review-smoke-20261011T102707Z-e657a820/probe.txt
+++ evidence/manual-review-smoke-20261011T102707Z-e657a820/probe.txt
@@ -1 +1 @@
-before
+after
```

本轮对原文件仅做只读 verify，确实重现 `invalid diff path prefix`（`original-rejection.json`）。旧验证器要求 `a/`、`b/` 前缀，但 contract、Worker 角色和派发指引没有规定如何从实际改前字节稳定生成此格式，demo 虽有正确示例，却不是明确的 Worker 操作链。这里应修正生成路径与指引，不能把裸路径放宽为已接受证据。

另发现独立缺陷：旧验证器跳过 `/dev/null` 后仍要求两个文件头计数，因此单独新增/删除的标准 diff 无法通过。现用成对文件头与 hunk 解析，允许缺失一侧的 `/dev/null`；另一侧仍须正确前缀、范围及 `changed_paths` 一致。不支持的格式继续拒绝。

真实原 diff SHA-256：`cbe103ef88c59abd5f943d5637f5b4c70e6b6d2f7c10c140e37dde651c8dcba7`。离线 fixture 与其逐字节一致。安装后的新验证器仍拒绝原样例，并提供 snapshot/diff 的诊断，未修改原证据。

## 实现与文件范围

本任务起点已有大量未提交修复。`source-before.tar.gz` 和 `source-before.json` 保存起点；`increment.diff` 只表示本轮增量；`git-diff-before.patch` 保留起点相对 HEAD 的既有修改。完整清单及前后 hash 见 `changed-files.json`。本轮改动 15 个已有文件，新增 2 个测试文件：

- `plugins/codex-duo/skills/workflow/scripts/codex_duo.py`：新增 task/project/精确路径绑定的 `snapshot` 与 `diff` CLI；快照当前改前字节而非 Git HEAD，生成 canonical unified text diff、缺少最终 LF 的标记；校验成对头部、hunk 计数、新增/删除、重复头和路径。demo 使用同一生成器。
- `plugins/codex-duo/skills/workflow/scripts/codex_duo_parallel.py`：reserve 返回 `evidence_commands` 的 snapshot/diff/preflight argv。命令路径规范化，支持 macOS 临时目录别名；不新增派发、不改预算规则，不重写旧 handoff。
- `.codex/agents/codex_duo_worker.toml`、插件 `skills/codex-duo/SKILL.md`、`skills/workflow/references/contract.md`：明确改前捕获、生成、保存真实测试日志/result hash、提交前 verify 的顺序；禁止猜测基线、全脏区 diff、修补终态证据及将拒绝视为重试授权。角色没有新增模型覆盖。
- `tests/test_diff_evidence.py`、`tests/fixtures/manual-review-unprefixed.diff`：17 项隔离回归；不执行真实模型或真实任务状态迁移。
- `README.md`、`NATIVE-INSTALL.md`、`macos/README.md`：更新实际入口、版本、证据链步骤和边界。
- 两个插件 manifest、`mcp/server.py`、`native-build/bridge.js`、`tests/test_native.py`：版本同步为 0.9.5；`macos/build.sh` 同步 0.9.5/build 14；重建 `plugins/codex-duo/ui/model-desk.html`。未改 Web/Swift 面板行为或已有头部布局。

helper 支持项目范围内非 Git、未跟踪、临时文本文件；拒绝绝对路径、`..`、非规范化路径、symlink、二进制、rename metadata、缺少或错配快照、已存在输出。重命名只能在两个文件均获授权时表示为删除+新增。仅空文件新增/删除不产生文本 hunk，明确不支持。快照/hash 证明一致性，不证明模型出处或语义正确；`evidence_valid` 仍需要主控独立验收。

## 回归与命令结果

| 命令/检查 | 结果与日志 |
| --- | --- |
| `PATH=/opt/homebrew/opt/python@3.14/libexec/bin:$PATH python3 -B -m unittest discover -s tests -v` | 最终 **243/243 通过**，`python-tests.log` |
| 同一 Python 的 `unittest discover -s tests -p test_diff_evidence.py -v` | **17/17 通过**，`diff-tests.log` |
| 原 contract 专项 | **15/15 通过**，`contract-tests.log`；亦包含于最终全量 |
| `node native-build/build.mjs` | exit 0，`web-build.log` |
| `node native-build/test-panel.mjs` | exit 0，MCP/HTTP 面板控制器与 manual 保存/重复复制/禁用态/错误/项目竞态通过，`panel-tests.log` |
| `swift test --package-path macos --cache-path macos/.build/cache --manifest-cache local`，设置两项项目内 ModuleCache 环境变量 | **27/27 通过**，`swift-tests.log`；含既有 offscreen 渲染与回调测试 |
| 同样 ModuleCache 设置的 `bash macos/build.sh` | exit 0，`macos-build.log`，产物 `macos/dist/Codex Duo.app` |
| `codesign --verify --deep --strict --verbose=2` | exit 0，磁盘签名有效，ad hoc 签名；`codesign.log` |
| `python3 -B evidence/diff-evidence-fix/installed_cli_fixture.py` | 系统 **Python 3.9.6**、实际安装 helper、隔离字节的 snapshot→diff→verify 通过，`installed-cli-fixture.json`。假测试日志明确标为离线数据 fixture，未执行 task argv、未验收、未派发 |
| `PATH=… python3 -B evidence/diff-evidence-fix/audit.py` | **36** 项结构检查通过、安装 hash 与保护检查通过，`audit.log`、`static-validation.json` |
| `git diff --check` | exit 0 |

专项覆盖真实裸路径失败样例、正确修改/新增/删除及 `/dev/null`、多 hunk/CRLF/缺少最终 LF、将生成 diff 在独立临时目录实际用 `patch -E -p1` 应用并比对字节、类似文件头的正文、changed_paths/方向、路径穿越/绝对路径、rename/binary/symlink、坏快照/hash/project/task、无变化和已存在输出。另验证 reserve 的实际 argv 全链路预检不改 ledger；证据拒绝、failed 重复回执及复制拒绝只在隔离账本内验证，dispatch_count 始终 1，预算不增加。

首轮全量发现 reserve 的临时目录别名未规范化，新增链路测试失败；已修正命令路径并重跑最终 243 项全部通过。未把先前失败计为通过。

## 安装与保护核验

使用官方入口：`/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex plugin add codex-duo@codex-duo-local --json`，exit 0。`plugin-update.json` 确认版本 0.9.5、缓存 `/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.9.5`。未手工覆盖缓存。

源码和缓存 **39 个文件全部 hash 匹配**；App 内 **11 个共享服务脚本**及 bridge 与源码匹配（`package-hashes.json`）。App binary SHA-256 `5fb3fce864a461f63e1a0b8f29bfaf311cbcf83159d4bb1cbb9ccb41f734e639`。这些证明安装/打包一致，不证明当前已运行宿主载入了新工具。

**419 个受保护文件全部 hash 不变**（`protected-after.json`）：既有 `.codex-duo` 记录/预算、真实 smoke 原结果/日志/报告、AGENTS、项目和全局配置、marketplace、Git HEAD/index、当前保存偏好。没有清除或重新创建真实任务 ID。

当前项目保持用户最近保存的 `manual_review`、Worker `gpt-6.1-sol/high`、当前聊天协调、10 总轮/1 并行、项目 Planner disabled。项目 revision `6226ef62e312ee777215528da1e015b381a9ddb259228f23dc7b48f741c5d84e` 不变。全局保持 Astra/xhigh Planner plan_only 和原模型配置、manual_review，revision `60433cd6accc04925d1a3ec01a6eab75e460e6d5c4a50e13addacb325e2a785c` 不变。本轮没有把偏好恢复到早先 return；未配置时的默认 return 仍由既有全量回归验证。

实际失败 ledger SHA-256 `6d89a79da34e41a84c5e7c760e394244b5615e9ebdc801cfdff6a7b573fd157e` 不变。安装模块的进程内只读 dispatcher 连续两次读取 failed/can_copy=false/result_token=null，连续两次复制请求拒绝；期间禁止保存、begin、prepare、reserve、complete、计划、验收写入等入口（`installed-read-only.json`）。未启动 MCP transport/server。真实累计派发 **1**、账本剩余 **9** 保留；用户单次授权剩余 **0**。剩余账本轮数不是再派授权，本轮不调用真实 complete 或 verify 状态迁移。

## 使用与未测边界

后续获准的新 Worker 任务由原聊天正常 defaults→begin→plan→reserve，主控原样转交 reserve.evidence_commands：修改前 snapshot、修改后 diff、真实检查和 result 保存后 preflight。不是把 argv 当 native spawn 参数，也不是要求用户复制内部 JSON。缺基线或预检失败时停下并报告，不修补本次真实 failed run。

完成列表入口延续现有实现：用户自行打开新 App，从双环菜单设置选择当前项目，在 **完成列表 · 手动验收** 刷新；Web/MCP 可用 `codex_duo_open(project_root=/Users/kola/codex-duo, scope=project)`。结果通过证据门槛且就绪时才提供 **复制验收提示**；复制不派发、不验收，用户回原项目聊天粘贴发送后才消耗验收模型用量。这次既有失败项仍不可复制。原手动功能交付报告 `evidence/manual-review/REPORT.md` 保留，其他前序报告亦未覆盖。

没有实际宿主 UI 点击、系统剪贴板或原聊天粘贴测试；没有原生新 Worker 验收、Planner 或验收模型调用。离线控制器/Swift offscreen 测试与安装 hash 不能代替这些真实验收。当前没有代码实现阻塞；成功 ready→copy→独立验收的真实链路仍未验证，需要另一次明确的新任务调用授权，不能继续消费原失败任务。
