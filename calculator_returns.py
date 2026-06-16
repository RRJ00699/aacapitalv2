"""
AACapital — IPO Returns Calculator V1
Source: price_candles table (already in Neon from Kite)
Fills:  return_day1_close, return_day7, return_day30, return_day90,
        max_drawdown_day30, max_upside_pct, days_to_break_issue,
        achieved_10pct, archetype (winner bucket)

Run:  python _scripts/calculator_returns.py
"""

import os
import logging
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")
LOG_FILE = "_scripts/logs/returns_calc.log"
os.makedirs("_scripts/logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("returns_calc")


def pct_return(price, base):
    if base and base > 0 and price:
        return round((float(price) - float(base)) / float(base) * 100, 2)
    return None


def determine_archetype(r30):
    """Map 30-day return to archetype string matching your existing schema."""
    if r30 is None:
        return "UNKNOWN"
    if r30 < -10:
        return "LOSS"
    elif r30 < 0:
        return "FLAT"
    elif r30 < 10:
        return "FLAT"
    elif r30 < 20:
        return "10PCT"
    elif r30 < 50:
        return "20PCT"
    elif r30 < 100:
        return "50PCT"
    else:
        return "MULTIBAGGER"


def check_symbol_coverage(conn):
    """Show which IPOs have matching candles."""
    sql = """
        SELECT
            i.company_name,
            i.symbol,
            i.listing_date,
            i.issue_price,
            COUNT(pc.date) AS candle_count
        FROM ipo_intelligence i
        LEFT JOIN price_candles pc ON pc.symbol = i.symbol
        GROUP BY i.company_name, i.symbol, i.listing_date, i.issue_price
        HAVING i.symbol IS NOT NULL
        ORDER BY candle_count DESC, i.company_name
    """
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        has_candles = [r for r in rows if r["candle_count"] > 0]
        no_candles  = [r for r in rows if r["candle_count"] == 0]

        log.info(f"\n=== Symbol Coverage ===")
        log.info(f"  IPOs with symbol + candles : {len(has_candles)}")
        log.info(f"  IPOs with symbol, no candles: {len(no_candles)}")
        log.info(f"  IPOs with no symbol         : {len(rows) - len(has_candles) - len(no_candles)}")

        if no_candles:
            log.info("\n  Missing candle examples:")
            for r in no_candles[:8]:
                log.info(f"    {r['company_name']} → symbol={r['symbol']}")
        return has_candles
    except Exception as e:
        log.error(f"Coverage check failed: {e}")
        return []


def process_returns(conn):
    """Calculate and write returns for all IPOs that have candle data."""

    # Fetch IPOs needing return calculation
    sql = """
        SELECT
            i.id,
            i.company_name,
            i.symbol,
            i.issue_price,
            i.listing_date::text AS listing_date,
            i.listing_price

        FROM ipo_intelligence i
        WHERE i.symbol IS NOT NULL
          AND i.issue_price IS NOT NULL
          AND i.issue_price > 0
          AND i.listing_date IS NOT NULL
          AND (i.return_day30 IS NULL OR i.return_day1_close IS NULL)
        ORDER BY i.listing_date
    """

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            ipos = cur.fetchall()
    except Exception as e:
        log.error(f"Failed to fetch IPOs: {e}")
        return

    log.info(f"\nIPOs needing returns: {len(ipos)}")

    updated = 0
    skipped = 0

    for row in ipos:
        company      = row["company_name"]
        symbol       = row["symbol"]
        issue_price  = float(row["issue_price"])
        listing_date = row["listing_date"]

        log.info(f"  {company} ({symbol}) ₹{issue_price} listed {listing_date}")

        # Query candles for this symbol around listing date
        candle_sql = """
            SELECT date::text, open, high, low, close
            FROM price_candles
            WHERE symbol = %s
              AND date >= %s::date
            ORDER BY date ASC
            LIMIT 120
        """
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(candle_sql, [symbol, listing_date])
                candles = cur.fetchall()
        except Exception as e:
            log.error(f"    Candle fetch failed: {e}")
            skipped += 1
            continue

        if not candles:
            log.warning(f"    No candles found for {symbol} from {listing_date}")
            skipped += 1
            continue

        # Build index by trading day number (0 = listing day)
        day_closes = [float(c["close"]) for c in candles]
        day_highs  = [float(c["high"])  for c in candles]
        day_lows   = [float(c["low"])   for c in candles]

        def nth_close(n):
            """Get close on approximately nth calendar day."""
            # Map calendar days → trading day index roughly
            # listing_date is day 0; day 7 ≈ index 5; day 30 ≈ index 21; day 90 ≈ index 63
            mapping = {1: 0, 2: 1, 7: 4, 30: 20, 90: 62}
            idx = mapping.get(n, n)
            if idx < len(day_closes):
                return day_closes[idx]
            return None

        d0_close  = day_closes[0] if day_closes else None       # listing day
        d1_close  = day_closes[1] if len(day_closes) > 1 else None
        d7_close  = day_closes[4] if len(day_closes) > 4 else None
        d30_close = day_closes[20] if len(day_closes) > 20 else None
        d90_close = day_closes[62] if len(day_closes) > 62 else None

        # Use latest available if not enough days yet
        cmp_close = day_closes[-1] if day_closes else None

        # Listing gap: use existing or compute from d0 vs issue price
        listing_price = row.get("listing_price") or d0_close
        listing_gap   = pct_return(listing_price, issue_price)

        r_d1  = pct_return(d1_close,  issue_price)
        r_d7  = pct_return(d7_close,  issue_price)
        r_d30 = pct_return(d30_close, issue_price)
        r_d90 = pct_return(d90_close, issue_price)
        r_cmp = pct_return(cmp_close,  issue_price)

        # Max upside and drawdown in first 30 trading days
        first30_highs = day_highs[:21]
        first30_lows  = day_lows[:21]
        max_high   = max(first30_highs) if first30_highs else None
        min_low    = min(first30_lows)  if first30_lows  else None
        max_upside   = pct_return(max_high, issue_price)
        max_drawdown = pct_return(min_low,  issue_price)

        # Days until price broke below issue price
        days_to_break = None
        for idx, c in enumerate(day_closes):
            if c < issue_price:
                days_to_break = idx
                break
        if days_to_break is None:
            days_to_break = 999   # never broke

        achieved_10pct = bool(max_upside and max_upside >= 10)
        archetype = determine_archetype(r_d30)

        update_sql = """
            UPDATE ipo_intelligence SET
                return_listing_open = %s,
                return_day1_close   = %s,
                return_day7         = %s,
                return_day30        = %s,
                return_day90        = %s,
                return_cmp          = %s,
                max_upside_pct      = %s,
                max_drawdown_day30  = %s,
                listing_gap_pct     = COALESCE(listing_gap_pct, %s),
                days_to_break_issue = %s,
                achieved_10pct      = %s,
                archetype           = %s,
                updated_at          = NOW()
            WHERE id = %s
        """
        try:
            with conn.cursor() as cur:
                cur.execute(update_sql, [
                    listing_gap, r_d1, r_d7, r_d30, r_d90, r_cmp,
                    max_upside, max_drawdown, listing_gap,
                    days_to_break, achieved_10pct, archetype,
                    row["id"],
                ])
            conn.commit()
            updated += 1
            log.info(
                f"    ✓ listing={listing_gap}% d7={r_d7}% "
                f"d30={r_d30}% d90={r_d90}% [{archetype}]"
            )
        except Exception as e:
            conn.rollback()
            log.error(f"    ✗ Update failed: {e}")

    log.info(f"\n✓ Updated: {updated} | Skipped (no candles): {skipped}")


def main():
    log.info("=" * 60)
    log.info("AACapital — IPO Returns Calculator")
    log.info("=" * 60)

    if not DATABASE_URL:
        log.error("DATABASE_URL not set. Load .env.local first.")
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        log.info("✓ Connected to Neon")
    except Exception as e:
        log.error(f"Connection failed: {e}")
        return

    check_symbol_coverage(conn)
    process_returns(conn)
    conn.close()
    log.info("\n✓ Done")


if __name__ == "__main__":
    main()
