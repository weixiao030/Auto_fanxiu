import unittest
from fanxiu_assistant.policy import Planner, DEFAULTS, QUALITIES, validate_config
from test_policy import state


class ExpansionTest(unittest.TestCase):
    def planner(self, task, preserve=False):
        p = Planner(clock=lambda: 1000)
        for rule in p.config['trade_rules'].values(): rule['enabled']=True
        p.config['equip_use_weights']=True
        p.config['equip_keep_weapon_type']=False
        p.config['preserve_steam_tradable'] = False
        p.config['preserve_tradable'] = preserve
        p.config['tasks'] = {k: k == task for k in DEFAULTS['tasks']}
        return p

    def test_nine_quality_levels_round_trip(self):
        self.assertEqual(len(QUALITIES), 9)
        for quality in QUALITIES:
            self.assertEqual(validate_config({'synth_max_quality': quality})['synth_max_quality'], quality)

    def test_world_free_exploration_does_not_require_props(self):
        p = self.planner('world_explore', True); s = state()
        s['world'] = {'free_remaining': 1, 'daily_count': 0, 'point_count': 0}
        self.assertEqual(p.choose(s)['params'], {})

    def test_world_daily_limit_and_pending_event_block_exploration(self):
        for change in ({'daily_count': 50}, {'pending_event': {'event_id': 9}}, {'point_count': 20}):
            p = self.planner('world_explore'); s = state()
            s['world'] = {'free_remaining': 5, **change}
            self.assertIsNone(p.choose(s))

    def test_world_mixed_props_respected_when_protection_toggles(self):
        s = state(); s['world'] = {'free_remaining': 0, 'rumor': {'count': 5, 'cost': 2, 'bound_only_safe': False}}
        self.assertIsNone(self.planner('world_explore', True).choose(s))
        self.assertEqual(self.planner('world_explore').choose(s)['params'], {'use_rumor': True})

    def exploration_fixture(self):
        p = self.planner('world_explore')
        p.config['preserve_steam_tradable'] = True
        p.config['world_use_mirror'] = True
        s = state()
        s['bridge_revision'] = 20
        s['world'] = {'free_remaining': 0, 'daily_count': 11, 'point_count': 0,
                      'rumor': {'id': 4006, 'count': 0, 'cost': 3, 'bound_only_safe': False},
                      'mirror': {'id': 4003, 'count': 7, 'cost': 1, 'spendable_count': 0, 'unlocked': True, 'bound_only_safe': False}}
        s['bound_items'] = {'material:4003': 0, 'material:4006': 0}
        s['inventory_view'] = {'items': [{'key': 'material:4003', 'id': 4003,
            'count': 7, 'bound_count': 0, 'steam_trade_known': True, 'steam_tradable': True}]}
        return p, s

    def test_exploration_explains_insufficient_bound_stock_without_dispatching(self):
        p, s = self.exploration_fixture()
        detail = p.world_exploration_status(s)
        self.assertFalse(detail['ready'])
        self.assertIsNone(p.choose(s))
        self.assertIn('免费探索已用完', detail['message'])
        self.assertIn('流言：数量不足', detail['message'])
        self.assertIn('绑定份不足', detail['message'])
        self.assertEqual(detail['props'][1]['bound_count'], 0)

    def test_exploration_status_refreshes_after_free_reset_or_protection_change(self):
        p, s = self.exploration_fixture()
        s['world']['free_remaining'] = 1
        self.assertEqual(p.world_exploration_status(s)['mode'], 'free')
        self.assertEqual(p.choose(s)['params'], {})
        p, s = self.exploration_fixture()
        p.config['preserve_steam_tradable'] = False
        s['world']['mirror'].update(bound_only_safe=True, spendable_count=7)  # Latest bridge has revalidated the new rule.
        self.assertEqual(p.world_exploration_status(s)['mode'], 'mirror')
        self.assertTrue(p.choose(s)['params']['use_mirror'])

    def test_exploration_skips_locked_rumor_and_uses_allowed_mirror(self):
        p, s = self.exploration_fixture()
        s['world']['rumor'].update(count=5, bound_only_safe=True)
        s['world']['mirror'].update(bound_only_safe=True, spendable_count=7)
        p.config['manual_locks'] = ['material:4006']
        self.assertTrue(p.choose(s)['params']['use_mirror'])
        self.assertIn('固定锁定', p.world_exploration_status(s)['props'][0]['reason'])

    def test_exploration_status_reports_limits_event_and_disabled_props(self):
        for changes, expected in (({'daily_count': 50}, '今日探索上限'),
                                  ({'point_count': 20}, '坐标已达上限'),
                                  ({'pending_event': {'event_id': 4}}, '当前奇遇')):
            p, s = self.exploration_fixture()
            s['world'].update(changes)
            self.assertIn(expected, p.world_exploration_status(s)['message'])
            self.assertIsNone(p.choose(s))
        p, s = self.exploration_fixture()
        p.config['world_use_mirror'] = False
        self.assertIn('窥真镜：未启用', p.world_exploration_status(s)['message'])

    def test_exploration_spends_mixed_bound_stock_and_preserves_unbound_floor(self):
        p, s = self.exploration_fixture()
        s['world']['rumor'].update(count=29, bound_count=28, cost=3, spendable_count=28, bound_only_safe=True)
        self.assertEqual(p.choose(s)['params'], {'use_rumor': True})
        self.assertEqual(p.world_exploration_status(s)['mode'], 'rumor')
        # Reserve is the remaining total stock; it need not hold back a bound unit.
        s['world']['rumor'].update(count=4, bound_count=3, spendable_count=3)
        self.assertEqual(p.plan_world_explore(s)[0], {'use_rumor': True})
        # Enough total stock does not permit crossing the protected unbound floor.
        s['world']['rumor'].update(bound_count=2, spendable_count=2, bound_only_safe=False)
        self.assertIsNone(p.plan_world_explore(s))
        self.assertIn('绑定份不足', p.world_exploration_status(s)['message'])
        s['world']['rumor'].update(bound_count=3, spendable_count=3, bound_only_safe=True)
        p.config['manual_locks'] = ['material:4006']
        self.assertIsNone(p.plan_world_explore(s))

    def test_pruning_keeps_current_home_and_breakthrough_realm(self):
        p = self.planner('world_prune'); s = state()
        s['world'] = {'point_count': 20, 'points': [{'marker_id': 1, 'type': 'empty', 'is_current': True},
                        {'marker_id': 2, 'type': 'breakthrough_realm'}, {'marker_id': 3, 'type': 'empty'}]}
        self.assertEqual(p.choose(s)['params']['marker_id'], 3)

    def test_forge_never_spends_breakthrough_or_upgrade_materials(self):
        p = self.planner('refine'); s = state(); s['idle'] = {'selected': {'stage': 0}}
        s['refine_inputs'] = [{'id': 1, 'category': 'breakthrough_main', 'value': 50, 'count': 100},
                             {'id': 2, 'category': 'equipment_upgrade', 'value': 50, 'count': 100},
                             {'id': 3, 'category': 'herb', 'value': 4, 'count': 45}]
        self.assertEqual(p.choose(s)['params']['materials'], {'3': 25})

    def test_synthesis_accepts_mixed_slots_and_all_high_qualities(self):
        p = self.planner('synth'); p.config['synth_max_quality'] = 'treasure'; s = state(); s['synth_count'] = 5
        s['equipment'] = [{'id': i, 'slot': 'ring' if i % 2 else 'neck', 'quality': 'innate', 'level': i,
                           'stats': {'atk': i}, 'bound': False} for i in range(2, 12)]
        command = p.choose(s)
        self.assertEqual(len(command['params']['item_ids']), 5)
        self.assertFalse({10, 11} & set(command['params']['item_ids']))

    def test_active_training_does_not_restart_or_consume_another_page(self):
        p = self.planner('gongfa'); s = state()
        s['character']['gongfa'] = {'training': {'6': {'state': 'running'}}}
        s['training_candidates'] = [{'id': 7, 'layer': 2, 'allowed': True}]
        self.assertIsNone(p.choose(s))

    def test_dangerous_realm_requires_config_and_failed_marker_backs_off(self):
        p = self.planner('realm_challenge'); p.config['realm_allow_danger'] = False; s = state()
        s['world'] = {'points': [{'marker_id': 9, 'type': 'breakthrough_realm', 'difficulty': 'DANGER'}]}
        self.assertIsNone(p.choose(s))
        p.config['realm_allow_danger'] = True
        command = p.choose(s); self.assertEqual(command['params']['marker_id'], 9)
        p.observe_result(command, {'ok': False}, s)
        self.assertGreater(p.item_due[('realm_challenge', 9)], 1000)

    def test_alchemy_retains_material_reserves_and_skips_mixed_inventory(self):
        p = self.planner('alchemy', True); s = state()
        s['alchemy_recipes'] = [{'pill_id': 6021, 'recipe_index': 0, 'useful': True, 'bound_only_safe': False,
                               'materials': [{'kind': 'herb', 'id': 7001, 'count': 10}]}]
        s['bound_items'] = {'herb:7001': 100}
        s['owned_items'] = s['bound_items']  # This fixture models pure-bound stock.
        self.assertIsNone(p.choose(s))
        s['alchemy_recipes'][0]['bound_only_safe'] = True
        s['bound_items']['herb:7001'] = 14
        self.assertIsNone(p.choose(s))
        s['bound_items']['herb:7001'] = 15
        self.assertEqual(p.choose(s)['params']['count'], 1)


    def test_material_synthesis_only_fills_equipped_upgrade_needs(self):
        p=self.planner('material_synth');p.config.update(upgrade_reserve=20, material_synth_reserve=20);p.config['tasks']['upgrade']=True;s=state();s['features']['synth']=True
        s['material_synthesis']=[{'input_id':1,'output_id':2,'required_count':5,'count':60,'unlocked':True,'bound_only_safe':False}]
        s['equipment']=[{'id':1,'level':1,'upgrade_needs':[{'kind':'material','id':2,'count':2}]}]
        s['owned_items']={'material:2':0}
        self.assertEqual(p.choose(s)['params'],{'material_id':1,'count':5})
        p=self.planner('material_synth',True)
        self.assertIsNone(p.choose(s))
        p=self.planner('material_synth');p.config.update(upgrade_reserve=20, material_synth_reserve=20);p.config['tasks']['upgrade']=True;s['owned_items']['material:2']=100
        self.assertIsNone(p.choose(s))
        s['owned_items']['material:2']=0;s['material_synthesis'][0]['count']=24
        self.assertIsNone(p.choose(s))

    def test_relocation_uses_improvement_and_source_checks(self):
        p=self.planner('home_relocate');s=state()
        s['world']={'relocate':{'count':2,'bound_only_safe':False},'home':{'score':10},'points':[
            {'marker_id':1,'type':'herb','home_score':10.1,'home_safe':True},
            {'marker_id':2,'type':'ordinary','home_score':20,'home_safe':False},
            {'marker_id':3,'type':'ordinary','home_score':14,'home_safe':True}]}
        self.assertEqual(p.choose(s)['params']['marker_id'],3)
        self.assertIsNone(self.planner('home_relocate',True).choose(s))
        s['world']['captured']=True
        self.assertIsNone(self.planner('home_relocate').choose(s))

    def test_furnace_collection_waits_for_exp_room(self):
        p=self.planner('furnace_absorb');s=state();s['features']['furnace']=True;s['furnace']={'exp_pool':20}
        self.assertEqual(p.choose(s)['kind'],'furnace_absorb')
        s['character']['exp']=s['character']['exp_needed']
        self.assertIsNone(self.planner('furnace_absorb').choose(s))


if __name__ == '__main__': unittest.main()
