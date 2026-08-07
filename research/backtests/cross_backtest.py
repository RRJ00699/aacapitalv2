#!/usr/bin/env python3
"""
cross_backtest.py — READ-ONLY two-factor cross-tab on the EXACT founding outcome:
entry = listing open, exit = best close within 10 SESSIONS (not calendar days).
Fixes the +30-calendar-day inflation in the earlier ad-hoc SQL cross.

  venv/bin/python research/backtests/cross_backtest.py --a bucket --b size
  venv/bin/python research/backtests/cross_backtest.py --a bucket --b peer
Factors: bucket | size | peer | pe | ofs | qib | regime
Cells with n<10 are suppressed; n>=30 tagged SIGNAL, else HINT. Era win%% shown
so a one-regime cell can't pose as an edge. Zero writes.
"""
import os, sys, argparse
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
HOLD = 10

def buck(v, edges, labels):
    if v is None: return None
    v = float(v)
    for e, l in zip(edges, labels):
        if v < e: return l
    return labels[-1]

REG = {
    "size":   (["issue_size_cr"], lambda r: buck(r.get("issue_size_cr"), [150, 500, 2000], ["<150", "150-500", "500-2000", ">2000cr"])),
    "bucket": (["gap_bucket"],    lambda r: (r.get("gap_bucket") or "").upper() or None),
    "peer":   (["ipo_pe", "peer_median_pe"], lambda r: (None if not r.get("ipo_pe") or not r.get("peer_median_pe") or float(r["peer_median_pe"]) <= 0
                                                       else buck(float(r["ipo_pe"]) / float(r["peer_median_pe"]), [0.6, 1.0, 1.5], ["CHEAP", "DISC", "PREM", "RICH"]))),
    "pe":     (["ipo_pe"],        lambda r: buck(r.get("ipo_pe"), [15, 30, 60], ["PE<15", "PE15-30", "PE30-60", "PE>60"])),
    "ofs":    (["ofs_cr", "fresh_cr"], lambda r: (None if (r.get("ofs_cr") is None and r.get("fresh_cr") is None) or (float(r.get("ofs_cr") or 0) + float(r.get("fresh_cr") or 0)) <= 0
                                                  else buck(float(r.get("ofs_cr") or 0) / (float(r.get("ofs_cr") or 0) + float(r.get("fresh_cr") or 0)) * 100, [10, 60, 90], ["FRESH", "MIXED", "OFS60-90", "PURE-OFS"]))),
    "qib":    (["final_qib"],     lambda r: buck(r.get("final_qib"), [1, 5, 25], ["QIB<1", "QIB1-5", "QIB5-25", "QIB>25"])),
    "regime": (["regime_at_listing"],        lambda r: (str(r.get("regime_at_listing") or "").upper() or None)),
}

def era_of(d):
    return "?" if d is None else ("<=2021" if d.year <= 2021 else ("2022-24" if d.year <= 2024 else "2025+"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, choices=REG); ap.add_argument("--b", required=True, choices=REG)
    ap.add_argument("--hold", type=int, default=HOLD)
    args = ap.parse_args()
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(DB, connect_timeout=20)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_consolidated'")
    cols = {r["column_name"] for r in cur.fetchall()}
    need = set(REG[args.a][0]) | set(REG[args.b][0])
    miss = [c for c in need if c not in cols]
    if miss: sys.exit(f"columns absent in consolidated: {miss}")
    sym = "symbol_final" if "symbol_final" in cols else "nse_symbol"
    open_col = next((c for c in ("listing_open", "listing_open_price") if c in cols), None)
    sel = sorted(need | {sym, "listing_date"} | ({open_col} if open_col else set()))
    cur.execute(f"SELECT {', '.join(sel)} FROM ipo_consolidated WHERE listing_date IS NOT NULL")
    rows = cur.fetchall()
    cur.execute(f"""SELECT UPPER(REGEXP_REPLACE(c.{sym},'\\.NS$','')) s, p.date, p.open, p.close
                    FROM ipo_consolidated c JOIN price_candles p
                      ON UPPER(p.symbol)=UPPER(REGEXP_REPLACE(c.{sym},'\\.NS$',''))
                     AND p.date>=c.listing_date AND p.date<=c.listing_date+30
                    WHERE c.listing_date IS NOT NULL ORDER BY s, p.date""")
    cnd = {}
    for r in cur.fetchall():
        cnd.setdefault(r["s"], []).append(r)
    conn.close()

    fa, fb = REG[args.a][1], REG[args.b][1]
    cells, base = {}, []
    for r in rows:
        cs = cnd.get((r.get(sym) or "").upper().replace(".NS", "")) or []
        if not cs: continue
        entry = float(r[open_col]) if open_col and r.get(open_col) else float(cs[0]["open"] or 0)
        closes = [float(x["close"]) for x in cs[:args.hold] if x["close"]]
        if entry <= 0 or len(closes) < 3: continue
        ret = (max(closes) - entry) / entry * 100
        rec = (ret, ret > 0 if max(closes) != entry else False, era_of(r["listing_date"]))
        rec = (ret, max(closes) > entry, era_of(r["listing_date"]))
        base.append(rec)
        A, B = fa(r), fb(r)
        if A and B:
            cells.setdefault((A, B), []).append(rec)

    n = len(base); w = sum(1 for _, win, _ in base if win)
    med = sorted(x for x, _, _ in base)[n // 2]
    print(f"HOLD={args.hold} sessions | BASELINE n={n} win={w/n*100:.0f}% med=+{med:.1f}%")
    print(f"{args.a.upper()} x {args.b.upper()}  (cells n>=10)\n" + "-" * 86)
    print(f"{'A':10} {'B':10} {'n':>4} {'win%':>6} {'med%':>7}  tag     eras")
    for (A, B), g in sorted(cells.items(), key=lambda kv: (-len(kv[1]))):
        gn = len(g)
        if gn < 10: continue
        gw = sum(1 for _, win, _ in g if win) / gn * 100
        gm = sorted(x for x, _, _ in g)[gn // 2]
        tag = "SIGNAL" if gn >= 30 else "HINT  "
        eras = []
        for e in ("<=2021", "2022-24", "2025+"):
            ge = [x for x in g if x[2] == e]
            eras.append(f"{e}:{sum(1 for _, win, _ in ge if win)/len(ge)*100:.0f}%({len(ge)})" if len(ge) >= 8 else f"{e}:-")
        print(f"{A:10} {B:10} {gn:>4} {gw:>6.1f} {gm:>+7.1f}  {tag}  {' '.join(eras)}")
    print("\nREAD-ONLY. Compare cells against the SAME-HOLD baseline above, not the earlier +30-day SQL.")

if __name__ == "__main__":
    main()
