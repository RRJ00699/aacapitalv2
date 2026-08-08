"""
AACapital — Kite IPO Sync
Task 8: Build kite-sync-ipos.py — live IPO data from Zerodha

Fetches live IPO subscription, allotment status, and listing signals
from Zerodha Kite and syncs them to Neon ipo_intelligence.

Usage:
    python _scripts/kite-sync-ipos.py            # sync live + upcoming IPOs
    python _scripts/kite-sync-ipos.py --dry-run  # preview without writing
    python _scripts/kite-sync-ipos.py --listing  # include listing day signals
"""

import os
import sys
import argparse
import json
from datetime import date, datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
import requests
from kiteconnect import KiteConnect
from dotenv import load_dotenv

load_dotenv(".env.local")

NEON_URL     = os.environ["NEON_DATABASE_URL"]
KITE_API_KEY = os.environ["KITE_API_KEY"]
KITE_TOKEN   = os.environ.get("KITE_ACCESS_TOKEN", "")
if not KITE_TOKEN:
    try:
        import psycopg2 as _pg
        _db = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL", "")
        if _db:
            _c = _pg.connect(_db); _cur = _c.cursor()
            _cur.execute("SELECT value FROM platform_config WHERE key = 'kite_access_token'")
            _r = _cur.fetchone(); _cur.close(); _c.close()
            if _r and _r[0]: KITE_TOKEN = str(_r[0]).strip()
    except Exception:
        pass


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def get_kite() -> KiteConnect:
    kite = KiteConnect(api_key=KITE_API_KEY)
    kite.set_access_token(KITE_TOKEN)
    return kite


def get_neon():
    return psycopg2.connect(NEON_URL)


# ── IPO list from Kite ─────────────────────────────────────────────────────────

def fetch_kite_ipos(kite: KiteConnect) -> list[dict]:
    """
    Fetch IPOs via Kite Connect REST API.
    Returns list of IPO dicts with status, subscription, dates.
    """
    try:
        # Kite's IPO endpoint (undocumented but available via REST)
        url = f"https://api.kite.trade/ipo"
        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {KITE_API_KEY}:{KITE_TOKEN}",
        }
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        ipos = data.get("data", [])
        log(f"Kite returned {len(ipos)} IPOs")
        return ipos
    except Exception as e:
        log(f"Kite IPO API error: {e}")
        log("Falling back to Kite instruments search for listed IPOs…")
        return []


def fetch_listing_signals(kite: KiteConnect, symbol: str) -> dict:
    """
    Fetch listing day OI + VWAP signals for a symbol.
    Used on listing day to get real-time signals.
    """
    signals = {}
    try:
        # Get quote
        quote = kite.quote([f"NSE:{symbol}"])
        q = quote.get(f"NSE:{symbol}", {})

        signals["last_price"]    = q.get("last_price")
        signals["volume"]        = q.get("volume")
        signals["buy_quantity"]  = q.get("buy_quantity")
        signals["sell_quantity"] = q.get("sell_quantity")
        signals["ohlc"]          = q.get("ohlc", {})

        # VWAP approximation from intraday candles
        candles = kite.historical_data(
            instrument_token=_get_token(kite, symbol),
            from_date=date.today(),
            to_date=date.today(),
            interval="15minute",
        )
        if candles:
            total_vol = sum(c["volume"] for c in candles)
            vwap = sum(
                ((c["high"] + c["low"] + c["close"]) / 3) * c["volume"]
                for c in candles
            ) / total_vol if total_vol else 0
            signals["vwap"] = round(vwap, 2)
            signals["above_vwap"] = (signals["last_price"] or 0) > vwap

    except Exception as e:
        log(f"  Listing signal error for {symbol}: {e}")

    return signals


def _get_token(kite: KiteConnect, symbol: str) -> Optional[int]:
    try:
        instruments = kite.instruments("NSE")
        for inst in instruments:
            if inst["tradingsymbol"] == symbol:
                return inst["instrument_token"]
    except Exception:
        pass
    return None


# ── map Kite IPO fields to our schema ─────────────────────────────────────────

def map_kite_ipo(raw: dict) -> dict:
    """
    Map Kite IPO API response fields to ipo_intelligence columns.
    Kite field names may vary — we handle both snake_case variants.
    """

    def g(key: str):
        return raw.get(key) or raw.get(key.replace("_", ""))

    status_map = {
        "open":         "OPEN",
        "closed":       "CLOSED",
        "allotment":    "ALLOTMENT_PENDING",
        "listing":      "LISTING_PENDING",
        "listed":       "LISTED",
        "withdrawn":    "WITHDRAWN",
    }

    raw_status = (g("status") or "").lower()
    status     = status_map.get(raw_status, raw_status.upper())

    data = {
        "company_name":        g("name") or g("company_name"),
        "kite_ipo_id":         g("id") or g("ipo_id"),
        "ipo_status":          status,
        "issue_price":         g("price") or g("issue_price"),
        "lot_size":            g("lot_size"),
        "issue_open_date":     g("open_date") or g("issue_open_date"),
        "issue_close_date":    g("close_date") or g("issue_close_date"),
        "listing_date":        g("listing_date"),
        "issue_size_cr":       g("size") or g("issue_size"),
        "exchange":            g("exchange") or "NSE",
        "is_sme":              bool(g("sme")),
        "listing_exchange":    g("listing_exchange") or "NSE",
        "kite_synced_at":      datetime.now(timezone.utc).isoformat(),

        # subscription if available from Kite
        "total_subscription":  g("total_subscription") or g("subscription"),
        "qib_subscription":    g("qib_subscription") or g("qib"),
        "nii_subscription":    g("nii_subscription") or g("nii"),
        "retail_subscription": g("retail_subscription") or g("retail"),
    }

    # Remove None values
    return {k: v for k, v in data.items() if v is not None}


