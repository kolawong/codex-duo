> 更新：本清单中的市场注册、插件安装及项目启用已在用户批准后完成。原生 UI 验证尚未完成，详情见 [安装报告](evidence/install-001/REPORT.md)。下面保留原审批范围和步骤。

# Fusion Minimal 0.3.0：待批准的本机安装

本包已经实现原生设置协议和 MCP App，**尚未安装或连接到 Codex**。本轮没有新增权限、修改全局配置、信任 Hooks 或启动额外模型。

## 已实现与证据

- `openai/settings` 能力指定 `fusion.settings_read` / `fusion.settings_update`。原生设置用“模型 / 强度”的有效组合枚举，避免宿主不支持联动字段时出现无效组合；设置页还有“打开模型面板”工具按钮。
- `fusion.open` 接受 `{}`，关联 `ui://fusion-minimal/model-desk-v3`，声明 `thread` 入口。资源 MIME 为 `text/html;profile=mcp-app`，支持并偏好 fullscreen；桌面对话中应对应内容侧栏，但位置需安装后实测。
- HTML 包含锁定版本的官方 MCP Apps SDK 2.0.3，初始渲染使用 opener 结果，通过宿主桥调用工具，无 CDN 或运行期下载。设置和界面复用同一服务、模型目录和 `.fusion/selection.json`。
- `fusion.prepare` 保存不可变任务和模型快照；`fusion.execution_plan` 只提供新主控任务和 worker 参数、验收要求。它不调用模型、不发送消息、不切换已经运行的主线程。
- 本机 `26.1002.52244 (13536)` 的打包代码包含结构化设置解析、设置组件、MCP App 和显示模式处理，见 `evidence/native/host-code.json`。代码存在不等于账号已启用或本插件已注册。

最新官方协议采用 Structured Settings。当前本机解析器另外仍接受旧 `type:"settings"` 元数据，但本包不依赖该旧入口。原生设置能力若未被宿主显示，受支持的候选替代入口是 `thread` MCP App 或调用 opener；同样必须安装后核实，不把原独立网页当作原生集成。

依据：[OpenAI Extensions](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md#structured-settings)、[MCP Apps SDK 2.0.3](https://www.npmjs.com/package/@modelcontextprotocol/ext-apps/v/2.0.3)、[官方插件打包说明](https://developers.openai.com/plugins/build/plugins)。本地 stdio 服务协商 MCP 2025-11-25，使用该版本允许的 `capabilities.experimental["openai/settings"]`；不声称实现 2026-07-28 的完整新协议。

## 最小安装步骤（尚未执行）

1. 用户批准下面的具体范围。
2. 用本机 CLI 注册现有本地市场：

   ```sh
   /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex plugin marketplace add /Users/kola/codex-fusion --json
   ```

3. 在 Codex 插件目录选择 `fusion-local` → `Fusion Minimal` → 安装。本机 CLI 也有 `plugin add fusion-minimal@fusion-local --json`，但官方文档建议用桌面应用安装和测试；优先宿主支持流程。
4. 项目 `.codex/config.toml` 目前显式禁用此插件。如需要，只启用 `fusion-minimal@fusion-local` 这一项；保持 `agents.enabled=false` 和 Hooks 关闭。不要修改全局模型选择、默认权限或其他插件。
5. 宿主启动本地 `stdio` MCP 进程。确认工具发现、原生设置页、“打开模型面板”按钮及对话入口；保存/恢复时只使用候选配置并还原原值。检查视图真正渲染，再记录为“已安装实测”。

如果安装流程要求应用重启、新任务、额外信任或范围更广的权限，先报告并停下，不自行执行。注册和安装可能写入 Codex 的插件市场记录、插件缓存和安装状态；这些属于本次待审批的安装动作，当前未写入。

## 访问范围与风险

- 启动命令：`/opt/homebrew/bin/python3 -B ${PLUGIN_ROOT}/mcp/server.py --project-root /Users/kola/codex-fusion`。此包针对当前 Mac；搬家需审查部署路径。运行不依赖 Node 或联网下载。
- 读取：插件自身文件、项目 `.fusion/` 数据，以及内置 CLI 的模型目录/版本。工具参数没有任意路径或任意命令接口，不读取凭证、聊天记录或无关项目。
- 写入：项目 `.fusion/selection.json`、损坏配置备份、锁文件及 `.fusion/handoffs/`。设置页的局部更新由服务合并，跨进程锁防止并发丢失另一角色；同一字段以最后一次有效更新为准。面板继续使用 revision 冲突保护。
- MCP 本身只走父子进程 stdio，不监听端口。MCP App 资源 CSP 的网络、资源、子框架域均为空；无 OAuth、Hooks、额外连接器或宿主文件访问能力。
- Python MCP 进程仍是本机用户进程；上述限制由当前代码实施，**不是操作系统强制沙箱**。安装相当于信任这份本地代码。保持宿主默认工具审批，不设置全局自动批准。
- 测试宿主 `tools/native_harness.py` 仅为开发测试，绑定 127.0.0.1，使用临时数据；不随插件启动，不构成 Codex 原生宿主实测。

## 请确认的具体一步

批准“在本机注册并安装 Fusion Minimal 0.3.0，启动其本地 stdio MCP，必要时仅启用本项目这一插件，验证原生设置页和对话面板”。该批准包括插件注册/缓存/安装状态写入及项目插件开关；不包括全局模型设置、Hooks、重启、发布或真实双模型任务。
