#!/usr/bin/env python3
"""READ ONLY — walk the profit-lock rule day-by-day on Knack (and Turtlemint) so it's crystal clear."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

def walk(label, symlike):
    cur.execute("""SELECT COALESCE(symbol_final,nse_symbol,symbol),listing_date
      FROM ipo_consolidated WHERE company_name ILIKE %s LIMIT 1""",(f'%{symlike}%',))
    r=cur.fetchone()
    if not r: print(f"{label}: not found"); return
    sym,ld=r
    cur.execute("""SELECT date,open,high,low,close FROM price_candles
      WHERE UPPER(symbol)=UPPER(%s) AND date>=%s ORDER BY date LIMIT 32""",(sym,ld))
    cs=cur.fetchall()
    if len(cs)<3: print(f"{label} ({sym}): only {len(cs)} candles"); return
    entry=float(cs[0][1])
    print(f"\n=== {label} ({sym}) — buy at OPEN ₹{entry:.1f} ===")
    print(f"  {'day':>3} {'high':>7} {'low':>7} {'close':>7} {'peak':>7} {'gain%':>6}  signal")
    peak=entry; hit15=False; sold=False
    for i,(d,o,h,l,c) in enumerate(cs):
        h,l,c=float(h),float(l),float(c); peak=max(peak,h)
        gain=(c/entry-1)*100
        if h>=entry*1.15: hit15=True
        floor5 = entry*1.05
        note=""
        if not sold:
            if hit15 and c<=floor5:
                note=f"🔴 SELL — was +15%, closed ₹{c:.1f} ≤ +5% floor ₹{floor5:.1f} → lock +5%"
                sold=True
            elif l<=peak*0.82:
                exitp=peak*0.82
                note=f"🔴 SELL — dropped to ₹{l:.1f} ≤ 18% off peak ₹{peak:.1f} (₹{exitp:.1f})"
                sold=True
            else:
                if hit15: note=f"hold (floor armed at ₹{floor5:.1f})"
                else: note=f"hold (need +15% = ₹{entry*1.15:.1f} to arm floor)"
        else:
            note="(already sold)"
        print(f"  {i:>3} {h:>7.1f} {l:>7.1f} {c:>7.1f} {peak:>7.1f} {gain:>+5.1f}  {note}")
        if sold and i>0: break

walk("KNACK", "knack")
walk("TURTLEMINT", "turtlemint")
conn.close()
