# Worker 断言转义：离线诊断与最小修复

日期：2026-10-11。项目 `/Users/kola/codex-duo`，本机 main 工作树。没有模型派发、Planner、complete 重提、提交、推送、分支、安装或 UI 操作。现有 return 流程未修改。

## 根因及证据边界

独立读取原 handoff/task.json、子 contracts/main.json、result.json、test.log、preflight.log、before 快照和 change.diff。三个 JSON 的测试 argv 一致。契约中的 Python 字符串含反斜杠加 n，原始 argv 直接交给 subprocess.run 后 exit 0，probe 字节为 61667465720a。before 保存 before 加 LF，规范 diff 为 before → after。

test.log 第一行 JSON 解码后的实际 ARGV 与契约不同：Python 字符串内是 LF。对原代码字符串额外执行一次 unicode_escape 解码，精确得到日志 argv，执行后 exit 1，并复现同样 SyntaxError。result.json 却记录原契约 argv 和 exit 1。详见 diagnosis.json。

因此，有证据的问题在 Worker 执行/记日志阶段，而非请求、handoff 生成器或子契约 JSON 序列化。生成器使用 json.dumps，子契约写入 json.dumps，没有找到这一链路的确定性二次解码代码 bug。日志与 SyntaxError 相互支持实际执行字符串被改变；但原 Worker 转换语句和原生执行调用未记录，不能确定是 unicode_escape、字符串重建或其他操作，也不能完全排除日志转录失真。复现代码是解释性实验，不是假冒旧 Worker 调用记录。

## 实际修改

- `.codex/agents/codex_duo_worker.toml`：追加 JSON 仅解码一次、原样 argv / shell=False 执行、记录实际 argv 与退出码的指导。
- `plugins/codex-duo/skills/workflow/scripts/codex_duo_selection.py`：生成新 handoff Worker 指导也包含同样要求；不改序列化协议或旧 handoff。
- `plugins/codex-duo/skills/codex-duo/SKILL.md` 与 `plugins/codex-duo/skills/workflow/references/contract.md`：明确不得二次解码、不得重建 python -c 字符串，以及独立脚本方案。
- 新增 `plugins/codex-duo/skills/workflow/scripts/assert_bytes.py`：只读指定文件，按 hex 比较真实字节；不匹配/缺失 exit 1，非法 hex exit 2；不使用可被 -O 禁用的 assert。
- 新增 `tests/test_assertion_escaping.py`：JSON 原样执行成功、二次解码复现 SyntaxError，脚本覆盖 LF、字面反斜杠、CRLF、空值、全字节、特殊文件名、错误字节、缺失文件、非法 hex 与 -O。

未修改预检、回执、预算、旧 failed 记录。指导加固与脚本已通过离线验证；没有宣称已修复模型行为或完成原生验收。插件缓存未更新/安装，新插件源码指导需以后由用户授权更新并重载后才可在已安装插件生效；本地脚本可直接使用。

## 离线验证

新增两项回归通过；独立脚本读取旧 probe 返回 exit 0（standalone.log）。原失败仍是失败，旧预检拒绝记录未更改。

要求的 `python3 -B -m unittest discover -s tests -v` 已运行：系统 Python 3.9，214 tests，8 errors，原因是缺少 tomllib 与 Path.stat(follow_symlinks=...) 不受支持。README 要求 Python 3.11+；使用已有 `/opt/homebrew/bin/python3.11` 跑完整套件，结果见下文与 unittest-python311-explicit.log。无环境安装。

本轮修改的已跟踪文件 git diff --check 通过；全工作树 diff --check 报 README.md:3 的既有尾空格，本轮未触碰 README。共享 panel 未改，不需要重建或 UI 检查。

## 历史、偏好及无关改动保护

baseline.json 在编辑前记录 3620 个已有文件 SHA-256，覆盖所有 .codex-duo 状态/账本/handoff、旧 evidence、已跟踪文件及项目/全局 selection.json/config.toml。protection.json 显示仅四个明确修改的已有文件变化，意外变化为空。旧 evidence 与所有账本、保存偏好及配置哈希均未变；其他现有工作树改动保留。允许修改的四个文件通过追加指导/单段替换保留原有改动。未创建新任务或重置预算。

## 后续新任务的稳健命令

在项目根目录执行，按新任务范围替换 probe 路径：

```sh
python3 -B plugins/codex-duo/skills/workflow/scripts/assert_bytes.py evidence/example/probe.txt 61667465720a
```

对应契约 argv：

```json
["python3", "-B", "plugins/codex-duo/skills/workflow/scripts/assert_bytes.py", "evidence/example/probe.txt", "61667465720a"]
```

由 Worker 对已审查的 argv 直接 subprocess.run(argv, shell=False)，记录真实 argv、exit code 和日志哈希，再走现有预检。不得替换旧契约或重提旧 complete。61667465720a 明确表示 after 加 LF，不需要嵌套 shell/Python 转义。

Python 3.11 完整回归终态：

```text
----------------------------------------------------------------------
Ran 245 tests in 51.053s

OK
```
