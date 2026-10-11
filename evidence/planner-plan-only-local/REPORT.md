# plan_only 本机验收报告

最新状态：批准后的真实调用准备检查已完成；官方会话级只读启动可用，但当前接口不能选择 fusion_planner 或证明子角色完整有效权限，停在模型调用前（0/1）。请优先阅读文末“真实调用准备检查”。前轮 Python 150 项、Swift 18 项及实际 MCP 注册通过。

日期：2026-10-11。项目：`/Users/kola/codex-duo`。范围：已批准的本机测试、构建、官方插件更新及加载检查；未启动 Planner、Worker、其他模型或用户聊天。

## 代码和保护结果

- 分支 `main`，本机 HEAD `78f38bef638a7643c5dcfe46d8e19fe6694c469d`，与待验收提交一致；ancestor 检查成功。
- 开始时工作树干净，生成报告前仍干净；仅新增本目录报告与忽略的检查日志。无功能源码修改、reset、pull、commit、push 或历史重写。
- 项目 selection、全局 selection、全局 `config.toml` 和 `.codex/agents/fusion_planner.toml` 的前后 SHA-256 完全相同。未改模型、激活模式或安全设置，未访问凭据。
- 已读取 AGENTS.md、README.md、NATIVE-INSTALL.md、cloud 验收报告、planner-host.md 和仓库内 codex-duo 技能；本机没有 `.agents/skills`。

## 本机测试和构建

| 检查 | 本机结果 | 证据 |
| --- | --- | --- |
| Python unittest | 148 项：147 通过、1 跳过 | `python-unittest-native.log` |
| Swift tests | 18 项全部通过，包括两项 Planner 配置兼容测试 | `swift-test-native.log` |
| Web 面板构建 | 通过，生成内容没有 Git diff | `web-build.log`, `web-build-restored.log` |
| HTTP/MCP 面板行为 | 两种 controller 均通过，包括 Planner 设置保留和不派发行为 | `web-controller.log` |
| JSDOM 8 项交互检查 | 未完成：缺少 jsdom；锁文件依赖恢复遇 npm registry ECONNREFUSED | `web-dom.log`, `npm-ci.log` |
| 官方 MCP SDK 源码检查 | 通过，无模型调用；恢复依赖后复查通过 | `mcp-sdk-source.log`, `mcp-sdk-restored.log` |
| 静态结构检查 | 35 项通过，使用本次全局配置基线 | `static.log` |
| macOS release 打包 | `bash macos/build.sh` 成功，产物 `macos/dist/Codex Duo.app` | `macos-build.log` |
| 应用签名和资源 | codesign 严格验证退出 0，Planner 脚本、角色模板、宿主说明与仓库逐字节一致 | `app-package-check.json` |
| Git diff 检查 | 通过，功能代码无差异 | `final-check.json` |

环境说明：默认 `/usr/bin/python3` 是 3.9.6，不满足仓库 Python 3.11+ 要求。第一次因此失败；最终测试用本机现有 Python 3.11.17，在单进程 PATH 中加入 `/opt/homebrew/opt/python@3.11/libexec/bin`，未安装 Python 或修改全局 PATH。Swift 首次受编译缓存权限限制；Python 3.11 首次受本地测试 socket 监听限制；使用已获批准的本机测试权限重跑后均通过。

Python 跳过项为 `test_launcher_without_path_and_from_unrelated_cwd`，原因 `requires the existing local Python deployment`。这与下面直接启动器复现的部署问题有关，不能当作部署已通过。

JSDOM 缺依赖不是已确认的源码错误。尝试 `npm ci --prefix native-build --ignore-scripts --no-audit --no-fund`，官方 registry 的 xmlchars tarball 连接被拒绝。随后 `npm ci --prefix native-build --offline --omit=dev --ignore-scripts --no-audit --no-fund` 从现有缓存恢复了 17 个构建依赖；恢复后构建及 SDK 检查再次通过。未改 package.json、锁文件、npm registry 配置或网络设置；JSDOM 仍未安装/执行。

## 官方插件更新

文档所列 CLI 路径存在，`plugin add` 支持指定身份和 `--json`。但正常 marketplace 查询显示 `fusion-local` 源仍是已不存在的 `/Users/kola/codex-fusion`，直接命令无法正确解析本次仓库。

