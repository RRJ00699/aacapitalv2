#!/usr/bin/env python3
"""
fill_v2.py — V2 backend engine, ALL DATA-FILL TABLES in one module.
Each upsert_*(conn, record) inserts-or-updates WITHOUT duplicates, following the 5
anti-dup rules: ISIN spine, one-fact-one-home, COALESCE-empty-only, ON CONFLICT on the
real unique key, source_facts logs only on change.

10 data-fill tables here. The 3 ENGINE-OUTPUT tables (valuation, decisions,
rhp_findings/insights) are stubbed — they store COMPUTED output and get real bodies
when their engines are designed. Do NOT fill them from here.

Run all tests:  python fill_v2.py --selftest
"""
import os, sys, io, argparse, datetime as dt, hashlib
if __name__=="__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

# reuse the spine resolver from fill_ipo.py
sys.path.insert(0,".")
from fill_ipo import upsert_ipo, resolve_ipo_id, _log_fact, _norm

# ============================================================ helpers
def _coalesce_update(conn, table, match_cols, match_vals, fields, source=None, ipo_id=None,
                     insert_defaults=None, commit=True):
    """COALESCE-empty-only upsert.
    match_cols/match_vals = the REAL unique key (used to find the row AND on insert).
    insert_defaults = dict of NOT-NULL columns set ONLY on insert, never used to match
      and never updated (e.g. source, fetched_at).
    fields = enrichable columns (fill NULLs only on conflict).
    Returns 'inserted'/'enriched'. Logs changed fields to source_facts if source+ipo_id."""
    cur=conn.cursor(); insert_defaults=insert_defaults or {}
    where=" AND ".join(f"{k}=%s" for k in match_cols)
    cur.execute(f"SELECT 1 FROM {table} WHERE {where}", match_vals)
    exists=cur.fetchone() is not None
    if not exists:
        cols=list(match_cols)+list(insert_defaults.keys())+[f for f in fields]
        vals=list(match_vals)+[insert_defaults[k] for k in insert_defaults]+[fields[f] for f in fields]
        ph=",".join(["%s"]*len(cols))
        cur.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({ph})", vals)
        action="inserted"
    else:
        sets=[f"{f} = COALESCE({f}, %s)" for f in fields]
        if sets:
            cur.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE {where}",
                        [fields[f] for f in fields]+list(match_vals))
        action="enriched"
    if source and ipo_id:
        for f in fields:
            _log_fact(cur, ipo_id, f, fields[f], source)
    if commit: conn.commit()
    return action

# ============================================================ 1. ipo_issue
def upsert_ipo_issue(conn, ipo_id, record, source="nse"):
    """Issue economics, 1 row/IPO, key=ipo_id. COALESCE so NSE+IPOMatrix don't clobber."""
    cur=conn.cursor()
    fields={k:record.get(k) for k in
            ["open_date","close_date","allotment_date","band_lo","band_hi","issue_price",
             "lot_size","face_value","fresh_cr","ofs_cr","issue_size_cr","registrar","brlm_count"]
            if record.get(k) is not None}
    # ensure row exists w/ updated_at
    cur.execute("SELECT 1 FROM ipo_issue WHERE ipo_id=%s",(ipo_id,))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO ipo_issue(ipo_id,updated_at) VALUES(%s,now())",(ipo_id,))
        conn.commit()
    if fields:
        sets=[f"{f} = COALESCE({f}, %s)" for f in fields]+["updated_at=now()"]
        cur.execute(f"UPDATE ipo_issue SET {', '.join(sets)} WHERE ipo_id=%s",
                    [fields[f] for f in fields]+[ipo_id])
        for f in fields: _log_fact(cur, ipo_id, f, fields[f], source)
    conn.commit()
    return "ok"

# ============================================================ 2. subscription_snapshots
def upsert_subscription(conn, ipo_id, captured_at, record, is_final=False):
    """Append-only demand snapshot, key=(ipo_id,captured_at). Never update a past snapshot."""
    cur=conn.cursor()
    cols=["qib_x","nii_x","bnii_x","snii_x","retail_x","total_x","anchor_amount_cr",
          "anchor_count","applications_lakh","mf_shares_bid","mf_pct_qib"]
    vals=[record.get(c) for c in cols]
    cur.execute(f"""INSERT INTO subscription_snapshots
        (ipo_id,captured_at,is_final,{','.join(cols)})
        VALUES (%s,%s,%s,{','.join(['%s']*len(cols))})
        ON CONFLICT (ipo_id,captured_at) DO NOTHING""",
        [ipo_id,captured_at,is_final]+vals)
    conn.commit(); return "ok"

