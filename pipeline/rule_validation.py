#!/usr/bin/env python3
"""
rule_validation.py — the V2 rule-validation producer for rule_validation_results.

WHY THIS IS A REWRITE, NOT A PROMOTION
  compatibility/scripts/rule_validation.py is V1-era and stays quarantined. It reads
  ipo_gold (a VIEW over ipo_consolidated + ipo_golden, both V1) and gates eligibility on
  `company_name !~* '\\y(REIT|InvIT)\\y'` — a NAME regex, which is exactly the
  classification method the canonical spine refuses. Nothing in it survives contact with
  the V2 schema, so it is replaced rather than ported.

WHAT IT DOES
  For each declared rule: select the V2 cohort, evaluate the rule's predicate over the
  IPOs whose declared inputs are actually present, measure the outcome against a
  baseline, and write ONE row per rule to rule_validation_results.

  A rule whose inputs are absent writes NOT_EVALUABLE and NAMES the absent inputs. It
  never writes a pass it cannot support, and it is never silently omitted — a rule that
  produced no row would be indistinguishable from a rule nobody wrote.

THE TWO LAYERS
  CANONICAL  — house rules the owner has ratified. Currently EMPTY, and that is the
               honest state: no rule has been ratified against V2 evidence yet.
  DISCOVERY  — candidate rules mined from the data. Every one of them is labelled
               DISCOVERY in its own row, so nothing here can be read as a house rule.

ADDING A RULE
  Append one Rule(...) to RULES. Everything else — selection, evaluation, the
  NOT_EVALUABLE path, the write, the report — is driven off that declaration. No rule
  gets its own code path, so no rule can acquire its own private definition of "pass".

  python rule_validation.py --dry-run          # report only; writes NOTHING
  python rule_validation.py --write            # + persist (owner-gated)
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import statistics
import sys
from typing import Any, Callable, NamedTuple

if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass

ENGINE_VERSION = "v2-rules-1"
OWNER_APPROVAL_ENV = "RULE_VALIDATION_OWNER_APPROVED"

# The outcome measure, stated once. best_close is the highest close in the window
# listing_outcomes already holds, measured against the LISTING OPEN — a CEILING, not an
# executable exit, and labelled as such wherever it is reported.
OUTCOME = "best_close_vs_listing_open (ceiling; not an executable exit)"
DATASET = ("V2 canonical spine: ipo x ipo_issue x subscription_snapshots(final) "
           "x valuation(v2-score) x decisions x listing_outcomes")
# A cohort this small cannot support a claim about a rule. Reported as NOT_EVALUABLE
# with the shortfall named, never as a pass.
MIN_COHORT = 10

LAYER_CANONICAL = "CANONICAL"
LAYER_DISCOVERY = "DISCOVERY"

PASS, FAIL, NOT_EVALUABLE = "PASS", "FAIL", "NOT_EVALUABLE"


class Rule(NamedTuple):
    """One declared rule. `inputs` are V2 columns; absence of any of them is reportable."""
    rule_id: str
    version: str
    layer: str
    rule_filter: str                       # human-readable predicate, stored verbatim
    inputs: tuple[str, ...]
    predicate: Callable[[dict[str, Any]], bool]


def _ratio(row, numerator, denominator, threshold):
    top, bottom = row.get(numerator), row.get(denominator)
    return bottom not in (None, 0) and float(top) / float(bottom) >= threshold


def _at_least(column, threshold):
    return lambda row: float(row[column]) >= threshold


# ---------------------------------------------------------------------------- CANONICAL
# Deliberately empty. No house rule has been ratified against V2 evidence, and inventing
# one here would make an unratified rule look ratified. The layer exists so that a
# ratified rule has somewhere to go that is not DISCOVERY.
CANONICAL_RULES: tuple[Rule, ...] = ()

# ---------------------------------------------------------------------------- DISCOVERY
DISCOVERY_RULES: tuple[Rule, ...] = (
    Rule("qib_15x", "v2-1", LAYER_DISCOVERY, "subscription_snapshots.qib_x >= 15",
         ("subscription_snapshots.qib_x",), _at_least("qib_x", 15)),
    Rule("qib_25x", "v2-1", LAYER_DISCOVERY, "subscription_snapshots.qib_x >= 25",
         ("subscription_snapshots.qib_x",), _at_least("qib_x", 25)),
    Rule("total_10x", "v2-1", LAYER_DISCOVERY, "subscription_snapshots.total_x >= 10",
         ("subscription_snapshots.total_x",), _at_least("total_x", 10)),
    Rule("bnii_20x", "v2-1", LAYER_DISCOVERY, "subscription_snapshots.bnii_x >= 20",
         ("subscription_snapshots.bnii_x",), _at_least("bnii_x", 20)),
    Rule("retail_5x", "v2-1", LAYER_DISCOVERY, "subscription_snapshots.retail_x >= 5",
         ("subscription_snapshots.retail_x",), _at_least("retail_x", 5)),
    # The owner's locked JUNK input, stated as a rule so its edge is measured, not assumed.
    Rule("mf_participated", "v2-1", LAYER_DISCOVERY, "subscription_snapshots.mf_shares_bid > 0",
         ("subscription_snapshots.mf_shares_bid",), lambda row: float(row["mf_shares_bid"]) > 0),
    Rule("anchors_30plus", "v2-1", LAYER_DISCOVERY, "subscription_snapshots.anchor_count >= 30",
         ("subscription_snapshots.anchor_count",), _at_least("anchor_count", 30)),
    Rule("anchor_amt_20pct", "v2-1", LAYER_DISCOVERY,
         "subscription_snapshots.anchor_amount_cr / ipo_issue.issue_size_cr >= 0.20",
         ("subscription_snapshots.anchor_amount_cr", "ipo_issue.issue_size_cr"),
         lambda row: _ratio(row, "anchor_amount_cr", "issue_size_cr", 0.20)),
    Rule("issue_size_150cr", "v2-1", LAYER_DISCOVERY, "ipo_issue.issue_size_cr >= 150",
         ("ipo_issue.issue_size_cr",), _at_least("issue_size_cr", 150)),
    Rule("fresh_issue_majority", "v2-1", LAYER_DISCOVERY,
         "ipo_issue.fresh_cr / (fresh_cr + ofs_cr) >= 0.50",
         ("ipo_issue.fresh_cr", "ipo_issue.ofs_cr"),
         lambda row: (float(row["fresh_cr"]) + float(row["ofs_cr"])) > 0
                     and float(row["fresh_cr"]) / (float(row["fresh_cr"]) + float(row["ofs_cr"])) >= 0.50),
    Rule("pb_high_7", "v2-1", LAYER_DISCOVERY, "valuation.pb >= 7",
         ("valuation.pb",), _at_least("pb", 7)),
    Rule("score_band_strong", "v2-1", LAYER_DISCOVERY, "valuation.score_band = 'STRONG'",
         ("valuation.score_band",), lambda row: str(row["score_band"]).upper() == "STRONG"),
    Rule("verdict_good", "v2-1", LAYER_DISCOVERY, "decisions.fundamental_verdict = 'GOOD'",
         ("decisions.fundamental_verdict",),
         lambda row: str(row["fundamental_verdict"]).upper() == "GOOD"),
    Rule("gap_positive", "v2-1", LAYER_DISCOVERY, "listing_outcomes.gap_pct > 0",
         ("listing_outcomes.gap_pct",), lambda row: float(row["gap_pct"]) > 0),
)

RULES: tuple[Rule, ...] = CANONICAL_RULES + DISCOVERY_RULES


def cohort_sql():
    """The one cohort selector. Reuses the canonical universe predicate, so a REIT/InvIT
    cannot enter a rule cohort any more than it can enter a candle lane."""
    from nse_fetch import CANONICAL_UNIVERSE_SQL
    return f"""
        SELECT i.id AS ipo_id, i.listing_date,
               ii.issue_size_cr, ii.fresh_cr, ii.ofs_cr, ii.issue_price,
               s.qib_x, s.nii_x, s.bnii_x, s.retail_x, s.total_x,
               s.anchor_amount_cr, s.anchor_count, s.mf_shares_bid,
               v.pe, v.pb, v.score, v.score_band,
               d.fundamental_verdict,
               lo.listing_open, lo.best_close, lo.gap_pct
          FROM ipo i
          JOIN listing_outcomes lo ON lo.ipo_id = i.id
          LEFT JOIN ipo_issue ii ON ii.ipo_id = i.id
          LEFT JOIN LATERAL (
                SELECT * FROM subscription_snapshots ss WHERE ss.ipo_id = i.id
                 ORDER BY ss.is_final DESC NULLS LAST, ss.captured_at DESC LIMIT 1) s ON TRUE
          LEFT JOIN LATERAL (
                SELECT * FROM valuation vv WHERE vv.ipo_id = i.id
                   AND vv.engine_version LIKE 'v2-score-%%'
                 ORDER BY vv.computed_at DESC LIMIT 1) v ON TRUE
          LEFT JOIN LATERAL (
                SELECT * FROM decisions dd WHERE dd.ipo_id = i.id
                 ORDER BY dd.decided_at DESC LIMIT 1) d ON TRUE
         WHERE {CANONICAL_UNIVERSE_SQL}
           AND lo.listing_open IS NOT NULL AND lo.listing_open > 0
           AND lo.best_close IS NOT NULL
         ORDER BY i.id"""


SQL_FILTER = ("canonical universe AND listing_outcomes.listing_open > 0 "
              "AND listing_outcomes.best_close IS NOT NULL")


def load_cohort(conn):
    cur = conn.cursor()
    cur.execute(cohort_sql())
    columns = [description[0] for description in cur.description]
    rows = [dict(zip(columns, values)) for values in cur.fetchall()]
    for row in rows:
        row["outcome_return"] = float(row["best_close"]) / float(row["listing_open"]) - 1.0
    return rows


def _column(input_name):
    """'subscription_snapshots.qib_x' -> 'qib_x'. Inputs are declared with their table so
    a NOT_EVALUABLE row names the column a human can go and look for."""
    return input_name.split(".", 1)[1]


def _outcome_stats(returns):
    if not returns:
        return {}
    wins = [value for value in returns if value > 0]
    win_rate = len(wins) / len(returns)
    losses = [value for value in returns if value <= 0]
    return {
        "win_rate": round(win_rate, 4),
        "avg_return": round(statistics.fmean(returns), 6),
        "median_return": round(statistics.median(returns), 6),
        "max_drawdown": round(min(returns), 6),
        "expectancy": round(
            win_rate * (statistics.fmean(wins) if wins else 0.0)
            + (1 - win_rate) * (statistics.fmean(losses) if losses else 0.0), 6),
    }


def evaluate_rule(rule: Rule, cohort: list[dict[str, Any]], *, min_cohort=MIN_COHORT):
    """One rule against one cohort. Returns the row that will be written, verbatim."""
    baseline_returns = [row["outcome_return"] for row in cohort]
    baseline_win_rate = (round(sum(1 for value in baseline_returns if value > 0)
                               / len(baseline_returns), 4) if baseline_returns else None)
    result = {
        "rule_id": rule.rule_id, "rule_version": rule.version, "layer": rule.layer,
        "engine_version": ENGINE_VERSION, "dataset": DATASET,
        "sql_filter": SQL_FILTER, "rule_filter": rule.rule_filter,
        "universe_n": len(cohort), "baseline_win_rate": baseline_win_rate,
        "inputs_used": {"outcome": OUTCOME, "declared": list(rule.inputs)},
        "missing_inputs": [], "n": 0, "beats_baseline": None,
        "p_vs_baseline": None, "status": NOT_EVALUABLE, "status_detail": None,
        "date_range": None,
    }

    # An input is ABSENT when no IPO in the cohort carries it. That is the honest unit:
    # one null row is a gap in that row, but a column that is null everywhere means the
    # rule cannot be evaluated at all, and the column is named so it can be fixed.
    coverage = {name: sum(1 for row in cohort if row.get(_column(name)) is not None)
                for name in rule.inputs}
    result["inputs_used"]["coverage"] = coverage
    absent = sorted(name for name, count in coverage.items() if count == 0)
    if absent:
        result["missing_inputs"] = absent
        result["status_detail"] = "no cohort row carries: " + ", ".join(absent)
        return result

    evaluable = [row for row in cohort
                 if all(row.get(_column(name)) is not None for name in rule.inputs)]
    if len(evaluable) < min_cohort:
        result["missing_inputs"] = sorted(rule.inputs)
        result["status_detail"] = (f"only {len(evaluable)} of {len(cohort)} cohort rows carry "
                                   f"every declared input; {min_cohort} required")
        return result

    matched = [row for row in evaluable if rule.predicate(row)]
    result["n"] = len(matched)
    dates = sorted(row["listing_date"] for row in evaluable if row["listing_date"])
    if dates:
        result["date_range"] = f"{dates[0].isoformat()}..{dates[-1].isoformat()}"
    if len(matched) < min_cohort:
        result["missing_inputs"] = []
        result["status_detail"] = (f"{len(matched)} IPOs match the rule; {min_cohort} required "
                                   "before any edge is claimed")
        return result

    returns = [row["outcome_return"] for row in matched]
    result.update(_outcome_stats(returns))
    rule_win_rate = result["win_rate"]
    result["beats_baseline"] = bool(baseline_win_rate is not None
                                    and rule_win_rate > baseline_win_rate)
    result["status"] = PASS if result["beats_baseline"] else FAIL
    result["status_detail"] = (f"win_rate {rule_win_rate} vs baseline {baseline_win_rate} "
                               f"over n={len(matched)} of {len(cohort)}")
    return result


def evaluate_all(cohort, rules=RULES, *, min_cohort=MIN_COHORT):
    return [evaluate_rule(rule, cohort, min_cohort=min_cohort) for rule in rules]


ENSURE_SQL = """
CREATE TABLE IF NOT EXISTS rule_validation_results (
    id BIGSERIAL PRIMARY KEY,
    rule_id TEXT NOT NULL, rule_version TEXT NOT NULL,
    backtest_version TEXT NOT NULL, dataset TEXT NOT NULL,
    sql_filter TEXT NOT NULL, rule_filter TEXT NOT NULL,
    date_range TEXT, n INT NOT NULL,
    win_rate NUMERIC, avg_return NUMERIC, median_return NUMERIC,
    max_drawdown NUMERIC, expectancy NUMERIC, p_vs_baseline NUMERIC,
    beats_baseline BOOLEAN, baseline_win_rate NUMERIC, universe_n INT,
    run_at TIMESTAMPTZ NOT NULL);
