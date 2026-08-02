#!/usr/bin/env python3
"""
verify_scores.py — READ-ONLY. Are the stored scores and verdicts still correct?

Four things can make a stored verdict wrong, and they compound:

  1. VERDICT RULE TOO BROAD. verdict_engine returns JUNK on ANY non-empty junk_signals
     array. The locked junk line is narrower: SEBI action, fraud, going-concern, or
     inflated figures. customer_concentration_high and contingent_liabilities_material
     appear in most RHPs and should be RED FLAGS -> WATCH, not JUNK.

  2. STALE DECISIONS. `decisions` is append-only. A decision written before an IPO's
     latest rhp_findings/valuation row never reflects them. Re-extracting an RHP does
     NOT update the verdict.

  3. STALE SCORE VERSION. verdict_engine reads SCORE_VERSION='v2-score-1' while
     score_engine now writes 'v2-score-2' (PE/PB from band+EPS/NAV rather than the
     issue-size proxy). Verdicts are being computed from superseded scores.

  4. MIXED SIGNAL VOCABULARIES. rhp_findings holds both 'v1-migration' rows (old
     pipeline) and 'v2-full' rows (current). They do not necessarily use the same
     junk_signals vocabulary, so a verdict's meaning depends on which produced it.

Writes nothing. Reports only.

  python verify_scores.py
  python verify_scores.py --ids 85,42,5
"""
import os, sys, io, argparse
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

