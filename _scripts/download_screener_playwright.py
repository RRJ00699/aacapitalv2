#!/usr/bin/env python3
"""
download_screener_playwright.py — fetch Screener's 10-yr Data Sheet Excel via a REAL headless
browser. This is the one method that reliably gets past Cloudflare (plain `requests` 404s because
cf_clearance is IP+UA-bound and expiring). Logs in with durable email/password, opens each company,
clicks "Export to Excel", and saves {SYMBOL}_10yr.xlsx into the directory that
import_screener_financials.py already reads — so the existing parser/importer needs no changes.

Pick exactly one selection mode:
  --stale            DB-driven: only names MISSING from annual_financials or BEHIND the latest FY
  --all              entire company_master universe (heavy — annual-results season only)
  --symbols-file F   newline list of NSE symbols
  --symbol SYM       a single symbol

Env:  SCREENER_USERNAME, SCREENER_PASSWORD  (login)
      DATABASE_URL / NEON_DATABASE_URL   (for --stale / --all)
Out:  data/fundamental_raw/{SYMBOL}_10yr.xlsx  (skipped if already present and > 5 KB)

  python _scripts/download_screener_playwright.py --stale --out data/fundamental_raw --sleep 3

NOTE: selectors below match screener.in at build time. If Screener changes its login form or the
export control, update LOGIN_* / the export locator. If Screener ever adds OTP/2FA on login, this
breaks by design (no silent credential handling) — fall back to a manual export for those names.
"""
import os, sys, time, argparse, datetime

BASE = "https://www.screener.in"
LOGIN_URL = f"{BASE}/login/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def expected_latest_fy() -> int:
    """Indian FY ends 31 Mar (labelled by ending year). Annuals file through ~Sept, so until
    Sept we treat last year's FY as the newest 'expected' — avoids chasing not-yet-filed names."""
    t = datetime.date.today()
    return t.year if t.month >= 9 else t.year - 1


def resolve_symbols(args):
    if args.symbol:
        return [args.symbol.upper()]
    if args.symbols_file:
        with open(args.symbols_file) as f:
            return [ln.strip().upper() for ln in f if ln.strip()]
    import psycopg2
    url = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        sys.exit("--stale / --all need DATABASE_URL")
    conn = psycopg2.connect(url); cur = conn.cursor()
    cur.execute("SELECT DISTINCT nse_symbol FROM company_master WHERE nse_symbol IS NOT NULL")
    universe = sorted({r[0].upper() for r in cur.fetchall() if r[0]})
    if args.all:
        conn.close(); return universe
    cur.execute("SELECT symbol, MAX(fiscal_year) FROM annual_financials GROUP BY symbol")
    have = {r[0].upper(): (r[1] or 0) for r in cur.fetchall()}
    conn.close()
    exp = expected_latest_fy()
    stale = [s for s in universe if have.get(s) is None or have.get(s, 0) < exp]
    print(f"stale check: universe={len(universe)}  current={len(universe)-len(stale)}  "
          f"to-refresh={len(stale)}  (expected latest FY={exp})")
    return stale


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/fundamental_raw")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--stale", action="store_true")
    g.add_argument("--all", action="store_true")
    g.add_argument("--symbols-file", dest="symbols_file")
    g.add_argument("--symbol")
    ap.add_argument("--limit", type=int, default=0, help="cap number of names (0 = no cap)")
    ap.add_argument("--sleep", type=float, default=3.0, help="seconds between companies (be polite)")
    ap.add_argument("--timeout", type=int, default=45000, help="per-action timeout (ms)")
    args = ap.parse_args()

    email = os.environ.get("SCREENER_USERNAME") or os.environ.get("SCREENER_EMAIL")
    pw = os.environ.get("SCREENER_PASSWORD")
    if not email or not pw:
        sys.exit("Set SCREENER_USERNAME and SCREENER_PASSWORD")

    os.makedirs(args.out, exist_ok=True)
    symbols = resolve_symbols(args)
    if args.limit:
        symbols = symbols[:args.limit]
    if not symbols:
        print("Nothing to fetch — everything is current."); return
    print(f"to fetch: {len(symbols)} symbols -> {args.out}")

    from playwright.sync_api import sync_playwright
    ok = skip = fail = 0
    fails = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(accept_downloads=True, user_agent=UA)
        page = ctx.new_page()

        # ---- login (real browser session earns its own cf_clearance) ----
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=args.timeout)
        page.fill("input[name='username']", email)
        page.fill("input[name='password']", pw)
        page.click("button[type='submit']")
        # Screener redirects OFF /login on success. Do NOT wait for networkidle — this site has
        # live polling so the network never idles (that hangs). Wait for the URL to change instead.
        try:
            page.wait_for_url(lambda u: "/login" not in u, timeout=20000)
        except Exception:
            pass
        page.wait_for_load_state("domcontentloaded", timeout=args.timeout)
        if "/login" in page.url:
            browser.close()
            sys.exit("Login failed — check SCREENER_USERNAME/PASSWORD, or a 2FA/Cloudflare challenge appeared.")
        print("logged in.")

        for i, sym in enumerate(symbols, 1):
            out = os.path.join(args.out, f"{sym}_10yr.xlsx")
            if os.path.exists(out) and os.path.getsize(out) > 5000:
                skip += 1; continue
            got = False
            last_reason = "no export control found"
            for path in (f"/company/{sym}/consolidated/", f"/company/{sym}/"):
                try:
                    page.goto(BASE + path, wait_until="domcontentloaded", timeout=args.timeout)
                    link = page.locator(
                        "a:has-text('Export to Excel'), button:has-text('Export to Excel')").first
                    if link.count() == 0:
                        last_reason = f"no export link at {path}"
                        continue
                    with page.expect_download(timeout=args.timeout) as di:
                        link.click()
                    di.value.save_as(out)
                    if os.path.getsize(out) > 5000:
                        got = True; break
                    last_reason = "downloaded file too small"
                except Exception as e:
                    last_reason = f"{type(e).__name__}: {str(e)[:60]}"
                    continue
            if got:
                ok += 1; print(f"  [{i}/{len(symbols)}] {sym} ok")
            else:
                fail += 1; fails.append((sym, last_reason))
                print(f"  [{i}/{len(symbols)}] {sym} FAILED — {last_reason}")
            time.sleep(args.sleep)
        browser.close()

    if fails:
        fp = os.path.join(args.out, "_download_failures.txt")
        with open(fp, "w") as f:
            for s, r in fails:
                f.write(f"{s}\t{r}\n")
        print(f"failures logged -> {fp}")
    print(f"done: {ok} downloaded, {skip} skipped, {fail} failed")


if __name__ == "__main__":
    main()
