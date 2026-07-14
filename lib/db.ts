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

const neonConnectionString = process.env.DATABASE_URL || process.env.NEON_DATABASE_URL

if (!neonConnectionString) {
  throw new Error('\n[db] DATABASE_URL or NEON_DATABASE_URL is required for AACapital cloud intelligence tables.\n')
}

// One HTTP client; neon() is stateless (no pool/socket), safe per-request on edge.
const client = neon(neonConnectionString)

type QueryValue = unknown

async function runQuery(strings: TemplateStringsArray, values: QueryValue[]): Promise<any[]> {
  // neon supports tagged-template queries with the same $1..$n semantics.
  // Delegate directly to the neon tagged template.
  return (await (client as any)(strings, ...values)) as any[]
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
