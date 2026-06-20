"""
_scripts/ipo/compute_brlm_scores.py
=====================================
Computes BRLM track record scores from historical ipo_intelligence data.
Run AFTER import_chittorgarh.py has loaded historical data.

Scores each BRLM on:
  - avg listing gain % (weight 30)
  - avg 1-month return (weight 25)
  - avg 6-month return (weight 20)
  - % IPOs with negative listing (weight 15)
  - valuation fairness — avg PE vs sector PE (weight 10)

Usage:
  python _scripts/ipo/compute_brlm_scores.py
"""

import os, sys, json, logging, math
import psycopg2, psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def n(v, default=0.0):
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)): return default
        return float(v)
    except: return default

def main():
    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    log.info("Loading all IPOs with BRLM data…")
    cur.execute("""
        SELECT brlm_names, return_listing_open, return_day1_close,
               return_day30, return_day90, ipo_pe, peer_median_pe,
               lqi_final, listing_gap_pct
        FROM ipo_intelligence
        WHERE brlm_names IS NOT NULL
          AND brlm_names != ''
          AND return_listing_open IS NOT NULL
        ORDER BY listing_date DESC NULLS LAST
    """)
    rows = cur.fetchall()
    log.info(f"  {len(rows)} IPOs with BRLM data")

    # Group by BRLM
    brlm_data: dict = {}
    for row in rows:
        brlm_raw = str(row['brlm_names'] or '').strip()
        # Split multiple BRLMs
        brlms = [b.strip() for b in brlm_raw.replace(';', ',').split(',') if b.strip()]
        for brlm in brlms[:3]:  # limit to first 3
            if brlm not in brlm_data:
                brlm_data[brlm] = {'listing_gains': [], 'day30_returns': [], 'day90_returns': [], 'pe_premiums': []}
            d = brlm_data[brlm]
            listing_gain = n(row['return_listing_open'])
            d['listing_gains'].append(listing_gain)
            if row['return_day30']: d['day30_returns'].append(n(row['return_day30']))
            if row['return_day90']: d['day90_returns'].append(n(row['return_day90']))
            if row['ipo_pe'] and row['peer_median_pe']:
                pe_prem = (n(row['ipo_pe']) / max(n(row['peer_median_pe']), 1) - 1) * 100
                d['pe_premiums'].append(pe_prem)

    log.info(f"Found {len(brlm_data)} unique BRLMs")

    # Compute scores and upsert
    brlm_scores = {}
    for brlm, d in brlm_data.items():
        if len(d['listing_gains']) < 3:
            continue  # need min 3 IPOs to score

        avg_listing = sum(d['listing_gains']) / len(d['listing_gains'])
        pct_negative = sum(1 for x in d['listing_gains'] if x < 0) / len(d['listing_gains']) * 100
        avg_30d = sum(d['day30_returns']) / len(d['day30_returns']) if d['day30_returns'] else avg_listing
        avg_90d = sum(d['day90_returns']) / len(d['day90_returns']) if d['day90_returns'] else avg_30d
        avg_pe_prem = sum(d['pe_premiums']) / len(d['pe_premiums']) if d['pe_premiums'] else 50

        # Score components (0-100 each, weighted)
        listing_score    = min(100, max(0, (avg_listing + 10) * 3))         # -10% = 0, +23% = 100
        day30_score      = min(100, max(0, (avg_30d + 20) * 2))             # -20% = 0, +30% = 100
        day90_score      = min(100, max(0, (avg_90d + 20) * 1.5))           # -20% = 0, +47% = 100
        negative_penalty = max(0, 100 - pct_negative * 2)                   # 50% neg = 0, 0% neg = 100
        valuation_score  = min(100, max(0, 100 - avg_pe_prem / 2))          # 200% prem = 0, 0% prem = 100

        final_score = (
            listing_score    * 0.30 +
            day30_score      * 0.25 +
            day90_score      * 0.20 +
            negative_penalty * 0.15 +
            valuation_score  * 0.10
        )

        brlm_scores[brlm] = {
            'score':        round(final_score, 1),
            'ipo_count':    len(d['listing_gains']),
            'avg_listing':  round(avg_listing, 2),
            'avg_day30':    round(avg_30d, 2),
            'pct_negative': round(pct_negative, 1),
        }
        log.info(f"  {brlm[:40]:40s} score={final_score:.0f} | {len(d['listing_gains'])} IPOs | avg listing {avg_listing:.1f}% | {pct_negative:.0f}% negative")

    # Save to DB as JSONB in a config table
    cur2 = conn.cursor()
    try:
        cur2.execute("""
            CREATE TABLE IF NOT EXISTS brlm_scores (
                brlm_name   TEXT PRIMARY KEY,
                score       NUMERIC,
                ipo_count   INTEGER,
                avg_listing NUMERIC,
                avg_day30   NUMERIC,
                pct_negative NUMERIC,
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        conn.commit()
        for brlm, s in brlm_scores.items():
            cur2.execute("""
                INSERT INTO brlm_scores (brlm_name, score, ipo_count, avg_listing, avg_day30, pct_negative, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,NOW())
                ON CONFLICT (brlm_name) DO UPDATE SET
                    score=EXCLUDED.score, ipo_count=EXCLUDED.ipo_count,
                    avg_listing=EXCLUDED.avg_listing, avg_day30=EXCLUDED.avg_day30,
                    pct_negative=EXCLUDED.pct_negative, updated_at=NOW()
            """, (brlm, s['score'], s['ipo_count'], s['avg_listing'], s['avg_day30'], s['pct_negative']))
        conn.commit()
        log.info(f"Saved {len(brlm_scores)} BRLM scores to Neon")
    except Exception as e:
        log.error(f"DB save failed: {e}")
        conn.rollback()
    finally:
        cur2.close()
        conn.close()

    log.info("=" * 60)
    log.info("BRLM scoring complete")
    log.info("Top 5 BRLMs:")
    for brlm, s in sorted(brlm_scores.items(), key=lambda x: -x[1]['score'])[:5]:
        log.info(f"  {s['score']:5.1f}  {brlm[:45]}")
    log.info("Bottom 5 BRLMs (avoid):")
    for brlm, s in sorted(brlm_scores.items(), key=lambda x: x[1]['score'])[:5]:
        log.info(f"  {s['score']:5.1f}  {brlm[:45]}")

if __name__ == "__main__":
    main()
