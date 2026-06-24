#!/usr/bin/env python3
"""
compute_institutional_flow.py — a SOFT 'smart money reducing/adding' flag per stock.

Backtests showed institutional DISTRIBUTION is a faint signal (one clean year, 6-12m,
only the ~17% of stocks with real FII/DII/MF data). Too thin to be a hard AVOID verdict.
So this writes a SEPARATE, clearly-labeled, soft flag — informational context, not a
recommendation. The UI should show it as "⚠ institutions reducing" / "institutions adding",
never as a buy/sell call, and only for stocks where real institutional data exists.

Signal: net change in (fii_pct+dii_pct+mf_pct) over the last ~2 quarters, for stocks that
actually have institutional data (inst>0 in recent quarters). Stocks without real data get
NO flag (not "stable" — we simply don't know).

Run:  python _scripts/compute_institutional_flow.py
Env:  DATABASE_URL ; FLOW_DROP=1.5 (pct-pt fall = REDUCING) ; FLOW_RISE=1.5 (= ADDING)
"""
import os, sys, re, psycopg2
from psycopg2.extras import execute_values, RealDictCursor

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

DROP = float(os.environ.get("FLOW_DROP", "1.5"))   # pct-points fall over window => REDUCING
RISE = float(os.environ.get("FLOW_RISE", "1.5"))   # pct-points rise over window => ADDING
WINDOW_Q = 2                                        # look back ~2 quarters

QEND = {"1": (6, 30), "2": (9, 30), "3": (12, 31), "4": (3, 31)}


def q_to_date(q):
    m = re.match(r"(\d{4})Q([1-4])", str(q).strip())
    if not m:
        return None
    mo, day = QEND[m.group(2)]
    return (int(m.group(1)), mo, day)


def main():
    conn = psycopg2.connect(URL); conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT nse_symbol, quarter,
               COALESCE(fii_pct,0)+COALESCE(dii_pct,0)+COALESCE(mf_pct,0) AS inst
        FROM shareholding_history
        WHERE quarter ~ '^[0-9]{4}Q[1-4]$' AND nse_symbol IS NOT NULL
    """)
    rows = cur.fetchall()

    # Identify DENSE quarters (coverage >= MIN_COVERAGE stocks). Sparse/partial quarters
    # have far fewer stocks and comparing against them manufactures fake REDUCING.
    MIN_COVERAGE = int(os.environ.get("FLOW_MIN_COVERAGE", "500"))
    from collections import Counter
    qcount = Counter(r["quarter"] for r in rows if float(r["inst"]) > 0)
    dense = {q for q, n in qcount.items() if n >= MIN_COVERAGE}
    if len(dense) < 2:
        sys.exit(f"Need >=2 dense quarters (>={MIN_COVERAGE} stocks); found {sorted(dense)}. "
                 "Institutional coverage too thin/lumpy to flag flow honestly.")
    print(f"Dense quarters used: {sorted(dense)}")

    # group by symbol using ONLY dense quarters, ordered by real quarter-end date
    series = {}
    for r in rows:
        if r["quarter"] not in dense:
            continue
        d = q_to_date(r["quarter"])
        if d is None:
            continue
        series.setdefault(r["nse_symbol"], []).append((d, float(r["inst"])))

    flags = []
    for sym, pts in series.items():
        pts.sort()  # chronological (dense quarters only)
        recent = [v for _, v in pts[-(WINDOW_Q + 1):]]
        # need at least 2 dense-quarter points, both with real institutional data
        recent = [v for v in recent if v > 0]
        if len(recent) < 2:
            continue                      # not enough real dense data -> NO flag
        latest = recent[-1]
        base = recent[0]
        net = latest - base               # pct-point change across dense quarters
        if net <= -DROP:
            label = "REDUCING"
        elif net >= RISE:
            label = "ADDING"
        else:
            label = "STABLE"
        flags.append((sym, round(latest, 2), round(net, 2), label))

    if not flags:
        sys.exit("No stocks had real institutional data to flag.")

    cur2 = conn.cursor()
    cur2.execute("""
        CREATE TABLE IF NOT EXISTS institutional_flow_flags (
            nse_symbol     TEXT PRIMARY KEY,
            inst_pct       NUMERIC,     -- latest FII+DII+MF %
            net_change_2q  NUMERIC,     -- pct-point change over ~2 quarters
            flow_label     TEXT,        -- REDUCING | ADDING | STABLE (soft, informational)
            updated_at     TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur2.execute("TRUNCATE institutional_flow_flags")
    execute_values(cur2, """
        INSERT INTO institutional_flow_flags (nse_symbol, inst_pct, net_change_2q, flow_label)
        VALUES %s
    """, flags, page_size=500)

    from collections import Counter
    c = Counter(f[3] for f in flags)
    print(f"institutional_flow_flags: {len(flags):,} stocks with real institutional data")
    print(f"  REDUCING={c['REDUCING']:,}  ADDING={c['ADDING']:,}  STABLE={c['STABLE']:,}")
    print("Soft, informational flag only. UI should label it 'institutions reducing/adding'")
    print("as context — never as a buy/sell verdict. Stocks without data get no flag.")
    cur.close(); cur2.close(); conn.close()


if __name__ == "__main__":
    main()
