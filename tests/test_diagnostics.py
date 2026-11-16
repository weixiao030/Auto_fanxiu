from copy import deepcopy
import unittest
from fanxiu_assistant.diagnostics import execution_status


class ExecutionDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.state = {'ready': True, 'online': True, 'tutorial_finished': True,
                      'bridge_revision': 42, 'character': {'level': 6}}
        self.config = {'tasks': {'collect': True}, 'stop_at_level': 0}
        self.options = dict(connected=True, heartbeat_age=1, enabled=True,
                            pending=None, pending_seconds=0, retry_after=0,
                            minimum_revision=42)

    def status(self):
        return execution_status(self.state, self.config, **self.options)

    def test_old_bridge_explains_reading_without_execution(self):
        self.state['bridge_revision'] = 40
        self.options['enabled'] = False
        self.assertEqual(self.status()['code'], 'bridge_update')
        self.assertIn('已经读到', self.status()['message'])

    def test_pausing_keeps_the_submitted_operation_visible(self):
        self.options.update(enabled=False, pending={'label': '突破'}, pending_seconds=9)
        self.assertEqual(self.status()['code'], 'settling')
        self.options['pending'] = None
        self.assertEqual(self.status()['code'], 'paused')

    def test_native_queue_remains_authoritative(self):
        self.state.update(ready=False, login_queue={'active': True, 'ahead_count': 123})
        self.assertIn('123', self.status()['message'])
        self.assertEqual(self.status()['code'], 'native_wait')

    def test_unavailable_status_never_claims_running(self):
        self.options['heartbeat_age'] = 10
        self.assertEqual(self.status()['code'], 'heartbeat_delayed')
        self.options.update(heartbeat_age=1, connected=False)
        self.assertEqual(self.status()['code'], 'disconnected')

    def test_task_and_level_gates_explain_idle_automation(self):
        self.config['tasks']['collect'] = False
        self.assertEqual(self.status()['code'], 'tasks_disabled')
        self.config['tasks']['collect'] = True
        self.config['stop_at_level'] = 6
        self.assertEqual(self.status()['code'], 'target_reached')

    def test_native_multiplayer_with_disabled_task_is_visible(self):
        self.state['multiplayer'] = {'active': True}
        self.config['tasks']['multiplayer_realm'] = False
        self.assertEqual(self.status()['code'], 'multiplayer')
        self.assertIn('开关关闭', self.status()['message'])

    def test_diagnostics_do_not_mutate_state_or_evaluate_plans(self):
        before = deepcopy((self.state, self.config, self.options))
        self.assertEqual(self.status()['code'], 'running')
        self.assertEqual((self.state, self.config, self.options), before)
        self.options['retry_after'] = 29.1
        self.assertEqual(self.status()['code'], 'backoff')
        self.assertIn('30秒', self.status()['message'])
