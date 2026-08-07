// lib/security/audit.ts
// Operational audit events for broker actions and data refreshes.
// Cloudflare captures console output in Worker logs.  Deliberately do not write
// to Postgres here: audit_log was retired and request code must never migrate a
// production schema (or wake Neon merely to record telemetry).

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
  console.info(JSON.stringify({
    type: "aacapital.audit.v1",
    action,
    actor: opts.actor,
    detail: opts.detail,
    ip: opts.ip,
    occurredAt: new Date().toISOString(),
  }))
}

// Extract client IP from Vercel/Next.js request headers
export function clientIp(req: Request): string | undefined {
  return (
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    req.headers.get("x-real-ip") ||
    undefined
  )
}