# ============================================================ 3. financial_statements
def upsert_financials(conn, ipo_id, period, basis, record, source="ipomatrix", commit=True):
    """Multi-period financials, key=(ipo_id,period,basis). COALESCE-empty-only.
    source+fetched_at are insert-only (NOT part of the dedup key).

    TWO revenue lines are stored, deliberately (Indo-MIM 07-31 finding):
      revenue      = Revenue from Operations  (RHP's core operating top line)
      total_income = Total Income             (= revenue + other income; what IPOMatrix reports)
    The 1 field that 'differed' vs IPOMatrix was definitional, not an error — so we keep
    both rather than pick one. Requires column total_income (migration 01_add_total_income.sql)."""
    return _coalesce_update(conn, "financial_statements",
        ["ipo_id","period","basis"], [ipo_id, period, basis],
        {k:record.get(k) for k in ["revenue","total_income","ebitda","pat","net_worth",
                                   "total_debt","total_assets"]
         if record.get(k) is not None},
        insert_defaults={"source":source, "fetched_at":dt.datetime.now(dt.timezone.utc)},
        commit=commit)

# ============================================================ 4. documents (dedup by hash)
def upsert_document(conn, ipo_id, doc_type, content_bytes=None, url=None, sha256=None,
                    page_count=None, document_date=None):
    """Compatibility facade; document_ledger owns all storage and DB writes."""
    if content_bytes is None:
        raise ValueError("documents: contract-v1 storage requires content bytes")
    if sha256 is not None and hashlib.sha256(content_bytes).hexdigest() != sha256:
        raise ValueError("documents: supplied sha256 does not match content")
    cur = conn.cursor()
    cur.execute("SELECT isin FROM ipo WHERE id=%s", (ipo_id,))
    owner = cur.fetchone()
    cur.close()
    if not owner:
        conn.rollback()
        raise ValueError("documents: ipo_id is not present in the Neon ownership spine")
    # End the ownership SELECT before any R2 operation; the ledger transaction starts
    # only after the orchestration layer has verified the immutable object.
    conn.commit()
    from document_ledger import store_document
    stored = store_document(
        conn, ipo_id=ipo_id, isin=owner[0], doc_type=doc_type,
        document_date=document_date or dt.datetime.now(dt.timezone.utc).date(),
        source_url=url, content=content_bytes, page_count=page_count,
    )
    return stored.id

# ============================================================ 5. source_facts (change-log)
def log_source_fact(conn, ipo_id, field, value, source, doc_id=None, confidence=1.0, commit=True):
    """Provenance, insert ONLY on change. Thin wrapper over the shared _log_fact."""
    cur=conn.cursor(); _log_fact(cur, ipo_id, field, value, source)
    if commit: conn.commit()

# ============================================================ 6. listing_outcomes
def upsert_listing_outcome(conn, ipo_id, record, dataset_version="v2"):
    """Post-listing result, 1 row/IPO, key=ipo_id. RECOMPUTED not enriched → overwrite."""
    cur=conn.cursor()
    cols=["listing_open","d1_close","gap_pct","best_close","worst_close","ceiling_20",
          "hold_positive_vs_open","winner_35","pool"]
    vals=[record.get(c) for c in cols]
    setclause=",".join(f"{c}=EXCLUDED.{c}" for c in cols)
    cur.execute(f"""INSERT INTO listing_outcomes
        (ipo_id,{','.join(cols)},computed_at,dataset_version)
        VALUES (%s,{','.join(['%s']*len(cols))},now(),%s)
        ON CONFLICT (ipo_id) DO UPDATE SET {setclause},
          computed_at=now(), dataset_version=EXCLUDED.dataset_version""",
        [ipo_id]+vals+[dataset_version])
    conn.commit(); return "ok"

