#!/usr/bin/env python3
"""rhp_sections.py — locate + gather the RIGHT sections of an RHP so we send only
relevant text to the API (not the whole 350K-token doc). Keeps input ~8-15K tokens.
Returns a dict of {section_name: text} for the extractor to feed the LLM.
"""
import re

def _pages_matching(pages, needles, maxp, skip_frac=0.03, exclude_toc=True):
    n=len(pages); start=int(n*skip_frac); hits=[]
    for p,t in pages:
        if p<start: continue
        low=t.lower()
        if exclude_toc and "....." in t[:400]: continue  # skip TOC dotted lines
        if any(nd in low for nd in needles):
            hits.append((p,t))
        if len(hits)>=maxp: break
    return hits

def _num_density(text):
    """How many multi-digit numbers on the page — separates a real ratio TABLE from a
    passing cross-reference to the section ('see Basis for the Offer Price on page X')."""
    return len(re.findall(r'[\d,]{4,}', text))

def _pages_span(pages, needles, span=3, skip_frac=0.03, exclude_toc=True, exclude_pages=None):
    """Anchor on the header page of a multi-page section and return it plus the
    following (span-1) pages. Among all candidate anchors, pick the one whose WHOLE
    SPAN carries the most numbers.

    WHY SPAN DENSITY, NOT PAGE DENSITY (Indo-MIM, 495pp, measured 08-01):
      p20  'basis for the offer price' — 0 numbers  (narrative cross-reference)
      p60  'basis for the offer price' — 9 numbers  (cross-reference)
      p136 'BASIS FOR OFFER PRICE'     — 5 numbers  <- THE REAL SECTION HEADER
           p137 peers 10 · p138 RoNW/NAV 20 · p141 KPI table 29
    The true header is PROSE ('The Price Band will be determined in consultation with
    the BRLMs'); the tables begin on the pages after it. A per-page density gate scores
    the real header at 5 and rejects it — which is exactly what happened, and why the
    first version anchored on p20. Scoring the span instead ranks p136 far above every
    cross-reference, with no magic threshold to tune.

    exclude_pages lets a later section skip pages an earlier one already claimed, so
    the same table is never billed to the API twice."""
    n=len(pages); start=int(n*skip_frac)
    exclude_pages = exclude_pages or set()
    best_i=None; best_score=-1
    for i,(p,t) in enumerate(pages):
        if p<start: continue
        if exclude_toc and "....." in t[:400]: continue
        if not any(nd in t.lower() for nd in needles): continue
        score=sum(_num_density(txt) for _,txt in pages[i:i+span])
        if score>best_score:
            best_score=score; best_i=i
    if best_i is None: return []
    return [(p,t) for p,t in pages[best_i:best_i+span] if p not in exclude_pages]

