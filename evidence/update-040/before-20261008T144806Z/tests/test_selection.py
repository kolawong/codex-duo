import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/fusion-minimal/skills/fusion/scripts'))
from fusion_selection import (SelectionError, SelectionStore, normalize_catalog, presets,
                              default_selection, validate_selection, prepare_handoff)
from fusion import demo, verify
sys.path.insert(0, str(ROOT))
from panel.server import PanelService


def catalog():
    return normalize_catalog({'models': [
        {'slug': name, 'visibility': 'list', 'display_name': name,
         'supported_reasoning_levels': [{'effort': e} for e in efforts],
         'default_reasoning_level': 'high'}
        for name, efforts in [('gpt-6-astra', ['high', 'ultra']),
                              ('gpt-6.1-sol', ['high', 'medium']),
                              ('gpt-6-luna', ['high', 'medium'])]]})


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog = catalog()
        self.selection = default_selection(self.catalog)
        self.store = SelectionStore(self.root / 'state')
        self.task = json.loads((ROOT / 'plugins/fusion-minimal/skills/fusion/templates/task.json').read_text())

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        return self.store.save(self.selection, self.catalog, 'none')

    def prepare(self):
        return prepare_handoff(self.task, self.selection, self.catalog, self.root / 'handoffs', 'revision')

    def test_empty_catalog_rejected(self):
        with self.assertRaises(SelectionError): normalize_catalog({'models': []})

    def test_hidden_models_not_exposed(self):
        with self.assertRaises(SelectionError):
            normalize_catalog({'models': [{'slug': 'hidden', 'visibility': 'hide',
                'supported_reasoning_levels': [{'effort': 'high'}]}]})

    def test_presets_only_include_supported_pairs(self):
        limited = copy.deepcopy(self.catalog)
        limited['models'] = [m for m in limited['models'] if m['id'] != 'gpt-6-astra']
        self.assertNotIn('deep', [p['id'] for p in presets(limited)])
        for p in presets(limited): validate_selection(p['selection'], limited)

    def test_unknown_model_rejected(self):
        self.selection['worker']['model'] = 'not-a-model'
        with self.assertRaises(SelectionError): self.save()
        self.assertFalse(self.store.path.exists())

    def test_invalid_effort_rejected(self):
        self.selection['worker']['reasoning_effort'] = 'ultra'
        with self.assertRaises(SelectionError): self.save()

    def test_invalid_selection_shape(self):
        with self.assertRaises(SelectionError): validate_selection({'coordinator': []}, self.catalog)

    def test_save_and_restore_across_instances(self):
        saved = self.save()
        recovered = SelectionStore(self.store.directory).read(self.catalog)
        self.assertEqual(saved['revision'], recovered['revision'])
        self.assertEqual(self.selection, recovered['document']['selection'])
        self.assertFalse(recovered['document']['execution_started'])

    def test_repeated_save_is_idempotent(self):
        first = self.save()
        again = self.save()
        self.assertFalse(again['changed'])
        self.assertEqual(first['revision'], again['revision'])

    def test_stale_window_cannot_overwrite(self):
        self.save()
        self.selection['worker']['reasoning_effort'] = 'medium'
        with self.assertRaises(SelectionError) as ctx: self.save()
        self.assertEqual(ctx.exception.code, 'revision_conflict')

    def test_atomic_write_failure_preserves_saved_config(self):
        saved = self.save()
        self.selection['worker']['reasoning_effort'] = 'medium'
        with patch('fusion_selection.os.replace', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError): self.store.save(self.selection, self.catalog, saved['revision'])
        self.assertEqual(saved['revision'], self.store.read(self.catalog)['revision'])
        self.assertEqual([], list(self.store.directory.glob('.selection-*')))

    def test_corrupt_config_recovery_backs_up_original(self):
        self.store.directory.mkdir()
        self.store.path.write_text('{broken')
        read = self.store.read(self.catalog)
        self.assertIsNotNone(read['error'])
        saved = self.store.save(self.selection, self.catalog, read['revision'])
        self.assertIsNone(saved['error'])
        self.assertEqual('{broken', (self.store.directory / 'history' / (read['revision'] + '.json')).read_text())

    def test_catalog_removal_invalidates_saved_model(self):
        self.save()
        self.catalog['models'] = [m for m in self.catalog['models'] if m['id'] != 'gpt-6-astra']
        self.assertIsNotNone(self.store.read(self.catalog)['error'])

    def test_symlink_state_rejected(self):
        self.store.directory.mkdir()
        other = self.root / 'other.json'; other.write_text('{}')
        self.store.path.symlink_to(other)
        with self.assertRaises(SelectionError): self.save()
        self.assertEqual('{}', other.read_text())

    def test_handoff_requires_save(self):
        service = PanelService(self.root / 'service', lambda: self.catalog)
        with self.assertRaises(SelectionError): service.prepare({'task': self.task, 'expected_revision': 'none'})

    def test_handoff_uses_saved_snapshot(self):
        service = PanelService(self.root / 'service', lambda: self.catalog)
        saved = service.save({'selection': self.selection, 'expected_revision': 'none'})
        first = service.prepare({'task': self.task, 'expected_revision': saved['revision']})
        self.selection['worker']['reasoning_effort'] = 'medium'
        service.save({'selection': self.selection, 'expected_revision': saved['revision']})
        self.assertEqual('high', json.loads((Path(first['path']) / 'handoff.json').read_text())['selection']['worker']['reasoning_effort'])
        with self.assertRaises(SelectionError): service.prepare({'task': self.task, 'expected_revision': saved['revision']})

    def test_repeated_handoff_has_same_path(self):
        one, two = self.prepare(), self.prepare()
        self.assertTrue(one['created']); self.assertFalse(two['created'])
        self.assertEqual(one['path'], two['path'])

    def test_modified_handoff_not_overwritten(self):
        one = self.prepare()
        (Path(one['path']) / 'task.json').write_text('{}')
        with self.assertRaises(SelectionError): self.prepare()

    def test_invalid_task_scope_rejected(self):
        self.task['allowed_paths'] = ['../outside.py']
        with self.assertRaises(SelectionError): self.prepare()

    def test_preparation_never_executes_commands(self):
        with patch('subprocess.run', side_effect=AssertionError('must not execute')):
            result = self.prepare()
        self.assertFalse(result['manifest']['execution_started'])
        self.assertFalse(result['manifest']['applies_to_current_thread'])
        self.assertTrue(result['manifest']['launch_approval_required'])

    def test_handoff_toml_matches_selection_and_is_disabled(self):
        import tomllib
        result = self.prepare()
        main = tomllib.loads((Path(result['path']) / 'config/project.toml').read_text())
        worker = tomllib.loads((Path(result['path']) / 'config/fusion_worker.toml').read_text())
        self.assertEqual(self.selection['coordinator']['model'], main['model'])
        self.assertEqual(self.selection['worker']['reasoning_effort'], worker['model_reasoning_effort'])
        self.assertFalse(main['agents']['enabled']); self.assertFalse(main['features']['hooks'])

    def test_handoff_integrates_with_existing_evidence_gate(self):
        ready = self.prepare()
        example = self.root / 'offline'; demo(example)
        task = json.loads((Path(ready['path']) / 'task.json').read_text())
        result = json.loads((example / 'result.json').read_text())
        self.assertEqual('evidence_valid', verify(task, result, example)['status'])

    def test_unavailable_catalog_exposes_recoverable_error(self):
        def fail(): raise SelectionError('catalog_unavailable', 'unavailable', 503)
        state = PanelService(self.root, fail).state()
        self.assertIsNone(state['catalog'])
        self.assertEqual('catalog_unavailable', state['error']['code'])


if __name__ == '__main__': unittest.main()
