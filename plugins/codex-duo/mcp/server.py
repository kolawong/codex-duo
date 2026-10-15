#!/usr/bin/env python3
"""Local stdio MCP. Only explicit planner_run can launch a restricted model session."""
import argparse
import json
import os
from pathlib import Path
import sys
import base64

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'skills/workflow/scripts'))
from codex_duo_service import CodexDuoService
from codex_duo_selection import SelectionError
from codex_duo_projects import project_path
from codex_duo_selection import ASSESSMENT_SCHEMA

VERSION = '0.11.0'
RESOURCE = 'ui://codex-duo/model-desk-v4'
MIME = 'text/html;profile=mcp-app'
EMPTY = {'type': 'object', 'properties': {}, 'additionalProperties': False}
PAIR = {'type': 'object', 'properties': {'model': {'type': 'string'},
        'reasoning_effort': {'type': 'string'}}, 'required': ['model', 'reasoning_effort'], 'additionalProperties': False}
WORKER_OVERRIDE = {**PAIR, 'required': [], 'minProperties': 1}
NATIVE_DISPATCH = {'type': 'object', 'properties': {
    'tool': {'type': 'string'}, 'agent_id': {'type': 'string'},
    'parameters': {'type': 'object', 'properties': {**PAIR['properties'],
        'agent_type': {'type': 'string', 'enum': ['codex_duo_worker']},
        'fork_turns': {'type': 'string', 'enum': ['none']}},
        'required': ['model', 'reasoning_effort', 'agent_type', 'fork_turns'], 'additionalProperties': False},
    'runtime': {**PAIR, 'required': []}},
    'required': ['tool', 'agent_id', 'parameters'], 'additionalProperties': False}
SELECTION = {'type': 'object', 'properties': {r: PAIR for r in ('coordinator', 'worker')},
             'required': ['coordinator', 'worker'], 'additionalProperties': False}
WORKFLOW = {'type': 'object', 'properties': {
    'activation': {'type': 'string', 'enum': ['automatic_project', 'manual']},
    'agent_activity': {'type': 'string', 'enum': ['conservative', 'balanced', 'aggressive']},
    'coordinator_mode': {'type': 'string', 'enum': ['current_thread', 'selected_model']},
    'max_worker_turns': {'type': 'integer', 'minimum': 1, 'maximum': 10},
    'max_parallel_workers': {'type': 'integer', 'minimum': 1, 'maximum': 3},
    'planner_mode': {'type': 'string', 'enum': ['disabled', 'plan_only']},
    'planner_model': {'type': 'string'}, 'planner_reasoning_effort': {'type': 'string'},
    'max_planner_turns': {'type': 'integer', 'minimum': 1, 'maximum': 3}},
    'required': ['activation', 'coordinator_mode', 'max_worker_turns'], 'additionalProperties': False}


def object_schema(properties, required=None):
    return {'type': 'object', 'properties': properties, 'required': list(properties) if required is None else required,
            'additionalProperties': False}


def tool(name, title, schema, readonly=True, model=False, **extra):
    return {'name': name, 'title': title, 'description': title + '。仅访问 Codex Duo 全局默认、项目设置和交接，不调用模型。',
            'inputSchema': json.loads(json.dumps(schema)), 'annotations': {'readOnlyHint': readonly, 'destructiveHint': False,
            'idempotentHint': True, 'openWorldHint': False},
            '_meta': {'ui': {'visibility': ['app', 'model'] if model else ['app']}}, **extra}


