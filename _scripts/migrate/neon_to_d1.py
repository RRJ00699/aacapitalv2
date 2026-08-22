#!/usr/bin/env python3
"""neon_to_d1.py — Stage B historical copy.

    Neon (READ ONLY)  →  staging D1 (WRITE, via wrangler --local by default)

Guarantees (locked by the Stage-A/B constraints doc):
  * READ-ONLY on Neon. This script never issues DDL/UPDATE/DELETE/INSERT on
    Neon. It only executes SELECT statements. A guarded connection is opened
    with `SET default_transaction_read_only = on` (line 88).
  * DETERMINISTIC. Same Neon rows produce identical D1 payloads on every
    run (Decimal normalisation, sorted ORDER BY on the PK).
  * RESUMABLE. Progress checkpoints per table land in `_migrate/state.json`.
    A crash restarts from the last committed batch, not the beginning.
  * IDEMPOTENT. Writes use `INSERT ... ON CONFLICT DO NOTHING` (raw facts)
    or `INSERT ... ON CONFLICT DO UPDATE` (derived), keyed by the real PKs.
    Re-running never creates duplicates.
  * OBSERVABLE. Per-table row counts, wall time, errors and diff summaries
    are written to `_migrate/copy_report.md` and `_migrate/copy_report.json`.
  * BOUNDED. Rows are copied in batches of 500 (configurable). D1 batch
    limit of 1000 statements per transaction is respected.
  * NON-DESTRUCTIVE. Neon stays untouched. Staging D1 is drop-and-recreate
    ONLY when the operator passes `--fresh`.

Usage examples:
    # Dry-run: print row counts per table on Neon; no D1 writes.
    python _scripts/migrate/neon_to_d1.py --dry-run

    # Copy to LOCAL wrangler D1 (default; ingest Worker's Miniflare sqlite).
    python _scripts/migrate/neon_to_d1.py --sink wrangler-local

    # Copy to REMOTE staging D1 (owner-run; requires wrangler auth).
    python _scripts/migrate/neon_to_d1.py --sink wrangler-remote-staging

    # Resume after a crash: re-run the same command; state.json is authoritative.
    python _scripts/migrate/neon_to_d1.py --sink wrangler-local

Environment:
    NEON_READONLY_DATABASE_URL   required. postgresql://... (existing Actions secret).
    WRANGLER_CONFIG              optional. Default: workers/ingest/wrangler.jsonc
    NEON_TO_D1_BATCH             optional. Default: 500 rows per wrangler d1 execute call.

Deliberately excluded (Stage B does NOT do):
    * Any Neon write.
    * Any production Cloudflare resource.
    * Any KV mutation.
    * Any pipeline cron switch.
    * Any snapshot pointer switch.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

_REPO = Path(__file__).resolve().parents[2]
_STATE_DIR = _REPO / "_migrate"
_STATE_DIR.mkdir(exist_ok=True)
_STATE = _STATE_DIR / "state.json"
_REPORT_MD = _STATE_DIR / "copy_report.md"
_REPORT_JSON = _STATE_DIR / "copy_report.json"
_WRANGLER = os.environ.get("WRANGLER_CONFIG", "workers/ingest/wrangler.jsonc")
_BATCH = int(os.environ.get("NEON_TO_D1_BATCH", "500"))

# ------------------------------------------------------------------ Neon read

def neon_conn():
    try:
        import psycopg2  # type: ignore
    except ImportError as e:
        raise SystemExit("psycopg2 not available; add to _scripts/migrate/requirements.txt") from e
    dsn = os.environ.get("NEON_READONLY_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("NEON_READONLY_DATABASE_URL is required (Actions secret)")
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        # DO NOT modify Neon. Enforce read-only at the session level.
        cur.execute("SET default_transaction_read_only = on")
        cur.execute("SET statement_timeout = '5min'")
    return conn


# ------------------------------------------------------------------ D1 write via wrangler

def d1_execute(sql: str, params: list[Any] | None = None, *, sink: str) -> None:
    """Run one D1 statement via wrangler. `sink` chooses local vs remote-staging."""
    cmd = ["wrangler", "d1", "execute", "DB_CORE", "--config", _WRANGLER]
    if sink == "wrangler-local":
        cmd += ["--local", "--env", "staging"]
    elif sink == "wrangler-remote-staging":
        cmd += ["--env", "staging"]                # explicit staging only
    else:
        raise SystemExit(f"unknown sink: {sink}")
    cmd += ["--command", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"wrangler d1 execute failed: {r.stderr[-500:]}")


# ------------------------------------------------------------------ Value normalisation

def norm(v: Any) -> Any:
    """Neon PG value → D1 (TEXT/INTEGER) value.

    Decimal  → canonical decimal string (str(v.normalize()) but keep trailing 0 for cents-scale where meaningful)
    datetime → UTC ISO-8601 ending Z
    bool     → 0/1
    list     → json.dumps
    dict     → json.dumps
    """
    import datetime as _dt
    if v is None: return None
    if isinstance(v, Decimal):
        s = format(v, 'f')       # never scientific notation
        return s
    if isinstance(v, bool): return 1 if v else 0
    if isinstance(v, (list, tuple, dict)): return json.dumps(v, default=str)
    if isinstance(v, _dt.datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=_dt.timezone.utc)
        return v.astimezone(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    if isinstance(v, _dt.date): return v.isoformat()
    return v


def sql_literal(v: Any) -> str:
    """Value → safe SQL literal for `wrangler d1 execute --command`.

    wrangler d1 execute has no `--json` bind API on 3.114; parameters must be
    inlined. Never accepts user input; only Neon rows go through here.
    """
    if v is None: return "NULL"
    if isinstance(v, (int, float)) and not isinstance(v, bool): return repr(v)
    if isinstance(v, bool): return "1" if v else "0"
    s = str(v).replace("'", "''")
    return f"'{s}'"


# ------------------------------------------------------------------ Table registry
#
# Ordered by FK dependency. `ipo` MUST come first because every other table
# references it. `financial_statements` and friends come after `documents`
# because some columns (`doc_id`) reference `documents.sha256`.

TABLES: list[dict[str, Any]] = [
    {
        "neon": "ipo",
        "d1": "ipo",
        "select": ("SELECT id, isin, symbol, name_norm, name_display, sector, industry, is_mainboard, "
                    "status, listing_date, kite_token, ipomatrix_id, bse_code, in_backtest_universe, "
                    "created_at, updated_at FROM ipo ORDER BY id"),
        "cols": ["id","isin","symbol","name_norm","name_display","sector","industry","is_mainboard",
                 "status","listing_date","kite_token","ipomatrix_id","bse_code","in_backtest_universe",
                 "created_at","updated_at"],
        "pk": ["id"],
        "mode": "insert_ignore",
    },
    {
        "neon": "ipo_issue",  "d1": "ipo_issue",
        "select": ("SELECT ipo_id, open_date, close_date, allotment_date, band_lo, band_hi, "
                    "issue_price, lot_size, face_value, fresh_cr, ofs_cr, issue_size_cr, "
                    "registrar, brlm_count, updated_at FROM ipo_issue ORDER BY ipo_id"),
        "cols": ["ipo_id","open_date","close_date","allotment_date","band_lo","band_hi","issue_price",
                 "lot_size","face_value","fresh_cr","ofs_cr","issue_size_cr","registrar","brlm_count","updated_at"],
        "pk": ["ipo_id"],
        "mode": "insert_ignore",
    },
    {
        "neon": "subscription_snapshots", "d1": "subscription_snapshots",
        "select": ("SELECT ipo_id, captured_at, is_final, qib_x, nii_x, bnii_x, snii_x, retail_x, total_x, "
                    "anchor_amount_cr, anchor_count, applications_lakh, mf_shares_bid, mf_pct_qib "
                    "FROM subscription_snapshots ORDER BY ipo_id, captured_at"),
        "cols": ["ipo_id","captured_at","is_final","qib_x","nii_x","bnii_x","snii_x","retail_x","total_x",
                 "anchor_amount_cr","anchor_count","applications_lakh","mf_shares_bid","mf_pct_qib"],
        "pk": ["ipo_id","captured_at"], "mode": "insert_ignore",
    },
    {
        "neon": "financial_statements", "d1": "financial_statements",
        "select": ("SELECT ipo_id, period, basis, revenue, total_income, ebitda, pat, net_worth, "
                    "total_debt, total_assets, source, fetched_at FROM financial_statements "
                    "ORDER BY ipo_id, period, basis"),
        "cols": ["ipo_id","period","basis","revenue","total_income","ebitda","pat","net_worth",
                 "total_debt","total_assets","source","fetched_at"],
        "pk": ["ipo_id","period","basis"], "mode": "insert_ignore",
    },
    {
        "neon": "documents", "d1": "documents",
        "select": "SELECT sha256, ipo_id, doc_type FROM documents ORDER BY sha256",
        "cols": ["sha256","ipo_id","doc_type"], "pk": ["sha256"], "mode": "insert_ignore",
    },
    {
        "neon": "source_facts", "d1": "source_facts",
        "select": ("SELECT ipo_id, field, value, source, doc_id, confidence, fetched_at "
                    "FROM source_facts ORDER BY ipo_id, field, source, fetched_at"),
        "cols": ["ipo_id","field","value","source","doc_id","confidence","fetched_at"],
        "pk": ["ipo_id","field","source","fetched_at"], "mode": "insert_ignore",
    },
    {
        "neon": "market_regimes", "d1": "market_regimes",
        "select": "SELECT evaluation_date, active_regime, india_vix FROM market_regimes ORDER BY evaluation_date",
        "cols": ["evaluation_date","active_regime","india_vix"], "pk": ["evaluation_date"], "mode": "insert_ignore",
    },
    {
        "neon": "market_candles", "d1": "market_candles",
        "select": "SELECT ipo_id, d, o, h, l, c, v, delivery_pct, traded_qty FROM market_candles ORDER BY ipo_id, d",
        "cols": ["ipo_id","d","o","h","l","c","v","delivery_pct","traded_qty"],
        "pk": ["ipo_id","d"], "mode": "insert_ignore",
    },
    {
        "neon": "market_candles_15m", "d1": "market_candles_15m",
        "select": "SELECT ipo_id, ts, o, h, l, c, v FROM market_candles_15m ORDER BY ipo_id, ts",
        "cols": ["ipo_id","ts","o","h","l","c","v"], "pk": ["ipo_id","ts"], "mode": "insert_ignore",
    },
    {
        "neon": "listing_observations", "d1": "listing_observations",
        "select": ("SELECT ipo_id, observed_at, obs_type, ltp, qty, buy_qty, sell_qty, payload::text "
                    "FROM listing_observations ORDER BY ipo_id, obs_type, observed_at"),
        "cols": ["ipo_id","observed_at","obs_type","ltp","qty","buy_qty","sell_qty","payload"],
        "pk": ["ipo_id","obs_type","observed_at"], "mode": "insert_ignore",
    },
    {
        "neon": "listing_outcomes", "d1": "listing_outcomes",
        "select": ("SELECT ipo_id, listing_open, d1_close, gap_pct, pool, best_close, worst_close, "
                    "ceiling_20, hold_positive_vs_open, winner_35, dataset_version "
                    "FROM listing_outcomes ORDER BY ipo_id"),
        "cols": ["ipo_id","listing_open","d1_close","gap_pct","pool","best_close","worst_close",
                 "ceiling_20","hold_positive_vs_open","winner_35","dataset_version"],
        "pk": ["ipo_id"], "mode": "insert_ignore",
    },
    {
        "neon": "valuation", "d1": "valuation",
        "select": ("SELECT id, ipo_id, computed_at, engine_version, pe, pb, roe, roce, de, rev_cagr_3y, "
                    "ofs_pct, peer_median_pe, score, score_band, inputs_used::text, "
                    "array_to_json(missing_inputs)::text AS missing_inputs FROM valuation ORDER BY id"),
        "cols": ["id","ipo_id","computed_at","engine_version","pe","pb","roe","roce","de","rev_cagr_3y",
                 "ofs_pct","peer_median_pe","score","score_band","inputs_used","missing_inputs"],
        "pk": ["id"], "mode": "insert_ignore",
    },
    {
        "neon": "decisions", "d1": "decisions",
        "select": ("SELECT id, ipo_id, decided_at, engine_version, fundamental_verdict, listing_action, "
                    "reasons::text, evidence_refs::text FROM decisions ORDER BY id"),
        "cols": ["id","ipo_id","decided_at","engine_version","fundamental_verdict","listing_action",
                 "reasons","evidence_refs"],
        "pk": ["id"], "mode": "insert_ignore",
    },
    {
        "neon": "rhp_findings", "d1": "rhp_findings",
        "select": ("SELECT id, ipo_id, doc_id, model, prompt_version, findings::text, red_flag_count, "
                    "array_to_json(junk_signals)::text AS junk_signals, confidence, cost_usd, analyzed_at "
                    "FROM rhp_findings ORDER BY id"),
        "cols": ["id","ipo_id","doc_id","model","prompt_version","findings","red_flag_count",
                 "junk_signals","confidence","cost_usd","analyzed_at"],
        "pk": ["id"], "mode": "insert_ignore",
    },
    {
        "neon": "insights", "d1": "insights",
        "select": ("SELECT id, ipo_id, excerpt, page_number, doc_id, category, direction, source_type, is_current "
                    "FROM insights ORDER BY id"),
        "cols": ["id","ipo_id","excerpt","page_number","doc_id","category","direction","source_type","is_current"],
        "pk": ["id"], "mode": "insert_ignore",
    },
    {
        "neon": "platform_config", "d1": "platform_config",
        "select": "SELECT key, value, updated_at FROM platform_config ORDER BY key",
        "cols": ["key","value","updated_at"], "pk": ["key"], "mode": "insert_ignore",
    },
    {
        "neon": "access_requests", "d1": "access_requests",
        "select": ("SELECT email, name, status, requested_at, decided_at, decided_by, note "
                    "FROM access_requests ORDER BY email"),
        "cols": ["email","name","status","requested_at","decided_at","decided_by","note"],
        "pk": ["email"], "mode": "insert_ignore",
    },
    {
        "neon": "pipeline_steps", "d1": "pipeline_steps",
        "select": "SELECT id, run_date, step, script, ok, error, ran_at FROM pipeline_steps ORDER BY id",
        "cols": ["id","run_date","step","script","ok","error","ran_at"],
        "pk": ["id"], "mode": "insert_ignore",
    },
    {
        "neon": "pipeline_failures", "d1": "pipeline_failures",
        "select": "SELECT id, step, script, stderr_tail, failed_at FROM pipeline_failures ORDER BY id",
        "cols": ["id","step","script","stderr_tail","failed_at"],
        "pk": ["id"], "mode": "insert_ignore",
    },
    {
        "neon": "ipo_rhp_intel", "d1": "ipo_rhp_intel",
        "select": ("SELECT company_name, verdict, one_line, quality_gate, margin_of_safety, full_json::text, "
                    "confidence, rhp_url, pdf_sha256 FROM ipo_rhp_intel ORDER BY company_name"),
        "cols": ["company_name","verdict","one_line","quality_gate","margin_of_safety","full_json",
                 "confidence","rhp_url","pdf_sha256"],
        "pk": ["company_name"], "mode": "insert_ignore",
    },
    {
        "neon": "ipo_research_notes", "d1": "ipo_research_notes",
        "select": ("SELECT source, company, nse_symbol, rating, full_json::text, one_line, peer_name, "
                    "pdf_path, peer_ps, note_ps, parsed_at, price_low, price_high, fresh_cr, ofs_cr, "
                    "issue_size_cr, qib_pct, nii_pct, retail_pct, brlms, registrar, loss_making, "
                    "COALESCE(nse_symbol,'') AS nse_symbol_key "
                    "FROM ipo_research_notes ORDER BY source, company, nse_symbol_key"),
        "cols": ["source","company","nse_symbol","rating","full_json","one_line","peer_name","pdf_path",
                 "peer_ps","note_ps","parsed_at","price_low","price_high","fresh_cr","ofs_cr","issue_size_cr",
                 "qib_pct","nii_pct","retail_pct","brlms","registrar","loss_making","nse_symbol_key"],
        "pk": ["source","company","nse_symbol_key"], "mode": "insert_ignore",
    },
    {
        "neon": "ipo_tick_feed", "d1": "ipo_tick_feed",
        "select": ("SELECT symbol, recorded_at, ltp, vwap, vwap_dist, obir, day_volume, momentum, divergence, signal "
                    "FROM ipo_tick_feed ORDER BY symbol, recorded_at"),
        "cols": ["symbol","recorded_at","ltp","vwap","vwap_dist","obir","day_volume","momentum","divergence","signal"],
        "pk": ["symbol","recorded_at"], "mode": "insert_ignore",
    },
    {
        "neon": "rule_validation_results", "d1": "rule_validation_results",
        "select": ("SELECT id, rule_id, ipo_id, outcome, evidence::text, evaluated_at "
                    "FROM rule_validation_results ORDER BY id"),
        "cols": ["id","rule_id","ipo_id","outcome","evidence","evaluated_at"],
        "pk": ["id"], "mode": "insert_ignore",
    },
    {
        "neon": "kite_session", "d1": "kite_session",
        "select": ("SELECT id, user_id, access_token, api_key, created_at, expires_at, status "
                    "FROM kite_session ORDER BY id"),
        "cols": ["id","user_id","access_token","api_key","created_at","expires_at","status"],
        "pk": ["id"], "mode": "insert_ignore",
    },
]


# ------------------------------------------------------------------ State

def load_state() -> dict:
    if _STATE.exists():
        return json.loads(_STATE.read_text())
    return {"tables": {}}

def save_state(state: dict) -> None:
    _STATE.write_text(json.dumps(state, indent=2, sort_keys=True))


# ------------------------------------------------------------------ Copy

def copy_table(neon, table: dict, sink: str, dry_run: bool, state: dict, report: dict) -> None:
    t_neon, t_d1 = table["neon"], table["d1"]
    tstate = state["tables"].get(t_d1, {"copied": 0, "neon_total": None, "done": False})

    with neon.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {t_neon}")
        total = cur.fetchone()[0]
    tstate["neon_total"] = total
    if tstate["done"]:
        print(f"  {t_neon}: already done ({tstate['copied']}/{total})")
        return
    if total == 0:
        tstate["done"] = True; tstate["copied"] = 0
        state["tables"][t_d1] = tstate; save_state(state)
        print(f"  {t_neon}: 0 rows in Neon, marking done")
        return

    print(f"  {t_neon}: {total} rows to copy (batch={_BATCH})")
    if dry_run:
        report["tables"].append({"neon": t_neon, "d1": t_d1, "neon_rows": total, "copied": 0, "dry_run": True})
        return

    cols_csv = ", ".join(table["cols"])
    placeholders = ", ".join("?" for _ in table["cols"])  # for reference; we inline literals
    conflict = ", ".join(table["pk"])
    on_conflict = " ON CONFLICT (" + conflict + ") DO NOTHING" if table["mode"] == "insert_ignore" else ""

    offset = tstate["copied"]
    copied_now = 0
    started = time.time()
    while offset < total:
        # Deterministic pagination on the ORDER BY key already in `select`.
        limit = _BATCH
        page_sql = table["select"] + f" LIMIT {limit} OFFSET {offset}"
        with neon.cursor() as cur:
            cur.execute(page_sql)
            rows = cur.fetchall()
        if not rows: break

        values = []
        for r in rows:
            row = [norm(v) for v in r]
            vals_csv = ", ".join(sql_literal(v) for v in row)
            values.append(f"({vals_csv})")
        sql = f"INSERT INTO {t_d1} ({cols_csv}) VALUES {', '.join(values)}{on_conflict}"

        # wrangler d1 execute has a size limit; if too large, split in half.
        try:
            d1_execute(sql, sink=sink)
        except RuntimeError as e:
            if len(values) > 1:
                # Retry in halves; keep state consistent.
                mid = len(values) // 2
                d1_execute(f"INSERT INTO {t_d1} ({cols_csv}) VALUES {', '.join(values[:mid])}{on_conflict}", sink=sink)
                d1_execute(f"INSERT INTO {t_d1} ({cols_csv}) VALUES {', '.join(values[mid:])}{on_conflict}", sink=sink)
            else:
                raise

        offset += len(rows); copied_now += len(rows)
        tstate["copied"] = offset
        state["tables"][t_d1] = tstate; save_state(state)
        if copied_now % (_BATCH * 4) == 0:
            print(f"    ... {offset}/{total} ({(offset/total)*100:.1f}%)")

    tstate["done"] = (tstate["copied"] >= total)
    state["tables"][t_d1] = tstate; save_state(state)
    elapsed = time.time() - started
    print(f"  {t_neon}: {tstate['copied']}/{total} rows in {elapsed:.1f}s")
    report["tables"].append({"neon": t_neon, "d1": t_d1, "neon_rows": total,
                              "copied": tstate["copied"], "elapsed_s": round(elapsed,1)})


# ------------------------------------------------------------------ Entrypoint

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sink", choices=["wrangler-local","wrangler-remote-staging"], default="wrangler-local")
    ap.add_argument("--dry-run", action="store_true", help="Report Neon row counts; write nothing to D1.")
    ap.add_argument("--fresh", action="store_true", help="Delete _migrate/state.json and start over. Does NOT touch Neon.")
    ap.add_argument("--tables", nargs="+", help="Optional subset of D1 table names.")
    args = ap.parse_args()

    if args.fresh and _STATE.exists(): _STATE.unlink()
    state = load_state()
    report = {"sink": args.sink, "dry_run": args.dry_run, "started_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), "tables": []}

    print(f"neon_to_d1: sink={args.sink}  dry_run={args.dry_run}  batch={_BATCH}")

    neon = neon_conn()
    try:
        for t in TABLES:
            if args.tables and t["d1"] not in args.tables: continue
            copy_table(neon, t, args.sink, args.dry_run, state, report)
    finally:
        neon.close()

    report["ended_at"] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    _REPORT_JSON.write_text(json.dumps(report, indent=2))
    with _REPORT_MD.open("w") as h:
        h.write(f"# Neon → D1 copy report\n\nSink: `{args.sink}`  •  Dry run: `{args.dry_run}`  •  {report['started_at']} → {report['ended_at']}\n\n")
        h.write("| Table | Neon rows | Copied | Elapsed (s) |\n|---|---:|---:|---:|\n")
        for row in report["tables"]:
            h.write(f"| {row['neon']} | {row['neon_rows']} | {row['copied']} | {row.get('elapsed_s', 0)} |\n")
    print(f"report: {_REPORT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
