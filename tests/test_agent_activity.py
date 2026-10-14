"""Activity routing uses synthetic coordinator assessments; no native models run."""
import copy
import itertools
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_native import catalog, mcp, DELEGATION_ASSESSMENT
from codex_duo_selection import SelectionError, prepare_handoff
from codex_duo_service import CodexDuoService


class AgentActivityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='duo-activity-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        env = patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'home')})
        env.start(); self.addCleanup(env.stop)
        self.service = CodexDuoService(self.root / '.codex-duo', catalog)
        self.selection = self.service.state()['default']
        self.workflow = {'activation': 'automatic_project', 'coordinator_mode': 'current_thread',
                         'max_worker_turns': 3, 'max_parallel_workers': 1}
        self.task = copy.deepcopy(self.service.template)

    def save(self, activity='balanced', scope='project', **workflow):
        store = self.service.defaults_store.store(scope)
        return self.service.save({'scope': scope, 'selection': self.selection,
            'workflow': {**self.workflow, 'agent_activity': activity, **workflow},
            'expected_revision': store.read(catalog())['revision']})

    def begin(self, assessment=None, invocation='automatic', **args):
        return self.service.begin({'project_root': str(self.root), 'task': self.task,
            'invocation': invocation, **({'assessment': assessment} if assessment is not None else {}), **args})

    def assert_no_dispatch(self):
        self.assertFalse((self.service.store.directory / 'handoffs').exists())
        self.assertFalse((self.service.store.directory / 'runs').exists())

    def test_legacy_defaults_read_balanced_without_rewriting(self):
        saved = self.save()
        doc = saved['document']; doc['workflow'].pop('agent_activity')
        self.service.store.path.write_text(json.dumps(doc))
        before = self.service.store.path.read_bytes()
        for _ in range(2):
            self.assertEqual('balanced', self.service.defaults(str(self.root))['workflow']['agent_activity'])
            self.assertEqual('balanced', self.service.state()['workflow']['agent_activity'])
        self.assertEqual(before, self.service.store.path.read_bytes())
        self.assert_no_dispatch()

    def test_global_project_override_reset_and_legacy_save(self):
        global_saved = self.save('aggressive', 'global')
        before = self.service.defaults_store.global_store.path.read_bytes()
        self.assertEqual('aggressive', self.service.defaults(str(self.root))['workflow']['agent_activity'])
        local = self.save('conservative')
        self.assertEqual('conservative', self.service.defaults(str(self.root))['workflow']['agent_activity'])
        # Older clients omit the new field: editing another preference must preserve it.
        self.service.save({'selection': self.selection, 'workflow': self.workflow,
            'expected_revision': local['revision']})
        current = self.service.store.read(catalog())
        self.assertEqual('conservative', current['document']['workflow']['agent_activity'])
        self.service.reset({'project_root': str(self.root), 'expected_revision': current['revision'],
                           'expected_global_revision': global_saved['revision']})
        self.assertEqual('aggressive', self.service.defaults(str(self.root))['workflow']['agent_activity'])
        self.assertEqual(before, self.service.defaults_store.global_store.path.read_bytes())

    def test_setting_only_changes_activity_and_invalid_values_do_not_write(self):
        self.save('balanced', 'global')
        before = self.service.defaults_store.global_store.read(catalog())['document']
        for activity in ('conservative', 'aggressive', 'balanced'):
            result = self.service.settings_update({'agent_activity': activity})
            self.assertEqual(activity, result['values']['agent_activity'])
            after = self.service.defaults_store.global_store.read(catalog())['document']
            self.assertEqual(before['selection'], after['selection'])
            self.assertEqual({k: v for k, v in before['workflow'].items() if k != 'agent_activity'},
                             {k: v for k, v in after['workflow'].items() if k != 'agent_activity'})
        raw = self.service.defaults_store.global_store.path.read_bytes()
        for invalid in ('', 'active', None, True, 1, [], {}):
            with self.subTest(invalid=invalid), self.assertRaises(SelectionError):
                self.service.settings_update({'agent_activity': invalid})
        self.assertEqual(raw, self.service.defaults_store.global_store.path.read_bytes())

    def test_simple_tasks_stay_local_at_every_level_without_calls_or_budget(self):
        for activity in ('conservative', 'balanced', 'aggressive'):
            self.save(activity)
            before = self.service.store.path.read_bytes()
            with patch('subprocess.run', side_effect=AssertionError('no classifier or test execution')):
                result = self.begin({**DELEGATION_ASSESSMENT, 'complexity': 'simple'})
            self.assertEqual('current_thread', result['state'])
            self.assertEqual('local', result['delegation']['decision'])
            self.assertIsNone(result['next_tool'])
            self.assertNotIn('handoff_id', result)
            self.assertFalse(result['execution_started'])
            self.assertFalse(result['created'])
            self.assertEqual(before, self.service.store.path.read_bytes())
            self.assert_no_dispatch()

    def test_thresholds_at_service_boundary(self):
        # Explicit expected outcomes, including no-benefit and non-independent work.
        accepted = {'conservative': {('complex', 'clear')},
                    'balanced': {('moderate', 'clear'), ('complex', 'clear')},
                    'aggressive': {('moderate', 'possible'), ('moderate', 'clear'),
                                   ('complex', 'possible'), ('complex', 'clear')}}
        for activity, complexity, benefit, independent in itertools.product(
                accepted, ('simple', 'moderate', 'complex'), ('none', 'possible', 'clear'), (False, True)):
            with self.subTest(activity=activity, complexity=complexity, benefit=benefit, independent=independent):
                self.save(activity)
                self.task['task_id'] = f'{activity}-{complexity}-{benefit}-{independent}'
                result = self.begin({**DELEGATION_ASSESSMENT, 'complexity': complexity,
                                     'benefit': benefit, 'independent': independent})
                expected = independent and (complexity, benefit) in accepted[activity]
                self.assertEqual('ready_for_native_worker' if expected else 'current_thread', result['state'])
                if expected:
                    self.assertEqual(self.selection['worker'], result['worker_summary']['requested'])
                    self.assertEqual(3, result['max_worker_turns'])
                    self.assertEqual(1, result['max_parallel_workers'])
        self.assertFalse((self.service.store.directory / 'runs').exists())

    def test_missing_or_invalid_assessment_cannot_prepare_automatic_dispatch(self):
        self.save()
        with self.assertRaises(SelectionError) as error:
            self.begin()
        self.assertEqual('assessment_required', error.exception.code)
        invalid = [{}, [], 'simple', {**DELEGATION_ASSESSMENT, 'reason': ' '},
                   {**DELEGATION_ASSESSMENT, 'reason': 'a' * 601},
                   {**DELEGATION_ASSESSMENT, 'independent': 1},
                   {**DELEGATION_ASSESSMENT, 'complexity': 'tiny'},
                   {**DELEGATION_ASSESSMENT, 'benefit': 'big'},
                   {**DELEGATION_ASSESSMENT, 'force': True}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(SelectionError):
                self.begin(value)
        self.assert_no_dispatch()

    def test_explicit_delegation_overrides_activity_but_manual_blocks_auto(self):
        self.save('conservative', activation='manual')
        with self.assertRaises(SelectionError) as error:
            self.begin(DELEGATION_ASSESSMENT)
        self.assertEqual('manual_mode', error.exception.code)
        self.assert_no_dispatch()
        result = self.begin({**DELEGATION_ASSESSMENT, 'complexity': 'simple', 'benefit': 'none'}, 'explicit')
        self.assertEqual('ready_for_native_worker', result['state'])
        self.assertEqual('explicit', result['delegation']['invocation'])
        self.assertEqual(self.selection['worker'], result['worker_summary']['requested'])
        self.assertEqual(3, result['max_worker_turns'])
        self.task['task_id'] = 'explicit-no-assessment'
        self.assertEqual('delegate', self.begin(invocation='explicit')['delegation']['decision'])

    def test_decision_is_immutable_across_settings_change_and_cannot_reset_budget(self):
        self.save('aggressive')
        assessment = {**DELEGATION_ASSESSMENT, 'complexity': 'moderate', 'benefit': 'possible'}
        result = self.begin(assessment)
        base = {'project_root': str(self.root), 'handoff_id': result['handoff_id'], 'host_capacity': 1}
        self.service.parallel('plan', base)
        reserved = self.service.parallel('reserve', {**base, 'workstream_id': 'main'})
        self.service.parallel('complete', {**base, 'dispatch_id': reserved['id'],
            'native_receipt': 'offline-fixture-no-model', 'outcome': 'failed'})
        manifest_path = Path(result['handoff_path']) / 'handoff.json'
        manifest_before = manifest_path.read_bytes()
        self.save('conservative')
        again = self.begin(assessment)
        self.assertEqual(result['handoff_id'], again['handoff_id'])
        self.assertEqual('aggressive', again['delegation']['agent_activity'])
        self.assertEqual(result['handoff_id'], self.begin()['handoff_id'])
        self.assertEqual(2, self.service.parallel('plan', base)['remaining_worker_turns'])
        for kwargs in ({'assessment': DELEGATION_ASSESSMENT}, {'invocation': 'explicit'}):
            with self.assertRaises(SelectionError) as error:
                self.begin(**kwargs)
            self.assertEqual('task_conflict', error.exception.code)
        self.assertEqual(manifest_before, manifest_path.read_bytes())

    def test_legacy_handoff_without_activity_or_decision_keeps_bytes_and_identity(self):
        saved = self.save()
        legacy = prepare_handoff(self.task, self.selection, catalog(), self.service.store.directory / 'handoffs',
                                 saved['revision'], self.workflow)
        files = {p: p.read_bytes() for p in Path(legacy['path']).rglob('*') if p.is_file()}
        self.assertEqual(legacy['id'], self.service.execution_plan(legacy['id'])['handoff_id'])
        self.assertEqual(legacy['id'], self.begin()['handoff_id'])
        self.assertEqual(files, {p: p.read_bytes() for p in files})

    def test_tampered_decision_is_rejected_before_reservation(self):
        self.save()
        result = self.begin(DELEGATION_ASSESSMENT)
        path = Path(result['handoff_path']) / 'handoff.json'
        value = json.loads(path.read_text()); value['delegation']['assessment']['complexity'] = 'simple'
        path.write_text(json.dumps(value))
        with self.assertRaises(SelectionError):
            self.service.parallel('plan', {'project_root': str(self.root),
                                          'handoff_id': result['handoff_id'], 'host_capacity': 1})
        self.assertFalse(Path(result['evidence_root']).exists())

    def test_mcp_settings_schema_and_begin_enforce_gate(self):
        self.save()
        server = mcp.MCPServer(self.service)
        definitions = {tool['name']: tool for tool in mcp.tool_definitions()}
        self.assertIn('assessment', definitions['codex_duo_begin']['inputSchema']['properties'])
        self.assertIn('agent_activity', definitions['codex_duo_settings_update']['inputSchema']['properties']['set']['properties'])
        self.assertEqual(['conservative', 'balanced', 'aggressive'],
            self.service.settings_read()['schema']['properties']['agent_activity']['enum'])
        base = {'project_root': str(self.root), 'task': self.task, 'invocation': 'automatic'}
        with self.assertRaises(SelectionError) as error:
            server.call('codex_duo_begin', base)
        self.assertEqual('assessment_required', error.exception.code)
        response = server.call('codex_duo_begin', {**base, 'assessment': {**DELEGATION_ASSESSMENT, 'complexity': 'simple'}})
        self.assertEqual('current_thread', response['structuredContent']['state'])
        self.assert_no_dispatch()

    def test_cli_requires_assessment_and_local_path_does_not_create_handoff(self):
        # Exercise CLI parsing with an isolated service and deterministic catalog.
        self.save()
        from unittest.mock import patch as mock_patch
        import codex_duo_workflow
        import contextlib
        import io
        task_path = self.root / 'task.json'; task_path.write_text(json.dumps(self.task))
        assessment_path = self.root / 'assessment.json'
        assessment_path.write_text(json.dumps({**DELEGATION_ASSESSMENT, 'complexity': 'simple'}))
        argv = ['workflow', 'begin', '--project-root', str(self.root), '--task', str(task_path), '--invocation', 'automatic']
        for extra, code, state in (([], 1, 'blocked'), (['--assessment', str(assessment_path)], 0, 'current_thread')):
            output = io.StringIO()
            with mock_patch('sys.argv', argv + extra), mock_patch.object(codex_duo_workflow, 'CodexDuoService', return_value=self.service), contextlib.redirect_stdout(output):
                self.assertEqual(code, codex_duo_workflow.main())
            self.assertEqual(state, json.loads(output.getvalue())['state'])
        self.assert_no_dispatch()


if __name__ == '__main__':
    unittest.main()
