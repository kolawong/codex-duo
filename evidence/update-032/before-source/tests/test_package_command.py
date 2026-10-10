"""Regression coverage for commands accepted by an SDK but rejected by Codex."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.validate_static import validate_stdio_command

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/fusion-minimal'


class PackageCommandTests(unittest.TestCase):
    def test_previous_absolute_command_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'bare executable'):
            validate_stdio_command('/opt/homebrew/bin/python3', PLUGIN)

    def test_bare_executable_is_valid(self):
        validate_stdio_command('python3', PLUGIN)

    def test_relative_escape_and_invalid_tokens_are_rejected(self):
        for value in ['./../outside', 'mcp/server.py', '', None, r'C:\Python\python.exe']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_stdio_command(value, PLUGIN)

    def test_contained_launcher_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'plugin'; root.mkdir()
            (root / 'launch').write_text('fixture')
            validate_stdio_command('./launch', root)
            outside = Path(tmp) / 'outside'; outside.write_text('fixture')
            (root / 'escape').symlink_to(outside)
            with self.assertRaises(ValueError):
                validate_stdio_command('./escape', root)

    def test_actual_manifest_command_starts_packaged_server(self):
        config = json.loads((PLUGIN / 'mcp.json').read_text())['mcpServers']['fusion']
        validate_stdio_command(config['command'], PLUGIN)
        with tempfile.TemporaryDirectory() as tmp:
            args = [a.replace('${PLUGIN_ROOT}', str(PLUGIN)) for a in config['args']]
            args[args.index('--project-root') + 1] = tmp
            requests = [{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
                        {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}]
            result = subprocess.run([config['command'], *args], cwd=PLUGIN,
                input=''.join(json.dumps(r)+'\n' for r in requests),
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            responses = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(responses[0]['result']['serverInfo']['version'],
                             json.loads((PLUGIN/'plugin.json').read_text())['version'])
            self.assertEqual(len(responses[1]['result']['tools']), 7)
            self.assertFalse((Path(tmp)/'.fusion').exists())
