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
        "base_months":      base_months,
        "stage":            stage,
        "stage_label":      stage_label,
        "pct_below_high":   round(pct_below_hi, 2),
    }

def ensure_columns(conn):
    additions = [
        ("buy_zone_score",   "NUMERIC"),
        ("above_ema200",     "BOOLEAN"),
        ("ema200",           "NUMERIC"),
        ("momentum_6m",      "NUMERIC"),
        ("vol_compression",  "NUMERIC"),
        ("base_months",      "INTEGER"),
        ("stage",            "TEXT"),
        ("stage_label",      "TEXT"),
        ("pct_below_high",   "NUMERIC"),
        ("is_nr7",           "BOOLEAN"),
        ("convergence_score","NUMERIC"),
    ]
    cur = conn.cursor()
    for col, typ in additions:
        try:
            cur.execute(f"ALTER TABLE technical_signals ADD COLUMN IF NOT EXISTS {col} {typ}")
            conn.commit()
        except Exception:
            conn.rollback()
    cur.close()

def upsert_signal(conn, sig: dict):
    cur = conn.cursor()
    # Upsert by symbol only — one row per stock, always latest
    cur.execute("""
        INSERT INTO technical_signals (
            symbol, signal_date, close, buy_zone_score, convergence_score,
            probability_score, signal_strength, action_label,
            is_nr7, nr7, above_ema200, ema200, momentum_6m,
            vol_compression, base_months, stage, stage_label,
            pct_below_high, updated_at
        ) VALUES (
            %(symbol)s, %(signal_date)s, %(close)s, %(buy_zone_score)s, %(buy_zone_score)s,
            %(probability_score)s, %(signal_strength)s, %(action_label)s,
            %(is_nr7)s, %(nr7)s, %(above_ema200)s, %(ema200)s, %(momentum_6m)s,
            %(vol_compression)s, %(base_months)s, %(stage)s, %(stage_label)s,
            %(pct_below_high)s, NOW()
        )
        ON CONFLICT (symbol) DO UPDATE SET
            signal_date      = EXCLUDED.signal_date,
            close            = EXCLUDED.close,
            buy_zone_score   = EXCLUDED.buy_zone_score,
            convergence_score= EXCLUDED.buy_zone_score,
            probability_score= EXCLUDED.probability_score,
            signal_strength  = EXCLUDED.signal_strength,
            action_label     = EXCLUDED.action_label,
            is_nr7           = EXCLUDED.is_nr7,
            nr7              = EXCLUDED.nr7,
            above_ema200     = EXCLUDED.above_ema200,
            ema200           = EXCLUDED.ema200,
            momentum_6m      = EXCLUDED.momentum_6m,
            vol_compression  = EXCLUDED.vol_compression,
            base_months      = EXCLUDED.base_months,
            stage            = EXCLUDED.stage,
            stage_label      = EXCLUDED.stage_label,
            pct_below_high   = EXCLUDED.pct_below_high,
            updated_at       = NOW()
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
