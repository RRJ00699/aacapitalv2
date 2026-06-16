import psycopg2, os
from dotenv import load_dotenv

load_dotenv(".env.local")
url = os.environ["NEON_DATABASE_URL"].strip('"')
conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute("""
SELECT
  COUNT(*) FILTER (WHERE listing_gap_pct IS NOT NULL)                                           AS listing_gap_filled,
  COUNT(*) FILTER (WHERE peer_median_pe IS NOT NULL)                                            AS peer_pe_filled,
  COUNT(*) FILTER (WHERE anchor_classification NOT IN ('Tier-2 Neutral','Not Found')
                     AND anchor_classification IS NOT NULL)                                      AS real_anchor,
  COUNT(*) FILTER (WHERE enrichment_status = 'COMPLETE')                                        AS complete,
  COUNT(*) FILTER (WHERE enrichment_status = 'PARTIAL')                                         AS partial,
  COUNT(*) FILTER (WHERE enrichment_status = 'ERROR')                                           AS error,
  COUNT(*) FILTER (WHERE enrichment_status IS NULL)                                             AS not_started,
  COUNT(*)                                                                                       AS total
FROM ipo_intelligence
""")
row = cur.fetchone()
labels = [
    "listing_gap_pct filled",
    "peer_median_pe filled",
    "real anchor quality",
    "enrichment COMPLETE",
    "enrichment PARTIAL",
    "enrichment ERROR",
    "enrichment not started",
    "total IPOs",
]
print()
print("=" * 40)
print("NEON ipo_intelligence status")
print("=" * 40)
for l, v in zip(labels, row):
    print(f"  {l:<26} {v}")
print("=" * 40)
conn.close()
