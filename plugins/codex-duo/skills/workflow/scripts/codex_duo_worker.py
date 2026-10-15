"""Task-local Worker choices and coordinator-recorded host evidence. No inference."""
from codex_duo_selection import SelectionError, canonical, WORKER_TIERS
import json

FIELDS = ('model', 'reasoning_effort')


def resolve_stream_worker(parent, routing=None):
    """Resolve from the immutable task policy, not today's settings or a classifier."""
    if routing is not None and (not isinstance(routing, dict)
            or set(routing) != {'tier', 'reason'} or routing['tier'] not in WORKER_TIERS
            or not isinstance(routing['reason'], str) or not routing['reason'].strip()
            or len(routing['reason']) > 600):
        raise SelectionError('invalid_routing', '子任务分级须包含 tier（light/standard/complex）和 1 到 600 字的具体 reason。')
    worker, resolution = parent['worker'], parent.get('worker_resolution')
    # Even a partial explicit override fixes the resolved task pair; never combine it
    # with a different tier to silently change an omitted field.
    if parent.get('worker_strategy', 'fixed') == 'fixed' or (resolution or {}).get('override'):
        if routing is not None:
            raise SelectionError('routing_not_enabled', '固定模式或本次显式覆盖使用任务组合，无需传入子任务分级。')
        return worker, resolution
    if routing is None:
        raise SelectionError('routing_required', '自动分级须在 plan 中为每个子任务提供 routing；由当前聊天判断，不启动分类器。')
    choice = parent['worker_profiles'][routing['tier']]
    return {**worker, **choice}, {'override': {}, 'sources': {k: 'profile_' + routing['tier'] for k in FIELDS},
                                 'routing': routing}


def validate_override(value):
    if (not isinstance(value, dict) or not value or set(value) - set(FIELDS)
            or any(not isinstance(v, str) or not v.strip() for v in value.values())):
        raise SelectionError('invalid_worker_override', '本次 Worker 覆盖仅接受 model、reasoning_effort，至少提供一项。')
    return json.loads(canonical(value))


def validate_native_dispatch(value, worker, receipt):
    """Check report consistency, never turn request settings into host telemetry."""
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) - {'tool', 'agent_id', 'parameters', 'runtime'}
            or not {'tool', 'agent_id', 'parameters'} <= set(value)
            or any(not isinstance(value[k], str) or not value[k].strip() for k in ('tool', 'agent_id'))
            or value['agent_id'] != receipt):
        raise SelectionError('invalid_native_dispatch', '需要实际成功派发的工具、代理 ID（与回执一致）和调用参数。')
    expected = {**{k: worker[k] for k in FIELDS}, 'agent_type': 'codex_duo_worker', 'fork_turns': 'none'}
    if value['parameters'] != expected:
        raise SelectionError('dispatch_mismatch', '成功派发参数必须与保留的 Worker、原生角色及 fresh context 一致。', 409)
    runtime = value.get('runtime', {})
    if (not isinstance(runtime, dict) or set(runtime) - set(FIELDS)
            or any(not isinstance(v, str) or not v.strip() for v in runtime.values())):
        raise SelectionError('invalid_native_dispatch', 'runtime 只能包含宿主实际返回的 model / reasoning_effort；缺失字段请省略。')
    return json.loads(canonical(value))


def worker_summary(worker, resolution=None, native_dispatch=None):
    requested = {k: worker[k] for k in FIELDS}
    sources = (resolution or {}).get('sources', {k: 'legacy_snapshot' for k in FIELDS})
    runtime = (native_dispatch or {}).get('runtime', {})
    labels = {'task_override': '本次覆盖', 'project': '项目配置', 'global': '全局默认', 'legacy_snapshot': '旧任务快照'}
    labels.update({'profile_light': '轻量候选', 'profile_standard': '标准候选', 'profile_complex': '复杂候选'})
    origin = labels[sources['model']] if sources['model'] == sources['reasoning_effort'] else (
        f"模型={labels[sources['model']]}，强度={labels[sources['reasoning_effort']]}")
    host = {k: {'status': 'provided' if k in runtime else 'not_provided', 'value': runtime.get(k)} for k in FIELDS}
    mismatch = any(runtime[k] != requested[k] for k in runtime)
    return {'requested': requested, 'sources': sources,
            'successful_dispatch': native_dispatch.get('parameters') if native_dispatch else None,
            'native_tool': native_dispatch.get('tool') if native_dispatch else None,
            'agent_id': native_dispatch.get('agent_id') if native_dispatch else None,
            'runtime': host, 'runtime_mismatch': mismatch,
            'provenance': 'coordinator_recorded_host_response' if native_dispatch else 'not_provided',
            'text': f"请求 {requested['model']} / {requested['reasoning_effort']} · 来源：{origin} · "
                + ('成功派发参数已记录' if native_dispatch else '成功派发参数未提供')
                + ' · 宿主运行时：' + ' / '.join(runtime.get(k, '未提供') for k in FIELDS)
                + ('（与请求不一致）' if mismatch else ''),
            'limitation': '回执由主控转录；服务只校验一致性，不能独立认证宿主运行时身份。'}
