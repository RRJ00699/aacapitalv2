#!/usr/bin/env python3
"""READ ONLY — 3 things: (1) fair-value table check, (2) lock8/trail12 walk on Knack,
(3) do negative-listing IPOs share patterns? Retries on SSL drop."""
import os,sys,io,time
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

def connect():
    for _ in range(3):
        try: return psycopg2.connect(DB,connect_timeout=30,keepalives=1,keepalives_idle=30)
        except Exception as e: print(f"  retry connect ({e})"); time.sleep(2)
    raise SystemExit("could not connect")
conn=connect();cur=conn.cursor()

# ---------- (1) fair-value table check ----------
print("="*55)
print("(1) WHICH TABLE HAS FAIR-VALUE COLUMNS")
fv=["ipo_pe","eps_post","peer_median_pe","roe","revenue_cagr_3y","profit_cagr_3y","debt_equity","ofs_pct","structure_type","issue_price"]
for tbl in ["ipo_consolidated","ipo_intelligence"]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s",(tbl,))
    cols=set(r[0] for r in cur.fetchall())
    print(f"  {tbl}: {[c for c in fv if c in cols]}")

# ---------- (2) lock8/trail12 walk on Knack ----------
print("\n"+"="*55)
print("(2) LOCK8/TRAIL12 walk on KNACK")
cur.execute("""SELECT COALESCE(symbol_final,nse_symbol,symbol),listing_date FROM ipo_consolidated WHERE company_name ILIKE '%knack%' LIMIT 1""")
r=cur.fetchone()
if r:
    sym,ld=r
    cur.execute("""SELECT high,low,close FROM price_candles WHERE UPPER(symbol)=UPPER(%s) AND date>=%s ORDER BY date LIMIT 32""",(sym,ld))
    cs=cur.fetchall()
    # entry = first open
    cur.execute("""SELECT open FROM price_candles WHERE UPPER(symbol)=UPPER(%s) AND date>=%s ORDER BY date LIMIT 1""",(sym,ld))
    entry=float(cur.fetchone()[0])
    print(f"  KNACK buy at open ₹{entry:.1f} — arm+8%=₹{entry*1.08:.1f}, floor+3%=₹{entry*1.03:.1f}")
    peak=entry;armed=False;sold=False
    for i,(h,l,c) in enumerate(cs):
        h,l,c=float(h),float(l),float(c);peak=max(peak,h)
        if h>=entry*1.08:armed=True
        sig=""
        if not sold:
            if armed and c<=entry*1.03: sig=f"🔴 SELL floor — closed ₹{c:.1f} ≤ ₹{entry*1.03:.1f} → +3%";sold=True
            elif l<=peak*0.88: sig=f"🔴 SELL trail — ₹{l:.1f} ≤ 12% off peak ₹{peak:.1f} → {(peak*0.88/entry-1)*100:+.1f}%";sold=True
            else: sig=("armed, holding" if armed else "not armed yet")
        print(f"  d{i:>2} H{h:>6.1f} L{l:>6.1f} C{c:>6.1f} peak{peak:>6.1f} {(c/entry-1)*100:>+5.1f}%  {sig}")
        if sold:break

# ---------- (3) negative-listing patterns ----------
print("\n"+"="*55)
print("(3) NEGATIVE-LISTING IPOs — shared patterns?")
cur.execute("""
  SELECT
    CASE WHEN return_listing_open < 0 THEN 'NEG-list' ELSE 'POS-list' END AS grp,
    COUNT(*) n,
    ROUND(AVG(NULLIF(ipo_pe,0)),1) avg_pe,
    ROUND(AVG(NULLIF(peer_median_pe,0)),1) avg_peerpe,
    ROUND(AVG(NULLIF(ofs_pct,0)),0) avg_ofs,
    ROUND(AVG(NULLIF(gmp_pct,0)),1) avg_gmp,
    ROUND(AVG(anchor_count),1) avg_anchors,
    ROUND(AVG(issue_size_cr),0) avg_size
  FROM ipo_consolidated
  WHERE return_listing_open IS NOT NULL
  GROUP BY grp
""")
print(f"  {'group':9}{'n':>5}{'ipoPE':>7}{'peerPE':>7}{'ofs%':>6}{'gmp%':>7}{'anchors':>8}{'size':>7}")
for r in cur.fetchall():
    print(f"  {r[0]:9}{r[1]:>5}{str(r[2]):>7}{str(r[3]):>7}{str(r[4]):>6}{str(r[5]):>7}{str(r[6]):>8}{str(r[7]):>7}")
# GMP as predictor of negative listing
cur.execute("""
  SELECT CASE WHEN gmp_pct<=0 THEN 'GMP<=0' WHEN gmp_pct<10 THEN 'GMP 0-10' ELSE 'GMP>10' END grp,
    COUNT(*) n, ROUND(100.0*SUM(CASE WHEN return_listing_open<0 THEN 1 ELSE 0 END)/COUNT(*),0) pct_neg
  FROM ipo_consolidated WHERE return_listing_open IS NOT NULL AND gmp_pct IS NOT NULL GROUP BY grp ORDER BY grp
""")
print("\n  GMP as predictor of NEGATIVE listing:")
for r in cur.fetchall(): print(f"    {r[0]:10} n={r[1]:>4}  listed negative: {r[2]}%")
conn.close()
