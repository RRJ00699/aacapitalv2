#!/usr/bin/env python3
"""
fill_ipo.py — V2 backend engine, TABLE 1: the `ipo` spine.
upsert_ipo(conn, record) inserts-or-updates one IPO on the ISIN spine WITHOUT
duplicates. Resolution: ISIN -> name_norm -> (never symbol, never fuzzy).
Enrichment is COALESCE-empty-only (fills NULLs, never clobbers a set value).
Every changed field is logged to source_facts (only on change).

record = dict with keys (all optional except name_display + name_norm):
  isin, symbol, name_norm, name_display, sector, industry, is_mainboard,
  status, listing_date, kite_token, ipomatrix_id, bse_code, issue_size_cr

Run tests:  python fill_ipo.py --selftest
"""
import os, sys, io, argparse, datetime as dt, math
if __name__=="__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2, psycopg2.extras

# columns we enrich with COALESCE-empty-only (never overwrite a set value)
ENRICH = ["symbol","sector","industry","kite_token","ipomatrix_id","bse_code",
          "listing_date","status"]

def _norm(name):
    """normalize a display name to name_norm (lower, alnum+space, collapsed)."""
    import re
    s=re.sub(r"[^a-z0-9 ]"," ",(name or "").lower())
    return re.sub(r"\s+"," ",s).strip()

def resolve_ipo_id(cur, isin=None, name_norm=None):
    """Return existing ipo.id by ISIN, else by name_norm, else None. Spine order."""
    if isin:
        cur.execute("SELECT id FROM ipo WHERE isin=%s", (isin,))
        r=cur.fetchone()
        if r: return r[0]
    if name_norm:
        cur.execute("SELECT id FROM ipo WHERE name_norm=%s", (name_norm,))
        r=cur.fetchone()
        if r: return r[0]
    return None

def _log_fact(cur, ipo_id, field, value, source, doc_id=None, confidence=1.0):
    """Insert into source_facts ONLY if the value changed vs the last source value."""
    if value is None:
        return
    if isinstance(confidence, bool):
        raise ValueError("source_facts confidence must be numeric between 0 and 1")
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError) as exc:
        raise ValueError("source_facts confidence must be numeric between 0 and 1") from exc
    if not math.isfinite(confidence_value) or not 0 <= confidence_value <= 1:
        raise ValueError("source_facts confidence must be numeric between 0 and 1")
    # Existing change-detection identity is deliberately unchanged: doc_id and
    # confidence enrich provenance but do not create a new fact identity.
    cur.execute("""SELECT value FROM source_facts
                   WHERE ipo_id=%s AND field=%s AND source=%s
                   ORDER BY fetched_at DESC LIMIT 1""", (ipo_id, field, source))
    last=cur.fetchone()
    if last and last[0]==str(value): return
    cur.execute("""INSERT INTO source_facts
                   (ipo_id,field,value,source,doc_id,confidence,fetched_at)
                   VALUES(%s,%s,%s,%s,%s,%s,now())
                   ON CONFLICT (ipo_id,field,source,fetched_at) DO NOTHING""",
                (ipo_id, field, str(value), source, doc_id, confidence_value))

def in_backtest(record):
    """mainboard + >=200cr + listing year >= 2016. Table is NOT self-limiting."""
    if not record.get("is_mainboard", True): return False
    sz=record.get("issue_size_cr")
    if sz is not None and sz<200: return False
    ld=record.get("listing_date")
    if isinstance(ld,str):
        try: ld=dt.date.fromisoformat(ld)
        except: ld=None
    if ld and ld.year<2016: return False
    return True

def upsert_ipo(conn, record, source="nse"):
    """Insert or enrich one IPO on the ISIN spine. Returns (ipo_id, action)."""
    cur=conn.cursor()
    name_display=record.get("name_display") or ""
    name_norm=record.get("name_norm") or _norm(name_display)
    isin=record.get("isin")
    ipo_id=resolve_ipo_id(cur, isin, name_norm)

    if ipo_id is None:
        # INSERT new spine row
        cur.execute("""INSERT INTO ipo
          (isin,symbol,name_norm,name_display,sector,industry,is_mainboard,status,
           listing_date,kite_token,ipomatrix_id,bse_code,in_backtest_universe,
           created_at,updated_at)
          VALUES (%(isin)s,%(symbol)s,%(name_norm)s,%(name_display)s,%(sector)s,
                  %(industry)s,%(is_mainboard)s,%(status)s,%(listing_date)s,
                  %(kite_token)s,%(ipomatrix_id)s,%(bse_code)s,%(ibu)s,now(),now())
          RETURNING id""",
          dict(isin=isin, symbol=record.get("symbol"), name_norm=name_norm,
               name_display=name_display, sector=record.get("sector"),
               industry=record.get("industry"),
               is_mainboard=record.get("is_mainboard", True),
               status=record.get("status","announced"),
               listing_date=record.get("listing_date"),
               kite_token=record.get("kite_token"),
               ipomatrix_id=record.get("ipomatrix_id"),
               bse_code=record.get("bse_code"), ibu=in_backtest(record)))
        ipo_id=cur.fetchone()[0]
        for f in ENRICH+["isin"]:
            _log_fact(cur, ipo_id, f, record.get(f), source)
        conn.commit(); return ipo_id, "inserted"

    # ENRICH existing row: COALESCE-empty-only (fill NULLs, never clobber)
    sets=[]; params={"id":ipo_id}
    # backfill ISIN only if currently NULL
    if isin:
        sets.append("isin = COALESCE(isin, %(isin)s)"); params["isin"]=isin
    for f in ENRICH:
        v=record.get(f)
        if v is not None:
            sets.append(f"{f} = COALESCE({f}, %({f})s)"); params[f]=v
    if sets:
        sets.append("updated_at = now()")
        cur.execute(f"UPDATE ipo SET {', '.join(sets)} WHERE id=%(id)s", params)
        for f in list(params.keys()):
            if f!="id": _log_fact(cur, ipo_id, f, params[f], source)
    conn.commit(); return ipo_id, "enriched"

