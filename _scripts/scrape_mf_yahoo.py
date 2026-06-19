"""
_scripts/scrape_mf_yahoo.py
=============================
Fetches MF equity holdings from Yahoo Finance via yahooquery.
No login needed. Covers 1000+ Indian MF schemes automatically.

Install: pip install yahooquery psycopg2-binary

Usage:
  python _scripts/scrape_mf_yahoo.py                  # top 30 equity funds
  python _scripts/scrape_mf_yahoo.py --funds 50        # top 50 funds
  python _scripts/scrape_mf_yahoo.py --ticker 0P0000XW8F.BO  # specific fund

Schedule: Monthly via GitHub Actions (monthly-amfi.yml)
On-demand: Settings → Data Pipeline button
"""

import os, sys, re, time, logging, argparse, datetime
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

# ── Top Indian equity MF Yahoo tickers ────────────────────────────────────────
# Discovered via yahooquery search("HDFC Equity Direct Growth") etc.
# Covers large/mid/small/flexi cap across major AMCs
TOP_FUNDS = [
    # Small Cap
    ("0P0000XVFY.BO", "Nippon India Small Cap Fund"),
    ("0P0001297N.BO", "HDFC Small Cap Fund"),
    ("0P0000XW86.BO", "SBI Small Cap Fund"),
    ("0P0000YWL2.BO", "Axis Small Cap Fund"),
    ("0P0000XVG7.BO", "Kotak Small Cap Fund"),
    ("0P00011BCE.BO", "Tata Small Cap Fund"),
    ("0P000187B0.BO", "Quant Small Cap Fund"),
    ("0P0000YWL4.BO", "ICICI Prudential Smallcap Fund"),
    ("0P00014B4W.BO", "Invesco India Smallcap Fund"),
    ("0P000150K2.BO", "Canara Robeco Small Cap Fund"),
    # Mid Cap
    ("0P0000XW8F.BO", "HDFC Mid-Cap Opportunities Fund"),
    ("0P0000XVDP.BO", "Nippon India Growth Fund"),
    ("0P0000XVG1.BO", "Kotak Emerging Equity Fund"),
    ("0P00012ALS.BO", "Motilal Oswal Midcap Fund"),
    ("0P0000XW54.BO", "SBI Magnum MidCap Fund"),
    ("0P0000XW7Y.BO", "Axis Midcap Fund"),
    ("0P0000YWL5.BO", "ICICI Prudential Midcap Fund"),
    ("0P0000XW69.BO", "DSP Midcap Fund"),
    ("0P0000XVFC.BO", "Mirae Asset Midcap Fund"),
    ("0P00017ZPC.BO", "Quant Mid Cap Fund"),
    # Flexi Cap
    ("0P0000YWL1.BO", "Parag Parikh Flexi Cap Fund"),
    ("0P0000XW97.BO", "HDFC Flexi Cap Fund"),
    ("0P0000XW1O.BO", "SBI Flexi Cap Fund"),
    ("0P0000XVGL.BO", "Kotak Flexi Cap Fund"),
    ("0P0000XWN9.BO", "UTI Flexi Cap Fund"),
    ("0P0000XVEE.BO", "Mirae Asset Flexi Cap Fund"),
    ("0P00017ZP7.BO", "Quant Flexi Cap Fund"),
    ("0P0000YWL0.BO", "ICICI Prudential Flexi Cap Fund"),
    ("0P0000XW4L.BO", "Canara Robeco Flexi Cap Fund"),
    # Large Cap
    ("0P0000XVG6.BO", "Nippon India Large Cap Fund"),
    ("0P0000XVEX.BO", "Mirae Asset Large Cap Fund"),
    ("0P0000XW93.BO", "HDFC Top 100 Fund"),
    ("0P0000XW19.BO", "SBI Bluechip Fund"),
    ("0P0000YWKZ.BO", "ICICI Prudential Bluechip Fund"),
    ("0P0000XVGK.BO", "Kotak Bluechip Fund"),
    ("0P0000XW55.BO", "SBI Large & Midcap Fund"),
    ("0P0000XVFN.BO", "Mirae Asset Large & Midcap Fund"),
    ("0P0000XW8C.BO", "HDFC Large and Mid Cap Fund"),
    ("0P0000XVFT.BO", "Nippon India Large & Mid Cap Fund"),
    # Multi Cap & ELSS
    ("0P00017ZP9.BO", "Quant Active Fund"),
    ("0P0000XW91.BO", "HDFC ELSS Tax Saver Fund"),
    ("0P0000XVFV.BO", "Nippon India Multi Cap Fund"),
    ("0P0000XW2G.BO", "SBI Long Term Equity Fund"),
    ("0P0000XW51.BO", "ICICI Prudential Multi-Asset Fund"),
    ("0P00017ZPF.BO", "Quant ELSS Tax Saver Fund"),
    ("0P0000XW6F.BO", "Mirae Asset ELSS Tax Saver Fund"),
    ("0P0000XVG8.BO", "Kotak Multi Cap Fund"),
    ("0P0000XW8G.BO", "HDFC Multi Cap Fund"),
    ("0P0000XW3L.BO", "Axis ELSS Tax Saver Fund"),
    # Additional Small Cap
    ("0P0000XVOY.BO", "DSP Small Cap Fund"),
    ("0P0000XW2B.BO", "Franklin India Smaller Companies Fund"),
    ("0P0001510C.BO", "Edelweiss Small Cap Fund"),
    ("0P0001AYY6.BO", "Bandhan Small Cap Fund"),
    ("0P0001BMCH.BO", "HSBC Small Cap Fund"),
    ("0P0001MZPK.BO", "UTI Small Cap Fund"),
    ("0P00017XF7.BO", "Baroda BNP Paribas Small Cap Fund"),
    # Additional Mid Cap
    ("0P0000XW0X.BO", "Tata Midcap Growth Fund"),
    ("0P0000XW1G.BO", "Canara Robeco Mid Cap Fund"),
    ("0P0000XWBY.BO", "Franklin India Prima Fund"),
    ("0P0000XWNR.BO", "UTI Mid Cap Fund"),
    ("0P0000XV9Y.BO", "Edelweiss Mid Cap Fund"),
    ("0P0000XVFF.BO", "Sundaram Mid Cap Fund"),
    ("0P0001BMCC.BO", "HSBC Midcap Fund"),
    ("0P00017XF6.BO", "Baroda BNP Paribas Midcap Fund"),
    ("0P0001K27C.BO", "WhiteOak Capital Mid Cap Fund"),
    ("0P00012ALS.BO", "Motilal Oswal Midcap Fund"),
]

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def ensure_tables(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mf_stock_summary (
            id SERIAL PRIMARY KEY,
            nse_symbol TEXT NOT NULL,
            month DATE NOT NULL,
            fund_count INTEGER DEFAULT 0,
            amc_count INTEGER DEFAULT 0,
            net_additions INTEGER DEFAULT 0,
            net_exits INTEGER DEFAULT 0,
            accumulation_score NUMERIC(6,2),
            UNIQUE(nse_symbol, month)
        );
        ALTER TABLE mf_stock_summary ADD COLUMN IF NOT EXISTS total_value_cr NUMERIC(14,2);
        ALTER TABLE mf_stock_summary ADD COLUMN IF NOT EXISTS signal TEXT;

        CREATE TABLE IF NOT EXISTS mf_scheme_holdings (
            id SERIAL PRIMARY KEY,
            nse_symbol TEXT NOT NULL,
            month DATE NOT NULL,
            amc_name TEXT,
            scheme_name TEXT,
            market_value_cr NUMERIC(14,2) DEFAULT 0,
            portfolio_weight_pct NUMERIC(6,2)
        );
    """)
    conn.commit()
    cur.close()

def clean_symbol(yahoo_sym: str) -> str:
    """Convert RELIANCE.NS or RELIANCE.BO → RELIANCE"""
    return re.sub(r'\.(NS|BO|BSE)$', '', str(yahoo_sym or '').strip().upper())

def fetch_fund_holdings(ticker: str, fund_name: str) -> list:
    """Fetch equity holdings for one MF ticker via yahooquery fund_top_holdings."""
    try:
        from yahooquery import Ticker
        fund   = Ticker(ticker)
        amc    = fund_name.split()[0] if fund_name else "Unknown"
        results = []

        # Primary: fund_top_holdings — MultiIndex(fund_ticker, row)
        df = fund.fund_top_holdings
        if df is not None and hasattr(df, 'empty') and not df.empty:
            # Drop the fund ticker level from MultiIndex, keep row level
            if hasattr(df.index, 'levels'):
                df = df.droplevel(0)  # removes "0P0000XVFY.BO" level, keeps row number
            for _, row in df.iterrows():
                sym_raw = str(row.get('symbol', '') or '')
                name    = str(row.get('holdingName', '') or '')
                weight  = float(row.get('holdingPercent', 0) or 0)
                if weight < 1.0:
                    weight *= 100
                nse_sym = clean_symbol(sym_raw)
                if nse_sym and weight > 0:
                    results.append({'symbol': nse_sym, 'name': name,
                                    'weight': round(weight, 2),
                                    'scheme': fund_name, 'amc': amc})
            if results:
                return results

        # Fallback: fund_holding_info holdings list
        info = fund.fund_holding_info
        if isinstance(info, dict):
            fund_data = info.get(ticker, {})
            if isinstance(fund_data, dict):
                for h in fund_data.get('holdings', []):
                    sym_raw = str(h.get('symbol', '') or '')
                    name    = str(h.get('holdingName', '') or '')
                    weight  = float(h.get('holdingPercent', 0) or 0)
                    if weight < 1.0:
                        weight *= 100
                    nse_sym = clean_symbol(sym_raw)
                    if nse_sym and weight > 0:
                        results.append({'symbol': nse_sym, 'name': name,
                                        'weight': round(weight, 2),
                                        'scheme': fund_name, 'amc': amc})

        return results

    except Exception as e:
        log.warning(f"  {ticker}: {e}")
        return []

def save_to_db(conn, all_holdings: dict, month_date: datetime.date):
    """
    all_holdings: {nse_symbol: [{scheme, amc, weight, name}]}
    """
    cur = conn.cursor()
    saved_stocks = 0; saved_schemes = 0

    for sym, records in all_holdings.items():
        if not records:
            continue

        fund_count = len(records)
        amc_count  = len(set(r['amc'] for r in records))
        avg_weight = sum(r['weight'] for r in records) / fund_count
        signal     = ("HEAVY_BUYING" if fund_count >= 10 else
                      "MODERATE"     if fund_count >= 5  else "LIGHT")

        cur.execute("""
            INSERT INTO mf_stock_summary
                (nse_symbol, month, fund_count, amc_count, signal, accumulation_score)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (nse_symbol, month) DO UPDATE SET
                fund_count        = EXCLUDED.fund_count,
                amc_count         = EXCLUDED.amc_count,
                signal            = EXCLUDED.signal,
                accumulation_score= EXCLUDED.accumulation_score
        """, (sym, month_date, fund_count, amc_count, signal, round(avg_weight, 2)))
        saved_stocks += 1

        # Delete old scheme rows for this stock+month then reinsert
        cur.execute("DELETE FROM mf_scheme_holdings WHERE nse_symbol=%s AND month=%s",
                    (sym, month_date))
        seen = set()
        for r in records:
            key = r['scheme'][:200]
            if key in seen:
                continue
            seen.add(key)
            cur.execute("""
                INSERT INTO mf_scheme_holdings
                    (nse_symbol, month, amc_name, scheme_name, portfolio_weight_pct)
                VALUES (%s,%s,%s,%s,%s)
            """, (sym, month_date, r['amc'][:100], key, r['weight']))
            saved_schemes += 1

    conn.commit()
    cur.close()
    return saved_stocks, saved_schemes

def discover_fund_tickers(query_list: list, max_funds: int) -> list:
    """Auto-discover Yahoo tickers for Indian MF schemes."""
    try:
        from yahooquery import search
        discovered = []
        for query in query_list[:max_funds]:
            try:
                results = search(query)
                for q in results.get('quotes', []):
                    if q.get('quoteType') == 'MUTUALFUND' and q.get('symbol'):
                        discovered.append((q['symbol'], q.get('longname', query)))
                        break
                time.sleep(0.5)
            except:
                pass
        return discovered
    except:
        return []

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--funds",  type=int, default=30, help="Number of funds to process")
    p.add_argument("--ticker", help="Process single Yahoo ticker")
    p.add_argument("--discover", action="store_true", help="Auto-discover fund tickers first")
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    try:
        from yahooquery import Ticker
    except ImportError:
        log.error("Install yahooquery: pip install yahooquery")
        sys.exit(1)

    conn = get_db()
    log.info("Connected to DB")
    ensure_tables(conn)

    month_date = datetime.date.today().replace(day=1)
    log.info(f"Fetching MF holdings for {month_date.strftime('%b %Y')}")
    log.info("=" * 60)

    # Build fund list
    if args.ticker:
        funds = [(args.ticker, args.ticker)]
    else:
        funds = TOP_FUNDS[:args.funds]

    # Aggregate holdings across all funds
    all_holdings: dict = {}  # {nse_symbol: [records]}

    ok = 0
    for ticker, name in funds:
        log.info(f"  Fetching {name} ({ticker})…")
        records = fetch_fund_holdings(ticker, name)
        
        if records:
            for r in records:
                sym = r['symbol']
                if sym not in all_holdings:
                    all_holdings[sym] = []
                all_holdings[sym].append(r)
            log.info(f"  ✓ {len(records)} holdings")
            ok += 1
        else:
            log.info(f"  ✗ No data")
        
        time.sleep(1.0)  # Be polite

    log.info(f"\nFetched {ok}/{len(funds)} funds, {len(all_holdings)} unique stocks")
    
    if all_holdings:
        stocks, schemes = save_to_db(conn, all_holdings, month_date)
        log.info("=" * 60)
        log.info(f"Done. {stocks} stocks, {schemes} scheme holdings saved")

        # Show top holdings
        top = sorted(all_holdings.items(), key=lambda x: len(x[1]), reverse=True)[:10]
        log.info("\nTop stocks by fund count:")
        for sym, recs in top:
            log.info(f"  {sym}: {len(recs)} funds, avg weight {sum(r['weight'] for r in recs)/len(recs):.1f}%")
    else:
        log.warning("No holdings data found — check if yahooquery can reach Yahoo Finance")

    conn.close()

if __name__ == "__main__":
    main()