使用 CLI 支持的单次配置覆盖先确认 marketplace 根为本项目，随后执行：

```sh
/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex plugin add fusion-minimal@fusion-local --json -c 'marketplaces.fusion-local.source="/Users/kola/codex-duo"'
```

安装退出 0；身份仍 `fusion-minimal@fusion-local`，版本仍 `0.7.0`，安装位置 `/Users/kola/.codex/plugins/cache/fusion-local/fusion-minimal/0.7.0`。未手动改缓存，全局配置哈希未变。版本号不作为更新证据；server、launcher、Planner 源码、角色模板、host 文档、技能、面板和 MCP 声明的源码/安装哈希全部一致，见 `cache-check.json`。

单次 `-c` 不持久化：全局 marketplace 旧路径仍存在，下次无覆盖的 CLI marketplace 解析仍会失败。这需要单独批准后通过官方 marketplace 入口纠正，不能靠重复安装消除。

## 四层加载证据

1. **安装缓存：已更新。** 关键文件哈希与 HEAD 源码一致，Planner 配置及资源已包含；版本未变。
2. **本机独立服务：有条件通过。** 使用安装缓存的 `./mcp/launch.sh`、显式实际项目根和一次性 Python 3.11 PATH 覆盖，stdio 握手成功，发现 18 个工具，包括 `fusion.planner_begin/reserve/complete/status`。实际只调用 `fusion.defaults` 和不存在 plan_id 的 `fusion.planner_status`，读取 panel resource；未 begin/reserve/complete 任何 Planner 任务。服务返回 plan_id 不存在的错误符合预期。见 `installed-mcp.json`。
3. **当前委派会话：未加载。** 安装前后可调用工具清单均没有 fusion 工具。独立 MCP 的工具 discovery 不会为这个委派会话注入工具；未无限重装、创建新聊天或触碰 Codex/ChatGPT 主界面。
4. **用户普通 Local 会话：未实测。** 未操作其他聊天、重启 Codex/ChatGPT 或推断另一个宿主的加载状态。需修复部署路径问题后，由用户按意愿刷新技能/工具或进入新的 Local 会话验证。当前证据不能保证刷新就会生效。

**直接启动复现：** 在当前未经覆盖的 PATH 下，安装缓存 launcher 退出 127：`Fusion requires an existing Python 3.11+ ... No runtime was installed.` 本机有 `python3.11/3.13/3.14`，但没有 `/opt/homebrew/bin/python3`；系统 python3 为 3.9。launcher 只寻找无版本 python3 及固定路径，未探测这些版本化命令。见 `installed-launch-default.log`。原生应用的 Python 探测包含版本化名称，因此它可以正常读取设置。

## 原生界面

新应用已实际打开。工具最初打开了 SwiftUI 空白 Settings scene；正常退出 **Codex Duo** 后，按文档用 `open ... --args --project-root /Users/kola/codex-duo --show-settings` 打开正确的共享设置窗口。未退出或重启 Codex/ChatGPT。

通过原生 Accessibility 和窗口截图核对 `fusion-settings-window`：当前项目 `/Users/kola/codex-duo`，编辑范围“当前项目”，来源“项目独立设置”，模型 GPT-6.1-Sol、强度“高”、自动模式、执行次数 10，独立规划者选中“关闭”。滚动后“仅规划”按钮和“保存仅更新设置，不启动模型；不会自动执行 Worker”的提示实际可见。未点击模型选择、规划开关或保存；状态保持“已保存”。观察字段记录在 `final-check.json`，截图已在本任务的 UI 工具输出中展示。

## 自定义角色和真实模型边界

项目 `.codex/agents/fusion_planner.toml` 与插件安装模板、应用内模板一致。TOML 为 `name=fusion_planner`、`sandbox_mode=read-only`、`approval_policy=never`、子代理禁用，未固定模型/强度。存在配置不等于真实宿主发现、有效只读执行或模型来源证明。

