#!/usr/bin/env python3
"""
drive.py — items 5 + 10: the full-sweep driver and the ntfy push.

ONE RUN, EVERY IPO, EVERY COLUMN. Per IPO, in dependency order:
  1. NSE      -> ipo_issue (band/dates/lot/face/registrar/BRLM) + subscription + anchor shares
  2. RHP      -> documents + financial_statements (both revenue lines) + v2-rhp-1 + insights
  3. DERIVED  -> score_engine (v2-score-2: PE/PB from band + EPS/NAV) then verdict
  4. CHECK    -> completeness across the V2 tables
  5. NOTIFY   -> ntfy per IPO + one run summary

DEPENDENCY ORDER IS NOT COSMETIC. score_engine's PE/PB need the NSE band AND the RHP's
EPS/NAV, so scoring MUST run after both fetchers or it silently falls back to the proxy.
listing_outcomes derives from candles, which need a kite_token — so an IPO without a
token is SKIPPED WITH A REASON rather than half-processed.

IDEMPOTENT AND RESUMABLE BY CONSTRUCTION:
  - every writer is COALESCE-empty-only or keyed ON CONFLICT, so re-running fills gaps
    and never duplicates
  - a manifest records each IPO's last completed step; an interrupted run resumes
  - the RHP step (the only one that costs money) is skipped when rhp_findings already
    holds a v2-full extraction for that document's sha256

COST. NSE and all derived steps are FREE. The RHP step costs ~$0.134/IPO. It runs ONLY
with --rhp, and --max-spend caps the run. Default is a dry run that spends nothing.

  python drive.py --limit 5 --dry-run          # plan only, no writes, no spend
  python drive.py --ids 710,709 --write        # NSE + derived + check (FREE)
  python drive.py --ids 710 --write --rhp --max-spend 0.50
"""
import os, sys, io, json, time, argparse, urllib.request, datetime as dt
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

FILE_BUILD = "drive 2026-08-01c — quiet ntfy + stage-aware pending"
MANIFEST = "drive_manifest.json"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "aacapital-access")
RHP_COST_EST = 0.134          # measured on Indo-MIM 08-01 (21282 in / 4701 out)


# ---------------------------------------------------------------- manifest
def load_manifest():
    if os.path.exists(MANIFEST):
        try: return json.load(open(MANIFEST, encoding="utf-8"))
        except Exception: pass
    return {}


def save_manifest(m):
    json.dump(m, open(MANIFEST, "w", encoding="utf-8"), indent=2, default=str)


# ---------------------------------------------------------------- ntfy
def ntfy(msg, title=None, topic=None, enabled=True):
    """Best-effort push. A notification failure must NEVER fail the run."""
    if not enabled:
        print(f"     [ntfy suppressed] {msg}")
        return False
    topic = topic or NTFY_TOPIC
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}",
                                     data=msg.encode("utf-8"), method="POST")
        if title:
            req.add_header("Title", title)
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"     [ntfy failed, ignored] {type(e).__name__}: {str(e)[:80]}")
        return False


# ---------------------------------------------------------------- steps
def step_nse(conn, ipo_id, symbol, session, write):
    """NSE issue details + subscription. FREE."""
    if not symbol:
        return {"step": "nse", "status": "skipped", "why": "no symbol on the spine"}
    import nse_fetch
    payload = nse_fetch.fetch_one(session, symbol.upper())
    issue, extras, notes = nse_fetch.parse_issue_info(payload)
    subs = nse_fetch.parse_bid_details(payload)
    if not write:
        return {"step": "nse", "status": "dry", "issue_fields": len(issue),
                "subs_fields": len(subs)}
    rep = nse_fetch.apply_to_db(conn, ipo_id, payload)
    return {"step": "nse", "status": "ok", "issue_fields": len(rep["issue_fields"]),
            "subs": rep["subs_action"], "diffs": len(rep["subs_diff"])}


def rhp_already_done(conn, doc_id):
    """The ledger document/model/prompt tuple is the paid-call idempotency key."""
    cur = conn.cursor()
    cur.execute("""SELECT 1 FROM rhp_findings
                    WHERE doc_id=%s AND model=%s AND prompt_version=%s LIMIT 1""",
                (doc_id, "claude-sonnet-4-6", "v2-full"))
    return cur.fetchone() is not None


