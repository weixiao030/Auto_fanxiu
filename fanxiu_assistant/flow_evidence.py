"""Conservative resource handoffs from native receipts, never from action totals."""
from collections import defaultdict
from datetime import datetime
import math
import re

RESOURCE = re.compile(r'^(material|herb|pill):[1-9][0-9]{0,15}$')
KINDS = {'refine', 'world_forge', 'material_synth', 'alchemy', 'upgrade', 'breakthrough'}
READ_ONLY = {'world_sync', 'social_sync', 'bounty_sync'}


def integer(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value != int(value):
        raise ValueError('invalid quantity')
    if not 0 <= value <= 2**53 - 1:
        raise ValueError('quantity out of range')
    return int(value)


def quantities(raw):
    if not isinstance(raw, dict) or len(raw) > 2048:
        raise ValueError('invalid resources')
    result = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not RESOURCE.fullmatch(key):
            raise ValueError('invalid resource key')
        result[key] = integer(value)
    return result


def sanitize_receipt(raw, expected_kind=None):
    """Drop unknown fields; malformed optional evidence cannot break scheduling."""
    try:
        if not isinstance(raw, dict) or raw.get('schema') != 1 or not isinstance(raw.get('kind'), str) or raw.get('kind') not in KINDS:
            return None
        if expected_kind is not None and raw['kind'] != expected_kind:
            return None
        result = {'schema': 1, 'kind': raw['kind'], 'native_success': raw.get('native_success') is True}
        for name in ('requirements', 'outputs', 'native_rewards'):
            result[name] = quantities(raw.get(name, {}))
        for phase in ('before', 'after'):
            snapshot = raw[phase]
            result[phase] = {'items': quantities(snapshot['items'])}
            for key in ('level', 'equipment_id', 'equipment_level'):
                result[phase][key] = integer(snapshot.get(key, 0))
        return result
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def balanced(receipt):
    if not receipt or not receipt['native_success'] or not receipt['requirements']:
        return False
    before, after = receipt['before']['items'], receipt['after']['items']
    needs, outputs = receipt['requirements'], receipt['outputs']
    if set(before) != set(after) or not (set(needs) | set(outputs)) <= set(before):
        return False
    if any(n <= 0 for n in needs.values()) or any(n <= 0 for n in outputs.values()):
        return False
    if set(needs) & set(outputs):
        return False  # No cyclic or self-producing proof.
    if any(after[k] != n - needs.get(k, 0) + outputs.get(k, 0) for k, n in before.items()):
        return False
    kind = receipt['kind']
    if kind in ('refine', 'world_forge'):
        return bool(outputs) and outputs == receipt['native_rewards']
    if kind in ('material_synth', 'alchemy'):
        return bool(outputs)
    if outputs:
        return False
    if kind == 'upgrade':
        return (receipt['before']['equipment_id'] > 0
                and receipt['before']['equipment_id'] == receipt['after']['equipment_id']
                and receipt['after']['equipment_level'] > receipt['before']['equipment_level'])
    return kind == 'breakthrough' and receipt['after']['level'] > receipt['before']['level']


def assess_flow(events, *, started=None, finished=None, revision=None):
    """Require a native reward to cover a shortage and be spent in actual growth.

    Unsupported mutations, failures, missing completions, restarts and inventory
    discontinuities break a chain. This deliberately reports some valid gameplay
    as unproven instead of attributing old stock or passive drops to refinement.
    """
    groups = defaultdict(dict)
    invalid_runs = set()
    begin = datetime.fromisoformat(started) if started else None
    end = datetime.fromisoformat(finished) if finished else None
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get('operation_id'), str) or not 1 <= len(event['operation_id']) <= 128:
            continue
        try:
            stamp = datetime.fromisoformat(event['time'])
            if (begin and stamp < begin) or (end and stamp > end):
                continue
            run, sequence = event['run_id'], integer(event['operation_sequence'])
            if not isinstance(run, str) or not 1 <= len(run) <= 80 or sequence < 1:
                continue
            if revision is not None and event.get('bridge_revision') != revision:
                continue
            previous = groups[run].get(sequence)
            if previous is not None and previous != event:
                invalid_runs.add(run)
            groups[run][sequence] = event
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    chains, receipts = [], 0
    for run, rows in groups.items():
        if run in invalid_runs:
            continue
        pending, last_sequence, seen_ids = [], None, set()
        for sequence, event in sorted(rows.items()):
            operation = event['operation_id']
            if operation in seen_ids:
                pending = []
                last_sequence = sequence
                continue
            seen_ids.add(operation)
            if last_sequence is not None and sequence != last_sequence + 1:
                pending = []
            last_sequence = sequence
            if event.get('level') != 'success':
                pending = []
                continue
            receipt = sanitize_receipt(event.get('growth_receipt'), event.get('kind'))
            if not balanced(receipt):
                if event.get('kind') not in READ_ONLY:
                    pending = []
                continue
            receipts += 1
            before = receipt['before']['items']
            after = receipt['after']['items']
            following = []
            for node in pending:
                key = node['resource']
                required = receipt['requirements'].get(key, 0)
                if before.get(key) != node['after_count'] or required <= node['baseline']:
                    continue
                edge = {'from_operation': node['operation'], 'to_operation': operation,
                        'resource': key, 'contributed_at_least': required - node['baseline']}
                path = node['path'] + [edge]
                if receipt['kind'] in ('upgrade', 'breakthrough'):
                    chains.append({'source_operation': node['source'], 'growth_operation': operation,
                                   'growth_kind': receipt['kind'], 'handoffs': path})
                elif receipt['kind'] in ('material_synth', 'alchemy'):
                    for output in receipt['outputs']:
                        following.append({'source': node['source'], 'operation': operation,
                                          'resource': output, 'baseline': before[output],
                                          'after_count': after[output], 'path': path})
            if receipt['kind'] in ('refine', 'world_forge'):
                for output in receipt['outputs']:
                    following.append({'source': operation, 'operation': operation, 'resource': output,
                                      'baseline': before[output], 'after_count': after[output], 'path': []})
            pending = following
    return {'schema': 1, 'causal_chain_proven': bool(chains), 'balanced_receipts': receipts,
            'chains': chains, 'scope': 'Native reward, necessary resource handoff, exact quantities and actual upgrade/level gain; gaps or unrelated mutations invalidate the chain.'}
