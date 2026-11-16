"""Resource demands derived from observed game rules; no predicted loot is inventory."""
from __future__ import annotations

from collections import defaultdict
import math
from .breakthrough import preparation, current_stage
from .readiness import waiting_message
from .protection import available, equipment_allowed, locked, metadata, trade_preserved, source_blocked


PRIORITY = {'breakthrough': 0, 'upgrade': 10, 'alchemy': 20, 'material_synth': 30, 'background': 100}


class ResourceLedger:
    def __init__(self, config, state):
        self.config, self.state = config, state
        self.claims = defaultdict(dict)
        self.names = {}
        self.breakthrough = preparation(config, state)
        for row in self.breakthrough['materials']:
            self.add('breakthrough', row['kind'], row['id'], row['need'], row['name'])
        upcoming = state.get('upcoming_breakthrough', {})
        if config['tasks']['breakthrough'] and not self.breakthrough['active'] and not state.get('realm_locked'):
            for row in upcoming.get('materials', []):
                self.add('breakthrough', row.get('kind', 'material'), row['id'], row['count'], row.get('name'))
        if config['tasks']['upgrade']:
            cap = min(state.get('max_upgrade_level', 90), state.get('character', {}).get('level', 0) - config['upgrade_level_gap'])
            needs = defaultdict(int)
            equipped = state.get('character', {}).get('equip_slots', [])
            for item in state.get('equipment', []):
                if item['id'] not in equipped or not equipment_allowed(config, item) or item.get('level', cap) >= cap:
                    continue
                for row in item.get('upgrade_needs', []):
                    needs[(row.get('kind', 'material'), int(row['id']))] += int(row['count'])
            for (kind, mid), amount in needs.items():
                self.add('upgrade', kind, mid, amount + config['upgrade_reserve'])
        self.alchemy_recipe = None
        if config['tasks']['alchemy']:
            by_pill = defaultdict(list)
            for recipe in state.get('alchemy_recipes', []):
                if (not recipe.get('is_breakthrough') and recipe.get('useful') and recipe.get('unlocked', True)
                        and int(state.get('owned_items', {}).get(f"pill:{recipe['pill_id']}", 0)) <= config['pill_reserve']
                        and recipe.get('materials')
                        and not any(source_blocked(config, state, m.get('kind', 'material'), int(m['id'])) for m in recipe['materials'])):
                    by_pill[recipe['pill_id']].append(recipe)
            choices = [r for recipes in by_pill.values() for r in recipes]
            if choices:
                # Prepare one achievable normal pill, then re-evaluate after crafting/use.
                recipe = min(choices, key=lambda r: (sum(max(0, int(m['count']) + config['alchemy_reserve']
                    - self.spendable(m['kind'], m['id'], 'alchemy')) for m in r['materials']), r['pill_id'], r['recipe_index']))
                self.alchemy_recipe = recipe
                for row in recipe['materials']:
                    self.add('alchemy', row['kind'], row['id'], int(row['count']) + config['alchemy_reserve'])
        # Trace upgrade conversion chains backwards; never reserve a nonexistent synthetic yield.
        if config['tasks']['material_synth']:
            recipes = {int(r['output_id']): r for r in state.get('material_synthesis', []) if r.get('unlocked')}
            # Visit output dependencies first, then reserve each shared input once.
            # Two equipped items may need both an intermediate and its successor.
            visited, order = {}, []
            def visit(mid, depth=0):
                status = visited.get(mid, 0)
                if status in (1, 3): return False  # A cyclic native recipe cannot be planned.
                if status == 2 or mid not in recipes or depth >= 8 or source_blocked(config, state, 'material', mid):
                    return True
                visited[mid] = 1
                if not visit(int(recipes[mid]['input_id']), depth + 1):
                    visited[mid] = 3
                    return False
                visited[mid] = 2
                order.append(mid)
                return True
            for key, owners in list(self.claims.items()):
                if key.startswith('material:') and 'upgrade' in owners:
                    visit(int(key.split(':')[1]))
            conversions = {}
            for mid in reversed(order):
                key = f'material:{mid}'
                need = sum(self.claims.get(key, {}).values()) + conversions.get(mid, 0)
                deficit = max(0, need - available(config, state, 'material', mid))
                if not deficit: continue
                recipe = recipes[mid]
                source = int(recipe['input_id'])
                if source not in conversions: conversions[source] = config['material_synth_reserve']
                conversions[source] += deficit * max(1, int(recipe['required_count']))
            for mid, amount in conversions.items():
                self.add('material_synth', 'material', mid, amount)

    def add(self, owner, kind, mid, amount, name=None):
        key = f'{kind}:{int(mid)}'
        self.claims[key][owner] = self.claims[key].get(owner, 0) + max(0, int(amount))
        info = metadata(self.state, kind, int(mid))
        native_name = next((row.get('name') for row in self.state.get('refine_candidates', [])
                            if ('material' if row.get('kind') == 'equipment_upgrade' else row.get('kind')) == kind
                            and int(row.get('id', 0)) == int(mid) and row.get('name')), None)
        self.names[key] = name or info.get('name') or native_name or key

    def held(self, key, consumer='background'):
        priority = PRIORITY.get(consumer, 100)
        return sum(amount for owner, amount in self.claims.get(key, {}).items() if PRIORITY[owner] < priority)

    def spendable(self, kind, mid, consumer='background', **kwargs):
        return max(0, available(self.config, self.state, kind, mid, **kwargs) - self.held(f'{kind}:{int(mid)}', consumer))

    def rows(self):
        result = []
        for key, owners in self.claims.items():
            kind, raw = key.split(':')
            mid = int(raw)
            usable = available(self.config, self.state, kind, mid)
            total = int(self.state.get('owned_items', {}).get(key, 0))
            info = metadata(self.state, kind, mid)
            need = sum(owners.values())
            result.append({'key': key, 'kind': kind, 'id': mid, 'name': self.names[key], 'need': need,
                           'have': total, 'usable': usable, 'missing': max(0, need - usable),
                           'owners': list(owners), 'priority': self.shortage_priority(owners, usable),
                           'blocked': locked(self.config, kind, mid),
                           'reason': '固定锁定' if locked(self.config, kind, mid) else ''})
        return sorted(result, key=lambda r: (r['priority'], -r['missing'], r['key']))

    @staticmethod
    def shortage_priority(owners, usable):
        for owner, amount in sorted(owners.items(), key=lambda pair: PRIORITY[pair[0]]):
            usable -= amount
            if usable < 0:
                return PRIORITY[owner]
        return min(PRIORITY[o] for o in owners)

    def gathering_stage(self):
        c, s = self.config, self.state
        if not c['growth_linked'] or c['idle_stage'] != 'auto' or not c['tasks']['idle_select'] or not c['tasks']['harvest']:
            return None
        shortages = {}
        for row in self.rows():
            if not row['missing'] or row['blocked']: continue
            owners = {owner: amount for owner, amount in self.claims[row['key']].items()
                      if owner != 'breakthrough' or c['breakthrough_auto_find']}
            if not owners: continue
            held = sum(amount for owner, amount in self.claims[row['key']].items() if owner not in owners)
            shortages[row['key']] = self.shortage_priority(owners, max(0, row['usable'] - held))
        tiers = sorted(set(shortages.values()))
        cleared = set(s.get('progress', {}).get('cleared_ids', []))
        candidates = []
        for stage in s.get('idle_reward_stages', []):
            key = stage.get('key', '')
            if key not in cleared or len(key.split('_')) != 3 or not all(p.isdigit() for p in key.split('_')):
                continue
            covers = sorted(set(stage.get('items', [])) & shortages.keys())
            if covers:
                # A lower-priority collection of shortages cannot outvote a breakthrough.
                score = tuple(sum(shortages[k] == tier for k in covers) for tier in tiers)
                candidates.append((score, stage, covers))
        if not candidates:
            return None
        best = max(row[0] for row in candidates)
        candidates = [row for row in candidates if row[0] == best]
        selected = next((row for row in candidates if row[1]['key'] == current_stage(s)), None)
        _, stage, covers = selected or max(candidates, key=lambda row: tuple(map(int, row[1]['key'].split('_'))))
        return {'key': stage['key'], 'name': stage.get('name', stage['key']), 'covers': covers, 'selected': stage['key'] == current_stage(s)}

    def refine_target(self):
        candidates = self.state.get('refine_candidates', [])
        requested = int(self.config['refine_preferred_id'])
        if requested:
            return next((dict(row, source='manual') for row in candidates if int(row['id']) == requested), None)
        if not self.config['growth_linked']:
            return None
        by_key = {f"{'material' if r['kind'] == 'equipment_upgrade' else r['kind']}:{int(r['id'])}": r for r in candidates}
        for row in self.rows():
            if row['missing'] and not row['blocked'] and row['key'] in by_key:
                return dict(by_key[row['key']], source='demand', owners=row['owners'], missing=row['missing'])

    def refine_retention(self, row):
        if row.get('obsolete') is True and self.config['refine_recycle_obsolete']:
            return self.config['refine_obsolete_reserve']
        # Current claims already protect part of the future absolute floor.
        held = self.held(f"{row.get('kind', 'material')}:{int(row['id'])}")
        return max(self.config['refine_reserve'], int(row.get('future_need', 0)) - held)

    def refine_plan(self, safe_flag, forge=False):
        c, s = self.config, self.state
        target = self.refine_target()
        legacy = s.get('bridge_revision', 0) < 22
        multiplier = max(1, int(s.get('refine_forge_multiplier', 3))) if forge else 1
        result = {'ready': False, 'target': target, 'materials': {}, 'progress': 0, 'input_progress': 0,
                  'multiplier': multiplier, 'level': int(c['refine_target_level']), 'message': ''}
        if s.get('features', {}).get('refine') is False or not s.get('idle', {}).get('selected'):
            result['message'] = '等待炼化解锁并选择已通关的挂机地点。'
            return result
        if forge and not any(p.get('type') == 'forge' and not p.get('is_current') for p in s.get('world', {}).get('points', [])):
            result['message'] = '等待发现可用的世界熔炉。'
            return result
        if c['refine_preferred_id'] and not target and not legacy:
            result['message'] = '指定产出偏好不在原生可选列表内，等待等级或配置变化。'
            return result
        if not target and not legacy and not c['refine_surplus_without_demand']:
            result['message'] = '当前没有可定向补给的资源缺口，保留材料。'
            return result
        per = max(1, int(s.get('refine_progress_per_level', 100)))
        target_progress = int(c['refine_target_level']) * per
        if int(c['refine_target_level']) > int(s.get('refine_max_level', 15)):
            result['message'] = '目标炼化等级超过当前游戏上限。'
            return result
        target_id = int(target['id']) if target else 0
        donors = []
        for row in s.get('refine_inputs', []):
            value = int(row.get('value', 0)) * multiplier
            category = row.get('category', '')
            if value <= 0 or int(row['id']) == target_id or row.get('auto_fill_excluded') or row.get('manual_only'):
                continue
            if category == 'breakthrough_rare' or (legacy and (category.startswith('breakthrough') or category == 'equipment_upgrade')):
                continue
            if not safe_flag(s, row):
                continue
            kind, mid = row.get('kind', 'material'), int(row['id'])
            count = max(0, int(self.spendable(kind, mid, total=row['count'], info=row) - self.refine_retention(row)))
            count = min(count, int(c['refine_max_items']), math.ceil(target_progress / value))
            if count:
                donors.append((mid, value, count))
        # Bounded knapsack: minimize overpayment first, then number of items. A greedy
        # low-value fill can fail the item budget even when a valid combination exists.
        limit = target_progress + max((v for _, v, _ in donors), default=1) - 1
        dp = {0: (0, ())}
        for mid, value, count in sorted(donors, key=lambda r: (-r[1], r[0])):
            batch = 1
            while count:
                n = min(batch, count); count -= n; batch *= 2
                for total, (units, selection) in list(dp.items()):
                    after, used = total + n * value, units + n
                    if after > limit or used > c['refine_max_items']:
                        continue
                    if after not in dp or used < dp[after][0]:
                        dp[after] = (used, selection + ((mid, n),))
        feasible = [total for total in dp if total >= target_progress]
        if not feasible:
            result['message'] = '目标已确定；当前盈余不足以在投入上限内达到炼化等级，继续领取和补给。'
            return result
        progress = min(feasible)
        mats = defaultdict(int)
        for mid, count in dp[progress][1]:
            mats[str(mid)] += count
        source = f'世界熔炉{multiplier}倍进度，' if forge else ''
        result.update(ready=True, materials=dict(mats), progress=progress, input_progress=progress // multiplier,
                      message=source + (f"定向补给{target.get('name', target['id'])}，投入{sum(mats.values())}件、{progress}进度；产出随机，确认后重算。" if target else f'盈余炼化：{progress}进度，确认后重算。'))
        return result

    def public(self, safe_flag):
        rows = self.rows()
        shortages = [r for r in rows if r['missing']]
        refine = self.refine_plan(safe_flag)
        forge = self.refine_plan(safe_flag, forge=True)
        stage = self.gathering_stage()
        if not self.state.get('ready') or not self.state.get('online'):
            phase, message = 'waiting', waiting_message(self.state)
        elif not self.config['growth_linked']:
            phase, message = 'independent', '功能联动已关闭，按各任务独立执行。'
        elif self.breakthrough.get('ready'):
            phase, message = 'breakthrough', '突破条件已满足，优先完成境界推进。'
        elif shortages:
            phase = 'supply'
            message = '当前瓶颈：' + '、'.join(f"{r['name']}缺{r['missing']}" for r in shortages[:3]) + '。'
        else:
            phase, message = 'growth', '资源需求已满足，持续修炼、换装与推图。'
        return {'linked': self.config['growth_linked'], 'phase': phase, 'message': message,
                'requirements': rows, 'shortages': shortages, 'refine': refine, 'world_forge': forge, 'gathering_stage': stage,
                'steps': ['领取与开箱', '升级／突破／服丹', '换装与修炼', '合成与定向炼化', '挂机与世界补料', '挑战后复查']}