# ============================================================ 7. market_regimes
def upsert_market_regime(conn, d, record):
    """Daily context, key=d. One row/trading day."""
    cur=conn.cursor()
    cols=["regime","vix","breadth_pct","pcr"]; vals=[record.get(c) for c in cols]
    setclause=",".join(f"{c}=COALESCE(market_regimes.{c},EXCLUDED.{c})" for c in cols)
    cur.execute(f"""INSERT INTO market_regimes (d,{','.join(cols)})
        VALUES (%s,{','.join(['%s']*len(cols))})
        ON CONFLICT (d) DO UPDATE SET {setclause}""", [d]+vals)
    conn.commit(); return "ok"

# ============================================================ 8. market_candles
def upsert_candles(conn, ipo_id, bars):
    """Daily OHLC+delivery, key=(ipo_id,d). bars = list of dicts {d,o,h,l,c,v,delivery_pct,traded_qty}."""
    cur=conn.cursor(); n=0
    for b in bars:
        cur.execute("""INSERT INTO market_candles(ipo_id,d,o,h,l,c,v,delivery_pct,traded_qty)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (ipo_id,d) DO UPDATE SET
              o=COALESCE(market_candles.o,EXCLUDED.o), h=COALESCE(market_candles.h,EXCLUDED.h),
              l=COALESCE(market_candles.l,EXCLUDED.l), c=COALESCE(market_candles.c,EXCLUDED.c),
              v=COALESCE(market_candles.v,EXCLUDED.v),
              delivery_pct=COALESCE(market_candles.delivery_pct,EXCLUDED.delivery_pct),
              traded_qty=COALESCE(market_candles.traded_qty,EXCLUDED.traded_qty)""",
            (ipo_id,b["d"],b.get("o"),b.get("h"),b.get("l"),b.get("c"),b.get("v"),
             b.get("delivery_pct"),b.get("traded_qty")))
        n+=1
    conn.commit(); return n

