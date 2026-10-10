---
name: codex-duo
description: Use for Codex Duo tasks and for implementation or bug-fix tasks in a project whose AGENTS.md enables Codex Duo automatic_project mode. Read the saved project defaults once per task; the current chat plans and verifies one native worker. The user need not invoke a slash command, reopen settings, write JSON, or copy a handoff. Do not use for ordinary questions, read-only checks, or worker subtasks.
---

# Configure once, use the saved defaults

Project AGENTS.md opts the project into automatic Codex Duo only after an explicit enable/save.
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

`automatic_project` plus the project instruction is the user's standing choice to use
Codex Duo for user-requested development work in this project. The current user request
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
3. Start ONE native worker with the exact returned model and reasoning effort, fresh
   context (`fork_context=false`, or the tool's documented equivalent). Map parameters
   to the discovered schema; do not pass unsupported keys. Do not rely on a named TOML
   agent that could override the explicit model. Give full bounded instructions including
   project cwd, task_path, evidence_root, relevant source references, and result contract.
   Instruct the worker not to recurse into Codex Duo or modify the immutable task snapshot.
4. The worker saves result.json, change.diff and test logs under evidence_root, and returns
   only status, summary, changed paths, evidence references, test exit codes and blockers.
   Keep full logs out of the main conversation. Wait for its result; do not interrupt it
   with routine progress messages.
5. Track native worker dispatches including corrections. At most max_worker_turns per task;
   each initial dispatch or follow-up execution counts as one. Reuse this task's snapshot
   through corrections, even if settings change. Do not reset the budget via a new task_id.
   Stop worker dispatch at the limit and report remaining work. Never silently expand scope.

## Verify and report

Use `../fusion/scripts/fusion.py verify --task <task_path> --result <evidence_root>/result.json
--root <evidence_root>`. This validates identity, scope and evidence hashes; it does not
prove correctness. The same coordinator independently reviews the actual diff and reruns
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

This helper does not add native worker tools to the host. Do not imply that a fresh tool
catalog or successful helper invocation proves worker runtime. Report an unavailable native
executor and continue the permitted parts of the task without pretending delegation occurred.

Legacy `fusion.prepare` and `fusion.execution_plan` remain available for inspecting old
handoffs. They are not the normal user flow. No service tool itself launches a model.

## Project setup and compatibility

The native menu is the primary directory picker and recent-projects view. The embedded panel
is pinned to the explicit root supplied by its opener; old openers without a root use only the
configured legacy fallback and do not follow chat or menu changes. Reading/switching never enables
a project. For first automatic setup the user selects automatic and explicitly saves;
`fusion.save` receives `enable_project=true` and the chat project_root, adding a small managed
AGENTS.md block while preserving existing instructions. Manual mode and ordinary legacy saves
do not change project instructions. Copying models into a new project keeps manual activation.

The skill is `$codex-duo`; `$fusion` is a compatibility alias. Internal fusion.* tool names and
.fusion storage remain unchanged. Existing chats may need an instruction/tool reload or a first
explicit `$codex-duo` call; do not promise immediate instruction injection into an open chat.
