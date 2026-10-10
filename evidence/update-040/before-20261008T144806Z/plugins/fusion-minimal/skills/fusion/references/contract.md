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
