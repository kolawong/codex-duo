# 0.9.4 原生设置头部布局修复

日期：2026-10-11。项目 `/Users/kola/codex-duo`，原 `main`。接续用户批准的本机代码修改、离线测试、构建签名与官方更新；保留全部既有未提交修复，无 reset/pull/新分支/commit/push，无额外 Planner、Worker 或验收模型。

## 截图与根因边界

原截图 **已实际查看**。使用 Library 当前技能和 `prepare_materialize`，通过受支持助手下载到本机 `input/截屏2026-10-11 17.52.30.png`，核实 PNG 可读（846×1790、271268 bytes），并通过 `view_image` 检查。Library ID：`libfile_bd0ea2d711488191926c034995da0d5a`。没有把父端云路径当作本机路径，也没有猜测 URL。

源码确认：截图对应原生浮动设置面板。头部的两个右侧动作是 **刷新**（arrow.clockwise）和 **在独立窗口中打开**（macwindow），不是刷新与关闭。浮动面板为 borderless，自身没有右上系统关闭按钮；独立设置窗口的系统关闭控件在左侧，头部已为它预留空间。Web 头部只含刷新按钮，本轮不改其设置布局。

**不能声称已完全定位宿主中的具体触发条件。** 对原完整头部进行 400pt 离屏渲染时，两个按钮实测各 26×26pt、水平间隔 9pt，未复现用户截图中的视觉叠加。`before-header.png`、`reproduction.log` 保存了这个反证，不能把“普通布局必然挤压”当作已证实根因。

源码可确认的布局/绘制薄弱点是：静止图标也一直使用暂停的 TimelineView；26pt 限定仅位于 label 内部，没有在 Button 外层固定占位；头部品牌、badge 和动作位于同一个横排，缺少长文案/窄宽度的独立动作区保护。本轮针对这些点做保守加固。是否完全消除用户桌面中的具体叠加，仍需用户重开新构建后视觉验收，本轮没有访问真实 UI。

## 具体修改

- `macos/Sources/CodexDuoMenu/Components.swift`：IconButton 在 Button 外层明确固定为 26×26pt并 fixedSize；静止图标直接使用 Image，仅忙碌刷新使用 TimelineView 旋转。保留 plain 按钮样式、hover、help、accessibility label 和原动作。共享图标组件的其他调用保持原功能，仅得到相同的稳定尺寸/静态绘制。
- 新增 `macos/Sources/CodexDuoMenu/SettingsHeader.swift`：抽出原头部；刷新与独立窗口动作区固定尺寸、9pt间隔，左侧品牌/badge 通过 ViewThatFits 在不足时排成两行。普通头部仍为 50pt，长文案离屏例为 73pt；独立窗口仍预留左侧 88pt。两个动作使用明确路由，忙碌只阻止刷新，独立窗口中不显示/路由重复打开动作。
- `SettingsView.swift`：接入上述头部，status 文案/tone、刷新调用 `store.refresh()`、独立窗口调用 `StartupDelegate.presentSettings()` 保留；设置、完成模式和其余面板内容未改。
- 新增 `macos/Tests/CodexDuoMenuTests/HeaderLayoutTests.swift`：实际 SwiftUI 视图的离屏 bitmap 回归，覆盖 320/400/520pt、短/长 badge、忙碌旋转、独立窗口左侧预留，以及刷新/开窗两个模拟回调独立路由。
- 更新版本元数据到 **0.9.4**、macOS **build 13**：两个 plugin manifest、MCP server、native bridge、native 版本断言和 build.sh；按现有入口重建 `ui/model-desk.html`。README、macos README、NATIVE-INSTALL 更新版本、重开步骤及未测边界。

本轮已有文件增量 12 项，加 2 个新 Swift 文件，共 **14 个源码/文档文件**，精确列表和前后 SHA-256 见 `source-changes.json`。`source-before.tar.gz`、`task-increment.patch`、`git-status-before.txt`/`after.txt` 与 `git-diff-before.patch` 区分既有脏工作区和本轮修改，不把旧修复算作本轮新增。

## 离屏验证与命令结果

最终检查均成功：

