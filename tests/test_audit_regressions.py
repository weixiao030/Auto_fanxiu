from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import time
from fanxiu_assistant.policy import Planner
import fanxiu_assistant.server as server


class FullAuditRegressions(TestCase):
    def test_failed_work_never_shortens_existing_cooldown(self):
        p = Planner(clock=lambda: 1000)
        for kind in ('collect', 'world_sync', 'home_relocate', 'partner_social'):
            p.due[kind] = 5000
            p.observe_result({'kind': kind, 'params': {}}, {'ok': False}, {})
            self.assertEqual(p.due[kind], 5000)
        for kind, key in (('realm_challenge', 'realm_retry_seconds'), ('partner_rescue', 'pvp_retry_seconds')):
            p.due[kind] = 1010
            p.observe_result({'kind': kind, 'params': {}}, {'ok': False}, {})
            self.assertEqual(p.due[kind], 1000 + p.config[key])
        p.due['breakthrough'] = 8000
        p.observe_result({'kind':'world_harvest','parent_kind':'breakthrough','params':{}}, {'ok':False}, {})
        self.assertEqual(p.due['breakthrough'], 8000)

    def test_protection_flags_wait_for_matching_policy(self):
        p = Planner()
        s = {'bridge_revision':21, 'protection_policy':p.protection_policy()}
        row = {'bound_only_safe':True}
        self.assertTrue(p.safe_flag(s, row))
        for field, value in (('preserve_steam_tradable',False), ('manual_locks',['material:4003']), ('preserve_tradable',True)):
            current = p.protection_policy()
            p.config[field] = value
            self.assertFalse(p.safe_flag(s,row))
            s['protection_policy'] = p.protection_policy()
            self.assertTrue(p.safe_flag(s,row))

    def test_exploration_free_paid_duplicates_restart_and_day_change(self):
        with TemporaryDirectory() as folder, patch.object(server,'RUNTIME',Path(folder)):
            c = server.Controller()
            def packet(free=11, results=None):
                return {'pid':77,'state':{'bridge_revision':21,'world':{'free_used':free,'daily_count':free}},'results':results or []}
            def acknowledge(rid, mode, free=11, day=None):
                c.pending = {'id':rid,'kind':'world_explore','label':'探索','params':{}}
                c.pending_at = time.monotonic()
                result = {'id':rid,'ok':True,'data':{'exploration_mode':mode}}
                if day: result['data']['exploration_day'] = day
                p = packet(free,[result]); c.bridge(p); return deepcopy(p)
            c.bridge(packet())
            self.assertEqual(c.daily['world_explore'],11)
            duplicate = acknowledge('paid-one','mirror')
            self.assertEqual(c.daily['world_explore'],12)
            c.bridge(duplicate)
            self.assertEqual(c.daily['world_explore'],12)
            acknowledge('free-twelve','free',12)
            self.assertEqual(c.daily['world_explore'],13)
            c = server.Controller(); c.bridge(packet(12))
            self.assertEqual(c.state['world']['daily_count'],13)
            self.assertEqual(c.state['assistant_daily']['world_explore'],13)
            c.daily = {'day':'1999-01-01','world_explore':100,'world_paid':90}
            c.bridge(packet(0))
            self.assertEqual(c.daily['world_explore'],0)
            acknowledge('late-previous-day','mirror',0,'1999-01-01')
            self.assertEqual(c.daily['world_explore'],0)

    def test_unknown_battle_confirmation_stops_and_cancels_queue(self):
        with TemporaryDirectory() as folder, patch.object(server,'RUNTIME',Path(folder)):
            c = server.Controller()
            p = {'pid':77,'state':{'bridge_revision':21},'results':[]}
            c.bridge(p); c.enabled=True; c.resume_requested=True
            c.pending={'id':'battle','kind':'challenge','label':'挑战','params':{'key':'0_0_1'}}
            c.pending_at=time.monotonic(); c.manual_queue.append('collect')
            p['results']=[{'id':'battle','ok':False,'data':{'unconfirmed':True}}]
            c.bridge(p)
            self.assertFalse(c.enabled); self.assertFalse(c.resume_requested)
            self.assertFalse(c.manual_queue); self.assertIsNone(c.pending)
