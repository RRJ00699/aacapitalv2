#!/usr/bin/env python3
"""
ipomatrix_ingest.py — FULL IPOMatrix ingester via the private API (gold standard).
One POST per IPO -> fills 24 fields across factors 1,2,3,4,7,9.
Adds 5 missing columns first (idempotent). JWT read from IPOMATRIX_COOKIE in .env.local.

  python _scripts/ipomatrix_ingest.py --id 2573 --raw   # preview one IPO's mapped fields
  python _scripts/ipomatrix_ingest.py --limit 5         # dry-run 5
  python _scripts/ipomatrix_ingest.py --apply           # full write (COALESCE — won't overwrite)
"""
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__))))
from lib.canon import canon as _canon
import os,sys,io,re,json,time,argparse,urllib.parse
try: sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
except Exception: pass
import psycopg2

API="https://alphanodejs.chittorgarh.com/api/media-ipo/analysis"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0 Safari/537.36"

def _jwt_from_cookie(raw):
    """Extract the accessToken JWT from a raw IPOMatrix cookie string."""
    if not raw: return None
    dec=urllib.parse.unquote(raw.strip().strip('"').strip("'"))
    m=re.search(r'"accessToken"\s*:\s*"([^"]+)"',dec)
    return m.group(1) if m else None

def load_jwt():
    # 1) platform_config (admin-settable from phone, same pattern as kite_access_token).
    #    Accept either a stored raw cookie (ipomatrix_cookie) or a pre-extracted JWT.
    db=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if db:
        try:
            import psycopg2
            c=psycopg2.connect(db); cur=c.cursor()
            cur.execute("SELECT key,value FROM platform_config "
                        "WHERE key IN ('ipomatrix_cookie','ipomatrix_jwt')")
            vals={k:v for k,v in cur.fetchall()}
            cur.close(); c.close()
            jwt=_jwt_from_cookie(vals.get("ipomatrix_cookie")) or vals.get("ipomatrix_jwt")
            if jwt: return jwt
        except Exception as e:
            print(f"  (platform_config JWT lookup skipped: {e})")
    # 2) .env file fallback (legacy / local dev)
    for envf in (".env.local",".env"):
        if os.path.exists(envf):
            for line in open(envf,encoding="utf-8"):
                if line.strip().startswith("IPOMATRIX_COOKIE="):
                    jwt=_jwt_from_cookie(line.split("=",1)[1])
                    if jwt: return jwt
    # 3) direct env var
    return os.environ.get("IPOMATRIX_JWT")

class CookieExpired(Exception):
    """Raised when IPOMatrix rejects the JWT (401/403) — the cookie needs refreshing in admin."""

def post(jwt,ipo_id,timeout=30):
    body=json.dumps({"id":int(ipo_id)}).encode()
    hdr={"content-type":"application/json","accept":"application/json, text/plain, */*",
         "origin":"https://www.ipomatrix.com","referer":"https://www.ipomatrix.com/",
         "user-agent":UA,"x-access-token":jwt}
    try:
        from curl_cffi import requests as creq
        r=creq.post(API,data=body,headers=hdr,impersonate="chrome",timeout=timeout)
        if r.status_code in (401,403):
            raise CookieExpired(f"IPOMatrix returned {r.status_code} — the cookie is EXPIRED. "
                                "Refresh 'ipomatrix_cookie' in admin (Settings/Secrets) and re-run.")
        return r.json()
    except ImportError:
        import urllib.request as u, urllib.error as ue
        try:
            return json.loads(u.urlopen(u.Request(API,data=body,headers=hdr,method="POST"),timeout=timeout).read().decode("utf-8","replace"))
        except ue.HTTPError as e:
            if e.code in (401,403):
                raise CookieExpired(f"IPOMatrix returned {e.code} — the cookie is EXPIRED. "
                                    "Refresh 'ipomatrix_cookie' in admin (Settings/Secrets) and re-run.")
            raise

def num(v):
    """'1,281.10' or '11961618350.29' -> float; cr-amounts left as-is (raw is rupees)."""
    if v is None or v=="": return None
    try: return float(str(v).replace(",","").replace("%",""))
    except Exception: return None

def cr(v):
    """raw rupees -> crore (÷1e7). API amt_cr fields are actually raw rupees in some places."""
    n=num(v)
    return round(n/1e7,2) if n and n>1e6 else n

def discover_unmapped(d):
    """DISCOVERY (2026-07-21): owner reports the JSON carries a peer-PE
    column; the mapper reads only pe_ratio/price_to_book/roe/debt_equity
    from kpi. We do NOT guess field names — this dumps unmapped kpi keys and
    any peer/industry-ish keys so the real name can be wired precisely.
    Pure function, called ONLY from main's --raw path.
    (2026-07-21 incident: v1 of this probe referenced the argparse namespace
    inside extract(), where it is not in scope — NameError on every pipeline
    run. Executed tests now cover extract() directly.)"""
    kpi=d.get("kpi",{}) or {}
    _mapped={"pe_ratio","price_to_book","roe","debt_equity"}
    _un=sorted(k for k in kpi.keys() if k not in _mapped)
    if _un: print(f"  [discovery] unmapped kpi keys: {_un}")
    _cand=[k for k in d.keys() if "peer" in k.lower() or "industr" in k.lower()]
    if _cand: print(f"  [discovery] peer/industry top-level keys: { {k:d[k] for k in _cand} }")


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
      # [discovery] keys from the owner's --raw evidence (2026-07-23). The
      # *_2 variants are the later-period restatement — prefer plain, fall
      # back to _2. peer_analysis is stored whole (dated peer table).
      "ronw":num(kpi.get("ronw") if kpi.get("ronw") is not None else kpi.get("ronw_2")),
      "roce":num(kpi.get("roce") if kpi.get("roce") is not None else kpi.get("roce_2")),
      "eps_pre":num(kpi.get("eps_pre")),
      "eps_post":num(kpi.get("eps_post")),
      "ebitda_margin":num(kpi.get("ebitda_margin") if kpi.get("ebitda_margin") is not None else kpi.get("ebitda_margin_2")),
      "pat_margin":num(kpi.get("pat_margin") if kpi.get("pat_margin") is not None else kpi.get("pat_margin_2")),
      "nav_per_share":num(kpi.get("nav") if kpi.get("nav") is not None else kpi.get("nav_2")),
      "post_pe_ratio":num(kpi.get("post_pe_ratio")),
      "market_cap_kpi_cr":num(kpi.get("market_cap_cr")),
      "kpi_as_of":(kpi.get("latest_fy_dt") or kpi.get("latest_financial_dt") or kpi.get("as_of_date")),
      "peer_json":json.dumps(d.get("peer_analysis")) if isinstance(d.get("peer_analysis"),dict) and d.get("peer_analysis",{}).get("data") else None,
    }
    return {k:v for k,v in out.items() if v is not None}

