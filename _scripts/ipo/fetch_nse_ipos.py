#!/usr/bin/env python3
"""
_scripts/ipo/fetch_nse_ipos.py
─────────────────────────────────────────────────────────────────────────────
Canonical live-IPO ingestion for AACapital.

Pulls OPEN + UPCOMING IPOs (mainboard + SME) from NSE's PUBLIC issue feeds and
upserts them into `ipo_intelligence` — the SAME table the UI reads via
/api/ipo/playbook. After this runs, ipo_play_selector.py scores the new rows.

Why this exists / what it replaces:
  - fetch_live_ipos.py wrote to a dead-end `ipo_live` table the UI never reads,
    and depended on Chittorgarh (dead). This writes to ipo_intelligence and uses
    NSE public feeds only. No Chittorgarh, no Yahoo.

NSE is bot-protected: a naive requests.get() returns 401/403. We use curl_cffi
with Chrome TLS impersonation, prime cookies on the homepage + the IPO landing
page, then call the JSON API with a matching Referer.

Pipeline shape (unchanged): NSE public feed -> upsert ipo_intelligence -> Neon
-> ipo_play_selector.py scores -> UI reads ONLY from Neon.

Usage:
  python _scripts/ipo/fetch_nse_ipos.py                # fetch + upsert
  python _scripts/ipo/fetch_nse_ipos.py --dry-run      # print, no DB writes
  python _scripts/ipo/fetch_nse_ipos.py --no-sme       # mainboard only

Install:
  pip install curl_cffi psycopg2-binary python-dotenv
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime, date, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetch_nse_ipos")

try:
    from curl_cffi import requests as cffi
except ImportError:
    log.error("Missing dependency: pip install curl_cffi")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(".env.local" if Path(".env.local").exists() else ".env")
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

NSE_BASE = "https://www.nseindia.com"
IPO_LANDING = f"{NSE_BASE}/market-data/all-upcoming-issues-ipo"
# Public JSON feeds backing the NSE IPO landing page.
FEEDS = {
    "current":      f"{NSE_BASE}/api/ipo-current-issue",                 # OPEN now
    "upcoming_ipo": f"{NSE_BASE}/api/all-upcoming-issues?category=ipo",  # mainboard upcoming
    "upcoming_sme": f"{NSE_BASE}/api/all-upcoming-issues?category=sme",  # SME upcoming
}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": IPO_LANDING,
}

# Values NSE / pandas exports use for "missing" that must become real NULLs.
_NULLISH = {"", "-", "—", "n/a", "na", "nan", "none", "null", "tbd", "--"}


# ── coercion helpers ──────────────────────────────────────────────────────────
def clean_str(v):
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in _NULLISH else s


def clean_num(v):
    """Parse a numeric out of messy strings ('₹ 1,234.5 Cr' -> 1234.5)."""
    s = clean_str(v)
    if s is None:
        return None
    s = (s.replace("\u20b9", "").replace(",", "")
           .replace("Cr", "").replace("cr", "").strip())
    try:
        return float(s.split()[0])
    except (ValueError, IndexError):
        return None


def parse_date(v):
    """Parse NSE date strings to ISO 'YYYY-MM-DD'. NSE uses dd-MMM-yyyy."""
    s = clean_str(v)
    if s is None:
        return None
    s = s.split("T")[0].strip()  # tolerate ISO datetimes
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y",
                "%b %d, %Y", "%d %b %Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    log.warning("Unparseable date: %r", v)
    return None


def first(d: dict, *keys):
    """First non-nullish value among the given keys."""
    for k in keys:
        if k in d:
            val = clean_str(d[k])
            if val is not None:
                return val
    return None


# ── NSE session + fetch ───────────────────────────────────────────────────────
def make_session():
    s = cffi.Session(impersonate="chrome124")
    try:
        s.get(NSE_BASE, headers=HEADERS, timeout=12)
        time.sleep(0.8)
        s.get(IPO_LANDING, headers=HEADERS, timeout=12)  # cookie for the IPO section
        time.sleep(0.8)
        log.info("NSE session primed")
    except Exception as e:  # noqa: BLE001
        log.warning("NSE prime warning (continuing): %s", e)
    return s


def fetch_feed(session, url: str) -> list[dict]:
    try:
        r = session.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            log.warning("HTTP %s for %s", r.status_code, url)
            return []
        raw = r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("Fetch/parse failed for %s: %s", url, e)
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("data", "issues", "records", "list"):
            if isinstance(raw.get(key), list):
                return raw[key]
    return []


# ── normalise one NSE record -> ipo_intelligence columns ──────────────────────
def normalise(item: dict, is_sme: bool) -> dict | None:
    company = first(item, "companyName", "issuerName", "name", "company")
    if not company:
        return None

    open_d  = parse_date(first(item, "issueStartDate", "openDate", "bidOpenDate",
                               "issueOpenDate", "startDate"))
    close_d = parse_date(first(item, "issueEndDate", "closeDate", "bidCloseDate",
                               "issueCloseDate", "endDate"))
    list_d  = parse_date(first(item, "listingDate", "dateOfListing"))

    # price band -> issue_price = upper end of the band when present
    price_raw = first(item, "issuePrice", "priceBand", "priceRange", "price")
    issue_price = None
    if price_raw:
        parts = [clean_num(p) for p in str(price_raw).replace("to", "-").split("-")]
        parts = [p for p in parts if p is not None]
        issue_price = max(parts) if parts else None

    row = {
        "company_name": company,
        "symbol":       first(item, "symbol", "ticker"),
        "is_sme":       is_sme,
        "issue_price":  issue_price,
        "issue_size_cr": clean_num(first(item, "issueSize", "issueSizeCr")),
        "lot_size":     int(clean_num(first(item, "lotSize", "marketLot", "minBidQuantity")) or 0) or None,
        "open_date":    open_d,
        "close_date":   close_d,
        "listing_date": list_d,
        "data_source":  "NSE",
    }
    # Drop keys with no value so the upsert never overwrites existing data with NULL.
    return {k: v for k, v in row.items() if v is not None}


def collect(session, include_sme: bool) -> list[dict]:
    seen, out = {}, []
    plan = [("current", False), ("upcoming_ipo", False)]
    if include_sme:
        plan.append(("upcoming_sme", True))
    for feed_key, sme in plan:
        items = fetch_feed(session, FEEDS[feed_key])
        log.info("%s -> %d raw records", feed_key, len(items))
        for it in items:
            row = normalise(it, sme)
            if not row:
                continue
            key = row["company_name"].upper()
            if key not in seen:          # first feed wins (current > upcoming)
                seen[key] = True
                out.append(row)
    return out


# ── DB upsert (match on company_name; never null existing columns) ────────────
def upsert(rows: list[dict], dry_run: bool):
    if dry_run:
        log.info("[dry-run] would upsert %d IPOs:", len(rows))
        for r in rows:
            log.info("  %-40s open=%s close=%s listing=%s sme=%s",
                     r["company_name"][:40], r.get("open_date"),
                     r.get("close_date"), r.get("listing_date"), r.get("is_sme"))
        return 0

    if not DATABASE_URL:
        log.error("No DATABASE_URL / NEON_DATABASE_URL set")
        sys.exit(1)

    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    n = 0
    try:
        cur = conn.cursor()
        for r in rows:
            company = r["company_name"]
            cur.execute("SELECT id FROM ipo_intelligence WHERE company_name = %s LIMIT 1", (company,))
            hit = cur.fetchone()
            fields = {k: v for k, v in r.items() if k != "company_name"}
            fields["updated_at"] = datetime.now(timezone.utc)
            if hit:
                sets = ", ".join(f"{k} = %s" for k in fields)
                cur.execute(f"UPDATE ipo_intelligence SET {sets} WHERE company_name = %s",
                            list(fields.values()) + [company])
            else:
                cols = ["company_name"] + list(fields.keys())
                ph   = ", ".join(["%s"] * len(cols))
                cur.execute(f"INSERT INTO ipo_intelligence ({', '.join(cols)}) VALUES ({ph})",
                            [company] + list(fields.values()))
            n += 1
        conn.commit()
    finally:
        conn.close()
    log.info("Upserted %d IPOs into ipo_intelligence", n)
    return n


def main():
    ap = argparse.ArgumentParser(description="Fetch live NSE IPOs into ipo_intelligence")
    ap.add_argument("--dry-run", action="store_true", help="print only, no DB writes")
    ap.add_argument("--no-sme", action="store_true", help="mainboard only (skip SME feed)")
    args = ap.parse_args()

    log.info("AACapital — NSE IPO ingestion (%s)", date.today().isoformat())
    session = make_session()
    rows = collect(session, include_sme=not args.no_sme)
    log.info("Normalised %d unique live IPOs", len(rows))
    if not rows:
        log.warning("No live IPOs returned. NSE feed may be empty (no open/upcoming) "
                    "or the cookie handshake was blocked. Exiting without writes.")
        return
    upsert(rows, dry_run=args.dry_run)
    log.info("Done. Run ipo_play_selector.py next to score new rows.")


if __name__ == "__main__":
    main()
