// lib/security/audit.ts
// Append-only audit trail for broker actions and data refreshes.
// Self-healing: creates audit_log table automatically on first call.
// Logging NEVER breaks the request path — all errors are swallowed.

import { neon } from "@neondatabase/serverless"

// neon() must be inside a function, never at module level (rule #5)
function db() {
  return neon(process.env.DATABASE_URL!)
}

export type AuditAction =
  | "broker.holdings.read"
  | "broker.positions.read"
  | "broker.quote.read"
  | "broker.order.place"
  | "auth.zerodha.connect"
  | "auth.zerodha.callback"
  | "data.refresh"
  | "db.init"
  | "ai.memo"
  | "ai.drhp"

export async function audit(
  action: AuditAction,
  opts: { actor?: string; detail?: unknown; ip?: string } = {}
): Promise<void> {
  try {
    const sql = db()
    // Self-healing: CREATE TABLE IF NOT EXISTS on every call.
    // Postgres caches the catalog check so overhead is negligible after the first hit.
    await sql`
      CREATE TABLE IF NOT EXISTS audit_log (
        id         BIGSERIAL PRIMARY KEY,
        action     TEXT        NOT NULL,
        actor      TEXT,
        detail     JSONB,
        ip         TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      )
    `
    await sql`
      INSERT INTO audit_log (action, actor, detail, ip)
      VALUES (
        ${action},
        ${opts.actor ?? null},
        ${opts.detail ? JSON.stringify(opts.detail) : null}::jsonb,
        ${opts.ip ?? null}
      )
    `
  } catch (err) {
    // Swallow — audit failure must never take down the actual operation
    console.error("audit_log write failed:", err)
  }
}

// Extract client IP from Vercel/Next.js request headers
export function clientIp(req: Request): string | undefined {
  return (
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    req.headers.get("x-real-ip") ||
    undefined
  )
}
