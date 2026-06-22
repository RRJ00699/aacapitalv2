"""
Run two things:
1. Check listing_gap_pct in Neon
2. Sync technical_signals from local Postgres to Neon
"""
import psycopg2, os, json
from dotenv import load_dotenv
load_dotenv(".env.local")

NEON_URL = os.environ["NEON_DATABASE_URL"].strip('"')

# Local DB — hardcoded to avoid URL encoding issues
LOCAL_CONN = {
    "host": "localhost",
    "port": 5432,
    "database": "aacapital",
    "user": "postgres",
    "password": "Ashrith@2820",
    "sslmode": "disable",
}

print("\n=== 1. Neon listing_gap_pct check ===")
neon = psycopg2.connect(NEON_URL)
cur = neon.cursor()
cur.execute("""
    SELECT company_name, listing_gap_pct 
    FROM ipo_intelligence 
    WHERE listing_gap_pct IS NOT NULL 
    ORDER BY listing_gap_pct DESC 
    LIMIT 10
""")
rows = cur.fetchall()
if rows:
    for r in rows:
        print(f"  {r[0]:<40} {r[1]}%")
else:
    print("  No rows with listing_gap_pct — backtest needs more data")
neon.close()

print("\n=== 2. Syncing technical_signals local → Neon ===")
try:
    local = psycopg2.connect(**LOCAL_CONN)
    print("  Local DB connected ✅")
    
    lcur = local.cursor()
    lcur.execute("""
        SELECT 
            symbol, signal_date, timeframe,
            monthly_rsi_14, monthly_ok,
            weekly_ema_30, weekly_ok,
            weekly_ha_green_no_lower_shadow,
            daily_nr7_recent, daily_inside_bar_recent,
            buy_zone_score, trigger_ok,
            probability_score, signal_strength, action_label,
            reasons, updated_at
        FROM technical_signals
        ORDER BY signal_date DESC, probability_score DESC
    """)
    signals = lcur.fetchall()
    print(f"  Found {len(signals)} signals in local DB")
    
    if not signals:
        print("  No signals to sync")
        local.close()
        exit(0)
    
    neon = psycopg2.connect(NEON_URL)
    ncur = neon.cursor()
    
    # Ensure table exists in Neon
    ncur.execute("""
        CREATE TABLE IF NOT EXISTS technical_signals (
            id                          SERIAL PRIMARY KEY,
            symbol                      TEXT NOT NULL,
            signal_date                 DATE NOT NULL,
            timeframe                   TEXT,
            monthly_rsi_14              NUMERIC(6,2),
            monthly_ok                  BOOLEAN,
            weekly_ema_30               NUMERIC(12,2),
            weekly_ok                   BOOLEAN,
            weekly_ha_green_no_lower_shadow BOOLEAN,
            daily_nr7_recent            BOOLEAN,
            daily_inside_bar_recent     BOOLEAN,
            buy_zone_score              NUMERIC(6,2),
            trigger_ok                  BOOLEAN,
            probability_score           NUMERIC(6,2),
            signal_strength             TEXT,
            action_label                TEXT,
            reasons                     JSONB,
            updated_at                  TIMESTAMPTZ DEFAULT now(),
            UNIQUE (symbol, signal_date)
        )
    """)
    neon.commit()
    
    upserted = 0
    for s in signals:
        reasons = s[15]
        if isinstance(reasons, list):
            reasons = json.dumps(reasons)
        
        ncur.execute("""
            INSERT INTO technical_signals (
                symbol, signal_date, timeframe,
                monthly_rsi_14, monthly_ok,
                weekly_ema_30, weekly_ok,
                weekly_ha_green_no_lower_shadow,
                daily_nr7_recent, daily_inside_bar_recent,
                buy_zone_score, trigger_ok,
                probability_score, signal_strength, action_label,
                reasons, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (symbol, signal_date) DO UPDATE SET
                probability_score = EXCLUDED.probability_score,
                signal_strength   = EXCLUDED.signal_strength,
                action_label      = EXCLUDED.action_label,
                trigger_ok        = EXCLUDED.trigger_ok,
                updated_at        = now()
        """, s[:15] + (reasons, s[16]))
        upserted += 1
    
    neon.commit()
    neon.close()
    local.close()
    print(f"  ✅ {upserted} signals synced to Neon")
    
    print("\n=== Neon technical_signals summary ===")
    neon2 = psycopg2.connect(NEON_URL)
    cur2 = neon2.cursor()
    cur2.execute("""
        SELECT symbol, probability_score, action_label, signal_date
        FROM technical_signals
        WHERE trigger_ok = true
        ORDER BY probability_score DESC
    """)
    for r in cur2.fetchall():
        print(f"  {r[0]:<15} score={r[1]}  {r[2]}  {r[3]}")
    neon2.close()

except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
