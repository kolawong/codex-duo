---
name: fusion
description: Use when the user asks for a Fusion workflow with separately selected coordinator and worker models, compact handoff, diff, test evidence, and explicit acceptance. Supports an offline demo without model calls.
---

Keep the main thread focused on decisions and acceptance. The selected coordinator plans,
the separately configured worker executes, and the same coordinator verifies.

## Approval boundary

The prototype is offline by default. Do not launch a worker merely because this
Skill was invoked. A real dual-model run requires explicit user approval naming
the worker model, reasoning effort, task scope, and maximum worker turns. Do not
enable an unapproved model, silently substitute a model, or start a second reviewer model.
Report installation, project trust, or configuration changes before requesting
their approval. Do not modify global settings or install/trust Hooks automatically.

## Prepare

Check the current client's model catalog and native custom-agent support. Read the
approved handoff.json model selection when available; otherwise use the explicitly
approved pair. Verify both model and effort. A saved selection describes a new
coordinator task and does not change the current thread. If named TOML selection
is unavailable, report it; use explicit native parameters only when supported
and authorized, without claiming TOML auto-discovery.

Copy templates/task.json into a task-specific local artifact directory and fill
its id, goal, allowed_paths, acceptance criteria, and test argv. Give the worker
only that compact specification and necessary file references. Use a fresh
context when supported. Do not forward the parent history or full tool logs.

Custom agent TOML files are companion project configuration, not portable plugin
components. Use the supplied .codex/agents/fusion_worker.toml only within the
approved project. Never overwrite an existing custom agent or AGENTS.md.

## Execute after approval

Use one native worker at a time. Pass a bounded task; wait for its result.
The worker saves result.json, diff, and logs locally. It returns only status,
summary, changed paths, artifact references, test exit codes, and blockers.
Limit corrections to the approved turn budget. When exhausted, report blockers.
Keep meaningful progress updates brief; do not suppress failures or approval needs.

## Verify

Read references/contract.md. Use scripts/fusion.py verify with the task JSON,
result JSON, and artifact root. That gate checks identity, scope, hashes, and
test evidence. It does not prove semantic correctness: the coordinator must
inspect the diff, confirm actual changed files, rerun appropriate checks, and
compare behavior with the acceptance criteria. Reject missing evidence or an
unresolved blocker. Describe the outcome and limitations in at most 12 lines.

## Offline demonstration

Run `python3 <skill-dir>/scripts/fusion.py demo --out <new-local-directory>`.
This uses a deterministic fixture edit and unittest, never calls a model, and
refuses to overwrite a directory. Full logs stay in the output directory.
Do not describe that fixture as a real Luna run or cost-saving measurement.

## Saved model selection

The local panel, MCP App, and native structured settings share project-only
`.fusion/selection.json`. None is a switch for a running thread. When the local
MCP server is installed and connected, `fusion.open` opens the model desk;
`fusion.settings_read` and `fusion.settings_update` serve native settings.
`fusion.prepare` creates a snapshot and `fusion.execution_plan` returns a
declarative adapter for a future coordinator and worker. No tool starts a model,
sends a prompt, or grants launch permission. Do not pretend installed tools exist
until discovery confirms them. Use `scripts/fusion.py prepare --selection <saved-json>
--task <task-json> --out <handoff-directory>` to validate the pair against the
current bundled CLI catalog and prepare an immutable handoff. Preparing does not
execute task commands, launch models, install configuration, or modify this thread.
Read the generated task.json and handoff.json together; use explicit approved
model/effort settings when a later launch is authorized. All result evidence
continues through the existing verify command.
