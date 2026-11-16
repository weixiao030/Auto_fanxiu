"""Server-observed breakthrough preparation; never invent resources or probabilities."""
from __future__ import annotations

import math
from .protection import available, locked, source_blocked

EPSILON = 1e-9


def target_rate(config):
    minimum = config['min_breakthrough_rate']
    if config.get('breakthrough_settings_version', 1) < 2 and config['breakthrough_auto_raise']:
        return max(minimum, config['breakthrough_target_rate'])
    return minimum


def current_stage(state):
    current = state.get('idle', {}).get('selected')
    return '' if not current else '_'.join(str(int(current[k])) for k in ('difficulty', 'tier', 'stage'))


def gathering_stage(config, state, detail):
    """Use only runtime-observed rewards of cleared stages. Never change a pinned stage."""
    if (not detail['active'] or not config['breakthrough_auto_find'] or config['idle_stage'] != 'auto'
            or not config['tasks'].get('idle_select') or not config['tasks'].get('harvest')
            or not state.get('features', {}).get('battle_idle')):
        return None
    missing = {r['key'] for r in detail['shortages'] if not r['protected']}
    cleared = set(state.get('progress', {}).get('cleared_ids', []))
    candidates = []
    for row in state.get('idle_reward_stages', []):
        key = row.get('key', '')
        if key not in cleared or len(key.split('_')) != 3 or not all(p.isdigit() for p in key.split('_')):
            continue
        covers = missing.intersection(row.get('items', []))
        if covers:
            candidates.append((len(covers), key, sorted(covers), row.get('name', key)))
    if not candidates:
        return None
    best_coverage = max(row[0] for row in candidates)
    candidates = [row for row in candidates if row[0] == best_coverage]
    # Stay on a working stage to avoid resetting a native idle batch every snapshot.
    selected = next((row for row in candidates if row[1] == current_stage(state)), None)
    selected = selected or max(candidates, key=lambda row: tuple(map(int, row[1].split('_'))))
    return {'key': selected[1], 'covers': selected[2], 'name': selected[3],
            'selected': selected[1] == current_stage(state)}


