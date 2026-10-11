# Test storage is deliberately independent of the user's real Codex home.
import os as _test_os, tempfile as _test_tempfile, atexit as _test_atexit
if not _test_os.environ.get('FUSION_TEST_CODEX_HOME'):
    _test_home = _test_tempfile.TemporaryDirectory(prefix='duo-test-home-')
    _test_atexit.register(_test_home.cleanup)
    _test_os.environ['FUSION_TEST_CODEX_HOME'] = _test_home.name
_test_os.environ['CODEX_HOME'] = _test_os.environ['FUSION_TEST_CODEX_HOME']
"""Saved defaults and automatic project routing; no model calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_native import mcp, catalog
from fusion_service import FusionService
from fusion_selection import SelectionError
from fusion_selection import saved_workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch as _home_patch
        _home = _test_tempfile.TemporaryDirectory(prefix='duo-case-home-')
        self.addCleanup(_home.cleanup)
        _environment = _home_patch.dict(_test_os.environ, {'CODEX_HOME': _home.name})
        _environment.start(); self.addCleanup(_environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.service = FusionService(self.root / '.fusion', catalog)
        self.server = mcp.MCPServer(self.service)
        self.selection = self.service.state()['default']
        self.workflow = {'activation': 'automatic_project', 'coordinator_mode': 'current_thread',
                         'max_worker_turns': 3, 'max_parallel_workers': 1}
        self.task = copy.deepcopy(self.service.template)

    def tearDown(self):
        self.temp.cleanup()

    def save(self, revision='none'):
        return self.service.save({'selection': self.selection, 'workflow': self.workflow,
                                  'expected_revision': revision})

    def begin(self, invocation='automatic'):
        return self.service.begin({'project_root': str(self.root), 'task': self.task, 'invocation': invocation})

    def call(self, name, arguments):
        return self.server.dispatch({'jsonrpc':'2.0', 'id':1, 'method':'tools/call',
                                    'params':{'name': name, 'arguments': arguments}})['result']

    def test_unconfigured_defaults_is_read_only(self):
        value = self.service.defaults(str(self.root))
        self.assertFalse(value['configured'])
        self.assertEqual('setup_required', value['state'])
        self.assertFalse(self.service.store.directory.exists())

    def test_saved_defaults_survive_new_service_without_reconfiguration(self):
        saved = self.save()
        another = FusionService(self.root / '.fusion', catalog)
        before = self.service.store.path.read_bytes()
        value = another.defaults(str(self.root))
        self.assertTrue(value['configured'])
        self.assertEqual(self.selection['worker'], value['worker'])
        self.assertEqual(saved_workflow({'workflow': self.workflow}), value['workflow'])
        self.assertEqual(saved['revision'], value['revision'])
        self.assertEqual(before, self.service.store.path.read_bytes())
        self.assertIsNone(value['coordinator']['selected_model'])

    def test_daily_begin_needs_no_revision_or_model_arguments(self):
        self.save()
        before = self.service.store.path.read_bytes()
        plan = self.begin()
        self.assertEqual('ready_for_native_worker', plan['state'])
        self.assertFalse(plan['execution_started'])
        self.assertFalse(plan['coordinator']['requires_new_task'])
        self.assertEqual('gpt-6-luna', plan['worker']['model'])
        self.assertFalse(plan['worker']['fork_context'])
        self.assertEqual(3, plan['max_worker_turns'])
        self.assertEqual(self.task, json.loads(Path(plan['task_path']).read_text()))
        self.assertEqual(before, self.service.store.path.read_bytes())
        self.assertFalse(Path(plan['evidence_root']).exists())

    def test_new_task_automatically_uses_explicitly_updated_defaults(self):
        saved = self.save()
        first = self.begin()
        self.selection['worker']['reasoning_effort'] = 'medium'
        self.workflow['max_worker_turns'] = 2
        self.save(saved['revision'])
        self.task['task_id'] = 'another-task'
        second = self.begin()
        self.assertEqual('medium', second['worker']['reasoning_effort'])
        self.assertEqual(2, second['max_worker_turns'])
        original = self.service.execution_plan(first['handoff_id'])
        self.assertEqual('high', original['worker']['reasoning_effort'])
        self.assertEqual(3, original['max_worker_turns'])

    def test_repeated_prepare_is_not_an_execution_or_duplicate(self):
        self.save()
        first, second = self.begin(), self.begin()
        self.assertTrue(first['created'])
        self.assertFalse(second['created'])
        self.assertEqual(first['handoff_id'], second['handoff_id'])
        self.assertFalse(second['execution_started'])

    def test_manual_mode_rejects_automatic_but_accepts_explicit_use(self):
        self.workflow['activation'] = 'manual'
        self.save()
        with self.assertRaises(SelectionError) as err:
            self.begin()
        self.assertEqual('manual_mode', err.exception.code)
        self.assertEqual('ready_for_native_worker', self.begin('explicit')['state'])

    def test_selected_coordinator_never_silently_uses_current_thread(self):
        self.workflow['coordinator_mode'] = 'selected_model'
        self.save()
        value = self.begin()
        self.assertEqual('new_coordinator_required', value['state'])
        self.assertTrue(value['coordinator']['requires_new_task'])
        self.assertEqual(self.selection['coordinator'], value['coordinator']['selected_model'])
        self.assertFalse(value['execution_started'])

    def test_cross_project_read_and_prepare_rejected_without_writes(self):
        other = self.root / 'other'; other.mkdir()
        for action in (lambda: self.service.defaults(str(other)),
                       lambda: self.service.begin({'project_root': str(other), 'task': self.task,
                                                   'invocation': 'automatic'})):
            with self.assertRaises(SelectionError) as err:
                action()
            self.assertEqual('project_mismatch', err.exception.code)
        self.assertFalse(self.service.store.directory.exists())
        self.assertEqual([], list(other.iterdir()))

    def test_missing_config_does_not_choose_a_worker_automatically(self):
        with self.assertRaises(SelectionError) as err:
            self.begin()
        self.assertEqual('setup_required', err.exception.code)
        self.assertFalse(self.service.store.path.exists())

    def test_legacy_saved_selection_is_preserved_and_stays_manual(self):
        self.service.save({'selection': self.selection, 'expected_revision': 'none'})
        doc = json.loads(self.service.store.path.read_text()); doc.pop('workflow')
        self.service.store.path.write_text(json.dumps(doc))
        before = self.service.store.path.read_bytes()
        value = self.service.defaults(str(self.root))
        self.assertEqual('manual', value['workflow']['activation'])
        self.assertEqual(self.selection['worker'], value['worker'])
        self.assertEqual(before, self.service.store.path.read_bytes())

    def test_settings_partial_update_preserves_workflow_and_inactive_coordinator(self):
        self.service.save({'scope':'global','selection':self.selection,'workflow':self.workflow,'expected_revision':'none'})
        self.service.settings_update({'max_worker_turns':'5'})
        self.service.settings_update({'worker':'gpt-6-luna / medium'})
        doc = self.service.defaults_store.global_store.read(catalog())['document']
        self.assertEqual('automatic_project', doc['workflow']['activation'])
        self.assertEqual(5, doc['workflow']['max_worker_turns'])
        self.assertEqual(self.selection['coordinator'], doc['selection']['coordinator'])
        self.assertEqual('medium', doc['selection']['worker']['reasoning_effort'])

    def test_legacy_save_does_not_reset_new_preferences(self):
        saved = self.save()
        self.selection['worker']['reasoning_effort'] = 'medium'
        saved = self.service.save({'selection': self.selection, 'expected_revision': saved['revision']})
        self.assertEqual(saved_workflow({'workflow': self.workflow}), saved['document']['workflow'])

    def test_invalid_workflow_cannot_replace_saved_preferences(self):
        saved = self.save()
        before = self.service.store.path.read_bytes()
        for key, bad in [('activation', 'global'), ('coordinator_mode', 'switch_thread'),
                         ('max_worker_turns', 0), ('max_worker_turns', 11), ('max_worker_turns', True)]:
            workflow = {**self.workflow, key: bad}
            with self.assertRaises(SelectionError):
                self.service.save({'selection': self.selection, 'workflow': workflow,
                                   'expected_revision': saved['revision']})
        self.assertEqual(before, self.service.store.path.read_bytes())

    def test_corrupt_workflow_is_never_silently_reset(self):
        self.save()
        doc = json.loads(self.service.store.path.read_text()); doc['workflow']['max_worker_turns'] = -1
        self.service.store.path.write_text(json.dumps(doc))
        before = self.service.store.path.read_bytes()
        with self.assertRaises(SelectionError): self.service.defaults(str(self.root))
        with self.assertRaises(SelectionError): self.begin()
        self.assertEqual(before, self.service.store.path.read_bytes())

    def test_stale_window_cannot_replace_updated_workflow(self):
        saved = self.save()
        self.service.save({'selection':self.selection,'workflow':{**self.workflow,'max_worker_turns':2},'expected_revision':saved['revision']})
        self.workflow['activation'] = 'manual'
        with self.assertRaises(SelectionError) as err: self.save(saved['revision'])
        self.assertEqual('revision_conflict', err.exception.code)
        self.assertEqual(2, self.service.defaults(str(self.root))['workflow']['max_worker_turns'])

    def test_new_tools_are_discoverable_and_validate_before_writing(self):
        definitions = {t['name']:t for t in mcp.tool_definitions()}
        for name in ('fusion.defaults','fusion.begin'):
            self.assertIn('model', definitions[name]['_meta']['ui']['visibility'])
        self.assertTrue(definitions['fusion.defaults']['annotations']['readOnlyHint'])
        self.assertFalse(definitions['fusion.begin']['annotations']['readOnlyHint'])
        saved = self.save()
        for workflow in ({**self.workflow,'max_worker_turns':True}, {**self.workflow,'activation':'all'}):
            value = self.call('fusion.save', {'selection':self.selection,'workflow':workflow,
                                             'expected_revision':saved['revision']})
            self.assertTrue(value['isError'])
        value = self.call('fusion.begin', {'project_root':str(self.root),'task':self.task,'invocation':'automatic'})
        self.assertFalse(value['structuredContent']['execution_started'])

    def test_preparation_and_read_never_execute_task_commands(self):
        self.save()
        self.task['tests'] = [['touch', 'must-not-exist']]
        with patch('subprocess.run', side_effect=AssertionError('No subprocess allowed')):
            self.service.defaults(str(self.root))
            plan = self.begin()
        self.assertFalse((self.root/'must-not-exist').exists())
        self.assertFalse(plan['execution_started'])

    def test_tampered_workflow_snapshot_refused(self):
        self.save()
        value = self.begin()
        path = Path(value['handoff_path'])/'handoff.json'
        doc = json.loads(path.read_text()); doc['workflow']['max_worker_turns'] = 10
        path.write_text(json.dumps(doc))
        with self.assertRaises(SelectionError): self.service.execution_plan(value['handoff_id'])


if __name__ == '__main__':
    unittest.main()
