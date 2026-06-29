#!/usr/bin/env python3
"""
analyze_listing_day.py — derive a floor / ceiling / risk read from captured ticks.

Reads ipo_tick_feed (written by kite_ticker_ipo.py) for a symbol+date, and computes,
purely from Kite data — no fitted score:

  - proportional 0.5%-of-price VOLUME PROFILE  -> where real money transacted
  - FLOOR  = highest-volume node BELOW current price that price defended (>=3 bounces)
  - CEILING= highest-volume node ABOVE current price that rejected rallies
  - POC    = the single highest-volume price (point of control)
  - OBIR arc (open -> close), session VWAP, OHLC
  - circuit-lock detection -> if locked, the floor/ceiling read is SUPPRESSED
                              (no two-sided tape = no real level, per the operator rule)
  - gap_bucket (LOW<10 / MID 10-30 / HIGH>30) from issue_price + listing_open
  - a level-based VERDICT (floor intact / at floor / floor broken / ceiling capped)

Honest by construction: this REPORTS observed supply mechanics. It is NOT a buy call.
Writes one upsertable row per (symbol, trade_date) to ipo_level_analysis.

Usage:
  python _scripts/ipo/analyze_listing_day.py --symbol TURTLEMINT
  python _scripts/ipo/analyze_listing_day.py --auto-today          # all in-window symbols
  python _scripts/ipo/analyze_listing_day.py --symbol X --date 2026-06-29
"""
import os, sys, json, argparse, logging
from collections import defaultdict
from datetime import datetime, date

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("ipo-levels")

try:
    import psycopg2
except ImportError:
    sys.exit("pip install psycopg2-binary")

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")


def db():
    if not DB:
        sys.exit("DATABASE_URL not set.")
    return psycopg2.connect(DB)


# ---------- math helpers (pure python) ----------
def median(xs):
    s = sorted(xs)
    n = len(s)
    if not n: return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def volume_profile(ticks, binw):
    """Assign cumulative-volume deltas to the price bin where they traded."""
    prof = defaultdict(float)
    prev = None
    for t in ticks:
        v, p = t["day_volume"], t["ltp"]
        if v is not None and p:
            if prev is not None:
                dv = v - prev
                if dv > 0:
                    key = round(p / binw) * binw
                    prof[round(key, 2)] += dv
            prev = v
    return dict(prof)


def count_defenses(ltps, level, tol, rebound=0.005):
    """Distinct touch-and-rebound events near `level` (price dipped into the zone, then rose >= rebound)."""
    n = len(ltps); i = 0; defenses = 0
    while i < n:
        if abs(ltps[i] - level) <= tol:
            j = i; local_min = ltps[i]
            while j < n and ltps[j] <= level + tol:
                local_min = min(local_min, ltps[j]); j += 1
            if j < n and ltps[j] >= local_min * (1 + rebound):
                defenses += 1
            i = max(j, i + 1)
        else:
            i += 1
    return defenses


def is_circuit_locked(ltps):
    """No two-sided tape: full-session price range < 0.3% = effectively pinned/locked."""
    if len(ltps) < 10:
        return False
    lo, hi = min(ltps), max(ltps)
    ref = sum(ltps) / len(ltps)
    return ref > 0 and (hi - lo) / ref * 100 < 0.3


def gap_bucket(gap_pct):
    if gap_pct is None: return None
    if gap_pct < 10:  return "LOW"
    if gap_pct <= 30: return "MID"
    return "HIGH"


# ---------- data access ----------
def load_ticks(conn, symbol, d):
    cur = conn.cursor()
    cur.execute("""
        SELECT ltp, vwap, vwap_dist, obir, day_volume, recorded_at
        FROM ipo_tick_feed
        WHERE symbol = %s AND (recorded_at AT TIME ZONE 'Asia/Kolkata')::date = %s
        ORDER BY recorded_at ASC
    """, [symbol, d])
    out = []
    for ltp, vwap, vd, obir, vol, ts in cur.fetchall():
        out.append({"ltp": float(ltp) if ltp is not None else None,
                    "vwap": float(vwap) if vwap is not None else None,
                    "obir": float(obir) if obir is not None else None,
                    "day_volume": int(vol) if vol is not None else None,
                    "ts": ts})
    cur.close()
    return out


def issue_and_open(conn, symbol):
    cur = conn.cursor()
    cur.execute("""
        SELECT issue_price, listing_open, listing_date
        FROM ipo_intelligence
        WHERE symbol = %s
        ORDER BY listing_date DESC NULLS LAST LIMIT 1
    """, [symbol])
    row = cur.fetchone(); cur.close()
    if not row: return None, None, None
    ip = float(row[0]) if row[0] is not None else None
    lo = float(row[1]) if row[1] is not None else None
    return ip, lo, row[2]