NEW_COLS={  # column: sql type — added if missing
  "anchor_pct_issue":"NUMERIC","registrar":"TEXT","rii_subscription":"NUMERIC",
  "listing_close":"NUMERIC","mcap_offer":"NUMERIC","anchor_total_cr":"NUMERIC",
  "ronw":"NUMERIC","roce":"NUMERIC","eps_pre":"NUMERIC","eps_post":"NUMERIC",
  "ebitda_margin":"NUMERIC","pat_margin":"NUMERIC","nav_per_share":"NUMERIC",
  "post_pe_ratio":"NUMERIC","market_cap_kpi_cr":"NUMERIC","kpi_as_of":"TEXT",
  "peer_json":"JSONB",
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
    norm = _canon  # shared canonicalizer (_scripts/lib/canon.py)
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
    ap.add_argument("--upcoming", action="store_true",
        help="re-pull IPOs listing today or later (IPOMatrix drip-feeds: details -> band -> anchors over days; fill-once misses updates). New non-null values WIN for these rows.")
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
        discover_unmapped((js.get("data") or js) if isinstance(js,dict) else {})
        return

    DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()
    # add missing columns (idempotent)
    if a.apply:
        for col,typ in NEW_COLS.items():
            cur.execute(f'ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS "{col}" {typ}')
        conn.commit()

    # NOTE: ofs_pct is NOT included here on purpose. IPOMatrix extract() produces
    # ofs_cr / fresh_issue_cr but never ofs_pct (that's computed downstream from
    # ofs_cr÷total). Including ofs_pct made --only-null re-pull the same ~139 rows
    # every night forever, since this job can never fill it. Filter on the fields
    # IPOMatrix actually provides.
    null_filter = " AND (anchor_count IS NULL OR fresh_issue_cr IS NULL OR ofs_cr IS NULL)" if a.only_null else ""
    if a.upcoming:
        # Drip-feed window: rows listing today or later (or undated) always re-pull,
        # regardless of what's already filled — IPOMatrix keeps adding fields.
        null_filter = (" AND ((listing_date IS NULL OR listing_date >= CURRENT_DATE)"
                       " OR (anchor_count IS NULL OR fresh_issue_cr IS NULL OR ofs_cr IS NULL))")
    cur.execute(f"""SELECT id, UPPER(COALESCE(NULLIF(nse_symbol,''),symbol)), company_name, UPPER(COALESCE(isin,''))
                   FROM ipo_intelligence WHERE listing_date IS NOT NULL{null_filter}
                   ORDER BY listing_date DESC""")
    todo=cur.fetchall()
    norm = _canon  # shared canonicalizer (_scripts/lib/canon.py)
    print(f"IPOs: {len(todo)} | resolving ids via IPOMatrix list API...")
    sym,name,isin=resolve_ids(jwt)

    filled=fetched=0
    for pid,s,cnm,isn in todo:
        cid=sym.get(s) or name.get(norm(cnm)) or (isin.get(isn) if isn else None)
        if not cid: continue
        fetched+=1
        try: js=post(jwt,cid)
        except CookieExpired as e:
            print(f"\n⛔ {e}\n   Stopping — no point retrying every IPO with a dead cookie.")
            break
        except Exception as e: print(f"  {s or cnm}: {str(e)[:40]}"); continue
        fields=extract(js)
        if not fields: print(f"  {s or cnm}: empty"); continue
        print(f"  {(s or cnm)[:18]:18} {len(fields):2} fields  anchors={fields.get('anchor_count','-')}")
        if a.apply and fields:
            if a.upcoming:
                # Pre-listing window: NEW value wins when non-null (drip-feed truth);
                # existing kept only when IPOMatrix sends nothing. Rakesh-approved
                # exception (2026-07-16) to the default fill-empty rule — anchors
                # grow, bands firm; stale values must not stick until listing.
                sets=", ".join(f'"{k}"=COALESCE(%s,"{k}")' for k in fields)
            else:
                sets=", ".join(f'"{k}"=COALESCE("{k}",%s)' for k in fields)
            cur.execute(f"UPDATE ipo_intelligence SET {sets} WHERE id=%s",list(fields.values())+[pid])
            conn.commit()
        filled+=1; time.sleep(0.4)
        if a.limit and fetched>=a.limit: break
    print(f"{'WROTE' if a.apply else 'DRY'}: {filled}/{fetched}")
    conn.close()

if __name__=="__main__": main()