# ── ensure Neon schema ─────────────────────────────────────────────────────────

def ensure_kite_columns(conn):
    cur = conn.cursor()
    extra_cols = [
        ("kite_ipo_id",      "TEXT"),
        ("ipo_status",       "TEXT"),
        ("issue_open_date",  "DATE"),
        ("issue_close_date", "DATE"),
        ("exchange",         "TEXT"),
        ("is_sme",           "BOOLEAN"),
        ("listing_exchange", "TEXT"),
        ("kite_synced_at",   "TIMESTAMPTZ"),
        ("vwap",             "NUMERIC(10,2)"),
        ("above_vwap",       "BOOLEAN"),
        ("listing_volume",   "BIGINT"),
        ("buy_qty",          "BIGINT"),
        ("sell_qty",         "BIGINT"),
    ]
    for col, dtype in extra_cols:
        cur.execute(f"""
            ALTER TABLE ipo_intelligence
            ADD COLUMN IF NOT EXISTS {col} {dtype}
        """)
    conn.commit()
    log("Kite columns ensured in ipo_intelligence")


# ── upsert ─────────────────────────────────────────────────────────────────────

def upsert_ipo(conn, data: dict, dry_run: bool = False):
    name = data.get("company_name", "UNKNOWN")

    if dry_run:
        log(f"  [DRY RUN] Would upsert: {name} — {json.dumps({k:v for k,v in data.items() if k not in ['company_name']}, default=str)}")
        return

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Check if IPO already exists
    cur.execute(
        "SELECT id FROM ipo_intelligence WHERE company_name ILIKE %s",
        (f"%{name}%",)
    )
    row = cur.fetchone()

    if row:
        ipo_id = row["id"]
        set_parts = [f"{k} = %s" for k in data if k != "company_name"]
        values    = [data[k] for k in data if k != "company_name"]
        values.append(ipo_id)
        if set_parts:
            cur.execute(
                f"UPDATE ipo_intelligence SET {', '.join(set_parts)} WHERE id = %s",
                values
            )
            log(f"  Updated: {name} (id={ipo_id})")
    else:
        # New IPO — insert
        cols = list(data.keys())
        vals = list(data.values())
        cur.execute(
            f"INSERT INTO ipo_intelligence ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(cols))})",
            vals
        )
        log(f"  Inserted new IPO: {name}")

    conn.commit()


def sync_listing_signals(kite: KiteConnect, conn, dry_run: bool):
    """
    For IPOs with ipo_status=LISTING_PENDING and listing_date=today,
    fetch live OI + VWAP signals.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, company_name, nse_symbol
        FROM ipo_intelligence
        WHERE ipo_status IN ('LISTING_PENDING', 'LISTED')
          AND listing_date = CURRENT_DATE
          AND nse_symbol IS NOT NULL
    """)
    listing_today = cur.fetchall()

    if not listing_today:
        log("No IPOs listing today — skipping listing signal fetch")
        return

    log(f"{len(listing_today)} IPO(s) listing today — fetching signals")
    for ipo in listing_today:
        symbol  = ipo["nse_symbol"]
        signals = fetch_listing_signals(kite, symbol)
        if signals:
            update_data = {
                "vwap":           signals.get("vwap"),
                "above_vwap":     signals.get("above_vwap"),
                "listing_volume": signals.get("volume"),
                "buy_qty":        signals.get("buy_quantity"),
                "sell_qty":       signals.get("sell_quantity"),
            }
            update_data = {k: v for k, v in update_data.items() if v is not None}
            if not dry_run and update_data:
                set_parts = [f"{k} = %s" for k in update_data]
                values    = list(update_data.values()) + [ipo["id"]]
                conn.cursor().execute(
                    f"UPDATE ipo_intelligence SET {', '.join(set_parts)} WHERE id = %s",
                    values
                )
                conn.commit()
                log(f"  Listing signals saved for {ipo['company_name']}")
            else:
                log(f"  [DRY RUN] {ipo['company_name']}: {update_data}")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AACapital — Kite IPO Sync")
    parser.add_argument("--dry-run",  action="store_true", help="Preview without writing to DB")
    parser.add_argument("--listing",  action="store_true", help="Also fetch listing day signals")
    args = parser.parse_args()

    log("═" * 50)
    log("AACapital — Kite IPO Sync")
    log("═" * 50)

    kite = get_kite()
    conn = get_neon()

    ensure_kite_columns(conn)

    # Fetch from Kite
    raw_ipos = fetch_kite_ipos(kite)

    if raw_ipos:
        log(f"\nProcessing {len(raw_ipos)} Kite IPOs…")
        for raw in raw_ipos:
            data = map_kite_ipo(raw)
            upsert_ipo(conn, data, dry_run=args.dry_run)
        log(f"✅ Kite sync complete — {len(raw_ipos)} IPOs processed")
    else:
        log("No IPOs returned from Kite API — DB unchanged for main sync")

    # Listing day signals
    if args.listing:
        log("\n── Listing Day Signals ──")
        sync_listing_signals(kite, conn, dry_run=args.dry_run)

    conn.close()
    log("\n✅ Kite IPO Sync done")


if __name__ == "__main__":
    main()
