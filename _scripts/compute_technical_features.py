#!/usr/bin/env python3
"""
compute_technical_features.py — the Technical Feature Store (Bucket A: honest descriptors).

COMPLEMENTS the existing technical_signals table (maintained nightly by generate_signals.py) — it
does NOT touch it. Adds the genuinely-missing institutional features and, crucially, a 0-100
UNIVERSE-PERCENTILE rank for each (the spec's key idea: every feature comparable across all stocks).

Features (all point-in-time, no look-ahead, raw value + universe-percentile score):
  - Relative Strength vs UNIVERSE and vs SECTOR (3m & 6m price return ranked across peers)
  - RVOL (today's volume / 20d average) + volume state
  - Volatility (ATR%/close) and its 252d percentile
  - 52-week-high & all-time-high proximity
  - Trend: EMA20/50/200 alignment + price location
These describe WHAT IS — not predictions. No buy calls. Writes table `technical_features`.

Run:  python _scripts/compute_technical_features.py            (all symbols -> DB)
      python _scripts/compute_technical_features.py --symbol RELIANCE --diag   (print one, no DB)
Env:  DATABASE_URL
"""
import os, sys, argparse, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
LOOK_3M, LOOK_6M = 63, 126           # trading days
MIN_HISTORY = 60                      # need at least ~3 months of candles


def rsi(close: np.ndarray, n: int = 14):
    if len(close) < n + 1:
        return None
    d = np.diff(close)
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = up[-n:].mean(); ad = dn[-n:].mean()
    if ad == 0:
        return 100.0
    rs = au / ad
    return float(100 - 100 / (1 + rs))


