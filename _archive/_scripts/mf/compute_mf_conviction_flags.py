#!/usr/bin/env python3
"""
compute_mf_conviction_flags.py — turn the backtested NEW-conviction signal into a live flag.

The one signal that survived this project's testing: a high-conviction active fund
(Nippon/quant/Canara/PPFAS small-mid-flexi) INITIATING a brand-new position predicts
forward outperformance (per-year EDGE+ in 3 of 4 years; strongest 1-3 months; modest in
weak regimes). This script detects those initiations from mf_scheme_holdings and writes a
mf_conviction_flags table the Stocks screen reads.

CADENCE-AGNOSTIC: an initiation = a stock present in a fund's disclosure that was ABSENT in
that fund's immediately-prior disclosure — works the same whether disclosures are monthly or
fortnightly (compares against the previous snapshot, not a fixed calendar gap).

FRESHNESS: the backtest says the edge lives in the ~1-3 month window after the buy. So each
flag carries first_seen + an expiry (default 90 days). Stale initiations are NOT flagged —
the screen never shows a 6-month-old 'new buy' as if it were fresh.

Run after every holdings load:  python _scripts/mf/compute_mf_conviction_flags.py
Env:  DATABASE_URL ; MF_EDGE_DAYS=90 (flag lifetime) ; MF_MIN_FUNDS=1 (min funds initiating)
"""
import os, sys
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

EDGE_DAYS = int(os.environ.get("MF_EDGE_DAYS", "90"))
MIN_FUNDS = int(os.environ.get("MF_MIN_FUNDS", "1"))
# Same threshold the freshness monitor uses (MF_STALE_DAYS=50): a fund whose own latest
# disclosure is older than this is untrustworthy, and its initiations are not flagged.
STALE_DAYS = int(os.environ.get("MF_STALE_DAYS", "50"))


def main():
    conn = psycopg2.connect(URL); conn.autocommit = True
    hold = pd.read_sql("""
        SELECT month AS as_of, scheme_name, amc_name, nse_symbol,
               COALESCE(portfolio_weight_pct, 0) AS wt
        FROM mf_scheme_holdings
        WHERE nse_symbol IS NOT NULL AND nse_symbol <> ''
    """, conn)
    if hold.empty:
        sys.exit("no holdings with symbols — load + run ISIN map first")
    hold["as_of"] = pd.to_datetime(hold["as_of"])

    # For each fund, find initiations: a (scheme, symbol) present on a date but absent on that
    # scheme's immediately-prior disclosure date. Cadence-agnostic.
    flags = []
    for scheme, g in hold.groupby("scheme_name"):
        dates = sorted(g["as_of"].unique())
        held_by_date = {d: set(g[g["as_of"] == d]["nse_symbol"]) for d in dates}
        amc = g["amc_name"].iloc[0]
        for i in range(1, len(dates)):
            prev, cur = dates[i - 1], dates[i]
            initiated = held_by_date[cur] - held_by_date[prev]   # new this disclosure
            for sym in initiated:
                wt = g[(g["as_of"] == cur) & (g["nse_symbol"] == sym)]["wt"].max()
                flags.append({"nse_symbol": sym, "scheme": scheme, "amc": amc,
                              "first_seen": pd.Timestamp(cur), "wt": float(wt)})

    if not flags:
        print("No initiations detected (need >=2 disclosure dates per fund)."); return
    fdf = pd.DataFrame(flags)

    # ── Staleness guard ───────────────────────────────────────────────────────
    # A fund whose own latest disclosure is older than MF_STALE_DAYS can't be trusted
    # to still hold what it last showed, so its "initiations" would surface as fake-fresh
    # buys. Drop those funds here (before the per-symbol counts) so the screen only fires
    # on funds we can stand behind — and a stock's fund-count reflects trustworthy funds only.
    today = pd.Timestamp.today().normalize()
    fund_latest = hold.groupby("scheme_name")["as_of"].max()
    stale_funds = {s for s, d in fund_latest.items() if (today - d).days > STALE_DAYS}
    if stale_funds:
        before = len(fdf)
        fdf = fdf[~fdf["scheme"].isin(stale_funds)].copy()
        print(f"staleness guard: dropped {before - len(fdf)} initiation(s) from "
              f"{len(stale_funds)} stale fund(s) (>{STALE_DAYS}d old):")
        for s in sorted(stale_funds):
            print(f"    - {s}  (latest {fund_latest[s].date()}, {(today - fund_latest[s]).days}d old)")
    if fdf.empty:
        print("All funds stale — no trustworthy initiations to flag."); return

    # latest disclosure date in the whole dataset = "now" for freshness purposes
    latest = hold["as_of"].max()
    cutoff = latest - pd.Timedelta(days=EDGE_DAYS)
    fresh = fdf[fdf["first_seen"] >= cutoff].copy()

    # aggregate per symbol: how many funds initiated it (within the window), names, newest date
    agg = (fresh.groupby("nse_symbol")
           .agg(n_funds=("scheme", "nunique"),
                funds=("scheme", lambda s: " · ".join(sorted(set(s)))),
                first_seen=("first_seen", "max"),
                total_wt=("wt", "sum"))
           .reset_index())
    agg = agg[agg["n_funds"] >= MIN_FUNDS]

    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mf_conviction_flags (
            nse_symbol   TEXT PRIMARY KEY,
            n_funds      INT,          -- how many conviction funds initiated (in window)
            funds        TEXT,         -- which funds
            first_seen   DATE,         -- newest initiation disclosure date
            total_weight NUMERIC,      -- summed entry weight across initiating funds
            expires_on   DATE,         -- first_seen + edge window; screen ignores after this
            flag         TEXT,         -- 'NEW_CONVICTION'
            updated_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("TRUNCATE mf_conviction_flags")
    rows = [(r.nse_symbol, int(r.n_funds), r.funds, r.first_seen.date(),
             round(float(r.total_wt), 4),
             (r.first_seen + pd.Timedelta(days=EDGE_DAYS)).date(), "NEW_CONVICTION")
            for r in agg.itertuples()]
    if rows:
        execute_values(cur, """
            INSERT INTO mf_conviction_flags
              (nse_symbol, n_funds, funds, first_seen, total_weight, expires_on, flag)
            VALUES %s
        """, rows, page_size=500)

    print(f"latest disclosure in data: {latest.date()}  (edge window = {EDGE_DAYS}d)")
    print(f"fresh NEW-conviction flags written: {len(rows)}")
    multi = agg[agg["n_funds"] >= 2]
    print(f"  of which multi-fund (>=2 funds initiating same stock): {len(multi)}")
    for r in agg.sort_values("n_funds", ascending=False).head(12).itertuples():
        print(f"    {r.nse_symbol:14s} {int(r.n_funds)} fund(s)  seen {r.first_seen.date()}  {r.funds[:40]}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
