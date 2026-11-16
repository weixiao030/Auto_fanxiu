from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from tempfile import TemporaryDirectory
from http.server import ThreadingHTTPServer
from threading import Thread
import json, time, urllib.request, urllib.error
import fanxiu_assistant.server as server
from fanxiu_assistant.policy import DEFAULTS

class ControllerTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.runtime = patch.object(server, 'RUNTIME', Path(self.temp.name)); self.runtime.start()
        self.c = server.Controller()

    def tearDown(self):
        self.runtime.stop(); self.temp.cleanup()

    def packet(self, results=None, pid=7):
        return {'pid':pid,'state':{'bridge_revision':server.MIN_BRIDGE_REVISION,'ready':True,'online':True,'tutorial_finished':True,'pending':0},'results':results or []}

    def test_manual_exploration_returns_specific_protection_reason(self):
        from test_expansion import ExpansionTest
        planner, state = ExpansionTest().exploration_fixture()
        self.c.bridge({'pid': 7, 'state': state})
        self.c.planner.config = planner.config
        self.c.queue_task('world_explore')
        self.assertIsNone(self.c.pending)
        self.assertIn('绑定份不足', self.c.task_feedback['world_explore'])
        detail = self.c.public()['task_details']['world_explore']
        self.assertFalse(detail['ready'])
        self.assertEqual(detail['props'][1]['bound_count'], 0)

    def test_manual_breakthrough_keeps_gathering_dependencies_without_dispatching_others(self):
        from test_breakthrough import BreakthroughClarityTest
        planner, state = BreakthroughClarityTest().base()
        self.c.bridge({'pid':7,'state':state})
        self.c.planner.config = planner.config
        self.c.queue_task('breakthrough')
        self.assertEqual(self.c.pending['parent_kind'], 'breakthrough')
        self.assertEqual(self.c.pending['kind'], 'idle_select')
        self.assertEqual(self.c.pending['params']['key'], '1_2_7')
        self.assertTrue(self.c.planner.config['tasks']['harvest'])

    def test_manual_other_task_keeps_breakthrough_reserve(self):
        from test_breakthrough import fixture
        from unittest.mock import patch
        planner, state = fixture()
        self.c.bridge({'pid':7,'state':state})
        self.c.planner.config = planner.config
        with patch.object(self.c.planner, 'plan_collect', side_effect=lambda s: self.assertEqual(self.c.planner.spendable(s, 'material', 1099),74)):
            self.c.queue_task('collect')
        self.assertIsNone(self.c.pending)

    def test_stop_cancels_only_unsent_manual_work(self):
        self.c.pending={'id':'unsent','kind':'collect','label':'领取','params':{}}
        self.c.manual=True
        self.c.stop()
        self.assertIsNone(self.c.pending)
        self.assertFalse(self.c.manual)
        self.assertFalse(self.c.bridge(self.packet())['command'])

    def test_stop_waits_for_delivered_work_without_repeating(self):
        self.c.bridge(self.packet())
        self.c.pending={'id':'sent','kind':'collect','label':'领取','params':{}}
        self.c.pending_at=time.monotonic(); self.c.manual=True
        self.assertEqual(self.c.bridge(self.packet())['command']['id'],'sent')
        self.c.stop()
        self.assertIsNotNone(self.c.pending)
        self.assertFalse(self.c.bridge(self.packet())['command'])
        packet=self.packet([{'id':'sent','ok':True,'detail':'confirmed'}])
        self.assertEqual(self.c.bridge(packet)['acks'],['sent'])
        self.c.bridge(packet)
        self.assertIsNone(self.c.pending)
        self.assertEqual(self.c.stats['success'],1)

    def test_replacement_client_does_not_inherit_pending_manual_work(self):
        self.c.pid=7; self.c.last_seen=time.monotonic()-31
        self.c.pending={'id':'old'};self.c.manual=True;self.c.enabled=True
        self.c.bridge(self.packet(pid=8))
        self.assertIsNone(self.c.pending)
        self.assertFalse(self.c.enabled);self.assertFalse(self.c.manual)

    def test_native_growth_evidence_is_sanitized_and_duplicate_receipts_count_once(self):
        from test_flow_evidence import source
        self.c.bridge(self.packet())
        raw = source()['growth_receipt']; raw['session_token'] = 'private-fixture'
        raw['before']['identity'] = 'private-identity'
        self.c.pending = {'id':'flow-op','kind':'refine','label':'炼化','params':{}}
        self.c.pending_at = time.monotonic(); self.c.pending_sent = True
        packet = self.packet([{'id':'flow-op','ok':True,'data':{'growth_receipt':raw}}])
        self.c.bridge(packet); self.c.bridge(packet)
        rows = [r for r in self.c.events if r.get('operation_id') == 'flow-op']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['operation_sequence'], 1)
        self.assertNotIn('private-fixture', str(rows)); self.assertNotIn('private-identity', str(rows))
        first_run = rows[0]['run_id']
        self.c.last_seen -= 31
        self.c.bridge(self.packet(pid=8))
        self.assertNotEqual(first_run, self.c.operation_run)
        self.assertEqual(self.c.operation_sequence, 0)

    def test_bad_optional_growth_evidence_does_not_break_result_confirmation(self):
        from test_flow_evidence import source
        for i, raw in enumerate((None, [], {'schema':1,'kind':['refine']}, source()['growth_receipt'])):
            self.c.bridge(self.packet())
            rid = 'op-' + str(i)
            self.c.pending = {'id':rid,'kind':'upgrade','label':'强化','params':{}}
            self.c.pending_at = time.monotonic(); self.c.pending_sent = True
            result = self.c.bridge(self.packet([{'id':rid,'ok':True,'data':{'growth_receipt':raw}}]))
            self.assertIn(rid, result['acks'])
            self.assertIsNone(self.c.pending)
            row = next(r for r in self.c.events if r.get('operation_id') == rid)
            self.assertNotIn('growth_receipt', row)

    def test_active_client_rejects_second_instance(self):
        self.c.bridge(self.packet())
        with self.assertRaises(ValueError): self.c.bridge(self.packet(pid=8))

    def test_busy_click_queues_once_and_executes_after_confirmation(self):
        self.c.bridge(self.packet())
        self.c.pending={'id':'first','kind':'world_sync','label':'同步','params':{}}
        self.c.pending_at=time.monotonic();self.c.pending_sent=True
        self.c.queue_task('collect');self.c.queue_task('collect')
        self.assertEqual(list(self.c.manual_queue),['collect'])
        self.assertEqual(self.c.pending['id'],'first')
        response=self.c.bridge(self.packet([{'id':'first','ok':True}]))
        self.assertEqual(response['command']['kind'],'collect')
        self.assertFalse(self.c.manual_queue)

    def test_queue_waits_for_battle_and_rechecks_changed_protection(self):
        packet=self.packet();packet['state']['battle']=True
        self.c.bridge(packet);self.c.queue_task('synth')
        self.assertIsNone(self.c.pending)
        self.assertEqual(list(self.c.manual_queue),['synth'])
        self.c.bridge(self.packet())
        self.assertIsNone(self.c.pending)
        self.assertFalse(self.c.manual_queue)
        self.assertIn('同步',self.c.task_feedback['synth'])

    def test_pause_cancels_queue_without_cancelling_sent_operation(self):
        self.c.bridge(self.packet())
        self.c.pending={'id':'sent','kind':'world_sync','label':'同步','params':{}}
        self.c.pending_sent=True;self.c.queue_task('collect');self.c.stop()
        self.assertFalse(self.c.manual_queue)
        self.assertEqual(self.c.pending['id'],'sent')

    def test_delayed_heartbeat_keeps_connection_without_dispatching(self):
        self.c.bridge(self.packet());self.c.last_seen=time.monotonic()-12
        state=self.c.public()
        self.assertTrue(state['connected'])
        self.assertEqual(state['connection']['state'],'recovering')
        self.c.queue_task('collect')
        self.assertIsNone(self.c.pending)
        self.c.bridge(self.packet())
        self.assertEqual(self.c.pending['kind'],'collect')
        self.c.last_seen=time.monotonic()-31
        self.assertFalse(self.c.public()['connected'])

    def test_queue_respects_minimum_action_interval(self):
        self.c.bridge(self.packet());self.c.planner.last_action=time.monotonic()
        self.c.queue_task('collect');self.assertIsNone(self.c.pending)
        self.c.planner.last_action-=10
        self.c.bridge(self.packet())
        self.assertEqual(self.c.pending['kind'],'collect')

    def test_queued_work_waits_for_shared_server_backoff(self):
        self.c.bridge(self.packet())
        self.c.planner.server_busy_until=time.monotonic()+30
        self.c.queue_task('collect')
        self.assertIsNone(self.c.pending)
        self.assertGreater(self.c.public()['retry_after_seconds'],0)
        self.c.planner.server_busy_until=time.monotonic()-1
        self.c.bridge(self.packet())
        self.assertEqual(self.c.pending['kind'],'collect')

    def test_all_features_accept_one_queue_entry_while_busy(self):
        self.c.bridge(self.packet());self.c.state['battle']=True
        for kind in server.LABELS:
            self.c.queue_task(kind);self.c.queue_task(kind)
        self.assertEqual(len(self.c.manual_queue),len(server.LABELS))
        self.assertIsNone(self.c.pending)
        self.c.stop();self.assertFalse(self.c.manual_queue)

    def test_local_http_origin_csrf_and_manual_pause(self):
        http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        http.controller=self.c; http.daemon_threads=True
        thread=Thread(target=http.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{http.server_port}'
        def post(route, body, headers=None):
            req=urllib.request.Request(base+route,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**(headers or {})})
            with urllib.request.urlopen(req,timeout=3) as response:return json.load(response)
        try:
            with self.assertRaises(urllib.error.HTTPError) as err:post('/api/start',{})
            self.assertEqual(err.exception.code,403)
            self.c.bridge(self.packet())
            headers={'Origin':base,'X-CSRF-Token':self.c.csrf}
            post('/api/run',{'kind':'collect'},headers)
            self.assertTrue(self.c.manual)
            post('/api/run',{'kind':'world_sync'},headers)
            self.assertEqual(list(self.c.manual_queue),['world_sync'])
            post('/api/cancel-run',{'kind':'world_sync'},headers)
            self.assertFalse(self.c.manual_queue)
            self.assertEqual(self.c.pending['kind'],'collect')
            post('/api/stop',{},headers)
            self.assertIsNone(self.c.pending)
            post('/api/start',{},headers)
            self.assertTrue(self.c.enabled)
            req=urllib.request.Request(base+'/api/status',headers={'Host':'outside.invalid'})
            with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
            self.assertEqual(err.exception.code,403)
        finally:
            http.shutdown();http.server_close();thread.join(3)
