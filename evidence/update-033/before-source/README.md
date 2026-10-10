# Fusion Minimal 0.3.2

插件内 `./mcp/launch.sh` 避免宿主直接解析裸 `python3`，从 PATH 或既有 Homebrew 路径选择 Python 3.11+。不安装运行时、不修改全局环境。新增空 PATH、含空格路径和无关工作目录的打包入口回归测试。安装、宿主调用与 UI 渲染的验证结果分别记录在 [0.3.2 报告](evidence/update-032/REPORT.md)。

以下保留先前版本说明。

# Fusion Minimal 0.3.1

修正便携 MCP 的启动命令为 `python3`，补充宿主命令路径规则校验和实际清单启动回归测试。此补丁沿用原插件身份、模型选择和部署目录；不启动模型。当前安装和原生宿主验收结果以 [0.3.1 更新报告](evidence/update-031/REPORT.md) 为准。

校验已安装状态时使用：`python3 -B tools/validate_static.py --installed --global-config-sha256 <本次修改前记录的配置哈希>`。默认模式仍用于初始禁用状态。SDK/子进程握手不等于桌面宿主加载成功。

以下是之前版本的历史记录，不代表当前安装状态。

# Fusion Minimal 0.3.0

> 安装状态更新：已通过官方 CLI 在本机安装并启用 0.3.0，安装缓存中的 MCP 启动及设置保存恢复通过；原生 Codex 设置页与会话面板仍待用户打开后核验。详见 [安装报告](evidence/install-001/REPORT.md)。以下候选版验收说明保留为安装前记录。

## 原生插件候选版本（0.3.0）

已新增本地 stdio MCP、原生结构化设置、对话入口与自包含 MCP App。它们与原网页面板共用模型目录、配置存储和任务快照；保存和生成仍不启动模型，不切换当前线程。

**当前状态：源码和无模型验证完成，尚未安装到 Codex。** 已通过 63 项 Python 测试、33 项静态检查、官方 MCP 客户端互通，以及测试宿主中的设置/面板双向保存恢复。测试宿主不是原生安装实测。

安装前请读 [具体安装步骤与权限范围](NATIVE-INSTALL.md)。交付包为 `fusion-minimal-0.3.0.zip`；原生证据在 `evidence/native/`。没有新增全局配置、Hooks 或实际模型任务。

复现：

```sh
python3 -B -m unittest discover -s tests -v
python3 -B tools/validate_static.py
# 仅重建 UI 或运行 SDK 互通测试时需要 Node 开发依赖：
npm ci --prefix native-build --ignore-scripts --no-audit --no-fund
node native-build/build.mjs
node native-build/test-client.mjs
# 可选测试宿主，只写临时状态：
python3 -B tools/native_harness.py
```

下面的 0.2.0 说明保留为独立网页入口的用法和历史验收记录；其“尚未注册/未包含 MCP”描述对应当时版本，不代表 0.3.0 源码内容。

## 模型选择面板（0.2.0）

启动独立本地面板：

```sh
cd /Users/kola/codex-fusion
python3 -B panel/server.py
```

打开 `http://127.0.0.1:8765`。可用 `--port 0` 让系统分配空闲端口，启动日志会显示地址。
按 Ctrl+C 停止服务。面板是普通本地网页，可在 Codex 浏览器侧栏打开；尚未注册为 MCP App、
插件面板或原生模型开关。无需安装额外 Python/Node 依赖（Python 3.11+）。

模型来自本机 `codex debug models --bundled` 的可见目录，推理强度逐模型校验；
这只能确认本机目录支持，不能证明账号额度、权限或实际推理路由。找不到内置 CLI 时可设置
`FUSION_CODEX_CLI` 指向已安装的 Codex 可执行文件。读取失败会禁用保存和生成，不会静默回退。
三个候选预设仅在完整组合受当前目录支持时出现。没有硬编码价格或宣称实际节省比例。

选择主控/执行模型及强度 → 保存配置 → 生成新交接包。三个动作的范围分别是：

- 草稿：仅留在当前页面，恢复已保存配置会舍弃草稿。
- 保存：原子写入本项目 `.fusion/selection.json`，不修改 `.codex/` 或全局配置，也不启动任务。
- 生成：把已保存组合和任务规范固定到 `.fusion/handoffs/<内容标识>/`。重复请求复用相同包。
  `task.json` 仍兼容原有 `fusion.py verify`；`handoff.json` 标明未启动、需批准且不作用于当前线程。
  `config/*.toml` 是待检查的候选配置，未安装，代理和 Hooks 默认关闭。

当前主线程的实际模型无法由此面板读取或切换。未来启动时须为新的主控任务显式选择交接包
请求的模型，并核实实际配置，再在授权范围内启动执行模型。本轮只验证面板与文件交接，不调用模型。
并发窗口更新发生冲突会提示恢复；配置损坏或模型从目录移除时，不自动覆盖，重新保存会先备份原文件。

