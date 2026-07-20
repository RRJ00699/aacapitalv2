#!/usr/bin/env python3
"""Production management commentary pipeline.
- Ingests .txt/.md transcript summaries from data/transcripts into Neon.
- Optionally archives/purges old Neon rows into local Postgres weekly.
- Anthropic integration can be added by setting ANTHROPIC_API_KEY; default uses a deterministic offline scorer.
"""
import os, re, json, argparse, logging
from pathlib import Path
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
LOCAL_DATABASE_URL = os.getenv('LOCAL_DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/aacapital?sslmode=disable')
NEON_DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('NEON_DATABASE_URL')

POS = {'strong','growth','margin','order book','guidance','capacity','demand','export','pipeline','profit','cash flow','debt reduction'}
NEG = {'weak','decline','delay','pressure','loss','debt','slowdown','risk','margin pressure','competition','inventory'}

def connect(url):
    kwargs = {}
    if 'localhost' not in url and '127.0.0.1' not in url and 'sslmode=disable' not in url:
        kwargs['sslmode'] = 'require'
    return psycopg2.connect(url, **kwargs)

def score_text(text):
    t = text.lower()
    p = sum(1 for w in POS if w in t)
    n = sum(1 for w in NEG if w in t)
    score = max(0, min(100, 50 + p * 6 - n * 7))
    tone = 'BULLISH' if score >= 68 else 'BEARISH' if score <= 42 else 'NEUTRAL'
    themes = [w for w in POS.union(NEG) if w in t][:8]
    return score, tone, themes

def ensure_tables(conn):
    with conn.cursor() as cur:
        cur.execute('''
        CREATE TABLE IF NOT EXISTS management_commentary_scores (
          symbol VARCHAR(20) PRIMARY KEY,
          sentiment_score NUMERIC,
          guidance_tone VARCHAR(32),
          key_themes JSONB DEFAULT '[]'::jsonb,
          summary TEXT,
          source_file TEXT,
          last_updated TIMESTAMPTZ DEFAULT NOW()
        )''')
        conn.commit()

def ingest(transcript_dir):
    NEON_DATABASE_URL = require_neon_url()
    files = list(Path(transcript_dir).glob('*.txt')) + list(Path(transcript_dir).glob('*.md'))
    rows=[]
    for fp in files:
        symbol = re.split(r'[_\-. ]', fp.stem.upper())[0]
        text = fp.read_text(errors='ignore')[:20000]
        score, tone, themes = score_text(text)
        rows.append((symbol, score, tone, json.dumps(themes), text[:1200], fp.name))
    with connect(NEON_DATABASE_URL) as conn:
        ensure_tables(conn)
        with conn.cursor() as cur:
            execute_values(cur, '''
              INSERT INTO management_commentary_scores(symbol, sentiment_score, guidance_tone, key_themes, summary, source_file, last_updated)
              VALUES %s
              ON CONFLICT(symbol) DO UPDATE SET
                sentiment_score=EXCLUDED.sentiment_score, guidance_tone=EXCLUDED.guidance_tone,
                key_themes=EXCLUDED.key_themes, summary=EXCLUDED.summary, source_file=EXCLUDED.source_file,
                last_updated=NOW()
            ''', rows) if rows else None
        conn.commit()
    logging.info('Ingested %s transcript files', len(rows))

def archive(days):
    NEON_DATABASE_URL = require_neon_url()
    with connect(NEON_DATABASE_URL) as neon, connect(LOCAL_DATABASE_URL) as local:
        with local.cursor() as lc, neon.cursor() as nc:
            lc.execute('''CREATE TABLE IF NOT EXISTS management_commentary_archive AS TABLE management_commentary_scores WITH NO DATA''')
            nc.execute("SELECT symbol, sentiment_score, guidance_tone, key_themes, summary, source_file, last_updated FROM management_commentary_scores WHERE last_updated < NOW() - (%s || ' days')::interval", (days,))
            rows = nc.fetchall()
            if rows:
                execute_values(lc, 'INSERT INTO management_commentary_archive(symbol, sentiment_score, guidance_tone, key_themes, summary, source_file, last_updated) VALUES %s', rows)
                nc.execute("DELETE FROM management_commentary_scores WHERE last_updated < NOW() - (%s || ' days')::interval", (days,))
        local.commit(); neon.commit()
    logging.info('Archived %s old commentary rows', len(rows) if 'rows' in locals() else 0)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--transcript-dir', default='data/transcripts')
    ap.add_argument('--archive', action='store_true')
    ap.add_argument('--purge-days', type=int, default=21)
    args = ap.parse_args()
    archive(args.purge_days) if args.archive else ingest(args.transcript_dir)
