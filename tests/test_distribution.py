from fanxiu_assistant.server import MIN_BRIDGE_REVISION
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import io
import tempfile
import threading
import unittest
from unittest.mock import patch
from fanxiu_assistant.policy import DEFAULTS, validate_config
from fanxiu_assistant import game_location as location
from fanxiu_assistant.supervisor import Supervisor, steam_update_needed


class DistributionTests(unittest.TestCase):
    def test_steam_update_response_is_parsed_and_validated(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);game=root/'common'/'凡修';game.mkdir(parents=True)
            (root/'appmanifest_3301840.acf').write_text('"buildid" "12345"',encoding='utf-8')
            for current in (True,False):
                with self.subTest(up_to_date=current), patch('fanxiu_assistant.supervisor.urllib.request.urlopen',return_value=io.StringIO(json.dumps({'response':{'success':True,'up_to_date':current}}))) as request:
                    self.assertEqual(steam_update_needed(game),not current)
                    self.assertIn('version=12345',request.call_args.args[0].full_url)
            with patch('fanxiu_assistant.supervisor.urllib.request.urlopen',return_value=io.StringIO('{"response":{"success":true}}')):
                with self.assertRaises(ValueError):steam_update_needed(game)

    def test_shipping_defaults(self):
        c = validate_config({})
        self.assertTrue(c['preserve_steam_tradable']);self.assertFalse(c['preserve_tradable'])
        self.assertEqual(c['min_breakthrough_rate'], .545)
        self.assertEqual(c['reserve_wuxing'], 0)
        self.assertTrue(c['auto_reconnect']);self.assertFalse(c['auto_steam_update'])
        self.assertFalse(c['allow_game_restart'])
        self.assertEqual(c['upgrade_reserve'],0)
        self.assertEqual(c['synth_max_quality'],'treasure')
        self.assertTrue(c['world_use_mirror'])
        self.assertEqual(c['world_mirror_target'],'auto')
        self.assertTrue(c['resource_realm_use_token'])

    def test_steam_library_and_manifest_with_spaces_and_chinese(self):
        with tempfile.TemporaryDirectory() as temp:
            root, library = Path(temp)/'Steam', Path(temp)/'游戏 Library'
            (root/'steamapps').mkdir(parents=True)
            (root/'steamapps/libraryfolders.vdf').write_text('"libraryfolders" { "1" { "path" "'+str(library).replace('\\','\\\\')+'" } }',encoding='utf-8')
            game = library/'steamapps/common/凡修'
            game.mkdir(parents=True)
            (game/'run.exe').write_bytes(b'fixture')
            (game/'release-manifest.json').write_text('{"app_id":"3301840","version":"future"}')
            (library/'steamapps/appmanifest_3301840.acf').write_text('"installdir" "凡修"',encoding='utf-8')
            with patch.object(location,'steam_roots',return_value=[root]), patch.object(location,'process_images',return_value=[]), patch.object(location,'RUNTIME',Path(temp)/'profile'):
                self.assertEqual(location.detect_game(),game.resolve())

    def test_running_game_has_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            game=Path(temp);(game/'run.exe').touch();(game/'release-manifest.json').write_text('{"app_id":"3301840","version":"future"}')
            with patch.object(location,'process_images',return_value=[(12,game/'run.exe')]):
                self.assertEqual(location.detect_game(),game)

    def controller(self):
        c = SimpleNamespace(lock=threading.RLock(),planner=SimpleNamespace(config=deepcopy(DEFAULTS)),
            state={'ready':True,'bridge_revision':MIN_BRIDGE_REVISION,'network_blocked':False},last_seen=100,pid=42,
            pending=None, enabled=False,resume_requested=True,maintenance={},log=lambda *a:None)
        c.planner.config['auto_steam_update']=False
        return c

    def test_native_reconnect_resumes_only_requested_session(self):
        c=self.controller();s=Supervisor(c,Path('.'))
        s.step(101);self.assertTrue(c.enabled)
        c.enabled=False;c.resume_requested=False;s.step(102);self.assertFalse(c.enabled)

    def test_blocked_session_does_not_restart_or_take_over(self):
        c=self.controller();c.state['network_blocked']=True;s=Supervisor(c,Path('.'))
        with patch.object(s,'restart') as restart:
            s.step(101);self.assertFalse(c.enabled);restart.assert_not_called()

    def test_short_heartbeat_gap_keeps_session_without_update_or_restart(self):
        c=self.controller();c.planner.config['auto_steam_update']=True
        c.state['client_update']={'state':'required'}
        s=Supervisor(c,Path('.'))
        with patch.object(s,'restart') as restart, patch('fanxiu_assistant.supervisor.steam_update_needed') as update:
            s.step(112)
            restart.assert_not_called();update.assert_not_called()
            self.assertIn('保持会话',c.maintenance['message'])

    def test_recovery_wait_backoff_and_attempt_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            game=Path(temp);(game/'release-manifest.json').write_text('{"version":"0.2.18"}')
            c=self.controller();c.planner.config['allow_game_restart']=True;c.last_seen=0;c.planner.config['reconnect_max_attempts']=1
            s=Supervisor(c,game)
            with patch.object(s,'restart') as restart:
                s.step(100);restart.assert_not_called()
                s.step(159);restart.assert_not_called()
                s.step(160);self.assertEqual(restart.call_count,1)
                s.step(300);self.assertEqual(restart.call_count,1)

    def test_steam_update_waits_for_battle_and_pending_operations(self):
        c=self.controller();c.planner.config['allow_game_restart']=True;c.planner.config['auto_steam_update']=True;c.state['battle']=True
        s=Supervisor(c,Path('.'))
        with patch('fanxiu_assistant.supervisor.steam_update_needed',return_value=True), patch.object(s,'restart') as restart:
            s.step(101);restart.assert_not_called()
            c.state['battle']=False;c.pending={'id':'already-submitted'};s.step(102);restart.assert_not_called()
            c.pending=None;s.step(103);restart.assert_called_once()

    def test_unknown_game_version_recovers_with_normal_backoff(self):
        with tempfile.TemporaryDirectory() as temp:
            game=Path(temp);(game/'release-manifest.json').write_text('{"version":"future"}')
            c=self.controller();c.planner.config['allow_game_restart']=True;c.last_seen=0;s=Supervisor(c,game)
            with patch.object(s,'restart') as restart:
                s.step(100);restart.assert_not_called()
                s.step(200);restart.assert_called_once()
                s.step(201);restart.assert_called_once()
            self.assertEqual(s.attempts,1)
            self.assertIn('等待恢复间隔',c.maintenance['message'])

    def test_stale_heartbeat_after_restart_does_not_count_as_recovery(self):
        c=self.controller();s=Supervisor(c,Path('.'));s.restarted_pid=42
        s.step(101);self.assertFalse(c.enabled)
        c.pid=43;s.step(102);self.assertTrue(c.enabled)


if __name__=='__main__':unittest.main()
