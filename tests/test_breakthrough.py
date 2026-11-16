import copy
import unittest

from fanxiu_assistant.policy import Planner, validate_config
from fanxiu_assistant.breakthrough import preparation


def fixture():
    p = Planner(clock=lambda: 1000)
    p.config['min_breakthrough_rate'] = 1.0
    p.config['tasks'] = {k: k == 'breakthrough' for k in p.config['tasks']}
    s = {'bridge_revision': 20, 'ready': True, 'online': True, 'tutorial_finished': True,
         'character': {'level': 25}, 'needs_breakthrough': True, 'features': {'explore': True, 'alchemy': True},
         'breakthrough': {'all_enough': True, 'bound_only_safe': True, 'final_rate': 0.6}, 'elixir_bonus': 0,
         'breakthrough_preparation': {'info': {'materials': [{'kind': 'material', 'id': 1099, 'count': 2}]},
                                      'minimum_rate': 0.6, 'maximum_rate': 0.6},
         'world': {'point_count': 0, 'free_remaining': 1, 'daily_count': 0},
         'pills': [{'id': 6021, 'name': '突破丹·练气', 'is_breakthrough': True, 'breakthrough_matching': True,
                    'bonus_min': 0.05, 'bonus_max': 0.05, 'count': 0, 'bound_count': 0,
                    'steam_trade_known': True, 'steam_tradable': True}],
         'alchemy_recipes': [{'pill_id': 6021, 'recipe_index': 0, 'is_breakthrough': True,
             'breakthrough_matching': True, 'unlocked': True, 'bound_only_safe': True,
             'materials': [{'kind': 'material', 'id': 1099, 'count': 3, 'name': '晨露砂'},
                           {'kind': 'herb', 'id': 7001, 'count': 10, 'name': '聚气草'}]}],
         'owned_items': {'material:1099': 100, 'herb:7001': 1},
         'bound_items': {'material:1099': 100, 'herb:7001': 1}}
    return p, s


