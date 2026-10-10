# Test storage is deliberately independent of the user's real Codex home.
import os as _test_os, tempfile as _test_tempfile, atexit as _test_atexit
if not _test_os.environ.get('FUSION_TEST_CODEX_HOME'):
    _test_home = _test_tempfile.TemporaryDirectory(prefix='duo-test-home-')
    _test_atexit.register(_test_home.cleanup)
    _test_os.environ['FUSION_TEST_CODEX_HOME'] = _test_home.name
_test_os.environ['CODEX_HOME'] = _test_os.environ['FUSION_TEST_CODEX_HOME']
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'macos/Sources/FusionMenu/Resources/bridge.py'
spec = importlib.util.spec_from_file_location('menubar_bridge', BRIDGE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
sys.path.insert(0, str(ROOT / 'plugins/fusion-minimal/skills/fusion/scripts'))
from fusion_service import FusionService
from fusion_selection import normalize_catalog, default_selection


class MenuBarBridgeTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch as _home_patch
        _home = _test_tempfile.TemporaryDirectory(prefix='duo-case-home-')
        self.addCleanup(_home.cleanup)
        _environment = _home_patch.dict(_test_os.environ, {'CODEX_HOME': _home.name})
        _environment.start(); self.addCleanup(_environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.raw_catalog = {'models': [
            {'slug': 'local-model', 'display_name': 'Local', 'description': 'Test model',
             'visibility': 'list', 'supported_reasoning_levels': [{'effort': 'high'}, {'effort': 'low'}],
             'default_reasoning_level': 'high'}]}
        self.catalog = normalize_catalog(self.raw_catalog)
        self.service = FusionService(self.root / '.fusion', lambda: self.catalog)
        self.selection = default_selection(self.catalog)
        self.workflow = {'activation': 'automatic_project', 'coordinator_mode': 'current_thread',
                         'max_worker_turns': 5, 'max_parallel_workers': 1}
        self.cli = self.root / 'codex-test'
        self.cli.write_text('#!' + sys.executable + '\nimport json,sys\n'
                            + 'print("codex-test 1" if "--version" in sys.argv else '
                            + repr(json.dumps(self.raw_catalog)) + ')\n')
        self.cli.chmod(0o700)

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, request, root=None, unavailable=False, raw=False):
        environment = {**os.environ, 'FUSION_CODEX_CLI': '/missing/codex' if unavailable else str(self.cli)}
        process = subprocess.run([sys.executable, '-I', '-B', str(BRIDGE), '--project-root',
                                  str(self.root) if root is None else root],
                                 input=request if raw else json.dumps(request), text=True,
                                 capture_output=True, env=environment, timeout=20)
        self.assertEqual('', process.stderr)
        return process.returncode, json.loads(process.stdout)

    def body(self, revision):
        return {'selection': self.selection, 'workflow': self.workflow, 'expected_revision': revision}

    def test_read_does_not_create_or_modify_preferences(self):
        code, response = self.invoke({'operation': 'state'})
        self.assertEqual(0, code)
        self.assertEqual('none', response['data']['saved']['revision'])
        self.assertFalse((self.root / '.fusion').exists())
        saved = self.service.save(self.body('none'))
        path = self.root / '.fusion/selection.json'
        before = path.read_bytes()
        code, response = self.invoke({'operation': 'state'})
        self.assertEqual(saved['revision'], response['data']['saved']['revision'])
        self.assertEqual(before, path.read_bytes())

    def test_service_interop_in_both_directions(self):
        code, response = self.invoke({'operation': 'save', 'body': self.body('none')})
        self.assertEqual(0, code)
        saved = self.service.state()['saved']
        self.assertEqual(response['data']['revision'], saved['revision'])
        self.assertEqual(self.workflow, saved['document']['workflow'])
        self.selection['worker']['reasoning_effort'] = 'low'
        second = self.service.save(self.body(saved['revision']))
        _, response = self.invoke({'operation': 'state'})
        self.assertEqual(second['revision'], response['data']['saved']['revision'])
        self.assertEqual('low', response['data']['saved']['document']['selection']['worker']['reasoning_effort'])

    def test_global_scope_shared_service_and_project_reset(self):
        code, response = self.invoke({'operation':'save','body':{**self.body('none'),'scope':'global'}})
        self.assertEqual(code,0)
        global_revision=response['data']['revision']
        self.assertFalse(self.service.store.path.exists())
        _, state=self.invoke({'operation':'state','scope':'global'})
        self.assertEqual(state['data']['scope'],'global')
        self.assertEqual(state['data']['saved']['revision'],global_revision)
        _, project=self.invoke({'operation':'state','scope':'project'})
        self.assertEqual(project['data']['source'],'global')
        local=self.service.save({**self.body('none'),'workflow':{**self.workflow,'activation':'manual'}})
        code, restored=self.invoke({'operation':'reset','body':{'expected_revision':local['revision'],
            'expected_global_revision':global_revision}})
        self.assertEqual(code,0)
        self.assertEqual(restored['data']['source'],'global')
        self.assertFalse(self.service.store.path.exists())

    def test_stale_revision_preserves_current_file(self):
        self.service.save(self.body('none'))
        before = (self.root / '.fusion/selection.json').read_bytes()
        self.selection['worker']['reasoning_effort'] = 'low'
        code, response = self.invoke({'operation': 'save', 'body': self.body('none')})
        self.assertEqual(1, code)
        self.assertEqual('revision_conflict', response['error']['code'])
        self.assertEqual(before, (self.root / '.fusion/selection.json').read_bytes())

    def test_invalid_request_and_missing_revision(self):
        for request in ([], {'operation': 'execute'}, {'operation': 'save', 'body': {}}):
            with self.subTest(request=request):
                code, response = self.invoke(request)
                self.assertEqual(1, code)
                self.assertEqual('invalid_request', response['error']['code'])
        code, response = self.invoke('{broken', raw=True)
        self.assertEqual(1, code)
        self.assertEqual('invalid_request', response['error']['code'])
        self.assertFalse((self.root / '.fusion').exists())

    def test_relative_and_missing_projects_rejected(self):
        for value in ('relative', str(self.root / 'missing')):
            code, response = self.invoke({'operation': 'state'}, root=value)
            self.assertEqual(1, code)
            self.assertEqual('invalid_project', response['error']['code'])
        self.assertFalse((self.root / '.fusion').exists())

    def test_unavailable_catalog_is_visible_without_mutation(self):
        code, response = self.invoke({'operation': 'state'}, unavailable=True)
        self.assertEqual(0, code)
        self.assertIsNone(response['data']['catalog'])
        self.assertEqual('catalog_unavailable', response['data']['error']['code'])
        code, response = self.invoke({'operation': 'save', 'body': self.body('none')}, unavailable=True)
        self.assertEqual(1, code)
        self.assertEqual('catalog_unavailable', response['error']['code'])
        self.assertFalse((self.root / '.fusion').exists())

    def test_invalid_saved_preferences_and_recovery_use_service(self):
        (self.root / '.fusion').mkdir()
        path = self.root / '.fusion/selection.json'
        path.write_text('{broken')
        _, response = self.invoke({'operation': 'state'})
        saved = response['data']['saved']
        self.assertEqual('saved_config_invalid', saved['error']['code'])
        self.assertEqual('{broken', path.read_text())
        code, response = self.invoke({'operation': 'save', 'body': self.body(saved['revision'])})
        self.assertEqual(0, code)
        backup = self.root / '.fusion/history' / (saved['revision'] + '.json')
        self.assertEqual('{broken', backup.read_text())

    def test_project_code_cannot_shadow_shared_service(self):
        (self.root / 'fusion_service.py').write_text('raise RuntimeError("untrusted code ran")')
        code, response = self.invoke({'operation': 'state'})
        self.assertEqual(0, code)
        self.assertEqual(str(self.root), response['data']['project_root'])

    def test_packaged_bridge_does_not_fall_back_to_surrounding_checkout(self):
        location = self.root / 'Fusion Menu.app/Contents/Resources/bridge.py'
        location.parent.mkdir(parents=True)
        location.write_text('')
        with patch.object(bridge, '__file__', str(location)):
            with self.assertRaises(RuntimeError):
                bridge.service_scripts()
            bundled = location.parent / 'fusion/scripts'
            bundled.mkdir(parents=True)
            (bundled / 'fusion_service.py').write_text('')
            self.assertEqual(bundled, bridge.service_scripts())


if __name__ == '__main__':
    unittest.main()
