# 名称统一与新会话验收记录

本轮已完成源码、状态迁移、构建签名及官方插件更新。**真实 Planner 调用 0；Worker 调用 0。普通聊天路由尚未验证；实际 UI 未测。** 唯一授权的 `gpt-6.1-sol / high / 1` 规划额度未消耗，没有新 plan/session/turn 回执，也没有把旧两次回执算作本轮调用。

仓库仍为本地 `main`，HEAD 前后均为 `78f38bef638a7643c5dcfe46d8e19fe6694c469d`。未 reset、pull、建分支、commit 或 push。原有未提交 Planner、设置保存和其他修复已先快照保留；改名基于工作树而非恢复 Git HEAD。见 `source-before.tar.gz`、`preexisting.diff`、`source-before.json`（内部备份）。

## 当前会话实际看到什么

这是已经委派的 Local 执行环境，不是已验收的普通用户聊天。开始时可读取的技能来源是 `/Users/kola/.codex/plugins/cache/fusion-local/fusion-minimal/0.7.0/skills/codex-duo/SKILL.md`，官方目录也是旧插件 ID 0.7.0。开始及安装后工具目录中，匹配 `fusion` / `codex_duo` / `codex-duo` 的 MCP 工具均为 **0**。可见原生 collaboration API；暴露的当前角色为 `/root`，没有依据证明命名 Planner 角色或当前聊天模型已实际运行。本轮明确禁止另启动编码主控/Worker，因此未派发任何模型。

完整实际工具名记录：`runtime-tools-before.json`；安装后匹配记录：`runtime-tools-after.json`。它们仅描述当前环境，不能推断用户普通新聊天也没有工具。未使用 app-server、手动 stdio 调用或本地 helper 来消耗这唯一 Planner 额度；离线 SDK 只用于协议回归，不算聊天加载验收。

## 改名映射及真实安装

| 项目 | 原标识 | 当前活动标识 |
|---|---|---|
| 品牌 | Fusion 等旧内部名称 | Codex Duo |
| 插件 ID | fusion-minimal@fusion-local | codex-duo@codex-duo-local |
| 插件目录 | plugins/fusion-minimal | plugins/codex-duo |
| MCP server | codex-duo（原先已是此名） | codex-duo |
| 工具 | fusion.* | codex_duo_*，仅字母与下划线 |
| 角色/模块 | fusion_worker、fusion_planner、fusion_*.py | codex_duo_worker、codex_duo_planner、codex_duo_*.py |
| 技能入口 | codex-duo | codex-duo（唯一入口，保持） |
| 工作流资源 | skills/fusion | skills/workflow |
| 项目状态 | .fusion | .codex-duo |
| Swift/应用域 | FusionMenu / io.kola.fusion.menu | CodexDuoMenu / io.kola.codex-duo.menu |
| UI bridge、token、资源 | fusionTransport / X-Fusion-Token / ui://fusion-minimal | codexDuoTransport / X-Codex-Duo-Token / ui://codex-duo |

修改覆盖 manifest、marketplace、MCP、技能、角色、服务与配置 metadata、面板、启动器、构建脚本、Swift、文档、测试和本项目 AGENTS.md。全局 AGENTS.md 只更新已有 `codex-duo-global` 管理块中的两个工具名称；块外字节不变，未更新 memory。逐源文件映射见 `mapping.json`。

官方 `plugin add` 最终返回版本 **0.8.0**，路径 `/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.8.0`。37 个源码包文件与实际缓存逐文件 SHA-256 匹配，无差异；见 `install-final.json`、`cache-check.json`。MCP server SHA-256 为 `fabd1696663ab4063f7c38bc80faa23311572cde5b9a4ea1c120907d2327bcd8`。

包声明的 20 个工具如下（**包声明，不是当前聊天实际加载清单**）：

```
codex_duo_open, codex_duo_reset, codex_duo_state, codex_duo_save,
codex_duo_defaults, codex_duo_begin, codex_duo_prepare,
codex_duo_execution_plan, codex_duo_settings_read, codex_duo_settings_update,
codex_duo_plan, codex_duo_reserve, codex_duo_complete, codex_duo_verify,
codex_duo_planner_begin, codex_duo_planner_reserve, codex_duo_planner_complete,
codex_duo_planner_status, codex_duo_planner_run, codex_duo_planner_stop
```

Planner 架构仍是已接受的官方 app-server 独立只读 Local 会话；角色模板只供兼容原生链使用，未声称本轮命名子代理已执行。Worker 仍原生路径。`packaged-tools.json` 包含工具可见性声明。

## 迁移与旧注册

先备份旧安装和真实状态，再核对新缓存完整性，通过官方 CLI 清理 `fusion-minimal@fusion-local`、`fusion-local` marketplace，以及历史报告已记录的 `fusion-local` HTTP 外部 MCP（127.0.0.1:27182，当时无监听）。见 `remove-old.json`、`remove-old-marketplace.json`、`legacy-http-mcp-backup.json`、`legacy-http-mcp-remove.txt`。未直接编辑缓存、没有新建凭据或另注册重复全局 MCP。旧 0.7.0 缓存已被官方卸载移除；初始备份仍在内部证据目录。

