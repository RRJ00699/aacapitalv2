#!/usr/bin/env python3
"""
verdict_engine.py — V2 STAGE B: the verdict engine → decisions.
compute_decision(conn, ipo_id) reads the latest v2-score-% valuation + rhp_findings +
issue/subscription facts and returns JUNK / WATCH / GOOD by a first-match-wins rule.

OWNER'S LOCKED JUNK LINE (07-31, narrowed 08-02):
  JUNK if ANY: MF=0 (mf_shares_bid=0) OR issue_size_cr<150 OR a SEVERE junk_signal
               (sebi_action / going_concern / fraud / inflated_figures). Red flags
               ALONE -> WATCH, not JUNK. auditor_qualified and criminal_litigation are
               RED FLAGS, not JUNK.
  WATCH if not JUNK and (missing_inputs non-empty OR red flags present OR
               NEUTRAL/FAVORABLE without a clean record).
  GOOD  if not JUNK AND missing_inputs EMPTY AND red_flag_count<=threshold AND
               score_band in the GOOD set.

Usage:
  python verdict_engine.py --report              # dry-run counts, BOTH GOOD strictnesses
  python verdict_engine.py --diff [--good-set strong|fav] [--all]   # BEFORE->AFTER per changed IPO
  python verdict_engine.py --ipo <id>            # explain one IPO's verdict
  python verdict_engine.py --selftest
  python verdict_engine.py --write --good-set strong|fav   # persist decisions (after owner picks)
"""
import os, sys, io, argparse, json
if __name__=="__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

ENGINE_VERSION="v2-verdict-3"   # bumped: pure decide() extraction + pinned missing-financials->WATCH (was v2-verdict-2: narrowed JUNK line + latest-score reads)
RED_FLAG_MAX  =2                # GOOD tolerates at most this many red flags

# The owner's LOCKED junk line — ONLY these signals are JUNK. Everything else
# (auditor_qualified, criminal_litigation, related_party_concern,
# customer_concentration_high, contingent_liabilities_material, promoter_pledge_flag, …)
# is a RED FLAG -> WATCH.
SEVERE_JUNK = {"sebi_action", "going_concern", "fraud", "inflated_figures"}

# The verdict run covers mainboard IPOs (was in_backtest_universe=TRUE, which starved
# every NEW listing of a V2 verdict — Indo-MIM/Lohia/Xtranet were stuck on v1-import).
# is_mainboard alone is unreliable (fill_ipo defaults it to True), so it doesn't exclude
# SME issues — add the >=Rs.150cr floor so we don't write verdicts for IPOs not traded.
# (NULL issue_size => kept, via COALESCE, for size-pending upcoming names.)
UNIVERSE_SQL = ("SELECT i.id FROM ipo i LEFT JOIN ipo_issue ii ON ii.ipo_id=i.id "
                "WHERE i.is_mainboard=TRUE AND COALESCE(ii.issue_size_cr,999999)>=150 "
                "ORDER BY i.id")

def _latest_valuation(cur, ipo_id):
    # newest v2-score-% row (was hardcoded 'v2-score-1'). LIKE excludes v2-rhp-1, which
    # carries pe/pb but NO score by design.
    cur.execute("""SELECT score, score_band, missing_inputs
                   FROM valuation WHERE ipo_id=%s AND engine_version LIKE 'v2-score-%%'
                   ORDER BY computed_at DESC LIMIT 1""",(ipo_id,))
    return cur.fetchone()

def _rhp(cur, ipo_id):
    """latest rhp_findings for the IPO: (red_flag_count, junk_signals[], measured, has_row).
    measured is True only for a v2-full row with a real (non-NULL) red_flag_count.
    has_row is True when an extraction row exists at all (absence of a row is absence of
    evidence — distinct from a v1 row that ran and found no flags)."""
    cur.execute("""SELECT red_flag_count, junk_signals, prompt_version FROM rhp_findings
                   WHERE ipo_id=%s ORDER BY analyzed_at DESC LIMIT 1""",(ipo_id,))
    r=cur.fetchone()
    if not r: return 0, [], False, False
    sigs = r[1] or []
    rc = r[0]
    # Only v2-full rows store a real red_flag_count. v1-migration rows are NULL, so their
    # count is INFERRED (len of signals) — usable for WATCH context.
    measured = (r[2] == "v2-full") and (r[0] is not None)
    if rc is None:
        rc = len(sigs)
    return rc, sigs, measured, True

