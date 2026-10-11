#!/usr/bin/env python3
"""One-shot JSON bridge to the shared service; never launches a Codex Duo worker."""
import argparse
import json
from pathlib import Path
import sys


def service_scripts():
    # Only app-owned resources or this bridge's source checkout, never project-root.
    here = Path(__file__).resolve()
    bundled = here.parent / 'workflow' / 'scripts'
    if (bundled / 'codex_duo_service.py').is_file():
        return bundled
    if here.parts[-5:] == ('macos', 'Sources', 'CodexDuoMenu', 'Resources', 'bridge.py'):
        development = here.parents[4] / 'plugins/codex-duo/skills/workflow/scripts'
        if (development / 'codex_duo_service.py').is_file():
            return development
    raise RuntimeError('应用内缺少 Codex Duo 服务资源，请重新构建。')


def project_path(value):
    sys.path.insert(0, str(service_scripts()))
    from codex_duo_projects import project_path as validate_project
    return validate_project(value)


def dispatch(request, project, service_factory=None):
    if not isinstance(request, dict) or request.get('operation') not in ('state', 'save', 'reset'):
        raise ValueError('请求必须包含 state 或 save 操作。')
    if service_factory is None:
        sys.path.insert(0, str(service_scripts()))
        from codex_duo_service import CodexDuoService
        service_factory = CodexDuoService
    service = service_factory(project / '.codex-duo')
    if request['operation'] == 'state':
        return service.state(request.get("scope", "project"))
    body = request.get('body')
    if not isinstance(body, dict) or not isinstance(body.get('expected_revision'), str):
        raise ValueError('保存请求必须包含配置和读取时的版本。')
    if request['operation'] == 'reset':
        return service.reset({**body, 'project_root': str(project)})
    return service.save(body)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', required=True)
    args = parser.parse_args(argv)
    try:
        project = project_path(args.project_root)
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('请求超过大小限制。')
        request = json.loads(raw)
        response = {'ok': True, 'data': dispatch(request, project)}
    except Exception as exc:
        code = getattr(exc, 'code', None)
        if code is None:
            code = 'invalid_request' if isinstance(exc, (ValueError, TypeError)) else 'bridge_unavailable'
        response = {'ok': False, 'error': {'code': code, 'message': str(exc)}}
    print(json.dumps(response, ensure_ascii=False, separators=(',', ':')))
    return 0 if response['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
