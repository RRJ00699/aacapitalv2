#!/usr/bin/env python3
"""
compute_earnings_estimates.py — transparent, backtestable "house estimate" for each
stock's next-quarter results, built only from your own quarterly_results history. No
external analyst consensus (none free for NSE); we estimate against the company's OWN
trajectory — "did results beat their own trend?" — which is reproducible and is what a
discipline tool actually wants.

DATA REALITY (from --diag on the live table): quarterly_results.fiscal_quarter is a
calendar quarter-end string 'YYYY-MM' (e.g. 2024-03/06/09/12); annual rows carry 'FY'
and are skipped. EPS is not populated, so we estimate REVENUE and PAT (whichever exist).

MODEL ("yoy_seasonal") per metric:
    est(Q) = value(same quarter last year) * (1 + g)
g = median year-over-year growth across recent quarters, clamped to a sane band so one
freak quarter can't blow it up. Confidence reflects history depth, growth consistency,
and a positive base. Writes earnings_estimates, keyed exactly like quarterly_results so
the surprise step (next) joins with no string-matching.

Modes:
  python _scripts/compute_earnings_estimates.py --diag        # inspect data + coverage
  python _scripts/compute_earnings_estimates.py --backtest    # walk-forward accuracy, no writes
  python _scripts/compute_earnings_estimates.py               # estimate next quarter per symbol
  python _scripts/compute_earnings_estimates.py --quarters 8  # also (re)estimate last 8 reported quarters
Env: DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, re, json, argparse, statistics

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
METRICS = ("revenue", "pat", "eps")          # estimate whichever are populated
GROWTH_LO, GROWTH_HI = -0.5, 1.0             # clamp YoY growth to [-50%, +100%]


def parse_period(fiscal_quarter):
    """'YYYY-MM' → chrono index in months (year*12+month). Annual 'FY'/bad → None."""
    m = re.match(r"^\s*(\d{4})-(\d{1,2})\s*$", str(fiscal_quarter or ""))
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    if not 1 <= mo <= 12:
        return None
    return y * 12 + mo


def inv_period(idx):
    """chrono index → (year, month, 'YYYY-MM')."""
    y = (idx - 1) // 12
    mo = idx - y * 12
    return y, mo, f"{y}-{mo:02d}"


def clamp(g):
    return max(GROWTH_LO, min(GROWTH_HI, g))


def estimate_metric(prior, by, target_idx, field):
    """YoY-seasonal estimate for one metric. prior sorted asc; by = {idx: row}."""
    base = by.get(target_idx - 12)            # same quarter, one year earlier
    if not base or base.get(field) is None or base[field] <= 0:
        return None
    pairs = []
    for p in prior:
        prev = by.get(p["idx"] - 12)
        if prev and prev.get(field) and prev[field] > 0 and p.get(field) is not None:
            pairs.append(p[field] / prev[field] - 1)
    if not pairs:
        return None
    recent = pairs[-4:]
    g = clamp(statistics.median(recent))
    disp = statistics.pstdev(recent) if len(recent) > 1 else 0.0
    est = round(base[field] * (1 + g), 4)
    return est, {"base": base[field], "growth": round(g, 4), "n_pairs": len(pairs), "dispersion": round(disp, 4)}


def estimate(prior, target_idx):
    """Revenue via YoY-seasonal; PAT via est_revenue × trailing net margin (smoother than
    raw PAT-YoY — margins are far more stable than absolute profit). EPS is omitted in v1:
    its surprise % equals PAT's (shares ~constant), so PAT already captures it."""
    if len(prior) < 5:
        return None
    by = {p["idx"]: p for p in prior}
    ests, basis = {}, {}

    # revenue — YoY-seasonal
    r = estimate_metric(prior, by, target_idx, "revenue")
    if r:
        ests["revenue"], basis["revenue"] = r

    # PAT — margin method: est_revenue × trailing median net margin (the §3a fix)
    if "revenue" in ests:
        margins = [p["pat"] / p["revenue"] for p in prior
                   if p.get("pat") is not None and p.get("revenue") and p["revenue"] > 0]
        if margins:
            recent = margins[-4:]
            est_margin = statistics.median(recent)
            ests["pat"] = round(ests["revenue"] * est_margin, 2)
            basis["pat"] = {"method": "revenue_x_margin", "margin": round(est_margin, 4),
                            "margin_dispersion": round(statistics.pstdev(recent) if len(recent) > 1 else 0.0, 4),
                            "n_margins": len(margins)}
    # fallback: direct PAT YoY if the revenue path wasn't available
    if "pat" not in ests:
        rp = estimate_metric(prior, by, target_idx, "pat")
        if rp:
            ests["pat"], basis["pat"] = rp
            basis["pat"]["method"] = "yoy_seasonal"

    if not ests:
        return None

    # confidence: history depth − revenue growth dispersion − margin dispersion
    conf = 40 + min(30, len(prior) * 2)
    if basis.get("revenue"):
        conf -= min(20, int(basis["revenue"]["dispersion"] * 50))
    md = basis.get("pat", {}).get("margin_dispersion")
    if md is not None:
        conf -= min(20, int(md * 200))
    conf = max(5, min(95, conf))
    return {"est": ests, "confidence": conf,
            "basis": {"target_idx": target_idx, "history_quarters": len(prior), **basis}}


