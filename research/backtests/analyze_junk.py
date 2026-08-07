#!/usr/bin/env python3
"""READ ONLY — split IPOs good vs junk (by verdict), analyze junk anchors + BRLMs for patterns."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

# good vs junk by verdict
cur.execute("""SELECT verdict, COUNT(*) FROM ipo_verdicts GROUP BY verdict ORDER BY COUNT(*) DESC""")
print("=== VERDICT SPLIT (good vs junk) ===")
for v,n in cur.fetchall(): print(f"  {v or 'null':12} {n}")

# junk = AVOID verdict. Pull their anchor + BRLM patterns.
cur.execute("""
  SELECT c.company_name, c.anchor_count, c.ofs_cr, c.fresh_issue_cr, c.brlm_names, c.issue_size_cr
  FROM ipo_verdicts v JOIN ipo_consolidated c ON c.company_name=v.company_name
  WHERE v.verdict='AVOID' AND c.listing_date < CURRENT_DATE
  ORDER BY c.listing_date DESC LIMIT 40
""")
junk=cur.fetchall()
print(f"\n=== JUNK (AVOID) IPOs — anchor + BRLM sample ({len(junk)}) ===")
low_anchor=0; brlm_count={}
for name,anc,ofs,fresh,brlm,size in junk[:20]:
    lead=(brlm or "").split(",")[0].strip()[:22]
    print(f"  {(name or '')[:26]:26} anc={anc or '?':>3}  size={size or '?':>6}  lead={lead}")
    if anc is not None and anc<=15: low_anchor+=1
    if lead: brlm_count[lead]=brlm_count.get(lead,0)+1

# which BRLMs appear most in junk?
print("\n=== BRLMs most associated with JUNK ===")
cur.execute("""
  SELECT TRIM(SPLIT_PART(c.brlm_names,',',1)) AS lead, COUNT(*) AS junk_n
  FROM ipo_verdicts v JOIN ipo_consolidated c ON c.company_name=v.company_name
  WHERE v.verdict='AVOID' AND c.brlm_names IS NOT NULL
  GROUP BY lead HAVING COUNT(*)>=2 ORDER BY junk_n DESC LIMIT 12
""")
for lead,n in cur.fetchall(): print(f"  {lead[:34]:34} {n} junk IPOs")

# anchor count: junk vs good
cur.execute("""
  SELECT v.verdict, ROUND(AVG(c.anchor_count),1), MIN(c.anchor_count), MAX(c.anchor_count)
  FROM ipo_verdicts v JOIN ipo_consolidated c ON c.company_name=v.company_name
  WHERE c.anchor_count IS NOT NULL GROUP BY v.verdict ORDER BY 2 DESC
""")
print("\n=== avg anchor count by verdict ===")
for v,avg,mn,mx in cur.fetchall(): print(f"  {v or 'null':12} avg={avg} (range {mn}-{mx})")
conn.close()