本次委派宿主 native spawn schema 不提供自定义角色选择；父环境为 workspace-write，并有外部连接器及代理工具。没有可信信息证明子角色会获得只读、禁提权、禁网络、禁外部工具和禁再次派发的完整有效权限。因此当前宿主不能通过真实 Planner 派发门禁；没有通过普通 Worker 或新 CLI 模型进程替代。未调用模型，未产生真实模型 receipt。

## 最小下一步，未实施

- 源码修正待另行批准：仅扩展 `plugins/fusion-minimal/mcp/launch.sh` 对既有 Python 3.11+ 版本化可执行文件的探测，并补有意义的受限 PATH 启动回归；不安装运行时、不改用户 PATH。验证后通过官方 plugin add 更新缓存。
- 配置修正待另行批准：使用官方 `codex plugin marketplace add /Users/kola/codex-duo --json` 更正 fusion-local 源，事先确认 CLI 对同名 marketplace 的更新语义，保留其他配置。不要手改缓存或安全设置。
- JSDOM 检查待 registry 连通后按现有锁文件补依赖再执行；本机原生入口已核对。
- 真实 Planner 测试需要用户另行批准**实际规划模型、强度、调用次数及用途**，并先找到能选择 fusion_planner 且可信证明上述有效权限的宿主。当前 Planner 设置为 disabled，未保存规划模型；Worker 的 gpt-6.1-sol/high 不能被当作已批准的 Planner 选择。
- 可供父会话提出的具体下一轮请求：`gpt-6.1-sol / high`、最多 **1 次**只读规划调用，读取 `README.md`、`plugins/fusion-minimal/skills/fusion/references/planner-host.md` 和 `.codex/agents/fusion_planner.toml`，返回 plan_only 宿主接入验收计划、风险及建议测试；不运行测试、不写文件、不网络访问、不派发 Worker。这只是建议，尚未批准；必须先满足有效权限门禁，结果回当前聊天由用户审核。

结论：本机主要测试、原生编译/打包、应用设置入口和插件缓存更新已验证。默认插件部署与会话加载仍有上述边界，真实 Planner 执行尚未验收。

---

## 2026-10-11 用户批准后的本地修复（最新结果）

用户已另行批准本地修复启动器和 marketplace 路径。本节取代上文关于这两个部署问题仍未解决的结论；保留之前验收记录以便追溯。仍未启动额外模型、Planner/Worker、用户聊天，未 commit/push 或重启 Codex/ChatGPT。

### 变更

- `plugins/fusion-minimal/mcp/launch.sh`：保留原先 PATH `python3`、Homebrew 无版本 `python3`、`/usr/local/bin/python3` 和系统 `python3` 的优先顺序；在这些候选均不适用时，扫描 PATH 和既有常见安装目录中的纯数字版本化 `python3.N` 命令。仍实际执行 >=3.11 的版本检查，排除 `python3.N-config` 等辅助程序，支持含空格的路径并保留全部 server 参数。仅使用 POSIX shell 内置操作，无运行时安装、无 shell profile 加载、无全局 PATH 更改。
- `tests/test_package_command.py`：增加旧无版本解释器不可用而 PATH 只有版本化 Python 的回归、无版本解释器优先顺序检查，并修正旧最小 PATH 测试的部署探测、显式 project_root 和当前 Planner 设置字段断言。原来跳过的本机部署测试现在真实执行通过。
- 全局 `~/.codex/config.toml`：仅 `marketplaces.fusion-local.source` 从 `/Users/kola/codex-fusion` 改为 `/Users/kola/codex-duo`。先用隔离 CODEX_HOME 验证官方命令同名更新语义，再运行官方 `codex plugin marketplace add /Users/kola/codex-duo --json`。没有直接覆写整个配置。对修改后内容只反向替换这一项即恢复修改前完整文件的 SHA-256，证明其他字节未变。

旧值与恢复基线记录在 `repair-baseline.json`；单项配置检查在 `repair-config-check.json`。修改前配置 SHA-256 为 `64a46ddaf7e5f6ec6c676d006d3a9b94cc9b1884f92b4eb7925271af14673a74`，修改后为 `7dcfb9d1211de8c5286841f7020434c5f539dbbd883c7e96a4468e75ee3fd509`。未复制凭据或完整全局配置到证据目录。

