import unittest
from tools.monitor import BehaviorGuard, fresh_events, event_identity


class MonitorBehaviorTests(unittest.TestCase):
    def test_monitor_window_excludes_initial_history_and_replayed_operations(self):
        old = {'operation_id':'old','run_id':'r','operation_sequence':1,'time':'old','message':'old'}
        new = dict(old, operation_id='new', operation_sequence=2, time='new')
        seen = {event_identity(old)}
        self.assertEqual(list(fresh_events({'events':[new, old]}, seen)), [new])
        self.assertEqual(list(fresh_events({'events':[new, old]}, seen)), [])
    def status(self, event=None, events=()):
        return {'state': {'world': {'pending_event': event or {}}},
                'config': {'tasks': {'world_events': True}}, 'events': list(events)}

    def test_settled_event_fails(self):
        self.assertTrue(BehaviorGuard().inspect(self.status({'event_id': 1, 'type': 'aura_fluctuation'}), 0))

    def test_same_event_times_out_but_new_event_restarts_clock(self):
        guard = BehaviorGuard()
        a = self.status({'event_id': 1, 'type': 'cultivator_help'})
        b = self.status({'event_id': 2, 'type': 'senior_cultivator'})
        self.assertFalse(guard.inspect(a, 0))
        self.assertFalse(guard.inspect(a, 179))
        self.assertTrue(guard.inspect(a, 181))
        self.assertFalse(guard.inspect(b, 182))
        self.assertFalse(guard.inspect(self.status(), 999))

    def test_replayed_event_log_is_not_counted_again(self):
        guard = BehaviorGuard()
        rows = [{'time': '1', 'level': 'warning', 'kind': 'world_events', 'message': '事件不存在或已处理'}]
        for _ in range(10):
            self.assertFalse(guard.inspect(self.status(events=rows), 0))
        for i in (2, 3):
            rows.insert(0, dict(rows[0], time=str(i)))
            found = guard.inspect(self.status(events=rows), 0)
        self.assertTrue(found)

    def test_stronghold_discovery_loop_requires_real_selection(self):
        guard = BehaviorGuard()
        status = self.status()
        status['state']['world']['points'] = [{'marker_id': 26.0, 'type': 'stronghold', 'choices': [{'quality': 'rare'}]}]
        for i in range(4):
            status['events'].insert(0, {'time': str(i), 'level': 'success', 'kind': 'world_points', 'marker_id': 26.0, 'message': '游戏已确认操作'})
            problems = guard.inspect(status, i)
            self.assertEqual(bool(problems), i == 3)
        status['state']['world']['points'] = []
        self.assertFalse(guard.inspect(status, 10))
        self.assertEqual(guard.stronghold_attempts, {})

    def test_repeated_unconfirmed_dungeon_settlement_is_a_failure(self):
        guard = BehaviorGuard()
        for i in range(3):
            status = self.status(events=[{'time':str(i),'level':'warning','kind':'challenge','message':'挑战结算未确认，等待状态同步后重试'}])
            found = guard.inspect(status, i)
            self.assertEqual(bool(found), i == 2)

    def test_normal_defeat_busy_and_recovery_are_allowed(self):
        guard = BehaviorGuard()
        rows = [{'time': str(i), 'level': 'warning', 'kind': 'challenge', 'message': '挑战未通关，等待成长后重试'} for i in range(6)]
        self.assertFalse(guard.inspect(self.status(events=rows), 0))
        for i in range(6, 8):
            rows.insert(0, {'time': str(i), 'level': 'warning', 'kind': 'world_events', 'message': '事件不存在或已处理'})
            self.assertFalse(guard.inspect(self.status(events=rows), 0))
        rows.insert(0, {'time': '8', 'level': 'success', 'kind': 'world_events', 'message': '游戏已确认操作'})
        self.assertFalse(guard.inspect(self.status(events=rows), 0))
        rows.insert(0, {'time': '9', 'level': 'warning', 'kind': 'world_events', 'message': '事件不存在或已处理'})
        self.assertFalse(guard.inspect(self.status(events=rows), 0))


if __name__ == '__main__':
    unittest.main()
