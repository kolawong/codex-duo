#!/usr/bin/env python3
"""Local stdio MCP 2025-11-25; no sockets, sampling, execution, or global writes."""
import argparse
import json
import os
from pathlib import Path
import sys

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'skills/fusion/scripts'))
from fusion_service import FusionService
from fusion_selection import SelectionError

VERSION = '0.3.2'
RESOURCE = 'ui://fusion-minimal/model-desk-v3'
MIME = 'text/html;profile=mcp-app'
EMPTY = {'type': 'object', 'properties': {}, 'additionalProperties': False}
PAIR = {'type': 'object', 'properties': {'model': {'type': 'string'},
        'reasoning_effort': {'type': 'string'}}, 'required': ['model', 'reasoning_effort'], 'additionalProperties': False}
SELECTION = {'type': 'object', 'properties': {r: PAIR for r in ('coordinator', 'worker')},
             'required': ['coordinator', 'worker'], 'additionalProperties': False}


def object_schema(properties, required=None):
    return {'type': 'object', 'properties': properties, 'required': list(properties) if required is None else required,
            'additionalProperties': False}


def tool(name, title, schema, readonly=True, model=False, **extra):
    return {'name': name, 'title': title, 'description': title + '。仅访问 Fusion 项目配置和交接，不调用模型。',
            'inputSchema': schema, 'annotations': {'readOnlyHint': readonly, 'destructiveHint': False,
            'idempotentHint': True, 'openWorldHint': False},
            '_meta': {'ui': {'visibility': ['app', 'model'] if model else ['app']}}, **extra}


def tool_definitions():
    opening = tool('fusion.open', 'Fusion 模型工作台', EMPTY, model=True)
    opening['_meta']['ui']['resourceUri'] = RESOURCE
    opening['_meta']['openai/ui'] = {'entrypoints': [{'type': 'thread'}]}
    opening['icons'] = [{'src': 'data:image/svg+xml,' +
        '%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 20 20%22 fill=%22none%22%3E%3Cpath d=%22M5 16V4h10M5 10h8%22 stroke=%22currentColor%22 stroke-width=%221.33%22/%3E%3C/svg%3E', 'mimeType': 'image/svg+xml'}]
    return [opening, tool('fusion.state', '读取模型面板状态', EMPTY),
        tool('fusion.save', '保存未来任务模型组合', object_schema({'selection': SELECTION,
             'expected_revision': {'type': 'string'}}), readonly=False),
        tool('fusion.prepare', '生成未启动的任务交接包', object_schema({'task': {'type': 'object'},
             'expected_revision': {'type': 'string'}}), readonly=False, model=True),
        tool('fusion.execution_plan', '读取交接执行适配说明', object_schema({'handoff_id': {'type': 'string',
             'pattern': '^[a-f0-9]{24}$'}}), model=True),
        tool('fusion.settings_read', '读取 Fusion 原生设置', EMPTY,
             outputSchema={'type': 'object', 'properties': {'schema': {'type': 'object'},
                 'values': {'type': 'object'}, 'layout': {'type': 'array', 'items': {'type': 'object'}}},
                 'required': ['schema', 'values']}),
        tool('fusion.settings_update', '更新 Fusion 原生设置', object_schema({'set': {
             'type': 'object', 'properties': {'coordinator': {'type': 'string'}, 'worker': {'type': 'string'}},
             'minProperties': 1, 'additionalProperties': False}}), readonly=False,
             outputSchema={'type': 'object', 'properties': {'values': {'type': 'object'}}, 'required': ['values']})]


def validate(value, schema):
    """Validate the small, explicitly used input-schema subset before dispatch."""
    import re
    kind = schema.get('type')
    if kind == 'string' and not isinstance(value, str):
        raise SelectionError('invalid_arguments', '参数必须为字符串。')
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
    if 'pattern' in schema and not re.fullmatch(schema['pattern'], value):
        raise SelectionError('invalid_arguments', '参数格式无效。')


def result(data, compact=False):
    if compact:
        return {'content': [{'type': 'text', 'text': 'Fusion 模型面板已准备。仅配置后续任务；未启动模型。'}],
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
        if name in ('fusion.open', 'fusion.state'):
            return result(self.service.state(), compact=name == 'fusion.open')
        if name == 'fusion.save':
            return result(self.service.save(arguments))
        if name == 'fusion.prepare':
            return result(self.service.prepare(arguments))
        if name == 'fusion.execution_plan':
            return result(self.service.execution_plan(arguments['handoff_id']))
        if name == 'fusion.settings_read':
            return result(self.service.settings_read())
        return result(self.service.settings_update(arguments['set']))

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
                data = {'protocolVersion': '2025-11-25', 'serverInfo': {'name': 'fusion-minimal', 'version': VERSION},
                    'capabilities': {'tools': {}, 'resources': {}, 'experimental': {'openai/settings': {
                        'readTool': 'fusion.settings_read', 'updateTool': 'fusion.settings_update'}}}}
            elif method == 'ping':
                data = {}
            elif method == 'tools/list':
                data = {'tools': tool_definitions()}
            elif method == 'resources/list':
                data = {'resources': [{'uri': RESOURCE, 'name': 'Fusion model desk', 'mimeType': MIME}]}
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
    # Deployment chooses this root. MCP/UI arguments cannot change it.
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
