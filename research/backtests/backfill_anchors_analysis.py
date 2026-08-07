#!/usr/bin/env python3
"""
backfill_anchors_analysis.py — fills anchor_names + anchor_count from IPOMatrix
'media-ipo/analysis' API (POST {id}). Confirmed endpoint + token + payload from
DevTools. Maps our ipo_id (== chittorgarh id) to the API's id.

Token: env IPOMATRIX_TOKEN or platform_config 'ipomatrix_token'.
Needs the master to have a chittorgarh id per IPO. Uses ipo_id if present; else
resolves via report 82 (~IPO id) — but most rows already carry it.

  python research/backtests/backfill_anchors_analysis.py --limit 5           # test
  python research/backtests/backfill_anchors_analysis.py --apply             # full
  python research/backtests/backfill_anchors_analysis.py --test-only         # backtest
"""
import os, re, sys, json, time, argparse

URL = "https://alphanodejs.chittorgarh.com/api/media-ipo/analysis"

def post(token, ipo_id):
    body = {"id": int(ipo_id)}
    try:
        from curl_cffi import requests as creq
        r = creq.post(URL, impersonate="chrome", timeout=35,
            headers={"x-access-token": token, "content-type": "application/json",
                     "origin": "https://www.ipomatrix.com"}, json=body)
        return json.loads(r.text)
    except ImportError:
        import urllib.request
        req = urllib.request.Request(URL, data=json.dumps(body).encode(),
            headers={"x-access-token": token, "content-type": "application/json",
                     "origin": "https://www.ipomatrix.com", "User-Agent": "Mozilla/5.0 Chrome/124.0"})
        return json.loads(urllib.request.urlopen(req, timeout=35).read().decode("utf-8", "replace"))

def extract_anchors(d):
    """Walk the analysis JSON for the anchor investor list. Returns list of names."""
    names = []
    def walk(o):
        if isinstance(o, dict):
            # a row that looks like an anchor investor
            for nk in ("anchor_investor", "investor_name", "AnchorInvestor", "name", "anchor_name"):
                if nk in o and isinstance(o[nk], str) and len(o[nk]) > 3:
                    v = o[nk].strip()
                    if v.lower() not in ("group / mf", "anchor investor") and not v.startswith("http"):
                        names.append(v)
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(d)
    seen = set(); out = []
    for n in names:
        if n not in seen: seen.add(n); out.append(n)
    return out

def get_token(cur):
    t = os.environ.get("IPOMATRIX_TOKEN")
    if t: return t
    try:
        cur.execute("SELECT value FROM platform_config WHERE key='ipomatrix_token'")
        r = cur.fetchone(); return r[0] if r else None
    except Exception: return None

def stats(rets):
    n=len(rets)
    if n<8: return None
    s=sorted(rets); return n,sum(1 for r in rets if r>0)/n*100,s[n//2],sum(rets)/n

def run_backtest(cur):
    cur.execute("""SELECT anchor_count, listing_gap_pct, d10_best_pct
                   FROM ipo_intelligence WHERE anchor_count IS NOT NULL AND d10_best_pct IS NOT NULL""")
    rows=cur.fetchall()
    print(f"\n=== ANCHOR COUNT vs d10 — n={len(rows)} ===")
    if len(rows)<30: print("still <30 with outcomes."); return
    def b(c): c=int(c); return "1-5" if c<=5 else "6-10" if c<=10 else "11-20" if c<=20 else "20+"
    p={}
    for c,g,d in rows: p.setdefault(b(c),[]).append(float(d))
    print(f"{'anchors':8}{'n':>5}{'win%':>7}{'med':>7}{'mean':>7}")
    for k in ("1-5","6-10","11-20","20+"):
        st=stats(p.get(k,[]))
        if st: print(f"{k:8}{st[0]:>5}{st[1]:>7.1f}{st[2]:>+7.1f}{st[3]:>+7.1f}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=0); ap.add_argument("--apply",action="store_true")
    ap.add_argument("--test-only",action="store_true"); ap.add_argument("--sleep",type=float,default=0.5)
    a=ap.parse_args()
    import psycopg2
    DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn=psycopg2.connect(DB,connect_timeout=20); cur=conn.cursor()
    if a.test_only: run_backtest(cur); return
    token=get_token(cur)
    if not token: sys.exit("no IPOMATRIX_TOKEN / platform_config ipomatrix_token")
    cols={r[0] for r in [(c,) for c in []]}
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    have_cols={r[0] for r in cur.fetchall()}
    idcol = next((c for c in ("ipo_id","chittorgarh_id","ipomatrix_id") if c in have_cols), None)
    if not idcol: sys.exit(f"no chittorgarh id column found; have: {sorted(c for c in have_cols if 'id' in c)}")
    cur.execute(f"""SELECT id, {idcol} FROM ipo_intelligence
                    WHERE {idcol} IS NOT NULL AND anchor_count IS NULL AND listing_date IS NOT NULL
                    ORDER BY listing_date DESC""")
    todo=cur.fetchall()
    print(f"IPOs with {idcol} needing anchors: {len(todo)}")
    filled=fetched=0
    for pid, cid in todo:
        if a.limit and fetched>=a.limit: break
        fetched+=1
        try: d=post(token,cid)
        except Exception as e: print(f"  id={cid}: {e}"); continue
        if isinstance(d,dict) and d.get("error"):
            print(f"  id={cid}: API {d.get('error')} (token expired?)"); 
            if "nauthor" in str(d.get('error','')): return
            continue
        names=extract_anchors(d)
        time.sleep(a.sleep)
        if not names: print(f"  id={cid}: no anchors in response"); continue
        filled+=1
        print(f"  id={cid:6} anchors={len(names):2}  e.g. {', '.join(names[:3])}")
        if a.apply:
            cur.execute("""UPDATE ipo_intelligence SET
                anchor_names=COALESCE(anchor_names,%s), anchor_count=COALESCE(anchor_count,%s)
                WHERE id=%s""",(json.dumps(names),len(names),pid))
    if a.apply: conn.commit()
    print(f"\n{'WROTE' if a.apply else 'DRY'}: {filled}/{fetched}")
    run_backtest(cur); conn.close()

if __name__=="__main__": main()
