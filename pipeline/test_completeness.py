import datetime as dt

import pytest

from pipeline.completeness import (FINANCIAL_FIELDS, SUBSCRIPTION_FIELDS, check_completeness,
                                   retry_lane, summarize_requirements)


def fields(table, columns):
    return [f"{table}.{column}" for column in columns]


def test_no_financial_row_and_partial_row_have_fixed_denominator_and_exact_gaps():
    required = fields("financial_statements", FINANCIAL_FIELDS)
    absent = summarize_requirements([], required, {})
    partial_present = required[:2]
    partial_missing = required[2:]
    partial = summarize_requirements(partial_present, partial_missing, {})
    assert absent == {"required_present": 0, "required_total": 5, "required_pending": 0,
                      "completeness_pct": 0.0, "retry_lanes": ["RHP"]}
    assert partial["required_total"] == 5
    assert partial["completeness_pct"] == 40.0
    assert partial_missing == ["financial_statements.pat", "financial_statements.net_worth",
                               "financial_statements.total_debt"]


def test_partial_to_more_complete_is_monotonic_with_exact_lane_ownership():
    required = fields("financial_statements", FINANCIAL_FIELDS)
    partial = summarize_requirements(required[:1], required[1:], {})
    more = summarize_requirements(required[:4], required[4:], {})
    assert more["required_total"] == partial["required_total"] == 5
    assert more["completeness_pct"] > partial["completeness_pct"]
    assert more["retry_lanes"] == ["RHP"]


def test_subscription_no_row_to_partial_is_fixed_and_pending_is_held_out_of_the_denominator():
    required = fields("subscription_snapshots", SUBSCRIPTION_FIELDS)
    absent = summarize_requirements([], required, {})
    partial = summarize_requirements(required[:3], required[3:], {})
    pending = summarize_requirements([], [], {field: "issue not closed yet" for field in required})
    assert absent["required_total"] == partial["required_total"] == 7
    assert partial["completeness_pct"] == 42.9
    assert partial["retry_lanes"] == ["NSE lifecycle", "anchor"]
    # Nothing is DUE yet, so nothing is owed and nothing is scored against. The count
    # stays visible, and the percentage now agrees with `complete`, which already
    # ignores pending entirely.
    assert pending["required_total"] == 0 and pending["required_pending"] == 7
    assert pending["completeness_pct"] == 100.0 and pending["retry_lanes"] == []
    assert retry_lane("subscription_snapshots.anchor_count") == "anchor"


def test_a_stage_that_adds_no_facts_cannot_lower_the_percentage():
    """The invariant, isolated from the schema: not-yet-due requirements are inert."""
    present = fields("ipo", ["isin", "name_display", "status"])
    missing = fields("ipo_issue", ["lot_size", "face_value"])
    before = summarize_requirements(present, missing, {"financial_statements.revenue": "awaiting RHP"})
    # A stage advance whose whole new wave is not yet due changes nothing at all.
    after = summarize_requirements(present, missing,
                                   {"financial_statements.revenue": "awaiting RHP",
                                    "ipo.kite_token": "instrument may not be in the NSE dump on day 1",
                                    "listing_outcomes.<no row>": "listed today — no session yet",
                                    "market_candles.<rows>": "listed today — no session yet",
                                    "market_candles_15m.<rows>": "listed today — no session yet"})
    assert after["completeness_pct"] == before["completeness_pct"] == 60.0
    assert after["required_pending"] == 5 and before["required_pending"] == 1


def test_a_genuinely_obtainable_gap_still_counts_against_the_percentage():
    """Monotonicity is not manufactured: a real new gap still lowers the score."""
    present = fields("ipo", ["isin", "name_display", "status"])
    missing = fields("ipo_issue", ["lot_size", "face_value"])
    before = summarize_requirements(present, missing, {})
    after = summarize_requirements(present, missing + ["decisions.<rows>"], {})
    assert after["completeness_pct"] < before["completeness_pct"]
    assert "score/verdict" in after["retry_lanes"]


def test_empty_valuation_row_cannot_enlarge_denominator():
    base_present = fields("financial_statements", FINANCIAL_FIELDS[:2])
    base_missing = fields("financial_statements", FINANCIAL_FIELDS[2:])
    absent = summarize_requirements(base_present, base_missing + ["valuation.<rows>"], {})
    # Five nullable missing_inputs belong to the row's diagnostic detail, not requirements.
    empty_row = summarize_requirements(base_present + ["valuation.<rows>"], base_missing, {})
    assert absent["required_total"] == empty_row["required_total"] == 6
    assert empty_row["completeness_pct"] >= absent["completeness_pct"]


# ---------------------------------------------------------------- D3, on a real schema
# The owner's 08-16 run: ids 1099 and 1100 went before=60.0% -> after=54.5%, missing 9->10,
# pending 1->5, with 'score/verdict' newly in the retry lanes. Reproduced here against real
# V2 row shapes, because the whole subject is how many rows and NULLs exist.
OWNER_IDS = (1099, 1100)
RUN_DAY = dt.date(2026, 8, 16)


