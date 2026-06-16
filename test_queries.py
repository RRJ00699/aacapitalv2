import psycopg2, os
from dotenv import load_dotenv
load_dotenv(".env.local")
conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"].strip('"'))
cur = conn.cursor()

queries = {
    "IPO Command Center": """
        SELECT
          id, company_name,
          issue_price, issue_size_cr,
          open_date AS issue_open_date,
          close_date AS issue_close_date,
          listing_date,
          suggested_action AS ipo_status,
          lqi_final AS lqi_score,
          archetype AS conviction,
          prob_10pct_profit AS p_profit_10pct,
          prob_loss_gt10 AS p_loss,
          expected_return AS expected_return_pct,
          qib_subscription, nii_subscription,
          retail_subscription, total_subscription,
          gmp_percentage, gmp_value,
          revenue_growth_3yr, pat_growth_3yr,
          pe_ratio, sector_pe_median,
          anchor_classification,
          NULL::int AS anchor_investor_count,
          ofs_percentage, promoter_holding_post,
          NULL::boolean AS is_sme,
          NULL::text AS listing_exchange
        FROM ipo_intelligence
        ORDER BY lqi_final DESC NULLS LAST
        LIMIT 5
    """,
    "IPO Stats": """
        SELECT
          COUNT(*) FILTER (WHERE suggested_action = 'APPLY') AS open_count,
          COUNT(*) FILTER (WHERE listing_date >= CURRENT_DATE) AS listing_pending,
          COUNT(*) FILTER (WHERE archetype IN ('STRONG_BUY','BUY','APPLY')) AS buy_signals,
          COUNT(*) FILTER (WHERE lqi_final >= 70) AS high_lqi,
          COUNT(*) FILTER (WHERE gmp_percentage >= 20) AS high_gmp,
          ROUND(AVG(lqi_final)::numeric, 1) AS avg_lqi,
          COUNT(*) AS total
        FROM ipo_intelligence
    """,
    "Listing Today": """
        SELECT
          id, company_name,
          symbol AS nse_symbol,
          issue_price, listing_date,
          listing_price, listing_gap_pct,
          lqi_final AS lqi_score,
          archetype AS conviction,
          NULL::numeric AS last_price,
          listing_vwap AS vwap,
          NULL::boolean AS above_vwap,
          listing_volume,
          NULL::bigint AS buy_qty,
          NULL::bigint AS sell_qty,
          total_subscription,
          qib_subscription_x AS qib_subscription,
          gmp_percentage
        FROM ipo_intelligence
        WHERE listing_date = CURRENT_DATE
        ORDER BY lqi_final DESC NULLS LAST
        LIMIT 5
    """,
    "Recent Listings": """
        SELECT
          id, company_name,
          symbol AS nse_symbol,
          issue_price, listing_date,
          listing_price, listing_gap_pct,
          lqi_final AS lqi_score,
          archetype AS conviction,
          total_subscription,
          qib_subscription_x AS qib_subscription,
          gmp_percentage
        FROM ipo_intelligence
        WHERE listing_date >= CURRENT_DATE - INTERVAL '14 days'
          AND listing_date < CURRENT_DATE
          AND listing_gap_pct IS NOT NULL
        ORDER BY listing_date DESC
        LIMIT 5
    """,
    "Listing Stats": """
        SELECT
          COUNT(*) FILTER (WHERE listing_gap_pct > 0)   AS positive_listings,
          COUNT(*) FILTER (WHERE listing_gap_pct >= 10)  AS gain_10plus,
          COUNT(*) FILTER (WHERE listing_gap_pct < 0)    AS negative_listings,
          ROUND(AVG(listing_gap_pct)::numeric, 1)        AS avg_gain,
          COUNT(*)                                        AS total_listed
        FROM ipo_intelligence
        WHERE listing_gap_pct IS NOT NULL
          AND listing_date >= CURRENT_DATE - INTERVAL '90 days'
    """,
}

for name, sql in queries.items():
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        print(f"  OK  {name} ({len(rows)} rows)")
    except Exception as e:
        print(f"  ERR {name}: {e}")
        conn.rollback()

conn.close()
