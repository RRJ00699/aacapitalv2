# Cloudflare Migration — Phase 0 Inventory (done 2026-07-14)

## The good news
- **0 routes use the filesystem** (fs) — removes the biggest edge-migration risk
- **18 of 46 routes already edge-ready** (use @neondatabase/serverless) — work on CF as-is
- Only **13 routes need conversion** — bounded, clear task

## 🟢 ALREADY EDGE-READY (18) — no changes needed
access-note, admin/access, admin/jobs, admin/secrets, cron/premarket-brief,
ipo-command, ipo/intelligence, ipo/journey, ipo/listing-day, ipo/live,
ipo/playbook, ipo/subscription, market/global, market/live, pipeline/status,
post-listing, settings, tracker

## 🔴 NEEDS CONVERSION (13) — pg Pool / lib/db → Hyperdrive or @neondatabase/serverless
auth/zerodha/callback, auth/zerodha/status, db/init, ipo/gmp, ipo/levels,
ipo/live-symbols, ipo/post-listing, ipo/predictions, ipo, ipo/tick-feed,
market-regime, market/snapshot, search

CONVERSION PATTERN (per route):
  OLD: import { Pool } from "pg"  /  import db from "@/lib/db"
       const pool = new Pool(...); pool.query(...)
  NEW: import { neon } from "@neondatabase/serverless"
       const sql = neon(env.DATABASE_URL); await sql`...`
  (or use Hyperdrive binding for connection pooling)

## ⚪ NO DB (15) — fine as-is
admin/check, auth/[...nextauth], auth/zerodha, broker/holdings, broker/positions,
broker/quote, broker/status, ipo/drhp, ipo/gmp-refresh, ipo/memo, ipo/monitor,
ipo/scrape, ipo/tape, ipo/upload, pipeline/trigger

## ⚠️ THE RISKY PIECES TO TEST HARD
1. **auth/[...nextauth]** — NextAuth v5-beta on Cloudflare Workers. The #1 risk.
   Test login/session thoroughly on the CF preview before cutover.
2. **auth/zerodha/*** — Kite OAuth callback. Test the token flow.
3. **lib/db.ts itself** — the shared pg Pool. Convert once, many routes follow.

## MIGRATION STEPS (Option B — app to CF, Neon stays)
1. Install @opennextjs/cloudflare adapter, test `next build` → CF build locally
2. Convert lib/db.ts + the 13 routes to edge driver
3. Set up Hyperdrive → Neon binding
4. Deploy to CF PREVIEW url (Vercel stays live)
5. Regression test EVERY screen + auth on preview
6. Only after green: point DNS, set up email routing
7. Monitor 48h with Vercel fallback, then decommission

## LIVE-FEATURE ARCHITECTURE (the upgrade CF enables)
- Move live Kite price → Workers KV cache (not Postgres)
- Live-exit / journey reads KV → Neon never touched intraday
- Optional: Durable Objects + WebSocket for true push (no polling)
- Result: per-second live features, Neon compute stays near-zero
