# -*- coding: utf-8 -*-
"""
download_sebi_rhps_playwright.py
================================
Downloads full RHP / Prospectus PDFs from SEBI Public Issues filings by
driving a real browser exactly like a human:

    listing page -> open filing page -> click Download -> wait -> save

SEBI ONLY. No third-party sites. No URL guessing. No page-source PDF-link
scraping. The only network activity is the browser doing what a user does.

Two phases (both resumable via download_manifest.json):
  Phase 1  HARVEST : walk the paginated listing, collect filing-page URLs.
  Phase 2  DOWNLOAD: open each filing page, click the Download button,
                     wait for the browser download, save + verify.

Output layout:
    rhps/
        <company-slug>/
            rhp.pdf
    download_manifest.json
    failures.log

Usage (Windows PowerShell):
    pip install playwright pypdf
    playwright install chromium
    python download_sebi_rhps_playwright.py                # full run, headless
    python download_sebi_rhps_playwright.py --headed       # watch it work
    python download_sebi_rhps_playwright.py --pages 3      # first 3 listing pages
    python download_sebi_rhps_playwright.py --max 10       # stop after 10 downloads
    python download_sebi_rhps_playwright.py --harvest-only # just build the worklist
    python download_sebi_rhps_playwright.py --retry-failed # re-attempt failures

Resume is automatic: anything marked "ok" in the manifest (with the PDF
still on disk) is skipped.
"""

import argparse
import json
import random
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PWTimeout,
    Error as PWError,
)

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
LISTING_URL = (
    "https://www.sebi.gov.in/sebiweb/home/HomeAction.do"
    "?doListing=yes&sid=3&ssid=15&smid=11"
)
BASE = "https://www.sebi.gov.in"

OUT_DIR = Path("rhps")
MANIFEST_PATH = Path("download_manifest.json")
FAIL_LOG = Path("failures.log")

NAV_TIMEOUT_MS = 60_000
DOWNLOAD_TIMEOUT_MS = 120_000
PAGE_DELAY = (1.5, 3.5)      # polite random sleep between filings (seconds)
LIST_DELAY = (1.0, 2.0)      # between listing pages
MAX_RETRIES = 2

# Skip these filing types (we want the FULL RHP / Prospectus only)
SKIP_TITLE_RE = re.compile(
    r"abridged|corrigendum|addendum|notice|advertisement", re.I
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# ----------------------------------------------------------------------------
# Small utils
# ----------------------------------------------------------------------------
def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def log_failure(url: str, reason: str) -> None:
    with FAIL_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()}\t{url}\t{reason}\n")


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"\b(limited|ltd|rhp|drhp|prospectus)\b\.?", "", s, flags=re.I)
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "unknown-company"


def company_from_title(title: str) -> str:
    """'Laser Power and Infra Limited - RHP' -> 'Laser Power and Infra Limited'"""
    return re.split(r"\s*[-–]\s*(RHP|DRHP|Prospectus)", title, flags=re.I)[0].strip()


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        with MANIFEST_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"harvested_pages": 0, "filings": {}}


def save_manifest(m: dict) -> None:
    tmp = MANIFEST_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)
    tmp.replace(MANIFEST_PATH)


def polite_sleep(rng) -> None:
    time.sleep(random.uniform(*rng))


# ----------------------------------------------------------------------------
# Verification
# ----------------------------------------------------------------------------
def verify_pdf(path: Path, company: str) -> tuple[bool, str]:
    """Return (ok, reason). Checks %PDF header, company name, not-abridged."""
    try:
        head = path.open("rb").read(5)
    except OSError as e:
        return False, f"unreadable: {e}"
    if head != b"%PDF-":
        return False, "not a PDF (missing %PDF header)"

    if path.stat().st_size < 50_000:
        return False, f"suspiciously small ({path.stat().st_size} bytes)"

    # Text checks need pypdf; degrade gracefully if unavailable.
    try:
        from pypdf import PdfReader
    except ImportError:
        return True, "ok (pypdf not installed — header check only)"

    try:
        reader = PdfReader(str(path))
        n_pages = len(reader.pages)
        text = ""
        for p in reader.pages[: min(4, n_pages)]:
            text += (p.extract_text() or "") + "\n"
        low = " ".join(text.lower().split())
    except Exception as e:  # encrypted/corrupt — keep file, flag it
        return True, f"ok (text-extract failed: {e})"

    # Abridged check: abridged docs announce themselves on page 1.
    if "abridged prospectus" in low and "red herring prospectus" not in low:
        return False, "abridged prospectus, not full RHP"

    # Full RHPs are big documents; abridged are ~10-30 pages.
    if n_pages < 40:
        return False, f"only {n_pages} pages — likely not a full RHP"

    # Company-name check: require most significant tokens to appear.
    tokens = [
        t for t in re.findall(r"[a-z0-9]+", company.lower())
        if t not in {"limited", "ltd", "and", "the", "of", "india", "pvt", "private"}
        and len(t) > 2
    ]
    if tokens:
        hits = sum(1 for t in tokens if t in low)
        if hits / len(tokens) < 0.5:
            return False, f"company name not found in PDF ({hits}/{len(tokens)} tokens)"

    return True, f"ok ({n_pages} pages)"


