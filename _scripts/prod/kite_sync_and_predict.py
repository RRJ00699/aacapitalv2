#!/usr/bin/env python3
"""AACapital production sync runner.
Stores Today screen market snapshot, IPO predictions and listing-day signals. Safe for GitHub Actions.
"""
import os, sys, argparse, logging, json, datetime as dt
from decimal import Decimal
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
for pth in (str(SCRIPT_DIR), str(PROJECT_ROOT)):
    if pth not in sys.path:
        sys.path.insert(0, pth)
from env_utils import load_dotenv_files, require_neon_url
load_dotenv_files()
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
NEON_DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('NEON_DATABASE_URL')
LOCAL_DATABASE_URL = os.getenv('LOCAL_DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/aacapital?sslmode=disable')
KITE_API_KEY = os.getenv('KITE_API_KEY')
KITE_ACCESS_TOKEN = os.getenv('KITE_ACCESS_TOKEN')

def json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value

def connect(url):
    kwargs = {}
    if 'localhost' not in url and '127.0.0.1' not in url and 'sslmode=disable' not in url:
        kwargs['sslmode'] = 'require'
    return psycopg2.connect(url, **kwargs)

def ensure(conn):
    """Create/upgrade the small Neon tables used by the UI.
    Important: CREATE TABLE IF NOT EXISTS does not add columns to an existing table,
    so we always run safe ADD COLUMN migrations after creation.
    """
    with conn.cursor() as cur:
        cur.execute('''CREATE TABLE IF NOT EXISTS market_snapshot(
          id INT PRIMARY KEY DEFAULT 1
        )''')
        for ddl in [
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS market_regime TEXT",
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS nifty_price NUMERIC",
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS sensex_price NUMERIC",
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS banknifty_price NUMERIC",
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS vix NUMERIC",
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS pcr NUMERIC",
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS fii_flow NUMERIC",
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS dii_flow NUMERIC",
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS deploy_min INT",
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS deploy_max INT",
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS payload JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS last_updated TIMESTAMPTZ DEFAULT NOW()",
        ]:
            cur.execute(ddl)
        cur.execute('''CREATE TABLE IF NOT EXISTS ipo_listing_signals(
          symbol TEXT PRIMARY KEY
        )''')
        for ddl in [
            "ALTER TABLE ipo_listing_signals ADD COLUMN IF NOT EXISTS listing_date DATE",
            "ALTER TABLE ipo_listing_signals ADD COLUMN IF NOT EXISTS oi_buy_pct NUMERIC",
            "ALTER TABLE ipo_listing_signals ADD COLUMN IF NOT EXISTS oi_sell_pct NUMERIC",
            "ALTER TABLE ipo_listing_signals ADD COLUMN IF NOT EXISTS vwap_open NUMERIC",
            "ALTER TABLE ipo_listing_signals ADD COLUMN IF NOT EXISTS vwap_30m NUMERIC",
            "ALTER TABLE ipo_listing_signals ADD COLUMN IF NOT EXISTS vwap_60m NUMERIC",
            "ALTER TABLE ipo_listing_signals ADD COLUMN IF NOT EXISTS volume_ratio NUMERIC",
            "ALTER TABLE ipo_listing_signals ADD COLUMN IF NOT EXISTS listing_gain_pct NUMERIC",
            "ALTER TABLE ipo_listing_signals ADD COLUMN IF NOT EXISTS signal TEXT",
            "ALTER TABLE ipo_listing_signals ADD COLUMN IF NOT EXISTS probability_gain NUMERIC",
            "ALTER TABLE ipo_listing_signals ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        ]:
            cur.execute(ddl)
        conn.commit()

def lqi_score(gmp, qib, nii, ofs=0, p10=50):
    score = 0
    score += 25 if qib >= 100 else 20 if qib >= 50 else 15 if qib >= 20 else 10 if qib >= 10 else 5 if qib >= 5 else 0
    score += 15 if nii >= 200 else 12 if nii >= 100 else 8 if nii >= 50 else 5 if nii >= 20 else 0
    score += 20 if gmp >= 50 else 16 if gmp >= 30 else 12 if gmp >= 15 else 7 if gmp >= 5 else 3 if gmp > 0 else -5
    score += 15 if ofs == 0 else 12 if ofs <= 20 else 8 if ofs <= 40 else 4 if ofs <= 60 else 1
    score += 15 if p10 >= 70 else 10 if p10 >= 55 else 6 if p10 >= 40 else 3 if p10 >= 25 else 0
    return max(0, min(100, score))

def ipo_predict():
    with connect(NEON_DATABASE_URL) as conn:
        ensure(conn)
        with conn.cursor() as cur:
            cur.execute('''SELECT symbol, company_name, COALESCE(gmp_percentage,0), COALESCE(qib_subscription_x,0), COALESCE(nii_subscription_x,0), COALESCE(ofs_pct,0)
                           FROM ipo_intelligence''')
            rows = cur.fetchall()
            for sym, name, gmp, qib, nii, ofs in rows:
                gmp=float(gmp or 0); qib=float(qib or 0); nii=float(nii or 0); ofs=float(ofs or 0)
                p10 = max(15, min(95, gmp * 1.35 + min(qib, 100) * .25 + min(nii, 200) * .08))
                if gmp < 0: p10, action = 15, 'AVOID'
                elif gmp < 5: p10, action = min(p10, 35), 'CAUTION'
                elif gmp < 10 and qib < 75: p10, action = min(p10, 50), 'WATCHLIST'
                else: action = 'MOMENTUM CHASE' if p10 >= 70 else 'VALUE DIP BUY' if p10 >= 50 else 'WATCHLIST'
                lqi = lqi_score(gmp,qib,nii,ofs,p10)
                cur.execute('''UPDATE ipo_intelligence SET lqi_final=%s, prob_10pct_profit=%s, expected_return=%s, suggested_action=%s, updated_at=NOW() WHERE symbol=%s''',
                            (lqi, round(p10,1), round(gmp*.85,1), action, sym))
        conn.commit(); logging.info('IPO predictions updated: %s', len(rows))

def market_snapshot():
    with connect(NEON_DATABASE_URL) as conn:
        ensure(conn)
        with conn.cursor() as cur:
            cur.execute('''SELECT active_regime, nifty_close, nifty_ema_200, breadth_percentage, india_vix, recommended_allocation_min, recommended_allocation_max
                           FROM market_regimes ORDER BY evaluation_date DESC LIMIT 1''')
            r = cur.fetchone() or ('NORMAL', None, None, None, None, 50, 70)
            cur.execute('''INSERT INTO market_snapshot(id, market_regime, nifty_price, vix, deploy_min, deploy_max, payload, last_updated)
                           VALUES(1,%s,%s,%s,%s,%s,%s,NOW())
                           ON CONFLICT(id) DO UPDATE SET market_regime=EXCLUDED.market_regime, nifty_price=EXCLUDED.nifty_price,
                           vix=EXCLUDED.vix, deploy_min=EXCLUDED.deploy_min, deploy_max=EXCLUDED.deploy_max, payload=EXCLUDED.payload, last_updated=NOW()''',
                        (r[0], r[1], r[4], r[5], r[6], json.dumps({'ema200': r[2], 'breadth': r[3]}, default=json_safe)))
        conn.commit(); logging.info('Market snapshot refreshed')

if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--mode', choices=['market','ipo','all'], default='all'); args=ap.parse_args()
    NEON_DATABASE_URL = require_neon_url()
    if args.mode in ('market','all'): market_snapshot()
    if args.mode in ('ipo','all'): ipo_predict()
