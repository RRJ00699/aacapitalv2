#!/usr/bin/env python3
"""
probe_sbi_viewpdf.py — click ONE 'View PDF' on the SBI IPO-notes tab and report the mechanism:
downloads, new tabs, same-tab navigation, and any pdf/fileserver/getreport network calls.
Run this, paste me the output, and I'll pin the final scraper.

  python _scripts\\probe_sbi_viewpdf.py
"""
import re
RESEARCH_URL = "https://www.sbisecurities.in/research/fundamental"

def main():
    from playwright.sync_api import sync_playwright
    hits = {"downloads": [], "popups": [], "pdf_requests": [], "nav": None}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(accept_downloads=True)
        pg = ctx.new_page()

        ctx.on("page", lambda pop: hits["popups"].append(pop.url))
        pg.on("download", lambda d: hits["downloads"].append(d.suggested_filename))
        def on_req(r):
            u = r.url.lower()
            if any(k in u for k in ("pdf", "fileserver", "getreport", "download")):
                hits["pdf_requests"].append(f'{r.method} {r.url[:110]}')
        ctx.on("request", on_req)

        pg.goto(RESEARCH_URL, wait_until="networkidle", timeout=60000); pg.wait_for_timeout(2500)
        pg.get_by_text("IPO notes", exact=False).first.click(); pg.wait_for_timeout(3000)

        before = pg.url
        btn = pg.get_by_text("View PDF", exact=False).first
        print("found View PDF:", btn.count() if hasattr(btn, "count") else "yes")
        try: btn.click()
        except Exception as e: print("click error:", e)
        pg.wait_for_timeout(6000)
        if pg.url != before: hits["nav"] = pg.url

        # also inspect any iframe that may now hold the PDF
        frames = [f.url for f in pg.frames if "pdf" in f.url.lower() or "fileserver" in f.url.lower()]

        print("\n=== RESULT ===")
        print("downloads      :", hits["downloads"])
        print("new tabs       :", hits["popups"])
        print("same-tab nav   :", hits["nav"])
        print("pdf/net calls  :"); [print("   ", x) for x in hits["pdf_requests"][:15]]
        print("pdf iframes    :", frames)
        b.close()
        print("\n→ paste this whole block back to me.")

if __name__ == "__main__":
    main()
