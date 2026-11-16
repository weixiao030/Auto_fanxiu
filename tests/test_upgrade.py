import io
from pathlib import Path
import unittest
from unittest.mock import patch
from fanxiu_assistant import desktop
import test_distribution as distribution
from fanxiu_assistant.supervisor import Supervisor

class HelperUpgradeTests(unittest.TestCase):
    def old(self,version='0.1'):
        return {'app_version':version,'csrf':'isolated-test','pending':None,'state':{}}

    def test_verified_old_helper_is_stopped_and_replaced_without_game_shutdown(self):
        old=self.old()
        with patch.object(desktop,'listener_process',return_value=(42,Path('猫头凡修助手0.1.exe'))),patch.object(desktop,'open_local',return_value=io.StringIO('{}')),patch.object(desktop,'existing_service',side_effect=[old,None]),patch.object(desktop,'end_helper_process') as end:
            self.assertTrue(desktop.replace_older_helper(old))
            end.assert_called_once_with(42,Path('猫头凡修助手0.1.exe'))

    def test_same_or_newer_version_is_reused_without_killing(self):
        with patch.object(desktop,'listener_process') as lookup,patch.object(desktop,'end_helper_process') as end:
            for version in (desktop.VERSION,'99.99','invalid'):
                self.assertFalse(desktop.replace_older_helper(self.old(version)))
            lookup.assert_not_called();end.assert_not_called()

    def test_other_app_or_steam_is_never_terminated(self):
        for name in ('steam.exe','run.exe','other.exe'):
            with self.subTest(name=name),patch.object(desktop,'listener_process',return_value=(42,Path(name))),patch.object(desktop,'end_helper_process') as end,patch.object(desktop,'open_local') as request:
                with self.assertRaises(RuntimeError):desktop.replace_older_helper(self.old())
                end.assert_not_called();request.assert_not_called()

    def test_unconfirmed_operation_prevents_takeover(self):
        old=self.old();old['pending']={'id':'submitted'}
        with patch.object(desktop,'listener_process',return_value=(42,Path('猫头凡修助手0.1.exe'))),patch.object(desktop,'open_local',return_value=io.StringIO('{}')),patch.object(desktop,'existing_service',return_value=old),patch.object(desktop.time,'monotonic',side_effect=[0,336]),patch.object(desktop,'end_helper_process') as end:
            with self.assertRaises(RuntimeError):desktop.replace_older_helper(old)
            end.assert_not_called()

    def test_missing_old_status_prevents_takeover(self):
        with patch.object(desktop,'listener_process',return_value=(42,Path('猫头凡修助手0.1.exe'))),patch.object(desktop,'open_local',return_value=io.StringIO('{}')),patch.object(desktop,'existing_service',return_value=None),patch.object(desktop,'end_helper_process') as end:
            with self.assertRaises(RuntimeError):desktop.replace_older_helper(self.old())
            end.assert_not_called()

    def test_old_bridge_upgrade_waits_for_settlement_and_only_requests_current_game_restart(self):
        c=distribution.DistributionTests().controller();c.planner.config['allow_game_restart']=True;c.state['bridge_revision']=15;c.pending={'id':'in-flight'}
        supervisor=Supervisor(c,Path('current-game'))
        with patch.object(supervisor,'restart') as restart:
            supervisor.step(101);restart.assert_not_called()
            c.pending=None;supervisor.step(102);restart.assert_called_once()
            self.assertFalse(c.enabled)
