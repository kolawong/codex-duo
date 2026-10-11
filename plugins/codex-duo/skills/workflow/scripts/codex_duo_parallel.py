"""Bounded native dispatch accounting. Data only; the coordinator owns model calls."""
import json
import os
from pathlib import Path
import re
import tempfile
from codex_duo_completion import completion_view
from codex_duo import verify as verify_evidence, EvidenceError
from codex_duo_selection import SelectionError, canonical, digest, validate_task


class ParallelExecution:
    def __init__(self, store, parent):
        self.store, self.parent = store, parent
        self.root = store.directory / 'runs' / parent['handoff_id']
        self.path = self.root / 'dispatch.json'

    def safe(self, path):
        cursor = self.store.directory
        for part in path.relative_to(cursor).parts:
            if cursor.is_symlink():
                raise SelectionError('unsafe_storage', '派发证据不能包含符号链接。', 409)
            cursor = cursor / part
        if cursor.is_symlink():
            raise SelectionError('unsafe_storage', '派发证据不能包含符号链接。', 409)
        return path

    def write(self, path, value):
        self.safe(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.dispatch-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as handle:
                handle.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def read(self):
        try:
            value = json.loads(self.safe(self.path).read_text())
            if value.get('project_root', str(self.store.directory.parent.resolve())) != str(self.store.directory.parent.resolve()):
                raise ValueError('project mismatch')
            if value.get('review_project_root', str(self.store.directory.parent.resolve())) != str(self.store.directory.parent.resolve()):
                raise ValueError('review project mismatch')
            if value['handoff_id'] != self.parent['handoff_id'] or value['plan_hash'] != digest(value['workstreams']):
                raise ValueError('plan mismatch')
            return value
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise SelectionError('invalid_dispatch', '派发计划不存在或已损坏，请检查证据。', 409) from exc

    @staticmethod
    def capacity(body):
        count = body.get('host_capacity')
        if type(count) is not int or count < 1:
            raise SelectionError('host_capacity_required', '请提供原生工具本父任务可占用的总执行名额（包含已保留或运行的本任务代理，不包含主控及其他任务）。')
        return count

    def plan(self, body):
        capacity = self.capacity(body)
        streams = body.get('workstreams')
        if streams is None:
            streams = [{'id': 'main', 'task': self.parent['task'], 'depends_on': []}]
        if not isinstance(streams, list) or not streams or len(streams) > 20:
            raise SelectionError('invalid_plan', '需要 1 到 20 个明确子任务。')
        if len(streams) > self.parent['max_worker_turns']:
            raise SelectionError('invalid_plan', '子任务数超过父任务总执行次数，请合并任务并为修正留出预算。')
        ids, owned, prepared = set(), set(), []
        for stream in streams:
            if not isinstance(stream, dict) or set(stream) != {'id', 'task', 'depends_on'}:
                raise SelectionError('invalid_plan', '子任务必须提供 id、task 和 depends_on。')
            sid = stream['id']
            if not isinstance(sid, str) or not re.fullmatch('[a-z][a-z0-9_-]{0,39}', sid) or sid in ids:
                raise SelectionError('invalid_plan', '子任务 ID 必须唯一且为安全的小写标识。')
            task = validate_task(stream['task'])
            if len(task['allowed_paths']) != len(set(task['allowed_paths'])) or not set(task['allowed_paths']) <= set(self.parent['task']['allowed_paths']):
                raise SelectionError('invalid_plan', '子任务文件范围必须是父任务内的明确文件。')
            if owned & set(task['allowed_paths']):
                raise SelectionError('ownership_conflict', '子任务文件所有权重叠，请重新拆分或合为一个任务。', 409)
            dependencies = stream['depends_on']
            if not isinstance(dependencies, list) or not all(isinstance(d, str) for d in dependencies) or len(dependencies) != len(set(dependencies)):
                raise SelectionError('invalid_plan', '依赖必须是唯一子任务 ID 列表。')
            ids.add(sid); owned.update(task['allowed_paths'])
            prepared.append({'id': sid, 'task': task, 'depends_on': dependencies})
        if len({s['task']['task_id'] for s in prepared}) != len(prepared):
            raise SelectionError('invalid_plan', '子任务契约 task_id 必须唯一。')
        resolved = set()
        while len(resolved) < len(ids):
            ready = {s['id'] for s in prepared if s['id'] not in resolved and set(s['depends_on']) <= resolved}
            if not ready:
                raise SelectionError('dependency_conflict', '依赖包含未知任务或循环，请重新规划。', 409)
            resolved.update(ready)
        with self.store.lock:
            if self.safe(self.path).exists():
                existing = self.read()
                if existing['workstreams'] != prepared:
                    raise SelectionError('plan_locked', '父任务计划已固定，不能重新建立预算。', 409)
                return self.view(existing)
            ledger = {'schema_version': 1, 'project_root': str(self.store.directory.parent.resolve()), 'handoff_id': self.parent['handoff_id'],
                'workstreams': prepared, 'plan_hash': digest(prepared), 'host_capacity': capacity,
                'current_host_capacity': capacity,
                'dispatches': []}
            self.write(self.path, ledger)
            for stream in prepared:
                self.write(self.root / 'contracts' / (stream['id'] + '.json'), stream['task'])
            return self.view(ledger)

    def view(self, ledger):
        remaining = self.parent['max_worker_turns'] - len(ledger['dispatches'])
        active = [d for d in ledger['dispatches'] if d['status'] == 'reserved']
        completed = {d['workstream_id'] for d in ledger['dispatches'] if d['status'] == 'verified'}
        ready = [s['id'] for s in ledger['workstreams'] if s['id'] not in completed
                 and not any(d['workstream_id'] == s['id'] for d in active)
                 and set(s['depends_on']) <= completed]
        limit = min(self.parent['max_parallel_workers'], ledger['host_capacity'],
                    ledger['current_host_capacity'], len(ledger['workstreams']))
        return {'completion': completion_view('worker', self.parent['handoff_id'], ledger['dispatches'],
                str(self.store.directory.parent.resolve())),
            'handoff_id': self.parent['handoff_id'], 'workstreams': ledger['workstreams'],
            'dispatch_count': len(ledger['dispatches']),
            'remaining_worker_turns': remaining, 'active_dispatches': active,
            'completed_workstreams': sorted(completed),
            'max_simultaneous_workers': limit, 'ready_workstreams': ready,
            'available_dispatch_slots': max(0, min(remaining, limit - len(active), len(ready))),
            'execution_started': False, 'model_calls': 0,
            'next_tool': 'codex_duo_reserve',
            'instructions': 'Reserve immediately before each native spawn or correction, including follow-ups. '
                'Every reservation consumes one parent turn, even if spawn fails. No refunds or child budget resets. '
                'Host capacity means total slots allocatable to this parent (including its active/reserved workers, '
                'excluding coordinator and other tasks), not currently idle slots. This service does not discover or start native models.'}

    def reserve(self, body):
        capacity = self.capacity(body)
        with self.store.lock:
            ledger = self.read()
            sid = body.get('workstream_id')
            stream = next((s for s in ledger['workstreams'] if s['id'] == sid), None)
            if stream is None: raise SelectionError('unknown_workstream', '子任务不存在。')
            if len(ledger['dispatches']) >= self.parent['max_worker_turns']:
                raise SelectionError('budget_exhausted', '父任务总执行次数已用完，首次执行和修正共享上限。', 409)
            active = [d for d in ledger['dispatches'] if d['status'] == 'reserved']
            if len(active) >= min(capacity, ledger['host_capacity'], self.parent['max_parallel_workers']):
                raise SelectionError('capacity_exhausted', '已达到保存上限或原生宿主容量，请等待现有任务完成。', 409)
            if any(d['workstream_id'] == sid for d in active):
                raise SelectionError('workstream_active', '同一子任务不能同时执行或修正。', 409)
            completed = {d['workstream_id'] for d in ledger['dispatches'] if d['status'] == 'verified'}
            if not set(stream['depends_on']) <= completed:
                raise SelectionError('dependencies_pending', '依赖子任务尚未通过证据验证。', 409)
            # A correction invalidates any previous completion of this workstream. Downstream
            # verified work must be rerun; active dependents forbid the correction entirely.
            dependents = {sid}
            while True:
                extended = dependents | {s['id'] for s in ledger['workstreams'] if set(s['depends_on']) & dependents}
                if extended == dependents: break
                dependents = extended
            if any(d['workstream_id'] in dependents for d in active):
                raise SelectionError('dependency_active', '依赖链正在执行，不能同时修正上游。', 409)
            for d in ledger['dispatches']:
                if d['status'] == 'verified' and d['workstream_id'] in dependents: d['status'] = 'superseded'
            dispatch_id = f"dispatch-{len(ledger['dispatches']) + 1:03d}"
            evidence = self.root / 'workers' / sid / dispatch_id
            task_path = self.root / 'contracts' / (sid + '.json')
            if json.loads(self.safe(task_path).read_text()) != stream['task']:
                raise SelectionError('invalid_dispatch', '子任务契约已变化。', 409)
            self.safe(evidence).mkdir(parents=True, exist_ok=False)
            record = {'id': dispatch_id, 'workstream_id': sid, 'status': 'reserved', 'native_receipt': None}
            ledger['current_host_capacity'] = capacity
            ledger['dispatches'].append(record); self.write(self.path, ledger)
            helper = str(Path(__file__).with_name('codex_duo.py').resolve())
            project = str(self.store.directory.parent.resolve())
            command_root = evidence.resolve()
            command_task = str(task_path.resolve())
            return {**record, 'worker': self.parent['worker'], 'task': stream['task'],
                'task_path': str(task_path), 'evidence_root': str(evidence),
                'evidence_commands': {
                    'snapshot_before_edit': ['python3', '-B', helper, 'snapshot', '--task', command_task,
                        '--project-root', project, '--out', str(command_root / 'before')],
                    'diff_after_edit': ['python3', '-B', helper, 'diff', '--task', command_task,
                        '--project-root', project, '--baseline', str(command_root / 'before'), '--out', str(command_root / 'change.diff')],
                    'preflight_result': ['python3', '-B', helper, 'verify', '--task', command_task,
                        '--result', str(command_root / 'result.json'), '--root', str(command_root)]},
                'remaining_worker_turns': self.parent['max_worker_turns'] - len(ledger['dispatches']),
                'execution_started': False, 'instruction': 'Spawn the saved native model only. Preserve other workers edits. '
                    'No recursion, no child budget; return result.json and scoped evidence. A reservation is not an execution receipt. '
                    'Forward evidence_commands to the Worker. Capture snapshot_before_edit BEFORE editing; '
                    'use diff_after_edit for canonical --- a/path, +++ b/path headers (or /dev/null), '
                    'then preflight_result after saving real test logs/result hashes. '
                    'These helpers run no model/test/dispatch. Evidence rejection grants no retry or repair of terminal records.'}

    def complete(self, body):
        receipt = body.get('native_receipt')
        if not isinstance(receipt, str) or not receipt.strip() or len(receipt) > 2000:
            raise SelectionError('native_receipt_required', '记录实际原生派发返回的执行代理 ID 或失败回执。')
        if body.get('outcome') not in ('completed', 'failed', 'blocked', 'cancelled'):
            raise SelectionError('invalid_outcome', '需要执行完成、失败或阻塞状态。')
        with self.store.lock:
            ledger = self.read()
            record = next((d for d in ledger['dispatches'] if d['id'] == body.get('dispatch_id')), None)
            if record is None:
                raise SelectionError('invalid_dispatch', '派发不存在。', 409)
            submission = digest({k: body.get(k) for k in ('dispatch_id', 'outcome', 'native_receipt')})
            replay = record['status'] != 'reserved'
            # Legacy terminal records are recognizable without rewriting their ledger.
            prior_outcome = 'completed' if record['status'] in ('verified', 'superseded') else record['status']
            if replay and (record.get('native_receipt') != receipt or prior_outcome != body['outcome'] or
                           record.get('submission_sha256', submission) != submission):
                raise SelectionError('invalid_dispatch', '已结束派发不能被另一份回执覆盖。', 409)
            if body['outcome'] == 'completed':
                stream = next(s for s in ledger['workstreams'] if s['id'] == record['workstream_id'])
                root = self.root / 'workers' / stream['id'] / record['id']
                try:
                    result = json.loads(self.safe(root / 'result.json').read_text())
                    verify_evidence(stream['task'], result, self.safe(root))
                except (EvidenceError, OSError, ValueError, TypeError, KeyError) as exc:
                    raise SelectionError('evidence_rejected', str(exc), 409) from exc
                if replay and record.get('result_sha256') != digest(result):
                    raise SelectionError('evidence_rejected', '完成后的证据已变化。', 409)
                if not replay:
                    record['status'] = 'verified'
                    record['result_sha256'] = digest(result)
            elif not replay: record['status'] = body['outcome']
            if replay: return self.view(ledger)
            record['submission_sha256'] = submission
            record['native_receipt'] = receipt
            self.write(self.path, ledger)
            return self.view(ledger)

    def verify(self, body):
        with self.store.lock:
            return self._verify(body)

    def _verify(self, body):
        # Read only: revalidate child evidence to catch changes after completion, then the
        # parent result containing integration tests and the combined scoped diff.
        ledger = self.read()
        if any(d['status'] == 'reserved' for d in ledger['dispatches']):
            raise SelectionError('workers_pending', '仍有执行代理未结束。', 409)
        try:
            child_paths = set()
            for stream in ledger['workstreams']:
                records = [d for d in ledger['dispatches'] if d['workstream_id'] == stream['id'] and d['status'] == 'verified']
                if not records: raise EvidenceError('workstream not verified: ' + stream['id'])
                record = records[-1]; root = self.root / 'workers' / stream['id'] / record['id']
                result = json.loads(self.safe(root / 'result.json').read_text())
                if digest(result) != record['result_sha256']: raise EvidenceError('child result changed')
                verify_evidence(stream['task'], result, self.safe(root))
                child_paths.update(result['changed_paths'])
            result = json.loads(self.safe(self.root / 'result.json').read_text())
            verdict = verify_evidence(self.parent['task'], result, self.safe(self.root))
            if not child_paths <= set(result['changed_paths']):
                raise EvidenceError('integrated parent diff omits verified child changes')
        except (EvidenceError, OSError, ValueError, TypeError, KeyError) as exc:
            raise SelectionError('evidence_rejected', str(exc), 409) from exc
        return {**verdict, 'verified_workstreams': len(ledger['workstreams']),
            'dispatch_count': len(ledger['dispatches']), 'requires_coordinator_review': True,
            'provenance': 'Receipts are coordinator-supplied; hashes validate consistency, not native model provenance.'}
