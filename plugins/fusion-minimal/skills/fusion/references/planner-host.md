# Native Planner host adapter

This is the executable-role configuration and coordinator procedure for the `plan_only`
protocol. The plugin never starts a second CLI process. Use a host's existing native
subagent tool; preserve the original Worker dispatch path.

## Official configuration, not an invented launch API

The repository includes `.codex/agents/fusion_planner.toml`, with an identical portable
copy at `../templates/fusion_planner.toml`. Codex officially discovers standalone custom
agents from `.codex/agents/` in a trusted project or `~/.codex/agents/`. The companion has
read-only sandbox defaults, no escalation, disabled agent tools, apps, hooks, web search,
and the known Codex Duo MCP/plugin disabled. It deliberately does not pin model/effort:
the coordinator passes the saved pair from the reservation to the actual native tool.

When using this repository, reload native agent discovery after pulling. For another
project, the coordinator may prepare this companion for review, but must obtain the
applicable approval before installing or changing security/agent configuration. Saving
Planner settings alone does not install it or authorize a persistent config change.
Do not edit global configuration, switch the parent's model, or invoke `codex exec` as a
fallback. Do not invent spawn parameter names: map `fusion_planner` plus model/effort and
fresh-context values to the discovered host tool's actual schema. If it cannot select
this custom role and exact model/effort, report a host limitation without dispatch.

## Required effective permissions

A custom agent file is NOT sufficient proof. Official docs state parent live runtime
sandbox/approval overrides can win over custom-agent defaults. In ChatGPT Work,
subagents inherit available parent tools and have no independent local sandbox control.
Do not assume a writable parent produces a read-only child. A public issue also reports
this inheritance in noninteractive Codex 0.153.4; this is a compatibility warning, not a
claim about every current app build.

Before reserve/spawn, inspect trusted host capability/configuration information to ensure
that the selected role's **effective** sandbox will be read-only with escalation disabled.
If the host cannot establish that before dispatch, stop with `readonly_host_required`.
An already read-only parent with no permissive live overrides may provide a viable route
on a host that documents inheritance, provided the remaining controls below also apply.
Do not silently change the parent's permissions to create that route.

Read-only shell access (`process_execution=read_only_sandbox`) is valid: `cat`, `rg`, and
read-only Git inspection may run inside the enforced sandbox. Do not require all process
execution to be disabled. Writes must be denied by the host, including attempts through
shell and editing tools. Network access and escalation must be disabled. Tests/builds
are not part of planning even if a particular command could run without writing.

Filesystem sandboxing does not govern external MCP/app side effects. Inspect the entire
inherited tool surface. The companion disables known Duo tools and apps; it cannot name
unknown MCP servers/plugins inherited from a user's configuration. Disable those in an
approved role configuration or require a native tool allowlist before using the role.
No external connector tools or agent-spawn tools may remain available. If their absence
cannot be established, stop. A model saying it will avoid them is not evidence.

Only then should the coordinator report host_capabilities to `planner_reserve`:
- actual `tool`, `model`, `reasoning_effort`
- `filesystem=read_only`, `network=disabled`, `writes=disabled`
- `process_execution=read_only_sandbox` or `disabled`
- `agent_spawn=disabled`, `approval_escalation=disabled`, `external_tools=disabled`
- `enforcement=host`

These are the coordinator's reports from host information, not signed attestations and
not fields a Planner can supply to authorize itself. The service validates the report
and ledger, but cannot authenticate host statements or intercept direct native calls.

## Dispatch and return

1. Resolve saved settings and explicitly requested plan scope. Call planner_begin.
2. Verify host compatibility as above. Reserve once immediately before each native call.
3. Pass the returned request, plan_id, dispatch_id, baseline_sha256, exact model/effort,
   and independent result contract to `fusion_planner` with fresh context. Include the
   project root and exact read_paths. Ask for a blocked result if runtime context differs
   from expected permissions; do not perform a write/network probe in the user's project.
4. Await the actual native result. Record its receipt with planner_complete. A spawn
   failure consumes the reservation; use failed/blocked. After an uncertain timeout,
   inspect the native task rather than reserving/spawning again. A still-reserved entry
   survives restart and prevents another concurrent launch. Never invent a failure receipt.
5. Show the validated result to the user in the current chat. Do not auto-execute. After
   explicit implementation approval, recheck planner_status and translate approved scope
   into a new ordinary Worker contract. The Planner never owns this transition.

## Verified scope of this implementation

Offline tests exercise persisted lifecycle, permissions-report gate, configuration,
MCP/CLI routing, result validation, and no Worker conversion. They do not verify a live
Codex build's sandbox inheritance, connector filtering, account model availability, or
model execution. The repository role is a concrete native configuration path on hosts
that honor these official settings; unsupported hosts remain blocked. Run macOS/native
acceptance with the user's authorization before claiming end-to-end Planner execution.

Official references (checked 2026-10-11):
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://learn.chatgpt.com/docs/config-file/config-reference
- Compatibility report: https://github.com/openai/codex/issues/45482
