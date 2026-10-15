# Compact handoff contract, version 1

Task JSON contains schema_version=1, task_id, goal, allowed_paths, acceptance,
and tests (an array of argv arrays). Tests must be selected by the coordinator;
never execute arbitrary task argv without reviewing scope and approval.

Before a NEW automatic begin, the current chat assesses the work itself. Pass
`assessment={complexity:simple|moderate|complex, benefit:none|possible|clear,
independent:boolean, reason:string}` with a concrete reason (1..600 characters).
Missing/invalid assessment cannot prepare a new automatic handoff. Simple work,
non-independent work or no-benefit handoffs return `state=current_thread`, no
handoff_id, next_tool=null and no dispatch budget. Finish locally and verify normally.
Conservative requires complex work and clear benefit; balanced requires clear benefit;
aggressive also permits possible benefit. File/line count alone is not an assessment.
No classifier or extra Planner is launched. `invocation=explicit` means the human
explicitly requested delegation for this task (not just implementation); it takes
precedence over activity and may omit assessment. Explicit no-agent requests stay local.
Activity never changes the selected model, effort, parallel or total turn limits.

New delegated snapshots bind `delegation` (activity, invocation, assessment, decision,
reason) into the immutable hash. Repeated task IDs reuse their original decision and
budget even after settings changes; conflicting invocation/assessment is rejected.
An omitted repeat assessment reuses the original. Legacy immutable handoffs without
delegation or agent_activity retain their exact serialization and remain verifiable.
Saved settings missing agent_activity resolve to balanced without rewriting files.

begin accepts a separate optional `worker_override` object with model and/or reasoning_effort.
It is not part of task JSON and cannot change the coordinator, Planner, scope or budget.
Each field merges over project then global defaults before the resulting pair is validated.
The immutable handoff includes `worker_resolution={override,sources}` and the effective Worker
selection. Same task_id + same contract/override reuses that snapshot and ledger after restarts
or settings changes; conflicting requests fail instead of creating another budget.

`workflow.worker_strategy` is fixed (legacy default) or adaptive. `worker_profiles`
is empty in legacy/fixed settings, or has exactly light/standard/complex, each an exact
catalog-valid `{model,reasoning_effort}` pair. Adaptive requires all three. Reads never
populate or save suggestions. New snapshots bind the strategy and candidate pairs;
old snapshots keep their original bytes and hashes.

In adaptive mode without a task override, each plan stream is
`{id,task,depends_on,routing:{tier:light|standard|complex,reason:string}}`.
The current chat selects a tier and concrete reason (1..600 characters); the service
resolves that candidate from the immutable parent snapshot and persists the pair/reason
in the plan hash. Arbitrary per-stream models and effort values are rejected. Fixed mode
or an explicit task override (even one field) rejects routing and keeps the resolved task
pair. Corrections preserve the chosen pair and consume the same parent budget.
`complete` checks the recorded native parameters against that dispatch's Worker;
per-dispatch summaries never substitute the parent default for a selected candidate.

Independent workstreams may be queued at capacity 1, or run concurrently up to the
minimum of saved max_parallel_workers, initial/current reported host capacity, ready
workstreams and remaining parent turns. Overlapping ownership and cyclic dependencies
remain invalid. Plan exposes capacity, occupied reservations and waiting reasons.
The panel's execution_status is the most recently updated project task, not live host
telemetry or the current chat. Missing/invalid evidence has unknown capacity; reading
status does not create files, launch models or bind the menu project to chats.

reserve.worker is the dispatch contract: use the actual native codex_duo_worker role,
its exact model/effort and fork_turns=none. The reservation is not proof of execution.
complete may attach `native_dispatch={tool,agent_id,parameters,runtime?}`, where parameters
are the successful native call's model, reasoning_effort, agent_type and fork_turns, and
runtime contains only host-returned model/effort fields (omit absent fields). The agent_id
must equal native_receipt. Reports are coordinator-transcribed, not MCP-authenticated telemetry.
worker_summary / dispatch_summaries distinguish requested, successful_dispatch and runtime;
missing runtime fields remain not_provided even with a valid agent ID or matching config.
Identical completion is idempotent; changed terminal evidence or identity is rejected.

Worker result JSON contains schema_version=1, task_id, status (completed, failed,
or blocked), summary (at most 280 characters), changed_paths, diff (artifact),
tests (argv, exit_code, log artifact), and blockers (short strings).

An artifact is {"path": "relative/path", "sha256": "64 lowercase hex digits"}.
Paths are relative to the dedicated artifact root. Absolute paths, .. segments,
backslashes, and symlinks are rejected. allowed_paths are exact files, not globs.
The diff's +++ and --- paths must match changed_paths and stay within scope.

## Canonical diff and deterministic helpers (0.9.5)

