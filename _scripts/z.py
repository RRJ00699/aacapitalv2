#!/usr/bin/env python3
"""
ipo_daily_levels.py — REAL daily floor/ceiling, updated each session until lock-in.

Each day d uses ONLY candles up to d (causal). Volume profile over listing..d -> VAL/VAH/POC.
FLOOR RATCHETS (only rises as support builds — "update the previous day's floor"); CEILING
tracks current value-area high. A close below the PRIOR day's floor = support broken = risk flag.

Modes:
  research (CSV):  python ipo_daily_levels.py --meta ipo_meta.csv --candles ipo_candles.csv
  populate DB:     python ipo_daily_levels.py --from-db --write-db
                   (reads price_candles + ipo_intelligence from Neon, upserts ipo_daily_levels;
                    GOLDEN RULE: ON CONFLICT (symbol,date) DO NOTHING — past days never overwritten)
Needs DATABASE_URL for DB modes.
"""
import argparse, os, numpy as np, pandas as pd
LOCK, KF = 40, 3

def vprofile(w, bins=40):
    lo, hi = float(w['low'].min()), float(w['high'].max())
    if not (hi > lo): return None
    edges=np.linspace(lo,hi,bins+1); centers=(edges[:-1]+edges[1:])/2; vol=np.zeros(bins)
    for _,d in w.iterrows():
        b0=max(0,np.searchsorted(edges,d['low'],'right')-1); b1=min(bins-1,np.searchsorted(edges,d['high'],'right')-1)
        if b1>=b0: vol[b0:b1+1]+=float(d['volume'] or 0)/(b1-b0+1)
    if vol.sum()<=0: return None
    poc=centers[vol.argmax()]; tot=vol.sum(); cum=0; sel=[]
    for i in vol.argsort()[::-1]:
        sel.append(i); cum+=vol[i]
        if cum>=0.70*tot: break
    return centers[min(sel)], centers[max(sel)], poc

def load_csv(meta_p,cand_p):
    meta=pd.read_csv(meta_p,low_memory=False); cand=pd.read_csv(cand_p,low_memory=False,parse_dates=['date'])
    return meta, cand

def load_db():
    import psycopg2
    u=os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not u: raise SystemExit("Set DATABASE_URL for --from-db.")
    conn=psycopg2.connect(u)
    meta=pd.read_sql("""SELECT nse_symbol AS symbol_final, listing_date, anchor_lock30_date,
                               listing_open, issue_size_cr, is_sme
                        FROM ipo_intelligence
                        WHERE nse_symbol IS NOT NULL AND listing_date IS NOT NULL""",conn)
    syms=tuple(meta['symbol_final'].dropna().unique())
    cand=pd.read_sql("SELECT symbol,date,open,high,low,close,volume FROM price_candles WHERE symbol IN %s",
                     conn,params=(syms,),parse_dates=['date'])
    conn.close(); return meta, cand

def run(meta,cand):
    meta['listing_date']=pd.to_datetime(meta['listing_date'],errors='coerce')
    meta['anchor_lock30_date']=pd.to_datetime(meta['anchor_lock30_date'],errors='coerce')
    meta['is_sme']=meta['is_sme'].astype(str).str.lower().isin(['true','1','t','yes'])
    sc=meta[(~meta['is_sme'])&(meta['issue_size_cr']>=200)&(meta['listing_date'].notna())]
    sc=sc.drop_duplicates('symbol_final').set_index('symbol_final')
    cand=cand.sort_values(['symbol','date']); have=set(cand['symbol'].unique())
    series=[]
    for sym,r in sc.iterrows():
        if sym not in have: continue
        g=cand[cand['symbol']==sym].reset_index(drop=True); g['t']=range(len(g))
        if len(g)<KF+2: continue
        lockdays=LOCK
        if pd.notna(r['anchor_lock30_date']):
            le=g[g['date']<=r['anchor_lock30_date']]
            if len(le): lockdays=int(le['t'].iloc[-1])
        # RESEARCHED levels: first-5-session low/high are the most-respected floor/ceiling
        # (78%/75% vs 65%/68% for volume-profile). They stay PUT — stability = why price respects them.
        form=g[g['t']<KF]
        if len(form)<KF: continue
        f5lo=float(form['low'].min()); f5hi=float(form['high'].max())
        vpf=vprofile(form); poc=round(vpf[2],2) if vpf else round((f5lo+f5hi)/2,2)
        for d in range(KF-1,len(g)):
            if g['t'].iloc[d]>lockdays: break
            close=float(g['close'].iloc[d])
            series.append(dict(sym=sym,t=int(g['t'].iloc[d]),date=g['date'].iloc[d].date(),
                close=round(close,2),floor=round(f5lo,2),ceiling=round(f5hi,2),poc=poc,
                broke_floor=bool(close<f5lo),broke_ceiling=bool(close>f5hi),
                cushion=round(close/f5lo-1,4)))
    return pd.DataFrame(series)

def write_db(s):
    import psycopg2
    from psycopg2.extras import execute_values
    u=os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    conn=psycopg2.connect(u); cur=conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS ipo_daily_levels(
        symbol text, date date, t int, close numeric, floor numeric, ceiling numeric,
        poc numeric, broke_floor boolean, broke_ceiling boolean, cushion numeric,
        PRIMARY KEY(symbol,date))""")
    cur.execute("ALTER TABLE ipo_daily_levels ADD COLUMN IF NOT EXISTS broke_ceiling boolean")
    rows=[(r.sym,r.date,int(r.t),r.close,r.floor,r.ceiling,r.poc,bool(r.broke_floor),
           bool(r.broke_ceiling),r.cushion) for r in s.itertuples()]
    execute_values(cur,"""INSERT INTO ipo_daily_levels
        (symbol,date,t,close,floor,ceiling,poc,broke_floor,broke_ceiling,cushion) VALUES %s
        ON CONFLICT (symbol,date) DO NOTHING""",rows)
    conn.commit(); conn.close()
    print(f"✓ upserted {len(rows)} rows into ipo_daily_levels (golden-rule: past days untouched)")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--meta",default="/mnt/user-data/uploads/ipo_meta.csv")
    ap.add_argument("--candles",default="/mnt/user-data/uploads/ipo_candles.csv")
    ap.add_argument("--from-db",action="store_true"); ap.add_argument("--write-db",action="store_true")
    a=ap.parse_args()
    meta,cand = load_db() if a.from_db else load_csv(a.meta,a.candles)
    s=run(meta,cand)
    print(f"daily level rows: {len(s)} across {s['sym'].nunique()} IPOs")
    if a.write_db: write_db(s)
    else:
        s.to_csv("ipo_daily_levels.csv",index=False); print("[saved ipo_daily_levels.csv]")
