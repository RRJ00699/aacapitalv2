#!/usr/bin/env python3
"""AACapital production D1 cron.

Order requested by owner:
  1. SEBI RHP download -> immutable R2 -> Sonnet -> D1
  2. NSE official discovery / issue / subscriptions -> D1 spine
  3. SBI note -> R2 -> Sonnet -> D1; NSE anchor PDF -> Sonnet facts -> discard PDF
  4. listing-day pre-open order book -> D1
  5. Kite 5m + daily candles listing->lock30 -> D1
Then: street/GMP context -> deterministic pro-forma/fair value -> KV snapshots.

A plain run is dry-run: it may perform free discovery/downloads but cannot write R2/D1
or call paid Sonnet extraction. --apply is the explicit production switch.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import traceback
import uuid

ROOT=pathlib.Path(__file__).resolve().parents[1]
PIPELINE=ROOT/"pipeline"
if str(PIPELINE) not in sys.path:sys.path.insert(0,str(PIPELINE))
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from d1_ingest import D1IngestClient,fingerprint
from d1_documents_lane import (SBI_DIR_DEFAULT,ingest_rhps,ingest_sbi_notes,run_sbi_download,run_sebi_download)
from d1_nse_lane import run as run_nse
from d1_anchor_lane import run as run_anchors
from d1_preopen_lane import capture as run_preopen
from d1_candles_lane import run as run_candles
from d1_street_gmp_lane import run as run_street_gmp
from d1_valuation_lane import run as run_valuation
from d1_snapshot_publish import run as publish_snapshots
from r2 import R2DocumentStore

VERSION="d1-cron-v1"


def now():return dt.datetime.now(dt.timezone.utc).isoformat()

def config_state():
    required=("D1_INGEST_URL","D1_INGEST_AUTH_SECRET")
    paid=("ANTHROPIC_API_KEY",)
    r2=("R2_ACCOUNT_ID","R2_ACCESS_KEY_ID","R2_SECRET_ACCESS_KEY","R2_DOCUMENT_BUCKET")
    broker=("KITE_BROKER_PROXY_URL","KITE_BROKER_PROXY_AUTH_SECRET")
    publish=("SNAPSHOT_PUBLISH_URL","SNAPSHOT_PUBLISH_KEY")
    return {"required":{k:bool(os.environ.get(k)) for k in required},
            "paid":{k:bool(os.environ.get(k)) for k in paid},
            "r2":{k:bool(os.environ.get(k)) for k in r2},
            "broker":{k:bool(os.environ.get(k)) for k in broker},
            "publish":{k:bool(os.environ.get(k)) for k in publish},
            "sbi_owner_approved":os.environ.get("SBI_SONNET_OWNER_APPROVED")=="YES"}

def failures_in(value):
    if isinstance(value,dict):
        n=len(value.get("failures") or [])
        return n+sum(failures_in(v) for k,v in value.items() if k!="failures")
    if isinstance(value,list):return sum(failures_in(v) for v in value)
    return 0

def cost_in(value):
    if isinstance(value,dict):
        total=float(value.get("cost_usd") or 0)
        return total+sum(cost_in(v) for k,v in value.items() if k!="cost_usd")
    if isinstance(value,list):return sum(cost_in(v) for v in value)
    return 0.0

class Run:
    def __init__(self,client,apply):
        self.client=client;self.apply=apply;self.id=f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}";self.started=now();self.results={};self.paid=0.0
        if apply:self.client.op({"op":"pipeline_run_start","run_id":self.id,"started_at":self.started,"mode":"live","orchestrator_version":VERSION,"summary_json":{"config":config_state()}})
    def lane(self,name,fn):
        started=now();print(f"\n=== {name}")
        try:
            result=fn();status="partial" if failures_in(result) else "ok"
        except Exception as exc:
            result={"failures":[{"error":f"{type(exc).__name__}:{exc}"}],"traceback":"\n".join(traceback.format_exc().splitlines()[-10:])};status="failed"
        self.results[name]=result;self.paid+=cost_in(result);finished=now();print(json.dumps({"lane":name,"status":status,"result":result},default=str,sort_keys=True))
        if self.apply:
            self.client.op({"op":"pipeline_event","run_id":self.id,"lane":name,"started_at":started,"finished_at":finished,"status":status,
                "counts_json":{k:v for k,v in result.items() if isinstance(v,(int,float))} if isinstance(result,dict) else {},"detail_json":result,
                "event_fingerprint":fingerprint(self.id,name,started,status,json.dumps(result,sort_keys=True,default=str))})
        return status,result
    def finish(self):
        bad=sum(failures_in(v) for v in self.results.values());status="ok" if bad==0 else "partial";summary={"run_id":self.id,"status":status,"failures":bad,"paid_cost_usd":round(self.paid,6),"lanes":self.results}
        if self.apply:self.client.op({"op":"pipeline_run_finish","run_id":self.id,"finished_at":now(),"status":status,"paid_cost_usd":round(self.paid,6),"summary_json":summary})
        print("D1_CRON_SUMMARY="+json.dumps(summary,sort_keys=True,default=str));return 0 if status=="ok" else 2

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--apply",action="store_true");ap.add_argument("--limit",type=int,default=25);ap.add_argument("--max-rhps",type=int,default=4);ap.add_argument("--max-sbi",type=int,default=8);ap.add_argument("--skip-download",action="store_true");a=ap.parse_args(argv)
    limit=max(1,min(a.limit,50));cfg=config_state();print("D1 PIPELINE PREFLIGHT="+json.dumps(cfg,sort_keys=True))
    if not all(cfg["required"].values()):raise SystemExit("D1 ingest Worker URL/secret missing — refusing any fallback database")
    client=D1IngestClient.from_env();print("D1 ingest health="+json.dumps(client.health(),sort_keys=True));run=Run(client,a.apply)
    store=R2DocumentStore() if a.apply else None

    # 1. RHP first. Download before NSE as requested; exact unresolved names are retried after NSE fills the spine.
    if not a.skip_download:
        run.lane("01_sebi_rhp_download",lambda:{"returncode":(p:=run_sebi_download(max_rhps=a.max_rhps)).returncode,"stdout_tail":(p.stdout or "")[-1200:],"failures":[] if p.returncode==0 else [{"stderr":(p.stderr or "")[-1200:]}]})
    run.lane("01_sebi_rhp_r2_sonnet",lambda:ingest_rhps(client=client,store=store,max_extract=a.max_rhps,apply=a.apply))

    # 2. NSE is the identity/lifecycle/terms/subscription authority.
    run.lane("02_nse_official",lambda:run_nse(limit=limit,apply=a.apply,client=client))
    # Retry any RHP that could not resolve before NSE discovery. D1 extraction guard prevents a second paid call.
    run.lane("02b_rhp_identity_retry",lambda:ingest_rhps(client=client,store=store,max_extract=a.max_rhps,apply=a.apply))

    # 3. SBI notes retained in R2; anchors are transient and discarded after extraction.
    if not a.skip_download:
        run.lane("03_sbi_download",lambda:{"returncode":(p:=run_sbi_download(out_dir=SBI_DIR_DEFAULT)).returncode,"stdout_tail":(p.stdout or "")[-1200:],"failures":[] if p.returncode==0 else [{"stderr":(p.stderr or "")[-1200:]}]})
    run.lane("03_sbi_r2_sonnet",lambda:ingest_sbi_notes(client=client,store=store,directory=SBI_DIR_DEFAULT,max_extract=a.max_sbi,apply=a.apply))
    run.lane("03_anchor_extract_discard",lambda:run_anchors(limit=limit,apply=a.apply,client=client))

    # 4. Pre-open is window-gated; outside 08:55-10:05 IST it honestly skips.
    run.lane("04_preopen_orderbook",lambda:run_preopen(limit=min(limit,10),apply=a.apply,d1=client))

    # 5. Listing->lock30 market history. 5m + daily only; 15m is derived, never stored.
    run.lane("05_kite_candles",lambda:run_candles(limit=limit,apply=a.apply,d1=client))

    # Context then deterministic calculations. GMP remains context, not a signal.
    run.lane("06_street_and_gmp",lambda:run_street_gmp(limit=limit,apply=a.apply,client=client))
    run.lane("07_proforma_fair_value",lambda:run_valuation(limit=limit,apply=a.apply,client=client))

    # Public app is KV-only: publication is part of a successful production run, never optional drift.
    if a.apply:run.lane("08_publish_kv_snapshots",lambda:publish_snapshots(limit=limit,client=client))
    else:run.results["08_publish_kv_snapshots"]={"status":"skipped","reason":"dry-run"}
    return run.finish()

if __name__=="__main__":raise SystemExit(main())
