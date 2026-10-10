# Fusion Minimal 0.3.3 修复与宿主验证

## 结论

启动器修复、测试和官方本地安装完成。**实际会话工具加载仍未通过，原生 UI 渲染未验证。** 不将独立 MCP 握手等同于当前桌面会话加载。

## 原始证据与归因边界

- 本会话 `01a11bc7-6e7b-7662-9d35-2f6f4f0800f9` 的 Skill 0.3.1 可见，Fusion 工具目录为空。
- 实际 `list_mcp_resources(server="fusion")` 返回 `MCP startup failed: exec-server rejected request (-32603): No such file or directory (os error 2)`。
- 官方 CLI `mcp get fusion --json` 确认原版变量已展开、工作目录和脚本存在；原命令为裸 `python3`。
- 空 PATH 环境下裸 `python3` 可复现 ENOENT。此为命令解析依赖的复现，**没有读取到 exec-server 的实际 PATH，不能将其确认为唯一根因**。

## 修改

- 清单改为插件内 `./mcp/launch.sh`，仍符合便携相对命令规则；不把绝对 Python 路径放回清单。
- `/bin/sh` 启动器按自身位置定位 server.py，无需外部 dirname，也不依赖 PLUGIN_ROOT 环境值。
- 选择 PATH 或现有 Homebrew / 系统路径中的 Python 3.11+；缺少运行时明确报错，不安装依赖。
- 0.3.2 启动回归通过后，进一步复现空 PATH 下 settings_read 的 catalog_unavailable：内置 CLI shell 包装器需要系统命令。0.3.3 仅对服务及子进程追加标准系统 PATH，并扩展完整设置读取回归。
- 保持插件身份、项目根目录、设置和工具业务实现不变。启动器可执行位为 0755。

## 验证

| 项目 | 实际结果 |
|---|---|
| 打包启动回归 | 7 项通过；包括空 PATH、含空格路径、无关 cwd、错误 PLUGIN_ROOT、实际设置读取和非可执行入口拒绝 |
| 原生协议测试 | 19 项通过（0.3.2 阶段；0.3.3 仅进一步修正启动器 PATH 和版本号） |
| 静态检查 | 0.3.3 的 36 项通过 |
| 官方安装 | `plugin add fusion-minimal@fusion-local --json` 返回 0.3.3 安装成功 |
| 安装缓存 | 26 文件与源码完全一致 |
| 官方解析 | command 为安装缓存中的绝对 launch.sh，cwd 和 PLUGIN_ROOT 均指向 0.3.3 |
| 安装后独立 stdio | 空 PATH、无关 cwd 下返回全部 7 工具；settings_read、open、resources/read 成功 |
| 面板资源 | `ui://fusion-minimal/model-desk-v3`，`text/html;profile=mcp-app`，622897 字节 |
| 实际会话 | 安装 0.3.3 后工具目录仍为 0；资源请求仍报原 exec-server ENOENT |
| UI 渲染 | 未验证；未启动独立网页或测试宿主冒充原生面板 |

7 工具：`fusion.open`、`fusion.state`、`fusion.save`、`fusion.prepare`、`fusion.execution_plan`、`fusion.settings_read`、`fusion.settings_update`。这份列表来自安装后独立服务，不代表当前模型工具目录可调用。

## 宿主阻塞与最小下一步

本机官方 app-server schema 声明了 `config/mcpServer/reload`、`mcpServerStatus/list`、`mcpServer/tool/call` 和 `mcpServer/resource/read`，但当前工具目录未提供刷新方法。官方 `app-server daemon version` 无法连接默认控制通道 `/Users/kola/.codex/app-server-control/app-server-control.sock`，返回 ENOENT。没有猜测其他 socket、附着未授权进程、创建新模型任务或绕过 UI 限制。

现有证据无法确认当前会话使用的是旧声明还是新声明，也无法证明刷新一定会消除错误。下一步是**用户完全退出并重新打开 Codex，回到同一任务发送“验证 Fusion 加载”**，让宿主重新初始化插件；不再重装、不另开模型工作者。若仍失败，以该次启动日志和实际工具调用结果继续定位宿主，不能宣称本插件已完成原生验收。

官方说明要求修改本地插件后重新启动桌面应用以加载更新：https://developers.openai.com/plugins/build/plugins 。本轮没有自行重启应用。

## 文件与不变量

- `package-tests.log`、`static-validation.log`：测试和静态检查。
- `install.json`、`resolved-mcp.json`：官方安装及展开后的启动声明。
- `installed-readonly.json`：独立只读验证；明确标记不是桌面线程工具调用。
- `actual-session.json`：本会话真实工具目录和资源调用失败。
- `change.diff`：从 0.3.1 到当前修改；修改前备份保存在 update-032/before-source，0.3.2 中间备份在本目录 before-source。

保存的 `.fusion/selection.json` 与全局配置哈希均未变化。未信任 Hooks、修改安全设置、启动模型、启动 8765 网页、创建子任务、读凭证或修改无关插件。此前自动审批拒绝未造成写入；用户在本任务直接批准后才实施修改。

## 用户请求重新验证后的结果

当前会话仍无 Fusion 工具，resources/list 和 resources/templates/list 均返回 exec-server ENOENT。本机 CLI 确认 0.3.3 已启用，launch.sh 存在且可执行，cwd 存在。新的桌面日志记录该线程的 Fusion 在 2026-10-08 22:09:17 至 22:09:18（Asia/Taipei）从 starting 转为 failed，hostId=durable。这表明新一轮启动仍失败，不能继续仅归因于旧连接缓存；本机 CLI 可运行与 durable 会话启动成功是不同证据。具体缺失路径仍未暴露。

详见 session-recheck.json。无需再次盲目重装或重启；后续需定位该会话宿主传给 exec-server 的实际 command/cwd 及其可见文件系统，而不是继续更改已通过本机验证的启动器。此轮未启动模型或网页、未修改插件或全局配置。

## 有界宿主诊断

后续只读诊断已结束。官方文档确认云端协调连接本机时，本地 MCP 服务与传输可能不可用；本会话日志为 durable。实际 spawn 参数 / 文件系统映射未暴露，不能断言全局不支持或插件代码故障。详见 [HOST-BOUNDARY.md](HOST-BOUNDARY.md) 和 host-boundary.json。停止重装 / 重启，下一步仅建议用户手动普通 Local 会话作一次对照，未自动创建任务。
