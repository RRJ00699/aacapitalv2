from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import tempfile
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]


def npx_cmd() -> str:
    return "npx.cmd" if platform.system().lower().startswith("win") else "npx"


def db_url() -> str:
    url = os.environ.get("NEON_READONLY_DATABASE_URL") or os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        raise SystemExit("NEON_READONLY_DATABASE_URL (preferred) or DATABASE_URL is required")
    return url


def sqlv(value) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def fp(*parts) -> str:
    body = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def decimal_text(value):
    if value is None:
        return None
    try:
        return str(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def d1_query(config: Path, binding: str, sql: str):
    sql = sql.strip()
    if not sql.endswith(";"):
        sql += ";"
    cmd = [npx_cmd(), "wrangler", "--config", str(config), "d1", "execute", binding,
           "--remote", "--command", sql, "--json"]
    cp = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if cp.returncode != 0:
        raise SystemExit(f"Wrangler D1 query failed (exit={cp.returncode})\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")
    payload = json.loads(cp.stdout)
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("results"), list):
                return item["results"]
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def execute_sql_file(config: Path, binding: str, statements: list[str], retries: int = 2):
    if not statements:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8", newline="\n") as f:
        f.write("PRAGMA foreign_keys=ON;\n")
        for statement in statements:
            f.write(statement + "\n")
        path = Path(f.name)
    try:
        cmd = [npx_cmd(), "wrangler", "--config", str(config), "d1", "execute", binding,
               "--remote", "--file", str(path), "--yes"]
        for attempt in range(retries + 1):
            cp = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
            if cp.returncode == 0:
                if cp.stdout:
                    print(cp.stdout, end="" if cp.stdout.endswith("\n") else "\n")
                return
            if attempt < retries and "Authentication error [code: 10000]" not in (cp.stdout + cp.stderr):
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(
                f"Wrangler D1 import failed (exit={cp.returncode})\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}"
            )
    finally:
        path.unlink(missing_ok=True)


