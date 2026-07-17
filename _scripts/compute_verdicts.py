#!/usr/bin/env python3
"""
compute_verdicts.py — the master verdict engine (TRADE / WATCH / CAUTION / AVOID).

Rebuilt from the LOCKED, backtest-proven logic (IPO_BUSINESS_REQUIREMENTS.md):
  - Score bands are monotonic on clean data: AVOID 60% / NEUTRAL 73% /
    FAVORABLE 79% / STRONG 81% win. The band is the quantitative signal.
  - RHP forensic gate (ipo_rhp_intel) is the governance junk-detector.
  - Proven trade strategies: (1) gap 0-15% + bull = 62% win;
    (2) quality promoter + bull = 71% win.
  - Hard junk: issue size < Rs.200cr, or euphoric gap >70% (buying the top).

Writes ipo_verdicts (company_name PK) with the columns the UI reads:
  verdict, why_trade, why_caution, why_avoid, why_passes, regime,
  quality_promoter, ai_summary, score, confidence, sub_scores.

DERIVED -> DO UPDATE (Rule 1). Does NOT touch ipo_intelligence. DRY-RUN default.
  venv/bin/python _scripts/compute_verdicts.py            # dry (prints tally)
  venv/bin/python _scripts/compute_verdicts.py --apply    # write
"""
import os, sys, argparse, re

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

HARD_FLAGS = ["auditor_qualified", "sebi_action", "criminal_litigation"]
SOFT_FLAGS = ["related_party_concern", "ofs_heavy", "promoter_pledge_flag",
              "customer_concentration_high", "contingent_liabilities_material"]

def fnum(v):
    # tolerate poison values like '--0.0000' (double-sign) that leak from
    # upstream scrapers — strip a leading redundant sign before converting.
    if isinstance(v, str):
        v = v.strip()
        if v.startswith("--"): v = v[1:]      # '--0.00' -> '-0.00'
        if v in ("", "-", "--", "n/a", "NA", "null"): return None
    try: return float(v)
    except (TypeError, ValueError): return None

