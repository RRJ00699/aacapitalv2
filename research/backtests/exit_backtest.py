#!/usr/bin/env python3
"""READ ONLY — Exit-strategy backtest. Buy at listing OPEN, hold to first anchor lock-in (~30 sessions).
Test which exit rule maximized return across historical IPOs. NO writes, pure analysis."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
from statistics import mean,median
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=30);cur=conn.cursor()

# universe: IPOs with a listing date + a resolvable symbol, mainboard-ish (>=150cr), since 2016
cur.execute("""
  SELECT company_name, COALESCE(symbol_final,nse_symbol,symbol) AS sym, listing_date, issue_size_cr
  FROM ipo_consolidated
  WHERE listing_date IS NOT NULL AND listing_date < CURRENT_DATE - INTERVAL '35 days'
    AND COALESCE(symbol_final,nse_symbol,symbol) IS NOT NULL
    AND issue_size_cr >= 150
  ORDER BY listing_date DESC
""")
ipos=cur.fetchall()
print(f"universe: {len(ipos)} IPOs (>=150cr, listed >35d ago)\n")

def candles(sym, ld, n=32):
    cur.execute("""SELECT date,open,high,low,close,volume FROM price_candles
      WHERE UPPER(symbol)=UPPER(%s) AND date>=%s ORDER BY date LIMIT %s""",(sym,ld,n))
    return cur.fetchall()

# strategies: each takes the candle series (from open), returns exit return %
def strat_hold30(cs, entry):   # baseline: just hold to day 30 close
    return (float(cs[-1][4])/entry-1)*100 if cs else None
def strat_target20(cs, entry): # sell first time +20% intraday high hit, else day30 close
    for d in cs:
        if float(d[2])>=entry*1.20: return 20.0
    return (float(cs[-1][4])/entry-1)*100 if cs else None
def strat_trail10(cs, entry):  # trailing stop 10% from peak
    peak=entry
    for d in cs:
        peak=max(peak,float(d[2]))
        if float(d[3])<=peak*0.90: return (peak*0.90/entry-1)*100
    return (float(cs[-1][4])/entry-1)*100 if cs else None
def strat_trail15(cs, entry):  # trailing stop 15% from peak
    peak=entry
    for d in cs:
        peak=max(peak,float(d[2]))
        if float(d[3])<=peak*0.85: return (peak*0.85/entry-1)*100
    return (float(cs[-1][4])/entry-1)*100 if cs else None
def strat_stop5_hold(cs, entry): # hard stop -5%, else hold to 30
    for d in cs:
        if float(d[3])<=entry*0.95: return -5.0
    return (float(cs[-1][4])/entry-1)*100 if cs else None
def strat_vwap_exit(cs, entry): # exit when close drops below running VWAP (institutions underwater)
    cumpv=cumv=0
    for i,d in enumerate(cs):
        tp=(float(d[2])+float(d[3])+float(d[4]))/3; v=float(d[5]) or 1
        cumpv+=tp*v; cumv+=v; vwap=cumpv/cumv
        if i>=2 and float(d[4])<vwap*0.98: return (float(d[4])/entry-1)*100
    return (float(cs[-1][4])/entry-1)*100 if cs else None

strats={"hold-to-30":strat_hold30,"target+20%":strat_target20,"trail-10%":strat_trail10,
        "trail-15%":strat_trail15,"hard-stop-5%":strat_stop5_hold,"vwap-exit":strat_vwap_exit}
results={k:[] for k in strats}
used=0
for name,sym,ld,sz in ipos:
    cs=candles(sym,ld)
    if len(cs)<10: continue
    entry=float(cs[0][1])  # listing-day OPEN
    if entry<=0: continue
    used+=1
    for k,fn in strats.items():
        r=fn(cs,entry)
        if r is not None: results[k].append(r)

print(f"backtested on {used} IPOs with candle data\n")
print(f"{'strategy':16} {'avg%':>7} {'median%':>8} {'win%':>6} {'worst%':>7}")
for k in strats:
    rs=results[k]
    if not rs: continue
    win=100*sum(1 for r in rs if r>0)/len(rs)
    print(f"  {k:14} {mean(rs):>6.1f} {median(rs):>8.1f} {win:>5.0f}% {min(rs):>7.1f}")
print("\n(entry = listing-day open; hold horizon = ~30 sessions to first anchor lock-in)")
print("higher avg + higher win% + less-negative worst = better exit rule")
conn.close()
