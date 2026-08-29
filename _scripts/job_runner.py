#!/usr/bin/env python3
"""VM side of the Admin job console. Queue state lives in D1 via the ingest Worker."""
import datetime,os,subprocess,sys,traceback
HERE=os.path.dirname(os.path.abspath(__file__));REPO=os.path.dirname(HERE);PIPELINE=os.path.join(REPO,"pipeline")
if PIPELINE not in sys.path:sys.path.insert(0,PIPELINE)
from d1_ingest import D1IngestClient

def _throttled():
    now_ist=datetime.datetime.utcnow()+datetime.timedelta(hours=5,minutes=30)
    active=now_ist.weekday()<6 and (7<=now_ist.hour<23 or (now_ist.hour==23 and now_ist.minute<=30))
    return (not active) and now_ist.minute%10!=0

def _flag_pending():
    key=os.getenv("ADMIN_JOB_KEY","")
    if not key:return None
    try:
        import urllib.request,json as _j
        req=urllib.request.Request("https://aacapitalprivatelimited.com/api/admin/job-flag",headers={"X-AAC-Key":key,"User-Agent":"aac-runner"})
        d=_j.load(urllib.request.urlopen(req,timeout=10));return bool(d.get("pending")) if d.get("ok") else None
    except Exception:return None

def _should_exit_idle():
    p=_flag_pending()
    if p is False:return True
    if p is None and _throttled():return True
    return False

def _clear_flag():
    key=os.getenv("ADMIN_JOB_KEY","")
    if not key:return
    try:
        import urllib.request
        req=urllib.request.Request("https://aacapitalprivatelimited.com/api/admin/job-flag",headers={"X-AAC-Key":key,"User-Agent":"aac-runner"},method="DELETE")
        urllib.request.urlopen(req,timeout=10)
    except Exception:pass

# Only current D1-safe jobs stay exposed. Historical Neon-era utilities are deliberately
# absent so one phone tap can never wake or mutate the retired database.
JOBS={
    "pipeline":["pipeline/d1_cron.py","--apply"],
    "pipeline_weekly":["pipeline/d1_cron.py","--apply"],
    "ipo_lifecycle":["pipeline/d1_nse_lane.py","--apply"],
    "news":["pipeline/d1_street_gmp_lane.py","--apply"],
    "gmp":["pipeline/d1_street_gmp_lane.py","--apply"],
    "token":["_scripts/refresh_kite_token.py"],
    "sync":["_scripts/git_sync.py"],
}

def run_job(job):
    cmd=JOBS.get(job)
    if not cmd:return 2,"",f"unknown/retired job '{job}'"
    p=subprocess.run([sys.executable]+cmd,cwd=REPO,capture_output=True,text=True,timeout=6*3600)
    out=((p.stdout or "")+("\n"+p.stderr if p.stderr else "")).strip();tail="\n".join(out.splitlines()[-60:]);err=None
    if p.returncode!=0:
        lines=(p.stderr or out).strip().splitlines();err=lines[-1] if lines else f"exit {p.returncode}"
    return p.returncode,tail,err

def main():
    if _should_exit_idle():return
    try:client=D1IngestClient.from_env();client.health()
    except Exception as exc:
        print(f"D1 job queue unavailable: {type(exc).__name__}: {exc}");return
    processed=0
    while True:
        claimed=client.claim_job()
        if not claimed:
            _clear_flag();break
        jid=int(claimed["id"]);job=str(claimed["job"])
        try:
            code,tail,err=run_job(job);client.finish_job(jid,status="done" if code==0 else "failed",exit_code=code,error=err,log_tail=tail)
        except Exception as exc:
            client.finish_job(jid,status="failed",exit_code=-1,error=str(exc)[:300],log_tail=traceback.format_exc()[-2000:])
        processed+=1
    if processed:print(f"{datetime.datetime.now():%H:%M} ran {processed} D1 job(s)")
if __name__=="__main__":main()
