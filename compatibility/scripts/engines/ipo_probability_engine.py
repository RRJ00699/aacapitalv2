"""
AACapital -- IPO Probability Engine V1
_scripts/engines/ipo_probability_engine.py

Usage:
  python _scripts/engines/ipo_probability_engine.py --test
  python _scripts/engines/ipo_probability_engine.py --all
  python _scripts/engines/ipo_probability_engine.py --ipo "BLS E-Services"
"""

import os
import sys
import math
import json
import logging
import argparse
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

# ── Feature weights ────────────────────────────────────────────────────────────

FEATURE_WEIGHTS = {
    "qib_subscription_x": 0.30,
    "nii_subscription_x": 0.15,
    "ofs_pct":            0.15,
    "gmp_percentage":     0.20,
    "sector_encoded":     0.10,
}

SECTOR_GROUPS = {
    "manufacturing":  ["Steel","Auto","Engineering","Chemical","Textile","Paper","Cement","Pipes"],
    "technology":     ["IT","Software","Tech","Digital","Electronics","Semiconductor"],
    "financial":      ["Bank","Finance","Insurance","NBFC","Fintech","Payments","Broking"],
    "healthcare":     ["Pharma","Health","Hospital","Diagnostic","Medical","Biotech"],
    "consumer":       ["FMCG","Retail","Food","Beverages","Fashion","Jewel","Consumer"],
    "infrastructure": ["Infra","Construction","Real Estate","Roads","Power","Energy","Renewable"],
    "logistics":      ["Logistics","Transport","Shipping","Aviation"],
    "other":          [],
}


def encode_sector(sector):
    if not sector: return 4
    s = str(sector).lower()
    for i, (group, keywords) in enumerate(SECTOR_GROUPS.items()):
        if any(k.lower() in s for k in keywords):
            return i
    return 7


def normalize(value, min_val, max_val):
    if max_val == min_val: return 0.5
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))


def cosine_similarity(v1, v2):
    dot = sum(a * b for a, b in zip(v1, v2))
    m1  = math.sqrt(sum(a * a for a in v1))
    m2  = math.sqrt(sum(b * b for b in v2))
    if m1 == 0 or m2 == 0: return 0.0
    return dot / (m1 * m2)


def compute_stats(data):
    def safe_range(vals):
        v = [x for x in vals if x]
        return (min(v), max(v)) if v else (0, 1)
    qib_min, qib_max = safe_range([float(r.get("qib_subscription_x") or 0) for r in data])
    nii_min, nii_max = safe_range([float(r.get("nii_subscription_x") or 0) for r in data])
    gmp_min, gmp_max = safe_range([float(r.get("gmp_percentage")      or 0) for r in data])
    return dict(qib_min=qib_min, qib_max=qib_max,
                nii_min=nii_min, nii_max=nii_max,
                gmp_min=gmp_min, gmp_max=gmp_max)


def build_feature_vector(row, stats):
    qib = float(row.get("qib_subscription_x") or 0)
    nii = float(row.get("nii_subscription_x") or 0)
    ofs = float(row.get("ofs_pct")             or 0)
    gmp = float(row.get("gmp_percentage")      or 0)
    sec = encode_sector(row.get("sector"))
    return [
        normalize(qib, stats["qib_min"], stats["qib_max"]) * FEATURE_WEIGHTS["qib_subscription_x"],
        normalize(nii, stats["nii_min"], stats["nii_max"]) * FEATURE_WEIGHTS["nii_subscription_x"],
        normalize(ofs, 0, 100)                             * FEATURE_WEIGHTS["ofs_pct"],
        normalize(gmp, stats["gmp_min"], stats["gmp_max"]) * FEATURE_WEIGHTS["gmp_percentage"],
        normalize(sec, 0, 7)                               * FEATURE_WEIGHTS["sector_encoded"],
    ]


def find_similar(query_row, training_data, stats, top_n=10):
    query_vec = build_feature_vector(query_row, stats)
    sims = []
    for row in training_data:
        if row["company_name"] == query_row.get("company_name"):
            continue
        if row["listing_gap_pct"] is None:
            continue
        vec = build_feature_vector(row, stats)
        sims.append((cosine_similarity(query_vec, vec), row))
    sims.sort(key=lambda x: x[0], reverse=True)
    return sims[:top_n]


