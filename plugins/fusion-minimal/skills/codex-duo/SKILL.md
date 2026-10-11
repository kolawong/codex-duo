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

Defaults resolve in this order: existing project `.fusion/selection.json` (including legacy
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
Pass this exact `project_root` on **every** fusion.* tool call, including open/state/save,
settings_read/settings_update, prepare and execution_plan. Refuse ambiguous/invalid roots;
on project_mismatch stop rather than falling back. Tools are stateless across projects.
Read `fusion.defaults` at the start of each eligible user task to pick up explicit
configuration updates. Never overwrite saved preferences just because a new task starts.
Open `fusion.open` with this chat project_root only for first setup or when the user asks to view/change settings.
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
2. Build the task specification internally, using `../fusion/references/contract.md`: a unique task_id,
   goal, exact allowed_paths, acceptance criteria, and meaningful tests as argv arrays.
   Call `fusion.begin` with project_root, task, and invocation (`automatic` or `explicit`).
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
   Use fusion.plan with project_root, handoff_id, host_capacity and optional workstreams
   (array of {id, task, depends_on}). The omitted list uses the original task as one worker.
   The service persists the plan and concrete contracts without launching any model.
4. Immediately before EVERY initial native spawn or correction/follow-up, call fusion.reserve
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
   change immutable contracts, or call fusion.begin for themselves. Do not create user-owned
   chats. Wait for each result without routine interruptions. The worker writes result.json,
   change.diff and only its task's required test logs under its distinct evidence_root.
6. For each reservation call fusion.complete with project_root, handoff_id, dispatch_id,
   native_receipt (actual native ID or failure receipt) and outcome completed/failed/blocked.
   completed verifies that child's contract and hashes before releasing dependencies. If
   evidence fails, independently inspect it; record failed/blocked to release the slot and
   reserve a correction within the same total budget. A correction invalidates prior child
   completion and downstream verification; active dependent work prevents upstream edits.
   Receipts are coordinator supplied; the ledger enforces accounting for adapter calls but
   cannot intercept direct native tool calls. Never bypass reserve or claim model provenance
   from ledger/hash success alone. At exhaustion stop dispatch and report remaining work.

## Verify and report

Verify every child with `../fusion/scripts/fusion.py verify --task <task_path> --result <evidence_root>/result.json
--root <evidence_root>`. This validates identity, scope and evidence hashes; it does not
prove correctness. Independently inspect every child diff, preserve other workers changes,
then run the parent integration checks. Write the combined parent result.json, change.diff
and parent-required test logs under the ORIGINAL parent evidence_root, with all final child
changed_paths represented. Call fusion.verify with project_root and handoff_id to revalidate
every final child and the integrated parent contract. The same coordinator independently reviews the actual diff and reruns
appropriate checks. Preserve unrelated pre-existing changes. Never claim acceptance before
this review, or equate a prepared snapshot with a worker actually running.
Use short progress messages for planning, execution and verification, based on actual events.
Return the result in this chat: what changed, verification, remaining issues. Link evidence
only when useful; the user should not need to understand the internal file format.

## Older hosts and local fallback

If newly installed MCP tools are not yet discovered, use the packaged local helper with
an absolute project root (it performs no inference):

- `python3 -B <skill-dir>/../fusion/scripts/fusion_workflow.py defaults --project-root <root>`
- `python3 -B <skill-dir>/../fusion/scripts/fusion_workflow.py begin --project-root <root> --task <internally-written-task.json> --invocation automatic`
- `python3 -B <skill-dir>/../fusion/scripts/fusion_workflow.py plan --project-root <root> --handoff-id <id> --host-capacity <total slots> [--workstreams <internal.json>]`
- `python3 -B <skill-dir>/../fusion/scripts/fusion_workflow.py reserve --project-root <root> --handoff-id <id> --host-capacity <total slots> --workstream-id <id>`
- `python3 -B <skill-dir>/../fusion/scripts/fusion_workflow.py complete --project-root <root> --handoff-id <id> --dispatch-id <id> --native-receipt <actual receipt> --outcome <completed|failed|blocked>`
- `python3 -B <skill-dir>/../fusion/scripts/fusion_workflow.py verify --project-root <root> --handoff-id <id>`

This helper does not add native worker tools to the host. Do not imply that a fresh tool
catalog or successful helper invocation proves worker runtime. Report an unavailable native
executor and continue the permitted parts of the task without pretending delegation occurred.

Legacy `fusion.prepare` and `fusion.execution_plan` remain available for inspecting old
handoffs. They are not the normal user flow. No service tool itself launches a model.

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
`fusion.defaults` with the actual current chat project cwd as explicit `project_root`.
Use this root on every fusion.* call. Resolve project overrides before global defaults;
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
`fusion.save` receives `enable_project=true` and the chat project_root, adding a small managed
AGENTS.md block while preserving existing instructions. Manual mode and ordinary legacy saves
do not change project instructions. Unconfigured projects inherit valid global defaults without a save or project opt-in. Without global defaults, copying models into a new project keeps manual activation.

The only skill entry is `$codex-duo`. Internal fusion.* tool names and
.fusion storage remain unchanged. Existing chats may need an instruction/tool reload or a first
explicit `$codex-duo` call; do not promise immediate instruction injection into an open chat.

## Explicit plan-only request (optional independent Planner)

`workflow.planner_mode=plan_only` enables an **independent advisory role**, not a switch of
this chat's model and not the old `selected_model` coordinator mode. Its model, effort,
and total 1–3 turn budget are separate from Worker settings. Missing legacy fields mean
`disabled`; enabling settings alone never authorizes dispatch. Only a user's explicit
request for a plan enters this flow. Do not use `fusion.begin` for that request.

1. Inspect the actual host tool schema and documented capabilities before dispatch. It
   must enforce read-only filesystem access, deny writes, privilege escalation, external connector tools, network operations,
   and child-agent spawning; shell reads inside the enforced read-only sandbox are valid, while supporting the exact
   saved Planner model and effort. A prompt saying "read only", an ordinary writable
   native worker, a model's own capability claim, or its result is NOT enforcement. If no
   such host tool exists, stop with `readonly_host_required` and explain the missing host
   integration. Do not silently use a normal worker or relax sandbox permissions. This
   release supplies the official `fusion_planner` custom-agent companion plus an adapter
   procedure in `../fusion/references/planner-host.md`; read it before dispatch. The service
   itself is not a native sandbox launcher. Parent runtime overrides can defeat role defaults.
2. Call `fusion.planner_begin` with the explicit `project_root`, `invocation=explicit`, and
   independent `request={schema_version:1, task_id, goal, read_paths, questions}`. Use exact
   relative file paths (new files may be missing), not directories/globs. Keep the same
   task_id for retries; never reset the total budget by creating another ID. The service
   snapshots the model settings and Git HEAD/index/worktree content hashes, including
   nonignored untracked files and explicitly scoped ignored files. It cannot capture a
   constantly changing workspace; wait for unrelated edits to settle. Common credential-looking filenames (a heuristic, not secret detection), symlinks,
   submodules, non-Git roots, and oversized baselines fail closed.
3. Call `fusion.planner_reserve` immediately before each native dispatch, passing plan_id
   and `host_capabilities` derived by the coordinator from the actual discovered tool:
   tool, model, reasoning_effort, filesystem="read_only", network="disabled",
   process_execution="read_only_sandbox" (or "disabled"), writes="disabled",
   agent_spawn="disabled", approval_escalation="disabled", external_tools="disabled",
   enforcement="host". Do not fabricate these fields to make validation pass. They are
   coordinator-supplied reports, not independently authenticated attestations. This
   service cannot intercept tool calls or prove isolation/model provenance.
4. Dispatch only with those verified, host-enforced restrictions and exact returned
   model/effort, using fresh context. The Planner reads and reasons, does not run tests,
   write evidence/files, approve implementation, or spawn Worker/other agents. It returns
   its result in memory to the coordinator, never writes into `.fusion`. Only the
   coordinator invokes lifecycle tools. Every reservation consumes one total Planner
   turn, including failed spawns; an unfinished reservation survives restart.
5. Call `fusion.planner_complete` with plan_id, dispatch_id, actual native_receipt,
   outcome=completed/failed/blocked and, only for completed, result. The independent result
   contains schema_version=1, plan_id, dispatch_id, baseline_sha256, summary, steps, risks,
   questions, and suggested_tests=[{argv:[...],status:"not_run"}]. No diff, changed_paths,
   test exit code/log, claimed approval, or Worker execution evidence is accepted.
6. Show the returned plan in this chat for user review. `fusion.planner_status` rechecks
   the baseline and stored hashes. An identical duplicate completion is idempotent;
   contradictory results are rejected. Changed code makes the plan stale; do not approve
   it as current. If the user later explicitly approves implementation, first recheck
   status and independently translate the approved scope into a fresh ordinary Worker
   task via the EXISTING execution workflow. No auto-conversion or approval token exists.
   A plan_id is never an execution handoff_id. Planner results grant no authority.

The local fallback adds `planner_begin --request <internal.json> --invocation explicit`,
`planner_reserve --plan-id <id> --host-capabilities <internal.json>`,
`planner_complete --plan-id <id> --dispatch-id <id> --native-receipt <receipt>
--outcome <completed|failed|blocked> [--result <internal.json>]`, and
`planner_status --plan-id <id>`, all requiring the same explicit `--project-root`.
These helpers only record contracts; they never launch models.