def _junk_facts(cur, ipo_id):
    """(mf_shares_bid, issue_size_cr) for the JUNK line."""
    cur.execute("""SELECT s.mf_shares_bid FROM subscription_snapshots s
                   WHERE s.ipo_id=%s ORDER BY s.is_final DESC NULLS LAST, s.captured_at DESC
                   LIMIT 1""",(ipo_id,))
    mf=cur.fetchone(); mf=mf[0] if mf else None
    cur.execute("SELECT issue_size_cr FROM ipo_issue WHERE ipo_id=%s",(ipo_id,))
    sz=cur.fetchone(); sz=float(sz[0]) if sz and sz[0] is not None else None
    return mf, sz

def decide(*, score, band, missing, red_count, junk_sigs, measured, has_row, mf, size,
           good_set="strong"):
    """Pure JUNK/WATCH/GOOD decision from already-fetched facts — no DB, so it is
    unit-testable offline. compute_decision() reads the facts and delegates here.

    MISSING FINANCIALS -> WATCH, NEVER JUNK. The ONLY JUNK triggers are the owner-locked
    STRUCTURAL signals below (mf_shares_bid==0, issue_size_cr<150, a SEVERE_JUNK RHP
    signal). An absent valuation / missing financial inputs is never a JUNK trigger: it
    gates GOOD off (so the row cannot be GOOD) and falls through to the WATCH bucket. This
    is enforced by ordering — no `missing`-derived condition ever returns JUNK — and pinned
    by pipeline/test_verdict_engine.py."""
    reasons=[]

    # 1) JUNK — owner's locked STRUCTURAL line (first match wins). None of these is
    #    "missing financials"; missing financials cannot reach a JUNK return.
    if mf is not None and mf==0:
        return dict(verdict="JUNK", reasons=["mf_zero"], score=score, band=band,
                    evidence=dict(mf_shares_bid=mf))
    if size is not None and size<150:
        return dict(verdict="JUNK", reasons=[f"issue_size_below_150cr({size})"], score=score, band=band,
                    evidence=dict(issue_size_cr=size))
    # ONLY severe signals are JUNK. Benign signals stay in red_count (below) -> WATCH.
    severe = [s for s in junk_sigs if s in SEVERE_JUNK]
    if severe:
        return dict(verdict="JUNK", reasons=["junk_signals:"+",".join(map(str,severe))],
                    score=score, band=band, evidence=dict(junk_signals=severe, all_signals=junk_sigs))

    # 3) GOOD — complete data + favorable/strong + a CLEAN RHP read, where "clean" is:
    #   * measured (v2-full row) with red_flag_count<=MAX, OR
    #   * case B: a v1 extraction row that EXISTS and found NO junk_signals — empty
    #     signals is positive evidence of cleanliness, not absent measurement.
    # It is NOT clean when: benign flags exist but the count is unmeasured (case A -> WATCH,
    # "red_flags_unmeasured"), or no extraction row exists at all (no evidence -> WATCH).
    # `missing` (which includes missing financials) gates GOOD off here, guaranteeing that
    # missing-financials rows drop to WATCH.
    good_bands = {"STRONG"} if good_set=="strong" else {"STRONG","FAVORABLE"}
    if measured:
        rhp_clean = red_count<=RED_FLAG_MAX
    elif has_row and not junk_sigs:
        rhp_clean = True                       # case B: extractor ran, found nothing
    else:
        rhp_clean = False                      # case A (unmeasured w/ flags) or no row
    if (not missing) and band in good_bands and rhp_clean:
        reasons.append(f"complete+{'measured' if measured else 'v1-clean'}+{band}")
        return dict(verdict="GOOD", reasons=reasons, score=score, band=band,
                    evidence=dict(red_flag_count=red_count, score_band=band, measured=measured))

    # 2) WATCH — everything else that isn't JUNK (the pending bucket), missing financials included.
    if missing: reasons.append("missing_inputs:"+",".join(missing[:4]))
    if not has_row: reasons.append("no_rhp_analysis")                 # no evidence at all
    elif (not measured) and junk_sigs: reasons.append("red_flags_unmeasured")  # case A
    elif measured and red_count>RED_FLAG_MAX: reasons.append(f"red_flags={red_count}")
    if junk_sigs and not severe: reasons.append("benign_signals:"+",".join(map(str,junk_sigs)))
    if band in ("NEUTRAL","FAVORABLE","AVOID"): reasons.append(f"band={band}")
    if not reasons: reasons.append("pending")
    return dict(verdict="WATCH", reasons=reasons, score=score, band=band,
                evidence=dict(red_flag_count=red_count, score_band=band, measured=measured, missing=missing[:4]))


