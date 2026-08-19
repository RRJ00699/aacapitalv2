#!/usr/bin/env python3
"""
score_engine.py — V2 STAGE A: the scoring engine → valuation.
compute_valuation(conn, ipo_id) derives PE/PB/ROE/ROCE/D-E/CAGR from financial_statements
+ ipo_issue, computes the weighted SCORE (Tier-1 low-D/E + high-ROE heaviest, PB
regime-conditional), maps to score_band via the LOCKED step function, and honors
val_null_explained (any uncomputable ratio is NAMED in missing_inputs, never silent NULL).

Writes valuation with engine_version (recompute — NEVER COALESCE).

Run tests:  python score_engine.py --selftest
Batch fill: python score_engine.py --all         (recompute every in-backtest IPO)
Preview:    python score_engine.py --ipo <id>     (compute one, print, no write)
"""
import os, sys, io, argparse, datetime as dt
if __name__=="__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2, json

ENGINE_VERSION = "v2-score-2"
# v2-score-1 -> v2-score-2 (08-01): PE/PB derivation changed, so the SCORE changes
# (pb feeds the pb_value factor). A shipped engine_version is never redefined — the 662
# v2-score-1 rows stay exactly as computed and remain comparable. Readers should prefer
# the newest version present and fall back to v2-score-1.

# EPS/NAV are written to source_facts by rhp_writer (they have no valuation column).
# Post-issue EPS is the correct denominator for an offer-price P/E; pre-issue is the
# documented fallback and is labelled as such so the two are never confused.
RHP_EPS_FIELDS = ["eps_post", "eps_pre"]
RHP_NAV_FIELD  = "nav_per_share"

def _rhp_eps_nav(cur, ipo_id):
    """Latest RHP-reported EPS and NAV for one IPO. Returns (eps, eps_field, nav)."""
    cur.execute("""SELECT DISTINCT ON (field) field, value
                     FROM source_facts
                    WHERE ipo_id=%s AND field = ANY(%s)
                    ORDER BY field, fetched_at DESC""",
                (ipo_id, RHP_EPS_FIELDS + [RHP_NAV_FIELD]))
    got = {}
    for f, v in cur.fetchall():
        try: got[f] = float(v)
        except (TypeError, ValueError): pass
    eps = eps_field = None
    for f in RHP_EPS_FIELDS:                      # eps_post preferred over eps_pre
        if got.get(f) not in (None, 0):
            eps, eps_field = got[f], f
            break
    return eps, eps_field, got.get(RHP_NAV_FIELD)

# LOCKED step function (ipo_score.py:33) — score -> band
def band_of(score):
    if score is None: return None
    if score <= -2: return "AVOID"
    if score <=  0: return "NEUTRAL"
    if score <=  2: return "FAVORABLE"
    return "STRONG"

def _latest_financials(cur, ipo_id):
    """Return (latest_row, rows_by_period_desc). Prefer consolidated, latest period."""
    # period is TEXT 'DD-Mon-YY'; ORDER BY period sorts lexicographically (day-first),
    # so '31-Mar-25' > '30-Sep-26'. Order by the PARSED date instead. Guarded so an
    # off-format value sorts last rather than erroring the whole query.
    cur.execute("""SELECT period,basis,revenue,ebitda,pat,net_worth,total_debt,total_assets
                   FROM financial_statements WHERE ipo_id=%s
                   ORDER BY (basis ILIKE '%%consolidat%%') DESC,
                            CASE WHEN period ~ '^[0-9]{1,2}-[A-Za-z]{3}-[0-9]{2}$'
                                 THEN to_date(period,'DD-Mon-YY') END DESC NULLS LAST""",(ipo_id,))
    rows=cur.fetchall()
    return (rows[0] if rows else None), rows

