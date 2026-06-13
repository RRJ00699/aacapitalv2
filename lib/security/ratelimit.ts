// lib/security/ratelimit.ts
// Neon-backed rate limiter for AI routes.
// Self-healing: creates the table on first call.
// On infra failure it ALLOWS the request — never blocks real users on a DB hiccup.

import { neon } from "@neondatabase/serverless"

function db() {
  return neon(process.env.DATABASE_URL!)
}

export interface RateLimitResult {
  allowed: boolean
  remaining: number
  limit: number
}

/**
 * Check and record a rate-limited request.
 * @param key       Unique identifier, e.g. `"ai-memo:1.2.3.4"`
 * @param limitPerHour  Max requests allowed per rolling hour window
 */
export async function checkRateLimit(
  key: string,
  limitPerHour = 20
): Promise<RateLimitResult> {
  try {
    const sql = db()

    // Self-healing table creation
    await sql`
      CREATE TABLE IF NOT EXISTS rate_limit_log (
        id         BIGSERIAL    PRIMARY KEY,
        key        TEXT         NOT NULL,
        created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
      )
    `

    // Count requests in the last hour for this key
    const rows = await sql`
      SELECT COUNT(*) AS count
      FROM rate_limit_log
      WHERE key = ${key}
        AND created_at > NOW() - INTERVAL '1 hour'
    `
    const count = parseInt(rows[0]?.count ?? "0", 10)

    if (count >= limitPerHour) {
      return { allowed: false, remaining: 0, limit: limitPerHour }
    }

    // Log this request
    await sql`INSERT INTO rate_limit_log (key) VALUES (${key})`

    // Cleanup old rows probabilistically (10% of requests) to keep table lean
    if (Math.random() < 0.1) {
      await sql`DELETE FROM rate_limit_log WHERE created_at < NOW() - INTERVAL '24 hours'`
    }

    return { allowed: true, remaining: limitPerHour - count - 1, limit: limitPerHour }
  } catch {
    // Never block a real user because of a rate-limit infra failure
    return { allowed: true, remaining: -1, limit: limitPerHour }
  }
}