def gather_sections(pages, max_chars_per_section=6000):
    """Return {section: text} with the most relevant pages per governance/forensic area."""
    S={}
    def grab(name, needles, maxp=2, chars=None):
        hits=_pages_matching(pages, needles, maxp)
        if hits:
            txt="\n".join(f"[p{p}] {t}" for p,t in hits)
            S[name]=txt[:(chars or max_chars_per_section)]
    # 1. Auditor opinion (standard section)
    grab("auditor", ["reservations, qualifications and adverse remarks","no reservations","emphasis of matter"], 2, 3000)
    # 2. Material litigation (the prose, back of doc) — most important for materiality
    grab("litigation", ["litigation involving our company","outstanding litigation against our company","material developments"], 3, 8000)
    # 3. Litigation summary table (counts + SEBI column)
    grab("litigation_summary", ["summary of outstanding matters","criminal proceedings"], 1, 2500)
    # 4. Concentration
    grab("concentration", ["top 10 customers","top ten customers","customer concentration","top 5 customers"], 2, 2500)
    # 5. Objects / use of proceeds
    grab("objects", ["objects of the offer","objects of the issue"], 2, 4000)
    # 6. Related party
    grab("related_party", ["summary of related party transactions","related party transactions"], 1, 2500)
    # 7. Promoter / capital structure (skin in the game, pledge)
    grab("promoter", ["shareholding of our promoter","promoter and promoter group","weighted average cost of acquisition"], 2, 3000)
    # 8. Cashflow (for quality)
    grab("cashflow", ["cash generated from operating activities","net cash from operating"], 1, 2000)
    # 8b. Contingent liabilities + promoter pledge (governance)
    grab("contingent", ["contingent liabilit","summary of contingent"], 1, 2000)
    grab("pledge", ["pledge","pledged","encumber"], 1, 1500)
    # 9. Key risk factors (top of RF section only)
    grab("risks", ["risk factors"], 2, 5000)
    # 10. FINANCIALS — the restated P&L + cashflow so the LLM can judge inflation.
    #     Pick the densest P&L page (revenue+profit+many numbers) and the cashflow page.
    import re as _re
    pl=[]
    for p,t in pages:
        low=t.lower()
        if "....." in t[:400]: continue
        if ("revenue from operations" in low or "total income" in low) and "profit" in low:
            nums=len(_re.findall(r'[\d,]{4,}',t))
            if nums>=20: pl.append((nums,p,t))
    pl.sort(reverse=True)
    fin_txt=""
    for _,p,t in pl[:2]:  # 2 densest P&L pages
        fin_txt+=f"[p{p}] {t[:3000]}\n\n"
    # cashflow page
    for p,t in pages:
        low=t.lower()
        if "cash generated from operating" in low or "cash flow from operating" in low:
            fin_txt+=f"[p{p} CASHFLOW] {t[:2500]}\n"; break
    # balance-sheet page (for debt trend + working capital): borrowings + receivables + inventory
    for p,t in pages:
        low=t.lower()
        if ("borrowings" in low or "total equity and liabilities" in low) and ("trade receivable" in low or "inventor" in low):
            nums=len(_re.findall(r'[\d,]{4,}',t))
            if nums>=15:
                fin_txt+=f"[p{p} BALANCE SHEET] {t[:2800]}\n"; break
    if fin_txt: S["financials"]=fin_txt[:12000]

    # ---------------------------------------------------------------- 11-13. THE NUMERIC BLOCK
    # ADDED 08-01. These sections carry the KPIs, the issuer's own P/E-P/B-RoNW and the
    # listed-peer table. None of the 12 grabs above reaches them: the P&L grab keys on
    # "revenue from operations"/"total income", which do NOT appear on these pages.
    # That is why the ratio fields came back None.
    #
    # SPANS are sized from the measured Indo-MIM layout (header p136, peers p137,
    # RoNW/NAV p138, KPI comparison table p141): the Basis section runs ~6 pages and
    # CONTAINS the KPI and peer subsections. So basis is grabbed FIRST and widest, and
    # the later two skip any page it already claimed — same content is never sent twice.
    used_pages=set()
    def grab_span(name, needles, span=3, chars=6000):
        hits=_pages_span(pages, needles, span=span, exclude_pages=used_pages)
        if hits:
            # PER-PAGE budget, not a global cut. A global [:chars] truncation drops the
            # LAST pages of the span entirely — and on Indo-MIM the last page (p141) is
            # the densest one in the section (the KPI comparison table). Splitting the
            # budget guarantees every page in the span is represented.
            per=max(1200, chars//max(1,len(hits)))
            S[name]="\n".join(f"[p{p}] {t[:per]}" for p,t in hits)
            used_pages.update(p for p,_ in hits)

    # 11. Basis for the Offer Price — SEBI ICDR mandates it; holds the issuer's stated
    #     P/E, P/B, RoNW, NAV and EPS at both band ends, plus (usually) KPI + peers.
    grab_span("basis_for_issue_price",
              ["basis for the offer price","basis for the issue price",
               "basis for offer price","basis for issue price"],
              span=6, chars=14000)
    # 12. Key Performance Indicators — only if it sits OUTSIDE the basis span.
    grab_span("kpi",
              ["key performance indicators","key financial and operational metrics",
               "kpis of our company","our key performance indicators"],
              span=4, chars=5000)
    # 13. Listed-peer comparison — only if it sits OUTSIDE the spans above.
    grab_span("peers",
              ["comparison with listed industry peers","comparison with listed peers",
               "industry peer group","peer group comparison",
               "comparison of accounting ratios"],
              span=3, chars=4000)
    return S

NUMERIC_SECTIONS = ["basis_for_issue_price", "kpi", "peers"]

def _synthetic_rhp():
    """A fake RHP modelled on the MEASURED Indo-MIM layout (495pp, diagnosed 08-01):
      - decoy 'basis for the offer price' cross-references EARLY, one of them
        number-dense (p20-equivalent), which is what defeated the first version
      - the REAL header late in the doc, in PROSE with barely any numbers
      - the ratio tables on the pages AFTER the header, never repeating it
    If the anchor rule regresses to per-page density, these tests fail."""
    pages=[]
    pages.append((1, "RED HERRING PROSPECTUS Dated July 2026 " + " ".join(f"{i},000" for i in range(20))))
    pages.append((2, "TABLE OF CONTENTS\nBASIS FOR OFFER PRICE.......136\n"
                     "RISK FACTORS.......30"))
    for p in range(3, 130):
        pages.append((p, f"Generic narrative page {p}. Our business operates across regions."))
    # DECOY A: number-dense cross-reference (the p20 trap that won last time)
    pages[19]=(20, "For details see Basis for the Offer Price on page 136. "
                   + " ".join(f"{i},{i}45.00" for i in range(1, 25)))
    # DECOY B: sparse cross-reference
    pages[59]=(60, "Investors should read Basis for the Offer Price before applying. 1,234 5,678")
    # a real RISK FACTORS page, so the pre-existing grab has something to find
    pages[29]=(30, "RISK FACTORS\nAn investment in Equity Shares involves a high degree of risk. "
                   "Our business depends on a limited number of customers.")
    # P&L page for the pre-existing financials grab
    pages[100]=(101, "Revenue from operations 4,192.98 3,801.44 Total income 4,320.70 3,912.55 "
                     "profit for the year 512.33 " + " ".join(f"{i},{i}00.55" for i in range(1, 30)))
    # THE REAL SECTION — prose header, almost no numbers (Indo-MIM p136 had 5)
    pages.append((136, "BASIS FOR OFFER PRICE\nThe Price Band and Offer Price will be determined "
                       "by our Company in consultation with the BRLMs on the basis of assessment "
                       "of market demand for the Equity Shares through the Book Building Process. "
                       "1,234 5,678"))
    pages.append((137, "COMPARISON WITH LISTED INDUSTRY PEERS\nPeer A P/E 41.00 P/B 6.10 RoNW 19.2% "
                       "Peer B P/E 38.50 P/B 5.40 " + " ".join(f"{i},{i}11.11" for i in range(1, 12))))
    pages.append((138, "Return on Net Worth RoNW 22.04% 19.88%\nNet Asset Value per share 88.20 "
                       "Basic EPS 12.10 P/E ratio at the Cap Price 34.10 Price to Book 5.20 "
                       + " ".join(f"{i},{i}22.22" for i in range(1, 18))))
    pages.append((139, "Return on Capital Employed 25.50% " + " ".join(f"{i},{i}33.33" for i in range(1, 16))))
    pages.append((140, "Other qualitative factors. 1,111 2,222"))
    pages.append((141, "Key Performance Indicators Units INDO-MIM EBITDA Margin 18.40% "
                       "PAT Margin 12.20% " + " ".join(f"{i},{i}44.44" for i in range(1, 28))))
    return pages

def _numeric_block(S):
    return "\n".join(S.get(n,"") for n in NUMERIC_SECTIONS)

def selftest():
    ok=True
    def chk(m,c):
        nonlocal ok; ok=ok and c; print(f"  [{'PASS' if c else 'FAIL'}] {m}")
    pages=_synthetic_rhp()
    S=gather_sections(pages)
    blk=_numeric_block(S)

    chk("numeric block produced at all", len(blk)>0)
    chk("anchored on the REAL header p136", "[p136]" in blk)
    chk("did NOT anchor on the number-dense decoy p20", "[p20]" not in blk)
    chk("did NOT anchor on the sparse decoy p60", "[p60]" not in blk)
    chk("TOC page never used as an anchor", "[p2]" not in blk)
    chk("span reaches the ratio table p138 (header repeats nowhere)", "[p138]" in blk)
    chk("span reaches the KPI table p141", "[p141]" in blk)

    # the values the extractor actually needs, wherever they landed
    for label,val in [("RoNW","22.04"), ("NAV","88.20"), ("EPS","12.10"),
                      ("P/E at cap","34.10"), ("P/B","5.20"), ("RoCE","25.50"),
                      ("EBITDA margin","18.40"), ("PAT margin","12.20"),
                      ("peer P/E","41.00"), ("peer RoNW","19.2")]:
        chk(f"{label} captured ({val})", val in blk)

    # no page billed to the API twice across the three grabs
    import collections
    pgs=re.findall(r'\[p(\d+)\]', blk)
    dupes=[p for p,c in collections.Counter(pgs).items() if c>1]
    chk(f"no page sent twice across numeric sections (dupes={dupes})", not dupes)

    # TRUNCATION MUST NOT DROP THE TAIL of a span. Force a tight budget against fat
    # pages: every page of the span must still appear. A global [:chars] cut fails this.
    fat=[(p, "HEADER BASIS FOR OFFER PRICE " + "x"*9000) if p==136 else
            (p, "y"*9000) for p in range(130, 145)]
    Sf=gather_sections(fat)
    fpgs=re.findall(r'\[p(\d+)\]', Sf.get("basis_for_issue_price",""))
    chk(f"tight budget keeps ALL span pages, tail included (got {fpgs})", len(fpgs)==6)

    # the 12 pre-existing grabs must be untouched by this change
    chk("pre-existing 'financials' grab still works", "financials" in S and "4,192.98" in S["financials"])
    chk("pre-existing 'risks' grab still works", "risks" in S)

    # a doc with NO such section must not crash and must not invent one
    bare=[(i, f"page {i} plain narrative with no ratio tables") for i in range(1,20)]
    Sb=gather_sections(bare)
    chk("absent section -> key simply absent, no crash, nothing invented",
        not any(n in Sb for n in NUMERIC_SECTIONS))

    total=sum(len(v) for v in S.values())
    added=len(blk)
    print(f"\n  total chars {total} (~{total//4} tokens); numeric block {added} chars "
          f"(~{added//4} tokens, ~${added/4*3.00/1_000_000:.4f} input at Sonnet rates)")
    print(f"\n{'ALL PASS ✓' if ok else 'SOME FAILED ✗'}")
    return ok

if __name__=="__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    import fitz,json,glob,os
    pdf=sys.argv[1]
    if not os.path.exists(pdf):
        g=glob.glob(f"rhps/**/{os.path.basename(pdf)}",recursive=True); pdf=g[0] if g else pdf
    doc=fitz.open(pdf);pages=[(i+1,doc[i].get_text()) for i in range(len(doc))]

    if "--diagnose" in sys.argv:
        # List EVERY page matching each numeric-section needle set, with its number
        # density and opening line. This is how we pick the anchor rule from evidence
        # instead of assuming which match is the real section.
        NEEDLES={
          "basis_for_issue_price":["basis for the offer price","basis for the issue price",
                                   "basis for offer price","basis for issue price"],
          "kpi":["key performance indicators","key financial and operational metrics",
                 "kpis of our company","our key performance indicators"],
          "peers":["comparison with listed industry peers","comparison with listed peers",
                   "industry peer group","peer group comparison",
                   "comparison of accounting ratios"],
        }
        print(f"{pdf} — {len(pages)} pages\n")
        for name,needles in NEEDLES.items():
            print(f"=== {name} — ALL matching pages ===")
            found=False
            for p,t in pages:
                low=t.lower()
                if any(nd in low for nd in needles):
                    found=True
                    toc = "TOC?" if "....." in t[:400] else "    "
                    first=" ".join(t.split())[:80]
                    print(f"  p{p:<5} numbers={_num_density(t):<4} {toc} {first}")
            if not found: print("  (no page matches)")
            print()
        # where do the ratio WORDS actually live, independent of headers?
        print("=== pages containing the ratio words themselves ===")
        for label,words in [("P/E",["p/e ratio","price to earnings","price/earnings"]),
                            ("RoNW",["return on net worth","ronw"]),
                            ("NAV",["net asset value"]),
                            ("EPS",["earnings per share"])]:
            hits=[p for p,t in pages if any(w in t.lower() for w in words)]
            print(f"  {label:6} pages: {hits[:15]}{' ...' if len(hits)>15 else ''}")
        sys.exit(0)

    S=gather_sections(pages)
    total=sum(len(v) for v in S.values())
    print(f"sections: {list(S.keys())}")
    print(f"total chars: {total} (~{total//4} tokens)")
    print("\nNUMERIC BLOCK (the fix):")
    claimed=set()
    for n in NUMERIC_SECTIONS:
        if n in S:
            pgs=re.findall(r'\[p(\d+)\]', S[n])
            claimed.update(pgs)
            print(f"  [FOUND]   {n:24} {len(S[n]):>6} chars   pages {pgs}")
        elif claimed:
            # NOT the same thing as absent: an earlier, wider section already claimed
            # these pages, so this grab correctly returned nothing to avoid sending the
            # same table to the API twice.
            print(f"  [ABSORBED]{n:24} — its pages fall inside an earlier span (not re-sent)")
        else:
            print(f"  [ABSENT]  {n:24} — no page in this RHP matched the needles")
    blk="\n".join(S.get(n,"") for n in NUMERIC_SECTIONS)
    print(f"\n  numeric block: {len(blk)} chars (~{len(blk)//4} tokens, "
          f"~${len(blk)/4*3.00/1_000_000:.4f} input)")
