---
name: codex-duo
description: Use for Codex Duo tasks and for implementation or bug-fix tasks when global or project AGENTS.md enables Codex Duo automatic_project mode. Resolve global defaults and per-project overrides once per task; the current chat plans and verifies bounded native workers under a shared total budget. The user need not invoke a slash command, reopen settings, write JSON, or copy a handoff. Do not use for ordinary questions, read-only checks, or worker subtasks.
---

# Configure once, use the saved defaults

Global instructions in the actual CODEX_HOME/AGENTS.md opt eligible development tasks into
this workflow across projects after the user explicitly authorizes global setup. Project
AGENTS.md remains an explicit opt-in alternative. Saving settings never installs global
instructions or edits Codex config.toml. The coordinator performs authorized global setup
separately, preserving other instructions in a bounded managed block.

Defaults resolve in this order: existing project `.codex-duo/selection.json` (including legacy
manual settings), then `CODEX_HOME/codex-duo/selection.json`, then setup-required. CODEX_HOME
uses the process environment override or `~/.codex`. Existing selections remain project
overrides and are never migrated automatically. A project manual override disables automatic
use even if global automatic is enabled; global manual disables automatic use for inheriting
projects. Invalid files in either layer fail closed; do not silently substitute defaults.
Reading and switching never write. Resetting project overrides requires explicit user action
and matching project/global revisions; it backs up the override and restores inheritance.
Determine the actual current chat's project cwd from trusted task/environment context;
if unavailable, read it via a shell `pwd -P`. Require an existing absolute canonical directory.
Never use menu selection, the plugin's configured fallback root, or another chat's project.
Pass this exact `project_root` on **every** codex_duo_* tool call, including open/state/save,
settings_read/settings_update, prepare and execution_plan. Refuse ambiguous/invalid roots;
on project_mismatch stop rather than falling back. Tools are stateless across projects.
Read `codex_duo_defaults` at the start of each eligible user task to pick up explicit
configuration updates. Never overwrite saved preferences just because a new task starts.
Open `codex_duo_open` with this chat project_root only for first setup or when the user asks to view/change settings.
For a question or read-only check, answer directly without starting a worker.
Workers must not invoke this workflow or spawn additional agents.

## Authorization and activation

`automatic_project` plus the global or project instruction is the user's standing choice
to use Codex Duo for eligible user-requested development work. Always resolve the actual
chat project; local activation and model overrides win over global defaults. The current user request
defines the allowed scope. In `manual` mode, require the user to request Codex Duo.
Saved preferences alone, loading the plugin, viewing settings, and preparing an internal
snapshot do not authorize new work. Do not run a model just to test plugin installation.
A task request and its saved model/effort/turn limit are enough: do not ask the user to
repeat model names, reconfigure, copy paths, or reconfirm an already-authorized task.
Honor explicit no-model/read-only instructions. Ask only for a materially missing scope
or a new action outside the existing authorization. Do not commit, push, publish, change
global settings, or install Hooks without a specific user request.

## Default: current chat coordinates

With `coordinator_mode=current_thread`, keep this chat as coordinator. The saved
coordinator model is an inactive advanced preference; never claim the current model
changed. Do not create a new user-owned chat for the worker. Do not use a second reviewer.
With `selected_model`, explain the saved choice and only create a new coordinator chat
when the user explicitly requests a new chat. Settings alone do not authorize creation.

## Prepare and dispatch automatically

1. Inspect the actual files and relevant instructions; resolve the bounded work and checks.
   Discover a native subagent tool supporting the selected worker model and reasoning
   effort. If unavailable or rejected, report the host limitation clearly. Do not start
   a separate CLI model process, silently substitute a model, or claim Codex Duo executed.
   Continue any independently authorized work in this chat with the limitation disclosed.
2. Build the task specification internally, using `../workflow/references/contract.md`: a unique task_id,
   goal, exact allowed_paths, acceptance criteria, and meaningful tests as argv arrays.
   Call `codex_duo_begin` with project_root, task, and invocation (`automatic` or `explicit`).
   It atomically reads saved settings, prepares an internal snapshot, and returns the
   task_path, evidence_root, worker parameters, and max_worker_turns. This is preparation,
   not an execution receipt. Never ask the user to edit/copy this snapshot.
