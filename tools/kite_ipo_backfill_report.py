from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import psycopg2
from kiteconnect import KiteConnect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "kite-ipo-backfill-report.json"

# Calibrated from the 10-IPO probe committed in tools/kite_ipo_coverage_probe.py.
# The sample covered 2016, 2018, 2020, 2023, 2026 and listing->lock30 only.
AVG_5M_ROWS_PER_IPO = 1626.6
AVG_DAY_ROWS_PER_IPO = 21.8
# Conservative planning range for a D1 market_bars row including SQLite/index overhead.
BYTES_PER_ROW_LOW = 120
BYTES_PER_ROW_HIGH = 180


def db_url() -> str:
    url = os.environ.get("NEON_READONLY_DATABASE_URL") or os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        raise SystemExit("NEON_READONLY_DATABASE_URL (preferred) or DATABASE_URL is required")
    return url


def get_rows(conn):
    cur = conn.cursor()
    cur.execute("""
      SELECT id, symbol, isin, listing_date, COALESCE(lock30, listing_date + 30) AS lock30, kite_token
      FROM ipo
      WHERE COALESCE(is_mainboard,false)=true
        AND listing_date IS NOT NULL
        AND listing_date >= DATE '2016-01-01'
        AND listing_date <= CURRENT_DATE
      ORDER BY listing_date, id
    """)
    rows = cur.fetchall()
    cur.close()
    return rows


def get_kite(conn):
    cur = conn.cursor()
    cur.execute("SELECT value FROM platform_config WHERE key='kite_api_key'")
    r = cur.fetchone()
    api_key = (r[0] if r else None) or os.environ.get("KITE_API_KEY")
    cur.execute("SELECT value FROM platform_config WHERE key='kite_access_token'")
    r = cur.fetchone()
    token = (r[0] if r else None) or os.environ.get("KITE_ACCESS_TOKEN")
    cur.close()
    if not api_key or not token:
        raise SystemExit("Kite credentials unavailable; run _scripts/refresh_kite_token.py first")
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(token)
    profile = kite.profile()
    print(f"Kite token valid for user_id={profile.get('user_id')}")
    return kite


def main():
    conn = psycopg2.connect(db_url(), connect_timeout=20)
    conn.set_session(readonly=True, autocommit=False)
    rows = get_rows(conn)
    kite = get_kite(conn)

    current = kite.instruments("NSE")
    current_by_symbol = {
        str(i.get("tradingsymbol") or "").upper(): int(i["instrument_token"])
        for i in current
        if i.get("segment") == "NSE" and i.get("instrument_token")
    }

    stored = 0
    recovered_current_symbol = 0
    unresolved = []
    windows = []
    for ipo_id, symbol, isin, listing_date, lock30, kite_token in rows:
        sym = str(symbol or "").strip().upper()
        token = int(kite_token) if kite_token is not None else None
        source = "stored"
        if token is None and sym:
            token = current_by_symbol.get(sym) or current_by_symbol.get(f"{sym}-EQ")
            if token is not None:
                source = "current_symbol"
                recovered_current_symbol += 1
        if token is not None and source == "stored":
            stored += 1
        if token is None:
            unresolved.append({"ipo_id": int(ipo_id), "symbol": sym or None, "isin": isin, "listing_date": str(listing_date)})
        windows.append({
            "ipo_id": int(ipo_id), "symbol": sym or None, "isin": isin,
            "listing_date": str(listing_date), "lock30": str(lock30),
            "kite_token": token, "token_source": source if token is not None else "unresolved"
        })

    resolved = len(rows) - len(unresolved)
    projected_5m = round(resolved * AVG_5M_ROWS_PER_IPO)
    projected_day = round(resolved * AVG_DAY_ROWS_PER_IPO)
    projected_total = projected_5m + projected_day
    storage_low = projected_total * BYTES_PER_ROW_LOW
    storage_high = projected_total * BYTES_PER_ROW_HIGH

    report = {
        "as_of": str(date.today()),
        "eligible_ipos": len(rows),
        "with_stored_kite_token": stored,
        "recovered_from_current_symbol": recovered_current_symbol,
        "resolved_for_backfill": resolved,
        "unresolved_token": len(unresolved),
        "projected_rows": {
            "5minute": projected_5m,
            "day": projected_day,
            "total_persisted": projected_total,
            "15minute_persisted": 0,
        },
        "projected_d1_increment_mb": {
            "low_120_bytes_per_row": round(storage_low / 1024 / 1024, 1),
            "high_180_bytes_per_row": round(storage_high / 1024 / 1024, 1),
        },
        "policy": {
            "window": "listing_date_through_lock30",
            "persist": ["5minute", "day"],
            "derive": ["15minute", "listing_outcomes", "top_bottom_metrics"],
            "writes_performed": False,
        },
        "unresolved": unresolved,
        "windows": windows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "eligible_ipos", "with_stored_kite_token", "recovered_from_current_symbol",
        "resolved_for_backfill", "unresolved_token", "projected_rows", "projected_d1_increment_mb"
    )}, sort_keys=True))
    print(f"output={OUT.relative_to(ROOT)}")
    conn.close()


if __name__ == "__main__":
    main()
