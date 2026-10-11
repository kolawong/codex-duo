"""Planner preferences are opt-in, catalog validated and never dispatch a model."""
import unittest
import test_workflow
from fusion_selection import DEFAULT_WORKFLOW, SelectionError, saved_workflow, validate_workflow


class PlannerConfigurationTests(unittest.TestCase):
    setUp = test_workflow.WorkflowTests.setUp
    tearDown = test_workflow.WorkflowTests.tearDown
    def test_legacy_defaults_keep_planner_disabled(self):
        legacy = {'activation': 'manual', 'coordinator_mode': 'selected_model', 'max_worker_turns': 3}
        self.assertEqual(legacy, validate_workflow(legacy))
        resolved = saved_workflow({'workflow': legacy})
        self.assertEqual('disabled', resolved['planner_mode'])
        self.assertEqual('selected_model', resolved['coordinator_mode'])

    def test_enabled_requires_explicit_catalog_choice(self):
        workflow = {**DEFAULT_WORKFLOW, 'planner_mode': 'plan_only'}
        with self.assertRaises(SelectionError):
            self.service.save({'selection': self.selection, 'workflow': workflow, 'expected_revision': 'none'})
        workflow.update(planner_model=self.selection['worker']['model'],
                        planner_reasoning_effort=self.selection['worker']['reasoning_effort'])
        saved = self.service.save({'selection': self.selection, 'workflow': workflow, 'expected_revision': 'none'})
        self.assertEqual('plan_only', saved['document']['workflow']['planner_mode'])
        self.assertFalse((self.root / '.fusion' / 'plans').exists())
        workflow['planner_model'] = 'not-in-catalog'
        with self.assertRaises(SelectionError):
            self.service.save({'selection': self.selection, 'workflow': workflow, 'expected_revision': saved['revision']})

    def test_invalid_planner_values_fail_closed(self):
        for key, value in [('planner_mode', 'execute'), ('planner_model', None),
                           ('planner_reasoning_effort', 3), ('max_planner_turns', True),
                           ('max_planner_turns', 0), ('max_planner_turns', 4)]:
            with self.subTest(key=key, value=value), self.assertRaises(SelectionError):
                validate_workflow({**DEFAULT_WORKFLOW, key: value})

    def test_mcp_planner_tools_require_explicit_project(self):
        from test_native import mcp
        definitions = {tool['name']: tool for tool in mcp.tool_definitions()}
        for operation in ('begin', 'reserve', 'complete', 'status'):
            tool = definitions['fusion.planner_' + operation]
            self.assertIn('project_root', tool['inputSchema']['required'])
        self.assertFalse(definitions['fusion.planner_reserve']['annotations']['idempotentHint'])
