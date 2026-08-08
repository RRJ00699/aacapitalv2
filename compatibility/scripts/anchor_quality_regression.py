#!/usr/bin/env python3
"""
anchor_quality_regression.py — READ-ONLY. The most conclusive test possible on
the anchor rosters we have: treat tier-1 SHARE (0-100%, continuous) as the
predictor of d10, rather than coarse buckets.

Outputs:
  - Pearson & Spearman correlation of tier1_share vs d10 (+ n, rough p-signal)
  - the same, split by issue-size band (isolates the size confound)
  - a simple top-half vs bottom-half share comparison for intuition
Honest about n: prints a WEAK/SUGGESTIVE/NOISE tag based on |r| and sample.

  python _scripts/anchor_quality_regression.py
"""
import os, re, sys, json, math

REGISTRARS = ("intime","kfin","bigshare","mas services","link intime","cameo",
              "purva","skyline","maashitla","integrated registry","kfintech","mufg")
TIER1 = ("sbi ","sbi mutual","life insurance corp","lic ","icici prudential","hdfc ",
         "kotak ","nippon india","axis ","aditya birla sun life","mirae","dsp ","uti ",
         "franklin","tata ","sundaram","invesco","morgan stanley","goldman sachs",
         "blackrock","abu dhabi investment","government of singapore","gic ",
         "monetary authority of singapore","nomura","fidelity","capital group",
         "vanguard","norges","canada pension","government pension","amundi","hsbc ",
         "jpmorgan","j.p. morgan","societe generale","bnp paribas","citigroup","ashoka india")

def clean(names): return [n for n in names if not any(r in n.lower() for r in REGISTRARS)]
def is_t1(n): return any(t in n.lower() for t in TIER1)

def pearson(xs, ys):
    n = len(xs)
    if n < 3: return None
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x-mx)**2 for x in xs)); dy = math.sqrt(sum((y-my)**2 for y in ys))
    if dx == 0 or dy == 0: return None
    return num/(dx*dy)

def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0]*len(v)
        for pos, i in enumerate(order): r[i] = pos
        return r
    return pearson(rank(xs), rank(ys))

def tag(r, n):
    if r is None: return "n/a"
    a = abs(r)
    if n < 20: return "NOISE (n too small)"
    if a < 0.15: return "NO relationship"
    if a < 0.30: return "WEAK"
    if a < 0.50: return "SUGGESTIVE"
    return "STRONG (verify — small n can fluke)"

def main():
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    cur = psycopg2.connect(DB, connect_timeout=20).cursor()
    cur.execute("""SELECT anchor_names, d10_best_pct, issue_size_cr, listing_gap_pct
                   FROM ipo_intelligence
                   WHERE anchor_names IS NOT NULL AND d10_best_pct IS NOT NULL""")
    shares, d10s, sizes, gaps = [], [], [], []
    for names_json, d10, size, gap in cur.fetchall():
        try:
            names = names_json if isinstance(names_json, list) else json.loads(names_json)
        except Exception: continue
        names = clean(names)
        if not names: continue
        shares.append(sum(1 for n in names if is_t1(n))/len(names)*100)
        d10s.append(float(d10))
        sizes.append(float(size) if size is not None else None)
        gaps.append(float(gap) if gap is not None else None)
    n = len(shares)
    print(f"n = {n} IPOs with clean rosters + d10\n")
    if n < 15:
        print("too few for even a regression."); return

    r = pearson(shares, d10s); rs = spearman(shares, d10s)
    print("=== tier-1 SHARE vs d10 (continuous) ===")
    print(f"  Pearson  r = {r:+.3f}   [{tag(r, n)}]")
    print(f"  Spearman r = {rs:+.3f}   [{tag(rs, n)}]")
    mean_share = sum(shares)/n
    hi = [d for s, d in zip(shares, d10s) if s >= mean_share]
    lo = [d for s, d in zip(shares, d10s) if s < mean_share]
    def m(v): return sum(v)/len(v) if v else float("nan")
    print(f"\n  above-median share (n={len(hi)}): mean d10 {m(hi):+.1f}")
    print(f"  below-median share (n={len(lo)}): mean d10 {m(lo):+.1f}")
    print(f"  spread: {m(hi)-m(lo):+.1f} pts")

    print("\n=== within issue-size bands (isolates size confound) ===")
    band = lambda s: None if s is None else ("small <300cr" if s < 300 else
           ("mid 300-1000cr" if s < 1000 else "large >=1000cr"))
    groups = {}
    for s, d, sz in zip(shares, d10s, sizes):
        b = band(sz)
        if b: groups.setdefault(b, ([], []))
        if b: groups[b][0].append(s); groups[b][1].append(d)
    for b in ("small <300cr", "mid 300-1000cr", "large >=1000cr"):
        if b in groups:
            xs, ys = groups[b]
            rr = pearson(xs, ys)
            print(f"  {b:16} n={len(xs):<3} r={rr if rr is None else f'{rr:+.3f}'}   [{tag(rr, len(xs))}]")

    print("\n=== within LOW-gap only (your thesis' home) ===")
    xs = [s for s, g in zip(shares, gaps) if g is not None and g < 4]
    ys = [d for d, g in zip(d10s, gaps) if g is not None and g < 4]
    rr = pearson(xs, ys)
    print(f"  LOW-gap n={len(xs)} r={rr if rr is None else f'{rr:+.3f}'}  [{tag(rr, len(xs))}]")
    print("\nREAD-ONLY. r>0 = more marquee anchors -> better d10. This is the ceiling of")
    print("what 38 IPOs can tell us; a real verdict needs the SME/pre-2022 trash tail.")

if __name__ == "__main__":
    main()