def ensure_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ipo_level_analysis (
            id              BIGSERIAL PRIMARY KEY,
            symbol          TEXT NOT NULL,
            trade_date      DATE NOT NULL,
            issue_price     NUMERIC,
            listing_open    NUMERIC,
            gap_pct         NUMERIC,
            gap_bucket      TEXT,
            day_open        NUMERIC,
            day_high        NUMERIC,
            day_low         NUMERIC,
            day_close       NUMERIC,
            session_vwap    NUMERIC,
            close_vs_vwap   NUMERIC,
            floor_price     NUMERIC,
            floor_volume    BIGINT,
            floor_defenses  INT,
            ceiling_price   NUMERIC,
            ceiling_volume  BIGINT,
            poc_price       NUMERIC,
            obir_open       NUMERIC,
            obir_close      NUMERIC,
            circuit_locked  BOOLEAN,
            verdict         TEXT,
            risk_note       TEXT,
            profile_json    JSONB,
            tick_count      INT,
            computed_at     TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (symbol, trade_date)
        )
    """)
    conn.commit(); cur.close()


# ---------- the analysis ----------
def analyze(conn, symbol, d):
    ticks = load_ticks(conn, symbol, d)
    if len(ticks) < 5:
        log.info(f"  {symbol} {d}: only {len(ticks)} ticks — skipping (need real trading data).")
        return None

    ltps = [t["ltp"] for t in ticks if t["ltp"]]
    if len(ltps) < 5:
        return None

    cur_price = ltps[-1]
    day_open, day_close = ltps[0], ltps[-1]
    day_high, day_low = max(ltps), min(ltps)
    session_vwap = next((t["vwap"] for t in reversed(ticks) if t["vwap"]), None)
    obir_open = next((t["obir"] for t in ticks if t["obir"] is not None), None)
    obir_close = next((t["obir"] for t in reversed(ticks) if t["obir"] is not None), None)

    locked = is_circuit_locked(ltps)

    ref = median(ltps) or cur_price
    binw = max(0.05, round(0.005 * ref, 2))      # proportional 0.5% bins, min 5 paise
    tol = binw * 0.75

    prof = volume_profile(ticks, binw)
    floor_price = floor_vol = floor_def = None
    ceil_price = ceil_vol = poc_price = None

    if prof and not locked:
        poc_price = max(prof, key=prof.get)
        below = {p: v for p, v in prof.items() if p < cur_price}
        above = {p: v for p, v in prof.items() if p > cur_price}
        if below:
            floor_price = max(below, key=below.get)
            floor_vol = int(below[floor_price])
            floor_def = count_defenses(ltps, floor_price, tol)
        if above:
            ceil_price = max(above, key=above.get)
            ceil_vol = int(above[ceil_price])

    # gap (listing-day property; same across the 30d window)
    issue_price, listing_open, _ = issue_and_open(conn, symbol)
    if listing_open is None:
        listing_open = day_open           # fall back to first captured print
    gap_pct = round((listing_open - issue_price) / issue_price * 100, 2) if (issue_price and listing_open) else None
    gb = gap_bucket(gap_pct)

    close_vs_vwap = round((day_close - session_vwap) / session_vwap * 100, 2) if session_vwap else None

    # ---- verdict (level-based, mechanical, NOT a buy call) ----
    if locked:
        verdict = "OPERATOR-LOCKED"
        note = "Circuit-locked tape — no two-sided market, no reliable floor. Treat as operator play; stand aside."
    elif floor_price is None:
        verdict = "NO LEVEL YET"
        note = "Not enough volume structure to locate a floor. Keep watching."
    elif cur_price < floor_price:
        verdict = "FLOOR BROKEN"
        note = (f"Price {cur_price:.2f} is BELOW the volume floor {floor_price:.2f}. "
                "The level that defined your risk has failed — risk elevated, no fresh capital into the break.")
    elif abs(cur_price - floor_price) <= tol * 2:
        verdict = "AT FLOOR"
        note = (f"Sitting on the {floor_price:.2f} floor ({floor_def} defenses). "
                "Opportunity ONLY if it holds — wait for the hold + a VWAP reclaim, don't catch the touch.")
    elif session_vwap and cur_price >= session_vwap and (floor_def or 0) >= 3:
        verdict = "FLOOR INTACT"
        note = (f"Above VWAP and holding the {floor_price:.2f} floor ({floor_def} defenses on volume). "
                "Defined-risk zone — stop sits just below the floor.")
    elif ceil_price and abs(cur_price - ceil_price) <= tol * 2:
        verdict = "CEILING CAPPED"
        note = f"Pressing the {ceil_price:.2f} ceiling where sellers absorbed — capped / range-bound."
    else:
        verdict = "RANGE-BOUND"
        note = (f"Between floor {floor_price:.2f} and "
                f"{('ceiling ' + format(ceil_price, '.2f')) if ceil_price else 'no clear ceiling'}.")

    # gap overlay (this session's headline finding)
    if gb == "MID":
        note += "  [MID-gap = the playable bucket — this is where a defended floor matters most.]"
    elif gb == "HIGH":
        note += "  [HIGH-gap = T+1 trap zone historically; gains front-loaded, treat strength with suspicion.]"
    elif gb == "LOW":
        note += "  [LOW-gap = historically dead money; defense rarely pays.]"

    profile_json = {f"{p:.2f}": int(v) for p, v in sorted(prof.items())}

    row = dict(symbol=symbol, trade_date=d, issue_price=issue_price, listing_open=listing_open,
               gap_pct=gap_pct, gap_bucket=gb, day_open=day_open, day_high=day_high, day_low=day_low,
               day_close=day_close, session_vwap=session_vwap, close_vs_vwap=close_vs_vwap,
               floor_price=floor_price, floor_volume=floor_vol, floor_defenses=floor_def,
               ceiling_price=ceil_price, ceiling_volume=ceil_vol, poc_price=poc_price,
               obir_open=obir_open, obir_close=obir_close, circuit_locked=locked,
               verdict=verdict, risk_note=note, profile_json=json.dumps(profile_json),
               tick_count=len(ticks))
    return row


def upsert(conn, r):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ipo_level_analysis
          (symbol, trade_date, issue_price, listing_open, gap_pct, gap_bucket,
           day_open, day_high, day_low, day_close, session_vwap, close_vs_vwap,
           floor_price, floor_volume, floor_defenses, ceiling_price, ceiling_volume,
           poc_price, obir_open, obir_close, circuit_locked, verdict, risk_note,
           profile_json, tick_count)
        VALUES (%(symbol)s,%(trade_date)s,%(issue_price)s,%(listing_open)s,%(gap_pct)s,%(gap_bucket)s,
                %(day_open)s,%(day_high)s,%(day_low)s,%(day_close)s,%(session_vwap)s,%(close_vs_vwap)s,
                %(floor_price)s,%(floor_volume)s,%(floor_defenses)s,%(ceiling_price)s,%(ceiling_volume)s,
                %(poc_price)s,%(obir_open)s,%(obir_close)s,%(circuit_locked)s,%(verdict)s,%(risk_note)s,
                %(profile_json)s,%(tick_count)s)
        ON CONFLICT (symbol, trade_date) DO UPDATE SET
           issue_price=EXCLUDED.issue_price, listing_open=EXCLUDED.listing_open,
           gap_pct=EXCLUDED.gap_pct, gap_bucket=EXCLUDED.gap_bucket,
           day_open=EXCLUDED.day_open, day_high=EXCLUDED.day_high, day_low=EXCLUDED.day_low,
           day_close=EXCLUDED.day_close, session_vwap=EXCLUDED.session_vwap, close_vs_vwap=EXCLUDED.close_vs_vwap,
           floor_price=EXCLUDED.floor_price, floor_volume=EXCLUDED.floor_volume, floor_defenses=EXCLUDED.floor_defenses,
           ceiling_price=EXCLUDED.ceiling_price, ceiling_volume=EXCLUDED.ceiling_volume, poc_price=EXCLUDED.poc_price,
           obir_open=EXCLUDED.obir_open, obir_close=EXCLUDED.obir_close, circuit_locked=EXCLUDED.circuit_locked,
           verdict=EXCLUDED.verdict, risk_note=EXCLUDED.risk_note, profile_json=EXCLUDED.profile_json,
           tick_count=EXCLUDED.tick_count, computed_at=NOW()
    """, r)
    conn.commit(); cur.close()


