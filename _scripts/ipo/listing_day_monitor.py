"""
_scripts/ipo/listing_day_monitor.py
=====================================
Runs on IPO listing mornings. Reads Kite API every 5 min.
At 10:15 AM computes Float Turnover Ratio → BUY / WAIT_VWAP / EXIT signal.

Schedule: Run manually or via Windows Task Scheduler on listing days.
  Start: 9:00 AM IST
  End:   10:35 AM IST (auto-stops after final signal)

Usage:
  python _scripts/ipo/listing_day_monitor.py --symbol NSDL
  python _scripts/ipo/listing_day_monitor.py --symbol NSDL --paper  # dry-run, no DB writes

What it writes to Neon:
  - ipo_intelligence: float_turnover_ratio, listing_open, listing_day_vwap, 
                      listing_vs_gmp_pct, final play_recommendation update
  - ipo_live_feed: timestamped signal every 5 min

Environment:
  DATABASE_URL or NEON_DATABASE_URL  → Neon connection
  KITE_API_KEY                       → from .env.local (default: br9m41pn8nvvywnl)
"""

import os, sys, time, math, json, logging, argparse, datetime
import psycopg2, psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
KITE_API_KEY = os.environ.get("KITE_API_KEY") or "br9m41pn8nvvywnl"

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_db():
    from urllib.parse import urlparse, unquote
    p = urlparse(DATABASE_URL)
    return psycopg2.connect(
        host=p.hostname, port=p.port or 5432,
        dbname=p.path.lstrip("/"),
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
    )

def n(v, default=0.0):
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)): return default
        return float(v)
    except: return default

def get_kite_token(conn) -> str | None:
    with conn.cursor() as c:
        c.execute("SELECT value FROM platform_config WHERE key='kite_access_token' LIMIT 1")
        row = c.fetchone()
        return row[0] if row else None

def kite_quote(token: str, symbol: str) -> dict:
    """Fetch live quote from Kite API."""
    import urllib.request
    url = f"https://api.kite.trade/quote?i=NSE:{symbol}"
    req = urllib.request.Request(url, headers={
        "X-Kite-Version": "3",
        "Authorization": f"token {KITE_API_KEY}:{token}"
    })
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read())
    return data.get("data", {}).get(f"NSE:{symbol}", {})

def compute_signal(
    current_price: float,
    open_price: float,
    vwap: float,
    volume: int,
    issue_price: float,
    gmp_t1: float,
    qib_x: float,
    anchor_t1: int,
    issue_size_cr: float,
    total_shares: int,
    retail_pct: float,
    hni_pct: float,
    qib_pct: float,
    volume_9_to_now: int,
    now: datetime.datetime,
) -> dict:
    """
    Compute trading signal based on real-time data.
    From IPO DNA Architecture doc — Step 4: Listing Day Signals.
    """
    ist_hour = now.hour
    ist_min  = now.minute

    # Float Turnover Ratio (FTR)
    day1_float = int(
        total_shares * (retail_pct / 100) +
        total_shares * (hni_pct   / 100) +
        total_shares * (qib_pct   / 100) * 0.5  # 50% of QIB unlocked Day 1
    )
    ftr = volume_9_to_now / max(day1_float, 1)

    # Price vs issue / GMP
    price_vs_issue = (current_price / issue_price - 1) * 100 if issue_price > 0 else 0
    gmp_price      = issue_price * (1 + gmp_t1 / 100) if gmp_t1 else issue_price
    price_vs_gmp   = (current_price - gmp_price) / issue_price * 100 if issue_price > 0 else 0
    price_vs_vwap  = (current_price / vwap - 1) * 100 if vwap > 0 else 0

    # Circuit thresholds
    uc_threshold = open_price * 1.05
    lc_threshold = open_price * 0.95

    # ── Signal logic (from IPO DNA Architecture) ────────────────────────
    if current_price <= lc_threshold * 1.005:
        signal = "EXIT"
        reason = f"Hit lower circuit (₹{lc_threshold:.0f}) — avg -19% next 7 days. Exit immediately."
        color  = "red"

    elif price_vs_gmp > 15 and qib_x < 30:
        signal = "AVOID_ENTRY"
        reason = "Listed 15%+ above GMP + weak QIB — euphoria trap, wait for pullback"
        color  = "amber"

    elif ftr > 0.8 and current_price >= open_price and ist_hour >= 10 and ist_min >= 10:
        signal = "BUY_NOW"
        reason = (f"FTR {ftr:.2f} > 0.8 — weak hands absorbed. "
                  f"Above open ₹{open_price:.0f}. Institutional accumulation confirmed. "
                  f"Enter 10:15–10:25 AM. Stop: -4%.")
        color  = "green"

    elif price_vs_gmp < -5 and anchor_t1 >= 10 and ist_hour >= 10:
        signal = "BUY_PANIC_DIP"
        reason = (f"Listed {abs(price_vs_gmp):.1f}% below GMP. "
                  f"{anchor_t1} tier-1 anchors = institutional floor. Buy now. Stop: -6%.")
        color  = "blue"

    elif current_price >= uc_threshold * 0.99:
        signal = "HOLD"
        reason = f"Hitting upper circuit (₹{uc_threshold:.0f}) — momentum strong. avg +26% next 7 days. Hold."
        color  = "green"

    elif ftr > 0.6 and price_vs_vwap > 1 and ist_hour >= 10:
        signal = "HOLD"
        reason = (f"Above VWAP by {price_vs_vwap:.1f}%. FTR {ftr:.2f}. "
                  f"QIB {qib_x:.0f}x. Hold with trailing stop at VWAP.")
        color  = "green"

    elif ftr < 0.3 or (ist_hour < 10 or (ist_hour == 9 and ist_min < 30)):
        signal = "WATCH"
        reason = f"FTR {ftr:.2f} — early data, wait. Check again at 10:15 AM."
        color  = "amber"

    elif price_vs_vwap < -2:
        signal = "EXIT"
        reason = "Price below VWAP — distribution. Exit by EOD."
        color  = "red"

    else:
        signal = "WAIT_VWAP"
        reason = (f"FTR {ftr:.2f}. Price {price_vs_vwap:+.1f}% vs VWAP. "
                  "Wait for clear VWAP crossover + 1.5x volume.")
        color  = "amber"

    return {
        "signal":        signal,
        "reason":        reason,
        "color":         color,
        "current_price": current_price,
        "open_price":    open_price,
        "vwap":          vwap,
        "ftr":           round(ftr, 3),
        "price_vs_vwap": round(price_vs_vwap, 2),
        "price_vs_gmp":  round(price_vs_gmp, 2),
        "price_vs_issue":round(price_vs_issue, 2),
        "volume":        volume,
        "day1_float":    day1_float,
        "timestamp":     now.isoformat(),
    }

