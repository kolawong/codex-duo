# Test storage is deliberately independent of the user's real Codex home.
import os as _test_os, tempfile as _test_tempfile, atexit as _test_atexit
if not _test_os.environ.get('FUSION_TEST_CODEX_HOME'):
    _test_home = _test_tempfile.TemporaryDirectory(prefix='duo-test-home-')
    _test_atexit.register(_test_home.cleanup)
    _test_os.environ['FUSION_TEST_CODEX_HOME'] = _test_home.name
_test_os.environ['CODEX_HOME'] = _test_os.environ['FUSION_TEST_CODEX_HOME']
"""Isolated multi-project routing and explicit project instruction opt-in."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_native import mcp, catalog
from fusion_service import FusionService
from fusion_selection import SelectionError
from fusion_projects import START, END, BLOCK, project_path


class ProjectTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch as _home_patch
        _home = _test_tempfile.TemporaryDirectory(prefix='duo-case-home-')
        self.addCleanup(_home.cleanup)
        _environment = _home_patch.dict(_test_os.environ, {'CODEX_HOME': _home.name})
        _environment.start(); self.addCleanup(_environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.a = self.base / 'project a'; self.a.mkdir()
        self.b = self.base / 'project b'; self.b.mkdir()
        self.service = FusionService(self.a / '.fusion', catalog)
        self.server = mcp.MCPServer(self.service)
        self.selection = self.service.state()['default']
        self.workflow = {'activation': 'automatic_project', 'coordinator_mode': 'current_thread', 'max_worker_turns': 2, 'max_parallel_workers': 1}

    def tearDown(self): self.temp.cleanup()

    def call(self, name, root, **args):
        return self.server.call(name, {'project_root': str(root), **args})

    def save(self, root, enable=False, revision='none', workflow=None):
        return self.call('fusion.save', root, selection=self.selection, workflow=workflow or self.workflow,
                         expected_revision=revision, enable_project=enable)['structuredContent']

    def test_roots_are_stateless_and_reads_never_write_or_enable(self):
        for root in [self.b, self.a, self.b]:
            state = self.call('fusion.open', root)['_meta']['fusion/state']
            self.assertEqual(str(root), state['project_root'])
            self.assertFalse(state['project_opt_in']['enabled'])
            self.assertEqual([], list(root.iterdir()))
        saved_a = self.save(self.a)
        before = (self.a / '.fusion/selection.json').read_bytes()
        self.selection = copy.deepcopy(self.selection); self.selection['worker']['reasoning_effort'] = 'medium'
        self.save(self.b)
        self.assertEqual('high', self.call('fusion.defaults', self.a)['structuredContent']['worker']['reasoning_effort'])
        self.assertEqual('medium', self.call('fusion.defaults', self.b)['structuredContent']['worker']['reasoning_effort'])
        self.assertEqual(before, (self.a / '.fusion/selection.json').read_bytes())
        # Legacy omitted-root calls still target constructor root, not the most recent call.
        self.assertEqual(saved_a['revision'], self.server.call('fusion.state', {})['structuredContent']['saved']['revision'])
        self.assertFalse((self.a / 'AGENTS.md').exists())
        self.assertFalse((self.b / 'AGENTS.md').exists())

    def test_explicit_enable_preserves_bytes_and_is_idempotent_then_manual(self):
        original = '# Existing\r\nKeep exactly.\r\n'.encode()
        path = self.b / 'AGENTS.md'; path.write_bytes(original)
        saved = self.save(self.b, enable=True)
        once = path.read_bytes()
        self.assertTrue(once.startswith(original))
        self.assertEqual(1, once.decode().count(START))
        self.assertTrue(saved['project_opt_in']['enabled'])
        second = self.save(self.b, enable=True, revision=saved['revision'])
        self.assertEqual(once, path.read_bytes())
        self.assertEqual(saved['revision'], second['revision'])
        self.save(self.b, revision=second['revision'], workflow={**self.workflow, 'activation':'manual'})
        self.assertEqual(once, path.read_bytes())
        with self.assertRaises(SelectionError) as error:
            self.call('fusion.begin', self.b, task=self.service.template, invocation='automatic')
        self.assertEqual('manual_mode', error.exception.code)
        self.assertFalse((self.a / '.fusion').exists())

    def test_bad_agents_or_symlink_cannot_enable_or_save(self):
        path = self.b / 'AGENTS.md'
        for value in [START.encode(), (END + START).encode(), b'\xff']:
            path.write_bytes(value)
            with self.assertRaises(SelectionError): self.save(self.b, enable=True)
            self.assertEqual(value, path.read_bytes())
            self.assertFalse((self.b / '.fusion').exists())
        path.unlink(); outside = self.base / 'outside'; outside.write_text('preserve')
        path.symlink_to(outside)
        with self.assertRaises(SelectionError): self.save(self.b, enable=True)
        self.assertEqual('preserve', outside.read_text())
        self.assertTrue(path.is_symlink())

    def test_instruction_write_failure_and_save_failure_preserve_both_files(self):
        saved = self.save(self.b)
        path = self.b / 'AGENTS.md'; path.write_bytes(b'# preserve\n')
        before = (self.b / '.fusion/selection.json').read_bytes()
        with patch('fusion_projects.atomic_instructions', side_effect=OSError('denied')):
            with self.assertRaises(OSError): self.save(self.b, enable=True, revision=saved['revision'])
        self.assertEqual(b'# preserve\n', path.read_bytes())
        with self.assertRaises(SelectionError):
            self.selection['worker']['reasoning_effort'] = 'medium'
            self.save(self.b, enable=True, revision='stale')
        self.assertEqual(b'# preserve\n', path.read_bytes())
        self.assertEqual(before, (self.b / '.fusion/selection.json').read_bytes())
        path.unlink()
        with self.assertRaises(SelectionError): self.save(self.b, enable=True, revision='stale')
        self.assertFalse(path.exists())

    def test_root_checks_and_cross_project_handoff_isolation(self):
        for root in ['relative', str(self.b / 'missing'), str(self.b / '..')]:
            with self.assertRaises(SelectionError): self.server.call('fusion.state', {'project_root':root})
        link = self.base / 'link'; link.symlink_to(self.b)
        with self.assertRaises(SelectionError): project_path(link)
        self.save(self.a)
        begun = self.call('fusion.begin', self.a, task=self.service.template, invocation='automatic')['structuredContent']
        with self.assertRaises(SelectionError): self.call('fusion.execution_plan', self.b, handoff_id=begun['handoff_id'])
        self.assertFalse((self.b / '.fusion').exists())
        with self.assertRaises(SelectionError): self.service.save({'project_root':str(self.b), 'selection':self.selection, 'expected_revision':'none'})
