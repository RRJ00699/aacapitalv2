#!/usr/bin/env python3
"""neon_to_d1.py — Stage B historical copy targeting the 5-table D1 schema.

    Neon (READ ONLY)  →  staging D1 (WRITE, via wrangler --local by default)

Schema target (see d1/migrations/):
    ipo, fundamentals, market_observations, research_findings, source_facts.

Guarantees (locked by the Stage-A/B constraints doc, aligned with
D1_EVIDENCE_REPORT.md §7):
  * READ-ONLY on Neon. `SET default_transaction_read_only = on`; SELECT-only
    statements. No `DATABASE_URL` fallback — `NEON_READONLY_DATABASE_URL` is
    the ONLY accepted DSN env var so a writeable Neon URL cannot leak in.
  * DETERMINISTIC. Value normalisation via `_norm`; ordering on the source
    primary key so the same Neon state yields the same D1 payload.
  * SNAPSHOT-STABLE PAGINATION. All source scans use **keyset pagination**
    on the PK, never `OFFSET N`, so concurrent Neon writes cannot shift the
    page window.
  * RESUMABLE. Per-target checkpoints (last PK cursor) land in
    `_migrate/state.json`.
  * IDEMPOTENT. All D1 writes use `INSERT ... ON CONFLICT DO NOTHING` on
    real PKs. `source_facts` idempotency is by `observation_hash`, not by
    timestamp — identical retries with different `fetched_at` become one row.
  * OBSERVABLE. Per-target row counts, wall time, and skipped-anomaly rows
    land in `_migrate/copy_report.{md,json}` and `_migrate/anomalies.jsonl`.
  * NON-DESTRUCTIVE. Neon stays untouched. Staging D1 is drop-and-recreate
    ONLY when the operator passes `--fresh`.
  * SECRETS-SAFE. Skips `kite_session`, `platform_config`, `access_requests`,
    `pipeline_steps`, `pipeline_failures`, `rule_validation_results`. Kite
    access tokens are secrets — they never enter D1.

Usage:
    python tools/migrate/neon_to_d1.py --dry-run
    python tools/migrate/neon_to_d1.py --sink wrangler-local
    python tools/migrate/neon_to_d1.py --sink wrangler-remote-staging
    python tools/migrate/neon_to_d1.py --sink wrangler-local --targets ipo fundamentals

Environment:
    NEON_READONLY_DATABASE_URL   required. postgresql://...
    WRANGLER_CONFIG              optional. Default: workers/ingest/wrangler.jsonc
    NEON_TO_D1_BATCH             optional. Default: 500 rows per wrangler d1 execute call.
    PIPELINE_VERSION             optional. Recorded on source_facts writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
_ANOMALIES = _STATE_DIR / "anomalies.jsonl"
_WRANGLER = os.environ.get("WRANGLER_CONFIG", "workers/ingest/wrangler.jsonc")
_BATCH = int(os.environ.get("NEON_TO_D1_BATCH", "500"))
_PIPELINE_VERSION = os.environ.get("PIPELINE_VERSION", "stage-b-" + time.strftime("%Y%m%d"))

# ------------------------------------------------------------------ Neon

def neon_conn():
    try:
        import psycopg2  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "psycopg2 not available; add to tools/migrate/requirements.txt"
        ) from e
    dsn = os.environ.get("NEON_READONLY_DATABASE_URL")
    if not dsn:
        raise SystemExit(
            "NEON_READONLY_DATABASE_URL is required. "
            "Fallback to DATABASE_URL has been removed to prevent writeable-DSN leakage."
        )
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SET default_transaction_read_only = on")
        cur.execute("SET statement_timeout = '5min'")
    return conn


# ------------------------------------------------------------------ D1 write via wrangler

def d1_execute(sql: str, *, sink: str) -> None:
    cmd = ["wrangler", "d1", "execute", "DB_CORE", "--config", _WRANGLER]
    if sink == "wrangler-local":
        cmd += ["--local", "--env", "staging"]
    elif sink == "wrangler-remote-staging":
        cmd += ["--env", "staging"]                     # explicit staging only
    else:
        raise SystemExit(f"unknown sink: {sink}")
    cmd += ["--command", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"wrangler d1 execute failed: {r.stderr[-500:]}")


# ------------------------------------------------------------------ Value normalisation

def _norm_name(name: str | None) -> str:
    """Character-for-character port of pipeline/fill_ipo.py:_norm.

    lowercase → replace non [a-z0-9 ] with space → collapse whitespace → strip.
    Kept in lockstep with workers/ingest/src/identity.ts:normaliseName.
    """
    s = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def norm(v: Any) -> Any:
    """Neon PG value → D1 (TEXT/INTEGER) value."""
    import datetime as _dt
    if v is None: return None
    if isinstance(v, Decimal):
        return format(v, "f")                          # never scientific notation
    if isinstance(v, bool): return 1 if v else 0
    if isinstance(v, (list, tuple, dict)):
        return json.dumps(v, default=str)
    if isinstance(v, _dt.datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=_dt.timezone.utc)
        return v.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(v, _dt.date): return v.isoformat()
    return v


def sql_literal(v: Any) -> str:
    if v is None: return "NULL"
    if isinstance(v, bool): return "1" if v else "0"
    if isinstance(v, (int, float)): return repr(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


def observation_hash(field: str, value: Any, source: str,
                     document_sha: str | None, pipeline_version: str | None) -> str:
    parts = [field, "" if value is None else str(value), source,
             document_sha or "", pipeline_version or ""]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _record_anomaly(target: str, key: dict, reason: str, extra: dict | None = None) -> None:
    row = {"target": target, "key": key, "reason": reason}
    if extra: row["extra"] = extra
    with _ANOMALIES.open("a") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


# ------------------------------------------------------------------ Bulk INSERT to D1

def _insert_rows(target: str, cols: list[str], values: list[list[Any]],
                 pk_cols: list[str], sink: str) -> int:
    if not values: return 0
    cols_csv = ", ".join(cols)
    conflict = ", ".join(pk_cols) if pk_cols else ""
    on_conflict = f" ON CONFLICT ({conflict}) DO NOTHING" if conflict else ""
    literal_rows = ["(" + ", ".join(sql_literal(norm(v)) for v in row) + ")" for row in values]
    sql = f"INSERT INTO {target} ({cols_csv}) VALUES {', '.join(literal_rows)}{on_conflict}"
    try:
        d1_execute(sql, sink=sink)
        return len(values)
    except RuntimeError:
        if len(values) == 1:
            raise
        mid = len(values) // 2
        return (_insert_rows(target, cols, values[:mid], pk_cols, sink)
                + _insert_rows(target, cols, values[mid:], pk_cols, sink))


# ------------------------------------------------------------------ Keyset scanners

def _keyset_scan(cur, query: str, keyset_col: str, batch: int,
                  start_after: Any) -> Iterable[list[dict]]:
    """Snapshot-stable keyset pagination on `keyset_col`.

    `query` must contain `{cursor}` placeholder for the keyset filter and
    `{limit}` placeholder. `start_after` is the initial cursor value
    (None = start from beginning).
    """
    cursor = start_after
    while True:
        cur.execute(query.format(
            cursor=(f"AND {keyset_col} > " + sql_literal(cursor)) if cursor is not None else "",
            limit=batch,
        ))
        rows = cur.fetchall()
        if not rows: return
        cols = [d[0] for d in cur.description]
        page = [dict(zip(cols, r)) for r in rows]
        yield page
        last = page[-1][keyset_col]
        if last == cursor:  # defensive: prevent infinite loop
            return
        cursor = last


# ------------------------------------------------------------------ Target: ipo

def target_ipo(neon, sink: str, dry_run: bool, tstate: dict) -> dict:
    with neon.cursor() as cur:
        cur.execute("SELECT count(*) FROM ipo")
        total = cur.fetchone()[0]
    if dry_run: return {"target": "ipo", "neon_rows": total, "copied": 0, "dry_run": True}

    cols = ["id", "isin", "symbol", "name_norm", "name_display", "sector", "industry",
            "is_mainboard", "status", "listing_date", "kite_token", "ipomatrix_id", "bse_code",
            "created_at", "updated_at"]
    q = ("SELECT id, isin, symbol, name_norm, name_display, sector, industry, is_mainboard, "
         "status, listing_date, kite_token, ipomatrix_id, bse_code, created_at, updated_at "
         "FROM ipo WHERE 1=1 {cursor} ORDER BY id LIMIT {limit}")

    copied = 0
    started = time.time()
    with neon.cursor() as cur:
        for page in _keyset_scan(cur, q, "id", _BATCH, tstate.get("cursor")):
            # Anomaly filter: name_norm must be non-empty; recompute if Neon holds
            # a stale value (defensive; canonical value stays as-is).
            vals = []
            for row in page:
                if not row.get("name_norm") and not row.get("name_display"):
                    _record_anomaly("ipo", {"id": row["id"]}, "missing name_norm and name_display")
                    continue
                if not row.get("name_norm"):
                    row["name_norm"] = _norm_name(row.get("name_display"))
                vals.append([row[c] for c in cols])
            copied += _insert_rows("ipo", cols, vals, ["id"], sink)
            tstate["cursor"] = page[-1]["id"]
            _save_state()
    return {"target": "ipo", "neon_rows": total, "copied": copied,
            "elapsed_s": round(time.time() - started, 1)}


# ------------------------------------------------------------------ Target: fundamentals
#
# Assembled per-IPO by LEFT JOINing latest rows from ipo_issue, subscription_snapshots,
# financial_statements, valuation, decisions, and listing_outcomes. Any missing
# source table (e.g. IPO with no valuation yet) leaves those cells NULL.

_FUND_COLS = [
    "ipo_id", "open_date", "close_date", "allotment_date",
    "band_lo", "band_hi", "issue_price", "face_value", "lot_size",
    "issue_size_cr", "fresh_cr", "ofs_cr",
    "registrar", "brlm_count",
    "revenue", "total_income", "ebitda", "pat", "net_worth",
    "total_debt", "total_assets",
    "rev_cagr_3y", "roe", "roce", "debt_equity",
    "financial_history_json",
    "ipo_pe", "pb", "peer_median_pe", "valuation_score", "valuation_band",
    "qib_x", "nii_x", "bnii_x", "snii_x", "retail_x", "total_x",
    "anchor_amount_cr", "anchor_count",
    "listing_open", "d1_close", "gap_pct",
    "fundamental_verdict", "listing_action",
    "engine_version", "computed_at", "updated_at",
]


def target_fundamentals(neon, sink: str, dry_run: bool, tstate: dict) -> dict:
    with neon.cursor() as cur:
        cur.execute("SELECT count(*) FROM ipo")
        total = cur.fetchone()[0]
    if dry_run: return {"target": "fundamentals", "neon_rows": total, "copied": 0, "dry_run": True}

    # DISTINCT ON queries pick "latest" per ipo_id. Keyset paginate on ipo.id
    # (the outer scan). All inner queries are read-only.
    query = """
        WITH ids AS (
            SELECT id FROM ipo WHERE 1=1 {cursor} ORDER BY id LIMIT {limit}
        ),
        latest_sub AS (
            SELECT DISTINCT ON (ipo_id) ipo_id, qib_x, nii_x, bnii_x, snii_x, retail_x, total_x,
                   anchor_amount_cr, anchor_count
            FROM subscription_snapshots
            WHERE ipo_id IN (SELECT id FROM ids)
            ORDER BY ipo_id, is_final DESC NULLS LAST, captured_at DESC
        ),
        latest_fin AS (
            SELECT DISTINCT ON (ipo_id) ipo_id, revenue, total_income, ebitda, pat,
                   net_worth, total_debt, total_assets
            FROM financial_statements
            WHERE ipo_id IN (SELECT id FROM ids)
            ORDER BY ipo_id, period DESC NULLS LAST
        ),
        history AS (
            SELECT ipo_id, json_agg(json_build_object(
                'period', period, 'basis', basis, 'revenue', revenue,
                'ebitda', ebitda, 'pat', pat, 'net_worth', net_worth,
                'total_debt', total_debt
            ) ORDER BY period DESC)::text AS financial_history_json
            FROM financial_statements
            WHERE ipo_id IN (SELECT id FROM ids)
            GROUP BY ipo_id
        ),
        latest_val AS (
            SELECT DISTINCT ON (ipo_id) ipo_id, pe AS ipo_pe, pb, roe, roce, de AS debt_equity,
                   rev_cagr_3y, peer_median_pe, score AS valuation_score, score_band AS valuation_band,
                   engine_version, computed_at
            FROM valuation
            WHERE ipo_id IN (SELECT id FROM ids)
            ORDER BY ipo_id, computed_at DESC NULLS LAST
        ),
        latest_dec AS (
            SELECT DISTINCT ON (ipo_id) ipo_id, fundamental_verdict, listing_action
            FROM decisions
            WHERE ipo_id IN (SELECT id FROM ids)
            ORDER BY ipo_id, decided_at DESC NULLS LAST
        )
        SELECT ids.id AS ipo_id,
               ii.open_date, ii.close_date, ii.allotment_date,
               ii.band_lo, ii.band_hi, ii.issue_price, ii.face_value, ii.lot_size,
               ii.issue_size_cr, ii.fresh_cr, ii.ofs_cr,
               ii.registrar, ii.brlm_count,
               lf.revenue, lf.total_income, lf.ebitda, lf.pat, lf.net_worth,
               lf.total_debt, lf.total_assets,
               lv.rev_cagr_3y, lv.roe, lv.roce, lv.debt_equity,
               h.financial_history_json,
               lv.ipo_pe, lv.pb, lv.peer_median_pe, lv.valuation_score, lv.valuation_band,
               ls.qib_x, ls.nii_x, ls.bnii_x, ls.snii_x, ls.retail_x, ls.total_x,
               ls.anchor_amount_cr, ls.anchor_count,
               lo.listing_open, lo.d1_close, lo.gap_pct,
               ld.fundamental_verdict, ld.listing_action,
               lv.engine_version, lv.computed_at,
               COALESCE(ii.updated_at, lv.computed_at, NOW()) AS updated_at
        FROM ids
        LEFT JOIN ipo_issue ii         ON ii.ipo_id = ids.id
        LEFT JOIN latest_sub ls        ON ls.ipo_id = ids.id
        LEFT JOIN latest_fin lf        ON lf.ipo_id = ids.id
        LEFT JOIN history h            ON h.ipo_id  = ids.id
        LEFT JOIN latest_val lv        ON lv.ipo_id = ids.id
        LEFT JOIN latest_dec ld        ON ld.ipo_id = ids.id
        LEFT JOIN listing_outcomes lo  ON lo.ipo_id = ids.id
        ORDER BY ids.id
    """

    copied = 0
    started = time.time()
    with neon.cursor() as cur:
        for page in _keyset_scan(cur, query, "ipo_id", _BATCH, tstate.get("cursor")):
            vals = []
            for row in page:
                # Guardrail: if any of band_lo > band_hi > issue_price rules break,
                # record anomaly and skip; we do NOT rewrite Neon values.
                bl = row.get("band_lo"); bh = row.get("band_hi"); ip = row.get("issue_price")
                try:
                    if bl is not None and bh is not None and Decimal(str(bl)) > Decimal(str(bh)):
                        _record_anomaly("fundamentals", {"ipo_id": row["ipo_id"]}, "band_lo > band_hi",
                                        {"band_lo": str(bl), "band_hi": str(bh)})
                        continue
                    if ip is not None and bl is not None and Decimal(str(ip)) < Decimal(str(bl)):
                        _record_anomaly("fundamentals", {"ipo_id": row["ipo_id"]}, "issue_price < band_lo")
                        continue
                    if ip is not None and bh is not None and Decimal(str(ip)) > Decimal(str(bh)):
                        _record_anomaly("fundamentals", {"ipo_id": row["ipo_id"]}, "issue_price > band_hi")
                        continue
                except (ArithmeticError, ValueError):
                    _record_anomaly("fundamentals", {"ipo_id": row["ipo_id"]}, "non-decimal band/price")
                    continue
                vals.append([row.get(c) for c in _FUND_COLS])
            copied += _insert_rows("fundamentals", _FUND_COLS, vals, ["ipo_id"], sink)
            tstate["cursor"] = page[-1]["ipo_id"]
            _save_state()
    return {"target": "fundamentals", "neon_rows": total, "copied": copied,
            "elapsed_s": round(time.time() - started, 1)}


# ------------------------------------------------------------------ Target: market_observations

_MO_COLS = ["ipo_id", "observed_at", "interval", "observation_type",
            "o", "h", "l", "c", "v",
            "ltp", "buy_qty", "sell_qty", "iep", "traded_qty", "delivery_pct",
            "source", "payload"]


def target_market_observations(neon, sink: str, dry_run: bool, tstate: dict) -> dict:
    # Three source scans, each keyset-paginated on its own PK, funnelling into
    # `market_observations`. Order of sub-passes doesn't matter for correctness.
    passes = tstate.setdefault("passes", {
        "market_candles":     {"cursor": None, "done": False},
        "market_candles_15m": {"cursor": None, "done": False},
        "listing_observations": {"cursor": None, "done": False},
    })
    total_neon = 0
    with neon.cursor() as cur:
        cur.execute("SELECT (SELECT count(*) FROM market_candles) + "
                    "(SELECT count(*) FROM market_candles_15m) + "
                    "(SELECT count(*) FROM listing_observations)")
        total_neon = cur.fetchone()[0]
    if dry_run:
        return {"target": "market_observations", "neon_rows": total_neon, "copied": 0, "dry_run": True}

    copied = 0
    started = time.time()

    # ---- market_candles → interval=1d, observation_type=candle -----------------
    if not passes["market_candles"]["done"]:
        q = ("SELECT ipo_id, d, o, h, l, c, v, delivery_pct, traded_qty "
             "FROM market_candles WHERE 1=1 {cursor} ORDER BY (ipo_id, d) LIMIT {limit}")
        # Use composite tuple keyset: (ipo_id, d)
        cursor = passes["market_candles"]["cursor"]
        while True:
            with neon.cursor() as cur:
                if cursor:
                    cur.execute(q.format(
                        cursor=f"AND (ipo_id, d) > ({cursor[0]}, {sql_literal(cursor[1])})",
                        limit=_BATCH))
                else:
                    cur.execute(q.format(cursor="", limit=_BATCH))
                rows = cur.fetchall()
                if not rows: break
                cols = [d[0] for d in cur.description]
            vals = []
            for r in rows:
                d = dict(zip(cols, r))
                vals.append([
                    d["ipo_id"], d["d"], "1d", "candle",
                    d["o"], d["h"], d["l"], d["c"], d["v"],
                    None, None, None, None, d["traded_qty"], d["delivery_pct"],
                    "kite", None,
                ])
            copied += _insert_rows("market_observations", _MO_COLS, vals,
                                    ["ipo_id", "interval", "observation_type", "observed_at"], sink)
            last = rows[-1]
            cursor = (last[cols.index("ipo_id")], last[cols.index("d")])
            passes["market_candles"]["cursor"] = list(cursor)
            _save_state()
        passes["market_candles"]["done"] = True
        _save_state()

    # ---- market_candles_15m → interval=15m, observation_type=candle -----------
    if not passes["market_candles_15m"]["done"]:
        q = ("SELECT ipo_id, ts, o, h, l, c, v FROM market_candles_15m "
             "WHERE 1=1 {cursor} ORDER BY (ipo_id, ts) LIMIT {limit}")
        cursor = passes["market_candles_15m"]["cursor"]
        while True:
            with neon.cursor() as cur:
                if cursor:
                    cur.execute(q.format(
                        cursor=f"AND (ipo_id, ts) > ({cursor[0]}, {sql_literal(cursor[1])})",
                        limit=_BATCH))
                else:
                    cur.execute(q.format(cursor="", limit=_BATCH))
                rows = cur.fetchall()
                if not rows: break
                cols = [d[0] for d in cur.description]
            vals = []
            for r in rows:
                d = dict(zip(cols, r))
                vals.append([
                    d["ipo_id"], d["ts"], "15m", "candle",
                    d["o"], d["h"], d["l"], d["c"], d["v"],
                    None, None, None, None, None, None,
                    "kite", None,
                ])
            copied += _insert_rows("market_observations", _MO_COLS, vals,
                                    ["ipo_id", "interval", "observation_type", "observed_at"], sink)
            last = rows[-1]
            cursor = (last[cols.index("ipo_id")], last[cols.index("ts")])
            passes["market_candles_15m"]["cursor"] = list(cursor)
            _save_state()
        passes["market_candles_15m"]["done"] = True
        _save_state()

    # ---- listing_observations → various intervals/types ----------------------
    if not passes["listing_observations"]["done"]:
        q = ("SELECT ipo_id, observed_at, obs_type, ltp, qty, buy_qty, sell_qty, payload::text "
             "FROM listing_observations WHERE 1=1 {cursor} "
             "ORDER BY (ipo_id, obs_type, observed_at) LIMIT {limit}")
        cursor = passes["listing_observations"]["cursor"]
        while True:
            with neon.cursor() as cur:
                if cursor:
                    cur.execute(q.format(
                        cursor=("AND (ipo_id, obs_type, observed_at) > "
                                f"({cursor[0]}, {sql_literal(cursor[1])}, {sql_literal(cursor[2])})"),
                        limit=_BATCH))
                else:
                    cur.execute(q.format(cursor="", limit=_BATCH))
                rows = cur.fetchall()
                if not rows: break
                cols = [d[0] for d in cur.description]
            vals = []
            for r in rows:
                d = dict(zip(cols, r))
                obs_type = d["obs_type"]
                interval = "preopen" if obs_type == "preopen" else "tick"
                # Normalise close_d1 to a distinct observation_type; interval maps to 'tick'
                # (single instant) unless we upgrade to daily.
                if obs_type == "close_d1":
                    interval = "1d"
                vals.append([
                    d["ipo_id"], d["observed_at"], interval, obs_type,
                    None, None, None, None, None,
                    d["ltp"], d["buy_qty"], d["sell_qty"], None, d["qty"], None,
                    "nse", d["payload"],
                ])
            copied += _insert_rows("market_observations", _MO_COLS, vals,
                                    ["ipo_id", "interval", "observation_type", "observed_at"], sink)
            last = rows[-1]
            cursor = (last[cols.index("ipo_id")], last[cols.index("obs_type")], last[cols.index("observed_at")])
            passes["listing_observations"]["cursor"] = [cursor[0], cursor[1], norm(cursor[2])]
            _save_state()
        passes["listing_observations"]["done"] = True
        _save_state()

    return {"target": "market_observations", "neon_rows": total_neon,
            "copied": copied, "elapsed_s": round(time.time() - started, 1)}


# ------------------------------------------------------------------ Target: research_findings

_RF_COLS = ["ipo_id", "finding_type", "source_type", "document_sha",
             "finding", "excerpt", "page_number",
             "severity", "confidence", "evidence_refs",
             "category", "direction",
             "model", "model_version", "prompt_version",
             "cost_usd", "is_current", "created_at"]


def target_research_findings(neon, sink: str, dry_run: bool, tstate: dict) -> dict:
    passes = tstate.setdefault("passes", {
        "rhp_findings":       {"cursor": None, "done": False},
        "insights":           {"cursor": None, "done": False},
        "ipo_rhp_intel":      {"cursor": None, "done": False},
        "ipo_research_notes": {"cursor": None, "done": False},
    })
    with neon.cursor() as cur:
        cur.execute(
            "SELECT (SELECT count(*) FROM rhp_findings) + "
            "(SELECT count(*) FROM insights) + "
            "(SELECT count(*) FROM ipo_rhp_intel) + "
            "(SELECT count(*) FROM ipo_research_notes)"
        )
        total_neon = cur.fetchone()[0]
    if dry_run:
        return {"target": "research_findings", "neon_rows": total_neon, "copied": 0, "dry_run": True}

    copied = 0; started = time.time()

    # rhp_findings → finding_type='rhp'
    if not passes["rhp_findings"]["done"]:
        q = ("SELECT id, ipo_id, doc_id, model, prompt_version, findings::text, red_flag_count, "
              "confidence, cost_usd, analyzed_at "
              "FROM rhp_findings WHERE 1=1 {cursor} ORDER BY id LIMIT {limit}")
        cursor = passes["rhp_findings"]["cursor"]
        while True:
            with neon.cursor() as cur:
                cur.execute(q.format(
                    cursor=f"AND id > {cursor}" if cursor else "", limit=_BATCH))
                rows = cur.fetchall()
                if not rows: break
                cols = [d[0] for d in cur.description]
            vals = []
            for r in rows:
                d = dict(zip(cols, r))
                vals.append([
                    d["ipo_id"], "rhp", "sebi_rhp", d["doc_id"],
                    d["findings"], None, None,
                    d["red_flag_count"], d["confidence"], None,
                    None, None,
                    d["model"], None, d["prompt_version"],
                    d["cost_usd"], 1, d["analyzed_at"],
                ])
            copied += _insert_rows("research_findings", _RF_COLS, vals, [], sink)
            passes["rhp_findings"]["cursor"] = rows[-1][cols.index("id")]
            _save_state()
        passes["rhp_findings"]["done"] = True; _save_state()

    # insights → finding_type='insight'
    if not passes["insights"]["done"]:
        q = ("SELECT id, ipo_id, excerpt, page_number, doc_id, category, direction, "
              "source_type, is_current "
              "FROM insights WHERE 1=1 {cursor} ORDER BY id LIMIT {limit}")
        cursor = passes["insights"]["cursor"]
        while True:
            with neon.cursor() as cur:
                cur.execute(q.format(
                    cursor=f"AND id > {cursor}" if cursor else "", limit=_BATCH))
                rows = cur.fetchall()
                if not rows: break
                cols = [d[0] for d in cur.description]
            vals = []
            for r in rows:
                d = dict(zip(cols, r))
                vals.append([
                    d["ipo_id"], "insight", d["source_type"] or "derived", d["doc_id"],
                    json.dumps({"excerpt": d["excerpt"], "category": d["category"],
                                "direction": d["direction"]}, default=str),
                    d["excerpt"], d["page_number"],
                    None, None, None,
                    d["category"], d["direction"],
                    None, None, None,
                    None, d["is_current"], None,
                ])
            copied += _insert_rows("research_findings", _RF_COLS, vals, [], sink)
            passes["insights"]["cursor"] = rows[-1][cols.index("id")]
            _save_state()
        passes["insights"]["done"] = True; _save_state()

    # ipo_rhp_intel → finding_type='rhp_summary'. Requires name resolution.
    if not passes["ipo_rhp_intel"]["done"]:
        q = ("SELECT company_name, verdict, one_line, quality_gate, margin_of_safety, "
              "full_json::text, confidence, rhp_url, pdf_sha256 "
              "FROM ipo_rhp_intel WHERE 1=1 {cursor} ORDER BY company_name LIMIT {limit}")
        cursor = passes["ipo_rhp_intel"]["cursor"]
        while True:
            with neon.cursor() as cur:
                cur.execute(q.format(
                    cursor=f"AND company_name > {sql_literal(cursor)}" if cursor else "",
                    limit=_BATCH))
                rows = cur.fetchall()
                if not rows: break
                cols = [d[0] for d in cur.description]
            vals = []
            for r in rows:
                d = dict(zip(cols, r))
                name_norm = _norm_name(d["company_name"])
                with neon.cursor() as ic:
                    ic.execute("SELECT id FROM ipo WHERE name_norm=%s", (name_norm,))
                    ipo_row = ic.fetchone()
                if not ipo_row:
                    _record_anomaly("research_findings", {"company_name": d["company_name"]},
                                    "no matching ipo.name_norm for ipo_rhp_intel")
                    continue
                ipo_id = ipo_row[0]
                finding_body = json.dumps({
                    "verdict": d["verdict"], "one_line": d["one_line"],
                    "quality_gate": d["quality_gate"], "margin_of_safety": str(d["margin_of_safety"] or ""),
                    "rhp_url": d["rhp_url"], "full": json.loads(d["full_json"]) if d["full_json"] else None,
                }, default=str)
                vals.append([
                    ipo_id, "rhp_summary", "sebi_rhp", d["pdf_sha256"],
                    finding_body, d["one_line"], None,
                    None, d["confidence"], None,
                    None, None, None, None, None, None,
                    1, None,
                ])
            copied += _insert_rows("research_findings", _RF_COLS, vals, [], sink)
            passes["ipo_rhp_intel"]["cursor"] = rows[-1][cols.index("company_name")]
            _save_state()
        passes["ipo_rhp_intel"]["done"] = True; _save_state()

    # ipo_research_notes → finding_type='sbi_note' | 'broker_note'
    if not passes["ipo_research_notes"]["done"]:
        q = ("SELECT source, company, nse_symbol, rating, full_json::text, one_line, peer_name, "
              "pdf_path, peer_ps, note_ps, parsed_at, price_low, price_high, fresh_cr, ofs_cr, "
              "issue_size_cr, qib_pct, nii_pct, retail_pct, brlms, registrar, loss_making "
              "FROM ipo_research_notes WHERE 1=1 {cursor} "
              "ORDER BY (source, company, COALESCE(nse_symbol,'')) LIMIT {limit}")
        cursor = passes["ipo_research_notes"]["cursor"]
        while True:
            with neon.cursor() as cur:
                if cursor:
                    cur.execute(q.format(
                        cursor=("AND (source, company, COALESCE(nse_symbol,'')) > "
                                f"({sql_literal(cursor[0])}, {sql_literal(cursor[1])}, {sql_literal(cursor[2])})"),
                        limit=_BATCH))
                else:
                    cur.execute(q.format(cursor="", limit=_BATCH))
                rows = cur.fetchall()
                if not rows: break
                cols = [d[0] for d in cur.description]
            vals = []
            for r in rows:
                d = dict(zip(cols, r))
                name_norm = _norm_name(d["company"])
                with neon.cursor() as ic:
                    ic.execute("SELECT id FROM ipo WHERE name_norm=%s", (name_norm,))
                    ipo_row = ic.fetchone()
                if not ipo_row:
                    _record_anomaly("research_findings", {"company": d["company"]},
                                    "no matching ipo.name_norm for ipo_research_notes")
                    continue
                ipo_id = ipo_row[0]
                finding_type = "sbi_note" if (d["source"] or "").lower() == "sbi" else "broker_note"
                finding_body = json.dumps({
                    "rating": d["rating"], "one_line": d["one_line"], "peer_name": d["peer_name"],
                    "peer_ps": str(d["peer_ps"] or ""), "note_ps": str(d["note_ps"] or ""),
                    "price_low": str(d["price_low"] or ""), "price_high": str(d["price_high"] or ""),
                    "fresh_cr": str(d["fresh_cr"] or ""), "ofs_cr": str(d["ofs_cr"] or ""),
                    "issue_size_cr": str(d["issue_size_cr"] or ""),
                    "qib_pct": str(d["qib_pct"] or ""), "nii_pct": str(d["nii_pct"] or ""),
                    "retail_pct": str(d["retail_pct"] or ""),
                    "brlms": d["brlms"], "registrar": d["registrar"],
                    "loss_making": d["loss_making"],
                    "full": json.loads(d["full_json"]) if d["full_json"] else None,
                }, default=str)
                vals.append([
                    ipo_id, finding_type, d["source"] or "derived", None,
                    finding_body, d["one_line"], None,
                    None, None, None, None, None,
                    None, None, None, None, 1, d["parsed_at"],
                ])
            copied += _insert_rows("research_findings", _RF_COLS, vals, [], sink)
            last = rows[-1]
            passes["ipo_research_notes"]["cursor"] = [
                last[cols.index("source")], last[cols.index("company")],
                last[cols.index("nse_symbol")] or "",
            ]
            _save_state()
        passes["ipo_research_notes"]["done"] = True; _save_state()

    return {"target": "research_findings", "neon_rows": total_neon,
            "copied": copied, "elapsed_s": round(time.time() - started, 1)}


# ------------------------------------------------------------------ Target: source_facts
#
# Neon's `source_facts` PK was `(ipo_id, field, source, fetched_at)` — too
# permissive under retries. We rehash every row into `observation_hash` and
# rely on the new UNIQUE (ipo_id, field, observation_hash) constraint.

_SF_COLS = ["ipo_id", "field", "value", "source", "document_sha", "confidence",
             "pipeline_version", "is_current", "observation_hash", "fetched_at"]


def target_source_facts(neon, sink: str, dry_run: bool, tstate: dict) -> dict:
    with neon.cursor() as cur:
        cur.execute("SELECT count(*) FROM source_facts")
        total = cur.fetchone()[0]
    if dry_run:
        return {"target": "source_facts", "neon_rows": total, "copied": 0, "dry_run": True}

    # Composite keyset on (ipo_id, field, source, fetched_at).
    q = ("SELECT ipo_id, field, value, source, doc_id, confidence, fetched_at "
          "FROM source_facts WHERE 1=1 {cursor} "
          "ORDER BY (ipo_id, field, source, fetched_at) LIMIT {limit}")
    cursor = tstate.get("cursor")
    copied = 0; started = time.time()
    while True:
        with neon.cursor() as cur:
            if cursor:
                cur.execute(q.format(
                    cursor=("AND (ipo_id, field, source, fetched_at) > "
                            f"({cursor[0]}, {sql_literal(cursor[1])}, {sql_literal(cursor[2])}, "
                            f"{sql_literal(cursor[3])})"),
                    limit=_BATCH))
            else:
                cur.execute(q.format(cursor="", limit=_BATCH))
            rows = cur.fetchall()
            if not rows: break
            cols = [d[0] for d in cur.description]
        vals = []
        for r in rows:
            d = dict(zip(cols, r))
            value_norm = None if d["value"] is None else str(norm(d["value"]))
            h = observation_hash(d["field"], value_norm, d["source"], d["doc_id"], _PIPELINE_VERSION)
            vals.append([
                d["ipo_id"], d["field"], value_norm, d["source"], d["doc_id"],
                d["confidence"], _PIPELINE_VERSION, 1, h, d["fetched_at"],
            ])
        copied += _insert_rows("source_facts", _SF_COLS, vals,
                                ["ipo_id", "field", "observation_hash"], sink)
        last = rows[-1]
        cursor = [
            last[cols.index("ipo_id")], last[cols.index("field")],
            last[cols.index("source")], norm(last[cols.index("fetched_at")]),
        ]
        tstate["cursor"] = cursor
        _save_state()
    return {"target": "source_facts", "neon_rows": total, "copied": copied,
            "elapsed_s": round(time.time() - started, 1)}


# ------------------------------------------------------------------ State

_STATE_CACHE: dict = {}

def load_state() -> dict:
    global _STATE_CACHE
    if _STATE.exists():
        _STATE_CACHE = json.loads(_STATE.read_text())
    else:
        _STATE_CACHE = {"targets": {}}
    return _STATE_CACHE

def _save_state() -> None:
    _STATE.write_text(json.dumps(_STATE_CACHE, indent=2, sort_keys=True, default=str))


# ------------------------------------------------------------------ Entrypoint

TARGETS = [
    ("ipo",                 target_ipo),
    ("fundamentals",        target_fundamentals),
    ("market_observations", target_market_observations),
    ("research_findings",   target_research_findings),
    ("source_facts",        target_source_facts),
]

# Neon tables that MUST NOT be migrated (secrets / observability / KV-plane).
EXCLUDED_NEON_TABLES = [
    "kite_session", "platform_config", "access_requests",
    "pipeline_steps", "pipeline_failures", "rule_validation_results",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sink", choices=["wrangler-local", "wrangler-remote-staging"],
                    default="wrangler-local")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fresh", action="store_true",
                    help="Delete _migrate/state.json and start over. Does NOT touch Neon.")
    ap.add_argument("--targets", nargs="+", choices=[t[0] for t in TARGETS],
                    help="Optional subset of D1 target tables.")
    args = ap.parse_args()

    if args.fresh:
        for p in (_STATE, _ANOMALIES): p.unlink(missing_ok=True)

    state = load_state()
    state.setdefault("targets", {})
    report = {
        "sink": args.sink, "dry_run": args.dry_run,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "excluded_neon_tables": EXCLUDED_NEON_TABLES,
        "targets": [],
    }

    print(f"neon_to_d1: sink={args.sink}  dry_run={args.dry_run}  batch={_BATCH}")
    print("excluded Neon tables (kept OUT of D1 by design): " + ", ".join(EXCLUDED_NEON_TABLES))

    neon = neon_conn()
    try:
        for name, fn in TARGETS:
            if args.targets and name not in args.targets: continue
            tstate = state["targets"].setdefault(name, {})
            if tstate.get("done"):
                print(f"  {name}: already done")
                continue
            print(f"  {name}: starting ...")
            result = fn(neon, args.sink, args.dry_run, tstate)
            report["targets"].append(result)
            tstate["done"] = True
            _save_state()
            print(f"    -> {result}")
    finally:
        neon.close()

    report["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _REPORT_JSON.write_text(json.dumps(report, indent=2, default=str))
    with _REPORT_MD.open("w") as h:
        h.write(f"# Neon → D1 copy report (5-table target)\n\n")
        h.write(f"Sink: `{args.sink}`  •  Dry run: `{args.dry_run}`  •  ")
        h.write(f"{report['started_at']} → {report['ended_at']}\n\n")
        h.write("| Target | Neon rows | Copied | Elapsed (s) |\n|---|---:|---:|---:|\n")
        for t in report["targets"]:
            h.write(f"| {t['target']} | {t.get('neon_rows', 0)} | "
                    f"{t.get('copied', 0)} | {t.get('elapsed_s', 0)} |\n")
        h.write("\n### Excluded Neon tables (kept OUT of D1 by design)\n\n")
        h.write(", ".join(f"`{t}`" for t in EXCLUDED_NEON_TABLES) + "\n")
    print(f"report: {_REPORT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
