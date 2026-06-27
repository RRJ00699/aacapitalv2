#!/usr/bin/env python3
"""
compute_valuation.py — the Valuation Lens. Answers "is this stock cheap or expensive vs its OWN
history?" — the price complement to DNA's quality. Pure compute, no scraping: builds a point-in-time
monthly P/E and P/B series from price_candles + annual_financials (no look-ahead — each month uses
only the annual EPS/book value that was public by then, ~Sept disclosure lag), then places today's
valuation as a PERCENTILE within that 10-year band. Also reports a TTM P/E from quarterly_financials
as a bonus "current trailing" view. Research/context, NOT a buy call.

Writes the `valuation` table (one row per symbol).
Modes:  --symbol SYM (print, no DB) · --diag (one symbol, no DB) · (default) all -> DB
  python _scripts/compute_valuation.py --symbol RELIANCE
  python _scripts/compute_valuation.py
"""
import os, sys, argparse, datetime, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message=".*pandas only supports SQLAlchemy.*")

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
CR = 1e7  # 1 crore = 10,000,000 ; Screener financials are in ₹ crore, price_candles in ₹/share


def public_fy(period) -> int:
    """Latest FY (ending-year) whose annual results are public as of a month — FY ending Mar Y is
    disclosed ~Sept Y, so until Sept we only know FY Y-1. Mirrors the DNA point-in-time rule."""
    return period.year if period.month >= 9 else period.year - 1


def asof(metric_by_fy, fy_target):
    """Value of a per-FY metric as known at fy_target: the latest fy <= target."""
    avail = [fy for fy in metric_by_fy if fy <= fy_target and metric_by_fy[fy] is not None]
    return metric_by_fy[max(avail)] if avail else None


def compute_symbol(sym, px, ann, ttm_np):
    """px: DataFrame(date,close) for one symbol. ann: DataFrame of annual_financials rows.
    ttm_np: trailing-4Q net profit (₹ cr) or None. Returns a dict or None."""
    if px is None or px.empty or ann is None or ann.empty:
        return None

    # per-FY EPS (₹/share) and book value per share, using THAT year's share count
    eps_by_fy, bvps_by_fy, shares_latest = {}, {}, None
    for r in ann.sort_values("fiscal_year").itertuples(index=False):
        sh = float(r.no_of_shares) if r.no_of_shares else None
        if not sh or sh <= 0:
            continue
        shares_latest = sh
        np_cr = float(r.net_profit) if r.net_profit is not None else None
        eq = float(r.equity_capital) if r.equity_capital is not None else 0.0
        res = float(r.reserves) if r.reserves is not None else 0.0
        eps_by_fy[int(r.fiscal_year)] = (np_cr * CR / sh) if np_cr is not None else None
        bvps_by_fy[int(r.fiscal_year)] = ((eq + res) * CR / sh) if (eq or res) else None

    if not eps_by_fy:
        return None

    # monthly close series
    px = px.copy()
    px["ym"] = px["date"].dt.to_period("M")
    monthly = px.groupby("ym")["close"].last()

    pe_hist, pb_hist = [], []
    for ym, price in monthly.items():
        if price is None or price <= 0:
            continue
        fy = public_fy(ym)
        eps = asof(eps_by_fy, fy)
        bv = asof(bvps_by_fy, fy)
        if eps and eps > 0:
            pe_hist.append(price / eps)
        if bv and bv > 0:
            pb_hist.append(price / bv)

    if len(pe_hist) < 24:           # need ~2yr of monthly obs for a meaningful band
        return None

    cur_price = float(monthly.iloc[-1])
    latest_fy = max(eps_by_fy)
    latest_eps = eps_by_fy.get(latest_fy)
    latest_bv = bvps_by_fy.get(latest_fy)

    # current P/E on the SAME basis as history (latest annual EPS) -> apples-to-apples percentile
    cur_pe = (cur_price / latest_eps) if (latest_eps and latest_eps > 0) else None
    cur_pb = (cur_price / latest_bv) if (latest_bv and latest_bv > 0) else None
    # bonus: TTM P/E (more current), price / (TTM net profit per share)
    ttm_eps = (ttm_np * CR / shares_latest) if (ttm_np and shares_latest) else None
    ttm_pe = (cur_price / ttm_eps) if (ttm_eps and ttm_eps > 0) else None

    pe_arr = np.array(pe_hist)
    pe_pctile = float((pe_arr <= cur_pe).mean() * 100) if cur_pe else None
    pb_arr = np.array(pb_hist) if pb_hist else None
    pb_pctile = float((pb_arr <= cur_pb).mean() * 100) if (cur_pb and pb_arr is not None and len(pb_arr)) else None

    verdict = None
    if pe_pctile is not None:
        verdict = ("cheap vs own history" if pe_pctile < 30 else
                   "expensive vs own history" if pe_pctile > 70 else "fair vs own history")
    elif cur_pe is None:
        verdict = "loss-making (no P/E)"

    return {
        "symbol": sym, "current_price": round(cur_price, 2),
        "current_pe": round(cur_pe, 2) if cur_pe else None,
        "ttm_pe": round(ttm_pe, 2) if ttm_pe else None,
        "current_pb": round(cur_pb, 2) if cur_pb else None,
        "pe_min": round(float(pe_arr.min()), 2), "pe_median": round(float(np.median(pe_arr)), 2),
        "pe_max": round(float(pe_arr.max()), 2), "pe_percentile": round(pe_pctile, 1) if pe_pctile is not None else None,
        "pb_median": round(float(np.median(pb_arr)), 2) if (pb_arr is not None and len(pb_arr)) else None,
        "pb_percentile": round(pb_pctile, 1) if pb_pctile is not None else None,
        "verdict": verdict, "n_obs": len(pe_hist), "years": round(len(pe_hist) / 12, 1),
    }


