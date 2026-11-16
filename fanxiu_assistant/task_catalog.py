"""All operations share one registry and a bounded priority scheduler."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Task:
    kind: str
    feature: str = ''

TASKS = (
    Task('harvest', 'battle_idle'),
    Task('equip', 'equipment'),
    Task('breakthrough', ''),
    Task('idle_select', 'battle_idle'),
    Task('levelup', ''),
    Task('collect', ''),
    Task('open_pack', ''),
    Task('gongfa_activate', 'gongfa'),
    Task('gongfa_slots', 'gongfa'),
    Task('gongfa', 'gongfa'),
    Task('gongfa_accelerate', 'gongfa'),
    Task('upgrade', 'equipment'),
    Task('pill', 'alchemy'),
    Task('alchemy', 'alchemy'),
    Task('world_sync', 'explore'),
    Task('world_events', 'explore'),
    Task('world_harvest', 'explore'),
    Task('world_points', 'explore'),
    Task('world_explore', 'explore'),
    Task('world_prune', 'explore'),
    Task('gacha', ''),
    Task('challenge', 'dungeon'),
    Task('realm_challenge', ''),
    Task('synth', 'synth'),
    Task('refine', 'refine'),
    Task('world_forge', 'refine'),
    Task('mail', 'mail'),
    Task('material_synth', 'synth'),
    Task('furnace_absorb', 'furnace'),
    Task('home_relocate', 'explore'),
    Task('social_sync', ''),
    Task('slave_escape', ''),
    Task('partner_practice', ''),
    Task('partner_social', ''),
    Task('partner_rescue', ''),
    Task('player_capture', ''),
    Task('player_occupy', ''),
    Task('bounty_sync', ''),
    Task('bounty_claim', ''),
    Task('bounty_publish', ''),
    Task('multiplayer_realm', ''),
    Task('resource_realm', ''),
    Task('resource_pack', ''),
)
TASK_ORDER = tuple(task.kind for task in TASKS)
TASK_BY_KIND = {task.kind: task for task in TASKS}

def ordered_tasks(cursor, state, config, growth, focus_streak):
    rotated = list(TASK_ORDER[cursor:] + TASK_ORDER[:cursor])
    if not config['growth_linked'] or focus_streak >= 3:
        return rotated, set()
    focus = ['slave_escape'] if state.get('world', {}).get('captured') else []
    if growth['phase'] == 'breakthrough':
        focus += ['breakthrough']
    elif growth['shortages']:
        focus += ['harvest', 'open_pack', 'breakthrough', 'material_synth', 'refine', 'world_forge', 'idle_select', 'world_harvest', 'resource_realm']
    focus = [kind for kind in focus if kind in TASK_BY_KIND]
    return focus + [k for k in rotated if k not in focus], set(focus)
