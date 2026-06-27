#!/usr/bin/env python3
"""
fetch_amc_disclosure.py — download each high-conviction AMC's latest MONTHLY PORTFOLIO
disclosure, robustly, for import_mf_from_excel.py to parse.

WHY THIS SHAPE:
AMFI is only a directory that deep-links to each AMC's own site; the files live on the
AMCs. The AMC pages are static HTML (Nippon = SharePoint), so they're scrapable. BUT the
file NAMES drift wildly month to month (day present/absent, "Mar" vs "March", - vs _,
2-digit vs 4-digit year, .xls vs .xlsx). So we DO NOT template the filename. We scrape the
listing page and pick the link whose LABEL says "monthly portfolio" — that survives the
naming chaos. The downloaded file then goes through the EXISTING, correct parser
(import_mf_from_excel.py), not a new fragile one.

Only the high-conviction AMCs the 💎 signal actually uses are worth wiring (Nippon, quant,
Canara, PPFAS, …). Add each by dropping its listing URL into AMCS once you've eyeballed the
page (every AMC's HTML differs slightly; the label/url matchers below are deliberately loose).

Run:  python _scripts/mf/fetch_amc_disclosure.py --out data/amfi_portfolios
      python _scripts/mf/fetch_amc_disclosure.py --amc "Nippon India" --dry-run   # show the URL only
Then: python _scripts/import_mf_from_excel.py --dir data/amfi_portfolios
Env:  (none needed to fetch)
"""
import os, re, sys, argparse, logging
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Each AMC: the page that lists its monthly portfolio disclosures.
# Only STATIC (server-rendered) AMC pages work here. Confirmed working:
AMCS = {
    "Nippon India": "https://mf.nipponindiaim.com/investor-service/downloads/factsheet-portfolio-and-other-disclosures",
    "PPFAS":        "https://amc.ppfas.com/downloads/portfolio-disclosure/",
}
# JS-rendered / accordion sites return 0 links to `requests` and need a different tactic
# (their underlying XHR endpoint, or a headless browser) — NOT worth it unless Screener
# has a real gap for that fund. Known JS sites: quant (CMOTS accordion), Canara, SBI,
# and most big houses (HDFC, ICICI, Groww, JioBlackRock). Triage any page with --url.

# A link is the monthly EQUITY portfolio if its FILENAME says "monthly portfolio".
# Classify off the filename (per-link, reliable) — NOT surrounding DOM text, which is
# flat on these SharePoint pages and would trip the skip-words on every row.
WANT  = re.compile(r"monthly[\s_\-]*portfolio", re.I)
SKIP  = re.compile(r"fortnight|debt|risk|fundamental|factsheet|riskometer|annual|\bsai\b|scheme[\s_\-]*info|changes?[\s_\-]*in", re.I)
ISXLS = re.compile(r"\.xls[xm]?(?:$|\?|#)", re.I)


def pick_monthly_portfolio(html: str, base: str):
    """Return (url, label) of the most recent monthly-portfolio file, or (None, None)."""
    soup = BeautifulSoup(html, "html.parser")
    xls = [a for a in soup.find_all("a", href=True) if ISXLS.search(a["href"])]
    log.info(f"   found {len(xls)} .xls/.xlsx links on the page")
    if not xls:
        log.warning("   0 spreadsheet links — page may be JS-rendered or served a non-browser shell")
        return None, None
    monthly = []
    for a in xls:
        href = a["href"].strip()
        fname = href.rsplit("/", 1)[-1]
        if SKIP.search(fname):
            continue
        label = a.get_text(" ", strip=True)
        if WANT.search(fname) or WANT.search(label):
            url = href if href.startswith("http") else requests.compat.urljoin(base, href)
            monthly.append((url, label or fname))
    if not monthly:
        sample = ", ".join(a["href"].rsplit("/", 1)[-1] for a in xls[:5])
        log.warning(f"   no monthly-portfolio link matched. First filenames seen: {sample}")
        return None, None
    # page is reverse-chronological → first qualifying link is the latest
    return monthly[0]
    return None, None


def fetch_amc(name: str, listing_url: str, out_dir: str, dry_run: bool) -> str | None:
    log.info(f"[{name}] reading {listing_url}")
    r = requests.get(listing_url, headers=HEADERS, timeout=40)
    r.raise_for_status()
    url, label = pick_monthly_portfolio(r.text, listing_url)
    if not url:
        log.warning(f"[{name}] no monthly-portfolio link found — page layout may have changed")
        return None
    log.info(f"[{name}] latest monthly portfolio → {url}")
    log.info(f"[{name}] label: {label}")
    if dry_run:
        return url

    os.makedirs(out_dir, exist_ok=True)
    ext = ".xlsx" if url.lower().split("?")[0].endswith("xlsx") else ".xls"
    safe = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    path = os.path.join(out_dir, f"{safe}_latest_monthly_portfolio{ext}")
    with requests.get(url, headers=HEADERS, timeout=120, stream=True) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
    size = os.path.getsize(path)
    if size < 10_000:
        log.warning(f"[{name}] downloaded only {size} bytes — suspicious, check the file")
    log.info(f"[{name}] saved {path} ({size:,} bytes)")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/amfi_portfolios")
    ap.add_argument("--amc", help="AMC label (key in AMCS, or any label when used with --url)")
    ap.add_argument("--url", help="listing-page URL to triage directly (overrides the AMCS dict)")
    ap.add_argument("--dry-run", action="store_true", help="resolve + print the URL, don't download")
    args = ap.parse_args()

    if args.url:                                   # triage any page: prints "found N links" + pick
        targets = {args.amc or "test": args.url}
    elif args.amc:
        if args.amc not in AMCS:
            sys.exit(f"Unknown AMC '{args.amc}'. Known: {', '.join(AMCS)} — or pass --url to test a new page.")
        targets = {args.amc: AMCS[args.amc]}
    else:
        targets = AMCS

    ok = 0
    for name, url in targets.items():
        try:
            if fetch_amc(name, url, args.out, args.dry_run):
                ok += 1
        except Exception as e:
            log.error(f"[{name}] failed: {e}")
    log.info(f"Done — {ok}/{len(targets)} AMCs. Next: python _scripts/import_mf_from_excel.py --dir {args.out}")


if __name__ == "__main__":
    main()
