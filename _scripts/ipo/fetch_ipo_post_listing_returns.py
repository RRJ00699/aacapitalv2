"""
_scripts/ipo/fetch_ipo_post_listing_returns.py
================================================
Fetches post-listing returns for all IPOs using Kite historical API.
Uses listing_date + nse_symbol from ipo_intelligence to compute:
  - return_listing_open  (open price on listing day vs issue price)
  - return_day1_close    (close price on listing day vs issue price)
  - return_day7          (7 days after listing vs issue price)
  - return_day30         (30 days after listing vs issue price)
  - return_day90         (90 days after listing vs issue price)
  - return_day180        (180 days after listing vs issue price)
  - return_day365        (1 year after listing vs issue price)
  - listing_day_high     (listing day high)
  - listing_day_low      (listing day low)
  - hit_uc_day1          (did it hit upper circuit on day 1?)
  - hit_lc_day1          (did it hit lower circuit on day 1?)

Why Kite? 
  - You already have access
  - Free historical OHLC data
  - 5+ years of data available
  - Works for all NSE listed stocks

Usage:
  python _scripts/ipo/fetch_ipo_post_listing_returns.py           # all IPOs missing returns
  python _scripts/ipo/fetch_ipo_post_listing_returns.py --year 2024
  python _scripts/ipo/fetch_ipo_post_listing_returns.py --symbol BAJAJHFL
  python _scripts/ipo/fetch_ipo_post_listing_returns.py --limit 20 --dry-run

Prerequisites:
  - Kite access token must be fresh (run refresh_kite_token.py if expired)
  - DATABASE_URL must be set
"""

import os, sys, time, math, logging, argparse, datetime
import psycopg2, psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
API_KEY      = os.environ.get("KITE_API_KEY", "br9m41pn8nvvywnl")

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def get_kite():
    """Get authenticated Kite instance."""
    from kiteconnect import KiteConnect
    # Try token from DB first
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT value FROM platform_config WHERE key = 'kite_access_token'")
    row = cur.fetchone()
    conn.close()
    if not row:
        raise Exception("No kite_access_token in DB. Run: python _scripts/refresh_kite_token.py")
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(row[0])
    log.info("Kite connected")
    return kite

def n(v, d=None):
    try:
        if v is None: return d
        return float(v)
    except: return d

