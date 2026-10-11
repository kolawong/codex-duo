# 插件详情图标引用修复 — 插件 0.9.8

用户反馈 0.9.7 后详情页大图标与「立即试用」示例仍为灰色回形针。本轮按授权只修正插件展示元数据；没有修改或重新打包应用图标，没有额外模型、应用 UI 操作、后台服务启动或私有宿主代码访问。

**已确认的配置根因：两份 manifest 的 `logo` / `composerIcon` 都写为 `assets/tandem.png`，缺少宿主要求的 `./` 前缀。** 官方公开加载器把这类引用忽略并返回空值，文件存在及安装 hash 相同也无法让它成为有效展示资源。上轮核验没有覆盖这项解析规则，也没有证明页面展示成功。

## 根因与证据

1. 当前根 manifest 使用 `extensions.com.openai.interface`；兼容 manifest 使用 `interface`。两者 0.9.7 都有同样错误路径。官方文档规定扩展存在时以扩展为准，不与兼容文件合并，因此两处均修正，防止回退宿主继续读取错误引用。
2. [官方打包文档](https://developers.openai.com/plugins/build/plugins) 的路径规则要求资源相对插件根目录并以 `./` 开头。`logo` 和 `composerIcon` 是受支持字段，无需换成其他字段名。
3. [官方公开加载器 manifest.rs](https://github.com/openai/codex/blob/main/codex-rs/core-plugins/src/manifest.rs) 的 `resolve_interface_asset_path` 调用 `resolve_manifest_path`；后者 `strip_prefix("./")` 失败即返回 None，并记录路径被忽略。这确认了缺少前缀的具体解析错误。该代码来自公开仓库，没有访问本机私有宿主实现。
4. 本机官方 CLI `0.162.0-alpha.17.2` 的 `app-server generate-json-schema --experimental` 输出 `PluginReadResponse` / `PluginInstalledResponse` 中的 `interface.logo` / `interface.composerIcon`，描述为安装包解析出的本地图标路径。schema 保存于 `protocol-schema/`；生成 schema 没有启动 server。
5. 官方 `plugin list --json` 和 `plugin marketplace list --json` 确认：只有一条名为 codex-duo 的安装注册，身份 `codex-duo@codex-duo-local`，marketplace 根 `/Users/kola/codex-duo`，源 `/Users/kola/codex-duo/plugins/codex-duo`。更新前版本 0.9.7，更新后 0.9.8，已安装并启用。没有证据显示读到了另一份注册。

输入截图 Library ID 为 `libfile_6518c62368108191afe90732bfb9c3fb`；两处回形针由主对话实际查看并随委派提供。本消费端没有重新下载或操作宿主 UI，不声称本机再次查看了截图。空图标引用与回形针 fallback 相符，但没有直接观察该页面 renderer 的 fallback 分支，也没有将问题归因于未经证实的缓存。

## 最小修改与官方安装

- `plugins/codex-duo/plugin.json`：版本 0.9.8，两个路径改为 `./assets/tandem.png`。
- `plugins/codex-duo/.codex-plugin/plugin.json`：同样修改，保持展示元数据一致。
- `plugins/codex-duo/mcp/server.py`：只同步 serverInfo 版本为 0.9.8，PNG 图标内容及业务代码不变。
- `tests/test_native.py`：同步版本断言，核验两种 manifest 均使用 `./` 引用、相对插件根目录解析、仍在包内且为真实 PNG；保留 MCP icon 的内容/MIME 检查。
- `README.md`、`NATIVE-INSTALL.md`：记录插件修复、应用保持原版本、重载及页面未测边界。

没有新增源码文件或删除源码文件。精确本轮增量见 `increment.diff`、`changed-files.json`，基线为任务开始的工作区字节，不以 Git HEAD 抹除既有修改。

官方更新命令：

```sh
/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex plugin add codex-duo@codex-duo-local --json
```

成功返回插件 **0.9.8**，安装目录 `/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.9.8`。39 个安装文件的集合与 SHA-256 全部与源码一致。两份实际安装 manifest 的两个图标路径均为 `./assets/tandem.png`，包内文件真实存在，为 1024×1024 PNG，SHA-256 保持 `af9920bc6a2dedb833748c8dd0339414e7f60314aef1247c90d1a187356778f4`。

这是有效配置、官方安装注册及实际安装文件核验；**没有得到运行时 `plugin/read` 返回的解析路径，不等于真实插件页面已显示双环。**

## 验证结果与边界

| 检查 | 结果 | 记录 |
| --- | --- | --- |
| `PATH=/opt/homebrew/opt/python@3.14/libexec/bin:/opt/homebrew/bin:/usr/bin:/bin python3 -B -m unittest discover -s tests -v` | 224 / 224 通过，52.909 秒 | `python-tests.log` |
| 首次完整 Python 测试，错误使用系统 3.9 | 193 项发现，8 个导入错误，缺少 tomllib；失败记录保留，随后按上行重跑 | `python-tests-system39.log` |
| `node native-build/test-panel.mjs` | MCP / HTTP 设置控制器与 return 流程通过 | `panel-tests.log` |
| `node native-build/test-client.mjs` | 官方 MCP SDK、隔离状态、跨项目和预算回归通过，model_calls=0 | `client-tests.log` |
| 官方 CLI `plugin list` / `marketplace list` | 来源、唯一身份、安装启用和版本确认 | `all-installed-before.json`、`all-installed-after.json`、`marketplaces.json` |
| `python3 -B evidence/plugin-display-icon-fix/audit.py` | 配置、39 个安装文件、保护清单通过 | `audit.log`、`installation-and-resource-validation.json` |
| `codesign --verify --deep --strict --verbose=2` | 原应用签名仍有效 | `unchanged-app-signature.log` |

尝试通过官方 `app-server proxy` 连接已有服务器，仅准备 initialize 与只读插件请求。默认 control socket 不存在，连接在 initialize 返回前结束，未发送 `plugin/installed` / `plugin/list` / `plugin/read`。记录见 `metadata-before.json`、`proxy-before.stderr`、`read_metadata.py`。遵守不启动服务器的限制，没有创建 daemon/server、修改监听或安全设置、寻找私有 socket 或绕过连接限制。CLI 的只读注册信息已成功获取，但它的 JSON 不包含运行时 interface 路径。

未重跑 Swift 或重建 Web / 应用：本轮未修改 Swift、共享面板、Web bundle、原 PNG / SVG / ICNS 或应用打包文件，保护清单确认实际 `.app` 和资产字节均未变。原应用仍 **0.9.7 / build 16**。

真实页面渲染、详情大图标及「立即试用」图标均未操作验证；没有证据证明后者是宿主固定不可配置，也不声称它已修复显示。用户可正常重新加载插件或重启宿主后查看这两处；如仍为回形针，后续依据新截图及可用的受支持 metadata 接口继续判断，不盲目重复重打包。

## 保护结果

1718 个受保护文件字节 hash 全部保持，包括旧 evidence、任务、预算、历史、项目/全局偏好、角色配置、AGENTS.md、Git HEAD/index、原应用与图标资源。本轮唯一允许的六个源码文件发生变化。没有清理旧缓存或历史。

项目偏好 SHA-256 `fdff92fa638e5494046b4adab310441dd665b7aa04caba229cefab2589897cf7`，全局偏好 SHA-256 `1900c32e3405535a2acc6cb11f88ac548cf57e70ab15c33e8bccf77f7a715a7c`。现有 Astra Planner、Worker、项目覆盖及 return 流程不变。真实额外模型 **0**，没有向其他聊天发送消息，没有 commit / push / pull / reset / 新分支。

交付状态：配置修复及官方更新完成；运行时解析路径受现有代理端点缺失所限，真实页面仍待用户重载后截图确认。
