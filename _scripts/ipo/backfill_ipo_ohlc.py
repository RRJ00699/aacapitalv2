#!/usr/bin/env python3
"""
backfill_ipo_ohlc.py — re-fetch CLEAN listing-day OHLC from Kite and overwrite the
corrupt/missing prices in ipo_intelligence, then compute the OPEN-based metrics the
revised thesis needs (you buy AT THE OPEN, not at issue price).

Why: diagnostic found ~18 rows clamped at ±20%, ~30 with impossible OHLC
(high<open or low>open), and ~136 missing the listing-day high. Those came from an
older non-Kite source. Kite daily candles are the clean truth.

For each listed IPO (has nse_symbol + listing_date, listed >7d ago) it:
  • fetches daily candles listing_date .. +90d from Kite
  • takes the FIRST candle = listing day; VALIDATES OHLC sanity
    (open>0, high>=max(open,close), low<=min(open,close), high>=low)
    — if a row fails, it is SKIPPED and logged, never written (no new garbage)
  • overwrites listing_open / listing_day_high / listing_day_low / listing_day_close
  • computes:  gain_open_close, gain_open_high  (the buyer-at-open day trade + ceiling)
               return_open_5d, return_open_20d  (open -> N-trading-day close = the HOLD)

Run:  python _scripts/refresh_kite_token.py        # make sure token is fresh first
      python _scripts/ipo/backfill_ipo_ohlc.py            # all eligible IPOs
      python _scripts/ipo/backfill_ipo_ohlc.py --symbol BAJAJHFL   # one
      python _scripts/ipo/backfill_ipo_ohlc.py --dry-run          # fetch+validate, no write
Env:  DATABASE_URL (or NEON_DATABASE_URL) ; KITE_API_KEY
"""
import os, sys, math, argparse, datetime, logging
import psycopg2, psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("ipo_ohlc")

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
API_KEY = os.environ.get("KITE_API_KEY")
if not URL:
    sys.exit("DATABASE_URL not set")


def n(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def get_kite():
    if not API_KEY:
        sys.exit("KITE_API_KEY not set")
    from kiteconnect import KiteConnect
    conn = psycopg2.connect(URL); cur = conn.cursor()
    cur.execute("SELECT value FROM platform_config WHERE key = 'kite_access_token'")
    row = cur.fetchone(); conn.close()
    if not row:
        sys.exit("No kite_access_token in DB. Run: python _scripts/refresh_kite_token.py")
    kite = KiteConnect(api_key=API_KEY); kite.set_access_token(row[0])
    return kite


_IMAP = None
def token_for(kite, symbol):
    global _IMAP
    if _IMAP is None:
        _IMAP = {i["tradingsymbol"]: i["instrument_token"] for i in kite.instruments("NSE")}
    s = symbol.upper().strip()
    for v in (s, s + "-BE", s + "-BL"):
        if v in _IMAP:
            return _IMAP[v]
    return None


def ohlc_is_sane(o, h, l, c):
    """Reject impossible candles so we never overwrite with new garbage."""
    if None in (o, h, l, c) or o <= 0:
        return False
    if h < max(o, c) - 1e-6:   # high must be >= open and close
        return False
    if l > min(o, c) + 1e-6:   # low must be <= open and close
        return False
    if h < l:
        return False
    # a real listing-day move clamped exactly at ±20% with no intraday range is suspect
    return True


def eligible(cur, symbol=None, limit=2000):
    q = """SELECT id, company_name, nse_symbol, issue_price, listing_date
           FROM ipo_intelligence
           WHERE nse_symbol IS NOT NULL AND nse_symbol NOT IN ('', 'nan')
             AND listing_date IS NOT NULL
             AND listing_date < CURRENT_DATE - INTERVAL '7 days'"""
    p = []
    if symbol:
        q += " AND (nse_symbol ILIKE %s OR company_name ILIKE %s)"; p += [f"%{symbol}%", f"%{symbol}%"]
    q += " ORDER BY listing_date DESC LIMIT %s"; p.append(limit)
    cur.execute(q, p)
    return cur.fetchall()


def ensure_columns(cur):
    for col, typ in [("gain_open_close", "NUMERIC"), ("gain_open_high", "NUMERIC"),
                     ("return_open_5d", "NUMERIC"), ("return_open_20d", "NUMERIC"),
                     ("ohlc_source", "TEXT")]:
        cur.execute(f"ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS {col} {typ}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol")
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    kite = get_kite()
    conn = psycopg2.connect(URL); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if not args.dry_run:
        ensure_columns(cur)
    ipos = eligible(cur, args.symbol, args.limit)
    log.info(f"{len(ipos)} eligible IPOs")

    fixed = skipped_bad = no_token = no_data = 0
    for ipo in ipos:
        sym = (ipo["nse_symbol"] or "").strip()
        ld = ipo["listing_date"]
        if isinstance(ld, str):
            ld = datetime.date.fromisoformat(ld[:10])
        tok = token_for(kite, sym)
        if not tok:
            no_token += 1; continue
        try:
            candles = kite.historical_data(tok, ld, min(ld + datetime.timedelta(days=90),
                                                        datetime.date.today()), "day")
        except Exception as e:
            log.debug(f"{sym}: {e}"); no_data += 1; continue
        if not candles:
            no_data += 1; continue
        candles = sorted(candles, key=lambda x: x["date"])
        c0 = candles[0]
        o, h, l, c = n(c0.get("open")), n(c0.get("high")), n(c0.get("low")), n(c0.get("close"))
        if not ohlc_is_sane(o, h, l, c):
            skipped_bad += 1
            log.info(f"  SKIP {sym}: bad OHLC o={o} h={h} l={l} c={c}")
            continue
        g_oc = round((c - o) / o * 100, 2)
        g_oh = round((h - o) / o * 100, 2)
        def close_after(days):
            idx = min(days, len(candles) - 1)
            return n(candles[idx].get("close"))
        c5, c20 = close_after(5), close_after(20)
        r5  = round((c5 - o) / o * 100, 2) if c5 else None
        r20 = round((c20 - o) / o * 100, 2) if c20 else None

        if args.dry_run:
            log.info(f"  {sym:14s} o={o:.1f} h={h:.1f} l={l:.1f} c={c:.1f}  "
                     f"o->c {g_oc:+.1f}%  o->hi {g_oh:+.1f}%  hold5 {r5}  hold20 {r20}")
            fixed += 1; continue

        cur.execute("""
            UPDATE ipo_intelligence SET
              listing_open=%s, listing_day_high=%s, listing_day_low=%s, listing_day_close=%s,
              gain_open_close=%s, gain_open_high=%s, return_open_5d=%s, return_open_20d=%s,
              ohlc_source='kite'
            WHERE id=%s
        """, (o, h, l, c, g_oc, g_oh, r5, r20, ipo["id"]))
        fixed += 1

    log.info(f"\nDONE  fixed={fixed}  skipped_bad_ohlc={skipped_bad}  "
             f"no_kite_token={no_token}  no_candles={no_data}")
    if no_token:
        log.info("no_kite_token = IPO symbol not in Kite's NSE list (renamed/delisted) — "
                 "leave as-is or map manually.")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