def decide(r):
    band = (r.get("score_band") or "").upper()
    size = fnum(r.get("issue_size_cr"))
    gap  = fnum(r.get("listing_gap_pct"))
    bull = r.get("regime_bull")           # True/False/None
    listed = r.get("listing_date") is not None and r.get("is_listed")
    pe   = fnum(r.get("ipo_pe")); ppe = fnum(r.get("peer_median_pe"))
    qib  = fnum(r.get("final_qib"))
    ofs  = fnum(r.get("ofs_pct"))
    anc  = fnum(r.get("anchor_count"))
    rhp_verdict = (r.get("rhp_verdict") or "").lower()
    rhp_gate = (r.get("rhp_gate") or "").lower()
    req_dd = r.get("requires_further_dd")
    hard = [f for f in HARD_FLAGS if r.get(f) is True]
    soft = [f for f in SOFT_FLAGS if r.get(f) is True]
    rhp_rejects = ("reject" in rhp_verdict or "avoid" in rhp_verdict
                   or "junk" in rhp_gate or "fail" in rhp_gate)

    trade, caution, avoid, passes = [], [], [], []

    # --- AVOID (hard junk) ---
    if band == "AVOID": avoid.append("score band AVOID (60% base — below the pack)")
    if size is not None and size < 200: avoid.append(f"issue size Rs.{size:.0f}cr < Rs.200cr junk floor")
    if gap is not None and gap > 70: avoid.append(f"listed +{gap:.0f}% (euphoric — buying the top)")
    if rhp_rejects: avoid.append("RHP forensic verdict rejects this IPO")
    if hard: avoid.append("RHP hard flag: " + ", ".join(f.replace("_"," ") for f in hard))

    # --- positive pass checks ---
    if band in ("STRONG", "FAVORABLE"): passes.append(f"score band {band}")
    if size is not None and size >= 2000: passes.append(f"mega issue Rs.{size:,.0f}cr (82% win)")
    elif size is not None and size >= 500: passes.append(f"size Rs.{size:,.0f}cr — liquid enough")
    if qib is not None and qib >= 10: passes.append(f"strong QIB demand ({qib:.0f}x)")
    if anc is not None and anc > 30: passes.append("anchors >30 (77% win)")
    if ofs is not None and ofs < 30: passes.append("fresh-heavy <30% OFS (82% win)")
    if not hard and not soft and rhp_verdict: passes.append("RHP forensic clean")

    # --- CAUTION (verify) ---
    if pe is not None and ppe and ppe > 0 and ppe*1.3 < pe <= ppe*2.5:
        caution.append(f"PE {pe:.0f} vs peer {ppe:.0f} — richer than peers, verify premium")
    elif pe is not None and ppe and ppe > 0 and pe > ppe*2.5:
        # >2.5x is compute_flags' "expensive" red-flag threshold — mirror it here so
        # the MOST overvalued IPOs don't escape the verdict rationale (bug: the old
        # window silently ended at 2.5x). Severity stays CAUTION to match the flag
        # scanner; escalation to AVOID is an owner call.
        caution.append(f"PE {pe:.0f} vs peer {ppe:.0f} — extreme premium (>{2.5:.1f}x peers, red-flagged)")
    if gap is not None and 15 <= gap <= 50:
        caution.append(f"gap +{gap:.0f}% (above sweet spot, coin-flip zone)")
    if req_dd: caution.append("RHP: requires further due diligence")
    for fl in soft: caution.append("RHP: " + fl.replace("_", " "))

    # --- TRADE (only once listed, gap known) ---
    quality = r.get("quality_promoter") is True
    not_junk = not avoid
    if not_junk and gap is not None and 0 <= gap < 15 and bull is True:
        trade.append(f"STRATEGY 1: gap +{gap:.0f}% (sweet spot) + bull → 62% win")
    if quality and bull is True and listed:
        trade.append("STRATEGY 2: quality promoter + bull → 71% win")

    # --- resolve verdict ---
    if avoid and not trade:
        verdict = "AVOID"
    elif trade:
        verdict = "TRADE"
    elif not listed:
        verdict = "WATCH"
        caution.append("not listed yet — gap at open decides the trade (see Playbook on listing day)")
    else:
        verdict = "CAUTION"

    conf = "high" if (band in ("STRONG", "AVOID") and rhp_verdict) else ("medium" if band else "low")
    return {
        "verdict": verdict,
        "why_trade": " · ".join(trade) or None,
        "why_caution": " · ".join(caution) or None,
        "why_avoid": " · ".join(avoid) or None,
        "why_passes": " · ".join(passes) or None,
        "quality_promoter": quality,
        "confidence": conf,
        "score": r.get("ipo_score"),
        "regime": ("bull" if bull is True else ("bear" if bull is False else None)),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(DB, connect_timeout=20)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if a.apply:
        cur.execute("""CREATE TABLE IF NOT EXISTS ipo_verdicts (
            company_name text PRIMARY KEY, verdict text, why_trade text,
            why_caution text, why_avoid text, why_passes text, regime text,
            quality_promoter boolean, ai_summary text, score numeric,
            confidence text, sub_scores jsonb, computed_at timestamptz DEFAULT now())""")
        conn.commit()

    # Introspect real columns first — never hardcode a name that might not exist
    # (the gmp_percentage lesson). Missing columns resolve to NULL, no crash.
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    ii = {r["column_name"] for r in cur.fetchall()}
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_rhp_intel'")
    ri = {r["column_name"] for r in cur.fetchall()}
    cur.execute("SELECT to_regclass('market_regimes') IS NOT NULL AS ok")
    has_regimes = bool(cur.fetchone()["ok"])
    def ic(name):  # ipo_intelligence column or NULL
        return f"i.{name} AS {name}" if name in ii else f"NULL AS {name}"
    def rc(name, alias=None):  # ipo_rhp_intel column or NULL
        a = alias or name
        return f"ri.{name} AS {a}" if name in ri else f"NULL AS {a}"
    cols = ["i.company_name",
            ic("score_band"), ic("ipo_score"), ic("issue_size_cr"), ic("listing_gap_pct"),
            ic("listing_date"), ic("ipo_pe"), ic("peer_median_pe"), ic("final_qib"),
            ic("ofs_pct"), ic("anchor_count"),
            "(i.listing_date IS NOT NULL AND i.listing_date <= CURRENT_DATE) AS is_listed",
            rc("verdict", "rhp_verdict"), rc("quality_gate", "rhp_gate"),
            rc("requires_further_dd"), rc("auditor_qualified"), rc("sebi_action"),
            rc("criminal_litigation"), rc("related_party_concern"), rc("ofs_heavy"),
            rc("promoter_pledge_flag"), rc("customer_concentration_high"),
            rc("contingent_liabilities_material")]
    # REGIME DEPRECATED (Rakesh 2026-07-17: "old regime, we don't use it now").
    # The table also lacks a `regime` column, which crashed verdicts for 2 days
    # (sink caught it). Always NULL — downstream already handles bull=None.
    regime_sql = "NULL"
    cur.execute(f"""
        SELECT {", ".join(cols)}, {regime_sql} AS regime_bull
        FROM ipo_intelligence i
        LEFT JOIN ipo_rhp_intel ri ON ri.company_name = i.company_name
        WHERE i.company_name IS NOT NULL
    """)
    rows = cur.fetchall()
    tally, wrote = {}, 0
    for r in rows:
        d = decide(r)
        tally[d["verdict"]] = tally.get(d["verdict"], 0) + 1
        if a.apply:
            cur.execute("""
                INSERT INTO ipo_verdicts
                  (company_name, verdict, why_trade, why_caution, why_avoid,
                   why_passes, regime, quality_promoter, score, confidence, computed_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (company_name) DO UPDATE SET
                  verdict=EXCLUDED.verdict, why_trade=EXCLUDED.why_trade,
                  why_caution=EXCLUDED.why_caution, why_avoid=EXCLUDED.why_avoid,
                  why_passes=EXCLUDED.why_passes, regime=EXCLUDED.regime,
                  quality_promoter=EXCLUDED.quality_promoter, score=EXCLUDED.score,
                  confidence=EXCLUDED.confidence, computed_at=now()
            """, (r["company_name"], d["verdict"], d["why_trade"], d["why_caution"],
                  d["why_avoid"], d["why_passes"], d["regime"], d["quality_promoter"],
                  d["score"],
                  # band string -> numeric at the boundary (UI vconf contract;
                  # crashed 2026-07-17: invalid input syntax for integer: "low")
                  {"high": 90, "medium": 65, "low": 40}.get(str(d["confidence"] or "").lower(),
                      d["confidence"] if isinstance(d["confidence"], (int, float)) else None)))
            wrote += 1
    if a.apply:
        conn.commit(); print(f"applied — {wrote} verdicts written.")
    print("verdict tally:", ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    conn.close()

if __name__ == "__main__":
    main()
