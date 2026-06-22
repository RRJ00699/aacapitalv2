"""
_scripts/ipo/ipo_play_selector.py
===================================
Runs the play selection engine on ALL IPOs in ipo_intelligence.
Called by:
  - weekly-ipo-calendar.yml (Sunday 6 PM IST)
  - After import_chittorgarh.py
  - Manually: python _scripts/ipo/ipo_play_selector.py

What it does:
  1. Reads all IPOs from ipo_intelligence
  2. For each: runs the 7-answer play logic (BUY_AT_OPEN / WAIT / AVOID etc.)
  3. Updates play_recommendation, play_confidence, play_reasons in Neon
  4. Also computes archetype: MOMENTUM_CHASE / VALUE_DIP / OPERATOR_TRAP / QUALITY_GROWTH

Usage:
  python _scripts/ipo/ipo_play_selector.py               # all IPOs
  python _scripts/ipo/ipo_play_selector.py --recent 30   # last 30 days only
  python _scripts/ipo/ipo_play_selector.py --symbol NSDL # single IPO
"""

import os, sys, json, math, logging, argparse, datetime
import psycopg2, psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

TIER1_ANCHORS = {
    "lic","life insurance","sbi mutual","sbi mf","icici prudential","icici pru",
    "nippon","hdfc mutual","hdfc mf","kotak mutual","kotak mf","adia","abu dhabi",
    "gic","singapore","norway","temasek","axis mutual","axis mf","dsp","mirae",
    "franklin","motilal","canara robeco","tata mutual","tata mf","birla","uti mf",
}

def n(v, default=0.0):
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)): return default
        return float(v)
    except: return default

def get_db():
    from urllib.parse import urlparse, unquote
    p = urlparse(DATABASE_URL)
    return psycopg2.connect(
        host=p.hostname, port=p.port or 5432,
        dbname=p.path.lstrip("/"),
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
    )

# ── Archetype classification ───────────────────────────────────────────────────
def classify_archetype(row: dict) -> str:
    qib        = n(row.get("qib_subscription_x"))
    gmp_trend  = str(row.get("gmp_momentum","")).upper()
    anchor_t1  = n(row.get("anchor_tier1_count"))
    issue_size = n(row.get("issue_size_cr"))
    ofs_pct    = n(row.get("ofs_pct"))
    retail_x   = n(row.get("rii_subscription_x"))
    lqi        = n(row.get("lqi_final"))
    list_vs_gmp= n(row.get("listing_vs_gmp_pct"))

    if issue_size < 300 and retail_x > 50 and qib < 5:
        return "OPERATOR_TRAP"
    if qib >= 50 and gmp_trend in ("RISING","STABLE") and anchor_t1 >= 10:
        return "MOMENTUM_CHASE"
    if list_vs_gmp < -5 and lqi >= 65:
        return "VALUE_DIP_BUY"
    if anchor_t1 >= 20 and ofs_pct < 60:
        return "QUALITY_GROWTH"
    return "WATCH"

