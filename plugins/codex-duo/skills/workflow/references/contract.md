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
