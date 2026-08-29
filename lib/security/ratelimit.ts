// lib/security/ratelimit.ts
// D1-backed rate limiter for AI routes. Infra failure allows the request.

import { d1First, d1Run } from "@/lib/d1"

export interface RateLimitResult {
  allowed: boolean
  remaining: number
  limit: number
}

export async function checkRateLimit(key: string, limitPerHour = 20): Promise<RateLimitResult> {
  try {
    const row = await d1First<{ count: number }>(
      `SELECT COUNT(*) AS count FROM rate_limit_log
       WHERE rate_key=? AND created_at > datetime('now','-1 hour')`,
      [key],
    )
    const count = Number(row?.count ?? 0)
    if (count >= limitPerHour) return { allowed: false, remaining: 0, limit: limitPerHour }

    await d1Run(`INSERT INTO rate_limit_log(rate_key,created_at) VALUES(?,CURRENT_TIMESTAMP)`, [key])
    if (Math.random() < 0.1) {
      await d1Run(`DELETE FROM rate_limit_log WHERE created_at < datetime('now','-24 hours')`)
    }
    return { allowed: true, remaining: limitPerHour - count - 1, limit: limitPerHour }
  } catch {
    return { allowed: true, remaining: -1, limit: limitPerHour }
  }
}