def find_local_rhp(ipo_id, name, rhp_dir="rhps"):
    """Locate a local RHP folder for this IPO. Returns path or None.

    Matching is by an EXPLICIT map file only (rhp_map.json: {"<ipo_id>": "<folder>"}).
    Folder slugs are filenames, not identifiers — inferring identity from them is the
    fuzzy matching the ISIN spine exists to prevent."""
    mp = "rhp_map.json"
    if not os.path.exists(mp):
        return None
    try:
        m = json.load(open(mp, encoding="utf-8"))
    except Exception:
        return None
    folder = m.get(str(ipo_id))
    if not folder:
        return None
    for cand in (os.path.join(rhp_dir, folder, "rhp.pdf"),):
        if os.path.exists(cand):
            return cand
    import glob
    hits = glob.glob(os.path.join(rhp_dir, folder, "*.pdf"))
    return hits[0] if hits else None


def resolve_rhp(conn, ipo_id, name=None, rhp_dir="rhps", ignore_local=False):
    """Resolve only the current verified contract-v1 ledger row and exact object key.

    ``ignore_local`` remains accepted for CLI compatibility but contract-v1 extraction
    never consults local filenames or ``documents.url``.
    """
    import r2, tempfile, hashlib
    cur = conn.cursor()
    cur.execute("""SELECT id, object_key, sha256, byte_size, content_type,
                          object_contract_version
                     FROM documents
                    WHERE ipo_id=%s AND doc_type='rhp'
                      AND object_key IS NOT NULL AND byte_size IS NOT NULL
                      AND content_type='application/pdf'
                      AND object_contract_version='1'
                    ORDER BY fetched_at DESC, id DESC LIMIT 1""", (ipo_id,))
    row = cur.fetchone()
    if not row:
        return None, "missing_object_key", None, None
    doc_id, object_key, sha, byte_size, content_type, contract_version = row
    if content_type != "application/pdf" or str(contract_version) != "1":
        raise ValueError("document ledger contract mismatch")
    content = r2.get_document(object_key)  # exact-key GET; R2 LIST is never used
    if not content.startswith(b"%PDF-"):
        raise ValueError("document bytes are not a PDF")
    if len(content) != byte_size:
        raise ValueError("document byte-size mismatch")
    got = hashlib.sha256(content).hexdigest()
    if not sha or got != sha:
        raise ValueError("document sha256 mismatch")
    fd, tmp = tempfile.mkstemp(suffix=".pdf"); os.close(fd)
    with open(tmp, "wb") as fh: fh.write(content)
    print(f"  [r2] verified contract-v1 RHP for ipo {ipo_id}, doc_id={doc_id}")
    return tmp, "r2-contract-v1", f"ipo{ipo_id}", doc_id


