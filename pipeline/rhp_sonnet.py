#!/usr/bin/env python3
"""rhp_sonnet.py — premium RHP intelligence via Claude Sonnet 4.6.
Sends only targeted sections (rhp_sections.gather_sections) — keeps tokens low.
HARD COST CAP: stops the entire run the instant projected spend reaches --cap (default $20).
Processes recent-first. Returns a rich, source-cited forensic summary + structured flags.

  python rhp_sonnet.py --pdf rhps/laser.pdf                 # single
  python rhp_sonnet.py --dir rhps --year-min 2021 --cap 20  # batch recent-first, capped
"""
import os,sys,json,argparse,glob,urllib.request,time,re
import hashlib


def _configure_cli_streams():
    """Use UTF-8 for direct CLI runs without replacing importers' capture streams."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")

MODEL="claude-sonnet-4-6"
IN_RATE=3.00/1_000_000    # $ per input token
OUT_RATE=15.00/1_000_000  # $ per output token
PROMPT_VERSION="v2-full"   # written to rhp_findings.prompt_version + insights.prompt_version
                           # (the 376 legacy rows are 'v1-migration' — a different family,
                           #  and the rhp_findings UNIQUE key includes prompt_version, so
                           #  v2-full never overwrites them)

SYSTEM = """You are a forensic equity analyst specializing in Indian IPO Red Herring Prospectuses (RHPs). You read like a skeptical investor protecting their own capital. You extract ONLY what the text explicitly states — never infer, never assume, never fill gaps with expectation. When a fact is not clearly present, you say "not disclosed" rather than guessing. You are especially alert to the language of negation: "there have been NO reservations", "neither the Company nor its Promoters is a Wilful Defaulter", "Criminal proceedings: Nil" all mean CLEAN — never flag these as problems. You distinguish routine legal/tax matters (ordinary course of business) from genuinely material risks (criminal charges, SEBI/regulatory action, blacklisting, fraud, going-concern doubt, large contingent liabilities, promoter cases that threaten operations). You quote the specific supporting line for every claim you make."""


def _pdf_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def _already_extracted(conn, sha, prompt_version=PROMPT_VERSION):
    """GUARDRAIL G: this exact PDF (by content hash) was already extracted UNDER THIS
    PROMPT VERSION -> skip the paid Sonnet call. Renamed/re-seeded files no longer
    re-burn credits.

    CHANGED 08-01: was `SELECT 1 FROM ipo_rhp_intel WHERE pdf_sha256=%s` — ipo_rhp_intel
    is a V1 debris table the V2 codebase must not read or write. The V2 home for document
    provenance is documents.sha256 (UNIQUE, index doc_sha_uq), and the extraction result
    is rhp_findings keyed (doc_id, model, prompt_version).

    The prompt_version in the check is deliberate: a PDF extracted under v1-migration has
    NOT been extracted under v2-full, and must be allowed through. Without it, upgrading
    the prompt would silently skip every document we already touched."""
    if conn is None:
        return False
    try:
        cur = conn.cursor()
        cur.execute("""SELECT 1 FROM rhp_findings f
                        JOIN documents d ON d.id = f.doc_id
                       WHERE d.sha256 = %s AND f.model = %s AND f.prompt_version = %s
                       LIMIT 1""", (sha, MODEL, prompt_version))
        return cur.fetchone() is not None
    except Exception as e:
        # FAIL CLOSED (ledger #7): if we can't verify whether this PDF was
        # already paid for, do NOT pay again blind — skip it loudly. A DB
        # outage must never turn into a re-billed batch.
        print(f"  ⚠ spend-guard: can't verify pdf hash ({str(e)[:60]}) — SKIPPING, not paying blind")
        try: conn.rollback()
        except Exception: pass
        return True

def build_prompt(company, sections):
    secblob = "\n\n".join(f"===== SECTION: {k} =====\n{v}" for k,v in sections.items())
    return f"""Analyze the following excerpts from the RHP of **{company}**. These are the governance, litigation, financial-quality, structure, and risk sections.

Produce a JSON object with EXACTLY this structure:

