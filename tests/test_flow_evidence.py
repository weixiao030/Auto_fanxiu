from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from fanxiu_assistant.flow_evidence import assess_flow, sanitize_receipt


def event(kind, sequence, before=None, after=None, needs=None, outputs=None, rewards=None):
    snapshot = lambda items, advanced: {
        'items': items or {}, 'level': 10 if advanced and kind == 'breakthrough' else 9,
        'equipment_id': 17 if kind == 'upgrade' else 0,
        'equipment_level': (3 if advanced else 2) if kind == 'upgrade' else 0}
    return {'operation_id': f'op-{sequence}', 'run_id': 'fixture-run', 'operation_sequence': sequence,
            'time': (datetime(2026, 11, 8, tzinfo=timezone.utc) + timedelta(seconds=sequence)).isoformat(),
            'bridge_revision': 29, 'kind': kind, 'level': 'success', 'message': 'fixture',
            'growth_receipt': {'schema': 1, 'kind': kind, 'native_success': True,
                               'requirements': needs or {}, 'outputs': outputs or {},
                               'native_rewards': rewards or {},
                               'before': snapshot(before, False), 'after': snapshot(after, True)}}


def source(kind='refine', amount=3, initial=0):
    return event(kind, 1, {'material:1': 10, 'material:2': initial},
                 {'material:1': 8, 'material:2': initial + amount}, {'material:1': 2},
                 {'material:2': amount}, {'material:2': amount})


def upgrade(sequence=2, amount=3, initial=None):
    initial = amount if initial is None else initial
    return event('upgrade', sequence, {'material:2': initial}, {'material:2': initial - amount},
                 {'material:2': amount})


