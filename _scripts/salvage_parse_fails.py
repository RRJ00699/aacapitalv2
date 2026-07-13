#!/usr/bin/env python3
"""
salvage_parse_fails.py — batch-recover parse-error RHPs for FREE (no API cost).
Finds every _raw.txt whose _summary.json is missing OR lacks a 'verdict',
re-parses the saved raw response (brace-balancing recovery), writes clean JSON.
  python _scripts/salvage_parse_fails.py --dir rhp_summaries
"""
import sys, json, io, os, glob, argparse
try: sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
except Exception: pass

def parse_json(text):
    text=text.strip()
    if text.startswith("```"): text=text.split("```")[1].replace("json","",1)
    i=text.find("{")
    if i<0: return {}
    body=text[i:]; j=body.rfind("}")
    if j>0:
        try: return json.loads(body[:j+1])
        except Exception: pass
    cut=max(body.rfind(","),body.rfind("}"),body.rfind("]"))
    frag=(body[:cut] if cut>0 else body).rstrip().rstrip(",")
    frag+="]"*max(0,frag.count("[")-frag.count("]"))+"}"*max(0,frag.count("{")-frag.count("}"))
    try: return json.loads(frag)
    except Exception: return {}

ap=argparse.ArgumentParser(); ap.add_argument("--dir",default="rhp_summaries"); a=ap.parse_args()
raws=glob.glob(os.path.join(a.dir,"*_raw.txt"))
recovered=0; skipped=0; failed=[]
for raw in raws:
    summ=raw.replace("_raw.txt","_summary.json")
    # already good? skip
    if os.path.exists(summ):
        try:
            d=json.load(open(summ,encoding="utf-8"))
            if d.get("verdict"): skipped+=1; continue
        except Exception: pass
    # try to salvage
    try:
        text=open(raw,encoding="utf-8").read()
        data=parse_json(text)
        if data.get("verdict"):
            json.dump(data,open(summ,"w",encoding="utf-8"),indent=2,ensure_ascii=False)
            recovered+=1
            print(f"  ✓ recovered {os.path.basename(summ)} -> {data.get('verdict')}")
        else:
            failed.append(os.path.basename(raw))
    except Exception as e:
        failed.append(f"{os.path.basename(raw)} ({str(e)[:40]})")

print(f"\nrecovered={recovered}  already-good={skipped}  still-failed={len(failed)}")
if failed:
    print("still failed (raw text too broken):")
    for f in failed: print(f"    {f}")
