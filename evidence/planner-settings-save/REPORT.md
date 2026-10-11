# Planner 全局设置保存修复（本机）

本轮修复的是全局插件设置的逐字段保存失败，不包含新的 Planner 或 Worker 模型执行。

## 问题与修改

HEAD：`78f38bef638a7643c5dcfe46d8e19fe6694c469d`，包含指定 main 提交。沿用任务开始时全部未提交修改；没有 reset、拉取、提交或推送。

实际全局设置的规划模型和强度为空。单独保存 `planner_mode=plan_only` 会返回 `invalid_workflow` / HTTP 400：启用仅规划模式前必须选择规划模型和推理强度。见 `reproduction-before.json`。

本轮代码修改位于 `fusion_service.py`：首次从关闭启用且规划组合为空时补齐已保存的主控组合；单独切换模型时保留受支持的强度，否则使用新模型默认强度。启用后的模型/强度枚举排除空值，强度枚举按模型限定。已有有效选择、其他偏好和项目覆盖保持原意；显式无效组合仍拒绝。新增六项 `test_planner_settings.py` 回归及 NATIVE-INSTALL 说明。

## 已安装插件与真实设置 API

通过官方命令更新：

```sh
/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex plugin add fusion-minimal@fusion-local --json
```

安装目录 `/Users/kola/.codex/plugins/cache/fusion-local/fusion-minimal/0.7.0`。版本号未变，使用文件比对确认更新：36 个包文件与源码一致。没有手改缓存。

从已安装 manifest 启动真实 stdio 服务，只调用 `fusion.settings_read` / `fusion.settings_update` / `fusion.defaults`，每次明确传入 `/Users/kola/codex-duo`。单独开启、单独改模型、单独改强度、关闭服务再启动重读均通过；当前项目覆盖仍优先且仍关闭 Planner。见 `installed-settings-check.json` / `installed-settings-rpc.json`。

这些结果证明安装缓存和新启动独立 MCP 服务可用，不证明本轮委派聊天或用户现有普通 Local 聊天已刷新工具，也不证明宿主内插件设置面板刷新后的逐项 UI 行为。

## 实际 UI 验证及限制

可访问的独立 `macos/dist/Codex Duo.app` 中，选择全局默认，开启仅规划，选择 GPT-6.1-Sol / 高，点击保存，实际 AX 状态显示“Codex Duo 状态：已保存”“已保存，之后的新任务会使用这套设置”。正常退出并重开后，全局默认实际 AX 仍显示：

```text
编辑范围, Value: 全局默认
Codex Duo 状态：已保存
button (selected) 仅规划
模型, Value: GPT-6.1-Sol
推理强度, Value: 高
规划次数上限, Details: 1 次
```

真实已安装 API 再读确认只有三个 Planner 字段临时变化。该独立原生 UI 使用完整配置保存，因此它的通过不能替代原宿主内逐字段设置 UI。见 `native-ui-saved-values.json` / `native-ui-check.json`。

原问题界面位于 `com.openai.codex`。Computer Use 明确拒绝访问该应用，本轮没有绕过限制，没有重启用户 Codex/ChatGPT，不能宣称原插件面板 UI 已实测。更新后的当前宿主服务是否热加载也尚未证实。剩余验收应在用户允许的宿主里重新加载插件工具/设置后，直接尝试逐字段开启及模型/强度选择；无需为这个设置验证启动模型。

## 恢复与安全边界

测试后，通过正常设置 API 且先确认当前值仍等于最后测试写入值，恢复全部原全局设置值：Astra/xhigh 主控、Sol/high Worker、automatic_project/current_thread、Worker 10 轮、并行 1、Planner 关闭且模型/强度为空、Planner 1 轮。刷新独立原生 UI 后实际显示“关闭”。见 `native-ui-restore-rpc.json`。

正常保存会更新元数据 saved_at、显式写出默认字段，故不能声称全局偏好文件字节未变；语义设置值已恢复。项目 `.fusion/selection.json` 与全局 `.codex/config.toml` SHA256 和基线一致。没有凭据、安全策略或用户其他模型选择修改，本轮 Planner/Worker 调用均为 0。历史真实规划收据未重用、重试或退款。

用户授权发送诊断进展后，尝试向来源任务 `01a118d8-7d00-75f5-b600-0c48ff8cd014` 发送，本机返回 thread not found，未成功投递；最终结果由平台正常回传。

## 验证记录

`bash macos/build.sh` 成功；`codesign --verify --deep --strict` 成功；构建中的 fusion_service.py 与本轮源码一致。Swift 18 项通过，静态检查 36 项通过，`git diff --check` 通过。

系统 `/usr/bin/python3` 为 3.9.6，不满足仓库 Python 3.11+ 要求（缺 tomllib）；使用已有 `/opt/homebrew/bin/python3.11`（3.11.17），没有安装运行时或改全局 PATH。默认沙箱禁止 Swift/Clang 用户模块缓存、Python HTTP fixture 的本机临时端口，分别以用户已批准的本机测试权限执行。保留原限制失败日志供区分环境错误。

首次全量测试 178 项通过，但包含因新测试导入 fixture TestCase 而重复发现的 9 项旧测试；已修正导入方式，最终唯一计数以 `python311-unittest-authorized.log` 为准。回归在修复前为 4 项错误、1 项失败、1 项原本通过，修复后六项均通过。

最终 `/opt/homebrew/bin/python3.11 -B -m unittest discover -s tests -v`：**169 项，45.000 秒，全部通过，无跳过**。Swift：**18 项全部通过**。本轮未调用任何真实 Planner/Worker，额外真实模型验收仍需用户另行确认模型和用途。