class FlowEvidenceTest(unittest.TestCase):
    def test_native_reward_must_cover_shortage_and_finish_actual_upgrade(self):
        for kind in ('refine', 'world_forge'):
            result = assess_flow([source(kind), upgrade()])
            self.assertTrue(result['causal_chain_proven'])
            self.assertEqual(result['chains'][0]['handoffs'][0]['contributed_at_least'], 3)

    def test_action_counts_or_success_messages_are_insufficient(self):
        self.assertFalse(assess_flow([])['causal_chain_proven'])
        rows = [source(), upgrade()]
        for row in rows: row.pop('growth_receipt')
        self.assertFalse(assess_flow(rows)['causal_chain_proven'])

    def test_old_inventory_already_sufficient_is_not_attributed_to_refine(self):
        self.assertFalse(assess_flow([source(initial=3), upgrade(initial=6)])['causal_chain_proven'])

    def test_partial_shortage_records_only_necessary_contribution(self):
        result = assess_flow([source(initial=2), upgrade(initial=5)])
        self.assertTrue(result['causal_chain_proven'])
        self.assertEqual(result['chains'][0]['handoffs'][0]['contributed_at_least'], 1)

    def test_native_reward_disagreement_or_unexpected_drop_cannot_prove_chain(self):
        for change in ('reward', 'before_consume', 'after_consume'):
            a, b = source(), upgrade()
            if change == 'reward': a['growth_receipt']['native_rewards']['material:2'] = 4
            if change == 'before_consume':
                b['growth_receipt']['before']['items']['material:2'] = 5
                b['growth_receipt']['after']['items']['material:2'] = 2
            if change == 'after_consume': b['growth_receipt']['after']['items']['material:2'] = 1
            self.assertFalse(assess_flow([a, b])['causal_chain_proven'], change)

    def test_native_success_without_power_gain_or_confirmation_is_insufficient(self):
        for change in ('no_gain', 'native_failed', 'failed_event'):
            a, b = source(), upgrade()
            if change == 'no_gain': b['growth_receipt']['after']['equipment_level'] = 2
            if change == 'native_failed': a['growth_receipt']['native_success'] = False
            if change == 'failed_event': b['level'] = 'warning'
            self.assertFalse(assess_flow([a, b])['causal_chain_proven'], change)

    def test_material_conversion_handoff_reaches_upgrade(self):
        conversion = event('material_synth', 2,
                           {'material:2': 6, 'material:3': 0}, {'material:2': 0, 'material:3': 2},
                           {'material:2': 6}, {'material:3': 2})
        growth = event('upgrade', 3, {'material:3': 2}, {'material:3': 0}, {'material:3': 2})
        result = assess_flow([source(amount=6), conversion, growth])
        self.assertTrue(result['causal_chain_proven'])
        self.assertEqual(len(result['chains'][0]['handoffs']), 2)

    def test_confirmed_breakthrough_requires_real_level_gain(self):
        growth = event('breakthrough', 2, {'material:2': 3}, {'material:2': 0}, {'material:2': 3})
        self.assertTrue(assess_flow([source(), growth])['causal_chain_proven'])
        growth['growth_receipt']['after']['level'] = 9
        self.assertFalse(assess_flow([source(), growth])['causal_chain_proven'])

    def test_alchemy_output_alone_is_not_actual_growth(self):
        craft = event('alchemy', 2, {'material:2': 3, 'pill:6001': 0},
                      {'material:2': 0, 'pill:6001': 1}, {'material:2': 3}, {'pill:6001': 1})
        self.assertFalse(assess_flow([source(), craft])['causal_chain_proven'])

    def test_restart_gap_or_untraced_mutation_breaks_continuity(self):
        a, b = source(), upgrade()
        for mutation in ('restart', 'gap', 'untraced'):
            rows = [deepcopy(a), deepcopy(b)]
            if mutation == 'restart': rows[1]['run_id'] = 'new-client'
            if mutation == 'gap': rows[1]['operation_sequence'] = 3
            if mutation == 'untraced':
                rows[1]['operation_sequence'] = 3
                rows.insert(1, event('gacha', 2))
            self.assertFalse(assess_flow(rows)['causal_chain_proven'], mutation)

    def test_read_only_sync_may_intervene_but_inventory_still_must_match(self):
        rows = [source(), event('world_sync', 2), upgrade(3)]
        self.assertTrue(assess_flow(rows)['causal_chain_proven'])

    def test_duplicate_delivery_is_deduplicated_and_conflicts_rejected(self):
        a, b = source(), upgrade()
        self.assertEqual(len(assess_flow([a, deepcopy(a), b])['chains']), 1)
        conflict = deepcopy(a); conflict['growth_receipt']['before']['items']['material:2'] = 99
        self.assertFalse(assess_flow([a, conflict, b])['causal_chain_proven'])
        b['operation_id'] = a['operation_id']
        self.assertFalse(assess_flow([a, b])['causal_chain_proven'])

    def test_other_revision_and_receipts_before_monitoring_are_excluded(self):
        a, b = source(), upgrade()
        self.assertFalse(assess_flow([a, b], revision=28)['causal_chain_proven'])
        self.assertFalse(assess_flow([a, b], started=b['time'])['causal_chain_proven'])
        self.assertFalse(assess_flow([a, b], finished=a['time'])['causal_chain_proven'])

    def test_sanitization_drops_unrelated_native_fields(self):
        raw = source()['growth_receipt']
        raw['session_token'] = 'fixture-secret'
        raw['before']['account'] = 'fixture-account'
        clean = sanitize_receipt(raw, 'refine')
        self.assertNotIn('fixture-secret', str(clean))
        self.assertNotIn('fixture-account', str(clean))
        self.assertIsNone(sanitize_receipt(raw, 'upgrade'))

    def test_bad_optional_evidence_does_not_raise(self):
        for value in (None, [], {}, {'schema': 1}, {'schema': 1, 'kind': ['refine']}):
            self.assertIsNone(sanitize_receipt(value))
        for value in (-1, True, float('nan'), float('inf'), '3', 1.25):
            raw = source()['growth_receipt']; raw['before']['items']['material:1'] = value
            self.assertIsNone(sanitize_receipt(raw))

    def test_cycles_and_unknown_keys_are_not_proof(self):
        raw = source()['growth_receipt']; raw['outputs']['material:1'] = 1
        a = source(); a['growth_receipt'] = raw
        self.assertFalse(assess_flow([a, upgrade()])['causal_chain_proven'])
        raw['before']['items']['session:1'] = 3
        self.assertIsNone(sanitize_receipt(raw))

    def test_malformed_event_identity_cannot_crash_or_prove_handoff(self):
        for value in ([], {}, 1, True, '', 'x' * 129):
            a = source(); a['operation_id'] = value
            self.assertFalse(assess_flow([a, upgrade()])['causal_chain_proven'])