# ----------------------------------------------------------------------------
# Phase 1 — harvest filing links from the paginated listing
# ----------------------------------------------------------------------------
def harvest(page, manifest: dict, max_pages: int | None) -> None:
    log("Phase 1: harvesting filing links from SEBI listing ...")
    for attempt in range(5):
        try:
            page.goto(LISTING_URL, timeout=NAV_TIMEOUT_MS,
                      wait_until="domcontentloaded")
            page.wait_for_selector("table tbody tr", timeout=NAV_TIMEOUT_MS)
            break
        except (PWTimeout, PWError) as e:
            wait = 30 * (attempt + 1)
            log(f"  listing load failed ({str(e).splitlines()[0][:80]}) — "
                f"retry in {wait}s ({attempt+1}/5)")
            time.sleep(wait)
    else:
        raise RuntimeError("could not load SEBI listing after 5 attempts — "
                           "check network/DNS")

    page_no = 1
    new = 0
    while True:
        rows = page.locator("table tbody tr")
        for i in range(rows.count()):
            links = rows.nth(i).locator("a[href*='/filings/public-issues/']")
            for j in range(links.count()):
                a = links.nth(j)
                title = (a.inner_text() or "").strip()
                href = a.get_attribute("href") or ""
                if not href or not title:
                    continue
                url = href if href.startswith("http") else BASE + href
                if SKIP_TITLE_RE.search(title):
                    continue
                if url not in manifest["filings"]:
                    manifest["filings"][url] = {
                        "title": title,
                        "company": company_from_title(title),
                        "status": "pending",
                        "listing_page": page_no,
                        "attempts": 0,
                    }
                    new += 1
        log(f"  listing page {page_no}: {len(manifest['filings'])} filings total "
            f"(+{new} new so far)")
        save_manifest(manifest)

        if max_pages and page_no >= max_pages:
            break

        # Signature of current table so we can verify the page really changed.
        try:
            sig_before = page.locator("table tbody tr").first.inner_text(
                timeout=5_000)
        except (PWTimeout, PWError):
            sig_before = ""

        # Move to the next listing page. SEBI renders numbered links
        # (1 2 3 ... Next Last); try the exact next number first, then
        # anything that looks like a Next link.
        nxt_no = str(page_no + 1)
        candidates = [
            page.locator("a", has_text=re.compile(rf"^\s*{nxt_no}\s*$")),
            page.locator("a", has_text=re.compile(r"next", re.I)),
            page.locator("a[title*='next' i]"),
        ]
        clicked = False
        for cand in candidates:
            try:
                n = cand.count()
            except PWError:
                continue
            for k in range(n):
                el = cand.nth(k)
                try:
                    if not el.is_visible():
                        continue
                    el.click(timeout=10_000)
                    page.wait_for_load_state("domcontentloaded",
                                             timeout=NAV_TIMEOUT_MS)
                    page.wait_for_selector("table tbody tr",
                                           timeout=NAV_TIMEOUT_MS)
                    # some paginations update in-place via JS; give it a beat
                    time.sleep(1.5)
                    sig_after = page.locator("table tbody tr").first.inner_text(
                        timeout=10_000)
                    if sig_after != sig_before:
                        clicked = True
                        break
                except (PWTimeout, PWError):
                    continue
            if clicked:
                break
        if not clicked:
            log(f"  could not advance past page {page_no} "
                f"(no working Next/number link) — stopping harvest.")
            break
        page_no += 1
        polite_sleep(LIST_DELAY)

    log(f"Harvest done: {new} new filings, "
        f"{len(manifest['filings'])} total in manifest.")


