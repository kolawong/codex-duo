"""Native plugin settings save one property at a time; no model dispatch."""
import copy
import unittest
from unittest.mock import patch
import test_global_defaults as global_defaults
from test_native import catalog, mcp
from codex_duo_selection import SelectionError
from codex_duo_service import CodexDuoService


class PlannerSettingsTests(unittest.TestCase):
    save = global_defaults.GlobalDefaultsTests.save

    def setUp(self):
        global_defaults.GlobalDefaultsTests.setUp(self)
        self.selection['coordinator']['reasoning_effort'] = 'ultra'
        self.save()
        self.initial = self.one.settings_read()['values']

    def update(self, **changes):
        response = mcp.MCPServer(self.one).call('codex_duo_settings_update', {
            'project_root': str(self.a), 'set': changes})
        self.assertFalse(response.get('isError'), response)
        return response['structuredContent']['values']

    def test_native_single_property_enable_initializes_missing_pair_only(self):
        before = copy.deepcopy(self.initial)
        with patch('codex_duo_service.CodexDuoService.planning', side_effect=AssertionError('settings must not dispatch')):
            values = self.update(planner_mode='plan_only')
        self.assertEqual('plan_only', values['planner_mode'])
        self.assertEqual(self.selection['coordinator']['model'], values['planner_model'])
        self.assertEqual('ultra', values['planner_reasoning_effort'])
        for key in set(before) - {'planner_mode', 'planner_model', 'planner_reasoning_effort'}:
            self.assertEqual(before[key], values[key])
        self.assertFalse((self.a / '.codex-duo/plans').exists())

    def test_model_then_effort_individual_updates_reopen_and_override_priority(self):
        self.save(scope='project', workflow={**self.workflow, 'activation': 'manual'})
        project_before = self.one.store.path.read_bytes()
        self.update(planner_mode='plan_only')
        values = self.update(planner_model='gpt-6-luna')
        self.assertEqual('high', values['planner_reasoning_effort'])
        values = self.update(planner_reasoning_effort='medium')
        reopened = CodexDuoService(self.a / '.codex-duo', catalog)
        self.assertEqual(values, reopened.settings_read()['values'])
        self.assertEqual('disabled', reopened.defaults(str(self.a))['planner']['mode'])
        self.assertEqual('plan_only', self.two.defaults(str(self.b))['planner']['mode'])
        self.assertEqual(project_before, self.one.store.path.read_bytes())
        schema = reopened.settings_read()['schema']['properties']
        self.assertEqual(['high', 'medium'], schema['planner_reasoning_effort']['enum'])
        self.assertNotIn('', schema['planner_model']['enum'])

    def test_disabled_model_first_selects_supported_effort_without_enabling(self):
        values = self.update(planner_model='gpt-6-luna')
        self.assertEqual('disabled', values['planner_mode'])
        self.assertEqual('high', values['planner_reasoning_effort'])
        self.update(planner_reasoning_effort='medium')
        values = self.update(planner_mode='plan_only')
        self.assertEqual('gpt-6-luna', values['planner_model'])
        self.assertEqual('medium', values['planner_reasoning_effort'])
        self.assertEqual('medium', self.update(planner_mode='disabled')['planner_reasoning_effort'])
        self.assertEqual('medium', self.update(planner_mode='plan_only')['planner_reasoning_effort'])

    def test_explicit_invalid_pair_rejected_without_overwriting_user_choice(self):
        self.update(planner_mode='plan_only')
        before = self.one.defaults_store.global_store.path.read_bytes()
        with self.assertRaises(SelectionError):
            self.one.settings_update({'planner_model': 'gpt-6-luna', 'planner_reasoning_effort': 'ultra'})
        self.assertEqual(before, self.one.defaults_store.global_store.path.read_bytes())
        with self.assertRaises(SelectionError): self.one.settings_update({'planner_model': ''})
        self.assertEqual(before, self.one.defaults_store.global_store.path.read_bytes())

    def test_unrelated_updates_do_not_fill_empty_planner_defaults(self):
        self.update(max_worker_turns='8')
        values = self.one.settings_read()['values']
        self.assertEqual('disabled', values['planner_mode'])
        self.assertEqual('', values['planner_model'])
        self.assertEqual('', values['planner_reasoning_effort'])

    def test_enable_full_form_empty_pair_is_supported_and_can_restore_original(self):
        values = self.update(planner_mode='plan_only', planner_model='', planner_reasoning_effort='')
        self.assertEqual('ultra', values['planner_reasoning_effort'])
        restored = self.update(**self.initial)
        self.assertEqual(self.initial, restored)
        self.assertEqual(self.initial, self.one.settings_read()['values'])


if __name__ == '__main__': unittest.main()
