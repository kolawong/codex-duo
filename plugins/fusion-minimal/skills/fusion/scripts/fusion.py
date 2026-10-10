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
    diff_paths = set()
    headers = []
    for line in diff.read_text().splitlines():
        if line.startswith(("--- ", "+++ ")):
            name = line[4:].split("\t", 1)[0]
            if name == "/dev/null":
                continue
            require(name.startswith(("a/", "b/")), "invalid diff path prefix")
            name = name[2:]
            relative(name)
            diff_paths.add(name)
            headers.append(line[:3])
        require(not line.startswith(("GIT binary patch", "Binary files", "rename from ",
                                     "rename to ", "new file mode 120000")),
                "unsupported binary, rename, or symlink diff")
    require(diff_paths == set(changed) and "---" in headers and "+++" in headers,
            "diff paths do not match reported changes")
    require(any(x.startswith("@@ ") for x in diff.read_text().splitlines()), "diff lacks hunks")
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
    patch.write_text("".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                               fromfile="a/math_ops.py", tofile="b/math_ops.py")))
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
    args = parser.parse_args()
    try:
        if args.command == "demo":
            verdict = demo(args.out)
        elif args.command == "prepare":
            from fusion_selection import read_catalog, prepare_handoff
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
