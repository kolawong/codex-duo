"""Offline task override, immutable identity and evidence boundaries. No model calls."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_native import mcp, ROOT
import test_parallel
from codex_duo_service import CodexDuoService
from codex_duo_selection import SelectionError, normalize_catalog, presets, default_selection, prepare_handoff


def catalog():
    return normalize_catalog({'models': [
        {'slug': model, 'visibility': 'list', 'supported_reasoning_levels': [{'effort': e} for e in efforts],
         'default_reasoning_level': 'high'} for model, efforts in [
             ('gpt-6-astra', ['high', 'ultra']), ('gpt-6.1-sol', ['low', 'high']),
             ('gpt-6-luna', ['low', 'high'])]]})


class WorkerOverrideTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='duo-override-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        env = patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'home')})
        env.start(); self.addCleanup(env.stop)
        self.service = CodexDuoService(self.root / '.codex-duo', catalog)
        self.selection = default_selection(catalog())
        self.selection['worker'] = {'model': 'gpt-6.1-sol', 'reasoning_effort': 'high'}
        self.light = {'model': 'gpt-6-luna', 'reasoning_effort': 'low'}
        self.workflow = {'activation': 'automatic_project', 'coordinator_mode': 'current_thread',
                         'max_worker_turns': 1, 'max_parallel_workers': 1}
        for scope in ('global', 'project'):
            self.service.save({'scope': scope, 'selection': self.selection,
                'workflow': self.workflow, 'expected_revision': 'none'})
        self.settings_before = {p: p.read_bytes() for p in (
            self.service.store.path, self.service.defaults_store.global_store.path)}
        self.task = {'schema_version': 1, 'task_id': 'one', 'goal': 'offline bounded change',
                     'allowed_paths': ['probe.txt'], 'acceptance': ['after'], 'tests': [['python3', '-V']]}

    def call(self, name, **args):
        response = mcp.MCPServer(self.service).call('codex_duo_' + name, {'project_root': str(self.root), **args})
        return response['structuredContent']

    def begin(self, task_id='one', **args):
        return self.call('begin', task={**self.task, 'task_id': task_id}, invocation='explicit', **args)

    def reserve(self, begun):
        self.call('plan', handoff_id=begun['handoff_id'], host_capacity=1)
        return self.call('reserve', handoff_id=begun['handoff_id'], workstream_id='main', host_capacity=1)

    def finish(self, begun, reservation, **args):
        return self.call('complete', handoff_id=begun['handoff_id'], dispatch_id=reservation['id'],
                         native_receipt='offline-agent-fixture', outcome='failed', **args)

    def report(self, **runtime):
        return {'tool': 'offline.spawn', 'agent_id': 'offline-agent-fixture',
                'parameters': {**self.light, 'agent_type': 'codex_duo_worker', 'fork_turns': 'none'},
                **({'runtime': runtime} if runtime else {})}

    def assert_settings_unchanged(self):
        self.assertEqual(self.settings_before, {p: p.read_bytes() for p in self.settings_before})

    def test_preset_appends_without_changing_default_and_only_changes_worker_draft(self):
        options = presets(catalog())
        self.assertEqual(['deep', 'balanced', 'consistent', 'light'], [p['id'] for p in options])
        self.assertEqual('deep', options[0]['id'])
        self.assertTrue(options[-1]['worker_only'])
        self.assertEqual(self.light, options[-1]['selection']['worker'])
        self.assertNotIn('workflow', options[-1])
        self.assertEqual(options[0]['selection'], default_selection(catalog()))
        # A new preset must not become a default even when old presets are unsupported.
        limited = normalize_catalog({'models': [{'slug': 'gpt-6-luna', 'visibility': 'list',
            'supported_reasoning_levels': [{'effort': 'high'}, {'effort': 'low'}], 'default_reasoning_level': 'high'}]})
        self.assertEqual(['light'], [p['id'] for p in presets(limited)])
        self.assertEqual('high', default_selection(limited)['worker']['reasoning_effort'])
        self.assert_settings_unchanged()

    def test_no_override_uses_project_and_next_task_restores_default(self):
        first = self.begin()
        self.assertEqual(self.selection['worker'], first['worker_summary']['requested'])
        self.assertEqual({'model': 'project', 'reasoning_effort': 'project'}, first['worker_summary']['sources'])
        overridden = self.begin('two', worker_override=self.light)
        self.assertEqual(self.light, overridden['worker_summary']['requested'])
        third = self.begin('three')
        self.assertEqual(first['worker'], third['worker'])
        self.assertEqual('return', third['completion_mode'])
        self.assert_settings_unchanged()

    def test_complete_override_reaches_plan_reserve_contract_and_receipt(self):
        begun = self.begin(worker_override=self.light)
        plan = self.call('plan', handoff_id=begun['handoff_id'], host_capacity=1)
        reservation = self.reserve(begun)
        for response in (begun, plan, reservation):
            self.assertEqual(self.light, response['worker_summary']['requested'])
            self.assertEqual({'model': 'task_override', 'reasoning_effort': 'task_override'}, response['worker_summary']['sources'])
            self.assertEqual('codex_duo_worker', response['worker']['agent_type'])
            self.assertEqual('none', response['worker']['fork_turns'])
            self.assertFalse(response['execution_started'])
        manifest = json.loads((Path(begun['handoff_path']) / 'handoff.json').read_text())
        self.assertEqual(self.light, manifest['selection']['worker'])
        self.assertIn('model = "gpt-6-luna"', (Path(begun['handoff_path']) / 'config/codex_duo_worker.toml').read_text())
        ledger = json.loads((Path(begun['evidence_root']) / 'dispatch.json').read_text())
        self.assertEqual(reservation['worker'], ledger['dispatches'][0]['requested_worker'])
        done = self.finish(begun, reservation, native_dispatch=self.report())
        summary = done['dispatch_summaries'][0]
        self.assertEqual(self.light['model'], summary['successful_dispatch']['model'])
        self.assertEqual('not_provided', summary['runtime']['model']['status'])
        self.assertIsNone(summary['runtime']['model']['value'])
        self.assertEqual(0, done['remaining_worker_turns'])
        self.assert_settings_unchanged()

    def test_single_fields_merge_independently(self):
        for key, value in self.light.items():
            begun = self.begin(key, worker_override={key: value})
            expected = {**self.selection['worker'], key: value}
            self.assertEqual(expected, begun['worker_summary']['requested'])
            self.assertEqual('task_override', begun['worker_summary']['sources'][key])
            other = 'model' if key == 'reasoning_effort' else 'reasoning_effort'
            self.assertEqual('project', begun['worker_summary']['sources'][other])
        self.assert_settings_unchanged()

    def test_global_inheritance_sources(self):
        self.service.store.path.unlink()
        begun = self.begin(worker_override={'reasoning_effort': 'low'})
        self.assertEqual({'model': 'global', 'reasoning_effort': 'task_override'}, begun['worker_summary']['sources'])
        self.assertEqual(self.selection['worker']['model'], begun['worker']['model'])

    def test_invalid_final_pair_rejected_before_snapshot_or_reservation(self):
        for override in ({'reasoning_effort': 'ultra'}, {'model': 'missing'}, {'model': 'gpt-6-luna', 'reasoning_effort': 'ultra'}):
            with self.assertRaises(SelectionError): self.begin(worker_override=override)
        self.assertFalse((self.service.store.directory / 'handoffs').exists())
        self.assertFalse((self.service.store.directory / 'runs').exists())
        self.assert_settings_unchanged()

    def test_invalid_defaults_do_not_poison_full_override_but_unresolved_invalid_field_fails(self):
        for p in self.settings_before:
            doc = json.loads(p.read_text())
            doc['selection']['worker'] = {'model': 'retired', 'reasoning_effort': 'obsolete'}
            p.write_text(json.dumps(doc))
        before = {p: p.read_bytes() for p in self.settings_before}
        self.assertEqual(self.light, self.begin(worker_override=self.light)['worker_summary']['requested'])
        for args in ({}, {'worker_override': {'model': 'gpt-6-luna'}}, {'worker_override': {'reasoning_effort': 'low'}}):
            with self.assertRaises(SelectionError): self.begin('bad', **args)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_invalid_shadowed_global_worker_does_not_block_valid_project(self):
        p = self.service.defaults_store.global_store.path
        doc = json.loads(p.read_text()); doc['selection']['worker']['model'] = 'retired'
        p.write_text(json.dumps(doc))
        self.assertEqual(self.selection['worker'], self.begin()['worker_summary']['requested'])

    def test_corrupt_workflow_or_json_is_not_bypassed(self):
        p = self.service.store.path
        original = p.read_bytes()
        doc = json.loads(original); doc['workflow']['max_worker_turns'] = 99
        for raw in (json.dumps(doc).encode(), b'{broken'):
            p.write_bytes(raw)
            with self.assertRaises(SelectionError): self.begin(worker_override=self.light)

    def test_duplicate_and_conflict_preserve_snapshot_and_exhausted_budget_after_restart(self):
        begun = self.begin(worker_override=self.light)
        reservation = self.reserve(begun)
        self.finish(begun, reservation)
        paths = list(Path(begun['handoff_path']).rglob('*')) + [Path(begun['evidence_root']) / 'dispatch.json']
        before = {p: p.read_bytes() for p in paths if p.is_file()}
        self.service = CodexDuoService(self.root / '.codex-duo', catalog)
        repeated = self.begin(worker_override=self.light)
        self.assertEqual(begun['handoff_id'], repeated['handoff_id'])
        self.assertFalse(repeated['created'])
        for args in ({}, {'worker_override': {'model': 'gpt-6.1-sol'}}, {'worker_override': {'reasoning_effort': 'high'}}):
            with self.assertRaises(SelectionError) as error: self.begin(**args)
            self.assertEqual('task_conflict', error.exception.code)
        with self.assertRaises(SelectionError) as error:
            self.call('begin', task={**self.task, 'goal': 'other'}, invocation='explicit', worker_override=self.light)
        self.assertEqual('task_conflict', error.exception.code)
        with self.assertRaises(SelectionError) as error: self.reserve(begun)
        self.assertEqual('budget_exhausted', error.exception.code)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assert_settings_unchanged()

    def test_saved_changes_cannot_change_started_task_even_without_override(self):
        begun = self.begin()
        reservation = self.reserve(begun)
        saved = self.service.store.read(catalog())
        self.service.save({'selection': {**self.selection, 'worker': self.light}, 'workflow': {**self.workflow, 'max_worker_turns': 10},
                           'expected_revision': saved['revision']})
        repeated = self.begin()
        self.assertEqual(begun['handoff_id'], repeated['handoff_id'])
        self.assertEqual(begun['worker'], repeated['worker'])
        self.assertEqual(1, repeated['max_worker_turns'])
        self.assertEqual(0, self.finish(begun, reservation)['remaining_worker_turns'])
        self.assertEqual(self.light, self.begin('next')['worker_summary']['requested'])

    def test_concurrent_new_tasks_are_isolated_and_same_id_conflicts(self):
        def run(task_id, override):
            service = CodexDuoService(self.root / '.codex-duo', catalog)
            return service.begin({'project_root': str(self.root), 'invocation': 'explicit',
                'task': {**self.task, 'task_id': task_id}, 'worker_override': override})
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda args: run(*args), [('left', self.light), ('right', self.selection['worker'])]))
        self.assertNotEqual(results[0]['handoff_id'], results[1]['handoff_id'])
        for result, expected in zip(results, [self.light, self.selection['worker']]):
            self.assertEqual(expected, self.reserve(result)['worker_summary']['requested'])
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(run, 'shared', override) for override in (self.light, self.selection['worker'])]
            self.assertEqual(1, sum(f.exception() is None for f in futures))
            self.assertEqual(['task_conflict'], [f.exception().code for f in futures if f.exception()])
        self.assert_settings_unchanged()

    def test_summary_never_infers_runtime_from_receipt_or_config(self):
        begun = self.begin(worker_override=self.light)
        self.assertIsNone(begun['worker_summary']['successful_dispatch'])
        done = self.finish(begun, self.reserve(begun))
        summary = done['dispatch_summaries'][0]
        self.assertIsNone(summary['successful_dispatch'])
        self.assertEqual({'status': 'not_provided', 'value': None}, summary['runtime']['model'])

    def test_partial_runtime_report_and_mismatch_stay_honest_and_terminal_immutable(self):
        begun = self.begin(worker_override=self.light); reservation = self.reserve(begun)
        report = self.report(model='host-reported-different-model')
        done = self.finish(begun, reservation, native_dispatch=report)
        summary = done['dispatch_summaries'][0]
        self.assertTrue(summary['runtime_mismatch'])
        self.assertEqual('host-reported-different-model', summary['runtime']['model']['value'])
        self.assertEqual('not_provided', summary['runtime']['reasoning_effort']['status'])
        self.assertEqual(done, self.finish(begun, reservation, native_dispatch=report))
        with self.assertRaises(SelectionError): self.finish(begun, reservation, native_dispatch=self.report())
        with self.assertRaises(SelectionError): self.finish(begun, reservation)

    def test_receipt_schema_rejects_role_model_effort_or_agent_mismatch(self):
        begun = self.begin(worker_override=self.light); reservation = self.reserve(begun)
        for key, value in [('agent_type', 'default'), ('model', 'gpt-6.1-sol'), ('reasoning_effort', 'high'), ('fork_turns', 'all')]:
            report = self.report(); report['parameters'][key] = value
            with self.assertRaises(SelectionError): self.finish(begun, reservation, native_dispatch=report)
        report = self.report(); report['agent_id'] = 'other'
        with self.assertRaises(SelectionError): self.finish(begun, reservation, native_dispatch=report)
        self.assertEqual(0, self.call('plan', handoff_id=begun['handoff_id'], host_capacity=1)['remaining_worker_turns'])

    def test_completed_evidence_and_parent_verify_keep_summary(self):
        begun = self.begin(worker_override=self.light); reservation = self.reserve(begun)
        # Synthetic evidence is deliberately labeled; it tests protocol validation only.
        test_parallel.ParallelTests.evidence(self, reservation['evidence_root'], reservation['task'])
        done = self.call('complete', handoff_id=begun['handoff_id'], dispatch_id=reservation['id'],
            native_receipt='offline-agent-fixture', outcome='completed', native_dispatch=self.report())
        test_parallel.ParallelTests.evidence(self, begun['evidence_root'], begun['task'])
        verified = self.call('verify', handoff_id=begun['handoff_id'])
        self.assertEqual(done['dispatch_summaries'], verified['dispatch_summaries'])
        self.assertEqual(1, verified['dispatch_count'])
        self.assert_settings_unchanged()

    def test_existing_legacy_begin_is_reused_without_rewriting(self):
        saved = self.service.store.read(catalog())
        old = prepare_handoff(self.task, self.selection, catalog(), self.service.store.directory / 'handoffs',
                              saved['revision'], self.workflow)
        before = (Path(old['path']) / 'handoff.json').read_bytes()
        self.assertEqual(old['id'], self.begin()['handoff_id'])
        self.assertEqual(before, (Path(old['path']) / 'handoff.json').read_bytes())
        with self.assertRaises(SelectionError): self.begin(worker_override=self.light)

    def test_mcp_schema_rejects_invalid_override_shapes(self):
        for value in ({}, None, {'model': 1}, {'planner': 'disabled'}, {'model': ''}):
            with self.assertRaises(SelectionError): self.begin(worker_override=value)
        definitions = {t['name']: t for t in mcp.tool_definitions()}
        self.assertIn('worker_override', definitions['codex_duo_begin']['inputSchema']['properties'])
        self.assertNotIn('worker_override', definitions['codex_duo_begin']['inputSchema']['required'])
        self.assertIn('native_dispatch', definitions['codex_duo_complete']['inputSchema']['properties'])

    def test_cli_has_real_override_arguments(self):
        task_path = self.root / 'task.json'; task_path.write_text(json.dumps(self.task))
        command = [sys.executable, '-B', str(ROOT / 'plugins/codex-duo/skills/workflow/scripts/codex_duo_workflow.py'),
                   'begin', '--project-root', str(self.root), '--task', str(task_path), '--invocation', 'explicit',
                   '--worker-model', 'gpt-6-luna', '--worker-effort', 'low']
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        first = json.loads(result.stdout)
        self.assertEqual(self.light, first['worker_summary']['requested'])
        snapshot = Path(first['handoff_path']) / 'handoff.json'
        before = snapshot.read_bytes()
        restarted = json.loads(subprocess.run(command, capture_output=True, text=True, check=True).stdout)
        self.assertEqual(first['handoff_id'], restarted['handoff_id'])
        self.assertFalse(restarted['created'])
        self.assertEqual(before, snapshot.read_bytes())
        self.assert_settings_unchanged()
