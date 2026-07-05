#!/usr/bin/env python3
"""
backup_critical_tables.py — nightly CSV.gz snapshots of the IRREPLACEABLE tables.

Philosophy: candles/regimes/consolidated are REBUILDABLE from sources; these are not:
  ipo_intelligence   (years of merged enrichment)
  trade_journal      (your actual trades — the training set)
  ipo_research_notes (parsed SBI corpus)
  ipo_gmp            (GMP history vanishes from the source)

Writes /root/aac/backups/YYYY-MM-DD/<table>.csv.gz, keeps 14 days, prints sizes.
Restore: gunzip + COPY table FROM STDIN CSV HEADER. Neon PITR is the first line of
defense; this is the second (survives account-level problems, enables local diffing).

  venv/bin/python _scripts/backup_critical_tables.py
"""
import os, sys, gzip, shutil, datetime
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
TABLES = ["ipo_intelligence", "trade_journal", "ipo_research_notes", "ipo_gmp"]
KEEP_DAYS = 14

def main():
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = os.path.join(repo, "backups")
    today = str(datetime.date.today())
    outdir = os.path.join(root, today); os.makedirs(outdir, exist_ok=True)
    conn = psycopg2.connect(DB, connect_timeout=15); cur = conn.cursor()
    for t in TABLES:
        cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name=%s", (t,))
        if not cur.fetchone():
            print(f"  {t}: not found, skipped"); continue
        path = os.path.join(outdir, f"{t}.csv.gz")
        with gzip.open(path, "wt", encoding="utf-8") as f:
            cur.copy_expert(f"COPY {t} TO STDOUT WITH CSV HEADER", f)
        print(f"  {t}: {os.path.getsize(path)/1024:.0f} KB -> {path}")
    conn.close()
    # retention
    cutoff = datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)
    for d in sorted(os.listdir(root)):
        p = os.path.join(root, d)
        try:
            if os.path.isdir(p) and datetime.date.fromisoformat(d) < cutoff:
                shutil.rmtree(p); print(f"  pruned {d}")
        except ValueError:
            continue
    print("backup done.")

if __name__ == "__main__":
    main()
