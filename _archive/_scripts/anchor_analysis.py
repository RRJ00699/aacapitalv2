import psycopg2, os

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
    SELECT 
        play_recommendation,
        COUNT(*) as total,
        COUNT(anchor_tier1_count) as has_anchor_data,
        ROUND(AVG(anchor_tier1_count)::numeric, 1) as avg_tier1,
        ROUND(AVG(anchor_alloc_pct)::numeric, 1) as avg_alloc_pct,
        SUM(CASE WHEN anchor_tier1_count >= 15 THEN 1 ELSE 0 END) as strong_anchors,
        SUM(CASE WHEN anchor_tier1_count IS NULL OR anchor_tier1_count = 0 THEN 1 ELSE 0 END) as no_anchors,
        ROUND(AVG(qib_subscription_x)::numeric, 1) as avg_qib,
        ROUND(AVG(return_listing_open)::numeric, 1) as avg_open_return
    FROM ipo_intelligence
    WHERE is_sme = FALSE AND play_recommendation IS NOT NULL
    GROUP BY play_recommendation
    ORDER BY avg_open_return DESC NULLS LAST
""")
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
print("=" * 80)
print("ANCHOR ANALYSIS BY PLAY")
print("=" * 80)
for row in rows:
    d = dict(zip(cols, row))
    print(f"\n{d['play_recommendation']}")
    print(f"  Total: {d['total']} | Has anchor data: {d['has_anchor_data']}")
    print(f"  Avg tier-1 anchors: {d['avg_tier1']} | 15+ anchors: {d['strong_anchors']} | No anchors: {d['no_anchors']}")
    print(f"  Avg alloc%: {d['avg_alloc_pct']}% | Avg QIB: {d['avg_qib']}x | Avg open: {d['avg_open_return']}%")

print("\n\n" + "="*80)
print("ANCHOR TIER-1 COUNT vs LISTING RETURN")
print("="*80)
cur.execute("""
    SELECT 
        CASE 
            WHEN anchor_tier1_count IS NULL OR anchor_tier1_count = 0 THEN 'No tier-1 anchors'
            WHEN anchor_tier1_count < 5  THEN '1-4 tier-1 anchors'
            WHEN anchor_tier1_count < 10 THEN '5-9 tier-1 anchors'
            WHEN anchor_tier1_count < 15 THEN '10-14 tier-1 anchors'
            ELSE '15+ tier-1 (institutional grade)'
        END as bucket,
        COUNT(*) as ipos,
        ROUND(AVG(return_listing_open)::numeric, 1) as avg_open,
        ROUND(AVG(return_day30)::numeric, 1) as avg_30d,
        SUM(CASE WHEN return_listing_open > 10 THEN 1 ELSE 0 END) as winners,
        SUM(CASE WHEN return_listing_open < -5 THEN 1 ELSE 0 END) as losers
    FROM ipo_intelligence
    WHERE is_sme = FALSE AND return_listing_open IS NOT NULL
    GROUP BY 1
    ORDER BY avg_open DESC
""")
for row in cur.fetchall():
    bucket, n, avg_open, avg_30, winners, losers = row
    print(f"  {bucket:35s} {n:3d} IPOs | open {str(avg_open):>6}% | 30d {str(avg_30):>6}% | ✅{winners} ❌{losers}")

conn.close()
