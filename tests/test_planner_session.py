"""Deterministic official-protocol fixtures; these tests never start a model."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import concurrent.futures
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/codex-duo/skills/workflow/scripts'))
from codex_duo_service import CodexDuoService
from codex_duo_selection import SelectionError, default_selection, normalize_catalog
from codex_duo_planner import PlannerExecution
from codex_duo_planner_session import SessionPlanner, restricted_command


class ProtocolFixture:
    def __init__(self, project):
        self.project, self.pending, self.calls = project, [], []
        self.config = {'sandbox_mode': 'read-only', 'approval_policy': 'never', 'allow_login_shell': False,
            'web_search': 'disabled', 'agents': {'enabled': False}, 'apps': {'_default': {'enabled': False}},
            'features': {k: False for k in ('apps', 'hooks', 'remote_plugin', 'tool_suggest', 'memories')},
            'plugins': {'fixture': {'enabled': False}}, 'mcp_servers': {'fixture': {'enabled': False}}}
        self.model, self.network, self.fail, self.raw, self.closed = 'planner', False, None, None, False

    def call(self, method, params=None):
        self.calls.append(method)
        if method == 'initialize': return {'userAgent': 'offline-protocol-fixture'}
        if method == 'config/read': return {'config': self.config}
        if method == 'thread/start': return {'cwd': str(self.project), 'model': self.model, 'reasoningEffort': 'high',
            'approvalPolicy': 'never', 'sandbox': {'type': 'readOnly', 'networkAccess': self.network},
            'thread': {'id': 'fixture-session', 'ephemeral': True}}
        if method == 'turn/start':
            self.params = params
            # The irreversible intent must be durable before any model request.
            state = next((self.project / '.codex-duo/plans').glob('*.json'))
            assert json.loads(state.read_text())['payload']['dispatches'][0]['session']['turn_committed']
            return {'turn': {'id': 'fixture-turn'}}
        if method == 'turn/interrupt': return {}
        raise AssertionError(method)

    def send(self, method, **kwargs): self.calls.append(method)

    def receive(self, timeout=1):
        if self.fail == 'lost': raise SelectionError('planner_transport_lost', 'fixture lost', 409)
        schema = self.params['outputSchema']['properties']
        result = {k: v['enum'][0] for k, v in schema.items() if 'enum' in v}
        result.update(summary='Read-only proposal', steps=['Review the change after approval'], risks=[], questions=[],
                      suggested_tests=[{'argv': ['python3', '-m', 'unittest'], 'status': 'not_run'}])
        return {'method': 'turn/completed', 'params': {'threadId': 'fixture-session', 'turn': {
            'id': 'fixture-turn', 'status': 'failed' if self.fail == 'failed' else 'completed',
            'items': [{'id': 'answer', 'type': 'agentMessage', 'text': self.raw or json.dumps(result)}]}}}

    def close(self): self.closed = True


class SessionPlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'home')}); env.start(); self.addCleanup(env.stop)
        def git(*args): subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)
        git('init', '-q'); git('config', 'user.name', 'Fixture'); git('config', 'user.email', 'fixture@example.invalid')
        (self.root / '.gitignore').write_text('.codex-duo/\nhome/\n'); (self.root / 'readme').write_text('bounded context')
        git('add', '.'); git('commit', '-qm', 'fixture')
        self.catalog = normalize_catalog({'models': [{'slug': 'planner', 'visibility': 'list', 'supported_reasoning_levels': [{'effort': 'high'}]}]})
        self.service = CodexDuoService(self.root / '.codex-duo', lambda: self.catalog)
        self.service.save({'selection': default_selection(self.catalog), 'expected_revision': 'none'})
        self.selection = (self.root / '.codex-duo/selection.json').read_bytes()
        self.request = {'schema_version': 1, 'task_id': 'fixture-plan', 'goal': 'Only propose', 'read_paths': ['readme'], 'questions': []}
        self.choice = {'model': 'planner', 'reasoning_effort': 'high', 'max_turns': 1}
        self.plan = self.service.planning('begin', {'project_root': str(self.root), 'request': self.request,
            'invocation': 'explicit', 'planner': self.choice})
        self.pid = self.plan['plan_id']; self.adapter = SessionPlanner(self.service); self.spawned = []

    def run_attempt(self):
        return self.adapter.run({'plan_id': self.pid, 'attempt_id': 'initial', 'invocation': 'explicit'},
            launch=lambda p, d: self.spawned.append((p, d)))

    def execute(self, fixture):
        self.adapter.execute(self.pid, 'planner-001', client_factory=lambda _: fixture, timeout=.1)
        return self.service.planning('status', {'project_root': str(self.root), 'plan_id': self.pid})

    def test_foreign_turn_message_cannot_satisfy_current_turn(self):
        self.run_attempt(); fixture = ProtocolFixture(self.root)
        original = fixture.receive; events = []
        def receive(timeout=1):
            if not events:
                terminal = original(timeout)
                answer = terminal['params']['turn']['items'].pop()
                events.extend([{'method': 'item/completed', 'params': {
                    'threadId': 'fixture-session', 'turnId': 'unrelated-turn', 'item': answer}}, terminal])
            return events.pop(0)
        fixture.receive = receive
        done = self.execute(fixture)
        self.assertIsNone(done['result'])
        self.assertEqual('failed', done['dispatches'][0]['status'])

    def test_explicit_choice_is_immutable_and_does_not_enable_defaults(self):
        self.assertEqual(self.selection, (self.root / '.codex-duo/selection.json').read_bytes())
        self.assertEqual('disabled', self.service.defaults(str(self.root))['planner']['mode'])
        with self.assertRaises(SelectionError):
            self.service.planning('begin', {'project_root': str(self.root), 'request': self.request, 'invocation': 'explicit',
                'planner': {**self.choice, 'max_turns': 2}})

    def test_explicit_planner_does_not_require_worker_configuration(self):
        (self.root / '.codex-duo/selection.json').unlink()
        done = self.service.planning('begin', {'project_root': str(self.root),
            'request': {**self.request, 'task_id': 'no-worker-config'}, 'invocation': 'explicit', 'planner': self.choice})
        self.assertEqual('ready_for_readonly_planner', done['state'])
        self.assertFalse((self.root / '.codex-duo/selection.json').exists())

    def test_real_protocol_shape_return_to_state_machine_and_no_worker(self):
        self.run_attempt(); fixture = ProtocolFixture(self.root); done = self.execute(fixture)
        self.assertEqual('awaiting_user_review', done['state']); self.assertFalse(done['worker_execution_allowed'])
        self.assertEqual('not_run', done['result']['suggested_tests'][0]['status'])
        self.assertEqual('fixture-session/fixture-turn', done['dispatches'][0]['native_receipt'])
        self.assertEqual('completed', done['dispatches'][0]['session']['stage'])
        self.assertTrue(fixture.closed); self.assertEqual(1, fixture.calls.count('turn/start'))
        self.assertFalse((self.root / '.codex-duo/runs').exists()); self.assertFalse((self.root / '.codex-duo/handoffs').exists())
        self.assertEqual('bounded context', (self.root / 'readme').read_text())

    def test_repeat_restart_and_second_owner_cannot_launch_or_charge_twice(self):
        self.run_attempt(); self.run_attempt(); self.assertEqual(1, len(self.spawned))
        restarted = SessionPlanner(CodexDuoService(self.root / '.codex-duo', lambda: self.catalog))
        restarted.run({'plan_id': self.pid, 'attempt_id': 'initial', 'invocation': 'explicit'}, launch=lambda *_: self.fail('relaunch'))
        done = self.execute(ProtocolFixture(self.root)); self.assertEqual(0, done['remaining_planner_turns'])
        restarted.execute(self.pid, 'planner-001', client_factory=lambda _: self.fail('second owner'))
        self.run_attempt(); self.assertEqual(1, len(self.spawned))

    def test_actual_permission_or_model_mismatch_blocks_before_model(self):
        for mismatch in ('network', 'model', 'mcp', 'agents'):
            with self.subTest(mismatch=mismatch):
                # Distinct fixture task; never a real inference retry.
                fixture = ProtocolFixture(self.root)
                if mismatch == 'network': fixture.network = True
                if mismatch == 'model': fixture.model = 'other'
                if mismatch == 'mcp': fixture.config['mcp_servers']['fixture']['enabled'] = True
                if mismatch == 'agents': fixture.config['agents']['enabled'] = True
                self.request['task_id'] = 'fixture-' + mismatch
                self.plan = self.service.planning('begin', {'project_root': str(self.root), 'request': self.request,
                    'invocation': 'explicit', 'planner': self.choice}); self.pid = self.plan['plan_id']
                self.run_attempt(); done = self.execute(fixture)
                self.assertNotIn('turn/start', fixture.calls); self.assertEqual('blocked', done['dispatches'][0]['status'])

    def test_lost_transport_stays_reserved_and_cannot_forge_completion(self):
        self.run_attempt(); fixture = ProtocolFixture(self.root); fixture.fail = 'lost'; done = self.execute(fixture)
        self.assertEqual('planner_uncertain', done['state']); self.assertEqual(0, done['remaining_planner_turns'])
        self.assertEqual('reserved', done['dispatches'][0]['status']); self.assertIn('turn/interrupt', fixture.calls)
        with self.assertRaises(SelectionError):
            self.service.planning('complete', {'project_root': str(self.root), 'plan_id': self.pid, 'dispatch_id': 'planner-001',
                'outcome': 'failed', 'native_receipt': 'fake'})
        self.run_attempt(); self.assertEqual(1, len(self.spawned))

    def test_failed_or_invalid_model_result_consumes_attempt_without_retry(self):
        self.run_attempt(); fixture = ProtocolFixture(self.root); fixture.raw = '{"approved":true}'
        done = self.execute(fixture)
        self.assertIsNone(done['result']); self.assertEqual('failed', done['dispatches'][0]['status'])
        self.assertEqual(0, done['remaining_planner_turns']); self.run_attempt(); self.assertEqual(1, len(self.spawned))

    def test_stop_before_turn_and_timeout_never_resubmit(self):
        self.run_attempt(); self.adapter.stop({'plan_id': self.pid})
        fixture = ProtocolFixture(self.root); done = self.execute(fixture)
        self.assertNotIn('turn/start', fixture.calls); self.assertEqual('blocked', done['dispatches'][0]['status'])

    def test_timeout_interrupt_ack_does_not_clear_uncertain_budget(self):
        self.run_attempt(); fixture = ProtocolFixture(self.root)
        self.adapter.execute(self.pid, 'planner-001', client_factory=lambda _: fixture, timeout=0)
        done = self.service.planning('status', {'project_root': str(self.root), 'plan_id': self.pid})
        self.assertEqual('planner_uncertain', done['state']); self.assertEqual('reserved', done['dispatches'][0]['status'])
        self.assertTrue(done['dispatches'][0]['session']['interrupt_requested'])
        self.run_attempt(); self.assertEqual(1, len(self.spawned))

    def test_concurrent_run_claims_only_one_durable_attempt(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: self.run_attempt(), range(2)))
        self.assertEqual(1, len(self.spawned)); self.assertEqual(1, len(self.run_attempt()['dispatches']))

    def test_crashed_owner_is_not_claimed_again(self):
        self.run_attempt(); self.adapter.update(self.pid, 'planner-001', stage='preparing')
        self.adapter.execute(self.pid, 'planner-001', client_factory=lambda _: self.fail('recovery launched model'))
        self.run_attempt(); self.assertEqual(1, len(self.spawned))

    def test_cli_override_preserves_transport_type_and_contains_no_credentials(self):
        home = self.root / 'home'; home.mkdir(exist_ok=True); (home / 'config.toml').write_text(
            '[mcp_servers.http]\nurl="https://example.invalid/private-token"\n[mcp_servers.stdio]\ncommand="private-command"\n'
            '[plugins."fixture@market"]\nenabled=true\n')
        command = restricted_command(self.root); joined = ' '.join(command)
        self.assertNotIn('private-token', joined); self.assertNotIn('private-command', joined)
        self.assertIn('mcp_servers.http={url="http://127.0.0.1:9",enabled=false}', command)
        self.assertIn('mcp_servers.stdio={command="false",enabled=false}', command)
        self.assertIn('plugins.fixture@market.enabled=false', command)

    def test_process_start_failure_and_changed_baseline_do_not_emit_turn(self):
        def failed_launch(*args): raise OSError('fixture')
        done = self.adapter.run({'plan_id': self.pid, 'attempt_id': 'initial', 'invocation': 'explicit'}, launch=failed_launch)
        self.assertEqual('failed', done['dispatches'][0]['status'])
        self.assertFalse(done['dispatches'][0]['session']['turn_committed'])


if __name__ == '__main__': unittest.main()
