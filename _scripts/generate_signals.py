"""
_scripts/generate_signals.py
==============================
Generates technical signals from price_candles in Neon DB.
Works fully in cloud — no local Postgres needed.
Runs daily via GitHub Actions after market close.

Pipeline:
  Neon price_candles → compute signals → write technical_signals (Neon)

Retention / Purge strategy:
  technical_signals: keep 1 signal per stock (upsert by symbol only, no date conflict)
  price_candles: retain 5Y rolling (purge_automation.py handles this)

Usage:
  python _scripts/generate_signals.py                # all stocks in price_candles
  python _scripts/generate_signals.py --limit 500    # top N stocks
  python _scripts/generate_signals.py --symbols RELIANCE INFY
"""

import os, sys, logging, argparse, datetime
import psycopg2, psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Works with either local or Neon depending on what's set
DATABASE_URL = (
    os.environ.get("DATABASE_URL") or
    os.environ.get("NEON_DATABASE_URL") or
    os.environ.get("LOCAL_DATABASE_URL") or
    "postgresql://postgres:Ashrith%402820@localhost:5432/aacapital?sslmode=disable"
)

def get_conn():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def get_symbols(conn, limit: int) -> list:
    cur = conn.cursor()
    cur.execute("""
        SELECT symbol, COUNT(*) as cnt
        FROM price_candles
        WHERE symbol NOT IN ('ANTELOPUS','ACUTAAS')
        GROUP BY symbol
        HAVING COUNT(*) >= 30
        ORDER BY cnt DESC
        LIMIT %s
    """, (limit,))
    syms = [r[0] for r in cur.fetchall()]
    cur.close()
    log.info(f"Found {len(syms)} symbols with >= 30 candles")
    return syms