3. Read the actual native tool capacity (worker slots available to THIS parent task in total,
   including its reserved/running workers, excluding the coordinator and other tasks). Never
   change host configuration to increase it. If capacity is unknown, use 1 conservatively.
   Plan one workstream for simple work. Split only clearly independent work: each workstream
   has a unique id, complete task contract, exact disjoint allowed_paths, and depends_on IDs.
   Coordinate shared interfaces before dispatch; consolidate overlapping file edits into one
   owner. Reject circular dependencies or replan conflicts. Do not split merely to fill slots.
   Use codex_duo_plan with project_root, handoff_id, host_capacity and optional workstreams
   (array of {id, task, depends_on}). The omitted list uses the original task as one worker.
   The service persists the plan and concrete contracts without launching any model.
4. Immediately before EVERY initial native spawn or correction/follow-up, call codex_duo_reserve
   with project_root, handoff_id, workstream_id and current confirmed host_capacity. The
   returned reservation contains exact saved model/effort, task_path, distinct evidence_root,
   dispatch_id (returned as id), and remaining_worker_turns. Respect the saved
   max_parallel_workers (1/2/3, missing legacy value means 1), actual host capacity, ready
   dependencies, and remaining TOTAL parent max_worker_turns. Parallel dispatch only when
   both independent ownership and slots permit. Wait/complete existing workers before
   dispatching dependencies. The durable ledger counts every reservation, including failed
   spawns; no refunds, per-child budgets or new task IDs to reset correction counts.
5. Start supported native workers with the returned model/effort and fresh context
   (fork_context=false or the documented equivalent). Map parameters to the actual tool;
   never pass unsupported keys or use named agents that override the saved model. Provide
   project cwd, task_path, evidence_root, full bounded instructions, result contract and
   references. Workers preserve other agents' edits, must not recurse, spawn children,
   change immutable contracts, or call codex_duo_begin for themselves. Do not create user-owned
   chats. Wait for each result without routine interruptions. The worker writes result.json,
   change.diff and only its task's required test logs under its distinct evidence_root.
   Forward reserve.evidence_commands unchanged to the Worker: snapshot_before_edit BEFORE
   any edit, diff_after_edit afterwards, then preflight_result after result.json/log hashes.
   Read ../workflow/references/contract.md for the canonical --- a/path / +++ b/path contract
   (/dev/null only for an absent side). These deterministic helpers support scoped non-Git
   text files; do not use Git HEAD as a baseline or diff unrelated existing dirty changes.
   Evidence failure does not authorize retries: an explicit one-dispatch cap remains binding.
6. For each reservation call codex_duo_complete with project_root, handoff_id, dispatch_id,
   native_receipt (actual native ID or failure receipt) and outcome completed/failed/blocked/cancelled.
   completed verifies that child's contract and hashes before releasing dependencies. If
   evidence fails, independently inspect it; record failed/blocked to release the slot and
   reserve a correction within the same total budget. A correction invalidates prior child
   completion and downstream verification; active dependent work prevents upstream edits.
   Receipts are coordinator supplied; the ledger enforces accounting for adapter calls but
   cannot intercept direct native tool calls. Never bypass reserve or claim model provenance
   from ledger/hash success alone. At exhaustion stop dispatch and report remaining work.

## Wait for results in the coordinating chat

The current chat observes native Worker completion, records its real receipt with
codex_duo_complete, and continues with the independent acceptance steps below.
Planner's existing read-only process observes official turn/completed events; its
plan returns to the coordinating chat and never authorizes execution on its own.
Do not stop at a copy prompt, invent a chat link, wake a background reviewer or
start another model to poll. Completion is not acceptance. Unconfirmed dispatch,
transport loss or an expired owner stays pending/unknown; cancellation acknowledgement
alone is not terminal completion. Read the same durable IDs and preserve consumed
budget; never create replacement task IDs to recover missing evidence.

## Verify and report

Verify every child with `../workflow/scripts/codex_duo.py verify --task <task_path> --result <evidence_root>/result.json
--root <evidence_root>`. This validates identity, scope and evidence hashes; it does not
prove correctness. Independently inspect every child diff, preserve other workers changes,
then run the parent integration checks. Write the combined parent result.json, change.diff
and parent-required test logs under the ORIGINAL parent evidence_root, with all final child
changed_paths represented. Call codex_duo_verify with project_root and handoff_id to revalidate
every final child and the integrated parent contract. The same coordinator independently reviews the actual diff and reruns
appropriate checks. Preserve unrelated pre-existing changes. Never claim acceptance before
this review, or equate a prepared snapshot with a worker actually running.
Use short progress messages for planning, execution and verification, based on actual events.
Return the result in this chat: what changed, verification, remaining issues. Link evidence
only when useful; the user should not need to understand the internal file format.

