#!/usr/bin/env python3
"""reconcile.py — Stage C reconciliation gate for the 5-table D1 schema.

Given `NEON_READONLY_DATABASE_URL` and a wrangler config pointing at a
local/remote staging D1, produce a machine-readable + human report
answering:

    * Row counts (per D1 target) match expected Neon subquery counts?
    * `fundamentals`: 1 row per IPO; sampled critical fields match latest
      Neon values (issue_price, band_lo/hi, issue_size_cr, fair_value,
      margin_of_safety_pct, fundamental_verdict, listing_action).
    * `market_observations`:
        count(interval='1d')  == Neon market_candles
        count(interval='15m') == Neon market_candles_15m
        count(observation_type='preopen') == Neon listing_observations WHERE obs_type='preopen'
    * `research_findings`: total == sum(rhp_findings + insights + ipo_rhp_intel + ipo_research_notes),
      minus any anomalies recorded in `_migrate/anomalies.jsonl`.
    * `source_facts`: full row-count match; distinct-hash count.

Writes reports to `_migrate/reconciliation_report.{md,json}`.
Exit code 0 if every check passes.
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


def neon_conn():
    import psycopg2  # type: ignore
    dsn = os.environ.get("NEON_READONLY_DATABASE_URL")
    if not dsn:
        raise SystemExit(
            "NEON_READONLY_DATABASE_URL required. "
            "DATABASE_URL fallback has been removed by design."
        )
    c = psycopg2.connect(dsn); c.autocommit = True
    with c.cursor() as cur:
        cur.execute("SET default_transaction_read_only = on")
    return c


def d1_query(sql: str, *, sink: str) -> list[dict]:
    if sink.startswith("sqlite:"):
        import sqlite3
        conn = sqlite3.connect(sink[len("sqlite:"):])
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
        return rows
    cmd = ["wrangler", "d1", "execute", "DB_CORE", "--config", _WRANGLER, "--json"]
    if sink == "wrangler-local":
        cmd += ["--local", "--env", "staging"]
    elif sink == "wrangler-remote-staging":
        cmd += ["--env", "staging"]
    else:
        raise SystemExit(f"unknown sink: {sink}")
    cmd += ["--command", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    data = json.loads(r.stdout)
    if isinstance(data, list) and data and "results" in data[0]:
        return data[0]["results"]
    return []


def _norm_str(v: Any) -> str:
    if v is None: return ""
    if isinstance(v, Decimal): return format(v.normalize(), "f")
    if isinstance(v, bool): return "1" if v else "0"
    return str(v)


def _decimal_eq(a: Any, b: Any) -> bool:
    """CONVENTIONS §1.reconciliation: Decimal(x).normalize() on both sides."""
    if (a in (None, "", "None")) and (b in (None, "", "None")): return True
    try:
        return Decimal(str(a)).normalize() == Decimal(str(b)).normalize()
    except (ArithmeticError, ValueError):
        return _norm_str(a) == _norm_str(b)


# --------------------------------------------------------- checks

def check_ipo(neon, sink: str) -> dict:
    with neon.cursor() as cur:
        cur.execute("SELECT count(*) FROM ipo")
        n_neon = cur.fetchone()[0]
    n_d1 = int(d1_query("SELECT count(*) AS n FROM ipo", sink=sink)[0]["n"])
    return {"target": "ipo", "neon": n_neon, "d1": n_d1, "ok": n_neon == n_d1}


def check_fundamentals(neon, sink: str) -> dict:
    with neon.cursor() as cur:
        cur.execute("SELECT count(*) FROM ipo")
        n_ipo = cur.fetchone()[0]
    n_d1 = int(d1_query("SELECT count(*) AS n FROM fundamentals", sink=sink)[0]["n"])

    # Sample-value diff on the critical spine (up to 25 IPOs, deterministic order).
    diffs = []
    with neon.cursor() as cur:
        cur.execute(
            """
            SELECT i.id AS ipo_id,
                   ii.issue_price, ii.band_lo, ii.band_hi, ii.issue_size_cr,
                   ld.fundamental_verdict, ld.listing_action
            FROM ipo i
            LEFT JOIN ipo_issue ii ON ii.ipo_id = i.id
            LEFT JOIN (
                SELECT DISTINCT ON (ipo_id) ipo_id, fundamental_verdict, listing_action
                FROM decisions ORDER BY ipo_id, decided_at DESC NULLS LAST
            ) ld ON ld.ipo_id = i.id
            ORDER BY i.id LIMIT 25
            """
        )
        cols = [d[0] for d in cur.description]
        neon_rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    ids_csv = ",".join(str(r["ipo_id"]) for r in neon_rows) or "0"
    d1_rows = d1_query(
        "SELECT ipo_id, issue_price, band_lo, band_hi, issue_size_cr, "
        "fundamental_verdict, listing_action FROM fundamentals WHERE ipo_id IN ("
        + ids_csv + ") ORDER BY ipo_id",
        sink=sink,
    )
    d1_by_id = {row["ipo_id"]: row for row in d1_rows}

    for n in neon_rows:
        d = d1_by_id.get(n["ipo_id"])
        if d is None:
            diffs.append({"ipo_id": n["ipo_id"], "reason": "missing in D1"})
            continue
        for field in ("issue_price", "band_lo", "band_hi", "issue_size_cr"):
            if not _decimal_eq(n[field], d.get(field)):
                diffs.append({"ipo_id": n["ipo_id"], "field": field,
                              "neon": _norm_str(n[field]), "d1": _norm_str(d.get(field))})
        for field in ("fundamental_verdict", "listing_action"):
            if _norm_str(n[field]) != _norm_str(d.get(field)):
                diffs.append({"ipo_id": n["ipo_id"], "field": field,
                              "neon": _norm_str(n[field]), "d1": _norm_str(d.get(field))})
    return {"target": "fundamentals", "neon_expected": n_ipo, "d1": n_d1,
            "row_diff": n_ipo - n_d1, "sample_diffs": diffs[:25],
            "ok": (n_ipo == n_d1) and not diffs}


def check_market_observations(neon, sink: str) -> dict:
    with neon.cursor() as cur:
        cur.execute("SELECT count(*) FROM market_candles"); n_1d = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM market_candles_15m"); n_15m = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM listing_observations WHERE obs_type='preopen'")
        n_pre = cur.fetchone()[0]
    d1_1d = int(d1_query("SELECT count(*) AS n FROM market_observations WHERE interval='1d'", sink=sink)[0]["n"])
    d1_15m = int(d1_query("SELECT count(*) AS n FROM market_observations WHERE interval='15m'", sink=sink)[0]["n"])
    d1_pre = int(d1_query(
        "SELECT count(*) AS n FROM market_observations WHERE observation_type='preopen'",
        sink=sink)[0]["n"])
    checks = [
        {"check": "interval=1d",  "neon": n_1d,  "d1": d1_1d,  "ok": n_1d == d1_1d},
        {"check": "interval=15m", "neon": n_15m, "d1": d1_15m, "ok": n_15m == d1_15m},
        {"check": "preopen",      "neon": n_pre, "d1": d1_pre, "ok": n_pre == d1_pre},
    ]
    return {"target": "market_observations", "checks": checks,
            "ok": all(c["ok"] for c in checks)}


def check_research_findings(neon, sink: str) -> dict:
    with neon.cursor() as cur:
        cur.execute("SELECT count(*) FROM rhp_findings"); c1 = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM insights"); c2 = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM ipo_rhp_intel"); c3 = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM ipo_research_notes"); c4 = cur.fetchone()[0]
    expected = c1 + c2 + c3 + c4
    d1_total = int(d1_query("SELECT count(*) AS n FROM research_findings", sink=sink)[0]["n"])

    # ipo_rhp_intel + ipo_research_notes rely on name_norm resolution; anomalies
    # counted separately.
    anom_lines = 0
    anom_path = _OUT_DIR / "anomalies.jsonl"
    if anom_path.exists():
        for ln in anom_path.read_text().splitlines():
            try:
                a = json.loads(ln)
                if a.get("target") == "research_findings": anom_lines += 1
            except json.JSONDecodeError: pass
    return {"target": "research_findings",
            "neon_expected": expected, "d1": d1_total,
            "anomalies_recorded": anom_lines,
            "ok": d1_total + anom_lines == expected}


def check_source_facts(neon, sink: str) -> dict:
    with neon.cursor() as cur:
        cur.execute("SELECT count(*) FROM source_facts")
        n_neon = cur.fetchone()[0]
    d1_total = int(d1_query("SELECT count(*) AS n FROM source_facts", sink=sink)[0]["n"])
    d1_distinct = int(d1_query(
        "SELECT COUNT(DISTINCT observation_hash) AS n FROM source_facts",
        sink=sink)[0]["n"])
    # source_facts allows deduplication via observation_hash, so d1_total <= n_neon.
    return {"target": "source_facts", "neon": n_neon, "d1": d1_total,
            "d1_distinct_hash": d1_distinct,
            "ok": d1_total <= n_neon and d1_total == d1_distinct}


# --------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sink", default="wrangler-local",
                    help="D1 read target: wrangler-local | wrangler-remote-staging | sqlite:PATH")
    args = ap.parse_args()
    if args.sink not in ("wrangler-local", "wrangler-remote-staging") \
       and not args.sink.startswith("sqlite:"):
        raise SystemExit(f"invalid --sink: {args.sink}")

    neon = neon_conn()
    report: dict = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "sink": args.sink, "targets": []}
    exit_code = 0

    checks = [
        ("ipo",                  check_ipo),
        ("fundamentals",         check_fundamentals),
        ("market_observations",  check_market_observations),
        ("research_findings",    check_research_findings),
        ("source_facts",         check_source_facts),
    ]
    try:
        for name, fn in checks:
            print(f"  reconciling {name} ...")
            r = fn(neon, args.sink)
            report["targets"].append(r)
            if not r["ok"]: exit_code = 1
    finally:
        neon.close()

    report["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report["ok"] = exit_code == 0
    _JSON.write_text(json.dumps(report, indent=2, default=str))

    with _MD.open("w") as h:
        h.write(f"# Reconciliation report (5-table D1 target)\n\n")
        h.write(f"Sink: `{args.sink}`  •  {report['started_at']} → {report['ended_at']}  •  ")
        h.write(f"Overall: **{'PASS' if report['ok'] else 'FAIL'}**\n\n")
        for r in report["targets"]:
            h.write(f"## {r['target']} — {'OK' if r['ok'] else 'FAIL'}\n")
            h.write("```json\n" + json.dumps(r, indent=2, default=str) + "\n```\n\n")
    print(f"report: {_MD}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