def tool_definitions():
    opening = tool('codex_duo_open', 'Codex Duo 全局默认与项目覆盖', EMPTY, model=True)
    opening['_meta']['ui']['resourceUri'] = RESOURCE
    opening['_meta']['openai/ui'] = {'entrypoints': [{'type': 'thread'}]}
    opening['icons'] = [{'src': 'data:image/png;base64,' +
        base64.b64encode((PLUGIN / 'assets/tandem.png').read_bytes()).decode(), 'mimeType': 'image/png'}]
    definitions = [opening, tool('codex_duo_reset', '清除项目覆盖并继承全局默认', object_schema({'project_root': {'type': 'string'}, 'expected_revision': {'type': 'string'}, 'expected_global_revision': {'type': 'string'}}), readonly=False), tool('codex_duo_state', '读取模型面板状态', EMPTY),
        tool('codex_duo_save', '保存默认配置，持续使用到主动更新', object_schema({'selection': SELECTION,
             'workflow': WORKFLOW, 'expected_revision': {'type': 'string'}},
             ['selection', 'expected_revision']), readonly=False),
        tool('codex_duo_defaults', '读取本项目已保存默认配置，无需打开面板或重新选择',
             object_schema({'project_root': {'type': 'string'}}), model=True),
        tool('codex_duo_begin', '按已保存配置准备当前任务，由当前聊天调度原生执行代理',
             object_schema({'project_root': {'type': 'string'}, 'task': {'type': 'object'},
                 'invocation': {'type': 'string', 'enum': ['automatic', 'explicit']},
                 'assessment': ASSESSMENT_SCHEMA,
                 'worker_override': WORKER_OVERRIDE}, ['project_root', 'task', 'invocation']), readonly=False, model=True),
        tool('codex_duo_prepare', '兼容旧式声明交接；当前聊天执行请用 codex_duo_begin', object_schema({'task': {'type': 'object'},
             'expected_revision': {'type': 'string'}}), readonly=False, model=True),
        tool('codex_duo_execution_plan', '只读检查交接状态与派发资格，不建立子任务计划', object_schema({'handoff_id': {'type': 'string',
             'pattern': '^[a-f0-9]{24}$'}}), model=True),
        tool('codex_duo_settings_read', '读取 Codex Duo 原生设置', EMPTY,
             outputSchema={'type': 'object', 'properties': {'schema': {'type': 'object'},
                 'values': {'type': 'object'}, 'layout': {'type': 'array', 'items': {'type': 'object'}}},
                 'required': ['schema', 'values']}),
        tool('codex_duo_settings_update', '更新 Codex Duo 原生设置', object_schema({'set': {
             'type': 'object', 'properties': {key: {'type': 'string'} for key in
                 ('coordinator', 'worker', 'activation', 'agent_activity', 'worker_strategy',
                  'worker_profile_light', 'worker_profile_standard', 'worker_profile_complex',
                  'coordinator_mode', 'max_worker_turns', 'max_parallel_workers', 'planner_mode', 'planner_model', 'planner_reasoning_effort', 'max_planner_turns')},
             'minProperties': 1, 'additionalProperties': False}}), readonly=False,
             outputSchema={'type': 'object', 'properties': {'values': {'type': 'object'}}, 'required': ['values']})]
    for operation, properties, required in [
        ('plan', {'host_capacity': {'type': 'integer', 'minimum': 1}, 'workstreams': {'type': 'array', 'items': {'type': 'object'}}}, ['handoff_id', 'host_capacity']),
        ('reserve', {'host_capacity': {'type': 'integer', 'minimum': 1}, 'workstream_id': {'type': 'string'}}, ['handoff_id', 'host_capacity', 'workstream_id']),
        ('complete', {'dispatch_id': {'type': 'string'}, 'native_receipt': {'type': 'string'}, 'native_dispatch': NATIVE_DISPATCH,
                      'outcome': {'type': 'string', 'enum': ['completed', 'failed', 'blocked', 'cancelled']}}, ['handoff_id', 'dispatch_id', 'native_receipt', 'outcome']),
        ('verify', {}, ['handoff_id'])]:
        definitions.append(tool('codex_duo_' + operation, '原生执行子任务：' + operation,
            object_schema({'handoff_id': {'type': 'string', 'pattern': '^[a-f0-9]{24}$'}, **properties}, required + ['project_root']),
            readonly=operation == 'verify', model=True))
    capabilities = object_schema({key: {'type': 'string'} for key in (
        'tool', 'model', 'reasoning_effort', 'filesystem', 'network', 'process_execution',
        'writes', 'agent_spawn', 'enforcement', 'approval_escalation', 'external_tools')})
    for operation, properties, required in [
        ('begin', {'request': {'type': 'object'}, 'invocation': {'type': 'string', 'enum': ['explicit']},
                   'planner': object_schema({'model': {'type': 'string'}, 'reasoning_effort': {'type': 'string'},
                       'max_turns': {'type': 'integer', 'minimum': 1, 'maximum': 3}})}, ['request', 'invocation']),
        ('reserve', {'host_capabilities': capabilities}, ['plan_id', 'host_capabilities']),
        ('complete', {'dispatch_id': {'type': 'string'}, 'native_receipt': {'type': 'string'},
                      'outcome': {'type': 'string', 'enum': ['completed', 'failed', 'blocked', 'cancelled']},
                      'result': {'type': 'object'}}, ['plan_id', 'dispatch_id', 'native_receipt', 'outcome']),
        ('status', {}, ['plan_id']),
        ('run', {'attempt_id': {'type': 'string'}, 'invocation': {'type': 'string', 'enum': ['explicit']}}, ['plan_id', 'attempt_id', 'invocation']),
        ('stop', {}, ['plan_id'])]:
        properties = {'project_root': {'type': 'string'}, **properties}
        if operation != 'begin': properties['plan_id'] = {'type': 'string', 'pattern': '^[a-f0-9]{24}$'}
        definitions.append(tool('codex_duo_planner_' + operation, '独立仅规划：' + operation,
            object_schema(properties, ['project_root'] + required), readonly=operation == 'status', model=True))
        if operation == 'run':
            definitions[-1]['description'] = '明确请求后启动一个官方独立只读规划模型会话，会产生模型调用费用；不运行 Worker、不执行计划。相同 attempt_id 只返回已有状态，绝不自动重试。'
            definitions[-1]['annotations']['openWorldHint'] = True
    for definition in definitions:
        if definition['name'] == 'codex_duo_begin':
            definition['description'] = '当前聊天执行入口：自动派发须先由当前聊天判断必要性并提供 assessment（complexity/benefit/independent/reason），按已保存的代理积极程度决定是否委派。简单或不值得交接的任务返回 current_thread，无交接和派发预算；仅 ready_for_native_worker 继续 plan → reserve → 原生派发 → complete → verify。invocation=explicit 仅用于用户本次明确要求派代理，优先于积极程度。可选 worker_override={model?,reasoning_effort?} 仅覆盖本任务；保存不可变判断与模型来源，重复 task_id 冲突拒绝。不改偏好、不启动分类器/Planner/Worker。'
        elif definition['name'] == 'codex_duo_prepare':
            definition['description'] = '旧式兼容入口：生成不含 workflow 的声明交接，状态 approval_required，不能直接用于 codex_duo_plan/reserve。当前聊天任务应调用 codex_duo_begin；不得通过替换旧交接或 task_id 重置已有预算。此工具不调用模型。'
        elif definition['name'] == 'codex_duo_execution_plan':
            definition['description'] = '只读校验已有交接并报告状态、模型和派发资格；不建立 workstreams，不启动模型，也不切换当前聊天。它不同于 codex_duo_plan；只在 ready_for_native_worker 时才继续 plan。'
        elif definition['name'] == 'codex_duo_plan':
            definition['description'] = '为 ready_for_native_worker 交接固定独立子任务和容量计划，不调用模型。workstreams 每项为 {id,task,depends_on}；自动分级且无本次覆盖时必须额外提供 routing={tier:light|standard|complex,reason:string}，从快照候选解析各自模型/强度；固定模式或本次覆盖不传 routing。明确所有权不重叠，依赖验证后才派发。返回保存上限、主控报告宿主容量、占用与等待原因；多任务可受容量限制顺序执行，不为凑数拆分。共享父任务预算，不自动升级。旧式 prepare 或 selected_model 交接拒绝。'
        if definition['name'] in ('codex_duo_reserve', 'codex_duo_planner_reserve', 'codex_duo_planner_begin'):
            definition['annotations']['idempotentHint'] = False
    # Each call is scoped independently. Omitted root remains a legacy fixed-root fallback.
    for definition in definitions:
        schema = definition['inputSchema']
        schema['properties'] = {**schema.get('properties', {}), 'project_root': {'type': 'string'}}
        if definition['name'] in ('codex_duo_open', 'codex_duo_state', 'codex_duo_save'):
            schema['properties']['scope'] = {'type': 'string', 'enum': ['global', 'project']}
        if definition['name'] == 'codex_duo_save':
            schema['properties']['enable_project'] = {'type': 'boolean'}
            schema['properties']['expected_global_revision'] = {'type': 'string'}
    return definitions



