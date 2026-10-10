# Compact handoff contract, version 1

Task JSON contains schema_version=1, task_id, goal, allowed_paths, acceptance,
and tests (an array of argv arrays). Tests must be selected by the coordinator;
never execute arbitrary task argv without reviewing scope and approval.

Worker result JSON contains schema_version=1, task_id, status (completed, failed,
or blocked), summary (at most 280 characters), changed_paths, diff (artifact),
tests (argv, exit_code, log artifact), and blockers (short strings).

An artifact is {"path": "relative/path", "sha256": "64 lowercase hex digits"}.
Paths are relative to the dedicated artifact root. Absolute paths, .. segments,
backslashes, and symlinks are rejected. allowed_paths are exact files, not globs.
The diff's +++ and --- paths must match changed_paths and stay within scope.

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
downstream verification. Final fusion.verify requires all final children plus combined
parent diff and integration test evidence. Parent changed_paths include every final
child changed path. The coordinator independently reviews and reruns checks. Native
receipts are supplied by the coordinator; data validation does not prove provenance
or intercept calls that bypass the adapter. MCP never starts a model.
Missing legacy max_parallel_workers resolves to 1 without rewriting settings. Legacy
immutable handoffs retain their original workflow serialization and artifact hashes.
