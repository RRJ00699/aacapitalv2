#!/usr/bin/env python3
"""
warm_kv.py — the last DB step: push V2 payloads into Cloudflare KV.

WHY
  Every page load would otherwise query Neon directly, waking the DB on user traffic.
  lib/kv-cache.ts already implements cached()/cachedWithStale(); the missing piece is
  somebody WRITING the keys twice a day. That is this file. Ported into the monorepo
  from the standalone pipeline (feat/kv-warming) and extended with ipo:<id>:details.

HOW
  POSTs to the app's own /api/admin/kv-put (X-AAC-Key == ADMIN_JOB_KEY). No Cloudflare
  credentials here; the app keeps sole ownership of its KV binding.

THE STALE TWIN
  cachedWithStale() reads <key> then falls back to <key>:stale, so a KV expiry never
  wakes Neon during market hours. We write BOTH: live at 12h (pipeline runs 2x/day),
  twin at 7d. Writing only the live key leaves the fallback useless.

  python warm_kv.py --ids 5,42,85 --dry-run
  python warm_kv.py --ids 85 --print          # dump one details payload, no network/DB write
  python warm_kv.py --limit 10 --write
"""
import os, sys, io, json, argparse, datetime as dt, math
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2
import urllib.request

FILE_BUILD = "warm_kv 2026-08-03 — ipo:<id>:details, two-tier evidence, completeness, honest gaps"
APP_URL = os.environ.get("AAC_APP_URL", "https://aacapitalprivatelimited.com")
LIVE_TTL = 43200      # 12h — matches lib/kv-cache.ts DEFAULT_TTL, pipeline runs 2x/day
STALE_TTL = 604800    # 7d  — matches STALE_TTL in lib/kv-cache.ts
RETAIL_CAP = 200000   # SEBI retail application ceiling (Rs); above this = S-HNI
SHNI_CAP = 1000000    # Rs 10L; above this = B-HNI


def _f(v):
    if v is None: return None
    try: return float(v)
    except (TypeError, ValueError): return None

def _d(v):
    return str(v) if isinstance(v, (dt.date, dt.datetime)) else v


# ─────────────────────────────────────────────────────────── derived (labelled)
def _issue_derived(issue):
    """Shares from Rs, sale type, market cap — all DERIVED, flagged so the UI labels them."""
    price = issue.get("issue_price") or issue.get("band_hi")
    out = {"_derived": True}
    if price:
        for k_cr, k_sh in [("fresh_cr", "fresh_shares"), ("ofs_cr", "ofs_shares"),
                           ("issue_size_cr", "total_shares")]:
            cr = issue.get(k_cr)
            out[k_sh] = round(cr * 1e7 / price) if cr else None
    fresh, ofs = issue.get("fresh_cr"), issue.get("ofs_cr")
    out["sale_type"] = ("fresh only" if fresh and not ofs else "OFS only" if ofs and not fresh
                        else "fresh + OFS" if fresh and ofs else None)
    return out

