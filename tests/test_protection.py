from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from fanxiu_assistant.policy import Planner, DEFAULTS, validate_config
from fanxiu_assistant.protection import available, trade_preserved, locked, command_keys
import fanxiu_assistant.server as server


class ProtectionTests(unittest.TestCase):
    def test_requested_defaults_and_quality_validation(self):
        c=validate_config({})
        self.assertEqual({k for k,v in c['trade_rules'].items() if v['enabled']},{'consumable','gongfa','fashion'})
        self.assertTrue(all(len(r['qualities'])==9 for r in c['trade_rules'].values()))
        self.assertFalse(c['equip_use_weights']);self.assertTrue(c['equip_keep_weapon_type'])
        self.assertTrue(c['tasks']['equip']);self.assertEqual(c['inventory_refresh_seconds'],60)
        for invalid in ({'inventory_refresh_seconds':4},{'inventory_refresh_seconds':3601},{'manual_locks':['material:1:2']},{'trade_rules':{'material':{'enabled':True,'qualities':['bogus']}}}):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):validate_config(invalid)

    def test_category_quality_unknown_and_main_switch(self):
        c=deepcopy(DEFAULTS);c.update(preserve_steam_tradable=False,preserve_tradable=True)
        for quality in c['trade_rules']['consumable']['qualities']:
            self.assertTrue(trade_preserved(c,'pill',{'quality':quality}))
            self.assertFalse(trade_preserved(c,'equipment',{'quality':quality}))
        c['trade_rules']['material']={'enabled':True,'qualities':['epic']}
        self.assertFalse(trade_preserved(c,'material',{'rarity':'common'}))
        self.assertTrue(trade_preserved(c,'material',{'rarity':'epic'}))
        self.assertTrue(trade_preserved(c,'material',{}))
        self.assertTrue(trade_preserved(c,'material',{'use_type':'equipment_box','rarity':'common'}))
        c['preserve_tradable']=False
        self.assertFalse(trade_preserved(c,'pill',{}))

    def test_steam_and_category_switches_are_independent_union(self):
        c=deepcopy(DEFAULTS)
        internal={'steam_trade_known':True,'steam_tradable':False,'quality':'common'}
        external={**internal,'steam_tradable':True}
        self.assertTrue(c['preserve_steam_tradable']);self.assertFalse(c['preserve_tradable'])
        self.assertTrue(trade_preserved(c,'material',external))
        self.assertFalse(trade_preserved(c,'pill',internal))
        self.assertTrue(trade_preserved(c,'pill',{}))
        self.assertFalse(trade_preserved(c,'equipment',{}))
        c['preserve_tradable']=True
        self.assertTrue(trade_preserved(c,'pill',internal))
        self.assertTrue(trade_preserved(c,'material',external))
        c['preserve_steam_tradable']=False
        self.assertFalse(trade_preserved(c,'material',external))
        self.assertTrue(trade_preserved(c,'pill',internal))
        c['preserve_tradable']=False
        self.assertFalse(trade_preserved(c,'pill',{}))
        self.assertFalse(trade_preserved(c,'material',external))

    def test_steam_stock_selector_and_lock_priority(self):
        c=deepcopy(DEFAULTS)
        row={'key':'material:4004','steam_trade_known':True,'steam_tradable':True}
        s={'owned_items':{'material:4004':10},'bound_items':{'material:4004':9},'inventory_view':{'items':[row]}}
        self.assertEqual(available(c,s,'material',4004),9)
        self.assertEqual(available(c,s,'material',4004,selector=True),9)
        row['steam_tradable']=False
        self.assertEqual(available(c,s,'material',4004),10)
        c['manual_locks']=['material:4004']
        self.assertEqual(available(c,s,'material',4004,selector=True),0)
        for key in ('preserve_tradable','preserve_steam_tradable'):
            with self.subTest(key=key),self.assertRaises(ValueError):validate_config({key:1})

    def test_new_steam_box_without_config_label_is_blocked(self):
        p=Planner()
        box={'id':2705,'count':2,'bound_count':0,'use_type':'equipment_box','steam_trade_known':True,'steam_tradable':True}
        s={'materials':[box]}
        self.assertIsNone(p.plan_open_pack(s))
        box['bound_count']=1
        self.assertEqual(p.plan_open_pack(s)[0]['material_id'],2705)
        p.config['manual_locks']=['material:2705']
        self.assertIsNone(p.plan_open_pack(s))

    def test_binding_selector_and_mixed_stock(self):
        c=deepcopy(DEFAULTS);s={'owned_items':{'pill:1':5},'bound_items':{'pill:1':2}}
        self.assertEqual(available(c,s,'pill',1,selector=True),2)
        self.assertEqual(available(c,s,'pill',1),2)
        s['owned_items']['pill:1']=2
        self.assertEqual(available(c,s,'pill',1),2)
        c['manual_locks']=['pill:1'];c['preserve_tradable']=False
        self.assertEqual(available(c,s,'pill',1,selector=True),0)
        self.assertTrue(locked({'manual_locks':['gongfa:1:2']},'gongfa',1,2))
        self.assertFalse(locked({'manual_locks':['gongfa:1:2']},'gongfa',1,3))

    def test_bound_first_keeps_unbound_floor_and_checks_batch_budget(self):
        from fanxiu_assistant.protection import requirements_allowed
        c = deepcopy(DEFAULTS)
        s = {'owned_items': {'material:4006': 29}, 'bound_items': {'material:4006': 28},
             'inventory_view': {'items': [{'key': 'material:4006', 'steam_trade_known': True, 'steam_tradable': True}]}}
        req = [{'id': 4006, 'count': 3}]
        self.assertEqual(available(c, s, 'material', 4006), 28)
        self.assertTrue(requirements_allowed(c, s, req, count=9))
        self.assertFalse(requirements_allowed(c, s, req, count=10))
        s['bound_items']['material:4006'] = 2
        self.assertFalse(requirements_allowed(c, s, req))
        s['bound_items']['material:4006'] = 999
        self.assertEqual(available(c, s, 'material', 4006), 29)
        c['manual_locks'] = ['material:4006']
        self.assertFalse(requirements_allowed(c, s, req))
        c['manual_locks'] = []
        c['preserve_steam_tradable'] = False
        self.assertEqual(available(c, s, 'material', 4006), 29)

    def equipment_state(self):
        return {'character':{'level':20,'equip_slots':[1]},'slots':['weapon'],'equipment':[
            {'id':1,'slot':'weapon_sword','level':10,'fixed_stats':{'atk':10,'hp':20},'stats':{'atk':1000}},
            {'id':2,'slot':'weapon_sword','level':12,'fixed_stats':{'atk':11,'hp':19},'stats':{'atk':3000}},
            {'id':3,'slot':'weapon_bow','level':12,'fixed_stats':{'atk':30,'hp':40},'stats':{'atk':9000}},
            {'id':4,'slot':'weapon_sword','level':12,'fixed_stats':{'atk':11,'hp':20},'stats':{'atk':1}}]}

    def test_fixed_upgrade_ignores_affixes_and_keeps_weapon_type(self):
        p=Planner();s=self.equipment_state()
        self.assertEqual(p.plan_equip(s)[0],{'item_id':4,'slot_idx':0})
        s['equipment'].pop();self.assertIsNone(p.plan_equip(s))
        p.config['equip_keep_weapon_type']=False
        self.assertEqual(p.plan_equip(s)[0]['item_id'],3)

    def test_fixed_upgrade_fills_empty_and_respects_both_locked_sides(self):
        p=Planner();s=self.equipment_state();s['character']['equip_slots']=[-1]
        self.assertIsNotNone(p.plan_equip(s))
        s['character']['equip_slots']=[1];p.config['manual_locks']=['equipment:4']
        self.assertIsNone(p.plan_equip(s))
        p.config['manual_locks']=['equipment:1'];p.config['equip_use_weights']=True
        self.assertIsNone(p.plan_equip(s))
        p.config['manual_locks']=[]
        self.assertEqual(p.plan_equip(s)[0]['item_id'],2)

    def test_synthesis_keeps_incomparable_fixed_upgrades(self):
        p=Planner();s=self.equipment_state();s['character']['equip_slots']=[]
        s['equipment'][1]['fixed_stats']['atk']=12
        for eq in s['equipment']:eq.update(quality='common')
        ids={x for group in p._synthesis_candidates(s).values() for x in group}
        self.assertFalse({2,3,4}&ids)
        self.assertIn(1,ids)

    def test_every_consumption_key_is_blocked_even_with_master_off(self):
        fixtures=[
            ('equip',{'item_id':2,'slot_idx':0},{'character':{'equip_slots':[1]}},'equipment:1'),
            ('upgrade',{'item_id':2},{'equipment':[{'id':2,'upgrade_needs':[{'id':9,'kind':'herb','count':1}]}]},'herb:9'),
            ('synth',{'item_ids':[1,2,3]},{},'equipment:2'),
            ('breakthrough',{}, {'breakthrough':{'info':{'materials':[{'id':9,'count':1}]}}},'material:9'),
            ('open_pack',{'material_id':9},{},'material:9'),
            ('material_synth',{'material_id':9},{},'material:9'),
            ('resource_pack',{'kind':'herb','material_id':9},{},'herb:9'),
            ('alchemy',{'pill_id':1,'recipe_index':0},{'alchemy_recipes':[{'pill_id':1,'recipe_index':0,'materials':[{'kind':'herb','id':9}]}]},'herb:9'),
            ('pill',{'pill_id':9},{},'pill:9'),
            ('refine',{'materials':{'9':2}},{'refine_inputs':[{'id':9,'kind':'herb'}]},'herb:9'),
            ('world_forge',{'materials':{'9':2}},{'refine_inputs':[{'id':9,'kind':'material'}]},'material:9'),
            ('gongfa',{'gongfa_id':9},{},'gongfa:9:2'),
            ('gongfa_activate',{'gongfa_id':9},{},'gongfa:9:0'),
            ('gongfa_accelerate',{'gongfa_id':9},{},'gongfa:9:3'),
            ('home_relocate',{}, {},'material:4001'),
            ('world_explore',{'use_rumor':True},{'world':{'rumor':{'id':9}}},'material:9'),
            ('partner_rescue',{'action':'rescue_talisman'},{'partner':{'rescue':{'id':9}}},'material:9'),
            ('bounty_publish',{}, {'world':{'bounty_prop':{'id':9}}},'material:9'),
            ('slave_escape',{'action':'escape_talisman'},{'world':{'escape_prop':{'id':9}}},'material:9'),
            ('multiplayer_realm',{'action':'enter'},{'multiplayer':{'key_item':'material:9'}},'material:9')]
        for kind,params,state,key in fixtures:
            with self.subTest(kind=kind):
                p=Planner(clock=lambda:1000);p.config['preserve_tradable']=False;p.config['manual_locks']=[key]
                p.config['tasks']={k:k==kind for k in DEFAULTS['tasks']}
                setattr(p,'plan_'+kind,lambda s,params=params:(params,'',1))
                state.update(ready=True,online=True,tutorial_finished=True)
                self.assertIsNone(p.choose(state));self.assertTrue(command_keys(kind,params,state))


class LockApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.runtime=Path(self.temp.name)
        self.patcher=patch.object(server,'RUNTIME',self.runtime);self.patcher.start()
        self.icons_patch=patch.object(server,'INVENTORY_ICONS',self.runtime/'.private/inventory-icons');self.icons_patch.start()
        self.c=server.Controller();self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.http.controller=self.c;self.http.daemon_threads=True
        self.thread=Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join(3);self.patcher.stop();self.icons_patch.stop();self.temp.cleanup()

    def post(self,path,data):
        request=urllib.request.Request(self.base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-CSRF-Token':self.c.csrf,'Origin':self.base})
        with urllib.request.urlopen(request) as response:return json.load(response)

    def test_locks_persist_across_reset_import_and_restart(self):
        self.post('/api/lock',{'key':'material:1','locked':True})
        self.post('/api/config',{'replace':{'preserve_tradable':False,'manual_locks':[]}})
        self.post('/api/config',{'replace':{}})
        self.assertEqual(self.c.planner.config['manual_locks'],['material:1'])
        self.assertEqual(server.Controller().planner.config['manual_locks'],['material:1'])
        self.post('/api/lock',{'key':'material:1','locked':False})
        self.assertEqual(server.Controller().planner.config['manual_locks'],[])

    def test_sent_conflict_rejected_unsent_cancelled_unrelated_allowed(self):
        self.c.pending={'id':'x','kind':'synth','params':{'item_ids':[1,2,3]}};self.c.pending_sent=True
        with self.assertRaises(urllib.error.HTTPError) as caught:self.post('/api/lock',{'key':'equipment:2','locked':True})
        self.assertEqual(caught.exception.code,409);self.assertEqual(self.c.planner.config['manual_locks'],[])
        self.post('/api/lock',{'key':'material:9','locked':True});self.assertIsNotNone(self.c.pending)
        self.c.pending_sent=False;self.c.manual=True
        self.post('/api/lock',{'key':'equipment:2','locked':True})
        self.assertIsNone(self.c.pending);self.assertFalse(self.c.manual)

    def test_inflight_gongfa_lock_uses_exact_observed_layer(self):
        self.c.state={'training_candidates':[{'id':9,'layer':3}]}
        self.c.pending={'id':'x','kind':'gongfa','params':{'gongfa_id':9,'action':'start_training'}}
        self.c.pending_sent=True
        self.post('/api/lock',{'key':'gongfa:9:2','locked':True})
        self.assertIsNotNone(self.c.pending)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('/api/lock',{'key':'gongfa:9:3','locked':True})
        self.assertEqual(caught.exception.code,409)
        self.c.pending_sent=False
        self.post('/api/lock',{'key':'gongfa:9:3','locked':True})
        self.assertIsNone(self.c.pending)

    def test_legacy_protection_survives_reset_and_explicit_unlock_works(self):
        self.c.planner.config['protected_equipment']=[42]
        self.post('/api/config',{'replace':{}})
        self.assertIn('equipment:42',self.c.planner.config['manual_locks'])
        self.post('/api/lock',{'key':'equipment:42','locked':False})
        self.assertNotIn('equipment:42',self.c.planner.config['manual_locks'])

    def test_field_edits_merge_with_latest_protection_and_nested_rules(self):
        self.post('/api/config', {'edit': {'path': ['preserve_steam_tradable'], 'value': False}})
        self.post('/api/config', {'edit': {'path': ['interval'], 'value': 9}})
        self.assertFalse(self.c.planner.config['preserve_steam_tradable'])
        self.post('/api/config', {'edit': {'path': ['preserve_steam_tradable'], 'value': True}})
        self.post('/api/config', {'edit': {'path': ['trade_rules', 'material', 'enabled'], 'value': True}})
        self.assertTrue(self.c.planner.config['preserve_steam_tradable'])
        self.assertTrue(self.c.planner.config['trade_rules']['material']['enabled'])
        self.assertEqual(self.c.planner.config['interval'], 9)

    def test_old_full_config_and_malformed_edits_cannot_override_protection(self):
        for packet in ({}, {'preserve_steam_tradable': False},
                       {'edit': {'path': [], 'value': False}},
                       {'edit': {'path': ['tasks', 'missing'], 'value': False}},
                       {'edit': {'path': ['manual_locks', '0'], 'value': False}},
                       {'edit': {'path': ['interval'], 'value': 0}},
                       {'edit': {'path': ['interval'], 'value': 3}, 'replace': {}}):
            with self.subTest(packet=packet), self.assertRaises(urllib.error.HTTPError) as caught:
                self.post('/api/config', packet)
            self.assertEqual(caught.exception.code, 400)
            self.assertTrue(self.c.planner.config['preserve_steam_tradable'])
        self.assertEqual(self.c.planner.config['interval'], 3)

    def test_refresh_generation_and_icon_path_validation(self):
        for resource in ('app.js','inventory.js','style.css'):
            with urllib.request.urlopen(self.base+'/'+resource) as response:
                self.assertEqual(response.read(),(server.ROOT/'web'/resource).read_bytes())
        initial=self.c.inventory_generation
        self.assertEqual(self.post('/api/inventory/refresh',{})['generation'],initial+1)
        icons=server.INVENTORY_ICONS;icons.mkdir(parents=True);name='a'*64+'.png';(icons/name).write_bytes(b'png-fixture')
        with urllib.request.urlopen(self.base+'/icons/'+name) as response:self.assertEqual(response.read(),b'png-fixture')
        for path in ['/icons/../config.json','/icons/config.json','/icons/'+'z'*64+'.png']:
            with self.subTest(path=path),self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(self.base+path)
