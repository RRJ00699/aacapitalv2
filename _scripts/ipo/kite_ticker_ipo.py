#!/usr/bin/env python3
"""
kite_ticker_ipo.py  —  AACapital live tick pipeline for the IPO Recovery Engine.

Streams tick-by-tick data from Kite's websocket (KiteTicker, MODE_FULL) for one or more
listed IPOs and derives, in real time:
  • VWAP anchor      = tick['average_traded_price']  (Kite's own day VWAP = institutional cost basis)
  • VWAP distance    = (ltp / vwap - 1) * 100
  • OBIR             = buy_qty / (buy_qty + sell_qty)  over the 5 depth levels the API exposes
  • Momentum state   = price vs VWAP + short LTP trend + OBIR
  • Divergence flag  = price ticking up while OBIR < 0.5 OR ltp < vwap  → "unbacked / distribution"

HONEST LIMITS:
  • The websocket exposes 5 depth levels, not 20. "View 20 Depth" is a Kite UI-only feature;
    the API tick carries 5 levels, so OBIR here is a 5-level proxy, not the full iceberg picture.
  • OBIR/VWAP show pressure and cost-basis — they are PROXIES for institutional activity, not a
    direct read of who is buying. Treat as research signal, not confirmation.

AUTH: api_key from KITE_API_KEY env; access_token from platform_config('kite_access_token')
(set by refresh_kite_token.py) or KITE_ACCESS_TOKEN env. Run refresh_kite_token.py first if stale.

Usage:
  python _scripts/ipo/kite_ticker_ipo.py --symbols TURTLEMINT
  python _scripts/ipo/kite_ticker_ipo.py --symbols TURTLEMINT,HEXAGON --write-db --interval 5
"""
import os, sys, time, argparse, logging
from collections import deque, defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("ipo-ticker")

API_KEY = os.environ.get("KITE_API_KEY", "br9m41pn8nvvywnl")


def db_conn():
    url = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        return None
    try:
        import psycopg2
        return psycopg2.connect(url)
    except ImportError:
        try:
            import psycopg
            return psycopg.connect(url)
        except ImportError:
            return None


def load_access_token():
    # platform_config (written fresh every morning by refresh_kite_token.py) is the source of
    # truth. Read it FIRST so a stale KITE_ACCESS_TOKEN env var can't shadow today's token.
    conn = db_conn()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM platform_config WHERE key = 'kite_access_token'")
        row = cur.fetchone(); conn.close()
        if row and row[0]:
            return row[0]
    # fallback only when there's no DB / no row
    tok = os.environ.get("KITE_ACCESS_TOKEN")
    if tok:
        return tok
    sys.exit("No kite_access_token in platform_config and no KITE_ACCESS_TOKEN env. "
             "Run refresh_kite_token.py first.")