| 命令/检查 | 结果 | 证据 |
|---|---|---|
| `python3 -B -m unittest discover -s tests -v`（已有 Homebrew Python 3.14 PATH） | **226 tests / OK**，58.123s | `python-tests.log` |
| `swift test --package-path macos --cache-path macos/.build/cache --manifest-cache local` | **27 tests / 0 failures**，含新增 4 项 | `swift-tests.log` |
| 同命令 `--filter HeaderLayoutTests` | **4 tests / 0 failures** | `header-tests.log` |
| `node native-build/test-panel.mjs` | 两种传输的 VM DOM 控制器回归通过 | `panel-tests.log` |
| `node native-build/build.mjs` | self-contained MCP App 重建通过 | `web-build.log` |
| `bash macos/build.sh` | release 0.9.4/build13 构建、ad-hoc 签名完成 | `macos-build.log` |
| `codesign --verify --deep --strict --verbose=2 'macos/dist/Codex Duo.app'` | valid on disk / satisfies Designated Requirement | `codesign.log` |
| 官方 `codex plugin add codex-duo@codex-duo-local --json` | **0.9.4**，正常官方缓存路径 | `plugin-update.json` |
| `tools/validate_static.py --installed --global-config-sha256 <本轮开始真实配置哈希>` | **36 checks / passed** | `static-validation.json`，没有覆盖旧 evidence |
| 安装缓存 MCP 进程内 initialize | runtime/serverInfo **0.9.4** | `installed-initialize.json` |
| `git diff --check` | 通过 | 本轮命令记录 |

Swift 测试/构建使用项目内 ModuleCache，按已批准外层执行权限运行 SwiftPM 自带沙箱，没有禁用沙箱或改变安全设置。Library 助手使用现有 Python 3.14；系统 Python 3.9 的类型标注不兼容在下载之前已发现并更正，没有原图路径猜测或绕过权限。

头部测试渲染自己的 NSHostingView，cacheDisplay 只读取测试拥有的视图像素，没有屏幕捕获、显示窗口、应用启动或 ComputerUse。实际头部图像每个宽度/文案组合均在刷新与开窗两个槽位分别产生可见像素，9pt分隔区可见像素数 **0**；忙碌旋转也不侵入分隔区。长文案移到左侧第二行，未覆盖右侧图标。动作测试调用实际头部路由的模拟闭包：busy=[false,true,false] 时刷新 2 次、开窗 3 次，没有调用真实开窗函数或真实点击。

离屏 accessibility 不提供可用宿主按钮节点，未把它升级为真实 UI 操作或申请权限；最终采用像素断言与路由模拟。**真实 Button hit testing、宿主装饰、窗口重开和点击仍未测。**

离屏图片已实际查看：`after-400-saved.png`、`after-320-long.png` 等六张结果图。普通宽度预览通过 Library 当前技能合规保存，并应用返回的身份/xattrs，结果见 `library-preview.json`：

**离屏预览 Library ID：`libfile_2df4f38cbb3c8191a93a3e144dacbe09`**，名称 `after-400-saved.png`。这是测试视图的离屏渲染，不是用户桌面实测截图，也没有覆盖原截图。

## 安装、偏好及历史保护

官方插件缓存 `/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.9.4` 的 **39 个文件**与源码逐个 SHA-256 相同，缓存没有额外未核验文件。构建应用的 **11 个服务脚本 + bridge 共 12 个文件**与源一致，Info.plist 为 0.9.4/build13；可执行文件哈希记录在 `cache-hashes.json`。没有直接修改缓存。菜单程序是构建产物，未打开或替换运行中的旧进程。

**本轮开始的 405 个受保护文件前后哈希全一致**，包括实际项目/全局设置、任务/结果/预算、AGENTS、Git HEAD/index 和配置。前轮清单中的 **171 个旧 evidence 文件**也完整保留。见 `protected-before.json`、`protected-after.json`、`unchanged-check.json`。

用户最新全局 revision 为 **60433cd6accc04925d1a3ec01a6eab75e460e6d5c4a50e13addacb325e2a785c**，在本轮开始时已经不同于上一个任务的全局快照，本轮前后完全不变。没有将旧报告中的偏好恢复过来。项目 revision 仍为 **4ff4fef07b8fff93eb0a532f1a8b82401601a000405d99ccfddfe9d082909980**。安装包只读复核见 `installed-defaults.json`、`installed-global-state.json`：全局保留 Astra/xhigh Planner、6.1 Sol/high Worker、manual_review；本项目旧覆盖仍为 return / Planner disabled / 6.1 Sol high。没有改主控、完成模式或任何保存选择。

## 用户查看步骤与剩余边界

用户自行退出已经运行的旧 Codex Duo 菜单程序，然后打开本次构建 **`/Users/kola/codex-duo/macos/dist/Codex Duo.app`**。如果另一个安装位置仍为旧产物，需要用户自行替换为本次构建；仅更新官方插件缓存不会替换运行中的菜单程序。重新点击菜单图标查看设置：右侧应分别是刷新和「在独立窗口中打开」。不需要改变任何模型、全局设置或项目覆盖。

代码、离线回归、构建签名、官方缓存更新无剩余阻塞。**宿主重叠的确切触发条件及用户桌面视觉验收仍未确认**，不得声称本轮完成了真实宿主 UI 验收。没有 ComputerUse/浏览器交互、应用访问授权弹窗、系统剪贴板、daemon/监听服务器、新凭据、安全配置更改。额外真实模型调用 **0**，无 commit/push。