# ── Play selection (The 7 Answers from IPO Playbook) ──────────────────────────
def compute_play(row: dict) -> dict:
    issue_size   = n(row.get("issue_size_cr"))
    op_risk      = n(row.get("operator_risk_score"))
    gmp_trend    = str(row.get("gmp_momentum","")).upper()
    gmp_t1       = n(row.get("gmp_pct_t1") or row.get("gmp_day_before_pct"))
    qib_x        = n(row.get("qib_subscription_x"))
    retail_x     = n(row.get("rii_subscription_x"))
    anchor_t1    = n(row.get("anchor_tier1_count"))
    lqi          = n(row.get("lqi_final"))
    listing_vs_gmp = n(row.get("listing_vs_gmp_pct"))
    listing_open = n(row.get("listing_open"))
    issue_price  = n(row.get("issue_price"))
    brlm_score   = n(row.get("brlm_score", 50))
    pe_premium   = n(row.get("valuation_premium_pct"))
    regime       = str(row.get("listing_regime") or "NORMAL").upper()
    ftr          = n(row.get("float_turnover_ratio"))

    # ── INSTANT REJECTS ───────────────────────────────────────────────────────
    if issue_size > 0 and issue_size < 150:
        return _play("AVOID", 95,
            ["Issue size < ₹150 Cr — 5% circuit band, operator manipulation territory"], 0, 0, "—")

    if op_risk > 70:
        return _play("AVOID", 85,
            [f"Operator risk {op_risk:.0f}/100 — SME/manipulation pattern"], 0, 0, "—")

    if regime == "BLACK_SWAN":
        return _play("AVOID", 90, ["Black swan event — all IPO trades suspended"], 0, 0, "—")

    if gmp_trend == "COLLAPSING" or gmp_t1 < -5:
        return _play("AVOID", 80, ["GMP collapsing — retail demand evaporating"], 0, 0, "—")

    if brlm_score < 45:
        return _play("AVOID", 70,
            [f"BRLM score {brlm_score:.0f}/100 — history of overpricing and abandonment"], 0, 0, "—")

    if qib_x < 5 and retail_x > 50:
        return _play("AVOID", 75,
            ["QIB < 5x but retail > 50x — no institutional conviction, retail mania"], 0, 0, "—")

    # ── BUY LISTED PEER ───────────────────────────────────────────────────────
    if pe_premium > 200 and lqi < 65:
        return _play("BUY_PEER", 70,
            [f"IPO PE {pe_premium:.0f}% above sector — listed peers offer better value"], 5, 15, "normal")

    # ── LISTING DAY SIGNALS (if listing data available) ───────────────────────
    if listing_open > 0 and issue_price > 0:
        listing_vs_issue = (listing_open / issue_price - 1) * 100
        gmp_price = issue_price * (1 + gmp_t1/100) if gmp_t1 else issue_price

        # Euphoria trap — listed way above GMP
        if listing_vs_issue > 30 and qib_x < 30:
            return _play("AVOID", 78,
                ["Listed 30%+ above GMP + weak QIB — euphoria trap, institutions will sell"], 0, 0, "—")

        # Float Turnover Ratio — absorption complete
        if ftr > 0.8 and listing_open > issue_price:
            return _play("BUY_AT_OPEN", 84,
                [f"FTR {ftr:.2f} > 0.8 — weak hands absorbed, institutional accumulation confirmed",
                 "Entry window: 10:15–10:25 AM IST"], 4, 18, "30 min → EOD")

        # Listed below GMP + strong anchors = panic dip
        if listing_vs_gmp < -5 and anchor_t1 >= 10:
            return _play("BUY_PANIC_DIP", 76,
                [f"Listed {abs(listing_vs_gmp):.1f}% below GMP — retail panic selling",
                 f"{anchor_t1:.0f} tier-1 anchors (LIC/SBI/ICICI) provide institutional floor",
                 "Institutions accumulate into weakness — mean reversion within 3 days"], 6, 20, "Day 1–3")

        # VWAP setup
        if ftr < 0.8:
            return _play("WAIT_FOR_VWAP", 68,
                ["FTR < 0.8 — weak hands not fully flushed yet",
                 "Wait for VWAP crossover + 1.5x volume before entering"], 5, 15, "10:30 AM → EOD")

    # ── PRE-LISTING SIGNALS (night before) ───────────────────────────────────
    # Strong buy setup
    if qib_x >= 50 and anchor_t1 >= 15 and gmp_trend in ("RISING","STABLE") and lqi >= 70:
        conf = min(90, 55 + qib_x/10 + anchor_t1/2)
        reasons = [
            f"QIB {qib_x:.0f}x — strong institutional demand (threshold: 20x)",
            f"{anchor_t1:.0f} tier-1 anchors (LIC, SBI MF, ICICI, Nippon, ADIA)",
            f"GMP {gmp_trend.lower()} T-5 to T-1 — genuine retail demand",
            f"LQI {lqi:.0f}/100 — high quality score",
        ]
        if regime == "HOT": reasons.append("HOT market regime — upgrade confidence +20%"); conf = min(90, conf + 10)
        return _play("BUY_AT_OPEN", round(conf), reasons, 4, 20, "30 min → EOD")

    # Decent setup — wait for VWAP
    if qib_x >= 20 and anchor_t1 >= 8 and gmp_trend in ("RISING","STABLE") and lqi >= 55:
        return _play("WAIT_FOR_VWAP", 65,
            [f"QIB {qib_x:.0f}x — decent institutional demand",
             f"GMP {gmp_trend.lower()} — demand holding",
             "Not strong enough for market open — confirm with VWAP crossover"], 5, 14, "10:30 AM → EOD")

    # Good quality but GMP cooling = expect panic dip
    if lqi >= 75 and gmp_trend in ("FALLING","STABLE") and anchor_t1 >= 12:
        return _play("BUY_PANIC_DIP", 68,
            [f"Strong fundamentals (LQI {lqi:.0f}) but GMP cooling — listing likely below GMP",
             f"{anchor_t1:.0f} tier-1 anchors = institutional floor at issue price",
             "Buy the panic dip, not the hype — avg +20% return within 3 days"], 6, 18, "Day 1–3")

    # Day 3 stabilization play
    if lqi >= 75 and qib_x >= 25:
        return _play("BUY_AFTER_DAY3", 62,
            [f"Strong LQI {lqi:.0f} and QIB {qib_x:.0f}x but no clear listing signal",
             "Let Day 1–2 distribution clear, enter Day 3 when selling slows",
             "Entry trigger: Day 3 price > Day 2 close on declining volume"], 5, 12, "1 week")

    # Anchor unlock play (post T+30)
    if lqi >= 80:
        return _play("BUY_AFTER_ANCHOR", 56,
            [f"Quality IPO (LQI {lqi:.0f}) — best entry at anchor unlock window",
             "T+30 and T+90 dates create supply pressure = buy the dip",
             "NSDL, Bajaj Housing, HDB Financial pattern"], 8, 25, "1–4 weeks")

    return _play("AVOID", 58, ["Insufficient conviction for any entry — no clear edge"], 0, 0, "—")