def validate(value, schema):
    """Validate the small, explicitly used input-schema subset before dispatch."""
    import re
    kind = schema.get('type')
    if kind == 'string' and not isinstance(value, str):
        raise SelectionError('invalid_arguments', '参数必须为字符串。')
    if kind == 'boolean' and type(value) is not bool:
        raise SelectionError('invalid_arguments', '参数必须为布尔值。')
    if kind == 'integer' and (type(value) is not int or value < schema.get('minimum', value)
                              or value > schema.get('maximum', value)):
        raise SelectionError('invalid_arguments', '整数参数超出允许范围。')
    if 'enum' in schema and value not in schema['enum']:
        raise SelectionError('invalid_arguments', '参数不在允许的选项中。')
    if kind == 'object':
        if not isinstance(value, dict):
            raise SelectionError('invalid_arguments', '参数必须为对象。')
        properties = schema.get('properties', {})
        if any(k not in value for k in schema.get('required', [])) or len(value) < schema.get('minProperties', 0):
            raise SelectionError('invalid_arguments', '缺少必要参数。')
        if schema.get('additionalProperties') is False and set(value) - set(properties):
            raise SelectionError('invalid_arguments', '包含未支持的参数。')
        for key in value.keys() & properties.keys():
            validate(value[key], properties[key])
    if kind == 'array':
        if not isinstance(value, list):
            raise SelectionError('invalid_arguments', '参数必须为数组。')
        for item in value: validate(item, schema.get('items', {}))
    if 'pattern' in schema and not re.fullmatch(schema['pattern'], value):
        raise SelectionError('invalid_arguments', '参数格式无效。')


