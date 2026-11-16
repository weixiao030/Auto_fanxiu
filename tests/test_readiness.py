import unittest
from fanxiu_assistant.readiness import waiting_message

class BattleRecoveryReadinessTests(unittest.TestCase):
    def test_recovery_explains_wait_instead_of_claiming_login(self):
        for state in ('pending', 'replaying', 'blocked'):
            with self.subTest(state=state):
                self.assertEqual(waiting_message({'battle_recovery':{'state':state,'message':'同场结算等待'}}), '同场结算等待')
                self.assertIn('战斗结算', waiting_message({'battle_recovery':{'state':state}}))

    def test_completed_recovery_retains_native_queue_facts(self):
        self.assertIn('214', waiting_message({'battle_recovery':{'state':'done'},'login_queue':{'active':True,'ahead_count':214}}))

    def test_network_and_queue_facts_take_priority_over_pending_recovery(self):
        s={'battle_recovery':{'state':'pending','message':'核对战斗'},'network_blocked':True}
        self.assertIn('连接中断', waiting_message(s))
        s['login_queue']={'active':True,'ahead_count':214}
        self.assertIn('214', waiting_message(s))
        self.assertIn('排队', waiting_message(s))
