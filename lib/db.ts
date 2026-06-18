/**
 * db.ts — AACapital database helpers
 * - sql     => Neon/cloud DB for Vercel UI and intelligence tables
 * - localSql=> Local Postgres for large candle tables when LOCAL_DATABASE_URL exists
 *
 * Safe behavior:
 * - Loads .env.local / .env automatically in local dev.
 * - Does not crash Vercel build if LOCAL_DATABASE_URL is missing.
 * - Uses ssl only for cloud URLs, not localhost.
 */

import { config } from 'dotenv'
import { existsSync } from 'fs'
import { Pool, type PoolConfig } from 'pg'
import path from 'path'

const envLocalPath = path.resolve(process.cwd(), '.env.local')
const envPath = path.resolve(process.cwd(), '.env')
if (existsSync(envLocalPath)) config({ path: envLocalPath })
else if (existsSync(envPath)) config({ path: envPath })

function isLocalUrl(url?: string | null): boolean {
  return !!url && (/localhost|127\.0\.0\.1|\[::1\]/i.test(url) || /sslmode=disable/i.test(url))
}

function makePool(connectionString: string, name: string): Pool {
  const cfg: PoolConfig = {
    connectionString,
    max: 5,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 10000,
  }
  if (!isLocalUrl(connectionString)) cfg.ssl = { rejectUnauthorized: false }
  const pool = new Pool(cfg)
  pool.on('error', (err) => console.error(`[db:${name}] idle client error`, err))
  return pool
}

const neonConnectionString = process.env.DATABASE_URL || process.env.NEON_DATABASE_URL
const localConnectionString = process.env.LOCAL_DATABASE_URL

if (!neonConnectionString) {
  throw new Error('\n[db] DATABASE_URL or NEON_DATABASE_URL is required for AACapital cloud intelligence tables.\n')
}

const neonPool = makePool(neonConnectionString, 'neon')
const localPool = localConnectionString ? makePool(localConnectionString, 'local') : null

type QueryValue = unknown

async function runQuery(pool: Pool, strings: TemplateStringsArray, values: QueryValue[]): Promise<any[]> {
  let text = ''
  strings.forEach((str, i) => {
    text += str
    if (i < values.length) text += `$${i + 1}`
  })
  const result = await pool.query(text, values as any[])
  return result.rows
}

export async function sql(strings: TemplateStringsArray, ...values: QueryValue[]): Promise<any[]> {
  return runQuery(neonPool, strings, values)
}

export async function localSql(strings: TemplateStringsArray, ...values: QueryValue[]): Promise<any[]> {
  // If LOCAL_DATABASE_URL is not available in Vercel, fall back to Neon so API routes still build/run.
  // Routes already catch query failures and return partial data instead of crashing.
  return runQuery(localPool || neonPool, strings, values)
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
