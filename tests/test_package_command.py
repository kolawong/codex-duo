# Test storage is deliberately independent of the user's real Codex home.
import os as _test_os, tempfile as _test_tempfile, atexit as _test_atexit
if not _test_os.environ.get('CODEX_DUO_TEST_CODEX_HOME'):
    _test_home = _test_tempfile.TemporaryDirectory(prefix='duo-test-home-')
    _test_atexit.register(_test_home.cleanup)
    _test_os.environ['CODEX_DUO_TEST_CODEX_HOME'] = _test_home.name
_test_os.environ['CODEX_HOME'] = _test_os.environ['CODEX_DUO_TEST_CODEX_HOME']
"""Regression coverage for commands accepted by an SDK but rejected by Codex."""
import json
import os
import shutil
import shlex
import sys
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.validate_static import validate_stdio_command

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/codex-duo'


class PackageCommandTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch as _home_patch
        _home = _test_tempfile.TemporaryDirectory(prefix='duo-case-home-')
        self.addCleanup(_home.cleanup)
        _environment = _home_patch.dict(_test_os.environ, {'CODEX_HOME': _home.name})
        _environment.start(); self.addCleanup(_environment.stop)

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
            (root / 'launch').chmod(0o755)
            validate_stdio_command('./launch', root)
            outside = Path(tmp) / 'outside'; outside.write_text('fixture')
            (root / 'escape').symlink_to(outside)
            with self.assertRaises(ValueError):
                validate_stdio_command('./escape', root)

    def test_actual_manifest_command_starts_packaged_server(self):
        config = json.loads((PLUGIN / 'mcp.json').read_text())['mcpServers']['codex-duo']
        validate_stdio_command(config['command'], PLUGIN)
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / 'installed plugin'
            shutil.copytree(PLUGIN, copied)
            # Exercise the declared startup root exactly as the host expands it.
            # Overriding --project-root here hid stale source checkout paths.
            args = [a.replace('${PLUGIN_ROOT}', str(copied)) for a in config['args']]
            requests = [{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
                        {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}]
            result = subprocess.run([config['command'], *args], cwd=copied,
                input=''.join(json.dumps(r)+'\n' for r in requests),
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            responses = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(responses[0]['result']['serverInfo']['version'],
                             json.loads((PLUGIN/'plugin.json').read_text())['version'])
            self.assertEqual(len(responses[1]['result']['tools']), 20)
            self.assertFalse((copied/'.codex-duo').exists())

    def test_launcher_without_path_and_from_unrelated_cwd(self):
        # The supported local macOS deployment already has Homebrew Python.
        candidates = [candidate for directory in ['/opt/homebrew/bin', '/usr/local/bin']
                      for candidate in Path(directory).glob('python3*')
                      if candidate.name == 'python3' or candidate.name.removeprefix('python3.').isdigit()]
        if not any(candidate.is_file() and subprocess.run(
                [str(candidate), '-B', '-c', 'import sys; sys.exit(sys.version_info < (3,11))'],
                capture_output=True, timeout=3).returncode == 0 for candidate in candidates):
            self.skipTest('requires the existing local Python deployment')
        with tempfile.TemporaryDirectory(prefix='codex-duo space ') as tmp:
            copied = Path(tmp) / 'plugin space'
            shutil.copytree(PLUGIN, copied)
            (Path(tmp) / 'project').mkdir()
            config = json.loads((copied / 'mcp.json').read_text())['mcpServers']['codex-duo']
            args = list(config['args'])
            args[args.index('--project-root') + 1] = str(Path(tmp) / 'project')
            env = dict(os.environ, PATH='', PLUGIN_ROOT='/nonexistent/stale-root')
            with self.assertRaises(FileNotFoundError):
                subprocess.run(['python3', '--version'], env=env, check=True)
            requests = [{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
                        {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}},
                        {'jsonrpc':'2.0','id':3,'method':'resources/list','params':{}},
                        {'jsonrpc':'2.0','id':4,'method':'tools/call',
                         'params':{'name':'codex_duo_settings_read','arguments':{}}}]
            run = subprocess.run([str(copied / config['command']), *args], cwd='/tmp', env=env,
                input=''.join(json.dumps(r)+'\n' for r in requests), capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            replies = [json.loads(line) for line in run.stdout.splitlines()]
            self.assertEqual(len(replies[1]['result']['tools']), 20)
            self.assertEqual(replies[2]['result']['resources'][0]['uri'], 'ui://codex-duo/model-desk-v4')
            self.assertFalse(replies[3]['result'].get('isError'), replies[3])
            self.assertEqual(set(replies[3]['result']['structuredContent']['values']), {
                'coordinator', 'worker', 'activation', 'agent_activity', 'coordinator_mode',
                'worker_strategy', 'worker_profile_light', 'worker_profile_standard', 'worker_profile_complex',
                'max_worker_turns', 'max_parallel_workers', 'planner_mode',
                'planner_model', 'planner_reasoning_effort', 'max_planner_turns'})
            self.assertFalse((Path(tmp) / 'project' / '.codex-duo').exists())

    def _launcher_fixture(self, compatible_unversioned):
        with tempfile.TemporaryDirectory(prefix='codex-duo python space ') as tmp:
            directory = Path(tmp)
            # Isolate fixed fallback paths too: a developer's newer system Python
            # must not hide the incompatible-python3/versioned-only regression.
            launcher = (PLUGIN / 'mcp/launch.sh').read_text()
            for source in ['/opt/homebrew/bin', '/usr/local/bin', '/usr/bin/python3']:
                launcher = launcher.replace(source, str(directory / 'missing' / source.lstrip('/')))
            (directory / 'launch.sh').write_text(launcher)
            (directory / 'launch.sh').chmod(0o755)
            (directory / 'server.py').write_text(
                'import json, os, sys\nprint(json.dumps({"selected": os.environ.get("CODEX_DUO_LAUNCHER_SELECTED"), "args": sys.argv[1:]}))\n')
            for name, selected in [('python3', 'unversioned' if compatible_unversioned else None),
                                   ('python3.10', None), ('python3.11', 'versioned')]:
                executable = directory / name
                body = '#!/bin/sh\n'
                if selected is None:
                    body += 'exit 1\n'  # Existing interpreter rejects the >=3.11 probe.
                else:
                    body += f'export CODEX_DUO_LAUNCHER_SELECTED={selected}\nexec {shlex.quote(sys.executable)} "$@"\n'
                executable.write_text(body)
                executable.chmod(0o755)
            # Executable helper names must not be considered interpreters.
            helper = directory / 'python3.10-config'
            helper.write_text('#!/bin/sh\n: > "${CODEX_DUO_HELPER_MARKER}"\nexit 1\n')
            helper.chmod(0o755)
            marker = directory / 'helper-invoked'
            run = subprocess.run([str(directory / 'launch.sh'), '--project-root', tmp],
                cwd='/tmp', env=dict(os.environ, PATH=tmp, CODEX_DUO_HELPER_MARKER=str(marker)),
                capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            reply = json.loads(run.stdout)
            self.assertEqual(reply['selected'], 'unversioned' if compatible_unversioned else 'versioned')
            self.assertEqual(reply['args'], ['--project-root', tmp])
            self.assertFalse(marker.exists())

    def test_versioned_python_after_incompatible_unversioned_in_spaced_path(self):
        self._launcher_fixture(compatible_unversioned=False)

    def test_compatible_unversioned_python_keeps_priority(self):
        self._launcher_fixture(compatible_unversioned=True)

    def test_nonexecutable_launcher_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'launch').write_text('#!/bin/sh\n')
            with self.assertRaisesRegex(ValueError, 'executable'):
                validate_stdio_command('./launch', root)
