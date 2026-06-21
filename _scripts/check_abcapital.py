import psycopg2, os

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

print("="*60)
print("ABCAPITAL — FULL ENGINE DIAGNOSIS")
print("="*60)

# 1. What's in technical_signals
cur.execute("""
    SELECT symbol, name, buy_zone_score, conviction_score,
           technical_signal, pattern, stage, stage_label,
           rsi, price_vs_200ema, volume_ratio,
           is_nr7, nr7, momentum_6m, momentum_12m,
           updated_at
    FROM technical_signals
    WHERE symbol = 'ABCAPITAL'
    LIMIT 1
""")
row = cur.fetchone()
if row:
    cols = [d[0] for d in cur.description]
    d = dict(zip(cols, row))
    print(f"\n1. TECHNICAL SIGNALS:")
    print(f"   Buy zone score:  {d['buy_zone_score']} / 10")
    print(f"   Conviction:      {d['conviction_score']}")
    print(f"   Signal:          {d['technical_signal']}")
    print(f"   Pattern:         {d['pattern']}")
    print(f"   Stage:           {d['stage']} — {d['stage_label']}")
    print(f"   RSI:             {d['rsi']}")
    print(f"   Price vs 200EMA: {d['price_vs_200ema']}")
    print(f"   Volume ratio:    {d['volume_ratio']} (3x = 3.0)")
    print(f"   Is NR7:          {d['is_nr7'] or d['nr7']}")
    print(f"   Momentum 6M:     {d['momentum_6m']}%")
    print(f"   Momentum 12M:    {d['momentum_12m']}%")
    print(f"   Last updated:    {d['updated_at']}")
else:
    print("   ❌ NOT IN technical_signals")

# 2. Intelligence dashboard
cur.execute("""
    SELECT symbol, business_dna_score, business_dna_grade,
           overall_score, tier, roce_5y_avg, roe,
           sales_growth_3y, pat_growth_3y,
           management_quality, smart_money_signal,
           updated_at
    FROM intelligence_dashboard
    WHERE symbol = 'ABCAPITAL'
    LIMIT 1
""")
row = cur.fetchone()
if row:
    cols = [d[0] for d in cur.description]
    d = dict(zip(cols, row))
    print(f"\n2. INTELLIGENCE DASHBOARD:")
    print(f"   DNA score:       {d['business_dna_score']} [{d['business_dna_grade']}]")
    print(f"   Overall:         {d['overall_score']}")
    print(f"   Tier:            {d['tier']}")
    print(f"   ROCE 5Y avg:     {d['roce_5y_avg']}%")
    print(f"   ROE:             {d['roe']}%")
    print(f"   Sales growth 3Y: {d['sales_growth_3y']}%")
    print(f"   PAT growth 3Y:   {d['pat_growth_3y']}%")
    print(f"   Mgmt quality:    {d['management_quality']}")
    print(f"   Smart money:     {d['smart_money_signal']}")
else:
    print("   ❌ NOT IN intelligence_dashboard")

# 3. Price candles — what's the latest candle
cur.execute("""
    SELECT date, close, volume
    FROM price_candles
    WHERE symbol = 'ABCAPITAL'
    ORDER BY date DESC LIMIT 5
""")
rows = cur.fetchall()
print(f"\n3. PRICE CANDLES (last 5):")
if rows:
    for r in rows:
        print(f"   {r[0]}  close:₹{r[1]}  vol:{r[2]:,}")
else:
    cur.execute("SELECT date, close, volume FROM price_monthly WHERE tradingsymbol='ABCAPITAL' ORDER BY date DESC LIMIT 3")
    rows = cur.fetchall()
    if rows:
        for r in rows: print(f"   {r[0]}  close:₹{r[1]}  vol:{r[2]:,} [monthly]")
    else:
        print("   ❌ NO CANDLE DATA AT ALL")

# 4. Shareholding
cur.execute("""
    SELECT quarter, promoter_pct, fii_pct, dii_pct, mf_pct, public_pct, pledge_pct
    FROM shareholding_history
    WHERE symbol = 'ABCAPITAL'
    ORDER BY quarter DESC LIMIT 4
""")
rows = cur.fetchall()
print(f"\n4. SHAREHOLDING HISTORY:")
if rows:
    for r in rows:
        print(f"   {r[0]}  Promoter:{r[1]}%  FII:{r[2]}%  DII:{r[3]}%  MF:{r[4]}%  Public:{r[5]}%  Pledge:{r[6]}%")
else:
    print("   ❌ NO SHAREHOLDING DATA")

# 5. Management commentary
cur.execute("""
    SELECT symbol, sentiment_score, tone, updated_at
    FROM management_commentary_scores
    WHERE symbol = 'ABCAPITAL'
    LIMIT 1
""")
row = cur.fetchone()
print(f"\n5. MANAGEMENT COMMENTARY:")
if row:
    print(f"   Score: {row[1]}  Tone: {row[2]}  Updated: {row[3]}")
else:
    print("   ❌ NOT SCORED — this is why Mgmt quality = 10/100")

# 6. Convergence score breakdown
cur.execute("""
    SELECT symbol, convergence_score, technical_score, 
           fundamental_score, smart_money_score,
           updated_at
    FROM convergence_scores
    WHERE symbol = 'ABCAPITAL'
    LIMIT 1
""")
row = cur.fetchone()
print(f"\n6. CONVERGENCE SCORE:")
if row:
    cols = [d[0] for d in cur.description]
    d = dict(zip(cols, row))
    print(f"   Total: {d['convergence_score']}")
    print(f"   Technical: {d['technical_score']}")
    print(f"   Fundamental: {d['fundamental_score']}")
    print(f"   Smart money: {d['smart_money_score']}")
else:
    print("   ❌ NOT IN convergence_scores")

conn.close()
