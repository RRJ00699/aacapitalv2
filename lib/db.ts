/**
 * db.ts — AACapital database helpers (edge-compatible)
 * - sql      => Neon cloud DB (HTTP driver, works on Cloudflare Workers + Vercel)
 * - localSql => falls back to the same Neon DB (no local Postgres on edge)
 *
 * Rewritten to use @neondatabase/serverless (HTTP) instead of `pg` (TCP Pool),
 * because `pg` can't run on Cloudflare Workers (it needs pg-cloudflare/native
 * sockets that don't bundle). The neon() HTTP driver is edge-native.
 * Exported API is unchanged so all existing routes keep working as-is.
 */

import { neon } from '@neondatabase/serverless'

type QueryValue = unknown

// Lazy client — do NOT read env or throw at MODULE SCOPE. `next build` evaluates
// route modules during "Collecting page data" without runtime env available, so a
// module-scope throw here fails the production build. deploy.yml runs the build
// with no DATABASE_URL; ci.yml injects a dummy one — which is exactly why CI went
// green but the deploy died at /api/auth/zerodha/callback. Resolving on first
// query keeps the identical clear error at runtime, but the build no longer needs
// the DB env.
let _client: ReturnType<typeof neon> | null = null

function getClient() {
  if (_client) return _client
  const neonConnectionString = process.env.DATABASE_URL
  if (!neonConnectionString) {
    throw new Error('\n[db] DATABASE_URL is required for AACapital production database access.\n')
  }
  // neon() is stateless (no pool/socket), safe per-request on edge.
  _client = neon(neonConnectionString)
  return _client
}

// ── UAT fixture mode (feat/ux-premium) ────────────────────────────────────
// When UAT_FIXTURE_JSON points at a JSON file mapping a lowercase SQL
// substring -> rows, every query is served from that file: deterministic,
// zero Neon, zero paid APIs. Used ONLY by `npm run uat:all` and the route
// harness — the env var is never set in production. Unmatched queries
// return [] (routes already handle empty sets).
let _fixture: Record<string, any[]> | null | undefined
function fixtureRows(q: string): any[] | null {
  if (_fixture === undefined) {
    const path = process.env.UAT_FIXTURE_JSON
    if (!path) { _fixture = null } else {
      try {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        _fixture = JSON.parse(require("fs").readFileSync(path, "utf8"))
        console.warn(`[db] UAT FIXTURE MODE — serving queries from ${path} (no Neon)`) 
      } catch { _fixture = null }
    }
  }
  if (!_fixture) return null
  const lower = q.toLowerCase()
  for (const k of Object.keys(_fixture)) if (lower.includes(k)) return JSON.parse(JSON.stringify(_fixture[k]))
  return []
}

async function runQuery(strings: TemplateStringsArray, values: QueryValue[]): Promise<any[]> {
  const fx = fixtureRows(strings.join(" "))
  if (fx !== null) return fx
  // neon supports tagged-template queries with the same $1..$n semantics.
  return (await (getClient() as any)(strings, ...values)) as any[]
}

export async function sql(strings: TemplateStringsArray, ...values: QueryValue[]): Promise<any[]> {
  return runQuery(strings, values)
}

export async function localSql(strings: TemplateStringsArray, ...values: QueryValue[]): Promise<any[]> {
  // No local Postgres on edge — use the same Neon DB. Routes already tolerate
  // partial data, so candle-heavy queries simply run against Neon.
  return runQuery(strings, values)
}

export function normalizeSymbol(symbol: string | null | undefined): string {
  return String(symbol || '').trim().toUpperCase().replace(/\.NS$/i, '')
}

export function ok(data: unknown, init?: ResponseInit) {
  return Response.json({ success: true, data }, init)
}

export function fail(message: string, status = 500, details?: unknown) {
  return Response.json({ success: false, error: message, details }, { status })
}

// UAT: drop-in replacement for private route-level neon(url) factories so
// fixture mode reaches EVERY route (several kept their own clients).
export function fixtureAwareNeon(url?: string) {
  let _r: ReturnType<typeof neon> | null = null
  return (async (strings: TemplateStringsArray, ...values: QueryValue[]) => {
    const fx = fixtureRows(strings.join(" "))
    if (fx !== null) return fx
    if (!_r) _r = neon(url || process.env.DATABASE_URL!)
    return (await (_r as any)(strings, ...values)) as any[]
  }) as unknown as ReturnType<typeof neon<false, false>>
}
