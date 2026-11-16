from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import test_distribution as distribution
from fanxiu_assistant.settings import validate_config
from fanxiu_assistant.session_upgrade import stage_bridge
from fanxiu_assistant.supervisor import Supervisor


class SessionContinuityTests(unittest.TestCase):
    def test_old_configs_default_to_no_restart(self):
        config = validate_config({'auto_reconnect': True, 'auto_steam_update': True})
        self.assertFalse(config['allow_game_restart'])
        with self.assertRaises(ValueError):
            validate_config({'allow_game_restart': 1})

    def test_every_supervisor_recovery_path_obeys_no_restart(self):
        for scenario in ('old_bridge', 'steam_update', 'disconnected', 'queue'):
            with self.subTest(scenario=scenario):
                c = distribution.DistributionTests().controller()
                c.planner.config.update(allow_game_restart=False, auto_reconnect=True, auto_steam_update=True)
                if scenario == 'old_bridge': c.state['bridge_revision'] = 1
                if scenario == 'steam_update': c.state['client_update'] = {'state': 'required'}
                if scenario == 'disconnected': c.last_seen = 0
                if scenario == 'queue': c.state.update(ready=False, login_queue={'active': True})
                s = Supervisor(c, Path('.')); s.update_pending = True
                with patch.object(s, 'restart') as restart, patch('fanxiu_assistant.supervisor.launch_steam') as launch, patch('fanxiu_assistant.supervisor.steam_update_needed') as update:
                    s.step(101); s.step(500); s.step(1000)
                    restart.assert_not_called(); launch.assert_not_called(); update.assert_not_called()

    def test_restart_final_guard_checks_latest_setting(self):
        c = distribution.DistributionTests().controller(); s = Supervisor(c, Path('.'))
        with patch('fanxiu_assistant.supervisor.game_processes') as lookup, patch('fanxiu_assistant.supervisor.close_window') as close, patch('fanxiu_assistant.supervisor.launch_steam') as launch:
            with self.assertRaisesRegex(RuntimeError, '禁止重启'):
                s.restart()
            lookup.assert_not_called(); close.assert_not_called(); launch.assert_not_called()

    def test_automation_resumes_existing_client_with_restart_forbidden(self):
        c = distribution.DistributionTests().controller(); c.planner.config['allow_game_restart'] = False
        Supervisor(c, Path('.')).step(101)
        self.assertTrue(c.enabled)

    def test_staging_is_immutable_and_manifest_is_last(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            for name in ('assistant.gd', 'resource_budget.gd', 'session_upgrade.gd'):
                (folder / name).write_text('extends Node\n', encoding='utf-8')
            first = stage_bridge(folder)
            self.assertEqual(stage_bridge(folder), first)
            old = (folder / first['target']).read_bytes()
            (folder / 'assistant.gd').write_text('extends Node\n# new\n', encoding='utf-8')
            second = stage_bridge(folder)
            self.assertNotEqual(second['target'], first['target'])
            self.assertEqual((folder / first['target']).read_bytes(), old)
            (folder / second['target']).write_text('damaged', encoding='utf-8')
            manifest = (folder / 'session-upgrade.json').read_bytes()
            with self.assertRaisesRegex(RuntimeError, '校验失败'): stage_bridge(folder)
            self.assertEqual((folder / 'session-upgrade.json').read_bytes(), manifest)

    def test_partial_scripts_never_publish_manifest(self):
        with TemporaryDirectory() as temp:
            with self.assertRaises(RuntimeError): stage_bridge(temp)
            self.assertFalse((Path(temp) / 'session-upgrade.json').exists())
