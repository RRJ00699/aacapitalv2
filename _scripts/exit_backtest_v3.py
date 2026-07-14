#!/usr/bin/env python3
"""READ ONLY — v3 exit backtest for the TYPICAL IPO (most don't hit +15%).
Lower thresholds + signals that fire on modest moves. Report coverage: how often does each rule ACTUALLY signal (vs stay silent to day 30)?"""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
from statistics import mean,median
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=30);cur=conn.cursor()
cur.execute("""SELECT COALESCE(symbol_final,nse_symbol,symbol),listing_date FROM ipo_consolidated
  WHERE listing_date IS NOT NULL AND listing_date<CURRENT_DATE-INTERVAL '35 days'
    AND COALESCE(symbol_final,nse_symbol,symbol) IS NOT NULL AND issue_size_cr>=150
  ORDER BY listing_date DESC""")
ipos=cur.fetchall()
def candles(sym,ld,n=32):
    cur.execute("""SELECT date,open,high,low,close,volume FROM price_candles
      WHERE UPPER(symbol)=UPPER(%s) AND date>=%s ORDER BY date LIMIT %s""",(sym,ld,n));return cur.fetchall()

# First: how many IPOs even REACH various gain levels? (the coverage problem)
reach={5:0,10:0,15:0,20:0}; tot=0
for sym,ld in ipos:
    cs=candles(sym,ld)
    if len(cs)<10: continue
    entry=float(cs[0][1])
    if entry<=0: continue
    tot+=1
    peakgain=max((float(d[2])/entry-1)*100 for d in cs)
    for lv in reach:
        if peakgain>=lv: reach[lv]+=1
print(f"=== COVERAGE: of {tot} IPOs, how many EVER reach... ===")
for lv,n in reach.items(): print(f"  +{lv}%: {n} ({100*n//tot}%)")
print("(this is the real problem — most IPOs never run big)\n")

# rules tuned for TYPICAL IPO, with SILENCE tracking (did it exit before day30, or ride to end?)
def r_lock8(cs,entry):  # arm at +8%, floor +3%, else 12% trail
    peak=entry;armed=False
    for i,d in enumerate(cs):
        h,l,c=float(d[2]),float(d[3]),float(d[4]);peak=max(peak,h)
        if h>=entry*1.08:armed=True
        if armed and c<=entry*1.03:return (3.0,i,"floor")
        if l<=peak*0.88:return ((peak*0.88/entry-1)*100,i,"trail")
    return ((float(cs[-1][4])/entry-1)*100,len(cs)-1,"day30")
def r_vwap(cs,entry):  # exit first close below VWAP after day 2 (institutions underwater)
    cumpv=cumv=0
    for i,d in enumerate(cs):
        h,l,c=float(d[2]),float(d[3]),float(d[4]);tp=(h+l+c)/3;v=float(d[5])or 1
        cumpv+=tp*v;cumv+=v;vwap=cumpv/cumv
        if i>=2 and c<vwap:return ((c/entry-1)*100,i,"vwap-break")
    return ((float(cs[-1][4])/entry-1)*100,len(cs)-1,"day30")
def r_trail10(cs,entry):  # simple 10% trail from peak, always active
    peak=entry
    for i,d in enumerate(cs):
        h,l=float(d[2]),float(d[3]);peak=max(peak,h)
        if l<=peak*0.90:return ((peak*0.90/entry-1)*100,i,"trail")
    return ((float(cs[-1][4])/entry-1)*100,len(cs)-1,"day30")
def r_time7(cs,entry):  # just exit at day 7 close (time-based, no drama)
    idx=min(7,len(cs)-1);return ((float(cs[idx][4])/entry-1)*100,idx,"day7")

strats={"lock8/trail12":r_lock8,"vwap-break":r_vwap,"trail-10%":r_trail10,"exit-day7":r_time7}
res={k:[] for k in strats};silent={k:0 for k in strats};used=0
for sym,ld in ipos:
    cs=candles(sym,ld)
    if len(cs)<10:continue
    entry=float(cs[0][1])
    if entry<=0:continue
    used+=1
    for k,fn in strats.items():
        try:
            r,day,how=fn(cs,entry);res[k].append(r)
            if how in("day30","day7") and k!="exit-day7":silent[k]+=1
        except:pass
print(f"=== RULES for typical IPO ({used} IPOs) ===")
print(f"{'rule':16}{'avg%':>7}{'median%':>8}{'win%':>6}{'worst%':>7}  {'rode-to-end':>11}")
for k in strats:
    rs=res[k]
    if not rs:continue
    win=100*sum(1 for r in rs if r>0)/len(rs)
    print(f"  {k:14}{mean(rs):>6.1f}{median(rs):>8.1f}{win:>5.0f}%{min(rs):>7.1f}  {silent[k]:>6}/{used}")
print("\n'rode-to-end' = times the rule NEVER signalled (stayed silent, held to day 30)")
print("lower silence = the rule actually GUIDES you on typical IPOs")
conn.close()
