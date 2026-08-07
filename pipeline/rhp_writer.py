#!/usr/bin/env python3
"""
rhp_writer.py — routes RHP-EXTRACTED numbers into the V2 tables.

WHY A SEPARATE ENGINE_VERSION
-----------------------------
valuation already holds two families of rows:
    v1-import    709 rows   (migrated)
    v2-score-1   662 rows   (score_engine.py — DERIVED ratios)
score_engine's PE/PB are PROXIES and are labelled as such in its own source:
PE = issue_size_cr / pat, PB = issue_size_cr / net_worth, because true PE needs
shares-outstanding, which is not in the schema.

The RHP "Basis for Issue Price" section reports the REAL ones — the issuer's own
audited ROE/RONW/EPS/NAV and the P/E computed on actual shares. Those are BETTER
numbers, but they are a DIFFERENT MEASUREMENT, not a correction. Writing them into
the v2-score-1 row would destroy the derived series and make the score irreproducible.

So they land as engine_version='v2-rhp-1'. The valuation UNIQUE key is
(ipo_id, engine_version, computed_at), so the two families cannot collide by
construction. Consumers read whichever they want, and the two can be compared —
which is exactly how vendor-independence was proven in the first place.

SCHEMA FACTS THIS FILE DEPENDS ON (verified 07-31, inspect_schema/inspect_checks):
  valuation UNIQUE : (ipo_id, engine_version, computed_at)
  CHECK val_null_explained : (pe NOT NULL AND pb NOT NULL) OR missing_inputs NOT NULL
  CHECK val_band_valid     : score_band NULL or STRONG|FAVORABLE|NEUTRAL|AVOID
  valuation columns available: pe pb roe roce de rev_cagr_3y ofs_pct peer_median_pe
                               fair_value_lo fair_value_hi score score_band
                               quality_promoter inputs_used(jsonb) missing_inputs(text[])

Run tests:  python rhp_writer.py --selftest
"""
import os, sys, io, argparse, json
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

sys.path.insert(0, ".")
from fill_v2 import log_source_fact

ENGINE_VERSION = "v2-rhp-1"

# valuation columns this writer fills from RHP-reported KPIs.
#
# PE AND PB ARE DELIBERATELY ABSENT (design correction 08-01, proven by the Indo-MIM run).
# The RHP states "the Offer Price is [●] times the face value" — the price band is not
# fixed at filing, so P/E and P/B are UNKNOWABLE from any pre-band RHP. Indo-MIM returned
# them null, which was CORRECT behaviour, not a miss. They are derived downstream by
# score_engine from the NSE band + the EPS/NAV this file stores. RHP owns the
# band-INDEPENDENT numbers; score_engine is the sole owner of PE/PB.
VAL_RATIOS = ["roe", "roce", "de", "rev_cagr_3y", "peer_median_pe"]

# Ratios this writer must never claim, and why — written into missing_inputs so the gap
# is self-explaining instead of looking like a failed extraction.
ENGINE_OWNED = {"pe": "pe_derived_from_band_by_score_engine",
                "pb": "pb_derived_from_band_by_score_engine"}

# A "median" of one or two peers is a single data point wearing a statistic's clothes.
# Indo-MIM disclosed exactly ONE listed comparable at P/E 148 — storing that as
# peer_median_pe would push false precision straight into the valuation row.
MIN_PEERS_FOR_MEDIAN = 3

# RHP KPIs that valuation has NO column for. Standing rule (Amendment 1):
# structured scalars -> source_facts. They are ALSO mirrored into inputs_used so the
# valuation row is self-describing without a join.
SCALAR_KPIS = ["ronw", "nav_per_share", "eps_pre", "eps_post", "ebitda_margin_pct",
               "pat_margin_pct", "market_cap_cr", "shares_outstanding"]


def _r(x):
    """Round to 2dp and clamp to the DB numeric range.

    NOT defensive guesswork: score_engine.py records a real NumericValueOutOfRange
    on this exact column set — valuation.pe/pb overflow for near-zero-PAT companies.
    A ratio above ~9999 means meaningless near-zero earnings/book anyway."""
    if x is None or isinstance(x, bool):
        return None
    try:
        x = round(float(x), 2)
    except (TypeError, ValueError):
        return None
    if x >= 9999.99:  return 9999.99
    if x <= -9999.99: return -9999.99
    return x


