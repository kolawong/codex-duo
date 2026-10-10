"""Global defaults and project overrides; resolution never writes or reroutes a chat."""
import os
from pathlib import Path
from fusion_selection import SelectionStore, SelectionError


def global_directory():
    home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser()
    if not home.is_absolute():
        raise SelectionError('unsafe_storage', 'CODEX_HOME 必须为绝对路径。', 409)
    return home / 'codex-duo'


class Defaults:
    def __init__(self, project_store):
        self.project = project_store
        self.global_store = SelectionStore(global_directory(), scope='global_duo_defaults')

    def store(self, scope):
        if scope not in ('global', 'project'):
            raise SelectionError('invalid_scope', '设置范围必须为 global 或 project。')
        return self.global_store if scope == 'global' else self.project

    def read(self, catalog):
        local, global_saved = self.project.read(catalog), self.global_store.read(catalog)
        # An invalid layer must be repaired explicitly, even if another layer exists.
        error = local['error'] or global_saved['error']
        source = 'project' if local['document'] else 'global' if global_saved['document'] else 'unconfigured'
        effective = local if local['document'] else global_saved
        return {'project': local, 'global': global_saved, 'source': source,
                'effective': {**effective, 'error': error}}

    def resolved(self, catalog):
        layers = self.read(catalog)
        if layers['effective']['error']:
            raise SelectionError('saved_config_invalid', layers['effective']['error']['message'], 409)
        return layers

    def reset(self, catalog, expected_revision, expected_global_revision):
        # Global first is the shared lock ordering for save, reset and snapshots.
        with self.global_store.lock, self.project.lock:
            layers = self.read(catalog)
            if expected_revision != layers['project']['revision'] or expected_global_revision != layers['global']['revision']:
                raise SelectionError('revision_conflict', '配置已在其他窗口更新，请重新载入后重试。', 409)
            if layers['global']['error']:
                raise SelectionError('saved_config_invalid', '全局配置无效，请先修复全局设置。', 409)
            if self.project.path.exists():
                # Preserve even malformed overrides as a recoverable history entry.
                from fusion_selection import safe_directory
                backup = safe_directory(self.project.directory / 'history') / (layers['project']['revision'] + '.json')
                if not backup.exists(): backup.write_bytes(self.project.path.read_bytes())
                self.project.path.unlink()
            return self.project.read(catalog)
