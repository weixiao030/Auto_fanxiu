"""Regression cases found while reviewing native rules and cross-module behavior."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch

from fanxiu_assistant import game_location as location, paths
from fanxiu_assistant.policy import Planner, DEFAULTS
from fanxiu_assistant.protection import command_keys, keys_overlap
from fanxiu_assistant.server import MIN_BRIDGE_REVISION
from fanxiu_assistant.supervisor import Supervisor


class ReviewTests(unittest.TestCase):
    def planner(self):
        p = Planner(clock=lambda: 1000)
        p.config.update(preserve_tradable=False, preserve_steam_tradable=False,
                        upgrade_reserve=0, alchemy_reserve=0, material_synth_reserve=0)
        p.config['tasks'] = {k: k in ('upgrade', 'alchemy', 'material_synth') for k in DEFAULTS['tasks']}
        return p

    def test_identity_accepts_future_versions_but_rejects_other_run_exe(self):
        with TemporaryDirectory() as temp:
            other, game = Path(temp)/'other', Path(temp)/'game'
            for folder, app in ((other, '123'), (game, location.APP_ID)):
                folder.mkdir(); (folder/'run.exe').touch()
                (folder/'release-manifest.json').write_text(json.dumps({'app_id':app,'version':'future'}), encoding='utf-8')
            with patch.object(location, 'process_images', return_value=[(1,other/'run.exe'),(2,game/'run.exe')]):
                self.assertEqual(location.detect_game(), game)
            self.assertFalse(location.is_game(other))
            with self.assertRaises(ValueError): location.remember_game(other)

    def test_damaged_metadata_requires_matching_steam_identity(self):
        with TemporaryDirectory() as temp:
            steamapps=Path(temp)/'steamapps';game=steamapps/'common/凡修';game.mkdir(parents=True)
            (game/'run.exe').touch();(game/'release-manifest.json').write_text('not json', encoding='utf-8')
            self.assertFalse(location.is_game(game))
            acf=steamapps/'appmanifest_3301840.acf'
            acf.write_text('"appid" "3301840" "installdir" "凡修"',encoding='utf-8')
            self.assertTrue(location.is_game(game))
            acf.write_text('"appid" "12" "installdir" "凡修"',encoding='utf-8')
            self.assertFalse(location.is_game(game))
            acf.write_text('"appid" "3301840" "installdir" "../凡修"',encoding='utf-8')
            self.assertFalse(location.is_game(game))

    def test_explicit_other_identity_is_not_overridden_by_steam_filename(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);game=root/'common/凡修';game.mkdir(parents=True);(game/'run.exe').touch()
            (root/'appmanifest_3301840.acf').write_text('"appid" "3301840" "installdir" "凡修"',encoding='utf-8')
            (game/'release-manifest.json').write_text('{"app_id":"123"}',encoding='utf-8')
            self.assertFalse(location.is_game(game))

    def test_page_lock_only_overlaps_observed_target_layer(self):
        s={'training_candidates':[{'id':9,'layer':3}], 'gongfa_options':[{'id':9,'training':{'target':4}}]}
        for kind,layer in [('gongfa_activate',0),('gongfa',3),('gongfa_accelerate',4)]:
            with self.subTest(kind=kind):
                touched=command_keys(kind,{'gongfa_id':9},s)
                self.assertEqual(touched,{f'gongfa:9:{layer}'})
                self.assertFalse(any(keys_overlap(key,'gongfa:9:2') for key in touched))
                self.assertTrue(any(keys_overlap(key,'gongfa:9') for key in touched))
                self.assertTrue(any(keys_overlap(key,f'gongfa:9:{layer}') for key in touched))
        self.assertEqual(command_keys('gongfa',{'gongfa_id':9},{}),{'gongfa:9'})

    def test_optional_alchemy_skips_locks_but_can_replenish_bound_stock(self):
        p=self.planner()
        s={'alchemy_recipes':[{'pill_id':1,'recipe_index':i,'useful':True,'materials':[{'kind':'herb','id':mid,'count':count}]} for i,mid,count in [(0,1,1),(1,2,3)]],
           'owned_items':{'herb:1':1,'herb:2':0},'bound_items':{}}
        p.config['manual_locks']=['herb:1']
        self.assertEqual(p.ledger(s).alchemy_recipe['recipe_index'],1)
        self.assertEqual([r['key'] for r in p.ledger(s).rows()],['herb:2'])
        p.config['manual_locks']=[];p.config['preserve_steam_tradable']=True
        self.assertEqual(p.ledger(s).alchemy_recipe['recipe_index'],0)
        p.config['preserve_steam_tradable']=False
        self.assertEqual(p.ledger(s).alchemy_recipe['recipe_index'],0)
        p.config['manual_locks']=['herb:1','herb:2']
        self.assertIsNone(p.ledger(s).alchemy_recipe)

    def test_required_breakthrough_still_reports_fixed_locked_material(self):
        p=self.planner();p.config['tasks']['breakthrough']=True;p.config['manual_locks']=['material:7']
        s={'bridge_revision':26,'needs_breakthrough':True,'character':{'level':9},'breakthrough_preparation':{'minimum_rate':1,'maximum_rate':1,'info':{'materials':[{'id':7,'count':2}]}}}
        rows=p.ledger(s).rows()
        self.assertTrue(any(r['key']=='material:7' and r['blocked'] and r['missing']==2 for r in rows))

    def test_unusable_equipment_cannot_dominate_synthesis_preservation(self):
        for weighted in (False,True):
            for blocked in ('fixed','game','trade'):
                with self.subTest(weighted=weighted,blocked=blocked):
                    p=self.planner();p.config['equip_use_weights']=weighted
                    gear=[{'id':i,'level':1,'slot':'head','quality':'common','fixed_stats':{'atk':5},'stats':{'atk':5},'bound':True} for i in range(1,5)]
                    gear[0].update(level=2,fixed_stats={'atk':9},stats={'atk':9})
                    if blocked=='fixed':p.config['manual_locks']=['equipment:1']
                    elif blocked=='game':gear[0]['locked']=True
                    else:p.config['preserve_tradable']=True;p.config['trade_rules']['equipment']['enabled']=True;gear[0]['bound']=False
                    s={'character':{'level':20,'equip_slots':[]},'equipment':gear}
                    eligible={eid for ids in p._synthesis_candidates(s).values() for eid in ids}
                    self.assertNotIn(1,eligible);self.assertNotIn(2,eligible)
                    self.assertEqual(eligible,{3,4})

    def material_fixture(self):
        return {'features':{'synth':True},'character':{'level':10,'equip_slots':[1,2]},
                'equipment':[{'id':i,'level':1,'bound':True,'upgrade_needs':[{'id':2,'kind':'material','count':2}]} for i in (1,2)],
                'owned_items':{'material:1':100,'material:2':0},
                'material_synthesis':[{'input_id':1,'output_id':2,'count':100,'required_count':5,'unlocked':True,'bound_only_safe':True}]}

    def test_conversion_aggregates_only_valid_upgrade_demands(self):
        for linked in (False,True):
            with self.subTest(linked=linked):
                p=self.planner();p.config.update(growth_linked=linked,material_synth_batch=100)
                s=self.material_fixture()
                self.assertEqual(p.plan_material_synth(deepcopy(s))[0]['count'],4)
                p.config['manual_locks']=['equipment:1']
                self.assertEqual(p.plan_material_synth(deepcopy(s))[0]['count'],2)
                s['equipment'][1]['level']=10
                self.assertIsNone(p.plan_material_synth(deepcopy(s)))
                s['equipment'][1]['level']=1;p.config['tasks']['upgrade']=False
                self.assertIsNone(p.plan_material_synth(deepcopy(s)))
                p.config['material_synth_demand_only']=False
                self.assertIsNotNone(p.plan_material_synth(deepcopy(s)))

    def test_shared_conversion_chain_reserves_stock_once(self):
        p=self.planner();p.config['tasks']['alchemy']=False
        s=self.material_fixture()
        s['equipment'][1]['upgrade_needs']=[{'id':3,'kind':'material','count':1}]
        s['owned_items'].update({'material:2':1,'material:3':0})
        s['material_synthesis'].append({'input_id':2,'output_id':3,'count':1,'required_count':5,'unlocked':True,'bound_only_safe':True})
        rows={r['key']:r for r in p.ledger(s).rows()}
        self.assertEqual(rows['material:2']['need'],7)
        self.assertEqual(rows['material:1']['need'],30)
        self.assertEqual(p.spendable(s,'material',1),70)

    def test_conversion_does_not_reserve_inputs_for_fixed_locked_output(self):
        p=self.planner();s=self.material_fixture();p.config['manual_locks']=['material:2']
        self.assertIsNone(p.plan_material_synth(s))
        self.assertNotIn('material:1',{r['key'] for r in p.ledger(s).rows()})

    def test_upgrade_honors_native_max_level_in_addition_to_character(self):
        p=self.planner();s=self.material_fixture();s['character']['level']=100;s['max_upgrade_level']=90
        for item in s['equipment']:item.update(level=90,upgrade_enough=True,bound_only_safe=True)
        self.assertIsNone(p.plan_upgrade(s));self.assertIsNone(p.plan_material_synth(deepcopy(s)))

    def test_waiting_status_never_claims_resources_met_or_restarts_queue(self):
        p=self.planner();p.config['auto_steam_update']=True
        state={'ready':False,'online':False,'bridge_revision':MIN_BRIDGE_REVISION,'login_queue':{'active':True,'ahead_count':214,'next_poll_seconds':23}}
        growth=p.growth_status(state)
        self.assertEqual(growth['phase'],'waiting');self.assertIn('214',growth['message']);self.assertIn('不是入场预计',growth['message'])
        c=SimpleNamespace(lock=threading.RLock(),planner=p,state=state,last_seen=100,pid=1,pending=None,resume_requested=True,enabled=False,maintenance={})
        supervisor=Supervisor(c,Path('.'))
        with patch.object(supervisor,'restart') as restart,patch('fanxiu_assistant.supervisor.steam_update_needed') as update:
            supervisor.step(101);restart.assert_not_called();update.assert_not_called()
        self.assertIn('排队',c.maintenance['message']);self.assertFalse(c.enabled)

    def test_artwork_and_backup_locations_are_private(self):
        self.assertTrue(paths.BACKUPS.is_relative_to(paths.DATA/'.private'))
        self.assertTrue(paths.INVENTORY_ICONS.is_relative_to(paths.DATA/'.private'))
