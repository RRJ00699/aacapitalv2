#!/usr/bin/env python3
"""
cron.py — THE ONE ENTRY POINT. Chains the already-tested scripts in order.

This file adds NO extraction logic. Every step is an existing, tested component; this
just runs them in dependency order, enforces the spend cap, and cleans up documents.

ORDER (each step is skipped-with-a-reason, never half-done):
  1. Kite token refresh      _scripts/refresh_kite_token.py   (TOTP, existing)
  2a. Download RHPs         _scripts/download_sebi_rhps_playwright.py (existing, SEBI)
  2b. Download SBI notes    _scripts/download_sbi_notes.py           (existing)
  (SBI note CONTENT extraction goes through Sonnet, not the old regex parser)
  3. NSE issue/subscription  nse_fetch.py                     (tested 35 PASS)
  4. RHP extraction          drive.py --rhp                   (tested, PAID)
  5. Vendor fallback         ipomatrix_fallback.py            (tested, fills nulls only)
  6. Kite candles + outcomes kite_fetch.py                    (auth verified)
  7. Score + verdict         inside drive.py                  (tested)
  8. Completeness + ntfy     inside drive.py                  (tested)
  9. Post-lockin cleanup     delete RHP PDFs past lock-in (SBI notes are KEPT)
 10. Purge RHP PDFs          transient by design
 11. Document home           github -> commit SBI notes · local -> leave in place

SPEND CAP — DYNAMIC, CHANGEABLE FROM ANYWHERE
  The cap lives in platform_config.key='daily_spend_cap_usd' (the same table the Kite
  token uses), so you can change it from your phone with any DB client without touching
  code or redeploying. Default $2.00 if the key is absent.
  Today's spend is summed from rhp_findings.cost_usd — the column the extractor already
  writes — so there is no new ledger table to keep in sync.

RE-RUNNABLE BY DESIGN
  Data arrives progressively (RHP ~2wk out, issue details ~1wk, subscription at close,
  candles at listing). Every writer is COALESCE-empty-only or keyed ON CONFLICT, so
  running this many times a day on the same IPO fills what has newly appeared and
  duplicates nothing.

  python cron.py --dry-run
  python cron.py --run
  python cron.py --run --skip-download        # when the PDFs are already local
"""
import os, sys, io, json, time, argparse, subprocess, datetime as dt
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

FILE_BUILD = "cron 2026-08-01j — dropped the V1 SBI regex parser"
DEFAULT_CAP = 2.00
LOCKIN_DAYS = 90          # anchor lock-in: 50% at 30d, remainder at 90d. Delete after 90.
# RHPs are 8-20MB and TRANSIENT: their content is extracted into the DB and the file is
# re-fetchable from documents.url, so they are purged.
# SBI notes are ~3 pages, are shown in the UI, and are KEPT. Different lifecycle, so
# they are tracked separately and never share a delete path.
RHP_DIRS = ["rhps"]
SBI_DIR = "data/research_notes"


# The cron works the LIVE WINDOW, not history. An IPO is "active" while there is still
# data left to arrive for it:
#   - not yet listed  -> RHP, issue details, subscription are all still to come
#   - listed recently -> candles and listing_outcomes are still filling, and the anchor
#                        lock-in has not passed so the documents are still relevant
# Anything older is finished business: re-running it every day burns API budget and
# rewrites nothing, because every writer is COALESCE-empty-only.
ACTIVE_DAYS = 90     # matches the anchor lock-in window
DOC_FRESH_DAYS = 30  # a document fetched this recently means the IPO is genuinely live