def compute_decision(conn, ipo_id, good_set="strong"):
    """Return dict(verdict, reasons[], evidence). good_set: 'strong'={STRONG} or 'fav'={FAVORABLE,STRONG}.
    Reads the latest facts from the DB and delegates the taxonomy to the pure decide()."""
    cur=conn.cursor()
    val=_latest_valuation(cur, ipo_id)
    score, band, missing = (val[0], val[1], val[2] or []) if val else (None, None, ["no_valuation"])
    red_count, junk_sigs, measured, has_row = _rhp(cur, ipo_id)
    mf, size = _junk_facts(cur, ipo_id)
    return decide(score=score, band=band, missing=missing, red_count=red_count,
                  junk_sigs=junk_sigs, measured=measured, has_row=has_row, mf=mf, size=size,
                  good_set=good_set)

def write_decision(conn, ipo_id, d):
    cur=conn.cursor()
    cur.execute("""INSERT INTO decisions
       (ipo_id,decided_at,engine_version,fundamental_verdict,listing_action,reasons,evidence_refs)
       VALUES (%s,now(),%s,%s,%s,%s,%s)""",
       (ipo_id, ENGINE_VERSION, d["verdict"], None,
        json.dumps(d["reasons"]), json.dumps(d.get("evidence",{}))))
    conn.commit()

def _universe(cur):
    cur.execute(UNIVERSE_SQL)
    return [r[0] for r in cur.fetchall()]

def report(good_set=None):
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    ids=_universe(cur)
    from collections import Counter
    for gs,label in ([(good_set,good_set)] if good_set else [("strong","STRONG-only"),("fav","FAVORABLE+STRONG")]):
        c=Counter(); good_examples=[]
        for iid in ids:
            d=compute_decision(conn, iid, good_set=gs)
            c[d["verdict"]]+=1
            if d["verdict"]=="GOOD" and len(good_examples)<12: good_examples.append((iid,d["band"]))
        print(f"\n=== VERDICTS (GOOD = {label}) — {len(ids)} mainboard IPOs ===")
        for v in ["GOOD","WATCH","JUNK"]:
            print(f"  {v:6} {c[v]:>4}  ({100*c[v]/max(1,len(ids)):.0f}%)")
        print(f"  sample GOOD ids: {good_examples[:12]}")
    conn.close()

def diff(good_set="strong", show_all=False):
    """READ-ONLY. BEFORE (current latest stored verdict) -> AFTER (recomputed) for every
    IPO whose verdict changes. JUNK->GOOD is broken out separately (finding #1)."""
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    cur.execute("""SELECT i.id, i.name_display FROM ipo i LEFT JOIN ipo_issue ii ON ii.ipo_id=i.id
                   WHERE i.is_mainboard=TRUE AND COALESCE(ii.issue_size_cr,999999)>=150 ORDER BY i.id""")
    ipos=cur.fetchall()
    cur.execute("""SELECT DISTINCT ON (ipo_id) ipo_id, fundamental_verdict
                   FROM decisions ORDER BY ipo_id, decided_at DESC""")
    before_map=dict(cur.fetchall())
    from collections import Counter
    trans=Counter(); changed=[]
    for iid,name in ipos:
        before=before_map.get(iid) or "(none)"
        after=compute_decision(conn, iid, good_set=good_set)["verdict"]
        if before!=after:
            trans[(before,after)]+=1
            changed.append((iid,name,before,after))
    print(f"=== VERDICT DIFF (GOOD={good_set}) — {len(ipos)} mainboard IPOs, {len(changed)} change ===\n")
    print("  transition matrix (before -> after):")
    for (b,a),n in sorted(trans.items(), key=lambda x:-x[1]):
        print(f"    {b:7} -> {a:7} {n:>4}")

    def dump(rows, limit=40):
        for iid,name,b,a in (rows if show_all else rows[:limit]):
            print(f"      id={iid:<5} {str(name)[:36]:38} {b:7} -> {a}")
        if not show_all and len(rows)>limit:
            print(f"      ... +{len(rows)-limit} more (use --all)")

    j2g=[c for c in changed if c[2]=="JUNK" and c[3]=="GOOD"]
    j2w=[c for c in changed if c[2]=="JUNK" and c[3]=="WATCH"]
    other=[c for c in changed if not (c[2]=="JUNK" and c[3] in ("GOOD","WATCH"))]

    print(f"\n  JUNK -> GOOD : {len(j2g)}  <- READ THESE (a wrongly-killed name promoted straight to GOOD)")
    dump(j2g, limit=len(j2g))            # always show ALL JUNK->GOOD
    print(f"\n  JUNK -> WATCH: {len(j2w)}")
    dump(j2w)
    if other:
        print(f"\n  OTHER transitions: {len(other)}")
        dump(other)
    conn.close()

