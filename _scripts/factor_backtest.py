#!/usr/bin/env python3
"""
factor_backtest.py — READ-ONLY factor-lift harness for the 10-point IPO thesis.

Zero writes. Pure SELECT against ipo_consolidated + price_candles + ipo_intelligence.
For each factor it prints a lift table vs the all-IPO baseline, with guardrails:
  * n >= 30  -> SIGNAL      * 10-29 -> HINT      * < 10 -> suppressed
  * era consistency: win%% shown for <=2021 / 2022-24 / 2025+ separately —
    a factor that only worked in one era is a regime artifact, not an edge.

OUTCOME (matches the founding backtest): entry = listing open; exit = best close
within 10 sessions; win = exit > entry; ret = (exit-entry)/entry.

Factors mapped to your thesis points:
  F1 issue size buckets (pt 1)          F2 OFS%% of issue (pt 2)
  F3 peer-P/E discount (pt 3/5)         F4 BRLM empirical table (pt 3)
  F5 absolute P/E + ROE (pt 5 — ROE expected to FAIL per prior backtest)
  F6 GMP level + trajectory decay (pt 6)
  F7 QIB subscription + backloaded (pt 4-adjacent, sub-quality)
  F8 anchor count / tier-1 (pt 4 — thin coverage, printed with honest n)
  F9 day-1 close-at-high -> day-2 continuation (pt 9 UC proxy)
  F10 regime x gap bucket (pt 10)
Columns are introspected from information_schema; a factor whose columns are
missing or thinner than 10 rows prints SKIP with the reason — never crashes.

  venv/bin/python _scripts/factor_backtest.py
  venv/bin/python _scripts/factor_backtest.py --csv /root/aac/factor_report.csv
"""
import os, sys, argparse, datetime
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
BASE_HOLD = 10

def buck(v, edges, labels):
    if v is None: return None
    for e, l in zip(edges, labels):
        if v < e: return l
    return labels[-1]

# ---- factor definitions: (name, needed_cols, row -> bucket-label) -----------
def f_size(r):    return buck(r.get("issue_size_cr"), [150, 500, 2000], ["<150cr", "150-500", "500-2000", ">2000cr"])
def f_ofs(r):
    o, f = r.get("ofs_cr"), r.get("fresh_cr")
    if o is None and f is None: return None
    o, f = float(o or 0), float(f or 0)
    if o + f <= 0: return None
    p = o / (o + f) * 100
    return buck(p, [10, 60, 90], ["FRESH(<10%ofs)", "MIXED", "OFS-HEAVY(60-90)", "PURE-OFS(>90)"])
def f_peer(r):
    pe, pm = r.get("ipo_pe"), r.get("peer_median_pe")
    if not pe or not pm or float(pm) <= 0: return None
    x = float(pe) / float(pm)
    return buck(x, [0.6, 1.0, 1.5], ["CHEAP(<0.6x)", "DISC(0.6-1x)", "PREMIUM(1-1.5x)", "RICH(>1.5x)"])
def f_pe(r):      return buck(r.get("ipo_pe"), [15, 30, 60], ["PE<15", "PE15-30", "PE30-60", "PE>60"])
def f_roe(r):     return buck(r.get("roe"), [8, 15, 25], ["ROE<8", "ROE8-15", "ROE15-25", "ROE>25"])
def f_gmp(r):     return buck(r.get("gmp_pct"), [5, 15, 35], ["GMP<5%", "GMP5-15", "GMP15-35", "GMP>35%"])
def f_gmptraj(r):
    a, b = r.get("gmp_t7"), r.get("gmp_t1")
    if a is None or b is None: return None
    d = float(b) - float(a)
    return buck(d, [-5, 2], ["FADING(<-5)", "FLAT", "BUILDING(>+2)"])
def f_qib(r):     return buck(r.get("final_qib"), [1, 5, 25], ["QIB<1x", "QIB1-5", "QIB5-25", "QIB>25x"])
def f_qibback(r):
    v = r.get("qib_backloaded")
    return None if v is None else ("QIB-BACKLOADED" if v else "QIB-EARLY")
def f_anchcnt(r): return buck(r.get("anchor_count"), [10, 30], ["ANCH<10", "ANCH10-30", "ANCH>30"])
def f_ancht1(r):  return buck(r.get("anchor_tier1_count"), [1, 4], ["T1=0", "T1 1-3", "T1>=4"])
def f_regime(r):
    v = (r.get("regime_at_listing") or r.get("regime") or "").strip().upper()
    return v or None
def f_bucket(r):
    v = (r.get("gap_bucket") or "").strip().upper()
    return v or None

FACTORS = [
    ("F1 issue size (pt1)",        ["issue_size_cr"],                 f_size),
    ("F2 OFS share (pt2)",         ["ofs_cr", "fresh_cr"],            f_ofs),
    ("F3 peer-PE discount (pt3)",  ["ipo_pe", "peer_median_pe"],      f_peer),
    ("F5a absolute PE (pt5)",      ["ipo_pe"],                        f_pe),
    ("F5b ROE (pt5, expect null)", ["roe"],                           f_roe),
    ("F6a GMP level (pt6)",        ["gmp_pct"],                       f_gmp),
    ("F6b GMP trajectory (pt6)",   ["gmp_t7", "gmp_t1"],              f_gmptraj),
    ("F7a final QIB (pt4/sub)",    ["final_qib"],                     f_qib),
    ("F7b QIB backloaded",         ["qib_backloaded"],                f_qibback),
    ("F8a anchor count (pt4)",     ["anchor_count"],                  f_anchcnt),
    ("F8b anchor tier-1 (pt4)",    ["anchor_tier1_count"],            f_ancht1),
    ("F10a regime (pt10)",         ["regime_at_listing","gap_bucket"],                                f_regime),
    ("REF gap bucket (baseline)",  ["gap_bucket"],                    f_bucket),
]

