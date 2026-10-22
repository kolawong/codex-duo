"""Completion behavior uses offline protocol/ledger fixtures; never model execution."""
import copy
import unittest
from pathlib import Path
from unittest.mock import patch
import test_planner_session as planner
import test_parallel as worker
from codex_duo_parallel import ParallelExecution
from codex_duo_selection import SelectionError
from codex_duo_service import CodexDuoService


class PlannerCompletionTests(unittest.TestCase):
    setUp = planner.SessionPlannerTests.setUp
    run_attempt = planner.SessionPlannerTests.run_attempt
    execute = planner.SessionPlannerTests.execute

    def completion(self, **kwargs):
        return self.service.planning('status', {'project_root': str(self.root), 'plan_id': self.pid})['completion']

    def test_reconnect_keeps_dispatch_budget_snapshot_and_preferences(self):
        self.run_attempt()
        before = self.service.planning('status', {'project_root': str(self.root), 'plan_id': self.pid})
        with patch('codex_duo_planner_session.SessionPlanner.run', side_effect=AssertionError('no dispatch')), \
             patch('codex_duo_planner_session.AppServer.__init__', side_effect=AssertionError('no host')):
            self.assertEqual(self.completion(), self.completion())
            self.service = CodexDuoService(self.root / '.codex-duo', lambda: self.catalog)
        after = self.service.planning('status', {'project_root': str(self.root), 'plan_id': self.pid})
        self.assertEqual(before['snapshot_sha256'], after['snapshot_sha256'])
        self.assertEqual(before['dispatches'], after['dispatches'])
        self.assertEqual(0, after['remaining_planner_turns'])
        self.assertEqual(self.selection, (self.root / '.codex-duo/selection.json').read_bytes())
        done = self.execute(planner.ProtocolFixture(self.root))
        first = self.completion(); self.assertEqual(first, self.completion())
        self.assertEqual(1, len(first['events'])); event = first['events'][0]
        self.assertEqual('completed', event['outcome']); self.assertEqual('pending', event['review_state'])
        self.assertTrue(event['host_terminal_observed']); self.assertFalse(done['worker_execution_allowed'])
        self.assertEqual(done['result_sha256'], event['result_sha256'])
        self.run_attempt(); self.assertEqual(1, len(self.spawned))

    def test_matching_item_and_foreign_terminal_correlate_without_polling_model(self):
        self.run_attempt(); fixture = planner.ProtocolFixture(self.root); original = fixture.receive
        events = []
        def receive(timeout=1):
            if not events:
                terminal = original(timeout); answer = terminal['params']['turn']['items'].pop()
                foreign = copy.deepcopy(terminal); foreign['params']['turn']['id'] = 'foreign'
                events.extend([foreign, {'method': 'item/completed', 'params': {
                    'threadId': 'fixture-session', 'turnId': 'fixture-turn', 'item': answer}}, terminal])
            return events.pop(0)
        fixture.receive = receive
        done = self.execute(fixture)
        self.assertEqual('awaiting_user_review', done['state'])
        self.assertEqual(1, fixture.calls.count('turn/start'))

    def test_stop_ack_waits_for_confirmed_interruption_and_distinguishes_cancelled(self):
        self.run_attempt(); fixture = planner.ProtocolFixture(self.root); original = fixture.call
        def call(method, params=None):
            result = original(method, params)
            if method == 'turn/start': self.adapter.stop({'plan_id': self.pid})
            return result
        fixture.call = call
        fixture.receive = lambda timeout=1: {'method': 'turn/completed', 'params': {
            'threadId': 'fixture-session', 'turn': {'id': 'fixture-turn', 'status': 'interrupted', 'items': []}}}
        done = self.execute(fixture)
        self.assertEqual('cancelled', done['dispatches'][0]['status'])
        self.assertEqual(1, fixture.calls.count('turn/interrupt'))
        self.assertEqual('cancelled', self.completion()['events'][0]['outcome'])
        self.assertEqual(0, done['remaining_planner_turns']); self.assertIsNone(done['result'])

    def test_lost_transport_and_stale_process_never_claim_terminal_or_relaunch(self):
        self.run_attempt(); fixture = planner.ProtocolFixture(self.root); fixture.fail = 'lost'
        self.execute(fixture)
        state = self.completion()
        self.assertEqual([], state['events']); self.assertEqual('unknown', state['pending'][0]['state'])
        self.assertFalse(state['pending'][0]['retry_allowed'])
        self.adapter.update(self.pid, 'planner-001', stage='running')
        # update writes a fresh heartbeat, so simulate a durable expired owner directly.
        plans = self.adapter.plans
        with self.service.store.lock:
            value = plans.read(self.pid); value['dispatches'][0]['session']['heartbeat'] = 1
            plans.write(plans.path(self.pid), value)
        self.assertEqual('unknown', self.completion()['pending'][0]['state'])
        self.run_attempt(); self.assertEqual(1, len(self.spawned))

    def test_terminal_before_interrupt_ack_is_drained_from_protocol_buffer(self):
        self.run_attempt(); fixture = planner.ProtocolFixture(self.root); original = fixture.call
        def call(method, params=None):
            result = original(method, params)
            if method == 'turn/start': self.adapter.stop({'plan_id': self.pid})
            if method == 'turn/interrupt':
                fixture.pending.append({'method': 'turn/completed', 'params': {
                    'threadId': 'fixture-session', 'turn': {'id': 'fixture-turn', 'status': 'interrupted', 'items': []}}})
            return result
        fixture.call = call
        fixture.receive = lambda timeout=1: self.fail('terminal already buffered before acknowledgement')
        done = self.execute(fixture)
        self.assertEqual('cancelled', done['dispatches'][0]['status'])
        self.assertEqual(1, fixture.calls.count('turn/interrupt'))

    def test_failed_turn_and_terminal_tool_record_reject_plan(self):
        self.run_attempt(); fixture = planner.ProtocolFixture(self.root); fixture.fail = 'failed'
        done = self.execute(fixture)
        self.assertEqual('failed', self.completion()['events'][0]['outcome'])
        self.assertNotIn('turn/interrupt', fixture.calls)
        self.assertEqual(0, done['remaining_planner_turns'])

    def test_terminal_tool_record_with_valid_answer_cannot_succeed(self):
        self.run_attempt(); fixture = planner.ProtocolFixture(self.root); original = fixture.receive
        def receive(timeout=1):
            event = original(timeout)
            event['params']['turn']['items'].append({'id': 'tool', 'type': 'mcpToolCall'})
            return event
        fixture.receive = receive
        done = self.execute(fixture)
        self.assertEqual('failed', done['dispatches'][0]['status']); self.assertIsNone(done['result'])

    def test_legacy_terminal_projection_is_read_only_and_stable(self):
        self.run_attempt(); self.execute(planner.ProtocolFixture(self.root))
        path = self.adapter.plans.path(self.pid); before = path.read_bytes()
        a = self.completion(); self.assertEqual(a, self.completion()); self.assertEqual(before, path.read_bytes())


