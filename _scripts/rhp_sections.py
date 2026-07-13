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
    return S

if __name__=="__main__":
    import sys,fitz,json,glob,os
    pdf=sys.argv[1]
    if not os.path.exists(pdf):
        g=glob.glob(f"rhps/**/{os.path.basename(pdf)}",recursive=True); pdf=g[0] if g else pdf
    doc=fitz.open(pdf);pages=[(i+1,doc[i].get_text()) for i in range(len(doc))]
    S=gather_sections(pages)
    total=sum(len(v) for v in S.values())
    print(f"sections: {list(S.keys())}")
    print(f"total chars: {total} (~{total//4} tokens)")