def result(data, compact=False):
    if compact:
        return {'content': [{'type': 'text', 'text': 'Codex Duo 项目设置已准备。与菜单栏共享配置；未启动模型。'}],
                'structuredContent': {'state': 'ready', 'execution_started': False},
                '_meta': {'codex-duo/state': data}}
    return {'content': [{'type': 'text', 'text': json.dumps(data, ensure_ascii=False)}], 'structuredContent': data}


class MCPServer:
    def __init__(self, service):
        self.service = service

    def call(self, name, arguments):
        definitions = {t['name']: t for t in tool_definitions()}
        if name not in definitions:
            raise SelectionError('unknown_tool', '工具不存在。')
        validate(arguments, definitions[name]['inputSchema'])
        root = project_path(arguments.get('project_root', self.service.store.directory.parent))
        service = CodexDuoService(root / '.codex-duo', self.service.catalog_loader)
        scoped = {**arguments, 'project_root': str(root)}
        if name in ('codex_duo_open', 'codex_duo_state'):
            return result(service.state(arguments.get('scope', 'global' if name == 'codex_duo_open' else 'project')), compact=name == 'codex_duo_open')
        if name == 'codex_duo_reset':
            return result(service.reset(scoped))
        if name == 'codex_duo_save':
            return result(service.save(scoped))
        if name == 'codex_duo_defaults':
            return result(service.defaults(str(root)))
        if name == 'codex_duo_begin':
            return result(service.begin(scoped))
        if name == 'codex_duo_prepare':
            return result(service.prepare(scoped))
        if name == 'codex_duo_execution_plan':
            return result(service.execution_plan(arguments['handoff_id']))
        if name in ('codex_duo_plan', 'codex_duo_reserve', 'codex_duo_complete', 'codex_duo_verify'):
            return result(service.parallel(name.removeprefix('codex_duo_'), scoped))
        if name.startswith('codex_duo_planner_'):
            return result(service.planning(name.split('planner_')[1], scoped))
        if name == 'codex_duo_settings_read':
            return result(service.settings_read())
        return result(service.settings_update(arguments['set']))

    def dispatch(self, message):
        rid = message.get('id') if isinstance(message, dict) else None
        def error(code, msg):
            return {'jsonrpc': '2.0', 'id': rid, 'error': {'code': code, 'message': msg}}
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
            return error(-32600, 'Invalid Request')
        if 'id' not in message:
            return None  # Notifications never receive a response.
        if isinstance(rid, bool) or not isinstance(rid, (str, int)):
            return error(-32600, 'Invalid request ID')
        method, params = message['method'], message.get('params', {})
        if not isinstance(params, dict):
            return error(-32602, 'Invalid params')
        try:
            if method == 'initialize':
                data = {'protocolVersion': '2025-11-25', 'serverInfo': {'name': 'codex-duo', 'title': 'Codex Duo', 'version': VERSION},
                    'capabilities': {'tools': {}, 'resources': {}, 'experimental': {'openai/settings': {
                        'readTool': 'codex_duo_settings_read', 'updateTool': 'codex_duo_settings_update'}}}}
            elif method == 'ping':
                data = {}
            elif method == 'tools/list':
                data = {'tools': tool_definitions()}
            elif method == 'resources/list':
                data = {'resources': [{'uri': RESOURCE, 'name': 'Codex Duo settings', 'mimeType': MIME}]}
            elif method == 'resources/templates/list':
                data = {'resourceTemplates': []}
            elif method == 'resources/read':
                if params.get('uri') != RESOURCE:
                    return error(-32002, 'Unknown resource')
                data = {'contents': [{'uri': RESOURCE, 'mimeType': MIME,
                    'text': (PLUGIN / 'ui/model-desk.html').read_text(), '_meta': {
                        'ui': {'csp': {'connectDomains': [], 'resourceDomains': [], 'frameDomains': [], 'baseUriDomains': []}},
                        'openai/ui': {'availableDisplayModes': ['fullscreen'], 'preferredDisplayMode': 'fullscreen'}}}]}
            elif method == 'tools/call':
                if set(params) - {'name', 'arguments', '_meta'} or not isinstance(params.get('name'), str):
                    return error(-32602, 'Invalid tool call')
                try:
                    data = self.call(params['name'], params.get('arguments', {}))
                except SelectionError as exc:
                    data = {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}],
                            'structuredContent': {'error': {'code': exc.code, 'message': str(exc)}}}
                except OSError:
                    data = {'isError': True, 'content': [{'type': 'text', 'text': '项目存储不可用，请检查权限或磁盘空间。'}],
                            'structuredContent': {'error': {'code': 'storage_unavailable', 'message': '项目存储不可用。'}}}
            else:
                return error(-32601, 'Method not found')
            return {'jsonrpc': '2.0', 'id': rid, 'result': data}
        except (OSError, ValueError, TypeError):
            return error(-32603, 'Local service unavailable')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        parser.error('project-root must be an existing absolute non-symlink directory')
    # Deployment chooses the omitted-root legacy fallback only; no global selected project.
    server = MCPServer(CodexDuoService(root / '.codex-duo'))
    while True:
        line = sys.stdin.buffer.readline(65537)
        if not line:
            break
        if len(line) > 65536:
            while line and not line.endswith(b'\n'):
                line = sys.stdin.buffer.readline(65537)
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Request exceeds 64 KiB'}}
        else:
            try:
                message = json.loads(line)
                response = server.dispatch(message)
            except (ValueError, UnicodeError):
                response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
