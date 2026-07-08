#!/usr/bin/env python3
"""
anchor_quality_backtest.py — tests anchor QUALITY (not count) vs d10.
Reads anchor_names (JSON) per IPO, strips registrars, tags each anchor as
TIER1 (marquee domestic MFs/insurers + top global/sovereign) or other, scores
the IPO by tier-1 share, and buckets vs d10 — pooled and by gap bucket.

The thesis under test: marquee anchors lift returns; trash-anchored (esp LOW-gap)
IPOs are the losers.

  python _scripts/anchor_quality_backtest.py
"""
import os, re, sys, json

REGISTRARS = ("intime", "kfin", "bigshare", "mas services", "link intime",
              "cameo", "purva", "skyline", "maashitla", "integrated registry",
              "kfintech", "mufg")

TIER1 = ("sbi ", "sbi mutual", "life insurance corp", "lic ", "icici prudential",
         "hdfc ", "kotak ", "nippon india", "axis ", "aditya birla sun life",
         "mirae", "dsp ", "uti ", "franklin", "tata ", "sundaram", "invesco",
         "morgan stanley", "goldman sachs", "blackrock", "abu dhabi investment",
         "government of singapore", "gic ", "monetary authority of singapore",
         "nomura", "fidelity", "capital group", "vanguard", "norges",
         "canada pension", "government pension", "amundi", "hsbc ", "jpmorgan",
         "j.p. morgan", "societe generale", "bnp paribas", "citigroup", "ashoka india")

def clean(names):
    out = []
    for n in names:
        low = n.lower()
        if any(r in low for r in REGISTRARS): continue
        out.append(n)
    return out

def is_tier1(name):
    low = name.lower()
    return any(t in low for t in TIER1)

def stats(rets):
    n = len(rets)
    if n < 8: return None
    s = sorted(rets)
    return n, sum(1 for r in rets if r > 0)/n*100, s[n//2], sum(rets)/n

def main():
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    cur = psycopg2.connect(DB, connect_timeout=20).cursor()
    cur.execute("""SELECT anchor_names, listing_gap_pct, d10_best_pct
                   FROM ipo_intelligence
                   WHERE anchor_names IS NOT NULL AND d10_best_pct IS NOT NULL""")
    rows = cur.fetchall()
    parsed = []
    for names_json, gap, d10 in rows:
        try:
            names = names_json if isinstance(names_json, list) else json.loads(names_json)
        except Exception:
            continue
        names = clean(names)
        if not names: continue
        t1 = sum(1 for n in names if is_tier1(n))
        share = t1 / len(names) * 100
        parsed.append((share, t1, len(names), float(gap) if gap is not None else None, float(d10)))
    print(f"IPOs with usable anchor rosters + outcome: {len(parsed)}\n")
    if len(parsed) < 20:
        print("thin coverage; backfill more anchors then rerun."); return

    def qb(share):
        return "0 tier1" if share == 0 else ("mostly-trash <34%" if share < 34
               else "mixed 34-66%" if share < 67 else "marquee >=67%")
    def gb(g):
        if g is None: return "?"
        return "LOW" if g < 4 else ("MID" if g <= 15 else "HIGH")

    pooled, cross, byabs = {}, {}, {}
    for share, t1, tot, gap, d10 in parsed:
        pooled.setdefault(qb(share), []).append(d10)
        cross.setdefault((qb(share), gb(gap)), []).append(d10)
        byabs.setdefault("has tier1" if t1 > 0 else "zero tier1", []).append(d10)

    print("=== by TIER-1 SHARE (pooled) ===")
    print(f"{'quality':20}{'n':>5}{'win%':>7}{'med':>7}{'mean':>7}")
    for k in ("0 tier1", "mostly-trash <34%", "mixed 34-66%", "marquee >=67%"):
        st = stats(pooled.get(k, []))
        if st: print(f"{k:20}{st[0]:>5}{st[1]:>7.1f}{st[2]:>+7.1f}{st[3]:>+7.1f}")

    print("\n=== has-any-tier1 vs none ===")
    for k in ("zero tier1", "has tier1"):
        st = stats(byabs.get(k, []))
        if st: print(f"  {k:12} n={st[0]:<3} win={st[1]:5.1f}% med={st[2]:+6.1f} mean={st[3]:+6.1f}")

    print("\n=== quality x gap bucket (the thesis: trash LOW-gap = losers) ===")
    for (q, g), v in sorted(cross.items(), key=lambda t: (t[0][1], t[0][0])):
        st = stats(v)
        if st: print(f"  {g:4} {q:20} n={st[0]:<3} win={st[1]:5.1f}% med={st[2]:+6.1f}")
    print("\nBar: n>=30, marquee win-gap >=8pts over trash, direction holds in a gap bucket.")

if __name__ == "__main__":
    main()