def compute_valuation(conn, ipo_id):
    """Compute ratios + score + band for one IPO. Returns a dict (does NOT write)."""
    cur=conn.cursor()
    missing=[]; used={}
    # issue economics
    cur.execute("""SELECT issue_price,band_hi,band_lo,issue_size_cr,ofs_cr
                   FROM ipo_issue WHERE ipo_id=%s""",(ipo_id,))
    iss=cur.fetchone()
    issue_price_raw, band_hi, _band_lo, issue_size_raw, ofs_raw = (
        iss if iss is not None else (None, None, None, None, None))
    # A price band is not the persisted final issue price. Price-dependent
    # valuation remains unavailable until issue_price has canonical provenance.
    issue_price = float(issue_price_raw) if issue_price_raw is not None else None
    issue_size = float(issue_size_raw) if issue_size_raw is not None else None
    ofs_cr = float(ofs_raw) if ofs_raw is not None else None
    if issue_price is None: missing.append("issue_price")

    latest, allrows = _latest_financials(cur, ipo_id)
    if latest is None:
        # no financials at all — everything uncomputable
        for r in ["pe","pb","roe","roce","de","rev_cagr_3y"]: missing.append(r+"_no_financials")
        return dict(ipo_id=ipo_id, pe=None,pb=None,roe=None,roce=None,de=None,
                    rev_cagr_3y=None,ofs_pct=None,peer_median_pe=None,score=None,
                    score_band=None, missing_inputs=missing, inputs_used=used)

    _,_,rev,ebitda,pat,nw,debt,assets = latest
    rev=float(rev) if rev is not None else None
    ebitda=float(ebitda) if ebitda is not None else None
    pat=float(pat) if pat is not None else None
    nw=float(nw) if nw is not None else None
    debt=float(debt) if debt is not None else None
    assets=float(assets) if assets is not None else None
    for k,v in [("revenue",rev),("pat",pat),("net_worth",nw),("total_debt",debt)]:
        if v is not None: used[k]=v

    # shares proxy from issue economics: issue_size_cr*1e7 / issue_price = value/price
    # (a rough share count; PE/PB use per-crore consistency so ratios are scale-free below)
    # ---- ROE = PAT / net_worth (scale-free) ----
    roe = (pat/nw*100) if (pat is not None and nw not in (None,0)) else None
    if roe is None:
        missing.append("roe_loss_making" if pat is not None and (pat<=0) else "roe_missing_networth")
    # ---- D/E = total_debt / net_worth ----
    de = (debt/nw) if (debt is not None and nw not in (None,0)) else None
    if de is None: missing.append("de_missing")
    # ---- ROCE = EBIT / (net_worth + total_debt); EBIT≈EBITDA (no D&A line) ----
    roce = (ebitda/(nw+debt)*100) if (ebitda is not None and nw is not None and debt is not None and (nw+debt)!=0) else None
    if roce is None: missing.append("roce_missing_ebitda" if ebitda is None else "roce_missing_capital")
    # ---- PE and PB (v2-score-2) --------------------------------------------------
    # score_engine is now the SOLE owner of PE/PB. The RHP cannot supply them: a Red
    # Herring states "Offer Price is [●] times the face value", so the band is not fixed
    # at filing and any pre-band P/E would be invented. What the RHP DOES supply is the
    # band-independent EPS and NAV; combined with the NSE band that gives the real ratio:
    #     PE = offer price / EPS(post-issue)     PB = offer price / NAV per share
    #
    # FALLBACK, DELIBERATE (owner ruling 08-01): when EPS/NAV are not yet extracted —
    # true for nearly every IPO today, since `documents` holds only 4 rows — we keep the
    # OLD issue-size proxy rather than returning null. Null would land "pb_missing" in
    # missing_inputs, and verdict_engine gates GOOD on `if (not missing)`, so every IPO
    # would collapse to WATCH and GOOD would go to ~0. That is the 0-GOOD bug returning
    # through the side door. The proxy degrades to today's behaviour and upgrades
    # silently per-IPO as each RHP is extracted.
    #
    # PROVENANCE IS MANDATORY: pe_source / pb_source record which derivation produced the
    # number, so an audit of GOOD names can always tell an authoritative ratio from an
    # approximate one. The proxy must never masquerade as the real thing.
    eps, eps_field, nav = _rhp_eps_nav(cur, ipo_id)
    pe = pb = None
    pe_source = pb_source = None

    if issue_price is not None and eps is not None and eps > 0:
        pe = issue_price / eps
        pe_source = f"rhp_computed:price/{eps_field}"
    elif pat is not None and pat > 0 and issue_size is not None:
        pe = issue_size / pat                    # cr / cr = x (proxy: issue-size-based)
        pe_source = "proxy:issue_size/pat"
    if pe is None:
        missing.append("pe_loss_making" if (pat is not None and pat <= 0) else "pe_missing")
        pe_source = "uncomputable"

    if issue_price is not None and nav not in (None, 0):
        pb = issue_price / nav
        pb_source = "rhp_computed:price/nav_per_share"
    elif issue_size is not None and nw not in (None, 0):
        pb = issue_size / nw                     # proxy
        pb_source = "proxy:issue_size/net_worth"
    if pb is None:
        missing.append("pb_missing")
        pb_source = "uncomputable"

    used["pe_source"] = pe_source
    used["pb_source"] = pb_source
    if eps is not None:
        used["rhp_eps"] = eps
        used["rhp_eps_field"] = eps_field
    if nav is not None: used["rhp_nav"] = nav
    # ---- rev_cagr_3y needs >=3 periods, ALL OF ONE BASIS ----
    # allrows is consolidated-first, newest-date-first. Restrict the CAGR series to the
    # LATEST row's basis so it never divides consolidated-newest by standalone-oldest.
    rev_cagr=None
    latest_basis=latest[1]
    revs=[float(r[2]) for r in allrows if r[1]==latest_basis and r[2] is not None]
    if len(revs)>=3 and revs[-1]>0:
        try: rev_cagr=((revs[0]/revs[-1])**(1/ (len(revs)-1)) -1)*100
        except Exception: rev_cagr=None
    if rev_cagr is None: missing.append("rev_cagr_3y_insufficient_periods")
    # ofs_pct
    ofs_pct = (ofs_cr/issue_size*100) if (ofs_cr is not None and issue_size not in (None,0)) else None

    # ---------- THE SCORE (weighted, owner tiers) ----------
    # ---------- THE SCORE (weighted, owner tiers — STRONG bar RAISED 07-31) ----------
    # STRONG must be EARNED by BREADTH, not two common traits (ROE+low-debt maxed).
    # Fix: (1) tighter "great" thresholds; (2) normalize by factor coverage so the score
    # is an AVERAGE quality, not a sum that saturates on 2 factors; (3) STRONG requires
    # growth data present (can't be exceptional on profitability alone).
    subs={}   # factor -> signed sub-score in [-2,+2]
    weights={}
    def add(name,val,w):
        subs[name]=val; weights[name]=w
    # ROE: >=25 exceptional, 18-25 strong, 12-18 ok, 8-12 weak, <8 poor, <=0 bad
    if roe is not None:
        r = 2 if roe>=25 else 1 if roe>=18 else 0.5 if roe>=12 else 0 if roe>=8 else -1 if roe>0 else -2
        add("roe", r, 2)
    # D/E: <=0.15 exceptional, <=0.35 strong, <=0.6 ok, <=1 weak, <=1.5 poor, >1.5 bad
    if de is not None:
        r = 2 if de<=0.15 else 1 if de<=0.35 else 0.5 if de<=0.6 else 0 if de<=1.0 else -1 if de<=1.5 else -2
        add("de", r, 2)
    # CAGR: >=30 exceptional, >=20 strong, >=12 ok, >=5 weak, <0 bad
    if rev_cagr is not None:
        r = 2 if rev_cagr>=30 else 1 if rev_cagr>=20 else 0.5 if rev_cagr>=12 else 0 if rev_cagr>=5 else -1 if rev_cagr>=0 else -2
        add("rev_cagr", r, 1.5)
    # valuation cheapness (PB proxy): <=1.5 cheap, <=3 fair, <=6 full, <=10 rich, >10 expensive
    if pb is not None:
        r = 1 if pb<=1.5 else 0.5 if pb<=3 else 0 if pb<=6 else -0.5 if pb<=10 else -1
        add("pb_value", r, 1)
    # PB regime factor: DEFAULT OFF (weight 0) — inverts by regime, owner said 0 in doubt

    # COVERAGE-NORMALIZED score: weighted AVERAGE of sub-scores, scaled to the [-5,+5] band axis.
    # This means a high band needs BROAD strength, not one or two maxed factors.
    if subs:
        wsum=sum(weights[k] for k in subs)
        avg=sum(subs[k]*weights[k] for k in subs)/wsum if wsum else 0   # avg in [-2,+2]
        raw = avg * 2.5                                                 # map [-2,+2] -> [-5,+5]
        # BREADTH GATE for STRONG (>2): require >=3 scorable factors AND growth data present,
        # else cap at FAVORABLE ceiling (2.0). Prevents "STRONG on ROE+debt alone".
        n_factors=len(subs)
        has_growth = "rev_cagr" in subs
        if raw>2 and (n_factors<3 or not has_growth):
            raw=2.0
            contribs_note="capped_favorable_insufficient_breadth"
        else:
            contribs_note=None
        score=round(max(-5.0,min(5.0,raw)),2)
    else:
        score=None; contribs_note=None; avg=None; n_factors=0
    contribs={k:round(subs[k]*weights[k],2) for k in subs}
    if contribs_note: contribs["_note"]=contribs_note
    if avg is not None: contribs["_avg"]=round(avg,2)
    sb = band_of(score)
    # if score uncomputable (no scorable factor), band stays None and that's explained
    if score is None: missing.append("score_no_scorable_factors")

    return dict(ipo_id=ipo_id, pe=_r(pe),pb=_r(pb),roe=_r(roe),roce=_r(roce),de=_r(de),
                rev_cagr_3y=_r(rev_cagr),ofs_pct=_r(ofs_pct),peer_median_pe=None,
                score=score, score_band=sb,
                missing_inputs=sorted(set(missing)),
                inputs_used={**used,"score_contribs":contribs})

