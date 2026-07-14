#!/usr/bin/env python3
"""READ ONLY — do upcoming/recent IPOs actually have grades? Why aren't they shown?"""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

# what grade-like fields exist + are they populated for upcoming/recent IPOs?
print("=== grade coverage on recent/upcoming IPOs ===")
cur.execute("""
  SELECT c.company_name, c.listing_date,
         c.ipo_score, c.score_band,
         v.verdict, v.score AS vscore
  FROM ipo_consolidated c
  LEFT JOIN ipo_verdicts v ON v.company_name=c.company_name
  WHERE c.listing_date >= CURRENT_DATE - INTERVAL '30 days'
     OR c.listing_date IS NULL
  ORDER BY c.listing_date DESC NULLS FIRST LIMIT 25
""")
print(f"  {'company':30} {'listing':11} {'ipo_score':>9} {'band':>10} {'verdict':>9} {'vscore':>6}")
for name,ld,sc,band,verd,vsc in cur.fetchall():
    print(f"  {(name or '')[:30]:30} {str(ld or 'upcoming')[:11]:11} {str(sc or '—'):>9} {str(band or '—')[:10]:>10} {str(verd or '—'):>9} {str(vsc or '—'):>6}")

# coverage stats
cur.execute("SELECT COUNT(*) FROM ipo_consolidated WHERE score_band IS NOT NULL")
withband=cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM ipo_consolidated")
total=cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM ipo_verdicts WHERE verdict IS NOT NULL")
withverd=cur.fetchone()[0]
print(f"\n  score_band populated: {withband}/{total}")
print(f"  verdicts populated:   {withverd}")
conn.close()
