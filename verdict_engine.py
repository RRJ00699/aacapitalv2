#!/usr/bin/env python3
"""
verdict_engine.py — V2 STAGE B: the verdict engine → decisions.
compute_decision(conn, ipo_id) reads the latest v2-score-1 valuation + rhp_findings +
issue/subscription facts and returns JUNK / WATCH / GOOD by a first-match-wins rule.

OWNER'S LOCKED JUNK LINE (07-31):
  JUNK if ANY: MF=0 (mf_shares_bid=0) OR issue_size_cr<150 OR explicit junk_signals
               (SEBI/fraud/going-concern/inflated). Red flags ALONE -> WATCH not JUNK.
  WATCH if not JUNK and (missing_inputs non-empty OR red flags present OR
               NEUTRAL/FAVORABLE without a clean record).
  GOOD  if not JUNK AND missing_inputs EMPTY AND red_flag_count<=threshold AND
               score_band in the GOOD set.

GOOD strictness is UNDECIDED — --report prints BOTH counts (STRONG-only vs
FAVORABLE+STRONG) so the owner picks. Nothing writes unless --write.

Usage:
  python verdict_engine.py --report              # dry-run: full JUNK/WATCH/GOOD counts, BOTH GOOD strictnesses
  python verdict_engine.py --ipo <id>            # explain one IPO's verdict
  python verdict_engine.py --selftest
  python verdict_engine.py --write --good-set strong|fav   # persist decisions (after owner picks)
"""
import os, sys, io, argparse, json
if __name__=="__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

ENGINE_VERSION="v2-verdict-1"
SCORE_VERSION ="v2-score-1"
RED_FLAG_MAX  =2          # GOOD tolerates at most this many red flags

def _latest_valuation(cur, ipo_id):
    cur.execute("""SELECT score, score_band, missing_inputs
                   FROM valuation WHERE ipo_id=%s AND engine_version=%s
                   ORDER BY computed_at DESC LIMIT 1""",(ipo_id, SCORE_VERSION))
    return cur.fetchone()

def _rhp(cur, ipo_id):
    """latest rhp_findings for the IPO: (red_flag_count, junk_signals[])."""
    cur.execute("""SELECT red_flag_count, junk_signals FROM rhp_findings
                   WHERE ipo_id=%s ORDER BY analyzed_at DESC LIMIT 1""",(ipo_id,))
    r=cur.fetchone()
    if not r: return 0, []
    return (r[0] or 0), (r[1] or [])

def _junk_facts(cur, ipo_id):
    """(mf_shares_bid, issue_size_cr) for the JUNK line."""
    cur.execute("""SELECT s.mf_shares_bid FROM subscription_snapshots s
                   WHERE s.ipo_id=%s ORDER BY s.is_final DESC NULLS LAST, s.captured_at DESC
                   LIMIT 1""",(ipo_id,))
    mf=cur.fetchone(); mf=mf[0] if mf else None
    cur.execute("SELECT issue_size_cr FROM ipo_issue WHERE ipo_id=%s",(ipo_id,))
    sz=cur.fetchone(); sz=float(sz[0]) if sz and sz[0] is not None else None
    return mf, sz

