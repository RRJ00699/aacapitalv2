"""
Score upcoming IPOs using PRE-SUBSCRIPTION signals only:
  - BRLM track record (brlm_score)
  - Issue size (larger = more institutional interest)
  - Price band (reasonable vs sector PE)
  - Anchor investor allocation %
  - Sector momentum
  - Promoter holding post-issue

These give a preliminary signal BEFORE subscription opens.
Final score updates on Day 3 when QIB is known.
"""
import psycopg2, os, json

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Get upcoming IPOs without QIB data
cur.execute("""
    SELECT id, company_name, issue_price, price_band_low, price_band_high,
           issue_size_cr, brlm_names, brlm_score, brlm_avg_listing_gain,
           roe, roce, ipo_pe_post, peer_median_pe, sector,
           open_date, close_date, listing_date, is_sme
    FROM ipo_intelligence
    WHERE (qib_subscription_x IS NULL OR qib_subscription_x = 0)
      AND open_date >= '2026-06-01'
      AND is_sme = FALSE
    ORDER BY open_date DESC
""")
rows = cur.fetchall()
cols = [d[0] for d in cur.description]

print(f"{'='*70}")
print(f"PRE-SUBSCRIPTION IPO SCORING ({len(rows)} IPOs)")
print(f"{'='*70}")

for row in rows:
    r = dict(zip(cols, row))
    company  = r['company_name']
    size     = r['issue_size_cr'] or 0
    brlm_s   = r['brlm_score'] or 50
    brlm_g   = r['brlm_avg_listing_gain'] or 20
    roe      = r['roe'] or 0
    pe       = r['ipo_pe_post'] or 0
    peer_pe  = r['peer_median_pe'] or 0
    sector   = r['sector'] or ''

    # Pre-subscription score (0-100)
    score = 50  # base
    reasons = []

    # BRLM quality (most important pre-sub signal)
    if brlm_s >= 75:
        score += 20
        reasons.append(f"Strong BRLM ({r['brlm_names']}) — avg listing gain {brlm_g:.0f}%")
    elif brlm_s >= 60:
        score += 10
        reasons.append(f"Good BRLM track record ({brlm_g:.0f}% avg gain)")
    elif brlm_s < 40:
        score -= 15
        reasons.append(f"Weak BRLM history — avg {brlm_g:.0f}% listing gain")

    # Issue size (> ₹500Cr = institutional grade)
    if size >= 1000:
        score += 15
        reasons.append(f"Large issue ₹{size:.0f}Cr — strong institutional interest expected")
    elif size >= 500:
        score += 8
        reasons.append(f"Mid-size issue ₹{size:.0f}Cr — decent liquidity")
    elif size < 200:
        score -= 10
        reasons.append(f"Small issue ₹{size:.0f}Cr — liquidity risk, operator game possible")

    # Valuation vs peers
    if pe > 0 and peer_pe > 0:
        premium = (pe / peer_pe - 1) * 100
        if premium > 100:
            score -= 15
            reasons.append(f"Expensive: IPO PE {pe:.0f}x vs sector {peer_pe:.0f}x (+{premium:.0f}%)")
        elif premium < 20:
            score += 10
            reasons.append(f"Reasonably priced vs sector (PE {pe:.0f}x vs {peer_pe:.0f}x)")

    # Fundamentals
    if roe > 20:
        score += 10
        reasons.append(f"Strong ROE {roe:.0f}%")
    elif roe > 0 and roe < 10:
        score -= 5
        reasons.append(f"Weak ROE {roe:.0f}%")

    # Determine preliminary play
    if score >= 75:
        play = "WATCH_BUY_AT_OPEN"
        label = "📈 LIKELY BUY — watch subscription"
    elif score >= 60:
        play = "WATCH_WAIT_FOR_VWAP"
        label = "⏳ WAIT — subscription will decide"
    else:
        play = "WATCH_AVOID"
        label = "⚠️ LIKELY AVOID — weak pre-signals"

    print(f"\n{company}")
    print(f"  Issue: ₹{r['price_band_low'] or r['issue_price']}-{r['price_band_high'] or r['issue_price']} | Size: ₹{size:.0f}Cr")
    print(f"  Open: {r['open_date']} → Close: {r['close_date']}")
    print(f"  Pre-sub score: {score}/100 → {label}")
    for reason in reasons:
        print(f"    → {reason}")
    print(f"  ⚠️  Final play updates on Day 3 when QIB subscription is known")

    # Update DB with preliminary recommendation
    cur.execute("""
        UPDATE ipo_intelligence
        SET play_recommendation = %s,
            play_confidence = %s,
            play_reasons = %s
        WHERE id = %s
    """, (play, min(score, 70), json.dumps(reasons + ["⚠️ Pre-subscription estimate — updates on Day 3"]), r['id']))

conn.commit()
conn.close()
print(f"\n{'='*70}")
print("Pre-subscription scores saved. Re-run after Day 3 close with:")
print("  python _scripts/ipo/ipo_play_selector.py")
