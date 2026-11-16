"""Record sanitized live proof of bound-first spending without issuing game commands."""
from datetime import datetime, timezone
import json
from pathlib import Path
from monitor import ROOT, fetch


def main():
    baseline = json.loads((ROOT / 'runtime/bound-first-live-baseline.json').read_text(encoding='utf-8'))
    status = fetch()
    prop = status['state']['world']['rumor']
    original = baseline['rumor']
    original_bound = baseline['bound_items'].get('material:4006', 0)
    row = {
        'time': datetime.now(timezone.utc).isoformat(),
        'app_version': status['app_version'],
        'bridge_revision': status['state'].get('bridge_revision'),
        'game_pid': status['pid'], 'same_game_process': status['pid'] == baseline['game_pid'],
        'enabled': status['enabled'], 'connected': status['connected'],
        'config_unchanged': status['config'] == baseline['config'],
        'before': {'count': original['count'], 'bound_count': original_bound,
                   'unbound_count': original['count'] - original_bound},
        'after': {key: prop.get(key) for key in ('count', 'bound_count', 'cost', 'spendable_count', 'bound_only_safe')},
        'successful_explorations': status.get('stats', {}).get('world_explore', 0),
        'exploration_status': status.get('task_details', {}).get('world_explore'),
        'steam_quantity': status['state'].get('steam_inventory', {}).get('quantity'),
    }
    row['after']['unbound_count'] = prop['count'] - prop['bound_count']
    row['bound_consumption_observed'] = prop['bound_count'] < original_bound and row['successful_explorations'] > 0
    row['unbound_floor_preserved'] = row['before']['unbound_count'] == row['after']['unbound_count']
    row['protected_unbound_decreases'] = []
    current = {item['key']: item for item in status['state'].get('inventory_view', {}).get('items', [])}
    for item in baseline['protected_inventory']:
        now = current.get(item['key'], {})
        first = int(item.get('count') or 0) - int(item.get('bound_count') or 0)
        last = int(now.get('count') or 0) - int(now.get('bound_count') or 0)
        if last < first:
            row['protected_unbound_decreases'].append({'key': item['key'], 'before': first, 'after': last})
    path = ROOT / 'runtime/bound-first-live-observations.jsonl'
    with path.open('a', encoding='utf-8') as output:
        output.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(json.dumps(row, ensure_ascii=False))


if __name__ == '__main__':
    main()
