#!/usr/bin/env python3
"""
ipomatrix_api.py — GOLD-STANDARD IPOMatrix data via its private API.
POST https://alphanodejs.chittorgarh.com/api/media-ipo/analysis  {"id": <ipomatrix_id>}
with header x-access-token: <JWT>. Returns full IPO JSON (anchors, GMP, subscription,
financials). No browser, no scraping — one POST per IPO.

JWT: read from IPOMATRIX_COOKIE in .env.local (the accessToken inside it). Never in code.

  python _scripts/ipomatrix_api.py --limit 3          # test (dry) — dumps what fields exist
  python _scripts/ipomatrix_api.py --apply            # write anchor_names+count
  python _scripts/ipomatrix_api.py --id 2573 --raw    # dump one IPO's full JSON (explore)
"""
import os, sys, io, re, json, time, argparse, urllib.parse
try: sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
except Exception: pass
import psycopg2

API="https://alphanodejs.chittorgarh.com/api/media-ipo/analysis"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0 Safari/537.36"

def load_jwt():
    for envf in (".env.local",".env"):
        if os.path.exists(envf):
            for line in open(envf,encoding="utf-8"):
                if line.strip().startswith("IPOMATRIX_COOKIE="):
                    raw=line.split("=",1)[1].strip().strip('"').strip("'")
                    # cookie has user={...%22accessToken%22:%22<JWT>%22...}
                    dec=urllib.parse.unquote(raw)
                    m=re.search(r'"accessToken"\s*:\s*"([^"]+)"', dec)
                    if m: return m.group(1)
    return os.environ.get("IPOMATRIX_JWT")

def post(jwt, ipo_id, timeout=30):
    body=json.dumps({"id":int(ipo_id)}).encode()
    hdr={"content-type":"application/json","accept":"application/json, text/plain, */*",
         "origin":"https://www.ipomatrix.com","referer":"https://www.ipomatrix.com/",
         "user-agent":UA,"x-access-token":jwt}
    try:
        from curl_cffi import requests as creq
        r=creq.post(API,data=body,headers=hdr,impersonate="chrome",timeout=timeout)
        return r.json()
    except ImportError:
        import urllib.request as u
        req=u.Request(API,data=body,headers=hdr,method="POST")
        return json.loads(u.urlopen(req,timeout=timeout).read().decode("utf-8","replace"))

def find_anchors(js):
    """Return investor names from data.anchor.investors[].investor_name.
    Ignores the qib_anchor_breakdown category headers (FI'S/BANK, MF's, ...)."""
    data = js.get("data", js) if isinstance(js, dict) else {}
    anchor = data.get("anchor") if isinstance(data, dict) else None
    names, groups = [], []
    if isinstance(anchor, dict):
        investors = anchor.get("investors")
        if isinstance(investors, list):
            for it in investors:
                if not isinstance(it, dict): continue
                nm = (it.get("investor_name") or "").strip()
                gp = (it.get("mutual_fund_name") or "").strip()
                if nm and len(nm) > 2:
                    names.append(nm); groups.append(gp or nm)
    seen=set(); out=[]
    for n in names:
        if n not in seen: seen.add(n); out.append(n)
    return out, groups

def resolve_ids():
    """symbol/name -> ipomatrix id from Chittorgarh report 82."""
    import urllib.request as u
    def get(url):
        try:
            from curl_cffi import requests as creq
            return json.loads(creq.get(url,impersonate="chrome",timeout=35).text)
        except ImportError:
            return json.loads(u.urlopen(u.Request(url,headers={"User-Agent":UA}),timeout=35).read().decode("utf-8","replace"))
    def norm(s): return re.sub(r'[^a-z0-9]','',(s or '').lower())
    sym,name={},{}
    for yr in range(2010,2027):
        fy=f"{yr}-{str(yr+1)[2:]}"
        try: d=get(f"https://webnodejs.chittorgarh.com/cloud/report/data-read/82/1/7/{yr}/{fy}/0/mainboard/0?search=&v=21-38")
        except Exception: continue
        for row in (d.get("reportTableData") or []):
            m=re.search(r"/ipo/([^/]+)/(\d+)/",str(row.get("Company","")))
            if not m: continue
            cid=int(m.group(2))
            sy=str(row.get("~nse_symbol") or "").upper().strip()
            if sy: sym[sy]=cid
            name[norm(row.get("~compare_name") or row.get("~IPO"))]=cid
    return sym,name

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=0)
    ap.add_argument("--apply",action="store_true")
    ap.add_argument("--id",type=int)
    ap.add_argument("--raw",action="store_true")
    a=ap.parse_args()

    jwt=load_jwt()
    if not jwt: sys.exit("No JWT — set IPOMATRIX_COOKIE in .env.local")

    if a.id and a.raw:
        js=post(jwt,a.id)
        print(json.dumps(js,indent=2)[:4000])
        print("\n--- top-level keys:",list(js.keys()) if isinstance(js,dict) else type(js))
        _names,_groups=find_anchors(js)
        print(f"--- anchors found: {len(_names)} investors")
        print("   e.g.:",_names[:8])
        print("   groups:",list(dict.fromkeys(_groups))[:8])
        return

    DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    conn=psycopg2.connect(DB,connect_timeout=25); cur=conn.cursor()
    cur.execute("""SELECT id, UPPER(COALESCE(NULLIF(nse_symbol,''),symbol)), company_name
                   FROM ipo_intelligence WHERE anchor_count IS NULL AND listing_date IS NOT NULL
                   ORDER BY listing_date DESC""")
    todo=cur.fetchall()
    print(f"IPOs needing anchors: {len(todo)}")
    def norm(s): return re.sub(r'[^a-z0-9]','',(s or '').lower())
    sym,name=resolve_ids()
    print(f"resolved ids: {len(sym)} by symbol, {len(name)} by name")

    filled=fetched=0
    for pid,s,cnm in todo:
        cid=sym.get(s) or name.get(norm(cnm))
        if not cid: continue
        fetched+=1
        try: js=post(jwt,cid)
        except Exception as e: print(f"  {s or cnm}: {str(e)[:50]}"); continue
        anchors,groups=find_anchors(js)
        if not anchors:
            print(f"  {s or cnm}: no anchors in response"); continue
        print(f"  {(s or cnm)[:20]:20} anchors={len(anchors):2}  e.g. {', '.join(anchors[:3])}")
        if a.apply:
            cur.execute("""UPDATE ipo_intelligence SET
                anchor_names=COALESCE(anchor_names,%s), anchor_count=COALESCE(anchor_count,%s)
                WHERE id=%s""",(json.dumps(anchors),len(anchors),pid))
            conn.commit()
        filled+=1
        time.sleep(0.5)
        if a.limit and fetched>=a.limit: break
    print(f"{'WROTE' if a.apply else 'DRY'}: {filled} filled / {fetched} fetched")
    conn.close()

if __name__=="__main__":
    main()