# The locked junk line (narrowed 08-02). auditor_qualified and criminal_litigation are
# RED FLAGS -> WATCH, NOT junk — including them here wrongly reported "correct" JUNKs.
SEVERE = {"sebi_action", "going_concern", "fraud", "inflated_figures"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids")
    a = ap.parse_args()
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()

    print("=" * 74)
    print("1. SCORE VERSIONS — which engine produced each IPO's latest score?")
    print("=" * 74)
    cur.execute("""SELECT engine_version, count(*), min(computed_at)::date,
                          max(computed_at)::date
                     FROM valuation GROUP BY engine_version ORDER BY 2 DESC""")
    for ev, n, lo, hi in cur.fetchall():
        print(f"   {str(ev):16} {n:>6} rows   {lo} -> {hi}")
    cur.execute("""SELECT count(DISTINCT ipo_id) FROM valuation
                    WHERE engine_version='v2-score-2'""")
    n2 = cur.fetchone()[0]
    cur.execute("""SELECT count(DISTINCT ipo_id) FROM valuation
                    WHERE engine_version LIKE 'v2-score-%'""")
    nall = cur.fetchone()[0]
    print(f"\n   {n2}/{nall} IPOs have a v2-score-2 score.")
    print(f"   verdict_engine reads SCORE_VERSION='v2-score-1' — so {nall - n2} IPOs are")
    print(f"   judged on the OLD proxy PE/PB, and the {n2} rescored ones are judged on a")
    print(f"   score that is no longer their latest.")

    print()
    print("=" * 74)
    print("2. JUNK VERDICTS — severe signals vs benign-only")
    print("=" * 74)
    cur.execute("""
        WITH latest_d AS (
          SELECT DISTINCT ON (ipo_id) ipo_id, fundamental_verdict, decided_at
            FROM decisions ORDER BY ipo_id, decided_at DESC),
        latest_f AS (
          SELECT DISTINCT ON (ipo_id) ipo_id, junk_signals, prompt_version, analyzed_at
            FROM rhp_findings ORDER BY ipo_id, analyzed_at DESC)
        SELECT d.ipo_id, i.name_display, d.fundamental_verdict, f.junk_signals,
               f.prompt_version
          FROM latest_d d
          JOIN ipo i ON i.id = d.ipo_id
          LEFT JOIN latest_f f ON f.ipo_id = d.ipo_id
         WHERE d.fundamental_verdict = 'JUNK'""")
    rows = cur.fetchall()
    severe = benign = nosig = 0
    benign_examples = []
    for ipo_id, name, verdict, sigs, pv in rows:
        s = set(sigs or [])
        if not s:
            nosig += 1
        elif s & SEVERE:
            severe += 1
        else:
            benign += 1
            if len(benign_examples) < 12:
                benign_examples.append((ipo_id, name, sorted(s), pv))
    print(f"   JUNK total                       {len(rows):>5}")
    print(f"     with a SEVERE signal (correct) {severe:>5}")
    print(f"     BENIGN signals only (WRONG)    {benign:>5}  <- should be WATCH")
    print(f"     no junk_signals at all         {nosig:>5}  (MF=0 or size<150 path)")
    if benign_examples:
        print("\n   Examples wrongly marked JUNK:")
        for ipo_id, name, s, pv in benign_examples:
            print(f"     id={ipo_id:<5} {str(name)[:30]:32} {s} [{pv}]")

    print()
    print("=" * 74)
    print("3. STALE DECISIONS — verdict older than the evidence it should reflect")
    print("=" * 74)
    cur.execute("""
        WITH latest_d AS (
          SELECT DISTINCT ON (ipo_id) ipo_id, fundamental_verdict, decided_at
            FROM decisions ORDER BY ipo_id, decided_at DESC),
        latest_f AS (
          SELECT DISTINCT ON (ipo_id) ipo_id, analyzed_at, prompt_version
            FROM rhp_findings ORDER BY ipo_id, analyzed_at DESC),
        latest_v AS (
          SELECT DISTINCT ON (ipo_id) ipo_id, computed_at, engine_version
            FROM valuation WHERE engine_version LIKE 'v2-score-%%'
            ORDER BY ipo_id, computed_at DESC)
        SELECT d.ipo_id, i.name_display, d.fundamental_verdict, d.decided_at,
               f.analyzed_at, f.prompt_version, v.computed_at, v.engine_version
          FROM latest_d d
          JOIN ipo i ON i.id = d.ipo_id
          LEFT JOIN latest_f f ON f.ipo_id = d.ipo_id
          LEFT JOIN latest_v v ON v.ipo_id = d.ipo_id
         WHERE (f.analyzed_at IS NOT NULL AND f.analyzed_at > d.decided_at)
            OR (v.computed_at IS NOT NULL AND v.computed_at > d.decided_at)
         ORDER BY d.ipo_id""")
    stale = cur.fetchall()
    print(f"   {len(stale)} IPOs have evidence NEWER than their verdict:")
    for ipo_id, name, verdict, dat, fat, pv, vat, ev in stale[:20]:
        newer = []
        if fat and fat > dat: newer.append(f"rhp_findings {str(fat)[:10]} [{pv}]")
        if vat and vat > dat: newer.append(f"valuation {str(vat)[:10]} [{ev}]")
        print(f"     id={ipo_id:<5} {str(name)[:28]:30} verdict={verdict:<6} "
              f"decided {str(dat)[:10]}  newer: {', '.join(newer)}")
    if len(stale) > 20:
        print(f"     ... +{len(stale)-20} more")

    print()
    print("=" * 74)
    print("4. SIGNAL VOCABULARIES — which pipeline wrote them")
    print("=" * 74)
    cur.execute("""SELECT prompt_version, count(*) FROM rhp_findings
                    GROUP BY prompt_version ORDER BY 2 DESC""")
    for pv, n in cur.fetchall():
        print(f"   {str(pv):16} {n:>5} rows")
    cur.execute("""SELECT prompt_version, unnest(junk_signals) AS sig, count(*)
                     FROM rhp_findings WHERE junk_signals IS NOT NULL
                    GROUP BY 1,2 ORDER BY 1, 3 DESC""")
    cur_pv = None
    for pv, sig, n in cur.fetchall():
        if pv != cur_pv:
            print(f"\n   [{pv}]"); cur_pv = pv
        tag = "SEVERE" if sig in SEVERE else "benign"
        print(f"     {sig:34} {n:>4}  ({tag})")

    if a.ids:
        print()
        print("=" * 74)
        print("5. NAMED IPOs — the full chain")
        print("=" * 74)
        for ipo_id in [int(x) for x in a.ids.split(",") if x.strip()]:
            cur.execute("SELECT name_display FROM ipo WHERE id=%s", (ipo_id,))
            r = cur.fetchone()
            print(f"\n   id={ipo_id} {r[0] if r else '(absent)'}")
            cur.execute("""SELECT engine_version, score, score_band, pe, pb, computed_at
                             FROM valuation WHERE ipo_id=%s
                            ORDER BY computed_at DESC LIMIT 4""", (ipo_id,))
            for ev, sc, band, pe, pb, at in cur.fetchall():
                print(f"     valuation  {str(ev):14} score={sc} band={band} "
                      f"pe={pe} pb={pb}  {str(at)[:16]}")
            cur.execute("""SELECT prompt_version, junk_signals, red_flag_count, analyzed_at
                             FROM rhp_findings WHERE ipo_id=%s
                            ORDER BY analyzed_at DESC LIMIT 3""", (ipo_id,))
            for pv, sigs, rf, at in cur.fetchall():
                print(f"     findings   {str(pv):14} signals={sigs} red_flags={rf} "
                      f"{str(at)[:16]}")
            cur.execute("""SELECT engine_version, fundamental_verdict, reasons, decided_at
                             FROM decisions WHERE ipo_id=%s
                            ORDER BY decided_at DESC LIMIT 3""", (ipo_id,))
            for ev, v, reasons, at in cur.fetchall():
                print(f"     decision   {str(ev):14} {v:<6} {str(reasons)[:60]} "
                      f"{str(at)[:16]}")

    conn.close()
    print("\ndone — nothing was written.")


if __name__ == "__main__":
    main()
