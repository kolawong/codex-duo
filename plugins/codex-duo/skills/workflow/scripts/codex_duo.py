#!/usr/bin/env python3
"""Offline evidence gate and deterministic demo. Standard library; no model/API calls."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


class EvidenceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def relative(value):
    require(isinstance(value, str) and value, "empty path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in value,
            "path escapes artifact scope")
    require(str(path) == value and value != ".", "path must be normalized")
    return path


def artifact(root, item):
    require(isinstance(item, dict), "artifact must be an object")
    path = relative(item.get("path"))
    expected = item.get("sha256", "")
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected),
            "invalid artifact hash")
    target = root.joinpath(*path.parts)
    cursor = root
    for part in path.parts:
        cursor = cursor / part
        require(not cursor.is_symlink(), "symlink artifact rejected")
    require(target.resolve().is_relative_to(root.resolve()) and target.is_file(),
            "artifact missing or outside root")
    require(hashlib.sha256(target.read_bytes()).hexdigest() == expected,
            "artifact hash mismatch")
    return target


def argv_valid(value):
    return (isinstance(value, list) and bool(value)
            and all(isinstance(x, str) and x and "\x00" not in x for x in value))


def diff_paths(text):
    """Parse paired unified headers and hunk counts; never reinterpret bare paths."""
    lines, paths, index = text.splitlines(), set(), 0
    while index < len(lines):
        line = lines[index]
        require(not line.startswith(("GIT binary patch", "Binary files", "rename from ",
                                     "rename to ", "new file mode 120000")),
                "unsupported binary, rename, or symlink diff")
        if not line.startswith("--- "):
            require(not line.startswith(("+++ ", "@@ ", "\\ No newline")), "unpaired diff header or hunk")
            index += 1
            continue
        require(index + 1 < len(lines) and lines[index + 1].startswith("+++ "), "missing paired +++ diff header")
        names = []
        for header, prefix in [(line, "a/"), (lines[index + 1], "b/")]:
            name = header[4:].split("\t", 1)[0]
            if name == "/dev/null":
                names.append(None)
                continue
            require(name.startswith(prefix), "invalid diff path prefix: --- requires a/, +++ requires b/ "
                    "(or /dev/null). Use codex_duo.py snapshot then diff; do not repair submitted evidence.")
            relative(name[2:]); names.append(name[2:])
        old, new = names
        require(old is not None or new is not None, "both diff paths are /dev/null")
        require(old is None or new is None or old == new, "unsupported rename diff")
        name = new if new is not None else old
        require(name not in paths, "duplicate diff file header")
        paths.add(name); index += 2
        hunks = 0
        while index < len(lines) and lines[index].startswith("@@ "):
            match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*", lines[index])
            require(match is not None, "malformed diff hunk")
            old_count = int(match[2]) if match[2] is not None else 1
            new_count = int(match[4]) if match[4] is not None else 1
            require(old is not None or old_count == 0, "addition hunk contains old content")
            require(new is not None or new_count == 0, "deletion hunk contains new content")
            require(old_count or new_count, "empty diff hunk")
            index += 1; hunks += 1
            while old_count or new_count:
                require(index < len(lines), "truncated diff hunk")
                body = lines[index]
                require(body.startswith((" ", "+", "-")), "malformed diff hunk body")
                if body.startswith((" ", "-")): old_count -= 1
                if body.startswith((" ", "+")): new_count -= 1
                require(old_count >= 0 and new_count >= 0, "diff hunk line count mismatch")
                index += 1
                if index < len(lines) and lines[index] == "\\ No newline at end of file": index += 1
            require(index >= len(lines) or not lines[index].startswith((" ", "+", "-"))
                    or lines[index].startswith("--- "), "diff hunk line count mismatch")
        require(hunks > 0, "diff lacks hunks")
    require(paths, "diff lacks file headers")
    return paths


def canonical_diff(path, before, after):
    """UTF-8 text bytes (None = absent); preserve LF/CRLF and missing final LF."""
    relative(path)
    require(not any(c in path for c in "\r\n\t\x00"), "diff path contains control characters")
    def lines(value):
        if value is None: return []
        require(isinstance(value, bytes) and b"\x00" not in value, "unsupported binary content")
        try: return value.decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError as exc: raise EvidenceError("unsupported non-UTF-8 content") from exc
    patch = difflib.unified_diff(lines(before), lines(after),
        fromfile="/dev/null" if before is None else "a/" + path,
        tofile="/dev/null" if after is None else "b/" + path)
    result = "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in patch)
    require(result, "no text changes (empty-file-only creation/deletion is unsupported)")
    require(diff_paths(result) == {path}, "generated diff path mismatch")
    return result


def scoped_file(project, name):
    relative(name)
    target = project
    for part in PurePosixPath(name).parts:
        target = target / part
        require(not target.is_symlink(), "symlink source rejected")
    require(target.resolve().is_relative_to(project), "source path escapes project")
    if not target.exists(): return None
    require(target.is_file(), "source is not a regular file")
    return target.read_bytes()


def evidence_task(task):
    from codex_duo_selection import validate_task, SelectionError
    try: return validate_task(task)
    except SelectionError as exc: raise EvidenceError(str(exc)) from exc


def evidence_snapshot(task, project_root, out):
    from codex_duo_selection import digest
    task = evidence_task(task)
    project = Path(project_root)
    require(project.is_absolute() and project.is_dir() and project == project.resolve(), "project root must be canonical and absolute")
    contents = {name: scoped_file(project, name) for name in task['allowed_paths']}
    for content in contents.values():
        if content is not None:
            require(b'\x00' not in content, "unsupported binary content")
            try: content.decode('utf-8')
            except UnicodeDecodeError as exc: raise EvidenceError("unsupported non-UTF-8 content") from exc
    out = Path(out)
    require(not out.exists() and not out.is_symlink(), "snapshot output exists; never overwrite a baseline")
    require(out.parent.resolve() == out.parent.absolute(), "snapshot parent must be canonical, without symlinks")
    out.mkdir(parents=True)
    files = {}
    for name, content in contents.items():
        if content is None: files[name] = {'exists': False}
        else:
            path = out / 'files' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
            files[name] = {'exists': True, **reference(path, out)}
    write_json(out / 'snapshot.json', {'schema_version': 1, 'project_root': str(project),
        'task_sha256': digest(task), 'files': files})
    return {'status': 'snapshot_saved', 'path': str(out.resolve()), 'model_calls': 0}


def evidence_diff(task, project_root, baseline, out):
    from codex_duo_selection import digest
    task = evidence_task(task); project = Path(project_root)
    require(project.is_absolute() and project.is_dir() and project == project.resolve(), "project root must be canonical and absolute")
    baseline = Path(baseline)
    require(baseline.is_dir() and baseline.resolve() == baseline.absolute(), "invalid snapshot root")
    manifest_path = baseline / 'snapshot.json'; require(not manifest_path.is_symlink(), "symlink snapshot rejected")
    manifest = json.loads(manifest_path.read_text())
    require(isinstance(manifest, dict) and manifest.get('schema_version') == 1 and manifest.get('project_root') == str(project)
            and manifest.get('task_sha256') == digest(task), "snapshot project or task mismatch")
    require(isinstance(manifest.get('files'), dict) and set(manifest['files']) == set(task['allowed_paths']), "snapshot file scope mismatch")
    patches, changed = [], []
    for name in task['allowed_paths']:
        entry = manifest['files'][name]
        require(isinstance(entry, dict) and type(entry.get('exists')) is bool, "invalid snapshot entry")
        before = artifact(baseline, entry).read_bytes() if entry['exists'] else None
        after = scoped_file(project, name)
        if before != after:
            patches.append(canonical_diff(name, before, after)); changed.append(name)
    require(changed, "no scoped changes; do not submit completed evidence")
    out = Path(out)
    require(not out.exists() and not out.is_symlink(), "diff output exists; never repair submitted evidence")
    require(out.parent.is_dir() and out.parent.resolve() == out.parent.absolute(), "diff parent must be canonical, without symlinks")
    with out.open('x', encoding='utf-8', newline='') as handle: handle.write(''.join(patches))
    return {'status': 'diff_saved_not_accepted', 'changed_paths': changed,
            'diff': reference(out, out.parent), 'model_calls': 0, 'requires_coordinator_review': True}


def verify(task, result, root):
    """Validate data/evidence, not semantic correctness or model provenance."""
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "invalid artifact root")
    require(task.get("schema_version") == result.get("schema_version") == 1,
            "unsupported contract version")
    require(isinstance(task.get("task_id"), str) and task["task_id"], "missing task id")
    require(task["task_id"] == result.get("task_id"), "wrong task id")
    require(isinstance(task.get("goal"), str) and task["goal"], "missing goal")
    require(isinstance(task.get("acceptance"), list) and task["acceptance"]
            and all(isinstance(x, str) and x for x in task["acceptance"]),
            "missing acceptance criteria")
    allowed = task.get("allowed_paths")
    require(isinstance(allowed, list) and allowed, "missing file scope")
    for path in allowed:
        relative(path)
    changed = result.get("changed_paths")
    require(isinstance(changed, list) and changed, "missing changed paths")
    for path in changed:
        relative(path)
    require(len(changed) == len(set(changed)) and set(changed) <= set(allowed),
            "changed paths exceed scope or repeat")
    require(result.get("status") in ["completed", "failed", "blocked"], "invalid status")
    require(result.get("status") == "completed", "worker did not complete")
    require(result.get("blockers") == [], "unresolved blockers")
    summary = result.get("summary")
    require(isinstance(summary, str) and 0 < len(summary) <= 280, "invalid summary length")
    diff = artifact(root, result.get("diff"))
    require(diff_paths(diff.read_bytes().decode('utf-8')) == set(changed), "diff paths do not match reported changes")
    expected = task.get("tests")
    require(isinstance(expected, list) and expected and all(argv_valid(x) for x in expected),
            "missing or malformed required tests")
    tests = result.get("tests")
    require(isinstance(tests, list) and len(tests) == len(expected), "missing test evidence")
    require(all(isinstance(x, dict) for x in tests), "malformed test evidence")
    require([x.get("argv") for x in tests] == expected, "test argv differs from task")
    for test in tests:
        require(type(test.get("exit_code")) is int and test["exit_code"] == 0,
                "test failed or exit code missing")
        artifact(root, test.get("log"))
    return {"status": "evidence_valid", "task_id": task["task_id"], "summary": summary,
            "changed_paths": changed, "test_count": len(tests), "diff": result["diff"]["path"],
            "blockers": [], "requires_coordinator_review": True}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def reference(path, root):
    return {"path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def demo(out):
    out = Path(out)
    require(not out.exists(), "demo output exists; choose a new directory")
    out.mkdir(parents=True)
    work = out / "workspace"
    work.mkdir()
    task = json.loads((Path(__file__).parent.parent / "templates/task.json").read_text())
    write_json(out / "task.json", task)
    before = "def add(a, b):\n    return a - b\n"
    after = "def add(a, b):\n    return a + b\n"
    target = work / "math_ops.py"
    target.write_text(before)
    (work / "test_math_ops.py").write_text(
        "import unittest\nfrom math_ops import add\n\n"
        "class AdditionTest(unittest.TestCase):\n"
        "    def test_positive(self):\n        self.assertEqual(add(2, 3), 5)\n"
        "    def test_negative(self):\n        self.assertEqual(add(-2, -3), -5)\n")
    baseline = subprocess.run(task["tests"][0], cwd=work, capture_output=True, text=True)
    (out / "baseline-test.log").write_text(baseline.stdout + baseline.stderr)
    require(baseline.returncode != 0, "fixture should fail before the change")
    # Deterministic local fixture edit. This is not a model/worker execution.
    target.write_text(after)
    patch = out / "change.diff"
    patch.write_text(canonical_diff("math_ops.py", before.encode(), after.encode()))
    run = subprocess.run(task["tests"][0], cwd=work, capture_output=True, text=True)
    log = out / "tests.log"
    log.write_text(run.stdout + run.stderr)
    result = {"schema_version": 1, "task_id": task["task_id"], "status": "completed",
              "summary": "Offline fixture: corrected addition; 2 tests passed. No model called.",
              "changed_paths": ["math_ops.py"], "diff": reference(patch, out),
              "tests": [{"argv": task["tests"][0], "exit_code": run.returncode,
                         "log": reference(log, out)}], "blockers": []}
    write_json(out / "result.json", result)
    verdict = verify(task, result, out)
    verdict.update({"mode": "offline_fixture", "model_calls": 0,
                    "baseline_exit_code": baseline.returncode})
    write_json(out / "acceptance.json", verdict)
    return verdict


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    d = commands.add_parser("demo")
    d.add_argument("--out", required=True)
    v = commands.add_parser("verify")
    v.add_argument("--task", required=True)
    v.add_argument("--result", required=True)
    v.add_argument("--root", required=True)
    p = commands.add_parser("prepare", help="Prepare a saved model selection and task; never launch it")
    p.add_argument("--selection", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--out", required=True)
    for command in ('snapshot', 'diff'):
        helper = commands.add_parser(command, help='Deterministic scoped text evidence; no tests or models')
        helper.add_argument('--task', required=True)
        helper.add_argument('--project-root', required=True)
        helper.add_argument('--out', required=True)
        if command == 'diff': helper.add_argument('--baseline', required=True)
    args = parser.parse_args()
    try:
        if args.command == "demo":
            verdict = demo(args.out)
        elif args.command in ('snapshot', 'diff'):
            task = json.loads(Path(args.task).read_text())
            verdict = (evidence_snapshot(task, args.project_root, args.out) if args.command == 'snapshot' else
                       evidence_diff(task, args.project_root, args.baseline, args.out))
        elif args.command == "prepare":
            from codex_duo_selection import read_catalog, prepare_handoff
            saved = Path(args.selection).read_bytes()
            document = json.loads(saved)
            if document.get("schema_version") != 1:
                raise EvidenceError("unsupported selection version")
            prepared = prepare_handoff(json.loads(Path(args.task).read_text()), document["selection"],
                                       read_catalog(), args.out, hashlib.sha256(saved).hexdigest())
            verdict = {"status": "prepared_not_started", "path": prepared["path"],
                       "created": prepared["created"], "execution_started": False}
        else:
            verdict = verify(json.loads(Path(args.task).read_text()),
                             json.loads(Path(args.result).read_text()), args.root)
        print(json.dumps(verdict, ensure_ascii=False))
    except (EvidenceError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
