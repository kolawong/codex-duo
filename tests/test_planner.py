"""Offline planner contracts. Fixtures never attest a real host or run a model."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/codex-duo/skills/workflow/scripts'))
from codex_duo_service import CodexDuoService
from codex_duo_selection import SelectionError, default_selection, normalize_catalog, digest
from codex_duo_planner import code_baseline, validate_request


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'home')}); self.env.start()
        self.git('init', '-q'); self.git('config', 'user.name', 'Fixture'); self.git('config', 'user.email', 'fixture@example.invalid')
        (self.root / '.gitignore').write_text('.codex-duo/\nhome/\nignored.txt\n.env\n')
        (self.root / 'a.py').write_text('before\n')
        self.git('add', '.'); self.git('commit', '-qm', 'fixture')
        self.catalog = normalize_catalog({'models': [{'slug': 'planner', 'visibility': 'list', 'supported_reasoning_levels': [{'effort': 'high'}]}]})
        self.service = CodexDuoService(self.root / '.codex-duo', lambda: self.catalog)
        self.workflow = {'activation': 'manual', 'coordinator_mode': 'current_thread', 'max_worker_turns': 3, 'max_parallel_workers': 1,
                         'planner_mode': 'plan_only', 'planner_model': 'planner', 'planner_reasoning_effort': 'high', 'max_planner_turns': 2}
        self.service.save({'selection': default_selection(self.catalog), 'workflow': self.workflow, 'expected_revision': 'none'})
        self.request = {'schema_version': 1, 'task_id': 'plan-example', 'goal': 'Plan a bounded feature', 'read_paths': ['a.py', 'new.py'], 'questions': []}
        self.host = {'tool': 'offline_readonly_fixture', 'model': 'planner', 'reasoning_effort': 'high', 'filesystem': 'read_only',
                     'network': 'disabled', 'process_execution': 'disabled', 'writes': 'disabled', 'agent_spawn': 'disabled', 'enforcement': 'host', 'approval_escalation': 'disabled', 'external_tools': 'disabled'}
        self.plan = self.call('begin', request=self.request, invocation='explicit')
        self.pid = self.plan['plan_id']

    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True).stdout

    def call(self, operation, **args):
        return self.service.planning(operation, {'project_root': str(self.root), **({'plan_id': self.pid} if hasattr(self, 'pid') else {}), **args})

    def reserve(self): return self.call('reserve', host_capabilities=self.host)

    def result(self, dispatch):
        return {'schema_version': 1, 'plan_id': self.pid, 'dispatch_id': dispatch['dispatch_id'],
                'baseline_sha256': self.plan['baseline_sha256'], 'summary': 'Proposed bounded implementation',
                'steps': ['Review and edit a.py after approval'], 'risks': [], 'questions': [],
                'suggested_tests': [{'argv': ['python3', '-m', 'unittest'], 'status': 'not_run'}]}

    def finish(self, dispatch, **changes):
        return self.call('complete', dispatch_id=dispatch['dispatch_id'], outcome='completed', native_receipt='offline fixture receipt', result={**self.result(dispatch), **changes})

    def assertCode(self, code, fn, *args, **kwargs):
        with self.assertRaises(SelectionError) as caught: fn(*args, **kwargs)
        self.assertEqual(code, caught.exception.code)

    def test_plan_only_returns_current_chat_review_and_no_worker(self):
        before = (self.root / 'a.py').read_bytes()
        dispatch = self.reserve(); contract = dispatch['dispatch_contract']
        self.assertEqual([], contract['allowed_write_paths'])
        self.assertFalse(contract['run_tests']); self.assertFalse(contract['spawn_agents']); self.assertFalse(contract['approve_execution'])
        self.assertEqual('in_memory_to_coordinator', contract['return_result'])
        result = self.finish(dispatch)
        self.assertEqual('awaiting_user_review', result['state']); self.assertFalse(result['worker_execution_allowed'])
        self.assertFalse(result['execution_started']); self.assertEqual(before, (self.root / 'a.py').read_bytes())
        self.assertFalse((self.root / '.codex-duo' / 'handoffs').exists()); self.assertFalse((self.root / '.codex-duo' / 'runs').exists())
        self.assertCode('plan_finished', self.reserve)
        self.assertCode('invalid_handoff', self.service.parallel, 'plan', {'project_root': str(self.root), 'handoff_id': self.pid, 'host_capacity': 1})

    def test_missing_prompt_only_and_wrong_model_capabilities_fail_closed(self):
        self.assertCode('readonly_host_required', self.call, 'reserve')
        for field in ('filesystem', 'network', 'process_execution', 'writes', 'agent_spawn', 'enforcement', 'approval_escalation', 'external_tools'):
            self.assertCode('readonly_host_required', self.call, 'reserve', host_capabilities={**self.host, field: 'prompt'})
        self.assertCode('readonly_host_required', self.call, 'reserve', host_capabilities={**self.host, 'read_only': True})
        self.assertCode('planner_model_unavailable', self.call, 'reserve', host_capabilities={**self.host, 'model': 'different'})
        self.assertEqual(2, self.call('status')['remaining_planner_turns'])

    def test_total_budget_failure_restart_and_repeat_begin(self):
        for _ in range(2):
            dispatch = self.reserve()
            self.call('complete', dispatch_id=dispatch['dispatch_id'], outcome='failed', native_receipt='offline spawn denied')
        self.service = CodexDuoService(self.root / '.codex-duo', lambda: self.catalog)
        repeated = self.call('begin', request=self.request, invocation='explicit')
        self.assertEqual(0, repeated['remaining_planner_turns']); self.assertEqual('budget_exhausted', repeated['state'])
        self.assertCode('budget_exhausted', self.reserve)
        self.assertCode('plan_locked', self.call, 'begin', request={**self.request, 'goal': 'changed'}, invocation='explicit')

    def test_concurrent_reservations_cannot_exceed_one_active(self):
        def attempt(_):
            try: return self.reserve()
            except SelectionError as exc: return exc.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(attempt, range(2)))
        self.assertEqual(1, sum(isinstance(x, dict) for x in results)); self.assertIn('planner_active', results)

    def test_duplicate_result_idempotent_conflicting_result_rejected(self):
        dispatch = self.reserve(); first = self.finish(dispatch); repeated = self.finish(dispatch)
        self.assertEqual(first, repeated)
        self.assertCode('invalid_dispatch', self.finish, dispatch, summary='different')
        self.assertCode('invalid_dispatch', self.call, 'complete', dispatch_id='planner-999', outcome='failed', native_receipt='fake')

    def test_model_catalog_change_and_saved_model_snapshot(self):
        saved = self.service.store.read(self.catalog)
        self.service.save({'selection': default_selection(self.catalog), 'workflow': {**self.workflow, 'max_planner_turns': 3}, 'expected_revision': saved['revision']})
        self.assertEqual(1, self.reserve()['remaining_planner_turns'])
        self.call('complete', dispatch_id='planner-001', outcome='failed', native_receipt='fixture')
        self.catalog = normalize_catalog({'models': [{'slug': 'different', 'visibility': 'list', 'supported_reasoning_levels': [{'effort': 'high'}]}]})
        self.assertCode('catalog_changed', self.reserve)

    def test_changed_tracked_untracked_index_head_and_ignored_scope(self):
        (self.root / 'a.py').write_text('changed\n'); self.assertCode('baseline_changed', self.reserve)
        self.assertEqual('stale', self.call('status')['state'])
        self.git('checkout', '--', 'a.py')
        (self.root / 'new_untracked.py').write_text('new'); self.assertCode('baseline_changed', self.reserve)
        (self.root / 'new_untracked.py').unlink()
        self.git('update-index', '--chmod=+x', 'a.py'); self.assertCode('baseline_changed', self.reserve)
        self.git('reset', '-q', 'HEAD', '--', 'a.py')
        self.git('commit', '--allow-empty', '-qm', 'new head'); self.assertCode('baseline_changed', self.reserve)
        self.git('reset', '--soft', 'HEAD~1')
        dispatch = self.reserve(); (self.root / 'new.py').write_text('new scoped file')
        self.assertCode('baseline_changed', self.finish, dispatch)
        (self.root / 'new.py').unlink()
        self.finish(dispatch)
        (self.root / 'ignored.txt').write_text('ignored unrelated')
        self.assertEqual('awaiting_user_review', self.call('status')['state'])
        baseline = code_baseline(self.root, ['ignored.txt'])
        (self.root / 'ignored.txt').write_text('changed ignored relevant')
        self.assertNotEqual(baseline, code_baseline(self.root, ['ignored.txt']))

    def test_result_rejects_wrong_identity_hash_diff_tests_or_approval(self):
        dispatch = self.reserve()
        for changes in ({'plan_id': '0'*24}, {'dispatch_id': 'planner-999'}, {'baseline_sha256': '0'*64},
                        {'diff': 'fake'}, {'approved': True}, {'suggested_tests': [{'argv': ['true'], 'status': 'passed'}]},
                        {'suggested_tests': [{'argv': ['true'], 'status': 'not_run', 'exit_code': 0}]}):
            self.assertCode('invalid_plan_result', self.finish, dispatch, **changes)
        self.assertEqual('planner_reserved', self.call('status')['state'])
        self.finish(dispatch)

    def test_hash_tamper_and_linked_storage_fail_closed(self):
        path = self.root / '.codex-duo' / 'plans' / (self.pid + '.json')
        original = path.read_bytes(); value = json.loads(original)
        value['payload']['snapshot']['planner']['max_turns'] = 5
        path.write_text(json.dumps(value)); self.assertCode('invalid_plan', self.call, 'status')
        path.write_bytes(original); path.unlink(); path.symlink_to(self.root / 'a.py')
        self.assertCode('unsafe_storage', self.call, 'status')

    def test_result_hash_rechecked_after_restart(self):
        dispatch = self.reserve(); self.finish(dispatch)
        path = self.root / '.codex-duo' / 'plans' / (self.pid + '.json'); envelope = json.loads(path.read_bytes())
        envelope['payload']['result']['summary'] = 'tampered'; envelope['sha256'] = digest(envelope['payload'])
        path.write_text(json.dumps(envelope)); self.assertCode('invalid_plan', self.call, 'status')

    def test_requests_are_independent_strict_and_explicit(self):
        self.assertCode('explicit_planning_required', self.call, 'begin', request=self.request, invocation='automatic')
        for path in ('../outside', '/absolute', '.git/config', '.codex-duo/selection.json', './a.py', 'a/../a.py'):
            self.assertCode('invalid_plan_contract', validate_request, {**self.request, 'read_paths': [path]})
        self.assertCode('invalid_plan_contract', validate_request, {**self.request, 'allowed_paths': ['a.py']})
        self.assertCode('invalid_plan_contract', validate_request, {**self.request, 'schema_version': True})

    def test_symlinks_large_files_credentials_and_non_git_fail_closed(self):
        (self.root / 'linked').symlink_to('/tmp')
        self.assertCode('baseline_unavailable', code_baseline, self.root, ['linked'])
        (self.root / 'linked').unlink()
        with (self.root / 'large.bin').open('wb') as handle: handle.truncate(32 * 1024 * 1024 + 1)
        self.assertCode('baseline_unavailable', code_baseline, self.root, ['a.py'])
        (self.root / 'large.bin').unlink()
        # Credential-looking paths are rejected before their content is opened.
        (self.root / '.env').write_text('DO_NOT_READ=fixture')
        self.assertCode('baseline_unavailable', code_baseline, self.root, ['.env'])
        outside = self.root / 'outside'; outside.mkdir()
        self.assertCode('baseline_unavailable', code_baseline, outside, ['a.py'])

    def test_mcp_and_cli_lifecycle_routes(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('planner_test_mcp', ROOT / 'plugins/codex-duo/mcp/server.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        server = module.MCPServer(self.service)
        def mcp(operation, **body):
            return server.call('codex_duo_planner_' + operation, {'project_root': str(self.root), **body})['structuredContent']
        begin = mcp('begin', request=self.request, invocation='explicit')
        self.assertEqual(self.pid, begin['plan_id'])
        dispatch = mcp('reserve', plan_id=self.pid, host_capabilities=self.host)
        done = mcp('complete', plan_id=self.pid, dispatch_id=dispatch['dispatch_id'], outcome='completed',
                   native_receipt='MCP offline fixture', result=self.result(dispatch))
        self.assertEqual('awaiting_user_review', done['state'])
        self.assertEqual(done, mcp('status', plan_id=self.pid))
        # CLI uses a strict model-catalog-only stub; it rejects all inference commands.
        fixture = self.root / 'home' / 'catalog.py'; fixture.parent.mkdir(exist_ok=True)
        fixture.write_text('#!/usr/bin/env python3\nimport json,sys\n'
                           'if sys.argv[1:] == ["--version"]: print("offline fixture")\n'
                           'elif sys.argv[1:] == ["debug","models","--bundled"]: print(json.dumps({"models":[{"slug":"planner","visibility":"list","supported_reasoning_levels":[{"effort":"high"}]}]}))\n'
                           'else: raise SystemExit(99)\n')
        fixture.chmod(0o755)
        command = [sys.executable, '-B', str(ROOT / 'plugins/codex-duo/skills/workflow/scripts/codex_duo_workflow.py')]
        request = {**self.request, 'task_id': 'cli-plan'}
        request_path = fixture.parent / 'request.json'; request_path.write_text(json.dumps(request))
        host_path = fixture.parent / 'host.json'; host_path.write_text(json.dumps(self.host))
        env = {**os.environ, 'CODEX_DUO_CODEX_CLI': str(fixture)}
        def cli(operation, *args):
            result = subprocess.run([*command, 'planner_' + operation, '--project-root', str(self.root), *args],
                                    capture_output=True, text=True, check=True, env=env)
            return json.loads(result.stdout)
        plan = cli('begin', '--request', str(request_path), '--invocation', 'explicit')
        reserved = cli('reserve', '--plan-id', plan['plan_id'], '--host-capabilities', str(host_path))
        finished = cli('complete', '--plan-id', plan['plan_id'], '--dispatch-id', reserved['dispatch_id'],
                       '--native-receipt', 'CLI offline fixture', '--outcome', 'failed')
        self.assertEqual(1, finished['remaining_planner_turns'])
        self.assertEqual(finished, cli('status', '--plan-id', plan['plan_id']))

    def test_readonly_shell_host_and_native_agent_template(self):
        import tomllib
        self.host['process_execution'] = 'read_only_sandbox'
        dispatch = self.reserve()
        template = Path(dispatch['dispatch_contract']['agent_template'])
        config = tomllib.loads(template.read_text())
        self.assertEqual((ROOT / '.codex/agents/codex_duo_planner.toml').read_bytes(), template.read_bytes())
        self.assertEqual('read-only', config['sandbox_mode'])
        self.assertEqual('never', config['approval_policy'])
        self.assertFalse(config['agents']['enabled'])
        self.assertFalse(config['apps']['_default']['enabled'])
        self.assertFalse(config['mcp_servers']['codex-duo']['enabled'])
        self.assertEqual('false', config['mcp_servers']['codex-duo']['command'])
        self.assertNotIn('model', config); self.assertNotIn('model_reasoning_effort', config)
        self.assertTrue(Path(dispatch['dispatch_contract']['host_guide']).is_file())
        build = (ROOT / 'macos/build.sh').read_text()
        for artifact in ('codex_duo_planner.py', 'codex_duo_planner.toml', 'planner-host.md'):
            self.assertIn(artifact, build)
        self.finish(dispatch)

    def test_total_size_file_count_and_submodule_bounds(self):
        with patch('codex_duo_planner.MAX_TOTAL_BYTES', 1):
            self.assertCode('baseline_unavailable', code_baseline, self.root, ['a.py'])
        with patch('codex_duo_planner.MAX_FILES', 1):
            self.assertCode('baseline_unavailable', code_baseline, self.root, ['a.py'])
        head = self.git('rev-parse', 'HEAD').decode().strip()
        self.git('update-index', '--add', '--cacheinfo', '160000,' + head + ',submodule')
        self.assertCode('baseline_unavailable', code_baseline, self.root, ['a.py'])

    def test_failed_completion_never_carries_success_result(self):
        dispatch = self.reserve()
        self.assertCode('invalid_plan_result', self.call, 'complete', dispatch_id=dispatch['dispatch_id'], outcome='failed', native_receipt='fixture', result=self.result(dispatch))
        self.call('complete', dispatch_id=dispatch['dispatch_id'], outcome='blocked', native_receipt='host readonly unavailable')
        self.assertEqual('ready_for_readonly_planner', self.call('status')['state'])


if __name__ == '__main__': unittest.main()
