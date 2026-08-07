#!/usr/bin/env python3
"""READ ONLY — why do Kusumgar/Laser/Alpine have no score circle but SBI/Knack do?"""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

names=['kusumgar','laser','alpine','sbi','knack']
print("=== score fields per IPO (circle uses vscore ?? ipo_score) ===")
for nm in names:
    cur.execute("""
      SELECT c.company_name, c.ipo_score, c.score_band,
             v.verdict, v.score AS vscore, v.confidence AS vconf
      FROM ipo_consolidated c
      LEFT JOIN ipo_verdicts v ON v.company_name=c.company_name
      WHERE c.company_name ILIKE %s ORDER BY c.company_name""", (f'%{nm}%',))
    for r in cur.fetchall():
        name,sc,band,verd,vsc,vcf=r
        circle = vsc if vsc is not None else sc
        print(f"  {(name or '')[:30]:30} ipo_score={str(sc or '—'):>6} vscore={str(vsc or '—'):>5} → CIRCLE={'SHOWS '+str(circle) if circle is not None else 'BLANK (data thin)'}")

# also: does RHP intel exist for laser?
print("\n=== RHP intel for laser ===")
cur.execute("SELECT company_name, gate, one_line, confidence FROM ipo_rhp_intel WHERE company_name ILIKE '%laser%'")
r=cur.fetchall()
print(f"  laser RHP rows: {len(r)}")
for x in r: print(f"    {x}")
conn.close()