## Older hosts and local fallback

If newly installed MCP tools are not yet discovered, use the packaged local helper with
an absolute project root (it performs no inference):

- `python3 -B <skill-dir>/../workflow/scripts/codex_duo_workflow.py defaults --project-root <root>`
- `python3 -B <skill-dir>/../workflow/scripts/codex_duo_workflow.py begin --project-root <root> --task <internally-written-task.json> --invocation automatic`
- `python3 -B <skill-dir>/../workflow/scripts/codex_duo_workflow.py plan --project-root <root> --handoff-id <id> --host-capacity <total slots> [--workstreams <internal.json>]`
- `python3 -B <skill-dir>/../workflow/scripts/codex_duo_workflow.py reserve --project-root <root> --handoff-id <id> --host-capacity <total slots> --workstream-id <id>`
- `python3 -B <skill-dir>/../workflow/scripts/codex_duo_workflow.py complete --project-root <root> --handoff-id <id> --dispatch-id <id> --native-receipt <actual receipt> --outcome <completed|failed|blocked>`
- `python3 -B <skill-dir>/../workflow/scripts/codex_duo_workflow.py verify --project-root <root> --handoff-id <id>`

This helper does not add native worker tools to the host. Do not imply that a fresh tool
catalog or successful helper invocation proves worker runtime. Report an unavailable native
executor and continue the permitted parts of the task without pretending delegation occurred.

`codex_duo_prepare` is a legacy creation API. Its immutable handoff deliberately has no
workflow and reports approval_required even if today's saved coordinator_mode is
current_thread. Do not send that ID directly to plan/reserve. The normal Worker order is
**defaults → begin → plan → reserve → native spawn → complete → verify**, with no prepare step.
`codex_duo_execution_plan` only reads an existing snapshot's eligibility; `codex_duo_plan`
persists workstreams/capacity for a ready_for_native_worker snapshot. Neither runs Planner
inference. A selected_model snapshot remains blocked in the current-thread adapter and
must not be bypassed with request fields or by changing the immutable snapshot.

When prepare was used accidentally and no reservation/dispatch exists for this task,
preserve that old handoff, reuse its exact task (including task_id), and call begin with
the actual project_root and invocation=explicit under the existing user authorization.
Adding the workflow to the new snapshot changes its content-derived handoff_id; this is
not an in-place conversion. Check all matching task ledgers first. If any dispatch exists,
keep its original ledger and consumed budget; do not create a new task ID to start over.
Saved max_worker_turns is an upper bound: an explicit one-call test authorization is
stricter, even when the saved preference allows more. Preserve the original one-call cap.

begin has no request-level coordinator/model override. current_thread uses the current
chat and leaves the saved selected-coordinator pair inactive. A project override wins
over global defaults. The MCP stores project/snapshot/dispatch identities, not a trusted
host thread binding; configuration and task names cannot attest the actual coordinator
or native role. Use the actual native tool schema and receipts for that evidence.

## Global setup and project compatibility

Plugin detail settings always edit GLOBAL defaults, regardless of the configured fallback
project. The native and embedded panels explicitly select global defaults or current-project
settings, and show the active source. Global changes never modify project overrides. Global
settings are model preferences only, never a selected project or chat destination.
For user-authorized global activation, the coordinator may install this narrow block into
the actual CODEX_HOME/AGENTS.md while preserving all unrelated content:

```markdown
<!-- codex-duo-global:begin -->
## Codex Duo development workflow
For user-requested implementation or bug fixes, load the `codex-duo` skill and read
`codex_duo_defaults` with the actual current chat project cwd as explicit `project_root`.
Use this root on every codex_duo_* call. Resolve project overrides before global defaults;
manual mode or explicit no-model requests stop automatic dispatch. Only eligible development
tasks use supported native workers under the saved model, effort, maximum parallel count
and shared total turn limit, bounded by actual host capacity. Simple tasks use one worker.
Questions, read-only checks and configuration changes do not start workers. Workers must
never recurse into this workflow. Do not create chats, commit, publish or change global
configuration without a user request. Invalid saved settings fail closed.
<!-- codex-duo-global:end -->
```

Existing chats may need a skill invocation or instruction reload; installation alone does
not prove fresh runtime execution. Do not modify global instructions without authorization.

## Project setup and compatibility

