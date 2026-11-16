"""SocialPlans: single-step intentions, confirmed by the game bridge."""
import math
import time
from ..settings import QUALITIES
from ..protection import available, locked, trade_preserved, equipment_allowed, metadata, valid_lock, command_keys, keys_overlap
from ..breakthrough import preparation, current_stage

class SocialPlans:
    def plan_social_sync(self, s):
        return {}, 'partner_result', self.config['social_interval']

    def _partner(self, s):
        p = s.get('partner', {})
        if time.time()*1000 - p.get('synced_at', 0) <= max(300, self.config['social_interval']*2)*1000:
            return p
        return {}

    def plan_partner_practice(self, s):
        p = self._partner(s); d = p.get('daily', {})
        if p.get('has_partner') and not s.get('world', {}).get('captured') and d.get('practice_used', 0) < min(d.get('practice_limit', 0), self.config['partner_practice_limit']):
            return {}, 'partner_result', 30

    def plan_partner_social(self, s):
        p = self._partner(s); target = self.config['partner_target']; now = time.time()*1000
        if not p or p.get('has_partner') or not target or p.get('cooldown_until', 0) > now:
            return
        if self.clock() < self.item_due.get(('partner_social', target), 0): return
        if self.config['partner_auto_accept']:
            for row in p.get('received_invites', []):
                if row.get('target') == target and row.get('expires_at', 0) > now:
                    return {'action':'accept_invite', 'invite_id':row['id'], 'target':target}, 'partner_result', 300
        if self.config['partner_auto_invite'] and not any(row.get('target') == target and row.get('expires_at', 0) > now for row in p.get('sent_invites', [])):
            return {'action':'invite', 'target':target}, 'partner_result', 300

    def plan_partner_rescue(self, s):
        p = self._partner(s); f = p.get('capture', {})
        if not p.get('has_partner') or p.get('self_is_captor') or not f or f.get('expires_at', 0) <= time.time()*1000 or s.get('world', {}).get('captured'): return
        mode = self.config['partner_rescue_mode']; prop = p.get('rescue', {})
        if mode != 'battle' and prop.get('count', 0)-prop.get('cost', 2) >= self.config['rescue_prop_reserve'] and self.safe_flag(s,prop):
            return {'action':'rescue_talisman', 'target':p.get('target',''), 'capture_id':f.get('capture_id','')}, 'partner_result', 120
        if mode != 'talisman' and s.get('character', {}).get('injury', 0) <= self.config['pvp_max_injury']:
            return {'action':'rescue_start', 'target':p.get('target',''), 'capture_id':f.get('capture_id','')}, '', self.config['pvp_retry_seconds']

    @staticmethod
    def assessment_allowed(value, threshold):
        allowed = {'crush':('碾压',), 'advantage':('碾压','优势'), 'close':('碾压','优势','相近')}
        return value in allowed[threshold]

    def _pvp(self, s, kind):
        w = s.get('world', {}); c = s.get('character', {})
        if w.get('captured') or c.get('injury', 0) > self.config['pvp_max_injury']: return
        cap = self.config['capture_daily_limit' if kind == 'player_capture' else 'occupy_daily_limit']
        if s.get('assistant_daily', {}).get(kind, 0) >= cap: return
        if kind == 'player_capture' and (not s.get('features', {}).get('furnace') or w.get('furnace_free', 0) <= 0): return
        points = self._world_candidates(s, kind, ('cultivator','player','robot'))
        for p in points:
            if p.get('expires_at', 0) <= time.time()*1000 or not self.assessment_allowed(p.get('power_assessment'), self.config['pvp_assessment']): continue
            if not p.get('target_token'): continue
            if kind == 'player_capture' and (p.get('furnace_unlocked') is not True or p.get('furnace_protected_until', 0) > time.time()*1000): continue
            if kind == 'player_occupy':
                current = w.get('home', {}).get('score', 0)
                if not p.get('home_safe') or p.get('home_score', 0) <= current + max(.01, abs(current)*self.config['occupy_min_gain']/100): continue
            return {'marker_id':p['marker_id'], 'target_token':p['target_token']}, '', 60

    def plan_player_capture(self, s): return self._pvp(s, 'player_capture')

    def plan_player_occupy(self, s): return self._pvp(s, 'player_occupy')

    def plan_bounty_sync(self, s):
        if s.get('features', {}).get('explore'): return {}, 'cave_result', self.config['bounty_interval']

    def plan_bounty_claim(self, s):
        b = s.get('bounty', {})
        if s.get('world', {}).get('captured') or time.time()*1000-b.get('synced_at', 0) > max(300,self.config['bounty_interval']*2)*1000: return
        if s.get('character', {}).get('injury', 0) > self.config['pvp_max_injury']: return
        if s.get('assistant_daily', {}).get('bounty_claim', 0) >= self.config['bounty_daily_limit'] or b.get('daily_claims_used', 0) >= b.get('daily_claim_limit', 0): return
        for e in b.get('events', []):
            if e.get('is_owner') or e.get('busy') or e.get('remaining_uses', 0) <= 0 or e.get('expires_at', 0) <= time.time()*1000: continue
            if e.get('event_type') != 'monster_clear' and not self.config['bounty_allow_players']: continue
            if not self.assessment_allowed(e.get('power_assessment'), self.config['bounty_assessment']): continue
            if self.clock() < self.item_due.get(('bounty_claim', e['id']), 0): continue
            return {'event_id':e['id'], 'target_token':e['target_token']}, '', 60

    def plan_bounty_publish(self, s):
        w=s.get('world', {}); f=w.get('capture', {}); prop=w.get('bounty_prop', {})
        cid=str(f.get('capture_id',''))
        if not self.config['bounty_publish_captured'] or not w.get('captured') or not cid or not f.get('master_token'): return
        if self.clock() < self.item_due.get(('bounty_publish', cid), 0) or s.get('capture_actions', {}).get(cid, {}).get('bounty_publish'): return
        if prop.get('count', 0)-1 < self.config['bounty_prop_reserve'] or not self.safe_flag(s,prop): return
        return {'capture_id':cid, 'master_token':f['master_token']}, 'cave_result', 300

    def plan_slave_escape(self, s):
        w=s.get('world', {}); f=w.get('capture', {}); prop=w.get('escape_prop', {})
        cid=str(f.get('capture_id',''))
        if not w.get('captured') or not cid or self.clock() < self.item_due.get(('slave_escape',cid), 0): return
        # Normal attempt and talisman have distinct persistent deduplication keys.
        actions=s.get('capture_actions', {}).get(cid, {})
        mode=self.config['escape_mode']
        if mode != 'free_only' and not actions.get('escape_talisman') and prop.get('count',0)-1 >= self.config['escape_prop_reserve'] and self.safe_flag(s,prop):
            return {'capture_id':cid,'action':'escape_talisman'}, 'cave_result', 60
        if mode != 'talisman_only' and not f.get('attempted_escape') and not actions.get('escape_free'):
            return {'capture_id':cid,'action':'escape_free'}, 'cave_result', 60

    def plan_multiplayer_realm(self, s):
        m=s.get('multiplayer', {})
        if m.get('suspended') or m.get('enabled') is not True: return
        if m.get('active'):
            if m.get('stale') or m.get('command_pending'): return
            params={'entry_id':m['entry_id']}
            hp=m.get('hp_percent',100)
            if m.get('can_escape') and hp <= self.config['mp_escape_hp']:
                return dict(params, action='battle_escape', battle_id=m['battle_id']), 'multiplayer_realm', 10
            if m.get('can_extract') and (hp<=self.config['mp_extract_hp'] or m.get('elapsed_seconds',0)>=self.config['mp_max_seconds']):
                return dict(params, action='extract'), 'multiplayer_realm', 10
            option=self.config['mp_event_option']; event=m.get('event', {})
            if m.get('state')=='choosing' and option and option in event.get('options',[]):
                return dict(params, action='choose', event_id=event['id'], option_id=option), 'multiplayer_realm', 10
            return
        if self.config['mp_auto_enter']:
            if not m.get('prepared'): return {'action':'prepare'}, 'multiplayer_realm', self.config['mp_interval']
            # Unknown key identities remain blocked; known keys obey category/locks.
            key=m.get('key_item','');parts=key.split(':')
            allowed=len(parts)==2 and valid_lock(key) and available(self.config,s,parts[0],int(parts[1]),total=m.get('key_count',0))>=1
            if m.get('available') and ((allowed and m.get('key_count',0)>0) or type(m.get('free_entries')) is int and m['free_entries']>0):
                return {'action':'enter','realm_key':m['realm_key']}, 'multiplayer_realm', self.config['mp_interval']