def era_of(d):
    if d is None: return "?"
    return "<=2021" if d.year <= 2021 else ("2022-24" if d.year <= 2024 else "2025+")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv"); ap.add_argument("--hold", type=int, default=BASE_HOLD)
    a = ap.parse_args()
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(DB, connect_timeout=20)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_consolidated'")
    cols = {r["column_name"] for r in cur.fetchall()}
    sym_col = "symbol_final" if "symbol_final" in cols else ("nse_symbol" if "nse_symbol" in cols else "symbol")
    open_col = next((c for c in ("listing_open", "listing_open_price", "open_price") if c in cols), None)
    want = {sym_col, "listing_date", "issue_price", "gap_bucket"} | {c for _, need, _ in FACTORS for c in need}
    sel = [c for c in want if c in cols] + ([open_col] if open_col else [])
    cur.execute(f"SELECT {', '.join(sorted(set(sel)))} FROM ipo_consolidated WHERE listing_date IS NOT NULL")
    rows = cur.fetchall()
    print(f"ipo_consolidated: {len(rows)} rows with listing_date | outcome hold={a.hold} sessions")

    # ---- outcomes from candles (one query) ----------------------------------
    cur.execute(f"""
        SELECT UPPER(c.{sym_col}) AS sym, p.date, p.open, p.close
        FROM ipo_consolidated c
        JOIN price_candles p
          ON UPPER(p.symbol) = UPPER(REGEXP_REPLACE(c.{sym_col}, '\\.NS$', ''))
         AND p.date >= c.listing_date AND p.date <= c.listing_date + 30
        WHERE c.listing_date IS NOT NULL AND c.{sym_col} IS NOT NULL
        ORDER BY sym, p.date""")
    cnd = {}
    for r in cur.fetchall():
        cnd.setdefault(r["sym"], []).append(r)
    conn.close()

    data = []
    day2 = []          # (day1_closed_at_high, day2_ret)  — F9
    for r in rows:
        sym = (r.get(sym_col) or "").upper().replace(".NS", "")
        cs = cnd.get(sym) or []
        if not cs: continue
        entry = float(r[open_col]) if open_col and r.get(open_col) else float(cs[0]["open"] or 0)
        if entry <= 0: continue
        closes = [float(x["close"]) for x in cs[:a.hold] if x["close"]]
        if len(closes) < 3: continue
        best = max(closes)
        rec = dict(r)
        rec["_ret"] = (best - entry) / entry * 100
        rec["_win"] = best > entry
        rec["_era"] = era_of(r["listing_date"])
        data.append(rec)
        if len(cs) >= 2 and cs[0]["close"] and cs[1]["close"]:
            d1o, d1c, d2c = float(cs[0]["open"] or 0), float(cs[0]["close"]), float(cs[1]["close"])
            if d1o > 0:
                strong = d1c >= d1o * 1.08          # closed >=8% above open = UC-proxy
                day2.append((strong, (d2c - d1c) / d1c * 100))
    n = len(data)
    if n < 30: sys.exit(f"only {n} IPOs matched candles — check symbol join before trusting anything")
    wins = sum(1 for d in data if d["_win"])
    med = sorted(d["_ret"] for d in data)[n // 2]
    print(f"\nBASELINE: n={n}  win={wins/n*100:.0f}%  median=+{med:.1f}%\n" + "=" * 78)

    out_csv = []
    for name, need, fn in FACTORS:
        missing = [c for c in need if c not in cols]
        if missing:
            print(f"\n{name}: SKIP (columns absent: {missing})"); continue
        groups = {}
        for d in data:
            b = fn(d)
            if b: groups.setdefault(b, []).append(d)
        covered = sum(len(v) for v in groups.values())
        print(f"\n{name}   (coverage {covered}/{n})")
        if covered < 10:
            print("   SKIP — <10 rows with this factor populated"); continue
        for b, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            gn = len(g)
            if gn < 10: continue
            w = sum(1 for d in g if d["_win"]) / gn * 100
            m = sorted(d["_ret"] for d in g)[gn // 2]
            tag = "SIGNAL" if gn >= 30 else "HINT  "
            eras = []
            for e in ("<=2021", "2022-24", "2025+"):
                ge = [d for d in g if d["_era"] == e]
                eras.append(f"{e}:{sum(1 for d in ge if d['_win'])/len(ge)*100:.0f}%({len(ge)})" if len(ge) >= 8 else f"{e}:-")
            print(f"   {b:22} n={gn:<4} win={w:5.1f}%  med={m:+6.1f}%  [{tag}]  {' '.join(eras)}")
            out_csv.append((name, b, gn, round(w, 1), round(m, 1)))

    if day2:
        strong = [r for s, r in day2 if s]; weak = [r for s, r in day2 if not s]
        print(f"\nF9 day-1 strength -> day-2 continuation (pt9, UC-proxy: d1 close >= open+8%)")
        for lbl, g in (("D1-STRONG", strong), ("D1-NORMAL", weak)):
            if len(g) >= 10:
                up = sum(1 for x in g if x > 0) / len(g) * 100
                print(f"   {lbl:22} n={len(g):<4} d2-up={up:5.1f}%  d2-med={sorted(g)[len(g)//2]:+6.1f}%")

    if a.csv:
        with open(a.csv, "w") as f:
            f.write("factor,bucket,n,win_pct,median_pct\n")
            for row in out_csv:
                f.write(",".join(str(x) for x in row) + "\n")
        print(f"\nCSV -> {a.csv}")
    print("\nREAD-ONLY run complete. n>=30 SIGNAL rows are the only actionable lines.")

if __name__ == "__main__":
    main()