# ------------------------------------------------------------------ tests
def selftest():
    conn=psycopg2.connect(os.environ["DATABASE_URL"])
    cur=conn.cursor()
    TEST_ISIN="INE000TEST999"; TEST_NORM=_norm("Zzz Selftest Ipo Ltd")
    # clean any prior test rows
    cur.execute("DELETE FROM source_facts WHERE ipo_id IN (SELECT id FROM ipo WHERE isin=%s OR name_norm=%s)",(TEST_ISIN,TEST_NORM))
    cur.execute("DELETE FROM ipo WHERE isin=%s OR name_norm=%s",(TEST_ISIN,TEST_NORM)); conn.commit()
    ok=True
    def check(msg, cond):
        nonlocal ok; ok=ok and cond
        print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")

    # 1. insert new
    id1,act1=upsert_ipo(conn, dict(isin=TEST_ISIN, name_display="Zzz Selftest Ipo Ltd",
                                   name_norm=TEST_NORM, sector="Tech", issue_size_cr=500,
                                   listing_date="2025-06-01", is_mainboard=True), "nse")
    check("first insert creates a row", act1=="inserted")
    cur.execute("SELECT count(*) FROM ipo WHERE isin=%s",(TEST_ISIN,)); check("exactly 1 row", cur.fetchone()[0]==1)
    cur.execute("SELECT in_backtest_universe FROM ipo WHERE isin=%s",(TEST_ISIN,)); check("in_backtest TRUE (500cr,2025)", cur.fetchone()[0] is True)

    # 2. re-insert SAME isin with new enrichment -> no dup, symbol filled
    id2,act2=upsert_ipo(conn, dict(isin=TEST_ISIN, name_display="Zzz Selftest Ipo Ltd",
                                   name_norm=TEST_NORM, symbol="ZZZTEST", kite_token=99999), "kite")
    check("same ISIN returns SAME id", id2==id1)
    check("action is enriched not inserted", act2=="enriched")
    cur.execute("SELECT count(*) FROM ipo WHERE isin=%s",(TEST_ISIN,)); check("still exactly 1 row (no dup)", cur.fetchone()[0]==1)
    cur.execute("SELECT symbol,kite_token FROM ipo WHERE isin=%s",(TEST_ISIN,)); r=cur.fetchone()
    check("symbol enriched to ZZZTEST", r[0]=="ZZZTEST"); check("kite_token enriched", r[1]==99999)

    # 3. COALESCE must NOT clobber: try to overwrite sector -> stays 'Tech'
    upsert_ipo(conn, dict(isin=TEST_ISIN, name_display="X", name_norm=TEST_NORM, sector="WRONG"), "bad")
    cur.execute("SELECT sector FROM ipo WHERE isin=%s",(TEST_ISIN,)); check("sector NOT clobbered (still Tech)", cur.fetchone()[0]=="Tech")

    # 4. ISIN NULL + same name_norm resolves to SAME row (name_norm fallback)
    id4,act4=upsert_ipo(conn, dict(isin=None, name_display="Zzz Selftest Ipo Ltd",
                                   name_norm=TEST_NORM, industry="Software"), "nse")
    check("ISIN-null + same name_norm returns SAME id", id4==id1)
    cur.execute("SELECT count(*) FROM ipo WHERE name_norm=%s",(TEST_NORM,)); check("still 1 row via name_norm fallback", cur.fetchone()[0]==1)

    # 5. source_facts logged changes, and unchanged re-log adds nothing
    cur.execute("SELECT count(*) FROM source_facts WHERE ipo_id=%s AND field='symbol'",(id1,))
    n_before=cur.fetchone()[0]
    upsert_ipo(conn, dict(isin=TEST_ISIN, name_display="X", name_norm=TEST_NORM, symbol="ZZZTEST"), "kite")
    cur.execute("SELECT count(*) FROM source_facts WHERE ipo_id=%s AND field='symbol'",(id1,))
    check("unchanged symbol adds NO new source_fact", cur.fetchone()[0]==n_before)

    # cleanup
    cur.execute("DELETE FROM source_facts WHERE ipo_id=%s",(id1,))
    cur.execute("DELETE FROM ipo WHERE id=%s",(id1,)); conn.commit()
    print(f"\n{'ALL PASS ✓' if ok else 'SOME FAILED ✗'}")
    conn.close(); return ok

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--selftest",action="store_true")
    a=ap.parse_args()
    if a.selftest: sys.exit(0 if selftest() else 1)
    print("import upsert_ipo(conn, record) — or run --selftest")
