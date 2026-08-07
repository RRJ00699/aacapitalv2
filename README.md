Status: CURRENT

# AACapital — IPO Decision-Support System

Personal, **IPO-only**, evidence-first research tool for Indian mainboard
IPOs: pre-listing research → listing-day entry decision → post-listing
hold/exit discipline. The app informs; the owner trades manually.
**"Research signal, not a buy call."**

**Authoritative product rules:** [`docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md`](docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md)
(where any other doc disagrees, the contract wins).

## Architecture

- **UI/API** — Next.js (`app/`), deployed via OpenNext on Cloudflare
  (`wrangler.jsonc`, `open-next.config.ts`). Main page:
  `/dashboard/ipo2` (Command · Live · Post views) + `/dashboard/journey`.
- **Data** — Neon Postgres. Source table `ipo_intelligence`; derived
  `ipo_consolidated` (see `SCHEMA.md`). **Zero-idle rule:** user reads serve
  from Cloudflare KV; Neon wakes only for pipeline writes/warms
  (`docs/architecture/ASSET_LIGHT_ARCHITECTURE.md`).
- **Pipelines** — Python in `_scripts/`, run 2×/day by cron on the VM
  (`run_ipo_pipeline_lean.py`; spec in `PIPELINE_SPEC.md`). Flow: NSE
  discovery → enrichment (Chittorgarh/NSE/SEBI/SBI/IPOMatrix) → RHP + SBI
  PDF extraction (Sonnet $3/day + Haiku $0.50/day caps) → scores/verdicts →
  consolidated rebuild → KV cache warm.
- **Listing day** — Kite token auto-refresh (TOTP, 08:00 IST) → tick capture
  (`_scripts/ipo/kite_ticker_ipo.py`) → KV `live:tick:*` → Live view.
- **Alerts** — ntfy.sh push (`_scripts/lib/notify.py`): URGENT on Kite token
  failure; HIGH on pipeline/RHP/scraper failures. Timestamps in IST +
  US-Central.

## Local setup

```bash
npm ci                       # Node deps
pip install -r requirements.txt --break-system-packages   # Python deps
```

## Environment variables

| Var | Purpose | Required |
|---|---|---|
| `DATABASE_URL` (or `NEON_DATABASE_URL`) | Neon Postgres | yes |
| `ADMIN_JOB_KEY` | machine auth for warm/kv-put endpoints | prod |
| `NTFY_TOPIC` / `NTFY_SERVER` | push alerts (topic = auth; server optional) | recommended |
| `KITE_API_KEY/SECRET/USER_ID/PASSWORD/TOTP_SECRET` | Zerodha auto-login (or set via Settings → platform_config) | for market data |
| `NEXT_PUBLIC_APP_URL` | app origin for VM→app KV pushes | VM |
| `ANTHROPIC_API_KEY` | RHP/SBI extraction | pipeline |

## Development

```bash
npm run dev                  # local app
npx tsc --noEmit             # typecheck (must be clean before any PR)
python -m pytest _scripts/tests/ -q     # test suite (DB-gated tests skip locally)
npm run build                # production build
```

Pipeline dry-runs from `_scripts/`: most writers take `--apply`; without it
they preview only.

## Operating discipline

- Backtest before shipping any signal; **n≥30 = SIGNAL bar**.
- Executable prices only — never theoretical allotment returns.
- Strong-key joins (ISIN > exact normalized name); raw facts fill-empty-only.
- Rejected/zero-weight factors stay rejected
  (contract §7) unless the §8 evidence process is followed.
- PRs merge only after typecheck + tests pass and owner review.

## Repo map

```
app/            Next.js UI + API routes (production)
components/     shared UI (production)
lib/            shared TS logic; lib/kv-cache.ts = KV helper
_scripts/       Python pipelines, scrapers, backtests, tests (_scripts/tests)
docs/           current documentation · docs/archive = history only
```
