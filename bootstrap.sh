#!/usr/bin/env bash
# AACapital CX22 bring-up. Run ONCE, as root, from inside the cloned repo.
#   apt update && apt install -y git
#   git clone https://github.com/RRJ00699/aacapitalv2 /root/aac
#   cd /root/aac && bash bootstrap.sh
set -euo pipefail
cd /root/aac

echo "== system deps =="
apt-get update -y
apt-get install -y python3-venv python3-pip python3-dev build-essential libpq-dev git tzdata

echo "== timezone -> IST (so cron times are IST) =="
timedatectl set-timezone Asia/Kolkata || true

echo "== python venv + deps =="
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
# used by parser + scrapers but not in requirements.txt:
./venv/bin/pip install rapidfuzz playwright sqlalchemy
./venv/bin/python -m playwright install --with-deps chromium

echo "== ensure GMP pipeline wrapper exists (missing from repo) =="
mkdir -p _scripts/ipo
if [ ! -f _scripts/ipo/refresh_gmp.py ]; then
cat > _scripts/ipo/refresh_gmp.py <<'PY'
import os, sys, runpy
here = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["scrape_investorgain_gmp.py", "--write-db"]
runpy.run_path(os.path.join(here, "..", "scrape_investorgain_gmp.py"), run_name="__main__")
PY
echo "  created _scripts/ipo/refresh_gmp.py"
fi

mkdir -p logs
echo
echo "DONE. Next:"
echo "  1) nano /root/aac/.env   (fill from .env.template) then: chmod 600 /root/aac/.env"
echo "  2) smoke test token:  cd /root/aac && set -a && . ./.env && set +a && venv/bin/python _scripts/refresh_kite_token.py"
echo "  3) smoke test pipe:   venv/bin/python _scripts/run_ipo_pipeline.py"
echo "  4) install cron:      crontab /root/aac/aac_crontab.txt && crontab -l"
