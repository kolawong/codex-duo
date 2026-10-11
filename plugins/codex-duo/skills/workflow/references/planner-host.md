# Independent read-only Planner session

The default plan_only adapter uses the installed official Codex CLI's app-server stdio
protocol. The parent remains the current chat. Only explicit planner_run starts a model;
settings, begin and status never do. Worker dispatch remains on the original native path.
An independent ephemeral Planner session is now authorized architecture, so custom role
selection is not required. Never substitute a CLI exec/coordinator/Worker model.

## Effective preflight

The adapter launches its own local transport with invocation-scoped restrictions. It
never changes global safety configuration or credentials, accesses another conversation,
boots a daemon, or restarts a user app. Config overrides disable agents, apps, hooks,
remote plugins, tool suggestions, memories and all configured plugins/explicit MCP.
CLI override keys must be safely representable. Disabled MCP overrides retain valid
transport type and inert values; disabled entries still undergo transport validation.
Unknown inherited enabled capabilities, malformed config or unconfirmed controls block.

Before any turn/start, inspect the actual config/read and thread/start responses:
- sandbox_mode=read-only; effective sandbox type=readOnly, networkAccess=false
- approvalPolicy=never; no escalation, login shell, web search, apps/hooks/agents
- every plugin and MCP enabled flag false; remote_plugin/tool_suggest/memories disabled
- exact snapshot model and reasoningEffort, allowProviderModelFallback=false
- independent ephemeral thread, actual project cwd, no dynamicTools

The transport receives these responses directly from the official host; it does not
accept host_capabilities filled by a user or model. The model receives bounded requested
file contents (256 KiB UTF-8 maximum) and strict outputSchema, and is instructed to return
only a proposal without tools. Shell tools are also disabled for this invocation. Tool
attempt notifications cause interruption/rejection; sandbox policy is the write/network
boundary, not the prompt. These checks trust the installed official binary and its
reported runtime policy; they are not a cryptographic attestation against a compromised
host. An unsupported host fails before model transmission rather than weakening controls.

## Durable dispatch and return

planner_begin freezes request, settings/explicit task choice and code hashes. planner_run
atomically claims a stable attempt_id and the shared task budget before detached adapter
startup. The child adapter claims ownership once. It records effective permission proof,
thread id and irreversible turn intent before sending turn/start, then records turn id.
Same attempt_id is idempotent, including across service restart. Each reservation consumes
an attempt, including startup/preflight failure; turn_committed distinguishes potentially
billable attempts. There is no automatic retry, model substitution or budget refund.

The adapter persists the actual terminal receipt and strict plan through the existing
Planner state machine. Only parent code writes .codex-duo state. Suggested tests must be
not_run; approvals, diffs and execution evidence are rejected. Code baseline changes
reject the result and make the plan stale. Only a later explicit approval can create a
new ordinary Worker contract, never an automatic conversion of plan_id.

planner_stop persists a stop request. A live adapter sends official turn/interrupt;
an acknowledgement alone does not prove termination. Timeout/transport loss/owner loss
after durable turn intent leaves a reserved uncertain attempt: status is inspectable,
no blind relaunch is allowed. Ephemeral transports cannot be resumed after owner loss;
resolve the uncertain attempt with trusted host evidence before considering further work.
A process-loss heartbeat older than the 600-second timeout plus grace reports uncertain.
No automatic completion or fabricated receipt clears that state.

## Compatibility and verification

The original planner_reserve/complete route remains available for verified native hosts.
The codex_duo_planner custom-role template is optional for that route. Its disabled MCP
entry retains command=false so native deserialization accepts it. Parent live permission
overrides can defeat role defaults, so that old route still requires effective child
permission/tool-surface evidence. Managed independent-session records cannot be manually
completed via this compatibility route.

Offline protocol fixtures test preflight, exact model, duplicate/restart ownership,
timeout/transport loss, cancellation, budget and result validation. They are not real
model receipts. Real acceptance must separately record host responses, actual model/effort,
turn/session receipt, validated result, unchanged code baseline and zero Worker.

Official references (checked 2026-10-11):
- https://learn.chatgpt.com/docs/app-server
- https://learn.chatgpt.com/docs/agent-configuration/subagents

## Completion delivery limitation (0.9.0)

The Python adapter consumes official events in the background. Correlation requires
threadId and turnId; interrupted is distinct from failed. Cancellation waits briefly for
a matching terminal event, otherwise the original reservation stays uncertain. Restart
reads the durable ledger and stable completion event IDs; it never reclaims a lost owner
or repeats turn/start. Worker events are reported by the native coordinator.

The coordinating chat reads planner_status and the original result, then reviews
the plan. Worker receipts and evidence return through the native coordinator.
No separate completion-mode tool, manual review inbox or background wake route exists.