def load_neon():
    conn = psycopg2.connect(db_url(), connect_timeout=20)
    conn.set_session(readonly=True, autocommit=False)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
              SELECT ipo_id, observed_at, ltp, qty, buy_qty, sell_qty, payload
              FROM listing_observations
              WHERE obs_type='preopen'
              ORDER BY ipo_id, observed_at
            """)
            preopen = list(cur.fetchall())

            cur.execute("""
              SELECT DISTINCT ON (obs_type, observed_at)
                     obs_type, observed_at, ltp, payload
              FROM listing_observations
              WHERE obs_type IN ('nifty_5m','vix_5m')
              ORDER BY obs_type, observed_at, ipo_id
            """)
            bars = list(cur.fetchall())

            cur.execute("""
              SELECT d, regime, vix, breadth_pct, pcr
              FROM market_regimes
              ORDER BY d
            """)
            daily = list(cur.fetchall())
    finally:
        conn.close()
    return preopen, bars, daily


def preopen_statement(r: dict) -> str:
    payload = r.get("payload") or {}
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    observed_at = r["observed_at"].isoformat()
    ipo_id = int(r["ipo_id"])
    price = decimal_text(r.get("ltp"))
    buy = int(r["buy_qty"]) if r.get("buy_qty") is not None else None
    sell = int(r["sell_qty"]) if r.get("sell_qty") is not None else None
    ieq_raw = payload.get("ieq") if isinstance(payload, dict) else None
    ieq = int(ieq_raw) if ieq_raw is not None else None
    fingerprint = fp("neon_preopen", ipo_id, observed_at, price, buy, sell, ieq, payload_json)
    return (
        "INSERT INTO listing_observations(ipo_id,observation_type,observed_at,price_rs,buy_qty_shares,sell_qty_shares,ieq_shares,payload_json,source_name,content_fingerprint) VALUES("
        f"{ipo_id},'preopen',{sqlv(observed_at)},{sqlv(price)},{'NULL' if buy is None else buy},{'NULL' if sell is None else sell},"
        f"{'NULL' if ieq is None else ieq},{sqlv(payload_json)},'neon_legacy_preopen',{sqlv(fingerprint)}) "
        "ON CONFLICT(content_fingerprint) DO NOTHING;"
    )


def bar_statement(r: dict) -> str | None:
    payload = r.get("payload") or {}
    symbol = "NIFTY50" if r["obs_type"] == "nifty_5m" else "INDIAVIX"
    vals = {k: decimal_text(payload.get(k)) for k in ("o", "h", "l", "c")}
    if any(vals[k] is None for k in vals):
        return None
    observed_at = r["observed_at"].isoformat()
    fingerprint = fp("neon_global_5m", symbol, observed_at, vals["o"], vals["h"], vals["l"], vals["c"])
    return (
        "INSERT INTO market_context_bars(symbol,interval,ts,open_value,high_value,low_value,close_value,source_name,content_fingerprint) VALUES("
        f"{sqlv(symbol)},'5m',{sqlv(observed_at)},{sqlv(vals['o'])},{sqlv(vals['h'])},{sqlv(vals['l'])},{sqlv(vals['c'])},"
        f"'neon_legacy_listing_observations',{sqlv(fingerprint)}) ON CONFLICT(symbol,interval,ts) DO NOTHING;"
    )


def daily_statement(r: dict) -> str:
    d = r["d"].date().isoformat() if hasattr(r["d"], "date") else str(r["d"])[:10]
    regime = r.get("regime")
    vix = decimal_text(r.get("vix"))
    breadth = decimal_text(r.get("breadth_pct"))
    # Neon has no populated historical PCR and no raw advances/declines columns.
    fingerprint = fp("neon_market_regime", d, regime, vix, breadth)
    return (
        "INSERT INTO market_context_daily(d,regime,vix_close,breadth_pct,advances,declines,pcr,source_name,content_fingerprint) VALUES("
        f"{sqlv(d)},{sqlv(regime)},{sqlv(vix)},{sqlv(breadth)},NULL,NULL,NULL,'neon_legacy_market_regimes',{sqlv(fingerprint)}) "
        "ON CONFLICT(d) DO NOTHING;"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate compact pre-open + global 5m Nifty/VIX + daily breadth from Neon to D1")
    ap.add_argument("--wrangler-config", type=Path, required=True)
    ap.add_argument("--binding", default="DB")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-statements-per-import", type=int, default=2000)
    args = ap.parse_args()

    if args.apply and os.environ.get("AACAPITAL_D1_STAGING_CONFIRM") != "YES":
        ap.error("set AACAPITAL_D1_STAGING_CONFIRM=YES before remote D1 writes")

    config = args.wrangler_config.resolve()
    # Fail fast if migration 0005 has not been applied.
    d1_query(config, args.binding, "SELECT COUNT(*) AS n FROM market_context_bars")
    d1_query(config, args.binding, "SELECT COUNT(*) AS n FROM market_context_daily")

    preopen, bars, daily = load_neon()
    parent_ids = sorted({int(r["ipo_id"]) for r in preopen})
    if parent_ids:
        csv = ",".join(map(str, parent_ids))
        found = d1_query(config, args.binding, f"SELECT id FROM ipo WHERE id IN ({csv})")
        found_ids = {int(r["id"]) for r in found}
        missing = sorted(set(parent_ids) - found_ids)
        if missing:
            raise SystemExit(f"D1 parent spine missing preopen ipo ids: {missing}")

    statements = [preopen_statement(r) for r in preopen]
    bad_bars = 0
    for r in bars:
        s = bar_statement(r)
        if s is None:
            bad_bars += 1
        else:
            statements.append(s)
    statements.extend(daily_statement(r) for r in daily)

    expected = {
        "preopen_rows": len(preopen),
        "global_5m_rows": len(bars) - bad_bars,
        "nifty_5m_rows": sum(1 for r in bars if r["obs_type"] == "nifty_5m"),
        "vix_5m_rows": sum(1 for r in bars if r["obs_type"] == "vix_5m"),
        "daily_context_rows": len(daily),
        "bad_market_bars": bad_bars,
        "statements": len(statements),
    }

    if not args.apply:
        print(json.dumps({"mode": "FETCH_ONLY", **expected}, sort_keys=True))
        return 0

    for i in range(0, len(statements), args.max_statements_per_import):
        chunk = statements[i:i + args.max_statements_per_import]
        print(f"D1 import {i + 1}-{i + len(chunk)} / {len(statements)}")
        execute_sql_file(config, args.binding, chunk)

    counts = {}
    checks = {
        "preopen_d1": "SELECT COUNT(*) AS n FROM listing_observations WHERE observation_type='preopen' AND source_name='neon_legacy_preopen'",
        "nifty_5m_d1": "SELECT COUNT(*) AS n FROM market_context_bars WHERE symbol='NIFTY50' AND interval='5m'",
        "vix_5m_d1": "SELECT COUNT(*) AS n FROM market_context_bars WHERE symbol='INDIAVIX' AND interval='5m'",
        "daily_context_d1": "SELECT COUNT(*) AS n FROM market_context_daily",
    }
    for key, sql in checks.items():
        rows = d1_query(config, args.binding, sql)
        counts[key] = int(rows[0]["n"]) if rows else 0

    result = {"mode": "APPLY", **expected, **counts,
              "nifty_policy": "GLOBAL_5M_ONLY",
              "vix_policy": "GLOBAL_5M_ONLY",
              "pcr_policy": "NO_HISTORICAL_DATA_FORWARD_ONLY",
              "advances_declines_policy": "NO_HISTORICAL_RAW_COUNTS_FORWARD_DAILY"}
    out = ROOT / "artifacts" / "d1-market-context-backfill.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    print(f"output={out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