def load_symbols(cur):
    cur.execute("""
        SELECT symbol, fiscal_quarter, revenue, pat, eps
        FROM quarterly_results
        WHERE symbol IS NOT NULL AND fiscal_quarter IS NOT NULL
    """)
    data = {}
    for sym, fq, rev, pat, eps in cur.fetchall():
        idx = parse_period(fq)
        if idx is None:                       # skip annual 'FY' + unparseable
            continue
        data.setdefault(sym, []).append({
            "idx": idx,
            "revenue": float(rev) if rev is not None else None,
            "pat":     float(pat) if pat is not None else None,
            "eps":     float(eps) if eps is not None else None,
        })
    for sym in data:
        data[sym].sort(key=lambda r: r["idx"])
        # de-dup same period (keep last)
        seen = {}
        for r in data[sym]:
            seen[r["idx"]] = r
        data[sym] = [seen[k] for k in sorted(seen)]
    return data


def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS earnings_estimates (
            symbol         TEXT NOT NULL,
            fiscal_year    TEXT,
            fiscal_quarter TEXT NOT NULL,
            est_revenue    NUMERIC(16,2),
            est_pat        NUMERIC(16,2),
            est_eps        NUMERIC(12,4),
            method         TEXT,
            confidence     NUMERIC(5,2),
            basis          JSONB DEFAULT '{}',
            generated_at   TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (symbol, fiscal_year, fiscal_quarter)
        )
    """)
    # idempotent: an older version may have created this table without est_pat etc.
    for col, typ in [("est_revenue", "NUMERIC(16,2)"), ("est_pat", "NUMERIC(16,2)"),
                     ("est_eps", "NUMERIC(12,4)"), ("method", "TEXT"),
                     ("confidence", "NUMERIC(5,2)"), ("basis", "JSONB DEFAULT '{}'"),
                     ("generated_at", "TIMESTAMPTZ DEFAULT NOW()")]:
        cur.execute(f"ALTER TABLE earnings_estimates ADD COLUMN IF NOT EXISTS {col} {typ}")


def run_compute(cur, conn, back_quarters):
    ensure_table(cur); conn.commit()
    data = load_symbols(cur)
    rows = []
    for sym, series in data.items():
        if len(series) < 6:
            continue
        last = series[-1]["idx"]
        targets = {last + 3}                                  # next quarter (3 months on)
        for i in range(max(0, len(series) - back_quarters), len(series)):
            targets.add(series[i]["idx"])
        for t in sorted(targets):
            prior = [p for p in series if p["idx"] < t]
            out = estimate(prior, t)
            if not out:
                continue
            y, mo, _ = inv_period(t)
            e = out["est"]
            rows.append((sym, str(y), f"{y}-{mo:02d}",
                         e.get("revenue"), e.get("pat"), e.get("eps"),
                         "yoy_seasonal", out["confidence"], json.dumps(out["basis"])))
    if not rows:
        print("No estimates produced.")
        return
    from psycopg2.extras import execute_values
    execute_values(cur, """
        INSERT INTO earnings_estimates
          (symbol, fiscal_year, fiscal_quarter, est_revenue, est_pat, est_eps, method, confidence, basis)
        VALUES %s
        ON CONFLICT (symbol, fiscal_year, fiscal_quarter) DO UPDATE SET
          est_revenue=EXCLUDED.est_revenue, est_pat=EXCLUDED.est_pat, est_eps=EXCLUDED.est_eps,
          method=EXCLUDED.method, confidence=EXCLUDED.confidence, basis=EXCLUDED.basis, generated_at=NOW()
    """, rows, page_size=len(rows))
    conn.commit()
    print(f"earnings_estimates: wrote {len(rows):,} rows across {len({r[0] for r in rows}):,} symbols "
          f"(metrics: revenue/pat where populated).")


def run_backtest(cur):
    data = load_symbols(cur)
    stat = {m: {"ape": [], "hit10": 0, "dir_hit": 0, "dir_n": 0} for m in METRICS}
    n_eval = 0
    for sym, series in data.items():
        for i in range(len(series)):
            t = series[i]["idx"]
            prior = [p for p in series if p["idx"] < t]
            out = estimate(prior, t)
            if not out:
                continue
            n_eval += 1
            by = {p["idx"]: p for p in prior}
            for m in METRICS:
                est = out["est"].get(m)
                actual = series[i].get(m)
                if est is None or actual is None or actual == 0:
                    continue
                stat[m]["ape"].append(abs(est - actual) / abs(actual))
                if abs(est - actual) / abs(actual) <= 0.10:
                    stat[m]["hit10"] += 1
                base = by.get(t - 12, {}).get(m)
                if base:
                    stat[m]["dir_n"] += 1
                    if (est >= base) == (actual >= base):
                        stat[m]["dir_hit"] += 1
    if not n_eval:
        print("Backtest: no estimable quarters (need >=6 quarters/symbol with a year-ago base).")
        return
    print(f"Backtest over {n_eval:,} estimable quarters — house estimate vs the company's own trend:")
    for m in METRICS:
        s = stat[m]
        if not s["ape"]:
            print(f"  {m:<8}: no data")
            continue
        med = statistics.median(s["ape"]) * 100
        w10 = 100 * s["hit10"] / len(s["ape"])
        d = 100 * s["dir_hit"] / s["dir_n"] if s["dir_n"] else float("nan")
        print(f"  {m:<8}: median abs%err {med:5.1f}%  |  within ±10% {w10:5.1f}%  |  direction {d:5.1f}%  (n={len(s['ape']):,})")


def run_diag(cur):
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT symbol) FROM quarterly_results")
    total, syms = cur.fetchone()
    print(f"quarterly_results: {total:,} rows, {syms:,} symbols")
    for m in METRICS:
        cur.execute(f"SELECT COUNT({m}) FROM quarterly_results")
        print(f"  non-null {m:<8}: {cur.fetchone()[0]:,}")
    data = load_symbols(cur)
    kept = sum(len(v) for v in data.values())
    enough = sum(1 for v in data.values() if len(v) >= 6)
    print(f"  parsed quarterly rows: {kept:,} across {len(data):,} symbols  "
          f"(symbols with >=6 quarters: {enough:,})")
    # history depth — how close are we to 10yr (40 quarters)?
    depths = sorted(len(v) for v in data.values())
    if depths:
        print(f"  quarters/symbol: min {depths[0]}, median {depths[len(depths)//2]}, max {depths[-1]}")
        for thr in (8, 12, 20, 40):
            print(f"    symbols with >={thr:>2} quarters (~{thr//4}yr): {sum(1 for d in depths if d >= thr):,}")
        all_idx = [r["idx"] for v in data.values() for r in v]
        print(f"  earliest quarter: {inv_period(min(all_idx))[2]}   latest: {inv_period(max(all_idx))[2]}")
    # show one symbol's parsed series as a sanity check
    for sym, v in data.items():
        if len(v) >= 6:
            print(f"  e.g. {sym}: " + ", ".join(inv_period(r['idx'])[2] for r in v[-6:]))
            break


def main():
    if not URL:
        sys.exit("DATABASE_URL not set")
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarters", type=int, default=4)
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--diag", action="store_true")
    args = ap.parse_args()
    import psycopg2
    conn = psycopg2.connect(URL); conn.autocommit = False
    cur = conn.cursor()
    if args.diag:
        run_diag(cur)
    elif args.backtest:
        run_backtest(cur)
    else:
        run_compute(cur, conn, args.quarters)
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