具体功能 diff 保存于 `repair.diff`：仅 2 个源码/测试文件，82 行新增、6 行删除。开始时仅有此前本报告目录未跟踪；没有覆盖其他用户改动。项目/global selection 和 Planner 自定义角色哈希均不变。HEAD 仍 `78f38bef638a7643c5dcfe46d8e19fe6694c469d`。

### 验证

| 检查 | 最新结果 | 证据 |
| --- | --- | --- |
| 旧启动器回归复现 | 使用 HEAD 旧文件运行新回归，按预期失败，退出 127 | `repair-regression-before.log` |
| 启动器相关回归 | 9 项通过；后续最终全量覆盖更新后的隔离 fixture | `repair-launcher-tests.log`, `repair-python-unittest.log` |
| 全量 Python unittest | 使用现有 Python 3.11.17，150 项全部通过，无跳过，不需 PATH 覆盖 | `repair-python-unittest.log` |
| Shell / diff 检查 | `sh -n`、`git diff --check` 通过 | `repair-final-check.json` |
| 静态结构 | 35 项通过，使用已批准修改后的全局配置哈希 | `repair-static.log` |
| 官方 SDK stdio | 默认环境通过，无 PATH 覆盖、无模型调用 | `repair-mcp-sdk.log` |
| 持久 marketplace | 默认配置查询成功，fusion-local 根为本项目 | `repair-marketplace-list.json` |
| 官方插件更新 | 无临时配置和 PATH 覆盖的 `codex plugin add fusion-minimal@fusion-local --json` 成功 | `repair-plugin-install.json` |
| 已安装缓存握手 | 默认 PATH、最小 `/usr/bin:/bin`、空 PATH 三种环境均退出 0，均发现 18 个接口和全部 4 个 Planner 接口 | `repair-installed-mcp.json` |

三种已安装服务探测均从无关 `/tmp` cwd 启动，明确传实际 project_root。仅 initialize、tools/list、fusion.defaults、不存在 plan_id 的 fusion.planner_status；无 Planner begin/reserve/complete 调用。安装缓存 launcher 与新源码逐字节相同，版本仍 0.7.0。默认环境 probe 完全继承调用者 PATH，没有添加 Python 路径；最小/空 PATH 探测仅减少 PATH，不给启动器补解释器路径。

这次仅修改插件 launcher 和 Python 测试，macOS 应用不会打包 launcher；应用源码、bridge、共用 service、UI 资源均未改变，因此不需要重新编译应用或重复此前已通过的 18 项 Swift 测试/签名验收。前端未变；JSDOM 依赖网络问题也未在这次修复范围内重试。

### 加载和剩余边界

- **插件缓存**：修复已安装，源码哈希一致。
- **本机独立服务**：默认、最小、空 PATH 启动问题均已消失，四个 `fusion.planner_*` 工具真实 discover 成功。
- **当前委派会话**：最终可调用工具清单仍没有 fusion 接口；没有因为独立服务成功而宣称会话加载成功。仅进行一次修复后的官方插件更新，没有重复重装。
- **用户普通 Local 会话**：未触碰、未实测；需要用户自行选择刷新工具/技能或新 Local 会话后核对。没有重启正在工作的 Codex/ChatGPT。
- **真实 Planner 执行**：仍未批准、未调用。本次不能证明当前宿主的自定义角色选择或有效只读权限。后续真实模型验收仍需明确模型/强度/调用范围批准及可信的权限门禁证据，不能用普通 Worker 代替。

结论：批准的两项本地修复已完成并通过回归，默认插件启动和 marketplace 路径问题已解决。剩余问题为会话工具刷新/宿主能力及此前 JSDOM 依赖下载边界，不是本次启动修复的失败。


---

## 2026-10-11 原生宿主接入诊断与修复（最新结果）

用户追加批准最小本地宿主接入修复、官方插件更新与验收；仍不批准额外模型调用。以下替代上文关于启动根和角色配置可用性尚不明确的结论。没有创建聊天、派发 Worker/Planner、提交、推送、重启用户的 Codex/ChatGPT 或更改其安全设置。

### 实际宿主发现的两个加载错误

