"""Isolated byte fixtures only: never repair/replay a real Worker result."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import test_parallel as worker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/codex-duo/skills/workflow/scripts'))
import codex_duo as gate
from codex_duo_selection import SelectionError


class DiffEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.project = self.root / 'project'; self.project.mkdir()
        self.task = {'schema_version': 1, 'task_id': 'offline-diff', 'goal': 'scoped edit',
                     'allowed_paths': ['evidence/probe.txt'], 'acceptance': ['exact bytes'], 'tests': [['offline-fixture']]}
        (self.project / 'evidence').mkdir(); self.file = self.project / 'evidence/probe.txt'; self.file.write_bytes(b'before\n')
        self.evidence = self.root / 'evidence'; self.evidence.mkdir()
        self.baseline = self.evidence / 'before'; self.patch = self.evidence / 'change.diff'

    def snapshot(self):
        return gate.evidence_snapshot(self.task, str(self.project), self.baseline)

    def diff(self):
        return gate.evidence_diff(self.task, str(self.project), self.baseline, self.patch)

    def validate(self, patch, changed=None):
        self.patch.write_bytes(patch.encode('utf-8')); (self.evidence / 'test.log').write_bytes(b'OFFLINE FIXTURE ONLY')
        result = {'schema_version': 1, 'task_id': self.task['task_id'], 'status': 'completed',
                  'summary': 'Offline fixture, no native model', 'changed_paths': changed or self.task['allowed_paths'],
                  'diff': gate.reference(self.patch, self.evidence), 'tests': [{'argv': self.task['tests'][0],
                    'exit_code': 0, 'log': gate.reference(self.evidence / 'test.log', self.evidence)}], 'blockers': []}
        return gate.verify(self.task, result, self.evidence)

    def test_actual_failed_sample_stays_rejected_with_actionable_prefix_diagnosis(self):
        patch = (ROOT / 'tests/fixtures/manual-review-unprefixed.diff').read_text()
        with self.assertRaisesRegex(gate.EvidenceError, 'invalid diff path prefix.*snapshot then diff'):
            gate.diff_paths(patch)

    def test_snapshot_diff_non_git_temporary_file_and_unrelated_dirty_preserved(self):
        unrelated = self.project / 'unrelated.txt'; unrelated.write_bytes(b'already dirty')
        self.snapshot(); self.file.write_bytes(b'after\n')
        result = self.diff(); before = {p: p.read_bytes() for p in self.evidence.rglob('*') if p.is_file()}
        self.assertEqual(['evidence/probe.txt'], result['changed_paths']); self.assertEqual(0, result['model_calls'])
        self.assertEqual('diff_saved_not_accepted', result['status'])
        text = self.patch.read_text(); self.assertTrue(text.startswith('--- a/evidence/probe.txt\n+++ b/evidence/probe.txt\n'))
        self.assertEqual({'evidence/probe.txt'}, gate.diff_paths(text))
        self.assertEqual(b'already dirty', unrelated.read_bytes()); self.assertEqual(before, {p: p.read_bytes() for p in self.evidence.rglob('*') if p.is_file()})

    def test_canonical_modify_create_delete_pass_full_gate(self):
        for before, after in [(b'before\n', b'after\n'), (None, b'new\n'), (b'deleted\n', None)]:
            with self.subTest(before=before, after=after):
                patch = gate.canonical_diff('evidence/probe.txt', before, after)
                self.assertEqual('evidence_valid', self.validate(patch)['status'])
                if before is None: self.assertIn('--- /dev/null\n+++ b/', patch)
                if after is None: self.assertIn('--- a/', patch); self.assertIn('+++ /dev/null', patch)

    def test_actual_no_final_newline_markers_and_header_like_hunk_content(self):
        for before, after in [(b'before', b'after'), (b'before\n', b'after'), (b'before', b'after\n'),
                              (b'-- a/not-a-header\n', b'++ b/not-a-header\n')]:
            patch = gate.canonical_diff('evidence/probe.txt', before, after)
            self.assertEqual('evidence_valid', self.validate(patch)['status'])
            if not before.endswith(b'\n') or not after.endswith(b'\n'):
                self.assertIn('\\ No newline at end of file\n', patch)

    def test_crlf_and_multiple_hunks_remain_structurally_valid(self):
        patch = gate.canonical_diff('evidence/probe.txt', b'a\r\n', b'b\r\n')
        self.assertIn('-a\r\n+b\r\n', patch); self.validate(patch)
        before = [f'{i}\n' for i in range(25)]; after = before[:]; after[1] = 'first\n'; after[22] = 'last\n'
        patch = gate.canonical_diff('evidence/probe.txt', ''.join(before).encode(), ''.join(after).encode())
        self.assertEqual(2, patch.count('@@ -')); self.validate(patch)

    def test_generated_diff_applies_to_actual_before_bytes_in_isolated_directory(self):
        import shutil
        executable = shutil.which('patch')
        if executable is None: self.skipTest('system patch unavailable')
        for i, (before, after) in enumerate([(b'before\n', b'after\n'), (b'before', b'after'),
                                           (None, b'new\n'), (b'deleted\n', None)]):
            with self.subTest(before=before, after=after):
                work = self.root / f'apply-{i}'; work.mkdir(); (work / 'evidence').mkdir()
                target = work / 'evidence/probe.txt'
                if before is not None: target.write_bytes(before)
                patch = self.root / f'apply-{i}.diff'; patch.write_text(gate.canonical_diff('evidence/probe.txt', before, after))
                applied = subprocess.run([executable, '--batch', '--forward', '-E', '-p1', '-i', str(patch)],
                                         cwd=work, capture_output=True, text=True)
                self.assertEqual(0, applied.returncode, applied.stdout + applied.stderr)
                self.assertEqual(after, target.read_bytes() if target.exists() else None)

    def test_snapshot_generate_combined_creation_and_deletion_with_exact_scope(self):
        self.task['allowed_paths'].append('evidence/new.txt')
        self.snapshot(); self.file.unlink(); (self.project / 'evidence/new.txt').write_bytes(b'created\n')
        result = self.diff(); patch = self.patch.read_text()
        self.assertEqual(self.task['allowed_paths'], result['changed_paths'])
        self.assertEqual('evidence_valid', self.validate(patch)['status'])
        self.assertIn('--- /dev/null\n+++ b/evidence/new.txt', patch)
        self.assertIn('--- a/evidence/probe.txt\n+++ /dev/null', patch)

    def test_changed_paths_and_directional_headers_must_match(self):
        patch = gate.canonical_diff('evidence/probe.txt', b'a\n', b'b\n')
        for bad in [patch.replace('--- a/', '--- b/'), patch.replace('+++ b/', '+++ a/'),
                    patch.replace('+++ b/evidence/probe.txt', '+++ b/other.txt')]:
            with self.assertRaises(gate.EvidenceError): self.validate(bad)
        with self.assertRaisesRegex(gate.EvidenceError, 'diff paths do not match'):
            self.task['allowed_paths'].append('other.txt'); self.validate(patch, ['other.txt'])

    def test_traversal_absolute_and_non_normalized_paths_rejected(self):
        for path in ['../probe.txt', '/tmp/probe.txt', 'dir/../probe.txt', 'dir//probe.txt', 'dir\\probe.txt', 'line\nname']:
            with self.subTest(path=path), self.assertRaises(gate.EvidenceError):
                gate.canonical_diff(path, b'a\n', b'b\n')
        for path in ['a/../escape', 'a//tmp/escape', 'a/dir//escape']:
            with self.assertRaises(gate.EvidenceError):
                gate.diff_paths(f'--- {path}\n+++ b/safe\n@@ -1 +1 @@\n-a\n+b\n')

    def test_rename_binary_symlink_and_malformed_hunks_stay_rejected(self):
        patch = gate.canonical_diff('evidence/probe.txt', b'a\n', b'b\n')
        for bad in ['rename from old\n' + patch, 'rename to new\n' + patch, 'GIT binary patch\n' + patch,
                    'new file mode 120000\n' + patch, patch.replace('@@ -1 +1 @@', '@@ -1,2 +1 @@'),
                    patch.replace('@@ -1 +1 @@', '@@ invalid @@'), patch.replace('+++ b/evidence/probe.txt\n', ''),
                    patch.replace('--- a/evidence/probe.txt', '--- /dev/null').replace('+++ b/evidence/probe.txt', '+++ /dev/null')]:
            with self.subTest(bad=bad), self.assertRaises(gate.EvidenceError): gate.diff_paths(bad)

    def test_snapshot_hash_task_project_and_file_scope_binding(self):
        self.snapshot(); self.file.write_bytes(b'after\n'); path = self.baseline / 'snapshot.json'; original = path.read_bytes()
        manifest = json.loads(original)
        for key, wrong in [('project_root', str(self.root)), ('task_sha256', '0'*64), ('files', {})]:
            path.write_text(json.dumps({**manifest, key: wrong}))
            with self.assertRaises(gate.EvidenceError): self.diff()
        path.write_bytes(original); (self.baseline / 'files/evidence/probe.txt').write_bytes(b'tampered')
        with self.assertRaisesRegex(gate.EvidenceError, 'artifact hash mismatch'): self.diff()
        self.assertFalse(self.patch.exists())

    def test_source_and_baseline_symlinks_rejected_without_reading_foreign_files(self):
        other = self.root / 'foreign'; other.write_bytes(b'outside')
        self.file.unlink(); self.file.symlink_to(other)
        with self.assertRaisesRegex(gate.EvidenceError, 'symlink source'): self.snapshot()
        self.assertFalse(self.baseline.exists())
        self.file.unlink(); self.file.write_bytes(b'before\n'); self.snapshot(); self.file.write_bytes(b'after\n')
        saved = self.baseline / 'files/evidence/probe.txt'; saved.unlink(); saved.symlink_to(other)
        with self.assertRaisesRegex(gate.EvidenceError, 'symlink artifact'): self.diff()

    def test_missing_before_snapshot_and_existing_outputs_never_repaired(self):
        with self.assertRaisesRegex(gate.EvidenceError, 'invalid snapshot'): self.diff()
        self.snapshot(); original = (self.baseline / 'snapshot.json').read_bytes()
        with self.assertRaisesRegex(gate.EvidenceError, 'output exists'): self.snapshot()
        self.assertEqual(original, (self.baseline / 'snapshot.json').read_bytes())
        self.file.write_bytes(b'after\n'); self.patch.write_bytes(b'original submitted diff')
        with self.assertRaisesRegex(gate.EvidenceError, 'never repair'): self.diff()
        self.assertEqual(b'original submitted diff', self.patch.read_bytes())

    def test_no_changes_empty_only_and_binary_are_explicitly_unsupported(self):
        self.snapshot()
        with self.assertRaisesRegex(gate.EvidenceError, 'no scoped changes'): self.diff()
        for before, after in [(None, b''), (b'', None), (b'\x00', b'b'), (b'\xff', b'b')]:
            with self.assertRaises(gate.EvidenceError): gate.canonical_diff('evidence/probe.txt', before, after)

    def test_cli_snapshot_and_diff_produce_valid_reference_without_running_task_tests(self):
        task = self.root / 'task.json'; task.write_text(json.dumps(self.task))
        helper = str(ROOT / 'plugins/codex-duo/skills/workflow/scripts/codex_duo.py')
        base = [sys.executable, '-B', helper]
        snapshot = subprocess.run(base + ['snapshot', '--task', str(task), '--project-root', str(self.project), '--out', str(self.baseline)], capture_output=True, text=True)
        self.assertEqual(0, snapshot.returncode, snapshot.stdout + snapshot.stderr)
        self.file.write_bytes(b'after\n')
        diff = subprocess.run(base + ['diff', '--task', str(task), '--project-root', str(self.project), '--baseline', str(self.baseline), '--out', str(self.patch)], capture_output=True, text=True)
        self.assertEqual(0, diff.returncode, diff.stdout + diff.stderr)
        self.assertEqual(hashlib.sha256(self.patch.read_bytes()).hexdigest(), json.loads(diff.stdout)['diff']['sha256'])
        again = subprocess.run(base + ['diff', '--task', str(task), '--project-root', str(self.project), '--baseline', str(self.baseline), '--out', str(self.patch)], capture_output=True, text=True)
        self.assertEqual(1, again.returncode); self.assertEqual('rejected', json.loads(again.stdout)['status'])


class FailedDiffAccountingTests(unittest.TestCase):
    setUp = worker.ParallelTests.setUp
    tearDown = worker.ParallelTests.tearDown
    call = worker.ParallelTests.call
    evidence = worker.ParallelTests.evidence

    def test_reserved_helper_commands_preflight_without_mutating_ledger_or_accepting(self):
        self.call('plan', host_capacity=1)
        r = self.call('reserve', host_capacity=1, workstream_id='main')
        ledger = Path(self.plan['evidence_root']) / 'dispatch.json'; before = ledger.read_bytes()
        for name in self.task['allowed_paths']: (self.root / name).write_bytes(b'before\n')
        def run(key):
            argv = r['evidence_commands'][key][:]; argv[0] = sys.executable
            result = subprocess.run(argv, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            return json.loads(result.stdout)
        run('snapshot_before_edit')
        for name in self.task['allowed_paths']: (self.root / name).write_bytes(b'after\n')
        generated = run('diff_after_edit'); root = Path(r['evidence_root'])
        (root / 'test.log').write_bytes(b'OFFLINE TEST CONTRACT FIXTURE; NO NATIVE MODEL')
        result = {'schema_version': 1, 'task_id': r['task']['task_id'], 'status': 'completed',
            'summary': 'Offline contract fixture, no model', 'changed_paths': generated['changed_paths'],
            'diff': generated['diff'], 'tests': [{'argv': argv, 'exit_code': 0,
                'log': gate.reference(root / 'test.log', root)} for argv in r['task']['tests']], 'blockers': []}
        (root / 'result.json').write_text(json.dumps(result))
        self.assertEqual('evidence_valid', run('preflight_result')['status'])
        self.assertEqual(before, ledger.read_bytes())
        self.assertEqual('reserved', json.loads(before)['dispatches'][0]['status'])
        self.assertNotIn('manual_review', json.loads(before))

    def test_rejection_failed_replay_and_copy_never_redispatch_or_change_budget(self):
        self.call('plan', host_capacity=1)
        identity = {'project_root': str(self.root), 'kind': 'worker', 'task_id': self.plan['handoff_id']}
        r = self.call('reserve', host_capacity=1, workstream_id='main')
        self.assertEqual({'snapshot_before_edit', 'diff_after_edit', 'preflight_result'}, set(r['evidence_commands']))
        self.evidence(r['evidence_root'], r['task']); root = Path(r['evidence_root'])
        patch = root / 'change.diff'; patch.write_text(patch.read_text().replace('--- a/', '--- ').replace('+++ b/', '+++ '))
        result = json.loads((root / 'result.json').read_text()); result['diff'] = gate.reference(patch, root); (root / 'result.json').write_text(json.dumps(result))
        with self.assertRaisesRegex(SelectionError, 'invalid diff path prefix'):
            self.call('complete', dispatch_id=r['id'], outcome='completed', native_receipt='OFFLINE FIXTURE ONLY')
        self.call('complete', dispatch_id=r['id'], outcome='failed', native_receipt='OFFLINE FIXTURE ONLY')
        ledger = Path(self.plan['evidence_root']) / 'dispatch.json'; before = ledger.read_bytes()
        for _ in range(2):
            self.call('complete', dispatch_id=r['id'], outcome='failed', native_receipt='OFFLINE FIXTURE ONLY')
            self.assertEqual('failed', self.call('plan', host_capacity=1)['completion']['events'][0]['outcome'])
        self.assertEqual(before, ledger.read_bytes())
        self.assertEqual(1, len(json.loads(before)['dispatches']))
