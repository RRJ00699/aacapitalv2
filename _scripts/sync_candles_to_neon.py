"""
_scripts/sync_candles_to_neon.py
==================================
Syncs price_candles from local Postgres → Neon for top N stocks.
Enables Vercel price charts without needing local DB access.

Usage:
  python _scripts/sync_candles_to_neon.py --top 200 --days 365
  python _scripts/sync_candles_to_neon.py --symbols ARVIND INFY TCS --days 730

Schedule: Daily via GitHub Actions after kite-sync-candles.py runs locally
"""

import os, sys, logging, argparse, datetime
import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

LOCAL_URL = os.environ.get("LOCAL_DATABASE_URL") or \
            os.environ.get("CANDLES_DATABASE_URL") or \
            "postgresql://postgres:Ashrith%402820@localhost:5432/aacapital?sslmode=disable"
NEON_URL  = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")


def get_top_symbols(local_conn, n: int) -> list[str]:
    """Get top N symbols by market cap from local stock_fundamentals."""
    cur = local_conn.cursor()
    try:
        cur.execute("""
            SELECT nse_symbol FROM stock_fundamentals
            WHERE nse_symbol IS NOT NULL
            ORDER BY market_cap DESC NULLS LAST
            LIMIT %s
        """, (n,))
        syms = [r[0] for r in cur.fetchall()]
        log.info(f"Top {n} symbols by market cap: {syms[:5]}…")
        return syms
    except Exception as e:
        log.warning(f"Could not get from stock_fundamentals: {e}")
        # Fallback: get distinct symbols from price_candles
        cur.execute("""
            SELECT DISTINCT tradingsymbol FROM price_candles
            ORDER BY tradingsymbol LIMIT %s
        """, (n,))
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()


def ensure_neon_table(neon_conn):
    cur = neon_conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_candles (
            id              SERIAL PRIMARY KEY,
            tradingsymbol   VARCHAR(20) NOT NULL,
            date            DATE NOT NULL,
            open            NUMERIC(12,2),
            high            NUMERIC(12,2),
            low             NUMERIC(12,2),
            close           NUMERIC(12,2),
            volume          BIGINT,
            interval        VARCHAR(10) DEFAULT 'day',
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (tradingsymbol, date, interval)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pc_sym_date ON price_candles (tradingsymbol, date DESC)")
    neon_conn.commit()
    cur.close()


def sync_symbol(local_conn, neon_conn, symbol: str, days: int) -> int:
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    local_cur = local_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    local_cur.execute("""
        SELECT tradingsymbol, date, open, high, low, close, volume
        FROM price_candles
        WHERE tradingsymbol = %s AND date >= %s
        ORDER BY date ASC
    """, (symbol, cutoff))
    rows = local_cur.fetchall()
    local_cur.close()

    if not rows:
        return 0

    neon_cur = neon_conn.cursor()
    psycopg2.extras.execute_values(neon_cur, """
        INSERT INTO price_candles (tradingsymbol, date, open, high, low, close, volume, interval)
        VALUES %s
        ON CONFLICT (tradingsymbol, date, interval) DO UPDATE SET
            open   = EXCLUDED.open,
            high   = EXCLUDED.high,
            low    = EXCLUDED.low,
            close  = EXCLUDED.close,
            volume = EXCLUDED.volume
    """, [(r['tradingsymbol'], r['date'], r['open'], r['high'], r['low'], r['close'], r['volume'], 'day')
           for r in rows])
    neon_conn.commit()
    neon_cur.close()
    return len(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--top",     type=int, default=200, help="Sync top N stocks by market cap")
    p.add_argument("--symbols", nargs="+",             help="Specific symbols")
    p.add_argument("--days",    type=int, default=365, help="Days of history to sync")
    args = p.parse_args()

    if not NEON_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    log.info(f"Candle Sync: Local → Neon (top {args.top} stocks, {args.days} days)")
    log.info("=" * 60)

    try:
        local = psycopg2.connect(LOCAL_URL, connect_timeout=5)
        log.info("Local Postgres: connected")
    except Exception as e:
        log.error(f"Cannot connect to local Postgres: {e}")
        sys.exit(1)

    neon = psycopg2.connect(NEON_URL, connect_timeout=10)
    log.info("Neon: connected")
    ensure_neon_table(neon)

    symbols = args.symbols if args.symbols else get_top_symbols(local, args.top)
    total_rows = 0

    for i, sym in enumerate(symbols):
        rows = sync_symbol(local, neon, sym, args.days)
        if rows > 0:
            log.info(f"  [{i+1}/{len(symbols)}] {sym}: {rows} rows synced")
        total_rows += rows

    local.close()
    neon.close()

    log.info("=" * 60)
    log.info(f"Done. {total_rows:,} total rows synced for {len(symbols)} stocks.")

if __name__ == "__main__":
    main()
