#!/usr/bin/env python3
"""chittorgarh_recon.py — throwaway: can Playwright clear Chittorgarh's Cloudflare, and
what does the mainboard IPO list look like? Dumps structure to build the scraper against
reality. No cookie, no creds. Needs Playwright chromium (already on the VM)."""
import os, sys, re
LIST_URL = "https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/mainboard/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("pip install playwright --break-system-packages ; python -m playwright install chromium")
    os.makedirs("data", exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        print(f"navigating {LIST_URL} ...")
        pg.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        for _ in range(15):
            t = pg.title().lower()
            if "just a moment" not in t and "attention" not in t and "moment" not in t: break
            pg.wait_for_timeout(1500)
        html = pg.content(); title = pg.title()
        cf = "just a moment" in title.lower() or "challenge-platform" in html[:4000].lower()
        print(f"title: {title!r}")
        print(f"cloudflare cleared: {not cf}")
        with open("data/chittorgarh_list.html", "w", encoding="utf-8") as f: f.write(html)
        print(f"saved full HTML -> data/chittorgarh_list.html ({len(html):,} bytes)")
        try:
            import pandas as pd
            tables = pd.read_html(html)
            print(f"\n{len(tables)} tables found. Largest:")
            for i, t in enumerate(sorted(tables, key=lambda x: -x.shape[0])[:3]):
                print(f"\n--- table {i}  shape={t.shape} ---")
                print("cols:", list(t.columns)[:12]); print(t.head(4).to_string()[:1400])
        except Exception as e:
            print(f"pandas.read_html failed ({e}); inspect data/chittorgarh_list.html manually")
        links = re.findall(r'href="(/ipo/[^"]+|/ipo_subscription/[^"]+)"', html)
        seen = []
        for l in links:
            if l not in seen: seen.append(l)
        print(f"\nsample IPO detail links ({len(seen)} unique):")
        for l in seen[:8]: print("  ", l)
        b.close()
if __name__ == "__main__": main()