def auto_today_symbols(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT symbol FROM ipo_intelligence
        WHERE COALESCE(is_sme,false)=false AND issue_price>=200
          AND symbol IS NOT NULL AND btrim(symbol)<>''
          AND listing_date IS NOT NULL
          AND (NOW() AT TIME ZONE 'Asia/Kolkata')::date >= listing_date
          AND (NOW() AT TIME ZONE 'Asia/Kolkata')::date <= listing_date + INTERVAL '30 days'
        ORDER BY listing_date DESC LIMIT 3
    """)
    syms = [r[0].strip().upper() for r in cur.fetchall()]; cur.close()
    return syms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", help="NSE symbol, e.g. TURTLEMINT")
    ap.add_argument("--auto-today", action="store_true", help="all mainboard >=Rs200 symbols in their 30d window")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today IST)")
    args = ap.parse_args()

    conn = db()
    ensure_table(conn)

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        cur = conn.cursor()
        cur.execute("SELECT (NOW() AT TIME ZONE 'Asia/Kolkata')::date")
        d = cur.fetchone()[0]; cur.close()

    if args.auto_today:
        symbols = auto_today_symbols(conn)
    elif args.symbol:
        symbols = [args.symbol.strip().upper()]
    else:
        sys.exit("Provide --symbol SYM or --auto-today.")

    if not symbols:
        log.info("No symbols to analyze today.")
        return

    for sym in symbols:
        r = analyze(conn, sym, d)
        if r:
            upsert(conn, r)
            fp = f"{r['floor_price']:.2f}" if r["floor_price"] else "—"
            cp = f"{r['ceiling_price']:.2f}" if r["ceiling_price"] else "—"
            log.info(f"  {sym} {d}: {r['verdict']} | floor {fp} ({r['floor_defenses']} def) "
                     f"ceiling {cp} | gap {r['gap_bucket']} | {r['tick_count']} ticks")
            log.info(f"      → {r['risk_note']}")
    conn.close()


if __name__ == "__main__":
    main()
