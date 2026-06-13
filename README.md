# AACapital Intelligence Layer — Complete Pack (1+2+3+4)

Full plug-and-play intelligence data layer for AACapital.
Covers 200 Indian equities across all intelligence modules.

---

## What's included

| Pack | Contents |
|---|---|
| Pack 1 | Scoring engines — earnings, commentary, AMFI |
| Pack 2 | Next.js API routes (4 endpoints) |
| Pack 3 | GitHub Actions cron workflows (daily, monthly, quarterly) |
| Pack 4 | Data loaders, extractors, backfill scripts |

---

## File Map

```
.github/
  workflows/
    daily-intelligence.yml      ← Mon–Fri 6:30 AM IST (results + commentary + scoring)
    monthly-amfi.yml            ← 10th of month (AMFI download + scoring)
    quarterly-backfill.yml      ← Quarterly + manual trigger (full history)

lib/
  db.ts                         ← Neon PostgreSQL client
  watchlist.ts                  ← 200-stock universe (edit this to add/remove)
  intelligence/
    types.ts                    ← Shared TypeScript types
    earnings-score.ts           ← Earnings acceleration scoring engine
    commentary-score.ts         ← Management commentary scoring engine
    amfi-score.ts               ← AMFI liquidity scoring engine

app/
  api/intelligence/
    earnings/route.ts           ← GET /api/intelligence/earnings[?symbol=X]
    commentary/route.ts         ← GET /api/intelligence/commentary[?symbol=X]
    amfi/route.ts               ← GET /api/intelligence/amfi
    dashboard/route.ts          ← GET /api/intelligence/dashboard

scripts/
  seed-intelligence-sample.ts   ← Seed 4 sample stocks + run scoring (dev/test)
  loaders/
    load-amfi.ts                ← Download AMFI monthly data (free, no LLM)
    load-quarterly-results.ts   ← Load results via Screener.in API or CSV
  extractors/
    extract-commentary.ts       ← Extract commentary via Claude API (only LLM)
  backfill/
    backfill-earnings.ts        ← 10-year earnings history
    backfill-amfi.ts            ← AMFI history from 2020

package-snippet.json            ← Dependencies and npm scripts to merge
```

---

## Cost at 200 Stocks

| Module | Source | Cost |
|---|---|---|
| Quarterly results | Screener.in API (free) or CSV upload | ₹0 |
| AMFI flows | amfiindia.com direct download | ₹0 |
| Management commentary | Claude claude-sonnet-4-6 (~$0.003/stock/quarter) | ~₹200–400/year |
| **Total** | | **< ₹500/year** |

---

## Required Environment Variables

```bash
DATABASE_URL=postgresql://user:pass@host/db    # Neon PostgreSQL
ANTHROPIC_API_KEY=sk-ant-...                   # For commentary extraction only
SCREENER_API_KEY=...                           # Optional: Screener.in free API token
```

---

## Setup Steps

### 1. Add to tsconfig.json (if not already)
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": { "@/*": ["./*"] }
  }
}
```

### 2. Install dependencies
```bash
npm install @neondatabase/serverless csv-parse
npm install -D tsx
```

### 3. Add .env.local
```bash
DATABASE_URL=postgresql://...
ANTHROPIC_API_KEY=sk-ant-...
SCREENER_API_KEY=...
```

### 4. Add GitHub Secrets
Go to: GitHub repo → Settings → Secrets and variables → Actions
Add: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `SCREENER_API_KEY`

### 5. Seed sample data (dev/test)
```bash
npx tsx scripts/seed-intelligence-sample.ts
```

### 6. Run full backfill (first time only, run locally)
```bash
npx tsx scripts/backfill/backfill-earnings.ts --from=2016 --to=2026
npx tsx scripts/backfill/backfill-amfi.ts --from-year=2020 --to-year=2026
npx tsx scripts/extractors/extract-commentary.ts --mode=incremental
npx tsx scripts/run-intelligence-scoring.ts
```

---

## API Endpoints

```
GET /api/intelligence/earnings              → all latest scores
GET /api/intelligence/earnings?symbol=WABAG → single stock
GET /api/intelligence/commentary            → all commentary scores
GET /api/intelligence/commentary?symbol=KAYNES
GET /api/intelligence/amfi                  → latest AMFI liquidity score
GET /api/intelligence/dashboard             → combined view (earnings + amfi)
```

---

## Architecture Principle

```
Vercel (API routes)    → query DB views only. No extraction, no LLM, no backfill.
GitHub Actions         → all data loading, extraction, scoring
Local machine          → initial backfill, manual PDF uploads
```