class WorkerCompletionTests(unittest.TestCase):
    setUp = worker.ParallelTests.setUp
    tearDown = worker.ParallelTests.tearDown
    call = worker.ParallelTests.call
    failed = worker.ParallelTests.failed
    evidence = worker.ParallelTests.evidence
    completed = worker.ParallelTests.completed

    def completion(self, **kwargs):
        runner = ParallelExecution(self.service.store, self.service.execution_plan(self.plan['handoff_id']))
        return runner.view(runner.read())['completion']

    def test_unknown_dispatch_reconnect_never_releases_or_resets_budget(self):
        self.call('plan', host_capacity=1)
        reservation = self.call('reserve', host_capacity=1, workstream_id='main')
        before = self.call('plan', host_capacity=1)
        state = self.completion()
        self.assertEqual('dispatch_unconfirmed', state['pending'][0]['state'])
        self.assertEqual('coordinator_native_host', state['listener'])
        self.assertEqual([], state['events'])
        self.service = CodexDuoService(self.root / '.codex-duo', lambda: self.catalog)
        self.completion()
        after = self.call('plan', host_capacity=1)
        self.assertEqual(before['remaining_worker_turns'], after['remaining_worker_turns'])
        self.assertEqual(before['active_dispatches'], after['active_dispatches'])
        self.failed(reservation)
        self.assertEqual('failed', self.completion()['events'][0]['outcome'])

    def test_duplicate_completed_evidence_conflicts_and_tampering(self):
        self.call('plan', host_capacity=1)
        r = self.call('reserve', host_capacity=1, workstream_id='main')
        first = self.completed(r); state = self.completion()
        again = self.call('complete', dispatch_id=r['id'], outcome='completed', native_receipt='offline native receipt fixture')
        self.assertEqual(first, again); self.assertEqual(state, self.completion())
        with self.assertRaises(SelectionError):
            self.call('complete', dispatch_id=r['id'], outcome='failed', native_receipt='different')
        (Path(r['evidence_root']) / 'tests.log').write_text('changed')
        with self.assertRaises(SelectionError):
            self.call('complete', dispatch_id=r['id'], outcome='completed', native_receipt='offline native receipt fixture')
        self.assertEqual(1, self.call('plan', host_capacity=1)['dispatch_count'])

    def test_cancelled_native_receipt_is_terminal_and_idempotent(self):
        self.call('plan', host_capacity=1)
        r = self.call('reserve', host_capacity=1, workstream_id='main')
        args = dict(dispatch_id=r['id'], outcome='cancelled', native_receipt='offline interrupted receipt')
        self.assertEqual(self.call('complete', **args), self.call('complete', **args))
        event = self.completion()['events'][0]
        self.assertEqual('cancelled', event['outcome']); self.assertEqual('coordinator_reported', event['source'])
        self.assertIsNone(event['host_terminal_observed']); self.assertTrue(event['requires_coordinator_review'])


if __name__ == '__main__': unittest.main()