The native menu is the primary directory picker and recent-projects view. The embedded panel
is pinned to the explicit root supplied by its opener; old openers without a root use only the
configured legacy fallback and do not follow chat or menu changes. Reading/switching never enables
a project. For first automatic setup the user selects automatic and explicitly saves;
`codex_duo_save` receives `enable_project=true` and the chat project_root, adding a small managed
AGENTS.md block while preserving existing instructions. Manual mode and ordinary legacy saves
do not change project instructions. Unconfigured projects inherit valid global defaults without a save or project opt-in. Without global defaults, copying models into a new project keeps manual activation.

The only skill entry is `$codex-duo`. Active tools use the legal `codex_duo_` prefix;
project state uses `.codex-duo`. Legacy state must be explicitly migrated with
`../workflow/scripts/codex_duo_workflow.py migrate --project-root <root>` before use.
Migration preserves every state byte and consumed budget; conflicts stop without overwrite.
Legacy recognition never registers old tools or roles. Existing chats may need an
instruction/tool reload; installation does not prove normal chat tool loading.

## Explicit plan-only request (independent Local session)

Saving Planner settings never launches a model. Legacy defaults remain disabled. Only
an explicit user request such as “只规划：梳理这项功能的接入步骤，不执行” enters this path.
The current chat remains coordinator; the Planner uses a dedicated official app-server
session, not a second coordinator, Worker, or role-selection fallback. Read
`../workflow/references/planner-host.md` before first use. The adapter, rather than a
caller-supplied capability report, verifies effective host/session responses before a turn.

1. Resolve actual cwd and saved settings. Keep the goal and read scope bounded; no tests,
   builds, writes, external tools, implementation approval, or Worker dispatch. Use exact
   project-relative file paths. Prepare task JSON internally; never ask the user to copy it.
2. Call `codex_duo_planner_begin` with explicit `project_root`, `invocation=explicit`, and
   `request={schema_version:1,task_id,goal,read_paths,questions}`. Reuse this task_id throughout.
   It snapshots Git HEAD/index/worktree and Planner choice. If settings are disabled but
   the user explicitly selected a model/effort/budget for this task, pass optional
   `planner={model,reasoning_effort,max_turns}`; it does not enable or change saved defaults.
   Otherwise require saved enabled Planner settings. Never infer Planner consent from a
   saved Worker choice. Symlinks, common credential paths, oversized or unstable baselines
   fail closed; supplied context is limited to 256 KiB of UTF-8 file contents.
3. Call `codex_duo_planner_run` with this plan_id, project_root, invocation=explicit and a
   stable internal attempt_id (for example `initial`). THIS call starts a billable model
   attempt after preflight; preparation/status/save do not. The adapter reserves the
   shared task budget before launching, disables inherited plugins/MCP/apps/hooks/agents,
   and validates actual readOnly/network-disabled/approval-never and exact model/effort
   responses. It provides file contents plus an independent strict result schema. No
   custom role selection or model self-attestation is required. It does not switch this
   chat's model. Do not invoke a separate codex exec process or a root coordinator model.
4. Poll `codex_duo_planner_status` (same explicit root/plan_id) until returned, failed, blocked,
   or uncertain. A repeated run with the same attempt_id only reads the prior state.
   A persisted unfinished/uncertain attempt blocks another launch. The turn intent is
   durable BEFORE transmission: after a crash it may have been billed, so never retry
   automatically or create another ID to reset budget. The adapter writes session/turn
   receipts and permissions to the parent ledger, validates the result, and returns it
   through status; the model never writes a result file. Use `codex_duo_planner_stop` when
   the user asks to stop; cancellation acknowledgement alone is not a final receipt.
5. Show the plan in THIS chat. Result fields are schema_version=1, plan_id, dispatch_id,
   baseline_sha256, summary, steps, risks, questions, suggested_tests=[{argv,status:not_run}].
   No approval, diff, changed_paths, executed tests, or Worker evidence is accepted.
   Code changes make the plan stale. Only a later explicit implementation approval can
   enter the EXISTING Worker flow with a new ordinary contract after status revalidation.

Old native planner_reserve/complete contracts remain for compatible verified hosts, but
are not the independent-session path. Managed session records cannot be completed or
cleared by a caller-supplied receipt. Neither path automatically executes a plan.

If MCP tools have not refreshed, the installed `codex_duo_workflow.py` helper supports
planner_begin, planner_run, planner_status and planner_stop with the same explicit root.
The coordinator prepares its --request/--planner files internally; planner_run takes
--plan-id, --attempt-id, --invocation explicit and launches the SAME protected adapter.
Do not instruct users to assemble JSON or claim offline fixtures are real model execution.

#
