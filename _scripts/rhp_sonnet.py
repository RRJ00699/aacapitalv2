#!/usr/bin/env python3
"""rhp_sonnet.py — premium RHP intelligence via Claude Sonnet 4.6.
Sends only targeted sections (rhp_sections.gather_sections) — keeps tokens low.
HARD COST CAP: stops the entire run the instant projected spend reaches --cap (default $20).
Processes recent-first. Returns a rich, source-cited forensic summary + structured flags.

  python rhp_sonnet.py --pdf rhps/laser.pdf                 # single
  python rhp_sonnet.py --dir rhps --year-min 2021 --cap 20  # batch recent-first, capped
"""
import os,sys,json,argparse,glob,urllib.request,time,io,re
try:
    sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
    sys.stderr=io.TextIOWrapper(sys.stderr.buffer,encoding="utf-8",errors="replace")
except Exception: pass

MODEL="claude-sonnet-4-6"
IN_RATE=3.00/1_000_000    # $ per input token
OUT_RATE=15.00/1_000_000  # $ per output token

SYSTEM = """You are a forensic equity analyst specializing in Indian IPO Red Herring Prospectuses (RHPs). You read like a skeptical investor protecting their own capital. You extract ONLY what the text explicitly states — never infer, never assume, never fill gaps with expectation. When a fact is not clearly present, you say "not disclosed" rather than guessing. You are especially alert to the language of negation: "there have been NO reservations", "neither the Company nor its Promoters is a Wilful Defaulter", "Criminal proceedings: Nil" all mean CLEAN — never flag these as problems. You distinguish routine legal/tax matters (ordinary course of business) from genuinely material risks (criminal charges, SEBI/regulatory action, blacklisting, fraud, going-concern doubt, large contingent liabilities, promoter cases that threaten operations). You quote the specific supporting line for every claim you make."""

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
  }}
}}

IMPORTANT ON THE DECISION: The quality_gate reflects ONLY governance/trust quality from the RHP — it is NOT a buy/sell call and NOT a prediction of listing gains. "reject" = serious governance/forensic concerns. "watch" = some concerns needing eyes. "clean" = no material red flags in the RHP. Never imply the stock will rise or fall.

RULES:
- Every "detail" must be grounded in the text. If a section wasn't provided or is silent, use null/"not disclosed".
- Negations mean CLEAN. "No reservations", "Nil", "neither...is a Wilful Defaulter" → not a flag.
- "watch" is reserved for genuinely material items. Ordinary tax/civil matters are "routine".
- Return ONLY the JSON. No preamble, no markdown fences.

TEXT:
{secblob}"""

def call_sonnet(system, prompt, api_key, max_tokens=4000):
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

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--pdf");ap.add_argument("--dir")
    ap.add_argument("--cap",type=float,default=20.0)   # HARD $ cap
    ap.add_argument("--year-min",type=int)
    ap.add_argument("--limit",type=int,default=0)
    ap.add_argument("--out-dir",default="rhp_summaries")
    a=ap.parse_args()
    key=os.environ.get("ANTHROPIC_API_KEY")
    if not key: sys.exit("ANTHROPIC_API_KEY not set")
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
                base=os.path.basename(os.path.dirname(p)) or os.path.splitext(os.path.basename(p))[0]
                return datemap.get(_norm(base.replace("-"," ")))
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
            done+=1
        except Exception as e:
            print(f"  ✗ {base}: {type(e).__name__} {str(e)[:60]}")
        time.sleep(0.5)
    print(f"\n{'STOPPED at cap' if stopped else 'done'}: {done} RHPs | total spend ${spent:.3f}")
if __name__=="__main__":main()