使用同一官方二进制 `codex-cli 0.162.0-alpha.17.2` 的 `app-server --strict-config --stdio`，继承真实 CODEX_HOME、明确项目 cwd，仅调用 initialize、config/read、plugin/read、mcpServerStatus/list。不调用 thread/start、turn/start 或模型接口，也未连接/修改用户正在使用的宿主实例。此前独立 MCP fixture 覆盖了 --project-root，因此未暴露第二个错误。

1. 原生角色加载器反复输出 `Ignoring malformed agent role definition ... fusion_planner.toml: invalid transport`。禁用的 `[mcp_servers.codex-duo]` 仍须提供有效传输字段，角色此前被整体忽略。
2. 原生 MCP 注册名称存在但工具为空，握手失败；server 输出 `project-root must be an existing absolute non-symlink directory`。两份 MCP 声明仍硬编码已经删除的 `/Users/kola/codex-fusion`。这不是 Python 启动器修复失效，也不是重复安装可以解决的缓存问题。

修复前实际宿主响应及过滤后的相关启动日志：`integration-host-config.json`。仅记录本项目相关信息，不保存凭据、完整配置或无关会话。

### 最小修改与保护

- 项目角色及相同插件模板在禁用 MCP 项中补 `command = "false"`；维持 `enabled = false`。若错误启用，惯常 inert command 退出而不会暴露工具。逐字段比较 HEAD 角色配置证明仅增加这一个命令，read-only、never、禁登录 shell/网络/应用/子代理/插件字段均未变化，也未固定模型。
- 两份 MCP 声明将启动根改为 `${PLUGIN_ROOT}`，工作目录也仍为该值。启动所需目录存在且随安装可移植；业务工具仍必须显式传实际聊天 `project_root`。旧无 root 调用会落到插件缓存目录，不能定位用户项目。
- 修正静态声明检查；包装启动回归不再人为覆盖 manifest 的 project-root，改为复制到含空格的临时安装目录并使用宿主实际占位符展开。旧 HEAD manifest 在新回归中按预期失败，证据 `integration-manifest-regression-before.log`。
- 更新 `NATIVE-INSTALL.md` 与 `planner-host.md` 说明上述事实。没有解除只读保护。

本轮结束累计 diff 为 10 个源码/配置/测试/文档文件，109 行新增、15 行删除（包含前轮启动器修复），见 `integration.diff`。HEAD 仍 `78f38bef638a7643c5dcfe46d8e19fe6694c469d`，main，ancestor 检查成功。项目/global selection 哈希和前轮批准后的全局 config 哈希保持不变；本轮未修改全局文件。见 `integration-final-check.json`。

### 最终验证

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Python unittest | 150 项全部通过，无跳过；现有 Python 3.11.17，无 PATH 补丁 | `integration-python-unittest.log` |
| Swift test --package-path macos | 18 项通过，0 failures | `integration-swift-test.log` |
| bash macos/build.sh | release 构建及打包成功 | `integration-macos-build.log` |
| codesign / 应用资源 | strict 签名验证退出 0；Planner script、角色模板、宿主说明均与源码一致 | `integration-final-check.json` |
| 静态结构 | 35 项通过 | `integration-static.log` |
| 官方 plugin add | 无配置覆盖的标准命令退出 0；身份和版本仍 fusion-minimal@fusion-local / 0.7.0 | `integration-plugin-install.json` |
| 已安装 stdio 服务 | 声明启动根不覆盖；默认、最小、空 PATH 均发现 18 工具 / 全部四个 Planner 接口 | `integration-installed-mcp.json` |
| 实际官方 app-server MCP 注册 | 原生宿主返回 18 个真实注册工具，全部四个 Planner 接口，toolsError 消失 | `integration-host-config-after.json` |
| 角色加载诊断 | 不再出现 malformed agent role / invalid transport | `integration-host-config-after.json` |
| diff / shell / 保护 | git diff --check、sh -n 通过；选择和全局配置哈希不变 | `integration-final-check.json` |

插件源码/缓存关键文件逐字节一致。Planner TOML 在项目、缓存模板、应用模板三处一致。实际宿主 config/read 确认项目 trusted、插件 enabled、agents enabled。尚有既有 defaultPrompt 超过 128 字符被宿主忽略的非阻塞 metadata 警告；此次没有扩大修改到默认提示文案。

