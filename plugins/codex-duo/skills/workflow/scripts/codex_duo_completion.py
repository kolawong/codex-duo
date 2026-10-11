"""Durable completion projection. No model, timer, message sender or host launcher.

The original dispatch ledger is the event store. Deterministic IDs make reconnects
and duplicate reads replayable without a second queue or a budget-resetting task.
"""
import time
from codex_duo_selection import digest

def completion_view(kind, identifier, records, project_root, *, now=None):
    now = time.time() if now is None else now
    events, pending = [], []
    for record in records:
        session = record.get('session', {})
        if record['status'] == 'reserved':
            uncertain = session.get('stage') == 'uncertain' or (record.get('adapter') and
                now - session.get('heartbeat', 0) > 660)
            state = ('unknown' if uncertain else 'cancellation_requested' if session.get('stop_requested') else
                     session.get('stage', 'dispatch_unconfirmed'))
            pending.append({'dispatch_id': record['id'], 'state': state,
                            'terminal_observed': False, 'retry_allowed': False,
                            'error_code': session.get('error_code')})
            continue
        outcome = record['status']
        if outcome in ('verified', 'superseded'): outcome = 'completed'
        if session.get('stage') == 'cancelled': outcome = 'cancelled'
        events.append({'event_id': digest([project_root, kind, identifier, record['id'], 'completion-v1']),
            'dispatch_id': record['id'], 'outcome': outcome,
            'native_receipt': record.get('native_receipt'),
            'result_sha256': record.get('result_sha256'),
            'source': 'official_adapter_record' if record.get('adapter') else 'coordinator_reported',
            'host_terminal_observed': session.get('terminal_observed') if record.get('adapter') else None,
            'superseded': record['status'] == 'superseded', 'requires_coordinator_review': True,
            'review_state': 'pending', 'worker_execution_authorized': False})
    return {'project_root': project_root, 'kind': kind, 'task_id': identifier, 'events': events,
            'pending': pending, 'listener': 'official_app_server_background' if kind == 'planner'
            else 'coordinator_native_host', 'event_store': 'original_dispatch_ledger',
            'instruction': 'Read the original result and evidence in the coordinating chat. Completion is not acceptance. '
                'Do not poll with another model, relaunch an unresolved dispatch, or treat a plan as implementation approval.'}
