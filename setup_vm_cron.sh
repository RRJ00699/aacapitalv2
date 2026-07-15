#!/usr/bin/env bash
# AACapital — VM cron setup (twice-daily pipeline + Kite token refresh)
#
# Run ONCE on the VM (ssh root@167.233.82.217):
#   cd /root/aac && bash setup_vm_cron.sh
#
# What it installs (IST → UTC; the VM is assumed UTC — verify with `date`):
#   - 08:30 IST (03:00 UTC) : Kite token refresh → full pipeline   [pre-market]
#   - 17:00 IST (11:30 UTC) : Kite token refresh → full pipeline   [post-close, 5 PM]
#
# The token refresh runs FIRST each time so every downstream step (candles,
# ticks, listing-day fields) has a fresh Kite session. If refresh fails the
# pipeline still runs (non-fatal) but logs it.
#
# Trading days: NSE runs Mon–Fri. We schedule Mon–Fri only.
# Frozen tables (ipo_master/predictions/feature_store/similarity) are never
# fed — the pipeline does not touch them (verified).

set -euo pipefail
AAC="/root/aac"
PY="venv/bin/python"
LOG="/root/aac/logs"
mkdir -p "$LOG"

# The command idiom mirrors job_runner: load .env, run with venv python, cwd=repo.
RUNNER='cd '"$AAC"' && set -a && . ./.env && set +a'

# token refresh then pipeline, both logged with a datestamped file
PRE="$RUNNER && $PY _scripts/refresh_kite_token.py >> $LOG/token.log 2>&1 ; $PY _scripts/run_ipo_pipeline.py >> $LOG/pipeline.log 2>&1"
POST="$RUNNER && $PY _scripts/refresh_kite_token.py >> $LOG/token.log 2>&1 ; $PY _scripts/run_ipo_pipeline.py >> $LOG/pipeline.log 2>&1"

# Build the new crontab: keep any NON-aacapital lines the user already has,
# drop our previous aacapital entries (idempotent re-run), add the two below.
TMP="$(mktemp)"
crontab -l 2>/dev/null | grep -v "run_ipo_pipeline.py" | grep -v "# AACAPITAL" > "$TMP" || true

cat >> "$TMP" <<CRON
# AACAPITAL twice-daily pipeline (token refresh first). Times in UTC. Mon-Fri.
# 08:30 IST pre-market
0 3 * * 1-5 $PRE
# 17:00 IST post-close
30 11 * * 1-5 $POST
CRON

crontab "$TMP"
rm -f "$TMP"

echo "Installed. Current crontab:"
crontab -l | grep -A1 "AACAPITAL"
echo ""
echo "NOTE: confirm the VM clock is UTC with 'date -u'. If the VM is already on"
echo "IST, use 30 8 and 0 17 instead of 0 3 and 30 11."
