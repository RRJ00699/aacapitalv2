#!/usr/bin/env python3
"""Kite market lane: listing -> lock30, persist 5m + daily only.

15m is deliberately not persisted; it is derived from 5m when needed.  Kite credentials
stay in Cloudflare: this VM lane talks only to the protected broker Worker.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

from d1_ingest import D1IngestClient, fingerprint
from kite_broker_client import KiteBrokerClient


def _day(value):
    return dt.date.fromisoformat(str(value)[:10])


def _ops(ipo_id:int,interval:str,rows:list[dict]):
    ops=[]
    for c in rows:
        ts=str(c.get("ts") or "")
        if not ts: continue
        fp=fingerprint("kite",ipo_id,interval,ts,c.get("open"),c.get("high"),c.get("low"),c.get("close"),c.get("volume"))
        ops.append({"op":"market_bar_upsert","ipo_id":ipo_id,"interval":interval,"ts":ts,
                    "open_rs":c.get("open"),"high_rs":c.get("high"),"low_rs":c.get("low"),"close_rs":c.get("close"),
                    "volume_shares":int(c.get("volume") or 0),"source_name":"kite_broker","content_fingerprint":fp})
    return ops


def run(*,limit=30,apply=False,d1=None,broker=None):
    d1=d1 or D1IngestClient.from_env();broker=broker or KiteBrokerClient.from_env()
    targets=d1.market_ipos(limit=limit);allowed=[str(x["nse_symbol"]).upper() for x in targets if x.get("nse_symbol")]
    report={"selected":len(targets),"rows_5m":0,"rows_1d":0,"ipos_written":0,"failures":[]}
    today=dt.date.today()
    for row in targets:
        sym=str(row.get("nse_symbol") or "").upper()
        try:
            start=_day(row["listing_date"]);end=min(today,_day(row.get("lock30_date") or (start+dt.timedelta(days=30))))
            if end<start: continue
            # Worker enforces <=45 days and only these two intervals.
            five=broker.historical(symbol=sym,allowed_symbols=allowed,from_date=start.isoformat(),to_date=end.isoformat(),interval="5minute")
            daily=broker.historical(symbol=sym,allowed_symbols=allowed,from_date=start.isoformat(),to_date=end.isoformat(),interval="day")
            ops=_ops(int(row["id"]),"5m",five)+_ops(int(row["id"]),"1d",daily)
            report["rows_5m"]+=len(five);report["rows_1d"]+=len(daily)
            if apply and ops:
                d1.batch(ops,chunk_size=250);report["ipos_written"]+=1
        except Exception as exc:
            report["failures"].append({"ipo_id":row.get("id"),"symbol":sym,"error":f"{type(exc).__name__}:{exc}"})
    return report


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--limit",type=int,default=30);ap.add_argument("--apply",action="store_true")
    a=ap.parse_args(argv);rep=run(limit=max(1,min(a.limit,100)),apply=a.apply)
    print("D1_CANDLES_SUMMARY="+json.dumps(rep,sort_keys=True,default=str));return 1 if rep["failures"] else 0
if __name__=="__main__":raise SystemExit(main())