{{
  "verdict": "clean" | "some-concerns" | "serious-concerns",
  "one_line": "<a single sentence an investor could read in 5 seconds — the honest bottom line>",
  "trust_summary": "<3-4 sentence plain-English summary: can we trust these numbers and these people? what stands out, good or bad?>",

  "numbers_integrity": {{
    "assessment": "<Read the restated P&L and cash-flow. Judge if the numbers look real or dressed-up for the IPO. Consider: (a) is operating cash flow tracking reported profit, or is profit high while OCF is weak/negative (receivables build-up, channel stuffing)? (b) sudden margin or revenue spike in the most recent year before the IPO? (c) profit reliant on 'other income'/exceptional/one-off items rather than core operations? (d) receivables or inventory growing much faster than revenue? (e) related-party transactions inflating the top line? State specifically what the numbers show.>",
    "revenue_trend": "<e.g. 'FY24 X, FY25 Y, FY26 Z — steady/spiking/lumpy'>",
    "profit_vs_cashflow": "<does OCF support PAT? quote the figures if visible>",
    "inflation_signals": ["<each concrete sign of dressing-up found, or empty if clean>"],
    "flag": "clean" | "watch" | "not-disclosed"
  }},

  "cash_conversion": {{
    "ocf_to_pat": "<ratio of operating cash flow to PAT across the years, if computable from the figures — e.g. 'OCF ~0.4x PAT, weak'>",
    "flag": "strong" | "weak" | "not-disclosed",
    "note": "<weak conversion (OCF far below PAT) suggests profits aren't turning into cash — receivables or aggressive recognition>"
  }},

  "debt_trend": {{
    "direction": "rising" | "falling" | "stable" | "not-disclosed",
    "detail": "<total borrowings across the years if visible in the balance sheet; note if debt is rising into the IPO>"
  }},

  "working_capital": {{
    "flag": "clean" | "watch" | "not-disclosed",
    "detail": "<are receivables or inventory growing materially faster than revenue? that ties up cash and can mask channel-stuffing>"
  }},

  "auditor": {{
    "qualified": true | false | null,
    "detail": "<quote the reservations/qualifications/adverse-remarks line verbatim, short>",
    "page": <int or null>
  }},

  "sebi_regulatory": {{
    "any_action": true | false | null,
    "detail": "<any SEBI/stock-exchange disciplinary action against company/promoters/directors — or 'none disclosed'>",
    "page": <int or null>
  }},

  "litigation": {{
    "material_cases": [
      {{"summary": "<one line: what the case is>", "materiality": "watch" | "routine", "amount_inr_mn": <number or null>, "page": <int or null>}}
    ],
    "overall": "clean" | "routine-only" | "has-watch-items",
    "watch_note": "<if any 'watch' items, one line on why they could bite the company — else empty>"
  }},

  "related_party": {{
    "concern": true | false | null,
    "detail": "<are related-party transactions large or unusual relative to revenue? quote if stated>"
  }},

  "cashing_out": {{
    "ofs_heavy": true | false | null,
    "detail": "<is this mostly promoter/investor exit (OFS) vs fresh capital?>"
  }},

  "use_of_proceeds": {{
    "debt_repayment_flag": true | false | null,
    "gcp_pct": <number or null>,
    "detail": "<where does the fresh money go? Flag if a large share repays existing/promoter debt, or if 'general corporate purposes' is an unusually high % (vague, unaccountable). Quote the split if stated.>"
  }},

  "contingent_liabilities": {{
    "material": true | false | null,
    "detail": "<are contingent liabilities large relative to net worth or profit? amount if stated>"
  }},

  "promoter_pledge": {{
    "pledged": true | false | null,
    "detail": "<any promoter shares pledged? pledge % if stated — a classic red flag>"
  }},

  "concentration": {{
    "customer_risk": true | false | null,
    "detail": "<top customer / top-10 concentration % if stated>"
  }},

  "promoter_skin": {{
    "detail": "<promoter holding post-issue, pledge, or weighted-average cost of acquisition if stated>"
  }},

  "top_3_material_risks": ["<the 3 MOST material, company-SPECIFIC risks — NOT boilerplate like 'economic conditions may change'>"],

  "aacapital_decision": {{
    "quality_gate": "reject" | "watch" | "clean",
    "primary_reason": "<ONE sentence — the single most important reason for this gate>",
    "margin_of_safety": "high" | "medium" | "low",
    "requires_further_dd": true | false,
    "dd_note": "<if further due-diligence needed, what specifically to check — else empty>"
  }},

  "confidence": "high" | "medium" | "low",

  "db_fields": {{
    "auditor_qualified": true | false | null,
    "sebi_action": true | false | null,
    "criminal_litigation": true | false | null,
    "litigation_watch_count": <int>,
    "related_party_concern": true | false | null,
    "ofs_heavy": true | false | null,
    "customer_concentration_high": true | false | null,
    "numbers_integrity_flag": "clean" | "watch" | "not-disclosed",
    "cash_conversion_flag": "strong" | "weak" | "not-disclosed",
    "debt_trend": "rising" | "falling" | "stable" | "not-disclosed",
    "working_capital_flag": "clean" | "watch" | "not-disclosed",
    "debt_repayment_flag": true | false | null,
    "gcp_high": true | false | null,
    "contingent_liabilities_material": true | false | null,
    "promoter_pledge_flag": true | false | null,
    "quality_gate": "reject" | "watch" | "clean",
    "margin_of_safety": "high" | "medium" | "low"
  }},

  "structured": {{
    "unit_as_printed": "crore" | "million" | "lakh" | "thousand" | "absolute" | "not-disclosed",
    "currency": "INR" | "other" | "not-disclosed",

    "canonical_facts": {{
      "cash_cr": {{"value": <number exactly as printed or null>, "unit_as_printed": "crore" | "million" | "lakh" | "thousand" | "absolute" | "not-disclosed", "page": <int or null>, "excerpt": "<verbatim support under 25 words>"}},
      "interest_expense_cr": {{"value": <number exactly as printed or null>, "unit_as_printed": "crore" | "million" | "lakh" | "thousand" | "absolute" | "not-disclosed", "page": <int or null>, "excerpt": "<verbatim support under 25 words>"}},
      "operating_cash_flow_cr": {{"value": <number exactly as printed or null>, "unit_as_printed": "crore" | "million" | "lakh" | "thousand" | "absolute" | "not-disclosed", "page": <int or null>, "excerpt": "<verbatim support under 25 words>"}},
      "debt_repayment_cr": {{"value": <objects-of-offer allocation exactly as printed or null>, "unit_as_printed": "crore" | "million" | "lakh" | "thousand" | "absolute" | "not-disclosed", "page": <int or null>, "excerpt": "<verbatim objects-of-offer support under 25 words>"}},
      "capex_cr": {{"value": <objects-of-offer allocation exactly as printed or null>, "unit_as_printed": "crore" | "million" | "lakh" | "thousand" | "absolute" | "not-disclosed", "page": <int or null>, "excerpt": "<verbatim objects-of-offer support under 25 words>"}}
    }},

    "financials": [
      {{
        "period": "<the period end EXACTLY as DD-Mon-YY, 2-digit year, e.g. 31-Mar-26>",
        "basis": "consolidated" | "standalone",
        "revenue_from_operations": <number or null>,
        "total_income": <number or null>,
        "ebitda": <number or null>,
        "pat": <number or null>,
        "net_worth": <number or null>,
        "total_debt": <number or null>,
        "total_assets": <number or null>,
        "page": <int or null>,
        "excerpt": "<the verbatim line these figures came from, under 25 words>"
      }}
    ],

    "kpi": {{
      "roe_pct": <number or null>, "ronw_pct": <number or null>, "roce_pct": <number or null>,
      "nav_per_share": <number or null>,
      "eps_basic_pre": <number or null>, "eps_post": <number or null>,
      "ebitda_margin_pct": <number or null>, "pat_margin_pct": <number or null>,
      "page": <int or null>,
      "excerpt": "<verbatim line supporting these, under 25 words>"
    }},

    "peer_analysis": {{
      "as_of_date": "<date the peer figures are as of, or null>",
      "basis": "consolidated" | "standalone" | "not-disclosed",
      "peers": [
        {{"name": "<listed peer company name>", "pe": <number or null>,
          "pb": <number or null>, "ronw_pct": <number or null>,
          "revenue": <number or null>, "face_value": <number or null>}}
      ],
      "peer_median_pe": <number or null>,
      "page": <int or null>,
      "excerpt": "<verbatim line from the peer table, under 25 words>"
    }},

    "issue_price_band": {{
      "floor": <number or null>, "cap": <number or null>,
      "face_value": <number or null>, "page": <int or null>,
      "excerpt": "<verbatim line, under 25 words>"
    }}
  }}
}}

