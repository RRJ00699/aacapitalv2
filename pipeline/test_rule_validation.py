"""D6: the V2 rule-validation producer.

The V1 producer (compatibility/scripts/rule_validation.py) stays quarantined: it reads
ipo_gold, a VIEW over two V1 tables, and gates eligibility on a company-name regex for
REIT/InvIT. This exercises the replacement against real V2 row shapes.
"""
import datetime as dt
import json

import pytest

import rule_validation as rules


LISTED = dt.date(2026, 6, 1)


def seed(conn, ipo_id, *, listing_open=100.0, best_close=None, qib_x=None,
         anchor_count=None, issue_size_cr=500.0, score_band=None, gap_pct=None):
    """One canonical, listed IPO with an outcome — the unit every rule measures."""
    cur = conn.cursor()
    cur.execute("""INSERT INTO ipo(id,isin,symbol,name_norm,name_display,is_mainboard,status,
                     listing_date) VALUES(%s,%s,%s,%s,%s,TRUE,'listed',%s)""",
                (ipo_id, f"INE0000{ipo_id:04d}", f"S{ipo_id}", f"n{ipo_id}", f"N{ipo_id}", LISTED))
    cur.execute("INSERT INTO ipo_issue(ipo_id,issue_size_cr,fresh_cr,ofs_cr) VALUES(%s,%s,300,200)",
                (ipo_id, issue_size_cr))
    cur.execute("""INSERT INTO subscription_snapshots(ipo_id,captured_at,is_final,qib_x,
                     anchor_count,mf_shares_bid,total_x)
                   VALUES(%s,now(),TRUE,%s,%s,1000,12)""", (ipo_id, qib_x, anchor_count))
    cur.execute("""INSERT INTO valuation(ipo_id,engine_version,score,score_band)
                   VALUES(%s,'v2-score-2',5,%s)""", (ipo_id, score_band))
    cur.execute("""INSERT INTO listing_outcomes(ipo_id,listing_open,best_close,gap_pct)
                   VALUES(%s,%s,%s,%s)""",
                (ipo_id, listing_open, best_close if best_close is not None else listing_open, gap_pct))
    conn.commit()


def rule_by_id(results, rule_id):
    return next(result for result in results if result["rule_id"] == rule_id)


def test_every_declared_rule_produces_exactly_one_row_even_with_an_empty_cohort():
    """A rule that writes nothing is indistinguishable from a rule nobody wrote."""
    results = rules.evaluate_all([])
    assert len(results) == len(rules.RULES)
    assert {result["rule_id"] for result in results} == {rule.rule_id for rule in rules.RULES}
    assert all(result["status"] == rules.NOT_EVALUABLE for result in results)


def test_the_canonical_layer_is_empty_and_every_mined_rule_is_labelled_discovery():
    assert rules.CANONICAL_RULES == (), "a rule the owner has not ratified is not canonical"
    assert rules.DISCOVERY_RULES
    assert all(rule.layer == rules.LAYER_DISCOVERY for rule in rules.DISCOVERY_RULES)
    summary = rules.summarize(rules.evaluate_all([]))
    assert summary["by_layer"] == {"CANONICAL": 0, "DISCOVERY": len(rules.DISCOVERY_RULES)}


def cohort(qib_wins, qib_losses, others):
    """qib_x >= 15 rows that win, qib_x >= 15 rows that lose, and sub-threshold rows."""
    built = []
    for index in range(qib_wins):
        built.append({"ipo_id": index, "listing_date": LISTED, "qib_x": 40,
                      "outcome_return": 0.30, "best_close": 130, "listing_open": 100})
    for index in range(qib_losses):
        built.append({"ipo_id": 100 + index, "listing_date": LISTED, "qib_x": 40,
                      "outcome_return": -0.10, "best_close": 90, "listing_open": 100})
    for index in range(others):
        built.append({"ipo_id": 200 + index, "listing_date": LISTED, "qib_x": 2,
                      "outcome_return": -0.20, "best_close": 80, "listing_open": 100})
    return built


def test_a_computable_rule_that_beats_the_baseline_passes():
    results = rules.evaluate_all(cohort(qib_wins=9, qib_losses=1, others=10))
    qib = rule_by_id(results, "qib_15x")
    assert qib["status"] == rules.PASS
    assert qib["n"] == 10 and qib["universe_n"] == 20
    assert qib["win_rate"] == 0.9 and qib["baseline_win_rate"] == 0.45
    assert qib["beats_baseline"] is True
    assert qib["missing_inputs"] == []
    assert qib["date_range"] == f"{LISTED.isoformat()}..{LISTED.isoformat()}"


def test_a_computable_rule_that_does_not_beat_the_baseline_fails():
    results = rules.evaluate_all(cohort(qib_wins=1, qib_losses=9, others=0)
                                 + [{"ipo_id": 900 + i, "listing_date": LISTED, "qib_x": 1,
                                     "outcome_return": 0.5} for i in range(10)])
    qib = rule_by_id(results, "qib_15x")
    assert qib["status"] == rules.FAIL
    assert qib["beats_baseline"] is False
    assert qib["win_rate"] < qib["baseline_win_rate"]


