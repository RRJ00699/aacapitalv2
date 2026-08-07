#!/usr/bin/env python3
"""READ ONLY — REFINED exit backtest. Tests SMART dynamic exits vs the v1 baselines.
Goal: beat 'target+20%' (caps winners) AND avoid 'hold-30' blowups (-76%). Buy at listing open."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
from statistics import mean,median
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=30);cur=conn.cursor()

cur.execute("""
  SELECT COALESCE(symbol_final,nse_symbol,symbol) AS sym, listing_date
  FROM ipo_consolidated
  WHERE listing_date IS NOT NULL AND listing_date < CURRENT_DATE - INTERVAL '35 days'
    AND COALESCE(symbol_final,nse_symbol,symbol) IS NOT NULL AND issue_size_cr >= 150
  ORDER BY listing_date DESC
""")
ipos=cur.fetchall()

def candles(sym, ld, n=32):
    cur.execute("""SELECT date,open,high,low,close,volume FROM price_candles
      WHERE UPPER(symbol)=UPPER(%s) AND date>=%s ORDER BY date LIMIT %s""",(sym,ld,n))
    return cur.fetchall()

# SMART strategies
def widening_trail(cs, entry):
    # trailing stop that LOOSENS as gain grows: <10% gain→tight 7%, 10-25%→12%, >25%→18%
    peak=entry
    for d in cs:
        hi,lo=float(d[2]),float(d[3])
        peak=max(peak,hi)
        gain=(peak/entry-1)*100
        trail = 0.07 if gain<10 else 0.12 if gain<25 else 0.18
        if lo<=peak*(1-trail): return (peak*(1-trail)/entry-1)*100
    return (float(cs[-1][4])/entry-1)*100

def profit_lock_trail(cs, entry):
    # give room early, but once +15% is hit, never let it close below +5% (lock partial gain)
    peak=entry; hit15=False
    for d in cs:
        hi,lo,cl=float(d[2]),float(d[3]),float(d[4])
        peak=max(peak,hi)
        if hi>=entry*1.15: hit15=True
        if hit15 and cl<=entry*1.05: return 5.0
        if lo<=peak*0.82: return (peak*0.82/entry-1)*100  # hard 18% trail floor
    return (float(cs[-1][4])/entry-1)*100

def vwap_plus_trail(cs, entry):
    # exit if closes below VWAP (institutions underwater) OR 15% off peak — whichever first
    cumpv=cumv=0; peak=entry
    for i,d in enumerate(cs):
        hi,lo,cl=float(d[2]),float(d[3]),float(d[4])
        tp=(hi+lo+cl)/3; v=float(d[5]) or 1
        cumpv+=tp*v; cumv+=v; vwap=cumpv/cumv; peak=max(peak,hi)
        if i>=2 and cl<vwap*0.98: return (cl/entry-1)*100
        if lo<=peak*0.85: return (peak*0.85/entry-1)*100
    return (float(cs[-1][4])/entry-1)*100

def first3day_then_trail(cs, entry):
    # hold first 3 days no matter what (let listing volatility settle), then trail 12%
    peak=entry
    for i,d in enumerate(cs):
        hi,lo=float(d[2]),float(d[3]); peak=max(peak,hi)
        if i>=3 and lo<=peak*0.88: return (peak*0.88/entry-1)*100
    return (float(cs[-1][4])/entry-1)*100

strats={"widening-trail":widening_trail,"profit-lock":profit_lock_trail,
        "vwap+trail":vwap_plus_trail,"hold3-then-trail12":first3day_then_trail}
results={k:[] for k in strats}; used=0
for sym,ld in ipos:
    cs=candles(sym,ld)
    if len(cs)<10: continue
    entry=float(cs[0][1])
    if entry<=0: continue
    used+=1
    for k,fn in strats.items():
        try:
            r=fn(cs,entry)
            if r is not None: results[k].append(r)
        except: pass

print(f"REFINED exit backtest — {used} IPOs\n")
print(f"{'strategy':20} {'avg%':>7} {'median%':>8} {'win%':>6} {'worst%':>7} {'>20%':>6}")
for k in strats:
    rs=results[k]
    if not rs: continue
    win=100*sum(1 for r in rs if r>0)/len(rs)
    big=100*sum(1 for r in rs if r>20)/len(rs)
    print(f"  {k:18} {mean(rs):>6.1f} {median(rs):>8.1f} {win:>5.0f}% {min(rs):>7.1f} {big:>5.0f}%")
print("\nvs v1 baselines: target+20% (avg6.4/win76/worst-76), trail-15% (avg27/win44/worst-15)")
print("BEST = high avg + decent win% + worst not catastrophic + captures >20% runners")
conn.close()