def compute_decision(conn, ipo_id, good_set="strong"):
    """Return dict(verdict, reasons[], evidence). good_set: 'strong'={STRONG} or 'fav'={FAVORABLE,STRONG}."""
    cur=conn.cursor()
    val=_latest_valuation(cur, ipo_id)
    score, band, missing = (val[0], val[1], val[2] or []) if val else (None, None, ["no_valuation"])
    red_count, junk_sigs = _rhp(cur, ipo_id)
    mf, size = _junk_facts(cur, ipo_id)
    reasons=[]

    # 1) JUNK — owner's locked line (first match wins)
    if mf is not None and mf==0:
        return dict(verdict="JUNK", reasons=["mf_zero"], score=score, band=band,
                    evidence=dict(mf_shares_bid=mf))
    if size is not None and size<150:
        return dict(verdict="JUNK", reasons=[f"issue_size_below_150cr({size})"], score=score, band=band,
                    evidence=dict(issue_size_cr=size))
    if junk_sigs:
        return dict(verdict="JUNK", reasons=["junk_signals:"+",".join(map(str,junk_sigs))],
                    score=score, band=band, evidence=dict(junk_signals=junk_sigs))

    # 3) GOOD — strict: complete data + clean RHP + favorable/strong
    good_bands = {"STRONG"} if good_set=="strong" else {"STRONG","FAVORABLE"}
    if (not missing) and red_count<=RED_FLAG_MAX and band in good_bands:
        reasons.append(f"complete+clean+{band}")
        return dict(verdict="GOOD", reasons=reasons, score=score, band=band,
                    evidence=dict(red_flag_count=red_count, score_band=band))

    # 2) WATCH — everything else that isn't JUNK (the pending bucket)
    if missing: reasons.append("missing_inputs:"+",".join(missing[:4]))
    if red_count>RED_FLAG_MAX: reasons.append(f"red_flags={red_count}")
    if band in ("NEUTRAL","FAVORABLE","AVOID"): reasons.append(f"band={band}")
    if not reasons: reasons.append("pending")
    return dict(verdict="WATCH", reasons=reasons, score=score, band=band,
                evidence=dict(red_flag_count=red_count, score_band=band, missing=missing[:4]))

def write_decision(conn, ipo_id, d):
    cur=conn.cursor()
    cur.execute("""INSERT INTO decisions
       (ipo_id,decided_at,engine_version,fundamental_verdict,listing_action,reasons,evidence_refs)
       VALUES (%s,now(),%s,%s,%s,%s,%s)""",
       (ipo_id, ENGINE_VERSION, d["verdict"], None,
        json.dumps(d["reasons"]), json.dumps(d.get("evidence",{}))))
    conn.commit()

def report(good_set=None):
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    cur.execute("SELECT id FROM ipo WHERE in_backtest_universe=TRUE ORDER BY id")
    ids=[r[0] for r in cur.fetchall()]
    from collections import Counter
    for gs,label in ([(good_set,good_set)] if good_set else [("strong","STRONG-only"),("fav","FAVORABLE+STRONG")]):
        c=Counter(); good_examples=[]
        for iid in ids:
            d=compute_decision(conn, iid, good_set=gs)
            c[d["verdict"]]+=1
            if d["verdict"]=="GOOD" and len(good_examples)<12: good_examples.append((iid,d["band"]))
        print(f"\n=== VERDICTS (GOOD = {label}) — {len(ids)} in-backtest IPOs ===")
        for v in ["GOOD","WATCH","JUNK"]:
            print(f"  {v:6} {c[v]:>4}  ({100*c[v]/len(ids):.0f}%)")
        print(f"  sample GOOD ids: {good_examples[:12]}")
    conn.close()

