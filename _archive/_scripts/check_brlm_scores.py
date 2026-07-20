import psycopg2, os

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# First check actual columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='brlm_scores' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print(f"brlm_scores columns: {cols}\n")

# Build query from actual columns
name_col  = 'brlm_name' if 'brlm_name' in cols else 'name'
score_col = 'score' if 'score' in cols else 'brlm_score'
gain_col  = next((c for c in cols if 'gain' in c or 'listing' in c), cols[2] if len(cols)>2 else 'score')
count_col = next((c for c in cols if 'count' in c or 'total' in c or 'ipo' in c.lower()), None)

print("="*60)
print("TOP 20 BRLMs IN DB")
print("="*60)
q = f"SELECT {name_col}, {score_col}, {gain_col}" + (f", {count_col}" if count_col else "") + " FROM brlm_scores ORDER BY {score_col} DESC LIMIT 20".format(score_col=score_col)
cur.execute(q)
for r in cur.fetchall():
    line = f"  {str(r[0])[:35]:35s} score:{r[1]:.0f} gain:{r[2]:.1f}%"
    if len(r) > 3: line += f" n:{r[3]}"
    print(line)

# Check upcoming IPO BRLMs
print("\n\nBRLMs on upcoming IPOs:")
cur.execute("""
    SELECT company_name, brlm_names, brlm_score, brlm_avg_listing_gain,
           issue_size_cr, open_date, close_date
    FROM ipo_intelligence
    WHERE open_date >= '2026-06-19' AND is_sme = FALSE
    ORDER BY open_date
""")
for r in cur.fetchall():
    co, brlm, bscore, bgain, size, od, cd = r
    print(f"  {co[:30]:30s} | {str(brlm or '?'):25s} | score:{bscore} gain:{bgain} | ₹{size}Cr | {od}→{cd}")

conn.close()
