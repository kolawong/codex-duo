"""Offline routing regressions. No native spawn or Planner/model execution."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_native import catalog, mcp
from codex_duo_service import CodexDuoService
from codex_duo_selection import SelectionError


class CoordinatorRoutingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='duo-routing-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        env = patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'home')})
        env.start(); self.addCleanup(env.stop)
        self.project = self.root / 'project'; self.project.mkdir()
        self.service = CodexDuoService(self.project / '.codex-duo', catalog)
        self.server = mcp.MCPServer(self.service)
        self.selection = self.service.state()['default']
        self.selection['worker'] = {'model': 'gpt-6.1-sol', 'reasoning_effort': 'high'}
        self.workflow = {'activation': 'manual', 'coordinator_mode': 'current_thread', 'max_worker_turns': 1}
        self.task = copy.deepcopy(self.service.template)
        self.task['task_id'] = 'routing-fixture'

    def save(self, **kwargs):
        return self.service.save({'selection': self.selection, 'workflow': self.workflow,
                                  'expected_revision': 'none', **kwargs})

    def call(self, name, **args):
        return self.server.dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': name, 'arguments': {'project_root': str(self.project), **args}}})['result']

    def begin(self):
        result = self.call('codex_duo_begin', task=self.task, invocation='explicit')
        self.assertFalse(result.get('isError'), result)
        return result['structuredContent']

    def test_prepare_current_thread_remains_legacy_and_direct_plan_explains_recovery(self):
        saved = self.save()
        prepared = self.call('codex_duo_prepare', task=self.task, expected_revision=saved['revision'])['structuredContent']
        self.assertNotIn('workflow', prepared['manifest'])
        self.assertEqual('legacy_declarative', prepared['handoff_kind'])
        self.assertEqual('codex_duo_begin', prepared['current_thread_entry_tool'])
        old = Path(prepared['path'])
        hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in old.rglob('*') if p.is_file()}
        failure = self.call('codex_duo_plan', handoff_id=prepared['id'], host_capacity=1)
        self.assertEqual('coordinator_required', failure['structuredContent']['error']['code'])
        self.assertIn('缺少 workflow', failure['structuredContent']['error']['message'])
        self.assertIn('codex_duo_begin', failure['structuredContent']['error']['message'])
        self.assertFalse((self.service.store.directory / 'runs').exists())
        # Same task identity, no dispatch exists: begin legally creates a workflow snapshot.
        begun = self.begin()
        self.assertNotEqual(prepared['id'], begun['handoff_id'])
        self.assertEqual(self.task, begun['task'])
        plan = self.call('codex_duo_plan', handoff_id=begun['handoff_id'], host_capacity=1)
        self.assertFalse(plan.get('isError'), plan)
        self.assertEqual(0, plan['structuredContent']['dispatch_count'])
        self.assertEqual(hashes, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes})

    def test_default_coordinator_mode_uses_begin_without_changing_saved_preferences(self):
        self.service.save({'selection': self.selection, 'expected_revision': 'none'})
        before = self.service.store.path.read_bytes()
        begun = self.begin()
        self.assertEqual('ready_for_native_worker', begun['state'])
        self.assertEqual('current_thread', begun['coordinator']['mode'])
        self.assertIsNone(begun['coordinator']['selected_model'])
        self.assertEqual(before, self.service.store.path.read_bytes())

    def test_selected_model_refuses_plan_and_no_longer_suggests_unusable_next_tool(self):
        self.workflow['coordinator_mode'] = 'selected_model'; self.save()
        begun = self.begin()
        self.assertEqual('new_coordinator_required', begun['state'])
        self.assertIsNone(begun['next_tool'])
        blocked = self.call('codex_duo_plan', handoff_id=begun['handoff_id'], host_capacity=1)
        self.assertEqual('coordinator_required', blocked['structuredContent']['error']['code'])
        self.assertIn('coordinator_mode=selected_model', blocked['structuredContent']['error']['message'])
        self.assertFalse((self.service.store.directory / 'runs').exists())

    def test_request_fields_cannot_override_coordinator_policy_or_claim_thread_binding(self):
        self.workflow['coordinator_mode'] = 'selected_model'; self.save()
        begun = self.begin()
        for override in ({'coordinator_mode': 'current_thread'}, {'thread_id': 'claimed-current-thread'},
                         {'model': 'gpt-6.1-sol'}):
            result = self.call('codex_duo_plan', handoff_id=begun['handoff_id'], host_capacity=1, **override)
            self.assertEqual('invalid_arguments', result['structuredContent']['error']['code'])
        self.assertFalse((self.service.store.directory / 'runs').exists())

    def test_global_inheritance_and_project_override_route_independently(self):
        for global_mode, project_mode in [('selected_model', 'current_thread'), ('current_thread', 'selected_model')]:
            with self.subTest(global_mode=global_mode):
                global_store = self.service.defaults_store.global_store
                global_revision = global_store.read(catalog())['revision']
                self.save(scope='global', expected_revision=global_revision,
                          workflow={**self.workflow, 'coordinator_mode': global_mode})
                project_revision = self.service.store.read(catalog())['revision']
                self.save(expected_revision=project_revision, workflow={**self.workflow, 'coordinator_mode': project_mode})
                local = self.begin()
                self.assertEqual(project_mode, local['coordinator']['mode'])
                other = self.root / ('other-' + global_mode); other.mkdir()
                inherited = CodexDuoService(other / '.codex-duo', catalog)
                ready = inherited.begin({'project_root': str(other), 'task': self.task, 'invocation': 'explicit'})
                self.assertEqual(global_mode, ready['coordinator']['mode'])
                self.assertFalse(inherited.store.path.exists())

    def test_snapshot_remains_selected_after_preferences_change(self):
        self.workflow['coordinator_mode'] = 'selected_model'; saved = self.save(); old = self.begin()
        self.save(expected_revision=saved['revision'], workflow={**self.workflow, 'coordinator_mode': 'current_thread'})
        inspected = self.call('codex_duo_execution_plan', handoff_id=old['handoff_id'])['structuredContent']
        self.assertEqual('selected_model', inspected['coordinator']['mode'])
        self.assertTrue(self.call('codex_duo_plan', handoff_id=old['handoff_id'], host_capacity=1)['isError'])

    def test_independent_client_and_repeated_begin_cannot_reset_reserved_budget(self):
        self.save(); begun = self.begin(); identifier = begun['handoff_id']
        self.call('codex_duo_plan', handoff_id=identifier, host_capacity=1)
        reservation = self.call('codex_duo_reserve', handoff_id=identifier, host_capacity=1, workstream_id='main')
        self.assertEqual(0, reservation['structuredContent']['remaining_worker_turns'])
        self.server = mcp.MCPServer(CodexDuoService(self.project / '.codex-duo', catalog))
        again = self.begin(); self.assertEqual(identifier, again['handoff_id']); self.assertFalse(again['created'])
        plan = self.call('codex_duo_plan', handoff_id=identifier, host_capacity=1)['structuredContent']
        self.assertEqual(1, plan['dispatch_count']); self.assertEqual(0, plan['remaining_worker_turns'])
        retry = self.call('codex_duo_reserve', handoff_id=identifier, host_capacity=1, workstream_id='main')
        self.assertEqual('budget_exhausted', retry['structuredContent']['error']['code'])

    def test_cross_project_cannot_use_another_projects_handoff(self):
        self.save(); begun = self.begin()
        other = self.root / 'other-project'; other.mkdir()
        result = self.call('codex_duo_plan', project_root=str(other), handoff_id=begun['handoff_id'], host_capacity=1)
        self.assertEqual('invalid_handoff', result['structuredContent']['error']['code'])
        self.assertFalse((other / '.codex-duo/runs').exists())


if __name__ == '__main__': unittest.main()