def calculate_probabilities(similar_ipos):
    if not similar_ipos: return {}
    total_weight = sum(sim for sim, _ in similar_ipos)
    if total_weight == 0: return {}

    buckets = {"100+": 0, "50-100": 0, "30-50": 0, "10-30": 0, "0-10": 0, "negative": 0}
    gains   = []

    for sim, row in similar_ipos:
        w    = sim / total_weight
        arch = row.get("archetype", "0-10") or "0-10"
        if arch in buckets:
            buckets[arch] += w
        gap = float(row.get("listing_gap_pct") or 0)
        gains.append(gap * w)

    expected_return = sum(gains)
    prob_above_10   = sum(v for k, v in buckets.items()
                          if k in ("10-30", "30-50", "50-100", "100+"))
    prob_above_30   = sum(v for k, v in buckets.items()
                          if k in ("30-50", "50-100", "100+"))
    prob_loss       = buckets.get("negative", 0)

    # ── GMP floor override (Carraro fix) ──
    return {
        "prob_above_10":  round(prob_above_10 * 100, 2),
        "prob_above_30":  round(prob_above_30 * 100, 2),
        "prob_loss":      round(prob_loss     * 100, 2),
        "expected_return":round(expected_return, 2),
        "bucket_probs":   {k: round(v * 100, 2) for k, v in buckets.items()},
    }


def apply_gmp_floor(probs, gmp_pct, lqi, qib):
    """Cap probabilities when GMP is too low to support upside."""
    gmp  = float(gmp_pct or 0)
    qib  = float(qib     or 0)
    p10  = probs.get("prob_above_10", 0)
    ret  = probs.get("expected_return", 0)
    warn = None

    if gmp < 0:
        probs["prob_above_10"]   = min(p10, 15.0)
        probs["expected_return"] = min(ret, 2.0)
        warn = "Negative GMP — grey market expects weak listing"
    elif gmp < 5:
        if not (lqi >= 85 and qib >= 50):
            probs["prob_above_10"]   = min(p10, 35.0)
            probs["expected_return"] = min(ret, 8.0)
            warn = "Low GMP floor — market not pricing listing alpha"
    elif gmp < 10:
        probs["prob_above_10"] = min(p10, 50.0)
        warn = "Weak GMP — moderate caution"

    probs["gmp_warning"] = warn
    return probs


def calculate_lqi(row, probs):
    score = 0

    qib = float(row.get("qib_subscription_x") or 0)
    if   qib >= 100: score += 25
    elif qib >= 50:  score += 20
    elif qib >= 20:  score += 15
    elif qib >= 10:  score += 10
    elif qib >= 5:   score += 5

    nii = float(row.get("nii_subscription_x") or 0)
    if   nii >= 200: score += 15
    elif nii >= 100: score += 12
    elif nii >= 50:  score += 8
    elif nii >= 20:  score += 5
    elif nii >= 5:   score += 2

    gmp = float(row.get("gmp_percentage") or 0)
    if   gmp >= 50:  score += 20
    elif gmp >= 30:  score += 16
    elif gmp >= 15:  score += 12
    elif gmp >= 5:   score += 7
    elif gmp > 0:    score += 3
    elif gmp < -5:   score -= 5

    ofs = float(row.get("ofs_pct") or 0)
    if   ofs == 0:   score += 15
    elif ofs <= 20:  score += 12
    elif ofs <= 40:  score += 8
    elif ofs <= 60:  score += 4
    elif ofs <= 80:  score += 1

    sector = str(row.get("sector") or "").lower()
    hot    = ["defense","railway","psu","capital goods","engineering","renewable","infra"]
    warm   = ["pharma","hospital","financial","nbfc","consumer","fmcg","technology"]
    cold   = ["real estate","media","telecom"]
    if   any(s in sector for s in hot):  score += 10
    elif any(s in sector for s in warm): score += 6
    elif any(s in sector for s in cold): score += 2
    else:                                 score += 4

    p10 = probs.get("prob_above_10", 0)
    if   p10 >= 70: score += 15
    elif p10 >= 55: score += 10
    elif p10 >= 40: score += 6
    elif p10 >= 25: score += 3

    return min(100, max(0, score))


def get_action(lqi, prob_above_10, prob_loss):
    if lqi >= 75 and prob_above_10 >= 60:
        return "MOMENTUM CHASE", "Buy at listing open if above issue price and VWAP"
    elif lqi >= 55 and prob_above_10 >= 45:
        return "VALUE DIP BUY", "Wait near issue price or anchored VWAP"
    elif lqi >= 40:
        return "TACTICAL HOLD", "Wait for 30-day lock-in expiry before deciding"
    else:
        return "AVOID", "Risk/reward not favorable based on similar IPOs"