def _r(x):
    """Round to 2dp AND cap to the DB numeric(6,2) range (abs < 10000). A PE/PB proxy
    above ~9999 means near-zero earnings/book — not meaningful; cap so the write is safe."""
    if not isinstance(x,(int,float)): return None
    x=round(x,2)
    if x >= 9999.99: return 9999.99
    if x <= -9999.99: return -9999.99
    return x

_VAL_NUMERIC = ["pe","pb","roe","roce","de","rev_cagr_3y","ofs_pct","peer_median_pe","score"]

def _same_valuation(prev, v):
    """True if the latest stored row equals this recompute on every COMPUTED value.
    prev is (pe,pb,roe,roce,de,rev_cagr_3y,ofs_pct,peer_median_pe,score,score_band,
    missing_inputs). inputs_used is derived provenance and is intentionally excluded."""
    for i,col in enumerate(_VAL_NUMERIC):
        a=prev[i]; b=v[col]
        if (a is None)!=(b is None): return False
        if a is not None and round(float(a),2)!=round(float(b),2): return False
    if (prev[9] or None)!=(v["score_band"] or None): return False
    if sorted(prev[10] or [])!=sorted(v["missing_inputs"] or []): return False
    return True

def write_valuation(conn, v):
    """Write one computed valuation row — IDEMPOTENT. If the latest row for this
    (ipo_id, engine_version) already matches every computed value, insert NOTHING
    (computed_at=now() otherwise made every run a duplicate — 135 dup rows across 15
    IPOs). Returns True on insert, False when skipped."""
    cur=conn.cursor()
    cur.execute("""SELECT pe,pb,roe,roce,de,rev_cagr_3y,ofs_pct,peer_median_pe,score,
                          score_band,missing_inputs
                   FROM valuation WHERE ipo_id=%s AND engine_version=%s
                   ORDER BY computed_at DESC LIMIT 1""",(v["ipo_id"],ENGINE_VERSION))
    prev=cur.fetchone()
    if prev is not None and _same_valuation(prev, v):
        return False
    cur.execute("""INSERT INTO valuation
       (ipo_id,computed_at,engine_version,pe,pb,roe,roce,de,rev_cagr_3y,ofs_pct,
        peer_median_pe,score,score_band,inputs_used,missing_inputs)
       VALUES (%s,now(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
       (v["ipo_id"],ENGINE_VERSION,v["pe"],v["pb"],v["roe"],v["roce"],v["de"],
        v["rev_cagr_3y"],v["ofs_pct"],v["peer_median_pe"],v["score"],v["score_band"],
        json.dumps(v["inputs_used"]), v["missing_inputs"]))
    conn.commit()
    return True

FILE_BUILD = "score_engine 2026-08-01 v2-score-2 — PE/PB from band+EPS/NAV, labelled proxy fallback"

# ------------------------------------------------------------------ selftest
def selftest():
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    ok=True
    print(f"  [build] {FILE_BUILD}")
    def chk(m,c):
        nonlocal ok; ok=ok and c; print(f"  [{'PASS' if c else 'FAIL'}] {m}")

    chk("ENGINE_VERSION bumped to v2-score-2", ENGINE_VERSION=="v2-score-2")
    # band step function
    chk("band(-3)=AVOID", band_of(-3)=="AVOID")
    chk("band(0)=NEUTRAL", band_of(0)=="NEUTRAL")
    chk("band(2)=FAVORABLE", band_of(2)=="FAVORABLE")
    chk("band(4)=STRONG", band_of(4)=="STRONG")

    # compute on 3 REAL fully-complete IPOs (read-only, no write)
    cur.execute("""SELECT v.ipo_id FROM valuation v
      WHERE v.pe IS NOT NULL AND v.pb IS NOT NULL AND v.roe IS NOT NULL LIMIT 5""")
    ids=[r[0] for r in cur.fetchall()]
    chk("found real complete IPOs to test", len(ids)>0)
    computed_scores=0
    for iid in ids:
        v=compute_valuation(conn, iid)
        if v["score"] is not None:
            computed_scores+=1
            chk(f"ipo {iid}: score={v['score']} band={v['score_band']} (band matches step fn)",
                v["score_band"]==band_of(v["score"]))
    chk("score COMPUTED (not NULL) for complete IPOs — the old bug fixed", computed_scores>0)

    # val_null_explained: an IPO with NO financials must name every missing ratio
    cur.execute("""SELECT i.id FROM ipo i
      WHERE NOT EXISTS(SELECT 1 FROM financial_statements f WHERE f.ipo_id=i.id) LIMIT 1""")
    r=cur.fetchone()
    if r:
        v=compute_valuation(conn, r[0])
        chk("no-financials IPO: missing_inputs populated (never silent NULL)", len(v["missing_inputs"])>0)
        chk("no-financials IPO: score is None AND explained", v["score"] is None)

    # a loss-making case names pe_loss_making — must find one whose LATEST financial
    # (consolidated, newest period) is loss-making, since the engine uses the latest row.
    cur.execute("""
      WITH latest AS (
        SELECT DISTINCT ON (ipo_id) ipo_id, pat
        FROM financial_statements
        ORDER BY ipo_id, (basis ILIKE '%consolidat%') DESC,
                 CASE WHEN period ~ '^[0-9]{1,2}-[A-Za-z]{3}-[0-9]{2}$'
                      THEN to_date(period,'DD-Mon-YY') END DESC NULLS LAST
      )
      SELECT ipo_id FROM latest WHERE pat<=0 LIMIT 1""")
    r=cur.fetchone()
    if r:
        v=compute_valuation(conn, r[0])
        loss_labeled = any("loss_making" in m for m in v["missing_inputs"])
        chk(f"loss-making IPO {r[0]}: PE/ROE explained as loss_making", loss_labeled)
    else:
        chk("loss-making test skipped (no IPO with loss-making LATEST financials)", True)

    # ---------------------------------------------------------- PE/PB PROVENANCE (v2-score-2)
    # A controlled IPO so the two derivation paths can be compared on identical inputs.
    from fill_ipo import upsert_ipo, _norm
    from fill_v2 import upsert_ipo_issue, upsert_financials, log_source_fact
    TI="INE000SCORE01"; TN=_norm("Zzz Score Provenance Selftest Ltd")
    for t in ["source_facts","ipo_issue","financial_statements","valuation"]:
        cur.execute(f"DELETE FROM {t} WHERE ipo_id IN (SELECT id FROM ipo WHERE isin=%s)",(TI,))
    cur.execute("DELETE FROM ipo WHERE isin=%s OR name_norm=%s",(TI,TN)); conn.commit()
    tid,_=upsert_ipo(conn, dict(isin=TI,name_display="Zzz Score Provenance Selftest Ltd",
                                name_norm=TN,issue_size_cr=500,listing_date="2025-06-01"),"test")
    upsert_ipo_issue(conn, tid, dict(issue_price=100.0, issue_size_cr=500.0), source="test")
    upsert_financials(conn, tid, "31-Mar-26","consolidated",
                      dict(revenue=1000.0, ebitda=200.0, pat=50.0,
                           net_worth=250.0, total_debt=50.0), source="test")

    # (a) no EPS/NAV yet -> PROXY, and it must still produce numbers (no regression)
    va=compute_valuation(conn, tid)
    chk("proxy PE computed when no RHP EPS (500/50=10)", va["pe"]==10.0)
    chk("proxy PB computed when no RHP NAV (500/250=2)", va["pb"]==2.0)
    chk("proxy PE LABELLED as proxy", va["inputs_used"]["pe_source"]=="proxy:issue_size/pat")
    chk("proxy PB LABELLED as proxy", va["inputs_used"]["pb_source"]=="proxy:issue_size/net_worth")
    chk("NO REGRESSION: pb_missing absent, so verdict GOOD gate is not tripped",
        "pb_missing" not in va["missing_inputs"])
    chk("NO REGRESSION: pe_missing absent", "pe_missing" not in va["missing_inputs"])

    # (b) RHP EPS/NAV arrive -> the REAL ratio takes over, labelled rhp_computed
    log_source_fact(conn, tid, "eps_post", 5.0, "rhp")
    log_source_fact(conn, tid, "nav_per_share", 25.0, "rhp")
    vb=compute_valuation(conn, tid)
    chk("RHP PE = price/EPS (100/5=20), overriding the proxy", vb["pe"]==20.0)
    chk("RHP PB = price/NAV (100/25=4), overriding the proxy", vb["pb"]==4.0)
    chk("RHP PE labelled rhp_computed", vb["inputs_used"]["pe_source"].startswith("rhp_computed"))
    chk("RHP PE names WHICH eps was used", "eps_post" in vb["inputs_used"]["pe_source"])
    chk("RHP PB labelled rhp_computed", vb["inputs_used"]["pb_source"].startswith("rhp_computed"))
    chk("eps/nav recorded in inputs_used for audit",
        vb["inputs_used"].get("rhp_eps")==5.0 and vb["inputs_used"].get("rhp_eps_field")=="eps_post" and vb["inputs_used"].get("rhp_nav")==25.0)
    chk("upgrading provenance changed the ratio (proxy 2.0 -> real 4.0)", va["pb"]!=vb["pb"])

    # (c) eps_pre is the documented fallback and says so
    cur.execute("DELETE FROM source_facts WHERE ipo_id=%s AND field='eps_post'",(tid,)); conn.commit()
    log_source_fact(conn, tid, "eps_pre", 4.0, "rhp")
    vc=compute_valuation(conn, tid)
    chk("falls back to eps_pre when eps_post absent (100/4=25)", vc["pe"]==25.0)
    chk("fallback names eps_pre, not eps_post", "eps_pre" in vc["inputs_used"]["pe_source"])

    # (d) IDEMPOTENT WRITES: first write inserts one row; an identical recompute inserts
    # NOTHING (computed_at=now() must not make a fresh duplicate on every run).
    vd=compute_valuation(conn, tid)
    w1=write_valuation(conn, vd)
    cur.execute("SELECT count(*) FROM valuation WHERE ipo_id=%s AND engine_version=%s",(tid,ENGINE_VERSION))
    n1=cur.fetchone()[0]
    w2=write_valuation(conn, compute_valuation(conn, tid))
    cur.execute("SELECT count(*) FROM valuation WHERE ipo_id=%s AND engine_version=%s",(tid,ENGINE_VERSION))
    n2=cur.fetchone()[0]
    chk("first valuation write inserts a row", w1 is True and n1>=1)
    chk("repeat valuation write inserts NOTHING (idempotent)", w2 is False and n2==n1)

    for t in ["source_facts","ipo_issue","financial_statements","valuation"]:
        cur.execute(f"DELETE FROM {t} WHERE ipo_id=%s",(tid,))
    cur.execute("DELETE FROM ipo WHERE id=%s",(tid,)); conn.commit()

    print(f"\n{'ALL PASS ✓' if ok else 'SOME FAILED ✗'}")
    conn.close(); return ok

def run_all(write=False):
    from nse_fetch import CANONICAL_UNIVERSE_SQL
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    # Was in_backtest_universe=TRUE, which skipped new listings on a manual --all run.
    # drive.py already scores new IPOs by calling compute_valuation directly; this makes
    # the batch run match that scope. is_mainboard defaults to True (unreliable), so add
    # the >=Rs.150cr floor to exclude SME issues (same scope as verdict_engine).
    cur.execute(f"""SELECT i.id FROM ipo i WHERE {CANONICAL_UNIVERSE_SQL}
                   ORDER BY i.id""")
    ids=[r[0] for r in cur.fetchall()]
    print(f"computing valuation for {len(ids)} mainboard IPOs (write={write})")
    bands={}; scored=0
    for i,iid in enumerate(ids,1):
        v=compute_valuation(conn, iid)
        if v["score"] is not None: scored+=1
        bands[v["score_band"]]=bands.get(v["score_band"],0)+1
        if write: write_valuation(conn, v)
        if i%100==0: print(f"  ...{i}/{len(ids)}")
    print(f"scored (non-null): {scored}/{len(ids)}")
    print("band distribution:", bands)
    conn.close()

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--all",action="store_true"); ap.add_argument("--write",action="store_true")
    ap.add_argument("--ipo",type=int)
    a=ap.parse_args()
    if a.selftest: sys.exit(0 if selftest() else 1)
    if a.ipo:
        conn=psycopg2.connect(os.environ["DATABASE_URL"])
        import pprint; pprint.pprint(compute_valuation(conn, a.ipo)); conn.close()
    elif a.all: run_all(write=a.write)
    else: print("--selftest | --ipo <id> | --all [--write]")
