#!/usr/bin/env python3
"""
compute_earnings_surprise.py — did the company beat OUR HOUSE ESTIMATE?

Joins earnings_estimates (the backtested house model: est_revenue, est_pat) with the realized
actuals in quarterly_financials (sales, net_profit) on the SAME key (symbol + 'YYYY-MM'). Classifies
each landed quarter BEAT / MISS / INLINE — but using the MODEL'S OWN BACKTESTED ERROR as the noise
floor so we never manufacture false precision:
    revenue: median abs err ~7.5%  -> |surprise| <= 7.5% is INLINE
    PAT    : median abs err ~25%   -> |surprise| <= 25% is INLINE
A surprise is "vs our estimate" (we have no street consensus) and the band is shown so it's honest.
Also computes a consecutive beat/miss streak. Writes the new earnings_surprise table (does NOT touch
earnings_events, which is a separate manually-curated feed).

Run:  python _scripts/compute_earnings_surprise.py [--symbol WABAG --diag]
Env:  DATABASE_URL
"""
import os, sys, argparse, warnings
import pandas as pd

warnings.filterwarnings("ignore")
URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
REV_BAND = float(os.environ.get("ES_REV_BAND", "7.5"))    # model's revenue median abs err
PAT_BAND = float(os.environ.get("ES_PAT_BAND", "25.0"))   # model's PAT median abs err


def indian_fy(label: str):
    """'YYYY-MM' calendar quarter-end -> ('QxFYyy', fy_ending). Mar=Q4 of that FY; Jun=Q1 of next."""
    y, m = map(int, label.split("-"))
    fy = {3: y, 6: y + 1, 9: y + 1, 12: y + 1}.get(m)
    qn = {3: "Q4", 6: "Q1", 9: "Q2", 12: "Q3"}.get(m)
    if not qn:
        return None, None
    return f"{qn}FY{str(fy)[2:]}", fy


def classify(surprise_pct, band):
    if surprise_pct is None:
        return None
    if surprise_pct > band:
        return "BEAT"
    if surprise_pct < -band:
        return "MISS"
    return "INLINE"


def compute(est: pd.DataFrame, act: pd.DataFrame) -> pd.DataFrame:
    # actuals keyed on (symbol, fiscal_label)
    a = act.rename(columns={"fiscal_label": "q", "sales": "act_revenue", "net_profit": "act_pat"})
    a = a[["symbol", "q", "act_revenue", "act_pat"]]
    e = est.rename(columns={"fiscal_quarter": "q"})
    e = e[["symbol", "q", "est_revenue", "est_pat", "confidence", "method"]]
    df = e.merge(a, on=["symbol", "q"], how="inner")          # only quarters that have ACTUALS
    if df.empty:
        return df

    def pct(actual, est):
        if pd.isna(actual) or pd.isna(est) or est == 0:
            return None
        return (float(actual) - float(est)) / abs(float(est)) * 100

    df["revenue_surprise_pct"] = df.apply(lambda r: pct(r["act_revenue"], r["est_revenue"]), axis=1)
    df["pat_surprise_pct"] = df.apply(lambda r: pct(r["act_pat"], r["est_pat"]), axis=1)
    df["revenue_verdict"] = df["revenue_surprise_pct"].apply(lambda x: classify(x, REV_BAND))
    df["pat_verdict"] = df["pat_surprise_pct"].apply(lambda x: classify(x, PAT_BAND))

    # overall: PAT-led (what the market reacts to), revenue as tiebreak
    def overall(r):
        p, rev = r["pat_verdict"], r["revenue_verdict"]
        if p == "BEAT" and rev != "MISS":
            return "BEAT"
        if p == "MISS" and rev != "BEAT":
            return "MISS"
        if p is None:
            return rev
        return "INLINE" if p == "INLINE" else "MIXED"
    df["verdict"] = df.apply(overall, axis=1)

    # sortable period + Indian FY label
    fy = df["q"].apply(indian_fy)
    df["quarter_label"] = fy.apply(lambda t: t[0])
    df["period"] = pd.to_datetime(df["q"] + "-01")            # sortable

    # consecutive beat/miss streak per symbol (chronological)
    df = df.sort_values(["symbol", "period"])
    streaks = []
    for _, g in df.groupby("symbol"):
        run, last = 0, None
        for v in g["verdict"]:
            if v == "BEAT":
                run = run + 1 if last == "BEAT" else 1; last = "BEAT"
            elif v == "MISS":
                run = run - 1 if last == "MISS" else -1; last = "MISS"
            else:
                run = 0; last = v
            streaks.append(run)
    df["streak"] = streaks
    return df


