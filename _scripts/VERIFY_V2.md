# Verifying feat/v2-database against misty-meadow (V2)

Status: reference — how to smoke the V2 routes against misty-meadow (added with PR #282).

## The problem with the cloud branch preview
A per-branch Cloudflare preview URL runs the **same worker** with the **same vars/secrets**
as production. Production's `DATABASE_URL` is a plaintext variable pointing at
`ep-small-river` (V1), which has none of the canonical tables (`ipo`, `valuation`,
`decisions`, …). So the rewritten routes would **500 on that preview and prove nothing**.
There is no per-version-alias var override.

## Recommended: local `next dev` against misty-meadow (no prod risk)
`.env.local` already sets `DATABASE_URL` to `ep-misty-meadow`. In `next dev`,
`getCloudflareContext()` throws (not on CF) → KV is `null` → every route queries Neon
directly against **V2**. This is the cheapest faithful full-app smoke.

```bash
npm run dev            # reads .env.local (misty-meadow)
```

Then exercise the rewritten routes (ungated ones need no session):

```bash
curl -s localhost:3000/api/ipo/index | head -c 300           # ungated
curl -s "localhost:3000/api/ipo/journey?sym=INDOMIM" | head  # ungated
curl -s localhost:3000/api/ipo/live-preopen | head           # ungated (array empty off listing-day — see below)
# ipo-command is session-gated; use the warm bypass with the machine key:
curl -s -H "x-aac-key: $ADMIN_JOB_KEY" "localhost:3000/api/ipo-command?warm=1" | head -c 300
# /api/admin/diagnostics needs a signed-in session (localhost Google callback works).
```

A route that returns a JSON error/500 or a `degraded` payload is not ready.
(`next dev` has no CACHE binding, so it always hits Neon — that's fine for correctness;
the KV path is exercised by a local `opennextjs-cloudflare preview` build, which needs
the `next build --webpack` fix — its own PR.)

## Cloud preview on misty-meadow (if you want a hosted one)
Add a named wrangler environment with its own DB var and re-declared bindings, then
`opennextjs-cloudflare deploy --env preview` (verify your opennext version supports `--env`):

```jsonc
// wrangler.jsonc
"env": {
  "preview": {
    "vars": { "DATABASE_URL": "<misty-meadow-url>" },      // plaintext var, V2
    "kv_namespaces": [ { "binding": "JOB_FLAG", "id": "<real>" },
                       { "binding": "CACHE",    "id": "<real>" } ]
    // secrets are per-env: `wrangler secret put AUTH_SECRET --env preview`, etc.
  }
}
```
Caveats: this is a **separate worker** (own workers.dev URL), so Google/Zerodha OAuth
callbacks won't match it — login won't work there. Most rewritten DB routes are ungated
(index, journey, live-preopen) or have the `?warm=1` machine-key bypass (ipo-command),
so API smoke still works; only `/api/admin/diagnostics` needs a real session.

## Owner's fallback (flip prod, smoke, roll back)
Legitimate but riskier: change the worker's `DATABASE_URL` to misty-meadow, smoke, and if
anything breaks set it straight back to the small-river URL (rollback is one variable, ~seconds
to propagate). Prefer the local `next dev` smoke first so a prod flip is a formality.

## Exercising /api/ipo/live-preopen with real data
The route filters `listing_date = IST-today`, so it returns `[]` on non-listing days —
it must not be judged only by an empty set. Three ways to exercise it:

1. **Permanent unit test (already in this PR):** `lib/v2/live-preopen.test.ts` feeds the
   two REAL rows captured for 2026-07-30 (INDOMIM, LCL) through `scoreListing()` — the exact
   money path the route runs — asserting e.g. INDOMIM (RHP=JUNK) → `confidence 0` despite a
   +44% open, and LCL's proxy `pe_source` is disclosed. `npm test`.

2. **Ad-hoc against misty-meadow** — run the route's query for a past listing date to see
   real rows (swap the date):
   ```sql
   -- same query as fetchPreopenRows, but with a fixed past date instead of IST-today:
   WHERE i.listing_date = '2026-07-30' AND i.is_mainboard = true ...
   ```
   (Recent qualifying mainboard listing dates: 2026-07-31, -07-30 ×2, -07-28, -07-24, -07-21 …)

3. **Next listing morning:** `curl localhost:3000/api/ipo/live-preopen` (or the preview) during
   the 09:00–10:00 IST window; the cache HARD-BYPASSES 08:55–10:05 IST so it's never stale then.
