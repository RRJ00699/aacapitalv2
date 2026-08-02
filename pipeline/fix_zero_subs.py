#!/usr/bin/env python3
"""
fix_zero_subs.py — remove zero-filled FINAL subscription snapshots.

WHY
  nse_fetch wrote is_final rows with every category at 0 for IPOs whose subscription had
  not been reported yet (Propshop id=12, Metalic id=10 on the 08-01 cron run). Two harms:
    1. mf_shares_bid=0 is the FIRST condition in verdict_engine's JUNK line, so those
       IPOs are classified JUNK on no evidence.
    2. subscription_snapshots is append-only with UNIQUE(ipo_id) WHERE is_final, so the
       real close-day numbers can never be written while the zero row sits there.

SAFETY
  Only deletes rows where EVERY meaningful column is 0 or NULL. A row with any real
  demand figure is left alone. Shows everything before touching anything.

  python fix_zero_subs.py --check
  python fix_zero_subs.py --delete
"""
import os, sys, io, argparse
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

COLS = ["qib_x", "nii_x", "bnii_x", "snii_x", "retail_x", "total_x", "mf_shares_bid"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true"); ap.add_argument("--delete", action="store_true")
    a = ap.parse_args()
    if not (a.check or a.delete):
        sys.exit("choose --check or --delete")
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()

    zero_cond = " AND ".join(f"COALESCE({c},0) = 0" for c in COLS)
    cur.execute(f"""SELECT s.ipo_id, i.name_display, s.captured_at, s.is_final
                      FROM subscription_snapshots s JOIN ipo i ON i.id = s.ipo_id
                     WHERE s.is_final AND {zero_cond}
                     ORDER BY s.captured_at DESC""")
    rows = cur.fetchall()
    print(f"  {len(rows)} zero-filled FINAL snapshot(s):")
    for ipo_id, name, cap, fin in rows:
        print(f"    ipo_id={ipo_id:<5} {str(name)[:38]:40} captured={cap}")
    if not rows:
        print("    (none — nothing to clean)")
        conn.close(); return

    if a.delete:
        for ipo_id, _, cap, _ in rows:
            cur.execute("""DELETE FROM subscription_snapshots
                            WHERE ipo_id=%s AND captured_at=%s AND is_final""", (ipo_id, cap))
        conn.commit()
        print(f"\n  deleted {len(rows)} zero rows — the real close-day figures can now land")
        cur.execute(f"""SELECT count(*) FROM subscription_snapshots
                         WHERE is_final AND {zero_cond}""")
        print(f"  verification: {cur.fetchone()[0]} zero-filled final rows remain")
    else:
        print("\n  --check only, nothing deleted.")
    conn.close()


if __name__ == "__main__":
    main()