# ==================================================== 8b. market_candles_15m
def ensure_15m_table(conn):
    """15-minute intraday OHLCV — NEW V2 table. Replaces the dropped intraday_30d,
    whose misleading name (said 30d, held 10 years) got it swept with the V1 debris
    and which had NO primary key, so nothing could upsert into it safely. PK
    (ipo_id, ts) makes the paginated backfill idempotent and re-runnable."""
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS market_candles_15m (
        ipo_id bigint NOT NULL, ts timestamptz NOT NULL,
        o numeric, h numeric, l numeric, c numeric, v bigint,
        PRIMARY KEY (ipo_id, ts))""")
    conn.commit()

def upsert_candles_15m(conn, ipo_id, bars):
    """15-min OHLCV, key=(ipo_id,ts). bars = list of {ts,o,h,l,c,v}. Idempotent —
    a re-fetch of the same window overwrites with the same values."""
    cur = conn.cursor(); n = 0
    for b in bars:
        cur.execute("""INSERT INTO market_candles_15m(ipo_id,ts,o,h,l,c,v)
            VALUES(%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (ipo_id,ts) DO UPDATE SET
              o=EXCLUDED.o, h=EXCLUDED.h, l=EXCLUDED.l, c=EXCLUDED.c, v=EXCLUDED.v""",
            (ipo_id, b["ts"], b.get("o"), b.get("h"), b.get("l"), b.get("c"), b.get("v")))
        n += 1
    conn.commit(); return n

# ============================================================ 9. listing_observations
def upsert_observation(conn, ipo_id, observed_at, obs_type, record):
    """Listing-day tape/preopen, key=(ipo_id,obs_type,observed_at). Append (idempotent)."""
    import json
    cur=conn.cursor()
    payload=record.get("payload")
    cur.execute("""INSERT INTO listing_observations
        (ipo_id,observed_at,obs_type,ltp,qty,buy_qty,sell_qty,payload)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (ipo_id,obs_type,observed_at) DO NOTHING""",
        (ipo_id,observed_at,obs_type,record.get("ltp"),record.get("qty"),
         record.get("buy_qty"),record.get("sell_qty"),
         json.dumps(payload) if payload is not None else None))
    conn.commit(); return "ok"

# ============================================================ ENGINE-OUTPUT STUBS
def upsert_valuation(*a, **k):
    raise NotImplementedError("valuation stores ENGINE output — build with the scoring engine, not here")
def upsert_decision(*a, **k):
    raise NotImplementedError("decisions stores VERDICT-engine output — build with the verdict engine")

# ============================================================ 11. rhp_findings (Sonnet run)
# Schema verified 07-31 via inspect_schema.py / inspect_checks.py:
#   cols   : id, ipo_id, doc_id, model, prompt_version, findings(jsonb NOT NULL),
#            red_flag_count(smallint), junk_signals(text[]), confidence, cost_usd, analyzed_at
#   UNIQUE : (doc_id, model, prompt_version) WHERE doc_id IS NOT NULL   <- PARTIAL index
#   CHECK  : rhp_conf_range — confidence NULL or 0..1
#
# The partial index is the reason doc_id is MANDATORY here. 372 of the 376 legacy rows
# have doc_id NULL and therefore have NO dedup protection at all — re-running the
# extractor on those would have silently duplicated. We refuse to write without a
# doc_id rather than inherit that hole.
def upsert_rhp_findings(conn, ipo_id, doc_id, findings, model, prompt_version,
                        red_flag_count=None, junk_signals=None, confidence=None,
                        cost_usd=None, commit=True):
    """One Sonnet extraction RUN for one document. Key=(doc_id,model,prompt_version).

    RECOMPUTE semantics (engine output, like valuation) — a re-run of the SAME
    doc+model+prompt_version OVERWRITES its previous result. It does NOT COALESCE:
    a corrected extraction must be able to clear a field that was previously wrong.
    Returns (rhp_findings.id, 'inserted'|'updated')."""
    import json as _json
    if doc_id is None:
        raise ValueError("upsert_rhp_findings: doc_id is required — the UNIQUE index is "
                         "partial (WHERE doc_id IS NOT NULL), so a NULL doc_id silently "
                         "disables dedup. Call upsert_document() first and pass its id.")
    if findings is None:
        raise ValueError("upsert_rhp_findings: findings is NOT NULL in schema")
    if confidence is not None and not (0 <= float(confidence) <= 1):
        raise ValueError(f"upsert_rhp_findings: confidence {confidence} violates rhp_conf_range (0..1)")
    cur = conn.cursor()
    cur.execute("""INSERT INTO rhp_findings
          (ipo_id, doc_id, model, prompt_version, findings, red_flag_count,
           junk_signals, confidence, cost_usd, analyzed_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT (doc_id, model, prompt_version) WHERE doc_id IS NOT NULL
        DO UPDATE SET findings        = EXCLUDED.findings,
                      red_flag_count  = EXCLUDED.red_flag_count,
                      junk_signals    = EXCLUDED.junk_signals,
                      confidence      = EXCLUDED.confidence,
                      cost_usd        = EXCLUDED.cost_usd,
                      analyzed_at     = now()
        RETURNING id, (xmax = 0) AS was_insert""",
        (ipo_id, doc_id, model, prompt_version, _json.dumps(findings),
         red_flag_count, junk_signals, confidence, cost_usd))
    rid, was_insert = cur.fetchone()
    if commit: conn.commit()
    return rid, ("inserted" if was_insert else "updated")

# ============================================================ 12. insights (renderable claims)
# Schema verified 07-31. insights has NO unique key beyond the PK, so dedup CANNOT be
# ON CONFLICT — it is SUPERSESSION (Amendment 1: is_current=FALSE, never delete).
# CHECKs that govern every row:
#   ins_category_valid : category   in structure|governance|financial|valuation|sbi|risk
#   ins_direction_valid: direction  in positive|negative|neutral|incomplete
#   ins_source_valid   : source_type in RHP|SBI|STRUCTURED|HOUSE_RULE
#   ins_evidence_required: source_type in (STRUCTURED,HOUSE_RULE) OR (doc_id AND excerpt)
#                          -> an RHP claim MUST carry doc_id AND excerpt. No exceptions.
#   ins_conf_range     : confidence NULL or 0..1
CATEGORIES   = {"structure", "governance", "financial", "valuation", "sbi", "risk"}
DIRECTIONS   = {"positive", "negative", "neutral", "incomplete"}
SOURCE_TYPES = {"RHP", "SBI", "STRUCTURED", "HOUSE_RULE"}

def upsert_insights(conn, ipo_id, items, model=None, prompt_version=None,
                    doc_id=None, source_type="RHP", run_id=None, commit=True):
    """Write a batch of renderable claims for one IPO, superseding the previous batch
    from the SAME (ipo_id, source_type, prompt_version).

    items = list of dicts: category, statement, direction, [excerpt], [page_number],
            [confidence], [doc_id] (falls back to the doc_id argument).

    Supersession scope is deliberately NARROW — it never touches rows of a different
    source_type or prompt_version, so the 252 existing HOUSE_RULE rows are untouched
    when the RHP extractor runs.

    Every item is validated against the CHECK constraints BEFORE any write, so a bad
    batch fails with a readable message instead of a mid-batch IntegrityError that
    leaves half the claims superseded and half written.
    Returns (inserted_count, superseded_count, run_id)."""
    import uuid as _uuid
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"insights.source_type {source_type!r} not in {sorted(SOURCE_TYPES)}")
    if not items:
        return 0, 0, None
    run_id = run_id or str(_uuid.uuid4())

    # ---- validate the WHOLE batch first (fail before touching anything) ----
    clean = []
    for i, it in enumerate(items):
        cat = it.get("category"); dirn = it.get("direction"); stmt = it.get("statement")
        did = it.get("doc_id", doc_id); exc = it.get("excerpt")
        conf = it.get("confidence")
        if cat not in CATEGORIES:
            raise ValueError(f"insights[{i}]: category {cat!r} not in {sorted(CATEGORIES)}")
        if dirn not in DIRECTIONS:
            raise ValueError(f"insights[{i}]: direction {dirn!r} not in {sorted(DIRECTIONS)}")
        if not stmt:
            raise ValueError(f"insights[{i}]: statement is NOT NULL in schema")
        if source_type in ("RHP", "SBI") and (did is None or not exc):
            raise ValueError(f"insights[{i}]: source_type={source_type} requires BOTH doc_id "
                             f"and excerpt (CHECK ins_evidence_required) — got doc_id={did}, "
                             f"excerpt={'present' if exc else 'MISSING'}")
        if conf is not None and not (0 <= float(conf) <= 1):
            raise ValueError(f"insights[{i}]: confidence {conf} violates ins_conf_range (0..1)")
        clean.append((ipo_id, did, cat, stmt, dirn, source_type, it.get("page_number"),
                      exc, model, prompt_version, run_id, conf))

    cur = conn.cursor()
    # ---- supersede the previous batch of the same kind (never delete) ----
    cur.execute("""UPDATE insights SET is_current = FALSE
                    WHERE ipo_id = %s AND source_type = %s AND is_current = TRUE
                      AND coalesce(prompt_version,'') = coalesce(%s,'')""",
                (ipo_id, source_type, prompt_version))
    superseded = cur.rowcount
    # ---- insert the new batch as current ----
    cur.executemany("""INSERT INTO insights
          (ipo_id, doc_id, category, statement, direction, source_type, page_number,
           excerpt, model, prompt_version, run_id, confidence, is_current, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, TRUE, now())""", clean)
    if commit: conn.commit()
    return len(clean), superseded, run_id

# ============================================================ SELFTEST
def selftest():
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    ensure_15m_table(conn)   # the one V2 table with a CREATE helper — make the cleanup
                             # DELETE below safe even before kite_fetch's first --write run
    TISIN="INE000FILL999"; TNORM=_norm("Zzz Fillv2 Test Ltd")
    # cleanup any prior
    cur.execute("SELECT id FROM ipo WHERE isin=%s OR name_norm=%s",(TISIN,TNORM))
    old=[r[0] for r in cur.fetchall()]
    for tid in old:
        for t in ["rhp_findings","insights","source_facts","ipo_issue","subscription_snapshots",
                  "financial_statements","listing_outcomes","market_candles","market_candles_15m",
                  "listing_observations","documents"]:
            cur.execute(f"DELETE FROM {t} WHERE ipo_id=%s",(tid,))
        cur.execute("DELETE FROM ipo WHERE id=%s",(tid,))
    cur.execute("DELETE FROM market_regimes WHERE d='1999-01-01'"); conn.commit()
    ok=True
    def chk(m,c):
        nonlocal ok; ok=ok and c; print(f"  [{'PASS' if c else 'FAIL'}] {m}")

    # spine
    iid,_=upsert_ipo(conn, dict(isin=TISIN,name_display="Zzz Fillv2 Test Ltd",name_norm=TNORM,
                                issue_size_cr=600,listing_date="2025-05-01",is_mainboard=True))
    chk("ipo spine row created", iid is not None)

    # 1 ipo_issue
    upsert_ipo_issue(conn, iid, dict(band_lo=100,band_hi=110,lot_size=50), "nse")
    upsert_ipo_issue(conn, iid, dict(band_hi=999,fresh_cr=300,issue_size_cr=600), "ipomatrix")  # band_hi must NOT clobber
    cur.execute("SELECT band_hi,fresh_cr,lot_size FROM ipo_issue WHERE ipo_id=%s",(iid,)); r=cur.fetchone()
    chk("ipo_issue band_hi NOT clobbered (110 not 999)", float(r[0])==110)
    chk("ipo_issue fresh_cr enriched (300)", float(r[1])==300)
    cur.execute("SELECT count(*) FROM ipo_issue WHERE ipo_id=%s",(iid,)); chk("ipo_issue exactly 1 row", cur.fetchone()[0]==1)

    # 2 subscription (append, dedup on captured_at)
    t1=dt.datetime(2025,4,28,10,0,tzinfo=dt.timezone.utc)
    upsert_subscription(conn, iid, t1, dict(qib_x=5,retail_x=3,total_x=8))
    upsert_subscription(conn, iid, t1, dict(qib_x=9))  # same captured_at -> DO NOTHING
    upsert_subscription(conn, iid, t1+dt.timedelta(hours=1), dict(qib_x=12), is_final=True)
    cur.execute("SELECT count(*) FROM subscription_snapshots WHERE ipo_id=%s",(iid,)); chk("subscription 2 distinct snapshots (no dup on captured_at)", cur.fetchone()[0]==2)

    # 3 financials (dedup on period,basis)
    upsert_financials(conn, iid, "FY24","consolidated", dict(revenue=1000,pat=100))
    upsert_financials(conn, iid, "FY24","consolidated", dict(pat=999,ebitda=200))  # pat must NOT clobber
    cur.execute("SELECT pat,ebitda FROM financial_statements WHERE ipo_id=%s AND period='FY24'",(iid,)); r=cur.fetchone()
    chk("financials pat NOT clobbered (100)", float(r[0])==100); chk("financials ebitda enriched (200)", float(r[1])==200)
    cur.execute("SELECT count(*) FROM financial_statements WHERE ipo_id=%s",(iid,)); chk("financials exactly 1 row (FY24,consol)", cur.fetchone()[0]==1)
    # 3b total_income: BOTH revenue lines coexist (rev-from-ops vs total-income), same row, no dup
    upsert_financials(conn, iid, "FY24","consolidated", dict(total_income=1100), source="rhp")
    cur.execute("SELECT revenue,total_income FROM financial_statements WHERE ipo_id=%s AND period='FY24'",(iid,)); r=cur.fetchone()
    chk("total_income enriched (1100)", r[1] is not None and float(r[1])==1100)
    chk("revenue NOT clobbered by total_income write (still 1000)", float(r[0])==1000)
    upsert_financials(conn, iid, "FY24","consolidated", dict(total_income=7777), source="rhp")
    cur.execute("SELECT total_income,count(*) OVER () FROM financial_statements WHERE ipo_id=%s AND period='FY24'",(iid,)); r=cur.fetchone()
    chk("total_income NOT clobbered on re-write (still 1100)", float(r[0])==1100)
    chk("still exactly 1 financials row after total_income writes", r[1]==1)

    # 4 documents (dedup by sha256)
    d1=upsert_document(conn, iid, "rhp", content_bytes=b"hello-rhp-pdf", page_count=200)
    d2=upsert_document(conn, iid, "rhp", content_bytes=b"hello-rhp-pdf")  # same bytes -> same id
    chk("documents same hash -> same doc_id (no dup)", d1==d2)
    cur.execute("SELECT count(*) FROM documents WHERE ipo_id=%s",(iid,)); chk("documents exactly 1 row", cur.fetchone()[0]==1)

    # 5 source_facts change-log
    cur.execute("SELECT count(*) FROM source_facts WHERE ipo_id=%s AND field='sbi_rating'",(iid,)); n0=cur.fetchone()[0]
    log_source_fact(conn, iid, "sbi_rating","4/5","sbi")
    log_source_fact(conn, iid, "sbi_rating","4/5","sbi")  # unchanged -> no new row
    cur.execute("SELECT count(*) FROM source_facts WHERE ipo_id=%s AND field='sbi_rating'",(iid,)); chk("source_facts unchanged adds no row", cur.fetchone()[0]==n0+1)

    # 6 listing_outcomes (recompute overwrites)
    upsert_listing_outcome(conn, iid, dict(listing_open=120,d1_close=130,pool="FLAT",hold_positive_vs_open=True))
    upsert_listing_outcome(conn, iid, dict(listing_open=120,d1_close=140,pool="FLAT"))  # recompute
    cur.execute("SELECT d1_close FROM listing_outcomes WHERE ipo_id=%s",(iid,)); chk("listing_outcome recomputed (d1_close 140)", float(cur.fetchone()[0])==140)
    cur.execute("SELECT count(*) FROM listing_outcomes WHERE ipo_id=%s",(iid,)); chk("listing_outcome exactly 1 row", cur.fetchone()[0]==1)

    # 7 market_regimes
    upsert_market_regime(conn, "1999-01-01", dict(regime="HOT",vix=12.5))
    cur.execute("SELECT count(*) FROM market_regimes WHERE d='1999-01-01'"); chk("market_regime 1 row", cur.fetchone()[0]==1)

    # 8 market_candles (dedup on d)
    upsert_candles(conn, iid, [dict(d="2025-05-01",o=120,h=135,l=118,c=130,v=100000),
                               dict(d="2025-05-02",o=130,h=140,l=128,c=138,v=90000)])
    upsert_candles(conn, iid, [dict(d="2025-05-01",o=120,h=135,l=118,c=130,v=100000)])  # dup day
    cur.execute("SELECT count(*) FROM market_candles WHERE ipo_id=%s",(iid,)); chk("market_candles 2 distinct days (no dup)", cur.fetchone()[0]==2)

    # 9 listing_observations (dedup on obs_type,observed_at)
    ot=dt.datetime(2025,5,1,4,15,tzinfo=dt.timezone.utc)
    upsert_observation(conn, iid, ot, "candle_1m", dict(ltp=125,payload={"o":120,"c":125}))
    upsert_observation(conn, iid, ot, "candle_1m", dict(ltp=999))  # same key -> DO NOTHING
    cur.execute("SELECT count(*) FROM listing_observations WHERE ipo_id=%s",(iid,)); chk("listing_observation 1 row (no dup on key)", cur.fetchone()[0]==1)

    # 10 engine stubs must refuse (valuation/decisions still belong to their own engines)
    try: upsert_valuation(); chk("valuation stub raises", False)
    except NotImplementedError: chk("valuation stub correctly refuses (engine table)", True)

    # 11 rhp_findings — key is the PARTIAL unique (doc_id,model,prompt_version)
    rid1, act1 = upsert_rhp_findings(conn, iid, d1, {"verdict":"clean","one_line":"t"},
                                     "claude-sonnet-4-6", "v2-full",
                                     red_flag_count=1, junk_signals=["sebi_action"],
                                     confidence=0.9, cost_usd=0.0123)
    chk("rhp_findings first write inserts", act1=="inserted")
    rid2, act2 = upsert_rhp_findings(conn, iid, d1, {"verdict":"some-concerns","one_line":"t2"},
                                     "claude-sonnet-4-6", "v2-full", red_flag_count=3)
    chk("rhp_findings re-run same doc+model+version UPDATES (no dup)", act2=="updated")
    chk("rhp_findings re-run keeps the SAME row id", rid2==rid1)
    cur.execute("SELECT count(*) FROM rhp_findings WHERE ipo_id=%s",(iid,))
    chk("rhp_findings exactly 1 row after re-run", cur.fetchone()[0]==1)
    cur.execute("SELECT findings->>'verdict', red_flag_count FROM rhp_findings WHERE id=%s",(rid1,))
    r=cur.fetchone()
    chk("rhp_findings RECOMPUTE overwrites (verdict now some-concerns)", r[0]=="some-concerns")
    chk("rhp_findings red_flag_count overwritten (3)", r[1]==3)
    try:
        upsert_rhp_findings(conn, iid, None, {"x":1}, "m", "v2-full")
        chk("rhp_findings refuses NULL doc_id (partial-index hole)", False)
    except ValueError: chk("rhp_findings refuses NULL doc_id (partial-index hole)", True)
    try:
        upsert_rhp_findings(conn, iid, d1, {"x":1}, "m", "v2-full", confidence=1.7)
        chk("rhp_findings rejects confidence>1 (rhp_conf_range)", False)
    except ValueError: chk("rhp_findings rejects confidence>1 (rhp_conf_range)", True)

    # 12 insights — supersession, CHECK validation, evidence requirement
    items=[dict(category="financial", statement="ROE 22% FY26", direction="positive",
                excerpt="Return on Equity 22.0%", page_number=112, confidence=0.9),
           dict(category="valuation", statement="P/E 34x at upper band", direction="neutral",
                excerpt="Price to Earnings 34.1", page_number=113)]
    n1, sup1, run1 = upsert_insights(conn, iid, items, model="claude-sonnet-4-6",
                                     prompt_version="v2-full", doc_id=d1, source_type="RHP")
    chk("insights batch inserted (2)", n1==2)
    chk("insights first batch supersedes nothing", sup1==0)
    cur.execute("SELECT count(*) FROM insights WHERE ipo_id=%s AND is_current",(iid,))
    chk("insights 2 current rows", cur.fetchone()[0]==2)
    n2, sup2, run2 = upsert_insights(conn, iid, items[:1], model="claude-sonnet-4-6",
                                     prompt_version="v2-full", doc_id=d1, source_type="RHP")
    chk("insights re-run supersedes the prior 2", sup2==2)
    cur.execute("SELECT count(*) FROM insights WHERE ipo_id=%s AND is_current",(iid,))
    chk("insights now 1 current row (supersession, not delete)", cur.fetchone()[0]==1)
    cur.execute("SELECT count(*) FROM insights WHERE ipo_id=%s",(iid,))
    chk("insights old rows RETAINED (3 total)", cur.fetchone()[0]==3)
    chk("insights run_id differs per run", run1!=run2)
    try:
        upsert_insights(conn, iid, [dict(category="bogus", statement="x", direction="positive",
                                         excerpt="e")], doc_id=d1)
        chk("insights rejects bad category (ins_category_valid)", False)
    except ValueError: chk("insights rejects bad category (ins_category_valid)", True)
    try:
        upsert_insights(conn, iid, [dict(category="risk", statement="x", direction="sideways",
                                         excerpt="e")], doc_id=d1)
        chk("insights rejects bad direction (ins_direction_valid)", False)
    except ValueError: chk("insights rejects bad direction (ins_direction_valid)", True)
    try:
        upsert_insights(conn, iid, [dict(category="risk", statement="x", direction="negative")],
                        doc_id=d1, source_type="RHP")
        chk("insights rejects RHP claim with no excerpt (ins_evidence_required)", False)
    except ValueError: chk("insights rejects RHP claim with no excerpt (ins_evidence_required)", True)
    # a HOUSE_RULE claim is exempt from the evidence requirement — must be accepted
    n3,_,_ = upsert_insights(conn, iid, [dict(category="structure", statement="MF>0",
                                              direction="positive")],
                             prompt_version="v2-full", source_type="HOUSE_RULE")
    chk("insights accepts HOUSE_RULE without doc_id/excerpt (CHECK exemption)", n3==1)
    cur.execute("SELECT count(*) FROM insights WHERE ipo_id=%s AND source_type='RHP' AND is_current",(iid,))
    chk("HOUSE_RULE write did NOT supersede the RHP rows (narrow scope)", cur.fetchone()[0]==1)

    # cleanup — rhp_findings/insights FIRST: both carry a doc_id FK into documents
    for t in ["rhp_findings","insights","source_facts","ipo_issue","subscription_snapshots",
              "financial_statements","listing_outcomes","market_candles","market_candles_15m",
              "listing_observations","documents"]:
        cur.execute(f"DELETE FROM {t} WHERE ipo_id=%s",(iid,))
    cur.execute("DELETE FROM ipo WHERE id=%s",(iid,))
    cur.execute("DELETE FROM market_regimes WHERE d='1999-01-01'"); conn.commit()
    print(f"\n{'ALL PASS ✓' if ok else 'SOME FAILED ✗'}")
    conn.close(); return ok

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--selftest",action="store_true")
    a=ap.parse_args()
    if a.selftest: sys.exit(0 if selftest() else 1)
    print("V2 fill module — 10 data-fill upserts. import them, or run --selftest")
