"""Shared application service for HTTP, MCP settings and the MCP App."""
import json
from pathlib import Path
from fusion_selection import (SelectionError, SelectionStore, read_catalog, default_selection,
                              presets, prepare_handoff, digest, validate_selection)


class FusionService:
    def __init__(self, directory, catalog_loader=read_catalog):
        self.store = SelectionStore(directory)
        self.catalog_loader = catalog_loader
        self.template = json.loads((Path(__file__).parent.parent / 'templates/task.json').read_text())

    def state(self):
        try:
            catalog = self.catalog_loader()
        except SelectionError as exc:
            return {'catalog': None, 'error': {'code': exc.code, 'message': str(exc)},
                    'task_template': self.template}
        return {'catalog': catalog, 'presets': presets(catalog), 'default': default_selection(catalog),
                'saved': self.store.read(catalog), 'task_template': self.template,
                'storage_path': str(self.store.path), 'current_thread_model': 'unknown',
                'native_model_switch': False, 'execution_started': False}

    def save(self, body):
        return self.store.save(body.get('selection'), self.catalog_loader(), body.get('expected_revision'))

    def prepare(self, body):
        with self.store.lock:
            catalog = self.catalog_loader()
            saved = self.store.read(catalog)
            if not saved['document']:
                raise SelectionError('save_required', '先保存一份有效配置，再生成交接包。', 409)
            if body.get('expected_revision') != saved['revision']:
                raise SelectionError('revision_conflict', '保存版本已变化，请恢复已保存配置后重试。', 409)
            return prepare_handoff(body.get('task'), saved['document']['selection'], catalog,
                                   self.store.directory / 'handoffs', saved['revision'])

    def settings_read(self):
        state = self.state()
        if state['catalog'] is None:
            raise SelectionError('catalog_unavailable', state['error']['message'], 503)
        if state['saved']['error']:
            raise SelectionError('saved_config_invalid', '请打开模型面板恢复损坏或过期配置。', 409)
        selection = state['saved']['document']['selection'] if state['saved']['document'] else state['default']
        pairs = [m['id'] + ' / ' + e for m in state['catalog']['models'] for e in m['efforts']]
        properties = {role: {'type': 'string', 'title': title, 'enum': pairs,
            'description': '模型 / 推理强度。仅影响未来交接，不切换当前会话，不启动任务。'}
            for role, title in [('coordinator', '主控模型与强度'), ('worker', '执行模型与强度')]}
        return {'schema': {'type': 'object', 'properties': properties},
                'values': {r: selection[r]['model'] + ' / ' + selection[r]['reasoning_effort'] for r in properties},
                'layout': [{'kind': 'group', 'title': 'Fusion · 新任务默认配置', 'items': [
                    {'kind': 'property', 'property': r} for r in properties] + [
                    {'kind': 'tool', 'tool': 'fusion.open', 'title': '打开模型面板',
                     'description': '预设、保存恢复、任务交接；不启动模型。'}]}]}

    def settings_update(self, changes):
        with self.store.lock:
            catalog = self.catalog_loader()
            saved = self.store.read(catalog)
            if saved['error']:
                raise SelectionError('saved_config_invalid', '请先在模型面板恢复配置。', 409)
            selection = saved['document']['selection'] if saved['document'] else default_selection(catalog)
            for role, pair in changes.items():
                if role not in ('coordinator', 'worker') or not isinstance(pair, str) or pair.count(' / ') != 1:
                    raise SelectionError('invalid_selection', '设置必须为有效的模型 / 推理强度组合。')
                model, effort = pair.split(' / ')
                selection[role] = {'model': model, 'reasoning_effort': effort}
            self.store.save(selection, catalog, saved['revision'])
            return {'values': {r: selection[r]['model'] + ' / ' + selection[r]['reasoning_effort'] for r in selection}}

    def execution_plan(self, identifier):
        # IDs, never caller-supplied paths. Reject linked or tampered snapshots.
        import re
        if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{24}', identifier):
            raise SelectionError('invalid_handoff', '交接 ID 格式无效。')
        root = self.store.directory / 'handoffs'
        target = root / identifier
        paths = [self.store.directory, root, target, target / 'handoff.json', target / 'task.json',
                 target / 'config', target / 'config/project.toml', target / 'config/fusion_worker.toml',
                 target / 'README.md']
        if any(p.is_symlink() for p in paths):
            raise SelectionError('unsafe_storage', '交接包不能包含符号链接。', 409)
        try:
            manifest = json.loads((target / 'handoff.json').read_text())
            catalog = self.catalog_loader()
            payload = {k: manifest[k] for k in ('schema_version', 'task', 'selection', 'catalog_fingerprint', 'selection_revision')}
            if digest(payload)[:24] != identifier or manifest.get('handoff_id') != identifier:
                raise ValueError('digest')
            if catalog['fingerprint'] != manifest['catalog_fingerprint']:
                raise SelectionError('catalog_changed', '模型目录已变化，请重新生成交接包。', 409)
            validate_selection(manifest['selection'], catalog)
            # Existing path: verify every immutable artifact, never modify it.
            result = prepare_handoff(manifest['task'], manifest['selection'], catalog, root, manifest['selection_revision'])
            if result['created']:
                raise ValueError('missing snapshot')
        except (OSError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, SelectionError):
                raise
            raise SelectionError('invalid_handoff', '交接包不存在或已损坏。', 409) from exc
        return {'schema_version': 1, 'handoff_id': identifier, 'state': 'approval_required',
                'execution_started': False, 'applies_to_current_thread': False,
                'coordinator': {'requires_new_task': True, **manifest['selection']['coordinator']},
                'worker': manifest['worker_spawn_parameters'], 'task': manifest['task'],
                'verification': 'Use fusion.py verify with task.json and worker result; coordinator independently reviews diff and reruns tests.',
                'required_before_execution': ['Explicit user approval for this task and model pair',
                    'Create a new coordinator task with the selected model and effort',
                    'Verify the actual coordinator settings before spawning one worker'],
                'adapter': 'Declarative handoff only; this server implements no model launcher or thread-switch API.'}
