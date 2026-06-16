"""
AACapital -- IPO Candle Backfill V2
Pulls Kite historical candles for all IPOs that have a symbol.
Fills: listing_gap_pct, return_day7, return_day30, return_day90, archetype.

Run: python _scripts/ipo_candle_backfill.py
"""

import os, time, logging
import psycopg2, psycopg2.extras
from datetime import date, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

DATABASE_URL      = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL", "")
KITE_API_KEY      = os.environ.get("KITE_API_KEY", "br9m41pn8nvvywnl")
KITE_ACCESS_TOKEN = os.environ.get("KITE_ACCESS_TOKEN", "")


def pct(price, base):
    try:
        if base and float(base) > 0 and price:
            return round((float(price) - float(base)) / float(base) * 100, 2)
    except Exception:
        pass
    return None


def main():
    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); return
    if not KITE_ACCESS_TOKEN:
        log.error("KITE_ACCESS_TOKEN not set — run: python _scripts/kite_login.py"); return

    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=KITE_API_KEY)
    kite.set_access_token(KITE_ACCESS_TOKEN)
    log.info("Kite connected")

    conn = psycopg2.connect(DATABASE_URL)
    log.info("Neon connected")

    # ── Load IPOs ──────────────────────────────────────────────────────────────
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, company_name, symbol, issue_price, listing_date::text
        FROM ipo_intelligence
        WHERE symbol IS NOT NULL
          AND issue_price IS NOT NULL
          AND issue_price > 0
        ORDER BY listing_date DESC NULLS LAST
    """)
    ipos = cur.fetchall()
    log.info(f"IPOs to process: {len(ipos)}")

    # ── Load instrument token map ──────────────────────────────────────────────
    # Use plain cursor (not RealDictCursor) to avoid KeyError on numeric index
    plain = conn.cursor()
    plain.execute("""
        SELECT tradingsymbol, instrument_token
        FROM instrument_master
        WHERE exchange = 'NSE'
    """)
    token_map = {row[0]: row[1] for row in plain.fetchall()}
    log.info(f"Instrument tokens loaded: {len(token_map)}")

    if not token_map:
        log.error("instrument_master is empty — run: python load_instrument_tokens.py first")
        conn.close()
        return

    today    = date.today().isoformat()
    updated  = skipped = errors = 0

    for ipo in ipos:
        company      = ipo["company_name"]
        symbol       = ipo["symbol"]
        issue_price  = float(ipo["issue_price"])
        listing_date = ipo.get("listing_date")

        token = token_map.get(symbol)
        if not token:
            log.warning(f"  No token: {symbol}")
            skipped += 1
            continue

        from_date = listing_date or (date.today() - timedelta(days=365 * 3)).isoformat()
        log.info(f"  {company} ({symbol}) from {from_date}")

        try:
            candles = kite.historical_data(
                token, from_date=from_date, to_date=today, interval="day"
            )
        except Exception as e:
            log.error(f"  Kite error: {e}")
            skipped += 1
            time.sleep(2)
            continue

        if not candles:
            log.warning(f"  No candles returned for {symbol}")
            skipped += 1
            time.sleep(0.5)
            continue

        closes = [float(c["close"]) for c in candles]
        highs  = [float(c["high"])  for c in candles]
        lows   = [float(c["low"])   for c in candles]

        def nth(n):
            return float(candles[n]["close"]) if len(candles) > n else None

        r_list = pct(nth(0),  issue_price)   # listing day close vs issue
        r_d7   = pct(nth(4),  issue_price)   # ~day 7
        r_d30  = pct(nth(20), issue_price)   # ~day 30
        r_d90  = pct(nth(62), issue_price)   # ~day 90
        r_cmp  = pct(closes[-1], issue_price) if closes else None

        max_up   = pct(max(highs[:21]), issue_price) if len(highs) >= 2 else None
        max_down = pct(min(lows[:21]),  issue_price) if len(lows)  >= 2 else None

        # Archetype from day-30 return (consistent with ipo_probability_engine)
        if r_d30 is not None:
            if   r_d30 >= 100: arch = "100+"
            elif r_d30 >= 50:  arch = "50-100"
            elif r_d30 >= 30:  arch = "30-50"
            elif r_d30 >= 10:  arch = "10-30"
            elif r_d30 >= 0:   arch = "0-10"
            else:               arch = "negative"
        else:
            arch = None

        try:
            ucur = conn.cursor()
            ucur.execute("""
                UPDATE ipo_intelligence SET
                    listing_gap_pct    = COALESCE(listing_gap_pct, %s),
                    return_day7        = %s,
                    return_day30       = %s,
                    return_day90       = %s,
                    return_cmp         = %s,
                    max_upside_pct     = %s,
                    max_drawdown_day30 = %s,
                    archetype          = COALESCE(NULLIF(archetype, 'UNKNOWN'), %s),
                    listing_date       = COALESCE(listing_date, %s),
                    updated_at         = NOW()
                WHERE id = %s
            """, [
                r_list, r_d7, r_d30, r_d90, r_cmp,
                max_up, max_down, arch,
                listing_date, ipo["id"],
            ])
            conn.commit()
            updated += 1
            log.info(f"    gap={r_list}%  d30={r_d30}%  d90={r_d90}%  [{arch}]  n={len(candles)}")
        except Exception as e:
            conn.rollback()
            log.error(f"    DB error: {e}")
            errors += 1

        time.sleep(0.35)  # Kite rate limit ~3 req/sec

    # ── Final report ───────────────────────────────────────────────────────────
    log.info(f"\nDone — updated={updated}  skipped={skipped}  errors={errors}")
    rcur = conn.cursor()
    rcur.execute("""
        SELECT COUNT(*), COUNT(listing_gap_pct), COUNT(return_day30),
               COUNT(return_day90), COUNT(archetype)
        FROM ipo_intelligence
    """)
    r = rcur.fetchone()
    log.info(f"Coverage — total={r[0]}  gap={r[1]}  d30={r[2]}  d90={r[3]}  archetype={r[4]}")
    conn.close()


if __name__ == "__main__":
    main()
