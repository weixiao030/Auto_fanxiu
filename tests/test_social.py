from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import tempfile
import time
import unittest
from fanxiu_assistant.policy import Planner, DEFAULTS, validate_config
from fanxiu_assistant import server


class SocialTests(unittest.TestCase):
    def setUp(self):
        self.p=Planner(clock=lambda:1000)
        self.p.config['preserve_tradable']=True
        self.p.config['preserve_steam_tradable']=False
        self.s={'ready':True,'online':True,'tutorial_finished':True,'character':{'level':18,'injury':0},
                'features':{'furnace':True,'explore':True},'world':{'captured':False,'furnace_free':1,'home':{'score':10}},
                'assistant_daily':{}}
        self.now=time.time()*1000

    def choose(self, kind):
        self.p.config['tasks']={k:k==kind for k in DEFAULTS['tasks']}
        return self.p.choose(self.s)

    def point(self):
        return {'marker_id':1,'type':'player','target_token':'identity','expires_at':self.now+60000,
                'power_assessment':'优势','furnace_unlocked':True,'home_score':20,'home_safe':True}

    def test_capture_requires_known_assessment_protection_and_empty_slot(self):
        for change in ({'power_assessment':''},{'power_assessment':'危险'},{'furnace_unlocked':False},{'furnace_protected_until':self.now+30000},{'expires_at':self.now-1}):
            self.s['world']['points']=[dict(self.point(),**change)]
            self.assertIsNone(self.choose('player_capture'),change)
        self.s['world']['points']=[self.point()]
        self.s['world']['furnace_free']=0
        self.assertIsNone(self.choose('player_capture'))
        self.s['world']['furnace_free']=1
        self.assertEqual(self.choose('player_capture')['params']['target_token'],'identity')

    def test_pvp_daily_limit_injury_and_occupation_gain(self):
        self.s['world']['points']=[self.point()]
        self.s['character']['injury']=1
        self.assertIsNone(self.choose('player_occupy'))
        self.s['character']['injury']=0
        self.s['assistant_daily']['player_occupy']=3
        self.assertIsNone(self.choose('player_occupy'))
        self.s['assistant_daily'].clear()
        self.s['world']['home']['score']=100
        self.assertIsNone(self.choose('player_occupy'))
        self.s['world']['home']['score']=10
        self.assertIsNotNone(self.choose('player_occupy'))

    def test_social_does_not_randomly_invite_or_accept(self):
        self.s['partner']={'synced_at':self.now,'received_invites':[{'id':1,'target':'123','expires_at':self.now+30000}]}
        self.assertIsNone(self.choose('partner_social'))
        self.p.config.update(partner_target='456',partner_auto_accept=True)
        self.assertIsNone(self.choose('partner_social'))
        self.p.config['partner_target']='123'
        self.assertEqual(self.choose('partner_social')['params']['invite_id'],1)

    def test_self_captor_blocks_talisman_and_battle_rescue(self):
        self.s['partner'] = {'has_partner': True, 'synced_at': self.now, 'target': 'partner',
            'self_is_captor': True, 'capture': {'capture_id': 'captivity', 'expires_at': self.now + 60000},
            'rescue': {'count': 5, 'cost': 2, 'bound_only_safe': True}}
        for mode in ('talisman', 'battle', 'talisman_first'):
            self.p.config['partner_rescue_mode'] = mode
            self.assertIsNone(self.choose('partner_rescue'), mode)
        self.s['partner']['self_is_captor'] = False
        self.assertIsNotNone(self.choose('partner_rescue'))

    def test_partner_practice_respects_server_and_user_limits(self):
        self.s['partner']={'has_partner':True,'synced_at':self.now,'daily':{'practice_used':1,'practice_limit':2}}
        self.p.config['partner_practice_limit']=1
        self.assertIsNone(self.choose('partner_practice'))
        self.p.config['partner_practice_limit']=2
        self.assertIsNotNone(self.choose('partner_practice'))

    def capture(self):
        self.s['world'].update(captured=True,capture={'capture_id':'opaque','master_token':'token','attempted_escape':False},
            escape_prop={'count':3,'bound_only_safe':False},bounty_prop={'count':3,'bound_only_safe':False})

    def test_escape_preserves_tradable_and_does_not_repeat_free_attempt(self):
        self.capture()
        cmd=self.choose('slave_escape')
        self.assertEqual(cmd['params']['action'],'escape_free')
        self.p.observe_result(cmd,{'ok':False},self.s)
        self.assertIsNone(self.choose('slave_escape'))
        self.p=Planner(clock=lambda:1000)
        self.p.config['preserve_tradable']=True
        self.p.config['preserve_steam_tradable']=False
        self.s['capture_actions']={'opaque':{'escape_free':True}}
        self.assertIsNone(self.choose('slave_escape'))

    def test_escape_talisman_and_bounty_obey_reserve(self):
        self.capture();self.s['world']['escape_prop']['bound_only_safe']=True
        self.p.config['escape_prop_reserve']=3
        self.p.config['escape_mode']='talisman_only'
        self.assertIsNone(self.choose('slave_escape'))
        self.p.config['escape_prop_reserve']=0
        self.assertEqual(self.choose('slave_escape')['params']['action'],'escape_talisman')
        self.p.last_action=0
        self.assertIsNone(self.choose('bounty_publish'))
        self.p.config['bounty_publish_captured']=True
        self.assertIsNone(self.choose('bounty_publish'))

    def test_bounty_excludes_self_busy_expired_and_player_when_disabled(self):
        self.p.config['bounty_allow_players'] = False
        event=dict(id=2,event_type='player',target_token='id',power_assessment='优势',remaining_uses=1,expires_at=self.now+30000)
        self.s['bounty']={'synced_at':self.now,'daily_claim_limit':5,'events':[event]}
        self.assertIsNone(self.choose('bounty_claim'))
        event['event_type']='monster_clear'
        for key,value in [('is_owner',True),('busy',True),('remaining_uses',0)]:
            old=event.get(key);event[key]=value;self.assertIsNone(self.choose('bounty_claim'));event[key]=old
        event['remaining_uses']=1
        self.assertIsNotNone(self.choose('bounty_claim'))

    def test_suspended_multiplayer_is_never_requested(self):
        self.s['multiplayer']={'enabled':True,'suspended':True}
        self.p.config['mp_auto_enter']=True
        self.assertIsNone(self.choose('multiplayer_realm'))

    def test_active_multiplayer_blocks_other_gameplay(self):
        self.s['multiplayer']={'enabled':True,'active':True,'entry_id':'x','hp_percent':20,'can_extract':True}
        self.assertIsNone(self.choose('social_sync'))
        cmd=self.choose('multiplayer_realm')
        self.assertEqual(cmd['params']['action'],'extract')

    def test_multiplayer_unknown_hp_waits_but_duration_still_extracts(self):
        self.s['multiplayer'] = dict(enabled=True, active=True, entry_id='x', can_extract=True,
            can_escape=True, battle_id='b', hp_known=False, hp_percent=None)
        self.assertIsNone(self.choose('multiplayer_realm'))
        self.s['multiplayer']['elapsed_seconds'] = 901
        self.assertEqual(self.choose('multiplayer_realm')['params']['action'], 'extract')

    def test_multiplayer_native_admission_does_not_resubmit_or_interrupt(self):
        self.p.config['mp_auto_enter'] = True
        self.s['multiplayer'] = dict(enabled=True, active=True, admission_pending=True,
            state='reserving', prepared=True, available=True, free_entries=1, realm_key='r')
        self.assertIsNone(self.choose('multiplayer_realm'))
        self.assertIsNone(self.choose('social_sync'))
        self.s['multiplayer'] = dict(enabled=True, native_busy=True)
        self.assertIsNone(self.choose('multiplayer_realm'))

    def test_multiplayer_hidden_view_resumes_before_using_stale_health(self):
        self.s['multiplayer'] = dict(enabled=True, active=True, entry_id='x', needs_resume=True,
            stale=True, hp_percent=1, can_extract=True)
        self.assertEqual(self.choose('multiplayer_realm')['params']['action'], 'resume')
        self.s['multiplayer']['command_pending'] = True
        self.assertIsNone(self.choose('multiplayer_realm'))

    def test_multiplayer_event_only_uses_current_enabled_option(self):
        self.p.config['mp_event_option'] = 'safe'
        self.s['multiplayer'] = dict(enabled=True, active=True, entry_id='x', state='choosing',
            event={'id':'event', 'options':[]})
        self.assertIsNone(self.choose('multiplayer_realm'))
        self.s['multiplayer']['event']['options'] = ['safe']
        self.assertEqual(self.choose('multiplayer_realm')['params']['option_id'], 'safe')
        self.s['multiplayer']['stale'] = True
        self.assertIsNone(self.choose('multiplayer_realm'))

    def test_multiplayer_unknown_binding_blocks_entry(self):
        self.s['multiplayer']={'enabled':True,'prepared':True,'available':True,'key_count':1,'realm_key':'realm','key_item':'material:4008'}
        self.s['inventory_view']={'items':[{'key':'material:4008','trade_category':'consumable','quality':'common'}]}
        self.p.config['mp_auto_enter']=True
        self.assertIsNone(self.choose('multiplayer_realm'))
        self.p.config['preserve_tradable']=False
        self.assertEqual(self.choose('multiplayer_realm')['params']['action'],'enter')

    def test_multiplayer_free_entry_does_not_touch_locked_or_unknown_key(self):
        self.p.config['mp_auto_enter'] = True
        self.p.config['manual_locks'] = ['material:4008']
        self.s['multiplayer'] = {'enabled': True, 'prepared': True, 'available': True,
            'key_item': 'material:4008', 'key_count': 0, 'realm_key': 'realm', 'free_entries': 1}
        self.assertEqual(self.choose('multiplayer_realm')['params']['action'], 'enter')
        self.p.clock = lambda: 1100
        self.s['multiplayer']['free_entries'] = 0
        self.assertIsNone(self.choose('multiplayer_realm'))

    def test_multiplayer_mixed_key_uses_only_bound_budget(self):
        self.p.config['preserve_steam_tradable'] = True
        self.p.config['mp_auto_enter'] = True
        self.s['multiplayer'] = {'enabled': True, 'prepared': True, 'available': True,
            'key_item': 'material:4008', 'key_count': 3, 'realm_key': 'realm'}
        self.s['bound_items'] = {'material:4008': 1}
        self.assertEqual(self.choose('multiplayer_realm')['params']['action'], 'enter')
        self.p.clock = lambda: 1100
        self.s['bound_items']['material:4008'] = 0
        self.assertIsNone(self.choose('multiplayer_realm'))

    def test_identifiers_remain_strings_and_invalid_values_rejected(self):
        self.assertEqual(validate_config({'partner_target':'76561199999999999'})['partner_target'],'76561199999999999')
        for value in (123,{},'１２３','abc'):
            with self.assertRaises(ValueError):validate_config({'partner_target':value})

    def test_attempt_deduplication_survives_controller_restart(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(server,'RUNTIME',Path(temp)):
            c=server.Controller()
            c.record_attempt({'kind':'slave_escape','params':{'capture_id':'opaque','action':'escape_free'}})
            c.record_attempt({'kind':'player_capture','params':{}})
            c2=server.Controller()
            self.assertTrue(c2.capture_actions['opaque']['escape_free'])
            self.assertEqual(c2.daily['player_capture'],1)

    def test_unconfirmed_battle_cannot_be_resumed_by_supervisor(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(server,'RUNTIME',Path(temp)):
            c=server.Controller();c.enabled=True;c.resume_requested=True
            c.pending={'id':'one','kind':'partner_rescue','params':{},'label':'test'}
            c.bridge({'pid':1,'state':{},'results':[{'id':'one','ok':False,'data':{'unconfirmed':True}}]})
            self.assertFalse(c.resume_requested)
            self.assertFalse(c.enabled)


if __name__=='__main__':unittest.main()