CLI 也能消费同一份已保存配置：

```sh
python3 -B plugins/fusion-minimal/skills/fusion/scripts/fusion.py prepare --selection .fusion/selection.json --task plugins/fusion-minimal/skills/fusion/templates/task.json --out .fusion/handoffs
python3 -B -m unittest discover -s tests -v
```

HTTP 测试只绑定本机临时端口；受限沙箱若禁止 bind，需在允许回环端口的本地环境运行。
测试和截图在 `evidence/panel/`，历史证据保持原样。此版本插件源码与归档为 0.2.0；
0.1.0 归档作为历史记录保留。插件安装、命名 TOML 自动发现和实际模型调用均不包含在面板验证内。

本轮最终验收：44 项自动化测试、27 项静态检查与桌面/窄屏浏览器实测通过。
浏览器与 CLI 生成同一交接包，均保持未启动。详见 [验收报告](evidence/panel/REPORT.md)
和 [结构化证据](evidence/panel/acceptance.json)。

下面保留先前能力核查与迁移记录；其中“本次”指对应历史阶段。

## 独立维护目录

当前规范维护路径是 `/Users/kola/codex-fusion`。在这里修改源码、测试和文档。
原目录 `/Users/kola/Documents/Codex/2026-10-08/task/fusion-prototype` 保留为迁移前的
可恢复副本；它不会与新目录自动同步。不要在两个目录并行维护。

从任意工作目录运行下列无模型验证：

```sh
cd /Users/kola/codex-fusion
python3 -B tools/validate_static.py
python3 -B -m unittest discover -s tests -v
python3 -B plugins/fusion-minimal/skills/fusion/scripts/fusion.py verify --task evidence/migration/offline-demo/task.json --result evidence/migration/offline-demo/result.json --root evidence/migration/offline-demo
```

`tools/` 和测试通过自身位置解析项目根目录；市场清单的 source.path 保持相对路径。
验证脚本的全局配置只读哈希路径从当前用户 home 解析，不写全局配置。
`evidence/current/` 接收此后静态检查和原生探针的新输出。迁移报告和无模型测试日志在
`evidence/migration/`。原生探针这轮没有启动，先前初始化超时仍是历史限制。
其他已有 `evidence/` 文件是保留的历史记录，其中的原路径、命令和哈希未篡改。
此次迁移不把历史证据中的绝对路径当成当前可运行配置。

项目代理、插件仍禁用，Hooks 仍关闭。没有注册/安装插件、信任 Hooks、修改全局配置、
调用额外模型或发布。插件安装仍需另行批准；本次授权仅覆盖迁移和无模型验证。

本机能力核查、离线原型和用户批准的一次原生 Luna/high 试跑已完成。
Sol 主线程独立验收通过；没有使用第二次纠正轮次。

真实试跑证据在 `evidence/live-run-001/`：`task.json` 是简明任务，`dispatch.json`
记录原生工具接受 `gpt-6-luna/high` 和 `fork_turns=none`，`result.json` 是 worker 的
精简回传，`change.diff`、`tests.log` 和 `coordinator-tests.log` 是变更与独立测试证据，
`acceptance.json` 是最终验收。修改前两项测试失败，Luna 修改后两项通过，主线程重跑也通过。
只改动 fixture 的 `math_ops.py`；原型受保护文件和全局配置未被 worker 修改。

当前原生工具没有选择命名 TOML 代理的参数，所以本次使用显式模型/effort 参数进行验证。
不声称 `.codex/agents/fusion_worker.toml` 被自动发现。平台确认接受指定参数并完成子代理任务；
没有独立的逐请求 reroute、token 或计费遥测，不能据此量化成本节省。

| 核查项 | 本机证据与结论 |
| --- | --- |
| 桌面应用 | `/Applications/ChatGPT.app`，bundle ID `com.openai.codex`；版本 `26.1002.52244`，build `13536` |
| 内置 CLI | `0.162.0-alpha.2`，aarch64；当前 shell PATH 没有独立 `codex` 命令，检查使用绝对路径 |
| 主模型配置 | 用户全局配置为 `gpt-6.1-sol` / `high`；此次未修改，不能仅凭全局配置断言所有线程的运行时选择 |
| 插件 | 内置 CLI 的 `plugin list --json` 返回 13 个 installed/enabled 项；当前会话另外暴露远程插件 Skill 和工具。缓存目录本身不证明插件启用 |
| 原生子代理 | CLI `multi_agent` 为 stable/true；原生 spawn 工具已接受指定 Luna/high 并完成一次任务 |
| 独立模型配置 | 内置目录列出 Sol、Luna/high；显式模型/effort 试跑通过。自定义 TOML 静态通过，命名代理自动发现和独立运行时分配遥测未验证 |
| Hooks | CLI `hooks` 为 stable/true；本原型未打包 Hooks，项目配置关闭 Hooks |

