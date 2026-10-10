# 原生插件候选版验收：0.3.0

2026-10-08；规范项目目录 `/Users/kola/codex-fusion`。

## 已实现

本地 stdio MCP 提供 7 个工具：打开面板、读取状态、保存配置、准备交接、读取执行适配说明，以及原生设置读取/更新。只有现有配置存储，没有新增第二套模型状态。

原生设置使用 `openai/settings` 能力，设置页面板按钮引用同一个 opener；对话面板使用 `thread` 入口和 MCP Apps HTML 资源。官方浏览器 SDK 固定为 2.0.3，构建依赖锁在 `native-build/package-lock.json`。HTML 内嵌资源，网络域白名单为空。运行 MCP 只需要本机 Python，不启动 HTTP 服务。

任务配置保存到 `.fusion/selection.json`；交接仍沿用现有契约和证据验收脚本。执行适配接口校验固定 ID、文件内容和当前模型目录，只返回新主控任务、worker 的候选配置及批准要求，不创建任务或调用模型。

## 已验证

- 本机桌面版本仍为 26.1002.52244（13536），内置 CLI 0.162.0-alpha.2。
- 读取安装包相关资源代码，确认结构化设置解析器、thread 入口、MCP App 资源和显示模式处理存在。文件名、代码片段与哈希见 `host-code.json`；这只是静态宿主证据。
- 63 项 Python 测试、33 项静态检查通过。覆盖设置部分更新、合法模型/强度、共享配置、并发锁、损坏配置、无效输入、路径与符号链接拒绝、超大请求、stdio 协议错误、新任务快照和无执行边界。
- 官方 `@modelcontextprotocol/client 2.3.1` 成功连接真实 Python stdio 进程，验证工具 schema、资源、设置、交接与错误，见 `sdk-client.json`。
- 在本机浏览器中的**开发测试宿主**完成 SDK 握手和首屏渲染，面板保存 → 设置读取、设置修改 → 面板恢复双向通过；重新加载恢复保存值，重复生成复用交接包。截图 `test-host.jpg` 明确标为模拟宿主。
- UI 初次构建发现 JavaScript 替换字符串中的 `$` 被 HTML 组装解释，已改为回调拼接，并在构建脚本增加提取后语法校验。修复后的浏览器记录没有新增警告/错误。

测试只使用临时目录；没有更改正式 `.fusion/` 的候选配置、全局模型配置或 `.codex/` 插件禁用状态。没有启动额外模型任务。

## 待安装实测

尚未注册本地市场、安装插件、连接宿主 MCP 或验证原生设置页的真实渲染。也没有验证 thread 入口在当前账号中的显示位置、宿主是否尊重 fullscreen 偏好、以及 `${PLUGIN_ROOT}` 在安装后的展开。安装验证步骤与明确权限范围见 `../../NATIVE-INSTALL.md`。

本机代码仍包含旧 `settings` 入口解析；最新官方规范改用结构化设置，本包采用新规范并保留 thread 入口。不能由静态代码推断所有账号的开关已启用。如果原生设置不可见，安装后可验证 thread 入口或 opener 作为最接近的受支持路径。

官方依据：[Structured Settings / Entrypoints](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md)、[MCP Apps](https://github.com/modelcontextprotocol/ext-apps)、[插件打包](https://developers.openai.com/plugins/build/plugins)。网络工具成功读取文档；直接下载 GitHub 原始文件遇到网络错误，未作为版本锁定来源。实现 API 另对照已下载的固定 SDK 类型检查。

下一步只需批准一次本机插件安装与入口验证；不包括模型运行、Hooks、重启或发布。安装的本地 Python 进程按用户权限运行，代码限制不等同于 OS 沙箱。