def select_active(conn, limit, backfill=False):
    """The id list every step operates on. ONE definition, passed to all of them."""
    cur = conn.cursor()
    if backfill:
        cur.execute("""SELECT id, name_display, listing_date FROM ipo
                        WHERE in_backtest_universe=TRUE AND COALESCE(is_mainboard,TRUE)=TRUE
                        ORDER BY listing_date DESC NULLS LAST LIMIT %s""", (limit,))
        return cur.fetchall(), "BACKFILL (most recently listed)"
    cur.execute("""
        SELECT i.id, i.name_display, i.listing_date
          FROM ipo i
          LEFT JOIN ipo_issue ii ON ii.ipo_id = i.id
         WHERE
               -- MAINBOARD ONLY. The 08-01 run pulled in Propshop, Vinit Mobile, Metalic
               -- Technoforge, Teja and IC Electricals — all SME. They are not tradable
               -- under the house rules and every one of them costs a paid extraction.
               -- Size floor mirrors verdict_engine's JUNK line (issue_size_cr < 150).
               COALESCE(i.is_mainboard, TRUE) = TRUE
           AND COALESCE(ii.issue_size_cr, 999999) >= 150
           AND (
                 -- listed inside the active window: candles/outcomes still filling
                 (i.listing_date IS NOT NULL AND i.listing_date >= current_date - %s)
                 OR
                 -- not yet listed, and genuinely current. Evidence must be a REAL date
                 -- from the issue itself or a freshly fetched document — NOT ipo.created_at,
                 -- which records when the ROW was imported. Using created_at pulled in
                 -- Suryoday Bank, Engineers India and Cube Highways (old rows with a null
                 -- listing_date) and reported them as "upcoming" on the 08-01 run.
                 (i.listing_date IS NULL AND (
                      ii.close_date >= current_date - 30
                   OR ii.open_date  >= current_date - 30
                   OR EXISTS (SELECT 1 FROM documents d
                               WHERE d.ipo_id = i.id
                                 AND d.fetched_at >= now() - (%s || ' days')::interval)))
               )
         ORDER BY COALESCE(i.listing_date, current_date + 365) DESC
         LIMIT %s""", (ACTIVE_DAYS, DOC_FRESH_DAYS, limit))
    return cur.fetchall(), f"ACTIVE (unlisted, or listed within {ACTIVE_DAYS}d)"


def where_am_i():
    """github | local. Decides where downloaded documents come to rest.

    On Actions the filesystem is ephemeral, so anything worth keeping must be committed
    back. On the laptop the files simply stay put. Auto-detected rather than configured,
    so the same command does the right thing in both places."""
    return "github" if os.environ.get("GITHUB_ACTIONS") == "true" else "local"


def db():
    """A SHORT-LIVED connection, opened per use and closed immediately.

    Never hold one across the run. Steps 2a/2b take 5-8 minutes of pure download with no
    DB activity, and Neon closes idle connections — on the 08-01 Actions run that killed
    the single long-lived connection and the final spend query died with InterfaceError,
    exiting 1 after every step had actually succeeded. The old repo hit the same thing
    (nse_anchor_backfill.py:58, a 92s stall losing a 700-symbol pass).
    Keepalives are set too, for the calls that do take a while."""
    return psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=25,
                            keepalives=1, keepalives_idle=30,
                            keepalives_interval=10, keepalives_count=3)


def with_db(fn, *args, **kwargs):
    """Run one DB operation on a fresh connection, always closing it."""
    conn = db()
    try:
        return fn(conn, *args, **kwargs)
    finally:
        try: conn.close()
        except Exception: pass


