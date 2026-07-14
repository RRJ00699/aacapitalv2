#!/usr/bin/env python3
"""READ ONLY — what's keeping Neon compute awake? Find the compute-hour drain."""
import os,sys,io,time
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
for _ in range(3):
    try: conn=psycopg2.connect(DB,connect_timeout=30,keepalives=1,keepalives_idle=30);break
    except: time.sleep(2)
cur=conn.cursor()

print("=== what could keep Neon compute awake 116 hrs/month ===\n")

# 1. how often does the pipeline / cron hit the DB? (job_runs frequency)
try:
    cur.execute("""SELECT DATE_TRUNC('hour', started_at) hr, COUNT(*) n
        FROM job_runs WHERE started_at > NOW() - INTERVAL '2 days'
        GROUP BY hr ORDER BY hr DESC LIMIT 20""")
    print("job_runs by hour (last 2 days):")
    for hr,n in cur.fetchall(): print(f"  {hr}: {n} jobs")
except Exception as e: print(f"  job_runs: {e}")

# 2. Neon auto-suspends after 5 min idle by default. If something pings every <5min,
#    compute NEVER sleeps → 24/7 = ~730 hrs/mo. 116 hrs = partial.
# check: is there a keepalive / frequent query pattern?
print("\n=== KEY QUESTION: is compute being pinged frequently? ===")
print("Neon suspends after 5 min idle. 116 hrs/mo means compute is up ~4 hrs/day.")
print("Likely causes:")
print("  1. Vercel serverless functions with connection pooling keeping it warm")
print("  2. A cron/health-check pinging the DB every few minutes")
print("  3. The nightly pipeline holding connections open too long")
print("  4. App API routes that don't close connections")

# 3. check for long-running or idle-in-transaction connections RIGHT NOW
try:
    cur.execute("""SELECT state, COUNT(*), MAX(NOW()-state_change) as longest_idle
        FROM pg_stat_activity WHERE datname=current_database() GROUP BY state""")
    print("\ncurrent connections by state:")
    for st,n,idle in cur.fetchall(): print(f"  {st}: {n} conns, longest {idle}")
except Exception as e: print(f"  pg_stat: {e}")
conn.close()
