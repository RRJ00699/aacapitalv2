"""
Fix listing_day_close — Kite's historical data for listing day:
  candles[0]['open']  = listing open price  ✅ correct
  candles[0]['close'] = listing day close   ← this should be DIFFERENT from open
  
The issue: for many IPOs listing_day_close = listing_open
This means Kite returned open==close which happens when:
  1. Stock hit Upper Circuit immediately (close = UC price, open != close)
  2. Or we stored open in both fields by mistake

Fix: recompute from Kite using candle high/low/close properly
Also compute the CORRECT real return metrics.
"""
import os, sys, datetime, math, logging, time
import psycopg2, psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
API_KEY = os.environ.get("KITE_API_KEY", "br9m41pn8nvvywnl")

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def get_kite():
    from kiteconnect import KiteConnect
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT value FROM platform_config WHERE key = 'kite_access_token'")
    row = cur.fetchone()
    conn.close()
    if not row: raise Exception("No kite token")
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(row[0])
    return kite

_IMAP = {}
def get_token(kite, symbol):
    global _IMAP
    if not _IMAP:
        log.info("Loading instruments...")
        insts = kite.instruments("NSE")
        _IMAP = {i['tradingsymbol']: i['instrument_token'] for i in insts}
        log.info(f"  {len(_IMAP)} instruments loaded")
    return _IMAP.get(symbol.upper())

def n(v, d=None):
    try:
        if v is None: return d
        f = float(v)
        return d if math.isnan(f) else f
    except: return d

def main():
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get IPOs where open == close (bad data)
    cur.execute("""
        SELECT id, company_name, nse_symbol, issue_price, listing_date,
               listing_open, listing_day_close, listing_day_high, listing_day_low,
               return_listing_open, return_day1_close,
               return_day7, return_day30
        FROM ipo_intelligence
        WHERE nse_symbol IS NOT NULL
          AND nse_symbol != 'nan'
          AND listing_date IS NOT NULL
          AND listing_open > 0
          AND (
            listing_day_close IS NULL
            OR listing_day_close = 0
            OR (listing_open > 0 AND ABS(listing_day_close - listing_open) / listing_open < 0.001)
        )
          AND is_sme = FALSE
        ORDER BY listing_date DESC
        LIMIT 200
    """)
    ipos = [dict(r) for r in cur.fetchall()]
    cur.close()
    log.info(f"Found {len(ipos)} IPOs with missing/wrong listing_day_close")
    for ipo in ipos[:8]:
        co = ipo['company_name'][:35]
        sym = ipo.get('nse_symbol','?')
        lo = ipo['listing_open']
        lc = ipo['listing_day_close']
        log.info(f"  {co:35s} sym={sym:12s} open={lo} close={lc}")

    kite = get_kite()
    get_token(kite, "RELIANCE")  # preload

    ok = 0; skipped = 0
    for i, ipo in enumerate(ipos):
        symbol       = str(ipo['nse_symbol']).strip().upper()
        listing_date = ipo['listing_date']
        issue_price  = n(ipo['issue_price'])
        listing_open = n(ipo['listing_open'])

        if isinstance(listing_date, str):
            listing_date = datetime.date.fromisoformat(listing_date[:10])

        token = get_token(kite, symbol)
        if not token:
            log.info(f"  [{i+1}] {symbol}: no instrument token found")
            skipped += 1
            continue

        try:
            # Fetch listing day candle
            candles = kite.historical_data(
                instrument_token=token,
                from_date=listing_date,
                to_date=listing_date + datetime.timedelta(days=1),
                interval="day",
            )
            if not candles:
                skipped += 1
                continue

            c = candles[0]
            open_px  = n(c.get('open'))
            high_px  = n(c.get('high'))
            low_px   = n(c.get('low'))
            close_px = n(c.get('close'))
            volume   = c.get('volume')

            if not close_px or not issue_price:
                skipped += 1
                continue

            # Correct returns
            real_eod_return = round((close_px / open_px - 1) * 100, 2) if open_px else None
            real_d1_return  = round((close_px / issue_price - 1) * 100, 2)

            # UC/LC detection (proper)
            # UC = close is very close to high AND > 15% above open
            uc_day1 = bool(high_px and close_px and abs(close_px - high_px) < 0.5 and
                          (close_px / open_px - 1) > 0.15) if open_px else False
            lc_day1 = bool(low_px and close_px and abs(close_px - low_px) < 0.5 and
                          (close_px / open_px - 1) < -0.15) if open_px else False

            # Update DB
            cur2 = conn.cursor()
            cur2.execute("""
                UPDATE ipo_intelligence SET
                    listing_day_high   = %s,
                    listing_day_low    = %s,
                    listing_day_close  = %s,
                    listing_volume_val = %s,
                    return_day1_close  = %s,
                    hit_uc_day1        = %s,
                    hit_lc_day1        = %s
                WHERE id = %s
            """, (high_px, low_px, close_px, volume,
                  real_d1_return, uc_day1, lc_day1, ipo['id']))
            conn.commit()
            cur2.close()

            log.info(f"  [{i+1}/{len(ipos)}] {ipo['company_name'][:35]:35s} "
                     f"O:{open_px:.0f} H:{high_px:.0f} L:{low_px:.0f} C:{close_px:.0f} "
                     f"| EOD: {real_eod_return:+.1f}% "
                     f"{'🔴UC' if uc_day1 else '🔵LC' if lc_day1 else ''}")
            ok += 1

        except Exception as e:
            err = str(e)
            if 'api_key' in err or 'access_token' in err:
                log.error(f"  Kite token expired for {symbol} — run refresh_kite_token.py")
                break
            log.warning(f"  [{i+1}] {symbol}: {e}")
            skipped += 1

        time.sleep(0.3)

    conn.close()
    log.info("=" * 60)
    log.info(f"Fixed {ok} IPOs, skipped {skipped}")
    log.info("Now run: python real_return_analysis.py")

if __name__ == "__main__":
    main()
