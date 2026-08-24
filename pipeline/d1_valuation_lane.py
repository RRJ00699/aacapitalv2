#!/usr/bin/env python3
"""Deterministic D1 pro-forma + fair-value + street/GMP calculation lane.

No LLM calculates valuation.  Sonnet only extracts source facts.  This lane consumes the
canonical D1 bundle and writes reproducible proforma_runs, valuation_runs and
street_summary rows.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from statistics import median

from d1_ingest import D1IngestClient, fingerprint

ENGINE="d1-fair-value-v1"
PROFORMA_ENGINE="d1-proforma-v1"


def n(v):
    if v is None or isinstance(v,bool): return None
    try:
        x=float(v);return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None


def latest_facts(rows):
    out={}
    for r in rows:
        k=r.get("target_field")
        if k and k not in out: out[k]=r
    return out


def parse_period(value):
    s=str(value or "")
    for fmt in ("%d-%b-%y","%Y-%m-%d","%d-%b-%Y"):
        try:return dt.datetime.strptime(s,fmt).date()
        except ValueError:pass
    return dt.date.min


def choose_financials(rows):
    # Prefer consolidated, then newest period.  Never mix bases inside a ratio.
    cons=[r for r in rows if str(r.get("basis") or "").lower()=="consolidated"]
    use=cons or list(rows)
    return sorted(use,key=lambda r:parse_period(r.get("period")),reverse=True)


def revenue_cagr(rows):
    clean=[(parse_period(r.get("period")),n(r.get("revenue_cr"))) for r in rows]
    clean=[x for x in clean if x[0]!=dt.date.min and x[1] and x[1]>0]
    clean.sort(reverse=True)
    if len(clean)<3:return None
    newest,oldest=clean[0],clean[2]
    years=max(1,(newest[0]-oldest[0]).days/365.25)
    return ((newest[1]/oldest[1])**(1/years)-1)*100


def fair_value(bundle):
    issue=bundle["issue"];facts=latest_facts(bundle.get("facts") or []);financials=choose_financials(bundle.get("financials") or [])
    latest=financials[0] if financials else {}
    eps=n((facts.get("eps_post") or {}).get("normalized_value")) or n((facts.get("eps_pre") or {}).get("normalized_value"))
    peer_pes=[n(r.get("pe_x")) for r in bundle.get("peers") or []];peer_pes=[x for x in peer_pes if x and x>0]
    peer_med=float(median(peer_pes)) if len(peer_pes)>=3 else None
    pat=n(latest.get("pat_cr"));nw=n(latest.get("net_worth_cr"));debt=n(latest.get("debt_cr"))
    roe=n((facts.get("roe_pct") or facts.get("ronw_pct") or {}).get("normalized_value"))
    if roe is None and pat is not None and nw and nw>0:roe=pat/nw*100
    de=debt/nw if debt is not None and nw and nw>0 else None
    rev_cagr=revenue_cagr(financials)
    issue_size=n(issue.get("issue_size_cr"));ofs=n(issue.get("ofs_cr"));ofs_pct=(ofs/issue_size*100) if ofs is not None and issue_size and issue_size>0 else None
    missing=[]
    if eps is None:missing.append("eps_post_or_pre")
    if peer_med is None:missing.append("peer_median_pe_requires_3_peers")
    quality=1.0
    if roe is not None and roe>=18:quality+=0.06
    if rev_cagr is not None and rev_cagr>=20:quality+=0.05
    if de is not None and de<=0.3:quality+=0.04
    quality=min(1.15,max(0.85,quality))
    structure=1.0
    if ofs_pct is not None and ofs_pct<20:structure+=0.06
    elif ofs_pct is not None and ofs_pct>60:structure-=0.08
    structure=min(1.10,max(0.90,structure))
    fv=(eps*peer_med*quality*structure) if eps is not None and peer_med is not None else None
    issue_price=n(issue.get("issue_price_rs"));band_hi=n(issue.get("band_hi_rs"));ref=issue_price or band_hi
    ref_source="issue_price" if issue_price is not None else "band_hi" if band_hi is not None else None
    gmp=bundle.get("gmp") or {};gmp_rs=n(gmp.get("gmp_rs"));gmp_pct=n(gmp.get("gmp_pct"))
    implied=(ref+gmp_rs) if ref is not None and gmp_rs is not None else (ref*(1+gmp_pct/100) if ref is not None and gmp_pct is not None else None)
    mos=(fv-ref)/ref*100 if fv is not None and ref and ref>0 else None
    gmp_rr=(fv-implied)/implied*100 if fv is not None and implied and implied>0 else None
    price_view=("UNDERVALUED" if mos is not None and mos>=10 else "OVERVALUED" if mos is not None and mos<=-10 else "FAIR") if mos is not None else "INSUFFICIENT_DATA"
    return {"fair_value":fv,"eps":eps,"peer_median_pe":peer_med,"quality_factor":quality,"structure_factor":structure,
            "roe_pct":roe,"de":de,"revenue_cagr_pct":rev_cagr,"ofs_pct":ofs_pct,"reference_price":ref,
            "reference_price_source":ref_source,"margin_of_safety_pct":mos,"gmp_rs":gmp_rs,"gmp_pct":gmp_pct,
            "gmp_implied_price":implied,"risk_reward_vs_gmp_pct":gmp_rr,"price_view":price_view,"missing":missing}


def proforma(bundle):
    facts=latest_facts(bundle.get("facts") or []);financials=choose_financials(bundle.get("financials") or []);latest=financials[0] if financials else {}
    debt=n(latest.get("debt_cr"));pat=n(latest.get("pat_cr"));repay=n((facts.get("debt_repayment_cr") or {}).get("normalized_value"));interest=n((facts.get("interest_expense_cr") or {}).get("normalized_value"))
    missing=[];savings=None;effective_rate=None
    if debt and debt>0 and interest is not None:
        effective_rate=interest/debt
    else:missing.append("debt_and_interest_expense_for_effective_rate")
    if repay is not None and effective_rate is not None:
        savings=min(max(repay,0),debt)*effective_rate
    else:missing.append("debt_repayment_for_interest_savings")
    outputs={"latest_pat_cr":pat,"latest_debt_cr":debt,"debt_repayment_cr":repay,
             "effective_interest_rate":effective_rate,"gross_interest_savings_cr":savings,
             "gross_interest_savings_pct_of_pat":(savings/pat*100 if savings is not None and pat and pat!=0 else None),
             "post_repayment_debt_cr":(max(0,debt-repay) if debt is not None and repay is not None else None),
             "proforma_pat_cr":None,"proforma_eps":None,
             "note":"Gross interest savings are deterministic. PAT/EPS are not increased without an explicit tax-effect input."}
    if savings is not None:missing.append("tax_effect_required_before_pat_or_eps_uplift")
    return outputs,sorted(set(missing))


def street(bundle):
    findings=bundle.get("sbi") or [];news=bundle.get("news") or []
    counts={"positive":0,"neutral":0,"negative":0}
    for r in findings:
        d=str(r.get("direction") or "neutral").lower();counts[d if d in counts else "neutral"]+=1
    return {"counts":counts,"sbi_findings":findings[:12],"news":news[:12],
            "note":"Direction counts use evidenced SBI findings only; news headlines are shown without invented sentiment."}


def run(*,limit=30,apply=False,client=None):
    client=client or D1IngestClient.from_env();targets=client.active_ipos(limit=limit,lookback_days=100)
    report={"selected":len(targets),"valued":0,"proforma":0,"street":0,"insufficient":0,"failures":[]}
    for row in targets:
        try:
            b=client.valuation_inputs(int(row["id"]));fv=fair_value(b);pf,pf_missing=proforma(b);st=street(b);now=dt.datetime.now(dt.timezone.utc).isoformat()
            if fv["fair_value"] is None:report["insufficient"]+=1
            ops=[
              {"op":"proforma_insert","ipo_id":int(row["id"]),"calculated_at":now,"engine_version":PROFORMA_ENGINE,
               "inputs_json":{"facts":"D1 canonical source_facts + latest same-basis financials"},"outputs_json":pf,"missing_inputs_json":pf_missing,
               "run_fingerprint":fingerprint(PROFORMA_ENGINE,row["id"],json.dumps(pf,sort_keys=True,default=str),json.dumps(pf_missing))},
              {"op":"valuation_insert","ipo_id":int(row["id"]),"calculated_at":now,"engine_version":ENGINE,
               "inputs_json":{"eps":fv["eps"],"reference_price":fv["reference_price"],"reference_price_source":fv["reference_price_source"],
                              "quality_factor":fv["quality_factor"],"structure_factor":fv["structure_factor"],"gmp_rs":fv["gmp_rs"],"gmp_pct":fv["gmp_pct"]},
               "ratios_json":{"roe_pct":fv["roe_pct"],"de":fv["de"],"revenue_cagr_pct":fv["revenue_cagr_pct"],"ofs_pct":fv["ofs_pct"],
                              "gmp_implied_price":fv["gmp_implied_price"],"risk_reward_vs_gmp_pct":fv["risk_reward_vs_gmp_pct"],"price_view":fv["price_view"]},
               "peer_median_pe_x":fv["peer_median_pe"],"fair_value_lo_rs":fv["fair_value"],"fair_value_hi_rs":fv["fair_value"],
               "margin_of_safety_pct":fv["margin_of_safety_pct"],"missing_inputs_json":fv["missing"],
               "run_fingerprint":fingerprint(ENGINE,row["id"],json.dumps(fv,sort_keys=True,default=str))},
              {"op":"street_summary_upsert","ipo_id":int(row["id"]),"calculated_at":now,
               "positive_count":st["counts"]["positive"],"neutral_count":st["counts"]["neutral"],"negative_count":st["counts"]["negative"],
               "summary_json":st,"source_fingerprint":fingerprint("street-v1",row["id"],json.dumps(st,sort_keys=True,default=str))},]
            if apply:client.batch(ops)
            report["valued"]+=int(fv["fair_value"] is not None);report["proforma"]+=1;report["street"]+=1
        except Exception as exc:report["failures"].append({"ipo_id":row.get("id"),"error":f"{type(exc).__name__}:{exc}"})
    return report


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--limit",type=int,default=30);ap.add_argument("--apply",action="store_true")
    a=ap.parse_args(argv);rep=run(limit=max(1,min(a.limit,100)),apply=a.apply)
    print("D1_VALUATION_SUMMARY="+json.dumps(rep,sort_keys=True,default=str));return 1 if rep["failures"] else 0
if __name__=="__main__":raise SystemExit(main())
