#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backtest_quality_score.py — evidence table for the Quality Score spec.
Computes SPEC v1 candidate factors on every historical IPO with outcomes and
prints win-rate/mean-d10 per factor and per band. READ-ONLY. Run on PC:
    python _scripts/backtest_quality_score.py
"""
import json, os
import psycopg2

TIER1 = ("kotak","icici","axis","jm financial","citigroup","morgan stanley",
         "goldman","jefferies","bofa","nomura","motilal")

def fnum(v):
    """psycopg2 returns NUMERIC as Decimal — coerce every numeric input once,
    at the boundary (mixing Decimal and float crashed the first 407-row run)."""
    if v is None: return None
    try: return float(v)
    except (TypeError, ValueError): return None

def factors(r):
    (rhp, qp, pledge, ofs_cr, fresh_cr, ipo_pe, peer_pe,
     roe, cagr, de, sbi, brlm) = r
    pledge, ofs_cr, fresh_cr = fnum(pledge), fnum(ofs_cr), fnum(fresh_cr)
    ipo_pe, peer_pe, roe, cagr, de = fnum(ipo_pe), fnum(peer_pe), fnum(roe), fnum(cagr), fnum(de)
    f, pts = {}, 0.0
    g = lit = integ = rel = conc = None
    if rhp:
        db = (rhp.get("db_fields") or {}) if isinstance(rhp, dict) else {}
        g = db.get("quality_gate"); lit = db.get("criminal_litigation")
        integ = db.get("numbers_integrity_flag"); rel = db.get("related_party_concern")
        conc = db.get("customer_concentration_high")
    f["rhp_gate"] = 20 if g == "clean" else 8 if g == "watch" else 0 if g else None
    f["no_criminal"] = None if lit is None else (6 if lit is False else 0)
    f["numbers_ok"] = None if integ is None else (5 if integ in ("ok","clean") else 0)
    f["related_ok"] = None if rel is None else (4 if rel in (False,"none",None) else 0)
    f["concentration_ok"] = None if conc is None else (5 if conc is False else 0)
    f["promoter_quality"] = None if qp is None else (10 if qp else 0)
    f["pledge_low"] = None if pledge is None else (5 if pledge < 5 else 0)
    tot = (ofs_cr or 0) + (fresh_cr or 0)
    ofs_pct = (ofs_cr / tot * 100) if (tot and ofs_cr is not None) else None
    f["structure"] = None if ofs_pct is None else (10 if ofs_pct < 20 else 5 if ofs_pct <= 60 else 0)
    ratio = (ipo_pe / peer_pe) if (ipo_pe and peer_pe and peer_pe > 0) else None
    f["valuation"] = None if ratio is None else (10 if ratio < 0.8 else 6 if ratio <= 1.2 else 3 if ratio <= 1.5 else 0)
    f["roe"] = None if roe is None else (5 if roe >= 18 else 0)
    f["cagr"] = None if cagr is None else (4 if cagr >= 20 else 0)
    f["de"] = None if de is None else (3 if de <= 0.5 else 0)
    f["sbi"] = None if not sbi else (5 if "subscribe" in str(sbi).lower() else 0)
    f["brlm_t1"] = None if not brlm else (3 if any(t in str(brlm).lower() for t in TIER1) else 0)
    have_w = sum(w for k, w in
        [("rhp_gate",20),("no_criminal",6),("numbers_ok",5),("related_ok",4),
         ("concentration_ok",5),("promoter_quality",10),("pledge_low",5),
         ("structure",10),("valuation",10),("roe",5),("cagr",4),("de",3),
         ("sbi",5),("brlm_t1",3)] if f[k] is not None)
    pts = sum(v for v in f.values() if v is not None)
    score = round(pts / have_w * 100) if have_w else None
    conf = min(100, round(have_w / 85 * 100))  # cap: full 14-factor set exceeds 85w -> 112% (fixed 2026-07-18)
    return f, score, conf

def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    # Every column below verified against live schema (2026-07-16 column dump +
    # ipo-command route): quality_promoter lives on ipo_verdicts (v.), NOT
    # intelligence — the first run of this script crashed guessing otherwise.
    cur.execute("""
      SELECT ri.full_json, v.quality_promoter, i.promoter_pledge_pct,
             i.ofs_cr, i.fresh_issue_cr, i.ipo_pe, i.peer_median_pe,
             i.roe, i.revenue_cagr_3y, i.debt_equity, i.sbi_rating, i.brlm_names,
             i.return_listing_open, i.d10_best_pct
      FROM ipo_intelligence i
      LEFT JOIN ipo_rhp_intel ri ON ri.company_name = i.company_name
      LEFT JOIN ipo_verdicts v  ON v.company_name  = i.company_name
      WHERE i.return_listing_open IS NOT NULL""")
    rows = cur.fetchall(); conn.close()
    print(f"historical IPOs with outcomes: {len(rows)}")
    factab, bands = {}, {}
    for r in rows:
        f, score, conf = factors(r[:12])
        ret_open, d10 = fnum(r[12]), fnum(r[13])
        if ret_open is None: continue
        win = ret_open > 0
        for k, v in f.items():
            if v is None: continue
            hit = v > 0
            key = (k, hit)
            a = factab.setdefault(key, [0, 0, 0.0, 0])
            a[0] += 1; a[1] += 1 if win else 0
            if d10 is not None: a[2] += d10; a[3] += 1
        if score is not None and conf >= 40:
            b = "STRONG" if score >= 75 else "SOLID" if score >= 55 else "MIXED" if score >= 35 else "WEAK"
            a = bands.setdefault(b, [0, 0, 0.0, 0])
            a[0] += 1; a[1] += 1 if win else 0
            if d10 is not None: a[2] += d10; a[3] += 1
    print(f"\n{'factor':<20}{'state':<6}{'n':>5}{'win%':>7}{'mean_d10':>10}")
    for (k, hit), (n, w, dsum, dn) in sorted(factab.items()):
        print(f"{k:<20}{'PASS' if hit else 'fail':<6}{n:>5}{w/n*100:>6.1f}%{(dsum/dn if dn else 0):>9.1f}%")
    print(f"\n{'band':<8}{'n':>5}{'win%':>7}{'mean_d10':>10}   (conf>=40 only)")
    for b in ("STRONG","SOLID","MIXED","WEAK"):
        if b in bands:
            n, w, dsum, dn = bands[b]
            print(f"{b:<8}{n:>5}{w/n*100:>6.1f}%{(dsum/dn if dn else 0):>9.1f}%")
    print("\nNext: review with Rakesh -> adjust weights -> LOCK -> compute step + dial.")

if __name__ == "__main__":
    main()