def test_a_rule_whose_input_is_absent_is_not_evaluable_and_names_the_input():
    """Never a false pass, never a silent omission."""
    results = rules.evaluate_all(cohort(qib_wins=9, qib_losses=1, others=10))
    anchors = rule_by_id(results, "anchors_30plus")
    assert anchors["status"] == rules.NOT_EVALUABLE
    assert anchors["missing_inputs"] == ["subscription_snapshots.anchor_count"]
    assert "subscription_snapshots.anchor_count" in anchors["status_detail"]
    assert anchors["n"] == 0
    assert anchors["win_rate"] is None if "win_rate" in anchors else True
    assert anchors["beats_baseline"] is None


def test_a_partly_covered_input_is_not_evaluable_and_says_how_short_it_fell():
    rows = cohort(qib_wins=9, qib_losses=1, others=10)
    rows[0]["anchor_count"] = 40           # one row only: real coverage, not enough of it
    anchors = rule_by_id(rules.evaluate_all(rows), "anchors_30plus")
    assert anchors["status"] == rules.NOT_EVALUABLE
    assert anchors["missing_inputs"] == ["subscription_snapshots.anchor_count"]
    assert "only 1 of 20" in anchors["status_detail"]


def test_a_thin_match_cannot_claim_an_edge():
    rows = cohort(qib_wins=3, qib_losses=0, others=17)
    qib = rule_by_id(rules.evaluate_all(rows), "qib_15x")
    assert qib["status"] == rules.NOT_EVALUABLE
    assert qib["n"] == 3
    assert "3 IPOs match the rule" in qib["status_detail"]
    assert qib["beats_baseline"] is None


def test_adding_a_rule_is_a_registry_addition_not_a_new_code_path():
    extra = rules.Rule("issue_size_1000cr", "v2-1", rules.LAYER_DISCOVERY,
                       "ipo_issue.issue_size_cr >= 1000", ("ipo_issue.issue_size_cr",),
                       lambda row: float(row["issue_size_cr"]) >= 1000)
    rows = [{"ipo_id": i, "listing_date": LISTED, "issue_size_cr": 2000,
             "outcome_return": 0.2 if i % 2 else -0.1} for i in range(20)]
    results = rules.evaluate_all(rows, rules=(extra,))
    assert len(results) == 1 and results[0]["rule_id"] == "issue_size_1000cr"
    assert results[0]["status"] in (rules.PASS, rules.FAIL)
    assert results[0]["rule_filter"] == "ipo_issue.issue_size_cr >= 1000"


# ------------------------------------------------------------------ against a real schema
def test_cohort_selector_runs_and_excludes_a_reit_or_invit(v2_db):
    seed(v2_db, 1, best_close=130, qib_x=40)
    seed(v2_db, 2, best_close=90, qib_x=2)
    cur = v2_db.cursor()
    cur.execute("""INSERT INTO source_facts(ipo_id,field,value,source)
                   VALUES(2,'security_kind','INVIT','nse_equity_master')""")
    v2_db.commit()
    loaded = rules.load_cohort(v2_db)
    assert [row["ipo_id"] for row in loaded] == [1], "a REIT/InvIT reached a rule cohort"
    assert loaded[0]["outcome_return"] == pytest.approx(0.30)


def test_write_is_idempotent_and_owner_gated(v2_db):
    for ipo_id in range(1, 21):
        seed(v2_db, ipo_id, best_close=130 if ipo_id % 2 else 90,
             qib_x=40 if ipo_id <= 12 else 2)
    cohort_rows = rules.load_cohort(v2_db)
    results = rules.evaluate_all(cohort_rows)

    rules.write_results(v2_db, results)
    cur = v2_db.cursor()
    cur.execute("SELECT count(*) FROM rule_validation_results")
    first = cur.fetchone()[0]
    assert first == len(rules.RULES)

    rules.write_results(v2_db, rules.evaluate_all(rules.load_cohort(v2_db)))
    cur.execute("SELECT count(*) FROM rule_validation_results")
    assert cur.fetchone()[0] == first, "a re-run appended instead of updating"

    cur.execute("""SELECT layer,status,missing_inputs,inputs_used,engine_version,backtest_version
                     FROM rule_validation_results WHERE rule_id='anchors_30plus'""")
    layer, status, missing, inputs_used, engine_version, backtest_version = cur.fetchone()
    assert layer == "DISCOVERY" and status == rules.NOT_EVALUABLE
    assert missing == ["subscription_snapshots.anchor_count"]
    assert inputs_used["declared"] == ["subscription_snapshots.anchor_count"]
    assert engine_version == rules.ENGINE_VERSION == backtest_version


def test_main_refuses_to_persist_without_owner_approval(monkeypatch):
    monkeypatch.delenv(rules.OWNER_APPROVAL_ENV, raising=False)
    with pytest.raises(SystemExit) as exc:
        rules.main(["--write"])
    assert rules.OWNER_APPROVAL_ENV in str(exc.value)
    with pytest.raises(SystemExit, match="exactly one"):
        rules.main([])


def test_no_paid_client_is_reachable_from_the_producer():
    source = open(rules.__file__, encoding="utf-8").read()
    for forbidden in ("anthropic", "Anthropic", "kiteconnect", "boto3", "requests"):
        assert forbidden not in source, f"the rules producer must stay free: {forbidden}"