def seed_closed_issue(conn, ipo_id):
    """The state the pipeline saw BEFORE its NSE lifecycle step ran on 08-16."""
    cur = conn.cursor()
    cur.execute("""INSERT INTO ipo(id,isin,symbol,name_norm,name_display,is_mainboard,status,
                     listing_date,kite_token)
                   VALUES(%s,%s,%s,%s,%s,TRUE,'closed',NULL,NULL)""",
                (ipo_id, f"INE00000{ipo_id}", f"SYM{ipo_id}", f"name {ipo_id}", f"Name {ipo_id}"))
    # lot_size / face_value not fetched yet -> two real NSE-lane gaps.
    cur.execute("""INSERT INTO ipo_issue(ipo_id,open_date,close_date,band_lo,band_hi,
                     issue_size_cr,lot_size,face_value,issue_price)
                   VALUES(%s,%s,%s,100,110,500,NULL,NULL,NULL)""",
                (ipo_id, RUN_DAY - dt.timedelta(days=6), RUN_DAY - dt.timedelta(days=4)))
    # No RHP document and no extraction row yet -> two real RHP-lane gaps, and revenue
    # is therefore PENDING ("awaiting RHP") rather than missing.
    cur.execute("""INSERT INTO financial_statements(ipo_id,period,basis,revenue,total_income,pat)
                   VALUES(%s,'FY26','consolidated',NULL,110,10)""", (ipo_id,))
    cur.execute("""INSERT INTO valuation(ipo_id,engine_version,score,missing_inputs)
                   VALUES(%s,'v2-score-1',60,'{}')""", (ipo_id,))
    cur.execute("""INSERT INTO subscription_snapshots(ipo_id,captured_at,is_final,
                     qib_x,nii_x,retail_x,total_x) VALUES(%s,now(),TRUE,10,5,3,6)""", (ipo_id,))
    conn.commit()


def advance_to_listed(conn, ipo_id):
    """What the NSE lifecycle step does mid-run: the listing date lands, the stage moves.

    The instrument is not in the NSE dump on day 1, so kite_token stays NULL — which is
    exactly why four of the eight new requirements are not yet due.
    """
    cur = conn.cursor()
    cur.execute("UPDATE ipo SET status='listed', listing_date=%s WHERE id=%s", (RUN_DAY, ipo_id))
    cur.execute("UPDATE ipo_issue SET issue_price=110 WHERE ipo_id=%s", (ipo_id,))
    conn.commit()


@pytest.mark.parametrize("ipo_id", OWNER_IDS)
def test_owner_08_16_stage_advance_no_longer_regresses_completeness(v2_db, ipo_id):
    seed_closed_issue(v2_db, ipo_id)
    before = check_completeness(v2_db, ipo_id, today=RUN_DAY)
    advance_to_listed(v2_db, ipo_id)
    after = check_completeness(v2_db, ipo_id, today=RUN_DAY)

    # The stage really did advance and really did add eight requirements' worth of state.
    assert (before["stage"], after["stage"]) == ("closed", "listed")
    assert len(before["missing"]) == 9 and len(before["pending"]) == 1
    assert len(after["missing"]) == 10 and len(after["pending"]) == 5

    # Three facts arrived; nothing was lost. The percentage must not fall.
    assert after["required_present"] == before["required_present"] + 3
    assert after["completeness_pct"] >= before["completeness_pct"]
    assert (before["completeness_pct"], after["completeness_pct"]) == (62.5, 64.3)

    # Not faked: the four not-yet-due requirements are reported as pending with reasons,
    # and the one genuinely obtainable new gap is still missing and still owns its lane.
    newly_pending = sorted(set(after["pending"]) - set(before["pending"]))
    assert [p.split(" (")[0] for p in newly_pending] == [
        "ipo.kite_token", "listing_outcomes.<no row>",
        "market_candles.<rows>", "market_candles_15m.<rows>"]
    newly_missing = sorted(set(after["missing"]) - set(before["missing"]))
    assert [m.split(" [")[0] for m in newly_missing] == ["decisions.<rows>"]
    assert "score/verdict" in after["retry_lanes"]


def test_completeness_percentage_agrees_with_the_complete_flag(v2_db):
    """An IPO whose only gaps are not yet due is COMPLETE — and now reads 100%."""
    cur = v2_db.cursor()
    cur.execute("""INSERT INTO ipo(id,isin,symbol,name_norm,name_display,is_mainboard,status)
                   VALUES(7,'INE0000007','SEVEN','seven','Seven Limited',TRUE,'announced')""")
    v2_db.commit()
    report = check_completeness(v2_db, 7, today=RUN_DAY)
    assert report["complete"] is (report["completeness_pct"] == 100.0)
