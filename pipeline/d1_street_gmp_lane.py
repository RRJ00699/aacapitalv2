#!/usr/bin/env python3
"""Free street/news + GMP context refresh for D1.

GMP remains context, never a predictor. Identity is exact name_norm only; unresolved vendor
names are reported rather than fuzzy-matched into the spine.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from email.utils import parsedate_to_datetime

from d1_ingest import D1IngestClient, fingerprint
from fill_ipo import _norm


def refresh_news(client:D1IngestClient,*,limit=20,apply=False):
    from _scripts.fetch_ipo_news import discover,score
    report={"targets":0,"selected":0,"written":0,"failures":[]}
    today=dt.date.today()
    for row in client.active_ipos(limit=limit,lookback_days=30):
        try:
            bundle=client.valuation_inputs(int(row["id"]));listing=bundle["issue"].get("listing_date")
            if not listing:continue
            ld=dt.date.fromisoformat(str(listing)[:10])
            if abs((ld-today).days)>7:continue
            report["targets"]+=1;name=str(bundle["issue"]["name"]);sym=bundle["issue"].get("nse_symbol")
            best=None
            for title,link,pub,date,desc in discover(name):
                sc=score(name,title,pub,True)
                if sc is not None and (best is None or sc>best[0]):best=(sc,title,link,pub,date,desc)
            if not best:continue
            report["selected"]+=1;sc,title,link,pub,date,desc=best
            published=None
            try:published=parsedate_to_datetime(date).astimezone(dt.timezone.utc).isoformat() if date else None
            except Exception:published=None
            if apply:
                client.op({"op":"news_upsert","company_name":name,"nse_symbol":sym,"publisher":pub,"headline":title,"url":link,
                           "published_at":published,"snippet":desc,"selection_score":sc,"source":"rss","fetch_status":"ok","is_current":True})
                report["written"]+=1
        except Exception as exc:report["failures"].append({"ipo_id":row.get("id"),"error":f"{type(exc).__name__}:{exc}"})
    return report


def refresh_gmp(client:D1IngestClient,*,apply=False):
    from _scripts.scrape_investorgain_gmp import scrape
    report={"scraped":0,"resolved":0,"written":0,"unresolved":[],"failures":[]};now=dt.datetime.now(dt.timezone.utc).isoformat()
    try:data=scrape()
    except BaseException as exc:
        report["failures"].append({"stage":"scrape","error":f"{type(exc).__name__}:{exc}"});return report
    report["scraped"]=len(data)
    for d in data:
        try:
            row=client.resolve_identity(name_norm=_norm(d["company"]))
            if not row:
                report["unresolved"].append(d["company"]);continue
            report["resolved"]+=1;gmp=None
            try:gmp=float(d.get("gmp")) if d.get("gmp") not in (None,"") else None
            except ValueError:gmp=None
            pct=None;m=re.search(r"(-?\d+(?:\.\d+)?)\s*%",str(d.get("est_listing") or ""))
            if m:
                try:pct=float(m.group(1))
                except ValueError:pass
            if apply and gmp is not None:
                fp=fingerprint("gmp",row["id"],now,gmp,pct,"investorgain")
                client.op({"op":"gmp_insert","ipo_id":int(row["id"]),"observed_at":now,"gmp_rs":gmp,"gmp_pct":pct,
                           "source_name":"investorgain_context","observation_fingerprint":fp});report["written"]+=1
        except Exception as exc:report["failures"].append({"company":d.get("company"),"error":f"{type(exc).__name__}:{exc}"})
    return report


def run(*,limit=20,apply=False,client=None):
    client=client or D1IngestClient.from_env();return {"news":refresh_news(client,limit=limit,apply=apply),"gmp":refresh_gmp(client,apply=apply)}

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--limit",type=int,default=20);ap.add_argument("--apply",action="store_true")
    a=ap.parse_args(argv);rep=run(limit=max(1,min(a.limit,50)),apply=a.apply);print("D1_STREET_GMP_SUMMARY="+json.dumps(rep,sort_keys=True,default=str))
    return 1 if rep["news"]["failures"] or rep["gmp"]["failures"] else 0
if __name__=="__main__":raise SystemExit(main())