class BreakthroughTest(unittest.TestCase):
    def test_full_confirmed_sequence_with_no_early_breakthrough_or_extra_pill(self):
        p, s = fixture()
        command = p.choose(s)
        self.assertEqual((command['kind'], command['parent_kind']), ('world_explore', 'breakthrough'))
        self.assertIsNone(p.choose(s), 'must wait for the action interval and acknowledgement')
        # Each transition represents a separate server-confirmed snapshot, not local mutation in production.
        p.clock = lambda: 1020
        s['owned_items']['herb:7001'] = s['bound_items']['herb:7001'] = 80
        command = p.choose(s)
        self.assertEqual(command['kind'], 'alchemy')
        self.assertEqual(command['params']['count'], 1)
        for index in range(8):
            p.clock = lambda index=index: 1040 + index * 10
            s['pills'][0].update(count=1, bound_count=1)
            self.assertEqual(p.choose(s)['kind'], 'pill')
            s['pills'][0].update(count=0, bound_count=0)
            s['elixir_bonus'] = (index + 1) * 0.05
            s['breakthrough_preparation'].update(minimum_rate=0.6+s['elixir_bonus'], maximum_rate=0.6+s['elixir_bonus'])
            p.clock = lambda index=index: 1044 + index * 10
            action = p.choose(s)
            self.assertEqual(action['kind'], 'breakthrough' if index == 7 else 'alchemy')
        self.assertIsNone(p.plan_alchemy(s))
        self.assertIsNone(p.plan_pill(s))

    def test_failure_bonus_reaches_target_without_spending_extra_pills(self):
        p, s = fixture()
        p.config['min_breakthrough_rate'] = 0.6
        s['breakthrough_preparation'].update(minimum_rate=0.6, maximum_rate=0.6, failure_bonus=0.2)
        s['pills'][0].update(count=10, bound_count=10)
        detail = preparation(p.config, s)
        self.assertEqual(detail['failure_bonus'], 0.2)
        self.assertEqual(p.choose(s)['kind'], 'breakthrough')
        self.assertIsNone(p.plan_pill(s))
        self.assertIsNone(p.plan_alchemy(s))

    def test_subswitches_cannot_be_bypassed_by_generic_pill_or_alchemy(self):
        for key, setup in [('breakthrough_auto_find', 'missing'), ('breakthrough_auto_craft', 'craft'),
                           ('breakthrough_auto_use', 'pill')]:
            p, s = fixture()
            if setup == 'craft': s['owned_items']['herb:7001'] = s['bound_items']['herb:7001'] = 80
            if setup == 'pill': s['pills'][0].update(count=1, bound_count=1)
            p.config[key] = False
            self.assertIsNone(p.plan_breakthrough(s), key)
            s['pills'][0]['useful'] = s['alchemy_recipes'][0]['useful'] = True
            self.assertIsNone(p.plan_pill(s))
            self.assertIsNone(p.plan_alchemy(s))
        p, s = fixture(); p.config['breakthrough_auto_raise'] = False
        p.config['min_breakthrough_rate'] = 0.6
        self.assertEqual(p.choose(s)['kind'], 'breakthrough')

    def test_fixed_locks_steam_mixed_stocks_and_source_selection(self):
        p, s = fixture()
        s['pills'][0].update(count=3, bound_count=1)
        self.assertEqual(p.choose(s)['kind'], 'pill', 'pill use has an explicit binding selector')
        p, s = fixture(); s['pills'][0].update(count=3, bound_count=0)
        self.assertNotEqual((p.plan_breakthrough(s) or [None, None, None, None])[-1], 'pill')
        s['owned_items']['herb:7001'] = 100; s['bound_items']['herb:7001'] = 80
        s['alchemy_recipes'][0]['bound_only_safe'] = False
        self.assertNotEqual((p.plan_breakthrough(s) or [None, None, None, None])[-1], 'alchemy')
        p.config['manual_locks'] = ['pill:6021', 'herb:7001']
        self.assertIsNone(p.plan_pill(s))
        self.assertEqual(preparation(p.config, s)['shortages'][-1]['usable'], 0)

    def test_minimum_random_probability_and_guaranteed_first_breakthrough(self):
        p, s = fixture()
        s['elixir_bonus'] = 0.5
        s['breakthrough_preparation'].update(minimum_rate=0.9, maximum_rate=1)
        self.assertNotEqual((p.choose(s) or {}).get('kind'), 'breakthrough')
        p, s = fixture(); s['guaranteed_breakthrough'] = True
        s['breakthrough_preparation'].update(minimum_rate=1, maximum_rate=1)
        self.assertEqual(p.choose(s)['kind'], 'breakthrough')

    def test_preparation_reserves_resources_from_other_consumers(self):
        p, s = fixture()
        s['owned_items']['herb:7001'] = s['bound_items']['herb:7001'] = 80
        self.assertEqual(p.spendable(s, 'herb', 7001), 0)
        self.assertEqual(p.spendable(s, 'material', 1099), 74)  # 8*3 plus 2 for breakthrough
        p.config['breakthrough_auto_raise'] = False
        self.assertEqual(p.spendable(s, 'herb', 7001), 80)
        self.assertEqual(p.spendable(s, 'material', 1099), 98, 'base materials stay reserved without pill automation')

    def test_prepares_before_full_exp_but_never_uses_pills_early(self):
        p, s = fixture(); s['needs_breakthrough'] = False
        s['owned_items']['herb:7001'] = s['bound_items']['herb:7001'] = 80
        self.assertEqual(p.choose(s)['kind'], 'alchemy')
        s['pills'][0].update(count=1, bound_count=1)
        self.assertIsNone(p.plan_breakthrough(s))
        self.assertEqual(preparation(p.config, s)['phase'], 'experience')

    def test_exploration_budget_and_mirror_switch_are_respected(self):
        p, s = fixture(); p.config['world_use_mirror'] = False; s['world'].update(free_remaining=0, mirror={'count': 5, 'cost': 1, 'unlocked': True, 'bound_only_safe': True})
        self.assertIsNone(p.plan_breakthrough(s))
        self.assertIn('没有可采集资源', p.breakthrough_status(s)['message'])
        p.config['world_use_mirror'] = True
        self.assertEqual(p.plan_breakthrough(s)[0]['target_type'], 'herb')
        s['world']['daily_count'] = p.config['world_daily_limit']
        self.assertIsNone(p.plan_breakthrough(s))

    def test_realm_changes_stop_old_recipe_and_failures_back_off(self):
        p, s = fixture(); s['pills'][0]['breakthrough_matching'] = False
        self.assertIsNone(p.choose(s))
        p, s = fixture(); command = p.choose(s)
        p.observe_result(command, {'ok': False, 'detail': 'server busy'}, s)
        p.clock = lambda: 1020
        self.assertIsNone(p.choose(s))
        self.assertGreaterEqual(p.due['breakthrough'], 1030)

    def test_controls_validate_and_target_does_not_undercut_minimum(self):
        for value in (-1, 1.01, float('nan'), True):
            with self.assertRaises(ValueError): validate_config({'breakthrough_target_rate': value})
        for key in ('raise', 'find', 'craft', 'use'):
            with self.assertRaises(ValueError): validate_config({f'breakthrough_auto_{key}': 'true'})
        p, s = fixture(); p.config['breakthrough_target_rate'] = 0.1
        p.config['min_breakthrough_rate'] = 0.6
        self.assertEqual(preparation(p.config, s)['target_rate'], 0.6)


