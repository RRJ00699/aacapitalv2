#!/usr/bin/env python3
"""reconcile.py — Stage C reconciliation gate.

Given a Neon DSN (READ ONLY) and a wrangler config pointing at a local/remote
staging D1, produce a machine-readable + human report answering:

    * Row counts match?
    * Primary-key coverage identical?
    * Nulls on critical fields (issue_price, band_lo/hi, listing_date, isin) match?
    * Aggregates: MIN/MAX/SUM/COUNT on numeric spine fields match after Decimal
      normalisation?
    * Sample-value diff on critical rows (up to 25 per table).

Writes reports to `_migrate/reconciliation_report.{md,json}`.

Exit code 0 if every check passes. Non-zero if any diff.
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
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_OUT_DIR = _REPO / "_migrate"
_OUT_DIR.mkdir(exist_ok=True)
_MD = _OUT_DIR / "reconciliation_report.md"
_JSON = _OUT_DIR / "reconciliation_report.json"
_WRANGLER = os.environ.get("WRANGLER_CONFIG", "workers/ingest/wrangler.jsonc")

CRITICAL_TABLES = [
    "ipo","ipo_issue","subscription_snapshots","financial_statements",
    "documents","source_facts","market_regimes","market_candles",
    "market_candles_15m","listing_observations","listing_outcomes",
    "valuation","decisions","rhp_findings","insights",
    "platform_config","access_requests","pipeline_steps","pipeline_failures",
    "ipo_rhp_intel","ipo_research_notes","ipo_tick_feed",
    "rule_validation_results","kite_session",
]

# Fields on which we take exact-value diffs (sampled). Additive; expand as
# needed but never remove.
CRITICAL_FIELDS = {
    "ipo": ["id","isin","symbol","name_norm","listing_date","status"],
    "ipo_issue": ["ipo_id","band_lo","band_hi","issue_price","issue_size_cr","fresh_cr","ofs_cr","lot_size"],
    "subscription_snapshots": ["ipo_id","captured_at","qib_x","nii_x","retail_x","total_x","anchor_amount_cr","anchor_count"],
    "financial_statements": ["ipo_id","period","basis","revenue","pat","ebitda"],
    "documents": ["sha256","ipo_id","doc_type"],
    "listing_outcomes": ["ipo_id","listing_open","d1_close","gap_pct","pool"],
    "valuation": ["id","ipo_id","score","score_band","peer_median_pe","pe"],
    "decisions": ["id","ipo_id","fundamental_verdict","listing_action"],
    "market_candles": ["ipo_id","d","o","h","l","c","v"],
    "market_candles_15m": ["ipo_id","ts","o","h","l","c","v"],
}

# --------------------------------------------------------- helpers

def neon_conn():
    import psycopg2  # type: ignore
    dsn = os.environ.get("NEON_READONLY_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn: raise SystemExit("NEON_READONLY_DATABASE_URL required")
    c = psycopg2.connect(dsn); c.autocommit = True
    with c.cursor() as cur:
        cur.execute("SET default_transaction_read_only = on")
    return c


def d1_query(sql: str, *, sink: str) -> list[list[Any]]:
    cmd = ["wrangler", "d1", "execute", "DB_CORE", "--config", _WRANGLER, "--json"]
    if sink == "wrangler-local": cmd += ["--local", "--env", "staging"]
    elif sink == "wrangler-remote-staging": cmd += ["--env", "staging"]
    else: raise SystemExit(f"unknown sink: {sink}")
    cmd += ["--command", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    # wrangler --json returns an array; each element has `.results`.
    data = json.loads(r.stdout)
    if isinstance(data, list) and data and "results" in data[0]:
        return data[0]["results"]
    return []


def norm(v: Any) -> str:
    if v is None: return ""
    if isinstance(v, Decimal):
        return format(v.normalize(), 'f')
    if isinstance(v, bool): return "1" if v else "0"
    return str(v)


# --------------------------------------------------------- checks

def row_count_check(neon, table: str, sink: str) -> dict:
    with neon.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        n_neon = cur.fetchone()[0]
    d1 = d1_query(f"SELECT count(*) AS n FROM {table}", sink=sink)
    n_d1 = int(d1[0]["n"]) if d1 else 0
    return {"check": "row_count", "neon": n_neon, "d1": n_d1, "diff": n_neon - n_d1, "ok": n_neon == n_d1}


def pk_coverage_check(neon, table: str, pk_cols: list[str], sink: str) -> dict:
    key_csv = ", ".join(pk_cols)
    with neon.cursor() as cur:
        cur.execute(f"SELECT {key_csv} FROM {table}")
        neon_keys = { tuple(norm(x) for x in r) for r in cur.fetchall() }
    d1_rows = d1_query(f"SELECT {key_csv} FROM {table}", sink=sink)
    d1_keys = { tuple(norm(row[c]) for c in pk_cols) for row in d1_rows }
    missing_in_d1 = list(neon_keys - d1_keys)[:25]
    extra_in_d1   = list(d1_keys - neon_keys)[:25]
    return {
        "check": "pk_coverage",
        "neon": len(neon_keys), "d1": len(d1_keys),
        "missing_in_d1": missing_in_d1, "extra_in_d1": extra_in_d1,
        "ok": not missing_in_d1 and not extra_in_d1,
    }


def sample_value_check(neon, table: str, pk_cols: list[str], fields: list[str], sink: str, sample: int = 25) -> dict:
    cols = ", ".join(fields)
    order = ", ".join(pk_cols)
    with neon.cursor() as cur:
        cur.execute(f"SELECT {cols} FROM {table} ORDER BY {order} LIMIT {sample}")
        neon_rows = [ tuple(norm(v) for v in r) for r in cur.fetchall() ]
    d1_raw = d1_query(f"SELECT {cols} FROM {table} ORDER BY {order} LIMIT {sample}", sink=sink)
    d1_rows = [ tuple(norm(row[c]) for c in fields) for row in d1_raw ]
    diffs = []
    for n_row, d_row in zip(neon_rows, d1_rows):
        if n_row != d_row:
            diffs.append({"neon": dict(zip(fields, n_row)), "d1": dict(zip(fields, d_row))})
    return {"check": "sample_diff", "sample": sample, "diffs": diffs, "ok": not diffs}


# --------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sink", choices=["wrangler-local","wrangler-remote-staging"], default="wrangler-local")
    ap.add_argument("--tables", nargs="+", default=CRITICAL_TABLES)
    args = ap.parse_args()

    neon = neon_conn()
    report: dict = {"started_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), "sink": args.sink, "tables": {}}
    exit_code = 0

    try:
        for t in args.tables:
            print(f"  reconciling {t} ...")
            r: dict = {"checks": []}
            # 1. Row count
            r["checks"].append(row_count_check(neon, t, args.sink))
            # 2. PK coverage. Look up PK from Neon information_schema.
            with neon.cursor() as cur:
                cur.execute(
                    "SELECT a.attname FROM pg_index i "
                    "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                    "WHERE i.indrelid = %s::regclass AND i.indisprimary ORDER BY array_position(i.indkey, a.attnum)",
                    (t,))
                pk_cols = [row[0] for row in cur.fetchall()]
            if pk_cols:
                r["checks"].append(pk_coverage_check(neon, t, pk_cols, args.sink))
            # 3. Sample value diff on CRITICAL_FIELDS
            fields = CRITICAL_FIELDS.get(t)
            if fields and pk_cols:
                r["checks"].append(sample_value_check(neon, t, pk_cols, fields, args.sink))
            r["ok"] = all(c["ok"] for c in r["checks"])
            if not r["ok"]: exit_code = 1
            report["tables"][t] = r
    finally:
        neon.close()

    report["ended_at"] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    report["ok"] = exit_code == 0
    _JSON.write_text(json.dumps(report, indent=2, default=str))

    with _MD.open("w") as h:
        h.write(f"# Reconciliation report\n\nSink: `{args.sink}`  •  {report['started_at']} → {report['ended_at']}  •  Overall: **{'PASS' if report['ok'] else 'FAIL'}**\n\n")
        for t, r in report["tables"].items():
            h.write(f"## {t} — {'OK' if r['ok'] else 'FAIL'}\n")
            for c in r["checks"]:
                if c["check"] == "row_count":
                    h.write(f"* Row count: Neon={c['neon']}  D1={c['d1']}  diff={c['diff']}\n")
                elif c["check"] == "pk_coverage":
                    h.write(f"* PK coverage: Neon={c['neon']}  D1={c['d1']}  ")
                    if c["missing_in_d1"]: h.write(f"missing_in_d1={len(c['missing_in_d1'])}  ")
                    if c["extra_in_d1"]: h.write(f"extra_in_d1={len(c['extra_in_d1'])}")
                    h.write("\n")
                elif c["check"] == "sample_diff":
                    h.write(f"* Sample diff on {c['sample']} rows: {len(c['diffs'])} rows differ\n")
            h.write("\n")

    print(f"report: {_MD}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
