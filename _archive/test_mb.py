import psycopg2, os
from dotenv import load_dotenv
load_dotenv(".env.local")
conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"].strip('"'))
cur = conn.cursor()

# Check if table exists
cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'technical_signals')")
exists = cur.fetchone()[0]
print(f"technical_signals table exists: {exists}")

if exists:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'technical_signals'")
    cols = [r[0] for r in cur.fetchall()]
    print(f"Columns: {cols}")
    
    try:
        cur.execute("""
            SELECT id, symbol, signal_date,
              monthly_rsi, monthly_rsi_ok,
              weekly_ema30, price_above_ema30,
              weekly_ha_bullish, daily_nr7, daily_inside_bar,
              criteria_met, all_criteria_met,
              mb_score, conviction,
              dtw_pattern_match, dtw_similarity_pct, synced_at
            FROM technical_signals LIMIT 1
        """)
        print("Query OK")
    except Exception as e:
        print(f"Query ERR: {e}")
else:
    print("Table missing - need to run sync-signals-to-neon.ts first")
    print("OR we can make multibagger page handle empty table gracefully")

conn.close()
