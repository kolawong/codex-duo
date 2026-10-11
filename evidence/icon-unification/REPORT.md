# Codex Duo 图标统一 — 0.9.7 / build 16

本轮按用户授权复用现有标题栏双环图案，完成本地实现、离线核验、构建签名、官方插件更新及 Library 预览保存。没有重画图案，没有额外模型、图像生成、Computer Use、浏览器 UI 或应用启动。

## 原图与修改

已通过本轮 Library materialization helper 下载并查看用户截图 `libfile_3ee993dcda2c8191a0809fb6bf672b5d`，本地文件为 `reference/user-screenshot.png`（436×166）。截图左侧确实显示灰色回形针形图标；没有依据将原因归结为特定宿主缓存或渲染错误。

唯一绘制源为 `macos/Sources/CodexDuoMenu/Resources/Brand/AppIcon.svg`：深色底板、两枚圆环、橙色交集。源文件 SHA-256 `4c857df280741b7a448a39bcfb4877b6869e5f4f3a2080f2c59a6f80b6ff38d8`，与本轮前完全相同。Swift 标题栏继续经 `LogoMark` / `Brand.appIcon` 使用该文件；菜单栏动态圆环绘制代码不变。

本轮增量（完整文件及前后 hash 见 `changed-files.json`，文本差异见 `increment.diff`）：

- 新增 `macos/generate-icons.py` 与 `macos/Assets/AppIcon.iconset/` 十个 PNG：从上述 SVG 直接按尺寸渲染，使用 macOS `iconutil` 打包。`macos/build.sh` 在构建前运行生成器，并更新应用版本。`AppIcon.icns` 与 `AppIcon-preview.png` 经重建后与本轮前字节一致，原应用图案本来已与标题栏一致。
- 新增 `plugins/codex-duo/assets/tandem.png`（1024×1024），两个插件 manifest 的 `logo` / `composerIcon` 改用它；`mcp/server.py` 的 `codex_duo_open` icon 改为相同 PNG 的 base64 / image/png。保留已有 `tandem.svg`，它与绘制源字节一致。
- `native-build/build.mjs` 在打包时从同一 SVG 注入 Web 标题图标，`bridge.js` 更新版本，重建 `plugins/codex-duo/ui/model-desk.html`。没有修改设置控制器或模型调度逻辑。
- 更新 `tests/test_native.py` 中 PNG 内容、MIME、manifest 路径和版本断言；更新 `README.md`、`NATIVE-INSTALL.md`、`macos/README.md` 的版本与构建说明。

## 离线验证与安装

| 命令 / 核验 | 结果 | 记录 |
| --- | --- | --- |
| `python3 -B -m unittest discover -s tests -v`，PATH 使用 Homebrew Python 3.14 | 224 / 224 通过 | `python-tests.log` |
| `swift test --package-path macos` | 24 / 24 通过，含离屏头部绘制 | `swift-tests.log` |
| `node native-build/test-panel.mjs` | MCP / HTTP 控制器、return 流程回归通过 | `panel-tests.log` |
| `node native-build/test-client.mjs` | 官方 MCP SDK 协议与隔离状态验证通过，model_calls=0 | `client-tests.log` |
| `node native-build/build.mjs` | 自包含 Web 面板构建成功 | `web-build.log` |
| `bash macos/build.sh` | 0.9.7 / build 16 构建成功，ad hoc 签名 | `macos-build.log` |
| `codesign --verify --deep --strict --verbose=2`，实际 `.app` | valid on disk，满足 designated requirement | `codesign.log`、`codesign-details.log` |
| 官方 `codex plugin add codex-duo@codex-duo-local --json` | 安装版本 0.9.7 | `plugin-update.json` |
| `python3 -B evidence/icon-unification/audit.py` | 图标、缓存、打包脚本与保护状态核验通过 | `audit.log`、`icon-validation.json`、`installation-hashes.json` |

官方安装位置 `/Users/kola/.codex/plugins/cache/codex-duo-local/codex-duo/0.9.7`，39 个插件文件集合及 SHA-256 全部与当前源码一致。最终应用 `macos/dist/Codex Duo.app` 的 Info.plist 为 0.9.7 / 16，CFBundleIconFile=AppIcon；十个服务脚本及桥接资源与源码一致。

实际 `.app` 的 ICNS 由 macOS 工具解包到 `final-app-icons.iconset`，包含 16/32/128/256/512 pt 的普通与 @2x 共十种表示，覆盖 16–1024 px。八种 RGBA 像素与源 PNG 完全一致。普通 16/32 px 经 iconutil 旧式 RGB+mask 编码后，透明度、轮廓和全部不透明像素一致，半透明边缘 RGB 有差异；准确 delta 见 `icon-validation.json`。这是与本轮前相同的 ICNS 编码结果，不声称十种逐像素一致。尝试直接封装 PNG 小尺寸后 macOS 解包核验失败，最终采用系统生成器，失败方案未安装或保留为最终代码。

插件 PNG SHA-256 `af9920bc6a2dedb833748c8dd0339414e7f60314aef1247c90d1a187356778f4`；最终 ICNS SHA-256 `149c8bd5f69d9ad6ca9fcdfe6605259576f764c4b2b375a03bf24f2cfc31f244`。

## 偏好与历史保护

本轮开始保存工作区状态、源码字节和保护清单。1595 个受保护文件 hash 不变，包含 `.codex-duo` 任务/结果/预算、旧 evidence、项目及全局偏好、角色配置、AGENTS.md、marketplace 和 Git HEAD。唯一额外变化为 Git index 的字节缓存；使用原 index 副本与当前 index 分别读取的 103 个 mode/blob/stage 条目完全一致，没有暂存内容或提交历史改变。记录见 `protected-before.json` / `protected-after.json`。

项目 selection SHA-256 保持 `fdff92fa638e5494046b4adab310441dd665b7aa04caba229cefab2589897cf7`，全局 selection 保持 `1900c32e3405535a2acc6cb11f88ac548cf57e70ab15c33e8bccf77f7a715a7c`。保留现有 Astra Planner、Worker、项目覆盖及 0.9.6 return 流程；不重派旧任务，不清预算，不覆盖之前的清理报告。真实额外模型调用 **0**，没有 commit / push / pull / reset / 新分支。

## 预览与使用边界

Library 预览已创建并确认成功：

- library_file_id：`libfile_66e5e23dbdb08191a51657cb676e26ee`
- file_id：`file_00000000dff081f58a2bfb2406b422c1`
- 文件名：`Codex-Duo-unified-icon-preview.png`，900×830 RGB，81312 字节，version 0
- 本地对应文件：`evidence/icon-unification/Codex-Duo-unified-icon-preview.png`
- 上传结果：`library-preview-result.json`，Library 身份 xattr 已应用到本地文件

用户可自行退出旧菜单应用，再打开 `macos/dist/Codex Duo.app`；Codex 插件工具必要时重新加载。官方缓存更新不会替换已经运行的菜单程序或证明当前宿主已刷新图标。

没有测实际宿主插件卡片、菜单栏点击、设置窗口交互或 Dock/Finder 显示；预览为离线生成的图标对照图，并非真实宿主 UI 截图。沒有声称回形针已在用户当前界面消失。当前交付无实现阻塞，实际宿主显示验收留待用户正常重载后观察。