def _lot_tiers(lot_size, band_hi):
    """Retail / S-HNI / B-HNI lot bands — DERIVED from lot_size × upper band vs the SEBI
    Rs 2L / Rs 10L ceilings. Rule is carried in the payload so the UI can show it."""
    if not lot_size or not band_hi:
        return None
    per_lot = lot_size * band_hi
    r_max = int(RETAIL_CAP // per_lot)
    s_max = int(SHNI_CAP // per_lot)
    if r_max < 1:
        return None
    tiers = [{"tier": "Retail", "min_lots": 1, "max_lots": r_max,
              "min_amount": round(per_lot), "max_amount": round(r_max * per_lot)}]
    if s_max > r_max:
        tiers.append({"tier": "S-HNI", "min_lots": r_max + 1, "max_lots": s_max,
                      "min_amount": round((r_max + 1) * per_lot), "max_amount": round(s_max * per_lot)})
        tiers.append({"tier": "B-HNI", "min_lots": s_max + 1, "max_lots": None,
                      "min_amount": round((s_max + 1) * per_lot), "max_amount": None})
    return {"_derived": True, "rule": "lots × (lot_size × upper band) vs Rs 2,00,000 (retail) and Rs 10,00,000 (S-HNI)",
            "per_lot_amount": round(per_lot), "tiers": tiers}


# ─────────────────────────────────────────────────────────── evidence (two tiers)
_EV_BLOCKS = [("sebi_regulatory", "SEBI / regulatory"), ("auditor", "Auditor"),
              ("litigation", "Litigation"), ("numbers_integrity", "Numbers integrity"),
              ("cashing_out", "Cashing out / OFS"), ("related_party", "Related party"),
              ("promoter_pledge", "Promoter pledge"), ("use_of_proceeds", "Use of proceeds")]

def _evidence(conn, ipo_id):
    """TIER 2 'cited' (page + verbatim excerpt, from insights) when available, else
    TIER 1 'narrative' (rhp_findings analysis, page refs live in prose, NOT a citation),
    else TIER 0 'none' (RHP not yet extracted — a pending state, not an error).
    The tier is written into the payload so the component never has to infer it."""
    cur = conn.cursor()
    cur.execute("""SELECT prompt_version, findings FROM rhp_findings WHERE ipo_id=%s
                   ORDER BY (prompt_version='v2-full') DESC, analyzed_at DESC LIMIT 1""", (ipo_id,))
    r = cur.fetchone()
    if not r:
        return {"tier": "none", "reason": "RHP not yet extracted"}
    pv, findings = r
    f = findings if isinstance(findings, dict) else json.loads(findings)

    # tier-2 citations: only insights rows that satisfy the same evidence bar the CHECK enforces
    cur.execute("""SELECT category, statement, direction, page_number, excerpt FROM insights
                   WHERE ipo_id=%s AND is_current AND source_type='RHP'
                     AND page_number IS NOT NULL AND excerpt IS NOT NULL ORDER BY category""",
                (ipo_id,))
    cited = [dict(zip(["category", "statement", "direction", "page", "excerpt"], x))
             for x in cur.fetchall()]

    blocks = []
    for key, label in _EV_BLOCKS:
        b = f.get(key)
        if isinstance(b, dict):
            text = b.get("detail") or b.get("watch_note") or b.get("assessment")
            if text:
                blocks.append({"key": key, "label": label, "page": b.get("page"), "text": text})
    risks = f.get("top_3_material_risks")
    if isinstance(risks, list) and risks:
        blocks.append({"key": "top_3_material_risks", "label": "Top material risks", "items": risks})

    return {
        "tier": "cited" if cited else "narrative",
        "prompt_version": pv,
        "verdict": f.get("verdict"), "one_line": f.get("one_line"),
        "trust_summary": f.get("trust_summary"),
        # TIER 1 — AI analysis. Page numbers may appear INSIDE the prose but this is NOT a
        # verified citation; the UI must render it visibly distinct from cited_excerpts.
        "blocks": blocks,
        # TIER 2 — verified page-cited excerpts. Empty for tier-1 IPOs.
        "cited_excerpts": cited,
    }


# ─────────────────────────────────────────────────────────── the details payload
# Known gaps rendered as honest "not available — <reason>", never a silent omission.
GAPS = {
    "reservation_split": "not captured — noOfSharesOffered discarded in parse_bid_details (fix pending)",
    "shareholding_pre_post": "not extracted — RHP re-extract pending (v2-full block)",
    "objects_with_amounts": "not extracted — RHP re-extract pending (text is sent to Sonnet, not in structured output)",
    "selling_shareholders": "not extracted — RHP re-extract pending",
    "promoters": "not extracted — RHP re-extract pending",
    "anchor_investor_names": "no primary source — IPOMatrix fallback only",
    "reserves": "not stored in financial_statements",
    "refund_credit_dates": "not captured",
    "employee_discount_quota": "not captured",
    "sbi_notes": "248 PDFs downloaded, Sonnet extraction not built",
}


def build_details(conn, ipo_id):
    """ipo:<id>:details — everything the Complete Details screen renders, KV-first, from
    V2 tables only. Neon is touched here (the pipeline), never by the route."""
    cur = conn.cursor()
    cur.execute("""SELECT id, isin, symbol, name_display, sector, industry, listing_date,
                          status, is_mainboard, lock30, lock90 FROM ipo WHERE id=%s""", (ipo_id,))
    r = cur.fetchone()
    if not r:
        return None
    out = {"id": r[0], "isin": r[1], "symbol": r[2], "name": r[3], "sector": r[4],
           "industry": r[5], "listing_date": _d(r[6]), "status": r[7], "is_mainboard": r[8]}
    lock30, lock90 = r[9], r[10]

    cur.execute("""SELECT open_date, close_date, allotment_date, band_lo, band_hi, issue_price,
                          issue_size_cr, fresh_cr, ofs_cr, lot_size, face_value, registrar, brlm_count
                     FROM ipo_issue WHERE ipo_id=%s""", (ipo_id,))
    r = cur.fetchone()
    if r:
        ik = ["open_date", "close_date", "allotment_date", "band_lo", "band_hi", "issue_price",
              "issue_size_cr", "fresh_cr", "ofs_cr", "lot_size", "face_value", "registrar", "brlm_count"]
        issue = {k: (_d(v) if k.endswith("date") else v if k == "registrar" else _f(v))
                 for k, v in zip(ik, r)}
        out["issue"] = issue
        out["issue_derived"] = _issue_derived(issue)
        out["lot_tiers"] = _lot_tiers(issue.get("lot_size"), issue.get("band_hi"))

    cur.execute("""SELECT qib_x, nii_x, bnii_x, snii_x, retail_x, total_x, mf_shares_bid,
                          anchor_amount_cr, anchor_count FROM subscription_snapshots
                    WHERE ipo_id=%s ORDER BY is_final DESC NULLS LAST, captured_at DESC LIMIT 1""",
                (ipo_id,))
    r = cur.fetchone()
    if r:
        sk = ["qib_x", "nii_x", "bnii_x", "snii_x", "retail_x", "total_x", "mf_shares_bid",
              "anchor_amount_cr", "anchor_count"]
        out["subscription"] = dict(zip(sk, [_f(v) for v in r]))
        out["anchor"] = {"amount_cr": _f(r[7]), "count": _f(r[8]),
                         "lock30": _d(lock30), "lock90": _d(lock90),
                         "names": None, "names_gap": GAPS["anchor_investor_names"]}

    # SCORE row only (v2-rhp-1 carries no score by design and would blank the band)
    cur.execute("""SELECT engine_version, pe, pb, roe, roce, de, rev_cagr_3y, peer_median_pe,
                          score, score_band, missing_inputs, inputs_used FROM valuation
                    WHERE ipo_id=%s AND engine_version LIKE 'v2-score-%%'
                    ORDER BY engine_version DESC, computed_at DESC LIMIT 1""", (ipo_id,))
    r = cur.fetchone()
    if r:
        iu = r[11] or {}
        out["valuation"] = {"engine": r[0], "pe": _f(r[1]), "pb": _f(r[2]), "roe": _f(r[3]),
                            "roce": _f(r[4]), "de": _f(r[5]), "rev_cagr_3y": _f(r[6]),
                            "peer_median_pe": _f(r[7]), "score": _f(r[8]), "band": r[9],
                            "missing_inputs": r[10] or [],
                            "pe_source": iu.get("pe_source"), "pb_source": iu.get("pb_source")}

    # LATEST v2-verdict row — NOT newest-by-date. A stale v1-import (07-25) can otherwise
    # win for an IPO the 08-02 rewrite hasn't reached — the same shadowing class as the
    # valuation v2-score-% filter and the completeness v2-rhp-1 fix.
    cur.execute("""SELECT engine_version, fundamental_verdict, listing_action, reasons, decided_at
                     FROM decisions WHERE ipo_id=%s AND engine_version LIKE 'v2-verdict-%%'
                    ORDER BY engine_version DESC, decided_at DESC LIMIT 1""", (ipo_id,))
    r = cur.fetchone()
    if r:
        reasons = r[3] or []
        # kill_reason: the junk_signals:* entries explain WHY a JUNK verdict fired — needed
        # so a FAVORABLE band next to a JUNK verdict never reads as a broken system.
        kill = [x for x in reasons if isinstance(x, str) and x.startswith("junk_signals:")]
        out["verdict"] = {"engine": r[0], "verdict": r[1], "listing_action": r[2],
                          "reasons": reasons, "kill_reason": kill or None, "at": _d(r[4])}

    cur.execute("""SELECT period, basis, revenue, total_income, ebitda, pat, net_worth,
                          total_debt, total_assets FROM financial_statements WHERE ipo_id=%s
                    ORDER BY period DESC LIMIT 6""", (ipo_id,))
    fk = ["period", "basis", "revenue", "total_income", "ebitda", "pat", "net_worth",
          "total_debt", "total_assets"]
    out["financials"] = [dict(zip(fk, [x[0], x[1]] + [_f(v) for v in x[2:]])) for x in cur.fetchall()]

    cur.execute("""SELECT listing_open, d1_close, gap_pct, pool, best_close, worst_close
                     FROM listing_outcomes WHERE ipo_id=%s LIMIT 1""", (ipo_id,))
    r = cur.fetchone()
    if r:
        out["listing"] = dict(zip(["listing_open", "d1_close", "gap_pct", "pool", "best_close", "worst_close"],
                                  [_f(r[0]), _f(r[1]), _f(r[2]), r[3], _f(r[4]), _f(r[5])]))

    ev = _evidence(conn, ipo_id)
    out["evidence"] = ev
    out["evidence_tier"] = ev["tier"]              # top-level so the list/screen reads it directly

    # ipo_gmp is PRESENT but stale (no live feed; InvestorGain unbuilt). available=false,
    # but the reason must say STALE, not "no source" — stale data is a different problem,
    # and the 584 historical rows are kept (the backtest set InvestorGain won't backfill).
    cur.execute("SELECT max(date) FROM ipo_gmp")
    gmp_max = cur.fetchone()[0]
    out["gmp"] = {"available": False,
                  "reason": (f"last updated {gmp_max} — no live source (InvestorGain integration pending)"
                             if gmp_max else "no source — InvestorGain integration pending")}
    out["gaps"] = GAPS

    try:
        from completeness import check_completeness
        rep = check_completeness(conn, ipo_id)
        out["completeness"] = {k: rep.get(k) for k in ("stage", "complete", "missing", "pending", "vendor_gaps")}
    except Exception as e:
        out["completeness"] = {"error": f"{type(e).__name__}: {str(e)[:80]}"}

    out["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return out


def build_list(conn, ids):
    """The index payload — one compact row per IPO, incl. evidence_tier for a tier badge.
    Verdict reads the LATEST v2-verdict row (not newest-by-date), same as build_details.
    Re-added on the port: dropping it would leave the index warmer cold and the routes
    reading ipo:list:v2 stale."""
    cur = conn.cursor()
    cur.execute("""
        SELECT i.id, i.name_display, i.symbol, i.listing_date, i.sector,
               ii.band_lo, ii.band_hi, ii.issue_size_cr,
               v.score, v.score_band, d.fundamental_verdict, lo.gap_pct, lo.pool,
               CASE WHEN ci.x IS NOT NULL THEN 'cited'
                    WHEN rf.x IS NOT NULL THEN 'narrative' ELSE 'none' END AS evidence_tier
          FROM ipo i
          LEFT JOIN ipo_issue ii ON ii.ipo_id = i.id
          LEFT JOIN listing_outcomes lo ON lo.ipo_id = i.id
          LEFT JOIN LATERAL (SELECT score, score_band FROM valuation
                              WHERE ipo_id=i.id AND engine_version LIKE 'v2-score-%%'
                              ORDER BY engine_version DESC, computed_at DESC LIMIT 1) v ON TRUE
          LEFT JOIN LATERAL (SELECT fundamental_verdict FROM decisions
                              WHERE ipo_id=i.id AND engine_version LIKE 'v2-verdict-%%'
                              ORDER BY engine_version DESC, decided_at DESC LIMIT 1) d ON TRUE
          LEFT JOIN LATERAL (SELECT 1 x FROM insights WHERE ipo_id=i.id AND source_type='RHP'
                              AND page_number IS NOT NULL AND excerpt IS NOT NULL LIMIT 1) ci ON TRUE
          LEFT JOIN LATERAL (SELECT 1 x FROM rhp_findings WHERE ipo_id=i.id LIMIT 1) rf ON TRUE
         WHERE i.id = ANY(%s)
         ORDER BY i.listing_date DESC NULLS FIRST""", (ids,))
    keys = ["id", "name", "symbol", "listing_date", "sector", "band_lo", "band_hi",
            "issue_size_cr", "score", "band", "verdict", "gap_pct", "pool", "evidence_tier"]
    rows = []
    for x in cur.fetchall():
        row = dict(zip(keys, x))
        row["listing_date"] = _d(row["listing_date"])
        for k in ("band_lo", "band_hi", "issue_size_cr", "score", "gap_pct"):
            row[k] = _f(row[k])
        rows.append(row)
    return {"rows": rows, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat()}


# ─────────────────────────────────────────────────────────── KV write
def kv_put(key, payload, ttl, job_key, dry):
    if dry:
        print(f"      [dry] {key:24} {len(payload):>7} bytes ttl={ttl}")
        return True
    req = urllib.request.Request(f"{APP_URL}/api/admin/kv-put",
        data=json.dumps({"key": key, "payload": payload, "ttl": ttl}).encode(),
        headers={"content-type": "application/json", "x-aac-key": job_key}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read().decode())
        if not body.get("ok"):
            print(f"      ! {key}: {body.get('reason')}"); return False
        print(f"      {key:24} {len(payload):>7} bytes ttl={ttl}"); return True
    except Exception as e:
        print(f"      ! {key}: {type(e).__name__}: {str(e)[:90]}"); return False

def put_both(key, obj, job_key, dry):
    payload = json.dumps(obj, separators=(",", ":"), default=str)
    a = kv_put(key, payload, LIVE_TTL, job_key, dry)
    b = kv_put(f"{key}:stale", payload, STALE_TTL, job_key, dry)
    return a and b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids"); ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--all", action="store_true",
                    help="warm EVERY in-scope IPO (not the active window) — the cron default")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--write", action="store_true")
    ap.add_argument("--print", action="store_true", help="print one details payload as JSON and exit")
    a = ap.parse_args()
    if not (a.dry_run or a.write or a.print):
        sys.exit("choose --dry-run, --write, or --print")

    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    if a.ids:
        ids = [int(x) for x in a.ids.split(",") if x.strip()]
    elif a.all:
        # EVERY in-scope IPO — warming is cheap KV puts (no Kite/Sonnet spend), and the
        # cron works only the active window, so without this most IPOs never get a payload
        # and their Details screen is permanently degraded.
        cur.execute("""SELECT id FROM ipo WHERE COALESCE(is_mainboard,TRUE)=TRUE
                        ORDER BY listing_date DESC NULLS FIRST""")
        ids = [r[0] for r in cur.fetchall()]
    else:
        cur.execute("""SELECT id FROM ipo WHERE COALESCE(is_mainboard,TRUE)=TRUE
                        ORDER BY listing_date DESC NULLS FIRST LIMIT %s""", (a.limit,))
        ids = [r[0] for r in cur.fetchall()]

    if a.print:
        print(json.dumps(build_details(conn, ids[0]), indent=2, default=str)); conn.close(); return

    dry = a.dry_run
    job_key = os.environ.get("ADMIN_JOB_KEY")
    if a.write and not job_key:
        sys.exit("ADMIN_JOB_KEY not set — /api/admin/kv-put returns 401 without it")
    print(f"  [build] {FILE_BUILD}\n  {APP_URL} · {len(ids)} IPOs · mode={'DRY-RUN' if dry else 'WRITE'}\n")
    ok = fail = 0
    for ipo_id in ids:
        d = build_details(conn, ipo_id)
        if not d:
            print(f"  ! id={ipo_id} not found"); fail += 1; continue
        print(f"  == id={ipo_id} {str(d['name'])[:34]}  tier={d['evidence_tier']}")
        ok, fail = (ok + 1, fail) if put_both(f"ipo:{ipo_id}:details", d, job_key, dry) else (ok, fail + 1)
    print("\n  == index (ipo:list:v2)")
    ok, fail = (ok + 1, fail) if put_both("ipo:list:v2", build_list(conn, ids), job_key, dry) else (ok, fail + 1)
    conn.close()
    print(f"\n  done. {ok} warmed · {fail} failed" + ("   (dry — nothing written)" if dry else ""))
    if fail and not dry: sys.exit(1)


if __name__ == "__main__":
    main()