def write_rhp_valuation(conn, ipo_id, kpi, doc_id=None, source="rhp", commit=True):
    """Write ONE valuation row of RHP-reported ratios under engine_version='v2-rhp-1'.

    kpi = dict which may contain any of VAL_RATIOS + SCALAR_KPIS. Absent or
    unparseable values are NOT silently dropped — each one is NAMED in missing_inputs
    as '<field>_not_in_rhp', which is what CHECK val_null_explained demands and what
    makes a gap auditable later.

    score / score_band are left NULL on purpose: this row REPORTS what the issuer
    disclosed, it does not judge it. Scoring stays with score_engine (v2-score-1).

    Returns dict(valuation_id, written, missing_inputs, scalars_logged).
    """
    cur = conn.cursor()
    ratios, missing = {}, []
    for f in VAL_RATIOS:
        v = _r(kpi.get(f))
        ratios[f] = v
        if v is None:
            missing.append(f"{f}_not_in_rhp")

    # PE/PB are never written by this engine family. If a caller passes them anyway
    # (an older prompt, a hand-built dict), they are DROPPED rather than stored — a
    # pre-band P/E is not a fact about this IPO no matter who supplies it.
    for f, reason in ENGINE_OWNED.items():
        ratios[f] = None
        missing.append(reason)

    # ofs_pct is issue structure, not an RHP KPI — owned by score_engine/ipo_issue.
    # Left NULL here deliberately rather than half-derived from a different source.
    missing.append("ofs_pct_not_an_rhp_kpi")

    scalars = {k: kpi[k] for k in SCALAR_KPIS if kpi.get(k) is not None}
    inputs_used = {"source": source, "reported_by": "rhp_basis_for_issue_price",
                   "scalars": scalars}
    if doc_id is not None:
        inputs_used["doc_id"] = doc_id

    # CHECK val_null_explained: (pe AND pb) OR missing_inputs NOT NULL.
    # missing is never empty here (ofs_pct line always present), so the CHECK always
    # has something to point at — but assert it rather than trust it.
    if not (ratios["pe"] is not None and ratios["pb"] is not None) and not missing:
        raise ValueError("val_null_explained would be violated: null ratio with empty missing_inputs")

    cur.execute("""INSERT INTO valuation
        (ipo_id, computed_at, engine_version, pe, pb, roe, roce, de, rev_cagr_3y,
         ofs_pct, peer_median_pe, score, score_band, inputs_used, missing_inputs)
        VALUES (%s, now(), %s, %s,%s,%s,%s,%s,%s, NULL, %s, NULL, NULL, %s, %s)
        ON CONFLICT (ipo_id, engine_version, computed_at) DO NOTHING
        RETURNING id""",
        (ipo_id, ENGINE_VERSION, ratios["pe"], ratios["pb"], ratios["roe"],
         ratios["roce"], ratios["de"], ratios["rev_cagr_3y"], ratios["peer_median_pe"],
         json.dumps(inputs_used), sorted(set(missing))))
    row = cur.fetchone()
    if commit: conn.commit()

    # scalar KPIs with no valuation column -> source_facts (change-logged, not duplicated)
    for k, v in scalars.items():
        log_source_fact(conn, ipo_id, k, v, source, commit=commit)

    return dict(valuation_id=(row[0] if row else None),
                written=bool(row),
                missing_inputs=sorted(set(missing)),
                scalars_logged=sorted(scalars.keys()))


def latest(conn, ipo_id, engine_version=ENGINE_VERSION):
    """Read back the newest row of one engine family (how consumers should read)."""
    cur = conn.cursor()
    cur.execute("""SELECT id, pe, pb, roe, roce, de, peer_median_pe, missing_inputs, computed_at
                     FROM valuation WHERE ipo_id=%s AND engine_version=%s
                    ORDER BY computed_at DESC LIMIT 1""", (ipo_id, engine_version))
    return cur.fetchone()


# ============================================================ UNIT NORMALISATION
# The RHP states its own unit ("₹ in million", "₹ in lakhs"). The model is instructed
# to report figures EXACTLY as printed and to label the unit — conversion happens here,
# in one auditable place. This is the fix that made Indo-MIM match IPOMatrix to the
# decimal (million ÷ 10); getting it wrong is a silent 10x error in every stored figure.
TO_CRORE = {
    "crore":    1.0,
    "cr":       1.0,
    "million":  0.1,          # 10 million = 1 crore
    "mn":       0.1,
    "lakh":     0.01,         # 100 lakh = 1 crore
    "lac":      0.01,
    "lakhs":    0.01,
    "thousand": 0.0001,       # 10,000 thousand = 1 crore
    "absolute": 0.0000001,    # 1,00,00,000 rupees = 1 crore
}

