#!/usr/bin/env bash
# AACapital — VM cron setup (LEAN pipeline, twice daily) + disable the old zombie-feeder.
#
# Run ONCE on the VM (ssh root@167.233.82.217):
#   cd /root/aac && bash setup_vm_cron.sh
#
# IMPORTANT — this REPLACES the earlier broken attempt AND removes the old
# full-pipeline / bloat cron lines so the 43-step zombie-feeder never runs again.
# It keeps your other existing jobs (listing-day launcher, feed verify, job_runner).
#
# TIMEZONE: `date -u` on this VM shows UTC. Cron uses system time, so the
# schedule below is written in UTC and mapped to the IST times you want:
#   03:00 UTC = 08:30 IST  (pre-market)
#   11:30 UTC = 17:00 IST  (post-close)
# If you later move the VM clock to IST, switch to `30 8` and `0 17`.

set -euo pipefail
AAC="/root/aac"
PY="venv/bin/python"
LOG="/root/aac/logs"
mkdir -p "$LOG"
RUN="cd $AAC && set -a && . ./.env && set +a"

TMP="$(mktemp)"
# Start from the current crontab, then strip:
#  - any previous AACAPITAL block we added
#  - the OLD full pipeline (run_ipo_pipeline.py — the 43-step zombie-feeder)
#  - the bloat scrapers if they were scheduled standalone
crontab -l 2>/dev/null \
  | grep -v "# AACAPITAL" \
  | grep -v "run_ipo_pipeline.py" \
  | grep -v "run_ipo_pipeline_lean.py" \
  | grep -v "fetch_institutional_deals" \
  | grep -v "fetch_insider_trades" \
  | grep -v "compute_convergence" \
  | grep -v "snapshot_convergence" \
  > "$TMP" || true

# Add the two LEAN runs. Token refresh FIRST each time, then the lean pipeline.
cat >> "$TMP" <<CRON
# AACAPITAL LEAN pipeline twice-daily (token refresh first). UTC times. Mon-Fri.
# 03:00 UTC = 08:30 IST (pre-market)
0 3 * * 1-5 $RUN && $PY _scripts/refresh_kite_token.py >> $LOG/token.log 2>&1 ; $RUN && $PY _scripts/run_ipo_pipeline_lean.py >> $LOG/pipeline_lean.log 2>&1
# 11:30 UTC = 17:00 IST (post-close)
30 11 * * 1-5 $RUN && $PY _scripts/refresh_kite_token.py >> $LOG/token.log 2>&1 ; $RUN && $PY _scripts/run_ipo_pipeline_lean.py >> $LOG/pipeline_lean.log 2>&1
CRON

crontab "$TMP"
rm -f "$TMP"

echo "Installed. AACAPITAL lean entries:"
crontab -l | grep -A1 "AACAPITAL"
echo ""
echo "Full crontab (verify the OLD run_ipo_pipeline.py line is GONE):"
crontab -l
