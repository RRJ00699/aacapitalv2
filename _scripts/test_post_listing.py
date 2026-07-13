#!/usr/bin/env python3
"""READ ONLY — test the post-listing signals for a listed symbol, as TEXT (no UI needed).
Mirrors the API's math so we confirm the dashboard will render real numbers.
  python _scripts/test_post_listing.py CLEANMAX
"""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
sym=(sys.argv[1] if len(sys.argv)>1 else "").upper().strip()
if not sym: sys.exit("usage: python _scripts/test_post_listing.py SYMBOL")
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

cur.execute("""SELECT date,open,high,low,close,volume FROM price_candles
               WHERE UPPER(symbol)=%s ORDER BY date ASC""",(sym,))
rows=cur.fetchall()
print(f"=== {sym} — post-listing signals ===")
print(f"candles: {len(rows)}")
if not rows:
    print("NO CANDLES — dashboard would show 'no trading data yet'. Try a listed symbol.")
    # suggest some listed symbols that DO have candles
    cur.execute("""SELECT UPPER(COALESCE(nse_symbol,symbol)), COUNT(*) FROM price_candles p
                   JOIN ipo_consolidated c ON UPPER(COALESCE(c.nse_symbol,c.symbol))=UPPER(p.symbol)
                   WHERE c.listing_date>='2026-01-01' GROUP BY 1 ORDER BY 2 DESC LIMIT 8""")
    print("\nlisted symbols WITH candles you can test:")
    for s,n in cur.fetchall(): print(f"  {s} ({n} candles)")
    sys.exit()

def vwap(cs):
    pv=vol=0
    for _,o,h,l,c,v in cs:
        tp=(float(h)+float(l)+float(c))/3; pv+=tp*float(v); vol+=float(v)
    return pv/vol if vol else None
price=float(rows[-1][4]); first_open=float(rows[0][1])
rv=vwap(rows); w=rows[-20:]
lo=min(float(r[3]) for r in w); hi=max(float(r[2]) for r in w)
# volume profile POC
bins=12; span=hi-lo or 1; buck=[0]*bins
for _,o,h,l,c,v in w:
    tp=(float(h)+float(l)+float(c))/3; i=min(bins-1,max(0,int((tp-lo)/span*bins))); buck[i]+=float(v)
poc=lo+span*(buck.index(max(buck))+0.5)/bins
above_vwap=price>=rv; above_poc=price>=poc

cur.execute("""SELECT issue_size_cr,issue_price,anchor_lock30_date,anchor_lock90_date
               FROM ipo_consolidated WHERE UPPER(COALESCE(symbol_final,nse_symbol,symbol,''))=%s LIMIT 1""",(sym,))
m=cur.fetchone() or (None,None,None,None)
import datetime as dt
today=dt.date.today()
def days(d): return (d-today).days if d else None
l30,l90=days(m[2]),days(m[3])
up=[x for x in [l30,l90] if x is not None and x>=0]
nxt=min(up) if up else None

# delivery
cur.execute("""SELECT delivery_percentage FROM delivery_data WHERE UPPER(symbol)=%s ORDER BY date DESC LIMIT 1""",(sym,))
dv=cur.fetchone()
# nifty
cur.execute("""SELECT value FROM platform_config WHERE key='nifty_now'""")
nf=cur.fetchone()

# verdict
unlock_soon=nxt is not None and nxt<14; unlock_imm=nxt is not None and nxt<7
if above_vwap and above_poc and not unlock_soon: verdict="🟢 ACCUMULATION — HOLD"
elif not above_vwap and (not above_poc or unlock_imm): verdict="🔴 DISTRIBUTION — EXIT"
else: verdict="🟡 BASE — WAIT"

print(f"price ₹{price:.1f} | since-listing VWAP ₹{rv:.1f} -> {'ABOVE' if above_vwap else 'BELOW'} ({(price/rv-1)*100:+.1f}%)")
print(f"volume POC ₹{poc:.0f} -> price {'above' if above_poc else 'below'} the heavy zone")
print(f"anchor unlock: 30d={l30} 90d={l90} | next={nxt}d")
print(f"delivery %: {float(dv[0]):.1f}%" if dv else "delivery %: none yet (runs forward)")
print(f"nifty_now: {nf[0]}" if nf else "nifty: not set")
print(f"rel-strength (vs listing open): {(price/first_open-1)*100:+.1f}%")
print(f"\nVERDICT: {verdict}")
conn.close()
