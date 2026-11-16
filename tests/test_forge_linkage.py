"""Native forge progress and confirmed downstream actions share one growth budget."""
from copy import deepcopy
import unittest

from fanxiu_assistant.task_catalog import TASK_ORDER
import test_growth


class ForgeLinkageTests(unittest.TestCase):
    def fixture(self):
        p, s = test_growth.GrowthTests().fixture()
        p.config['tasks']['world_forge'] = True
        s.update(bridge_revision=27, refine_forge_multiplier=3,
                 world={'points': [{'marker_id': 14, 'type': 'forge'}]})
        return p, s

    def test_forge_reaches_target_with_six_donors_instead_of_seventeen(self):
        p, s = self.fixture()
        s['owned_items']['material:1001'] = s['refine_inputs'][0]['count'] = 8
        self.assertFalse(p.refine_status(s)['ready'])
        plan = p.ledger(s).refine_plan(p.safe_flag, forge=True)
        self.assertTrue(plan['ready'])
        self.assertEqual(plan['materials'], {'1001': 6})
        self.assertEqual(plan['progress'], 108)
        self.assertEqual(plan['input_progress'], 36)
        self.assertEqual(p.plan_world_forge(s)[0]['marker_id'], 14)

    def test_breakthrough_prefers_forge_then_waits_for_confirmed_inventory(self):
        p, s = self.fixture()
        before = deepcopy(s['owned_items'])
        command = p.choose(s)
        self.assertEqual((command['kind'], command['parent_kind']), ('world_forge', 'breakthrough'))
        self.assertEqual(command['params']['materials'], {'1001': 6})
        p.observe_result(command, {'ok': True}, s)
        self.assertEqual(s['owned_items'], before)
        confirmed = deepcopy(s)
        confirmed['owned_items']['material:1008'] = 10
        confirmed['breakthrough']['all_enough'] = True
        p.clock = lambda: 1100
        self.assertEqual(p.choose(confirmed)['kind'], 'breakthrough')

    def test_forge_disabled_or_backed_off_falls_back_to_normal_refine(self):
        for blocked in ('disabled', 'task_backoff', 'point_backoff', 'current_home', 'missing'):
            with self.subTest(blocked=blocked):
                p, s = self.fixture()
                if blocked == 'disabled': p.config['tasks']['world_forge'] = False
                elif blocked == 'task_backoff': p.due['world_forge'] = 1100
                elif blocked == 'point_backoff': p.item_due[('world_forge', 14)] = 1100
                elif blocked == 'current_home': s['world']['points'][0]['is_current'] = True
                else: s['world']['points'].clear()
                command = p.choose(s)
                self.assertEqual(command['kind'], 'refine')
                self.assertEqual(command['params']['materials'], {'1001': 17})

    def test_forge_independent_task_can_supply_when_normal_refine_is_off(self):
        p, s = self.fixture()
        p.config['tasks']['refine'] = False
        command = p.choose(s)
        self.assertEqual((command['kind'], command['parent_kind']), ('world_forge', 'breakthrough'))

    def test_ordinary_rotation_prefers_available_forge_but_honors_manual_task(self):
        for cursor in (0, TASK_ORDER.index('refine'), TASK_ORDER.index('world_forge')):
            p, s = self.fixture()
            p.config['tasks']['breakthrough'] = False
            s['needs_breakthrough'] = False
            s['breakthrough_preparation'] = {}
            p.config['refine_preferred_id'] = 1008
            p.cursor = cursor
            self.assertEqual(p.choose(s)['kind'], 'world_forge')
        p, s = self.fixture()
        self.assertEqual(p.choose(s, only_kind='refine')['kind'], 'refine')

    def test_forge_keeps_stage_requirement_reserves_locks_and_protection(self):
        for blocked in ('stage', 'reserve', 'lock', 'bound_shortage'):
            with self.subTest(blocked=blocked):
                p, s = self.fixture()
                if blocked == 'stage': s['idle'] = {}
                elif blocked == 'reserve': p.config['refine_obsolete_reserve'] = 25
                elif blocked == 'lock': p.config['manual_locks'] = ['material:1001']
                else:
                    p.config['preserve_steam_tradable'] = True
                    s['bound_items']['material:1001'] = 1
                    s['refine_inputs'][0].update(steam_trade_known=True, steam_tradable=True)
                s['protection_policy'] = p.protection_policy()
                self.assertIsNone(p.plan_world_forge(s))


if __name__ == '__main__':
    unittest.main()
