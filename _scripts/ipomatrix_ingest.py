#!/usr/bin/env python3
"""
ipomatrix_ingest.py — FULL IPOMatrix ingester via the private API (gold standard).
One POST per IPO -> fills 24 fields across factors 1,2,3,4,7,9.
Adds 5 missing columns first (idempotent). JWT read from IPOMATRIX_COOKIE in .env.local.

  python _scripts/ipomatrix_ingest.py --id 2573 --raw   # preview one IPO's mapped fields
  python _scripts/ipomatrix_ingest.py --limit 5         # dry-run 5
  python _scripts/ipomatrix_ingest.py --apply           # full write (COALESCE — won't overwrite)
"""
import os,sys,io,re,json,time,argparse,urllib.parse
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
                    dec=urllib.parse.unquote(line.split("=",1)[1].strip().strip('"').strip("'"))
                    m=re.search(r'"accessToken"\s*:\s*"([^"]+)"',dec)
                    if m: return m.group(1)
    return os.environ.get("IPOMATRIX_JWT")

def post(jwt,ipo_id,timeout=30):
    body=json.dumps({"id":int(ipo_id)}).encode()
    hdr={"content-type":"application/json","accept":"application/json, text/plain, */*",
         "origin":"https://www.ipomatrix.com","referer":"https://www.ipomatrix.com/",
         "user-agent":UA,"x-access-token":jwt}
    try:
        from curl_cffi import requests as creq
        return creq.post(API,data=body,headers=hdr,impersonate="chrome",timeout=timeout).json()
    except ImportError:
        import urllib.request as u
        return json.loads(u.urlopen(u.Request(API,data=body,headers=hdr,method="POST"),timeout=timeout).read().decode("utf-8","replace"))

def num(v):
    """'1,281.10' or '11961618350.29' -> float; cr-amounts left as-is (raw is rupees)."""
    if v is None or v=="": return None
    try: return float(str(v).replace(",","").replace("%",""))
    except Exception: return None

def cr(v):
    """raw rupees -> crore (÷1e7). API amt_cr fields are actually raw rupees in some places."""
    n=num(v)
    return round(n/1e7,2) if n and n>1e6 else n

def extract(js):
    """map API json -> {db_column: value}. Uses exact paths from the Clean Max response."""
    d=js.get("data",{}) if isinstance(js,dict) else {}
    idt=d.get("issue_details",{}) or {}
    kpi=d.get("kpi",{}) or {}
    anc=d.get("anchor",{}) or {}
    sub=(d.get("subscription",{}) or {}).get("summary",{}) or {}
    pph=d.get("pre_post_holding",{}) or {}
    mc=d.get("market_cap",{}) or {}
    # listing: prefer NSE exchange row
    lo=lh=ll=lc=None
    for ex in (d.get("listing",{}) or {}).get("exchanges",[]) or []:
        if ex.get("exchange")=="NSE":
            lo,lh,ll,lc=ex.get("open"),ex.get("high"),ex.get("low"),ex.get("close")
    # anchors
    names=[]
    for it in anc.get("investors",[]) or []:
        nm=(it.get("investor_name") or "").strip()
        if nm: names.append(nm)
    # brlm
    brlm=[m.get("comp_short_name") or m.get("comp_name") for m in idt.get("lead_managers",[]) or []]
    reg=(idt.get("registrar",{}) or {}).get("name")

    out={
      "price_band_low":num(idt.get("price_band_lower")),
      "price_band_high":num(idt.get("price_band_upper")),
      "issue_price":num(idt.get("final_price")),
      "ofs_cr":cr(idt.get("ttl_ofs_amt_cr")),
      "fresh_issue_cr":cr(idt.get("ttl_fresh_issue_amt_cr")),
      "anchor_names":json.dumps(names) if names else None,
      "anchor_count":len(names) or None,
      "anchor_total_cr":num(anc.get("total_amount_cr")),
      "anchor_pct_issue":num(anc.get("total_issue_percentage")),
      "ipo_pe":num(kpi.get("pe_ratio")),
      "ipo_pb":num(kpi.get("price_to_book")),
      "roe":num(kpi.get("roe")),
      "debt_equity":num(kpi.get("debt_equity")),
      "brlm_names":json.dumps([b for b in brlm if b]) if brlm else None,
      "registrar":reg,
      "qib_subscription":num(sub.get("qib")),
      "nii_subscription":num(sub.get("nii")),
      "rii_subscription":num(sub.get("rii")),
      "total_subscription":num(sub.get("total")),
      "listing_open":num(lo),"listing_high":num(lh),"listing_low":num(ll),"listing_close":num(lc),
      "mcap_offer":num(mc.get("at_offer_price")),
      "promoter_holding_post":num(pph.get("promoter_shareholding_post_issue")),
    }
    return {k:v for k,v in out.items() if v is not None}

NEW_COLS={  # column: sql type — added if missing
  "anchor_pct_issue":"NUMERIC","registrar":"TEXT","rii_subscription":"NUMERIC",
  "listing_close":"NUMERIC","mcap_offer":"NUMERIC","anchor_total_cr":"NUMERIC",
}

