#!/usr/bin/env python3
"""
fetch_new_rhps.py — PURPOSE-BUILT for future IPOs. No manifest, no backlog.

Design (exactly as specified):
  1. Query ipo_intelligence for NEW IPOs (recent/upcoming) that have NO RHP yet
     (no matching row in ipo_rhp_intel).
  2. Read SEBI's Public Issues listing — newest page only (1 page).
  3. For each new IPO, match its name against that page's filings.
  4. Download ONLY the matched RHP PDF(s) to rhps/<slug>/rhp.pdf.

Fast: one page load, a handful of targeted downloads. Never walks history.

  python _scripts/fetch_new_rhps.py            # dry-run: show matches, download nothing
  python _scripts/fetch_new_rhps.py --apply    # download matched RHPs
  python _scripts/fetch_new_rhps.py --days 45  # how far back counts as "new" (default 45)
"""
import os, sys, io, re, argparse, unicodedata
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "https://www.sebi.gov.in"
LISTING_URL = f"{BASE}/sebiweb/home/HomeAction.do?doListing=yes&sid=3&ssid=15&smid=11"
SKIP_TITLE_RE = re.compile(r"abridged|corrigendum|addendum|notice|advertisement", re.I)
OUT_DIR = "rhps"

def norm(s):
    """Doc-word pre-strip (rhp/drhp/prospectus/red herring/the/india — SEBI
    title furniture) + the ONE shared canonicalizer for the corporate-suffix
    core. Keeps this matcher in lockstep with every other matcher while
    preserving the SEBI-specific tokens the old inline copy handled.
    NOTE (Caliber 2026-07-17): the norm was NOT why Caliber missed — this
    script scans only SEBI's NEWEST page, and Caliber's RHP rolled off it
    before Caliber entered our window. Manual seed path: drop the PDF into
    rhps/ (from the card's docs link) and rhp_auto processes it next run."""
    import re as _re, sys as _s, os as _o, unicodedata as _u
    s = _u.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = _re.sub(r"\b(rhp|drhp|prospectus|red herring|the|india)\b", "", s, flags=_re.I)
    _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from lib.canon import canon
    return canon(s)

def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"\b(limited|ltd|rhp|drhp|prospectus)\b\.?", "", s, flags=re.I)
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower() or "unknown"

def new_ipos_without_rhp(days):
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("no DATABASE_URL")
    c = psycopg2.connect(DB, connect_timeout=20); cur = c.cursor()
    # new = listing within +/- `days` window OR upcoming; AND no rhp row yet
    cur.execute("""
        SELECT ii.company_name
        FROM ipo_intelligence ii
        WHERE (ii.listing_date IS NULL
               OR ii.listing_date >= CURRENT_DATE - INTERVAL '%s days')
          AND NOT EXISTS (
              SELECT 1 FROM ipo_rhp_intel r
              WHERE lower(regexp_replace(r.company_name,'[^a-zA-Z0-9]','','g'))
                  = lower(regexp_replace(ii.company_name,'[^a-zA-Z0-9]','','g')))
    """, (days,))
    names = [r[0] for r in cur.fetchall()]
    c.close()
    return names

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=45)
    a = ap.parse_args()

    targets = new_ipos_without_rhp(a.days)
    print(f"NEW IPOs (last {a.days}d) without an RHP: {len(targets)}")
    if not targets:
        print("nothing to fetch — all recent IPOs already have RHPs."); return
    tset = {norm(t): t for t in targets}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip install playwright pypdf ; playwright install chromium")

    matched = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(accept_downloads=True)
        pg.goto(LISTING_URL, timeout=60000, wait_until="domcontentloaded")
        try: pg.wait_for_selector("table tbody tr", timeout=30000)
        except Exception: pass
        # read ONLY the first (newest) page
        rows = pg.locator("table tbody tr")
        listings = []
        for i in range(rows.count()):
            links = rows.nth(i).locator("a[href*='/filings/public-issues/']")
            for j in range(links.count()):
                al = links.nth(j)
                title = (al.inner_text() or "").strip()
                href = al.get_attribute("href") or ""
                if not title or not href or SKIP_TITLE_RE.search(title): continue
                url = href if href.startswith("http") else BASE + href
                listings.append((title, url))
        print(f"SEBI newest page: {len(listings)} filings")
        # match each new IPO against the page
        for title, url in listings:
            ntitle = norm(title)
            hit = next((orig for k, orig in tset.items()
                        if k and (k in ntitle or ntitle.startswith(k) or k[:8] in ntitle)), None)
            if hit:
                matched.append((hit, title, url))
                print(f"  ✓ MATCH: {hit!r}  <-  SEBI '{title[:50]}'")
        if not matched:
            print("  no new IPOs found on SEBI's newest page yet.")
        br.close()

    if not a.apply:
        print(f"\nDRY RUN — {len(matched)} would download. Add --apply.")
        return

    # apply: download each matched filing using the proven PDF.js click logic
    _download_matched(matched)

def _download_matched(matched):
    from playwright.sync_api import sync_playwright
    import pypdf
    os.makedirs(OUT_DIR, exist_ok=True)
    got = 0
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(accept_downloads=True)
        pg = ctx.new_page()
        for company, title, url in matched:
            try:
                # The source URL was captured here and then THROWN AWAY — the
                # cards had no RHP link (Rakesh 2026-07-16). Persist it now;
                # the sonnet row upserts later and keeps this column.
                # Self-contained connection: this downloader has no DB handle.
                import os as _os, psycopg2 as _pg
                _c = _pg.connect(_os.environ["DATABASE_URL"])
                _u = _c.cursor()
                _u.execute("ALTER TABLE ipo_rhp_intel ADD COLUMN IF NOT EXISTS rhp_url TEXT")
                _u.execute("""INSERT INTO ipo_rhp_intel (company_name, rhp_url)
                    VALUES (%s, %s)
                    ON CONFLICT (company_name) DO UPDATE SET rhp_url = EXCLUDED.rhp_url""",
                    (company, url))
                _c.commit(); _c.close()
            except Exception:
                pass
            slug = slugify(company)
            d = os.path.join(OUT_DIR, slug); os.makedirs(d, exist_ok=True)
            dest = os.path.join(d, "rhp.pdf")
            if os.path.exists(dest):
                print(f"  ⏭ {company} (have it)"); continue
            try:
                pg.goto(url, timeout=60000, wait_until="domcontentloaded")
                pg.wait_for_selector("iframe, embed", timeout=20000)
                dl = None
                for i in range(pg.locator("iframe").count()):
                    fr = pg.frame_locator("iframe").nth(i)
                    for sel in ["#download", "#downloadButton", "#secondaryDownload", "button[title*='Download' i]"]:
                        b = fr.locator(sel)
                        if b.count():
                            try:
                                b.first.wait_for(state="visible", timeout=8000)
                                with pg.expect_download(timeout=30000) as di:
                                    b.first.click()
                                dl = di.value; break
                            except Exception: continue
                    if dl: break
                if not dl:
                    print(f"  ✗ {company} (no download control)"); continue
                dl.save_as(dest)
                # verify it's a real RHP (>40 pages)
                try:
                    n = len(pypdf.PdfReader(dest).pages)
                    if n < 40:
                        print(f"  ✗ {company} ({n}pp — not a full RHP)"); os.remove(dest); continue
                except Exception:
                    pass
                print(f"  ✓ {company} -> {dest}"); got += 1
            except Exception as e:
                print(f"  ✗ {company} ({type(e).__name__})")
        br.close()
    print(f"\ndownloaded {got} RHP(s) into {OUT_DIR}/")

if __name__ == "__main__":
    main()