def step_rhp(conn, ipo_id, name, write, spent, max_spend, ignore_local=False):
    """RHP extraction + routing. THE ONLY STEP THAT COSTS MONEY."""
    pdf = src = base = doc_id = None
    pdf, src, base, doc_id = resolve_rhp(conn, ipo_id, name, ignore_local=ignore_local)
    if not pdf:
        return {"step": "rhp", "status": "skipped",
                "why": "no current fully verified contract-v1 document (missing object_key is legacy)"}
    if rhp_already_done(conn, doc_id):
        return {"step": "rhp", "status": "skipped", "why": "document/model/prompt extraction exists"}
    try:
        if spent + RHP_COST_EST > max_spend:
            return {"step": "rhp", "status": "skipped",
                    "why": f"would exceed --max-spend (${spent:.2f}+{RHP_COST_EST} > ${max_spend})"}
        if not write:
            return {"step": "rhp", "status": "dry", "pdf": pdf, "source": src, "est_cost": RHP_COST_EST}

        import fitz, rhp_sonnet
        from rhp_sections import gather_sections
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return {"step": "rhp", "status": "skipped", "why": "ANTHROPIC_API_KEY not set"}
        doc = fitz.open(pdf)
        pages = [(i + 1, doc[i].get_text()) for i in range(len(doc))]
        S = gather_sections(pages)
        if not S:
            return {"step": "rhp", "status": "failed", "why": "no sections located"}
        prompt = rhp_sonnet.build_prompt(name or f"ipo {ipo_id}", S)
        text, itok, otok = rhp_sonnet.call_sonnet(rhp_sonnet.SYSTEM, prompt, key)
        cost = itok * rhp_sonnet.IN_RATE + otok * rhp_sonnet.OUT_RATE
        os.makedirs("rhp_v2full", exist_ok=True)
        open(os.path.join("rhp_v2full", base + "_raw.txt"), "w", encoding="utf-8").write(text)
        try:
            data = rhp_sonnet.parse_json(text)
        except Exception as e:
            return {"step": "rhp", "status": "failed", "why": f"parse: {e}", "cost": cost}
        data["_meta"] = {"input_tokens": itok, "output_tokens": otok,
                         "cost_usd": round(cost, 4), "model": rhp_sonnet.MODEL}
        json.dump(data, open(os.path.join("rhp_v2full", base + "_summary.json"), "w",
                             encoding="utf-8"), indent=2, ensure_ascii=False)
        if "structured" not in data:
            return {"step": "rhp", "status": "failed", "why": "no structured block", "cost": cost}
        rep = rhp_sonnet.route_to_db(pdf, ipo_id, data, "rhp_v2full", base,
                                     doc_id=doc_id, conn=conn)
        return {"step": "rhp", "status": "ok", "cost": round(cost, 4), "source": src,
                "financials": len(rep["financials"]), "insights": rep["insights"]}
    finally:
        # a fetched R2 copy is a temp file — never leave it lying around
        if src == "r2-contract-v1" and pdf and os.path.exists(pdf):
            try: os.remove(pdf)
            except OSError: pass


