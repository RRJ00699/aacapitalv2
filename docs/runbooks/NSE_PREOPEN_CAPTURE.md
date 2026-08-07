Status: CURRENT

# NSE IPO Special Pre-Open Capture — 2026-07-17

## Endpoint (verify before enabling — 60-second ritual below)
- Page: `https://www.nseindia.com/market-data/pre-open-market-cm-and-emerge-market` (IPO/Re-listed category)
- API : `https://www.nseindia.com/api/market-data-pre-open?key=IPO`
- Evidence: same `/api/*` family as the repo's proven `fetch_nse_ipos.py` FEEDS; targeted historically by `wayback_preopen_harvest.py`. **Sandbox cannot reach NSE, so the ritual is mandatory once:** open the page on a listing morning → DevTools → Network → filter `pre-open` → confirm the API URL + that rows carry `metadata.symbol/lastPrice/totalBuyQuantity/totalSellQuantity` and `detail.preOpenMarket.preopen[]` levels. The script ALSO shape-validates on first contact and aborts to the failure sink on mismatch.
- Validation vs visible page: run `--once` during a window, compare printed IEP/buy/sell for one symbol against the page numbers.

## Fields captured
IEP (`lastPrice`/`IEP`), IEQ (`finalQuantity`), total buy/sell qty, best bid/ask + qty (derived from book levels: highest buy-price level / lowest sell-price level), cancelled qty **when exposed**, full raw row JSON.

## Storage
- Normalized → `ipo_preopen_book` (`source='nse-live'`), **idempotent** via `state_hash` UNIQUE + ON CONFLICT DO NOTHING — only *changed* book states insert (dedupe by content).
- Raw → `nse_preopen_raw` (JSONB), written only on state change.
- Migration: owned by `schema_sync.py` (runs first in lean; already idempotent).

## Schedule (IST) — pick ONE line per your server TZ (`timedatectl`)
```
# server in IST:
57 8 * * 1-5  cd /root/aac && set -a && . ./.env && set +a && venv/bin/python _scripts/nse_preopen_capture.py >> logs/nse_preopen.log 2>&1
# server in UTC:
27 3 * * 1-5  cd /root/aac && set -a && . ./.env && set +a && venv/bin/python _scripts/nse_preopen_capture.py >> logs/nse_preopen.log 2>&1
```
Self-exits instantly on non-listing days; polls 20s±3 jitter 08:59:30–10:00:30 IST only.
⚠️ Pre-existing crontab oddity noted during this work: it mixes IST-style and UTC-style lines with IST comments — worth reconciling once.

## Alerting
3 consecutive failures / empty-during-window / shape change / 8-poll stale book → `pipeline_failures` (Pipeline health, phone) + ntfy push when `NTFY_TOPIC` set.

## Legal / reliability risks (stated plainly)
- NSE's terms disallow automated scraping; robots and Akamai actively resist bots. This capture is **internal, personal-research use, listing mornings only, ~180 requests/morning max** — conservative, but the risk is not zero: NSE can block or change the API without notice (shape guard + alerts cover detection, not permission). **Never redistribute this data** in the product beyond your own decision screens. The sanctioned long-term path remains the NSE Data & Analytics licence (research doc from earlier).
- Dependency: `curl_cffi` on the VM (`pip install curl_cffi --break-system-packages`).

## Rollback (fully additive build)
Remove the cron line → capture stops. Data isolated by tag: `DELETE FROM ipo_preopen_book WHERE source='nse-live'; DROP TABLE nse_preopen_raw;` reverses storage. No existing code paths modified.
