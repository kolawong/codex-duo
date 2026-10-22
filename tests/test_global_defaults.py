"""Global inheritance, fail-closed resolution and actual-root routing."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_native import catalog, mcp, DELEGATION_ASSESSMENT
from codex_duo_service import CodexDuoService
from codex_duo_selection import SelectionError
from codex_duo_selection import saved_workflow


class GlobalDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='duo-global-case-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / 'codex'
        env = patch.dict(os.environ, {'CODEX_HOME': str(self.home)})
        env.start(); self.addCleanup(env.stop)
        self.a = Path(self.temp.name).resolve() / 'a'; self.a.mkdir()
        self.b = Path(self.temp.name).resolve() / 'b'; self.b.mkdir()
        self.one = CodexDuoService(self.a / '.codex-duo', catalog)
        self.two = CodexDuoService(self.b / '.codex-duo', catalog)
        self.selection = self.one.state()['default']
        self.workflow = {'activation':'automatic_project', 'coordinator_mode':'current_thread', 'max_worker_turns':7, 'max_parallel_workers':1}

    def save(self, service=None, scope='global', revision='none', workflow=None, **extra):
        return (service or self.one).save({'scope':scope, 'selection':copy.deepcopy(self.selection),
            'workflow':workflow or self.workflow, 'expected_revision':revision, **extra})

    def test_two_unconfigured_projects_inherit_without_reads_writing(self):
        saved = self.save()
        before = (self.home/'codex-duo/selection.json').read_bytes()
        for service, root in [(self.one,self.a),(self.two,self.b)]:
            value = service.defaults(str(root))
            self.assertEqual(value['source'],'global')
            self.assertEqual(value['workflow'],saved_workflow({'workflow': self.workflow}))
            self.assertEqual(value['revision'],saved['revision'])
            self.assertFalse((root/'.codex-duo').exists())
            self.assertFalse((root/'AGENTS.md').exists())
        self.assertEqual(before,(self.home/'codex-duo/selection.json').read_bytes())

    def test_override_manual_wins_and_reset_inherits_without_changing_global(self):
        global_saved = self.save()
        before = self.one.defaults_store.global_store.path.read_bytes()
        local = self.save(scope='project',workflow={**self.workflow,'activation':'manual'})
        self.assertEqual(self.one.defaults(str(self.a))['source'],'project')
        with self.assertRaises(SelectionError) as error:
            self.one.begin({'project_root':str(self.a),'task':self.one.template,'invocation':'automatic'})
        self.assertEqual(error.exception.code,'manual_mode')
        self.assertEqual(self.two.defaults(str(self.b))['workflow']['activation'],'automatic_project')
        state = self.one.reset({'project_root':str(self.a),'expected_revision':local['revision'],
            'expected_global_revision':global_saved['revision']})
        self.assertEqual(state['source'],'global')
        self.assertEqual(state['workflow'],saved_workflow({'workflow': self.workflow}))
        self.assertEqual(before,self.one.defaults_store.global_store.path.read_bytes())
        self.assertTrue((self.a/'.codex-duo/history'/ (local['revision']+'.json')).exists())

    def test_global_manual_stops_automatic_but_local_automatic_wins(self):
        self.save(workflow={**self.workflow,'activation':'manual'})
        with self.assertRaises(SelectionError) as error:
            self.two.begin({'project_root':str(self.b),'task':self.two.template,'invocation':'automatic'})
        self.assertEqual(error.exception.code,'manual_mode')
        self.save(service=self.two,scope='project')
        plan=self.two.begin({'project_root':str(self.b),'task':self.two.template,'invocation':'automatic',
                             'assessment': DELEGATION_ASSESSMENT})
        self.assertEqual(plan['project_root'],str(self.b))
        self.assertTrue(plan['handoff_path'].startswith(str(self.b/'.codex-duo/handoffs')))
        self.assertFalse((self.home/'codex-duo/handoffs').exists())

    def test_global_plugin_settings_ignore_fallback_project_override(self):
        self.save(scope='project',workflow={**self.workflow,'max_worker_turns':2})
        before=self.one.store.path.read_bytes()
        self.assertEqual(self.one.state('global')['source'],'unconfigured')
        self.one.settings_update({'max_worker_turns':'9','activation':'automatic_project'})
        settings=self.one.settings_read()
        self.assertIn('全局',settings['layout'][0]['title'])
        self.assertEqual(settings['values']['max_worker_turns'],'9')
        self.assertEqual(self.one.defaults(str(self.a))['workflow']['max_worker_turns'],2)
        self.assertEqual(self.two.defaults(str(self.b))['workflow']['max_worker_turns'],9)
        self.assertEqual(before,self.one.store.path.read_bytes())

    def test_revision_conflict_blocks_reset_and_inherited_override_save(self):
        old=self.save(); local=self.save(scope='project')
        new=self.save(revision=old['revision'],workflow={**self.workflow,'max_worker_turns':8})
        before=self.one.store.path.read_bytes()
        for action in [lambda:self.one.reset({'project_root':str(self.a),'expected_revision':local['revision'],'expected_global_revision':old['revision']}),
                       lambda:self.save(scope='project',revision=local['revision'],expected_global_revision=old['revision'])]:
            with self.assertRaises(SelectionError) as error:action()
            self.assertEqual(error.exception.code,'revision_conflict')
        self.assertEqual(before,self.one.store.path.read_bytes())
        self.assertNotEqual(old['revision'],new['revision'])

    def test_invalid_either_layer_fails_closed_and_global_editor_is_scope_specific(self):
        self.save(); self.save(scope='project')
        self.one.defaults_store.global_store.path.write_text('{bad')
        with self.assertRaises(SelectionError):self.one.defaults(str(self.a))
        with self.assertRaises(SelectionError):self.one.begin({'project_root':str(self.a),'task':self.one.template,'invocation':'automatic'})
        self.assertIsNotNone(self.one.state('global')['saved']['error'])
        self.save(scope='global',revision=self.one.state('global')['saved']['revision'])
        self.one.store.path.write_text('{bad')
        with self.assertRaises(SelectionError):self.one.defaults(str(self.a))
        self.assertIsNone(self.one.state('global')['saved']['error'])
        self.assertEqual(self.one.state('global')['source'],'global')

    def test_mcp_open_defaults_global_but_handoff_uses_explicit_chat_root(self):
        self.save()
        server=mcp.MCPServer(self.one)
        opened=server.call('codex_duo_open',{'project_root':str(self.b)})['_meta']['codex-duo/state']
        self.assertEqual(opened['scope'],'global');self.assertEqual(opened['project_root'],str(self.b))
        begun=server.call('codex_duo_begin',{'project_root':str(self.b),'task':self.one.template,'invocation':'automatic',
                                          'assessment': DELEGATION_ASSESSMENT})['structuredContent']
        self.assertEqual(begun['project_root'],str(self.b))
        self.assertTrue(begun['task_path'].startswith(str(self.b)))
        self.assertFalse((self.a/'.codex-duo').exists())

    def test_stale_noop_save_checks_revision(self):
        saved=self.save()
        with self.assertRaises(SelectionError) as error:self.save(revision='stale')
        self.assertEqual(error.exception.code,'revision_conflict')
        self.assertEqual(self.one.state('global')['saved']['revision'],saved['revision'])

    def test_symlinked_global_store_rejected(self):
        self.home.mkdir(); target=Path(self.temp.name)/'target';target.mkdir()
        (self.home/'codex-duo').symlink_to(target,target_is_directory=True)
        with self.assertRaises(SelectionError):self.one.defaults(str(self.a))
        with self.assertRaises(SelectionError):self.save()