def ensure_live_feed_table(conn):
    with conn.cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS ipo_live_feed (
                id              SERIAL PRIMARY KEY,
                symbol          TEXT NOT NULL,
                company_name    TEXT,
                signal          TEXT,
                reason          TEXT,
                current_price   NUMERIC,
                open_price      NUMERIC,
                vwap            NUMERIC,
                ftr             NUMERIC,
                price_vs_vwap   NUMERIC,
                price_vs_gmp    NUMERIC,
                volume          BIGINT,
                recorded_at     TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        conn.commit()

def run_monitor(symbol: str, paper: bool = False):
    """Main monitoring loop for one symbol."""
    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_db()
    ensure_live_feed_table(conn)

    # Fetch IPO data from ipo_intelligence
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
        c.execute("""
            SELECT company_name, issue_price, issue_size_cr,
                   gmp_pct_t1, gmp_day_before_pct,
                   qib_subscription_x, rii_subscription_x, nii_subscription_x,
                   anchor_tier1_count, listing_date,
                   fresh_issue_ratio, ofs_pct
            FROM ipo_intelligence
            WHERE symbol ILIKE %s OR company_name ILIKE %s
            LIMIT 1
        """, (symbol, f"%{symbol}%"))
        ipo = c.fetchone()

    if not ipo:
        log.error(f"IPO not found: {symbol}")
        sys.exit(1)

    company      = ipo["company_name"]
    issue_price  = n(ipo["issue_price"])
    issue_size   = n(ipo["issue_size_cr"])
    gmp_t1       = n(ipo.get("gmp_pct_t1") or ipo.get("gmp_day_before_pct"))
    qib_x        = n(ipo["qib_subscription_x"])
    anchor_t1    = int(n(ipo["anchor_tier1_count"]))
    fresh_pct    = n(ipo.get("fresh_issue_ratio", 0.5)) * 100
    ofs_pct      = n(ipo.get("ofs_pct", 0))

    total_shares = int(issue_size * 1e7 / issue_price) if issue_price > 0 else 0
    retail_pct   = 35.0
    hni_pct      = 15.0
    qib_pct      = 50.0

    log.info("=" * 60)
    log.info(f"  📊 IPO LISTING MONITOR — {company} ({symbol})")
    log.info(f"  Issue Price: ₹{issue_price:.0f} | GMP T-1: {gmp_t1:+.1f}%")
    log.info(f"  QIB: {qib_x:.1f}x | Anchor Tier-1: {anchor_t1}")
    log.info(f"  {'PAPER TRADING — no DB writes' if paper else 'LIVE MODE — writing to Neon'}")
    log.info("=" * 60)

    token = get_kite_token(conn)
    if not token:
        log.error("Kite access token not found in platform_config. Run refresh_kite_token.py first.")
        sys.exit(1)

    # Market hours: 9:00 AM to 10:35 AM IST
    MARKET_OPEN  = datetime.time(9, 0)
    STOP_AT      = datetime.time(10, 35)
    POLL_SECS    = 300  # every 5 minutes

    volume_at_open = 0
    open_price     = 0.0
    final_signal   = None

    while True:
        now_ist = datetime.datetime.now(IST)
        t       = now_ist.time()

        if t < MARKET_OPEN:
            wait = (datetime.datetime.combine(now_ist.date(), MARKET_OPEN, tzinfo=IST) - now_ist).seconds
            log.info(f"Market opens in {wait//60}m {wait%60}s")
            time.sleep(min(wait, 60))
            continue

        if t > STOP_AT:
            log.info(f"Monitoring complete at {now_ist.strftime('%H:%M IST')}")
            break

        try:
            quote = kite_quote(token, symbol.upper())
        except Exception as e:
            log.warning(f"Kite quote error: {e} — retry in 60s")
            time.sleep(60)
            continue

        current_price = n(quote.get("last_price"))
        ohlc          = quote.get("ohlc", {})
        op            = n(ohlc.get("open"))
        volume        = int(n(quote.get("volume", 0)))
        vwap          = n(quote.get("average_price") or current_price)

        if op > 0 and open_price == 0:
            open_price     = op
            volume_at_open = volume
            log.info(f"  OPEN: ₹{open_price:.0f}  (GMP implied: ₹{issue_price*(1+gmp_t1/100):.0f})")

        if open_price == 0:
            log.info(f"  {now_ist.strftime('%H:%M')} | Waiting for open price...")
            time.sleep(30)
            continue

        volume_since_open = volume - volume_at_open

        sig = compute_signal(
            current_price, open_price, vwap, volume, issue_price, gmp_t1,
            qib_x, anchor_t1, issue_size, total_shares, retail_pct, hni_pct, qib_pct,
            volume_since_open, now_ist
        )

        icon = "🟢" if sig["color"]=="green" else "🔴" if sig["color"]=="red" else "🟡"
        log.info(
            f"  {now_ist.strftime('%H:%M')} | ₹{current_price:.2f} | "
            f"VWAP ₹{vwap:.2f} ({sig['price_vs_vwap']:+.1f}%) | "
            f"FTR {sig['ftr']:.2f} | {icon} {sig['signal']}"
        )
        log.info(f"    → {sig['reason']}")

        final_signal = sig

        if not paper:
            with conn.cursor() as c:
                c.execute("""
                    INSERT INTO ipo_live_feed
                    (symbol, company_name, signal, reason, current_price,
                     open_price, vwap, ftr, price_vs_vwap, price_vs_gmp, volume)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (symbol.upper(), company, sig["signal"], sig["reason"],
                      sig["current_price"], sig["open_price"], sig["vwap"],
                      sig["ftr"], sig["price_vs_vwap"], sig["price_vs_gmp"], volume))
                conn.commit()

        # If we have a clear BUY/EXIT signal after 10:15 AM, write final recommendation
        if t >= datetime.time(10, 15) and sig["signal"] in ("BUY_NOW","BUY_PANIC_DIP","EXIT") and not paper:
            # Update ipo_intelligence with listing day data
            with conn.cursor() as c:
                c.execute("""
                    UPDATE ipo_intelligence SET
                        listing_open         = %s,
                        listing_day_vwap     = %s,
                        listing_volume_val   = %s,
                        float_turnover_ratio = %s,
                        listing_vs_gmp_pct   = %s,
                        play_recommendation  = %s,
                        play_confidence      = %s,
                        play_reasons         = %s,
                        play_updated_at      = NOW()
                    WHERE symbol ILIKE %s
                """, (open_price, vwap, volume, sig["ftr"], sig["price_vs_gmp"],
                      sig["signal"], 85, json.dumps([sig["reason"]]), symbol.upper()))
                conn.commit()
            log.info(f"\n  ✅ FINAL SIGNAL: {sig['signal']} written to ipo_intelligence")

        time.sleep(POLL_SECS)

    if final_signal:
        log.info("\n" + "="*60)
        log.info(f"  FINAL: {final_signal['signal']}")
        log.info(f"  {final_signal['reason']}")
        log.info(f"  Price: ₹{final_signal['current_price']:.2f}")
        log.info(f"  FTR:   {final_signal['ftr']:.2f}")

    conn.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True, help="NSE symbol (e.g. NSDL)")
    ap.add_argument("--paper",  action="store_true", help="Paper mode — no DB writes")
    args = ap.parse_args()
    run_monitor(args.symbol, args.paper)

if __name__ == "__main__":
    main()
