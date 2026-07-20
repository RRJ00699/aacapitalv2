# Asset-Light Architecture — AACapital

**Principle:** reads serve from cache; Neon wakes only for scheduled WRITES.
Between the 08:30 and 17:00 IST pipelines, derived data is static — a page load
must never touch Neon.

## Step 1 — Cache-on-write (SHIPPED this PR)
- `CACHE` KV namespace bound in wrangler (was missing → command-route cache
  writes were silently no-op'ing; every "cached" load actually hit Neon).
- Command route TTL 10min → 12h; accepts machine key for `?warm=1`.
- Pipeline calls `?warm=1` after a clean run → rebuilds KV while Neon is already
  awake → page loads serve from KV until the next pipeline. **Neon read traffic
  between pipelines → zero.**

## Step 2 — Extend to other read routes (SHIPPED this PR)
- `lib/kv-cache.ts` `cached(key, build, ttl)` helper. Routes serving derived
  data (gmp, playbook, market/snapshot, post-listing) wrap their DB work in it.
  Per-route adoption is one line; done incrementally to keep each testable.
- Live routes (tick-feed, live-preopen) are NOT cached — they're the real-time
  signal (Step 3).

## Step 3 — Live values via KV + WebSocket (DESIGN — needs owner enable)
Listing mornings only (~5/month). Goal: live prices don't wake Neon per tick.
- `kite_ticker_ipo.py` holds ONE Zerodha WebSocket (already exists).
- Ticks → KV (`live:preopen:<sym>`), NOT Neon. App reads live prices from KV.
- ONE batched flush to Neon per minute for the historical record (executemany),
  not per-tick. Between listing days: zero live traffic.
- Enable: point the ticker's sink at the KV PUT route + add the per-minute
  archival flush. Requires the tick writer to hold ADMIN_JOB_KEY.

## Step 4 — Batched writes, DB wakes once (DESIGN — refinement)
Pipeline already batches 2x/day. Refinements:
- Ensure no script opens an EARLY connection mid-run (schema_sync + smoke
  currently bookend; keep the single connection window tight).
- Heavy compute stages stage to local SQLite/memory; ONE bulk COPY at the end.
- NB: an Excel intermediary was considered and rejected — fragile parse/format
  step + a file to lose. Bulk INSERT is the same "one shot" done safely.

## Guard
`neon_sleep_sentinel.py` (03:33 IST) proves the DB slept overnight; alerts phone
on violation. This is how we KNOW the architecture holds, every night.

## Expected outcome
Steps 1–2: Neon wakes ~2x/day (pipeline) + rare cold-start cache misses →
**< 1 CU-h/day**. Steps 3–4 shave listing-day tick spikes.

## Step 3 — SHIPPED (this PR)
- `/api/admin/kv-put` — auth-gated (ADMIN_JOB_KEY) KV-write route for the VM ticker.
- Ticker (`ipo/kite_ticker_ipo.py`) writes each throttled snapshot to KV
  (`live:tick:<sym>`, 5-min TTL) every ~5s → live view reads KV, ZERO Neon.
- Neon flush throttled to once per 60s (option B) — 1-min archival trickle
  instead of a continuous session. DB can suspend even during trading.
- `/api/ipo/tick-feed` reads KV latest first (`?live=1` = zero-Neon path);
  history still from Neon only when the chart is expanded.
- Symbols already IPO-only (≤6 mainboard ≥₹200cr, listing-day) — verified, not
  1440 stocks.

## Command-center staleness — FIXED (this PR)
Root cause: `OR (listing_date IS NULL AND ipo_close_date IS NULL)` made any
dateless row show forever → Suryoday/Mamaearth/Ventive (2023-24) leaked in.
Removed; now shows ONLY current IPOs (open, upcoming, or within ~45d anchor
lock-in). This also cleans Upcoming/Open-Now (those dateless rows had null
state and filtered inconsistently).

## Step 4 — DOCUMENTED, metrics-gated (not built)
Build ONLY if 1–3 don't reach target. Track weekly:
| Metric | Source | Target |
|---|---|---|
| CU-hours/day | Neon console Usage | < 1 |
| Endpoint idle overnight | sleep sentinel (03:33) | idle |
| Cache hit-rate | route x-cache headers | > 90% |
| Neon wake events/day | pg_stat_activity samples | ~2 (pipelines) + rare |
If these hold after 1–3, Step 4 (local-SQLite staging + bulk load) is
unnecessary and will NOT be built.
