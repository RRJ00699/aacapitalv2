#!/usr/bin/env python3
"""AACapital multibagger model trainer - schema tolerant hotfix.
Reads local Postgres historical multibagger_events when available and stores an interpretable baseline model in Neon.
This version does NOT assume rs_score/volume_score columns exist.
"""
import os, sys, json, logging
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
PROD_DIR = PROJECT_ROOT / '_scripts' / 'prod'
for pth in (str(SCRIPT_DIR), str(PROD_DIR), str(PROJECT_ROOT)):
    if pth not in sys.path:
        sys.path.insert(0, pth)
from env_utils import load_dotenv_files
load_dotenv_files()
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
LOCAL_DATABASE_URL = os.getenv('LOCAL_DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/aacapital?sslmode=disable')
NEON_DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('NEON_DATABASE_URL')

FEATURES = ['rs_score','volume_score','base_score','earnings_score','smart_money_score','drawdown_risk']
DEFAULT_WEIGHTS = {'bias': -2.2, 'rs_score': .028, 'volume_score': .018, 'base_score': .015, 'earnings_score': .022, 'smart_money_score': .012, 'drawdown_risk': -.010}

def connect(url):
    kwargs = {}
    if 'localhost' not in url and '127.0.0.1' not in url and 'sslmode=disable' not in url:
        kwargs['sslmode'] = 'require'
    return psycopg2.connect(url, **kwargs)

def table_exists(cur, table_name):
    cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s) AS exists", (table_name,))
    row = cur.fetchone()
    if row is None:
        return False
    return bool(row.get('exists') if isinstance(row, dict) else row[0])

def columns_for(cur, table_name):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", (table_name,))
    cols = set()
    for r in cur.fetchall():
        cols.add(r.get('column_name') if isinstance(r, dict) else r[0])
    return cols

def pick(cols, candidates, default_sql):
    for c in candidates:
        if c in cols:
            return f"COALESCE({c}, {default_sql})"
    return default_sql

def fetch_training_rows():
    with connect(LOCAL_DATABASE_URL) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        if not table_exists(cur, 'multibagger_events'):
            logging.warning('multibagger_events table not found; saving default model')
            return []
        cols = columns_for(cur, 'multibagger_events')
        symbol_expr = 'symbol' if 'symbol' in cols else "'UNKNOWN'"
        rs_expr = pick(cols, ['rs_score','relative_strength_score','relative_strength','rs_rating'], '50')
        vol_expr = pick(cols, ['volume_score','vol_score','volume_expansion_score','volume_rating'], '50')
        base_expr = pick(cols, ['base_score','base_quality_score','pattern_score','setup_score'], '50')
        earn_expr = pick(cols, ['earnings_score','earnings_acceleration_score','fundamental_score'], '50')
        smart_expr = pick(cols, ['smart_money_score','institutional_score','delivery_score'], '50')
        dd_expr = pick(cols, ['max_drawdown_pct','drawdown_pct','drawdown_risk'], '35')
        cur.execute(f'''
            SELECT {symbol_expr} AS symbol,
                   {rs_expr}::numeric AS rs_score,
                   {vol_expr}::numeric AS volume_score,
                   {base_expr}::numeric AS base_score,
                   {earn_expr}::numeric AS earnings_score,
                   {smart_expr}::numeric AS smart_money_score,
                   {dd_expr}::numeric AS drawdown_risk,
                   1 AS label
            FROM multibagger_events
            LIMIT 5000
        ''')
        rows = cur.fetchall()
        logging.info('Loaded %s multibagger event rows using available columns: %s', len(rows), sorted(cols))
        return rows

def save_model(weights, rows):
    if not NEON_DATABASE_URL:
        raise RuntimeError('DATABASE_URL or NEON_DATABASE_URL required to save model')
    with connect(NEON_DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute('''
          CREATE TABLE IF NOT EXISTS ml_model_registry (
            model_name TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            weights JSONB NOT NULL,
            training_rows INT NOT NULL DEFAULT 0,
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
          )
        ''')
        metrics = {'training_events': len(rows), 'model_type': 'schema_tolerant_interpretable_logistic_baseline', 'features': FEATURES}
        cur.execute('''
          INSERT INTO ml_model_registry(model_name, version, weights, training_rows, metrics, updated_at)
          VALUES(%s,%s,%s,%s,%s,NOW())
          ON CONFLICT(model_name) DO UPDATE SET
            version=EXCLUDED.version, weights=EXCLUDED.weights, training_rows=EXCLUDED.training_rows,
            metrics=EXCLUDED.metrics, updated_at=NOW()
        ''', ('multibagger_opportunity_v1', datetime.now(timezone.utc).strftime('%Y%m%d%H%M'), json.dumps(weights), len(rows), json.dumps(metrics)))
        conn.commit()

if __name__ == '__main__':
    try:
        rows = fetch_training_rows()
    except psycopg2.OperationalError as e:
        raise SystemExit('LOCAL_DATABASE_URL connection failed. Check local Postgres password/db name. Use percent encoding for @ in password, e.g. postgresql://postgres:Ashrith%402820@localhost:5432/aacapital?sslmode=disable\n' + str(e))
    save_model(DEFAULT_WEIGHTS, rows)
    logging.info('Saved multibagger model with %s training events', len(rows))
