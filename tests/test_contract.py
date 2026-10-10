# Test storage is deliberately independent of the user's real Codex home.
import os as _test_os, tempfile as _test_tempfile, atexit as _test_atexit
if not _test_os.environ.get('FUSION_TEST_CODEX_HOME'):
    _test_home = _test_tempfile.TemporaryDirectory(prefix='duo-test-home-')
    _test_atexit.register(_test_home.cleanup)
    _test_os.environ['FUSION_TEST_CODEX_HOME'] = _test_home.name
_test_os.environ['CODEX_HOME'] = _test_os.environ['FUSION_TEST_CODEX_HOME']
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "fusion", ROOT / "plugins/fusion-minimal/skills/fusion/scripts/fusion.py")
fusion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fusion)


class ContractTest(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch as _home_patch
        _home = _test_tempfile.TemporaryDirectory(prefix='duo-case-home-')
        self.addCleanup(_home.cleanup)
        _environment = _home_patch.dict(_test_os.environ, {'CODEX_HOME': _home.name})
        _environment.start(); self.addCleanup(_environment.stop)

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.artifacts = Path(cls.temp.name) / "demo"
        cls.verdict = fusion.demo(cls.artifacts)
        cls.task = json.loads((cls.artifacts / "task.json").read_text())
        cls.result = json.loads((cls.artifacts / "result.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def reject(self, change):
        result = copy.deepcopy(self.result)
        change(result)
        with self.assertRaises(fusion.EvidenceError):
            fusion.verify(self.task, result, self.artifacts)

    def test_offline_red_then_green(self):
        self.assertNotEqual(self.verdict["baseline_exit_code"], 0)
        self.assertEqual(self.verdict["test_count"], 1)
        self.assertEqual(self.verdict["model_calls"], 0)

    def test_wrong_task(self):
        self.reject(lambda r: r.update(task_id="another-task"))

    def test_scope_escape(self):
        self.reject(lambda r: r.update(changed_paths=["other.py"]))

    def test_traversal(self):
        self.reject(lambda r: r["diff"].update(path="../change.diff"))

    def test_absolute_path(self):
        self.reject(lambda r: r["diff"].update(path="/tmp/change.diff"))

    def test_hash_tampering(self):
        self.reject(lambda r: r["diff"].update(sha256="0" * 64))

    def test_missing_tests(self):
        self.reject(lambda r: r.update(tests=[]))

    def test_test_command_substitution(self):
        self.reject(lambda r: r["tests"][0].update(argv=["true"]))

    def test_nonzero_exit(self):
        self.reject(lambda r: r["tests"][0].update(exit_code=1))

    def test_forged_boolean_exit(self):
        self.reject(lambda r: r["tests"][0].update(exit_code=False))

    def test_blockers(self):
        self.reject(lambda r: r.update(blockers=["approval needed"]))

    def test_failed_status(self):
        self.reject(lambda r: r.update(status="failed"))

    def test_oversized_summary(self):
        self.reject(lambda r: r.update(summary="x" * 281))

    def test_symlink(self):
        link = self.artifacts / "link.diff"
        link.symlink_to(self.artifacts / "change.diff")
        self.reject(lambda r: r["diff"].update(path="link.diff"))
        link.unlink()

    def test_existing_demo_not_overwritten(self):
        with self.assertRaises(fusion.EvidenceError):
            fusion.demo(self.artifacts)


if __name__ == "__main__":
    unittest.main()