def get_cap(conn):
    """Daily $ cap from platform_config — changeable from your phone, no redeploy."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM platform_config WHERE key='daily_spend_cap_usd'")
        r = cur.fetchone()
        if r and r[0]:
            return float(r[0])
    except Exception:
        conn.rollback()
    return DEFAULT_CAP


def spent_today(conn):
    """Sum of what the extractor already recorded. No separate ledger to drift."""
    cur = conn.cursor()
    try:
        cur.execute("""SELECT COALESCE(SUM(cost_usd),0) FROM rhp_findings
                        WHERE analyzed_at >= date_trunc('day', now())""")
        return float(cur.fetchone()[0] or 0)
    except Exception:
        conn.rollback()
        return 0.0


def run(step, cmd, dry, timeout=1800):
    """Run one existing script. A failure is isolated and reported, never fatal."""
    print(f"\n  === {step}")
    print(f"      $ {' '.join(cmd)}")
    if dry:
        print("      [dry-run] not executed")
        return {"step": step, "status": "dry"}
    t0 = time.time()
    try:
        # Child processes inherit a cp1252 console on Windows, so a single unicode
        # character in a progress line raises UnicodeEncodeError and fails a step that
        # actually succeeded — download_sbi_notes.py died on its "→" summary line after
        # downloading every note. Forcing UTF-8 makes local behave like the runner.
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           env=env, errors="replace")
        out = (p.stdout or "")[-1500:]
        err = (p.stderr or "")[-400:]
        for line in out.splitlines()[-25:]:
            print(f"      {line}")
        if p.returncode != 0:
            print(f"      ! exit {p.returncode}  {err[:200]}")
            return {"step": step, "status": "failed", "rc": p.returncode}
        print(f"      ok ({time.time()-t0:.0f}s)")
        return {"step": step, "status": "ok"}
    except subprocess.TimeoutExpired:
        print(f"      ! TIMEOUT after {timeout}s — step abandoned, chain continues")
        return {"step": step, "status": "timeout"}
    except FileNotFoundError:
        print("      ! script not found — skipped")
        return {"step": step, "status": "missing"}


def cleanup_docs(conn, dry):
    """Delete RHP/SBI PDFs once the anchor lock-in has passed.

    The DATA lives in the DB and the PROVENANCE lives in documents.sha256 + url, so the
    PDF is re-fetchable and holding 8-20MB per IPO forever is waste. Only deletes when
    the IPO listed more than LOCKIN_DAYS ago AND a document row exists (i.e. we actually
    banked what the PDF contained)."""
    cur = conn.cursor()
    cur.execute("""SELECT i.id, i.name_display, i.listing_date
                     FROM ipo i
                    WHERE i.listing_date IS NOT NULL
                      AND i.listing_date < current_date - %s
                      AND EXISTS (SELECT 1 FROM documents d WHERE d.ipo_id = i.id)""",
                (LOCKIN_DAYS,))
    # NOTE: this only ever touches RHP_DIRS. SBI notes are never deleted here.
    eligible = cur.fetchall()
    if not eligible:
        print("      nothing past lock-in with a banked document")
        return 0
    mapping = {}
    if os.path.exists("rhp_map.json"):
        try: mapping = json.load(open("rhp_map.json", encoding="utf-8"))
        except Exception: pass
    freed = 0
    for ipo_id, name, ld in eligible:
        folder = mapping.get(str(ipo_id))
        if not folder:
            continue
        for base in RHP_DIRS:
            d = os.path.join(base, folder)
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f.lower().endswith(".pdf"):
                    p = os.path.join(d, f)
                    sz = os.path.getsize(p)
                    print(f"      {'[dry] ' if dry else ''}delete {p} ({sz/1e6:.1f}MB) "
                          f"— {name} listed {ld}")
                    if not dry:
                        os.remove(p)
                    freed += sz
    # R2 (point 3): RHPs are transient — drop the R2 copy too once past lock-in. SBI
    # notes are NEVER touched here. Best-effort; the 180-day bucket lifecycle is the backstop.
    import r2
    r2_del = 0
    for eid, _n, _ld in eligible:
        cur.execute("""SELECT url FROM documents WHERE ipo_id=%s AND doc_type='rhp'
                       AND url LIKE 'r2://%%'""", (eid,))
        for (url,) in cur.fetchall():
            r2_del += 1
            if not dry:
                r2.delete_url(url)
    print(f"      {freed/1e6:.1f}MB {'would be ' if dry else ''}freed; "
          f"{r2_del} RHP object(s) {'would be ' if dry else ''}deleted from R2 (SBI notes untouched)")
    return freed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--backfill", action="store_true",
                    help="process the most recently LISTED IPOs instead of the active "
                         "window. For one-off history work, never for the schedule.")
    ap.add_argument("--skip-download", action="store_true", help="skip ALL downloads")
    ap.add_argument("--skip-rhp-download", action="store_true",
                    help="skip only the SEBI RHP download. Until rhp_map.json maps the "
                         "downloaded folders to ipo ids, those PDFs are fetched and then "
                         "purged unextracted — pure waste on every run.")
    ap.add_argument("--skip-kite", action="store_true")
    ap.add_argument("--max-rhps", type=int, default=4,
                    help="cap RHP downloads per run — each is 8-20MB and each costs an "
                         "extraction; 1-4/day is the real arrival rate")
    ap.add_argument("--purge-pdfs", action="store_true",
                    help="delete downloaded RHP PDFs at the end of the run. OFF by "
                         "default — documents are kept locally.")
    ap.add_argument("--cleanup-lockin", action="store_true",
                    help="prune documents whose anchor lock-in has passed. OFF by "
                         "default.")
    ap.add_argument("--ignore-local", action="store_true",
                    help="force RHP reads from R2 even when a local copy exists — tests "
                         "the runner read path without deleting local PDFs.")
    a = ap.parse_args()
    if not (a.run or a.dry_run):
        sys.exit("choose --run or --dry-run")
    dry = a.dry_run
    py = sys.executable

    # ========== PHASE A: DOWNLOADS. NO DB CONTACT AT ALL. ==========
    # These take 5-10 minutes. Running them BEFORE the DB work means the database is
    # never left awake across a long idle gap — on the 08-01 run the downloads sat
    # BETWEEN DB steps, holding the connection open (and Neon awake) for the full 15
    # minutes, then dropping it. Downloads first = one short contiguous DB window.
    steps = []
    if not (a.skip_download or a.skip_rhp_download):
        steps.append(run("2a. download RHPs (SEBI)",
                         [py, os.path.join("_scripts", "download_sebi_rhps_playwright.py"),
                          "--max", str(a.max_rhps)], dry, 2400))
    else:
        why = "--skip-download" if a.skip_download else "--skip-rhp-download"
        print(f"\n  === 2a. download RHPs (SEBI)\n      SKIPPED ({why})")
        steps.append({"step": "2a. download RHPs (SEBI)", "status": "skipped"})
    if not a.skip_download:
        steps.append(run("2b. download SBI notes",
                         [py, os.path.join("_scripts", "download_sbi_notes.py"),
                          "--out", "data/research_notes"], dry, 1200))
        # 2c REMOVED 08-01. parse_sbi_notes.py is a V1 regex/pdfplumber parser that
        # re-derives PE and peer names from the PDFs. Sonnet already reads documents far
        # more reliably, and this was the ONLY step failing on every run. SBI notes are
        # downloaded and kept for the UI; their CONTENT will be extracted the same way
        # RHPs are, not by regex.

    # ========== PHASE B: DB WORK. One contiguous window from here on. ==========
    cap = with_db(get_cap)
    already = with_db(spent_today)
    remaining = max(0.0, cap - already)
    print(f"  [build] {FILE_BUILD}")
    print(f"  {dt.datetime.now():%Y-%m-%d %H:%M}  mode={'DRY-RUN' if dry else 'RUN'}")
    print(f"  SPEND: cap ${cap:.2f}/day (platform_config.daily_spend_cap_usd) · "
          f"already ${already:.3f} today · ${remaining:.2f} available")

    targets, scope = with_db(select_active, a.limit, a.backfill)
    ids = ",".join(str(t[0]) for t in targets)
    print(f"  SCOPE: {scope} — {len(targets)} IPO(s)")
    for tid, tname, tld in targets:
        print(f"         id={tid:<5} {str(tname)[:38]:40} listed={tld or '(upcoming)'}")
    if not targets:
        print("\n  nothing active — no upcoming IPOs and none listed recently. Exiting.")
        return

    # NOTE: no `steps = []` here — that would discard the Phase A download results.
    # 1. Kite token — must be first: everything price-related depends on it
    if not a.skip_kite:
        steps.append(run("1. kite token refresh (TOTP)",
                         [py, os.path.join("_scripts", "refresh_kite_token.py")], dry, 300))
    # 2. Documents — RHPs from SEBI, then SBI research notes (both existing + proven).
    #    PDFs are transient: downloaded, extracted, then removed. They are deliberately
    #    NOT committed to the repo — git keeps blobs forever, so a committed 8-20MB PDF
    #    is permanent weight that a later delete does not reclaim. The data lives in the
    #    DB and the provenance in documents.sha256 + url, so the file is re-fetchable.
    # 3. NSE
    steps.append(run("3. NSE issue + subscription",
                     [py, "nse_fetch.py", "--ids", ids,
                      "--dry-run" if dry else "--write"], dry, 900))
    # 4. RHP extraction — the only paid step, gated on the remaining budget
    if remaining <= 0:
        print(f"\n  === 4. RHP extraction\n      SKIPPED — daily cap ${cap:.2f} already spent")
        steps.append({"step": "4. rhp", "status": "capped"})
    else:
        steps.append(run(f"4. RHP extraction (budget ${remaining:.2f})",
                         [py, "drive.py", "--ids", ids,
                          "--dry-run" if dry else "--write", "--rhp",
                          "--max-spend", f"{remaining:.2f}"]
                         + (["--ignore-local"] if a.ignore_local else []), dry, 3600))
    # 5. Vendor fallback — fills only what the primary sources left null
    steps.append(run("5. IPOMatrix fallback",
                     [py, "ipomatrix_fallback.py", "--ids", ids,
                      "--dry-run" if dry else "--write"], dry, 600))
    # 6. Kite candles + derived outcomes
    if not a.skip_kite:
        steps.append(run("6. Kite candles + listing outcomes",
                         [py, "kite_fetch.py", "--ids", ids,
                          "--dry-run" if dry else "--write"], dry, 900))
    # 7. score + verdict + completeness + ntfy (drive without --rhp is free)
    steps.append(run("7. score + verdict + completeness + ntfy",
                     [py, "drive.py", "--ids", ids,
                      "--dry-run" if dry else "--write"], dry, 900))
    # 8. warm Cloudflare KV — push V2 payloads (ipo:<id>:details + ipo:list:v2, live +
    #    stale twin) so user reads are served from KV and never wake Neon. --all, NOT the
    #    active-window `ids`: warming is cheap KV puts, and every in-scope IPO needs a
    #    payload or its Details screen is permanently degraded. Runs LAST, after
    #    score/verdict, so KV reflects the freshest data. Needs ADMIN_JOB_KEY in the env
    #    (warm_kv exits loudly without it on --write).
    steps.append(run("8. warm KV cache (all in-scope)",
                     [py, "warm_kv.py", "--all",
                      "--dry-run" if dry else "--write"], dry, 900))
    # 9. post-lockin cleanup — OPT-IN ONLY (owner 08-01: keep the documents locally).
    #    Documents now live on the laptop and are KEPT. Nothing is deleted unless you
    #    explicitly ask, because a deleted RHP costs a re-download and a re-extraction
    #    while disk is free.
    if a.cleanup_lockin:
        print("\n  === 9. post-lockin document cleanup")
        try:
            with_db(cleanup_docs, dry)
        except Exception as e:
            print(f"      ! cleanup failed (non-fatal): {type(e).__name__}: {str(e)[:100]}")
    else:
        print("\n  === 9. post-lockin cleanup — SKIPPED (documents are kept; "
              "pass --cleanup-lockin to prune)")

    # 10. On an ephemeral runner the PDFs die with the job, but purge explicitly so a
    #     local run behaves identically and no file is left lying around after its data
    #     has been banked.
    if not a.purge_pdfs:
        print("\n  === 10. purge — SKIPPED. RHPs and SBI notes both KEPT on disk.")
    if a.purge_pdfs:
        print("\n  === 10. purge RHP PDFs (SBI notes are KEPT)")
        n = sz = 0
        for base in RHP_DIRS:
            if not os.path.isdir(base):
                continue
            for root, _, files in os.walk(base):
                for f in files:
                    if f.lower().endswith(".pdf"):
                        p = os.path.join(root, f)
                        sz += os.path.getsize(p); n += 1
                        if not dry: os.remove(p)
        print(f"      {'would purge' if dry else 'purged'} {n} RHP PDFs ({sz/1e6:.1f}MB)")
        kept = sum(1 for r, _, fs in os.walk(SBI_DIR) for f in fs
                   if f.lower().endswith(".pdf")) if os.path.isdir(SBI_DIR) else 0
        print(f"      {kept} SBI note PDFs KEPT in {SBI_DIR} (needed by the UI)")

    # 11. TWO-PATH DOCUMENT HOME.
    #     github : the runner is ephemeral, so SBI notes must be committed back or they
    #              vanish with the job. Only SBI notes are committed — never RHPs, whose
    #              size would sit in git history permanently.
    #     local  : the files are already where they need to be; nothing to do.
    # 11. DOCUMENTS LIVE ON THE LAPTOP, NOT IN GIT (owner decision 08-01).
    #     Nothing is ever committed. Git keeps every blob forever, so PDFs in the repo
    #     are permanent weight no later delete reclaims — and .gitignore now excludes
    #     them outright. On an ephemeral runner they cannot persist at all, which is
    #     exactly why the downloads belong on the local machine.
    where = where_am_i()
    print(f"\n  === 11. document home ({where})")
    def _count(d):
        return sum(1 for r, _, fs in os.walk(d) for f in fs
                   if f.lower().endswith(".pdf")) if os.path.isdir(d) else 0
    n_rhp = sum(_count(d) for d in RHP_DIRS)
    n_sbi = _count(SBI_DIR)
    if where == "github":
        print(f"      ephemeral runner — {n_rhp} RHPs and {n_sbi} SBI notes will vanish "
              f"with this job and are NOT committed.")
        print(f"      Run the downloads locally (or pass --skip-download here) so the "
              f"documents persist.")
    else:
        print(f"      local — {n_rhp} RHPs and {n_sbi} SBI notes kept on disk, "
              f"nothing committed")

    # Fresh connection: the one opened 15 minutes ago is long gone.
    try:
        today_total = with_db(spent_today)
    except Exception as e:
        print(f"  (spend read failed, non-fatal: {type(e).__name__})")
        today_total = already
    final_spend = today_total - already
    print("\n  " + "=" * 60)
    for s in steps:
        print(f"    {s['step']:44} {s['status']}")
    print(f"    spend this run: ${final_spend:.3f} · today total "
          f"${today_total:.3f} of ${cap:.2f}")
    # A step that failed must surface in the exit code, but a NON-fatal step (a skipped
    # download, a parser that errored on one note) must not fail the whole run.
    hard_failed = [s_["step"] for s_ in steps if s_["status"] in ("failed", "timeout")]
    if hard_failed:
        print(f"    FAILED STEPS: {hard_failed}")


if __name__ == "__main__":
    main()
