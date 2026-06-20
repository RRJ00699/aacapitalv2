"""
_scripts/ipo/ipo_play_selector.py
===================================
AACapital IPO Play Selector — trained on real Kite post-listing returns.

Answers ONE question per IPO:
  "Can I make money from this IPO in the next 1–5 trading sessions?"

Uses 340 historical IPOs with real Day1/30/90/365 returns to:
  1. Compute archetype (MOMENTUM / VALUE_DIP / OPERATOR_TRAP / QUALITY_GROWTH)
  2. Select the best play (7 options)
  3. Compute confidence from historical similarity
  4. Update play_recommendation in ipo_intelligence

Usage:
  python _scripts/ipo/ipo_play_selector.py              # update all IPOs
  python _scripts/ipo/ipo_play_selector.py --company "Bajaj Housing"
  python _scripts/ipo/ipo_play_selector.py --stats       # show model stats
"""

import os, sys, math, json, logging, argparse, datetime
import psycopg2, psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def n(v, d=0.0):
    try:
        if v is None: return d
        f = float(v)
        return d if math.isnan(f) or math.isinf(f) else f
    except: return d

# ── STEP 1: Compute historical base rates from real Kite data ─────────────────

def compute_base_rates(conn) -> dict:
    """
    Compute base rates from 340 historical IPOs with real returns.
    This IS the training data.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            company_name, sector, is_sme,
            issue_size_cr, issue_price,
            qib_subscription_x, nii_subscription_x, rii_subscription_x,
            total_subscription_x,
            return_listing_open, return_day1_close,
            return_day7, return_day30, return_day90, return_day365,
            max_upside_30d, max_drawdown_30d,
            hit_uc_day1, hit_lc_day1,
            anchor_lock30_date, anchor_lock90_date,
            anchor_tier1_count, anchor_alloc_pct,
            brlm_score, roe, roce, ipo_pe_post, peer_median_pe,
            operator_risk_score, fresh_issue_ratio, ofs_pct
        FROM ipo_intelligence
        WHERE return_listing_open IS NOT NULL
          AND is_sme = FALSE
          AND issue_size_cr >= 150
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()

    log.info(f"Training on {len(rows)} historical IPOs with real returns")

    # Bucket by QIB tier
    qib_buckets = {
        "ultra":  [r for r in rows if n(r['qib_subscription_x']) >= 100],
        "high":   [r for r in rows if 50 <= n(r['qib_subscription_x']) < 100],
        "medium": [r for r in rows if 20 <= n(r['qib_subscription_x']) < 50],
        "low":    [r for r in rows if 5  <= n(r['qib_subscription_x']) < 20],
        "weak":   [r for r in rows if n(r['qib_subscription_x']) < 5],
    }

    def stats(bucket):
        if not bucket: return {}
        opens = [n(r['return_listing_open']) for r in bucket if r['return_listing_open']]
        d30   = [n(r['return_day30']) for r in bucket if r['return_day30']]
        d365  = [n(r['return_day365']) for r in bucket if r['return_day365']]
        ucs   = [r for r in bucket if r.get('hit_uc_day1')]
        lcs   = [r for r in bucket if r.get('hit_lc_day1')]
        return {
            'count':        len(bucket),
            'avg_open':     sum(opens)/len(opens) if opens else 0,
            'avg_day30':    sum(d30)/len(d30) if d30 else 0,
            'avg_day365':   sum(d365)/len(d365) if d365 else 0,
            'pct_positive_open': sum(1 for x in opens if x > 5) / len(opens) * 100 if opens else 0,
            'pct_negative_open': sum(1 for x in opens if x < -5) / len(opens) * 100 if opens else 0,
            'pct_uc_day1':  len(ucs) / len(bucket) * 100,
            'pct_lc_day1':  len(lcs) / len(bucket) * 100,
        }

    base_rates = {k: stats(v) for k, v in qib_buckets.items()}

    # Overall stats
    all_opens = [n(r['return_listing_open']) for r in rows if r['return_listing_open']]
    base_rates['overall'] = {
        'count':       len(rows),
        'avg_open':    sum(all_opens)/len(all_opens) if all_opens else 0,
        'pct_positive': sum(1 for x in all_opens if x > 5) / len(all_opens) * 100 if all_opens else 0,
        'pct_negative': sum(1 for x in all_opens if x < -5) / len(all_opens) * 100 if all_opens else 0,
    }

    log.info(f"  QIB ultra (100x+): {base_rates['ultra'].get('count',0)} IPOs, "
             f"avg open {base_rates['ultra'].get('avg_open',0):.1f}%")
    log.info(f"  QIB high (50-100x): {base_rates['high'].get('count',0)} IPOs, "
             f"avg open {base_rates['high'].get('avg_open',0):.1f}%")
    log.info(f"  QIB medium (20-50x): {base_rates['medium'].get('count',0)} IPOs, "
             f"avg open {base_rates['medium'].get('avg_open',0):.1f}%")
    log.info(f"  Overall positive: {base_rates['overall']['pct_positive']:.0f}%")

    return base_rates, rows

# ── STEP 2: Archetype classifier ──────────────────────────────────────────────

def classify_archetype(ipo: dict, base_rates: dict, historical: list) -> str:
    """
    Classify IPO into one of 4 archetypes using real historical patterns.
    """
    qib      = n(ipo.get('qib_subscription_x'))
    ret_open = n(ipo.get('return_listing_open'))
    ret_30   = n(ipo.get('return_day30'))
    size     = n(ipo.get('issue_size_cr'))
    op_risk  = n(ipo.get('operator_risk_score'))
    tier1    = n(ipo.get('anchor_tier1_count'))

    # OPERATOR_TRAP: small size, weak QIB, retail mania
    if size < 300 and qib < 10 and op_risk > 50:
        return "OPERATOR_TRAP"

    # Post-listing classification (if we have returns)
    if ret_open != 0:
        if ret_open > 20 and qib >= 20:
            if n(ipo.get('return_day365')) > 30:
                return "QUALITY_GROWTH"
            return "MOMENTUM_CHASE"

        if ret_open < -5 and tier1 >= 10 and n(ipo.get('return_day90')) > 10:
            return "VALUE_DIP_BUY"

        if ret_open < -10:
            return "OPERATOR_TRAP"

    # Pre-listing classification
    if qib >= 50 and tier1 >= 15:
        return "MOMENTUM_CHASE"
    if qib >= 20 and n(ipo.get('roe')) > 15:
        return "QUALITY_GROWTH"
    if qib < 5:
        return "OPERATOR_TRAP"

    return "VALUE_DIP_BUY"

# ── STEP 3: Historical similarity ─────────────────────────────────────────────

def find_similar_historical(ipo: dict, historical: list, n_similar: int = 10) -> list:
    """Find most similar historical IPOs by QIB, size, sector, anchors."""
    qib    = n(ipo.get('qib_subscription_x'))
    size   = n(ipo.get('issue_size_cr'))
    sector = str(ipo.get('sector') or '')
    tier1  = n(ipo.get('anchor_tier1_count'))

    scored = []
    for h in historical:
        if not h.get('return_listing_open'):
            continue
        h_qib    = n(h.get('qib_subscription_x'))
        h_size   = n(h.get('issue_size_cr'))
        h_sector = str(h.get('sector') or '')
        h_tier1  = n(h.get('anchor_tier1_count'))

        # Similarity score (lower = more similar)
        qib_diff    = abs(qib - h_qib) / max(qib, h_qib, 1) * 40
        size_diff   = abs(size - h_size) / max(size, h_size, 1) * 20
        sector_same = 0 if sector == h_sector else 20
        tier1_diff  = abs(tier1 - h_tier1) * 2

        similarity = 100 - (qib_diff + size_diff + sector_same + tier1_diff)
        scored.append((similarity, h))

    scored.sort(key=lambda x: -x[0])
    return [h for _, h in scored[:n_similar]]

# ── STEP 4: Play selector ──────────────────────────────────────────────────────

def select_play(ipo: dict, base_rates: dict, historical: list) -> dict:
    """
    Select the best play from 7 options using real historical data.
    """
    qib      = n(ipo.get('qib_subscription_x'))
    nii      = n(ipo.get('nii_subscription_x'))
    ret_open = n(ipo.get('return_listing_open'))
    ret_30   = n(ipo.get('return_day30'))
    ret_90   = n(ipo.get('return_day90'))
    ret_365  = n(ipo.get('return_day365'))
    size     = n(ipo.get('issue_size_cr'))
    op_risk  = n(ipo.get('operator_risk_score'))
    tier1    = n(ipo.get('anchor_tier1_count'))
    brlm     = n(ipo.get('brlm_score'), 50)
    roe      = n(ipo.get('roe'))
    ipo_pe   = n(ipo.get('ipo_pe_post'))
    peer_pe  = n(ipo.get('peer_median_pe'))
    uc_day1  = ipo.get('hit_uc_day1')
    lc_day1  = ipo.get('hit_lc_day1')
    archetype = ipo.get('archetype', '')

    # Get QIB bucket rates
    if qib >= 100: bucket = base_rates.get('ultra', {})
    elif qib >= 50: bucket = base_rates.get('high', {})
    elif qib >= 20: bucket = base_rates.get('medium', {})
    elif qib >= 5:  bucket = base_rates.get('low', {})
    else:           bucket = base_rates.get('weak', {})

    # Find similar IPOs
    similar = find_similar_historical(ipo, historical)
    sim_opens = [n(h['return_listing_open']) for h in similar if h.get('return_listing_open')]
    sim_avg_open = sum(sim_opens)/len(sim_opens) if sim_opens else 0
    sim_pct_positive = sum(1 for x in sim_opens if x > 5)/len(sim_opens)*100 if sim_opens else 50

    reasons = []

    # ── INSTANT REJECT ────────────────────────────────────────────────────────
    if size > 0 and size < 150:
        return _play("AVOID", 92, ["Issue size ₹{:.0f}Cr — 5% circuit band, operator trap".format(size)], 0, 0, "—")

    if op_risk > 70:
        return _play("AVOID", 82, [f"High operator risk score ({op_risk:.0f})"], 0, 0, "—")

    if brlm < 40:
        return _play("AVOID", 75, [f"BRLM score {brlm:.0f}/100 — history of overpricing and abandonment"], 0, 0, "—")

    if lc_day1:
        return _play("AVOID", 88, ["Hit lower circuit on Day 1 — trapped liquidity, no exit"], 0, 0, "—")

    # ── BUY LISTED PEER ───────────────────────────────────────────────────────
    if ipo_pe > 0 and peer_pe > 0 and ipo_pe > peer_pe * 3:
        premium = (ipo_pe / peer_pe - 1) * 100
        return _play("BUY_PEER", 70,
            [f"IPO PE {ipo_pe:.0f}x vs sector PE {peer_pe:.0f}x (+{premium:.0f}%) — listed peers offer better value"],
            4, 15, "normal")

    # ── POST-LISTING SIGNALS (historical IPO — for backtest label) ────────────
    if ret_open != 0:
        # UC Day 1 pattern
        if uc_day1:
            uc_d2_rate = base_rates['overall'].get('pct_uc_day1', 30)
            return _play("BUY_AT_OPEN", 80,
                ["Hit upper circuit Day 1 — high probability of gap-up Day 2",
                 f"Similar IPOs avg open: +{sim_avg_open:.1f}%"],
                4, ret_open + 10, "30min → EOD")

        # Listed below GMP with anchors = panic dip
        if ret_open < -5 and tier1 >= 10:
            reasons = [
                f"Listed {ret_open:.1f}% — retail panic sell",
                f"{tier1:.0f} tier-1 anchors = institutional support floor",
                f"Historical: similar IPOs avg +{sim_avg_open:.1f}% open"
            ]
            # Check if Day30 recovers (from historical data)
            good_recovery = ret_30 > 15 if ret_30 else sim_avg_open > 10
            conf = 74 if good_recovery else 60
            return _play("BUY_PANIC_DIP", conf, reasons, 6, max(20, abs(ret_open)), "Day 1-3")

        # Strong open + strong QIB
        if ret_open > 10 and qib >= 30:
            reasons = [
                f"QIB {qib:.0f}x + listed +{ret_open:.0f}% — institutional demand confirmed",
                f"Similar IPOs: {sim_pct_positive:.0f}% positive open",
            ]
            return _play("BUY_AT_OPEN", min(85, 55 + qib/5), reasons, 4, ret_open + 8, "30min → EOD")

        if ret_open > 15:
            return _play("WAIT_FOR_VWAP", 65,
                [f"Listed +{ret_open:.1f}% — wait for VWAP confirmation",
                 f"Avg similar: +{sim_avg_open:.1f}%"],
                5, ret_open + 5, "10:30AM → EOD")

        if 0 < ret_open <= 15 and qib >= 10:
            return _play("BUY_AFTER_DAY3", 62,
                [f"Listed +{ret_open:.1f}% with QIB {qib:.0f}x — moderate setup, buy after Day 3 dip",
                 f"Similar IPOs avg: +{sim_avg_open:.1f}%"],
                5, 12, "1 week")

        if 0 < ret_open <= 15:
            return _play("WAIT_FOR_VWAP", 58,
                [f"Listed +{ret_open:.1f}% — weak QIB {qib:.0f}x, VWAP confirmation needed"],
                5, ret_open + 3, "10:30AM → EOD")

        if -5 <= ret_open <= 0:
            if tier1 >= 8:
                return _play("BUY_PANIC_DIP", 60,
                    [f"Listed flat/slight negative ({ret_open:.1f}%) with {tier1:.0f} tier-1 anchors"],
                    6, 15, "Day 1-3")
            return _play("BUY_AFTER_DAY3", 55,
                [f"Listed near flat {ret_open:.1f}% — wait for Day 3 direction confirmation"],
                5, 10, "1 week")

        if ret_open < -5:
            if roe > 15 and tier1 >= 5:
                return _play("BUY_AFTER_DAY3", 60,
                    [f"Listed {ret_open:.1f}% but ROE {roe:.0f}% + quality anchors — wait for stabilization"],
                    5, 15, "1 week")
            return _play("AVOID", 65,
                [f"Negative listing {ret_open:.1f}% without strong institutional support"],
                0, 0, "—")

    # ── PRE-LISTING SIGNALS (upcoming IPO) ────────────────────────────────────
    hist_pct_pos = bucket.get('pct_positive_open', 50)
    hist_avg     = bucket.get('avg_open', 10)

    if qib >= 100 and tier1 >= 15:
        reasons = [
            f"QIB {qib:.0f}x — ultra-high institutional demand",
            f"{tier1:.0f} tier-1 anchors (LIC/SBI/ICICI/Nippon/ADIA)",
            f"Historical: {hist_pct_pos:.0f}% of similar IPOs gave positive open",
            f"Avg open for QIB 100x+: +{hist_avg:.1f}%",
        ]
        conf = min(90, 65 + qib/20 + tier1)
        return _play("BUY_AT_OPEN", round(conf), reasons, 4, hist_avg + 5, "30min → EOD")

    if qib >= 50 and tier1 >= 10:
        reasons = [
            f"QIB {qib:.0f}x — strong institutional demand",
            f"Historical: {hist_pct_pos:.0f}% of QIB 50x+ IPOs gave positive open",
            f"Avg open: +{hist_avg:.1f}%",
        ]
        conf = min(84, 60 + qib/15)
        return _play("BUY_AT_OPEN", round(conf), reasons, 4, hist_avg, "30min → EOD")

    if qib >= 20:
        reasons = [
            f"QIB {qib:.0f}x — decent institutional demand",
            f"Historical: {hist_pct_pos:.0f}% positive open for this QIB range",
            "Wait for VWAP before entry",
        ]
        return _play("WAIT_FOR_VWAP", 65, reasons, 5, hist_avg, "10:30AM → EOD")

    if qib >= 5 and roe > 15 and tier1 >= 5:
        return _play("BUY_AFTER_DAY3", 58,
            [f"Moderate QIB {qib:.0f}x but strong fundamentals (ROE {roe:.0f}%)"],
            5, 12, "1 week")

    if qib >= 5 and tier1 >= 15:
        return _play("BUY_AFTER_ANCHOR", 55,
            [f"Quality anchors ({tier1:.0f} tier-1) despite weak subscription — buy at T+30 dip"],
            8, 25, "1 month")

    # Moderate setup — not strong enough for open, but not avoid
    if qib >= 10 and tier1 >= 5:
        return _play("BUY_AFTER_DAY3", 55,
            [f"Moderate QIB {qib:.0f}x with {tier1:.0f} quality anchors — buy after Day 3 stabilization"],
            5, 12, "1 week")

    if tier1 >= 15 and size >= 500:
        return _play("BUY_AFTER_ANCHOR", 55,
            [f"Quality anchors ({tier1:.0f} tier-1), large IPO — buy at T+30 anchor unlock dip"],
            8, 20, "1 month")

    return _play("AVOID", 60, ["Insufficient conviction — no clear edge in this IPO"], 0, 0, "—")


def _play(play, conf, reasons, stop_loss, target, window):
    return {
        "play_recommendation": play,
        "play_confidence":     min(95, max(30, round(conf))),
        "play_reasons":        json.dumps(reasons),
        "play_stop_loss_pct":  stop_loss,
        "play_target_pct":     target,
        "play_hold_window":    window,
        "play_updated_at":     datetime.datetime.now(datetime.timezone.utc),
    }

# ── STEP 5: Archetype labeling ────────────────────────────────────────────────

def label_archetype_from_returns(ipo: dict) -> str:
    """
    Label historical IPOs with actual archetype based on realized returns.
    This is the ground truth for ML training.
    """
    ret_open = n(ipo.get('return_listing_open'))
    ret_30   = n(ipo.get('return_day30'))
    ret_365  = n(ipo.get('return_day365'))
    qib      = n(ipo.get('qib_subscription_x'))
    size     = n(ipo.get('issue_size_cr'))
    op_risk  = n(ipo.get('operator_risk_score'))
    tier1    = n(ipo.get('anchor_tier1_count'))
    lc       = ipo.get('hit_lc_day1')

    if size < 200 and op_risk > 50:
        return "OPERATOR_TRAP"
    if lc:
        return "OPERATOR_TRAP"
    if ret_open < -10 and ret_30 < -15:
        return "OPERATOR_TRAP"

    if ret_open > 20 and qib >= 20 and ret_365 > 30:
        return "QUALITY_GROWTH"
    if ret_open > 15 and qib >= 30:
        return "MOMENTUM_CHASE"
    if ret_open < -5 and tier1 >= 10 and ret_30 > 10:
        return "VALUE_DIP_BUY"
    if ret_open > 5:
        return "MOMENTUM_CHASE"

    return "VALUE_DIP_BUY"

# ── Main ──────────────────────────────────────────────────────────────────────

def show_stats(conn, base_rates):
    """Print model statistics."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT play_recommendation, COUNT(*) as n,
               AVG(return_listing_open) as avg_open,
               AVG(return_day30) as avg_30d,
               COUNT(CASE WHEN return_listing_open > 10 THEN 1 END) as positive,
               COUNT(CASE WHEN return_listing_open < -5 THEN 1 END) as negative
        FROM ipo_intelligence
        WHERE play_recommendation IS NOT NULL
          AND return_listing_open IS NOT NULL
          AND is_sme = FALSE
        GROUP BY play_recommendation
        ORDER BY n DESC
    """)
    rows = cur.fetchall()
    cur.close()

    log.info("\n" + "="*70)
    log.info("PLAY SELECTOR BACKTESTING RESULTS (on 340 historical IPOs)")
    log.info("="*70)
    for r in rows:
        play = r['play_recommendation']
        n_ipos = r['n']
        avg_open = n(r['avg_open'])
        avg_30d  = n(r['avg_30d'])
        pos = r['positive'] or 0
        neg = r['negative'] or 0
        total = n_ipos
        log.info(f"  {play:20s} {n_ipos:3d} IPOs | "
                 f"avg open {avg_open:+6.1f}% | "
                 f"avg 30d {avg_30d:+6.1f}% | "
                 f"✅{pos:3d} ❌{neg:3d}")
    log.info("="*70)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--company", help="Filter by company name")
    p.add_argument("--stats", action="store_true", help="Show model statistics only")
    p.add_argument("--limit", type=int, default=500)
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_db()
    log.info("Connected to Neon DB")

    base_rates, historical_ipos = compute_base_rates(conn)

    if args.stats:
        show_stats(conn, base_rates)
        conn.close()
        return

    # Load all IPOs to update
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    q = """
        SELECT id, company_name, sector, is_sme,
               issue_size_cr, issue_price, fresh_issue_ratio, ofs_pct,
               qib_subscription_x, nii_subscription_x, rii_subscription_x,
               total_subscription_x,
               listing_date, listing_open,
               return_listing_open, return_day1_close,
               return_day7, return_day30, return_day90, return_day365,
               max_upside_30d, max_drawdown_30d,
               hit_uc_day1, hit_lc_day1,
               anchor_tier1_count, anchor_lock30_date, anchor_lock90_date,
               brlm_score, brlm_names,
               roe, roce, ipo_pe_post, peer_median_pe,
               operator_risk_score, archetype,
               gmp_pct_t1, gmp_momentum
        FROM ipo_intelligence
        WHERE is_sme = FALSE
    """
    params = []
    if args.company:
        q += " AND company_name ILIKE %s"
        params.append(f"%{args.company}%")
    q += " ORDER BY listing_date DESC NULLS LAST LIMIT %s"
    params.append(args.limit)

    cur.execute(q, params)
    ipos = [dict(r) for r in cur.fetchall()]
    cur.close()
    log.info(f"Processing {len(ipos)} IPOs")
    log.info("="*60)

    ok = 0
    play_counts = {}

    for ipo in ipos:
        company = ipo['company_name']

        # Label archetype from real returns
        if ipo.get('return_listing_open') is not None:
            archetype = label_archetype_from_returns(ipo)
        else:
            archetype = classify_archetype(ipo, base_rates, historical_ipos)

        # Select play
        play_data = select_play(ipo, base_rates, historical_ipos)
        play_data['archetype'] = archetype

        # Update DB
        cur2 = conn.cursor()
        cols = list(play_data.keys())
        vals = [play_data[c] for c in cols]
        set_clause = ', '.join([f"{c} = %s" for c in cols])
        try:
            cur2.execute(f"UPDATE ipo_intelligence SET {set_clause} WHERE id = %s",
                        vals + [ipo['id']])
            conn.commit()
            ok += 1
            play = play_data['play_recommendation']
            play_counts[play] = play_counts.get(play, 0) + 1
        except Exception as e:
            log.warning(f"  {company}: {e}")
            conn.rollback()
        finally:
            cur2.close()

    conn.close()

    log.info("="*60)
    log.info(f"Updated {ok}/{len(ipos)} IPOs")
    log.info("\nPlay distribution:")
    for play, count in sorted(play_counts.items(), key=lambda x: -x[1]):
        log.info(f"  {play:22s}: {count}")
    log.info("\nRun with --stats to see backtesting results")

if __name__ == "__main__":
    main()
