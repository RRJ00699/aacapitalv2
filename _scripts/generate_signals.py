"""
_scripts/generate_signals.py
==============================
Generates technical signals directly from price_candles in local Postgres.
Bypasses the TypeScript screener which requires monthly indicators.

Computes per stock:
- Buy zone score (0-100)
- NR7 detection
- EMA200 position
- Momentum 6M
- Volume expansion
- Stage classification

Writes to technical_signals (local) then you run sync-signals-to-neon.ts

Usage:
  python _scripts/generate_signals.py
  python _scripts/generate_signals.py --symbols RELIANCE INFY TCS
  python _scripts/generate_signals.py --min-candles 60
"""

import os, sys, logging, argparse, datetime
import psycopg2, psycopg2.extras
import statistics

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

LOCAL_URL = os.environ.get("LOCAL_DATABASE_URL") or \
            "postgresql://postgres:Ashrith%402820@localhost:5432/aacapital?sslmode=disable"

def get_symbols(conn, limit: int) -> list[str]:
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT symbol FROM price_candles
        WHERE symbol NOT IN ('ANTELOPUS','ACUTAAS')
        ORDER BY symbol
        LIMIT %s
    """, (limit,))
    syms = [r[0] for r in cur.fetchall()]
    cur.close()
    return syms

def get_candles(conn, symbol: str, days: int = 365) -> list[dict]:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT date, open, high, low, close, volume
        FROM price_candles
        WHERE symbol = %s
        ORDER BY date DESC
        LIMIT %s
    """, (symbol, days))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return list(reversed(rows))  # oldest first

