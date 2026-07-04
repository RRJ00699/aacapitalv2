# AACapital — CX22 bring-up (move cron off GitHub Actions, go live end-to-end)

**Root cause of the failing crons:** all 17 jobs run on **GitHub Actions with no Python deps installed** (`No module named 'dotenv'/'kiteconnect'`). Fix = move them to CX22 (this bundle) + turn Actions off.

---
## STEP 1 — on your PC: kill all GitHub Actions crons (one commit)
GitHub only runs workflows inside `.github/workflows/`. Rename the folder to disable all 17 at once. (Vercel deploys are unaffected — Vercel uses its own git integration, not Actions.)
```powershell
cd C:\aacapital-v2
git mv .github/workflows .github/workflows_disabled
git add _scripts/ipo/refresh_gmp.py 2>$null   # if you created it locally; harmless if not
git commit -m "Move cron to CX22: disable GitHub Actions crons"
git push
```

## STEP 2 — on the VM: clone + bootstrap
```bash
ssh root@<your-cx22-ip>
apt update && apt install -y git
git clone https://github.com/RRJ00699/aacapitalv2 /root/aac
cd /root/aac
# copy the 3 files from this bundle into /root/aac first (scp or nano-paste):
#   bootstrap.sh, .env.template, aac_crontab.txt
bash bootstrap.sh
```
`bootstrap.sh` installs system deps, sets tz=IST, makes a venv, installs requirements.txt **plus rapidfuzz/playwright/sqlalchemy**, installs headless Chromium, creates the missing `refresh_gmp.py`, and makes `logs/`.

## STEP 3 — secrets
```bash
cp .env.template .env
nano .env            # fill DATABASE_URL, KITE_API_SECRET, KITE_USER_ID(MNX015), KITE_PASSWORD, KITE_TOTP_SECRET
chmod 600 .env
```

## STEP 4 — smoke test (run in this order; token must exist before pipeline)
```bash
cd /root/aac && set -a && . ./.env && set +a
venv/bin/python _scripts/refresh_kite_token.py     # expect: "Token verified ... ✅"
venv/bin/python _scripts/run_ipo_pipeline.py       # preflight OK -> steps run -> check_data_contract
venv/bin/python _scripts/ipo_tick_capture.py       # only does work on a listing day; else exits cleanly
```
If token or pipeline print errors, paste me the log — that's the real-world debug pass.

## STEP 5 — install cron
```bash
crontab /root/aac/aac_crontab.txt
crontab -l          # confirm 4 lines
```
Schedule (IST): token 08:00 daily · ticks 09:14 Mon–Fri · pipeline 18:30 daily · purge Sun 19:00.

## STEP 6 — verify it's alive tomorrow
```bash
tail -n 40 /root/aac/logs/pipe.log
tail -n 40 /root/aac/logs/token.log
```
And the `/ipo` page should show fresh candles/levels after the first 18:30 run.

---
### Notes
- **Stateless box:** code=GitHub, data=Neon. If the VM ever dies, repeat Steps 2–5 (~15 min), zero data loss.
- **refresh_gmp.py:** bootstrap creates it on the VM. To make it permanent in git, commit the same 4-line file from your PC later.
- **Weekends:** token refreshes daily so the 18:30 pipeline's preflight stays green even Sat/Sun (just no new candles).
