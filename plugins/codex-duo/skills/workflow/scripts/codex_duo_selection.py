"""Model selection and immutable handoffs. No inference or installation."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import fcntl
from datetime import datetime, timezone


class SelectionError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_catalog(cli=None):
    cli = cli or os.environ.get("CODEX_DUO_CODEX_CLI") or "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
    try:
        raw = subprocess.run([cli, "debug", "models", "--bundled"], capture_output=True,
                             text=True, timeout=10, check=True)
        version = subprocess.run([cli, "--version"], capture_output=True,
                                 text=True, timeout=5, check=True).stdout.strip()
        return normalize_catalog(json.loads(raw.stdout), {"kind": "bundled_cli", "cli": cli,
            "version": version, "loaded_at": datetime.now(timezone.utc).isoformat(),
            "availability": "本机内置目录；未验证账号权限或运行时可用性"})
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SelectionError("catalog_unavailable", "无法读取本机模型目录。检查 CODEX_DUO_CODEX_CLI 后重试。", 503) from exc


def normalize_catalog(raw, source=None):
    if not isinstance(raw, dict) or not isinstance(raw.get('models'), list):
        raise SelectionError('catalog_unavailable', '本机目录格式无效。', 503)
    models = []
    for row in raw.get("models", []):
        if not isinstance(row, dict):
            continue
        if row.get("visibility") != "list":
            continue
        slug = row.get("slug", "")
        levels = row.get("supported_reasoning_levels", [])
        efforts = [r.get("effort") for r in levels if isinstance(r, dict)] if isinstance(levels, list) else []
        if not isinstance(slug, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", slug) or not efforts or any(
                not isinstance(e, str) or not re.fullmatch(r"[a-z_]+", e) for e in efforts):
            continue
        models.append({"id": slug, "name": row.get("display_name", slug),
                       "description": row.get("description", ""),
                       "efforts": list(dict.fromkeys(efforts)),
                       "default_effort": row.get("default_reasoning_level")
                       if row.get("default_reasoning_level") in efforts else efforts[0]})
    if not models or len({m['id'] for m in models}) != len(models):
        raise SelectionError("catalog_unavailable", "本机目录没有可供选择的有效模型。", 503)
    return {"models": models, "fingerprint": digest(models), "source": source or {"kind": "test"}}


def validate_selection(selection, catalog):
    if not isinstance(selection, dict) or set(selection) != {"coordinator", "worker"}:
        raise SelectionError("invalid_selection", "请分别选择主控模型和执行模型。")
    models = {m['id']: m for m in catalog['models']}
    for role in ["coordinator", "worker"]:
        value = selection[role]
        if not isinstance(value, dict) or set(value) != {"model", "reasoning_effort"}:
            raise SelectionError("invalid_selection", "模型配置字段不完整。")
        model, effort = value['model'], value['reasoning_effort']
        if not isinstance(model, str) or model not in models:
            raise SelectionError("invalid_model", "所选模型不在当前本机目录中。")
        if not isinstance(effort, str) or effort not in models[model]['efforts']:
            raise SelectionError("invalid_effort", "所选推理强度不受该模型支持。")
    return json.loads(canonical(selection))


def presets(catalog):
    candidates = [
        ("deep", "深入规划", "Astra 负责计划与验收，Luna 执行明确任务。", "gpt-6-astra", "gpt-6-luna"),
        ("balanced", "日常开发", "Sol 负责计划与验收，Luna 执行明确任务。", "gpt-6.1-sol", "gpt-6-luna"),
        ("consistent", "同模型协作", "两个角色使用同一模型，仍保留独立交接。", "gpt-6.1-sol", "gpt-6.1-sol")]
    result = []
    for key, name, description, main, worker in candidates:
        value = {"coordinator": {"model": main, "reasoning_effort": "high"},
                 "worker": {"model": worker, "reasoning_effort": "high"}}
        try:
            validate_selection(value, catalog)
        except SelectionError:
            continue
        result.append({"id": key, "name": name, "description": description, "selection": value})
    return result


def default_selection(catalog):
    options = presets(catalog)
    if options:
        return options[0]['selection']
    first = catalog['models'][0]
    return {role: {"model": first['id'], "reasoning_effort": first['default_effort']}
            for role in ['coordinator', 'worker']}


DEFAULT_WORKFLOW = {'activation': 'manual', 'coordinator_mode': 'current_thread',
                    'max_worker_turns': 3, 'max_parallel_workers': 1, 'completion_mode': 'return',
                    'planner_mode': 'disabled', 'planner_model': '',
                    'planner_reasoning_effort': '', 'max_planner_turns': 1}


def validate_workflow(value, *, legacy_completion=False):
    if (not isinstance(value, dict) or set(value) - set(DEFAULT_WORKFLOW)
            or not {'activation', 'coordinator_mode', 'max_worker_turns'} <= set(value)):
        raise SelectionError('invalid_workflow', '请提供完整的使用方式、主控方式和执行轮数。')
    modes = ('return', 'manual_review', 'wake_on_completion') if legacy_completion else ('return',)
    if value.get('completion_mode', 'return') not in modes:
        raise SelectionError('invalid_completion_mode', '完成流程仅支持 return，由原聊天等待并验收。')
    if value['activation'] not in ('automatic_project', 'manual'):
        raise SelectionError('invalid_workflow', '使用方式必须为项目自动使用或手动使用。')
    if value['coordinator_mode'] not in ('current_thread', 'selected_model'):
        raise SelectionError('invalid_workflow', '主控方式必须为当前聊天或指定模型。')
    if type(value['max_worker_turns']) is not int or not 1 <= value['max_worker_turns'] <= 10:
        raise SelectionError('invalid_workflow', '执行轮数必须为 1 到 10 的整数。')
    if type(value.get('max_parallel_workers', 1)) is not int or not 1 <= value.get('max_parallel_workers', 1) <= 3:
        raise SelectionError('invalid_workflow', '最大并行执行代理数必须为 1 到 3 的整数。')
    if value.get('planner_mode', 'disabled') not in ('disabled', 'plan_only'):
        raise SelectionError('invalid_workflow', '规划模式必须为 disabled 或 plan_only。')
    if type(value.get('max_planner_turns', 1)) is not int or not 1 <= value.get('max_planner_turns', 1) <= 3:
        raise SelectionError('invalid_workflow', '规划轮数必须为 1 到 3 的整数。')
    for key in ('planner_model', 'planner_reasoning_effort'):
        if not isinstance(value.get(key, ''), str):
            raise SelectionError('invalid_workflow', '规划模型和推理强度必须为字符串。')
        if value.get('planner_mode') == 'plan_only' and not value.get(key, '').strip():
            raise SelectionError('invalid_workflow', '启用仅规划模式前必须选择规划模型和推理强度。')
    # Preserve legacy serialization for immutable snapshot hashes.
    return dict(value)


def validate_planner_selection(workflow, catalog):
    if workflow.get('planner_mode', 'disabled') == 'plan_only':
        choice = {'model': workflow['planner_model'], 'reasoning_effort': workflow['planner_reasoning_effort']}
        validate_selection({'coordinator': choice, 'worker': choice}, catalog)


def saved_workflow(document):
    # Legacy configurations remain manual until the user explicitly enables automatic use.
    return {**DEFAULT_WORKFLOW,
            **validate_workflow((document or {}).get('workflow', DEFAULT_WORKFLOW), legacy_completion=True),
            'completion_mode': 'return'}


def safe_directory(path):
    path = Path(path).absolute()
    if path.is_symlink():
        raise SelectionError("unsafe_storage", "配置目录包含符号链接，无法写入。", 409)
    # macOS /var and /tmp are system symlinks. Canonicalize the parent while
    # rejecting a symlink at the selected storage location itself.
    path = path.parent.resolve() / path.name
    path.mkdir(parents=True, exist_ok=True)
    return path


class StorageLock:
    """Reentrant process lock: HTTP and stdio MCP may run concurrently."""
    def __init__(self, directory):
        self.directory = directory
        self.thread_lock = threading.RLock()
        self.depth = 0
        self.fd = None

    def __enter__(self):
        self.thread_lock.acquire()
        try:
            if self.depth == 0:
                safe_directory(self.directory)
                self.fd = os.open(self.directory / '.selection.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                fcntl.flock(self.fd, fcntl.LOCK_EX)
            self.depth += 1
            return self
        except BaseException:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            self.thread_lock.release()
            raise

    def __exit__(self, *args):
        self.depth -= 1
        if self.depth == 0:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None
        self.thread_lock.release()


class SelectionStore:
    def __init__(self, directory, scope="project_codex_duo_defaults"):
        self.scope = scope
        self.directory = Path(directory)
        self.path = self.directory / 'selection.json'
        self.lock = StorageLock(self.directory)

    def read(self, catalog):
        if self.directory.is_symlink() or self.path.is_symlink():
            raise SelectionError('unsafe_storage', '配置文件不能是符号链接。', 409)
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return {'document': None, 'revision': 'none', 'error': None}
        revision = hashlib.sha256(raw).hexdigest()
        try:
            document = json.loads(raw)
            if not isinstance(document, dict) or document.get('schema_version') != 1:
                raise ValueError('schema')
            validate_selection(document['selection'], catalog)
            validate_planner_selection(saved_workflow(document), catalog)
            if not isinstance(document.get('saved_at'), str):
                raise ValueError('saved_at')
            # Present canonical metadata while preserving legacy bytes/revisions.
            if document.get('scope') == 'project_fusion_defaults':
                document = {**document, 'scope': 'project_codex_duo_defaults'}
            return {'document': document, 'revision': revision, 'error': None}
        except (ValueError, KeyError, TypeError) as exc:
            return {'document': None, 'revision': revision,
                    'error': {'code': 'saved_config_invalid',
                              'message': '已保存配置损坏或不再受目录支持。可重新选择并保存；原文件会备份。'}}

    def migrate_completion(self, expected_revision):
        """Explicit settings-only retirement; reads never migrate historical ledgers."""
        with self.lock:
            if self.directory.is_symlink() or self.path.is_symlink():
                raise SelectionError('unsafe_storage', '配置不能包含符号链接。', 409)
            raw = self.path.read_bytes()
            revision = hashlib.sha256(raw).hexdigest()
            if revision != expected_revision:
                raise SelectionError('revision_conflict', '配置已变化，停止迁移。', 409)
            document = json.loads(raw)
            if not isinstance(document, dict) or document.get('schema_version') != 1:
                raise SelectionError('saved_config_invalid', '配置格式无效，停止迁移。', 409)
            workflow = document.get('workflow', DEFAULT_WORKFLOW)
            validate_workflow(workflow, legacy_completion=True)
            if workflow.get('completion_mode', 'return') == 'return':
                return {'changed': False, 'before_revision': revision, 'revision': revision}
            document['workflow'] = {**workflow, 'completion_mode': 'return'}
            backup = safe_directory(self.directory / 'history') / ('completion-return-' + revision + '.json')
            if backup.is_symlink():
                raise SelectionError('unsafe_storage', '迁移备份不能是符号链接。', 409)
            if backup.exists():
                if backup.read_bytes() != raw:
                    raise SelectionError('backup_conflict', '迁移备份冲突，停止迁移。', 409)
            else:
                with backup.open('xb') as handle: handle.write(raw)
            fd, temporary = tempfile.mkstemp(prefix='.selection-', dir=self.directory)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(json.dumps(document, ensure_ascii=False, indent=2).encode() + b'\n')
                    handle.flush(); os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)
            return {'changed': True, 'before_revision': revision,
                    'revision': hashlib.sha256(self.path.read_bytes()).hexdigest(), 'backup': str(backup)}

    def save(self, selection, catalog, expected_revision, workflow=None):
        value = validate_selection(selection, catalog)
        with self.lock:
            safe_directory(self.directory)
            current = self.read(catalog)
            preferences = saved_workflow(current['document']) if workflow is None else {
                **saved_workflow(current['document']), **validate_workflow(workflow)}
            validate_planner_selection(preferences, catalog)
            if expected_revision != current['revision']:
                raise SelectionError('revision_conflict', '配置已被其他窗口更新。请恢复已保存配置后重试。', 409)
            if (current['document'] and current['document']['selection'] == value
                    and saved_workflow(current['document']) == preferences):
                return {**current, 'changed': False}
            if current['error']:
                backup = safe_directory(self.directory / 'history') / (current['revision'] + '.json')
                if not backup.exists():
                    with backup.open('xb') as handle:
                        handle.write(self.path.read_bytes())
            document = {'schema_version': 1, 'selection': value,
                        'workflow': preferences,
                        'catalog_fingerprint': catalog['fingerprint'],
                        'saved_at': datetime.now(timezone.utc).isoformat(),
                        'scope': self.scope, 'execution_started': False}
            fd, temporary = tempfile.mkstemp(prefix='.selection-', dir=self.directory)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(json.dumps(document, ensure_ascii=False, indent=2).encode() + b'\n')
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return {**self.read(catalog), 'changed': True}


def validate_task(task):
    from codex_duo import relative, argv_valid, EvidenceError
    if not isinstance(task, dict) or task.get('schema_version') != 1:
        raise SelectionError('invalid_task', '任务必须使用交接契约 schema_version=1。')
    if task.get('mode') == 'plan_only' or {'plan_id', 'read_paths', 'suggested_tests'} & set(task):
        raise SelectionError('invalid_task', '规划输出不能作为执行任务；请明确新建并批准执行契约。')
    for key in ['task_id', 'goal']:
        if not isinstance(task.get(key), str) or not task[key].strip() or len(task[key]) > 4000:
            raise SelectionError('invalid_task', '任务 ID 和目标不能为空。')
    for key in ['allowed_paths', 'acceptance']:
        if not isinstance(task.get(key), list) or not task[key] or not all(
                isinstance(x, str) and x for x in task[key]):
            raise SelectionError('invalid_task', '请提供文件范围和验收条件。')
    try:
        for value in task['allowed_paths']:
            relative(value)
    except EvidenceError as exc:
        raise SelectionError('invalid_task', '任务文件路径必须限制在工作区内。') from exc
    if not isinstance(task.get('tests'), list) or not task['tests'] or not all(argv_valid(x) for x in task['tests']):
        raise SelectionError('invalid_task', '测试命令必须是非空 argv 数组。')
    # Task content is serialized as data; commands are never executed here.
    return json.loads(canonical(task))


def prepare_handoff(task, selection, catalog, destination, revision, workflow=None, *, legacy_completion=False):
    task = validate_task(task)
    selection = validate_selection(selection, catalog)
    payload = {'schema_version': 1, 'task': task, 'selection': selection,
               'catalog_fingerprint': catalog['fingerprint'], 'selection_revision': revision}
    if workflow is not None:
        payload['workflow'] = validate_workflow(workflow, legacy_completion=legacy_completion)
    identifier = digest(payload)[:24]
    root = safe_directory(destination)
    target = root / identifier
    coordinator, worker = selection['coordinator'], selection['worker']
    manifest = {**payload, 'handoff_id': identifier, 'state': 'prepared_not_started',
                'execution_started': False, 'applies_to_current_thread': False,
                'scope': 'new_codex_duo_task_with_explicit_role_settings',
                'launch_approval_required': True, 'task_sha256': digest(task),
                'worker_spawn_parameters': {'fork_turns': 'none', 'model': worker['model'],
                                            'reasoning_effort': worker['reasoning_effort']}}
    toml = lambda role: 'model = ' + json.dumps(role['model']) + '\nmodel_reasoning_effort = ' + json.dumps(role['reasoning_effort']) + '\n'
    files = {
        'task.json': json.dumps(task, ensure_ascii=False, indent=2) + '\n',
        'handoff.json': json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
        'config/project.toml': toml(coordinator) + '\n[agents]\nenabled = false\nmax_concurrent_threads_per_session = 1\n\n[features]\nhooks = false\n',
        'config/codex_duo_worker.toml': 'name = "codex_duo_worker"\ndescription = "Execute the approved bounded task and return compact evidence."\n' + toml(worker) +
            'developer_instructions = "Read task.json; stay within allowed_paths; return diff, test evidence and blockers. Do not spawn more agents or change global configuration. Launch only after user approval."\n',
        'README.md': '# Prepared Codex Duo handoff\n\nThis package has not started a task.\n'
            'Create a new coordinator task with the requested model and effort after approval.\n'
            'Verify the actual coordinator model before launching the bounded worker.\n'
            'The current thread is not changed by this package. Candidate TOML files are not installed.\n'
            'Use the existing codex_duo.py verify command with task.json and worker evidence for acceptance.\n'}
    if workflow is not None:
        current = workflow['coordinator_mode'] == 'current_thread'
        manifest.update({'coordinator_mode': workflow['coordinator_mode'],
                         'scope': 'authorized_project_task',
                         'max_worker_turns': workflow['max_worker_turns'],
                         'authorization': 'User task plus saved project preferences; scope still applies.',
                         'launch_approval_required': False})
        files['handoff.json'] = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
        files['README.md'] = ('# Codex Duo internal task snapshot\n\n'
            'No model has started. The coordinator consumes this snapshot automatically.\n'
            + ('The current chat plans and verifies; the saved coordinator model is inactive.\n' if current else
               'The selected coordinator requires an explicitly requested new chat; do not switch the current chat.\n')
            + f"Use one native worker, at most {workflow['max_worker_turns']} dispatches including corrections.\n"
            'Read the saved project policy and current user request for authorization.\n'
            'Do not ask the user to copy this directory or repeat an existing authorization.\n'
            'Use codex_duo.py verify, then independently inspect the diff and rerun relevant checks.\n')
    if workflow is not None and 'max_parallel_workers' in workflow:
        files['README.md'] = files['README.md'].replace(
            f"Use one native worker, at most {workflow['max_worker_turns']} dispatches including corrections.",
            f"Use at most {workflow['max_parallel_workers']} native workers concurrently, bounded by actual host capacity. \
All workstreams and corrections share {workflow['max_worker_turns']} total dispatches. Reserve each dispatch before native execution.")
    if target.is_symlink():
        raise SelectionError('handoff_conflict', '交接目录不可用。', 409)
    if target.exists():
        for name, text in files.items():
            path = snapshot_path(target, name)
            if path.is_symlink() or not path.is_file():
                raise SelectionError('handoff_conflict', '已有交接包内容已变化，未覆盖。', 409)
            actual = path.read_text()
            if path.name == 'fusion_worker.toml':  # Immutable migration input only.
                actual = actual.replace('name = "fusion_worker"', 'name = "codex_duo_worker"')
            if name == 'README.md':
                actual = actual.replace('Fusion', 'Codex Duo').replace('fusion.py', 'codex_duo.py').replace('fusion.reserve', 'codex_duo_reserve')
            if name == 'handoff.json':
                old = json.loads(actual)
                if old.get('scope') == 'new_fusion_task_with_explicit_role_settings':
                    old['scope'] = 'new_codex_duo_task_with_explicit_role_settings'
                actual = json.dumps(old, ensure_ascii=False, indent=2) + '\n'
            if actual != text:
                raise SelectionError('handoff_conflict', '已有交接包内容已变化，未覆盖。', 409)
        return {'id': identifier, 'path': str(target), 'created': False, 'manifest': manifest}
    temporary = Path(tempfile.mkdtemp(prefix='.handoff-', dir=root))
    try:
        for name, text in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        os.rename(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {'id': identifier, 'path': str(target), 'created': True, 'manifest': manifest}


def snapshot_path(target, name):
    """Recognize one immutable legacy filename without exposing an old role."""
    path = target / name
    if name == 'config/codex_duo_worker.toml':
        legacy = target / 'config/fusion_worker.toml'
        if legacy.exists() and path.exists():
            raise SelectionError('handoff_conflict', '交接包含冲突的旧新角色配置，未覆盖。', 409)
        if legacy.exists():
            return legacy
    return path