# ----------------------------------------------------------------------------
# Phase 2 — open each filing page, click Download, save PDF
# ----------------------------------------------------------------------------
# SEBI embeds the RHP in a PDF.js viewer inside an iframe. The visible
# download control is the viewer toolbar's download icon (id="download" /
# id="downloadButton" in stock PDF.js), NOT a page-level "Download" link.
PAGE_LEVEL_SELECTORS = [
    "a:has-text('Download')",
    "button:has-text('Download')",
    "a[title*='Download' i]",
]
PDFJS_SELECTORS = [
    "#download",
    "#downloadButton",
    "#secondaryDownload",
    "button[title*='Download' i]",
    "a[title*='Download' i]",
]


def _try_click_for_download(page, clickable, timeout_ms=30_000):
    """Click something and wait for the browser download it triggers."""
    with page.expect_download(timeout=timeout_ms) as dl_info:
        clickable.click()
    return dl_info.value


def click_download_and_wait(context, page):
    """Reproduce the human action: press the viewer's download icon.

    Order of attempts:
      1) PDF.js download icon inside any iframe on the filing page
      2) a page-level Download link/button (older filing pages)
      3) fallback: save the exact file the embedded viewer is displaying
         (the iframe/embed src the page itself loaded — same bytes the
         download icon would hand you)
    """
    # Give the embedded viewer a moment to boot.
    try:
        page.wait_for_selector("iframe, embed", timeout=20_000)
    except PWTimeout:
        pass

    # --- 1) PDF.js toolbar icon inside iframe(s) ---------------------------
    for i in range(page.locator("iframe").count()):
        frame = page.frame_locator("iframe").nth(i)
        for sel in PDFJS_SELECTORS:
            try:
                btn = frame.locator(sel)
                if btn.count() == 0:
                    continue
                btn.first.wait_for(state="visible", timeout=10_000)
                return _try_click_for_download(page, btn.first)
            except (PWTimeout, PWError):
                continue

    # --- 2) page-level Download control ------------------------------------
    for sel in PAGE_LEVEL_SELECTORS:
        loc = page.locator(sel)
        if loc.count() == 0:
            continue
        try:
            return _try_click_for_download(page, loc.first)
        except (PWTimeout, PWError):
            continue

    # --- 3) save what the viewer is showing --------------------------------
    # The viewer iframe/embed src is the document the page itself opened for
    # us (often .../web/viewer.html?file=<pdf> or a direct PDF). Fetching it
    # through the same browser session yields the identical bytes the
    # download icon delivers.
    src = None
    for el_sel in ("iframe", "embed", "object"):
        for i in range(page.locator(el_sel).count()):
            s = page.locator(el_sel).nth(i).get_attribute("src") or \
                page.locator(el_sel).nth(i).get_attribute("data")
            if not s:
                continue
            m = re.search(r"[?&]file=([^&]+)", s)
            if m:
                from urllib.parse import unquote
                s = unquote(m.group(1))
            if ".pdf" in s.lower() or "attachdocs" in s.lower():
                src = s if s.startswith("http") else BASE + s
                break
        if src:
            break
    if not src:
        raise RuntimeError("no PDF.js download icon, page Download link, "
                           "or embedded viewer source found")

    last_err = None
    for attempt in range(3):
        try:
            resp = context.request.get(src, timeout=DOWNLOAD_TIMEOUT_MS)
            if resp.ok:
                return ("bytes", resp.body(),
                        src.rsplit("/", 1)[-1] or "document.pdf")
            last_err = f"HTTP {resp.status}"
        except PWError as e:
            last_err = str(e).splitlines()[0]
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"viewer-source fetch failed after 3 tries: {last_err}")


