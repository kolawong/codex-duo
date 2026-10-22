"""Retired delivery preferences: isolated settings/history fixtures, no models."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_parallel as worker
from test_native import mcp
from codex_duo_parallel import ParallelExecution
from codex_duo_selection import SelectionError, prepare_handoff, saved_workflow


class ReturnFlowTests(unittest.TestCase):
    setUp = worker.ParallelTests.setUp
    tearDown = worker.ParallelTests.tearDown
    call = worker.ParallelTests.call
    failed = worker.ParallelTests.failed
    completed = worker.ParallelTests.completed
    evidence = worker.ParallelTests.evidence

    def legacy(self, store, mode):
        document = json.loads(self.service.store.path.read_bytes())
        document['workflow']['completion_mode'] = mode
        store.path.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(document, indent=2) + '\n').encode(); store.path.write_bytes(raw)
        return document, raw, hashlib.sha256(raw).hexdigest()

    def test_legacy_settings_resolve_to_return_without_writing_or_dispatching(self):
        for mode in ('manual_review', 'wake_on_completion'):
            with self.subTest(mode=mode):
                document, raw, _ = self.legacy(self.service.store, mode)
                with patch.object(self.service, 'parallel', side_effect=AssertionError('no Worker')), \
                     patch.object(self.service, 'planning', side_effect=AssertionError('no Planner')):
                    defaults = self.service.defaults(str(self.root)); state = self.service.state()
                self.assertEqual('return', defaults['workflow']['completion_mode'])
                self.assertEqual('return', state['workflow']['completion_mode'])
                self.assertEqual(document['selection']['worker'], defaults['worker'])
                self.assertNotIn('review_inbox', state); self.assertNotIn('completion', state)
                self.assertEqual(raw, self.service.store.path.read_bytes())

    def test_explicit_project_and_global_migration_changes_only_mode_and_preserves_backup(self):
        stores = [self.service.store, self.service.defaults_store.global_store]
        for store, mode in zip(stores, ('manual_review', 'wake_on_completion')):
            original, raw, revision = self.legacy(store, mode)
            result = store.migrate_completion(revision)
            self.assertTrue(result['changed']); self.assertEqual(raw, Path(result['backup']).read_bytes())
            migrated = json.loads(store.path.read_bytes())
            expected = copy.deepcopy(original); expected['workflow']['completion_mode'] = 'return'
            self.assertEqual(expected, migrated)
            before = store.path.read_bytes()
            again = store.migrate_completion(result['revision'])
            self.assertFalse(again['changed']); self.assertEqual(before, store.path.read_bytes())
        self.assertEqual('return', self.service.defaults(str(self.root))['workflow']['completion_mode'])
        self.assertEqual('return', saved_workflow(json.loads(stores[1].path.read_bytes()))['completion_mode'])

    def test_migration_revision_invalid_config_and_symlink_fail_without_overwrite(self):
        _, raw, revision = self.legacy(self.service.store, 'manual_review')
        with self.assertRaises(SelectionError): self.service.store.migrate_completion('stale')
        self.assertEqual(raw, self.service.store.path.read_bytes())
        invalid = json.loads(raw); invalid['workflow']['completion_mode'] = 'invalid'
        self.service.store.path.write_text(json.dumps(invalid)); before = self.service.store.path.read_bytes()
        with self.assertRaises(SelectionError):
            self.service.store.migrate_completion(hashlib.sha256(before).hexdigest())
        self.assertEqual(before, self.service.store.path.read_bytes())
        target = self.root / 'target.json'; target.write_bytes(raw)
        self.service.store.path.unlink(); self.service.store.path.symlink_to(target)
        with self.assertRaises(SelectionError): self.service.store.migrate_completion(revision)
        self.assertEqual(raw, target.read_bytes())

    def test_new_saves_cannot_reactivate_removed_preferences(self):
        before = self.service.store.path.read_bytes()
        for mode in ('manual_review', 'wake_on_completion'):
            with self.assertRaises(SelectionError):
                self.service.save({'selection': self.selection, 'expected_revision': hashlib.sha256(before).hexdigest(),
                    'workflow': {**self.workflow, 'completion_mode': mode}})
            self.assertEqual(before, self.service.store.path.read_bytes())
            with self.assertRaises(SelectionError): self.service.settings_update({'completion_mode': mode})

    def test_removed_tools_and_settings_are_unavailable(self):
        names = {item['name'] for item in mcp.tool_definitions()}
        for name in ('codex_duo_completion', 'codex_duo_review_prompt', 'codex_duo_review_record'):
            self.assertNotIn(name, names)
            with self.assertRaises(SelectionError): mcp.MCPServer(self.service).call(name, {'project_root': str(self.root)})
        settings = self.service.settings_read()
        self.assertNotIn('completion_mode', settings['schema']['properties'])
        self.assertNotIn('completion_mode', settings['values'])

    def test_old_handoffs_and_ledgers_stay_readonly_with_return_runtime(self):
        for mode in ('manual_review', 'wake_on_completion'):
            task = {**self.task, 'task_id': 'old-' + mode}
            prepared = prepare_handoff(task, self.selection, self.catalog,
                self.service.store.directory / 'handoffs', 'historical-revision',
                {**self.workflow, 'completion_mode': mode}, legacy_completion=True)
            before = {p: p.read_bytes() for p in Path(prepared['path']).rglob('*') if p.is_file()}
            plan = self.service.execution_plan(prepared['id'])
            self.assertEqual('return', plan['completion_mode'])
            self.assertEqual(before, {p: p.read_bytes() for p in before})
            runner = ParallelExecution(self.service.store, plan); runner.plan({'host_capacity': 1})
            reservation = runner.reserve({'host_capacity': 1, 'workstream_id': 'main'})
            runner.complete({'dispatch_id': reservation['id'], 'outcome': 'failed', 'native_receipt': 'OFFLINE ONLY'})
            ledger = runner.read(); ledger['completion_mode'] = mode
            ledger['manual_review'] = {'outcome': 'failed', 'summary': 'historical fixture'}
            runner.write(runner.path, ledger); raw = runner.path.read_bytes()
            a = runner.view(runner.read()); b = runner.view(runner.read())
            self.assertEqual(a, b); self.assertEqual('failed', a['completion']['events'][0]['outcome'])
            self.assertNotIn('effective_mode', a['completion']); self.assertEqual(raw, runner.path.read_bytes())
            self.assertEqual(2, a['remaining_worker_turns'])

    def test_return_dispatch_complete_and_parent_verify_preserve_idempotent_budget(self):
        self.call('plan', host_capacity=1); reservation = self.call('reserve', host_capacity=1, workstream_id='main')
        completed = self.completed(reservation)
        repeated = self.call('complete', dispatch_id=reservation['id'], outcome='completed', native_receipt='offline native receipt fixture')
        self.assertEqual(completed, repeated); self.assertEqual(2, repeated['remaining_worker_turns'])
        root = Path(self.plan['evidence_root']); self.evidence(root, self.task)
        first = self.call('verify'); second = self.call('verify')
        self.assertEqual(first, second); self.assertEqual('evidence_valid', first['status'])
        self.assertEqual(1, self.call('plan', host_capacity=1)['dispatch_count'])


if __name__ == '__main__': unittest.main()