def per_symbol(df: pd.DataFrame) -> dict:
    """df: date-sorted OHLCV for one symbol. Returns raw features (ranks added later)."""
    if len(df) < MIN_HISTORY:
        return None
    close = df["close"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    vol = df["volume"].to_numpy(float)
    px = close[-1]
    if px <= 0:
        return None

    def ret(n):
        return (close[-1] / close[-1 - n] - 1) * 100 if len(close) > n and close[-1 - n] > 0 else None

    # ATR% (14)
    tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
    atr = tr[-14:].mean() if len(tr) >= 14 else (tr.mean() if len(tr) else None)
    atr_pct = (atr / px * 100) if atr else None
    # volatility percentile: today's ATR% vs its own 252d history
    vol_pctile = None
    if len(tr) >= 30:
        win = min(252, len(tr))
        atr_series = pd.Series(tr).rolling(14).mean().to_numpy()
        atr_pct_series = atr_series / close[1:] * 100
        recent = atr_pct_series[-win:]
        recent = recent[~np.isnan(recent)]
        if len(recent) > 10 and atr_pct is not None:
            vol_pctile = float((recent <= atr_pct).mean() * 100)

    # RVOL — today's volume vs the average of the PRIOR 20 days (excludes today)
    avg20 = vol[-21:-1].mean() if len(vol) >= 21 else (vol[:-1].mean() if len(vol) > 1 else None)
    rvol = (vol[-1] / avg20) if (avg20 and avg20 > 0) else None

    # EMAs
    def ema(n):
        if len(close) < n:
            return None
        return float(pd.Series(close).ewm(span=n, adjust=False).mean().iloc[-1])
    e20, e50, e200 = ema(20), ema(50), ema(200)
    aligned = (e20 is not None and e50 is not None and e200 is not None and e20 > e50 > e200 and px > e20)
    above200 = (e200 is not None and px > e200)

    # 52w & ATH proximity
    win252 = close[-252:] if len(close) >= 252 else close
    hi52 = win252.max()
    ath = close.max()
    pct_from_52wh = (px / hi52 - 1) * 100 if hi52 > 0 else None     # negative = below high
    pct_from_ath = (px / ath - 1) * 100 if ath > 0 else None

    return {
        "price": round(px, 2),
        "ret_3m": ret(LOOK_3M), "ret_6m": ret(LOOK_6M),
        "rvol": round(rvol, 2) if rvol else None,
        "atr_pct": round(atr_pct, 2) if atr_pct else None,
        "vol_pctile": round(vol_pctile, 1) if vol_pctile is not None else None,
        "rsi14": rsi(close),
        "ema_aligned": aligned, "above_ema200": above200,
        "pct_from_52wh": round(pct_from_52wh, 2) if pct_from_52wh is not None else None,
        "pct_from_ath": round(pct_from_ath, 2) if pct_from_ath is not None else None,
    }


def pctile_rank(series: pd.Series) -> pd.Series:
    """0-100 percentile rank across the universe (NaN-safe)."""
    return series.rank(pct=True) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol"); ap.add_argument("--diag", action="store_true")
    args = ap.parse_args()
    if not URL:
        sys.exit("DATABASE_URL not set")
    import psycopg2
    from psycopg2.extras import execute_values
    conn = psycopg2.connect(URL)

    # sector map
    cm = pd.read_sql("SELECT nse_symbol AS symbol, sector FROM company_master WHERE nse_symbol IS NOT NULL", conn)
    sector_of = dict(zip(cm["symbol"].str.upper(), cm["sector"]))

    if args.symbol:
        sym = args.symbol.upper()
        df = pd.read_sql("SELECT date,open,high,low,close,volume FROM price_candles WHERE symbol=%s AND close>0 ORDER BY date", conn, params=(sym,))
        conn.close()
        f = per_symbol(df)
        if not f:
            print(f"{sym}: insufficient history."); return
        print(f"\n{sym}  ₹{f['price']}  ({sector_of.get(sym,'?')})")
        print(f"  ret 3m={f['ret_3m']}  6m={f['ret_6m']}   RVOL={f['rvol']}   ATR%={f['atr_pct']} (vol pctile {f['vol_pctile']})")
        print(f"  RSI={f['rsi14']}   EMA-aligned={f['ema_aligned']}  above200={f['above_ema200']}")
        print(f"  from 52wH={f['pct_from_52wh']}%   from ATH={f['pct_from_ath']}%")
        print("  (universe & sector RS ranks are assigned in the full run)")
        return

    # full universe
    print("loading candles (this is the heavy step)…")
    allpx = pd.read_sql("SELECT symbol,date,open,high,low,close,volume FROM price_candles WHERE close>0 ORDER BY symbol,date", conn)
    allpx["symbol"] = allpx["symbol"].str.upper()
    rows = []
    for sym, g in allpx.groupby("symbol", sort=False):
        f = per_symbol(g)
        if f:
            f["symbol"] = sym; f["sector"] = sector_of.get(sym)
            rows.append(f)
    F = pd.DataFrame(rows)
    if F.empty:
        sys.exit("no features computed")

    # universe-percentile ranks
    F["rs_3m_universe"] = pctile_rank(F["ret_3m"])
    F["rs_6m_universe"] = pctile_rank(F["ret_6m"])
    F["rvol_rank"] = pctile_rank(F["rvol"])
    # sector-relative strength (rank within sector on 6m return)
    F["rs_6m_sector"] = F.groupby("sector")["ret_6m"].transform(lambda s: s.rank(pct=True) * 100)
    # composite RS = blend of 3m & 6m universe percentile (descriptive momentum rank, NOT a forecast)
    F["rs_score"] = F[["rs_3m_universe", "rs_6m_universe"]].mean(axis=1)

    for c in ["rs_3m_universe", "rs_6m_universe", "rs_6m_sector", "rvol_rank", "rs_score"]:
        F[c] = F[c].round(1)

    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS technical_features (
            symbol TEXT PRIMARY KEY, sector TEXT, price NUMERIC(14,2),
            ret_3m NUMERIC(8,2), ret_6m NUMERIC(8,2),
            rs_3m_universe NUMERIC(5,1), rs_6m_universe NUMERIC(5,1),
            rs_6m_sector NUMERIC(5,1), rs_score NUMERIC(5,1),
            rvol NUMERIC(8,2), rvol_rank NUMERIC(5,1),
            atr_pct NUMERIC(8,2), vol_pctile NUMERIC(5,1), rsi14 NUMERIC(6,2),
            ema_aligned BOOLEAN, above_ema200 BOOLEAN,
            pct_from_52wh NUMERIC(8,2), pct_from_ath NUMERIC(8,2),
            computed_at TIMESTAMPTZ DEFAULT NOW())""")
    conn.commit()

    cols = ["symbol", "sector", "price", "ret_3m", "ret_6m", "rs_3m_universe", "rs_6m_universe",
            "rs_6m_sector", "rs_score", "rvol", "rvol_rank", "atr_pct", "vol_pctile", "rsi14",
            "ema_aligned", "above_ema200", "pct_from_52wh", "pct_from_ath"]
    data = [tuple(None if pd.isna(r[c]) else r[c] for c in cols) for _, r in F.iterrows()]
    execute_values(cur, f"""
        INSERT INTO technical_features ({", ".join(cols)}) VALUES %s
        ON CONFLICT (symbol) DO UPDATE SET {", ".join(f"{c}=EXCLUDED.{c}" for c in cols[1:])}, computed_at=NOW()
    """, data, page_size=500)
    conn.commit(); conn.close()
    print(f"technical_features: scored {len(F):,} symbols (universe + sector RS ranks assigned).")


if __name__ == "__main__":
    main()
