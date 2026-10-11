# Codex Duo 0.9.8 本地插件更新

活动插件身份统一为 `codex-duo@codex-duo-local`，MCP 标识为 `codex-duo`，工具为 `codex_duo_*`，角色为 `codex_duo_worker` / `codex_duo_planner`。唯一技能入口是 `$codex-duo`。独立 Planner 仍由官方 app-server 的受限 Local 会话执行，Worker 仍使用原生路径。

项目状态从 `.fusion` 显式迁移到 `.codex-duo`。迁移原样移动所有配置、交接、预算账本、规划结果与会话记录，不修改记录哈希，不清空预算，不重试调用；冲突停止而不覆盖。持久迁移日志允许同一次中断恢复。旧目录原位置保留只读文件标记，阻止旧服务重建空预算。旧交接包的角色文件仅识别和校验，不注册旧角色。命名迁移本身不改变全局 `CODEX_HOME/codex-duo/selection.json`；本轮完成模式迁移见下文。应用最近项目记录只读识别旧应用域，新域已有值优先。

先验证源码并备份旧安装信息。通过官方 CLI 注册和安装新插件，核对缓存，再通过官方 CLI 移除旧插件和旧 marketplace；不能直接修改缓存或清空配置。旧注册移除前应确认新缓存完整且原状态有恢复备份。源代码 marketplace 位于 `.agents/plugins/marketplace.json`。

```sh
/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex plugin marketplace add /Users/kola/codex-duo
/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex plugin add codex-duo@codex-duo-local --json
python3 -B plugins/codex-duo/skills/workflow/scripts/codex_duo_workflow.py migrate --project-root /Users/kola/codex-duo
node native-build/build.mjs
bash macos/build.sh
```

迁移不启动模型。设置仍逐字段保存，首次启用 `plan_only` 时空规划组合沿用已保存的指定主控组合；保存不启动模型。保留已有有效模型和强度，切换模型时仅为不受支持的旧强度采用新模型默认强度。

聊天须在每次工具调用显式传实际 cwd。启动根与 cwd 为 `${PLUGIN_ROOT}`，不是聊天或菜单项目选择。菜单选项目只编辑该项目，不路由聊天。现有聊天可能需要重新加载；缓存完整、stdio 离线测试和 UI 测试都不证明普通聊天工具已加载。普通聊天验证必须在正常聊天工具入口进行；若该入口不暴露规划工具，不应绕到底层消耗授权调用额度。

历史安装与真实 Planner 回执保留在 `evidence/`；本轮证据见 [名称统一报告](evidence/name-unification/REPORT.md)。不要修改全局安全设置、扩大权限、创建凭据、重写 Git 历史、commit 或 push。

### 0.9.6 return 流程

完成模式设置、手动完成列表/复制提示及唤醒专用工具已移除。主聊天等待原生 Worker 并继续验收；只读 Planner、统一预算、取消/完成幂等、规范 diff 快照/生成/预检和现有界面修复保留。旧配置读取有效模式统一 return，不自动写盘。显式设置迁移入口：`codex_duo_workflow.py migrate_completion --project-root <实际项目> --scope project|global --expected-revision <当前hash>`，只改保存偏好并备份原字节，不更改旧任务。

仍使用官方本地 marketplace 更新：`codex plugin add codex-duo@codex-duo-local --json`。Python 3.11+ 用于完整测试；更新后核对源码与缓存 hash。0.9.8 只修复两份 manifest 的 `logo` / `composerIcon` 为 `./assets/tandem.png`：宿主会忽略缺少 `./` 前缀的资源引用。现有双环 PNG 不变。App 保持 `macos/dist/Codex Duo.app`，版本 0.9.7 / build 16，本轮不重建或打开应用。官方注册/文件核验不能证明页面已刷新；用户可正常重新载入插件后检查详情大图标与「立即试用」示例。证据见 `evidence/plugin-display-icon-fix/REPORT.md`，此前图标生成及原流程清理记录保留于 `evidence/icon-unification/REPORT.md`、`evidence/return-flow-cleanup/REPORT.md`。
