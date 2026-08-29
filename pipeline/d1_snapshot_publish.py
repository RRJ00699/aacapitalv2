#!/usr/bin/env python3
"""Build the public KV snapshots from D1 only and publish through the protected route."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.error
import urllib.request

from d1_ingest import D1IngestClient


def j(v,default=None):
    if v is None:return default
    if isinstance(v,(dict,list)):return v
    try:return json.loads(v)
    except Exception:return default if default is not None else v

def num(v):
    if v is None or v=="":return None
    try:return float(v)
    except (TypeError,ValueError):return None

def field(value,source,as_of=None,reason="Data is not available from the current D1 source."):
    return {"state":"AVAILABLE","value":value,"reason":None,"source":source,"as_of":as_of} if value is not None else {"state":"MISSING","value":None,"reason":reason,"source":source,"as_of":as_of}

def latest_by_source(extractions,source):
    for r in extractions or []:
        if str(r.get("source_type") or "").upper()==source:return r
    return None

def latest_subs(rows):
    out={}
    for r in rows or []:
        cat=str(r.get("category") or "").upper()
        if cat and cat not in out:out[cat]=r
    return out

def state(issue):
    today=dt.date.today();op=issue.get("open_date");cl=issue.get("close_date");li=issue.get("listing_date")
    try:
        if op and cl and dt.date.fromisoformat(str(op)[:10])<=today<=dt.date.fromisoformat(str(cl)[:10]):return "OPEN"
        if li and dt.date.fromisoformat(str(li)[:10])==today:return "LISTING"
        if li and dt.date.fromisoformat(str(li)[:10])>today:return "UPCOMING"
        if li and dt.date.fromisoformat(str(li)[:10])>=today-dt.timedelta(days=30):return "INWINDOW"
    except ValueError:pass
    return "UPCOMING"

def quality(bundle):
    rhp=latest_by_source(bundle.get("extractions"),"RHP");raw=j((rhp or {}).get("output_json"),{}) or {}
    gate=str(((raw.get("aacapital_decision") or {}).get("quality_gate") or (raw.get("db_fields") or {}).get("quality_gate") or "")).lower()
    verdict={"reject":"JUNK","watch":"WATCH","clean":"GOOD"}.get(gate)
    return verdict,gate,raw,rhp

def card(bundle):
    i=bundle["issue"];subs=latest_subs(bundle.get("subscriptions"));v=bundle.get("valuation") or {};pf=bundle.get("proforma") or {};street=bundle.get("street") or {}
    verdict,gate,rhp_raw,rhp_ex=quality(bundle);g=bundle.get("gmp") or {};anchor=bundle.get("anchor") or {}
    ratios=j(v.get("ratios_json"),{}) or {};vin=j(v.get("inputs_json"),{}) or {};pfo=j(pf.get("outputs_json"),{}) or {};st=j(street.get("summary_json"),{}) or {}
    fresh=num(i.get("fresh_cr"));ofs=num(i.get("ofs_cr"));issue_size=num(i.get("issue_size_cr"));ofs_pct=(ofs/issue_size*100 if ofs is not None and issue_size else None)
    sbi=bundle.get("sbi") or []
    return {"ipo_id":i["id"],"isin":i.get("isin"),"company_name":i.get("name"),"listing_date":i.get("listing_date"),
      "open_date":i.get("open_date"),"close_date":i.get("close_date"),"issue_size_cr":issue_size,"issue_price":num(i.get("issue_price_rs")),
      "ofs_cr":ofs,"fresh_issue_cr":fresh,"band_high":num(i.get("band_hi_rs")),"band_low":num(i.get("band_lo_rs")),
      "lot_size":i.get("lot_size_shares"),"face_value":num(i.get("face_value_rs")),"sym":i.get("nse_symbol"),"state":state(i),
      "anchor_count":anchor.get("investor_count"),"final_qib":num((subs.get("QIB") or {}).get("subscription_x")),
      "final_nii":num((subs.get("NII") or {}).get("subscription_x")),"final_retail":num((subs.get("RETAIL") or {}).get("subscription_x")),
      "final_total":num((subs.get("TOTAL") or {}).get("subscription_x")),"peer_median_pe":num(v.get("peer_median_pe_x")),
      "fair_value_lo":num(v.get("fair_value_lo_rs")),"fair_value_hi":num(v.get("fair_value_hi_rs")),"margin_of_safety_pct":num(v.get("margin_of_safety_pct")),
      "revenue_cagr_3y":num(ratios.get("revenue_cagr_pct")),"debt_equity":num(ratios.get("de")),"ofs_pct":ofs_pct,"verdict":verdict,"rhp_gate":gate or None,
      "gmp":{"rs":num(g.get("gmp_rs")),"pct":num(g.get("gmp_pct")),"observed_at":g.get("observed_at"),"source":g.get("source_name")},
      "risk_reward_vs_gmp_pct":num(ratios.get("risk_reward_vs_gmp_pct")),"gmp_implied_price":num(ratios.get("gmp_implied_price")),
      "price_view":ratios.get("price_view"),"proforma":pfo,"street":st,"sbi_findings":sbi[:8],
      "research":{"pipeline_status":"RESEARCH_COMPLETE" if rhp_ex and sbi else "RESEARCH_PARTIAL" if rhp_ex or sbi else "ENRICHED",
        "research_completeness":{"done":int(bool(rhp_ex))+int(bool(sbi))+int(bool(v)),"of":3},"rhp_status":"CONFIRMED" if rhp_ex else "PENDING",
        "sbi_status":"CONFIRMED" if sbi else "PENDING","company_quality":{"status":"CONFIRMED","verdict":verdict} if verdict else {"status":"INCOMPLETE"},
        "fair_value_status":"READY" if v.get("fair_value_lo_rs") is not None else "UNAVAILABLE","evidence":sbi},
      "rhp_analysis":{"verdict":verdict,"quality_gate":gate or None,"one_line":rhp_raw.get("one_line"),"confidence":rhp_raw.get("confidence")},
    }

def details(bundle,generated):
    i=bundle["issue"];v=bundle.get("valuation") or {};pf=bundle.get("proforma") or {};g=bundle.get("gmp") or {};verdict,gate,rhp_raw,rhp_ex=quality(bundle)
    evidence=[{"excerpt":r.get("evidence_excerpt"),"page_number":r.get("page"),"document":{"doc_type":"sbi","sha256":r.get("document_sha256")},
               "category":r.get("category"),"direction":r.get("direction"),"source_type":"SBI"} for r in bundle.get("sbi") or []]
    ratios=j(v.get("ratios_json"),{}) or {};inputs=j(v.get("inputs_json"),{}) or {};missing=j(v.get("missing_inputs_json"),[]) or []
    return {"schema_version":"ipo-details-v1","generated_at":generated,
      "identity":{"isin":i.get("isin"),"symbol":i.get("nse_symbol"),"company_name":i.get("name"),"listing_date":field(i.get("listing_date"),"ipo_issue")},
      "issue":{"issue_price":field(num(i.get("issue_price_rs")),"ipo_issue"),"band_low":field(num(i.get("band_lo_rs")),"ipo_issue"),"band_high":field(num(i.get("band_hi_rs")),"ipo_issue"),
        "issue_size_cr":field(num(i.get("issue_size_cr")),"ipo_issue"),"fresh_issue_cr":field(num(i.get("fresh_cr")),"ipo_issue"),"ofs_cr":field(num(i.get("ofs_cr")),"ipo_issue"),
        "lot_size":field(i.get("lot_size_shares"),"ipo_issue"),"face_value":field(num(i.get("face_value_rs")),"ipo_issue"),
        "registrar":field(i.get("registrar_name"),"ipo_issue"),"brlm":field(j(i.get("brlm_json"),i.get("brlm_json")),"ipo_issue")},
      "fundamentals":{"financials":bundle.get("financials") or [],"source_facts":bundle.get("facts") or [],"peers":bundle.get("peers") or []},
      "anchor":{"summary":bundle.get("anchor"),"allocations":bundle.get("anchor_allocations") or [],"pdf_retained":False},
      "subscriptions":bundle.get("subscriptions") or [],"reservations":bundle.get("reservations") or [],
      "ai_analysis":{"state":"AVAILABLE" if rhp_ex else "PENDING","findings":rhp_raw if rhp_ex else None,"model":(rhp_ex or {}).get("model"),
        "prompt_version":(rhp_ex or {}).get("prompt_version"),"confidence":rhp_raw.get("confidence") if rhp_ex else None,"analyzed_at":(rhp_ex or {}).get("extracted_at"),"reason":None if rhp_ex else "RHP extraction pending"},
      "sbi_analysis":{"state":"AVAILABLE" if bundle.get("sbi") else "PENDING","findings":bundle.get("sbi") or [],"reason":None if bundle.get("sbi") else "SBI note/extraction pending"},
      "verified_evidence":evidence,"decision":{"verdict":field(verdict,"RHP extraction"),"quality_gate":gate or None},
      "valuation":{"engine_version":field(v.get("engine_version"),"valuation_runs",v.get("calculated_at")),"fair_value_low":field(num(v.get("fair_value_lo_rs")),"valuation_runs",v.get("calculated_at")),
        "fair_value_high":field(num(v.get("fair_value_hi_rs")),"valuation_runs",v.get("calculated_at")),"peer_median_pe":field(num(v.get("peer_median_pe_x")),"valuation_runs",v.get("calculated_at")),
        "margin_of_safety":field(num(v.get("margin_of_safety_pct")),"valuation_runs",v.get("calculated_at")),"inputs_used":field(inputs,"valuation_runs",v.get("calculated_at")),
        "missing_inputs":field(missing,"valuation_runs",v.get("calculated_at")),"ratios":ratios},
      "proforma":{"state":"AVAILABLE" if pf else "MISSING","engine_version":pf.get("engine_version"),"outputs":j(pf.get("outputs_json"),{}),"missing_inputs":j(pf.get("missing_inputs_json"),[])},
      "street":j((bundle.get("street") or {}).get("summary_json"),{}),"news":bundle.get("news") or [],
      "gmp":{"state":"AVAILABLE" if g else "MISSING","available":bool(g),"gmp_rs":num(g.get("gmp_rs")),"gmp_pct":num(g.get("gmp_pct")),"observed_at":g.get("observed_at"),"source":g.get("source_name"),
             "implied_price":num(ratios.get("gmp_implied_price")),"risk_reward_vs_fair_value_pct":num(ratios.get("risk_reward_vs_gmp_pct"))},
      "listing_outcome":bundle.get("outcome") or {},"documents":bundle.get("documents") or [],"extractions":bundle.get("extractions") or [],
      "intelligence_profile":{"ipo_id":i.get("id"),"isin":i.get("isin"),"identity":{"company_name":i.get("name"),"symbol":i.get("nse_symbol"),"listing_date":i.get("listing_date")},
        "financials":bundle.get("financials") or [],"peers":bundle.get("peers") or [],"anchor":bundle.get("anchor_allocations") or [],"subscriptions":bundle.get("subscriptions") or [],
        "rhp_analysis":rhp_raw if rhp_ex else None,"sbi_analysis":bundle.get("sbi") or [],"proforma":j(pf.get("outputs_json"),{}),"valuation":{"inputs":inputs,"ratios":ratios,"fair_value":num(v.get("fair_value_lo_rs"))},
        "market":{"gmp":g,"street":j((bundle.get("street") or {}).get("summary_json"),{})},"provenance":{"documents":bundle.get("documents") or [],"verified_evidence":evidence}},
    }

def publish(endpoint,key,snapshots):
    raw=json.dumps({"snapshots":snapshots},separators=(",",":"),default=str).encode()
    req=urllib.request.Request(endpoint,data=raw,method="POST",headers={"content-type":"application/json","x-aac-key":key,"user-agent":"aacapital-pipeline/1"})
    try:
        with urllib.request.urlopen(req,timeout=120) as res:return json.load(res)
    except urllib.error.HTTPError as exc:raise RuntimeError(f"snapshot publish HTTP {exc.code}: {exc.read().decode(errors='replace')[:800]}") from None

def run(*,limit=25,client=None):
    client=client or D1IngestClient.from_env();origin=(os.environ.get("SNAPSHOT_PUBLISH_URL") or "").rstrip("/");key=os.environ.get("SNAPSHOT_PUBLISH_KEY") or ""
    if not origin or not key:raise RuntimeError("SNAPSHOT_PUBLISH_URL and SNAPSHOT_PUBLISH_KEY are required")
    endpoint=origin if origin.endswith("/api/admin/snapshots") else origin+"/api/admin/snapshots"
    generated=dt.datetime.now(dt.timezone.utc).isoformat();targets=client.active_ipos(limit=limit,lookback_days=30);bundles=[client.valuation_inputs(int(r["id"])) for r in targets]
    cards=[card(b) for b in bundles if not (num(b["issue"].get("issue_size_cr")) is not None and num(b["issue"].get("issue_size_cr"))<200)]
    filtered=[{**card(b),"filtered_reason":"issue size < ₹200cr junk floor"} for b in bundles if num(b["issue"].get("issue_size_cr")) is not None and num(b["issue"].get("issue_size_cr"))<200]
    index=client._request("/v1/state/index",{}).get("rows") or []
    live=[];journeys=[];detail_items=[]
    for b in bundles:
        i=b["issue"];isin=str(i.get("isin") or "").upper();sym=str(i.get("nse_symbol") or "").upper()
        if isin and len(isin)==12:
            journeys.append({"name":f"journey:isin:{isin}:v1","payload":{"isin":isin,"sym":sym,"rows":b.get("daily_bars") or [],"level_observation":None,"generated_at":generated}})
            detail_items.append({"name":f"ipo-details:isin:{isin}:v1","payload":details(b,generated)})
        if b.get("latest_preopen"):
            live.append({"ipo_id":i["id"],"isin":isin,"sym":sym,"company_name":i.get("name"),"latest_observation":b["latest_preopen"]})
    globals=[{"name":"ipo-command:v6","payload":{"cards":cards,"filtered":filtered,"filtered_count":len(filtered),"live":live,"levels":[],"blocks":[],"post":[],"brlm":[],"dl":[],"track":[],
              "notes":{"source":"D1 production pipeline","includes":["RHP","SBI","street","proforma","fair-value","GMP"]},"generated_at":generated}},
             {"name":"ipo:index:v3","payload":{"rows":index,"generated_at":generated}},
             {"name":"ipo-live-preopen:v2","payload":{"ok":True,"book_live":bool(live),"count":len(live),"listings":live,"fetchedAt":generated}},*journeys]
    pub=publish(endpoint,key,globals);details_published={}
    for off in range(0,len(detail_items),5):
        r=publish(endpoint,key,detail_items[off:off+5]);details_published.update(r.get("published") or {})
    return {"cards":len(cards),"filtered":len(filtered),"journeys":len(journeys),"details":len(detail_items),"global_published":len(pub.get("published") or {}),"details_published":len(details_published)}

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--limit",type=int,default=25);a=ap.parse_args(argv);rep=run(limit=max(1,min(a.limit,50)))
    print("D1_SNAPSHOT_SUMMARY="+json.dumps(rep,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
