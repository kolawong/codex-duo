"""Isolated policy/dispatch contracts; fixtures are not native model execution."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_worker_override import catalog
from test_native import DELEGATION_ASSESSMENT, mcp
import test_parallel
from codex_duo_service import CodexDuoService
from codex_duo_selection import SelectionError, default_selection, digest, saved_workflow


class AdaptiveTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='duo-adaptive-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        env = patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'home')})
        env.start(); self.addCleanup(env.stop)
        self.service = CodexDuoService(self.root / '.codex-duo', catalog)
        self.selection = default_selection(catalog())
        self.selection['worker'] = {'model': 'gpt-6.1-sol', 'reasoning_effort': 'high'}
        self.profiles = {'light': {'model': 'gpt-6-luna', 'reasoning_effort': 'low'},
                         'standard': {'model': 'gpt-6.1-sol', 'reasoning_effort': 'high'},
                         'complex': {'model': 'gpt-6-astra', 'reasoning_effort': 'ultra'}}
        self.workflow = {'activation': 'automatic_project', 'coordinator_mode': 'current_thread',
                         'max_worker_turns': 5, 'max_parallel_workers': 3,
                         'worker_strategy': 'adaptive', 'worker_profiles': self.profiles}
        self.save(self.workflow)
        self.task = {'schema_version': 1, 'task_id': 'adaptive', 'goal': 'three independent offline fixtures',
                     'allowed_paths': ['a.py', 'b.py', 'c.py'], 'acceptance': ['verify integration'],
                     'tests': [['python3', '-V']]}

    def save(self, workflow, scope='project'):
        target = self.service.defaults_store.store(scope)
        return self.service.save({'scope': scope, 'selection': self.selection, 'workflow': workflow,
                                 'expected_revision': target.read(catalog())['revision']})

    def begin(self, **kwargs):
        self.parent = self.service.begin({'project_root': str(self.root), 'task': self.task,
            'invocation': 'automatic', 'assessment': DELEGATION_ASSESSMENT, **kwargs})
        return self.parent

    def call(self, operation, **kwargs):
        return self.service.parallel(operation, {'project_root': str(self.root),
            'handoff_id': self.parent['handoff_id'], **kwargs})

    def streams(self):
        return [{'id': sid, 'task': {**self.task, 'task_id': sid, 'allowed_paths': [sid + '.py']},
                 'depends_on': [], 'routing': {'tier': tier, 'reason': reason}}
                for sid, tier, reason in [('a', 'light', '独立重复性修改，验收标准确定'),
                    ('b', 'standard', '独立模块实现，需要局部判断'), ('c', 'complex', '复杂依赖分析与边界验证')]]

    def native(self, worker):
        return {'tool': 'offline.fixture', 'agent_id': 'fixture-agent',
                'parameters': {**{k: worker[k] for k in ('model', 'reasoning_effort')},
                               'agent_type': 'codex_duo_worker', 'fork_turns': 'none'}}

    def finish(self, reservation, outcome='failed', worker=None):
        if outcome == 'completed':
            test_parallel.ParallelTests.evidence(self, reservation['evidence_root'], reservation['task'])
        return self.call('complete', dispatch_id=reservation['id'], outcome=outcome,
                         native_receipt='fixture-agent', native_dispatch=self.native(worker or reservation['worker']))

    def test_legacy_fixed_balanced_and_reads_never_write(self):
        legacy = {k: v for k, v in self.workflow.items() if k not in ('worker_strategy', 'worker_profiles')}
        doc = json.loads(self.service.store.path.read_text()); doc['workflow'] = legacy
        self.service.store.path.write_text(json.dumps(doc))
        before = self.service.store.path.read_bytes()
        self.assertEqual('fixed', self.service.defaults(str(self.root))['workflow']['worker_strategy'])
        self.assertEqual('balanced', self.service.defaults(str(self.root))['workflow']['agent_activity'])
        state = self.service.state()
        self.assertIsNone(state['execution_status'])
        self.assertEqual({}, state['workflow']['worker_profiles'])
        self.assertEqual(self.profiles['light'], state['suggested_worker_profiles']['light'])
        self.assertEqual(self.selection['worker'], state['suggested_worker_profiles']['complex'])
        self.assertEqual(before, self.service.store.path.read_bytes())
        workflow = saved_workflow(None); workflow['worker_profiles']['bad'] = {}
        self.assertEqual({}, saved_workflow(None)['worker_profiles'])

    def test_candidates_strict_catalog_validation_and_no_partial_save(self):
        before = self.service.store.path.read_bytes()
        variants = [dict(self.workflow, worker_strategy='unknown'), dict(self.workflow, worker_profiles={}),
                    dict(self.workflow, worker_profiles=[])]
        for mutation in ('missing', 'extra', 'effort', 'model', 'wrong_type'):
            profiles = copy.deepcopy(self.profiles)
            if mutation == 'missing': profiles.pop('light')
            if mutation == 'extra': profiles['other'] = profiles['light']
            if mutation == 'effort': profiles['light']['reasoning_effort'] = 'ultra'
            if mutation == 'model': profiles['light']['model'] = 'unknown-model'
            if mutation == 'wrong_type': profiles['light'] = 'low'
            variants.append(dict(self.workflow, worker_profiles=profiles))
        for variant in variants:
            with self.subTest(variant=variant), self.assertRaises(SelectionError): self.save(variant)
            self.assertEqual(before, self.service.store.path.read_bytes())

    def test_activity_simple_tasks_never_create_adaptive_handoffs(self):
        for activity in ('conservative', 'balanced', 'aggressive'):
            self.save(dict(self.workflow, agent_activity=activity))
            response = self.begin(assessment={**DELEGATION_ASSESSMENT, 'complexity': 'simple'})
            self.assertEqual('current_thread', response['state'])
            self.assertNotIn('handoff_id', response)
        self.assertFalse((self.service.store.directory / 'handoffs').exists())

    def test_routing_required_and_cannot_supply_arbitrary_model(self):
        self.begin()
        with self.assertRaisesRegex(SelectionError, 'routing'): self.call('plan', host_capacity=3)
        for value in ({'tier': 'light'}, {'tier': 'unknown', 'reason': 'work'},
                      {'tier': 'light', 'reason': ' '}, {'tier': 'light', 'reason': 'x' * 601},
                      {'tier': 'light', 'reason': 'work', 'model': 'arbitrary'}):
            streams = self.streams(); streams[0]['routing'] = value
            with self.assertRaises(SelectionError): self.call('plan', host_capacity=3, workstreams=streams)
        self.assertFalse((Path(self.parent['evidence_root']) / 'dispatch.json').exists())

    def test_three_independent_profiles_and_per_dispatch_evidence(self):
        self.begin()
        plan = self.call('plan', host_capacity=3, workstreams=self.streams())
        self.assertEqual(3, plan['available_dispatch_slots'])
        reservations = [self.call('reserve', host_capacity=3, workstream_id=sid) for sid in ('a', 'b', 'c')]
        for tier, reservation in zip(self.profiles, reservations):
            self.assertEqual(self.profiles[tier], reservation['worker_summary']['requested'])
            self.assertEqual(tier, reservation['routing']['tier'])
        with self.assertRaisesRegex(SelectionError, '一致'):
            self.finish(reservations[0], worker=self.profiles['complex'])
        for reservation in reservations: self.finish(reservation, 'completed')
        test_parallel.ParallelTests.evidence(self, self.parent['evidence_root'], self.task)
        result = self.call('verify')
        self.assertEqual(3, result['verified_workstreams'])
        self.assertEqual(list(self.profiles.values()), [d['requested'] for d in result['dispatch_summaries']])
        self.assertTrue(all(d['runtime']['model']['status'] == 'not_provided' for d in result['dispatch_summaries']))

    def test_profiles_frozen_after_settings_change_and_failed_correction(self):
        parent = self.begin(); streams = self.streams()
        self.call('plan', host_capacity=3, workstreams=streams)
        first = self.call('reserve', host_capacity=3, workstream_id='a'); self.finish(first)
        self.save(dict(self.workflow, worker_profiles={tier: self.profiles['complex'] for tier in self.profiles}))
        self.assertEqual(parent['handoff_id'], self.begin()['handoff_id'])
        correction = self.call('reserve', host_capacity=3, workstream_id='a')
        self.assertEqual(self.profiles['light'], correction['worker_summary']['requested'])
        self.assertEqual(3, correction['remaining_worker_turns'])
        changed = copy.deepcopy(streams); changed[0]['routing']['tier'] = 'complex'
        with self.assertRaisesRegex(SelectionError, '固定'): self.call('plan', host_capacity=3, workstreams=changed)

    def test_partial_explicit_override_keeps_resolved_pair_for_all_streams(self):
        self.begin(worker_override={'reasoning_effort': 'low'})
        streams = self.streams()
        with self.assertRaisesRegex(SelectionError, '显式覆盖'): self.call('plan', host_capacity=3, workstreams=streams)
        for stream in streams: stream.pop('routing')
        self.call('plan', host_capacity=3, workstreams=streams)
        for sid in ('a', 'b', 'c'):
            worker = self.call('reserve', host_capacity=3, workstream_id=sid)['worker']
            self.assertEqual('gpt-6.1-sol', worker['model']); self.assertEqual('low', worker['reasoning_effort'])

    def test_fixed_mode_rejects_routing_and_preserves_candidates(self):
        self.save(dict(self.workflow, worker_strategy='fixed'))
        self.begin()
        with self.assertRaisesRegex(SelectionError, '固定模式'): self.call('plan', host_capacity=3, workstreams=self.streams())
        self.call('plan', host_capacity=3)
        self.assertEqual(self.selection['worker'], self.call('reserve', host_capacity=3, workstream_id='main')['worker_summary']['requested'])
        self.assertEqual(self.profiles, self.service.defaults(str(self.root))['workflow']['worker_profiles'])

    def test_saved_caps_and_host_caps_bound_all_tiers(self):
        for saved, host in ((1, 3), (2, 3), (3, 1), (3, 2), (3, 3)):
            with self.subTest(saved=saved, host=host):
                self.save(dict(self.workflow, max_parallel_workers=saved))
                self.task['task_id'] = f'limit-{saved}-{host}'; self.begin()
                self.call('plan', host_capacity=host, workstreams=self.streams())
                for sid in ('a', 'b', 'c')[:min(saved, host)]: self.call('reserve', host_capacity=host, workstream_id=sid)
                view = self.call('plan', host_capacity=host, workstreams=self.streams())
                self.assertEqual(min(saved, host), view['occupied_workers'])
                self.assertEqual(0, view['available_dispatch_slots'])
                if min(saved, host) < 3:
                    with self.assertRaises(SelectionError): self.call('reserve', host_capacity=host, workstream_id='c')
                    self.assertIn('上限' if saved <= host else '宿主容量', view['waiting_workstreams'][-1]['reason'])

    def test_dependencies_shared_budget_and_status_are_read_only(self):
        self.save(dict(self.workflow, max_worker_turns=3)); self.begin()
        streams = self.streams(); streams[1]['depends_on'] = ['a']
        self.call('plan', host_capacity=1, workstreams=streams)
        a = self.call('reserve', host_capacity=1, workstream_id='a')
        status = self.service.state()['execution_status']
        self.assertEqual(3, status['configured_max_parallel_workers'])
        self.assertEqual(1, status['reported_host_capacity']); self.assertEqual(1, status['occupied_workers'])
        self.assertEqual(2, status['queued_workstreams'])
        self.assertIn('依赖', status['waiting_workstreams'][0]['reason'])
        self.assertIsNone(self.service.state('global')['execution_status'])
        self.finish(a, 'completed')
        for sid in ('b', 'c'): self.finish(self.call('reserve', host_capacity=1, workstream_id=sid))
        before = {p: p.read_bytes() for p in self.service.store.directory.rglob('*') if p.is_file()}
        status = self.service.state()['execution_status']
        self.assertEqual(0, status['remaining_worker_turns'])
        self.assertTrue(all('用完' in item['reason'] for item in status['waiting_workstreams']))
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        with self.assertRaisesRegex(SelectionError, '用完'): self.call('reserve', host_capacity=1, workstream_id='b')

    def test_tampered_stream_or_dispatch_worker_rejected(self):
        self.begin(); self.call('plan', host_capacity=3, workstreams=self.streams())
        self.call('reserve', host_capacity=3, workstream_id='a')
        path = Path(self.parent['evidence_root']) / 'dispatch.json'; original = path.read_bytes()
        for section in ('workstreams', 'dispatches'):
            value = json.loads(original)
            key = 'worker' if section == 'workstreams' else 'requested_worker'
            value[section][0][key]['model'] = 'gpt-6-astra'
            value['plan_hash'] = digest(value['workstreams']); path.write_text(json.dumps(value))
            with self.assertRaises(SelectionError): self.call('reserve', host_capacity=3, workstream_id='b')
            self.assertIsNone(self.service.state()['execution_status'])
            path.write_bytes(original)

    def test_mcp_settings_tier_controls_and_project_precedence(self):
        self.save(dict(self.workflow, worker_strategy='fixed', worker_profiles={}), 'global')
        server = mcp.MCPServer(self.service)
        def settings(changes):
            return server.call('codex_duo_settings_update', {'project_root': str(self.root), 'set': changes})['structuredContent']['values']
        values = settings({'worker_strategy': 'adaptive'})
        self.assertEqual('gpt-6-luna / low', values['worker_profile_light'])
        values = settings({'worker_profile_complex': 'gpt-6-astra / ultra'})
        self.assertEqual('gpt-6-astra / ultra', values['worker_profile_complex'])
        before = self.service.defaults_store.global_store.path.read_bytes()
        with self.assertRaises(SelectionError): settings({'worker_profile_light': 'gpt-6-luna / ultra'})
        self.assertEqual(before, self.service.defaults_store.global_store.path.read_bytes())
        self.assertEqual(self.profiles, self.service.defaults(str(self.root))['workflow']['worker_profiles'])
        # Old editors omit new keys, preserving explicit choices.
        legacy = {k: v for k, v in self.workflow.items() if k not in ('worker_strategy', 'worker_profiles')}
        self.save(legacy)
        self.assertEqual(self.profiles, self.service.defaults(str(self.root))['workflow']['worker_profiles'])


if __name__ == '__main__': unittest.main()
