# Codex Duo 菜单栏设置

macOS 14+ 原生 SwiftUI 菜单栏应用，使用系统颜色，无 Dock 图标，无自启动。可编辑全局默认或当前项目独立设置，显示配置来源；不会运行模型或创建聊天。全局模型偏好独立于 Codex config.toml。

```sh
bash macos/build.sh
open "macos/dist/Codex Duo.app"
```

构建需要 Xcode Command Line Tools（Swift 6+）；运行需要 Python 3.11+ 和已安装的 Codex 本机 CLI。应用从 Homebrew、系统与现有 PATH 查找并验证 Python。服务默认读取 `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex` 的本机模型目录；可用 `CODEX_DUO_CODEX_CLI` 环境变量显式指定其他 CLI。本机目录不代表账户权限或模型实际可执行。

首次默认路径来自 Info.plist 的 `CodexDuoProjectRoot`；之后可从项目卡选择现有目录和最近项目，最近路径只存在应用 UserDefaults。项目 `.codex-duo/selection.json` 优先于实际 CODEX_HOME 下 `codex-duo/selection.json` 的全局默认；未配置项目只读继承。切换不会路由 Codex 聊天。开发时也请使用上述打包命令运行 `.app`；单独 `swift run` 不包含完整的 Python 服务资源。

隔离验证或管理明确的其他项目，请覆盖绝对路径：

```sh
open -n "macos/dist/Codex Duo.app" --args --project-root /absolute/existing/project
# 显示可自动化的独立设置窗口；菜单栏面板仍然可用。
open -n "macos/dist/Codex Duo.app" --args --project-root /absolute/existing/project --show-settings
```

点击菜单栏双环图标可打开面板。底部窗口按钮或再次打开已运行的应用可显示独立设置窗口；窗口和菜单面板共享草稿。模型及推理强度来自本机目录；保存通过应用打包的同一份 CodexDuoService 校验并原子写入，带读取时的 revision。刷新或重新打开面板保留未保存草稿，外部版本冲突会阻止覆盖；「重新载入并放弃草稿」确认后才替换草稿。保存只影响后续任务。高级设置保留未启用的主控选择；当前聊天模式不能切换当前模型，指定模型模式也不会自动创建聊天。

桥接使用一次性 Python 进程和 stdin/stdout JSON，无监听端口，无第三方依赖；服务导入路径仅来自应用资源或桥接源码仓库，绝不从所选项目加载代码。进程执行在后台，具有超时和输出大小上限。

验证：

```sh
python3 -B -m unittest discover -s tests -v
swift test --package-path macos
bash macos/build.sh
```

自动测试与构建只证明桥接、草稿逻辑及打包可用。实际菜单栏显示、交互、读写和无 Dock 图标需单独进行原生 UI 验证；不代表模型已执行。

新项目继承全局默认；没有全局配置时默认手动，可复制上个项目的模型选择。选择自动并保存才在该项目 AGENTS.md 添加管理指令块。切换前 Save/Discard/Cancel，切换失败保留原项目与草稿；忙碌时不能切换，保存始终使用发起时的项目服务。清除项目覆盖会检查项目及全局版本、备份原设置后恢复继承；失败保留草稿。测试使用隔离 CODEX_HOME 与 UserDefaults suite。

0.7.0：高级设置可选最大并行执行代理数 1 / 2 / 3，默认 1。旧配置缺字段时只补显示默认，不自动保存；全局和项目覆盖仍分别管理。并发受实际宿主容量与父任务剩余总执行次数限制。



0.9.4 / build 13 固定头部刷新与「在独立窗口中打开」的独立图标占位，静止图标不再使用动画容器，长状态文案在头部换行排布。右侧不是关闭按钮。退出已运行的旧 Codex Duo，再自行打开 `macos/dist/Codex Duo.app` 或替换为此构建；仅官方插件缓存更新不会替换运行中的菜单程序。离屏验证与未测宿主边界见 `evidence/header-layout-fix/REPORT.md`。


0.9.6 / build 15 移除完成模式选择、完成列表及剪贴板提示。原聊天等待结果并验收。保留 Planner 设置与头部布局修复；不自动打开菜单应用。

0.9.7 / build 16：`generate-icons.py` 在打包前从标题栏使用的 `Resources/Brand/AppIcon.svg` 生成 16–1024 px 的完整 iconset、AppIcon.icns 和插件 PNG。需要 rsvg-convert 与 macOS iconutil；不另绘一套图标。

0.10.0 / build 17：新增「代理积极程度」三档滑杆（保守、均衡、积极），默认均衡。旧配置缺少此字段时按均衡读取，不自动改写设置。简单任务由当前聊天完成，适合独立交接的任务按档位门槛派发；模型、推理强度和预算保持原设置。