共用 UI 未修改：此前 native 设置窗口已经实际核对当前项目、Worker Sol/high、Planner 关闭、“仅规划”入口，保存不启动模型。此次重打包只刷新角色模板/说明，严格验证资源，未操作正在工作的 Codex/ChatGPT。Web/JSDOM 状态沿用先前验收；JSDOM 仍因依赖下载连接被拒绝未执行。

### 四层结论与真正剩余的宿主门禁

1. **安装缓存可用：通过。** 标准官方更新及文件一致性确认。
2. **本机独立服务与全新实际官方宿主注册：通过。** 不仅离线 fixture，实际宿主已经注册 18 工具；角色解析拒绝已消失。不能将“解析成功”写成“角色已经能由原生调用选择”。
3. **当前委派会话：仍未加载。** 可调用工具清单没有 fusion.*，native spawn schema 没有自定义角色选择字段。不能发明 agent_type 参数或替换为 CLI 模型进程。没有对该会话执行真实工具调用。
4. **用户正在使用的普通 Local 会话：未直接验收。** 没有操作其主界面/其他聊天。现有本地控制 daemon socket 不存在，版本检查返回 ENOENT；没有启动 daemon、重启用户应用或以内部 IPC 绕过边界。生成的官方 app-server client schema 提供 MCP 状态读取，但没有无模型角色 roster/派发选择接口；thread/start 亦未调用。fresh app-server 的成功不能证明已有 Local 会话已经刷新。

额外的权限证据：实际官方宿主 config/read 返回原有默认 `sandbox_mode = danger-full-access`、`approval_policy = never`，并保留模型 gpt-6.1-sol/high。这里没有修改它们。当前委派运行环境本身为 workspace-write，且提供连接器/代理工具。官方文档说明父级 live 权限覆盖可优先于角色默认，因此 TOML read-only 不足以证明子角色的有效权限。必须从实际能够选择 fusion_planner 的 native 工具及可信运行信息证明只读、禁止提权/网络/外部副作用工具/再次派发后，才能 reserve/spawn。当前不能提供这样的证据。

