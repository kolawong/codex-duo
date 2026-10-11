"""Shared application service for HTTP, MCP settings and the MCP App."""
import json
from pathlib import Path
from codex_duo_defaults import Defaults
from codex_duo_projects import project_path, opt_in_status, enable_and_save, instructions
from codex_duo_selection import (SelectionError, SelectionStore, read_catalog, default_selection,
                              presets, prepare_handoff, digest, validate_selection, saved_workflow, validate_workflow, validate_task)
from codex_duo_worker import validate_override, worker_summary


class CodexDuoService:
    def __init__(self, directory, catalog_loader=read_catalog):
        from codex_duo_migration import ensure_current_storage
        ensure_current_storage(directory)
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
            return {'configured': False, 'state': 'setup_required', 'setup_tool': 'codex_duo_open',
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
                'planning_tool': 'codex_duo_planner_begin',
                'next_tool': 'codex_duo_begin', 'execution_started': False,
                'instructions': 'Use these saved settings for the authorized task. Do not reopen settings, '
                    'ask for JSON or handoff paths, or request the same approval again. '
                    'Discover a native worker tool before dispatch; this MCP server does not launch models.'}

    def begin(self, body):
        """Resolve current defaults and create the internal task snapshot in one step."""
        self.check_project(body.get('project_root'))
        task = validate_task(body.get('task'))
        override = validate_override(body['worker_override']) if 'worker_override' in body else {}
        invocation = body.get('invocation')
        if invocation not in ('automatic', 'explicit'):
            raise SelectionError('invalid_invocation', '请说明由项目默认流程还是用户明确要求启用。')
        with self.defaults_store.global_store.lock, self.store.lock:
            # Resolve identity before today's defaults: retries keep their immutable
            # choice and budget even after a settings change or service restart.
            existing = self.existing_task(task, override)
            if existing:
                return self.begin_view(existing, False)
            catalog = self.catalog_loader()
            saved, selection, resolution = self.defaults_store.for_task(catalog, override)
            workflow = saved_workflow(saved['document'])
            if invocation == 'automatic' and workflow['activation'] != 'automatic_project':
                raise SelectionError('manual_mode', '当前为手动模式，仅在用户要求使用 Codex Duo 时启用。', 409)
            prepared = prepare_handoff(task, selection, catalog, self.store.directory / 'handoffs',
                                       saved['revision'], workflow, worker_resolution=resolution)
            return self.begin_view(prepared['id'], prepared['created'])

    def begin_view(self, identifier, created):
        path = self.store.directory / 'handoffs' / identifier
        return {**self.execution_plan(identifier), 'handoff_path': str(path), 'created': created,
                'evidence_root': str(self.store.directory / 'runs' / identifier),
                'task_path': str(path / 'task.json')}

    def existing_task(self, task, override):
        """Project lock held. Preserve old records; no new ledger for an existing ID."""
        root = self.store.directory / 'handoffs'
        if root.is_symlink():
            raise SelectionError('unsafe_storage', '交接目录不能是符号链接。', 409)
        matches = []
        for path in sorted(root.glob('*/handoff.json')):
            if path.is_symlink() or path.parent.is_symlink():
                raise SelectionError('unsafe_storage', '交接不能包含符号链接。', 409)
            try:
                manifest = json.loads(path.read_text())
                if manifest['task']['task_id'] != task['task_id']:
                    continue
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise SelectionError('invalid_handoff', '已有交接损坏，无法确认任务身份。', 409) from exc
            identifier = path.parent.name
            self.execution_plan(identifier)  # Verify original snapshot, never repair it.
            if manifest['task'] != task:
                raise SelectionError('task_conflict', '同一 task_id 的任务参数冲突；保留原快照与预算。', 409)
            if 'workflow' not in manifest:
                # Legacy prepare can enter begin only if it has never reserved.
                ledger = self.store.directory / 'runs' / identifier / 'dispatch.json'
                if ledger.exists() or ledger.is_symlink():
                    raise SelectionError('task_conflict', '旧交接已有派发记录，不能新建预算。', 409)
                continue
            if manifest.get('worker_resolution', {}).get('override', {}) != override:
                raise SelectionError('task_conflict', '同一 task_id 的 Worker 覆盖冲突；不能更换模型或重置预算。', 409)
            matches.append(identifier)
        if len(matches) > 1:
            raise SelectionError('task_conflict', '同一 task_id 已有多个历史快照，请保留原记录并核对预算。', 409)
        return matches[0] if matches else None

    def prepare(self, body):
        if 'project_root' in body: self.check_project(body['project_root'])
        with self.defaults_store.global_store.lock, self.store.lock:
            catalog = self.catalog_loader()
            saved = self.defaults_store.resolved(catalog)['effective']
            if not saved['document']:
                raise SelectionError('save_required', '先保存一份有效配置，再生成交接包。', 409)
            if body.get('expected_revision') != saved['revision']:
                raise SelectionError('revision_conflict', '保存版本已变化，请恢复已保存配置后重试。', 409)
            prepared = prepare_handoff(body.get('task'), saved['document']['selection'], catalog,
                                       self.store.directory / 'handoffs', saved['revision'])
            # Compatibility API: do not silently change old snapshot identity or policy.
            return {**prepared, 'state': 'approval_required', 'handoff_kind': 'legacy_declarative',
                    'next_tool': 'codex_duo_execution_plan', 'current_thread_entry_tool': 'codex_duo_begin',
                    'instructions': '这是不含 workflow 的旧式声明交接，不能直接传给 codex_duo_plan/reserve。'
                        '当前聊天执行使用 codex_duo_begin → codex_duo_plan。先检查同一任务的已有派发；'
                        '保留旧交接，不改哈希、不换 task_id 重置预算。'}

    def settings_read(self):
        state = self.state("global")
        if state['catalog'] is None:
            raise SelectionError('catalog_unavailable', state['error']['message'], 503)
        if state['saved']['error']:
            raise SelectionError('saved_config_invalid', '请打开模型面板恢复损坏或过期配置。', 409)
        selection = state['saved']['document']['selection'] if state['saved']['document'] else state['default']
        pairs = [m['id'] + ' / ' + e for m in state['catalog']['models'] for e in m['efforts']]
        workflow = state['workflow']
        planner_enabled = workflow['planner_mode'] == 'plan_only'
        planner_model = next((m for m in state['catalog']['models'] if m['id'] == workflow['planner_model']), None)
        planner_efforts = planner_model['efforts'] if planner_model else sorted({e for m in state['catalog']['models'] for e in m['efforts']})
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
                'description': '首次启用且未选模型时，沿用已保存的指定主控组合，可继续修改。保存不启动模型；计划回当前聊天，不自动执行。'},
            'planner_model': {'type': 'string', 'title': '规划模型', 'enum': ([] if planner_enabled else ['']) + [m['id'] for m in state['catalog']['models']],
                'description': '切换模型时保留受支持的强度，否则采用该模型的默认强度。'},
            'planner_reasoning_effort': {'type': 'string', 'title': '规划强度', 'enum': ([] if planner_enabled else ['']) + planner_efforts},
            'max_planner_turns': {'type': 'string', 'title': '规划总轮数', 'enum': [str(n) for n in range(1, 4)]},
            'max_parallel_workers': {'type': 'string', 'title': '高级：最大并行执行代理数',
                'enum': ['1', '2', '3'], 'description': '默认 1；独立任务可并行，受宿主容量和整个任务总执行次数限制。'},
            'max_worker_turns': {'type': 'string', 'title': '每项任务最多执行轮数',
                'enum': [str(n) for n in range(1, 11)], 'description': '包括首次执行和修正，达到上限停止。'}})
        return {'schema': {'type': 'object', 'properties': properties},
                'values': self.settings_values(selection, state['workflow']),
                'layout': [{'kind': 'group', 'title': 'Codex Duo · 全局默认', 'items': [
                    {'kind': 'property', 'property': r} for r in properties] + [
                    {'kind': 'tool', 'tool': 'codex_duo_open', 'title': '打开模型面板',
                     'description': '管理全局默认与项目覆盖。'}]}]}

    @staticmethod
    def settings_values(selection, workflow):
        return {**{r: selection[r]['model'] + ' / ' + selection[r]['reasoning_effort'] for r in selection},
                **{k: v for k, v in workflow.items() if k != 'completion_mode'}, 'max_worker_turns': str(workflow['max_worker_turns']),
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
            previous_mode = workflow['planner_mode']
            for role, pair in changes.items():
                if role in workflow and role != 'completion_mode':
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
            # Native settings persist one property at a time. Keep the coupled
            # Planner pair valid without weakening enabled-config validation.
            enabling = previous_mode == 'disabled' and changes.get('planner_mode') == 'plan_only'
            initialized = enabling and workflow['planner_model'] == ''
            if initialized:
                workflow['planner_model'] = selection['coordinator']['model']
            planner_model = next((m for m in catalog['models'] if m['id'] == workflow['planner_model']), None)
            if planner_model:
                if enabling and workflow['planner_reasoning_effort'] == '':
                    preferred = selection['coordinator']['reasoning_effort'] if initialized else planner_model['default_effort']
                    workflow['planner_reasoning_effort'] = preferred if preferred in planner_model['efforts'] else planner_model['default_effort']
                elif 'planner_model' in changes and 'planner_reasoning_effort' not in changes and workflow['planner_reasoning_effort'] not in planner_model['efforts']:
                    workflow['planner_reasoning_effort'] = planner_model['default_effort']
            elif changes.get('planner_model') == '' and workflow['planner_mode'] == 'disabled' and 'planner_reasoning_effort' not in changes:
                workflow['planner_reasoning_effort'] = ''
            self.defaults_store.global_store.save(selection, catalog, saved['revision'], workflow)
            return {'values': self.settings_values(selection, workflow)}

    def execution_plan(self, identifier):
        # IDs, never caller-supplied paths. Reject linked or tampered snapshots.
        import re
        if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{24}', identifier):
            raise SelectionError('invalid_handoff', '交接 ID 格式无效。')
        root = self.store.directory / 'handoffs'
        target = root / identifier
        from codex_duo_selection import snapshot_path
        paths = [self.store.directory, root, target, target / 'handoff.json', target / 'task.json',
                 target / 'config', target / 'config/project.toml', snapshot_path(target, 'config/codex_duo_worker.toml'),
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
            if 'worker_resolution' in manifest:
                payload['worker_resolution'] = manifest['worker_resolution']
            if digest(payload)[:24] != identifier or manifest.get('handoff_id') != identifier:
                raise ValueError('digest')
            if catalog['fingerprint'] != manifest['catalog_fingerprint']:
                raise SelectionError('catalog_changed', '模型目录已变化，请重新生成交接包。', 409)
            validate_selection(manifest['selection'], catalog)
            # Existing path: verify every immutable artifact, never modify it.
            result = prepare_handoff(manifest['task'], manifest['selection'], catalog, root,
                                     manifest['selection_revision'], manifest.get('workflow'), legacy_completion=True,
                                     worker_resolution=manifest.get('worker_resolution'))
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
                    'worker': {**manifest['worker_spawn_parameters'], 'fork_context': False, 'agent_type': 'codex_duo_worker'},
                    'worker_resolution': manifest.get('worker_resolution'),
                    'worker_summary': worker_summary(manifest['selection']['worker'], manifest.get('worker_resolution')),
                    'max_worker_turns': workflow['max_worker_turns'],
                    'max_parallel_workers': workflow['max_parallel_workers'],
                    'completion_mode': workflow['completion_mode'],
                    'next_tool': 'codex_duo_plan' if current else None, 'task': manifest['task'],
                    'handoff_kind': 'workflow_snapshot',
                    'authorization': 'Use the current user task and saved settings; honor all task scope limits.',
                    'verification': 'Use codex_duo.py verify, then independently review changes and rerun tests.',
                    'adapter': 'The current chat plans bounded workstreams and reserves native dispatches with codex_duo_reserve.  No model has started. '
                        'Do not claim execution until a native worker receipt exists. '
                        'Never substitute a model or create a new chat without the user requesting one.'}
        return {'schema_version': 1, 'handoff_id': identifier, 'state': 'approval_required',
                'handoff_kind': 'legacy_declarative', 'next_tool': None,
                'current_thread_entry_tool': 'codex_duo_begin',
                'execution_started': False, 'applies_to_current_thread': False,
                'coordinator': {'requires_new_task': True, **manifest['selection']['coordinator']},
                'worker': manifest['worker_spawn_parameters'], 'task': manifest['task'],
                'verification': 'Use codex_duo.py verify with task.json and worker result; coordinator independently reviews diff and reruns tests.',
                'required_before_execution': ['Explicit user approval for this task and model pair',
                    'Create a new coordinator task with the selected model and effort',
                    'Verify the actual coordinator settings before spawning one worker'],
                'adapter': 'Declarative handoff only; this server implements no model launcher or thread-switch API.'}

    def parallel(self, operation, body):
        self.check_project(body.get('project_root'))
        from codex_duo_parallel import ParallelExecution
        plan = self.execution_plan(body.get('handoff_id'))
        if plan['state'] != 'ready_for_native_worker':
            if plan['state'] == 'approval_required':
                message = ('该交接来自旧式 codex_duo_prepare，缺少 workflow（approval_required），'
                    '不能直接用于 codex_duo_plan/reserve。当前聊天执行应使用 codex_duo_begin → codex_duo_plan；'
                    '先确认同一任务没有已有派发，保留旧交接和预算，不修改其哈希或更换 task_id 重置次数。')
            else:
                message = ('该交接快照为 coordinator_mode=selected_model（new_coordinator_required），'
                    '当前线程派发适配器仅支持 current_thread。重复 plan 或请求级参数不会切换主控；'
                    '请按用户明确授权安排受支持的主控流程，保留原快照和已用预算，不擅改用户偏好。')
            raise SelectionError('coordinator_required', message, 409)
        runner = ParallelExecution(self.store, plan)
        return getattr(runner, operation)(body)

    def planning(self, operation, body):
        """Separate plan-only lifecycle; it never enters the execution ledger."""
        self.check_project(body.get('project_root'))
        if operation not in ('begin', 'reserve', 'complete', 'status', 'run', 'stop'):
            raise SelectionError('invalid_arguments', '未知规划操作。')
        from codex_duo_planner import PlannerExecution
        if operation in ('run', 'stop'):
            from codex_duo_planner_session import SessionPlanner
            return getattr(SessionPlanner(self), operation)(body)
        return getattr(PlannerExecution(self), operation)(body)