Use UTF-8 unified text diff: `--- a/<project-relative-file>` then
`+++ b/<same-project-relative-file>`. Creation uses `--- /dev/null`, deletion
uses `+++ /dev/null`; the remaining side still needs its a/ or b/ prefix.
Never submit bare or absolute paths, .., backslashes, rename metadata, binary
patches or symlink changes. Hunk counts must match their body. A missing final LF
is represented by `\ No newline at end of file` after the affected line.

`reserve` supplies three argv arrays under `evidence_commands`. Forward them
unchanged to the Worker (not as native spawn parameters):

1. BEFORE editing, `codex_duo.py snapshot --task <child-task.json>
   --project-root <actual-canonical-project> --out <evidence-root>/before`.
2. AFTER editing, `codex_duo.py diff --task <same-task.json> --project-root <same-project>
   --baseline <evidence-root>/before --out <evidence-root>/change.diff`.
3. Save result.json with the returned `changed_paths` and `diff` reference and
   actual required test logs, then `codex_duo.py verify --task <child-task.json>
   --result <evidence-root>/result.json --root <evidence-root>` before reporting.

Snapshot hashes bind the same task, project and exact files; the helpers read
only allowed_paths, reject symlink sources, and refuse existing output paths.
They do not edit project files, invoke Git/tests/models, dispatch or accept work.
Use current pre-edit bytes, preserving other dirty changes; Git HEAD is not a
baseline for a task in a dirty checkout. Non-repository, ignored and untracked
files inside the explicit project are supported by the same scoped byte reads.
Empty-file-only creation/deletion and binary changes are unsupported; report
the limitation rather than inventing a hunk. Renames may only be represented
as separately authorized deletion+creation, with both exact paths in scope.

Example for a scoped temporary file, not an absolute filesystem path:

```diff
--- a/evidence/example/probe.txt
+++ b/evidence/example/probe.txt
@@ -1 +1 @@
-before
+after
```

A preflight pass validates data/hashes, not model provenance or semantic
acceptance. A rejection never grants another Worker call. Missing original
baseline cannot be reconstructed from guessed strings; do not rewrite a failed
run, regenerate its evidence, resubmit complete or replenish its consumed budget.

The evidence gate rejects failed or blocked results, nonzero test exits, missing
tests, different argv, changed artifact hashes, path escapes, and oversized
summaries. It parses data only and never launches a model or task command.
Hashes establish artifact consistency; they do not establish provenance.
The coordinator must independently inspect changes and rerun tests before
acceptance. Large logs and diffs stay on disk; the main-thread summary contains
references and conclusions only. User-facing errors and blockers are never hidden.

Parallel adapter contracts (0.7.0): the parent contract remains schema_version=1.
A plan is [{id, task, depends_on}], where task uses the complete contract above. Child
file scopes are exact, pairwise disjoint subsets of the parent scope. Unique IDs and
acyclic dependencies are required; consolidate conflicting ownership before planning.
An omitted plan creates one main child using the parent contract. Each dispatch gets
its own workers/<id>/dispatch-NNN evidence directory and consumes one parent turn.
plan/reserve/complete/verify use the same parent handoff_id and explicit project_root.
Host capacity means total worker slots allocatable to this parent, including its active
reservations, excluding the coordinator and other tasks; never pass idle slots alone.
Reservations are atomic and persistent; failures, initial spawns and corrections share
the same max_worker_turns and never refund it. No child begin or reset of task IDs.
Completed child evidence gates dependencies. Corrections invalidate previous child and
downstream verification. Final codex_duo_verify requires all final children plus combined
parent diff and integration test evidence. Parent changed_paths include every final
child changed path. The coordinator independently reviews and reruns checks. Native
receipts are supplied by the coordinator; data validation does not prove provenance
or intercept calls that bypass the adapter. MCP never starts a model.
Missing legacy max_parallel_workers resolves to 1 without rewriting settings. Legacy
immutable handoffs retain their original workflow serialization and artifact hashes.

## Test argv escaping

Execute reviewed tests using the JSON-decoded argv array directly with
`subprocess.run(argv, shell=False)`. Decode JSON once; never use `unicode_escape`,
replace backslash sequences, interpolate argv into shell/Python source, or rebuild
`python -c` strings. Log the actual executed argv (JSON serialization is suitable)
and actual exit code; do not copy contract argv over transformed execution evidence.
Failure remains failure and preflight rules remain mandatory.

Prefer a standalone assertion script over nested shell / `python -c` quoting.
For a new authorized task requiring exactly `after` plus LF, use this argv:

```json
["python3", "-B", "plugins/codex-duo/skills/workflow/scripts/assert_bytes.py", "evidence/example/probe.txt", "61667465720a"]
```

Run from the explicit project root (or use reviewed absolute script/file paths).
The script reads only the selected file and returns nonzero for mismatched bytes,
missing files or invalid hex. Review scope before execution. It does not write
logs/results, dispatch workers, accept evidence or alter historical contracts.
