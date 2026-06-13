@echo off
REM ============================================================================
REM AACapital — Master Data Pipeline Runner
REM Run from C:\aacapital-v2
REM Usage: scripts\run-all.bat [daily|weekly|monthly|ipo|all]
REM ============================================================================

cd /d C:\aacapital-v2
set MODE=%1
if "%MODE%"=="" set MODE=daily

echo.
echo ========================================
echo  AACapital Data Pipeline — %MODE%
echo  %DATE% %TIME%
echo ========================================
echo.

REM ── DAILY (run every weekday after 6 PM) ─────────────────────────────────────
if "%MODE%"=="daily" goto :daily
if "%MODE%"=="all"   goto :daily

:daily
echo [1/5] FII/DII Institutional Flows...
python _scripts\fetch_fii_dii.py
echo.

echo [2/5] Market Regime Engine (Nifty EMA200 + Breadth)...
python _scripts\engines\market_regime.py
echo.

echo [3/5] Live IPO Data (NSE + Chittorgarh GMP)...
python _scripts\fetch_live_ipos.py
echo.

echo [4/5] Intelligence Scoring (Earnings + Commentary + AMFI)...
call npx tsx _scripts\run-intelligence-scoring.ts --module=earnings
call npx tsx _scripts\run-intelligence-scoring.ts --module=commentary
echo.

if "%MODE%"=="daily" goto :done

REM ── WEEKLY (run every Monday morning) ────────────────────────────────────────
:weekly
echo [5/8] Shareholding Patterns (NSE)...
python _scripts\fetch_shp.py --limit 50
echo.

echo [6/8] Download Weekly Candles (new stocks only)...
python _scripts\download_candles_retry.py
echo.

if "%MODE%"=="weekly" goto :done

REM ── MONTHLY (run on 10th of month) ───────────────────────────────────────────
:monthly
echo [7/9] AMFI Mutual Fund Flows...
call npx tsx _scripts\loaders\load-amfi.ts
call npx tsx _scripts\run-intelligence-scoring.ts --module=amfi
echo.

echo [8/9] Download Monthly Candles...
python _scripts\download_monthly.py
echo.

if "%MODE%"=="monthly" goto :done

REM ── IPO ONLY ─────────────────────────────────────────────────────────────────
:ipo
echo [IPO] Fetching live IPO data...
python _scripts\fetch_live_ipos.py --source both
goto :done

REM ── ALL ───────────────────────────────────────────────────────────────────────
:all
echo [9/9] Full Shareholding Pattern Refresh (all stocks)...
python _scripts\fetch_shp.py
echo.

:done
echo.
echo ========================================
echo  Done: %DATE% %TIME%
echo ========================================
