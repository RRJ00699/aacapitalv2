#!/usr/bin/env python3
"""
clean_data_tests.py — READ ONLY. The factor tests on the newly-clean IPOMatrix data.
Per factor: real edge / no edge / NEEDS MORE DATA (the 2006-upgrade signal).
Return = d10_best_pct from listing OPEN (the tradeable entry). 2016+, non-archived.
"""
import os,sys,io,json
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_consolidated'")
ccols={r[0] for r in cur.fetchall()}
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
icols={r[0] for r in cur.fetchall()}

def f(x):
    try: return float(x)
    except: return None

# join consolidated(outcomes) + intelligence(new rich fields) + rhp(gate)
arch="AND COALESCE(c.is_archive,false)=false" if "is_archive" in ccols else ""
cur.execute(f"""
  SELECT c.company_name, c.issue_size_cr, c.listing_gap_pct, c.d10_best_pct,
         i.price_band_low, i.price_band_high, i.anchor_count, i.ofs_cr, i.fresh_issue_cr,
         i.ipo_pe, i.qib_subscription, i.anchor_names,
         r.quality_gate
  FROM ipo_consolidated c
  LEFT JOIN ipo_intelligence i
    ON regexp_replace(lower(i.company_name),'[^a-z0-9]','','g')
     = regexp_replace(lower(c.company_name),'[^a-z0-9]','','g')
  LEFT JOIN ipo_rhp_intel r
    ON regexp_replace(lower(r.company_name),'[^a-z0-9]','','g')
     = regexp_replace(lower(c.company_name),'[^a-z0-9]','','g')
  WHERE c.listing_date>='2016-01-01' {arch}
""")
R=[]
for row in cur.fetchall():
    (nm,size,gap,d10,pbl,pbh,anc,ofs,fresh,pe,qib,anames,gate)=row
    R.append(dict(nm=nm,size=f(size),gap=f(gap),d10=f(d10),pbl=f(pbl),pbh=f(pbh),
        anc=f(anc),ofs=f(ofs),fresh=f(fresh),pe=f(pe),qib=f(qib),anames=anames,gate=gate))

def stats(vals,minn=1):
    v=[x for x in vals if x is not None];n=len(v)
    if n<minn: return None
    v.sort();win=sum(1 for x in v if x>0)/n*100
    return n,win,v[n//2],sum(v)/n,v[max(0,int(n*0.1))]
def show(lbl,vals,w=30):
    st=stats(vals)
    if not st or st[0]<5: print(f"  {lbl:<{w}} n={st[0] if st else 0:<3} — too few"); return
    n,win,med,mean,p10=st
    flag=""
    if 5<=n<20: flag=" ⚠ NEEDS MORE DATA"
    print(f"  {lbl:<{w}} n={n:<3} win={win:5.1f}%  med={med:+6.1f}  p10={p10:+6.1f}{flag}")

print("="*70)
print("CLEAN-DATA FACTOR TESTS (2016+, d10 from open)")
print("="*70)
print(f"rows: {len(R)} | with d10: {sum(1 for r in R if r['d10'] is not None)} | "
      f"with anchors: {sum(1 for r in R if r['anc'] is not None)} | "
      f"with price band: {sum(1 for r in R if r['pbl'] is not None)}\n")

# ===== FACTOR 4: ANCHORS =====
print("― FACTOR 4: ANCHOR COUNT → d10 (your >30 hypothesis) ―")
for lbl,lo,hi in [("<10 anchors",0,10),("10-20",10,20),("20-30",20,30),("30-45",30,45),(">45",45,999)]:
    show(lbl,[r["d10"] for r in R if r["anc"] is not None and lo<=r["anc"]<hi])

# ===== FACTOR 1: PRICE BAND =====
print("\n― FACTOR 1: PRICE BAND (upper) → d10 (your ₹10-20 liquidity idea) ―")
for lbl,lo,hi in [("band <100",0,100),("100-300",100,300),("300-600",300,600),("600-1200",600,1200),(">1200",1200,99999)]:
    show(lbl,[r["d10"] for r in R if r["pbh"] is not None and lo<=r["pbh"]<hi])

# ===== FACTOR 2: OFS vs FRESH =====
print("\n― FACTOR 2: OFS SHARE → d10 ―")
def ofs_pct(r):
    if r["ofs"] is None or r["fresh"] is None: return None
    tot=r["ofs"]+r["fresh"]
    return 100*r["ofs"]/tot if tot>0 else None
for lbl,lo,hi in [("fresh-heavy <30% OFS",0,30),("balanced 30-70%",30,70),("OFS-heavy >70%",70,101)]:
    show(lbl,[r["d10"] for r in R if (op:=ofs_pct(r)) is not None and lo<=op<hi])

# ===== FACTOR 2b: pure-OFS + quality anchor (your NSDL/Bajaj/HDB point) =====
print("\n― FACTOR 2b: OFS-heavy split by anchor count (quality proxy) ―")
ofsh=[r for r in R if (op:=ofs_pct(r)) is not None and op>70]
show("OFS>70% + >20 anchors",[r["d10"] for r in ofsh if r["anc"] and r["anc"]>20])
show("OFS>70% + <20 anchors",[r["d10"] for r in ofsh if r["anc"] and r["anc"]<=20])

# ===== FACTOR 3: PE =====
print("\n― FACTOR 3: IPO PE → d10 ―")
for lbl,lo,hi in [("PE<20",0,20),("20-40",20,40),("40-70",40,70),(">70",70,999999)]:
    show(lbl,[r["d10"] for r in R if r["pe"] is not None and lo<=r["pe"]<hi])

# ===== THE LOCKED EDGE re-confirmed on clean data =====
print("\n― CORE EDGE re-check: MEGA (>2000cr) + gap, on clean data ―")
show("mega + gap>15%",[r["d10"] for r in R if r["size"] and r["size"]>=2000 and r["gap"] is not None and r["gap"]>15])
show("mega + gap 0-15%",[r["d10"] for r in R if r["size"] and r["size"]>=2000 and r["gap"] is not None and 0<=r["gap"]<=15])
show("<500cr (avoid)",[r["d10"] for r in R if r["size"] and r["size"]<500])

# ===== JUNK (RHP reject) confirm =====
print("\n― RHP GATE → d10 (junk vs clean) ―")
for g in ("clean","watch","reject"):
    show(f"gate={g}",[r["d10"] for r in R if r["gate"]==g])

print("\n"+"="*70)
print("⚠ NEEDS MORE DATA (n 5-19) = where 2006 backfill WOULD help.")
print("n>=20 with clear separation = real edge, no upgrade needed.")
print("="*70)
conn.close()
