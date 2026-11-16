from copy import deepcopy
import unittest

from tools.release_growth import publication_decision


class ReleasePolicyTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            'app_version': '0.47',
            'source_fingerprint': 'candidate-source',
            'user_requested_no_additional_live_confirmation': True,
            'request': '无需继续等待特定实机链，按功能检查验收。',
        }

    def decide(self, full=False, record=None):
        return publication_decision(full, record, 'candidate-source', '0.47')

    def test_default_still_requires_growth_evidence(self):
        result = self.decide()
        self.assertFalse(result['release_ready'])
        self.assertFalse(result['full_growth_verified'])
        self.assertTrue(result['growth_chain_required'])

    def test_proven_growth_can_release_without_exception(self):
        result = self.decide(full=True)
        self.assertEqual(result['status'], 'PASS')
        self.assertTrue(result['release_ready'])
        self.assertTrue(result['full_growth_verified'])

    def test_functional_acceptance_does_not_fabricate_growth_proof(self):
        result = self.decide(record=self.record)
        self.assertEqual(result['status'], 'FUNCTIONAL_PASS')
        self.assertTrue(result['release_ready'])
        self.assertFalse(result['full_growth_verified'])
        self.assertFalse(result['growth_chain_required'])
        self.assertEqual(result['acceptance_basis'], 'functional_checks_and_existing_live_stability')

    def test_exception_cannot_apply_to_another_source_or_version(self):
        for key in ('app_version', 'source_fingerprint'):
            changed = dict(self.record, **{key: 'another-candidate'})
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.decide(record=changed)

    def test_explicit_boolean_authorization_required(self):
        for value in (False, None, 1, 'true'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.decide(record=dict(self.record, user_requested_no_additional_live_confirmation=value))

    def test_request_must_be_present_and_bounded(self):
        for value in (None, '', '   ', [], 'x' * 1001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.decide(record=dict(self.record, request=value))

    def test_malformed_record_cannot_release(self):
        for value in ([], '', True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.decide(record=value)

    def test_public_record_is_sanitized_without_mutating_input(self):
        original = dict(self.record, private_path='private-fixture', request='  明确指令  ')
        saved = deepcopy(original)
        public = self.decide(record=original)['functional_acceptance']
        self.assertNotIn('private_path', public)
        self.assertEqual(public['request'], '明确指令')
        self.assertEqual(original, saved)


if __name__ == '__main__':
    unittest.main()
