#!/usr/bin/env python3
"""
compute_financial_dna.py — institutional Financial-DNA engine over 10yr annual_financials.

Deterministic and fully explainable (no ML, no black box — every score traces to named
metrics and thresholds). Reads annual_financials, engineers features across the whole
history (not single-year snapshots), scores 7 dimensions, detects green/red flags, and
emits a 0-100 DNA score + investment grade with reasons.

Sub-scores (master-prompt steps 2-12, scoped to what Screener data supports):
  Growth · Profitability · Cash Flow · Balance Sheet · Capital Allocation · Efficiency ·
  Earnings Quality.  (Governance is out — not in Screener financials; wire pledge/holding
  from ownership tables later. Risk is derived from red-flag severity.)

Usage:
  python _scripts/compute_financial_dna.py --dir ./samples            # in-memory, prints reports, NO DB
  python _scripts/compute_financial_dna.py --symbol MARICO            # one symbol from DB
  python _scripts/compute_financial_dna.py                            # whole universe -> financial_dna
Env: DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, json, glob, argparse

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

# ── small numeric helpers ──
def sdiv(a, b):
    try:
        return a / b if (a is not None and b not in (None, 0)) else None
    except Exception:
        return None

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def lin(v, lo, hi):
    """map v: lo->0, hi->100 (clamped). hi<lo means lower-is-better."""
    if v is None:
        return None
    if hi == lo:
        return 50.0
    return clamp((v - lo) / (hi - lo) * 100, 0, 100)

def avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None

def cagr(vals):
    vals = [v for v in vals if v is not None]
    if len(vals) < 2 or vals[0] is None or vals[0] <= 0 or vals[-1] <= 0:
        return None
    return (vals[-1] / vals[0]) ** (1 / (len(vals) - 1)) - 1

def trend(vals):
    """early-half mean vs late-half mean → ('improving'|'stable'|'declining', pct_change)."""
    vals = [v for v in vals if v is not None]
    if len(vals) < 4:
        return "n/a", None
    h = len(vals) // 2
    early, late = avg(vals[:h]), avg(vals[-h:])
    base = abs(early) if early else 1
    ch = (late - early) / base
    return ("improving" if ch > 0.1 else "declining" if ch < -0.1 else "stable"), ch


def col(years, c):
    return [years[fy].get(c) for fy in sorted(years)]


def engineer(years):
    """Build the feature dictionary from the 10yr annual series."""
    fys = sorted(years)
    L = fys[-1]
    g = years[L]
    f = {}

    sales = col(years, "sales"); pat = col(years, "net_profit")
    equity = col(years, "equity_capital"); reserves = col(years, "reserves")
    borrow = col(years, "borrowings"); cfo = col(years, "cfo")
    netblock = col(years, "net_block"); cwip = col(years, "cwip")
    deprec = col(years, "depreciation"); interest = col(years, "interest")
    pbt = col(years, "pbt"); ta = col(years, "total_assets")
    inv = col(years, "inventory"); recv = col(years, "receivables")
    shares = col(years, "no_of_shares"); div = col(years, "dividend_amount")

    nw = [(e or 0) + (r or 0) for e, r in zip(equity, reserves)]
    ebit = [(p or 0) + (i or 0) for p, i in zip(pbt, interest)]
    ebitda = [(e or 0) + (d or 0) for e, d in zip(ebit, deprec)]

    # CAGRs (growth across the full window)
    f["revenue_cagr"] = cagr(sales)
    f["pat_cagr"] = cagr(pat)
    f["bookvalue_cagr"] = cagr([x for x in nw if x > 0] or [None])
    f["ocf_cagr"] = cagr([c for c in cfo if c is not None])

    # latest-year profitability
    f["roe"] = sdiv(pat[-1], nw[-1]) if nw[-1] else None
    f["roce"] = sdiv(ebit[-1], (nw[-1] or 0) + (borrow[-1] or 0))
    f["roa"] = sdiv(pat[-1], ta[-1])
    f["net_margin"] = sdiv(pat[-1], sales[-1])
    f["ebitda_margin"] = sdiv(ebitda[-1], sales[-1])

    # balance sheet
    f["debt_equity"] = sdiv(borrow[-1], nw[-1]) if nw[-1] and nw[-1] > 0 else None
    f["debt_ebitda"] = sdiv(borrow[-1], ebitda[-1]) if ebitda[-1] and ebitda[-1] > 0 else None
    f["interest_coverage"] = sdiv(ebit[-1], interest[-1]) if interest[-1] else None

    # cash flow / earnings quality (cumulative is more robust than 1yr)
    cfo_sum = sum(c for c in cfo if c is not None)
    pat_sum = sum(p for p in pat if p is not None)
    f["ocf_pat_cum"] = sdiv(cfo_sum, pat_sum) if pat_sum > 0 else None
    # capex ≈ Δnet_block + Δcwip + depreciation ; FCF ≈ cfo - capex (per year)
    fcf_years = []
    for i in range(1, len(fys)):
        if None in (netblock[i], netblock[i-1], deprec[i], cfo[i]):
            continue
        capex = (netblock[i] - netblock[i-1]) + ((cwip[i] or 0) - (cwip[i-1] or 0)) + (deprec[i] or 0)
        fcf_years.append(cfo[i] - capex)
    f["fcf_positive_share"] = sdiv(sum(1 for x in fcf_years if x > 0), len(fcf_years)) if fcf_years else None
    f["fcf_margin"] = sdiv(fcf_years[-1], sales[-1]) if fcf_years else None

    # efficiency
    f["inventory_days"] = sdiv((inv[-1] or 0) * 365, sales[-1])
    f["receivable_days"] = sdiv((recv[-1] or 0) * 365, sales[-1])
    f["asset_turnover"] = sdiv(sales[-1], ta[-1])

    # capital allocation signals
    f["share_cagr"] = cagr([s for s in shares if s])
    f["div_trend"], _ = trend(div)
    f["borrow_trend"], f["borrow_ch"] = trend(borrow)

    # trends used by flags
    f["roce_series"] = [sdiv(e, (n or 0) + (b or 0)) for e, n, b in zip(ebit, nw, borrow)]
    f["roce_trend"], _ = trend(f["roce_series"])
    f["margin_trend"], _ = trend([sdiv(p, s) for p, s in zip(pat, sales)])
    f["recv_cagr"] = cagr([r for r in recv if r is not None])
    f["inv_cagr"] = cagr([i for i in inv if i is not None])
    f["years"] = len(fys)
    f["_raw"] = {"sales": sales, "pat": pat, "nw": nw, "borrow": borrow, "cfo": cfo, "cwip": cwip, "netblock": netblock}
    return f


def score(years):
    f = engineer(years)

    growth = avg([lin(f["revenue_cagr"], 0, 0.25), lin(f["pat_cagr"], 0, 0.25),
                  lin(f["bookvalue_cagr"], 0, 0.20), lin(f["ocf_cagr"], 0, 0.25)])
    profitability = avg([lin(f["roe"], 0, 0.25), lin(f["roce"], 0, 0.30),
                         lin(f["net_margin"], 0, 0.20), lin(f["ebitda_margin"], 0, 0.30)])
    cashflow = avg([lin(f["ocf_pat_cum"], 0.3, 1.2), lin(f["fcf_positive_share"], 0.3, 1.0),
                    lin(f["fcf_margin"], 0, 0.12)])
    balancesheet = avg([lin(f["debt_equity"], 1.5, 0.0), lin(f["interest_coverage"], 1, 8),
                        lin(f["debt_ebitda"], 4, 0.0)])
    capalloc = avg([lin(f["borrow_ch"], 0.3, -0.5) if f["borrow_ch"] is not None else None,
                    100 if f["div_trend"] == "improving" else 60 if f["div_trend"] == "stable" else 30,
                    lin(f["share_cagr"], 0.05, -0.02) if f["share_cagr"] is not None else 50])
    efficiency = avg([lin(f["inventory_days"], 180, 15), lin(f["receivable_days"], 120, 10),
                      lin(f["asset_turnover"], 0.3, 1.5)])
    earnings_q = avg([lin(f["ocf_pat_cum"], 0.4, 1.1),
                      100 if f["margin_trend"] == "improving" else 60 if f["margin_trend"] == "stable" else 30])

    subs = {"growth": growth, "profitability": profitability, "cashflow": cashflow,
            "balancesheet": balancesheet, "capalloc": capalloc, "efficiency": efficiency,
            "earnings_quality": earnings_q}

    W = {"growth": .25, "profitability": .20, "cashflow": .15, "balancesheet": .15,
         "capalloc": .10, "efficiency": .05, "earnings_quality": .10}
    num = sum((subs[k] or 0) * w for k, w in W.items())
    den = sum(w for k, w in W.items() if subs[k] is not None)
    dna = round(num / den, 1) if den else None

    grade = ("AAA+" if dna >= 85 else "AAA" if dna >= 78 else "AA" if dna >= 70 else
             "A" if dna >= 62 else "BBB" if dna >= 52 else "BB" if dna >= 44 else
             "B" if dna >= 36 else "Avoid") if dna is not None else "N/A"

    green, red = flags(f)
    risk = clamp(100 - 18 * sum(1 for _, sev in red if sev in ("High", "Critical")) - 7 * len(red), 0, 100)
    subs["risk"] = risk
    return {"dna_score": dna, "grade": grade, "subs": {k: (round(v, 1) if v is not None else None) for k, v in subs.items()},
            "green_flags": green, "red_flags": red, "features": f}


def flags(f):
    green, red = [], []
    def g(msg): green.append(msg)
    def r(msg, sev): red.append((msg, sev))

    if (f["revenue_cagr"] or 0) > 0.15: g(f"Revenue compounding {f['revenue_cagr']*100:.0f}% CAGR")
    if (f["pat_cagr"] or 0) > 0.20: g(f"PAT compounding {f['pat_cagr']*100:.0f}% CAGR")
    if f["roce"] and f["roce"] > 0.20: g(f"High ROCE {f['roce']*100:.0f}%")
    if f["roce_trend"] == "improving": g("ROCE trending up over the decade")
    if f["ocf_pat_cum"] and f["ocf_pat_cum"] >= 1.0: g(f"Operating cash exceeds PAT (cum OCF/PAT {f['ocf_pat_cum']:.2f}) — clean earnings")
    if f["borrow_trend"] == "declining": g("Debt reduced over the period")
    if f["fcf_positive_share"] and f["fcf_positive_share"] >= 0.7: g("Positive free cash flow in most years")
    if f["margin_trend"] == "improving": g("Net margins expanding")
    if (f["bookvalue_cagr"] or 0) > 0.15: g(f"Book value compounding {f['bookvalue_cagr']*100:.0f}%")
    if f["share_cagr"] is not None and f["share_cagr"] < -0.005: g("Share count falling — buybacks")

    if f["ocf_pat_cum"] is not None and f["ocf_pat_cum"] < 0.6:
        r(f"Earnings quality risk: cumulative OCF only {f['ocf_pat_cum']*100:.0f}% of PAT",
          "Critical" if f["ocf_pat_cum"] < 0.4 else "High")
    if f["recv_cagr"] is not None and f["revenue_cagr"] is not None and f["recv_cagr"] > f["revenue_cagr"] + 0.10:
        r("Receivables growing faster than sales", "Medium")
    if f["inv_cagr"] is not None and f["revenue_cagr"] is not None and f["inv_cagr"] > f["revenue_cagr"] + 0.10:
        r("Inventory growing faster than sales", "Medium")
    if f["borrow_trend"] == "improving" and (f["revenue_cagr"] or 0) < 0.05:
        r("Debt rising while revenue stagnates", "High")
    if f["interest_coverage"] is not None and f["interest_coverage"] < 2:
        r(f"Weak interest coverage ({f['interest_coverage']:.1f}x)", "High")
    if f["fcf_positive_share"] is not None and f["fcf_positive_share"] < 0.4:
        r("Persistent negative free cash flow", "High")
    if f["share_cagr"] is not None and f["share_cagr"] > 0.03:
        r(f"Equity dilution ({f['share_cagr']*100:.0f}%/yr share growth)", "Medium")
    if f["roce_trend"] == "declining":
        r("ROCE deteriorating over the decade", "Medium")
    if f["margin_trend"] == "declining":
        r("Margin compression", "Medium")
    return green, red


def report(symbol, name, years):
    if len(years) < 4:
        print(f"\n{symbol}: only {len(years)} years — skipped")
        return
    out = score(years)
    print(f"\n{'='*64}\n{symbol}  {name or ''}   DNA {out['dna_score']}  [{out['grade']}]   ({out['features']['years']}yr)")
    s = out["subs"]
    print("  " + "  ".join(f"{k}:{s[k]}" for k in ["growth","profitability","cashflow","balancesheet","capalloc","efficiency","earnings_quality","risk"]))
    if out["green_flags"]:
        print("  GREEN:")
        for x in out["green_flags"][:6]: print(f"    + {x}")
    if out["red_flags"]:
        print("  RED:")
        for x, sev in out["red_flags"][:6]: print(f"    - [{sev}] {x}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="sample mode: parse *_10yr.xlsx in dir, print, no DB")
    ap.add_argument("--symbol")
    ap.add_argument("--history", action="store_true",
                    help="point-in-time: grade each company as-of each past year (no look-ahead) -> financial_dna_history")
    args = ap.parse_args()

    if args.dir:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import import_screener_financials as imp
        for p in sorted(glob.glob(os.path.join(args.dir, "*.xlsx"))):
            name, years = imp.parse_file(p)
            report(imp.symbol_from_path(p), name, {fy: years[fy] for fy in years})
        return

    if not URL:
        sys.exit("DATABASE_URL not set")
    import psycopg2
    conn = psycopg2.connect(URL); cur = conn.cursor()
    cols_q = ("SELECT symbol, fiscal_year, sales, net_profit, equity_capital, reserves, borrowings, cfo, "
              "net_block, cwip, depreciation, interest, pbt, total_assets, inventory, receivables, "
              "no_of_shares, dividend_amount, company_name FROM annual_financials")
    if args.symbol:
        cols_q += " WHERE symbol = %s"
        cur.execute(cols_q, (args.symbol.upper(),))
    else:
        cur.execute(cols_q)
    fields = ["sales","net_profit","equity_capital","reserves","borrowings","cfo","net_block","cwip",
              "depreciation","interest","pbt","total_assets","inventory","receivables","no_of_shares","dividend_amount"]
    by_sym, names = {}, {}
    for row in cur.fetchall():
        sym, fy = row[0], row[1]
        by_sym.setdefault(sym, {})[fy] = {
            fields[i]: (float(row[2 + i]) if row[2 + i] is not None else None) for i in range(len(fields))
        }
        names[sym] = row[-1]

    from psycopg2.extras import execute_values

    # ── point-in-time history: grade as-of each year using only fiscal_year <= Y ──
    if args.history:
        cur.execute("""CREATE TABLE IF NOT EXISTS financial_dna_history (
            symbol TEXT NOT NULL, as_of_year INT NOT NULL, dna_score NUMERIC(5,1), grade TEXT,
            growth NUMERIC(5,1), profitability NUMERIC(5,1), cashflow NUMERIC(5,1),
            balancesheet NUMERIC(5,1), capalloc NUMERIC(5,1), efficiency NUMERIC(5,1),
            earnings_quality NUMERIC(5,1), risk NUMERIC(5,1), years INT,
            computed_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE (symbol, as_of_year))""")
        conn.commit()
        hrows = []
        for sym, years in by_sym.items():
            for Y in sorted(years):
                sub = {fy: years[fy] for fy in years if fy <= Y}
                if len(sub) < 5:                      # need a few years for a meaningful grade
                    continue
                o = score(sub); s = o["subs"]
                hrows.append((sym, Y, o["dna_score"], o["grade"], s["growth"], s["profitability"],
                              s["cashflow"], s["balancesheet"], s["capalloc"], s["efficiency"],
                              s["earnings_quality"], s["risk"], o["features"]["years"]))
        execute_values(cur, """INSERT INTO financial_dna_history (symbol, as_of_year, dna_score, grade,
            growth, profitability, cashflow, balancesheet, capalloc, efficiency, earnings_quality, risk, years)
            VALUES %s ON CONFLICT (symbol, as_of_year) DO UPDATE SET dna_score=EXCLUDED.dna_score,
            grade=EXCLUDED.grade, growth=EXCLUDED.growth, profitability=EXCLUDED.profitability,
            cashflow=EXCLUDED.cashflow, balancesheet=EXCLUDED.balancesheet, capalloc=EXCLUDED.capalloc,
            efficiency=EXCLUDED.efficiency, earnings_quality=EXCLUDED.earnings_quality, risk=EXCLUDED.risk,
            years=EXCLUDED.years, computed_at=NOW()""", hrows, page_size=1000)
        conn.commit()
        print(f"financial_dna_history: {len(hrows):,} vintage grades across {len({r[0] for r in hrows}):,} companies "
              f"(as-of each year, fiscal_year<=Y only — no look-ahead).")
        cur.close(); conn.close()
        return

    cur.execute("""CREATE TABLE IF NOT EXISTS financial_dna (
        symbol TEXT PRIMARY KEY, company_name TEXT, dna_score NUMERIC(5,1), grade TEXT,
        growth NUMERIC(5,1), profitability NUMERIC(5,1), cashflow NUMERIC(5,1),
        balancesheet NUMERIC(5,1), capalloc NUMERIC(5,1), efficiency NUMERIC(5,1),
        earnings_quality NUMERIC(5,1), risk NUMERIC(5,1),
        green_flags JSONB, red_flags JSONB, years INT, computed_at TIMESTAMPTZ DEFAULT NOW())""")
    conn.commit()

    from psycopg2.extras import execute_values
    rows = []
    for sym, years in by_sym.items():
        if len(years) < 4:
            continue
        o = score(years); s = o["subs"]
        rows.append((sym, names.get(sym), o["dna_score"], o["grade"], s["growth"], s["profitability"],
                     s["cashflow"], s["balancesheet"], s["capalloc"], s["efficiency"], s["earnings_quality"],
                     s["risk"], json.dumps(o["green_flags"]), json.dumps(o["red_flags"]), o["features"]["years"]))
    execute_values(cur, """INSERT INTO financial_dna (symbol, company_name, dna_score, grade, growth, profitability,
        cashflow, balancesheet, capalloc, efficiency, earnings_quality, risk, green_flags, red_flags, years)
        VALUES %s ON CONFLICT (symbol) DO UPDATE SET company_name=EXCLUDED.company_name, dna_score=EXCLUDED.dna_score,
        grade=EXCLUDED.grade, growth=EXCLUDED.growth, profitability=EXCLUDED.profitability, cashflow=EXCLUDED.cashflow,
        balancesheet=EXCLUDED.balancesheet, capalloc=EXCLUDED.capalloc, efficiency=EXCLUDED.efficiency,
        earnings_quality=EXCLUDED.earnings_quality, risk=EXCLUDED.risk, green_flags=EXCLUDED.green_flags,
        red_flags=EXCLUDED.red_flags, years=EXCLUDED.years, computed_at=NOW()""", rows, page_size=500)
    conn.commit()
    print(f"financial_dna: scored {len(rows):,} companies.")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
