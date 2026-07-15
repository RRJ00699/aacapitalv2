#!/usr/bin/env python3
"""
rhp_auto.py — FUTURE-IPO RHP automation. Fault-proof, shared daily budget.

Chains the proven steps for NEW IPOs only:
  1. DOWNLOAD  new SEBI RHP filings (fetch_new_rhps.py, resumable manifest)
  2. EXTRACT   via Sonnet (rhp_sonnet.py), gated to the REMAINING daily budget
  3. STORE     -> ipo_rhp_intel (rhp_sonnet_store.py --apply, idempotent)
  4. PURGE     delete each PDF AFTER its IPO's first anchor lock-in date
               (anchor_lock30_date in ipo_consolidated), keeping the UI link
  5. LOG       write this run to rhp_run_log (admin-visible): processed,
               deferred (downloaded-but-not-extracted due to cap), spend.

DAILY BUDGET ($3/day, shared across both cron runs):
  Before extracting, we read today's spend from rhp_run_log and pass the
  REMAINING budget (3.00 − spent_today) to rhp_sonnet as its --cap. Two runs
  therefore never exceed $3 combined. If the budget is exhausted, extraction
  is skipped and any downloaded-but-unextracted RHPs are logged as DEFERRED —
  they carry to the next run automatically (rhp_sonnet skips already-done files).

Run:  python _scripts/rhp_auto.py --apply
Dry:  python _scripts/rhp_auto.py
"""
import os, sys, io, subprocess, argparse, glob, json, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))     # _scripts/
REPO = os.path.dirname(HERE)
DAILY_CAP = 3.00                                       # $3/day TOTAL (both runs combined)
OUT  = os.path.join(REPO, "rhps")
SUMM = os.path.join(REPO, "rhp_summaries")


def _db():
    import psycopg2
    url = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        return None
    return psycopg2.connect(url, connect_timeout=20)


def ensure_log_table(conn):
    """Idempotent — the run log is a plain append table, safe to auto-create."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rhp_run_log (
                id          BIGSERIAL PRIMARY KEY,
                run_date    DATE        NOT NULL DEFAULT CURRENT_DATE,
                started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                processed   JSONB       NOT NULL DEFAULT '[]'::jsonb,
                deferred    JSONB       NOT NULL DEFAULT '[]'::jsonb,
                spent_usd   NUMERIC(8,4) NOT NULL DEFAULT 0,
                daily_cap   NUMERIC(8,4) NOT NULL DEFAULT 3,
                cap_hit     BOOLEAN     NOT NULL DEFAULT false,
                notes       TEXT
            )
        """)
    conn.commit()


