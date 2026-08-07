import datetime as dt
import unittest

from lifecycle import IPOWindow, plan_run
from nse_lifecycle import _find_anchor_url


class LifecycleTest(unittest.TestCase):
    def test_four_concurrent_ipos_get_independent_actions(self):
        today = dt.date(2026, 8, 7)
        ipos = [
            IPOWindow(1, "DAY1", "IPO A", today, today + dt.timedelta(days=2), None, True, True),
            IPOWindow(2, "FINAL", "IPO B", today - dt.timedelta(days=2), today, None, True, True),
            IPOWindow(3, "ANCHOR", "IPO C", today + dt.timedelta(days=1), today + dt.timedelta(days=3), None, True),
            IPOWindow(4, "LIST", "IPO D", today - dt.timedelta(days=5), today - dt.timedelta(days=3), today, True, True, True),
        ]
        plans = {p.ipo.ipo_id: set(p.actions) for p in plan_run(ipos, today)}
        self.assertEqual(plans[1], {"subscription_forward"})
        self.assertEqual(plans[2], {"subscription_final"})
        self.assertEqual(plans[3], {"anchor_discovery"})
        self.assertEqual(plans[4], {"preopen_capture"})

    def test_banked_final_and_anchor_are_not_repeated(self):
        today = dt.date(2026, 8, 7)
        ipo = IPOWindow(8, "DONE", "Done", today - dt.timedelta(days=2), today,
                        today + dt.timedelta(days=3), True, True, True)
        self.assertEqual(plan_run([ipo], today)[0].actions, ())

    def test_anchor_link_discovery_is_nesting_independent(self):
        payload = {"reports": [{"label": "Anchor Allocation Report",
                                 "download": "/content/anchor-allocation.pdf"}]}
        self.assertEqual(_find_anchor_url(payload), "/content/anchor-allocation.pdf")


if __name__ == "__main__": unittest.main()
