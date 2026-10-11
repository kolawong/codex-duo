"""Explicit, byte-preserving project state migration. Never launches models."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from codex_duo_selection import SelectionError, StorageLock

LEGACY_DIRECTORY = '.fusion'  # Migration recognition only, never active storage.
CURRENT_DIRECTORY = '.codex-duo'


def marker(root):
    return {'schema_version': 1, 'migration': 'codex-duo-state',
            'destination': str(root / CURRENT_DIRECTORY)}


def ensure_current_storage(directory):
    directory = Path(directory)
    if directory.name != CURRENT_DIRECTORY:
        return
    legacy = directory.parent / LEGACY_DIRECTORY
    journal = directory.parent / '.codex-duo-migration.json'
    if journal.exists() and not legacy.exists():
        raise SelectionError('migration_incomplete', '状态迁移尚未完成，请恢复同一次迁移；不会创建新预算。', 409)
    if legacy.is_symlink():
        raise SelectionError('unsafe_storage', '旧状态不能包含符号链接。', 409)
    if legacy.is_dir():
        raise SelectionError('migration_required', '请先显式迁移旧项目状态；不会忽略已有预算或覆盖新状态。', 409)
    if legacy.exists():
        try:
            valid = json.loads(legacy.read_bytes()) == marker(directory.parent.resolve())
        except (OSError, ValueError):
            valid = False
        if not valid or not directory.is_dir() or directory.is_symlink():
            raise SelectionError('migration_conflict', '旧状态标记或迁移目标冲突，未覆盖。', 409)


def manifest(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            # Rename the container, never follow nested links in historical test
            # evidence. Active readers still reject linked settings and contracts.
            result[str(path.relative_to(directory))] = {'type': 'symlink',
                'target_sha256': hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()}
        elif not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise SelectionError('unsafe_storage', '状态含特殊文件，停止迁移。', 409)
        elif stat.S_ISREG(mode) and path.name != '.selection.lock':
            result[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def migrate(project_root):
    from codex_duo_projects import project_path
    root = project_path(project_root)
    legacy, current = root / LEGACY_DIRECTORY, root / CURRENT_DIRECTORY
    journal = root / '.codex-duo-migration.json'
    # One project-specific lock; no global preferences or security configuration.
    fd = os.open(root / '.codex-duo-migration.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if legacy.is_symlink() or current.is_symlink():
            raise SelectionError('unsafe_storage', '状态目录不能是符号链接。', 409)
        if not legacy.exists() and journal.exists():
            if journal.is_symlink():
                raise SelectionError('unsafe_storage', '迁移记录不能是符号链接。', 409)
            saved = json.loads(journal.read_bytes())
            if saved.get('destination') != str(current) or not current.is_dir() or manifest(current) != saved.get('files'):
                raise SelectionError('migration_conflict', '中断迁移与现有状态冲突，未覆盖。', 409)
            write_marker(root, legacy)
            return {'state': 'migration_recovered', 'changed': True, 'files': saved['files'], 'model_calls': 0}
        if not legacy.exists():
            return {'state': 'no_legacy_state', 'changed': False, 'model_calls': 0}
        if not legacy.is_dir():
            ensure_current_storage(current)
            return {'state': 'already_migrated', 'changed': False, 'model_calls': 0}
        if current.exists():
            raise SelectionError('migration_conflict', '新旧状态同时存在；保留两者且停止，不合并预算。', 409)
        with StorageLock(legacy):
            before = manifest(legacy)
            intent = {**marker(root), 'files': before}
            if journal.exists():
                if journal.is_symlink() or json.loads(journal.read_bytes()) != intent:
                    raise SelectionError('migration_conflict', '已有迁移记录冲突，未覆盖。', 409)
            else:
                with journal.open('x') as handle:
                    json.dump(intent, handle, ensure_ascii=False)
                    handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
                sync(root)
            os.rename(legacy, current)
            # A file tombstone stops an old plugin from recreating an empty directory
            # and hence restarting a consumed budget. All original bytes stay intact.
            write_marker(root, legacy)
            after = manifest(current)
            if before != after:
                raise SelectionError('migration_changed', '迁移后状态变化，保留记录并停止。', 409)
            return {'state': 'migrated', 'changed': True, 'source': str(legacy),
                    'destination': str(current), 'files': after, 'model_calls': 0}
    finally:
        os.close(fd)


def write_marker(root, legacy):
    with legacy.open('x') as handle:
        json.dump(marker(root), handle, ensure_ascii=False)
        handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
    os.chmod(legacy, 0o400)
    sync(root)