def ensure_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ipo_tick_feed (
            id           BIGSERIAL PRIMARY KEY,
            symbol       TEXT NOT NULL,
            ltp          NUMERIC,
            vwap         NUMERIC,
            vwap_dist    NUMERIC,
            obir         NUMERIC,
            day_volume   BIGINT,
            momentum     TEXT,
            divergence   BOOLEAN,
            signal       TEXT,
            recorded_at  TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.commit()


def resolve_auto_today_symbols(conn):
    """
    Pick the IPOs to capture today, straight from ipo_intelligence (NSE-scrape-fed).
    Rules (locked with owner):
      - mainboard only            -> COALESCE(is_sme,false) = false
      - total issue SIZE >= 200cr -> issue_size_cr >= 200   (skip junk/operator-driven small issues)
      - active window             -> listing_date <= today(IST) <= anchor first lock-in (anchor_lock30_date)
      - max 6 names
    Returns a list of NSE symbols (upper-cased).
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT symbol, company_name, issue_size_cr, listing_date, anchor_lock30_date
        FROM ipo_intelligence
        WHERE COALESCE(is_sme, false) = false
          -- mainboard, total issue SIZE >= Rs200cr (skip junk/operator small issues); upper bound drops malformed sizes
          AND issue_size_cr >= 200 AND issue_size_cr < 100000
          AND symbol IS NOT NULL AND btrim(symbol) <> ''
          AND listing_date IS NOT NULL
          AND (NOW() AT TIME ZONE 'Asia/Kolkata')::date >= listing_date
          -- capture runs to the ANCHOR FIRST LOCK-IN, not a guessed listing+30d
          AND (NOW() AT TIME ZONE 'Asia/Kolkata')::date
              <= COALESCE(anchor_lock30_date, (listing_date + INTERVAL '30 days')::date)
        ORDER BY listing_date DESC
        LIMIT 6
    """)
    rows = cur.fetchall(); cur.close()
    out = []
    for sym, name, size, ld, lock in rows:
        out.append(sym.strip().upper())
        log.info(f"  auto-today: {sym} ({name}) size Rs{size}cr listed {ld} lock {lock}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="", help="comma-separated NSE symbols, e.g. TURTLEMINT,HEXAGON")
    ap.add_argument("--auto-today", action="store_true",
                    help="auto-pick mainboard IPOs (issue size >=Rs200cr) inside their anchor lock-in window")
    ap.add_argument("--exchange", default="NSE")
    ap.add_argument("--write-db", action="store_true", help="persist throttled snapshots to ipo_tick_feed")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between DB snapshots per symbol")
    ap.add_argument("--trend-ticks", type=int, default=8, help="LTP window for the short trend")
    args = ap.parse_args()

    # Decide WHAT to capture before touching Kite, so a no-listing day exits in ~1s.
    if args.auto_today:
        c0 = db_conn()
        if not c0:
            sys.exit("--auto-today needs DATABASE_URL to read ipo_intelligence.")
        symbols = resolve_auto_today_symbols(c0); c0.close()
        if not symbols:
            log.info("auto-today: no mainboard IPO (>=Rs200) inside its listing->+30d window today. "
                     "Nothing to capture — exiting clean.")
            return
    else:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if not symbols:
            sys.exit("Provide --symbols TURTLEMINT[,HEX] or --auto-today.")

    try:
        from kiteconnect import KiteConnect, KiteTicker
    except ImportError:
        sys.exit("pip install kiteconnect")

    access_token = load_access_token()
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(access_token)

    # pre-flight: is the token actually valid? (separates 'bad token' from 'bad symbol')
    try:
        prof = kite.profile()
        log.info(f"token OK — logged in as {prof.get('user_name') or prof.get('user_id')}")
    except Exception as e:
        sys.exit(f"TOKEN INVALID ({e}). Kite tokens expire every morning — run "
                 f"`python _scripts/refresh_kite_token.py` today, and make sure KITE_API_KEY "
                 f"matches the app that minted the token (currently {API_KEY}).")

    # symbols already resolved above (from --auto-today or --symbols)
    # resolve symbol -> instrument_token via ltp (also verifies the token works)
    token_to_sym, sym_to_token = {}, {}
    for sym in symbols:
        key = f"{args.exchange}:{sym}"
        try:
            info = kite.ltp([key])[key]
            it = info["instrument_token"]
            token_to_sym[it] = sym
            sym_to_token[sym] = it
            log.info(f"  resolved {sym} -> token {it}  (ltp {info.get('last_price')})")
        except Exception as e:
            log.warning(f"  could not resolve {sym}: {e}  (delisted? token stale? wrong symbol?)")
    if not token_to_sym:
        sys.exit("No symbols resolved — fix the token (refresh_kite_token.py) or the symbols.")

    conn = db_conn() if args.write_db else None
    if conn:
        ensure_table(conn)

    state = defaultdict(lambda: {"ltps": deque(maxlen=args.trend_ticks), "last_db": 0.0,
                                 "last_sig": None, "obir_hist": deque(maxlen=5), "smooth": None,
                                 "regime": "BALANCED", "flip_px": None, "flip_t": 0.0,
                                 "armed_reversal": False})

    # OBIR regime thresholds (displayed-depth). Smoothed by rolling MEDIAN of last ticks —
    # responsive to a real sustained flip, immune to a single spoofed tick.
    BID_HEAVY, ASK_HEAVY = 0.62, 0.38       # ~1.6:1 ; tighten to 0.70/0.30 for stricter 3:1

    def regime_of(m):
        if m is None: return "BALANCED"
        return "BID_HEAVY" if m >= BID_HEAVY else "ASK_HEAVY" if m <= ASK_HEAVY else "BALANCED"

    def detect_flip_reversal(st, obir, ltp, vwap, now):
        """Emit an event when the displayed book flips heavy↔heavy, or a post-flip dip reverses."""
        if obir is None:
            return None
        import statistics as _st
        st["obir_hist"].append(obir)
        med = _st.median(st["obir_hist"])
        st["smooth"] = med
        new, old = regime_of(med), st["regime"]
        event = None
        if new != old and {old, new} == {"BID_HEAVY", "ASK_HEAVY"}:
            arrow = "bids→asks (support pulled, sellers stacking)" if new == "ASK_HEAVY" \
                    else "asks→bids (sellers exhausted, buyers stepping in)"
            event = f"⚡ IMBALANCE FLIP {old}→{new}  [{arrow}]  OBIR~{med:.2f}  @{ltp}"
            st["flip_px"], st["flip_t"] = ltp, now
            st["armed_reversal"] = (new == "ASK_HEAVY")
        if new != old:
            st["regime"] = new
        # reversal after an ask-heavy flip: bids genuinely return AND price reclaims VWAP
        # (VWAP reclaim is the trustworthy confirmation that the dip was actually absorbed)
        if st["armed_reversal"] and ltp is not None and vwap is not None:
            if med >= 0.55 and ltp >= vwap:
                event = (event + " | " if event else "") + \
                        f"↩ REVERSAL CONFIRMED (bids back ~{med:.2f}, reclaimed VWAP @{ltp})"
                st["armed_reversal"] = False
        return event

    def obir_from_depth(depth):
        try:
            buy = sum(l["quantity"] for l in depth.get("buy", []))
            sell = sum(l["quantity"] for l in depth.get("sell", []))
            tot = buy + sell
            return (buy / tot) if tot else None
        except Exception:
            return None

    def classify(ltp, vwap, obir, ltps):
        above = (vwap is not None and ltp >= vwap)
        rising = len(ltps) >= 3 and ltps[-1] > ltps[0]
        falling = len(ltps) >= 3 and ltps[-1] < ltps[0]
        strong_bid = obir is not None and obir >= 0.55
        weak_bid = obir is not None and obir < 0.45
        # momentum
        if above and rising and not weak_bid:
            momentum = "BUILDING"
        elif (not above) and falling:
            momentum = "DISTRIBUTION"
        else:
            momentum = "NEUTRAL"
        # divergence: price up but not backed (below VWAP, or sellers dominant)
        divergence = bool(rising and (weak_bid or (vwap is not None and ltp < vwap)))
        # one-line signal (research, not advice)
        if above and strong_bid and momentum == "BUILDING":
            sig = "ACCUMULATION (above VWAP, bid-heavy)"
        elif divergence:
            sig = "UNBACKED BOUNCE (price up, no bid/VWAP support)"
        elif not above and weak_bid:
            sig = "WEAK (below VWAP, sellers dominant)"
        else:
            sig = "BALANCED"
        return momentum, divergence, sig

    def on_ticks(ws, ticks):
        now = time.time()
        for t in ticks:
            sym = token_to_sym.get(t.get("instrument_token"))
            if not sym:
                continue
            ltp = t.get("last_price")
            vwap = t.get("average_traded_price")          # Kite day VWAP
            vol = t.get("volume_traded")
            obir = obir_from_depth(t.get("depth", {}) or {})
            st = state[sym]
            if ltp is not None:
                st["ltps"].append(ltp)
            dist = ((ltp / vwap - 1) * 100) if (ltp and vwap) else None
            momentum, divergence, sig = classify(ltp, vwap, obir, st["ltps"])

            # imbalance flip / cooldown-reversal events (the pattern you observed)
            flip_event = detect_flip_reversal(st, obir, ltp, vwap, now)
            if flip_event:
                log.info(f"[{sym}] {flip_event}")

            if sig != st["last_sig"]:
                d = f"{dist:+.2f}%" if dist is not None else "—"
                o = f"{obir:.2f}" if obir is not None else "—"
                log.info(f"[{sym}] {ltp}  vwap {vwap} ({d})  OBIR {o}  {momentum}  ->  {sig}"
                         + ("  ⚠ DIVERGENCE" if divergence else ""))
                st["last_sig"] = sig

            if conn and (now - st["last_db"]) >= args.interval:
                try:
                    cur = conn.cursor()
                    cur.execute("""INSERT INTO ipo_tick_feed
                        (symbol, ltp, vwap, vwap_dist, obir, day_volume, momentum, divergence, signal)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        [sym, ltp, vwap, dist, obir, vol, momentum, divergence, sig])
                    conn.commit()
                    st["last_db"] = now
                except Exception as e:
                    log.warning(f"db write failed: {e}")

    def on_connect(ws, response):
        toks = list(token_to_sym.keys())
        ws.subscribe(toks)
        ws.set_mode(ws.MODE_FULL, toks)        # full = depth + average_traded_price
        log.info(f"subscribed (MODE_FULL): {[token_to_sym[t] for t in toks]}")

    def on_close(ws, code, reason):
        log.info(f"closed: {code} {reason}")

    def on_error(ws, code, reason):
        log.warning(f"error: {code} {reason}")

    kws = KiteTicker(API_KEY, access_token)
    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close
    kws.on_error = on_error
    log.info("connecting to KiteTicker… (Ctrl-C to stop)")
    kws.connect(threaded=False)


if __name__ == "__main__":
    main()
