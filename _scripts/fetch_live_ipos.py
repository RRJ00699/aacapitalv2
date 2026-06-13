#!/usr/bin/env python3
"""
_scripts/fetch_live_ipos.py
─────────────────────────────────────────────────────────────────────────────
Fetches live open IPOs from NSE + upcoming pipeline from Chittorgarh
Inserts into ipo_live table in Neon PostgreSQL

Usage:
  python _scripts/fetch_live_ipos.py               # fetch + insert
  python _scripts/fetch_live_ipos.py --dry-run      # print only
  python _scripts/fetch_live_ipos.py --source nse   # NSE only
  python _scripts/fetch_live_ipos.py --source chittorgarh  # pipeline only

Install:
  pip install curl_cffi beautifulsoup4 psycopg2-binary python-dotenv
"""

import sys
import json
import os
import time
import argparse
from datetime import datetime, date
from pathlib import Path

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    print("ERROR: pip install curl_cffi", file=sys.stderr)
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: pip install beautifulsoup4", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(".env.local" if Path(".env.local").exists() else ".env")
except ImportError:
    pass

NSE_BASE = "https://www.nseindia.com"
CHITTORGARH_URL = "https://www.chittorgarh.com/report/mainboard-ipo-list-in-india-bse-nse/83/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_BASE,
}

# ─── NSE session ──────────────────────────────────────────────────────────────
def make_nse_session():
    session = cffi_requests.Session(impersonate="chrome120")
    try:
        r = session.get(NSE_BASE, headers=HEADERS, timeout=12)
        print(f"[nse] Prime → HTTP {r.status_code}")
        time.sleep(1.2)
    except Exception as e:
        print(f"[nse] Prime warning: {e}", file=sys.stderr)
    return session

# ─── Task 1: NSE live IPOs ────────────────────────────────────────────────────
def fetch_nse_live_ipos(session) -> list[dict]:
    """Fetch currently open IPOs from NSE public-issues API."""
    url = f"{NSE_BASE}/api/public-issues"
    try:
        resp = session.get(url, headers={**HEADERS, "Referer": f"{NSE_BASE}/market-data/all-upcoming-issues-ipo"}, timeout=15)
        if resp.status_code != 200:
            print(f"[nse] HTTP {resp.status_code}", file=sys.stderr)
            return []
        raw = resp.json()
        issues = raw if isinstance(raw, list) else raw.get("data", raw.get("issues", []))
        result = []
        for ipo in issues:
            result.append({
                "source":       "NSE",
                "name":         ipo.get("companyName") or ipo.get("issuerName") or "",
                "symbol":       ipo.get("symbol") or ipo.get("ticker") or "",
                "open_date":    ipo.get("openDate") or ipo.get("issueOpenDate") or "",
                "close_date":   ipo.get("closeDate") or ipo.get("issueCloseDate") or "",
                "price_band_low":  _parse_price(ipo.get("minBidQuantity") or ipo.get("priceBandLow") or "0"),
                "price_band_high": _parse_price(ipo.get("issuePriceLow") or ipo.get("priceBandHigh") or "0"),
                "issue_size":   _parse_price(ipo.get("issueSize") or "0"),
                "lot_size":     int(ipo.get("lotSize") or ipo.get("minBidQuantity") or 0),
                "status":       _derive_status(ipo.get("openDate") or "", ipo.get("closeDate") or ""),
                "series":       ipo.get("series") or "EQ",
                "listing_exchange": ipo.get("listedOn") or "NSE,BSE",
                "subscription_times": None,
                "gmp":          None,
            })
        print(f"[nse] {len(result)} IPOs fetched")
        return result
    except Exception as e:
        print(f"[nse] Fetch error: {e}", file=sys.stderr)
        return []

# ─── Task 2: Chittorgarh pipeline scraper ────────────────────────────────────
def fetch_chittorgarh_pipeline() -> list[dict]:
    """Scrape upcoming + open IPOs including GMP from Chittorgarh."""
    try:
        import requests as std_requests
        resp = std_requests.get(CHITTORGARH_URL, headers={
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "text/html",
        }, timeout=20)
        soup = BeautifulSoup(resp.content, "html.parser")
        table = soup.find("table")
        if not table:
            print("[chittorgarh] No table found", file=sys.stderr)
            return []

        rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")[1:]
        result = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            name       = cols[0].get_text(strip=True)
            open_date  = cols[1].get_text(strip=True) if len(cols) > 1 else ""
            close_date = cols[2].get_text(strip=True) if len(cols) > 2 else ""
            price_band = cols[3].get_text(strip=True) if len(cols) > 3 else ""
            gmp_text   = cols[4].get_text(strip=True) if len(cols) > 4 else ""
            issue_size = cols[5].get_text(strip=True) if len(cols) > 5 else ""

            # Parse GMP
            gmp = None
            try:
                gmp_clean = gmp_text.replace("₹","").replace(",","").strip()
                if gmp_clean and gmp_clean not in ["-","—","N/A",""]:
                    gmp = float(gmp_clean.split()[0])
            except Exception:
                pass

            # Parse price band
            pb_low, pb_high = 0.0, 0.0
            try:
                parts = price_band.replace("₹","").replace(",","").split("-")
                pb_low  = float(parts[0].strip()) if parts else 0
                pb_high = float(parts[-1].strip()) if len(parts) > 1 else pb_low
            except Exception:
                pass

            status = _derive_status(open_date, close_date)
            if status == "LISTED":
                continue  # skip already listed

            result.append({
                "source":          "CHITTORGARH",
                "name":            name,
                "symbol":          "",
                "open_date":       open_date,
                "close_date":      close_date,
                "price_band_low":  pb_low,
                "price_band_high": pb_high,
                "issue_size":      _parse_price(issue_size),
                "lot_size":        0,
                "status":          status,
                "series":          "EQ",
                "listing_exchange":"NSE,BSE",
                "subscription_times": None,
                "gmp":             gmp,
            })

        print(f"[chittorgarh] {len(result)} IPOs scraped")
        return result
    except Exception as e:
        print(f"[chittorgarh] Scrape error: {e}", file=sys.stderr)
        return []