ALTER TABLE rule_validation_results ADD COLUMN IF NOT EXISTS layer TEXT;
ALTER TABLE rule_validation_results ADD COLUMN IF NOT EXISTS status TEXT;
ALTER TABLE rule_validation_results ADD COLUMN IF NOT EXISTS status_detail TEXT;
ALTER TABLE rule_validation_results ADD COLUMN IF NOT EXISTS inputs_used JSONB;
ALTER TABLE rule_validation_results ADD COLUMN IF NOT EXISTS missing_inputs TEXT[];
ALTER TABLE rule_validation_results ADD COLUMN IF NOT EXISTS engine_version TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS rule_validation_identity
    ON rule_validation_results (rule_id, rule_version, engine_version);
"""

WRITE_SQL = """
INSERT INTO rule_validation_results
    (rule_id, rule_version, backtest_version, engine_version, layer, dataset,
     sql_filter, rule_filter, date_range, n, win_rate, avg_return, median_return,
     max_drawdown, expectancy, p_vs_baseline, beats_baseline, baseline_win_rate,
     universe_n, status, status_detail, inputs_used, missing_inputs, run_at)
VALUES (%(rule_id)s, %(rule_version)s, %(engine_version)s, %(engine_version)s, %(layer)s,
        %(dataset)s, %(sql_filter)s, %(rule_filter)s, %(date_range)s, %(n)s, %(win_rate)s,
        %(avg_return)s, %(median_return)s, %(max_drawdown)s, %(expectancy)s,
        %(p_vs_baseline)s, %(beats_baseline)s, %(baseline_win_rate)s, %(universe_n)s,
        %(status)s, %(status_detail)s, %(inputs_used)s, %(missing_inputs)s, now())
