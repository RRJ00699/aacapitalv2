"""
AACapital — Market Regime Engine (with India VIX)
Task 12: Wire India VIX to market regime engine

Computes daily Nifty regime + breadth + VIX and writes to Neon market_regimes table.

Usage:
    python _scripts/engines/market_regime.py              # today only
    python _scripts/engines/market_regime.py --backfill   # last 30 days
    python _scripts/engines/market_regime.py --days 90    # last N days
"""

import os
import sys
import argparse
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
from kiteconnect import KiteConnect
from dotenv import load_dotenv

load_dotenv(".env.local")

NEON_URL     = os.environ["NEON_DATABASE_URL"]
KITE_API_KEY = os.environ.get("KITE_API_KEY", "br9m41pn8nvvywnl")

# Access token: prefer env var, then fall back to .kite_token file
# (same file your existing kite_token_refresh.py writes to)
def _load_kite_token() -> str:
    token = os.environ.get("KITE_ACCESS_TOKEN", "")
    if not token:
        token_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", ".kite_token")
        )
        if os.path.exists(token_file):
            with open(token_file) as f:
                token = f.read().strip()
    return token

KITE_TOKEN = _load_kite_token()

# Kite instrument tokens
NIFTY_TOKEN  = 256265   # NIFTY 50
INDIA_VIX_TOKEN = 264969  # INDIA VIX


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def _get_token() -> str:
    t = os.environ.get('KITE_ACCESS_TOKEN', '').strip()
    if t:
        return t
    for p in [os.path.join(os.getcwd(), '.kite_token'),
              os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.kite_token'))]:
        if os.path.exists(p):
            t = open(p).read().strip()
            if t:
                return t
    t = os.environ.get('ACCESS_TOKEN', '').strip()
    if t:
        return t
    # Fallback: read the freshly-refreshed token from Neon platform_config
    # (refresh_kite_token.py writes it there earlier in the daily workflow; same
    #  source every other script uses via kite_connect.get_token_from_db()).
    try:
        import psycopg2
        db = os.environ.get('DATABASE_URL') or os.environ.get('NEON_DATABASE_URL', '')
        if db:
            conn = psycopg2.connect(db)
            cur = conn.cursor()
            cur.execute("SELECT value FROM platform_config WHERE key = 'kite_access_token'")
            row = cur.fetchone()
            cur.close(); conn.close()
            if row and row[0] and str(row[0]).strip():
                return str(row[0]).strip()
    except Exception as e:
        print(f"[market_regime] Neon token read failed: {e}")
    raise RuntimeError('No Kite access token. Run refresh_kite_token.py first '
                       '(writes kite_access_token to Neon platform_config), '
                       'or set $env:KITE_ACCESS_TOKEN locally.')


def get_kite() -> KiteConnect:
    # Prefer the canonical loader (reads the live token from Neon platform_config, the same
    # source refresh_kite_token.py writes to). Fall back to the local env/.kite_token path.
    try:
        from kite_connect import get_kite as _canonical_get_kite
        return _canonical_get_kite()
    except Exception:
        kite = KiteConnect(api_key=KITE_API_KEY)
        kite.set_access_token(_get_token())
        return kite


def get_neon():
    return psycopg2.connect(NEON_URL)


# ── VIX level classifier ───────────────────────────────────────────────────────

def classify_vix(vix: Optional[float]) -> str:
    """
    India VIX interpretation:
    < 13  → Very Low Fear  (complacency risk)
    13-17 → Low            (normal market)
    17-22 → Moderate       (caution)
    22-28 → High           (fear zone)
    > 28  → Extreme Fear   (potential reversal zone)
    """
    if vix is None:
        return "UNKNOWN"
    if vix < 13:   return "VERY_LOW"
    if vix < 17:   return "LOW"
    if vix < 22:   return "MODERATE"
    if vix < 28:   return "HIGH"
    return "EXTREME"


def vix_deployment_signal(vix: Optional[float]) -> str:
    """
    Maps VIX level to a capital deployment signal.
    Counterintuitively: high VIX = buying opportunity.
    """
    if vix is None:
        return "NEUTRAL"
    if vix < 13:   return "REDUCE"      # overconfidence
    if vix < 17:   return "FULL"        # normal — deploy freely
    if vix < 22:   return "SELECTIVE"   # stay selective
    if vix < 28:   return "ACCUMULATE"  # fear = opportunity
    return "AGGRESSIVE_BUY"             # extreme fear = back up the truck


# ── Nifty regime classifier ────────────────────────────────────────────────────

def compute_ema(prices: list[float], period: int) -> list[float]:
    ema = []
    k = 2 / (period + 1)
    for i, p in enumerate(prices):
        if i == 0:
            ema.append(p)
        else:
            ema.append(p * k + ema[-1] * (1 - k))
    return ema


def classify_regime(
    nifty_close: float,
    ema200: float,
    breadth_pct: float,
    vix: Optional[float],
) -> dict:
    """
    Composite regime using Nifty vs EMA200 + breadth + VIX.
    Returns regime label + deployment pct.
    """
    above_ema = nifty_close > ema200
    strong_breadth = breadth_pct >= 60

    vix_class  = classify_vix(vix)
    vix_signal = vix_deployment_signal(vix)

    # Base regime
    if above_ema and strong_breadth:
        base = "BULLISH"
        base_deploy = 80
    elif above_ema and not strong_breadth:
        base = "NEUTRAL_BULLISH"
        base_deploy = 50
    elif not above_ema and strong_breadth:
        base = "NEUTRAL_BEARISH"
        base_deploy = 30
    else:
        base = "BEARISH"
        base_deploy = 10

    # VIX modifier: extreme fear can override bearish to "accumulate"
    if vix and vix >= 28 and base == "BEARISH":
        deploy_pct = 40  # extreme VIX = contrarian buy signal
        regime_label = "BEARISH_REVERSAL_WATCH"
    elif vix and vix < 13 and base == "BULLISH":
        deploy_pct = 60  # complacency — trim
        regime_label = "BULLISH_CAUTIOUS"
    else:
        deploy_pct = base_deploy
        regime_label = base

    return {
        "regime":         regime_label,
        "deploy_pct":     deploy_pct,
        "vix_class":      vix_class,
        "vix_signal":     vix_signal,
        "above_ema200":   above_ema,
        "breadth_strong": strong_breadth,
    }


# ── fetch candles ──────────────────────────────────────────────────────────────

def fetch_historical(kite: KiteConnect, token: int, from_dt: date, to_dt: date) -> list[dict]:
    """Fetch daily OHLCV candles from Kite."""
    try:
        data = kite.historical_data(
            instrument_token=token,
            from_date=from_dt,
            to_date=to_dt,
            interval="day",
        )
        return data
    except Exception as e:
        log(f"ERROR fetching token {token}: {e}")
        return []


def fetch_breadth_from_local(conn_local, as_of: date) -> float:
    """
    Compute % of stocks above their 200-day EMA from local price_candles.
    Falls back to 50% if local DB unavailable.
    """
    LOCAL_URL = os.environ.get(
        "LOCAL_DATABASE_URL",
        "postgresql://postgres:Ashrith%402820@localhost:5432/aacapital?sslmode=disable"
    )
    try:
        lconn = psycopg2.connect(LOCAL_URL)
        lcur  = lconn.cursor()
        lcur.execute("""
            WITH latest AS (
                SELECT symbol,
                       close,
                       AVG(close) OVER (
                           PARTITION BY symbol
                           ORDER BY date
                           ROWS BETWEEN 199 PRECEDING AND CURRENT ROW
                       ) AS ema200
                FROM price_candles
                WHERE date <= %s
            ),
            ranked AS (
                SELECT symbol, close, ema200,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY (SELECT 1)) AS rn
                FROM latest
            ),
            last_row AS (
                SELECT symbol, close > ema200 AS above
                FROM ranked
                WHERE rn = 1
            )
            SELECT
                ROUND(100.0 * SUM(CASE WHEN above THEN 1 ELSE 0 END) / COUNT(*), 1)
            FROM last_row
        """, (as_of,))
        row = lcur.fetchone()
        lconn.close()
        return float(row[0]) if row and row[0] else 50.0
    except Exception as e:
        log(f"Local DB breadth error (using 50% fallback): {e}")
        return 50.0


# ── upsert regime ──────────────────────────────────────────────────────────────

def ensure_schema(conn):
    cur = conn.cursor()
    cur.execute("""
        ALTER TABLE market_regimes
        ADD COLUMN IF NOT EXISTS india_vix        NUMERIC(6,2),
        ADD COLUMN IF NOT EXISTS vix_class        TEXT,
        ADD COLUMN IF NOT EXISTS vix_signal       TEXT,
        ADD COLUMN IF NOT EXISTS above_ema200     BOOLEAN,
        ADD COLUMN IF NOT EXISTS breadth_strong   BOOLEAN,
        ADD COLUMN IF NOT EXISTS deploy_pct       INT,
        ADD COLUMN IF NOT EXISTS updated_at       TIMESTAMPTZ DEFAULT now()
    """)
    conn.commit()
    log("Schema ensured (VIX columns added if missing)")


def upsert_regime(conn, day: date, nifty: float, ema200: float,
                  breadth: float, vix: Optional[float], regime_data: dict):
    cur = conn.cursor()
    # deploy_pct maps to both min and max allocation range
    alloc_min = max(0, regime_data["deploy_pct"] - 10)
    alloc_max = min(100, regime_data["deploy_pct"] + 10)

    cur.execute("""
        INSERT INTO market_regimes
            (evaluation_date, nifty_close, nifty_ema_200, breadth_percentage,
             india_vix, vix_class, vix_signal,
             active_regime, deploy_pct, above_ema200, breadth_strong,
             recommended_allocation_min, recommended_allocation_max,
             updated_at)
        VALUES (%s,%s,%s,%s, %s,%s,%s, %s,%s,%s,%s, %s,%s, now())
        ON CONFLICT (evaluation_date) DO UPDATE SET
            nifty_close                 = EXCLUDED.nifty_close,
            nifty_ema_200               = EXCLUDED.nifty_ema_200,
            breadth_percentage          = EXCLUDED.breadth_percentage,
            india_vix                   = EXCLUDED.india_vix,
            vix_class                   = EXCLUDED.vix_class,
            vix_signal                  = EXCLUDED.vix_signal,
            active_regime               = EXCLUDED.active_regime,
            deploy_pct                  = EXCLUDED.deploy_pct,
            above_ema200                = EXCLUDED.above_ema200,
            breadth_strong              = EXCLUDED.breadth_strong,
            recommended_allocation_min  = EXCLUDED.recommended_allocation_min,
            recommended_allocation_max  = EXCLUDED.recommended_allocation_max,
            updated_at                  = now()
    """, (
        day, nifty, ema200, breadth,
        vix, regime_data["vix_class"], regime_data["vix_signal"],
        regime_data["regime"], regime_data["deploy_pct"],
        regime_data["above_ema200"], regime_data["breadth_strong"],
        alloc_min, alloc_max,
    ))
    conn.commit()


# ── main loop ──────────────────────────────────────────────────────────────────

def process_days(days: int = 1):
    kite  = get_kite()
    conn  = get_neon()

    ensure_schema(conn)

    to_dt   = date.today()
    # Need 300 extra days of Nifty to compute EMA200 accurately
    from_dt = to_dt - timedelta(days=days + 300)

    log(f"Fetching Nifty candles {from_dt} → {to_dt}")
    nifty_candles = fetch_historical(kite, NIFTY_TOKEN, from_dt, to_dt)

    log(f"Fetching India VIX candles {from_dt} → {to_dt}")
    vix_candles   = fetch_historical(kite, INDIA_VIX_TOKEN, from_dt, to_dt)

    if not nifty_candles:
        log("ERROR: No Nifty candles returned. Check Kite token.")
        sys.exit(1)

    # Build EMA200 series over full Nifty history
    closes   = [c["close"] for c in nifty_candles]
    ema200s  = compute_ema(closes, 200)

    # Map VIX by date
    vix_by_date = {c["date"].date(): c["close"] for c in vix_candles}

    # Process only the requested window
    process_from = to_dt - timedelta(days=days - 1)
    processed = 0

    for i, candle in enumerate(nifty_candles):
        cdate = candle["date"].date() if hasattr(candle["date"], "date") else candle["date"]
        if cdate < process_from:
            continue

        nifty_close = candle["close"]
        ema200      = ema200s[i]
        vix         = vix_by_date.get(cdate)

        # Breadth from local DB
        breadth = fetch_breadth_from_local(None, cdate)

        regime_data = classify_regime(nifty_close, ema200, breadth, vix)

        upsert_regime(conn, cdate, nifty_close, ema200, breadth, vix, regime_data)

        log(
            f"{cdate} | Nifty={nifty_close:,.0f} EMA200={ema200:,.0f} "
            f"Breadth={breadth:.1f}% VIX={vix or 'N/A'} "
            f"→ {regime_data['regime']} deploy={regime_data['deploy_pct']}%"
        )
        processed += 1

    conn.close()
    log(f"\n✅ Done. {processed} day(s) processed.")

    # Print current regime summary
    if processed > 0:
        print("\n" + "═"*50)
        print("CURRENT MARKET REGIME SUMMARY")
        print("═"*50)
        last = nifty_candles[-1]
        cdate = last["date"].date() if hasattr(last["date"], "date") else last["date"]
        vix   = vix_by_date.get(cdate)
        print(f"  Date:          {cdate}")
        print(f"  Nifty:         {last['close']:,.0f}")
        print(f"  EMA200:        {ema200s[-1]:,.0f}")
        print(f"  India VIX:     {vix or 'N/A'} ({classify_vix(vix)})")
        rd = classify_regime(last["close"], ema200s[-1], 52.5, vix)
        print(f"  Regime:        {rd['regime']}")
        print(f"  Deploy signal: {rd['deploy_pct']}%")
        print(f"  VIX signal:    {rd['vix_signal']}")
        print("═"*50)


def main():
    parser = argparse.ArgumentParser(description="AACapital Market Regime Engine + India VIX")
    parser.add_argument("--backfill", action="store_true",
                        help="Process last 30 days")
    parser.add_argument("--days", type=int, default=1,
                        help="Number of days to process (default: 1 = today)")
    args = parser.parse_args()

    d = 30 if args.backfill else args.days

    log("═"*50)
    log(f"AACapital — Market Regime Engine (VIX enabled)")
    log(f"Processing {d} day(s)")
    log("═"*50)

    process_days(days=d)


if __name__ == "__main__":
    main()