13 项 CLI 插件清单：documents、pdf、spreadsheets、presentations、template-creator、
codex-app-tools、browser、unified-computer-use、chrome、computer-use、messages、
code-review、visualize。准确版本见 `evidence/installed-plugins.json`。
远程插件的 Skill/工具出现在本会话环境中，不把这 13 项称为全部账号插件。

原型以一个 Skill 控制工作流：Sol 主线程写简明 task JSON、限定文件和验收条件；
批准后由一个 `fusion_worker`（候选 `gpt-6-luna/high`）执行；同一 Sol 主线程验收。
结果只回传状态、短摘要、diff 和日志引用、测试退出码、阻塞点。完整日志保存在本地。
不引入额外规划模型、MCP 或 Hooks。这里的低成本角色依据官方定位；尚未测量实际成本或节省比例。

插件与代理配置分别交付。`.codex/agents/` 不是插件可移植组件，安装插件不会自动安装代理。
根目录和兼容清单身份同步；现代客户端使用根清单的 OpenAI 扩展，旧客户端可使用兼容清单。
根目录 `.agents/plugins/marketplace.json` 仅为此独立目录准备本地市场条目；尚未注册或安装。
`.codex/config.toml` 中插件与代理均 disabled，候选配置不会主动发起模型任务。

在本目录复现无模型检查（Python 3.11+；本机使用 Homebrew Python）：

```sh
python3 -B tools/validate_static.py
python3 -B -m unittest discover -s tests -v
python3 -B plugins/fusion-minimal/skills/fusion/scripts/fusion.py verify --task evidence/offline-demo/task.json --result evidence/offline-demo/result.json --root evidence/offline-demo
```

生成新离线示例时选一个不存在的目录：

```sh
python3 -B plugins/fusion-minimal/skills/fusion/scripts/fusion.py demo --out /tmp/fusion-new-demo
```

示例先运行失败测试，再确定性修改加法函数，最后执行两项通过测试。没有调用模型。
验收脚本只检查交接契约、文件范围和证据一致性，不执行 result 中的命令。
哈希不能证明来源，Sol 仍须检查 diff、确认实际文件变化并独立重跑检查。
首次实现发现 Python 对同秒、同大小改动复用 bytecode 的问题；示例命令加 `-B` 后修复并通过。

检查结果：27 项静态检查通过，15 项协议测试通过；离线示例修改前两项失败，修改后两项通过。
全局配置 SHA-256 前后相同。静态检查为本原型结构校验，不冒充完整 Agent Plugins schema 验证。

原生协议探针 `tools/native_probe.py` 只请求初始化和只读接口；不会创建线程或模型 turn。
初次启动因只读 `~/.codex` 无法初始化 SQLite；使用官方 `sqlite_home` 运行时覆盖后，
状态写入移至本目录，未修改全局配置。有效配置的 `initialize` 在 12 秒内未返回，
所以 `config/read` 和 `plugin/read` 未执行，插件原生加载未验证。
未知配置键被本机 `--strict-config` 拒绝，见 `evidence/native-probe.json`。
后续应在受支持的本地宿主完成发现验证，不能把此超时推断为产品不支持。

最新官方依据（2026-10-08 核对）：

- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)：项目/个人自定义代理 TOML、独立 model/effort 和代理默认值受支持。
- [Package your plugin](https://developers.openai.com/plugins/build/plugins)：Skill 插件、根清单与兼容清单受支持；含 Hooks 的插件限手动安装且需审阅信任。
- [Hooks](https://learn.chatgpt.com/docs/hooks)：安装或启用插件不会自动信任 Hooks。
- [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference)：`sqlite_home` 指定本地状态目录。
- [App Server](https://learn.chatgpt.com/docs/app-server)：由已安装 CLI 生成的协议 schema 与该版本对应。

未执行：命名 TOML 自动发现验证、插件安装/市场注册、项目信任、全局配置更改、Hooks 安装或信任、
Astra、升级、重启、推送或发布。没有读取用户凭证、私人聊天记录或无关项目。

用户回复“批准”覆盖的单任务验证已经执行并验收。只临时把本目录 `agents.enabled`
设为 true，验收后恢复原文件；插件始终禁用，Hooks 始终关闭。
继续验证命名代理发现或其他真实任务时，明确后续范围；需要本地安装 Skill 时单独批准
注册/安装此插件和项目信任。如宿主要求重启，按用户要求先报告并停下。
本次未申请或执行全局更改、安装或 Hooks 信任。

主要交付文件见 `FILES.txt`；可移植插件包为 `fusion-minimal-0.1.0.zip`，仅包含插件目录，
代理和项目配置仍在源码目录内单独交付。