def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS earnings_surprise (
            symbol TEXT NOT NULL, q TEXT NOT NULL, quarter_label TEXT, period DATE,
            est_revenue NUMERIC(18,4), act_revenue NUMERIC(18,4), revenue_surprise_pct NUMERIC(10,2),
            revenue_verdict TEXT,
            est_pat NUMERIC(18,4), act_pat NUMERIC(18,4), pat_surprise_pct NUMERIC(10,2),
            pat_verdict TEXT, verdict TEXT, streak INT,
            est_confidence NUMERIC(6,2), est_method TEXT,
            computed_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (symbol, q))""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol"); ap.add_argument("--diag", action="store_true")
    args = ap.parse_args()
    if not URL:
        sys.exit("DATABASE_URL not set")
    import psycopg2
    from psycopg2.extras import execute_values
    conn = psycopg2.connect(URL)

    where = "WHERE symbol=%(s)s" if args.symbol else ""
    params = {"s": args.symbol.upper()} if args.symbol else {}
    est = pd.read_sql(f"SELECT symbol, fiscal_quarter, est_revenue, est_pat, confidence, method FROM earnings_estimates {where}", conn, params=params)
    act = pd.read_sql(f"SELECT symbol, fiscal_label, sales, net_profit FROM quarterly_financials {where}", conn, params=params)
    est["symbol"] = est["symbol"].str.upper(); act["symbol"] = act["symbol"].str.upper()

    df = compute(est, act)
    if df.empty:
        print("No matched estimate/actual quarters."); conn.close(); return

    if args.symbol or args.diag:
        d = df[df["symbol"] == (args.symbol or df["symbol"].iloc[0]).upper()] if args.symbol else df
        print(f"\n{d['symbol'].iloc[0]} — earnings surprise vs house estimate (rev band ±{REV_BAND}%, PAT band ±{PAT_BAND}%)")
        for r in d.sort_values("period").itertuples():
            print(f"  {r.quarter_label:8} rev: est {r.est_revenue:.0f} act {r.act_revenue:.0f} "
                  f"({_s(r.revenue_surprise_pct)}) {r.revenue_verdict or '-':6}  |  "
                  f"pat: est {r.est_pat:.0f} act {r.act_pat:.0f} ({_s(r.pat_surprise_pct)}) {r.pat_verdict or '-':6}  "
                  f"=> {r.verdict} (streak {r.streak:+d})")
        conn.close(); return

    cur = conn.cursor(); ensure_table(cur); conn.commit()
    cols = ["symbol", "q", "quarter_label", "period", "est_revenue", "act_revenue",
            "revenue_surprise_pct", "revenue_verdict", "est_pat", "act_pat", "pat_surprise_pct",
            "pat_verdict", "verdict", "streak", "est_confidence", "est_method"]
    df = df.rename(columns={"confidence": "est_confidence", "method": "est_method"})
    rows = [tuple(None if pd.isna(r.get(c)) else r.get(c) for c in cols) for _, r in df.iterrows()]
    execute_values(cur, f"""
        INSERT INTO earnings_surprise ({", ".join(cols)}) VALUES %s
        ON CONFLICT (symbol, q) DO UPDATE SET {", ".join(f"{c}=EXCLUDED.{c}" for c in cols[2:])}, computed_at=NOW()
    """, rows, page_size=500)
    conn.commit()
    n_beat = (df["verdict"] == "BEAT").sum(); n_miss = (df["verdict"] == "MISS").sum()
    conn.close()
    print(f"earnings_surprise: wrote {len(df):,} quarters across {df['symbol'].nunique():,} symbols "
          f"({n_beat:,} beats, {n_miss:,} misses vs house estimate).")


def _s(x):
    return "—" if x is None or pd.isna(x) else f"{x:+.0f}%"


if __name__ == "__main__":
    main()
