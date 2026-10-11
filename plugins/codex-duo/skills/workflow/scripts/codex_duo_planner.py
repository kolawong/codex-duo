"""Plan-only contracts and accounting. No approval or Worker transition.

Host capabilities are adapter reports, not sandbox attestations. The coordinator MUST
inspect an actual native tool that enforces this contract before reserving/dispatching.
A prompt, ledger hash, receipt, or this module cannot establish execution isolation.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import time
from codex_duo_completion import completion_view

from codex_duo_selection import SelectionError, canonical, digest, saved_workflow

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_FILES = 20000


def reject(code, message):
    raise SelectionError(code, message, 409)


def strings(value, name, *, nonempty=False):
    if not isinstance(value, list) or len(value) > 200 or (nonempty and not value) or any(
            not isinstance(item, str) or not item.strip() or len(item) > 16000 for item in value):
        reject('invalid_plan_contract', name + ' 必须为有限的非空文字列表。')
    return value


def validate_request(value):
    fields = {'schema_version', 'task_id', 'goal', 'read_paths', 'questions'}
    if not isinstance(value, dict) or set(value) != fields or type(value['schema_version']) is not int or value['schema_version'] != 1:
        reject('invalid_plan_contract', '规划请求必须使用独立的 schema_version=1 契约。')
    for key in ('task_id', 'goal'):
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 4000:
            reject('invalid_plan_contract', '规划任务 ID 和目标不能为空。')
    strings(value['questions'], 'questions')
    strings(value['read_paths'], 'read_paths', nonempty=True)
    if len(set(value['read_paths'])) != len(value['read_paths']):
        reject('invalid_plan_contract', '读取路径不能重复。')
    for path in value['read_paths']:
        parts = PurePosixPath(path).parts
        if not parts or path != str(PurePosixPath(path)) or '\\' in path or '\x00' in path or PurePosixPath(path).is_absolute() or any(p in ('.', '..', '.git', '.codex-duo', '.fusion') for p in parts):
            reject('invalid_plan_contract', '读取路径必须是项目内明确文件，不能访问 Git 或内部状态。')
    return json.loads(canonical(value))


def git(root, *args):
    try:
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True,
                              timeout=30, env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise SelectionError('baseline_unavailable', '无法读取 Git 代码基线；仅规划暂不支持无提交的仓库。', 409) from exc


def code_baseline(root, read_paths):
    """Hash HEAD, index entries, and tracked/untracked worktree content, never commands.

