import datetime as dt
import unittest

from lifecycle import IPOWindow, plan_run
from nse_lifecycle import (_exclusion_reasons, _find_anchor_url,
                           _inside_target_window, build_diagnostics)


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

    def test_diagnostics_explain_zero_action_live_rows_and_missing_upcoming(self):
        today = dt.date(2026, 8, 7)
        rows = [
            IPOWindow(757, "VPRPL-BE", "Historical", today - dt.timedelta(days=5),
                      today - dt.timedelta(days=3), today - dt.timedelta(days=1), True, True, True),
            IPOWindow(347, None, "No symbol", None, None,
                      today - dt.timedelta(days=1), True, True, True),
            IPOWindow(900, None, "Missing dates", None, None, None),
            IPOWindow(901, "FUTURE", "Expected upcoming", today + dt.timedelta(days=8),
                      today + dt.timedelta(days=10), today + dt.timedelta(days=15)),
        ]
        diagnostic = build_diagnostics(rows, today)
        by_id = {row["ipo_id"]: row for row in diagnostic["candidates"]}
        self.assertEqual(by_id[757]["planned_actions"], [])
        self.assertIn("historical_listing_buffer", by_id[757]["exclusion_reason"])
        self.assertIn("already_complete", by_id[757]["exclusion_reason"])
        self.assertIn("missing_symbol", by_id[347]["exclusion_reason"])
        self.assertEqual(by_id[347]["planned_actions"], [])
        self.assertIn("missing_dates", by_id[900]["exclusion_reason"])
        self.assertIn("outside_window", by_id[901]["exclusion_reason"])
        self.assertEqual(diagnostic["aggregate_counts"]["eligible_candidates"], 2)
        self.assertEqual(diagnostic["aggregate_counts"]["missing_symbol"], 2)

    def test_target_window_predicate_matches_live_sql_boundaries(self):
        today = dt.date(2026, 8, 7)
        listing_yesterday = IPOWindow(1, "A", "A", None, None,
                                      today - dt.timedelta(days=1))
        issue_tomorrow = IPOWindow(2, "B", "B", today + dt.timedelta(days=1),
                                   today + dt.timedelta(days=4), None)
        old = IPOWindow(3, "C", "C", today - dt.timedelta(days=8),
                        today - dt.timedelta(days=4), today - dt.timedelta(days=3))
        self.assertTrue(_inside_target_window(listing_yesterday, today))
        self.assertTrue(_inside_target_window(issue_tomorrow, today))
        self.assertFalse(_inside_target_window(old, today))
        self.assertIn("outside_window", _exclusion_reasons(old, today, []))


if __name__ == "__main__": unittest.main()
