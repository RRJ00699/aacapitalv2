#!/usr/bin/env python3
"""
anchor_quality_d5.py — READ-ONLY. Re-tests anchor quality vs the EXECUTABLE
horizons (d1..d5 close from listing open), not just the d10 ceiling. d10_best is
hindsight; the real question is whether marquee anchors help the trade you'd
actually make. Computes each horizon from price_candles.

  python _scripts/anchor_quality_d5.py
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
    n=len(xs)
    if n<3: return None
    mx,my=sum(xs)/n,sum(ys)/n
    num=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    dx=math.sqrt(sum((x-mx)**2 for x in xs)); dy=math.sqrt(sum((y-my)**2 for y in ys))
    return None if dx==0 or dy==0 else num/(dx*dy)

def stats(rets):
    n=len(rets)
    if n<8: return None
    s=sorted(rets); return n,sum(1 for r in rets if r>0)/n*100,s[n//2],sum(rets)/n

def main():
    import psycopg2
    DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    cur=psycopg2.connect(DB,connect_timeout=20).cursor()
    # pull anchors + listing_open + first 6 session closes
    cur.execute("""
        SELECT i.anchor_names, i.listing_gap_pct, i.listing_open,
               ARRAY_AGG(p.close ORDER BY p.date)
        FROM ipo_intelligence i
        JOIN price_candles p
          ON UPPER(p.symbol)=UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol))
         AND p.date >= i.listing_date
        WHERE i.anchor_names IS NOT NULL AND i.listing_open > 0
        GROUP BY 1,2,3 HAVING COUNT(*) >= 5""")
    rows=cur.fetchall()
    recs=[]
    for names_json, gap, lopen, closes in rows:
        try:
            names=names_json if isinstance(names_json,list) else json.loads(names_json)
        except Exception: continue
        names=clean(names)
        if not names: continue
        share=sum(1 for n in names if is_t1(n))/len(names)*100
        entry=float(lopen); cl=[float(x) for x in closes]
        rets={f"d{d}":(cl[d-1]-entry)/entry*100 for d in (1,2,3,4,5) if d-1<len(cl)}
        recs.append((share, gap, rets))
    n=len(recs)
    print(f"n={n} IPOs with clean rosters + listing open + >=5 closes\n")
    if n<15: print("too thin."); return

    print("=== correlation: tier-1 share vs each horizon return ===")
    for d in ("d1","d2","d3","d4","d5"):
        xs=[r[0] for r in recs if d in r[2]]; ys=[r[2][d] for r in recs if d in r[2]]
        rr=pearson(xs,ys)
        print(f"  {d}: n={len(xs):<3} r={rr if rr is None else f'{rr:+.3f}'}")

    print("\n=== marquee (>=50% tier1) vs trashy (<50%): mean return by horizon ===")
    print(f"{'horizon':8}{'marquee_n':>10}{'marq_mean':>10}{'trash_n':>9}{'trash_mean':>11}{'spread':>8}")
    for d in ("d1","d2","d3","d4","d5"):
        marq=[r[2][d] for r in recs if d in r[2] and r[0]>=50]
        trash=[r[2][d] for r in recs if d in r[2] and r[0]<50]
        if marq and trash:
            mm,tm=sum(marq)/len(marq),sum(trash)/len(trash)
            print(f"{d:8}{len(marq):>10}{mm:>+10.1f}{len(trash):>9}{tm:>+11.1f}{mm-tm:>+8.1f}")

    print("\n=== LOW-gap only: marquee vs trash by horizon (the thesis) ===")
    low=[r for r in recs if r[1] is not None and float(r[1])<4]
    print(f"  LOW-gap n={len(low)}")
    for d in ("d1","d3","d5"):
        marq=[r[2][d] for r in low if d in r[2] and r[0]>=50]
        trash=[r[2][d] for r in low if d in r[2] and r[0]<50]
        sm=stats(marq); st=stats(trash)
        line=f"  {d}: "
        line+=f"marquee n={len(marq)} mean={sum(marq)/len(marq):+.1f} " if marq else "marquee n<1 "
        line+=f"| trash n={len(trash)} mean={sum(trash)/len(trash):+.1f}" if trash else "| trash n<1"
        print(line)
    print("\nREAD-ONLY. d1..d5 are the executable exits (unlike d10_best ceiling).")
    print("Same n=38-ceiling caveat: needs the SME/trash tail for a hard verdict.")

if __name__=="__main__": main()