def _play(p, conf, reasons, stop, target, hold):
    return {"play": p, "confidence": conf, "reasons": reasons,
            "stop_loss_pct": stop, "target_pct": target, "hold_window": hold}

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recent", type=int, help="Only IPOs listed in last N days")
    ap.add_argument("--symbol", help="Single symbol/company name")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Build WHERE clause
    where = "WHERE 1=1"
    if args.recent:
        cutoff = (datetime.date.today() - datetime.timedelta(days=args.recent)).isoformat()
        where += f" AND (listing_date >= '{cutoff}' OR listing_date IS NULL)"
    if args.symbol:
        s = args.symbol.replace("'","''")
        where += f" AND (symbol ILIKE '{s}' OR company_name ILIKE '%{s}%')"

    cur.execute(f"""
        SELECT id, company_name, symbol, issue_size_cr, operator_risk_score,
               gmp_pct_t1, gmp_day_before_pct, gmp_momentum, qib_subscription_x,
               rii_subscription_x, anchor_tier1_count, lqi_final, listing_vs_gmp_pct,
               listing_open, issue_price, brlm_score, valuation_premium_pct,
               float_turnover_ratio, listing_regime, ofs_pct
        FROM ipo_intelligence {where}
        ORDER BY listing_date DESC NULLS LAST
        LIMIT 500
    """)
    rows = cur.fetchall()
    log.info(f"Processing {len(rows)} IPOs")

    ok = 0
    play_counts: dict[str, int] = {}
    for row in rows:
        d  = dict(row)
        pl = compute_play(d)
        at = classify_archetype(d)
        play_counts[pl["play"]] = play_counts.get(pl["play"], 0) + 1

        if args.dry_run:
            log.info(f"  {d['company_name']}: {pl['play']} ({pl['confidence']}%) — {at}")
            continue

        with conn.cursor() as uc:
            uc.execute("""
                UPDATE ipo_intelligence SET
                    play_recommendation = %s,
                    play_confidence     = %s,
                    play_reasons        = %s,
                    play_stop_loss_pct  = %s,
                    play_target_pct     = %s,
                    play_hold_window    = %s,
                    play_updated_at     = NOW(),
                    archetype           = %s
                WHERE id = %s
            """, (pl["play"], pl["confidence"], json.dumps(pl["reasons"]),
                  pl["stop_loss_pct"], pl["target_pct"], pl["hold_window"], at, d["id"]))
        ok += 1
        if ok % 50 == 0:
            conn.commit()
            log.info(f"  {ok}/{len(rows)} updated")

    if not args.dry_run:
        conn.commit()
        log.info(f"\n✅ Updated {ok} IPOs")
        log.info("Play distribution:")
        for play, count in sorted(play_counts.items(), key=lambda x: -x[1]):
            log.info(f"  {play:20s}: {count}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
