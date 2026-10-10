"""Model selection and immutable handoffs. No inference, installation, or global writes."""
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
    cli = cli or os.environ.get("FUSION_CODEX_CLI") or "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
    try:
        raw = subprocess.run([cli, "debug", "models", "--bundled"], capture_output=True,
                             text=True, timeout=10, check=True)
        version = subprocess.run([cli, "--version"], capture_output=True,
                                 text=True, timeout=5, check=True).stdout.strip()
        return normalize_catalog(json.loads(raw.stdout), {"kind": "bundled_cli", "cli": cli,
            "version": version, "loaded_at": datetime.now(timezone.utc).isoformat(),
            "availability": "本机内置目录；未验证账号权限或运行时可用性"})
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SelectionError("catalog_unavailable", "无法读取本机模型目录。检查 FUSION_CODEX_CLI 后重试。", 503) from exc


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
    def __init__(self, directory):
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
            if not isinstance(document.get('saved_at'), str):
                raise ValueError('saved_at')
            return {'document': document, 'revision': revision, 'error': None}
        except (ValueError, KeyError, TypeError) as exc:
            return {'document': None, 'revision': revision,
                    'error': {'code': 'saved_config_invalid',
                              'message': '已保存配置损坏或不再受目录支持。可重新选择并保存；原文件会备份。'}}

    def save(self, selection, catalog, expected_revision):
        value = validate_selection(selection, catalog)
        with self.lock:
            safe_directory(self.directory)
            current = self.read(catalog)
            if current['document'] and current['document']['selection'] == value:
                return {**current, 'changed': False}
            if expected_revision != current['revision']:
                raise SelectionError('revision_conflict', '配置已被其他窗口更新。请恢复已保存配置后重试。', 409)
            if current['error']:
                backup = safe_directory(self.directory / 'history') / (current['revision'] + '.json')
                if not backup.exists():
                    with backup.open('xb') as handle:
                        handle.write(self.path.read_bytes())
            document = {'schema_version': 1, 'selection': value,
                        'catalog_fingerprint': catalog['fingerprint'],
                        'saved_at': datetime.now(timezone.utc).isoformat(),
                        'scope': 'new_fusion_handoffs_only', 'execution_started': False}
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
    from fusion import relative, argv_valid, EvidenceError
    if not isinstance(task, dict) or task.get('schema_version') != 1:
        raise SelectionError('invalid_task', '任务必须使用交接契约 schema_version=1。')
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


def prepare_handoff(task, selection, catalog, destination, revision):
    task = validate_task(task)
    selection = validate_selection(selection, catalog)
    payload = {'schema_version': 1, 'task': task, 'selection': selection,
               'catalog_fingerprint': catalog['fingerprint'], 'selection_revision': revision}
    identifier = digest(payload)[:24]
    root = safe_directory(destination)
    target = root / identifier
    coordinator, worker = selection['coordinator'], selection['worker']
    manifest = {**payload, 'handoff_id': identifier, 'state': 'prepared_not_started',
                'execution_started': False, 'applies_to_current_thread': False,
                'scope': 'new_fusion_task_with_explicit_role_settings',
                'launch_approval_required': True, 'task_sha256': digest(task),
                'worker_spawn_parameters': {'fork_turns': 'none', 'model': worker['model'],
                                            'reasoning_effort': worker['reasoning_effort']}}
    toml = lambda role: 'model = ' + json.dumps(role['model']) + '\nmodel_reasoning_effort = ' + json.dumps(role['reasoning_effort']) + '\n'
    files = {
        'task.json': json.dumps(task, ensure_ascii=False, indent=2) + '\n',
        'handoff.json': json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
        'config/project.toml': toml(coordinator) + '\n[agents]\nenabled = false\nmax_concurrent_threads_per_session = 1\n\n[features]\nhooks = false\n',
        'config/fusion_worker.toml': 'name = "fusion_worker"\ndescription = "Execute the approved bounded task and return compact evidence."\n' + toml(worker) +
            'developer_instructions = "Read task.json; stay within allowed_paths; return diff, test evidence and blockers. Do not spawn more agents or change global configuration. Launch only after user approval."\n',
        'README.md': '# Prepared Fusion handoff\n\nThis package has not started a task.\n'
            'Create a new coordinator task with the requested model and effort after approval.\n'
            'Verify the actual coordinator model before launching the bounded worker.\n'
            'The current thread is not changed by this package. Candidate TOML files are not installed.\n'
            'Use the existing fusion.py verify command with task.json and worker evidence for acceptance.\n'}
    if target.is_symlink():
        raise SelectionError('handoff_conflict', '交接目录不可用。', 409)
    if target.exists():
        if any(not (target / name).is_file() or (target / name).read_text() != text for name, text in files.items()):
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