ON CONFLICT (rule_id, rule_version, engine_version) DO UPDATE SET
    backtest_version = EXCLUDED.backtest_version, layer = EXCLUDED.layer,
    dataset = EXCLUDED.dataset, sql_filter = EXCLUDED.sql_filter,
    rule_filter = EXCLUDED.rule_filter, date_range = EXCLUDED.date_range,
    n = EXCLUDED.n, win_rate = EXCLUDED.win_rate, avg_return = EXCLUDED.avg_return,
    median_return = EXCLUDED.median_return, max_drawdown = EXCLUDED.max_drawdown,
    expectancy = EXCLUDED.expectancy, p_vs_baseline = EXCLUDED.p_vs_baseline,
    beats_baseline = EXCLUDED.beats_baseline, baseline_win_rate = EXCLUDED.baseline_win_rate,
    universe_n = EXCLUDED.universe_n, status = EXCLUDED.status,
    status_detail = EXCLUDED.status_detail, inputs_used = EXCLUDED.inputs_used,
    missing_inputs = EXCLUDED.missing_inputs, run_at = now()
"""


def ensure_table(conn):
    """Idempotent; the added columns and the identity index are what make a re-run an
    UPDATE rather than an append."""
    cur = conn.cursor()
    for statement in filter(None, (part.strip() for part in ENSURE_SQL.split(";"))):
        cur.execute(statement)
    conn.commit()


def write_results(conn, results):
    ensure_table(conn)
    cur = conn.cursor()
    for result in results:
        params = dict(result)
        params["inputs_used"] = json.dumps(result["inputs_used"], sort_keys=True, default=str)
        params.setdefault("win_rate", None)
        for column in ("win_rate", "avg_return", "median_return", "max_drawdown", "expectancy"):
            params.setdefault(column, None)
        cur.execute(WRITE_SQL, params)
    conn.commit()
    return len(results)


def summarize(results):
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return {"rules": len(results), "by_status": counts,
            "by_layer": {layer: sum(1 for r in results if r["layer"] == layer)
                         for layer in (LAYER_CANONICAL, LAYER_DISCOVERY)},
            "engine_version": ENGINE_VERSION, "outcome": OUTCOME}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-cohort", type=int, default=MIN_COHORT)
    args = parser.parse_args(argv)
    if not (args.write ^ args.dry_run):
        raise SystemExit("choose exactly one of --write or --dry-run")
    if args.write and os.environ.get(OWNER_APPROVAL_ENV) != "1":
        raise SystemExit(f"owner: set {OWNER_APPROVAL_ENV}=1 to persist rule validation results")

    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=25)
    try:
        cohort = load_cohort(conn)
        results = evaluate_all(cohort, min_cohort=args.min_cohort)
        written = write_results(conn, results) if args.write else 0
    finally:
        conn.close()
    for result in results:
        print(f"  [{result['status']:14}] {result['layer']:9} {result['rule_id']:22} "
              f"n={result['n']:<5} {result['status_detail'] or ''}")
        if result["missing_inputs"]:
            print(f"       missing inputs: {', '.join(result['missing_inputs'])}")
    summary = summarize(results)
    summary.update(cohort_n=len(cohort), written=written,
                   mode="write" if args.write else "dry-run")
    print("RULE_VALIDATION_SUMMARY=" + json.dumps(summary, sort_keys=True))
    return summary


if __name__ == "__main__":
    main()