def get_candles(conn, symbol: str) -> list:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT date, open, high, low, close, volume
        FROM price_candles
        WHERE symbol = %s
        ORDER BY date ASC
    """, (symbol,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows

def ema(prices: list, period: int) -> list:
    result = [None] * len(prices)
    if len(prices) < period:
        return result
    k = 2 / (period + 1)
    seed = sum(float(p) for p in prices[:period]) / period
    result[period - 1] = seed
    for i in range(period, len(prices)):
        prev = result[i-1] if result[i-1] is not None else seed
        result[i] = float(prices[i]) * k + prev * (1 - k)
    return result

def true_ranges(candles: list) -> list:
    trs = []
    for i, c in enumerate(candles):
        h, l = float(c['high']), float(c['low'])
        if i == 0:
            trs.append(h - l)
        else:
            pc = float(candles[i-1]['close'])
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return trs

def compute_signal(symbol: str, candles: list) -> dict | None:
    if len(candles) < 30:
        return None

    closes  = [float(c['close'])  for c in candles]
    highs   = [float(c['high'])   for c in candles]
    lows    = [float(c['low'])    for c in candles]
    volumes = [float(c['volume'] or 0) for c in candles]
    trs     = true_ranges(candles)
    price   = closes[-1]
    today   = candles[-1]['date']

    # EMA200
    ema200_s = ema(closes, 200)
    ema200   = ema200_s[-1]
    above_200 = price > ema200 if ema200 else False

    # EMA50
    ema50_s  = ema(closes, 50)
    ema50    = ema50_s[-1]

    # Momentum
    mom_6m = ((price / closes[-126] - 1) * 100) if len(closes) >= 126 else 0.0
    mom_3m = ((price / closes[-63]  - 1) * 100) if len(closes) >= 63  else 0.0

    # NR7
    recent_trs = trs[-7:]
    is_nr7 = len(recent_trs) == 7 and recent_trs[-1] == min(recent_trs)

    # Volume
    vol_avg_20   = (sum(volumes[-21:-1]) / 20) if len(volumes) >= 21 else None
    vol_expansion = (volumes[-1] / vol_avg_20) if vol_avg_20 and vol_avg_20 > 0 else 1.0
    vol_compress  = round(1 / vol_expansion, 3) if vol_expansion > 0 else 1.0

    # 52W high
    high_52w     = max(highs[-252:]) if len(highs) >= 252 else max(highs)
    pct_below_hi = (high_52w - price) / high_52w * 100 if high_52w > 0 else 0

    # Base months
    base_months = 0
    if len(closes) >= 20:
        for i in range(len(closes)-1, max(0, len(closes)-104), -5):
            if abs(closes[i] / price - 1) < 0.30:
                base_months += 1
            else:
                break
        base_months = round(base_months * 5 / 21)

    # ── Score ─────────────────────────────────────────────────────────
    score = 0

    if above_200:                         score += 30
    if mom_6m >= 20:                      score += 20
    elif mom_6m >= 10:                    score += 12
    elif mom_6m >= 0:                     score += 5
    if is_nr7:                            score += 15
    if vol_expansion >= 1.5:              score += 10
    elif vol_expansion >= 1.2:            score += 5
    if pct_below_hi <= 5:                 score += 10
    elif pct_below_hi <= 15:              score += 5
    if base_months >= 6:                  score += 15
    elif base_months >= 3:                score += 8

    # Stage
    if above_200 and mom_6m >= 15:
        stage, stage_label = "2", "Stage 2: Markup"
    elif above_200:
        stage, stage_label = "1", "Stage 1: Accumulation"
    elif mom_6m < -20:
        stage, stage_label = "4", "Stage 4: Decline"
    else:
        stage, stage_label = "3", "Stage 3: Distribution"

    action = ("ACCUMULATE"        if score >= 75 else
              "WATCH_FOR_BREAKOUT" if score >= 60 else
              "WATCH"              if score >= 40 else "IGNORE")

    strength = ("VERY_HIGH" if score >= 80 else
                "HIGH"      if score >= 65 else
                "MEDIUM"    if score >= 50 else "LOW")

    return {
        "symbol":           symbol,
        "signal_date":      today,
        "close":            round(price, 2),
        "buy_zone_score":   score,
        "probability_score": score,
        "signal_strength":  strength,
        "action_label":     action,
        "is_nr7":           is_nr7,
        "nr7":              is_nr7,
        "above_ema200":     above_200,
        "ema200":           round(ema200, 2) if ema200 else None,
        "momentum_6m":      round(mom_6m, 2),
        "vol_compression":  vol_compress,
        "volume_ratio_20":  round(vol_expansion, 2),   # SESSION 9: added for breakout watch
        "base_months":      base_months,
        "stage":            stage,
        "stage_label":      stage_label,
        "pct_below_high":   round(pct_below_hi, 2),
    }

def ensure_columns(conn):
    additions = [
        ("buy_zone_score",         "NUMERIC"),
        ("above_ema200",           "BOOLEAN"),
        ("ema200",                 "NUMERIC"),
        ("momentum_6m",            "NUMERIC"),
        ("vol_compression",        "NUMERIC"),
        ("volume_ratio_20",        "NUMERIC"),   # SESSION 9
        ("base_months",            "INTEGER"),
        ("stage",                  "TEXT"),
        ("stage_label",            "TEXT"),
        ("pct_below_high",         "NUMERIC"),
        ("is_nr7",                 "BOOLEAN"),
        ("convergence_score",      "NUMERIC"),
        ("breakout_watch_score",   "INTEGER"),   # SESSION 9
        ("breakout_watch_tier",    "TEXT"),       # SESSION 9: COILED | BUILDING | EARLY
    ]
    cur = conn.cursor()
    for col, typ in additions:
        try:
            cur.execute(f"ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS {col} {typ}")
            conn.commit()
        except Exception:
            conn.rollback()
    cur.close()

def _compute_breakout_watch(sig: dict) -> tuple:
    """
    SESSION 9 — Breakout Watch scoring.
    Surfaces ABCAPITAL-type setups BEFORE they break out.
    Returns (score: int 0-100, tier: str|None)

    Key difference from mb_score:
      mb_score rewards momentum (already moving).
      breakout_watch rewards anticipation: coiled under 52W high with building volume.
    """
    s = 0

    # 1. Proximity to 52W high (32 pts)
    pct = float(sig.get('pct_below_high') or 100)
    if pct < 0:           s += 8    # just punched through — early continuation
    elif pct <= 3:        s += int(32 * (1.0 - pct / 4.5))   # sweet spot
    elif pct <= 8:        s += int(20 * (1.0 - (pct - 3) / 8))

    # 2. Range compression — NR7 (16 pts) + quiet vol (10 pts)
    if sig.get('is_nr7') or sig.get('nr7'):
        s += 16
    vc = float(sig.get('vol_compression') or 1.0)
    # vol_compression = 1/vol_expansion; >1 means recent candle quieter than avg
    if vc > 1.5:   s += min(10, int((vc - 1.0) * 5))
    elif vc > 1.2: s += 4

    # 3. Trend confirmation (18 pts)
    if sig.get('above_ema200'):       s += 11
    if sig.get('price_above_ema30'):  s += 7

    # 4. Volume building — NOT blow-off (16 pts)
    # volume_ratio_20 = today's vol / 20-day avg
    vr = float(sig.get('volume_ratio_20') or 1.0)
    if 1.3 <= vr <= 5.0:
        frac = 1.0 - abs(vr - 2.5) / 3.0   # peaks at 2.5x (ABCAPITAL profile)
        s += int(16 * max(0.3, min(1.0, frac)))
    elif vr > 5.0:
        s += 4   # blow-off top — move may have already fired

    # 5. Stage (8 pts)
    stage = str(sig.get('stage') or '')
    if stage in ('1', '2'):
        s += 8

    score = min(100, max(0, s))
    tier  = ('COILED'   if score >= 80 else
             'BUILDING' if score >= 60 else
             'EARLY'    if score >= 48 else None)
    return score, tier


def upsert_signal(conn, sig: dict):
    cur = conn.cursor()

    # Compute mb_score from available signals (multibagger filter needs this >= 40)
    score = 0
    if sig.get('above_ema200'):       score += 25
    if sig.get('stage') in [2, '2']:  score += 20
    if sig.get('is_nr7') or sig.get('nr7'): score += 15
    mom = float(sig.get('momentum_6m') or 0)
    if mom > 10:  score += 15
    elif mom > 0: score += 8
    vc = float(sig.get('vol_compression') or 0)
    if vc > 5:    score += 10
    elif vc > 2:  score += 5
    pct_hi = float(sig.get('pct_below_high') or 100)
    if pct_hi < 5:  score += 15  # near 52W high
    elif pct_hi < 15: score += 8
    sig.setdefault('volume_ratio_20', None)
    sig.setdefault('stage', None)
    sig.setdefault('stage_label', None)
    sig.setdefault('is_nr7', False)
    sig.setdefault('nr7', False)
    sig.setdefault('above_ema200', False)
    sig.setdefault('ema200', None)
    sig.setdefault('momentum_6m', None)
    sig.setdefault('vol_compression', None)
    sig.setdefault('base_months', None)
    sig.setdefault('pct_below_high', None)
    sig['mb_score']           = min(score, 95)
    sig['buy_zone_score']     = min(score, 95)
    sig['price_above_ema30']  = sig.get('above_ema200', False)
    sig['conviction']         = sig.get('action_label', 'WATCH')
    sig['all_criteria_met']   = score >= 40
    sig['volume_ratio_20']    = sig.get('volume_ratio_20', None)

    # SESSION 9 — Breakout Watch
    bw_score, bw_tier         = _compute_breakout_watch(sig)
    sig['breakout_watch_score'] = bw_score
    sig['breakout_watch_tier']  = bw_tier

    # Use DELETE + INSERT to avoid constraint issues
    sig.setdefault('timeframe', 'daily')
    cur.execute("DELETE FROM technical_signals WHERE symbol = %(symbol)s AND timeframe = %(timeframe)s", sig)
    cur.execute("""
        INSERT INTO technical_signals (
            symbol, signal_date, timeframe, close, buy_zone_score, mb_score,
            convergence_score, probability_score, signal_strength, action_label,
            conviction, all_criteria_met, price_above_ema30,
            is_nr7, nr7, above_ema200, ema200, momentum_6m,
            vol_compression, volume_ratio_20, base_months, stage, stage_label,
            pct_below_high, breakout_watch_score, breakout_watch_tier,
            updated_at, synced_at
        ) VALUES (
            %(symbol)s, %(signal_date)s, %(timeframe)s, %(close)s,
            %(buy_zone_score)s, %(mb_score)s, %(buy_zone_score)s,
            %(probability_score)s, %(signal_strength)s, %(action_label)s,
            %(conviction)s, %(all_criteria_met)s, %(price_above_ema30)s,
            %(is_nr7)s, %(nr7)s, %(above_ema200)s, %(ema200)s, %(momentum_6m)s,
            %(vol_compression)s, %(volume_ratio_20)s, %(base_months)s, %(stage)s, %(stage_label)s,
            %(pct_below_high)s, %(breakout_watch_score)s, %(breakout_watch_tier)s,
            NOW(), NOW()
        )
    """, sig)
    conn.commit()
    cur.close()

def purge_old_signals(conn):
    """Keep only 1 signal per stock (latest). Remove signals older than 30 days."""
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM technical_signals
        WHERE signal_date < NOW() - INTERVAL '30 days'
          AND symbol NOT IN (
              SELECT DISTINCT symbol FROM technical_signals
              WHERE signal_date >= NOW() - INTERVAL '30 days'
          )
    """)
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    if deleted > 0:
        log.info(f"Purged {deleted} stale signal rows")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols",     nargs="+")
    p.add_argument("--limit",       type=int, default=500)
    p.add_argument("--min-candles", type=int, default=30)
    p.add_argument("--purge-only",  action="store_true")
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_conn()
    source = "Neon" if "neon.tech" in DATABASE_URL else "Local Postgres"
    log.info(f"Connected to {source}")

    ensure_columns(conn)

    if args.purge_only:
        purge_old_signals(conn)
        conn.close()
        return

    symbols = args.symbols or get_symbols(conn, args.limit)
    log.info(f"Generating signals for {len(symbols)} stocks")
    log.info("=" * 60)

    ok = 0; skipped = 0
    for i, sym in enumerate(symbols):
        candles = get_candles(conn, sym)
        if len(candles) < args.min_candles:
            skipped += 1
            continue
        sig = compute_signal(sym, candles)
        if sig:
            upsert_signal(conn, sig)
            ok += 1
            if ok % 50 == 0:
                log.info(f"  [{i+1}/{len(symbols)}] {ok} signals written…")

    purge_old_signals(conn)
    conn.close()

    log.info("=" * 60)
    log.info(f"Done. {ok} signals written, {skipped} skipped")

if __name__ == "__main__":
    main()
