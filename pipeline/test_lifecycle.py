import datetime as dt
import unittest
from unittest.mock import Mock, patch

from lifecycle import IPOWindow, plan_run
from nse_lifecycle import (_exclusion_reasons, _find_anchor_url,
                           _inside_target_window, build_diagnostics,
                           reconcile_discovery, validate_diagnostic_superset)
from nse_fetch import DISCOVERY_APIS, fetch_discovery, parse_discovery_item


class FakeCursor:
    def __init__(self, rows): self.rows, self.sql = iter(rows), []
    def execute(self, sql, params=()): self.sql.append(sql)
    def fetchone(self): return next(self.rows)


class FakeConn:
    def __init__(self, rows): self.cur, self.rollbacks = FakeCursor(rows), 0
    def cursor(self): return self.cur
    def rollback(self): self.rollbacks += 1


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
        self.assertEqual(by_id[901]["planned_actions"], ["nse_issue_metadata"])
        self.assertEqual(diagnostic["aggregate_counts"]["eligible_candidates"], 3)
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

    def test_target_ids_must_be_subset_of_diagnostic_ids(self):
        today = dt.date(2026, 8, 7)
        target = IPOWindow(757, "VPRPL-BE", "Historical", today - dt.timedelta(days=60),
                           None, None)
        with self.assertRaisesRegex(RuntimeError, "757"):
            validate_diagnostic_superset([target], [])
        validate_diagnostic_superset([target], [target])
        self.assertFalse(_inside_target_window(target, today))

    def test_unknown_official_upcoming_is_bootstrap_or_unresolved_without_write(self):
        item = {"companyName": "Official New Ltd", "symbol": "OFFNEW",
                "isin": "INE000000001", "issueStartDate": "10-Aug-2026",
                "issueEndDate": "12-Aug-2026", "priceBand": "100-110", "lotSize": "10"}
        row = parse_discovery_item(item)
        conn = FakeConn([None, None, None])
        report, overlays, _, writes = reconcile_discovery(conn, [row], write=False)
        self.assertEqual(report[0]["resolution"], "bootstrap_required")
        self.assertEqual(overlays, []); self.assertEqual(writes, 0)
        self.assertFalse(any("INSERT" in sql or "UPDATE" in sql for sql in conn.cur.sql))

    def test_official_isin_bootstrap_is_idempotent_on_second_discovery(self):
        row = parse_discovery_item({"companyName":"Official Bootstrap Ltd",
            "symbol":"BOOT", "isin":"INE0BOOT0001", "issueStartDate":"10-Aug-2026",
            "issueEndDate":"12-Aug-2026", "priceBand":"100-110", "lotSize":"10"})
        first = FakeConn([None, None, None])
        with patch("fill_ipo.upsert_ipo", return_value=(77,"inserted")) as spine, \
             patch("fill_v2.upsert_ipo_issue") as issue:
            report, _, _, writes = reconcile_discovery(first, [row], write=True)
        self.assertEqual(report[0]["ipo_id"], 77)
        self.assertEqual(report[0]["resolution"], "inserted")
        self.assertEqual(writes, 2); spine.assert_called_once(); issue.assert_called_once()

        complete = FakeConn([(77,"Official Bootstrap Ltd","official bootstrap ltd",
                              "BOOT",None,"INE0BOOT0001"),
                             (77,"Official Bootstrap Ltd","official bootstrap ltd",
                              "BOOT",None,"INE0BOOT0001"),
                             (dt.date(2026,8,10),dt.date(2026,8,12),100,110,10,None,
                              False,False)])
        with patch("fill_ipo.upsert_ipo") as spine, patch("fill_v2.upsert_ipo_issue") as issue:
            report, _, _, writes = reconcile_discovery(complete, [row], write=True)
        self.assertEqual(report[0]["resolution"], "unchanged")
        self.assertEqual(writes, 0); spine.assert_not_called(); issue.assert_not_called()

    def test_existing_missing_dates_refresh_overlay_enables_lifecycle(self):
        today = dt.date(2026, 8, 7)
        row = parse_discovery_item({"companyName": "Existing Ltd", "symbol": "EXIST",
            "issueStartDate": "07-Aug-2026", "issueEndDate": "09-Aug-2026",
            "priceBand": "100-110", "lotSize": "10"})
        conn = FakeConn([(44, "Existing Ltd", "existing ltd", "EXIST", None, None),
                         (None, None, None, None, None, None, False, False)])
        report, overlays, _, writes = reconcile_discovery(conn, [row], write=False)
        self.assertEqual(report[0]["resolution"], "matched_existing")
        self.assertEqual(writes, 0)
        self.assertIn("subscription_forward", plan_run(overlays, today)[0].actions)

    def test_five_simultaneous_stages_remain_independent(self):
        today = dt.date(2026, 8, 7)
        rows = [
            IPOWindow(1, "BAND", "A", today + dt.timedelta(days=3), today + dt.timedelta(days=5), None, False, True),
            IPOWindow(2, "DAY1", "B", today, today + dt.timedelta(days=2), None, True, True),
            IPOWindow(3, "FINAL", "C", today - dt.timedelta(days=2), today, None, True, True),
            IPOWindow(4, "ANCHOR", "D", today + dt.timedelta(days=1), today + dt.timedelta(days=3), None, True),
            IPOWindow(5, "LIST", "E", today - dt.timedelta(days=5), today - dt.timedelta(days=3), today, True, True, True)]
        actions = {p.ipo.ipo_id: set(p.actions) for p in plan_run(rows, today)}
        self.assertEqual(actions[1], {"nse_issue_metadata"})
        self.assertEqual(actions[2], {"subscription_forward"})
        self.assertEqual(actions[3], {"subscription_final"})
        self.assertEqual(actions[4], {"anchor_discovery"})
        self.assertEqual(actions[5], {"preopen_capture"})

    def test_discovery_failure_is_reported_without_db_or_vendor_fallback(self):
        session = Mock(); session.get.return_value.status_code = 503
        rows, calls, errors = fetch_discovery(session)
        self.assertEqual(rows, []); self.assertEqual(calls, 2); self.assertEqual(len(errors), 2)
        self.assertTrue(all("nseindia.com" in url for _, url in DISCOVERY_APIS))
        self.assertFalse(any(vendor in url.lower() for _, url in DISCOVERY_APIS
                             for vendor in ("chittorgarh", "ipomatrix")))

    def test_one_identity_conflict_does_not_stop_next_discovered_ipo(self):
        bad = parse_discovery_item({"companyName": "Bad", "symbol": "BAD",
                                    "isin": "INE000000001"})
        good = parse_discovery_item({"companyName": "Good", "symbol": "GOOD",
            "issueStartDate": "07-Aug-2026", "issueEndDate": "09-Aug-2026"})
        conn = FakeConn([
            (1, "Bad", "bad", "BAD", None, "INE000000002"),
            (1, "Bad", "bad", "BAD", None, "INE000000002"),
            (2, "Good", "good", "GOOD", None, None),
            (None, None, None, None, None, None, True, True)])
        report, overlays, _, writes = reconcile_discovery(conn, [bad, good], write=False)
        self.assertEqual(report[0]["resolution"], "failed")
        self.assertEqual(report[1]["resolution"], "matched_existing")
        self.assertEqual([ipo.ipo_id for ipo in overlays], [2])
        self.assertEqual(writes, 0); self.assertEqual(conn.rollbacks, 1)


if __name__ == "__main__": unittest.main()
