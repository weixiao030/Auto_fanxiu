import copy
import unittest
from fanxiu_assistant.policy import Planner, DEFAULTS, validate_config


def state():
    return {'ready': True, 'online': True, 'tutorial_finished': True, 'pending': 0,
            'character': {'level': 12, 'equip_slots': [1], 'wuxing': 30, 'exp': 20, 'exp_needed': 100},
            'slots': ['weapon'], 'equipment': [], 'features': {'dungeon': True, 'explore': True}}


class PolicyTest(unittest.TestCase):
    def test_server_busy_applies_shared_backoff_without_stopping_session(self):
        p=self.planner('collect');s=state()
        p.observe_result({'kind':'world_sync'}, {'ok':False,'detail':'server busy'}, s)
        self.assertIsNone(p.choose(s))
        self.assertIn('服务器繁忙',p.reason)
        p.clock=lambda:1031
        self.assertEqual(p.choose(s)['kind'],'collect')

    def planner(self, task):
        p = Planner(clock=lambda: 1000)
        for rule in p.config['trade_rules'].values(): rule['enabled']=True
        p.config['equip_use_weights']=True
        p.config['equip_keep_weapon_type']=False
        p.config['upgrade_reserve']=20
        p.config['preserve_steam_tradable'] = False
        p.config['preserve_tradable'] = True
        p.config['tasks'] = {key: key == task for key in DEFAULTS['tasks']}
        return p

    def test_no_work_for_offline_blocked_tutorial_and_battle(self):
        for changes in ({'online': False}, {'network_blocked': True}, {'tutorial_finished': False}, {'battle': True}, {'pending': 1}):
            p = self.planner('collect')
            s = state(); s.update(changes)
            self.assertIsNone(p.choose(s))

    def test_equipment_real_attributes_level_and_protection(self):
        p = self.planner('equip'); s = state()
        s['equipment'] = [{'id': 1, 'bound': True, 'slot': 'weapon_sword', 'level': 5, 'stats': {'atk': 10}},
                          {'id': 2, 'bound': True, 'slot': 'weapon_bow', 'level': 10, 'stats': {'atk': 20}},
                          {'id': 3, 'bound': True, 'slot': 'weapon_sword', 'level': 30, 'stats': {'atk': 999}}]
        command = p.choose(s)
        self.assertEqual(command['params'], {'item_id': 2, 'slot_idx': 0})
        p = self.planner('equip'); p.config['protected_equipment'] = [1]
        self.assertIsNone(p.choose(s))

    def test_breakthrough_requires_materials_rate_and_unlock(self):
        p = self.planner('breakthrough'); s = state(); s.update(needs_breakthrough=True, breakthrough={'all_enough': True, 'bound_only_safe': True, 'final_rate': 0.5})
        self.assertIsNone(p.choose(s))
        s['elixir_bonus'] = 0.4
        self.assertEqual(p.choose(s)['kind'], 'breakthrough')
        p = self.planner('breakthrough'); s['realm_locked'] = True
        self.assertIsNone(p.choose(s))

    def test_gacha_reserve_is_not_spent(self):
        p = self.planner('gacha'); p.config['reserve_wuxing'] = 20; s = state(); s['gacha_cost'] = 3
        self.assertEqual(p.choose(s)['params']['count'], 3)
        p = self.planner('gacha'); s['character']['wuxing'] = p.config['reserve_wuxing']
        self.assertIsNone(p.choose(s))

    def test_gacha_uses_native_unlock_and_batch_limit(self):
        s = state()
        s.update(gacha_batch_limit=15, gacha_batch_unlock_level=10)
        s['character'].update(level=7, wuxing=30)
        self.assertEqual(self.planner('gacha').choose(s)['params']['count'], 1)
        s['character']['level'] = 10
        self.assertEqual(self.planner('gacha').choose(s)['params']['count'], 15)
        s['gacha_batch_unlock_level'] = 20
        self.assertEqual(self.planner('gacha').choose(s)['params']['count'], 1)
        s['gacha_batch_unlock_level'] = 10
        s['gacha_batch_limit'] = 4
        self.assertEqual(self.planner('gacha').choose(s)['params']['count'], 4)
        p = self.planner('gacha'); p.config['reserve_wuxing'] = 29
        self.assertEqual(p.choose(s)['params']['count'], 1)

    def test_upgrade_skips_unaffordable_item_and_keeps_reserve(self):
        s = state()
        s['character']['equip_slots'] = [1, 2]
        s['bound_items'] = {'material:100': 25}
        s['owned_items'] = {'material:100': 25}
        s['equipment'] = [
            {'id': 1, 'level': 1, 'bound': True, 'bound_only_safe': True, 'upgrade_enough': True,
             'upgrade_needs': [{'kind': 'material', 'id': 100, 'count': 8}]},
            {'id': 2, 'level': 2, 'bound': True, 'bound_only_safe': True, 'upgrade_enough': True,
             'upgrade_needs': [{'kind': 'material', 'id': 100, 'count': 3}]},
        ]
        for preserve in (True, False):
            p = self.planner('upgrade'); p.config['preserve_tradable'] = preserve
            self.assertEqual(p.choose(s)['params'], {'item_id': 2})
        s['bound_items']['material:100'] = 22
        self.assertIsNone(self.planner('upgrade').choose(s))
        s['bound_items']['material:100'] = 25
        s['equipment'][1]['bound'] = False
        self.assertIsNone(self.planner('upgrade').choose(s))
        s['equipment'][1]['bound'] = True
        p = self.planner('upgrade'); p.config['protected_equipment'] = [2]
        self.assertIsNone(p.choose(s))

    def test_synthesis_feedback_matches_eligible_inventory(self):
        p=self.planner('synth');s=state()
        s['equipment']=[{'id':i,'bound':False,'quality':'common','slot':'ring','level':1,'stats':{'atk':i}} for i in range(7)]
        detail=p.synthesis_status(s)
        self.assertFalse(detail['ready']);self.assertEqual(detail['preserved_tradable_or_unknown'],7)
        self.assertIn('交易保护开启',detail['message']);self.assertIsNone(p.plan_synth(s))
        for item in s['equipment']:item['bound']=True
        detail=p.synthesis_status(s)
        self.assertTrue(detail['ready']);self.assertIsNotNone(p.plan_synth(s))
        s['features']['synth']=False
        self.assertFalse(p.synthesis_status(s)['ready']);self.assertIsNone(p.plan_synth(s))

    def test_pack_requires_opt_out_of_protection_and_honors_budget(self):
        p=self.planner('resource_pack');s=state();s.update(bridge_revision=12,resource_pack_remaining=2,
            resource_pack_recipes=[{'input_kind':'herb','input_id':7001,'size':4,'cost':5,'unbound_count':115}])
        self.assertIsNone(p.choose(s))
        p.config['preserve_tradable']=False;p.config['resource_pack_batch']=3
        self.assertEqual(p.plan_resource_pack(s)[0]['count'],2)
        s['resource_pack_recipes'][0]['unbound_count']=104
        self.assertIsNone(p.plan_resource_pack(s))
        s['resource_pack_recipes'][0]['unbound_count']=115;p.config['resource_pack_materials']=[999]
        self.assertIsNone(p.plan_resource_pack(s))
        p.config['resource_pack_materials']=[];s['bridge_revision']=11
        self.assertIsNone(p.plan_resource_pack(s))

    def test_pack_and_unpack_cannot_form_a_resource_loss_loop(self):
        p=self.planner('open_pack');s=state()
        s['materials']=[{'id':1,'use_type':'resource_pack','bound_count':1,'count':1}]
        self.assertIsNotNone(p.plan_open_pack(s))
        p.config['tasks']['resource_pack']=True
        self.assertIsNone(p.plan_open_pack(s))
        s['materials'].append({'id':2,'use_type':'equipment_box','bound_count':1,'count':1})
        self.assertEqual(p.plan_open_pack(s)[0]['material_id'],2)

    def test_idle_never_selects_uncleared_stage(self):
        p = self.planner('idle_select'); s = state(); s['features']['battle_idle'] = True
        s['progress'] = {'cleared_ids': ['0_0_2', '0_0_9', '0_1_0']}
        self.assertEqual(p.choose(s)['params']['key'], '0_1_0')
        p = self.planner('idle_select'); p.config['idle_stage'] = '9_9_9'
        self.assertIsNone(p.choose(s))

    def test_failed_challenge_backs_off(self):
        p = self.planner('challenge'); s = state(); s['next_dungeon'] = {'key': '0_1_0', 'required_level': 10}
        command = p.choose(s)
        p.observe_result(command, {'ok': False, 'data': {'won': False}}, s)
        self.assertIsNone(p.choose(s))

    def test_synth_preserves_equipped_protected_and_best(self):
        p = self.planner('synth'); p.config['protected_equipment'] = [3]; s = state()
        s['equipment'] = [{'id': i, 'bound': True, 'slot': 'weapon_sword', 'quality': 'common', 'level': 5, 'stats': {'atk': i}} for i in range(1, 9)]
        ids = p.choose(s)['params']['item_ids']
        self.assertEqual(len(ids), 5)
        self.assertFalse({1, 3, 8} & set(ids))

    def test_validation_rejects_nan_unknown_and_wrong_boolean(self):
        for raw in ({'interval': float('nan')}, {'interval': 0}, {'tasks': {'gacha': 'true'}}, {'password': 'x'}, {'protected_equipment': ['1']}):
            with self.assertRaises(ValueError): validate_config(raw)

    def test_tradable_or_unknown_equipment_is_never_used(self):
        for bound in (False, None):
            p = self.planner('equip'); s = state()
            s['equipment'] = [{'id': 2, 'slot': 'weapon', 'bound': bound, 'level': 5, 'stats': {'atk': 900}}]
            self.assertIsNone(p.choose(s))
            p = self.planner('synth')
            s['equipment'] = [{'id': i, 'bound': bound, 'slot': 'weapon', 'quality': 'common', 'level': 5, 'stats': {'atk': 1}} for i in range(2, 12)]
            self.assertIsNone(p.choose(s))

    def test_unknown_or_mixed_breakthrough_source_is_never_consumed(self):
        for flag in (False, None):
            p = self.planner('breakthrough'); s = state()
            s.update(needs_breakthrough=True, breakthrough={'all_enough': True, 'final_rate': 1, 'bound_only_safe': flag})
            self.assertIsNone(p.choose(s))

    def test_only_explicitly_bound_boxes_are_opened(self):
        p = self.planner('open_pack'); s = state()
        s['materials'] = [{'id': 100, 'count': 99, 'use_type': 'equipment_box'}]
        self.assertIsNone(p.choose(s))
        s['materials'][0]['bound_count'] = 1
        self.assertEqual(p.choose(s)['params']['material_id'], 100)

    def test_mixed_gongfa_pages_are_skipped(self):
        p = self.planner('gongfa'); s = state()
        s['training_candidates'] = [{'id': 6, 'layer': 2, 'allowed': True, 'bound_only_safe': False}]
        self.assertIsNone(p.choose(s))

    def test_tradable_protection_is_optional_and_on_by_default(self):
        self.assertTrue(validate_config({})['preserve_steam_tradable']);self.assertFalse(validate_config({})['preserve_tradable'])
        p = self.planner('equip'); s = state()
        s['equipment'] = [{'id': 2, 'bound': False, 'slot': 'weapon', 'level': 5, 'stats': {'atk': 99}}]
        self.assertIsNone(p.choose(s))
        p.config['preserve_tradable'] = False
        self.assertEqual(p.choose(s)['params']['item_id'], 2)

    def test_locked_equipment_is_kept_with_protection_off(self):
        p = self.planner('synth'); p.config['preserve_tradable'] = False; s = state()
        s['equipment'] = [{'id': i, 'bound': True, 'locked': True, 'slot': 'weapon', 'quality': 'common', 'level': 5, 'stats': {'atk': 1}} for i in range(2, 12)]
        self.assertIsNone(p.choose(s))


if __name__ == '__main__': unittest.main()