Ignored files explicitly requested are included. Internal .codex-duo storage is excluded.
Symlinks/submodules and concurrent baseline changes fail closed rather than following
links outside the project or pretending a partial snapshot covers the repository.
"""
    root = Path(root).resolve()
    if Path(os.fsdecode(git(root, 'rev-parse', '--show-toplevel')).strip()).resolve() != root:
        reject('baseline_unavailable', '规划项目必须是 Git 工作树根目录。')
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    index = git(root, 'ls-files', '--stage', '-z')
    if any(entry.startswith(b'160000 ') for entry in index.split(b'\0')):
        reject('baseline_unavailable', '含子模块的仓库需要宿主提供完整只读快照，当前暂不支持。')
    names = set(os.fsdecode(x) for x in git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0') if x)
    names.update(read_paths)
    if len(names) > MAX_FILES:
        reject('baseline_unavailable', '代码基线文件数超过安全读取限制。')
    files = []
    total = 0
    for name in sorted(names):
        if name in ('.codex-duo', '.fusion', '.codex-duo-migration.lock', '.codex-duo-migration.json') or name.startswith(('.codex-duo/', '.fusion/')):
            continue
        path = root / name
        if any(part in ('.aws', '.ssh') or part == '.env' or part.startswith('.env.') and part not in ('.env.example', '.env.sample') or part.endswith(('.pem', '.p12', '.key')) for part in Path(name).parts):
            reject('baseline_unavailable', '基线包含可能的凭据文件；请将其移出规划代码范围后重试。')
        if not path.is_relative_to(root) or any(p.is_symlink() for p in [path, *path.parents] if p.is_relative_to(root)):
            reject('baseline_unavailable', '代码基线包含符号链接，无法保证只读范围。')
        try:
            before = path.stat()
            if not path.is_file(): reject('baseline_unavailable', '读取范围必须是明确文件。')
            if before.st_size > MAX_FILE_BYTES or total + before.st_size > MAX_TOTAL_BYTES:
                reject('baseline_unavailable', '代码基线超过安全读取大小限制。')
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as handle:
                content = handle.read(MAX_FILE_BYTES + 1)
            if len(content) > MAX_FILE_BYTES or total + len(content) > MAX_TOTAL_BYTES:
                reject('baseline_unavailable', '读取时文件超过安全大小限制。')
            after = path.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                reject('baseline_changed', '读取基线时文件正在变化，请稍后重试。')
            total += len(content)
            files.append({'path': name, 'sha256': hashlib.sha256(content).hexdigest(), 'executable': bool(after.st_mode & 0o111)})
        except FileNotFoundError:
            files.append({'path': name, 'missing': True})
    if head != git(root, 'rev-parse', 'HEAD').decode().strip() or index != git(root, 'ls-files', '--stage', '-z'):
        reject('baseline_changed', '读取基线时 Git 状态正在变化。')
    # A second path listing detects newly added/deleted untracked files during capture.
    current = set(os.fsdecode(x) for x in git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0') if x)
    current.update(read_paths)
    if current != names: reject('baseline_changed', '读取基线时文件列表正在变化。')
    value = {'head': head, 'index_sha256': hashlib.sha256(index).hexdigest(), 'files': files}
    return {**value, 'sha256': digest(value)}


def validate_host(value, planner):
    """Validate reported native capabilities; never infer enforcement from instructions."""
    expected = {'filesystem': 'read_only', 'network': 'disabled', 'approval_escalation': 'disabled', 'external_tools': 'disabled',
                'writes': 'disabled', 'agent_spawn': 'disabled', 'enforcement': 'host'}
    if not isinstance(value, dict) or set(value) != set(expected) | {'tool', 'model', 'reasoning_effort', 'process_execution'} or any(value.get(k) != v for k, v in expected.items()) or value.get('process_execution') not in ('disabled', 'read_only_sandbox'):
        reject('readonly_host_required', '需要宿主真正强制只读、禁网络/外部工具/提权/写入/子代理；仅允许只读沙箱命令，提示词约束不够。')
    if not isinstance(value['tool'], str) or not value['tool'].strip() or len(value['tool']) > 200:
        reject('readonly_host_required', '必须提供已发现并核验的原生工具名称。')
    if any(value[k] != planner[k] for k in ('model', 'reasoning_effort')):
        reject('planner_model_unavailable', '宿主不支持快照中的规划模型或强度；禁止静默替换。')
    return json.loads(canonical(value))


def validate_result(value, snapshot, dispatch_id):
    fields = {'schema_version', 'plan_id', 'dispatch_id', 'baseline_sha256', 'summary', 'steps', 'risks', 'questions', 'suggested_tests'}
    if not isinstance(value, dict) or set(value) != fields or type(value['schema_version']) is not int or value['schema_version'] != 1:
        reject('invalid_plan_result', '规划结果不能包含代码变更、diff、执行证据或额外字段。')
    if value['plan_id'] != snapshot['plan_id'] or value['dispatch_id'] != dispatch_id or value['baseline_sha256'] != snapshot['baseline']['sha256']:
        reject('invalid_plan_result', '规划结果的任务、派发或代码基线不匹配。')
    if not isinstance(value['summary'], str) or not value['summary'].strip() or len(value['summary']) > 16000:
        reject('invalid_plan_result', '规划结果必须包含有限的计划摘要。')
    for key in ('steps', 'risks', 'questions'): strings(value[key], key, nonempty=key == 'steps')
    tests = value['suggested_tests']
    if not isinstance(tests, list) or len(tests) > 100:
        reject('invalid_plan_result', '建议测试列表无效。')
    for test in tests:
        if not isinstance(test, dict) or set(test) != {'argv', 'status'} or test['status'] != 'not_run':
            reject('invalid_plan_result', '所有建议测试必须明确标注 not_run，不能伪造执行结果。')
        strings(test['argv'], 'argv', nonempty=True)
    if len(canonical(value)) > 256 * 1024: reject('invalid_plan_result', '规划结果过大。')
    return json.loads(canonical(value))


class PlannerExecution:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.project = self.store.directory.parent.resolve()
        self.root = self.store.directory / 'plans'

    def safe(self, path):
        cursor = self.store.directory
        for part in path.relative_to(cursor).parts:
            if cursor.is_symlink(): reject('unsafe_storage', '规划状态不能包含符号链接。')
            cursor /= part
        if cursor.is_symlink(): reject('unsafe_storage', '规划状态不能包含符号链接。')
        return path

    def path(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{24}', identifier):
            reject('invalid_plan', '规划 ID 格式无效。')
        return self.safe(self.root / (identifier + '.json'))

    def write(self, path, value):
        self.safe(path).parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.plan-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(canonical({'payload': value, 'sha256': digest(value)}))
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
            for directory in (path.parent, self.store.directory):
                descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(descriptor)
                finally: os.close(descriptor)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def read(self, identifier):
        try:
            envelope = json.loads(self.path(identifier).read_bytes())
            value = envelope['payload']; snapshot = value['snapshot']
            if envelope['sha256'] != digest(value) or value['snapshot_sha256'] != digest(snapshot) or snapshot['plan_id'] != identifier:
                raise ValueError('hash')
            if digest({'project_root': str(self.project), 'task_id': snapshot['request']['task_id']})[:24] != identifier:
                raise ValueError('identity')
            if snapshot['project_root'] != str(self.project) or snapshot['mode'] != 'plan_only': raise ValueError('scope')
            if value.get('result') is not None and value['result_sha256'] != digest(value['result']): raise ValueError('result hash')
            return value
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, SelectionError): raise
            raise SelectionError('invalid_plan', '规划状态不存在或已损坏；不会重置预算。', 409) from exc

    def check_baseline(self, snapshot):
        if code_baseline(self.project, snapshot['request']['read_paths']) != snapshot['baseline']:
            reject('baseline_changed', '代码基线已变化；旧计划不可继续派发或作为当前确认依据。')

    def begin(self, body):
        request = validate_request(body.get('request'))
        if body.get('invocation') != 'explicit':
            reject('explicit_planning_required', '仅规划必须由用户明确请求；不会自动规划后执行。')
        identifier = digest({'project_root': str(self.project), 'task_id': request['task_id']})[:24]
        with self.service.defaults_store.global_store.lock, self.store.lock:
            path = self.path(identifier)
            if path.exists():
                value = self.read(identifier)
                if value['snapshot']['request'] != request: reject('plan_locked', '该规划任务已固定；不可更换输入重置预算。')
                if body.get('planner') is not None and body['planner'] != {k: value['snapshot']['planner'][k] for k in ('model', 'reasoning_effort', 'max_turns')}:
                    reject('plan_locked', '该任务的规划模型和预算已经固定。')
                return self.view(value)
            catalog = self.service.catalog_loader()
            saved = self.service.defaults_store.resolved(catalog)['effective']
            if saved['error'] or not saved['document'] and body.get('planner') is None:
                reject('setup_required', '请先保存有效规划配置，或明确提供本任务的规划选择。')
            workflow = saved_workflow(saved['document'])
            planner = {'mode': workflow.get('planner_mode', 'disabled'),
                       'model': workflow.get('planner_model', ''),
                       'reasoning_effort': workflow.get('planner_reasoning_effort', ''),
                       'max_turns': workflow.get('max_planner_turns', 1)}
            # Explicit task-scoped choice never enables or rewrites saved defaults.
            if body.get('planner') is not None:
                chosen = body['planner']
                if not isinstance(chosen, dict) or set(chosen) != {'model', 'reasoning_effort', 'max_turns'}:
                    reject('invalid_plan_contract', '单次规划选择必须包含模型、强度和总次数。')
                planner = {'mode': 'plan_only', **chosen}
            if not isinstance(planner, dict) or planner.get('mode') != 'plan_only':
                reject('planner_disabled', '请先明确启用独立的只读规划配置。')
            model = next((m for m in catalog['models'] if m['id'] == planner.get('model')), None)
            if model is None or planner.get('reasoning_effort') not in model['efforts']:
                reject('planner_model_unavailable', '规划模型或强度不在当前目录，不能替换。')
            if type(planner.get('max_turns')) is not int or not 1 <= planner['max_turns'] <= 3:
                reject('invalid_plan_contract', '规划总轮数必须为 1 到 3。')
            snapshot = {'schema_version': 1, 'mode': 'plan_only', 'plan_id': identifier,
                        'project_root': str(self.project), 'request': request, 'planner': planner,
                        'selection_revision': saved['revision'], 'catalog_fingerprint': catalog['fingerprint'],
                        'baseline': code_baseline(self.project, request['read_paths'])}
            value = {'snapshot': snapshot, 'snapshot_sha256': digest(snapshot), 'dispatches': [],
                     'result': None, 'result_sha256': None}
            self.write(path, value)
            return self.view(value)

    def view(self, value):
        snapshot = value['snapshot']
        fresh = code_baseline(self.project, snapshot['request']['read_paths']) == snapshot['baseline']
        active = [d for d in value['dispatches'] if d['status'] == 'reserved']
        remaining = snapshot['planner']['max_turns'] - len(value['dispatches'])
        uncertain = any(d.get('session', {}).get('stage') == 'uncertain' or
                        d.get('adapter') and time.time() - d.get('session', {}).get('heartbeat', 0) > 660 for d in active)
        state = ('stale' if not fresh else 'awaiting_user_review' if value['result'] is not None else
                 'planner_uncertain' if uncertain else 'planner_reserved' if active else 'budget_exhausted' if remaining == 0 else 'ready_for_readonly_planner')
        return {'completion': completion_view('planner', snapshot['plan_id'], value['dispatches'],
                    str(self.project)),
                'plan_id': snapshot['plan_id'], 'mode': 'plan_only', 'state': state,
                'snapshot_sha256': value['snapshot_sha256'], 'baseline_sha256': snapshot['baseline']['sha256'],
                'baseline_current': fresh, 'planner': snapshot['planner'], 'request': snapshot['request'],
                'remaining_planner_turns': remaining, 'dispatches': value['dispatches'], 'result': value['result'],
                'result_sha256': value['result_sha256'], 'execution_started': False, 'worker_execution_allowed': False,
                'next_tool': None if state in ('stale', 'awaiting_user_review', 'budget_exhausted') else
                    'codex_duo_planner_status' if active and any(d.get('adapter') for d in active) else
                    'codex_duo_planner_complete' if active else 'codex_duo_planner_run',
                'instructions': 'Return the plan to the current chat for user review. No automatic execution or approval. '
                    'A future explicitly approved implementation uses a new ordinary Worker contract after baseline revalidation. '
                    'Adapter capability reports and native receipts do not themselves prove sandbox enforcement or model provenance.'}

    def status(self, body):
        with self.store.lock: return self.view(self.read(body.get('plan_id')))

    def reserve(self, body):
        with self.store.lock:
            value = self.read(body.get('plan_id')); snapshot = value['snapshot']
            self.check_baseline(snapshot)
            if value['result'] is not None: reject('plan_finished', '计划已返回当前聊天；不能悄悄修正已提交计划。')
            if any(d['status'] == 'reserved' for d in value['dispatches']): reject('planner_active', '该规划已有未结束派发。')
            if len(value['dispatches']) >= snapshot['planner']['max_turns']: reject('budget_exhausted', '规划总轮数已用完，失败也计入预算。')
            catalog = self.service.catalog_loader()
            if catalog['fingerprint'] != snapshot['catalog_fingerprint']: reject('catalog_changed', '模型目录已变化，禁止使用过期规划快照。')
            host = validate_host(body.get('host_capabilities'), snapshot['planner'])
            record = {'id': 'planner-%03d' % (len(value['dispatches']) + 1), 'status': 'reserved',
                      'host_capabilities': host, 'native_receipt': None}
            value['dispatches'].append(record); self.write(self.path(snapshot['plan_id']), value)
            return {**self.view(value), 'dispatch_id': record['id'],
                    'dispatch_contract': {'mode': 'plan_only', 'model': snapshot['planner']['model'],
                        'reasoning_effort': snapshot['planner']['reasoning_effort'], 'fork_context': False,
                        'read_paths': snapshot['request']['read_paths'], 'allowed_write_paths': [],
                        'run_tests': False, 'spawn_agents': False, 'approve_execution': False,
                        'return_result': 'in_memory_to_coordinator', 'host_requirements': host,
                        'native_agent': 'codex_duo_planner',
                        'agent_template': str(Path(__file__).parent.parent / 'templates/codex_duo_planner.toml'),
                        'host_guide': str(Path(__file__).parent.parent / 'references/planner-host.md')}}

    def complete(self, body, *, adapter=False):
        outcome, receipt = body.get('outcome'), body.get('native_receipt')
        if outcome not in ('completed', 'failed', 'blocked', 'cancelled') or not isinstance(receipt, str) or not receipt.strip() or len(receipt) > 2000:
            reject('invalid_plan_result', '必须提供实际派发回执和完成、失败或阻塞状态。')
        submission = {k: body.get(k) for k in ('dispatch_id', 'outcome', 'native_receipt', 'result')}
        with self.store.lock:
            value = self.read(body.get('plan_id')); snapshot = value['snapshot']
            record = next((d for d in value['dispatches'] if d['id'] == body.get('dispatch_id')), None)
            if record is None: reject('invalid_dispatch', '规划派发不存在。')
            if record.get('adapter') and not adapter:
                reject('adapter_receipt_required', '独立会话回执仅能由实际适配器记录；不能手工完成或清除不确定派发。')
            if record['status'] != 'reserved':
                if record.get('submission_sha256') == digest(submission): return self.view(value)
                reject('invalid_dispatch', '已结束派发不能被另一份结果覆盖。')
            if outcome == 'completed':
                self.check_baseline(snapshot)
                result = validate_result(body.get('result'), snapshot, record['id'])
                value['result'], value['result_sha256'] = result, digest(result)
            elif body.get('result') is not None:
                reject('invalid_plan_result', '失败或阻塞不能提交成功计划。')
            record.update(status=outcome, native_receipt=receipt, submission_sha256=digest(submission))
            if outcome == 'completed': record['result_sha256'] = value['result_sha256']
            self.write(self.path(snapshot['plan_id']), value)
            return self.view(value)