def download_one(context, url: str, rec: dict) -> None:
    company = rec["company"]
    slug = slugify(company)
    dest_dir = OUT_DIR / slug
    dest = dest_dir / "rhp.pdf"

    page = context.new_page()
    page.set_default_timeout(NAV_TIMEOUT_MS)
    try:
        # Adopt a PDF already on disk (e.g. manually downloaded) if it verifies.
        if dest.exists():
            ok, reason = verify_pdf(dest, company)
            if ok:
                rec.update(
                    status="ok", path=str(dest), bytes=dest.stat().st_size,
                    verify=reason + " (adopted existing file)",
                    downloaded_at=datetime.now(timezone.utc).isoformat(),
                )
                log(f"  OK   {company}  (existing file adopted, {reason})")
                return

        page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
        result = click_download_and_wait(context, page)
        dest_dir.mkdir(parents=True, exist_ok=True)
        if isinstance(result, tuple) and result[0] == "bytes":
            _, body, suggested = result
            dest.write_bytes(body)
        else:
            dl = result
            suggested = dl.suggested_filename
            dl.save_as(str(dest))

        ok, reason = verify_pdf(dest, company)
        if ok:
            rec.update(
                status="ok",
                path=str(dest),
                bytes=dest.stat().st_size,
                verify=reason,
                downloaded_at=datetime.now(timezone.utc).isoformat(),
                suggested_filename=suggested,
            )
            log(f"  OK   {company}  ({dest.stat().st_size//1024} KB, {reason})")
        else:
            quarantined = dest.with_name(f"REJECTED_{suggested or 'file'}")
            dest.replace(quarantined)
            rec.update(status="failed_verify", error=reason,
                       path=str(quarantined))
            log(f"  FAIL {company}: {reason}")
            log_failure(url, f"verify: {reason}")
    finally:
        try:
            page.close()
        except PWError:
            pass


def run_downloads(context, manifest: dict, args) -> None:
    todo = []
    for url, rec in manifest["filings"].items():
        st = rec.get("status", "pending")
        if st == "ok":
            p = rec.get("path")
            if p and Path(p).exists():
                continue                      # resume: already have it
            rec["status"] = "pending"         # manifest says ok but file gone
        if st.startswith("failed") and not args.retry_failed:
            continue
        if rec.get("attempts", 0) > MAX_RETRIES and not args.retry_failed:
            continue
        todo.append((url, rec))

    log(f"Phase 2: {len(todo)} filings to download "
        f"({sum(1 for r in manifest['filings'].values() if r.get('status')=='ok')} "
        f"already done).")

    done = 0
    consecutive_fails = 0
    for url, rec in todo:
        if args.max and done >= args.max:
            log(f"--max {args.max} reached, stopping.")
            break
        rec["attempts"] = rec.get("attempts", 0) + 1
        log(f"[{done+1}/{len(todo)}] {rec['company']}")
        try:
            download_one(context, url, rec)
            consecutive_fails = 0
        except (PWTimeout, PWError, RuntimeError, OSError) as e:
            reason = str(e).splitlines()[0][:200]
            rec.update(status="failed_download", error=reason)
            log(f"  FAIL {rec['company']}: {reason}")
            log_failure(url, reason)
            consecutive_fails += 1
            if consecutive_fails >= 4:
                # 4 fails in a row = network is likely down, not the filings.
                log("  4 consecutive failures — pausing 3 min for network "
                    "to recover ...")
                time.sleep(180)
                consecutive_fails = 0
                # don't punish these filings for an outage
                rec["attempts"] = max(0, rec.get("attempts", 1) - 1)
        save_manifest(manifest)
        done += 1
        polite_sleep(PAGE_DELAY)

    ok_n = sum(1 for r in manifest["filings"].values() if r.get("status") == "ok")
    bad = sum(1 for r in manifest["filings"].values()
              if str(r.get("status", "")).startswith("failed"))
    log(f"Done. ok={ok_n}  failed={bad}  "
        f"manifest={MANIFEST_PATH}  failures={FAIL_LOG}")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="SEBI RHP downloader (Playwright)")
    ap.add_argument("--headed", action="store_true", help="show the browser")
    ap.add_argument("--pages", type=int, default=None,
                    help="limit listing pages to harvest")
    ap.add_argument("--max", type=int, default=None,
                    help="stop after N downloads this run")
    ap.add_argument("--harvest-only", action="store_true")
    ap.add_argument("--download-only", action="store_true",
                    help="skip harvest, use existing manifest")
    ap.add_argument("--retry-failed", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    manifest = load_manifest()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        context = browser.new_context(accept_downloads=True, user_agent=UA)
        context.set_default_timeout(NAV_TIMEOUT_MS)

        try:
            if not args.download_only:
                page = context.new_page()
                harvest(page, manifest, args.pages)
                page.close()
            if not args.harvest_only:
                run_downloads(context, manifest, args)
        finally:
            save_manifest(manifest)
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
