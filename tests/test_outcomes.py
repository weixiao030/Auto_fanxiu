import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fanxiu_assistant.outcomes import failure_metadata, result_detail, shared_backoff
from fanxiu_assistant.policy import Planner
import fanxiu_assistant.server as server


def failure(**fields):
    return {'ok': False, 'data': {'failure': fields}}


class NativeFailureTest(TestCase):
    def test_error_code_fallback_and_specific_reason(self):
        result = failure(error_code='PREPARING_BATTLE_TIMEOUT')
        self.assertEqual(result_detail(result), '游戏请求失败：PREPARING_BATTLE_TIMEOUT')
        result['detail'] = '  等级不足  '
        self.assertEqual(result_detail(result), '等级不足')
        self.assertIn('HTTP 503', result_detail(failure(http_code=503)))

    def test_only_bounded_scalar_diagnostics_are_retained(self):
        result = failure(code='RATE_LIMITED', error_code='RETRY_LATER', http_code=429,
                         retry_after_seconds=75, body='private-body', session_token='private-token')
        self.assertEqual(failure_metadata(result), dict(code='RATE_LIMITED', error_code='RETRY_LATER',
                                                        http_code=429, retry_after_seconds=75))
        for fields in ({'code': 'Authorization: private-token'}, {'code': {'token': 'secret'}},
                       {'error_code': 'x' * 97}, {'http_code': True}, {'http_code': 200},
                       {'retry_after_seconds': math.inf}, {'retry_after_seconds': math.nan},
                       {'retry_after_seconds': -1}, {'retry_after_seconds': True},
                       {'retry_after_seconds': 86401}):
            with self.subTest(fields=fields):
                self.assertEqual(failure_metadata(failure(**fields)), {})

    def test_rate_limit_and_retry_after_pause_all_dispatch(self):
        for fields, delay in (({'http_code': 429}, 30), ({'http_code': 503}, 30),
                              ({'error_code': 'RATE_LIMITED'}, 30),
                              ({'code': 'SERVER_BUSY', 'retry_after_seconds': 75}, 75),
                              ({'retry_after_seconds': 60}, 60)):
            with self.subTest(fields=fields):
                now = [1000]
                planner = Planner(clock=lambda: now[0])
                planner.config['tasks'] = {kind: kind == 'collect' for kind in planner.config['tasks']}
                state = {'ready': True, 'online': True, 'tutorial_finished': True}
                result = failure(**fields)
                planner.observe_result({'kind': 'world_sync'}, result, state)
                self.assertEqual(shared_backoff(result), delay)
                self.assertIsNone(planner.choose(state))
                self.assertEqual(planner.server_busy_until, 1000 + delay)
                now[0] += delay + 1
                self.assertEqual(planner.choose(state)['kind'], 'collect')

    def test_controller_logs_safe_failure_once_and_never_replays_unconfirmed_battle(self):
        with TemporaryDirectory() as directory, patch.object(server, 'RUNTIME', Path(directory)):
            controller = server.Controller()
            packet = {'pid': 7, 'state': {'bridge_revision': server.MIN_BRIDGE_REVISION,
                      'ready': True, 'online': True, 'tutorial_finished': True}, 'results': []}
            controller.bridge(packet)
            controller.pending = {'id': 'battle', 'kind': 'realm_challenge', 'label': '挑战', 'params': {}}
            controller.pending_sent = True
            controller.enabled = True
            controller.resume_requested = True
            result = failure(error_code='RATE_LIMITED', http_code=429, retry_after_seconds=75,
                             body='private-body', session_token='private-token')
            result['id'] = 'battle'
            result['data']['unconfirmed'] = True
            packet['results'] = [result]
            self.assertFalse(controller.bridge(packet)['command'])
            self.assertFalse(controller.bridge(packet)['command'])
            self.assertFalse(controller.enabled)
            self.assertFalse(controller.resume_requested)
            self.assertIsNone(controller.pending)
            self.assertEqual(controller.stats['failed'], 1)
            events = [row for row in controller.events if row.get('operation_id') == 'battle']
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]['failure'], dict(error_code='RATE_LIMITED', http_code=429, retry_after_seconds=75))
            self.assertIn('RATE_LIMITED', controller.task_feedback['realm_challenge'])
            logged = (Path(directory) / 'events.jsonl').read_text(encoding='utf-8')
            self.assertNotIn('private-body', logged)
            self.assertNotIn('private-token', logged)