# ─── Helpers ──────────────────────────────────────────────────────────────────
def _parse_price(val: str) -> float:
    try:
        return float(str(val).replace("₹","").replace(",","").replace("Cr","").strip().split()[0])
    except Exception:
        return 0.0

def _derive_status(open_date: str, close_date: str) -> str:
    try:
        today = date.today()
        for fmt in ["%d-%b-%Y", "%b %d, %Y", "%d/%m/%Y", "%Y-%m-%d", "%d %b %Y"]:
            try:
                o = datetime.strptime(open_date.strip(), fmt).date()
                c = datetime.strptime(close_date.strip(), fmt).date()
                if today < o:  return "UPCOMING"
                if today > c:  return "CLOSED"
                return "OPEN"
            except Exception:
                continue
    except Exception:
        pass
    return "UPCOMING"

# ─── Merge NSE + Chittorgarh ─────────────────────────────────────────────────
def merge_sources(nse: list[dict], chitto: list[dict]) -> list[dict]:
    """NSE is authoritative. Enrich with Chittorgarh GMP where available."""
    merged = {ipo["name"].upper()[:20]: ipo for ipo in nse}
    for c in chitto:
        key = c["name"].upper()[:20]
        if key in merged:
            # Enrich NSE record with GMP from Chittorgarh
            if c.get("gmp") is not None:
                merged[key]["gmp"] = c["gmp"]
        else:
            merged[key] = c
    return list(merged.values())

# ─── DB upsert ────────────────────────────────────────────────────────────────
def upsert_to_db(ipos: list[dict], dry_run: bool):
    if dry_run:
        print(f"\n[dry-run] Would upsert {len(ipos)} IPOs:")
        for ipo in ipos:
            print(f"  {ipo['status']:8s} {ipo['name'][:40]:40s} | {ipo['open_date']} → {ipo['close_date']} | GMP: {ipo.get('gmp','—')}")
        return

    db_url = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not db_url:
        print("[db] ERROR: No DATABASE_URL", file=sys.stderr)
        return
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur  = conn.cursor()
        for ipo in ipos:
            cur.execute("""
                INSERT INTO ipo_live (
                    name, symbol, open_date, close_date,
                    price_band_low, price_band_high, issue_size, lot_size,
                    status, listing_exchange, gmp, source, updated_at
                ) VALUES (
                    %(name)s, %(symbol)s, %(open_date)s, %(close_date)s,
                    %(price_band_low)s, %(price_band_high)s, %(issue_size)s, %(lot_size)s,
                    %(status)s, %(listing_exchange)s, %(gmp)s, %(source)s, NOW()
                )
                ON CONFLICT (name) DO UPDATE SET
                    status        = EXCLUDED.status,
                    gmp           = COALESCE(EXCLUDED.gmp, ipo_live.gmp),
                    open_date     = EXCLUDED.open_date,
                    close_date    = EXCLUDED.close_date,
                    price_band_low= EXCLUDED.price_band_low,
                    price_band_high=EXCLUDED.price_band_high,
                    updated_at    = NOW()
            """, ipo)
        conn.commit()
        conn.close()
        print(f"[db] ✓ Upserted {len(ipos)} IPOs")
    except Exception as e:
        print(f"[db] Error: {e}", file=sys.stderr)

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--source",   choices=["nse","chittorgarh","both"], default="both")
    args = parser.parse_args()

    print("━" * 52)
    print(" AACapital — IPO Live Data Ingestion")
    print("━" * 52)

    nse_ipos, chitto_ipos = [], []

    if args.source in ["nse", "both"]:
        session = make_nse_session()
        nse_ipos = fetch_nse_live_ipos(session)

    if args.source in ["chittorgarh", "both"]:
        chitto_ipos = fetch_chittorgarh_pipeline()

    all_ipos = merge_sources(nse_ipos, chitto_ipos) if args.source == "both" else (nse_ipos or chitto_ipos)

    print(f"\n[merge] {len(all_ipos)} total unique IPOs")
    upsert_to_db(all_ipos, dry_run=args.dry_run)
    print("\n✅ Done")

if __name__ == "__main__":
    main()
