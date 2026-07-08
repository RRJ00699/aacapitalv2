"""
AACapital -- IPO Candle Backfill V2
Pulls Kite historical candles for all IPOs that have a symbol.
Fills: listing_gap_pct, return_day7, return_day30, return_day90, archetype.

Run: python _scripts/ipo_candle_backfill.py
"""

import os, sys, time, logging
import psycopg2, psycopg2.extras
from datetime import date, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

DATABASE_URL      = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL", "")
KITE_API_KEY      = os.environ["KITE_API_KEY"]
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
    token = KITE_ACCESS_TOKEN
    if not token:
        # Fallback: read the freshly-refreshed token from Neon platform_config
        # (refresh_kite_token.py writes it there; same source other scripts use).
        try:
            # NOTE: no local `import psycopg2` here — it shadowed the module-level
            # import as a function-local for ALL of main(), so any run where the
            # env token WAS set (this branch skipped) crashed at psycopg2.connect
            # later with UnboundLocalError. Module is imported at top; use that.
            conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
            cur.execute("SELECT value FROM platform_config WHERE key = 'kite_access_token'")
            row = cur.fetchone(); cur.close(); conn.close()
            if row and row[0] and str(row[0]).strip():
                token = str(row[0]).strip()
        except Exception as e:
            log.error(f"Neon token read failed: {e}")
    if not token:
        log.error("KITE_ACCESS_TOKEN not set and none in Neon — run refresh_kite_token.py"); return

    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=KITE_API_KEY)
    kite.set_access_token(token)
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
    # optional targeted mode: --symbols GLS,PARAS,... (or BACKFILL_SYMBOLS env)
    only = [s.strip().upper() for s in
            (os.environ.get("BACKFILL_SYMBOLS", "") or "").split(",") if s.strip()]
    for a in sys.argv[1:]:
        if a.startswith("--symbols="):
            only = [s.strip().upper() for s in a.split("=", 1)[1].split(",") if s.strip()]
    if only:
        ipos = [r for r in ipos if (r["symbol"] or "").upper() in only]
        log.info(f"Targeted mode: {len(ipos)} IPOs matching --symbols {','.join(only)}")
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
    candles_written = 0

    # only UPDATE master columns that actually exist (post-prune schema is 208
    # cols; return_day7/30/cmp etc. were dropped — writing them aborted every
    # row on 2026-07-08, updated=0). Checked once, applied per-row below.
    ccur = conn.cursor()
    ccur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    master_cols = {r[0] for r in ccur.fetchall()}
    ccur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='price_candles'")
    has_volume = "volume" in {r[0] for r in ccur.fetchall()}
    ccur.close()

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
        # cap the window at listing+70d: matches the purge policy (pre-lock
        # window is all we keep), and stays under Kite's 2000-day request
        # limit that killed every pre-2021 fetch on 2026-07-08.
        d0 = date.fromisoformat(str(from_date)[:10])
        to_date = min(date.today(), d0 + timedelta(days=70)).isoformat()
        log.info(f"  {company} ({symbol}) {from_date} -> {to_date}")

        try:
            candles = kite.historical_data(
                token, from_date=from_date, to_date=to_date, interval="day"
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
            # 1) the actual candles -> price_candles (this was MISSING: the
            # script's docstring promised candles but never wrote them; the
            # nightly derives listing fields/d10/cir/levels from this table)
            rows = [(symbol, c["date"].date() if hasattr(c["date"], "date") else str(c["date"])[:10],
                     c["open"], c["high"], c["low"], c["close"], c.get("volume"))
                    for c in candles]
            if has_volume:
                psycopg2.extras.execute_values(ucur, """
                    INSERT INTO price_candles (symbol, date, open, high, low, close, volume)
                    VALUES %s
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                        close=EXCLUDED.close, volume=EXCLUDED.volume""", rows)
            else:
                psycopg2.extras.execute_values(ucur, """
                    INSERT INTO price_candles (symbol, date, open, high, low, close)
                    VALUES %s
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                        close=EXCLUDED.close""", [r[:6] for r in rows])
            candles_written += len(rows)

            # 2) master fields — only the columns that survived the prune
            sets, vals = [], []
            for col, val, fill_empty in [
                ("return_day90",       r_d90,  False),
                ("return_cmp",         r_cmp,  False),
                ("max_upside_pct",     max_up, False),
                ("max_drawdown_day30", max_down, False),
                ("archetype",          arch,   False),
                ("listing_date",       listing_date, True),
            ]:
                if col in master_cols:
                    sets.append(f"{col} = COALESCE({col}, %s)" if fill_empty else f"{col} = %s")
                    vals.append(val)
            if "updated_at" in master_cols:
                sets.append("updated_at = NOW()")
            if sets:
                ucur.execute(f"UPDATE ipo_intelligence SET {', '.join(sets)} WHERE id = %s",
                             vals + [ipo["id"]])
            conn.commit()
            updated += 1
            log.info(f"    candles={len(rows)}  d90={r_d90}%  [{arch}]")
        except Exception as e:
            conn.rollback()
            log.error(f"    DB error: {e}")
            errors += 1

        time.sleep(0.35)  # Kite rate limit ~3 req/sec

    # ── Final report ───────────────────────────────────────────────────────────
    log.info(f"\nDone — updated={updated}  candles_written={candles_written}  "
             f"skipped={skipped}  errors={errors}")
    rcur = conn.cursor()
    count_cols = [c for c in ("listing_gap_pct", "return_day90", "archetype") if c in master_cols]
    rcur.execute(f"SELECT COUNT(*){''.join(f', COUNT({c})' for c in count_cols)} FROM ipo_intelligence")
    r = rcur.fetchone()
    log.info("Coverage — total=%s  %s" % (r[0], "  ".join(f"{c}={v}" for c, v in zip(count_cols, r[1:]))))
    conn.close()


if __name__ == "__main__":
    main()
