# Test storage is deliberately independent of the user's real Codex home.
import os as _test_os, tempfile as _test_tempfile, atexit as _test_atexit
if not _test_os.environ.get('CODEX_DUO_TEST_CODEX_HOME'):
    _test_home = _test_tempfile.TemporaryDirectory(prefix='duo-test-home-')
    _test_atexit.register(_test_home.cleanup)
    _test_os.environ['CODEX_DUO_TEST_CODEX_HOME'] = _test_home.name
_test_os.environ['CODEX_HOME'] = _test_os.environ['CODEX_DUO_TEST_CODEX_HOME']
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('codex_duo_mcp', ROOT / 'plugins/codex-duo/mcp/server.py')
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)
from codex_duo_selection import normalize_catalog, SelectionError
from codex_duo_service import CodexDuoService
from panel.server import PanelService


def catalog():
    return normalize_catalog({'models': [
        {'slug': name, 'visibility': 'list', 'display_name': name,
         'supported_reasoning_levels': [{'effort': e} for e in efforts], 'default_reasoning_level': 'high'}
        for name, efforts in [('gpt-6-astra', ['high', 'ultra']), ('gpt-6-luna', ['high', 'medium']),
                              ('gpt-6.1-sol', ['high'])]]})


class NativeTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch as _home_patch
        _home = _test_tempfile.TemporaryDirectory(prefix='duo-case-home-')
        self.addCleanup(_home.cleanup)
        _environment = _home_patch.dict(_test_os.environ, {'CODEX_HOME': _home.name})
        _environment.start(); self.addCleanup(_environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = CodexDuoService(self.root / '.codex-duo', catalog)
        self.server = mcp.MCPServer(self.service)
        self.selection = self.service.state()['default']

    def tearDown(self):
        self.temp.cleanup()

    def rpc(self, method, params=None):
        return self.server.dispatch({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})

    def call(self, name, args=None):
        return self.rpc('tools/call', {'name': name, 'arguments': args or {}})['result']

    def saved(self):
        return self.service.save({'selection': self.selection, 'expected_revision': 'none'})

    def handoff(self):
        saved = self.saved()
        return self.service.prepare({'task': self.service.template, 'expected_revision': saved['revision']})

    def test_initialize_settings_capability_no_sampling(self):
        data = self.rpc('initialize')['result']
        self.assertEqual(data['protocolVersion'], '2025-11-25')
        settings = data['capabilities']['experimental']['openai/settings']
        self.assertEqual(settings, {'readTool': 'codex_duo_settings_read', 'updateTool': 'codex_duo_settings_update'})
        self.assertNotIn('sampling', data['capabilities'])

    def test_entrypoint_metadata_and_settings_action(self):
        tools = {t['name']: t for t in self.rpc('tools/list')['result']['tools']}
        self.assertEqual(tools['codex_duo_open']['_meta']['openai/ui']['entrypoints'], [{'type': 'thread'}])
        self.assertEqual(tools['codex_duo_open']['_meta']['ui']['resourceUri'], mcp.RESOURCE)
        layout = self.call('codex_duo_settings_read')['structuredContent']['layout']
        self.assertEqual(layout[0]['items'][-1]['tool'], 'codex_duo_open')
        self.assertEqual(tools['codex_duo_save']['_meta']['ui']['visibility'], ['app'])
        self.assertTrue(tools['codex_duo_execution_plan']['annotations']['readOnlyHint'])

    def test_resource_closed_network_fullscreen_self_contained(self):
        item = self.rpc('resources/read', {'uri': mcp.RESOURCE})['result']['contents'][0]
        self.assertEqual(item['mimeType'], 'text/html;profile=mcp-app')
        self.assertEqual(item['_meta']['openai/ui']['availableDisplayModes'], ['fullscreen'])
        self.assertTrue(all(not domains for domains in item['_meta']['ui']['csp'].values()))
        self.assertNotIn('src="/app.js"', item['text'])
        self.assertNotIn('href="/style.css"', item['text'])
        self.assertIn('codexDuoTransport', item['text'])

    def test_codex_duo_branding_preserves_internal_contract(self):
        import base64
        tools = {t['name']: t for t in self.rpc('tools/list')['result']['tools']}
        self.assertEqual(tools['codex_duo_open']['title'], 'Codex Duo 全局默认与项目覆盖')
        self.assertFalse(tools['codex_duo_reserve']['annotations']['idempotentHint'])
        icon = (ROOT / 'plugins/codex-duo/assets/tandem.svg').read_text()
        self.assertEqual(base64.b64decode(tools['codex_duo_open']['icons'][0]['src'].split(',', 1)[1]),
            (ROOT / 'plugins/codex-duo/assets/tandem.png').read_bytes())
        self.assertEqual(tools['codex_duo_open']['icons'][0]['mimeType'], 'image/png')
        self.assertEqual(self.rpc('initialize')['result']['serverInfo']['version'], '0.9.9')
        self.assertEqual(mcp.RESOURCE, 'ui://codex-duo/model-desk-v4')
        public = json.loads((ROOT / 'plugins/codex-duo/plugin.json').read_text())
        native = json.loads((ROOT / 'plugins/codex-duo/.codex-plugin/plugin.json').read_text())
        interface = public['extensions']['com.openai']['interface']
        self.assertEqual(interface, native['interface'])
        for manifest in (public, native):
            self.assertEqual(manifest['name'], 'codex-duo')
            self.assertEqual(manifest['version'], '0.9.9')
            interface = manifest.get('interface') or manifest['extensions']['com.openai']['interface']
            self.assertIn('max_parallel_workers', interface['defaultPrompt'])
            self.assertIn('shared total max_worker_turns', interface['defaultPrompt'])
            self.assertLessEqual(len(manifest['description']), 30)
        self.assertEqual(interface['displayName'], 'Codex Duo')
        # Codex ignores interface assets without the required ./ prefix.
        # Resolve from the plugin root, including the compatibility overlay.
        for manifest in (public, native):
            surface = manifest.get('interface') or manifest['extensions']['com.openai']['interface']
            for field in ('logo', 'composerIcon'):
                self.assertEqual(surface[field], './assets/tandem.png')
                self.assertTrue(surface[field].startswith('./'))
                asset = (ROOT / 'plugins/codex-duo' / surface[field]).resolve()
                self.assertTrue(asset.is_relative_to(ROOT / 'plugins/codex-duo'))
                self.assertEqual(asset.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
        self.assertLessEqual(len(interface['shortDescription']), 30)
        self.assertLessEqual(len(interface['defaultPrompt']), 128)
        self.assertIn('$codex-duo', interface['defaultPrompt'])
        bundled = self.rpc('resources/read', {'uri': mcp.RESOURCE})['result']['contents'][0]['text']
        self.assertIn('<title>Codex Duo · 默认设置</title>', bundled)
        self.assertIn(icon, bundled)
        self.assertNotIn('src="/app.js"', bundled)
        self.assertNotIn('href="/style.css"', bundled)

    def test_unknown_resource_not_filesystem_read(self):
        self.assertEqual(self.rpc('resources/read', {'uri': 'file:///etc/passwd'})['error']['code'], -32002)

    def test_read_and_open_do_not_create_state_directory(self):
        self.call('codex_duo_settings_read')
        opened = self.call('codex_duo_open')
        self.assertFalse((self.root / '.codex-duo').exists())
        self.assertIn('codex-duo/state', opened['_meta'])
        self.assertNotIn('catalog', opened['structuredContent'])

    def test_settings_values_cover_properties_and_valid_pairs(self):
        data = self.call('codex_duo_settings_read')['structuredContent']
        self.assertEqual(set(data['values']), set(data['schema']['properties']))
        pairs = data['schema']['properties']['worker']['enum']
        self.assertIn('gpt-6-luna / high', pairs)
        self.assertNotIn('gpt-6-luna / ultra', pairs)

    def test_partial_settings_update_preserves_other_role(self):
        self.saved()
        value = self.call('codex_duo_settings_update', {'set': {'worker': 'gpt-6-luna / medium'}})
        self.assertEqual(value['structuredContent']['values']['coordinator'], 'gpt-6-astra / high')
        self.assertEqual(self.service.defaults_store.global_store.read(catalog())['document']['selection']['worker']['reasoning_effort'], 'medium')

    def test_settings_and_http_share_state_both_directions(self):
        panel = PanelService(self.root / '.codex-duo', catalog)
        revision = panel.save({'scope':'global', 'selection': self.selection, 'expected_revision': 'none'})['revision']
        self.assertEqual(self.call('codex_duo_state', {'scope':'global'})['structuredContent']['saved']['revision'], revision)
        self.call('codex_duo_settings_update', {'set': {'worker': 'gpt-6-luna / medium'}})
        self.assertEqual(panel.state('global')['saved']['document']['selection']['worker']['reasoning_effort'], 'medium')
        with self.assertRaises(SelectionError):
            panel.save({'scope':'global', 'selection': {**self.selection, 'worker': {'model': 'gpt-6-luna', 'reasoning_effort': 'high'}}, 'expected_revision': revision})

    def test_invalid_arguments_and_pairs_are_tool_errors(self):
        cases = [('codex_duo_settings_update', {'set': {}}), ('codex_duo_settings_update', {'set': {'worker': 'gpt-6-luna / ultra'}}),
                 ('codex_duo_settings_update', {'set': {'worker': []}}), ('codex_duo_save', {'selection': self.selection}),
                 ('codex_duo_open', {'project_root': 'relative'}), ('codex_duo_settings_update', {'set': {'path': '/etc/passwd'}}),
                 ('codex_duo_execution_plan', {'handoff_id': '../../etc/passwd'}), ('codex_duo_unknown', {})]
        for name, arguments in cases:
            with self.subTest(name=name, arguments=arguments):
                self.assertTrue(self.call(name, arguments)['isError'])

    def test_corruption_not_overwritten_by_settings(self):
        self.service.save({'scope':'global','selection':self.selection,'expected_revision':'none'})
        self.service.defaults_store.global_store.path.write_text('{')
        self.assertTrue(self.call('codex_duo_settings_read')['isError'])
        self.assertTrue(self.call('codex_duo_settings_update', {'set': {'worker': 'gpt-6-luna / high'}})['isError'])
        self.assertEqual(self.service.defaults_store.global_store.path.read_text(), '{')

    def test_storage_error_converted_no_stacktrace(self):
        with patch.object(CodexDuoService, 'save', side_effect=PermissionError('/private/not-shown')):
            data = self.call('codex_duo_save', {'selection': self.selection, 'expected_revision': 'none'})
        self.assertEqual(data['structuredContent']['error']['code'], 'storage_unavailable')
        self.assertNotIn('/private/', json.dumps(data))

    def test_new_snapshot_uses_saved_configuration(self):
        first = self.handoff()
        self.service.save({'selection': {**self.selection, 'worker': {'model':'gpt-6-luna','reasoning_effort':'medium'}}, 'expected_revision': self.service.state()['saved']['revision']})
        state = self.service.state()
        second = self.call('codex_duo_prepare', {'task': self.service.template,
            'expected_revision': state['saved']['revision']})['structuredContent']
        self.assertNotEqual(first['id'], second['id'])
        old = self.call('codex_duo_execution_plan', {'handoff_id': first['id']})['structuredContent']
        self.assertEqual(old['worker']['reasoning_effort'], 'high')
        self.assertEqual(second['manifest']['selection']['worker']['reasoning_effort'], 'medium')

    def test_execution_adapter_does_not_run_commands(self):
        prepared = self.handoff()
        with patch('subprocess.run', side_effect=AssertionError('no command execution')):
            plan = self.call('codex_duo_execution_plan', {'handoff_id': prepared['id']})['structuredContent']
        self.assertFalse(plan['execution_started'])
        self.assertFalse(plan['applies_to_current_thread'])
        self.assertTrue(plan['coordinator']['requires_new_task'])
        self.assertEqual(plan['state'], 'approval_required')

    def test_tampered_or_linked_snapshot_refused(self):
        handoff = self.handoff()
        path = Path(handoff['path']) / 'config/project.toml'
        original = path.read_text()
        path.write_text(original + '# tampered')
        self.assertTrue(self.call('codex_duo_execution_plan', {'handoff_id': handoff['id']})['isError'])
        path.unlink()
        other = self.root / 'other'; other.write_text(original); path.symlink_to(other)
        self.assertTrue(self.call('codex_duo_execution_plan', {'handoff_id': handoff['id']})['isError'])

    def test_symlink_state_rejected_for_read(self):
        outside = self.root / 'outside'; outside.mkdir()
        (self.root / '.codex-duo').symlink_to(outside)
        self.assertTrue(self.call('codex_duo_state')['isError'])

    def test_notifications_and_protocol_errors(self):
        self.assertIsNone(self.server.dispatch({'jsonrpc': '2.0', 'method': 'notifications/initialized'}))
        for request in ([], {'jsonrpc': '1.0', 'id': 1}, {'jsonrpc': '2.0', 'id': True, 'method': 'ping'}):
            self.assertEqual(self.server.dispatch(request)['error']['code'], -32600)
        self.assertEqual(self.rpc('sampling/createMessage')['error']['code'], -32601)
        self.assertEqual(self.rpc('tools/call', {'name': 'codex_duo_open', 'arbitrary': True})['error']['code'], -32602)

    def test_stdio_real_process_no_model_calls(self):
        data = '\n'.join([json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}}),
                         json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'}),
                         '{', json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/list'})]) + '\n'
        run = subprocess.run([sys.executable, '-B', str(ROOT/'plugins/codex-duo/mcp/server.py'),
            '--project-root', str(self.root)], input=data, text=True, capture_output=True, timeout=10)
        lines = [json.loads(x) for x in run.stdout.splitlines()]
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[1]['error']['code'], -32700)
        self.assertEqual(len(lines[2]['result']['tools']), 20)
        self.assertFalse((self.root/'.codex-duo').exists())

    def test_oversize_stdio_rejected_then_recovers(self):
        data = 'x' * 70000 + '\n' + json.dumps({'jsonrpc':'2.0','id':4,'method':'ping'}) + '\n'
        run = subprocess.run([sys.executable, '-B', str(ROOT/'plugins/codex-duo/mcp/server.py'),
            '--project-root', str(self.root)], input=data, text=True, capture_output=True, timeout=10)
        lines = [json.loads(x) for x in run.stdout.splitlines()]
        self.assertEqual(lines[0]['error']['code'], -32600)
        self.assertEqual(lines[1]['result'], {})

    def test_process_lock_preserves_disjoint_updates(self):
        self.saved()
        source = '''import sys,time
sys.path.insert(0,sys.argv[1])
from codex_duo_selection import StorageLock
with StorageLock(__import__('pathlib').Path(sys.argv[2])):
 print('locked',flush=True)
 time.sleep(0.3)
'''
        process = subprocess.Popen([sys.executable, '-B', '-c', source, str(ROOT/'plugins/codex-duo/skills/workflow/scripts'),
            str(self.service.defaults_store.global_store.directory)], stdout=subprocess.PIPE, text=True)
        self.assertEqual(process.stdout.readline().strip(), 'locked')
        import time
        start = time.monotonic()
        self.service.settings_update({'worker':'gpt-6-luna / medium'})
        self.assertGreater(time.monotonic()-start, 0.15)
        process.wait(timeout=3); process.stdout.close()


if __name__ == '__main__':
    unittest.main()
