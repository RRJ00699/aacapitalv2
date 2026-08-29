#!/usr/bin/env python3
"""Listing-day pre-open order-book capture through the protected Kite broker Worker."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from zoneinfo import ZoneInfo

from d1_ingest import D1IngestClient, fingerprint
from kite_broker_client import KiteBrokerClient

IST=ZoneInfo("Asia/Kolkata")
START_MINUTE=8*60+55
END_MINUTE=10*60+5


def capture(*,now=None,limit=10,apply=False,d1=None,broker=None):
    now=now or dt.datetime.now(IST); minute=now.hour*60+now.minute
    report={"eligible":False,"selected":0,"captured":0,"failures":[]}
    if now.weekday()>4 or not START_MINUTE<=minute<=END_MINUTE:
        report["reason"]="outside weekday 08:55-10:05 IST"; return report
    report["eligible"]=True
    d1=d1 or D1IngestClient.from_env(); broker=broker or KiteBrokerClient.from_env()
    rows=d1.listing_today(day=now.date().isoformat(),limit=limit); report["selected"]=len(rows)
    allowed=[str(r["nse_symbol"]).upper() for r in rows if r.get("nse_symbol")]
    if not allowed: return report
    try: quotes=broker.quotes(allowed,allowed)
    except Exception as exc:
        report["failures"].append({"stage":"quotes","error":f"{type(exc).__name__}:{exc}"}); return report
    observed=now.replace(second=0,microsecond=0).astimezone(dt.timezone.utc).isoformat()
    ops=[]
    for row in rows:
        sym=str(row.get("nse_symbol") or "").upper(); q=quotes.get(sym)
        if not q:
            report["failures"].append({"ipo_id":row.get("id"),"symbol":sym,"error":"quote_missing"}); continue
        payload={"isin":row.get("isin"),"symbol":sym,"discovery_price":q.get("open") or q.get("last_price"),
                 "depth":q.get("depth"),"total_buy_quantity":q.get("total_buy_quantity"),
                 "total_sell_quantity":q.get("total_sell_quantity"),"broker_as_of":q.get("as_of")}
        fp=fingerprint("preopen",row["id"],observed,q.get("last_price"),q.get("total_buy_quantity"),q.get("total_sell_quantity"),json.dumps(payload,sort_keys=True,separators=(",",":"),default=str))
        ops.append({"op":"listing_observation_insert","ipo_id":int(row["id"]),"observation_type":"preopen",
                    "observed_at":observed,"price_rs":q.get("last_price"),"buy_qty_shares":q.get("total_buy_quantity"),
                    "sell_qty_shares":q.get("total_sell_quantity"),"payload_json":payload,
                    "source_name":"kite_preopen","content_fingerprint":fp})
    if apply and ops:
        d1.batch(ops); report["captured"]=len(ops)
    else: report["planned"]=len(ops)
    return report


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--limit",type=int,default=10);ap.add_argument("--apply",action="store_true");ap.add_argument("--at",type=dt.datetime.fromisoformat)
    a=ap.parse_args(argv)
    now=a.at.astimezone(IST) if a.at and a.at.tzinfo else a.at.replace(tzinfo=IST) if a.at else None
    rep=capture(now=now,limit=max(1,min(a.limit,20)),apply=a.apply)
    print("D1_PREOPEN_SUMMARY="+json.dumps(rep,sort_keys=True,default=str));return 1 if rep["failures"] else 0
if __name__=="__main__":raise SystemExit(main())