官方依据：[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)、[Config reference](https://learn.chatgpt.com/docs/config-file/config-reference)。没有把离线测试、角色解析或 fresh host 注册说成模型执行通过。

下一步由父端在可访问的普通 Local 宿主确认真实角色选择 API、工具刷新及有效权限；需要刷新会话时由用户决定，不能保证新会话本身就满足门禁。**仅当门禁证据成立后**，再批准 gpt-6.1-sol / high、最多 1 次只读 smoke：只读 README、planner-host.md 和 fusion_planner.toml，返回接入验收计划、风险及建议测试；不测试、不构建、不写文件、不网络、不 Worker。目前调用数、Planner reservation 和 Worker dispatch 均为 0；候选模型尚不能当作已批准调用。

进展回传：用户已明确授权向来源任务 `01a118d8-7d00-75f5-b600-0c48ff8cd014` 发送诊断。此前发送被自动审批因缺少目标授权拒绝；取得授权后接口返回 `thread not found`，因此消息未送达。这是来源任务在本地消息接口中不可访问的问题；未重试其他目标。本轮最终结果由平台自动通知父端。


---

## 2026-10-11 真实调用准备检查（最新结果）

用户批准 gpt-6.1-sol / high 最多一次真实规划调用，前提是实际原生 role 选择及全部有效保护成立；允许官方会话级只读准备，但禁止额外主控模型、Worker、执行计划、源码修改、放宽全局权限或操作受禁主界面。本轮**未启动模型，额度 0/1**。保留全部前轮未提交修复。

### 成功

- 重读 AGENTS、规范技能与 Planner host 规则，并只读解析实际 saved defaults；Planner 仍 disabled，模型偏好没有自动修改。用户单次 smoke 授权没有被转换为持久设置变更。
- 现有官方 CLI 支持 `--sandbox read-only`；官方 JSON 协议亦提供会话级只读启动。使用同一本机官方 app-server、仅当前进程覆盖，禁用 agents/apps/hooks/web 和全部 14 个已配置插件、7 个显式 MCP server；不修改全局配置文件。
- `permissionProfile/list` 确认 `:read-only` 可选择；`thread/start` 创建 ephemeral 无模型诊断会话，返回实际会话 `sandbox={type:readOnly, networkAccess:false}`、approvalPolicy=never、model=gpt-6.1-sol、reasoningEffort=high。从未发送 turn/start，所有临时宿主均已退出，无持久用户聊天。
- 最终 config/read 确认所有已配置插件及显式 MCP 均禁用，apps default、apps/hooks、agents 关闭，禁止 login shell、web search。这里证明的是该诊断根会话的宿主政策和配置，不是 Planner 子角色的完整工具清单，更没有用模型承诺作为保护证明。见 `smoke-readonly-session.json`。
- 本轮所有 tracked 文件 SHA-256 与开始时一致，工作树状态完全一致；全局 config、项目/global selection 哈希一致。没有源代码修改、commit/push、应用重启、安装重试或全局安全改动。见 `smoke-final-check.json`。

### 失败 / 缺失能力

- 诊断根会话返回 `agentRole=null`。实际生成的官方 ClientRequest schema 没有原生 role roster/select/spawn 请求；thread/start 与 turn/start 也没有自定义角色字段。名为 externalAgentConfig 的方法是外部配置导入，不是 native agent role 派发。
- 当前委派 spawn schema 只有 fork_turns/message/model/reasoning_effort/task_name，没有角色或沙箱/工具 allowlist 参数。不能选择 fusion_planner，亦无法派发前查询所选子角色的有效工具面。
- 已有用户运行宿主的官方 daemon version 查询仍返回 control socket ENOENT。没有 bootstrap/start/restart daemon、开启远程控制、读取其他会话或绕过 IPC。
- 协议 ThreadStartResponse 明确声明 `disabledPluginIds` 仅保存列表，**尚不筛除 plugin capabilities**；不能拿这个列表当有效外部工具禁用证据。此轮用实际 config enabled=false 做根会话禁用，但没有子角色工具 inventory 证明。
- 准备过程中两次宿主在初始化前分别拒绝覆盖：invalid transport（禁用项仍需传输字段）、url is not supported for stdio（原 HTTP 配置与临时 stdio 字段合并冲突）。另一次启动虽返回只读，但引用式 CLI 键名未覆盖原条目，config/read 暴露禁用检查失败，未进行模型调用。最终使用原始合法键名并保持各 MCP 原传输类型的惰性禁用值，检查全部通过。这些都是零模型准备查询，均保留脱敏证据 `smoke-readonly-session-first.json`、`smoke-readonly-session-quoted-keys.json`、`smoke-readonly-session-transport-conflict.json`；未以失败配置派发。

### 未测及停止理由

真实 Planner 调用、原生角色回执、模型输出及 planner_complete 返回计划校验均**未测**，因为没有可行的原生 role 选择及所选子角色完整权限证据。未调用 planner_begin/reserve/complete，未填写虚假 host_capabilities、receipt 或 result；未产生 Worker。前轮已确认角色解析拒绝消失及 MCP 注册成功，未重复安装验证，也未将其视为模型执行通过。

[官方 Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)说明父 turn 的 live sandbox/approval 覆盖会重新应用于子角色；[官方 App-server](https://learn.chatgpt.com/docs/app-server)区分 thread 创建与 turn 执行。CLI 只读入口因此提供会话级准备路径，但不能凭此把普通根会话冒充原生 Planner。仓库 [codex-duo SKILL.md](../../plugins/fusion-minimal/skills/codex-duo/SKILL.md)明确要求：“Do not start a separate CLI model process”；用户本轮也禁止增加第二个主控模型，所以没有用 codex exec、根 turn 或让主控模型代为 spawn 绕过门禁。

最小可行下一步：把同一次已批准的 smoke 放到**已提供自定义角色选择接口**的普通 Local coordinator 宿主，并使用官方只读父会话方式、禁用继承外部工具；先取得选择 fusion_planner 及该子角色有效 sandbox/approval/network/tool surface 的可信证据。仅确认只读 session flag、新聊天或重装插件都不足以补齐缺失 API。当前任务环境无法执行这一步；需要宿主提供受支持接口或用户在允许的实际 Local 环境中开展，而不是再重复检查安装。现有一次模型调用额度尚未消耗，不需要用户重复批准同一模型/范围。
