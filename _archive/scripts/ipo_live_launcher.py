#!/usr/bin/env python3
"""
ipo_live_launcher.py — automate the listing-day LIVE tick feed on the VM.

Runs the REAL analytics tick writer (ipo/kite_ticker_ipo.py, which owns the
ipo_tick_feed analytics schema: VWAP / OBIR / momentum / signal) with the lifecycle
it lacks on its own:
  • a fresh child process every ~4h  — fresh Twisted reactor + re-read token from
    platform_config, so no socket nears Kite's ~6h honor ceiling;
  • a clean stop at 15:35 IST (SIGINT, then hard kill as a fallback);
  • between/within cycles, refresh ipo_level_analysis (ipo/analyze_listing_day.py)
    every 5 min so the LIVE floor/ceiling stays current in /ipo through the session.

Both child scripts use --auto-today (mainboard IPOs >= Rs200cr inside their
listing->+30d anchor window), so the feed and the levels stay in sync, and a day
with no active IPO exits in ~1s (no hot respawn).

Replaces the dead ipo_tick_capture.py in the 09:14 cron:
  14 9 * * 1-5 cd $AAC && set -a && . ./.env && set +a && venv/bin/python _scripts/ipo_live_launcher.py >> logs/ticks.log 2>&1
Needs DATABASE_URL + a valid Kite token (refresh_kite_token.py runs 08:00).
"""
import os, sys, time, signal, subprocess, datetime
HERE = os.path.dirname(os.path.abspath(__file__))          # _scripts/
REPO = os.path.dirname(HERE)                               # repo root
TICKER   = os.path.join(HERE, "ipo", "kite_ticker_ipo.py")
ANALYZER = os.path.join(HERE, "ipo", "analyze_listing_day.py")
try:
    from zoneinfo import ZoneInfo; IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = None
RECYCLE_SECONDS = 4 * 3600     # rebuild the socket every 4h (< Kite's ~6h ceiling)
LEVELS_EVERY    = 300          # refresh ipo_level_analysis every 5 min
PY = sys.executable

def _now(): return datetime.datetime.now(IST) if IST else datetime.datetime.now()

def refresh_levels():
    """Recompute live floor/ceiling from the ticks captured so far -> ipo_level_analysis."""
    try:
        subprocess.run([PY, ANALYZER, "--auto-today"], cwd=REPO, timeout=240,
                       stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        print(f"{_now():%H:%M} levels refreshed")
    except Exception as e:
        print(f"{_now():%H:%M} levels refresh skipped ({e})")

def run_cycle(until):
    """Spawn the ticker; refresh levels periodically; stop the ticker at `until`.
    Returns the ticker's runtime in seconds (to detect a no-IPO fast exit)."""
    t0 = _now()
    p = subprocess.Popen([PY, TICKER, "--auto-today", "--write-db", "--interval", "5"], cwd=REPO)
    last_levels = 0.0
    while True:
        if p.poll() is not None:                 # ticker exited on its own
            return (_now() - t0).total_seconds()
        if _now() >= until:
            break
        if time.time() - last_levels >= LEVELS_EVERY:
            refresh_levels(); last_levels = time.time()
        time.sleep(10)
    # graceful stop: SIGINT is KiteTicker's clean-shutdown path (Ctrl-C), then hard kill
    try:
        p.send_signal(signal.SIGINT)
        try: p.wait(timeout=15)
        except subprocess.TimeoutExpired: p.kill()
    except Exception:
        try: p.kill()
        except Exception: pass
    refresh_levels()                             # final levels pass after the cycle
    return (_now() - t0).total_seconds()

def main():
    end = _now().replace(hour=15, minute=35, second=0, microsecond=0)
    if _now() >= end:
        print("after 15:35 IST — nothing to launch."); return
    first = True
    while _now() < end:
        cycle_end = min(end, _now() + datetime.timedelta(seconds=RECYCLE_SECONDS))
        print(f"{_now():%H:%M} cycle -> ticker until {cycle_end:%H:%M:%S}")
        dur = run_cycle(cycle_end)
        if first and dur < 10:
            print("ticker exited immediately — no active IPO today. done."); return
        first = False
        if _now() < end: time.sleep(3)
    print("15:35 IST — live feed window closed.")

if __name__ == "__main__": main()
