/**
 * db.ts — AACapital Intelligence Layer
 * Uses pg (standard TCP driver) for all environments.
 * Neon accepts standard PostgreSQL TCP connections fine.
 */

import { config } from 'dotenv';
import { existsSync } from 'fs';
import { Pool } from 'pg';
import path from 'path';

const envLocalPath = path.resolve(process.cwd(), '.env.local');
const envPath      = path.resolve(process.cwd(), '.env');
if (existsSync(envLocalPath)) {
  config({ path: envLocalPath });
} else if (existsSync(envPath)) {
  config({ path: envPath });
}

// For local scripts use NEON — it already has your schema.
// Local PostgreSQL is only needed if you explicitly set DATABASE_URL to it.
const connectionString =
  process.env.DATABASE_URL ||
  process.env.NEON_DATABASE_URL ||
  process.env.LOCAL_DATABASE_URL;

if (!connectionString) {
  throw new Error(
    '\n[db] No database URL found in .env.local\n' +
    'Make sure DATABASE_URL or NEON_DATABASE_URL is set.\n'
  );
}

const pool = new Pool({
  connectionString,
  ssl: { rejectUnauthorized: false }, // works for both Neon and local with ssl
  max: 5,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 10000,
});

export async function sql(
  strings: TemplateStringsArray,
  ...values: unknown[]
): Promise<any[]> {
  let text = '';
  strings.forEach((str, i) => {
    text += str;
    if (i < values.length) text += `$${i + 1}`;
  });
  const result = await pool.query(text, values as any[]);
  return result.rows;
}

export function normalizeSymbol(symbol: string | null | undefined): string {
  return String(symbol || '').trim().toUpperCase();
}

export function ok(data: unknown, init?: ResponseInit) {
  return Response.json({ success: true, data }, init);
}

export function fail(message: string, status = 500, details?: unknown) {
  return Response.json({ success: false, error: message, details }, { status });
}
