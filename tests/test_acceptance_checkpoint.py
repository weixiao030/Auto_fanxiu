from fanxiu_assistant.server import MIN_BRIDGE_REVISION
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import unittest
from tools.checkpoint_acceptance import review


class CheckpointTests(unittest.TestCase):
    def rows(self):
        start = datetime(2026, 11, 7, tzinfo=timezone.utc)
        return [dict(time=(start+timedelta(seconds=i)).isoformat(), elapsed_seconds=i,
                     connected=True, enabled=True, ready=True, protection=True,
                     network_blocked=False, pid=42, revision=MIN_BRIDGE_REVISION, pending_seconds=0,
                     stats={'success':i//10}) for i in range(0, 1801, 10)]

    def test_observed_window_and_success(self):
        first, last = review(self.rows())
        self.assertEqual(last['elapsed_seconds']-first['elapsed_seconds'],1800)

    def test_short_window_and_gap_fail(self):
        with self.assertRaises(ValueError): review(self.rows()[:-1])
        rows=self.rows()
        with self.assertRaises(ValueError): review(rows[:3]+rows[10:])

    def test_each_interruption_fails(self):
        for key, value in [('connected',False),('enabled',False),('ready',False),('protection',False),
                           ('network_blocked',True),('pid',43),('revision',9),('pending_seconds',331),
                           ('read_error','TimeoutError')]:
            with self.subTest(key=key):
                rows=self.rows();rows[15][key]=value
                with self.assertRaises(ValueError):review(rows)

    def test_wall_clock_jump_and_no_success_fail(self):
        rows=self.rows();rows[15]['time']=rows[16]['time']
        with self.assertRaises(ValueError):review(rows)
        rows=self.rows()
        for row in rows:row['stats']={'success':0}
        with self.assertRaises(ValueError):review(rows)


if __name__=='__main__':unittest.main()