最终目标注册仅有 `codex-duo@codex-duo-local` 与 `codex-duo-local`；没有旧外部 MCP。插件内 stdio 声明名为 `codex-duo`，不会为了在外部 MCP 列表里显示它而再造一套全局注册。`plugin list` / MCP handshake 都不能证明聊天工具加载。

迁移显式执行一次，原子移动整目录，不改状态内容或记录哈希。**含锁文件的 375 项原有文件/链接与迁移前归档完全一致**；其中 6 个链接属于历史 UI 测试 CLI 别名，原样移动链接本身、从未读取其目标。活动设置/契约/证据读取仍保留自身的链接拒绝检查。见 `state-byte-proof.json`。

原位置 `.fusion` 为只读文件标记，阻止旧插件重建空状态/重置预算；`.codex-duo-migration.json` 记录同一次迁移意图。重复运行返回 `already_migrated, changed=false`。新旧目录冲突停止而不覆盖；中断同次迁移可恢复。旧配置 scope 在返回值中只读规范化，不重写原偏好字节。旧交接角色文件仅识别校验，旧工具调用被拒绝，不注册双套活动标识。旧名只存在于识别逻辑、反向回归、备份及历史不可变证据中。

项目和全局模型偏好文件原字节不变：

- 项目 SHA-256：`4ff4fef07b8fff93eb0a532f1a8b82401601a000405d99ccfddfe9d082909980`；仍为 automatic_project、Worker Sol/high、总轮数10、并行1，项目 Planner disabled。
- 全局 SHA-256：`27395179829d08cef560a64438cd99d0c51b0a6a3d692478bd580d7a34e0117e`；用户 Astra/xhigh/1 偏好未覆盖。

两份原真实 Planner 账本均继续通过内容与结果哈希校验，每份仍是1个 completed 派发和已有结果（`migrated-plan-ledgers.json`）。它们是以前的调用，本轮没有重复。全局 config.toml 因官方注册清理发生变化，未声称整份文件哈希不变；没有执行全局安全/权限设置操作。最终注册字段见 `global-config-final.json`。旧生成的 Fusion Menu/Tandem 应用移至内部 `legacy-apps/` 备份，活动 dist 只保留新 Codex Duo 应用。

## 验证与限制

| 检查 | 最终结果 | 证据 |
|---|---|---|
| Python 全部回归 | 178通过，已有169 + 新迁移9 | python-final.log |
| 首次 plan_only 空组合及逐字段保存 | 纳入完整回归，保存禁止派发、覆盖优先级不变 | tests/test_planner_settings.py |
| 迁移 | 重复、冲突、同次中断恢复、旧交接、总预算、不确定尝试不重发、scope只读规范化 | tests/test_migration.py |
| Swift | 19通过，包括旧域历史只读继承及新域优先 | swift-final.log |
| 共享面板构建 | 成功 | native-build/build.mjs；build-final.log |
| 面板行为 | mjs 测试通过 | panel.log |
| SDK 协议 | 通过，离线模型调用0 | sdk.log |
| 静态结构 | 36通过 | static.log |
| 应用 release 与签名 | 构建成功，ad-hoc 签名 deep/strict 校验通过 | signature.log、build-final.log |
| 真实安装缓存 | 37源码文件全部匹配 | cache-check.json |
| Git diff whitespace | 通过，main/HEAD未变 | git diff --check |

辅助旧 `test-panel.cjs` 未执行成功，因为现有环境没有 jsdom；未新增安装依赖。它不替代已通过的 mjs 行为检查，也不证明外观。

实际 UI：Computer Use 选择新应用路径返回 timeoutReached；按真实新 bundle ID 重试返回 Invalid app。没有换 AppleScript、shell UI 控制或其他方式绕过，故 **UI 未测**。普通聊天路由：安装后该 delegated Local 工具目录仍无规划 MCP，故 **未验证**；没有据此断言普通聊天必然不可用，也没有伪称另开了普通宿主会话。

最小下一步：父端回到或由用户打开一个真正的普通项目聊天，选择 6.1 Sol，让正常工具加载先显示 `codex_duo_defaults` 和 `codex_duo_planner_begin/run/status`。若仍未显示，先解决宿主工具加载，额度保持未用。若显示，沿用本轮已有授权，只请求级指定 `gpt-6.1-sol / high / max_turns=1`，读取 README 返回「添加使用说明」的三步计划；预算/派发先持久化，确认实际只读、禁网、approval never 和外部工具/递归禁用，失败不重试、不改 Astra 偏好、不运行 Worker/测试、不写 README。给出真实 session/turn/计划与文件未变证据后，才能验收普通聊天路由。
