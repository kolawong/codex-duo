#!/usr/bin/env python3
"""Local saved-default workflow adapter; never launches a model or task command."""
import argparse
import json
from pathlib import Path
from fusion_service import FusionService
from fusion_projects import project_path
from fusion_selection import SelectionError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('defaults', 'begin'):
        sub = commands.add_parser(command)
        sub.add_argument('--project-root', type=Path, required=True)
        if command == 'begin':
            sub.add_argument('--task', type=Path, required=True)
            sub.add_argument('--invocation', choices=['automatic', 'explicit'], required=True)
    for command in ('plan', 'reserve', 'complete', 'verify'):
        sub = commands.add_parser(command)
        sub.add_argument('--project-root', type=Path, required=True)
        sub.add_argument('--handoff-id', required=True)
        if command in ('plan', 'reserve'): sub.add_argument('--host-capacity', type=int, required=True)
        if command == 'plan': sub.add_argument('--workstreams', type=Path)
        if command == 'reserve': sub.add_argument('--workstream-id', required=True)
        if command == 'complete':
            sub.add_argument('--dispatch-id', required=True)
            sub.add_argument('--native-receipt', required=True)
            sub.add_argument('--outcome', choices=['completed', 'failed', 'blocked'], required=True)
    args = parser.parse_args()
    try:
        args.project_root = project_path(args.project_root)
        service = FusionService(args.project_root / '.fusion')
        if args.command == 'defaults':
            result = service.defaults(str(args.project_root))
        elif args.command == 'begin':
            result = service.begin({'project_root': str(args.project_root),
                'task': json.loads(args.task.read_text()), 'invocation': args.invocation})
        else:
            body = {key: value for key, value in vars(args).items() if key != 'command' and value is not None}
            body['project_root'] = str(args.project_root)
            if body.get('workstreams'): body['workstreams'] = json.loads(body['workstreams'].read_text())
            result = service.parallel(args.command, body)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (SelectionError, OSError, ValueError) as exc:
        print(json.dumps({'state': 'blocked', 'execution_started': False,
                          'error': {'code': getattr(exc, 'code', 'local_error'), 'message': str(exc)}}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