def preparation(config, state):
    """Return a fresh plan for one confirmed step, plus a UI explanation."""
    b = state.get('breakthrough_preparation', {})
    target = target_rate(config)
    result = {'active': False, 'phase': 'waiting', 'message': '等待新版游戏桥接同步突破信息。',
              'target_rate': target, 'minimum_rate': b.get('minimum_rate', 0),
              'maximum_rate': b.get('maximum_rate', 0), 'failure_bonus': b.get('failure_bonus', 0), 'shortages': [], 'reserved': {},
              'action': None, 'ready': False, 'materials': [],
              'experience_ready': bool(state.get('needs_breakthrough')),
              'rate_ready': float(b.get('minimum_rate', 0)) + EPSILON >= target,
              'materials_ready': False}
    if not config['tasks'].get('breakthrough'):
        result.update(phase='disabled', message='境界突破任务已关闭。')
        return result
    if not b or state.get('bridge_revision', 0) < 18:
        return result
    if not b.get('info'):
        result.update(message='尚未到达突破等级，继续修炼。')
        return result
    if state.get('realm_locked'):
        result.update(message='原游戏境界尚未开放，等待开放。')
        return result
    result['active'] = True
    needs = {}
    def add(rows, multiplier=1, purpose='breakthrough'):
        for row in rows:
            key = f"{row.get('kind', 'material')}:{int(row['id'])}"
            if key not in needs:
                needs[key] = {**row, 'kind': row.get('kind', 'material'), 'need': 0, 'purpose': purpose}
            needs[key]['need'] += int(row['count']) * multiplier
            if purpose == 'pill': needs[key]['pill_material'] = True
    add(b['info'].get('materials', []))
    deficit = max(0, target - float(b.get('minimum_rate', 0)))
    choices = []
    if deficit > EPSILON and not state.get('guaranteed_breakthrough') and config['breakthrough_auto_raise']:
        for pill in state.get('pills', []):
            bonus = float(pill.get('bonus_min', 0))
            if not pill.get('is_breakthrough') or not pill.get('breakthrough_matching') or bonus <= 0:
                continue
            usable = max(0, available(config, state, 'pill', pill['id'], selector=True, info=pill,
                                      total=pill.get('count', 0), bound=pill.get('bound_count', 0)) - config['pill_reserve'])
            needed = max(1, math.ceil((deficit - EPSILON) / bonus))
            recipes = [r for r in state.get('alchemy_recipes', [])
                       if r.get('pill_id') == pill['id'] and r.get('breakthrough_matching') and r.get('unlocked') and r.get('materials')]
            if usable or recipes:
                recipe = min(recipes, key=lambda r: (sum(max(0, int(m['count']) + config['breakthrough_material_reserve']
                        - available(config, state, m['kind'], m['id'])) for m in r['materials']), r['recipe_index'])) if recipes else None
                choices.append((0 if usable else 1, needed, pill['id'], pill, recipe, usable))
        if not choices:
            result.update(phase='blocked', message='概率未达目标，没有当前境界可用的突破丹或已解锁配方。')
        else:
            _, count, _, pill, recipe, usable = min(choices, key=lambda x: x[:3])
            result.update(pill_id=pill['id'], pill_name=pill['name'], pills_needed=count, pills_available=usable)
            missing_pills = max(0, count - usable)
            if recipe and missing_pills and config['breakthrough_auto_craft']:
                add(recipe['materials'], missing_pills, 'pill')
            if usable and state.get('needs_breakthrough'):
                if config['breakthrough_auto_use']:
                    result.update(phase='use', message=f"服用{pill['name']}后等待服务器确认，再复查概率。",
                                  action={'kind': 'pill', 'params': {'pill_id': pill['id'], 'breakthrough_prepare': True}, 'key': 'alchemy', 'cooldown': 3})
                else:
                    result.update(phase='blocked', message='突破丹可用，自动服丹子开关已关闭。')
            elif usable:
                result.update(phase='experience', message='突破丹已备好，等待修为满后服用。')
            elif not config['breakthrough_auto_craft']:
                result.update(phase='blocked', message='缺少突破丹，自动炼丹子开关已关闭。')
            elif not recipe:
                result.update(phase='blocked', message='当前境界突破丹配方未解锁。')
            else:
                # Reserve the breakthrough itself, but craft just one pill and replan after acknowledgement.
                direct = {}
                for row in b['info'].get('materials', []):
                    k = f"{row.get('kind', 'material')}:{int(row['id'])}"
                    direct[k] = direct.get(k, 0) + int(row['count'])
                craft_needs = {}
                for m in recipe['materials']:
                    k = f"{m['kind']}:{int(m['id'])}"
                    craft_needs[k] = craft_needs.get(k, 0) + int(m['count'])
                enough = all(available(config, state, k.split(':')[0], int(k.split(':')[1])) >= amount
                             + direct.get(k, 0) + config['breakthrough_material_reserve'] for k, amount in craft_needs.items())
                if enough and recipe.get('bound_only_safe') is True:
                    result.update(phase='craft', message=f"炼制1颗{pill['name']}，确认入库后再继续。",
                                  action={'kind': 'alchemy', 'params': {'pill_id': pill['id'], 'recipe_index': recipe['recipe_index'],
                                           'count': 1, 'breakthrough_prepare': True}, 'key': 'alchemy', 'cooldown': 3})
                else:
                    result.update(phase='materials', message='正在等待突破丹材料，按缺口寻找资源。')
    elif deficit > EPSILON:
        result.update(phase='probability', message='成功率未达目标；自动用丹药提高成功率已关闭。')
    elif state.get('needs_breakthrough'):
        result.update(phase='ready', ready=True, message='概率已达目标，检查突破材料后执行。')
    else:
        result.update(phase='experience', message='概率已达目标，等待修为满后突破。')
    for key, row in needs.items():
        usable = available(config, state, row['kind'], row['id'])
        reserve = config['breakthrough_material_reserve'] if row.get('pill_material') else 0
        needed = row['need'] + reserve
        result['reserved'][key] = needed
        total = state.get('owned_items', {}).get(key, 0)
        item = {'key': key, 'kind': row['kind'], 'id': row['id'], 'purpose': row['purpose'],
                'name': row.get('name', str(row['id'])), 'need': needed, 'have': total, 'usable': usable,
                'missing': max(0, needed - usable), 'protected': source_blocked(config, state, row['kind'], row['id'])}
        result['materials'].append(item)
        if usable < needed:
            result['shortages'].append(item)
    base_missing = [r for r in result['shortages'] if r['purpose'] == 'breakthrough']
    result['materials_ready'] = not base_missing
    if result['shortages'] and (result['ready'] or (base_missing and not result['action'])):
        result.update(ready=False, phase='materials', message='等待补齐突破材料。')
    result['gathering_stage'] = gathering_stage(config, state, result)
    return result
