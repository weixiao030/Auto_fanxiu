"""WorldPlans: single-step intentions, confirmed by the game bridge."""
import math
import time
from ..settings import QUALITIES
from ..protection import available, locked, trade_preserved, equipment_allowed, metadata, valid_lock, command_keys, keys_overlap
from ..breakthrough import preparation, current_stage

class WorldPlans:
    def _world_map_full(self, world):
        limit = min(self.config['world_point_limit'], world.get('max_points', 20))
        return world.get('point_count', 0) >= limit

    def plan_world_sync(self, s):
        if s.get('features', {}).get('explore'): return {}, '', 90

    def plan_world_explore(self, s):
        if not s.get('features', {}).get('explore'): return
        w = s.get('world', {})
        if not w or w.get('pending_event') or self._world_map_full(w):
            return
        if w.get('daily_count', 0) >= self.config['world_daily_limit']: return
        options = {}
        if w.get('free_remaining', 0) <= 0:
            for mode in ('rumor', 'mirror'):
                if not self.config['world_use_' + mode]: continue
                prop = w.get(mode, {})
                if prop.get('count', 0) - prop.get('cost', 1) < self.config['world_prop_reserve']: continue
                if locked(self.config, 'material', prop.get('id', 4006 if mode == 'rumor' else 4003)): continue
                if not self.safe_flag(s,prop): continue
                if mode == 'mirror' and not prop.get('unlocked'): continue
                options['use_' + mode] = True
                if mode == 'mirror':
                    target = self.config['world_mirror_target']
                    if target == 'auto':
                        target = next((r['kind'] for r in self.ledger(s).rows() if r['missing'] and not r['blocked'] and r['kind'] in ('herb', 'material')), 'material')
                    options['target_type'] = target
                break
            else: return
        return options, 'cave_result', self.config['world_interval']

    def world_exploration_status(self, s):
        w = s.get('world', {})
        props = []
        for mode, name, default_id in (('rumor', '流言', 4006), ('mirror', '窥真镜', 4003)):
            prop = w.get(mode, {})
            mid = int(prop.get('id', default_id))
            key = f'material:{mid}'
            info = metadata(s, 'material', mid)
            total = int(prop.get('count', 0))
            bound = prop.get('bound_count', s.get('bound_items', {}).get(key, info.get('bound_count')))
            usable = int(prop.get('spendable_count', total))
            cost = max(1, int(prop.get('cost', 1)))
            reserve = self.config['world_prop_reserve']
            reason = ''
            if not self.config['world_use_' + mode]:
                reason = '未启用'
            elif mode == 'mirror' and not prop.get('unlocked'):
                reason = '尚未解锁'
            elif locked(self.config, 'material', mid):
                reason = '已固定锁定'
            elif prop.get('steam_trade_known') is False and self.config['preserve_steam_tradable']:
                reason = '等待Steam物品定义识别'
            elif total - cost < reserve:
                reason = f'数量不足（每次需{cost}个，保留{reserve}个）'
            elif usable < cost:
                reason = f'绑定份不足（可用{usable}个，每次需{cost}个）；保留未绑定保护份'
            elif not self.safe_flag(s, prop):
                if bound is None or int(bound) < cost:
                    reason = '没有足够的已确认绑定份，受物品保护限制'
                else:
                    reason = '等待游戏按当前保护规则重新同步'
            props.append({'mode': mode, 'name': name, 'id': mid, 'count': total,
                          'bound_count': bound, 'spendable_count': usable, 'cost': cost, 'reserve': reserve,
                          'ready': not reason, 'reason': reason})
        choice = self.plan_world_explore(s)
        ready = choice is not None
        mode = ('mirror' if choice[0].get('use_mirror') else 'rumor' if choice[0].get('use_rumor') else 'free') if ready else None
        if not s.get('features', {}).get('explore'):
            message = '等待游戏解锁世界探索。'
        elif not w:
            message = '等待同步世界地图与免费探索次数。'
        elif w.get('pending_event'):
            message = '等待处理当前奇遇后继续探索。'
        elif self._world_map_full(w):
            message = '地图坐标已达上限，等待采集或清理后继续探索。'
        elif w.get('daily_count', 0) >= self.config['world_daily_limit']:
            message = f"已达今日探索上限（{w.get('daily_count', 0)}/{self.config['world_daily_limit']}），等待次日刷新或调整上限。"
        elif ready:
            message = '可进行免费探索。' if mode == 'free' else '免费探索已用完，可使用' + ('流言' if mode == 'rumor' else '窥真镜') + '继续探索。'
        else:
            message = '免费探索已用完；' + '；'.join(row['name'] + '：' + row['reason'] for row in props) + '。'
        return {'ready': ready, 'mode': mode, 'message': message,
                'free_remaining': w.get('free_remaining'), 'props': props}

    def _world_candidates(self, s, task, kinds):
        return [p for p in s.get('world', {}).get('points', []) if p.get('type') in kinds and not p.get('is_current')
                and self.clock() >= self.item_due.get((task, p.get('marker_id')), 0)]

    def plan_world_harvest(self, s):
        points = self._world_candidates(s, 'world_harvest', ('ordinary', 'herb', 'material'))
        for point in sorted(points, key=lambda p: -list(QUALITIES).index(p.get('quality', 'common')) if p.get('quality') in QUALITIES else 0):
            if point.get('remaining', 1) > 0 and point.get('cooldown_until', 0) <= time.time()*1000:
                return {'marker_id': point['marker_id']}, 'cave_result', 6

    def plan_world_points(self, s):
        kinds = ['spring', 'stronghold'] + (['relic'] if self.config['world_relics'] else [])
        points = self._world_candidates(s, 'world_points', kinds)
        c = s.get('character', {})
        if c.get('exp', 0) >= c.get('exp_needed', float('inf')):
            points = [p for p in points if p.get('type') != 'spring']
        if points: return {'marker_id': points[0]['marker_id']}, 'cave_result', 8

    def world_points_status(self, s):
        kinds = ['spring', 'stronghold'] + (['relic'] if self.config['world_relics'] else [])
        points = self._world_candidates(s, 'world_points', kinds)
        character = s.get('character', {})
        exp = character.get('exp', 0)
        needed = character.get('exp_needed')
        full = isinstance(needed, (int, float)) and exp >= needed
        waiting_springs = sum(p.get('type') == 'spring' for p in points) if full else 0
        ready = self.plan_world_points(s) is not None
        if not s.get('features', {}).get('explore'):
            message = '等待游戏解锁世界探索。'
        elif waiting_springs:
            message = f'修为已满（{exp:,.0f}/{needed:,.0f}），保留{waiting_springs}处灵泉；升级或突破后自动吸取，避免浪费。'
            if ready: message += '其余据点和允许探索的遗迹仍会继续处理。'
        elif ready:
            message = '发现可处理的灵泉、据点或遗迹，等待调度；已提交操作须先结算。'
        else:
            message = '暂无可处理的灵泉、据点或遗迹，等待新发现或失败退避结束。'
        return {'ready': ready, 'waiting_springs': waiting_springs, 'message': message}

    def world_events_status(self, s):
        event = s.get('world', {}).get('pending_event') or {}
        ready = bool(event.get('event_id'))
        if ready:
            message = '有待处理奇遇，等待调度；赠送资源或社交决策类按当前策略关闭，不赠送物品。'
        else:
            message = '当前没有待处理奇遇；探索中的即时奖励已由游戏直接结算，需选择的奇遇出现后才处理。'
        return {'ready': ready, 'message': message}

    def plan_world_events(self, s):
        e = s.get('world', {}).get('pending_event', {})
        if e.get('event_id'): return {'event_id': int(e['event_id']), 'action': 'close'}, 'cave_result', 5

    def plan_world_prune(self, s):
        w = s.get('world', {})
        if not self.config['world_prune'] or not self._world_map_full(w): return
        points = self._world_candidates(s, 'world_prune', ('empty', 'player', 'cultivator', 'robot'))
        # An empty visible point frees capacity; expired players already do not count.
        for p in sorted(points, key=lambda p: p.get('type') != 'empty'):
            if p.get('type') == 'empty' or p.get('expires_at', 0) <= time.time()*1000:
                return {'marker_id': p['marker_id']}, 'cave_result', 8

    def plan_realm_challenge(self, s):
        points = self._world_candidates(s, 'realm_challenge', ['breakthrough_realm'])
        points = [p for p in points if p.get('required_level', 0) <= s.get('character', {}).get('level', 0)
                  and (self.config['realm_allow_danger'] or p.get('difficulty', 'DANGER') != 'DANGER')]
        if points: return {'marker_id': points[0]['marker_id']}, '', 30

    def plan_home_relocate(self, s):
        w = s.get('world', {}); prop = w.get('relocate', {})
        if w.get('captured') or prop.get('count', 0) <= self.config['home_reserve']: return
        if not self.safe_flag(s,prop) or locked(self.config,'material',4001): return
        current = w.get('home', {}).get('score', 0)
        candidates = self._world_candidates(s, 'home_relocate', ('ordinary', 'herb', 'material', 'spring', 'relic', 'stronghold', 'forge', 'empty'))
        candidates = [p for p in candidates if p.get('home_safe') and p.get('home_score', 0) > current + max(0.01, abs(current)*self.config['home_min_gain']/100)]
        if candidates:
            target = max(candidates, key=lambda p: (p['home_score'], -p['marker_id']))
            return {'marker_id': target['marker_id']}, 'cave_result', 300

    def plan_resource_realm(self, s):
        realm = s.get('resource_realm', {})
        if not realm.get('enabled'):
            return
        if realm.get('command_pending') or realm.get('battle_playing'):
            return
        if realm.get('active'):
            if realm.get('stale'):
                return {'action': 'status'}, 'resource_realm', 30
            return
        portal = realm.get('portal') or {}
        if not portal.get('id'):
            return
        if self.config['growth_linked']:
            kinds = {row['kind'] for row in self.ledger(s).rows() if row['missing'] and not row['blocked']}
            if portal.get('type') not in kinds:
                return
        if realm.get('free_remaining', 0) <= 0:
            token = realm.get('token', {})
            if not self.config['resource_realm_use_token'] or not self.safe_flag(s, token):
                return
            if available(self.config, s, 'material', int(token.get('id', 4204))) - int(token.get('cost', 1)) < self.config['resource_realm_token_reserve']:
                return
        return {'action': 'enter', 'portal_id': str(portal['id'])}, 'resource_realm', 30
