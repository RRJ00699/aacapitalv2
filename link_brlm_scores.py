"""
Links brlm_scores table → ipo_intelligence.brlm_score
Matches on brlm_name partial match against brlm_names column.
Also recalibrates scores (currently all 100 = too generous).
"""
import psycopg2, os, re

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Step 1: Recalibrate BRLM scores (score=100 for everyone is useless)
# Real score formula: 
#   avg_listing > 50% = 90+
#   avg_listing 30-50% = 75-89
#   avg_listing 15-30% = 60-74
#   avg_listing 5-15%  = 45-59
#   avg_listing < 5%   = 30-44
#   pct_negative > 30% = penalty

print("Recalibrating BRLM scores...")
cur.execute("SELECT brlm_name, avg_listing, pct_negative, ipo_count FROM brlm_scores")
brlms = cur.fetchall()

for brlm_name, avg_listing, pct_neg, n_ipos in brlms:
    avg = float(avg_listing or 0)
    pct_neg_val = float(pct_neg or 0)
    n = int(n_ipos or 1)

    # Base score from avg listing
    if avg >= 50:   base = 90
    elif avg >= 30: base = 78
    elif avg >= 15: base = 65
    elif avg >= 5:  base = 50
    else:           base = 35

    # Bonus for consistency (many IPOs)
    if n >= 20:   base += 5
    elif n >= 10: base += 3
    elif n <= 2:  base -= 10  # small sample, unreliable

    # Penalty for negative listings
    if pct_neg_val > 40:  base -= 20
    elif pct_neg_val > 25: base -= 10
    elif pct_neg_val > 15: base -= 5

    score = max(20, min(98, base))

    cur.execute("UPDATE brlm_scores SET score = %s WHERE brlm_name = %s", (score, brlm_name))

conn.commit()
print(f"  Recalibrated {len(brlms)} BRLM scores")

# Step 2: Show top BRLMs after recalibration
print("\nTop 15 BRLMs after recalibration:")
cur.execute("""
    SELECT brlm_name, score, avg_listing, ipo_count, pct_negative
    FROM brlm_scores ORDER BY score DESC LIMIT 15
""")
for r in cur.fetchall():
    print(f"  {r[0][:35]:35s} score:{r[1]:.0f} avg:{r[2]:.1f}% n:{r[3]} neg:{r[4]:.0f}%")

# Step 3: Link scores to ipo_intelligence
print("\nLinking BRLM scores to ipo_intelligence...")
cur.execute("SELECT brlm_name, score, avg_listing FROM brlm_scores")
brlm_map = {r[0].lower(): (r[1], r[2]) for r in cur.fetchall()}

cur.execute("""
    SELECT id, brlm_names FROM ipo_intelligence 
    WHERE brlm_names IS NOT NULL AND brlm_names != ''
""")
ipos = cur.fetchall()

matched = 0
for ipo_id, brlm_names in ipos:
    if not brlm_names: continue
    
    # Try to find matching BRLM score
    best_score = None
    best_gain  = None
    
    # Split by comma for multiple BRLMs
    for bname in re.split(r'[,;&]', str(brlm_names)):
        bname = bname.strip().lower()
        if not bname: continue
        
        # Exact match first
        if bname in brlm_map:
            s, g = brlm_map[bname]
            if best_score is None or s > best_score:
                best_score, best_gain = s, g
            continue
        
        # Partial match — first significant word
        first_word = bname.split()[0] if bname.split() else ''
        if len(first_word) >= 4:
            for db_name, (s, g) in brlm_map.items():
                if first_word in db_name:
                    if best_score is None or s > best_score:
                        best_score, best_gain = s, g
                    break
    
    if best_score is not None:
        cur.execute("""
            UPDATE ipo_intelligence 
            SET brlm_score = %s, brlm_avg_listing_gain = %s
            WHERE id = %s
        """, (best_score, best_gain, ipo_id))
        matched += 1

conn.commit()
print(f"  Linked {matched}/{len(ipos)} IPOs to BRLM scores")

# Step 4: Check upcoming IPOs now
print("\nUpcoming IPOs with BRLM scores:")
cur.execute("""
    SELECT company_name, brlm_names, brlm_score, brlm_avg_listing_gain,
           issue_size_cr, open_date, close_date
    FROM ipo_intelligence
    WHERE open_date >= '2026-06-19' AND is_sme = FALSE
    ORDER BY open_date
""")
for r in cur.fetchall():
    co, brlm, bscore, bgain, size, od, cd = r
    score_str = f"score:{bscore:.0f} gain:{bgain:.1f}%" if bscore else "❌ no score"
    print(f"  {co[:32]:32s} | {str(brlm or '?'):22s} | {score_str} | ₹{size}Cr")

conn.close()
print("\nNow run: python pre_subscription_score.py")
print("Then:    python _scripts\\ipo\\ipo_play_selector.py")