def to_crore(value, unit):
    """Convert a printed figure to crore. Returns (value_or_None, note_or_None)."""
    if value is None:
        return None, None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None, "unparseable"
    if unit is None:
        return None, "unit_not_disclosed"
    f = TO_CRORE.get(str(unit).strip().lower())
    if f is None:
        # REFUSE rather than assume crore. An unknown unit label silently treated as
        # crore is exactly the 10x corruption this function exists to prevent.
        return None, f"unknown_unit:{unit}"
    return round(v * f, 4), None


# ============================================================ THE ROUTER
# junk_signals vocabulary — taken from what is ALREADY stored in the DB (inspect_checks
# 08-01 read these 7 distinct values off the existing 376 rows). Not invented: a new
# vocabulary here would split the field and break every consumer of the old rows.
JUNK_SIGNAL_MAP = {
    "auditor_qualified":               "auditor_qualified",
    "sebi_action":                     "sebi_action",
    "criminal_litigation":             "criminal_litigation",
    "related_party_concern":           "related_party_concern",
    "customer_concentration_high":     "customer_concentration_high",
    "contingent_liabilities_material": "contingent_liabilities_material",
    "promoter_pledge_flag":            "promoter_pledge_flag",
}

# The owner's LOCKED junk line: ONLY these are JUNK. auditor_qualified,
# criminal_litigation, related_party_concern, customer_concentration_high,
# contingent_liabilities_material, promoter_pledge_flag are RED FLAGS -> WATCH.
SEVERE_JUNK = {"sebi_action", "going_concern", "fraud", "inflated_figures"}

def _derive_flags(db_fields):
    """(red_flag_count, junk_signals[]) from the model's db_fields block.

    ONLY severe signals go into junk_signals (which is the JUNK line). Every triggered
    signal — severe OR benign — counts toward red_flag_count, so a benign concern is
    recorded as a red flag (WATCH) rather than silently dropped or wrongly escalated."""
    fired = [name for key, name in JUNK_SIGNAL_MAP.items() if db_fields.get(key) is True]
    junk  = [s for s in fired if s in SEVERE_JUNK]
    reds  = list(fired)                         # benign signals are red flags, not junk
    for k in ["numbers_integrity_flag", "working_capital_flag"]:
        if db_fields.get(k) == "watch":
            reds.append(k)
    if db_fields.get("cash_conversion_flag") == "weak":
        reds.append("cash_conversion_weak")
    if db_fields.get("debt_trend") == "rising":
        reds.append("debt_rising")
    if db_fields.get("gcp_high") is True:
        reds.append("gcp_high")
    return len(set(reds)), sorted(set(junk))


