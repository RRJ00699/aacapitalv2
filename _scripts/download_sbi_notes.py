#!/usr/bin/env python3
"""
download_sbi_notes.py — SBI 'IPO notes' PDFs (all pages). Clicking 'View PDF' fires a browser
download; we catch it. Resilient: a missing/slow note is skipped (Escape + continue), and
--start-page lets you resume. Skips files already saved (golden-rule).

  python _scripts\\download_sbi_notes.py --out data\\research_notes                 # all
  python _scripts\\download_sbi_notes.py --out data\\research_notes --start-page 27 # resume/mop-up
"""
import argparse, os, re, sys

RESEARCH_URL = "https://www.sbisecurities.in/research/fundamental"

def goto_page(pg, target):
    """click Next until the 'Page X of N' shows target (best-effort)."""
    for _ in range(target + 3):
        m = re.search(r"Page\s+(\d+)\s+of\s+\d+", pg.inner_text("body"))
        cur = int(m.group(1)) if m else 1
        if cur >= target: return
        try: pg.get_by_text("Next", exact=False).first.click(); pg.wait_for_timeout(2200)
        except Exception: return

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/research_notes")
    ap.add_argument("--pages", type=int, default=0)
    ap.add_argument("--start-page", type=int, default=1)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip install playwright --break-system-packages ; python -m playwright install --with-deps chromium")

    saved = skipped = failed = 0
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(accept_downloads=True); pg = ctx.new_page()
        pg.goto(RESEARCH_URL, wait_until="networkidle", timeout=60000); pg.wait_for_timeout(2500)
        pg.get_by_text("IPO notes", exact=False).first.click(); pg.wait_for_timeout(3000)

        total = a.pages or (lambda m: int(m.group(1)) if m else 1)(re.search(r"Page\s+\d+\s+of\s+(\d+)", pg.inner_text("body")))
        if a.start_page > 1: goto_page(pg, a.start_page)
        print(f"pages {a.start_page}..{total}")

        for page_no in range(a.start_page, total + 1):
            btns = pg.get_by_text("View PDF", exact=False); n = btns.count()
            print(f"  page {page_no}: {n} notes")
            for i in range(n):
                try:
                    with pg.expect_download(timeout=12000) as di:
                        btns.nth(i).click(timeout=8000)
                    dl = di.value
                    name = re.sub(r"[^A-Za-z0-9._ -]", "_", dl.suggested_filename or f"note_{page_no}_{i}.pdf")
                    dest = os.path.join(a.out, name)
                    if os.path.exists(dest): skipped += 1; continue          # golden-rule
                    dl.save_as(dest); saved += 1; print("     ↓", name)
                except Exception:
                    failed += 1
                    try: pg.keyboard.press("Escape")                          # clear any stuck viewer
                    except Exception: pass
                    pg.wait_for_timeout(500)
                    continue                                                  # one bad note never kills the page
            if page_no < total:
                try: pg.get_by_text("Next", exact=False).first.click(); pg.wait_for_timeout(2200)
                except Exception: print("  (stopped: couldn't advance)"); break
        b.close()
    print(f"✓ {saved} new, {skipped} existing, {failed} skipped(no file) → {a.out}")

if __name__ == "__main__":
    main()
