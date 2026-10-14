#!/usr/bin/env python3
"""Local workflow adapter; explicit planner_run alone launches a restricted Planner."""
import argparse
import json
from pathlib import Path
from codex_duo_service import CodexDuoService
from codex_duo_projects import project_path
from codex_duo_selection import SelectionError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('defaults', 'begin', 'migrate'):
        sub = commands.add_parser(command)
        sub.add_argument('--project-root', type=Path, required=True)
        if command == 'begin':
            sub.add_argument('--task', type=Path, required=True)
            sub.add_argument('--invocation', choices=['automatic', 'explicit'], required=True)
            sub.add_argument('--worker-model')
            sub.add_argument('--worker-effort')
            sub.add_argument('--assessment', type=Path, help='Current-chat delegation assessment JSON; required for new automatic tasks')
    sub = commands.add_parser('migrate_completion', help='Explicit saved-settings migration to return; never edits tasks')
    sub.add_argument('--project-root', type=Path, required=True)
    sub.add_argument('--scope', choices=['project', 'global'], required=True)
    sub.add_argument('--expected-revision', required=True)
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
            sub.add_argument('--native-dispatch', type=Path)
            sub.add_argument('--outcome', choices=['completed', 'failed', 'blocked', 'cancelled'], required=True)
    for command in ('planner_begin', 'planner_reserve', 'planner_complete', 'planner_status', 'planner_run', 'planner_stop'):
        sub = commands.add_parser(command)
        sub.add_argument('--project-root', type=Path, required=True)
        if command == 'planner_begin':
            sub.add_argument('--request', type=Path, required=True)
            sub.add_argument('--invocation', choices=['explicit'], required=True)
            sub.add_argument('--planner', type=Path)
        else:
            sub.add_argument('--plan-id', required=True)
        if command == 'planner_reserve': sub.add_argument('--host-capabilities', type=Path, required=True)
        if command == 'planner_run':
            sub.add_argument('--attempt-id', required=True)
            sub.add_argument('--invocation', choices=['explicit'], required=True)
        if command == 'planner_complete':
            sub.add_argument('--dispatch-id', required=True)
            sub.add_argument('--native-receipt', required=True)
            sub.add_argument('--outcome', choices=['completed', 'failed', 'blocked', 'cancelled'], required=True)
            sub.add_argument('--result', type=Path)
    args = parser.parse_args()
    try:
        args.project_root = project_path(args.project_root)
        if args.command == 'migrate':
            from codex_duo_migration import migrate
            print(json.dumps(migrate(args.project_root), ensure_ascii=False))
            return 0
        service = CodexDuoService(args.project_root / '.codex-duo')
        if args.command == 'defaults':
            result = service.defaults(str(args.project_root))
        elif args.command == 'begin':
            override = {k: v for k, v in {'model': args.worker_model,
                        'reasoning_effort': args.worker_effort}.items() if v is not None}
            result = service.begin({'project_root': str(args.project_root),
                'task': json.loads(args.task.read_text()), 'invocation': args.invocation,
                **({'assessment': json.loads(args.assessment.read_text())} if args.assessment else {}),
                **({'worker_override': override} if override else {})})
        else:
            body = {key: value for key, value in vars(args).items() if key != 'command' and value is not None}
            body['project_root'] = str(args.project_root)
            if body.get('workstreams'): body['workstreams'] = json.loads(body['workstreams'].read_text())
            if body.get('native_dispatch'): body['native_dispatch'] = json.loads(body['native_dispatch'].read_text())
            if args.command == 'migrate_completion':
                result = service.defaults_store.store(args.scope).migrate_completion(args.expected_revision)
            elif args.command.startswith('planner_'):
                for key in ('request', 'host_capabilities', 'result', 'planner'):
                    if body.get(key): body[key] = json.loads(body[key].read_text())
                result = service.planning(args.command.removeprefix('planner_'), body)
            else:
                result = service.parallel(args.command, body)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (SelectionError, OSError, ValueError) as exc:
        print(json.dumps({'state': 'blocked', 'execution_started': False,
                          'error': {'code': getattr(exc, 'code', 'local_error'), 'message': str(exc)}}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