def route_extraction(conn, ipo_id, doc_id, data, model, prompt_version, source="rhp", commit=True):
    """Route ONE parsed v2-full extraction into the V2 tables.

    Everything goes through the already-tested writers — this function decides WHERE
    each fact belongs (Rule A: one fact, one home) and normalises units. It does not
    open its own SQL.

      qualitative + db_fields -> rhp_findings   (upsert_rhp_findings)
      structured.financials   -> financial_statements (upsert_financials, unit-normalised)
      structured.kpi + peers  -> valuation v2-rhp-1  (write_rhp_valuation)
      evidenced claims        -> insights        (upsert_insights)

    Returns a report dict — nothing is printed, so the caller decides how loud to be.
    """
    from fill_v2 import upsert_financials, upsert_rhp_findings, upsert_insights

    rep = {"ipo_id": ipo_id, "doc_id": doc_id, "financials": [], "canonical_facts": [], "skipped": [],
           "valuation": None, "insights": 0, "findings": None}
    st = data.get("structured") or {}
    unit = st.get("unit_as_printed")

    # ---- 1. rhp_findings: the whole analysis run, verbatim ----
    dbf = data.get("db_fields") or {}
    red, sigs = _derive_flags(dbf)
    conf_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
    rep["findings"] = upsert_rhp_findings(
        conn, ipo_id, doc_id, data, model, prompt_version,
        red_flag_count=red, junk_signals=sigs,
        confidence=conf_map.get(data.get("confidence")),
        cost_usd=(data.get("_meta") or {}).get("cost_usd"), commit=False)

    # ---- 2. financial_statements: one row per period+basis, unit-normalised ----
    MONEY = [("revenue_from_operations", "revenue"), ("total_income", "total_income"),
             ("ebitda", "ebitda"), ("pat", "pat"), ("net_worth", "net_worth"),
             ("total_debt", "total_debt"), ("total_assets", "total_assets")]
    for row in (st.get("financials") or []):
        period = row.get("period"); basis = row.get("basis")
        if not period or basis not in ("consolidated", "standalone"):
            rep["skipped"].append({"why": "bad period/basis", "period": period, "basis": basis})
            continue
        rec = {}; notes = []
        for src_key, col in MONEY:
            v, note = to_crore(row.get(src_key), unit)
            if v is not None:
                rec[col] = v
            elif note and row.get(src_key) is not None:
                notes.append(f"{src_key}:{note}")
        if not rec:
            rep["skipped"].append({"why": "no convertible figures", "period": period,
                                   "notes": notes})
            continue
        upsert_financials(conn, ipo_id, period, basis, rec, source=source, commit=False)
        rep["financials"].append({"period": period, "basis": basis,
                                  "fields": sorted(rec.keys()), "notes": notes})

    # ---- 2b. canonical scalar facts: only explicitly disclosed, page-cited values ----
    # The model reports figures exactly as printed; this writer remains the single
    # unit-normalisation and storage boundary. Missing/page-less facts are refused.
    for field in ("cash_cr","interest_expense_cr","operating_cash_flow_cr","debt_repayment_cr","capex_cr"):
        fact = (st.get("canonical_facts") or {}).get(field) or {}
        value, page, excerpt = fact.get("value"), fact.get("page"), fact.get("excerpt")
        crore, note = to_crore(value, unit)
        if crore is None or not isinstance(page, int) or not str(excerpt or "").strip():
            if value is not None:
                rep["skipped"].append({"why":"canonical fact lacks convertible value/page/excerpt","field":field,"note":note})
            continue
        fact_source=f"{source}:doc={doc_id}:page={page}"
        log_source_fact(conn, ipo_id, field, crore, fact_source, doc_id=doc_id, commit=False)
        rep["canonical_facts"].append({"field":field,"value_cr":crore,"page":page,"excerpt":str(excerpt)[:250]})

    # ---- 3. valuation v2-rhp-1: reported ratios (unit-free, band-independent) ----
    kpi = st.get("kpi") or {}
    peers = st.get("peer_analysis") or {}
    peer_rows = peers.get("peers") or []

    # PEER MEDIAN GUARD: store every peer row (the data is real and worth keeping), but
    # only promote a MEDIAN into valuation when there are enough peers for the word to
    # mean anything. Below the threshold the median is suppressed and the reason is
    # recorded — a null we can explain beats a number we can't defend.
    median_pe = peers.get("peer_median_pe")
    median_note = None
    if median_pe is not None and len(peer_rows) < MIN_PEERS_FOR_MEDIAN:
        median_note = f"peer_median_suppressed_only_{len(peer_rows)}_peers"
        median_pe = None
    if peer_rows:
        # every peer row preserved verbatim, median or not
        log_source_fact(conn, ipo_id, "peer_analysis", json.dumps(peer_rows), source, commit=False)
        if peers.get("as_of_date"):
            log_source_fact(conn, ipo_id, "peer_analysis_as_of", peers["as_of_date"], source, commit=False)
        rep["peers_stored"] = len(peer_rows)
        rep["peer_median_note"] = median_note

    if kpi or peers:
        rep["valuation"] = write_rhp_valuation(conn, ipo_id, dict(
            # RoNW is the RHP's name for return on net worth; prefer it, fall back to roe
            roe=kpi.get("ronw_pct") if kpi.get("ronw_pct") is not None else kpi.get("roe_pct"),
            roce=kpi.get("roce_pct"),
            peer_median_pe=median_pe,
            ronw=kpi.get("ronw_pct"), nav_per_share=kpi.get("nav_per_share"),
            eps_pre=kpi.get("eps_basic_pre"), eps_post=kpi.get("eps_post"),
            ebitda_margin_pct=kpi.get("ebitda_margin_pct"),
            pat_margin_pct=kpi.get("pat_margin_pct"),
        ), doc_id=doc_id, source=source, commit=False)
        if median_note:
            rep["valuation"]["missing_inputs"] = sorted(
                set(rep["valuation"]["missing_inputs"]) | {median_note})

    # ---- 4. insights: only claims that carry page + excerpt (CHECK ins_evidence_required) ----
    items = []
    def add(cat, direction, statement, block):
        exc = (block or {}).get("excerpt"); pg = (block or {}).get("page")
        if statement and exc:
            items.append(dict(category=cat, direction=direction, statement=statement,
                              excerpt=str(exc)[:500], page_number=pg))
    if kpi:
        bits = [f"{k.replace('_pct','')} {kpi[k]}" for k in
                ["ronw_pct", "roce_pct", "nav_per_share", "eps_basic_pre",
                 "ebitda_margin_pct", "pat_margin_pct"]
                if kpi.get(k) is not None]
        if bits:
            add("valuation", "neutral", "Issuer-reported KPIs: " + ", ".join(bits), kpi)
    if peers.get("peers"):
        names = ", ".join(str(p.get("name")) for p in peers["peers"][:5] if p.get("name"))
        if names:
            add("valuation", "neutral", f"Listed peers disclosed: {names}", peers)
    band = st.get("issue_price_band") or {}
    if band.get("floor") or band.get("cap"):
        add("structure", "neutral", f"Price band {band.get('floor')}–{band.get('cap')}", band)
    aud = data.get("auditor") or {}
    if aud.get("qualified") is True:
        add("governance", "negative", "Auditor has reported qualifications/reservations", aud)
    sebi = data.get("sebi_regulatory") or {}
    if sebi.get("any_action") is True:
        add("governance", "negative", "SEBI or exchange action disclosed", sebi)
    if items:
        n, sup, run_id = upsert_insights(conn, ipo_id, items, model=model,
                                         prompt_version=prompt_version, doc_id=doc_id,
                                         source_type="RHP", commit=False)
        rep["insights"] = n; rep["insights_superseded"] = sup; rep["run_id"] = run_id
    if commit:
        conn.commit()
    return rep


