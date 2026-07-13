#!/usr/bin/env python3
"""rhp_sonnet_store.py — store Sonnet RHP summaries into a NEW table (ipo_rhp_intel).
Saves BOTH the full narrative JSON (so we never lose what we paid for) AND the flat
db_fields for querying/feeding the verdict engine. Canonicalizes company name to master.
  python rhp_sonnet_store.py --dir rhp_summaries --apply
  python rhp_sonnet_store.py --json rhp_summaries/x_summary.json --apply
"""
import os,sys,json,argparse,glob,re,io
try: sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
except Exception: pass

def norm(n):
    n=(n or "").lower()
    n=re.sub(r'\b(red herring|prospectus|limited|ltd|private|pvt|inc|corporation|corp|company|co)\b','',n)
    return re.sub(r'[^a-z0-9]+',' ',n).strip()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dir");ap.add_argument("--json");ap.add_argument("--apply",action="store_true")
    a=ap.parse_args()
    import psycopg2
    from psycopg2.extras import Json
    DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    conn=psycopg2.connect(DB,connect_timeout=30);cur=conn.cursor()
    if a.apply:
        cur.execute("""CREATE TABLE IF NOT EXISTS ipo_rhp_intel(
            company_name text PRIMARY KEY,
            verdict text, one_line text, quality_gate text, margin_of_safety text,
            requires_further_dd boolean,
            auditor_qualified boolean, sebi_action boolean, criminal_litigation boolean,
            litigation_watch_count int, related_party_concern boolean, ofs_heavy boolean,
            customer_concentration_high boolean, numbers_integrity_flag text,
            cash_conversion_flag text, debt_trend text, working_capital_flag text,
            contingent_liabilities_material boolean, promoter_pledge_flag boolean,
            confidence text, full_json jsonb, raw_text text, model text, cost_usd numeric,
            stored_at timestamptz DEFAULT now())""")
        cur.execute("ALTER TABLE ipo_rhp_intel ADD COLUMN IF NOT EXISTS raw_text text")
        conn.commit()
        conn.commit()
    # master names for canonicalization
    cur.execute("SELECT DISTINCT company_name FROM ipo_intelligence")
    master={}
    for (nm,) in cur.fetchall():
        k=norm(nm)
        if k: master.setdefault(k,nm)

    files=[]
    if a.json: files=[a.json]
    elif a.dir: files=sorted(glob.glob(os.path.join(a.dir,"*_summary.json")))
    done=0
    for fp in files:
        try:
            d=json.load(open(fp,encoding="utf-8"))
            if "_parse_error" in d: 
                print(f"  skip {os.path.basename(fp)} (parse error)"); continue
            meta=d.get("_meta",{})
            company=meta.get("company") or os.path.basename(fp).replace("_summary.json","").replace("-"," ").title()
            # MISLABEL CHECK: does the summary's own text name a clearly different company?
            oneline=(d.get("one_line","")+" "+d.get("trust_summary","")).lower()
            cn=norm(company)
            mismatch=None
            # crude: if the folder name's key tokens don't appear anywhere in the summary text
            # AND a different known company name does, flag it
            toks=[t for t in cn.split() if len(t)>3]
            if toks and not any(t in oneline for t in toks):
                # summary doesn't mention the folder company at all — likely mislabel
                for mk,mn in master.items():
                    mtoks=[t for t in mk.split() if len(t)>4]
                    if mtoks and sum(1 for t in mtoks if t in oneline)>=2 and mk!=cn:
                        mismatch=mn; break
            if mismatch:
                print(f"  ⚠ MISLABEL: folder='{company}' but text describes '{mismatch}' — SKIPPING (needs re-run with correct name)")
                continue
            company=master.get(norm(company),company)  # canonicalize
            db=d.get("db_fields",{})
            dec=d.get("aacapital_decision",{})
            # read raw text if present (the paid response, human-readable)
            raw_text=None
            _rawp=fp.replace("_summary.json","_raw.txt")
            if os.path.exists(_rawp):
                try: raw_text=open(_rawp,encoding="utf-8").read()[:60000]
                except Exception: pass
            row=(company, d.get("verdict"), d.get("one_line"),
                 db.get("quality_gate") or dec.get("quality_gate"),
                 db.get("margin_of_safety") or dec.get("margin_of_safety"),
                 dec.get("requires_further_dd"),
                 db.get("auditor_qualified"), db.get("sebi_action"), db.get("criminal_litigation"),
                 db.get("litigation_watch_count"), db.get("related_party_concern"), db.get("ofs_heavy"),
                 db.get("customer_concentration_high"), db.get("numbers_integrity_flag"),
                 db.get("cash_conversion_flag"), db.get("debt_trend"), db.get("working_capital_flag"),
                 db.get("contingent_liabilities_material"), db.get("promoter_pledge_flag"),
                 d.get("confidence"), Json(d), raw_text, meta.get("model"), meta.get("cost_usd"))
            if a.apply:
                cur.execute("""INSERT INTO ipo_rhp_intel(
                    company_name,verdict,one_line,quality_gate,margin_of_safety,requires_further_dd,
                    auditor_qualified,sebi_action,criminal_litigation,litigation_watch_count,
                    related_party_concern,ofs_heavy,customer_concentration_high,numbers_integrity_flag,
                    cash_conversion_flag,debt_trend,working_capital_flag,contingent_liabilities_material,
                    promoter_pledge_flag,confidence,full_json,raw_text,model,cost_usd,stored_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                    ON CONFLICT(company_name) DO UPDATE SET verdict=EXCLUDED.verdict,one_line=EXCLUDED.one_line,
                    quality_gate=EXCLUDED.quality_gate,margin_of_safety=EXCLUDED.margin_of_safety,
                    requires_further_dd=EXCLUDED.requires_further_dd,auditor_qualified=EXCLUDED.auditor_qualified,
                    sebi_action=EXCLUDED.sebi_action,criminal_litigation=EXCLUDED.criminal_litigation,
                    litigation_watch_count=EXCLUDED.litigation_watch_count,related_party_concern=EXCLUDED.related_party_concern,
                    ofs_heavy=EXCLUDED.ofs_heavy,customer_concentration_high=EXCLUDED.customer_concentration_high,
                    numbers_integrity_flag=EXCLUDED.numbers_integrity_flag,cash_conversion_flag=EXCLUDED.cash_conversion_flag,
                    debt_trend=EXCLUDED.debt_trend,working_capital_flag=EXCLUDED.working_capital_flag,
                    contingent_liabilities_material=EXCLUDED.contingent_liabilities_material,
                    promoter_pledge_flag=EXCLUDED.promoter_pledge_flag,confidence=EXCLUDED.confidence,
                    full_json=EXCLUDED.full_json,raw_text=EXCLUDED.raw_text,model=EXCLUDED.model,cost_usd=EXCLUDED.cost_usd,stored_at=now()""",row)
                conn.commit()
            print(f"  {'stored' if a.apply else 'would store'}: {company[:34]:36} [{row[3]}] {d.get('verdict')}")
            done+=1
        except Exception as e:
            print(f"  ✗ {os.path.basename(fp)}: {type(e).__name__} {str(e)[:60]}")
    print(f"\n{'stored' if a.apply else 'dry-run'} {done} summaries")
if __name__=="__main__":main()