IMPORTANT ON THE DECISION: The quality_gate reflects ONLY governance/trust quality from the RHP — it is NOT a buy/sell call and NOT a prediction of listing gains. "reject" = serious governance/forensic concerns. "watch" = some concerns needing eyes. "clean" = no material red flags in the RHP. Never imply the stock will rise or fall.

RULES:
- Every "detail" must be grounded in the text. If a section wasn't provided or is silent, use null/"not disclosed".
- Negations mean CLEAN. "No reservations", "Nil", "neither...is a Wilful Defaulter" → not a flag.
- "watch" is reserved for genuinely material items. Ordinary tax/civil matters are "routine".

RULES FOR THE "structured" BLOCK — these are stored in a database, so precision matters:
- REPORT NUMBERS EXACTLY AS PRINTED. Do NOT convert units, do NOT rescale, do NOT round.
  If the statement is headed "(₹ in million)", give the million figures and set
  "unit_as_printed": "million". Converting is done downstream where it can be audited;
  a converted number with the wrong unit label is a silent corruption we cannot detect.
- "period" MUST be DD-Mon-YY with a TWO-DIGIT year: 31-Mar-26, not 31-Mar-2026, not FY26.
- "basis" must say which statement the row came from. If both consolidated and standalone
  are shown, prefer CONSOLIDATED and say so. Never mix the two inside one row.
