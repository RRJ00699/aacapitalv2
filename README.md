Status: CURRENT

# AACapital — IPO Decision-Support System

Personal, **IPO-only**, evidence-first research tool for Indian mainboard
IPOs: pre-listing research → listing-day entry decision → post-listing
hold/exit discipline. The app informs; the owner trades manually.
**"Research signal, not a buy call."**

**Authoritative product rules:** [`docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md`](docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md)
(where any other doc disagrees, the contract wins).

## Repository zones

This repository intentionally keeps its current layout; an `apps/web` or
`packages/*` conversion belongs in a future repository.

- **FRONTEND — `app/`, `components/`, `lib/`**: product UI, routes, and web/domain
  helpers. Public surfaces are KV-only and zero-wake: they may not use `psycopg`,
  `@neondatabase`, `DATABASE_URL`, or `@/lib/db`.
- **BACKEND — `pipeline/`**: the canonical database boundary for the offline
  production pipeline. It owns document ingestion and extraction, lifecycle,
  valuation, intelligence, and snapshot construction.
- **EDGE — `workers/`**: Cloudflare edge responsibilities only.
- **OPS — `_scripts/`**: caller-evidenced operational tooling only. Its keep set
  and caller chain are recorded in `docs/repository-inventory.tsv`.
- **QUARANTINE — `compatibility/`, `_archive/`**: runnable compatibility or
  historical reference. Production code must never import from either zone.
- **KNOWLEDGE — `docs/`, `research/`**: architecture, decisions, runbooks,
  specifications, and offline research/backtests; never production entrypoints.

Public reads remain Cloudflare KV-only. Neon wakes only for explicit offline
pipeline work and publication, as described in
`docs/architecture/ASSET_LIGHT_ARCHITECTURE.md`.
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