def load_one(conn, sym):
    px = pd.read_sql("SELECT date, close FROM price_candles WHERE symbol=%s AND close>0 ORDER BY date",
                     conn, params=(sym,))
    px["date"] = pd.to_datetime(px["date"])
    ann = pd.read_sql("""SELECT fiscal_year, net_profit, no_of_shares, equity_capital, reserves
                         FROM annual_financials WHERE symbol=%s""", conn, params=(sym,))
    ttm = pd.read_sql("""SELECT net_profit FROM quarterly_financials WHERE symbol=%s
                         ORDER BY period DESC LIMIT 4""", conn, params=(sym,))
    ttm_np = float(ttm["net_profit"].sum()) if len(ttm) == 4 and ttm["net_profit"].notna().all() else None
    return px, ann, ttm_np


def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS valuation (
            symbol TEXT PRIMARY KEY, current_price NUMERIC(14,2),
            current_pe NUMERIC(10,2), ttm_pe NUMERIC(10,2), current_pb NUMERIC(10,2),
            pe_min NUMERIC(10,2), pe_median NUMERIC(10,2), pe_max NUMERIC(10,2),
            pe_percentile NUMERIC(5,1), pb_median NUMERIC(10,2), pb_percentile NUMERIC(5,1),
            verdict TEXT, n_obs INT, years NUMERIC(5,1), computed_at TIMESTAMPTZ DEFAULT NOW())""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol")
    ap.add_argument("--diag", action="store_true")
    args = ap.parse_args()
    if not URL:
        sys.exit("DATABASE_URL not set")
    import psycopg2
    from psycopg2.extras import execute_values
    conn = psycopg2.connect(URL)

    if args.symbol or args.diag:
        sym = (args.symbol or "RELIANCE").upper()
        px, ann, ttm_np = load_one(conn, sym)
        out = compute_symbol(sym, px, ann, ttm_np)
        conn.close()
        if not out:
            print(f"{sym}: insufficient data (need price history + annual EPS)."); return
        print(f"\n{sym}  price ₹{out['current_price']}")
        print(f"  P/E now {out['current_pe']}  (TTM {out['ttm_pe']})   band {out['pe_min']}–{out['pe_median']}–{out['pe_max']}"
              f"   percentile {out['pe_percentile']}  -> {out['verdict']}")
        print(f"  P/B now {out['current_pb']}  median {out['pb_median']}  percentile {out['pb_percentile']}")
        print(f"  ({out['years']}yr, {out['n_obs']} monthly obs)")
        return

    cur = conn.cursor(); ensure_table(cur); conn.commit()
    syms = pd.read_sql("SELECT DISTINCT symbol FROM annual_financials", conn)["symbol"].tolist()
    rows, n = [], 0
    cols = ["symbol", "current_price", "current_pe", "ttm_pe", "current_pb", "pe_min", "pe_median",
            "pe_max", "pe_percentile", "pb_median", "pb_percentile", "verdict", "n_obs", "years"]
    for sym in syms:
        try:
            px, ann, ttm_np = load_one(conn, sym)
            out = compute_symbol(sym, px, ann, ttm_np)
        except Exception as e:
            continue
        if out:
            rows.append(tuple(out[c] for c in cols)); n += 1
    execute_values(cur, f"""
        INSERT INTO valuation ({", ".join(cols)}) VALUES %s
        ON CONFLICT (symbol) DO UPDATE SET {", ".join(f"{c}=EXCLUDED.{c}" for c in cols[1:])}, computed_at=NOW()
    """, rows, page_size=500)
    conn.commit(); conn.close()
    print(f"valuation: scored {n:,} companies.")


if __name__ == "__main__":
    main()
