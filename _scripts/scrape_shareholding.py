"""
_scripts/scrape_shareholding.py
================================
Scrapes quarterly shareholding patterns from Screener.in (free, no API key).
Populates: shareholding_history, ownership_signals

Data: Promoter%, FII%, DII%, MF%, Public%, Pledge%
Source: Screener.in company pages (public data, no login needed for basic patterns)

Schedule: Quarterly (after BSE quarterly filings — April, July, October, January)
On-demand: python _scripts/scrape_shareholding.py --symbols INFY TCS

Usage:
  python _scripts/scrape_shareholding.py --limit 100   # top 100 stocks
  python _scripts/scrape_shareholding.py --symbols RELIANCE INFY TCS HDFCBANK
"""

import os, sys, re, time, logging, argparse, datetime
import requests, psycopg2, psycopg2.extras
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122"}

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def ensure_tables(conn):
    cur = conn.cursor()
    # Create tables if missing
    cur.execute("""
        CREATE TABLE IF NOT EXISTS shareholding_history (
            id         SERIAL PRIMARY KEY,
            nse_symbol TEXT NOT NULL,
            quarter    TEXT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(nse_symbol, quarter)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ownership_signals (
            id         SERIAL PRIMARY KEY,
            nse_symbol TEXT NOT NULL UNIQUE,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.commit()
    # Add columns safely — works even if they already exist
    for col, typ in [
        ("quarter_date",    "DATE"),
        ("promoter_pct",    "NUMERIC(6,2)"),
        ("promoter_pledge", "NUMERIC(6,2)"),
        ("fii_pct",         "NUMERIC(6,2)"),
        ("dii_pct",         "NUMERIC(6,2)"),
        ("mf_pct",          "NUMERIC(6,2)"),
        ("public_pct",      "NUMERIC(6,2)"),
    ]:
        try:
            cur.execute(f"ALTER TABLE shareholding_history ADD COLUMN IF NOT EXISTS {col} {typ}")
            conn.commit()
        except Exception:
            conn.rollback()
    for col, typ in [
        ("promoter_trend",  "TEXT"),
        ("fii_trend",       "TEXT"),
        ("dii_trend",       "TEXT"),
        ("pledge_risk",     "TEXT"),
        ("insider_buying",  "BOOLEAN DEFAULT FALSE"),
        ("latest_quarter",  "TEXT"),
        ("promoter_pct",    "NUMERIC(6,2)"),
        ("fii_pct",         "NUMERIC(6,2)"),
        ("dii_pct",         "NUMERIC(6,2)"),
        ("pledge_pct",      "NUMERIC(6,2)"),
        ("signal",          "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE ownership_signals ADD COLUMN IF NOT EXISTS {col} {typ}")
            conn.commit()
        except Exception:
            conn.rollback()
    cur.close()

def get_symbols(conn, limit: int) -> list:
    cur = conn.cursor()
    cur.execute("""
        SELECT nse_symbol FROM stock_fundamentals
        WHERE nse_symbol IS NOT NULL AND market_cap > 500
        ORDER BY market_cap DESC NULLS LAST
        LIMIT %s
    """, (limit,))
    syms = [r[0] for r in cur.fetchall()]
    cur.close()
    return syms

def scrape_shareholding(session: requests.Session, symbol: str) -> list:
    """Scrape quarterly shareholding from Screener.in."""
    quarters = []
    
    for url in [
        f"https://www.screener.in/company/{symbol}/consolidated/",
        f"https://www.screener.in/company/{symbol}/",
    ]:
        try:
            r = session.get(url, timeout=12)
            if not r.ok:
                continue
            
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Find shareholding section
            sh_section = None
            for section in soup.find_all("section"):
                h2 = section.find("h2")
                if h2 and "Shareholding" in h2.get_text():
                    sh_section = section
                    break
            
            if not sh_section:
                # Try finding table with promoter data
                for table in soup.find_all("table"):
                    headers = [th.get_text(strip=True) for th in table.find_all("th")]
                    if any("Promoter" in h for h in headers):
                        sh_section = table
                        break
            
            if not sh_section:
                continue
            
            # Parse table
            table = sh_section.find("table") if sh_section.name != "table" else sh_section
            if not table:
                continue
            
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            
            # Get quarter headers from first row
            header_row = rows[0]
            quarter_headers = [th.get_text(strip=True) for th in header_row.find_all(["th","td"])]
            
            # Parse data rows
            data: dict = {}
            for row in rows[1:]:
                cells = row.find_all(["th","td"])
                if not cells:
                    continue
                label = cells[0].get_text(strip=True).lower()
                values = [c.get_text(strip=True) for c in cells[1:]]
                
                key = None
                if "promoter" in label and "pledge" not in label:
                    key = "promoter_pct"
                elif "pledge" in label:
                    key = "promoter_pledge"
                elif "fii" in label or "foreign" in label:
                    key = "fii_pct"
                elif "dii" in label:
                    key = "dii_pct"
                elif "mutual fund" in label or "mf" == label:
                    key = "mf_pct"
                elif "public" in label:
                    key = "public_pct"
                
                if key:
                    data[key] = values
            
            if not data:
                continue
            
            # Map to quarters — use header columns
            for i, qtr_label in enumerate(quarter_headers[1:]):
                if not qtr_label:
                    continue
                
                # Parse quarter label e.g. "Jun 2026" → "2026Q1"
                quarter_str = parse_quarter(qtr_label)
                if not quarter_str:
                    continue
                
                q_data = {"quarter": quarter_str}
                for key, values in data.items():
                    if i < len(values):
                        try:
                            q_data[key] = float(re.sub(r"[^0-9.]", "", values[i]) or 0)
                        except:
                            q_data[key] = None
                
                if q_data.get("promoter_pct"):
                    quarters.append(q_data)
            
            if quarters:
                break
                
        except Exception as e:
            log.debug(f"  {symbol} scrape error: {e}")
    
    return quarters[:8]  # last 8 quarters

def parse_quarter(label: str) -> str | None:
    """Convert 'Jun 2026' → '2026Q1', 'Sep 2025' → '2025Q2' etc."""
    months = {
        "mar": "Q4", "jun": "Q1", "sep": "Q2", "dec": "Q3",
        "jan": "Q4", "feb": "Q4", "apr": "Q1", "may": "Q1",
        "jul": "Q2", "aug": "Q2", "oct": "Q3", "nov": "Q3",
    }
    label = label.lower().strip()
    for month, qtr in months.items():
        if month in label:
            year_match = re.search(r"\d{4}", label)
            if year_match:
                return f"{year_match.group()}{qtr}"
    return None

def compute_signal(quarters: list) -> dict:
    """Compute ownership trend signals from quarterly history."""
    if not quarters:
        return {}
    
    latest = quarters[0]
    
    def trend(key: str) -> str:
        vals = [q.get(key) for q in quarters[:4] if q.get(key) is not None]
        if len(vals) < 2:
            return "STABLE"
        diff = vals[0] - vals[-1]
        if diff > 1.0:   return "INCREASING"
        if diff < -1.0:  return "DECREASING"
        return "STABLE"
    
    pledge = latest.get("promoter_pledge", 0) or 0
    pledge_risk = ("HIGH" if pledge > 25 else
                   "MEDIUM" if pledge > 10 else
                   "LOW" if pledge > 0 else "NONE")
    
    # Signal logic
    prom_trend = trend("promoter_pct")
    fii_trend  = trend("fii_pct")
    dii_trend  = trend("dii_pct")
    
    bullish_signals = sum([
        prom_trend == "INCREASING",
        fii_trend  == "INCREASING",
        dii_trend  == "INCREASING",
        pledge_risk in ("NONE", "LOW"),
    ])
    bearish_signals = sum([
        prom_trend == "DECREASING",
        pledge_risk in ("HIGH", "MEDIUM"),
    ])
    
    signal = ("BULLISH" if bullish_signals >= 3 else
              "BEARISH" if bearish_signals >= 2 else "NEUTRAL")
    
    return {
        "promoter_trend":  prom_trend,
        "fii_trend":       fii_trend,
        "dii_trend":       dii_trend,
        "pledge_risk":     pledge_risk,
        "latest_quarter":  latest.get("quarter"),
        "promoter_pct":    latest.get("promoter_pct"),
        "fii_pct":         latest.get("fii_pct"),
        "dii_pct":         latest.get("dii_pct"),
        "pledge_pct":      latest.get("promoter_pledge"),
        "signal":          signal,
    }

def save_shareholding(conn, symbol: str, quarters: list, signal_data: dict):
    cur = conn.cursor()
    
    for q in quarters:
        quarter_str = q.get("quarter")
        if not quarter_str:
            continue
        cur.execute("""
            INSERT INTO shareholding_history
                (nse_symbol, quarter, promoter_pct, promoter_pledge,
                 fii_pct, dii_pct, mf_pct, public_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (nse_symbol, quarter) DO UPDATE SET
                promoter_pct    = COALESCE(EXCLUDED.promoter_pct, shareholding_history.promoter_pct),
                promoter_pledge = COALESCE(EXCLUDED.promoter_pledge, shareholding_history.promoter_pledge),
                fii_pct         = COALESCE(EXCLUDED.fii_pct, shareholding_history.fii_pct),
                dii_pct         = COALESCE(EXCLUDED.dii_pct, shareholding_history.dii_pct),
                mf_pct          = COALESCE(EXCLUDED.mf_pct, shareholding_history.mf_pct),
                public_pct      = COALESCE(EXCLUDED.public_pct, shareholding_history.public_pct)
        """, (
            symbol, quarter_str,
            q.get("promoter_pct"), q.get("promoter_pledge"),
            q.get("fii_pct"), q.get("dii_pct"),
            q.get("mf_pct"), q.get("public_pct"),
        ))
    
    if signal_data:
        cur.execute("""
            INSERT INTO ownership_signals
                (nse_symbol, promoter_trend, fii_trend, dii_trend, pledge_risk,
                 latest_quarter, promoter_pct, fii_pct, dii_pct, pledge_pct,
                 signal)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (nse_symbol) DO UPDATE SET
                promoter_trend = EXCLUDED.promoter_trend,
                fii_trend      = EXCLUDED.fii_trend,
                dii_trend      = EXCLUDED.dii_trend,
                pledge_risk    = EXCLUDED.pledge_risk,
                latest_quarter = EXCLUDED.latest_quarter,
                promoter_pct   = EXCLUDED.promoter_pct,
                fii_pct        = EXCLUDED.fii_pct,
                dii_pct        = EXCLUDED.dii_pct,
                pledge_pct     = EXCLUDED.pledge_pct,
                signal         = EXCLUDED.signal
        """, (
            symbol,
            signal_data.get("promoter_trend"),
            signal_data.get("fii_trend"),
            signal_data.get("dii_trend"),
            signal_data.get("pledge_risk"),
            signal_data.get("latest_quarter"),
            signal_data.get("promoter_pct"),
            signal_data.get("fii_pct"),
            signal_data.get("dii_pct"),
            signal_data.get("pledge_pct"),
            signal_data.get("signal"),
        ))
    
    conn.commit()
    cur.close()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+")
    p.add_argument("--limit",   type=int, default=100)
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_db()
    log.info("Connected to DB")
    ensure_tables(conn)

    symbols = args.symbols or get_symbols(conn, args.limit)
    log.info(f"Scraping shareholding for {len(symbols)} stocks")
    log.info("=" * 60)

    session = requests.Session()
    session.headers.update(HEADERS)

    ok = 0; skipped = 0
    for i, sym in enumerate(symbols):
        quarters = scrape_shareholding(session, sym)
        if not quarters:
            skipped += 1
            if i % 20 == 0:
                log.info(f"  [{i+1}/{len(symbols)}] {ok} saved, {skipped} skipped…")
            time.sleep(0.5)
            continue
        
        signal_data = compute_signal(quarters)
        save_shareholding(conn, sym, quarters, signal_data)
        ok += 1
        log.info(f"  ✓ {sym}: {len(quarters)}Q | {signal_data.get('signal')} | "
                 f"Promoter {signal_data.get('promoter_pct','?')}% "
                 f"FII {signal_data.get('fii_pct','?')}% "
                 f"Pledge {signal_data.get('pledge_risk','?')}")
        time.sleep(1.0)

    conn.close()
    log.info("=" * 60)
    log.info(f"Done. {ok} stocks saved, {skipped} skipped (no data found)")

if __name__ == "__main__":
    main()