def step_derived(conn, ipo_id, write):
    """score_engine then verdict. FREE. MUST run after NSE + RHP."""
    import score_engine
    v = score_engine.compute_valuation(conn, ipo_id)
    out = {"step": "derived", "score": v["score"], "band": v["score_band"],
           "pe_source": (v["inputs_used"] or {}).get("pe_source"),
           "pb_source": (v["inputs_used"] or {}).get("pb_source")}
    if write:
        score_engine.write_valuation(conn, v)
        out["status"] = "ok"
    else:
        out["status"] = "dry"
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids"); ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rhp", action="store_true", help="enable the PAID RHP step")
    ap.add_argument("--ignore-local", action="store_true",
                    help="force reading the RHP from R2 even when a local copy is on disk "
                         "— exercises the runner read path without deleting local PDFs. "
                         "Pair with --dry-run to verify the fetch without paying for extraction.")
    ap.add_argument("--max-spend", type=float, default=0.50)
    ap.add_argument("--no-ntfy", action="store_true", help="suppress ALL pushes")
    ap.add_argument("--ntfy-each", action="store_true",
                    help="push per IPO. Default is ONE summary push per run — a push "
                         "for every IPO on every run is noise, not signal.")
    ap.add_argument("--resume", action="store_true", help="skip IPOs already COMPLETE in the manifest")
    a = ap.parse_args()
    if not (a.write or a.dry_run):
        sys.exit("choose --write or --dry-run")
    write = a.write and not a.dry_run

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    if a.ids:
        ids = [int(x) for x in a.ids.split(",") if x.strip()]
        cur.execute("""SELECT id, symbol, name_display FROM ipo WHERE id = ANY(%s)
                        ORDER BY id""", (ids,))
    else:
        cur.execute("""SELECT id, symbol, name_display FROM ipo
                        WHERE in_backtest_universe=TRUE
                        ORDER BY listing_date DESC NULLS LAST LIMIT %s""", (a.limit,))
    targets = cur.fetchall()

    manifest = load_manifest()
    import completeness
    errs = completeness.validate_map(conn, verbose=False)
    if errs:
        sys.exit(f"completeness map invalid: {errs}")

    print(f"  [build] {FILE_BUILD}")
    print(f"  {len(targets)} IPOs · mode={'WRITE' if write else 'DRY-RUN'} · "
          f"RHP={'ON (paid)' if a.rhp else 'OFF (free run)'} · cap=${a.max_spend}")
    if a.rhp and write:
        # Exact payable count is resolved per current ledger document in step_rhp.
        n_pay = len(targets)
        print(f"  COST: up to {n_pay} RHP calls x ${RHP_COST_EST} = "
              f"${n_pay * RHP_COST_EST:.2f} (hard cap ${a.max_spend})")
    print()

    session = None
    spent = 0.0
    results = []
    for ipo_id, symbol, name in targets:
        if a.resume and manifest.get(str(ipo_id), {}).get("complete"):
            print(f"  == id={ipo_id} {str(name)[:34]} — COMPLETE in manifest, skipped")
            continue
        print(f"  == id={ipo_id} {symbol or '(no symbol)':14} {str(name)[:34]}")
        steps = []
        try:
            if session is None:
                from curl_cffi import requests as cffi
                import nse_fetch
                session = nse_fetch.prime(cffi)
            steps.append(step_nse(conn, ipo_id, symbol, session, write))
        except Exception as e:
            try: conn.rollback()
            except Exception: pass
            steps.append({"step": "nse", "status": "failed", "why": f"{type(e).__name__}: {str(e)[:90]}"})

        if a.rhp:
            try:
                r = step_rhp(conn, ipo_id, name, write, spent, a.max_spend, ignore_local=a.ignore_local)
                spent += r.get("cost", 0.0)
                steps.append(r)
            except Exception as e:
                try: conn.rollback()
                except Exception: pass
                steps.append({"step": "rhp", "status": "failed",
                              "why": f"{type(e).__name__}: {str(e)[:90]}"})
        else:
            steps.append({"step": "rhp", "status": "skipped", "why": "--rhp not set"})

        try:
            steps.append(step_derived(conn, ipo_id, write))
        except Exception as e:
            try: conn.rollback()
            except Exception: pass
            steps.append({"step": "derived", "status": "failed",
                          "why": f"{type(e).__name__}: {str(e)[:90]}"})

        for s in steps:
            extra = " ".join(f"{k}={v}" for k, v in s.items() if k not in ("step", "status"))
            print(f"       {s['step']:8} {s['status']:8} {extra[:110]}")

        rep = completeness.check_completeness(conn, ipo_id)
        line = completeness.ntfy_line(rep)
        print(f"       -> {line}")
        for m in rep["missing"]:
            print(f"          - {m}")
        for m in rep.get("pending", []):
            print(f"          . {m} [not due yet]")
        for m in rep.get("vendor_gaps", []):
            print(f"          ~ {m} [IPOMatrix fallback]")
        results.append(rep)
        # PER-IPO PUSH ONLY WHEN IT SAYS SOMETHING NEW. A run that re-reports the same
        # gaps every time trains you to ignore the alerts. Default: summary only.
        # prev MUST be read before the manifest entry is replaced, or it compares the
        # new state against itself and nothing ever looks changed.
        prev = manifest.get(str(ipo_id), {})
        changed = (prev.get("missing") != rep["missing"]
                   or prev.get("complete") != rep["complete"])
        manifest[str(ipo_id)] = {"complete": rep["complete"], "stage": rep["stage"],
                                 "missing": rep["missing"], "at": dt.datetime.now().isoformat()}
        if write and (a.ntfy_each or (changed and prev)):
            ntfy(line, title="AA Capital", enabled=not a.no_ntfy)
        print()
        time.sleep(1.0)

    save_manifest(manifest)
    n_ok = sum(1 for r in results if r["complete"])
    summary = (f"Run complete: {len(results)} IPOs, {n_ok} COMPLETE, "
               f"{len(results)-n_ok} missing columns"
               + (f" · spent ${spent:.3f}" if spent else " · $0"))
    print(f"  {summary}")
    if write:
        ntfy(summary, title="AA Capital run", enabled=not a.no_ntfy)
    print(f"  manifest -> {MANIFEST}" + ("" if write else "   (dry run — nothing written)"))
    conn.close()


if __name__ == "__main__":
    main()
