"""Migration fixtures consume durable budgets, never real model calls."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_planner
from test_native import mcp
from codex_duo_migration import migrate, manifest
from codex_duo_selection import SelectionError
from codex_duo_service import CodexDuoService


class MigrationTests(unittest.TestCase):
    setUp = test_planner.PlannerTests.setUp
    tearDown = test_planner.PlannerTests.tearDown
    git = test_planner.PlannerTests.git
    call = test_planner.PlannerTests.call

    def legacy(self):
        current = self.root / '.codex-duo'
        legacy = self.root / '.fusion'
        current.rename(legacy)
        return legacy

    def reopen(self):
        self.service = CodexDuoService(self.root / '.codex-duo', lambda: self.catalog)

    def test_read_never_ignores_old_state_and_migration_preserves_bytes_and_budget(self):
        self.call('reserve', host_capabilities=self.host)
        legacy = self.legacy()
        before = manifest(legacy)
        with self.assertRaises(SelectionError) as error:
            self.reopen()
        self.assertEqual('migration_required', error.exception.code)
        self.assertFalse((self.root / '.codex-duo').exists())
        self.assertEqual(before, migrate(self.root)['files'])
        self.reopen()
        status = self.call('status')
        self.assertEqual(1, status['remaining_planner_turns'])
        with self.assertRaises(SelectionError):
            self.call('reserve', host_capabilities=self.host)
        self.assertEqual('already_migrated', migrate(self.root)['state'])
        self.assertEqual(before, manifest(self.root / '.codex-duo'))
        with self.assertRaises(OSError):
            legacy.mkdir()

    def test_uncertain_managed_attempt_remains_blocked_after_repeat_migration(self):
        from codex_duo_planner import PlannerExecution
        plans = PlannerExecution(self.service)
        value = plans.read(self.pid)
        value['dispatches'].append({'id': 'planner-001', 'status': 'reserved',
            'adapter': 'official_app_server', 'attempt_id': 'initial',
            'session': {'state': 'uncertain', 'heartbeat': 0}, 'native_receipt': None})
        plans.write(plans.path(self.pid), value)
        self.legacy(); migrate(self.root); migrate(self.root); self.reopen()
        from codex_duo_planner_session import SessionPlanner
        def forbidden(*args): raise AssertionError('no retry')
        status = SessionPlanner(self.service).run({'project_root': str(self.root), 'plan_id': self.pid,
            'invocation': 'explicit', 'attempt_id': 'initial'}, launch=forbidden)
        self.assertEqual(1, status['remaining_planner_turns'])
        with self.assertRaises(SelectionError):
            self.call('run', invocation='explicit', attempt_id='another')

    def test_conflicts_do_not_merge_or_overwrite(self):
        legacy = self.legacy()
        current = self.root / '.codex-duo'; current.mkdir()
        (current / 'selection.json').write_text('user new choice')
        before = manifest(legacy)
        with self.assertRaises(SelectionError): migrate(self.root)
        self.assertEqual(before, manifest(legacy))
        self.assertEqual('user new choice', (current / 'selection.json').read_text())

    def test_nested_evidence_symlink_preserved_without_following_target(self):
        legacy = self.legacy()
        outside = self.root / 'outside'; outside.write_text('preserve')
        (legacy / 'linked').symlink_to(outside)
        migrate(self.root)
        self.assertEqual('preserve', outside.read_text())
        self.assertEqual(str(outside), str((self.root / '.codex-duo/linked').readlink()))

    def test_state_root_symlink_rejected_without_touching_target(self):
        outside = self.root / 'other'; outside.mkdir()
        (self.root / '.fusion').symlink_to(outside)
        with self.assertRaises(SelectionError): migrate(self.root)
        self.assertEqual([], list(outside.iterdir()))

    def test_interrupted_move_recovery_preserves_all_records(self):
        legacy = self.legacy(); before = manifest(legacy)
        with patch('codex_duo_migration.write_marker', side_effect=OSError('fixture crash')):
            with self.assertRaises(OSError): migrate(self.root)
        with self.assertRaises(SelectionError): self.reopen()
        self.assertEqual('migration_recovered', migrate(self.root)['state'])
        self.assertEqual(before, manifest(self.root / '.codex-duo'))
        self.assertEqual('already_migrated', migrate(self.root)['state'])

    def test_legacy_handoff_and_worker_ledger_keep_total_budget(self):
        body = {'project_root': str(self.root), 'task': self.service.template, 'invocation': 'explicit'}
        begun = self.service.begin(body); hid = begun['handoff_id']
        self.service.parallel('plan', {'project_root': str(self.root), 'handoff_id': hid, 'host_capacity': 1})
        self.service.parallel('reserve', {'project_root': str(self.root), 'handoff_id': hid, 'workstream_id': 'main', 'host_capacity': 1})
        target = self.root / '.codex-duo/handoffs' / hid
        worker = target / 'config/codex_duo_worker.toml'
        old = target / 'config/fusion_worker.toml'
        old.write_text(worker.read_text().replace('codex_duo_worker', 'fusion_worker')); worker.unlink()
        readme = target / 'README.md'
        readme.write_text(readme.read_text().replace('Codex Duo', 'Fusion').replace('codex_duo.py', 'fusion.py'))
        legacy = self.legacy(); before = manifest(legacy)
        migrate(self.root); self.reopen()
        plan = self.service.execution_plan(hid)
        self.assertEqual('codex_duo_plan', plan['next_tool'])
        status = self.service.parallel('plan', {'project_root': str(self.root), 'handoff_id': hid, 'host_capacity': 1})
        self.assertEqual(2, status['remaining_worker_turns'])
        self.assertEqual(before, manifest(self.root / '.codex-duo'))

    def test_catalog_exposes_only_legal_current_names_and_rejects_old_calls(self):
        import re
        for tool in mcp.tool_definitions():
            self.assertRegex(tool['name'], r'^codex_duo_[a-z_]+$')
            self.assertNotIn('fusion', json.dumps(tool))
        with self.assertRaises(SelectionError):
            mcp.MCPServer(self.service).call('fusion.defaults', {'project_root': str(self.root)})

    def test_legacy_scope_is_presented_canonically_without_rewriting_preference(self):
        path = self.service.store.path
        value = json.loads(path.read_bytes()); value['scope'] = 'project_fusion_defaults'
        path.write_text(json.dumps(value))
        before = path.read_bytes()
        self.legacy(); migrate(self.root); self.reopen()
        saved = self.service.store.read(self.catalog)
        self.assertEqual('project_codex_duo_defaults', saved['document']['scope'])
        self.assertEqual(before, self.service.store.path.read_bytes())


if __name__ == '__main__': unittest.main()