def selftest():
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    ok=True
    def chk(m,c):
        nonlocal ok; ok=ok and c; print(f"  [{'PASS' if c else 'FAIL'}] {m}")
    # find an MF=0 IPO -> must be JUNK
    cur.execute("""SELECT DISTINCT ON (ipo_id) ipo_id FROM subscription_snapshots
                   WHERE mf_shares_bid=0 ORDER BY ipo_id LIMIT 1""")
    r=cur.fetchone()
    if r:
        d=compute_decision(conn, r[0]); chk(f"MF=0 IPO {r[0]} -> JUNK", d["verdict"]=="JUNK")
    # find a <150cr IPO -> JUNK (and MF!=0 so it's the size rule)
    cur.execute("""SELECT ii.ipo_id FROM ipo_issue ii
                   JOIN ipo i ON i.id=ii.ipo_id
                   WHERE ii.issue_size_cr<150 AND i.in_backtest_universe=TRUE
                     AND EXISTS(SELECT 1 FROM subscription_snapshots s WHERE s.ipo_id=ii.ipo_id AND s.mf_shares_bid>0)
                   LIMIT 1""")
    r=cur.fetchone()
    if r:
        d=compute_decision(conn, r[0]); chk(f"<150cr IPO {r[0]} -> JUNK", d["verdict"]=="JUNK")
    # a STRONG + complete + MF>0 + >=150cr + NO junk_signals should be GOOD under strong-set
    cur.execute("""SELECT v.ipo_id FROM valuation v JOIN ipo_issue ii ON ii.ipo_id=v.ipo_id
                   WHERE v.engine_version=%s AND v.score_band='STRONG'
                     AND (v.missing_inputs IS NULL OR array_length(v.missing_inputs,1) IS NULL)
                     AND ii.issue_size_cr>=150
                     AND EXISTS(SELECT 1 FROM subscription_snapshots s WHERE s.ipo_id=v.ipo_id AND s.mf_shares_bid>0)
                     AND NOT EXISTS(SELECT 1 FROM subscription_snapshots s2 WHERE s2.ipo_id=v.ipo_id
                                    AND s2.mf_shares_bid=0
                                    AND s2.captured_at=(SELECT max(captured_at) FROM subscription_snapshots s3 WHERE s3.ipo_id=v.ipo_id))
                     AND NOT EXISTS(SELECT 1 FROM rhp_findings r WHERE r.ipo_id=v.ipo_id
                                    AND r.junk_signals IS NOT NULL AND array_length(r.junk_signals,1)>0)
                   LIMIT 1""",(SCORE_VERSION,))
    r=cur.fetchone()
    if r:
        d=compute_decision(conn, r[0], good_set="strong")
        chk(f"complete STRONG clean-RHP IPO {r[0]} -> GOOD", d["verdict"]=="GOOD")
    else:
        chk("no complete-STRONG-clean example (skipped)", True)
    # a missing-inputs IPO that is NOT junk (MF>0, >=150cr, NO junk_signals) -> WATCH not JUNK (the core fix)
    cur.execute("""SELECT v.ipo_id FROM valuation v JOIN ipo_issue ii ON ii.ipo_id=v.ipo_id
                   WHERE v.engine_version=%s AND array_length(v.missing_inputs,1)>0
                     AND ii.issue_size_cr>=150
                     AND EXISTS(SELECT 1 FROM subscription_snapshots s WHERE s.ipo_id=v.ipo_id AND s.mf_shares_bid>0)
                     AND NOT EXISTS(SELECT 1 FROM rhp_findings r WHERE r.ipo_id=v.ipo_id
                                    AND r.junk_signals IS NOT NULL AND array_length(r.junk_signals,1)>0)
                   LIMIT 1""",(SCORE_VERSION,))
    r=cur.fetchone()
    if r:
        d=compute_decision(conn, r[0])
        chk(f"missing-inputs non-junk IPO {r[0]} -> WATCH not JUNK (the 0-GOOD fix)", d["verdict"]=="WATCH")
    print(f"\n{'ALL PASS ✓' if ok else 'SOME FAILED ✗'}")
    conn.close(); return ok

def run_write(good_set):
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    cur.execute("SELECT id FROM ipo WHERE in_backtest_universe=TRUE ORDER BY id")
    ids=[r[0] for r in cur.fetchall()]
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
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--ipo",type=int)
    ap.add_argument("--write",action="store_true")
    ap.add_argument("--good-set",choices=["strong","fav"],default="strong")
    a=ap.parse_args()
    if a.selftest: sys.exit(0 if selftest() else 1)
    if a.ipo:
        conn=psycopg2.connect(os.environ["DATABASE_URL"])
        import pprint; pprint.pprint(compute_decision(conn, a.ipo, good_set=a.good_set)); conn.close()
    elif a.write: run_write(a.good_set)
    elif a.report: report()
    else: print("--report | --ipo <id> | --selftest | --write --good-set strong|fav")
