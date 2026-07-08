#!/usr/bin/env python3
"""
compute_quality_flags.py — the Laser-pattern red-flag layer, from our own
annual_financials (10-yr history per company, current as of tonight).

Per listed IPO (matched by symbol into annual_financials), from its last 4 FYs:
  revenue_cagr_3y, profit_cagr_3y, debt_equity(latest)   -> written (Rule 1)
  FLAGS: pat_surge_on_rev_decline (PAT +25%+ while revenue fell)
         debt_spike (borrowings +30%+ last FY)
         margin_jump (EBITDA margin +300bps+ last FY)
         de_above_1 (debt/equity > 1)
  -> operator_risk_flags = 'QF:n|flag1,flag2' (NULL only)

Then the EVIDENCE (read-only print): quality-flag count x gap bucket vs the
d10 outcome — does the market already price the polish, or do flags predict?

  python _scripts/compute_quality_flags.py            # dry run + backtest
  python _scripts/compute_quality_flags.py --apply
"""
import os, sys, argparse

def cagr(a, b, yrs):
    try:
        a, b = float(a), float(b)
        if a <= 0 or b <= 0 or yrs <= 0: return None
        return round(((b / a) ** (1 / yrs) - 1) * 100, 1)
    except (TypeError, ValueError):
        return None

def flags_from(fys):
    """fys: list of dicts oldest->newest with rev, pat, ebitda, borrowings, net_worth."""
    out = []
    if len(fys) < 2: return None, None, None, out
    p, c = fys[-2], fys[-1]
    rg = cagr(fys[0]["rev"], c["rev"], len(fys) - 1)
    pg = cagr(fys[0]["pat"], c["pat"], len(fys) - 1)
    de = None
    try:
        if c["net_worth"] and float(c["net_worth"]) > 0 and c["borrowings"] is not None:
            de = round(float(c["borrowings"]) / float(c["net_worth"]), 2)
    except (TypeError, ValueError):
        pass
    try:
        if p["rev"] and c["rev"] and p["pat"] and c["pat"]:
            if float(c["rev"]) < float(p["rev"]) and float(c["pat"]) > 1.25 * float(p["pat"]):
                out.append("pat_surge_on_rev_decline")
    except (TypeError, ValueError): pass
    try:
        if p["borrowings"] and c["borrowings"] and float(c["borrowings"]) > 1.30 * float(p["borrowings"]):
            out.append("debt_spike")
    except (TypeError, ValueError): pass
    try:
        m_p = float(p["ebitda"]) / float(p["rev"]) if p["ebitda"] and p["rev"] else None
        m_c = float(c["ebitda"]) / float(c["rev"]) if c["ebitda"] and c["rev"] else None
        if m_p is not None and m_c is not None and (m_c - m_p) * 100 >= 3:
            out.append("margin_jump")
    except (TypeError, ValueError, ZeroDivisionError): pass
    if de is not None and de > 1: out.append("de_above_1")
    return rg, pg, de, out

def stats(rets):
    n = len(rets)
    if n < 8: return None
    s = sorted(rets)
    return n, sum(1 for r in rets if r > 0) / n * 100, s[n // 2]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='annual_financials'")
    afc = {r[0] for r in cur.fetchall()}
    symc = "symbol" if "symbol" in afc else "nse_symbol"
    col = lambda *names: next((n for n in names if n in afc), None)
    rev, pat = col("revenue", "rev", "sales", "total_income"), col("pat", "net_profit", "profit")
    ebi, bor = col("ebitda", "operating_profit"), col("borrowings", "total_borrowings", "debt")
    nw = col("net_worth", "networth", "equity")
    eqc, res = col("equity_capital", "equity_share_capital"), col("reserves")
    fyc = col("fiscal_year", "fy")
    ebi_expr = f"f.{ebi}" if ebi else ("(COALESCE(f.pbt,0)+COALESCE(f.interest,0)+COALESCE(f.depreciation,0))"
                                       if "pbt" in afc else "NULL")
    nw_expr = f"f.{nw}" if nw else (f"(COALESCE(f.{eqc},0)+COALESCE(f.{res},0))" if eqc and res else "NULL")
    print(f"using: year={fyc} rev={rev} pat={pat} ebitda={'col' if ebi else 'pbt+int+dep'} nw={'col' if nw else 'eq+res'}")
    if not (rev and pat): sys.exit("required columns missing")

    cur.execute(f"""
        SELECT i.id, UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol)), i.listing_gap_pct, i.d10_best_pct,
               ARRAY_AGG(f.{fyc} ORDER BY f.{fyc}), ARRAY_AGG(f.{rev} ORDER BY f.{fyc}),
               ARRAY_AGG(f.{pat} ORDER BY f.{fyc}),
               ARRAY_AGG({ebi_expr} ORDER BY f.{fyc}),
               ARRAY_AGG({f'f.{bor}' if bor else 'NULL'} ORDER BY f.{fyc}),
               ARRAY_AGG({nw_expr} ORDER BY f.{fyc})
        FROM ipo_intelligence i
        JOIN annual_financials f ON UPPER(f.{symc}) = UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol))
        WHERE i.listing_date IS NOT NULL
        GROUP BY 1,2,3,4 HAVING COUNT(*) >= 2""")
    wrote = 0
    dist = {}
    def bucket(g):
        try: g = float(g)
        except (TypeError, ValueError): return "?"
        return "LOW" if g < 4 else ("MID" if g <= 15 else "HIGH")
    for pid, sym, gp, d10, fy, rv, pt, eb, br, nwv in cur.fetchall():
        gb = bucket(gp)
        fys = [dict(rev=rv[i], pat=pt[i], ebitda=eb[i], borrowings=br[i], net_worth=nwv[i])
               for i in range(len(fy))][-4:]
        rg, pg, de, fl = flags_from(fys)
        from psycopg2.extras import Json
        tag = Json({"qf": len(fl), "flags": fl, "src": "annual_financials"})
        if a.apply:
            cur.execute("""UPDATE ipo_intelligence SET
                revenue_cagr_3y = COALESCE(revenue_cagr_3y, %s),
                profit_cagr_3y  = COALESCE(profit_cagr_3y, %s),
                debt_equity     = COALESCE(debt_equity, %s),
                operator_risk_flags = COALESCE(operator_risk_flags, %s)
                WHERE id=%s""", (rg, pg, de, tag, pid))
            wrote += 1
        if d10 is not None:
            key = ("2+ flags" if len(fl) >= 2 else ("1 flag" if fl else "clean"), gb)
            dist.setdefault(key, []).append(float(d10))
    if a.apply: conn.commit()
    print(f"IPOs {'written' if a.apply else 'computable'}: {wrote if a.apply else 'dry'}")
    print("\nEVIDENCE — d10 outcome by quality-flag count (win% / median, n>=8):")
    for (band, gb), rets in sorted(dist.items()):
        st = stats(rets)
        if st: print(f"  {band:9} x {gb:4}  n={st[0]:<3} win={st[1]:5.1f}%  med={st[2]:+6.1f}")
    allb = {}
    for (band, _), rets in dist.items(): allb.setdefault(band, []).extend(rets)
    print("  --- pooled ---")
    for band, rets in sorted(allb.items()):
        st = stats(rets)
        if st: print(f"  {band:9}         n={st[0]:<3} win={st[1]:5.1f}%  med={st[2]:+6.1f}")
    if not a.apply: print("\nDRY RUN — --apply writes CAGRs/DE/flags (fill-empty only).")
    conn.close()

if __name__ == "__main__":
    main()