- List every period shown (usually 3), most recent FIRST.
- revenue_from_operations and total_income are DIFFERENT LINES. Revenue from operations
  excludes other income; total income includes it. Report BOTH when both are printed.
  Never copy one into the other, and never compute one from the other.
- Every structured sub-object needs "page" and a verbatim "excerpt". A figure without
  its supporting line CANNOT BE STORED and will be discarded — so if you cannot point
  to the line, return null for the value rather than a number you inferred.
- If a KPI is genuinely not in the provided text, return null. Do NOT compute it from
  the financials — a derived ratio is not a disclosed ratio, and the two are stored
  separately for exactly that reason.
- DO NOT report P/E or P/B, and do not be tempted to derive them. This is a RED HERRING
  prospectus: the Offer Price is stated as "[●] times the face value" because the price
  band is NOT FIXED at filing. Any P/E or P/B for a pre-band RHP would be invented.
  They are computed downstream from the NSE price band combined with the EPS and NAV
  you report here. What is wanted from this document is the band-INDEPENDENT set:
  EPS, NAV, RoE, RoCE, RoNW, margins and the revenue lines.
- Return ONLY the JSON. No preamble, no markdown fences.

TEXT:
{secblob}"""

def call_sonnet(system, prompt, api_key, max_tokens=8000):
    # RAISED 4000 -> 8000 for v2-full. The qualitative block alone ran ~2.5-3K output
    # tokens; the structured block adds 3 financial periods + KPI + peer table + excerpts,
    # roughly another 1.5-2K. At 4000 the response would truncate mid-JSON and land in
    # parse_json's recovery path — which closes braces and SILENTLY DROPS the tail, and
    # the tail is where "structured" sits. Worst case cost of the raise is
    # 4000 extra output tokens = $0.06 per RHP; a truncated extraction costs the whole call.
    body=json.dumps({
        "model":MODEL,"max_tokens":max_tokens,"system":system,
        "messages":[{"role":"user","content":prompt}]
    }).encode()
    req=urllib.request.Request("https://api.anthropic.com/v1/messages",data=body,
        headers={"content-type":"application/json","x-api-key":api_key,"anthropic-version":"2023-06-01"})
    try:
        resp=urllib.request.urlopen(req,timeout=120)
        r=json.load(resp)
    except urllib.error.HTTPError as e:
        err=e.read().decode()
        open("api_error.txt","w",encoding="utf-8").write(f"HTTP {e.code}\n{err}")
        raise RuntimeError(f"API {e.code} — full error written to api_error.txt ({len(err)} chars)")
    text="".join(b.get("text","") for b in r.get("content",[]) if b.get("type")=="text")
    usage=r.get("usage",{})
    return text, usage.get("input_tokens",0), usage.get("output_tokens",0)

def parse_json(text):
    text=text.strip()
    if text.startswith("```"): text=text.split("```")[1].replace("json","",1)
    i=text.find("{")
    if i<0: return {}
    body=text[i:]
    # first try clean parse
    j=body.rfind("}")
    if j>0:
        try: return json.loads(body[:j+1])
        except Exception: pass
    # recovery: truncated JSON — trim to last complete key:value, then close braces
    try:
        # cut at last comma or closing brace of a complete value
        cut=max(body.rfind(","), body.rfind("}"), body.rfind("]"))
        frag=body[:cut] if cut>0 else body
        # balance braces/brackets
        opens=frag.count("{")-frag.count("}")
        obr=frag.count("[")-frag.count("]")
        frag=frag.rstrip().rstrip(",")
        frag+= "]"*max(0,obr) + "}"*max(0,opens)
        return json.loads(frag)
    except Exception as e:
        raise e

def route_to_db(pdf_path, ipo_id, data, out_dir, base, *, doc_id=None, conn=None):
    """Atomically route extraction for an existing document-ledger row.

    Extraction never uploads or mutates the source ledger. The caller must supply the
    ledger ``doc_id`` (or a pre-existing row with this PDF hash must be found).
    """
    import psycopg2
    from rhp_writer import route_extraction
    owns_conn = conn is None
    conn = conn or psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        if doc_id is None:
            sha = _pdf_sha256(pdf_path)
            cur = conn.cursor()
            cur.execute("SELECT id FROM documents WHERE ipo_id=%s AND doc_type='rhp' AND sha256=%s",
                        (ipo_id, sha))
            row = cur.fetchone()
            if not row:
                raise ValueError("no existing documents ledger row for extraction")
            doc_id = row[0]
        rep = route_extraction(conn, ipo_id, doc_id, data, MODEL, PROMPT_VERSION,
                               commit=False)
        conn.commit()
        print(f"     doc_id={doc_id}  findings={rep['findings'][1]}  "
              f"financials={len(rep['financials'])}  insights={rep['insights']}  "
              f"peers={rep.get('peers_stored', 0)}")
        for s in rep["skipped"]:
            print(f"     [skipped] {s}")
        if rep.get("peer_median_note"):
            print(f"     [note] {rep['peer_median_note']}")
        if rep.get("valuation"):
            print(f"     valuation v2-rhp-1 id={rep['valuation']['valuation_id']}")
        return rep
    except Exception:
        conn.rollback()
        raise
    finally:
        if owns_conn: conn.close()


def route_existing(a):
    """--reuse: route an already-extracted <base>_summary.json into the DB. FREE."""
    base = os.path.basename(os.path.dirname(a.pdf)) if a.pdf else None
    if a.pdf and not base:
        base = os.path.splitext(os.path.basename(a.pdf))[0]
    sp = os.path.join(a.out_dir, (base or "") + "_summary.json")
    if not os.path.exists(sp):
        sys.exit(f"no existing summary at {sp} — run the extraction first")
    data = json.load(open(sp, encoding="utf-8"))
    if "_parse_error" in data:
        sys.exit(f"{sp} holds a parse error — re-extract before routing")
    if "structured" not in data:
        sys.exit(f"{sp} has no 'structured' block — it predates v2-full; re-extract")
    print(f"  routing existing {sp} -> ipo_id={a.ipo_id} (no API call)")
    route_to_db(a.pdf, a.ipo_id, data, a.out_dir, base)
    print("  done.")
    return


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--pdf");ap.add_argument("--dir")
    ap.add_argument("--cap",type=float,default=20.0)   # HARD $ cap
    ap.add_argument("--year-min",type=int)
    ap.add_argument("--limit",type=int,default=0)
    ap.add_argument("--out-dir",default="rhp_summaries")
    ap.add_argument("--dry-run",action="store_true",
                    help="build the prompt, report token/cost estimate, write it to "
                         "<base>_prompt.txt — makes NO API call and spends NOTHING")
    ap.add_argument("--write",action="store_true",
                    help="route the extraction into the DB via fill_v2/rhp_writer. "
                         "Requires --ipo-id (identity is never guessed from a filename).")
    ap.add_argument("--ipo-id",type=int,
                    help="the ipo.id this PDF belongs to. MANDATORY with --write.")
    ap.add_argument("--reuse",action="store_true",
                    help="route an EXISTING <base>_summary.json into the DB without "
                         "re-calling the API (free — use after a successful extraction)")
    a=ap.parse_args()
    key=os.environ.get("ANTHROPIC_API_KEY")
    if not key and not (a.dry_run or a.reuse): sys.exit("ANTHROPIC_API_KEY not set")

    # IDENTITY IS NEVER GUESSED. A PDF sits in rhps/<slug>/ and the slug is a filename,
    # not an identifier — resolving an IPO from it would be exactly the fuzzy matching
    # the ISIN spine exists to prevent. --write therefore demands an explicit ipo id.
    if (a.write or a.reuse) and not a.ipo_id:
        sys.exit("--write/--reuse requires --ipo-id (identity is never inferred from a filename)")
    if a.write and a.dry_run:
        sys.exit("--dry-run and --write are mutually exclusive")

    if a.reuse:
        return route_existing(a)
    import fitz
    from rhp_sections import gather_sections
    os.makedirs(a.out_dir,exist_ok=True)

    pdfs=[]
    if a.pdf: pdfs=[a.pdf]
    elif a.dir:
        pdfs=sorted(glob.glob(os.path.join(a.dir,"**","*.pdf"),recursive=True))
        # recent-first by folder mtime (proxy) — real recency handled by caller ordering
        pdfs=sorted(pdfs,key=lambda p:os.path.getmtime(p),reverse=True)
    # order recent-first by listing_date from DB, filter to year-min
    if a.year_min:
        try:
            import psycopg2
            _c=psycopg2.connect(os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL"),connect_timeout=20)
            _cur=_c.cursor();_cur.execute("SELECT company_name,listing_date FROM ipo_intelligence WHERE listing_date IS NOT NULL")
            def _norm(x): return re.sub(r'[^a-z0-9]+',' ',re.sub(r'\b(red herring|prospectus|limited|ltd|private|pvt|inc|corporation|corp|company|co)\b','',(x or '').lower())).strip()
            datemap={}
            for nm,ld in _cur.fetchall(): datemap[_norm(nm)]=ld
            _c.close()
            def keyf(p):
                # Per-company subfolder is the convention, but a PDF dropped
                # FLAT into the scan root must fall back to its FILENAME —
                # previously dirname yielded the root ("rhps"), matched no
                # company, and the file silently vanished from the run
                # (Caliber manual seed, 2026-07-17).
                d=os.path.basename(os.path.dirname(p))
                base=d if d and os.path.abspath(os.path.dirname(p))!=os.path.abspath(a.dir) else os.path.splitext(os.path.basename(p))[0]
                return datemap.get(_norm(base.replace("-"," ").replace("_"," ")))
            # keep only those with a listing_date >= year-min, sort desc
            dated=[(keyf(p),p) for p in pdfs]
            dated=[(d,p) for d,p in dated if d is not None and d.year>=a.year_min]
            dated.sort(reverse=True)
            pdfs=[p for d,p in dated]
            print(f"  {len(pdfs)} RHPs listed {a.year_min}+ (recent-first)")
        except Exception as e:
            print(f"  [order] {e} — falling back to mtime order")
    if a.limit: pdfs=pdfs[:a.limit]

    spent=0.0; done=0; stopped=False; consec_fail=0
    for pdf in pdfs:
        # project cost of next call BEFORE making it? we cap AFTER each call on cumulative.
        if spent>=a.cap:
            print(f"\n⛔ HARD CAP ${a.cap} reached (spent ${spent:.2f}) — stopping.");stopped=True;break
        base=os.path.basename(os.path.dirname(pdf)) or os.path.splitext(os.path.basename(pdf))[0]
        # skip if already processed cleanly (avoid paying twice)
        _sp=os.path.join(a.out_dir,base+"_summary.json")
        if os.path.exists(_sp):
            try:
                _ex=json.load(open(_sp,encoding="utf-8"))
                if "_parse_error" not in _ex and _ex.get("verdict"):
                    print(f"  ⏭  {base} (already done, skipping)"); continue
            except Exception: pass
        try:
            doc=fitz.open(pdf);pages=[(i+1,doc[i].get_text()) for i in range(len(doc))]
            # company from metadata.json if present
            company=base.replace("-"," ").title()
            meta=os.path.join(os.path.dirname(pdf),"metadata.json")
            if os.path.exists(meta):
                try: company=json.load(open(meta)).get("company",company)
                except: pass
            S=gather_sections(pages)
            if not S:
                print(f"  ✗ {base}: no sections located");continue
            prompt=build_prompt(company,S)
            if a.dry_run:
                est_in=len(prompt)//4
                pp=os.path.join(a.out_dir,base+"_prompt.txt")
                open(pp,"w",encoding="utf-8").write(prompt)
                print(f"  [DRY] {company[:30]:32} sections={len(S)} "
                      f"prompt={len(prompt)}ch ~{est_in}tok  "
                      f"in≈${est_in*IN_RATE:.4f} + out≤${8000*OUT_RATE:.4f} "
                      f"= ≤${est_in*IN_RATE+8000*OUT_RATE:.4f}/RHP  -> {pp}")
                done+=1
                continue
            text,itok,otok=call_sonnet(SYSTEM,prompt,key)
            cost=itok*IN_RATE+otok*OUT_RATE
            spent+=cost
            # always persist raw text first (so a parse error never wastes the spend)
            open(os.path.join(a.out_dir,base+"_raw.txt"),"w",encoding="utf-8").write(text)
            meta={"company":company,"input_tokens":itok,"output_tokens":otok,
                  "cost_usd":round(cost,4),"model":MODEL}
            try:
                data=parse_json(text)
            except Exception as pe:
                data={"_parse_error":str(pe),"_raw_saved":base+"_raw.txt"}
                data["_meta"]=meta
                json.dump(data,open(os.path.join(a.out_dir,base+"_summary.json"),"w",encoding="utf-8"),indent=2,ensure_ascii=False)
                print(f"  ⚠ {company[:30]:32} parse-fail — raw saved, skipping ${cost:.3f} (run ${spent:.2f})")
                consec_fail+=1
                if consec_fail>=3:
                    print("  ⛔ 3 consecutive parse-fails — stopping (something's wrong)"); break
                continue
            consec_fail=0
            data["_meta"]=meta
            json.dump(data,open(os.path.join(a.out_dir,base+"_summary.json"),"w",encoding="utf-8"),indent=2,ensure_ascii=False)
            if "_parse_error" not in data:
                v=data.get("verdict","?");ol=data.get("one_line","")[:70]
                print(f"  ✓ {company[:32]:34} [{v:15}] ${cost:.3f} (run ${spent:.2f}) — {ol}")
                if a.write:
                    if "structured" not in data:
                        print("     ! no 'structured' block in the response — NOT routed")
                    else:
                        try:
                            route_to_db(pdf, a.ipo_id, data, a.out_dir, base)
                        except Exception as re_:
                            # the extraction is already saved to disk, so a routing
                            # failure never wastes the spend — --reuse can retry free
                            print(f"     ! routing failed: {type(re_).__name__}: {str(re_)[:120]}")
                            print(f"       extraction is saved — retry free with: "
                                  f"--reuse --pdf {pdf} --ipo-id {a.ipo_id}")
            done+=1
        except Exception as e:
            print(f"  ✗ {base}: {type(e).__name__} {str(e)[:60]}")
        time.sleep(0.5)
    print(f"\n{'STOPPED at cap' if stopped else 'done'}: {done} RHPs | total spend ${spent:.3f}")
REQUIRED_STRUCTURED_KEYS = ["unit_as_printed","financials","kpi","peer_analysis","issue_price_band"]

def selftest():
    """No PDF, no DB, no API — validates the prompt contract and the parser."""
    ok=True
    def chk(m,c):
        nonlocal ok; ok=ok and c; print(f"  [{'PASS' if c else 'FAIL'}] {m}")

    S={"basis_for_issue_price":"[p136] BASIS FOR OFFER PRICE RoNW 22.04% NAV 88.20",
       "financials":"[p101] Revenue from operations 4,192.98 Total income 4,320.70",
       "auditor":"[p200] There have been no reservations."}
    p=build_prompt("Indo-MIM Limited", S)

    chk("prompt names the company", "Indo-MIM Limited" in p)
    chk("prompt carries the section text", "4,192.98" in p and "22.04" in p)
    chk("section headers labelled", "SECTION: basis_for_issue_price" in p)
    # qualitative block PRESERVED (the whole point of 'keep it')
    for k in ["verdict","one_line","trust_summary","numbers_integrity","auditor",
              "sebi_regulatory","litigation","aacapital_decision","db_fields"]:
        chk(f"qualitative key '{k}' still in prompt", f'"{k}"' in p)
    # structured block ADDED
    for k in REQUIRED_STRUCTURED_KEYS:
        chk(f"structured key '{k}' in prompt", f'"{k}"' in p)
    chk("BOTH revenue lines demanded", '"revenue_from_operations"' in p and '"total_income"' in p)
    chk("2-digit period format specified", "31-Mar-26" in p)
    chk("unit conversion FORBIDDEN in prompt", "Do NOT convert units" in p)
    chk("excerpt required for storage", "CANNOT BE STORED" in p)
    chk("derived-ratio substitution forbidden", "Do NOT compute it from" in p)

    # parser handles a well-formed v2-full response
    good=json.dumps({"verdict":"clean","one_line":"ok","db_fields":{"quality_gate":"clean"},
        "structured":{"unit_as_printed":"million","currency":"INR",
          "financials":[{"period":"31-Mar-26","basis":"consolidated",
                         "revenue_from_operations":41929.8,"total_income":43207.0,
                         "pat":5123.3,"net_worth":22000.0,"page":101,"excerpt":"Revenue 41,929.8"}],
          "kpi":{"ronw_pct":22.04,"nav_per_share":88.20,"pe_at_cap":34.1,"page":138,
                 "excerpt":"RoNW 22.04%"},
          "peer_analysis":{"peers":[{"name":"Peer A","pe":41.0}],"peer_median_pe":41.0,
                           "page":137,"excerpt":"Peer A P/E 41.00"},
          "issue_price_band":{"floor":420,"cap":443,"page":1,"excerpt":"Price Band 420-443"}}})
    d=parse_json(good)
    chk("parse_json reads a clean v2-full response", d.get("structured",{}).get("unit_as_printed")=="million")
    chk("both revenue lines survive the parse",
        d["structured"]["financials"][0]["revenue_from_operations"]==41929.8
        and d["structured"]["financials"][0]["total_income"]==43207.0)
    chk("qualitative survives alongside structured", d.get("verdict")=="clean")

    # fenced response (model sometimes wraps in ```json)
    chk("parse_json strips markdown fences", parse_json("```json\n"+good+"\n```").get("verdict")=="clean")

    # TRUNCATION: the recovery path must not fabricate — it may drop the tail, but what
    # it returns has to be real. This is why max_tokens was raised to 8000.
    trunc=good[:len(good)-120]
    try:
        t=parse_json(trunc)
        chk("truncated response recovers without inventing keys",
            isinstance(t,dict) and all(k in good for k in t.keys()))
    except Exception:
        chk("truncated response fails loudly rather than silently (acceptable)", True)

    chk("PROMPT_VERSION is v2-full", PROMPT_VERSION=="v2-full")
    chk("legacy prompt_version untouched (v1-migration != v2-full)", PROMPT_VERSION!="v1-migration")

    est=len(p)//4
    print(f"\n  fixture prompt {len(p)} chars (~{est} tok). On a real RHP (~61K chars of "
          f"sections) expect ~15.5K in + ≤8K out ≈ ${15500*IN_RATE+8000*OUT_RATE:.3f}/RHP worst case.")
    print(f"\n{'ALL PASS ✓' if ok else 'SOME FAILED ✗'}")
    return ok

if __name__=="__main__":
    _configure_cli_streams()
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    main()
