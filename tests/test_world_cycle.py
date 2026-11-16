"""Map capacity must agree from planning through native execution."""
import unittest
from copy import deepcopy

from fanxiu_assistant.policy import Planner, DEFAULTS
from test_policy import state


class WorldCycleTest(unittest.TestCase):
    def test_full_experience_preserves_springs_with_visible_reason(self):
        p = Planner(clock=lambda: 1000)
        s = state()
        s['character'].update(exp=59422, exp_needed=26622)
        s['world'] = {'points': [{'marker_id': 91, 'type': 'spring'}]}
        self.assertIsNone(p.plan_world_points(s))
        detail = p.world_points_status(s)
        self.assertFalse(detail['ready'])
        self.assertEqual(detail['waiting_springs'], 1)
        self.assertIn('59,422/26,622', detail['message'])
        self.assertIn('升级或突破后自动吸取', detail['message'])
        s['character']['exp_needed'] = 70000
        self.assertEqual(p.plan_world_points(s)[0], {'marker_id': 91})
        self.assertTrue(p.world_points_status(s)['ready'])
        self.assertEqual(p.world_points_status(s)['waiting_springs'], 0)

    def test_full_springs_do_not_block_strongholds_or_allowed_relics(self):
        p = Planner(clock=lambda: 1000)
        s = state()
        s['character'].update(exp=100, exp_needed=100)
        s['world'] = {'points': [{'marker_id': 91, 'type': 'spring'}, {'marker_id': 92, 'type': 'stronghold'}]}
        self.assertEqual(p.plan_world_points(s)[0], {'marker_id': 92})
        self.assertIn('仍会继续处理', p.world_points_status(s)['message'])
        s['world']['points'][1]['type'] = 'relic'
        p.config['world_relics'] = False
        self.assertFalse(p.world_points_status(s)['ready'])
        p.config['world_relics'] = True
        self.assertTrue(p.world_points_status(s)['ready'])

    def test_event_waiting_message_tracks_authoritative_pending_event(self):
        p = Planner(clock=lambda: 1000)
        s = state()
        s['world'] = {'pending_event': {}}
        self.assertFalse(p.world_events_status(s)['ready'])
        self.assertIn('当前没有待处理奇遇', p.world_events_status(s)['message'])
        self.assertIsNone(p.plan_world_events(s))
        s['world']['pending_event'] = {'event_id': 12, 'type': 'cultivator_help'}
        self.assertTrue(p.world_events_status(s)['ready'])
        self.assertIn('不赠送物品', p.world_events_status(s)['message'])
        self.assertEqual(p.plan_world_events(s)[0], {'event_id': 12, 'action': 'close'})

    def fixture(self):
        p = Planner(clock=lambda: 1000)
        p.config['tasks'] = {kind: kind in ('world_prune', 'world_explore') for kind in DEFAULTS['tasks']}
        s = state()
        s['world'] = {'point_count': 3, 'max_points': 3, 'free_remaining': 1,
                      'points': [{'marker_id': 1, 'type': 'empty', 'is_current': True},
                                 {'marker_id': 2, 'type': 'breakthrough_realm'},
                                 {'marker_id': 3, 'type': 'empty'}]}
        return p, s

    def test_native_capacity_stops_exploring_and_starts_safe_cleanup(self):
        p, s = self.fixture()
        self.assertIsNone(p.plan_world_explore(s))
        self.assertIn('坐标已达上限', p.world_exploration_status(s)['message'])
        command = p.choose(s)
        self.assertIsNotNone(command)
        self.assertEqual((command['kind'], command['params']), ('world_prune', {'marker_id': 3}))

    def test_confirmed_cleanup_reopens_exploration_without_deleting_another_point(self):
        p, s = self.fixture()
        command = p.choose(s)
        self.assertIsNotNone(command)
        after = deepcopy(s)
        after['world']['points'] = after['world']['points'][:2]
        after['world']['point_count'] = 2
        p.observe_result(command, {'ok': True}, after)
        self.assertIsNone(p.plan_world_prune(after))
        self.assertIsNotNone(p.plan_world_explore(after))
        self.assertEqual(p.world_exploration_status(after)['mode'], 'free')
        # No optimistic inventory/map mutation in the original server snapshot.
        self.assertEqual(s['world']['point_count'], 3)

    def test_lower_user_limit_is_respected_by_all_three_checks(self):
        p, s = self.fixture()
        p.config['world_point_limit'] = 2
        s['world']['max_points'] = 20
        s['world']['point_count'] = 2
        self.assertIsNone(p.plan_world_explore(s))
        self.assertEqual(p.plan_world_prune(s)[0], {'marker_id': 3})
        self.assertFalse(p.world_exploration_status(s)['ready'])
        p.config['world_point_limit'] = 3
        self.assertIsNone(p.plan_world_prune(s))
        self.assertTrue(p.world_exploration_status(s)['ready'])

    def test_cleanup_switch_and_special_points_survive_full_map(self):
        p, s = self.fixture()
        p.config['world_prune'] = False
        self.assertIsNone(p.plan_world_prune(s))
        p.config['world_prune'] = True
        s['world']['points'] = s['world']['points'][:2]
        self.assertIsNone(p.plan_world_prune(s))

    def test_cleanup_frees_a_visible_slot_before_expired_history(self):
        p, s = self.fixture()
        s['world']['points'].insert(0, {'marker_id': 9, 'type': 'player', 'expires_at': 1})
        self.assertEqual(p.plan_world_prune(s)[0], {'marker_id': 3})
