"""Shared application service for HTTP, MCP settings and the MCP App."""
import json
from pathlib import Path
from fusion_defaults import Defaults
from fusion_projects import project_path, opt_in_status, enable_and_save, instructions
from fusion_selection import (SelectionError, SelectionStore, read_catalog, default_selection,
                              presets, prepare_handoff, digest, validate_selection, saved_workflow, validate_workflow)


class FusionService:
    def __init__(self, directory, catalog_loader=read_catalog):
        self.store = SelectionStore(directory)
        self.catalog_loader = catalog_loader
        self.defaults_store = Defaults(self.store)
        self.template = json.loads((Path(__file__).parent.parent / 'templates/task.json').read_text())

    def state(self, scope="project"):
        try:
            catalog = self.catalog_loader()
        except SelectionError as exc:
            return {'catalog': None, 'error': {'code': exc.code, 'message': str(exc)},
                    'task_template': self.template}
        layers = self.defaults_store.read(catalog)
        saved = layers[scope] if scope in ('project', 'global') else self.defaults_store.store(scope).read(catalog)
        effective = layers['effective']
        selected = saved if scope == 'global' else effective
        return {'catalog': catalog, 'presets': presets(catalog), 'default': (selected['document'] or {}).get('selection', default_selection(catalog)),
                'saved': saved, 'workflow': saved_workflow(selected['document']),
                'scope': scope, 'source': ('global' if saved['document'] else 'unconfigured') if scope == 'global' else layers['source'],
                'effective': effective, 'layers': layers, 'global_revision': layers['global']['revision'], 'task_template': self.template,
                'project_root': str(self.store.directory.parent.resolve()),
                'project_opt_in': opt_in_status(self.store.directory.parent.resolve()),
                'storage_path': str(self.defaults_store.store(scope).path), 'current_thread_model': 'unknown',
                'native_model_switch': False, 'execution_started': False}

    def save(self, body):
        if 'project_root' in body:
            self.check_project(body['project_root'])
        scope = body.get('scope', 'project')
        target = self.defaults_store.store(scope)
        enable = body.get('enable_project', False)
        if scope == 'global' and enable:
            raise SelectionError('invalid_scope', '全局设置不会写入项目指令。')
        if type(enable) is not bool:
            raise SelectionError('invalid_arguments', 'enable_project 必须为布尔值。')
        if enable and (body.get('workflow') or {}).get('activation') != 'automatic_project':
            raise SelectionError('invalid_workflow', '只有明确保存本项目自动模式时才能启用项目指令。')
        catalog = self.catalog_loader()
        validate_selection(body.get('selection'), catalog)
        if body.get('workflow') is not None: validate_workflow(body['workflow'])
        def save():
            with self.defaults_store.global_store.lock:
                if 'expected_global_revision' in body and self.defaults_store.global_store.read(catalog)['revision'] != body['expected_global_revision']:
                    raise SelectionError('revision_conflict', '全局配置已变化，请重新载入。', 409)
                return target.save(body.get('selection'), catalog, body.get('expected_revision'), body.get('workflow'))
        if enable:
            root = self.store.directory.parent.resolve()
            instructions(root)  # preflight before creating any storage
            with self.defaults_store.global_store.lock, self.store.lock:
                saved = enable_and_save(root, save)
        else:
            saved = save()
        return {**saved, 'scope': scope, 'project_opt_in': opt_in_status(self.store.directory.parent.resolve()),
                'state': self.state(scope)}

    def reset(self, body):
        self.check_project(body.get('project_root'))
        self.defaults_store.reset(self.catalog_loader(), body.get('expected_revision'), body.get('expected_global_revision'))
        return self.state('project')

    def check_project(self, project_root):
        if project_path(project_root) != self.store.directory.parent.resolve():
            raise SelectionError('project_mismatch', '此配置仅用于显式指定的项目，不能应用到其他项目。', 409)

    def defaults(self, project_root):
        """Compact model-visible entry point. Reading does not create files."""
        self.check_project(project_root)
        layers = self.defaults_store.resolved(self.catalog_loader())
        saved = layers['effective']
        if saved['error']:
            raise SelectionError('saved_config_invalid', saved['error']['message'], 409)
        if not saved['document']:
            return {'configured': False, 'state': 'setup_required', 'setup_tool': 'fusion.open',
                    'execution_started': False}
        workflow = saved_workflow(saved['document'])
        return {'configured': True, 'state': 'ready', 'project_root': project_root,
                'revision': saved['revision'], 'source': layers['source'], 'workflow': workflow,
                'worker': saved['document']['selection']['worker'],
                'coordinator': {'mode': workflow['coordinator_mode'],
                    'selected_model': saved['document']['selection']['coordinator']
                    if workflow['coordinator_mode'] == 'selected_model' else None},
                'planner': {'mode': workflow.get('planner_mode', 'disabled'),
                    'model': workflow.get('planner_model', ''),
                    'reasoning_effort': workflow.get('planner_reasoning_effort', ''),
                    'max_turns': workflow.get('max_planner_turns', 1)},
                'planning_tool': 'fusion.planner_begin',
                'next_tool': 'fusion.begin', 'execution_started': False,
                'instructions': 'Use these saved settings for the authorized task. Do not reopen settings, '
                    'ask for JSON or handoff paths, or request the same approval again. '
                    'Discover a native worker tool before dispatch; this MCP server does not launch models.'}

    def begin(self, body):
        """Resolve current defaults and create the internal task snapshot in one step."""
        self.check_project(body.get('project_root'))
        with self.defaults_store.global_store.lock, self.store.lock:
            catalog = self.catalog_loader()
            saved = self.defaults_store.resolved(catalog)['effective']
            if not saved['document']:
                raise SelectionError('setup_required', '请先完成一次 Codex Duo 配置。已有无效配置时请恢复。', 409)
            workflow = saved_workflow(saved['document'])
            invocation = body.get('invocation')
            if invocation not in ('automatic', 'explicit'):
                raise SelectionError('invalid_invocation', '请说明由项目默认流程还是用户明确要求启用。')
            if invocation == 'automatic' and workflow['activation'] != 'automatic_project':
                raise SelectionError('manual_mode', '当前为手动模式，仅在用户要求使用 Codex Duo 时启用。', 409)
            prepared = prepare_handoff(body.get('task'), saved['document']['selection'], catalog,
                                       self.store.directory / 'handoffs', saved['revision'], workflow)
            plan = self.execution_plan(prepared['id'])
            return {**plan, 'handoff_path': prepared['path'], 'created': prepared['created'],
                    'evidence_root': str(self.store.directory / 'runs' / prepared['id']),
                    'task_path': str(Path(prepared['path']) / 'task.json')}

    def prepare(self, body):
        if 'project_root' in body: self.check_project(body['project_root'])
        with self.defaults_store.global_store.lock, self.store.lock:
            catalog = self.catalog_loader()
            saved = self.defaults_store.resolved(catalog)['effective']
            if not saved['document']:
                raise SelectionError('save_required', '先保存一份有效配置，再生成交接包。', 409)
            if body.get('expected_revision') != saved['revision']:
                raise SelectionError('revision_conflict', '保存版本已变化，请恢复已保存配置后重试。', 409)
            return prepare_handoff(body.get('task'), saved['document']['selection'], catalog,
                                   self.store.directory / 'handoffs', saved['revision'])

    def settings_read(self):
        state = self.state("global")
        if state['catalog'] is None:
            raise SelectionError('catalog_unavailable', state['error']['message'], 503)
        if state['saved']['error']:
            raise SelectionError('saved_config_invalid', '请打开模型面板恢复损坏或过期配置。', 409)
        selection = state['saved']['document']['selection'] if state['saved']['document'] else state['default']
        pairs = [m['id'] + ' / ' + e for m in state['catalog']['models'] for e in m['efforts']]
        properties = {role: {'type': 'string', 'title': title, 'enum': pairs,
            'description': '保存后持续使用，直到主动修改。保存本身不启动任务。'}
            for role, title in [('worker', '执行模型与强度'), ('coordinator', '高级：指定主控模型与强度')]}
        properties.update({
            'activation': {'type': 'string', 'title': '使用方式',
                'enum': ['automatic_project', 'manual'],
                'description': '全局默认：automatic_project 让各项目开发任务自动使用；manual 仅明确请求时使用。项目覆盖优先。'},
            'coordinator_mode': {'type': 'string', 'title': '主控方式',
                'enum': ['current_thread', 'selected_model'],
                'description': 'current_thread：当前聊天规划验收；selected_model：另开聊天使用指定主控。'},
            'planner_mode': {'type': 'string', 'title': '独立规划代理', 'enum': ['disabled', 'plan_only'],
                'description': '仅规划返回当前聊天确认。要求宿主确认只读能力；不会启动执行代理。'},
            'planner_model': {'type': 'string', 'title': '规划模型', 'enum': [''] + [m['id'] for m in state['catalog']['models']]},
            'planner_reasoning_effort': {'type': 'string', 'title': '规划强度', 'enum': [''] + sorted({e for m in state['catalog']['models'] for e in m['efforts']})},
            'max_planner_turns': {'type': 'string', 'title': '规划总轮数', 'enum': [str(n) for n in range(1, 4)]},
            'max_parallel_workers': {'type': 'string', 'title': '高级：最大并行执行代理数',
                'enum': ['1', '2', '3'], 'description': '默认 1；独立任务可并行，受宿主容量和整个任务总执行次数限制。'},
            'max_worker_turns': {'type': 'string', 'title': '每项任务最多执行轮数',
                'enum': [str(n) for n in range(1, 11)], 'description': '包括首次执行和修正，达到上限停止。'}})
        return {'schema': {'type': 'object', 'properties': properties},
                'values': self.settings_values(selection, state['workflow']),
                'layout': [{'kind': 'group', 'title': 'Codex Duo · 全局默认', 'items': [
                    {'kind': 'property', 'property': r} for r in properties] + [
                    {'kind': 'tool', 'tool': 'fusion.open', 'title': '打开模型面板',
                     'description': '管理全局默认与项目覆盖。'}]}]}

    @staticmethod
    def settings_values(selection, workflow):
        return {**{r: selection[r]['model'] + ' / ' + selection[r]['reasoning_effort'] for r in selection},
                **workflow, 'max_worker_turns': str(workflow['max_worker_turns']),
                'max_parallel_workers': str(workflow['max_parallel_workers']),
                'max_planner_turns': str(workflow.get('max_planner_turns', 1))}

    def settings_update(self, changes):
        with self.defaults_store.global_store.lock:
            catalog = self.catalog_loader()
            saved = self.defaults_store.global_store.read(catalog)
            if saved['error']:
                raise SelectionError('saved_config_invalid', '请先在模型面板恢复配置。', 409)
            selection = saved['document']['selection'] if saved['document'] else default_selection(catalog)
            workflow = saved_workflow(saved['document'])
            for role, pair in changes.items():
                if role in workflow:
                    if role in ('max_worker_turns', 'max_parallel_workers', 'max_planner_turns'):
                        if not isinstance(pair, str) or not pair.isascii() or not pair.isdigit():
                            raise SelectionError('invalid_workflow', '最大并行执行代理数必须为 1 到 3。'
                                if role == 'max_parallel_workers' else '规划轮数必须为 1 到 3。'
                                if role == 'max_planner_turns' else '执行轮数必须为 1 到 10。')
                        pair = int(pair)
                    workflow[role] = pair
                    continue
                if role not in ('coordinator', 'worker') or not isinstance(pair, str) or pair.count(' / ') != 1:
                    raise SelectionError('invalid_selection', '设置必须为有效的模型 / 推理强度组合。')
                model, effort = pair.split(' / ')
                selection[role] = {'model': model, 'reasoning_effort': effort}
            self.defaults_store.global_store.save(selection, catalog, saved['revision'], workflow)
            return {'values': self.settings_values(selection, workflow)}

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
            if not all(p.exists() for p in paths):
                raise ValueError('missing snapshot')
            catalog = self.catalog_loader()
            payload = {k: manifest[k] for k in ('schema_version', 'task', 'selection', 'catalog_fingerprint', 'selection_revision')}
            if 'workflow' in manifest:
                payload['workflow'] = manifest['workflow']
            if digest(payload)[:24] != identifier or manifest.get('handoff_id') != identifier:
                raise ValueError('digest')
            if catalog['fingerprint'] != manifest['catalog_fingerprint']:
                raise SelectionError('catalog_changed', '模型目录已变化，请重新生成交接包。', 409)
            validate_selection(manifest['selection'], catalog)
            # Existing path: verify every immutable artifact, never modify it.
            result = prepare_handoff(manifest['task'], manifest['selection'], catalog, root,
                                     manifest['selection_revision'], manifest.get('workflow'))
            if result['created']:
                raise ValueError('missing snapshot')
        except (OSError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, SelectionError):
                raise
            raise SelectionError('invalid_handoff', '交接包不存在或已损坏。', 409) from exc
        if 'workflow' in manifest:
            workflow = saved_workflow(manifest)
            current = workflow['coordinator_mode'] == 'current_thread'
            return {'schema_version': 1, 'handoff_id': identifier,
                    'state': 'ready_for_native_worker' if current else 'new_coordinator_required',
                    'execution_started': False, 'project_root': str(self.store.directory.parent.resolve()),
                    'coordinator': {'mode': workflow['coordinator_mode'], 'requires_new_task': not current,
                        'selected_model': None if current else manifest['selection']['coordinator']},
                    'worker': {**manifest['worker_spawn_parameters'], 'fork_context': False},
                    'max_worker_turns': workflow['max_worker_turns'],
                    'max_parallel_workers': workflow['max_parallel_workers'],
                    'next_tool': 'fusion.plan', 'task': manifest['task'],
                    'authorization': 'Use the current user task and saved settings; honor all task scope limits.',
                    'verification': 'Use fusion.py verify, then independently review changes and rerun tests.',
                    'adapter': 'The current chat plans bounded workstreams and reserves native dispatches with fusion.reserve.  No model has started. '
                        'Do not claim execution until a native worker receipt exists. '
                        'Never substitute a model or create a new chat without the user requesting one.'}
        return {'schema_version': 1, 'handoff_id': identifier, 'state': 'approval_required',
                'execution_started': False, 'applies_to_current_thread': False,
                'coordinator': {'requires_new_task': True, **manifest['selection']['coordinator']},
                'worker': manifest['worker_spawn_parameters'], 'task': manifest['task'],
                'verification': 'Use fusion.py verify with task.json and worker result; coordinator independently reviews diff and reruns tests.',
                'required_before_execution': ['Explicit user approval for this task and model pair',
                    'Create a new coordinator task with the selected model and effort',
                    'Verify the actual coordinator settings before spawning one worker'],
                'adapter': 'Declarative handoff only; this server implements no model launcher or thread-switch API.'}

    def parallel(self, operation, body):
        self.check_project(body.get('project_root'))
        from fusion_parallel import ParallelExecution
        plan = self.execution_plan(body.get('handoff_id'))
        if plan['state'] != 'ready_for_native_worker':
            raise SelectionError('coordinator_required', '当前交接不能由本聊天派发执行代理。', 409)
        runner = ParallelExecution(self.store, plan)
        return getattr(runner, operation)(body)

    def planning(self, operation, body):
        """Separate plan-only lifecycle; it never enters the execution ledger."""
        self.check_project(body.get('project_root'))
        if operation not in ('begin', 'reserve', 'complete', 'status'):
            raise SelectionError('invalid_arguments', '未知规划操作。')
        from fusion_planner import PlannerExecution
        return getattr(PlannerExecution(self), operation)(body)
