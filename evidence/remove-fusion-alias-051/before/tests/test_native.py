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
spec = importlib.util.spec_from_file_location('fusion_mcp', ROOT / 'plugins/fusion-minimal/mcp/server.py')
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)
from fusion_selection import normalize_catalog, SelectionError
from fusion_service import FusionService
from panel.server import PanelService


def catalog():
    return normalize_catalog({'models': [
        {'slug': name, 'visibility': 'list', 'display_name': name,
         'supported_reasoning_levels': [{'effort': e} for e in efforts], 'default_reasoning_level': 'high'}
        for name, efforts in [('gpt-6-astra', ['high', 'ultra']), ('gpt-6-luna', ['high', 'medium']),
                              ('gpt-6.1-sol', ['high'])]]})


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = FusionService(self.root / '.fusion', catalog)
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
        self.assertEqual(settings, {'readTool': 'fusion.settings_read', 'updateTool': 'fusion.settings_update'})
        self.assertNotIn('sampling', data['capabilities'])

    def test_entrypoint_metadata_and_settings_action(self):
        tools = {t['name']: t for t in self.rpc('tools/list')['result']['tools']}
        self.assertEqual(tools['fusion.open']['_meta']['openai/ui']['entrypoints'], [{'type': 'thread'}])
        self.assertEqual(tools['fusion.open']['_meta']['ui']['resourceUri'], mcp.RESOURCE)
        layout = self.call('fusion.settings_read')['structuredContent']['layout']
        self.assertEqual(layout[0]['items'][-1]['tool'], 'fusion.open')
        self.assertEqual(tools['fusion.save']['_meta']['ui']['visibility'], ['app'])
        self.assertTrue(tools['fusion.execution_plan']['annotations']['readOnlyHint'])

    def test_resource_closed_network_fullscreen_self_contained(self):
        item = self.rpc('resources/read', {'uri': mcp.RESOURCE})['result']['contents'][0]
        self.assertEqual(item['mimeType'], 'text/html;profile=mcp-app')
        self.assertEqual(item['_meta']['openai/ui']['availableDisplayModes'], ['fullscreen'])
        self.assertTrue(all(not domains for domains in item['_meta']['ui']['csp'].values()))
        self.assertNotIn('src="/app.js"', item['text'])
        self.assertNotIn('href="/style.css"', item['text'])
        self.assertIn('fusionTransport', item['text'])

    def test_codex_duo_branding_preserves_internal_contract(self):
        from urllib.parse import unquote
        tools = {t['name']: t for t in self.rpc('tools/list')['result']['tools']}
        self.assertEqual(tools['fusion.open']['title'], 'Codex Duo 项目设置')
        icon = (ROOT / 'plugins/fusion-minimal/assets/tandem.svg').read_text()
        self.assertEqual(unquote(tools['fusion.open']['icons'][0]['src'].split(',', 1)[1]), icon)
        self.assertEqual(self.rpc('initialize')['result']['serverInfo']['version'], '0.5.0')
        self.assertEqual(mcp.RESOURCE, 'ui://fusion-minimal/model-desk-v4')
        public = json.loads((ROOT / 'plugins/fusion-minimal/plugin.json').read_text())
        native = json.loads((ROOT / 'plugins/fusion-minimal/.codex-plugin/plugin.json').read_text())
        interface = public['extensions']['com.openai']['interface']
        self.assertEqual(interface, native['interface'])
        for manifest in (public, native):
            self.assertEqual(manifest['name'], 'fusion-minimal')
            self.assertEqual(manifest['version'], '0.5.0')
            self.assertLessEqual(len(manifest['description']), 30)
        self.assertEqual(interface['displayName'], 'Codex Duo')
        self.assertEqual(interface['logo'], 'assets/tandem.svg')
        self.assertEqual(interface['composerIcon'], 'assets/tandem.svg')
        self.assertLessEqual(len(interface['shortDescription']), 30)
        self.assertEqual(interface['defaultPrompt'], 'Use the saved Codex Duo defaults for this project. Keep planning and verification in this chat, prepare task details internally, and use one native worker when supported. Reuse existing task authorization; do not reopen settings unless needed.')
        bundled = self.rpc('resources/read', {'uri': mcp.RESOURCE})['result']['contents'][0]['text']
        self.assertIn('<title>Codex Duo · 项目设置</title>', bundled)
        self.assertIn(icon, bundled)
        self.assertNotIn('src="/app.js"', bundled)
        self.assertNotIn('href="/style.css"', bundled)

    def test_unknown_resource_not_filesystem_read(self):
        self.assertEqual(self.rpc('resources/read', {'uri': 'file:///etc/passwd'})['error']['code'], -32002)

    def test_read_and_open_do_not_create_state_directory(self):
        self.call('fusion.settings_read')
        opened = self.call('fusion.open')
        self.assertFalse((self.root / '.fusion').exists())
        self.assertIn('fusion/state', opened['_meta'])
        self.assertNotIn('catalog', opened['structuredContent'])

    def test_settings_values_cover_properties_and_valid_pairs(self):
        data = self.call('fusion.settings_read')['structuredContent']
        self.assertEqual(set(data['values']), set(data['schema']['properties']))
        pairs = data['schema']['properties']['worker']['enum']
        self.assertIn('gpt-6-luna / high', pairs)
        self.assertNotIn('gpt-6-luna / ultra', pairs)

    def test_partial_settings_update_preserves_other_role(self):
        self.saved()
        value = self.call('fusion.settings_update', {'set': {'worker': 'gpt-6-luna / medium'}})
        self.assertEqual(value['structuredContent']['values']['coordinator'], 'gpt-6-astra / high')
        self.assertEqual(self.service.store.read(catalog())['document']['selection']['worker']['reasoning_effort'], 'medium')

    def test_settings_and_http_share_state_both_directions(self):
        panel = PanelService(self.root / '.fusion', catalog)
        revision = panel.save({'selection': self.selection, 'expected_revision': 'none'})['revision']
        self.assertEqual(self.call('fusion.state')['structuredContent']['saved']['revision'], revision)
        self.call('fusion.settings_update', {'set': {'worker': 'gpt-6-luna / medium'}})
        self.assertEqual(panel.state()['saved']['document']['selection']['worker']['reasoning_effort'], 'medium')
        with self.assertRaises(SelectionError):
            panel.save({'selection': {**self.selection, 'worker': {'model': 'gpt-6-luna', 'reasoning_effort': 'high'}}, 'expected_revision': revision})

    def test_invalid_arguments_and_pairs_are_tool_errors(self):
        cases = [('fusion.settings_update', {'set': {}}), ('fusion.settings_update', {'set': {'worker': 'gpt-6-luna / ultra'}}),
                 ('fusion.settings_update', {'set': {'worker': []}}), ('fusion.save', {'selection': self.selection}),
                 ('fusion.open', {'project_root': 'relative'}), ('fusion.settings_update', {'set': {'path': '/etc/passwd'}}),
                 ('fusion.execution_plan', {'handoff_id': '../../etc/passwd'}), ('fusion.unknown', {})]
        for name, arguments in cases:
            with self.subTest(name=name, arguments=arguments):
                self.assertTrue(self.call(name, arguments)['isError'])

    def test_corruption_not_overwritten_by_settings(self):
        self.saved()
        self.service.store.path.write_text('{')
        self.assertTrue(self.call('fusion.settings_read')['isError'])
        self.assertTrue(self.call('fusion.settings_update', {'set': {'worker': 'gpt-6-luna / high'}})['isError'])
        self.assertEqual(self.service.store.path.read_text(), '{')

    def test_storage_error_converted_no_stacktrace(self):
        with patch.object(FusionService, 'save', side_effect=PermissionError('/private/not-shown')):
            data = self.call('fusion.save', {'selection': self.selection, 'expected_revision': 'none'})
        self.assertEqual(data['structuredContent']['error']['code'], 'storage_unavailable')
        self.assertNotIn('/private/', json.dumps(data))

    def test_new_snapshot_uses_saved_configuration(self):
        first = self.handoff()
        self.call('fusion.settings_update', {'set': {'worker': 'gpt-6-luna / medium'}})
        state = self.service.state()
        second = self.call('fusion.prepare', {'task': self.service.template,
            'expected_revision': state['saved']['revision']})['structuredContent']
        self.assertNotEqual(first['id'], second['id'])
        old = self.call('fusion.execution_plan', {'handoff_id': first['id']})['structuredContent']
        self.assertEqual(old['worker']['reasoning_effort'], 'high')
        self.assertEqual(second['manifest']['selection']['worker']['reasoning_effort'], 'medium')

    def test_execution_adapter_does_not_run_commands(self):
        prepared = self.handoff()
        with patch('subprocess.run', side_effect=AssertionError('no command execution')):
            plan = self.call('fusion.execution_plan', {'handoff_id': prepared['id']})['structuredContent']
        self.assertFalse(plan['execution_started'])
        self.assertFalse(plan['applies_to_current_thread'])
        self.assertTrue(plan['coordinator']['requires_new_task'])
        self.assertEqual(plan['state'], 'approval_required')

    def test_tampered_or_linked_snapshot_refused(self):
        handoff = self.handoff()
        path = Path(handoff['path']) / 'config/project.toml'
        original = path.read_text()
        path.write_text(original + '# tampered')
        self.assertTrue(self.call('fusion.execution_plan', {'handoff_id': handoff['id']})['isError'])
        path.unlink()
        other = self.root / 'other'; other.write_text(original); path.symlink_to(other)
        self.assertTrue(self.call('fusion.execution_plan', {'handoff_id': handoff['id']})['isError'])

    def test_symlink_state_rejected_for_read(self):
        outside = self.root / 'outside'; outside.mkdir()
        (self.root / '.fusion').symlink_to(outside)
        self.assertTrue(self.call('fusion.state')['isError'])

    def test_notifications_and_protocol_errors(self):
        self.assertIsNone(self.server.dispatch({'jsonrpc': '2.0', 'method': 'notifications/initialized'}))
        for request in ([], {'jsonrpc': '1.0', 'id': 1}, {'jsonrpc': '2.0', 'id': True, 'method': 'ping'}):
            self.assertEqual(self.server.dispatch(request)['error']['code'], -32600)
        self.assertEqual(self.rpc('sampling/createMessage')['error']['code'], -32601)
        self.assertEqual(self.rpc('tools/call', {'name': 'fusion.open', 'arbitrary': True})['error']['code'], -32602)

    def test_stdio_real_process_no_model_calls(self):
        data = '\n'.join([json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}}),
                         json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'}),
                         '{', json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/list'})]) + '\n'
        run = subprocess.run([sys.executable, '-B', str(ROOT/'plugins/fusion-minimal/mcp/server.py'),
            '--project-root', str(self.root)], input=data, text=True, capture_output=True, timeout=10)
        lines = [json.loads(x) for x in run.stdout.splitlines()]
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[1]['error']['code'], -32700)
        self.assertEqual(len(lines[2]['result']['tools']), 9)
        self.assertFalse((self.root/'.fusion').exists())

    def test_oversize_stdio_rejected_then_recovers(self):
        data = 'x' * 70000 + '\n' + json.dumps({'jsonrpc':'2.0','id':4,'method':'ping'}) + '\n'
        run = subprocess.run([sys.executable, '-B', str(ROOT/'plugins/fusion-minimal/mcp/server.py'),
            '--project-root', str(self.root)], input=data, text=True, capture_output=True, timeout=10)
        lines = [json.loads(x) for x in run.stdout.splitlines()]
        self.assertEqual(lines[0]['error']['code'], -32600)
        self.assertEqual(lines[1]['result'], {})

    def test_process_lock_preserves_disjoint_updates(self):
        self.saved()
        source = '''import sys,time
sys.path.insert(0,sys.argv[1])
from fusion_selection import StorageLock
with StorageLock(__import__('pathlib').Path(sys.argv[2])):
 print('locked',flush=True)
 time.sleep(0.3)
'''
        process = subprocess.Popen([sys.executable, '-B', '-c', source, str(ROOT/'plugins/fusion-minimal/skills/fusion/scripts'),
            str(self.root/'.fusion')], stdout=subprocess.PIPE, text=True)
        self.assertEqual(process.stdout.readline().strip(), 'locked')
        import time
        start = time.monotonic()
        self.service.settings_update({'worker':'gpt-6-luna / medium'})
        self.assertGreater(time.monotonic()-start, 0.15)
        process.wait(timeout=3); process.stdout.close()


if __name__ == '__main__':
    unittest.main()