def resolve_ids(jwt):
    """Pull ALL IPO ids from IPOMatrix report 82 (Mainboard IPOs by year) via
    media-report-data-read. The Company link carries /ipo/<slug>/<id>/.
    Returns symbol->id, name->id, isin->id."""
    import urllib.request as u
    LIST="https://alphanodejs.chittorgarh.com/api/media-report-data-read"
    def post(body):
        data=json.dumps(body).encode()
        hdr={"content-type":"application/json","accept":"application/json, text/plain, */*",
             "origin":"https://www.ipomatrix.com","referer":"https://www.ipomatrix.com/",
             "user-agent":UA,"x-access-token":jwt}
        try:
            from curl_cffi import requests as creq
            return creq.post(LIST,data=data,headers=hdr,impersonate="chrome",timeout=35).json()
        except ImportError:
            return json.loads(u.urlopen(u.Request(LIST,data=data,headers=hdr,method="POST"),timeout=35).read().decode("utf-8","replace"))
    def norm(x): return re.sub(r'[^a-z0-9]','',(x or '').lower())
    sym,name,isin={},{},{}
    for yr in range(2010,2027):
        pg=1
        while True:
            try:
                d=post({"id":82,"pageno":pg,"month":7,"year":str(yr),"fy":"2026-27","sort":"0",
                        "param_id":"mainboard","sub_param_id":"0","search":"","extraParam":"",
                        "minplandate":"2006-01-01"})
            except Exception:
                break
            rows=d.get("reportTableData") or []
            if not rows: break
            for row in rows:
                comp=str(row.get("Company",""))
                m=re.search(r"/ipo/([^/]+)/(\d+)/",comp)
                cid=int(m.group(2)) if m else None
                if not cid: continue
                sy=str(row.get("~nse_symbol") or "").upper().strip()
                nm=row.get("~compare_name") or row.get("~IPO")
                isn=str(row.get("~isin") or "").upper().strip()
                if sy: sym[sy]=cid
                if nm: name[norm(nm)]=cid
                if isn: isin[isn]=cid
            tp=int(d.get("totalPages") or 1)
            if pg>=tp: break
            pg+=1
    print(f"  resolved from report 82: {len(sym)} sym, {len(name)} name, {len(isin)} isin")
    return sym,name,isin
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=0);ap.add_argument("--apply",action="store_true")
    ap.add_argument("--id",type=int);ap.add_argument("--raw",action="store_true")
    ap.add_argument("--only-null",action="store_true",help="only IPOs missing anchor/structure (nightly mode)")
    a=ap.parse_args()
    jwt=load_jwt()
    if not jwt:
        print("IPOMatrix JWT missing/stale — SKIPPING enrichment (set IPOMATRIX_COOKIE in .env.local). "
              "New IPOs keep Chittorgarh data; anchors fill when the cookie is refreshed.")
        sys.exit(0)   # clean exit — nightly continues

    if a.id and a.raw:
        js=post(jwt,a.id); fields=extract(js)
        print(f"mapped {len(fields)} fields for id {a.id}:")
        for k,v in fields.items():
            sv=str(v); print(f"   {k:24} = {sv[:60]}")
        return

    DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()
    # add missing columns (idempotent)
    if a.apply:
        for col,typ in NEW_COLS.items():
            cur.execute(f'ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS "{col}" {typ}')
        conn.commit()

    null_filter = " AND (anchor_count IS NULL OR ofs_pct IS NULL OR fresh_issue_cr IS NULL)" if a.only_null else ""
    cur.execute(f"""SELECT id, UPPER(COALESCE(NULLIF(nse_symbol,''),symbol)), company_name, UPPER(COALESCE(isin,''))
                   FROM ipo_intelligence WHERE listing_date IS NOT NULL{null_filter}
                   ORDER BY listing_date DESC""")
    todo=cur.fetchall()
    def norm(s): return re.sub(r'[^a-z0-9]','',(s or '').lower())
    print(f"IPOs: {len(todo)} | resolving ids via IPOMatrix list API...")
    sym,name,isin=resolve_ids(jwt)

    filled=fetched=0
    for pid,s,cnm,isn in todo:
        cid=sym.get(s) or name.get(norm(cnm)) or (isin.get(isn) if isn else None)
        if not cid: continue
        fetched+=1
        try: js=post(jwt,cid)
        except Exception as e: print(f"  {s or cnm}: {str(e)[:40]}"); continue
        fields=extract(js)
        if not fields: print(f"  {s or cnm}: empty"); continue
        print(f"  {(s or cnm)[:18]:18} {len(fields):2} fields  anchors={fields.get('anchor_count','-')}")
        if a.apply and fields:
            sets=", ".join(f'"{k}"=COALESCE("{k}",%s)' for k in fields)
            cur.execute(f"UPDATE ipo_intelligence SET {sets} WHERE id=%s",list(fields.values())+[pid])
            conn.commit()
        filled+=1; time.sleep(0.4)
        if a.limit and fetched>=a.limit: break
    print(f"{'WROTE' if a.apply else 'DRY'}: {filled}/{fetched}")
    conn.close()

if __name__=="__main__": main()
