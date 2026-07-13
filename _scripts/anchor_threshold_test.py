#!/usr/bin/env python3
"""READ ONLY — test the anchor threshold EXACTLY as asked: >30 as one bucket,
plus combined with the core edge (mega + gap). Buy-at-open (d10). 2016+."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()
def f(x):
    try:return float(x)
    except:return None
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_consolidated'")
ccols={r[0] for r in cur.fetchall()}
arch="AND COALESCE(c.is_archive,false)=false" if "is_archive" in ccols else ""
cur.execute(f"""
  SELECT c.issue_size_cr,c.listing_gap_pct,c.d10_best_pct,i.anchor_count,i.price_band_high,i.ofs_cr,i.fresh_issue_cr
  FROM ipo_consolidated c
  LEFT JOIN ipo_intelligence i ON regexp_replace(lower(i.company_name),'[^a-z0-9]','','g')=regexp_replace(lower(c.company_name),'[^a-z0-9]','','g')
  WHERE c.listing_date>='2016-01-01' {arch}""")
R=[dict(size=f(a),gap=f(b),d10=f(c),anc=f(d),pbh=f(e),ofs=f(g),fresh=f(h)) for a,b,c,d,e,g,h in cur.fetchall()]
def stats(v):
    v=[x for x in v if x is not None];n=len(v)
    if n<5:return None
    v.sort();return n,sum(1 for x in v if x>0)/n*100,v[n//2],v[max(0,int(n*.1))]
def show(l,vals,w=34):
    st=stats(vals)
    if st:print(f"  {l:<{w}} n={st[0]:<3} win={st[1]:5.1f}%  med={st[2]:+6.1f}  p10={st[3]:+6.1f}")
    else:print(f"  {l:<{w}} n<5")

print("="*66);print("ANCHOR THRESHOLD — buy at open (d10), your >30 hypothesis");print("="*66)
print("\n― simple threshold splits ―")
show(">30 anchors",       [r["d10"] for r in R if r["anc"] and r["anc"]>30])
show("<=30 anchors",      [r["d10"] for r in R if r["anc"] and r["anc"]<=30])
show(">40 anchors",       [r["d10"] for r in R if r["anc"] and r["anc"]>40])
show(">50 anchors",       [r["d10"] for r in R if r["anc"] and r["anc"]>50])

print("\n― >30 anchors COMBINED with the core edge ―")
show(">30 anc + mega>2000cr", [r["d10"] for r in R if r["anc"] and r["anc"]>30 and r["size"] and r["size"]>=2000])
show(">30 anc + gap>15%",     [r["d10"] for r in R if r["anc"] and r["anc"]>30 and r["gap"] is not None and r["gap"]>15])
show(">30 anc + gap 0-15%",   [r["d10"] for r in R if r["anc"] and r["anc"]>30 and r["gap"] is not None and 0<=r["gap"]<=15])
show(">30 anc + fresh-heavy",  [r["d10"] for r in R if r["anc"] and r["anc"]>30 and r["ofs"] is not None and r["fresh"] is not None and (r["ofs"]+r["fresh"])>0 and r["ofs"]/(r["ofs"]+r["fresh"])<0.3])

print("\n― the STACK: >30 anchors + mega + positive gap (buy signal?) ―")
show(">30 anc + mega + gap>0", [r["d10"] for r in R if r["anc"] and r["anc"]>30 and r["size"] and r["size"]>=2000 and r["gap"] is not None and r["gap"]>0])
print("="*66)
conn.close()
