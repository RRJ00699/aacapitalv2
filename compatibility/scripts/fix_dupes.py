#!/usr/bin/env python3
"""READ ONLY (dry-run) — find TRUE duplicate IPOs (same listing_date + size + near-identical name).
Emits the cleanup SQL. Does NOT modify anything. Run with --apply-preview to see the SQL only."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

# TRUE dupe = same listing_date AND same issue_size AND one name is a prefix of another
# (catches "Kusumgar Ltd." / "Kusumgar Ltd. CT" / "Kusumgar Ltd. O" but NOT ESAF/RBL/CSB)
cur.execute("""
  SELECT company_name, listing_date, issue_size_cr
  FROM ipo_consolidated
  WHERE listing_date IS NOT NULL AND issue_size_cr IS NOT NULL
  ORDER BY listing_date, issue_size_cr, LENGTH(company_name)
""")
rows=cur.fetchall()
# group by (listing_date, size), then within group find prefix-dupes
from collections import defaultdict
groups=defaultdict(list)
for name,ld,sz in rows:
    groups[(ld,sz)].append(name)

true_dupes=[]
for (ld,sz),names in groups.items():
    if len(names)<2: continue
    # sort by length; shortest is the "canonical" base
    names=sorted(set(names),key=len)
    base=names[0]
    dupes=[n for n in names[1:] if n.startswith(base) or n.replace(" ","").startswith(base.replace(" ",""))]
    if dupes:
        true_dupes.append((base,dupes,ld,sz))

print(f"=== TRUE DUPLICATES (same date+size, name is base+suffix) ===")
for base,dupes,ld,sz in true_dupes:
    print(f"  KEEP: '{base}'  ({ld}, Rs{sz}cr)")
    for d in dupes: print(f"    DROP: '{d}'")

# emit cleanup SQL — delete the junk-suffix rows, keep the clean base name
print("\n" + "="*55)
print("-- CLEANUP SQL (review before running) --")
print("BEGIN;")
for base,dupes,ld,sz in true_dupes:
    for d in dupes:
        d_esc=d.replace("'","''")
        print(f"DELETE FROM ipo_verdicts WHERE company_name = '{d_esc}';")
        print(f"DELETE FROM ipo_consolidated WHERE company_name = '{d_esc}';")
print("COMMIT;")
print(f"\n-- {sum(len(d) for _,d,_,_ in true_dupes)} junk-suffix rows to remove --")
conn.close()
