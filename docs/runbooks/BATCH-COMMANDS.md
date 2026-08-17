Status: SUPERSEDED by docs/runbooks/DAILY_RUN.md and docs/runbooks/PRODUCTION_JOBS.md
Authority: docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md

# AACapital — Batch Command Reference (SUPERSEDED — equity era, do not run)

> **Do not run anything below.** This was the equity-era batch reference. Almost
> nothing in it still exists. Verified against the tree on 2026-08-17:
>
> * **9 of the 10 referenced scripts are gone** from the paths shown —
>   `fetch_fii_dii.py`, `fetch_live_ipos.py`, `run-intelligence-scoring.ts`,
>   `fetch_shp.py`, `loaders/load-amfi.ts`, `backfill/backfill-earnings.ts`,
>   `seed-intelligence-sample.ts`, `run-all.bat`, and both `sql/*.sql` files.
>   Only `_scripts/engines/market_regime.py` still exists.
> * **All 5 GitHub Actions workflows it names are gone** —
>   `daily-intelligence.yml`, `daily-data-engine.yml`, `ipo-data-pipeline.yml`,
>   `monthly-amfi.yml`, `quarterly-backfill.yml`. The live set is
>   `.github/workflows/{ci,daily-pipeline,deploy,pipeline,preopen-capture,probe-nse,sbi-notes}.yml`.
> * Its AMFI / shareholding / commentary-scoring lanes are the equity-era
>   surface the product contract retired; `README.md` is contract-tested to
>   carry no such claim.
>
> **Read instead:** `docs/runbooks/DAILY_RUN.md` for the owner's supported daily
> command (`python pipeline\cron.py`), and `docs/runbooks/PRODUCTION_JOBS.md`
> for the verified production caller map.
>
> Retained, not deleted: it is the record of what the equity era actually ran.

# Run all commands from C:\aacapital-v2

## ── DAILY (run after 6 PM IST, Mon–Fri) ──────────────────────────────────────

# 1. FII/DII institutional flows (NSE)
python _scripts\fetch_fii_dii.py

# 2. Market regime (Nifty EMA200 + breadth)
python _scripts\engines\market_regime.py

# 3. Live IPO data (NSE live + Chittorgarh GMP)
python _scripts\fetch_live_ipos.py

# 4. Intelligence scoring
npx tsx _scripts\run-intelligence-scoring.ts --module=earnings
npx tsx _scripts\run-intelligence-scoring.ts --module=commentary

## ── WEEKLY (run Monday morning) ──────────────────────────────────────────────

# 5. Shareholding patterns — promoter %, FII %, DII % (50 stocks at a time)
python _scripts\fetch_shp.py --limit 50

# 6. Reload weekly candle data
python C:\Users\Admin\Downloads\download_candles_retry.py

## ── MONTHLY (run on 10th of month) ───────────────────────────────────────────

# 7. AMFI mutual fund flows
npx tsx _scripts\loaders\load-amfi.ts
npx tsx _scripts\run-intelligence-scoring.ts --module=amfi

# 8. Monthly candles
python C:\Users\Admin\Downloads\download_monthly.py

## ── QUARTERLY (run after results season: Jan, Apr, Jul, Oct) ─────────────────

# 9. Earnings backfill from Screener.in CSVs
#    First: download CSVs manually from screener.in/company/SYMBOL/consolidated/
#    Then:
npx tsx _scripts\backfill\backfill-earnings.ts --source=csv
npx tsx _scripts\run-intelligence-scoring.ts --module=earnings

# 10. Full shareholding refresh (all stocks)
python _scripts\fetch_shp.py

## ── ONE-TIME SETUP (already done, for reference) ─────────────────────────────

# Download 10yr daily + weekly candles for 520 stocks
python C:\Users\Admin\Downloads\download_nifty500.py

# Seed intelligence sample data
npx tsx _scripts\seed-intelligence-sample.ts

# Run DB migrations (Neon SQL Editor)
# → sql/schema.sql
# → sql/ipo_schema.sql

## ── DRY RUN (test without writing to DB) ─────────────────────────────────────

python _scripts\fetch_fii_dii.py --dry-run
python _scripts\engines\market_regime.py --dry-run
python _scripts\fetch_live_ipos.py --dry-run
python _scripts\fetch_shp.py --symbol WABAG   # single stock test

## ── OR RUN EVERYTHING AT ONCE ────────────────────────────────────────────────

_scripts\run-all.bat daily     # FII + Regime + IPO + Scoring
_scripts\run-all.bat weekly    # + Shareholding + Candles
_scripts\run-all.bat monthly   # + AMFI + Monthly candles
_scripts\run-all.bat all       # Everything

## ── GITHUB ACTIONS (automatic, no manual run needed) ─────────────────────────

# .github/workflows/daily-intelligence.yml  → 6:30 AM IST Mon–Fri
# .github/workflows/daily-data-engine.yml   → 6:30 PM IST Mon–Fri (FII + Regime)
# .github/workflows/ipo-data-pipeline.yml   → 8 AM + 6 PM IST Mon–Fri
# .github/workflows/monthly-amfi.yml        → 10th of month
# .github/workflows/quarterly-backfill.yml  → Jan/Apr/Jul/Oct 15th

## ── PYTHON DEPENDENCIES (install once) ───────────────────────────────────────

pip install curl_cffi beautifulsoup4 psycopg2-binary python-dotenv pandas numpy yfinance requests
