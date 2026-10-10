"""Explicit project scoping and bounded, reversible project instruction opt-in."""
from pathlib import Path
import os
import tempfile
from fusion_selection import SelectionError

START = '<!-- codex-duo:begin -->'
END = '<!-- codex-duo:end -->'
BLOCK = f'''{START}
## Codex Duo project workflow

For user-requested implementation or bug fixes, load the `codex-duo` skill and read
`fusion.defaults` with the actual current chat project directory as `project_root`.
Pass this same explicit root to every fusion.* call; menu selection never routes chats.
Resolve project overrides before global defaults. Follow saved activation:
automatic_project uses this chat and supported native workers, bounded by the saved
maximum parallel count, actual host capacity and shared total turn limit; simple tasks use one;
manual requires the user to request Codex Duo. Ordinary questions, read-only checks,
configuration changes and explicit no-model requests do not start workers.
Workers must not recursively invoke Codex Duo. Preserve task scope and existing authorization;
do not create chats, commit, publish or change global configuration without a user request.
{END}'''


def project_path(value):
    if not isinstance(value, (str, Path)) or not str(value).startswith('/'):
        raise SelectionError('invalid_project', '项目必须是现有的绝对路径目录。')
    path = Path(value)
    if '..' in path.parts or path.is_symlink() or not path.is_dir():
        raise SelectionError('invalid_project', '项目必须是现有的绝对路径目录，不能是符号链接。')
    return path.resolve(strict=True)


def instructions(root):
    path = root / 'AGENTS.md'
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise SelectionError('unsafe_instructions', 'AGENTS.md 不是普通文件；未修改项目指令或配置。', 409)
    original = path.read_bytes() if path.exists() else None
    if original is not None and len(original) > 1024 * 1024:
        raise SelectionError('unsafe_instructions', 'AGENTS.md 过大；未修改项目指令或配置。', 409)
    try:
        text = (original or b'').decode('utf-8')
    except UnicodeError as exc:
        raise SelectionError('unsafe_instructions', 'AGENTS.md 不是 UTF-8；未修改项目指令或配置。', 409) from exc
    if text.count(START) != text.count(END) or text.count(START) > 1 or (END in text and text.index(END) < text.index(START)):
        raise SelectionError('unsafe_instructions', 'AGENTS.md 的 Codex Duo 标记不完整；未修改项目指令或配置。', 409)
    return path, original, text


def opt_in_status(root):
    try:
        _, _, text = instructions(root)
        return {'enabled': BLOCK in text, 'error': None}
    except (SelectionError, OSError) as exc:
        return {'enabled': False, 'error': {'code': getattr(exc, 'code', 'instructions_unavailable'), 'message': str(exc)}}


def atomic_instructions(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.codex-duo-', dir=path.parent)
    try:
        if path.exists():
            os.fchmod(fd, path.stat(follow_symlinks=False).st_mode & 0o777)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(value); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def enable_and_save(root, save):
    """Called under the project storage lock; roll back instructions on save failure."""
    path, original, text = instructions(root)
    if START in text:
        begin, end = text.index(START), text.index(END) + len(END)
        updated = text[:begin] + BLOCK + text[end:]
    else:
        updated = text + ('\n' if text.endswith('\n') else '\n\n' if text else '') + BLOCK + '\n'
    value = updated.encode('utf-8')
    changed = value != original
    if instructions(root)[1] != original:
        raise SelectionError('instructions_conflict', '项目指令刚在别处修改，请重试。', 409)
    if changed: atomic_instructions(path, value)
    try:
        return save()
    except BaseException as exc:
        if changed:
            try:
                if instructions(root)[1] != value:
                    raise OSError('instructions changed externally')
                if original is None: path.unlink()
                else: atomic_instructions(path, original)
            except (OSError, SelectionError) as rollback:
                raise SelectionError('instructions_rollback_failed', '配置保存失败，项目指令回滚也失败；请检查 AGENTS.md 后重试。', 503) from rollback
        raise exc
