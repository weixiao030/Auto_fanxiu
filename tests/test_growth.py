"""Cross-module budgets and acknowledged progression, rather than method mirrors."""
from copy import deepcopy
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fanxiu_assistant.policy import Planner, DEFAULTS, validate_config
from fanxiu_assistant.task_catalog import TASK_ORDER, ordered_tasks
from fanxiu_assistant.verification import source_fingerprint
from test_policy import state


class GrowthTests(unittest.TestCase):
    def fixture(self):
        p = Planner(clock=lambda: 1000)
        p.config.update(preserve_steam_tradable=False, preserve_tradable=False,
                        refine_reserve=0, refine_obsolete_reserve=2, upgrade_reserve=0)
        p.config['tasks'] = {k: k in ('breakthrough', 'refine', 'idle_select', 'harvest') for k in DEFAULTS['tasks']}
        s = state()
        s.update(bridge_revision=22, protection_policy=p.protection_policy(), needs_breakthrough=True,
                 owned_items={'material:1001': 25, 'material:1008': 0}, bound_items={},
                 breakthrough_preparation={'info': {'materials': [{'kind': 'material', 'id': 1008, 'count': 10, 'name': '目标材料'}]},
                                            'minimum_rate': 1, 'maximum_rate': 1},
                 breakthrough={'all_enough': False, 'bound_only_safe': True},
                 idle={'selected': {'difficulty': 0, 'tier': 0, 'stage': 0}},
                 refine_candidates=[{'kind': 'material', 'id': 1008, 'name': '目标材料'}],
                 refine_progress_per_level=100, refine_max_level=15,
                 refine_inputs=[{'id': 1001, 'kind': 'material', 'category': 'breakthrough_main',
                                 'value': 6, 'count': 25, 'obsolete': True, 'bound_only_safe': True}])
        return p, s

    def test_all_tasks_registered_once_and_moved_to_domains(self):
        self.assertEqual(set(TASK_ORDER), set(DEFAULTS['tasks']))
        self.assertEqual(len(TASK_ORDER), len(set(TASK_ORDER)))
        p = Planner()
        for task in TASK_ORDER:
            method = getattr(p, 'plan_' + task)
            self.assertTrue(method.__module__.startswith('fanxiu_assistant.modules.'))

    def test_old_config_migration_keeps_every_existing_choice(self):
        config = validate_config({'refine_reserve': 37, 'world_use_mirror': False, 'preserve_steam_tradable': True, 'resource_realm_use_token': False})
        self.assertEqual(config['refine_reserve'], 37)
        self.assertFalse(config['world_use_mirror'])
        self.assertTrue(config['growth_linked'])
        self.assertFalse(config['resource_realm_use_token'])
        self.assertEqual(validate_config(config), config)

    def test_breakthrough_uses_real_refine_preference_and_waits_for_snapshot(self):
        p, s = self.fixture()
        before = deepcopy(s['owned_items'])
        command = p.choose(s)
        self.assertEqual(command['kind'], 'refine')
        self.assertEqual(command['parent_kind'], 'breakthrough')
        self.assertEqual(command['params']['preferred_reward'], {'kind': 'material', 'id': 1008})
        self.assertLessEqual(sum(command['params']['materials'].values()), 23)
        p.observe_result(command, {'ok': True}, s)
        self.assertEqual(s['owned_items'], before)  # A request is not an inventory grant.
        self.assertFalse(p.growth_status(s)['refine']['target'] is None)
        confirmed = deepcopy(s)
        confirmed['owned_items']['material:1008'] = 10
        confirmed['breakthrough']['all_enough'] = True
        p.clock = lambda: 1100
        self.assertEqual(p.choose(confirmed)['kind'], 'breakthrough')

    def test_no_target_self_recycling_or_future_material_consumption(self):
        p, s = self.fixture()
        s['refine_inputs'] += [{'id': 1008, 'kind': 'material', 'value': 100, 'count': 200, 'bound_only_safe': True},
                               {'id': 1010, 'kind': 'material', 'category': 'breakthrough_main', 'value': 100, 'count': 10, 'obsolete': False, 'bound_only_safe': True}]
        s['upcoming_breakthrough'] = {'materials': [{'id': 1010, 'count': 10}]}
        p.config['refine_reserve'] = 20
        plan = p.refine_status(s)
        self.assertTrue(plan['ready'])
        self.assertNotIn('1008', plan['materials'])
        self.assertNotIn('1010', plan['materials'])

    def test_fixed_locks_and_game_exclusions_block_refine(self):
        for flag in ('lock', 'auto_fill_excluded', 'manual_only'):
            p, s = self.fixture()
            if flag == 'lock':
                p.config['manual_locks'] = ['material:1001']
                s['protection_policy'] = p.protection_policy()
            else:
                s['refine_inputs'][0][flag] = True
            self.assertFalse(p.refine_status(s)['ready'])

    def test_mixed_protected_donors_use_only_bound_budget(self):
        p, s = self.fixture()
        p.config['preserve_steam_tradable'] = True
        s['protection_policy'] = p.protection_policy()
        s['bound_items']['material:1001'] = 24
        s['refine_inputs'][0].update(steam_trade_known=True, steam_tradable=True)
        self.assertTrue(p.refine_status(s)['ready'])
        s['bound_items']['material:1001'] = 1
        self.assertFalse(p.refine_status(s)['ready'])

    def test_knapsack_finds_smallest_overpayment_under_item_budget(self):
        p, s = self.fixture()
        p.config['refine_max_items'] = 10
        s['refine_inputs'] = [{'id': mid, 'kind': 'herb', 'count': 10, 'value': value, 'category': 'herb', 'bound_only_safe': True}
                              for mid, value in ((1, 6), (2, 11))]
        s['owned_items'].update({'herb:1': 10, 'herb:2': 10})
        plan = p.refine_status(s)
        brute = min(6 * a + 11 * b for a, b in product(range(11), repeat=2) if a + b <= 10 and 6 * a + 11 * b >= 100)
        self.assertTrue(plan['ready'])
        self.assertEqual(plan['progress'], brute)

    def test_upgrade_and_alchemy_reserve_materials_against_refine(self):
        p, s = self.fixture()
        p.config['tasks'].update(upgrade=True, alchemy=True, pill=True)
        s['equipment'] = [{'id': 1, 'bound': True, 'level': 1, 'upgrade_needs': [{'kind': 'material', 'id': 1001, 'count': 20}]}]
        s['alchemy_recipes'] = [{'pill_id': 1, 'recipe_index': 0, 'useful': True, 'materials': [{'kind': 'material', 'id': 1001, 'count': 5}]}]
        self.assertFalse(p.refine_status(s)['ready'])
        self.assertEqual(p.spendable(s, 'material', 1001, consumer='upgrade'), 25)
        self.assertEqual(p.spendable(s, 'material', 1001, consumer='alchemy'), 5)
        self.assertEqual(p.spendable(s, 'material', 1001), 0)

    def test_refine_current_and_future_floors_overlap_without_spending_either(self):
        for protected, total, bound, ready in ((False, 32, 1, True), (True, 40, 32, True), (True, 40, 31, False)):
            with self.subTest(protected=protected, total=total, bound=bound):
                p, s = self.fixture()
                p.config.update(preserve_steam_tradable=protected, refine_reserve=3)
                s['breakthrough_preparation']['info']['materials'].append({'kind': 'material', 'id': 1001, 'count': 10, 'name': '当前用料'})
                s['owned_items']['material:1001'] = total
                s['bound_items']['material:1001'] = bound
                s['refine_inputs'][0].update(count=total, obsolete=False, future_need=15)
                s['protection_policy'] = p.protection_policy()
                plan = p.refine_status(s)
                self.assertEqual(plan['ready'], ready)
                if ready:
                    spent = plan['materials']['1001']
                    self.assertEqual(spent, 17)
                    self.assertGreaterEqual((bound if protected else total) - spent, max(10 + 3, 15))

    def test_no_speculative_refine_when_demand_satisfied(self):
        p, s = self.fixture()
        s['owned_items']['material:1008'] = 10
        self.assertFalse(p.refine_status(s)['ready'])
        self.assertIn('没有', p.refine_status(s)['message'])

    def test_explicit_invalid_preference_does_not_fall_back_to_random(self):
        p, s = self.fixture()
        p.config['refine_preferred_id'] = 999
        self.assertFalse(p.refine_status(s)['ready'])

    def test_stage_selection_covers_upgrade_and_stays_until_goal_changes(self):
        p, s = self.fixture()
        p.config['tasks']['breakthrough'] = False
        p.config['tasks']['upgrade'] = True
        s['equipment'] = [{'id': 1, 'bound': True, 'level': 1, 'upgrade_needs': [{'kind': 'material', 'id': 5, 'count': 2}]}]
        s['progress'] = {'cleared_ids': ['0_0_0', '0_0_1']}
        s['idle_reward_stages'] = [{'key': '0_0_0', 'items': ['material:5']}, {'key': '0_0_1', 'items': ['material:5']}]
        self.assertTrue(p.growth_status(s)['gathering_stage']['selected'])
        self.assertIsNone(p.plan_idle_select(s))

    def test_breakthrough_and_idle_share_one_target_without_priority_oscillation(self):
        from test_breakthrough import BreakthroughClarityTest
        p, s = BreakthroughClarityTest().base()
        p.config.update(preserve_steam_tradable=False, upgrade_reserve=0)
        p.config['tasks']['upgrade'] = True
        # One stage covers all breakthrough materials; another covers one plus
        # many upgrade shortages. Both planners must stick to the first stage.
        requirements = [{'kind':'material','id':2000+i,'count':1} for i in range(30)]
        s['equipment'] = [{'id':1,'bound':False,'level':1,'upgrade_needs':requirements}]
        s['character']['equip_slots'] = [1]
        s['idle_reward_stages'][2]['items'] = ['material:1007'] + [f'material:{2000+i}' for i in range(30)]
        chosen = p.plan_breakthrough(s)
        self.assertEqual(chosen[0]['key'], '1_2_7')
        self.assertEqual(p.plan_idle_select(s)[0]['key'], chosen[0]['key'])
        self.assertEqual(p.breakthrough_status(s)['gathering_stage']['key'], chosen[0]['key'])
        confirmed = deepcopy(s); confirmed['idle']['selected'] = {'difficulty':1,'tier':2,'stage':7}
        self.assertIsNone(p.plan_idle_select(confirmed))
        self.assertTrue(p.breakthrough_status(confirmed)['gathering_stage']['selected'])

    def test_lower_priority_shortages_never_outvote_one_breakthrough_material(self):
        p, s = self.fixture(); p.config['tasks']['upgrade'] = True
        s['equipment'] = [{'id':1,'bound':False,'level':1,'upgrade_needs':[
            {'kind':'material','id':2000+i,'count':1} for i in range(30)]}]
        s['progress'] = {'cleared_ids':['0_0_0','0_0_1']}
        s['idle_reward_stages'] = [
            {'key':'0_0_0','items':['material:1008']},
            {'key':'0_0_1','items':[f'material:{2000+i}' for i in range(30)]}]
        self.assertEqual(p.ledger(s).gathering_stage()['key'], '0_0_0')

    def test_gathering_moves_to_upgrade_pool_after_breakthrough_supply_and_honors_locks(self):
        p, s = self.fixture()
        p.config['tasks']['upgrade'] = True
        s['features']['battle_idle'] = True
        s['character']['equip_slots'] = [1]
        s['equipment'] = [{'id': 1, 'bound': False, 'level': 1,
                           'upgrade_needs': [{'kind': 'material', 'id': 1107, 'count': 1}]}]
        s['progress'] = {'cleared_ids': ['0_0_0', '0_0_1']}
        s['idle_reward_stages'] = [
            {'key': '0_0_0', 'items': ['material:1008']},
            {'key': '0_0_1', 'items': ['material:1107']}]
        self.assertEqual(p.ledger(s).gathering_stage()['key'], '0_0_0')
        supplied = deepcopy(s)
        supplied['owned_items']['material:1008'] = 10
        self.assertEqual(p.plan_idle_select(supplied)[0]['key'], '0_0_1')
        p.config['manual_locks'] = ['material:1107']
        self.assertIsNone(p.ledger(supplied).gathering_stage())
        p.config['manual_locks'] = []
        p.config['preserve_steam_tradable'] = True
        supplied['inventory_view'] = {'items': [{'key': 'material:1107', 'steam_trade_known': True,
                                                'steam_tradable': True, 'count': 1, 'bound_count': 0},
                                               {'key': 'material:1008', 'steam_trade_known': True,
                                                'steam_tradable': False, 'count': 10, 'bound_count': 0}]}
        supplied['owned_items']['material:1107'] = 1
        self.assertEqual(p.ledger(supplied).gathering_stage()['key'], '0_0_1')

    def test_material_synthesis_links_multiple_tiers(self):
        p, s = self.fixture()
        p.config['tasks'].update(breakthrough=False, upgrade=True, material_synth=True)
        p.config['material_synth_reserve'] = 0
        s['features']['synth'] = True
        s['equipment'] = [{'id': 1, 'bound': True, 'level': 1, 'upgrade_needs': [{'kind': 'material', 'id': 3, 'count': 1}]}]
        s['owned_items'] = {'material:1': 25}
        s['material_synthesis'] = [{'input_id': 1, 'output_id': 2, 'required_count': 5, 'count': 25, 'unlocked': True, 'bound_only_safe': True},
                                 {'input_id': 2, 'output_id': 3, 'required_count': 5, 'count': 0, 'unlocked': True, 'bound_only_safe': True}]
        command = p.plan_material_synth(s)
        self.assertEqual(command[0], {'material_id': 1, 'count': 5})

    def test_priority_bursts_return_to_fair_rotation(self):
        p, s = self.fixture()
        growth = p.growth_status(s)
        tasks, focus = ordered_tasks(15, s, p.config, growth, 3)
        self.assertFalse(focus)
        self.assertEqual(tasks[0], TASK_ORDER[15])

    def test_free_resource_realm_needs_no_token_or_override(self):
        p, s = self.fixture()
        s['resource_realm'] = {'enabled': True, 'portal': {'id': 'portal', 'type': 'material'}, 'free_remaining': 1}
        self.assertEqual(p.plan_resource_realm(s)[0], {'action': 'enter', 'portal_id': 'portal'})
        s['resource_realm']['free_remaining'] = 0
        self.assertIsNone(p.plan_resource_realm(s))
        s['resource_realm'].update(active=True, stale=True)
        self.assertEqual(p.plan_resource_realm(s)[0], {'action': 'status'})

    def test_domain_sources_are_in_acceptance_fingerprint(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            nested = root / 'fanxiu_assistant/modules'
            nested.mkdir(parents=True)
            module = nested / 'world.py'
            module.write_text('first', encoding='utf8')
            first = source_fingerprint(root)
            module.write_text('second', encoding='utf8')
            self.assertNotEqual(first, source_fingerprint(root))


    def test_normal_alchemy_prepares_one_feasible_recipe_and_replans(self):
        p, s = self.fixture()
        p.config['tasks'].update(alchemy=True, pill=True)
        s['owned_items'].update({'herb:7': 100, 'herb:8': 1})
        s['alchemy_recipes'] = [
            {'pill_id': 2, 'recipe_index': 0, 'useful': True, 'unlocked': True, 'bound_only_safe': True,
             'materials': [{'kind': 'herb', 'id': 8, 'count': 10}]},
            {'pill_id': 3, 'recipe_index': 0, 'useful': True, 'unlocked': True, 'bound_only_safe': True,
             'materials': [{'kind': 'herb', 'id': 7, 'count': 10}]}]
        demand = p.growth_status(s)['requirements']
        self.assertFalse(any(r['key'] == 'herb:8' for r in demand))
        self.assertEqual(p.plan_alchemy(s)[0]['pill_id'], 3)
        next_state = deepcopy(s)
        next_state['owned_items']['pill:3'] = 1
        self.assertEqual(p.ledger(next_state).alchemy_recipe['pill_id'], 2)

    def test_mirror_auto_uses_demand_and_manual_target_is_retained(self):
        p, s = self.fixture()
        p.config.update(world_use_mirror=True, world_mirror_target='auto')
        s['world'] = {'free_remaining': 0, 'mirror': {'id': 4003, 'unlocked': True, 'count': 3, 'cost': 1, 'bound_only_safe': True}}
        self.assertEqual(p.plan_world_explore(s)[0]['target_type'], 'material')
        p.config['world_mirror_target'] = 'relic'
        detail = p.breakthrough_status(s)
        command = p._preparation_gather(s, detail)
        self.assertEqual(command[0]['target_type'], 'relic')

    def test_satisfied_higher_claim_does_not_raise_lower_shortage_priority(self):
        p, s = self.fixture()
        ledger = p.ledger(s)
        self.assertEqual(ledger.shortage_priority({'breakthrough': 2, 'alchemy': 5}, 3), 20)


    def test_full_experience_skips_spring_but_keeps_other_points(self):
        p, s = self.fixture()
        s['character'].update(exp=100, exp_needed=100)
        s['world'] = {'points': [{'marker_id': 1, 'type': 'spring'}, {'marker_id': 2, 'type': 'stronghold'}]}
        self.assertEqual(p.plan_world_points(s)[0]['marker_id'], 2)
        s['character']['exp'] = 99
        self.assertEqual(p.plan_world_points(s)[0]['marker_id'], 1)

if __name__ == '__main__':
    unittest.main()
