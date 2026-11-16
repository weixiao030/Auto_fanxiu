"""Exercise previously untested positive task paths using client snapshot contracts."""
from copy import deepcopy
import time
import unittest

from fanxiu_assistant.policy import Planner, LABELS
from test_policy import state


class FullFunctionPathTests(unittest.TestCase):
    def test_remaining_positive_task_contracts(self):
        now = time.time() * 1000
        cases = [
            ('levelup', {'character': {'exp': 100}}, {}, {}),
            ('harvest', {'idle': {'drops': [{'available_at': now - 1000}]}}, {}, {}),
            ('mail', {'mails': [{'id': 5, 'claimed': False, 'rewards': [{'count': 1}]}]}, {}, {'mail_id': 5}),
            ('world_sync', {}, {}, {}),
            ('world_harvest', {'world': {'points': [{'marker_id': 11, 'type': 'herb', 'remaining': 1}]}}, {}, {'marker_id': 11}),
            ('world_points', {'world': {'points': [{'marker_id': 12, 'type': 'spring'}]}}, {}, {'marker_id': 12}),
            ('world_events', {'world': {'pending_event': {'event_id': 13}}}, {}, {'event_id': 13, 'action': 'close'}),
            ('gongfa', {'training_candidates': [{'id': 7, 'layer': 1, 'state': 'ready', 'allowed': True, 'bound_only_safe': True}]}, {}, {'gongfa_id': 7, 'action': 'start_training'}),
            ('gongfa_activate', {'gongfa_options': [{'id': 7, 'can_activate': True, 'activation_bound_safe': True}]}, {}, {'gongfa_id': 7}),
            ('gongfa_slots', {'character': {'gongfa': {'active_slots': [0, 0]}}, 'gongfa_options': [{'id': 7, 'activated': True, 'element_match': True, 'active': True}]}, {}, {'slots': [7, 0]}),
            ('pill', {'pills': [{'id': 6001, 'quality': 'common', 'useful': True, 'count': 2, 'bound_count': 2}]}, {}, {'pill_id': 6001}),
            ('gongfa_accelerate', {'gongfa_options': [{'id': 7, 'training': {'state': 'running', 'target': 2}, 'spare_pages': 10, 'acceleration_bound_safe': True}]}, {}, {'gongfa_id': 7}),
            ('world_forge', {'idle': {'selected': {'difficulty': 0, 'tier': 0, 'stage': 0}}, 'world': {'points': [{'marker_id': 14, 'type': 'forge'}]}, 'refine_inputs': [{'id': 7001, 'kind': 'herb', 'category': 'herb', 'steam_trade_known': True, 'steam_tradable': False, 'count': 45, 'value': 4, 'bound_only_safe': True}], 'owned_items': {'herb:7001': 45}}, {}, {'marker_id': 14, 'materials': {'7001': 9}}),
            ('social_sync', {}, {}, {}),
            ('partner_rescue', {'partner': {'has_partner': True, 'target': '123', 'synced_at': now, 'capture': {'capture_id': 'test-capture', 'expires_at': now + 60000}, 'rescue': {'id': 4004, 'count': 100, 'cost': 2, 'bound_only_safe': True}}}, {}, {'action': 'rescue_talisman', 'target': '123', 'capture_id': 'test-capture'}),
            ('bounty_sync', {}, {}, {}),
            ('bounty_publish', {'world': {'captured': True, 'capture': {'capture_id': 'test-capture', 'master_token': 'test-master'}, 'bounty_prop': {'id': 4003, 'count': 100, 'bound_only_safe': True}}}, {'bounty_publish_captured': True}, {'capture_id': 'test-capture', 'master_token': 'test-master'}),
        ]
        for kind, snapshot, options, expected in cases:
            with self.subTest(kind=kind):
                planner = Planner(clock=lambda: 1000)
                planner.config['tasks'] = {key: key == kind for key in LABELS}
                planner.config.update(options)
                current = state()
                current['bridge_revision'] = 16
                snapshot = deepcopy(snapshot)
                current['character'].update(snapshot.pop('character', {}))
                current.update(snapshot)
                command = planner.choose(current)
                self.assertIsNotNone(command)
                self.assertEqual(command['kind'], kind)
                self.assertEqual(command['params'], expected)
                self.assertTrue(command['id'])


if __name__ == '__main__':
    unittest.main()