def get_ipos_needing_returns(year=None, limit=100, symbol=None) -> list:
    """Get IPOs where post-listing returns are missing."""
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    q = """
        SELECT id, company_name, nse_symbol, issue_price, listing_date,
               return_day30, return_day365
        FROM ipo_intelligence
        WHERE nse_symbol IS NOT NULL
          AND nse_symbol != ''
          AND nse_symbol != 'nan'
          AND listing_date IS NOT NULL
          AND listing_date < CURRENT_DATE - INTERVAL '7 days'
          AND (return_day30 IS NULL OR return_day7 IS NULL)
    """
    params = []

    if symbol:
        q += " AND (nse_symbol ILIKE %s OR company_name ILIKE %s)"
        params += [f"%{symbol}%", f"%{symbol}%"]
    elif year:
        q += " AND EXTRACT(YEAR FROM listing_date) = %s"
        params.append(year)

    q += " ORDER BY listing_date DESC LIMIT %s"
    params.append(limit)

    cur.execute(q, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    log.info(f"Found {len(rows)} IPOs needing post-listing returns")
    return rows

# Global instrument map — loaded once
_INSTRUMENT_MAP: dict = {}

def load_instruments(kite) -> dict:
    """Load all NSE instruments once and build symbol→token map."""
    global _INSTRUMENT_MAP
    if _INSTRUMENT_MAP:
        return _INSTRUMENT_MAP
    try:
        log.info("Loading NSE instrument list...")
        instruments = kite.instruments("NSE")
        _INSTRUMENT_MAP = {
            inst['tradingsymbol']: inst['instrument_token']
            for inst in instruments
        }
        log.info(f"  Loaded {len(_INSTRUMENT_MAP)} NSE instruments")
    except Exception as e:
        log.error(f"Failed to load instruments: {e}")
    return _INSTRUMENT_MAP

def get_instrument_token(kite, symbol: str) -> int | None:
    """Get instrument token from pre-loaded map."""
    imap = load_instruments(kite)
    token = imap.get(symbol.upper())
    if not token:
        # Try common suffix variants
        for variant in [symbol.upper(), symbol.upper()+"-BE", symbol.upper()+"-BL"]:
            if variant in imap:
                return imap[variant]
    return token

def compute_returns(kite, ipo: dict) -> dict:
    """
    Compute post-listing returns for one IPO using Kite historical data.
    Returns dict of return fields.
    """
    symbol       = str(ipo['nse_symbol'] or '').strip().upper()
    issue_price  = n(ipo['issue_price'])
    listing_date = ipo['listing_date']

    if not symbol or not issue_price or not listing_date:
        return {}

    # Convert listing_date to date object
    if isinstance(listing_date, str):
        listing_date = datetime.date.fromisoformat(listing_date[:10])

    # Fetch 400 days of data from listing date
    to_date   = min(listing_date + datetime.timedelta(days=400), datetime.date.today())
    from_date = listing_date

    if from_date >= datetime.date.today():
        return {}  # Future IPO

    # Get instrument token
    token = get_instrument_token(kite, symbol)
    if not token:
        log.debug(f"  No token for {symbol}")
        return {}

    # Fetch candles
    try:
        candles = kite.historical_data(
            instrument_token=token,
            from_date=from_date,
            to_date=to_date,
            interval="day",
        )
    except Exception as e:
        log.debug(f"  {symbol}: {e}")
        return {}

    if not candles:
        return {}

    data = {}

    # Sort by date
    candles = sorted(candles, key=lambda x: x['date'])

    # Listing day (first candle)
    c0 = candles[0]
    listing_open  = n(c0.get('open'))
    listing_close = n(c0.get('close'))
    listing_high  = n(c0.get('high'))
    listing_low   = n(c0.get('low'))

    if listing_open and issue_price:
        data['listing_open']       = listing_open
        data['listing_day_high']   = listing_high
        data['listing_day_low']    = listing_low
        data['listing_day_close']  = listing_close
        data['return_listing_open']= round((listing_open  / issue_price - 1) * 100, 2)
        data['return_day1_close']  = round((listing_close / issue_price - 1) * 100, 2)

        # UC/LC detection
        # Upper circuit = close very close to high AND gain > 15%
        if listing_high and listing_close:
            uc_threshold = listing_open * 1.19  # ~20% above open
            lc_threshold = listing_open * 0.81  # ~20% below open
            data['hit_uc_day1'] = bool(listing_close >= uc_threshold)
            data['hit_lc_day1'] = bool(listing_close <= lc_threshold)

    # Helper: get price N trading days after listing
    def price_at_day(n_days: int) -> float | None:
        if n_days >= len(candles):
            return candles[-1].get('close') if candles else None
        return candles[min(n_days, len(candles)-1)].get('close')

    # Compute returns at key intervals
    intervals = {
        'return_day7':   (5,   7),    # ~1 week = 5 trading days
        'return_day30':  (22,  30),   # ~1 month = 22 trading days
        'return_day90':  (63,  90),   # ~3 months
        'return_day180': (126, 180),  # ~6 months
        'return_day365': (252, 365),  # ~1 year
    }

    for col, (trading_days, _) in intervals.items():
        price = price_at_day(trading_days)
        if price and issue_price:
            data[col] = round((price / issue_price - 1) * 100, 2)

    # Max upside and drawdown in first 30 days
    first_30 = candles[:22] if len(candles) >= 22 else candles
    if first_30 and issue_price:
        highs  = [c.get('high', 0) for c in first_30]
        lows   = [c.get('low', 999999) for c in first_30]
        data['max_upside_30d']  = round((max(highs)  / issue_price - 1) * 100, 2)
        data['max_drawdown_30d']= round((min(lows)   / issue_price - 1) * 100, 2)

    return data

def ensure_columns(conn):
    cols = [
        ("listing_day_high","NUMERIC"), ("listing_day_low","NUMERIC"),
        ("listing_day_close","NUMERIC"), ("return_listing_open","NUMERIC"),
        ("return_day1_close","NUMERIC"), ("return_day7","NUMERIC"),
        ("return_day30","NUMERIC"), ("return_day90","NUMERIC"),
        ("return_day180","NUMERIC"), ("return_day365","NUMERIC"),
        ("max_upside_30d","NUMERIC"), ("max_drawdown_30d","NUMERIC"),
        ("hit_uc_day1","BOOLEAN"), ("hit_lc_day1","BOOLEAN"),
    ]
    cur = conn.cursor()
    for col, typ in cols:
        try:
            cur.execute(f"ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS {col} {typ}")
            conn.commit()
        except: conn.rollback()
    cur.close()

def save_returns(conn, ipo_id: int, data: dict):
    if not data: return
    cur = conn.cursor()
    cols = list(data.keys())
    vals = [data[c] for c in cols]
    set_clause = ', '.join([f"{c} = %s" for c in cols])
    cur.execute(f"UPDATE ipo_intelligence SET {set_clause} WHERE id = %s", vals + [ipo_id])
    conn.commit()
    cur.close()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--year",    type=int)
    p.add_argument("--symbol",  help="Filter by NSE symbol or company name")
    p.add_argument("--limit",   type=int, default=100)
    p.add_argument("--delay",   type=float, default=0.5, help="Delay between Kite API calls")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_db()
    ensure_columns(conn)

    ipos = get_ipos_needing_returns(args.year, args.limit, args.symbol)
    if not ipos:
        log.info("No IPOs need returns data. All up to date.")
        conn.close()
        return

    if args.dry_run:
        log.info("DRY RUN — would process:")
        for ipo in ipos[:10]:
            log.info(f"  {ipo['company_name'][:45]:45s} {ipo['nse_symbol']:15s} listed {ipo['listing_date']}")
        conn.close()
        return

    kite = get_kite()
    load_instruments(kite)  # Load once, reuse for all IPOs
    log.info(f"Processing {len(ipos)} IPOs")
    log.info("=" * 60)

    ok = 0; skipped = 0
    for i, ipo in enumerate(ipos):
        company = ipo['company_name']
        symbol  = str(ipo['nse_symbol'] or '').strip()
        log.info(f"  [{i+1}/{len(ipos)}] {company[:40]:40s} ({symbol})")

        try:
            data = compute_returns(kite, ipo)
            if data:
                save_returns(conn, ipo['id'], data)
                ret_open = data.get('return_listing_open', '?')
                ret_30   = data.get('return_day30', '?')
                ret_365  = data.get('return_day365', '?')
                uc       = "🔴UC" if data.get('hit_uc_day1') else ("🔵LC" if data.get('hit_lc_day1') else "")
                log.info(f"    ✓ Open:{ret_open}% | 30d:{ret_30}% | 1Y:{ret_365}% {uc}")
                ok += 1
            else:
                log.info(f"    ✗ No data (delisted or token not found)")
                skipped += 1
        except Exception as e:
            log.warning(f"    ✗ Error: {e}")
            skipped += 1

        time.sleep(args.delay)

    conn.close()
    log.info("=" * 60)
    log.info(f"Done. {ok} IPOs updated, {skipped} skipped")
    log.info("ML training data is now ready — run ipo_listing_probability_engine.py next")

if __name__ == "__main__":
    main()
