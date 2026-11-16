from copy import deepcopy
import unittest
from tools.build_exe import validate_functional_waiver

class FunctionalWaiverTests(unittest.TestCase):
    def setUp(self):
        self.info = dict(app_version='0.48', sha256='exe')
        self.record = dict(user_requested_skip_monitoring=True, request='无需额外实机等待', app_version='0.48', source_fingerprint='source')
        self.checks = {name:dict(status='PASS', source_fingerprint='source') for name in ('quick-regression', 'summary', 'native-contracts', 'project-ui', 'growth-ui', 'review-ui')}
        self.checks['summary']['exe_sha256'] = 'exe'
        self.checks['quick-regression'].update(positive_task_paths=43, task_count=43)
    def check(self): validate_functional_waiver(self.record, self.info, 'source', self.checks)
    def test_current_checks_and_instruction_allow_promotion(self): self.check()
    def test_stale_instruction_is_rejected(self):
        for key in ('app_version', 'source_fingerprint'):
            saved=self.record.copy();self.record[key]='old'
            with self.assertRaises(ValueError): self.check()
            self.record=saved
    def test_stale_missing_or_failed_checks_are_rejected(self):
        for name in self.checks:
            for mutation in ({}, dict(status='FAIL', source_fingerprint='source'), dict(status='PASS', source_fingerprint='old')):
                saved=deepcopy(self.checks);self.checks[name]=mutation
                with self.subTest(name=name), self.assertRaises(ValueError): self.check()
                self.checks=saved
    def test_different_exe_or_incomplete_coverage_is_rejected(self):
        self.checks['summary']['exe_sha256']='old'
        with self.assertRaises(ValueError): self.check()
        self.checks['summary']['exe_sha256']='exe'
        self.checks['quick-regression']['positive_task_paths']=42
        with self.assertRaises(ValueError): self.check()
    def test_instruction_is_explicit(self):
        for value in (False, 1, 'true', None):
            self.record['user_requested_skip_monitoring']=value
            with self.assertRaises(ValueError): self.check()