class BreakthroughClarityTest(unittest.TestCase):
    def base(self):
        p, s = fixture()
        p.config.update(min_breakthrough_rate=0.5, breakthrough_auto_raise=False)
        p.config['tasks'].update(idle_select=True, harvest=True)
        s['features']['battle_idle'] = True
        s['breakthrough']['all_enough'] = False
        s['breakthrough_preparation'] = {'minimum_rate':0.55,'maximum_rate':0.55,'info':{'materials':[
            {'kind':'material','id':1007,'count':15,'name':'灵气石后'},
            {'kind':'material','id':1008,'count':10,'name':'聚灵草后'},
            {'kind':'material','id':1009,'count':5,'name':'凝气丹后'}]}}
        s['owned_items'] = {'material:1007':7,'material:1008':0,'material:1009':2}
        s['bound_items'] = dict(s['owned_items'])
        s['progress'] = {'cleared_ids':['1_0_5','1_2_7','2_0_5']}
        s['idle'] = {'selected':{'difficulty':2,'tier':0,'stage':5}}
        s['idle_reward_stages'] = [{'key':'1_0_5','items':['material:1007','material:1008','material:1009']},
            {'key':'1_2_7','items':['material:1007','material:1008','material:1009']},
            {'key':'2_0_5','items':['material:1010']}]
        return p, s

    def test_screenshot_case_reports_the_real_blocker_and_switches_drop_pool(self):
        p, s = self.base()
        d = p.breakthrough_status(s)
        self.assertTrue(d['rate_ready']); self.assertTrue(d['experience_ready'])
        self.assertFalse(d['materials_ready'])
        self.assertEqual([r['missing'] for r in d['shortages']], [8,10,3])
        self.assertEqual(d['gathering_stage']['key'], '1_2_7')
        command = p.choose(s)
        self.assertEqual(command['kind'], 'idle_select')
        self.assertTrue(command['params']['breakthrough_prepare'])
        self.assertEqual(p.plan_idle_select(s)[0]['key'], '1_2_7')
        self.assertEqual(p.spendable(s, 'material', 1007), 0)

    def test_stays_on_working_stage_and_restores_growth_after_materials_arrive(self):
        p, s = self.base()
        s['idle']['selected'] = {'difficulty':1,'tier':0,'stage':5}
        self.assertEqual(p.breakthrough_status(s)['gathering_stage']['key'], '1_0_5')
        self.assertIsNone(p.plan_idle_select(s))
        for r in s['breakthrough_preparation']['info']['materials']:
            s['owned_items'][f"material:{r['id']}"] = s['bound_items'][f"material:{r['id']}"] = r['count']
        s['breakthrough']['all_enough'] = True
        self.assertEqual(p.plan_breakthrough(s)[1], 'breakthrough')
        self.assertEqual(p.plan_idle_select(s)[0]['key'], '2_0_5')

    def test_pinned_stage_switches_missing_metadata_and_locks_are_respected(self):
        for option in ('pinned','find_off','harvest_off','no_metadata','locked'):
            p, s = self.base()
            if option == 'pinned': p.config['idle_stage'] = '2_0_5'
            if option == 'find_off': p.config['breakthrough_auto_find'] = False
            if option == 'harvest_off': p.config['tasks']['harvest'] = False
            if option == 'no_metadata': s.pop('idle_reward_stages')
            if option == 'locked': p.config['manual_locks'] = ['material:1007','material:1008','material:1009']
            self.assertIsNone(p.breakthrough_status(s)['gathering_stage'], option)

    def test_low_rate_without_pills_waits_and_random_rate_uses_minimum(self):
        p, s = self.base(); p.config['min_breakthrough_rate'] = 0.6
        s['breakthrough_preparation'].update(minimum_rate=0.55,maximum_rate=1)
        for r in s['breakthrough_preparation']['info']['materials']:
            s['owned_items'][f"material:{r['id']}"] = s['bound_items'][f"material:{r['id']}"] = r['count']
        s['breakthrough']['all_enough'] = True
        self.assertFalse(p.breakthrough_status(s)['rate_ready'])
        self.assertIsNone(p.plan_breakthrough(s))

    def test_old_settings_preserve_effective_goal_and_new_ui_has_one_threshold(self):
        for enabled, expected in [(False,0.5),(True,0.7)]:
            cfg = validate_config({'min_breakthrough_rate':0.5,'breakthrough_target_rate':0.7,'breakthrough_auto_raise':enabled})
            self.assertEqual(cfg['min_breakthrough_rate'], expected)
            self.assertEqual(cfg['breakthrough_target_rate'], expected)
        cfg = validate_config({'breakthrough_settings_version':2,'min_breakthrough_rate':0.65,'breakthrough_target_rate':1})
        self.assertEqual(cfg['breakthrough_target_rate'],0.65)


if __name__ == '__main__': unittest.main()