def get_confidence(n_similar, avg_sim):
    if n_similar >= 8 and avg_sim >= 0.85: return "HIGH"
    if n_similar >= 5 and avg_sim >= 0.70: return "MEDIUM"
    return "LOW"


def get_position_size(lqi, prob_above_10, gmp_pct):
    gmp = float(gmp_pct or 0)
    if gmp < 5:
        return "0 LOTS — GMP floor override"
    if lqi >= 85 and prob_above_10 >= 65 and gmp >= 10:
        return "2 LOTS (MAX CONVICTION)"
    elif lqi >= 70 and prob_above_10 >= 50:
        return "1 LOT (TACTICAL)"
    elif lqi >= 60:
        return "WATCHLIST ONLY"
    else:
        return "AVOID"


def load_training_data(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT company_name, sector, archetype,
               qib_subscription_x, nii_subscription_x, ofs_pct,
               gmp_percentage, listing_gap_pct, issue_size_cr, fresh_issue_ratio
        FROM ipo_intelligence
        WHERE listing_gap_pct IS NOT NULL
        ORDER BY company_name
    """)
    rows = cur.fetchall()
    log.info(f"Training data: {len(rows)} IPOs")
    return rows


def print_card(row, similar, probs, lqi, conn):
    name   = row.get("company_name", "Unknown")
    sector = row.get("sector", "Unknown")
    gap    = float(row.get("listing_gap_pct") or 0)
    qib    = float(row.get("qib_subscription_x") or 0)
    gmp    = float(row.get("gmp_percentage")  or 0)
    ofs    = float(row.get("ofs_pct")         or 0)

    n_sim   = len(similar)
    avg_sim = sum(s for s, _ in similar) / n_sim if similar else 0
    conf    = get_confidence(n_sim, avg_sim)
    action, action_detail = get_action(lqi, probs.get("prob_above_10", 0), probs.get("prob_loss", 0))
    pos_size = get_position_size(lqi, probs.get("prob_above_10", 0), gmp)

    print("\n" + "="*62)
    print(f"  AACapital IPO Intelligence")
    print(f"  {name}")
    print("="*62)
    print(f"  Sector          : {sector}")
    print(f"  QIB Sub         : {qib:.1f}x")
    print(f"  NII Sub         : {float(row.get('nii_subscription_x') or 0):.1f}x")
    print(f"  GMP             : {gmp:.1f}%")
    print(f"  OFS             : {ofs:.0f}%")
    if gap:
        print(f"  Listing Gain    : {gap:.1f}%  [{row.get('archetype')}]")
    print()
    print(f"  LQI Score       : {lqi}/100")
    print(f"  Position Size   : {pos_size}")
    print(f"  Confidence      : {conf}")
    print()
    print(f"  P(>10% gain)    : {probs.get('prob_above_10', 0):.1f}%")
    print(f"  P(>30% gain)    : {probs.get('prob_above_30', 0):.1f}%")
    print(f"  P(loss)         : {probs.get('prob_loss', 0):.1f}%")
    print(f"  Expected return : {probs.get('expected_return', 0):.1f}%")

    if probs.get("gmp_warning"):
        print(f"\n  ⚠ WARNING: {probs['gmp_warning']}")

    print()
    bp = probs.get("bucket_probs", {})
    for bucket in ["100+", "50-100", "30-50", "10-30", "0-10", "negative"]:
        pct = bp.get(bucket, 0)
        bar = "█" * int(pct / 5)
        print(f"    {bucket:<10} {pct:5.1f}%  {bar}")

    print()
    print(f"  Historically, IPOs like this had:")
    print(f"  {probs.get('prob_above_10', 0):.0f}% probability of >10% listing gains")
    print(f"  {probs.get('expected_return', 0):.1f}% median expected return")
    print()
    print(f"  Closest matches:")
    for sim, r in similar[:5]:
        rname = r.get("company_name", "?")
        rgap  = float(r.get("listing_gap_pct") or 0)
        rarch = r.get("archetype", "?")
        print(f"    {rname:<35} {rgap:+.1f}%  [{rarch}]  sim={sim:.2f}")
    print()
    print(f"  ACTION    : {action}")
    print(f"  DETAIL    : {action_detail}")
    print("="*62)


def save_scores(conn, rows, training_data, stats):
    cur   = conn.cursor()
    saved = 0

    for row in rows:
        similar = find_similar(row, training_data, stats, top_n=10)
        if not similar: continue

        probs = calculate_probabilities(similar)
        probs = apply_gmp_floor(
            probs,
            row.get("gmp_percentage"),
            row.get("lqi_final") or 50,
            row.get("qib_subscription_x"),
        )
        lqi   = calculate_lqi(row, probs)
        action, _ = get_action(lqi, probs.get("prob_above_10", 0), probs.get("prob_loss", 0))

        n_sim   = len(similar)
        avg_sim = sum(s for s, _ in similar) / n_sim if similar else 0
        conf    = get_confidence(n_sim, avg_sim)

        similar_names = json.dumps([r.get("company_name") for _, r in similar[:5]])

        cur.execute("""
            UPDATE ipo_intelligence SET
                lqi_final         = %s,
                prob_10pct_profit = %s,
                prob_loss_gt10    = %s,
                expected_return   = %s,
                confidence_level  = %s,
                archetype         = COALESCE(NULLIF(archetype, 'UNKNOWN'), %s),
                suggested_action  = %s,
                similar_ipos      = %s,
                updated_at        = NOW()
            WHERE company_name = %s
        """, [
            float(lqi),
            round(float(probs.get("prob_above_10") or 0), 2),
            round(float(probs.get("prob_loss")     or 0), 2),
            round(float(probs.get("expected_return") or 0), 2),
            conf,
            row.get("archetype"),
            action,
            similar_names,
            row["company_name"],
        ])
        saved += 1
        if saved % 50 == 0:
            conn.commit()
            log.info(f"  Saved {saved} scores...")

    conn.commit()
    log.info(f"Saved {saved} LQI scores to Neon")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ipo",  type=str,          help="Score a specific IPO")
    parser.add_argument("--all",  action="store_true", help="Score all IPOs and save")
    parser.add_argument("--test", action="store_true", help="Test on 5 known IPOs")
    args = parser.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set")
        return

    conn = psycopg2.connect(DATABASE_URL)
    log.info("Connected to Neon")

    training_data = load_training_data(conn)
    stats         = compute_stats(training_data)

    if args.ipo:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT company_name, sector, archetype,
                   qib_subscription_x, nii_subscription_x, ofs_pct,
                   gmp_percentage, listing_gap_pct, issue_size_cr, fresh_issue_ratio
            FROM ipo_intelligence WHERE company_name ILIKE %s
        """, [f"%{args.ipo}%"])
        for row in cur.fetchall():
            similar = find_similar(row, training_data, stats)
            probs   = calculate_probabilities(similar)
            probs   = apply_gmp_floor(probs, row.get("gmp_percentage"),
                                      50, row.get("qib_subscription_x"))
            lqi     = calculate_lqi(row, probs)
            print_card(row, similar, probs, lqi, conn)

    elif args.test:
        tests = ["BLS E-Services", "Carraro India", "Bharti Hexacom",
                 "Bansal Wire", "Aether Industries"]
        cur   = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        for name in tests:
            cur.execute("""
                SELECT company_name, sector, archetype,
                       qib_subscription_x, nii_subscription_x, ofs_pct,
                       gmp_percentage, listing_gap_pct, issue_size_cr, fresh_issue_ratio
                FROM ipo_intelligence WHERE company_name = %s
            """, [name])
            row = cur.fetchone()
            if row:
                similar = find_similar(row, training_data, stats)
                probs   = calculate_probabilities(similar)
                probs   = apply_gmp_floor(probs, row.get("gmp_percentage"),
                                          50, row.get("qib_subscription_x"))
                lqi     = calculate_lqi(row, probs)
                print_card(row, similar, probs, lqi, conn)

    elif args.all:
        log.info("Scoring all IPOs...")
        save_scores(conn, training_data, training_data, stats)

        cur = conn.cursor()
        cur.execute("""
            SELECT company_name, lqi_final, prob_10pct_profit,
                   expected_return, archetype, suggested_action
            FROM ipo_intelligence
            WHERE lqi_final IS NOT NULL
            ORDER BY lqi_final DESC
            LIMIT 10
        """)
        print(f"\nTOP 10 IPOs by LQI:")
        print(f"{'Company':<35} {'LQI':>5} {'P(>10%)':>8} {'Exp.Ret':>8} {'Archetype':<12} Action")
        print("-"*85)
        for r in cur.fetchall():
            print(f"{r[0]:<35} {r[1] or 0:>5.0f} {r[2] or 0:>7.1f}% "
                  f"{r[3] or 0:>7.1f}% {r[4] or '?':<12} {r[5] or '?'}")
    else:
        parser.print_help()

    conn.close()


if __name__ == "__main__":
    main()
