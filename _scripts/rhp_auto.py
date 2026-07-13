#!/usr/bin/env python3
"""
rhp_auto.py — FUTURE-IPO RHP automation (separate cron, mainboard-only, $1 cap).
Chains the four proven steps for NEW IPOs only:

  1. DOWNLOAD  new SEBI RHP filings   (download_sebi_rhps_playwright.py, resumable
               manifest => only new filings are fetched)
  2. EXTRACT   via Sonnet, mainboard-only + $1 cap
               (rhp_sonnet.py --year-min 2016 filters to ipo_intelligence =
               Chittorgarh mainboard; SME with no match are auto-excluded)
  3. STORE     -> ipo_rhp_intel   (rhp_sonnet_store.py --apply, canonicalized,
               mislabel-guarded, idempotent upsert)
  4. PURGE     delete each PDF AFTER its IPO's first anchor lock-in date
               (anchor_lock30_date in ipo_consolidated), keeping the UI link.
               Until lock-in, the PDF is retained.

Run (cron / job console):
  python _scripts/rhp_auto.py --apply
Dry-run (plan only):
  python _scripts/rhp_auto.py
"""
import os, sys, io, subprocess, argparse, glob, json, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))     # _scripts/
REPO = os.path.dirname(HERE)
CAP  = "1"                                             # $1/night hard cap
OUT  = os.path.join(REPO, "rhps")
SUMM = os.path.join(REPO, "rhp_summaries")

def run(label, args):
    print(f"\n[{label}] {' '.join(args)}")
    r = subprocess.run([sys.executable] + args, cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (r.stdout or "").strip().splitlines()[-8:]
    for l in tail: print("   " + l)
    if r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()[-4:]
        for l in err: print("   ! " + l)
    return r.returncode == 0

def purge_after_lockin(apply):
    """Delete PDFs whose IPO has passed its first anchor lock-in date."""
    try:
        import psycopg2
    except ImportError:
        print("  (psycopg2 missing — skip purge)"); return
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: print("  (no DB url — skip purge)"); return
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    # companies whose anchor 30-day lock-in is in the past
    cur.execute("""SELECT company_name, anchor_lock30_date FROM ipo_consolidated
                   WHERE anchor_lock30_date IS NOT NULL AND anchor_lock30_date < CURRENT_DATE""")
    passed = {}
    def norm(s): return "".join(ch for ch in (s or "").lower() if ch.isalnum())
    for nm, d in cur.fetchall(): passed[norm(nm)] = d
    conn.close()

    deleted = 0; kept = 0
    for pdf in glob.glob(os.path.join(OUT, "**", "*.pdf"), recursive=True):
        base = os.path.basename(os.path.dirname(pdf)) or os.path.splitext(os.path.basename(pdf))[0]
        key = norm(base.replace("-", " "))
        # match if any passed-lockin company name shares the key
        hit = next((d for k, d in passed.items() if k and (k in key or key in k)), None)
        if hit:
            print(f"  purge {base} (lock-in {hit} passed)")
            if apply:
                try: os.remove(pdf); deleted += 1
                except Exception as e: print(f"    ! {e}")
        else:
            kept += 1
    print(f"  purge: {deleted} deleted, {kept} retained (pre-lock-in)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    print(f"=== RHP AUTO (future IPOs · mainboard · ${CAP} cap) ===")
    if not a.apply:
        print("DRY RUN — steps that would run:")
        print("  1) fetch_new_rhps.py --apply  (new IPOs only, SEBI newest page, name-matched)")
        print("  2) rhp_sonnet.py --dir rhps --year-min 2016 --cap 1  (mainboard, $1)")
        print("  3) rhp_sonnet_store.py --dir rhp_summaries --apply")
        print("  4) purge PDFs past anchor lock-in (keeps UI link)")
        purge_after_lockin(apply=False)
        return
    ok = run("download", ["_scripts/fetch_new_rhps.py", "--apply"])
    run("extract", ["_scripts/rhp_sonnet.py", "--dir", "rhps", "--year-min", "2016", "--cap", CAP])
    run("store",   ["_scripts/rhp_sonnet_store.py", "--dir", "rhp_summaries", "--apply"])
    print("\n[purge] PDFs past anchor lock-in")
    purge_after_lockin(apply=True)
    print("\n✓ RHP AUTO COMPLETE")

if __name__ == "__main__":
    main()