def selftest():
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    ok=True
    def chk(m,c):
        nonlocal ok; ok=ok and c; print(f"  [{'PASS' if c else 'FAIL'}] {m}")

    # MF=0 -> JUNK
    cur.execute("""SELECT DISTINCT ON (ipo_id) ipo_id FROM subscription_snapshots
                   WHERE mf_shares_bid=0 ORDER BY ipo_id LIMIT 1""")
    r=cur.fetchone()
    if r: d=compute_decision(conn, r[0]); chk(f"MF=0 IPO {r[0]} -> JUNK", d["verdict"]=="JUNK")

    # <150cr -> JUNK
    cur.execute("""SELECT ii.ipo_id FROM ipo_issue ii JOIN ipo i ON i.id=ii.ipo_id
                   WHERE ii.issue_size_cr<150 AND i.is_mainboard=TRUE
                     AND EXISTS(SELECT 1 FROM subscription_snapshots s WHERE s.ipo_id=ii.ipo_id AND s.mf_shares_bid>0)
                   LIMIT 1""")
    r=cur.fetchone()
    if r: d=compute_decision(conn, r[0]); chk(f"<150cr IPO {r[0]} -> JUNK", d["verdict"]=="JUNK")

    # a SEVERE signal (sebi_action) -> JUNK
    cur.execute("""SELECT DISTINCT ON (ipo_id) ipo_id FROM rhp_findings
                   WHERE 'sebi_action' = ANY(junk_signals) ORDER BY ipo_id, analyzed_at DESC LIMIT 1""")
    r=cur.fetchone()
    if r: d=compute_decision(conn, r[0]); chk(f"sebi_action IPO {r[0]} -> JUNK", d["verdict"]=="JUNK")
    else: chk("no sebi_action example (skipped)", True)

    # BENIGN-only signals (no severe), MF>0, >=150cr -> WATCH not JUNK (the core fix)
    cur.execute("""SELECT DISTINCT ON (rf.ipo_id) rf.ipo_id FROM rhp_findings rf
                   JOIN ipo_issue ii ON ii.ipo_id=rf.ipo_id
                   WHERE rf.junk_signals IS NOT NULL AND array_length(rf.junk_signals,1)>0
                     AND NOT (rf.junk_signals && ARRAY['sebi_action','going_concern','fraud','inflated_figures'])
                     AND ii.issue_size_cr>=150
                     AND EXISTS(SELECT 1 FROM subscription_snapshots s WHERE s.ipo_id=rf.ipo_id AND s.mf_shares_bid>0)
                   ORDER BY rf.ipo_id, rf.analyzed_at DESC LIMIT 1""")
    r=cur.fetchone()
    if r: d=compute_decision(conn, r[0]); chk(f"benign-only signals IPO {r[0]} -> WATCH not JUNK", d["verdict"]=="WATCH")
    else: chk("no benign-only-signals example (skipped)", True)

    # latest-rhp helper for the two RHP-cleanliness cases below
    LATEST_SIGS = ("(SELECT junk_signals FROM rhp_findings rf WHERE rf.ipo_id=v.ipo_id "
                   "ORDER BY analyzed_at DESC LIMIT 1)")
    HAS_ROW = "EXISTS(SELECT 1 FROM rhp_findings rf WHERE rf.ipo_id=v.ipo_id)"
    NOT_V2FULL = ("(SELECT prompt_version FROM rhp_findings rf WHERE rf.ipo_id=v.ipo_id "
                  "ORDER BY analyzed_at DESC LIMIT 1) IS DISTINCT FROM 'v2-full'")
    COMPLETE_STRONG = ("""v.engine_version LIKE 'v2-score-%%' AND v.score_band='STRONG'
        AND (v.missing_inputs IS NULL OR array_length(v.missing_inputs,1) IS NULL)
        AND ii.issue_size_cr>=150
        AND EXISTS(SELECT 1 FROM subscription_snapshots s WHERE s.ipo_id=v.ipo_id AND s.mf_shares_bid>0)""")

    # CASE B — complete + STRONG + a v1 row that found NO signals -> GOOD (v1-clean).
    cur.execute(f"""SELECT v.ipo_id FROM valuation v JOIN ipo_issue ii ON ii.ipo_id=v.ipo_id
                     WHERE {COMPLETE_STRONG} AND {HAS_ROW} AND {NOT_V2FULL}
                       AND COALESCE(array_length({LATEST_SIGS},1),0)=0
                     ORDER BY v.computed_at DESC LIMIT 1""")
    r=cur.fetchone()
    if r:
        d=compute_decision(conn, r[0])
        chk(f"case B: complete STRONG, v1 row w/ EMPTY signals {r[0]} -> GOOD", d["verdict"]=="GOOD")
    else: chk("no case-B example (skipped)", True)

    # CASE A — complete + STRONG + a v1 row with benign signals but unmeasured count -> WATCH.
    cur.execute(f"""SELECT v.ipo_id FROM valuation v JOIN ipo_issue ii ON ii.ipo_id=v.ipo_id
                     WHERE {COMPLETE_STRONG} AND {HAS_ROW} AND {NOT_V2FULL}
                       AND COALESCE(array_length({LATEST_SIGS},1),0)>0
                       AND NOT ({LATEST_SIGS} && ARRAY['sebi_action','going_concern','fraud','inflated_figures'])
                     ORDER BY v.computed_at DESC LIMIT 1""")
    r=cur.fetchone()
    if r:
        d=compute_decision(conn, r[0])
        chk(f"case A: complete STRONG, v1 row w/ benign signals {r[0]} -> WATCH (red_flags_unmeasured)",
            d["verdict"]=="WATCH" and "red_flags_unmeasured" in d["reasons"])
    else: chk("no case-A example (skipped)", True)

    # a NEW mainboard IPO (NOT in the backtest universe) now gets a verdict
    cur.execute("""SELECT id FROM ipo WHERE is_mainboard=TRUE AND COALESCE(in_backtest_universe,FALSE)=FALSE
                   ORDER BY listing_date DESC NULLS LAST LIMIT 1""")
    r=cur.fetchone()
    if r:
        d=compute_decision(conn, r[0])
        chk(f"new (non-backtest) mainboard IPO {r[0]} gets a verdict [{d['verdict']}]",
            d["verdict"] in ("JUNK","WATCH","GOOD"))
    else: chk("no non-backtest mainboard IPO (skipped)", True)

    print(f"\n{'ALL PASS ✓' if ok else 'SOME FAILED ✗'}")
    conn.close(); return ok