def spent_today(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(SUM(spent_usd),0) FROM rhp_run_log WHERE run_date = CURRENT_DATE")
        return float(cur.fetchone()[0] or 0)


def run(label, args):
    print(f"\n[{label}] {' '.join(args)}")
    r = subprocess.run([sys.executable] + args, cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    for l in (r.stdout or "").strip().splitlines()[-8:]: print("   " + l)
    if r.returncode != 0:
        for l in (r.stderr or "").strip().splitlines()[-4:]: print("   ! " + l)
    return r.returncode == 0


def summarize_spend_and_queue():
    """Read the summary dir to compute actual spend today and the pending queue.
    processed = summaries with a verdict; deferred = downloaded PDFs with no summary yet."""
    processed, spent = [], 0.0
    done_bases = set()
    for sp in glob.glob(os.path.join(SUMM, "*_summary.json")):
        try:
            d = json.load(open(sp, encoding="utf-8"))
            meta = d.get("_meta", {})
            cost = float(meta.get("cost_usd", 0) or 0)
            base = os.path.basename(sp).replace("_summary.json", "")
            done_bases.add(base)
            # only count spend logged today (mtime today) to avoid double-counting old runs
            if datetime.date.fromtimestamp(os.path.getmtime(sp)) == datetime.date.today():
                spent += cost
                if d.get("verdict"):
                    processed.append({"company": meta.get("company", base), "cost": round(cost, 4),
                                      "verdict": d.get("verdict")})
        except Exception:
            pass
    # deferred = downloaded PDFs whose base has no summary yet (cap cut them off)
    deferred = []
    for pdf in glob.glob(os.path.join(OUT, "**", "*.pdf"), recursive=True):
        base = os.path.basename(os.path.dirname(pdf)) or os.path.splitext(os.path.basename(pdf))[0]
        if base not in done_bases:
            deferred.append({"company": base.replace("-", " ").title()})
    return processed, deferred, round(spent, 4)


def purge_after_lockin(apply):
    """Delete PDFs whose IPO has passed its first anchor lock-in date (keeps UI link)."""
    conn = None
    try:
        conn = _db()
        if not conn:
            print("  (no DB url — skip purge)"); return
        cur = conn.cursor()
        cur.execute("""SELECT company_name, anchor_lock30_date FROM ipo_consolidated
                       WHERE anchor_lock30_date IS NOT NULL AND anchor_lock30_date < CURRENT_DATE""")
        def norm(s): return "".join(ch for ch in (s or "").lower() if ch.isalnum())
        passed = {norm(nm): d for nm, d in cur.fetchall()}
        deleted = kept = 0
        for pdf in glob.glob(os.path.join(OUT, "**", "*.pdf"), recursive=True):
            base = os.path.basename(os.path.dirname(pdf)) or os.path.splitext(os.path.basename(pdf))[0]
            key = norm(base.replace("-", " "))
            hit = next((d for k, d in passed.items() if k and (k in key or key in k)), None)
            if hit:
                print(f"  purge {base} (lock-in {hit} passed)")
                if apply:
                    try: os.remove(pdf); deleted += 1
                    except Exception as e: print(f"    ! {e}")
            else:
                kept += 1
        print(f"  purge: {deleted} deleted, {kept} retained (pre-lock-in)")
    finally:
        if conn: conn.close()


def write_run_log(conn, processed, deferred, spent, cap_hit, notes):
    """Append this run to rhp_run_log. Called in finally so spend is always recorded."""
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO rhp_run_log (processed, deferred, spent_usd, daily_cap, cap_hit, notes)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (json.dumps(processed), json.dumps(deferred), spent, DAILY_CAP, cap_hit, notes))
        conn.commit()
        print(f"  logged run: {len(processed)} processed, {len(deferred)} deferred, ${spent:.2f} spent")
    except Exception as e:
        print(f"  ! run-log write failed: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    conn = _db()
    if conn:
        try: ensure_log_table(conn)
        except Exception as e: print(f"  (log table ensure failed: {e})")

    already = spent_today(conn) if conn else 0.0
    remaining = max(0.0, round(DAILY_CAP - already, 2))
    print(f"=== RHP AUTO (mainboard · daily cap ${DAILY_CAP:.2f} · spent today ${already:.2f} · remaining ${remaining:.2f}) ===")

    if not a.apply:
        print("DRY RUN — steps that would run:")
        print(f"  1) fetch_new_rhps.py --apply")
        print(f"  2) rhp_sonnet.py --dir rhps --year-min 2016 --cap {remaining}  (remaining daily budget)")
        print(f"  3) rhp_sonnet_store.py --dir rhp_summaries --apply")
        print(f"  4) purge PDFs past anchor lock-in (keeps UI link)")
        print(f"  5) write rhp_run_log (admin-visible)")
        purge_after_lockin(apply=False)
        if conn: conn.close()
        return

    processed, deferred, spent, cap_hit, notes = [], [], 0.0, False, ""
    try:
        run("download", ["_scripts/fetch_new_rhps.py", "--apply"])
        if remaining <= 0.01:
            cap_hit = True
            notes = f"Daily ${DAILY_CAP:.0f} budget already spent (${already:.2f}); extraction skipped — RHPs deferred to next run."
            print(f"  ⛔ {notes}")
        else:
            run("extract", ["_scripts/rhp_sonnet.py", "--dir", "rhps", "--year-min", "2016", "--cap", str(remaining)])
            run("store",   ["_scripts/rhp_sonnet_store.py", "--dir", "rhp_summaries", "--apply"])
        print("\n[purge] PDFs past anchor lock-in")
        purge_after_lockin(apply=True)
    finally:
        # Always compute + record spend, even if a step above threw — fault-proof budget.
        processed, deferred, spent = summarize_spend_and_queue()
        if deferred and not cap_hit:
            cap_hit = (already + spent) >= DAILY_CAP - 0.01
            if cap_hit and not notes:
                notes = f"Cap reached at ${already + spent:.2f}/${DAILY_CAP:.0f}; {len(deferred)} RHP(s) deferred to next run."
        write_run_log(conn, processed, deferred, spent, cap_hit, notes or f"OK — {len(processed)} processed.")
        if conn: conn.close()
    print("\n✓ RHP AUTO COMPLETE")


if __name__ == "__main__":
    main()
