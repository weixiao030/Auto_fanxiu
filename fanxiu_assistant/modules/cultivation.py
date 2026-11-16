"""CultivationPlans: single-step intentions, confirmed by the game bridge."""
import math
import time
from ..settings import QUALITIES
from ..protection import available, locked, trade_preserved, equipment_allowed, metadata, valid_lock, command_keys, keys_overlap
from ..breakthrough import preparation, current_stage

class CultivationPlans:
    def plan_levelup(self, s):
        c = s.get("character", {})
        if c.get("exp", 0) >= c.get("exp_needed", 1) and not s.get("needs_breakthrough"):
            return {}, "", 30

    def breakthrough_status(self, s):
        result = preparation(self.config, s)
        if self.config['growth_linked'] and result['active']:
            result['gathering_stage'] = self.ledger(s).gathering_stage()
        if result['active'] and result['phase'] == 'materials' and result['shortages']:
            stage = result.get('gathering_stage')
            if not self.config['breakthrough_auto_find']:
                result['message'] = '材料不足；开启自动找料后可按缺口补给。'
            elif stage:
                result['message'] = ('正在挂机补料：' if stage['selected'] else '准备切换补料关卡：') + stage['name'] + '。随机掉落，领取后重新检查。'
            elif (refining := self._breakthrough_refine(s)):
                result['message'] = self.ledger(s).refine_plan(self.safe_flag, forge=refining[3] == 'world_forge')['message']
            elif not self._preparation_gather(s, result):
                result['message'] = '材料不足；当前没有可采集资源或允许的探索次数/道具，等待补给。'
        return result

    def _preparation_gather(self, s, detail):
        if not self.config['breakthrough_auto_find'] or not detail['shortages']: return
        stage = self.ledger(s).gathering_stage() if self.config['growth_linked'] else detail.get('gathering_stage')
        if stage and not stage['selected']:
            return {'key': stage['key'], 'breakthrough_prepare': True}, '', 20, 'idle_select'
        kinds = {r['kind'] for r in detail['shortages'] if not r['protected'] and r['key'] not in (stage['covers'] if stage else [])}
        if not kinds: return
        points = self._world_candidates(s, 'world_harvest', ('herb', 'material', 'ordinary'))
        for point in sorted(points, key=lambda p: p.get('type') not in kinds):
            if point.get('type') not in kinds and point.get('type') != 'ordinary': continue
            if point.get('remaining', 1) > 0 and point.get('cooldown_until', 0) <= time.time()*1000:
                return {'marker_id': point['marker_id'], 'breakthrough_prepare': True}, 'cave_result', 6, 'world_harvest'
        choice = self.plan_world_explore(s)
        if choice:
            params, key, cooldown = choice
            params['breakthrough_prepare'] = True
            if params.get('use_mirror') and self.config['world_mirror_target'] == 'auto':
                params['target_type'] = 'herb' if 'herb' in kinds else 'material'
            return params, key, cooldown, 'world_explore'

    def _breakthrough_refine(self, s):
        if not self.config['growth_linked'] or not self.config['breakthrough_auto_find']:
            return
        target = self.ledger(s).refine_target()
        if not target or 'breakthrough' not in target.get('owners', []):
            return
        # The native world forge triples progress for the same physical inputs.
        for kind in ('world_forge', 'refine'):
            if not self.config['tasks'][kind] or self.clock() < self.due.get(kind, 0):
                continue
            choice = getattr(self, 'plan_' + kind)(s)
            if choice:
                params, key, cooldown = choice
                return dict(params, breakthrough_prepare=True), key, cooldown, kind

    def plan_breakthrough(self, s):
        detail = preparation(self.config, s)
        if detail['active']:
            action = detail['action']
            if action: return action['params'], action['key'], action['cooldown'], action['kind']
            if detail['phase'] == 'materials':
                refining = self._breakthrough_refine(s)
                if refining:
                    return refining
                return self._preparation_gather(s, detail)
            if not detail['ready']: return
        elif s.get('bridge_revision', 0) >= 18:
            return
        b = s.get("breakthrough", {})
        rate = detail["minimum_rate"] if detail["active"] else 1 if s.get("guaranteed_breakthrough") else min(1, b.get("final_rate", 0) + s.get("elixir_bonus", 0))
        if s.get("needs_breakthrough") and not s.get("realm_locked") and b.get("all_enough") and self.safe_flag(s,b) and rate + 1e-9 >= (detail['target_rate'] if detail['active'] else self.config["min_breakthrough_rate"]):
            return {}, "breakthrough", 60

    def plan_gacha(self, s):
        cost = max(1, int(s.get("gacha_cost", 1)))
        surplus = s.get("character", {}).get("wuxing", 0) - self.config["reserve_wuxing"]
        if s.get("features", {}).get("explore") and surplus >= cost:
            unlock = max(1, int(s.get("gacha_batch_unlock_level", 10)))
            limit = max(1, int(s.get("gacha_batch_limit", 10))) if s.get("character", {}).get("level", 0) >= unlock else 1
            return {"count": min(limit, int(surplus // cost))}, "gacha", 15

    def plan_idle_select(self, s):
        cleared = s.get("progress", {}).get("cleared_ids", [])
        if not cleared or not s.get("features", {}).get("battle_idle"):
            return
        target = self.config["idle_stage"]
        if target == "auto":
            stage = self.ledger(s).gathering_stage() or preparation(self.config, s).get("gathering_stage")
            target = stage["key"] if stage else max(cleared, key=lambda k: tuple(map(int, k.split("_"))))
        if target not in cleared:
            return
        current = s.get("idle", {}).get("selected")
        current_key = "" if not current else f'{int(current["difficulty"])}_{int(current["tier"])}_{int(current["stage"])}'
        if target != current_key:
            return {"key": target}, "", 20

    def plan_challenge(self, s):
        if s.get("resource_realm", {}).get("active"):
            return
        node = s.get("next_dungeon", {})
        if not s.get("features", {}).get("dungeon") or not node or node.get("required_level", 0) > s.get("character", {}).get("level", 0):
            return
        previous = self.challenges.get(node["key"])
        if previous and not previous["won"] and self.clock() - previous["at"] < self.config["challenge_retry_seconds"]:
            return
        return {"key": node["key"]}, "", 10

    def plan_gongfa(self, s):
        training = s.get("character", {}).get("gongfa", {}).get("training", {})
        if any(t.get("state") in ("running", "training") for t in training.values()):
            return
        for entry in sorted(s.get("training_candidates", []), key=lambda x: (x["layer"], x["id"])):
            if entry.get("allowed") and self.safe_flag(s,entry) and not locked(self.config,'gongfa',entry['id'],entry.get('layer')) and entry.get("state") != "training":
                action = "resume_training" if entry.get("state") == "paused" else "start_training"
                return {"action": action, "gongfa_id": entry["id"]}, "gongfa_result", 30

    def plan_gongfa_activate(self, s):
        for g in s.get('gongfa_options', []):
            if g.get('can_activate') and not locked(self.config,'gongfa',g['id'],0) and self.safe_flag(s,g,'activation_bound_safe'):
                return {'gongfa_id': g['id']}, 'gongfa_result', 6

    def plan_gongfa_slots(self, s):
        candidates = [g for g in s.get('gongfa_options', []) if g.get('activated') and g.get('element_match') and g.get('active')]
        preferred = self.config['gongfa_preferred']
        candidates.sort(key=lambda g: (preferred.index(g['id']) if g['id'] in preferred else len(preferred), -g.get('power', 0), -g.get('layer', 0), g['id']))
        current = s.get('character', {}).get('gongfa', {}).get('active_slots', [])
        if not candidates or not current: return
        slots = [g['id'] for g in candidates[:len(current)]]
        slots += [0] * (len(current)-len(slots))
        if slots != current: return {'slots': slots}, 'gongfa_result', 15

    def plan_pill(self, s):
        for p in s.get('pills', []):
            if p.get('is_breakthrough'): continue
            if not p.get('useful') or p.get('count', 0) <= self.config['pill_reserve']: continue
            if available(self.config,s,'pill',p['id'],selector=True,info=p,total=p.get('count',0),bound=p.get('bound_count',0)) <= self.config['pill_reserve']: continue
            return {'pill_id': p['id']}, 'alchemy', 10

    def plan_alchemy(self, s):
        recipes = s.get('alchemy_recipes', [])
        if self.config['growth_linked']:
            chosen = self.ledger(s).alchemy_recipe
            recipes = [chosen] if chosen else []
        for r in recipes:
            if r.get('is_breakthrough') or not r.get('unlocked', True): continue
            if not r.get('useful') or not self.safe_flag(s,r): continue
            needs = r.get('materials', [])
            if not needs: continue
            count = min([int((self.spendable(s,m['kind'],m['id'], consumer='alchemy')-self.config['alchemy_reserve'])//max(1,m['count'])) for m in needs] + [self.config['alchemy_batch']])
            if count > 0: return {'pill_id': r['pill_id'], 'recipe_index': r['recipe_index'], 'count': count}, 'alchemy', 15

    def plan_gongfa_accelerate(self, s):
        for g in s.get('gongfa_options', []):
            tr = g.get('training', {})
            if tr.get('state') != 'running' or g.get('spare_pages', 0) <= self.config['gongfa_accelerate_reserve']: continue
            if locked(self.config,'gongfa',g['id'],tr.get('target')) or not self.safe_flag(s,g,'acceleration_bound_safe'): continue
            return {'gongfa_id': g['id']}, 'gongfa_result', 20

    def _refine_materials(self, s):
        plan = self.ledger(s).refine_plan(self.safe_flag)
        return plan['materials'] if plan['ready'] else None

    def refine_status(self, s):
        return self.ledger(s).refine_plan(self.safe_flag)

    def _refine_params(self, s, forge=False):
        plan = self.ledger(s).refine_plan(self.safe_flag, forge=forge)
        if not plan['ready']:
            return None
        params = {'materials': plan['materials']}
        if s.get('bridge_revision', 0) >= 22:
            params['preferred_reward'] = ({'kind': plan['target']['kind'], 'id': int(plan['target']['id'])}
                                          if plan['target'] else {})
            params['growth_linked'] = self.config['growth_linked']
        return params

    def plan_refine(self, s):
        params = self._refine_params(s)
        if params:
            return params, 'refine', 30

    def plan_world_forge(self, s):
        points = self._world_candidates(s, 'world_forge', ['forge'])
        if not points:
            return
        params = self._refine_params(s, forge=True)
        if params:
            return dict(params, marker_id=points[0]['marker_id']), 'cave_result', 30