def ema(prices: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(prices)
    if len(prices) < period:
        return result
    k = 2 / (period + 1)
    # seed with SMA
    seed = sum(prices[:period]) / period
    result[period - 1] = seed
    for i in range(period, len(prices)):
        result[i] = prices[i] * k + (result[i-1] or seed) * (1 - k)
    return result

def true_ranges(candles: list[dict]) -> list[float]:
    trs = []
    for i, c in enumerate(candles):
        if i == 0:
            trs.append(float(c['high']) - float(c['low']))
        else:
            prev_close = float(candles[i-1]['close'])
            trs.append(max(
                float(c['high']) - float(c['low']),
                abs(float(c['high']) - prev_close),
                abs(float(c['low'])  - prev_close),
            ))
    return trs

def compute_signal(symbol: str, candles: list[dict]) -> dict | None:
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
    ema200_series = ema(closes, 200)
    ema200        = ema200_series[-1]
    above_ema200  = price > ema200 if ema200 else False

    # EMA50
    ema50_series  = ema(closes, 50)
    ema50         = ema50_series[-1]

    # Momentum 6M (126 trading days)
    momentum_6m = 0.0
    if len(closes) >= 126:
        momentum_6m = (price / closes[-126] - 1) * 100

    # NR7 — narrowest range in last 7 days
    recent_trs = trs[-7:]
    is_nr7 = len(recent_trs) == 7 and recent_trs[-1] == min(recent_trs)

    # Volume expansion — today vs 20-day avg
    vol_avg_20   = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else None
    vol_expansion = (volumes[-1] / vol_avg_20) if vol_avg_20 and vol_avg_20 > 0 else 1.0

    # 52-week high
    high_52w     = max(highs[-252:]) if len(highs) >= 252 else max(highs)
    pct_below_hi = (high_52w - price) / high_52w * 100 if high_52w > 0 else 0

    # Base months — count consecutive weeks within 30% of current price
    base_months = 0
    if len(closes) >= 20:
        base_close = closes[-1]
        weeks = 0
        for i in range(len(closes)-1, max(0, len(closes)-104), -5):
            if abs(closes[i] / base_close - 1) < 0.30:
                weeks += 1
            else:
                break
        base_months = round(weeks * 5 / 21)

    # ── Score (0–100) ──────────────────────────────────────────────────
    score = 0

    # EMA200 position (30 pts)
    if above_ema200:
        score += 30

    # Momentum 6M (20 pts)
    if momentum_6m >= 20:
        score += 20
    elif momentum_6m >= 10:
        score += 12
    elif momentum_6m >= 0:
        score += 5

    # NR7 (15 pts)
    if is_nr7:
        score += 15

    # Volume expansion (10 pts)
    if vol_expansion >= 1.5:
        score += 10
    elif vol_expansion >= 1.2:
        score += 5

    # Near 52W high (10 pts)
    if pct_below_hi <= 5:
        score += 10
    elif pct_below_hi <= 15:
        score += 5

    # Base building (15 pts)
    if base_months >= 6:
        score += 15
    elif base_months >= 3:
        score += 8

    # Stage classification
    if above_ema200 and momentum_6m >= 15:
        stage = "2"
        stage_label = "Stage 2: Markup"
    elif above_ema200:
        stage = "1"
        stage_label = "Stage 1: Accumulation"
    elif momentum_6m < -20:
        stage = "4"
        stage_label = "Stage 4: Decline"
    else:
        stage = "3"
        stage_label = "Stage 3: Distribution"

    action = "ACCUMULATE" if score >= 75 else \
             "WATCH_FOR_BREAKOUT" if score >= 60 else \
             "WATCH" if score >= 40 else "IGNORE"

    return {
        "symbol":           symbol,
        "signal_date":      today,
        "close":            price,
        "buy_zone_score":   score,
        "convergence_score": score,
        "probability_score": score,
        "signal_strength":  "VERY_HIGH" if score >= 80 else "HIGH" if score >= 65 else "MEDIUM" if score >= 50 else "LOW",
        "action_label":     action,
        "is_nr7":           is_nr7,
        "nr7":              is_nr7,
        "above_ema200":     above_ema200,
        "ema200":           round(ema200, 2) if ema200 else None,
        "momentum_6m":      round(momentum_6m, 2),
        "vol_compression":  round(1 / vol_expansion, 2) if vol_expansion > 0 else 1.0,
        "volume_expansion": round(vol_expansion, 2),
        "base_months":      base_months,
        "stage":            stage,
        "stage_label":      stage_label,
        "pct_below_high":   round(pct_below_hi, 2),
    }

def upsert_signal(conn, sig: dict):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO technical_signals (
            symbol, signal_date, close, buy_zone_score,
            probability_score, signal_strength, action_label,
            nr7, above_ema200, ema200, momentum_6m,
            base_months, stage, stage_label,
            all_criteria_met, updated_at
        ) VALUES (
            %(symbol)s, %(signal_date)s, %(close)s, %(buy_zone_score)s,
            %(probability_score)s, %(signal_strength)s, %(action_label)s,
            %(nr7)s, %(above_ema200)s, %(ema200)s, %(momentum_6m)s,
            %(base_months)s, %(stage)s, %(stage_label)s,
            %(above_ema200)s, NOW()
        )
        ON CONFLICT (symbol, signal_date) DO UPDATE SET
            close           = EXCLUDED.close,
            buy_zone_score  = EXCLUDED.buy_zone_score,
            probability_score = EXCLUDED.probability_score,
            signal_strength = EXCLUDED.signal_strength,
            action_label    = EXCLUDED.action_label,
            nr7             = EXCLUDED.nr7,
            above_ema200    = EXCLUDED.above_ema200,
            momentum_6m     = EXCLUDED.momentum_6m,
            stage           = EXCLUDED.stage,
            stage_label     = EXCLUDED.stage_label,
            updated_at      = NOW()
    """, sig)
    conn.commit()
    cur.close()

def ensure_columns(conn):
    cur = conn.cursor()
    for col, typ in [
        ("buy_zone_score",   "NUMERIC"),
        ("convergence_score","NUMERIC"),
        ("above_ema200",     "BOOLEAN"),
        ("ema200",           "NUMERIC"),
        ("momentum_6m",      "NUMERIC"),
        ("volume_expansion", "NUMERIC"),
        ("vol_compression",  "NUMERIC"),
        ("base_months",      "INTEGER"),
        ("stage",            "TEXT"),
        ("stage_label",      "TEXT"),
        ("pct_below_high",   "NUMERIC"),
        ("is_nr7",           "BOOLEAN"),
    ]:
        try:
            cur.execute(f"ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS {col} {typ}")
            conn.commit()
        except Exception:
            conn.rollback()
    cur.close()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols",     nargs="+")
    p.add_argument("--limit",       type=int, default=500)
    p.add_argument("--min-candles", type=int, default=30)
    args = p.parse_args()

    conn = psycopg2.connect(LOCAL_URL, connect_timeout=10)
    log.info("Local Postgres connected")

    ensure_columns(conn)

    symbols = args.symbols or get_symbols(conn, args.limit)
    log.info(f"Processing {len(symbols)} stocks")
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
            if ok % 25 == 0:
                log.info(f"  [{i+1}/{len(symbols)}] {ok} signals written…")

    conn.close()
    log.info("=" * 60)
    log.info(f"Done. {ok} signals written, {skipped} skipped (insufficient candles)")
    log.info("Now run: npx tsx _scripts/sync-signals-to-neon.ts")

if __name__ == "__main__":
    main()