def run_write(good_set):
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    ids=_universe(cur)
    from collections import Counter; c=Counter()
    for i,iid in enumerate(ids,1):
        d=compute_decision(conn, iid, good_set=good_set)
        write_decision(conn, iid, d); c[d["verdict"]]+=1
        if i%100==0: print(f"  ...{i}/{len(ids)}")
    print(f"wrote decisions (GOOD={good_set}):", dict(c))
    conn.close()

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--report",action="store_true")
    ap.add_argument("--diff",action="store_true")
    ap.add_argument("--all",action="store_true", help="with --diff: list every changed IPO, not the first 40")
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--ipo",type=int)
    ap.add_argument("--write",action="store_true")
    ap.add_argument("--good-set",choices=["strong","fav"],default="strong")
    a=ap.parse_args()
    if a.selftest: sys.exit(0 if selftest() else 1)
    if a.ipo:
        conn=psycopg2.connect(os.environ["DATABASE_URL"])
        import pprint; pprint.pprint(compute_decision(conn, a.ipo, good_set=a.good_set)); conn.close()
    elif a.diff: diff(good_set=a.good_set, show_all=a.all)
    elif a.write: run_write(a.good_set)
    elif a.report: report()
    else: print("--report | --diff | --ipo <id> | --selftest | --write --good-set strong|fav")
