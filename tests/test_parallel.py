"""Offline contracts/accounting tests. They do not execute native models."""
import concurrent.futures
import difflib
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/fusion-minimal/skills/fusion/scripts'))
from fusion_service import FusionService
from fusion_selection import SelectionError, normalize_catalog, default_selection, prepare_handoff


class ParallelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'home')}); self.env.start()
        self.catalog = normalize_catalog({'models':[{'slug':'worker','visibility':'list','supported_reasoning_levels':[{'effort':'high'}]}]})
        self.service = FusionService(self.root / '.fusion', lambda:self.catalog)
        self.task = {'schema_version':1, 'task_id':'parent', 'goal':'bounded feature',
            'allowed_paths':['a.py','b.py','c.py'], 'acceptance':['integration'], 'tests':[['python3','-m','unittest']]}
        self.workflow = {'activation':'automatic_project', 'coordinator_mode':'current_thread', 'max_worker_turns':3, 'max_parallel_workers':3}
        self.selection = default_selection(self.catalog)
        self.service.save({'selection':self.selection,'workflow':self.workflow,'expected_revision':'none'})
        self.plan = self.service.begin({'project_root':str(self.root), 'task':self.task,'invocation':'automatic'})
        self.base = {'project_root':str(self.root), 'handoff_id':self.plan['handoff_id']}

    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def call(self, operation, **args):
        return self.service.parallel(operation, {**self.base, **args})

    def streams(self, dependencies=False):
        return [{'id':sid,'task':{**self.task,'task_id':sid,'allowed_paths':[sid+'.py']},'depends_on':['a'] if dependencies and sid=='b' else []} for sid in ['a','b','c']]

    def failed(self, reservation):
        return self.call('complete',dispatch_id=reservation['id'],outcome='failed',native_receipt='offline mock spawn failure')

    def evidence(self, root, task, paths=None):
        root = Path(root); root.mkdir(parents=True,exist_ok=True)
        paths = paths or task['allowed_paths']
        patch_text = ''.join(''.join(difflib.unified_diff(['before\n'],['after\n'],fromfile='a/'+p,tofile='b/'+p)) for p in paths)
        (root/'change.diff').write_text(patch_text); (root/'tests.log').write_text('offline fixture: pass')
        ref=lambda p:{'path':p,'sha256':hashlib.sha256((root/p).read_bytes()).hexdigest()}
        result={'schema_version':1,'task_id':task['task_id'],'status':'completed','summary':'offline evidence fixture','changed_paths':paths,
            'diff':ref('change.diff'),'tests':[{'argv':argv,'exit_code':0,'log':ref('tests.log')} for argv in task['tests']], 'blockers':[]}
        (root/'result.json').write_text(json.dumps(result))

    def completed(self, reservation):
        self.evidence(reservation['evidence_root'], reservation['task'])
        return self.call('complete',dispatch_id=reservation['id'],outcome='completed',native_receipt='offline native receipt fixture')

    def test_simple_task_still_single_worker(self):
        plan=self.call('plan',host_capacity=3)
        self.assertEqual(1,plan['max_simultaneous_workers'])
        reserve=self.call('reserve',host_capacity=3,workstream_id='main')
        self.assertEqual(self.task,reserve['task'])
        self.assertFalse(reserve['execution_started'])
        self.assertEqual('none',reserve['worker']['fork_turns'])

    def test_capacity_and_shared_total_budget_including_failures_and_corrections(self):
        self.call('plan',host_capacity=1,workstreams=self.streams())
        a=self.call('reserve',host_capacity=1,workstream_id='a')
        with self.assertRaisesRegex(SelectionError,'容量'): self.call('reserve',host_capacity=3,workstream_id='b')
        self.failed(a)
        correction=self.call('reserve',host_capacity=1,workstream_id='a'); self.failed(correction)
        b=self.call('reserve',host_capacity=1,workstream_id='b'); self.failed(b)
        with self.assertRaisesRegex(SelectionError,'用完'): self.call('reserve',host_capacity=1,workstream_id='c')
        # Restarting the service / retrying the plan cannot replenish the parent budget.
        self.service=FusionService(self.root/'.fusion',lambda:self.catalog)
        self.assertEqual(0,self.call('plan',host_capacity=3,workstreams=self.streams())['remaining_worker_turns'])
        with self.assertRaises(SelectionError): self.call('plan',host_capacity=3)

    def test_saved_limit_and_current_actual_host_capacity(self):
        self.call('plan',host_capacity=3,workstreams=self.streams())
        a=self.call('reserve',host_capacity=1,workstream_id='a')
        with self.assertRaises(SelectionError): self.call('reserve',host_capacity=1,workstream_id='b')
        b=self.call('reserve',host_capacity=3,workstream_id='b')
        self.assertNotEqual(a['evidence_root'],b['evidence_root'])
        self.assertEqual(self.selection['worker']['model'],a['worker']['model'])
        self.assertEqual(1,self.call('plan',host_capacity=3,workstreams=self.streams())['available_dispatch_slots'])

    def test_overlapping_unknown_scope_and_cyclic_dependencies_rejected(self):
        for mutation in ['overlap','outside','cycle']:
            streams=self.streams()
            if mutation=='overlap': streams[1]['task']['allowed_paths']=['a.py']
            if mutation=='outside': streams[1]['task']['allowed_paths']=['outside.py']
            if mutation=='cycle': streams[0]['depends_on']=['b'];streams[1]['depends_on']=['a']
            with self.assertRaises(SelectionError): self.call('plan',host_capacity=3,workstreams=streams)
        self.assertFalse((Path(self.plan['evidence_root'])/'dispatch.json').exists())

    def test_dependencies_require_verified_evidence(self):
        self.call('plan',host_capacity=3,workstreams=self.streams(True))
        with self.assertRaises(SelectionError): self.call('reserve',host_capacity=3,workstream_id='b')
        a=self.call('reserve',host_capacity=3,workstream_id='a')
        with self.assertRaises(SelectionError): self.call('complete',dispatch_id=a['id'],outcome='completed',native_receipt='fixture')
        self.completed(a)
        self.call('reserve',host_capacity=3,workstream_id='b')
        with self.assertRaises(SelectionError): self.call('reserve',host_capacity=3,workstream_id='a')

    def test_all_children_plus_integrated_parent_gate_and_tamper(self):
        self.call('plan',host_capacity=3,workstreams=self.streams())
        receipts=[self.call('reserve',host_capacity=3,workstream_id=sid) for sid in ['a','b','c']]
        for receipt in receipts: self.completed(receipt)
        with self.assertRaises(SelectionError): self.call('verify') # missing integrated tests/result
        self.evidence(self.plan['evidence_root'],self.task, ['a.py','b.py'])
        with self.assertRaisesRegex(SelectionError,'omits'): self.call('verify')
        self.evidence(self.plan['evidence_root'],self.task)
        verdict=self.call('verify');self.assertEqual(3,verdict['verified_workstreams']);self.assertEqual(3,verdict['dispatch_count'])
        (Path(receipts[0]['evidence_root'])/'tests.log').write_text('tampered')
        with self.assertRaises(SelectionError): self.call('verify')

    def test_concurrent_reservations_cannot_exceed_actual_capacity(self):
        self.call('plan',host_capacity=1,workstreams=self.streams())
        def reserve(sid):
            service=FusionService(self.root/'.fusion',lambda:self.catalog)
            try: return service.parallel('reserve',{**self.base,'host_capacity':1,'workstream_id':sid})
            except SelectionError: return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(reserve,['a','b','c']))
        self.assertEqual(1,sum(r is not None for r in results))

    def test_legacy_settings_and_snapshot_read_are_unchanged(self):
        legacy={key:value for key,value in self.workflow.items() if key!='max_parallel_workers'}
        doc=json.loads(self.service.store.path.read_text());doc['workflow']=legacy;self.service.store.path.write_text(json.dumps(doc))
        settings_before=self.service.store.path.read_bytes()
        self.assertEqual(1,self.service.defaults(str(self.root))['workflow']['max_parallel_workers'])
        self.assertEqual(settings_before,self.service.store.path.read_bytes())
        old=prepare_handoff(self.task,self.selection,self.catalog,self.root/'.fusion/handoffs','old',legacy)
        files={p:p.read_bytes() for p in Path(old['path']).rglob('*') if p.is_file()}
        dirs=set((self.root/'.fusion').rglob('*'))
        value=self.service.execution_plan(old['id'])
        self.assertEqual(1,value['max_parallel_workers'])
        self.assertEqual(dirs,set((self.root/'.fusion').rglob('*')))
        self.assertEqual(files,{p:p.read_bytes() for p in files})
        missing=self.root/'.fusion/handoffs'/('0'*24)
        with self.assertRaises(SelectionError): self.service.execution_plan('0'*24)
        self.assertFalse(missing.exists())

    def test_global_and_project_parallel_settings_validate_persist_and_override(self):
        self.service.save({'scope':'global','selection':self.selection,'workflow':self.workflow,'expected_revision':'none'})
        self.service.settings_update({'max_parallel_workers':'2'})
        self.assertEqual('2',self.service.settings_read()['values']['max_parallel_workers'])
        self.assertEqual(3,self.service.defaults(str(self.root))['workflow']['max_parallel_workers'])
        for bad in ['0','4','true','1.5']:
            with self.assertRaises(SelectionError): self.service.settings_update({'max_parallel_workers':bad})
        for bad in [True,0,4,'2']:
            with self.assertRaises(SelectionError): self.service.save({'selection':self.selection,'workflow':{**self.workflow,'max_parallel_workers':bad},'expected_revision':'none'})

    def test_modified_contract_reservation_leaves_no_orphan(self):
        self.call('plan',host_capacity=1)
        contract=Path(self.plan['evidence_root'])/'contracts/main.json'
        original=contract.read_bytes();contract.write_text('{}')
        with self.assertRaises(SelectionError):self.call('reserve',host_capacity=1,workstream_id='main')
        evidence=Path(self.plan['evidence_root'])/'workers/main/dispatch-001'
        self.assertFalse(evidence.exists())
        contract.write_bytes(original)
        self.assertEqual('dispatch-001',self.call('reserve',host_capacity=1,workstream_id='main')['id'])

    def test_saved_parallel_limits_one_and_two_bound_three_ready_streams(self):
        for limit in [1,2]:
            current=self.service.store.read(self.catalog)
            self.service.save({'selection':self.selection,'workflow':{**self.workflow,'max_parallel_workers':limit},'expected_revision':current['revision']})
            parent={**self.task,'task_id':'limit-'+str(limit)}
            plan=self.service.begin({'project_root':str(self.root),'task':parent,'invocation':'automatic'})
            self.base['handoff_id']=plan['handoff_id']
            self.assertEqual(limit,self.call('plan',host_capacity=3,workstreams=self.streams())['max_simultaneous_workers'])
            for sid in ['a','b'][:limit]:self.call('reserve',host_capacity=3,workstream_id=sid)
            with self.assertRaises(SelectionError):self.call('reserve',host_capacity=3,workstream_id='c')

    def test_correction_invalidates_downstream_completion_without_resetting_budget(self):
        self.call('plan',host_capacity=3,workstreams=self.streams(True)[:2])
        a=self.call('reserve',host_capacity=3,workstream_id='a');self.completed(a)
        b=self.call('reserve',host_capacity=3,workstream_id='b');self.completed(b)
        correction=self.call('reserve',host_capacity=3,workstream_id='a');self.completed(correction)
        self.evidence(self.plan['evidence_root'],self.task)
        with self.assertRaisesRegex(SelectionError,'b'):self.call('verify')
        self.assertEqual(['a'],self.call('plan',host_capacity=3,workstreams=self.streams(True)[:2])['completed_workstreams'])
        with self.assertRaisesRegex(SelectionError,'用完'):self.call('reserve',host_capacity=3,workstream_id='b')

    def test_legacy_editor_save_preserves_new_parallel_preference(self):
        current=self.service.store.read(self.catalog)
        legacy={key:value for key,value in self.workflow.items() if key!='max_parallel_workers'}
        saved=self.service.save({'selection':self.selection,'workflow':legacy,'expected_revision':current['revision']})
        self.assertEqual(3,saved['document']['workflow']['max_parallel_workers'])

    def test_symlink_dispatch_storage_rejected(self):
        root=Path(self.plan['evidence_root']);root.mkdir(parents=True)
        (root/'dispatch.json').symlink_to(self.root/'outside')
        with self.assertRaises(SelectionError):self.call('plan',host_capacity=1)

if __name__=='__main__': unittest.main()
