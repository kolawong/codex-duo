#!/usr/bin/env python3
"""Local stdio MCP 2025-11-25; no sockets, sampling, or model execution."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'skills/fusion/scripts'))
from fusion_service import FusionService
from fusion_selection import SelectionError
from fusion_projects import project_path

VERSION = '0.7.0'
RESOURCE = 'ui://fusion-minimal/model-desk-v4'
MIME = 'text/html;profile=mcp-app'
EMPTY = {'type': 'object', 'properties': {}, 'additionalProperties': False}
PAIR = {'type': 'object', 'properties': {'model': {'type': 'string'},
        'reasoning_effort': {'type': 'string'}}, 'required': ['model', 'reasoning_effort'], 'additionalProperties': False}
SELECTION = {'type': 'object', 'properties': {r: PAIR for r in ('coordinator', 'worker')},
             'required': ['coordinator', 'worker'], 'additionalProperties': False}
WORKFLOW = {'type': 'object', 'properties': {
    'activation': {'type': 'string', 'enum': ['automatic_project', 'manual']},
    'coordinator_mode': {'type': 'string', 'enum': ['current_thread', 'selected_model']},
    'max_worker_turns': {'type': 'integer', 'minimum': 1, 'maximum': 10},
    'max_parallel_workers': {'type': 'integer', 'minimum': 1, 'maximum': 3}},
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
    opening = tool('fusion.open', 'Codex Duo 全局默认与项目覆盖', EMPTY, model=True)
    opening['_meta']['ui']['resourceUri'] = RESOURCE
    opening['_meta']['openai/ui'] = {'entrypoints': [{'type': 'thread'}]}
    opening['icons'] = [{'src': 'data:image/svg+xml,' +
        quote((PLUGIN / 'assets/tandem.svg').read_text(encoding='utf-8'), safe=''), 'mimeType': 'image/svg+xml'}]
    definitions = [opening, tool('fusion.reset', '清除项目覆盖并继承全局默认', object_schema({'project_root': {'type': 'string'}, 'expected_revision': {'type': 'string'}, 'expected_global_revision': {'type': 'string'}}), readonly=False), tool('fusion.state', '读取模型面板状态', EMPTY),
        tool('fusion.save', '保存默认配置，持续使用到主动更新', object_schema({'selection': SELECTION,
             'workflow': WORKFLOW, 'expected_revision': {'type': 'string'}},
             ['selection', 'expected_revision']), readonly=False),
        tool('fusion.defaults', '读取本项目已保存默认配置，无需打开面板或重新选择',
             object_schema({'project_root': {'type': 'string'}}), model=True),
        tool('fusion.begin', '按已保存配置准备当前任务，由当前聊天调度原生执行代理',
             object_schema({'project_root': {'type': 'string'}, 'task': {'type': 'object'},
                 'invocation': {'type': 'string', 'enum': ['automatic', 'explicit']}}), readonly=False, model=True),
        tool('fusion.prepare', '生成未启动的任务交接包', object_schema({'task': {'type': 'object'},
             'expected_revision': {'type': 'string'}}), readonly=False, model=True),
        tool('fusion.execution_plan', '读取交接执行适配说明', object_schema({'handoff_id': {'type': 'string',
             'pattern': '^[a-f0-9]{24}$'}}), model=True),
        tool('fusion.settings_read', '读取 Codex Duo 原生设置', EMPTY,
             outputSchema={'type': 'object', 'properties': {'schema': {'type': 'object'},
                 'values': {'type': 'object'}, 'layout': {'type': 'array', 'items': {'type': 'object'}}},
                 'required': ['schema', 'values']}),
        tool('fusion.settings_update', '更新 Codex Duo 原生设置', object_schema({'set': {
             'type': 'object', 'properties': {key: {'type': 'string'} for key in
                 ('coordinator', 'worker', 'activation', 'coordinator_mode', 'max_worker_turns', 'max_parallel_workers')},
             'minProperties': 1, 'additionalProperties': False}}), readonly=False,
             outputSchema={'type': 'object', 'properties': {'values': {'type': 'object'}}, 'required': ['values']})]
    for operation, properties, required in [
        ('plan', {'host_capacity': {'type': 'integer', 'minimum': 1}, 'workstreams': {'type': 'array', 'items': {'type': 'object'}}}, ['handoff_id', 'host_capacity']),
        ('reserve', {'host_capacity': {'type': 'integer', 'minimum': 1}, 'workstream_id': {'type': 'string'}}, ['handoff_id', 'host_capacity', 'workstream_id']),
        ('complete', {'dispatch_id': {'type': 'string'}, 'native_receipt': {'type': 'string'}, 'outcome': {'type': 'string', 'enum': ['completed', 'failed', 'blocked']}}, ['handoff_id', 'dispatch_id', 'native_receipt', 'outcome']),
        ('verify', {}, ['handoff_id'])]:
        definitions.append(tool('fusion.' + operation, '原生执行子任务：' + operation,
            object_schema({'handoff_id': {'type': 'string', 'pattern': '^[a-f0-9]{24}$'}, **properties}, required + ['project_root']),
            readonly=operation == 'verify', model=True))
    for definition in definitions:
        if definition['name'] == 'fusion.reserve':
            definition['annotations']['idempotentHint'] = False
    # Each call is scoped independently. Omitted root remains a legacy fixed-root fallback.
    for definition in definitions:
        schema = definition['inputSchema']
        schema['properties'] = {**schema.get('properties', {}), 'project_root': {'type': 'string'}}
        if definition['name'] in ('fusion.open', 'fusion.state', 'fusion.save'):
            schema['properties']['scope'] = {'type': 'string', 'enum': ['global', 'project']}
        if definition['name'] == 'fusion.save':
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
                '_meta': {'fusion/state': data}}
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
        service = FusionService(root / '.fusion', self.service.catalog_loader)
        scoped = {**arguments, 'project_root': str(root)}
        if name in ('fusion.open', 'fusion.state'):
            return result(service.state(arguments.get('scope', 'global' if name == 'fusion.open' else 'project')), compact=name == 'fusion.open')
        if name == 'fusion.reset':
            return result(service.reset(scoped))
        if name == 'fusion.save':
            return result(service.save(scoped))
        if name == 'fusion.defaults':
            return result(service.defaults(str(root)))
        if name == 'fusion.begin':
            return result(service.begin(scoped))
        if name == 'fusion.prepare':
            return result(service.prepare(scoped))
        if name == 'fusion.execution_plan':
            return result(service.execution_plan(arguments['handoff_id']))
        if name in ('fusion.plan', 'fusion.reserve', 'fusion.complete', 'fusion.verify'):
            return result(service.parallel(name.split('.')[1], scoped))
        if name == 'fusion.settings_read':
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
                        'readTool': 'fusion.settings_read', 'updateTool': 'fusion.settings_update'}}}}
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
    server = MCPServer(FusionService(root / '.fusion'))
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