FILE_BUILD = "rhp_writer 2026-08-01c — PE/PB moved to score_engine + peer-median>=3 guard"

# ------------------------------------------------------------------ selftest
def selftest():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    ok = True
    print(f"  [build] {FILE_BUILD}")
    print(f"  [build] router present: {'route_extraction' in globals()}")
    def chk(m, c):
        nonlocal ok; ok = ok and c; print(f"  [{'PASS' if c else 'FAIL'}] {m}")

    from fill_ipo import upsert_ipo, _norm
    TEST_ISIN = "INE000RHPW01"; TEST_NORM = _norm("Zzz Rhp Writer Selftest Ltd")
    for t in ["source_facts", "valuation"]:
        cur.execute(f"DELETE FROM {t} WHERE ipo_id IN (SELECT id FROM ipo WHERE isin=%s)", (TEST_ISIN,))
    cur.execute("DELETE FROM ipo WHERE isin=%s OR name_norm=%s", (TEST_ISIN, TEST_NORM))
    conn.commit()
    iid, _ = upsert_ipo(conn, dict(isin=TEST_ISIN, name_display="Zzz Rhp Writer Selftest Ltd",
                                   name_norm=TEST_NORM, issue_size_cr=500,
                                   listing_date="2025-06-01"), "test")
    chk("test IPO spine row created", iid is not None)

    # 1. full KPI set writes cleanly — note NO pe/pb: they are not RHP facts
    res = write_rhp_valuation(conn, iid, dict(roe=22.0, roce=25.5,
                                              de=0.31, peer_median_pe=41.0,
                                              ronw=21.4, nav_per_share=88.2, eps_post=12.1),
                              doc_id=None, source="rhp")
    chk("v2-rhp-1 row written", res["written"] is True)
    r = latest(conn, iid)
    chk("roe stored (22.00)", float(r[3]) == 22.00)
    chk("roce stored (25.50)", float(r[4]) == 25.50)
    chk("peer_median_pe stored (41.00)", float(r[6]) == 41.00)
    chk("scalar KPIs logged to source_facts", set(res["scalars_logged"]) ==
        {"ronw", "nav_per_share", "eps_post"})
    cur.execute("SELECT count(*) FROM source_facts WHERE ipo_id=%s AND field='nav_per_share'", (iid,))
    chk("source_facts has nav_per_share (no valuation column for it)", cur.fetchone()[0] == 1)

    # 1b. PE/PB ARE NOT RHP FACTS — dropped even when a caller supplies them, and the
    #     reason is recorded. Pre-band RHPs cannot know these (Offer Price = "[●] x FV").
    resx = write_rhp_valuation(conn, iid, dict(roe=20.0, pe=34.1, pb=5.2))
    rx = latest(conn, iid)
    chk("pe NOT stored by the RHP engine even when passed in", rx[1] is None)
    chk("pb NOT stored by the RHP engine even when passed in", rx[2] is None)
    chk("pe explained as engine-owned", "pe_derived_from_band_by_score_engine" in resx["missing_inputs"])
    chk("pb explained as engine-owned", "pb_derived_from_band_by_score_engine" in resx["missing_inputs"])
    chk("roe still stored alongside (20.00)", float(rx[3]) == 20.00)

    # 2. NO CLOBBER — a v2-score-1 row for the same IPO must survive untouched.
    #    score_engine is now the SOLE owner of pe/pb, so this matters more, not less.
    cur.execute("""INSERT INTO valuation (ipo_id, computed_at, engine_version, pe, pb,
                                          score, score_band, missing_inputs)
                   VALUES (%s, now(), 'v2-score-1', 11.11, 2.22, 3.0, 'STRONG', ARRAY[]::text[])""",
                (iid,))
    conn.commit()
    write_rhp_valuation(conn, iid, dict(roe=1.0))
    cur.execute("""SELECT pe, pb, score_band FROM valuation
                    WHERE ipo_id=%s AND engine_version='v2-score-1'""", (iid,))
    s = cur.fetchone()
    chk("v2-score-1 pe NOT clobbered by RHP write (11.11)", float(s[0]) == 11.11)
    chk("v2-score-1 score_band intact (STRONG)", s[2] == "STRONG")
    cur.execute("""SELECT count(DISTINCT engine_version) FROM valuation WHERE ipo_id=%s""", (iid,))
    chk("both engine families coexist on one IPO", cur.fetchone()[0] == 2)

    # 3. honest absence — missing ratios are NAMED, never silently NULL
    res2 = write_rhp_valuation(conn, iid, dict(roe=15.0))
    chk("missing roce named in missing_inputs", "roce_not_in_rhp" in res2["missing_inputs"])
    r3 = latest(conn, iid)
    chk("val_null_explained satisfied (row accepted with null pe/pb)", r3 is not None)
    chk("missing_inputs persisted non-empty", r3[7] is not None and len(r3[7]) > 0)

    # 4. score/score_band stay NULL — this row reports, it does not judge
    cur.execute("""SELECT count(*) FROM valuation
                    WHERE ipo_id=%s AND engine_version=%s
                      AND (score IS NOT NULL OR score_band IS NOT NULL)""",
                (iid, ENGINE_VERSION))
    chk("v2-rhp-1 rows carry NO score/score_band (reporting, not scoring)", cur.fetchone()[0] == 0)

    # 5. overflow guard (score_engine hit a real NumericValueOutOfRange here)
    res5 = write_rhp_valuation(conn, iid, dict(roe=12345678.0))
    chk("absurd ratio capped, write survives", res5["written"] is True)
    r5 = latest(conn, iid)
    chk("capped to 9999.99", float(r5[3]) == 9999.99)

    # 6. garbage input is dropped as missing, not crashed on
    res6 = write_rhp_valuation(conn, iid, dict(roe="not-a-number", roce=None))
    chk("unparseable ratio -> named missing, no exception", "roe_not_in_rhp" in res6["missing_inputs"])

    # ---------------------------------------------------------------- UNIT NORMALISATION
    chk("crore passes through", to_crore(4192.98, "crore")[0] == 4192.98)
    chk("million -> crore (÷10): the Indo-MIM fix", to_crore(41929.8, "million")[0] == 4192.98)
    chk("lakh -> crore (÷100)", to_crore(419298.0, "lakh")[0] == 4192.98)
    chk("thousand -> crore (÷10000)", to_crore(41929800.0, "thousand")[0] == 4192.98)
    chk("absolute rupees -> crore", to_crore(41929800000.0, "absolute")[0] == 4192.98)
    chk("UNKNOWN unit REFUSED, not assumed crore", to_crore(100.0, "bushels")[0] is None)
    chk("unknown unit explains itself", "unknown_unit" in (to_crore(100.0, "bushels")[1] or ""))
    chk("missing unit REFUSED", to_crore(100.0, None)[0] is None)
    chk("None value stays None", to_crore(None, "million")[0] is None)

    # ---------------------------------------------------------------- END-TO-END ROUTER
    from fill_v2 import upsert_document
    doc_id = upsert_document(conn, iid, "rhp", content_bytes=b"fixture-rhp-bytes",
                             url="https://example.test/rhp.pdf", page_count=495)
    fixture = {
      "verdict": "clean", "one_line": "Solid.", "confidence": "high",
      "auditor": {"qualified": True, "detail": "Qualification on inventory valuation",
                  "excerpt": "The auditor has reported a qualification", "page": 200},
      "sebi_regulatory": {"any_action": False, "detail": "none disclosed"},
      "db_fields": {"auditor_qualified": True, "sebi_action": False,
                    "criminal_litigation": False, "customer_concentration_high": True,
                    "numbers_integrity_flag": "watch", "cash_conversion_flag": "weak",
                    "debt_trend": "rising", "quality_gate": "watch"},
      "_meta": {"cost_usd": 0.1234},
      "structured": {
        "unit_as_printed": "million", "currency": "INR",
        "canonical_facts": {
          "cash_cr": {"value": 800.0, "page": 102, "excerpt": "Cash and cash equivalents 800.0"},
          "interest_expense_cr": {"value": 100.0, "page": 101, "excerpt": "Finance costs 100.0"},
          "operating_cash_flow_cr": {"value": 900.0, "page": 103, "excerpt": "Net cash from operating activities 900.0"},
          "debt_repayment_cr": {"value": 500.0, "page": 80, "excerpt": "Repayment of borrowings 500.0"},
          "capex_cr": {"value": 300.0, "page": 80, "excerpt": "Capital expenditure 300.0"}},
        "financials": [
          {"period": "31-Mar-26", "basis": "consolidated",
           "revenue_from_operations": 41929.8, "total_income": 43207.0,
           "pat": 5123.3, "net_worth": 22000.0, "total_debt": 6800.0,
           "page": 101, "excerpt": "Revenue from operations 41,929.8"},
          {"period": "31-Mar-25", "basis": "consolidated",
           "revenue_from_operations": 38014.4, "total_income": 39125.5,
           "pat": 4801.0, "page": 101, "excerpt": "Revenue from operations 38,014.4"},
          {"period": "31-Mar-24", "basis": "BOGUS",       # must be skipped, not guessed
           "revenue_from_operations": 32041.1, "page": 101, "excerpt": "x"}
        ],
        "kpi": {"ronw_pct": 22.04, "roce_pct": 25.50,
                "nav_per_share": 88.20, "eps_post": 12.10, "ebitda_margin_pct": 18.40,
                "page": 138, "excerpt": "Return on Net Worth 22.04%"},
        "peer_analysis": {"peers": [{"name": "Peer A", "pe": 41.0},
                                    {"name": "Peer B", "pe": 38.5}],
                          "peer_median_pe": 39.75, "page": 137,
                          "excerpt": "Peer A P/E 41.00 Peer B P/E 38.50"},
        "issue_price_band": {"floor": 420, "cap": 443, "page": 1,
                             "excerpt": "Price Band 420 to 443 per Equity Share"}
      }}
    rep = route_extraction(conn, iid, doc_id, fixture, "claude-sonnet-4-6", "v2-full")

    chk("router wrote rhp_findings", rep["findings"][1] in ("inserted", "updated"))
    cur.execute("SELECT red_flag_count, junk_signals FROM rhp_findings WHERE doc_id=%s", (doc_id,))
    rf = cur.fetchone()
    chk("junk_signals use the EXISTING DB vocabulary",
        set(rf[1]) == {"auditor_qualified", "customer_concentration_high"})
    chk("red_flag_count counts flags beyond junk signals (>2)", rf[0] > 2)

    chk("2 valid financial periods routed", len(rep["financials"]) == 2)
    chk("bad basis SKIPPED, not guessed", any(s.get("basis") == "BOGUS" for s in rep["skipped"]))
    cur.execute("""SELECT revenue, total_income, pat FROM financial_statements
                    WHERE ipo_id=%s AND period='31-Mar-26'""", (iid,))
    f = cur.fetchone()
    chk("revenue million->crore (41929.8 -> 4192.98)", float(f[0]) == 4192.98)
    chk("total_income million->crore (43207.0 -> 4320.70)", float(f[1]) == 4320.70)
    chk("pat million->crore (5123.3 -> 512.33)", float(f[2]) == 512.33)
    cur.execute("SELECT field,value,source FROM source_facts WHERE ipo_id=%s AND field='cash_cr' ORDER BY fetched_at DESC LIMIT 1",(iid,))
    cf=cur.fetchone();chk("canonical cash fact unit-normalised with document/page provenance",cf[0]=="cash_cr" and float(cf[1])==80.0 and f"doc={doc_id}:page=102" in cf[2])

    v = latest(conn, iid)
    chk("valuation v2-rhp-1 got RoNW as roe (22.04)", float(v[3]) == 22.04)
    chk("valuation roce (25.50)", float(v[4]) == 25.50)
    chk("router does NOT write pe (score_engine owns it)", v[1] is None)
    chk("router does NOT write pb (score_engine owns it)", v[2] is None)

    # PEER MEDIAN GUARD — 2 peers is not a median
    chk("peer rows STORED even when median suppressed", rep.get("peers_stored") == 2)
    chk("median SUPPRESSED below 3 peers", v[6] is None)
    chk("suppression reason recorded", "only_2_peers" in (rep.get("peer_median_note") or ""))
    cur.execute("SELECT value FROM source_facts WHERE ipo_id=%s AND field='peer_analysis'", (iid,))
    pf = cur.fetchone()
    chk("peer rows preserved verbatim in source_facts", pf is not None and "Peer B" in pf[0])

    # 3 peers -> the median is allowed through
    fx3 = json.loads(json.dumps(fixture))
    fx3["structured"]["peer_analysis"]["peers"].append({"name": "Peer C", "pe": 44.2})
    fx3["structured"]["peer_analysis"]["peer_median_pe"] = 41.0
    rep3 = route_extraction(conn, iid, doc_id, fx3, "claude-sonnet-4-6", "v2-full")
    v3 = latest(conn, iid)
    chk("median ALLOWED at 3 peers (41.00)", v3[6] is not None and float(v3[6]) == 41.00)
    chk("3 peer rows stored", rep3.get("peers_stored") == 3)

    chk("insights written with evidence", rep["insights"] >= 3)
    cur.execute("""SELECT count(*) FROM insights
                    WHERE ipo_id=%s AND is_current AND (excerpt IS NULL OR doc_id IS NULL)""", (iid,))
    chk("every RHP insight carries doc_id AND excerpt", cur.fetchone()[0] == 0)
    cur.execute("SELECT count(*) FROM insights WHERE ipo_id=%s AND category='valuation' AND is_current", (iid,))
    chk("KPI + peer claims landed under category 'valuation'", cur.fetchone()[0] == 2)

    # re-run must not duplicate anything
    rep2 = route_extraction(conn, iid, doc_id, fixture, "claude-sonnet-4-6", "v2-full")
    chk("re-run UPDATES rhp_findings (no dup)", rep2["findings"][1] == "updated")
    cur.execute("SELECT count(*) FROM rhp_findings WHERE doc_id=%s", (doc_id,))
    chk("still 1 rhp_findings row", cur.fetchone()[0] == 1)
    cur.execute("SELECT count(*) FROM financial_statements WHERE ipo_id=%s", (iid,))
    chk("still 2 financial rows after re-run", cur.fetchone()[0] == 2)
    cur.execute("SELECT count(*) FROM insights WHERE ipo_id=%s AND is_current", (iid,))
    chk("insights superseded not duplicated on re-run", cur.fetchone()[0] == rep2["insights"])

    # cleanup
    for t in ["rhp_findings", "insights", "financial_statements", "documents"]:
        cur.execute(f"DELETE FROM {t} WHERE ipo_id=%s", (iid,))
    cur.execute("DELETE FROM valuation WHERE ipo_id=%s", (iid,))
    cur.execute("DELETE FROM source_facts WHERE ipo_id=%s", (iid,))
    cur.execute("DELETE FROM ipo WHERE id=%s", (iid,))
    conn.commit()
    print(f"\n{'ALL PASS ✓' if ok else 'SOME FAILED ✗'}")
    conn.close(); return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: sys.exit(0 if selftest() else 1)
    print("import write_rhp_valuation(conn, ipo_id, kpi) — or run --selftest")
