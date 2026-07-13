import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_consolidated'")
cc={r[0] for r in cur.fetchall()}
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
ic={r[0] for r in cur.fetchall()}
both=cc & ic
print("columns in BOTH tables (ambiguous if unqualified):")
for c in sorted(both): print("  ",c)
print("\ncheck specific:")
for c in ["final_total","symbol_final","nse_symbol","symbol","issue_size_cr","brlm_names"]:
    print(f"  {c}: consolidated={c in cc} intelligence={c in ic} -> {'AMBIGUOUS' if c in both else 'ok'}")
conn.close()
