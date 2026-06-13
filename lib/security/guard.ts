// lib/security/guard.ts
// Gate server-only endpoints behind ADMIN_SECRET.
// Use for routes NOT called from the browser (db/init, maintenance).
//
// Generate ADMIN_SECRET (run in PowerShell, one line):
//   node -e "console.log(require('crypto').randomBytes(24).toString('base64url'))"
// Add to Vercel env AND .env.local as ADMIN_SECRET=<value>
//
// Call from endpoint:  const blocked = requireAdminSecret(req); if (blocked) return blocked

import crypto from "node:crypto"

function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a, "utf8")
  const bb = Buffer.from(b, "utf8")
  if (ab.length !== bb.length) return false
  return crypto.timingSafeEqual(ab, bb)
}

/**
 * Returns a 404 Response if the x-admin-secret header doesn't match
 * ADMIN_SECRET, or null to let the request proceed.
 * Uses 404 (not 403) so the endpoint's existence is never confirmed.
 */
export function requireAdminSecret(req: Request): Response | null {
  const secret   = process.env.ADMIN_SECRET ?? ""
  const provided = req.headers.get("x-admin-secret") ?? ""
  if (!secret || !safeEqual(provided, secret)) {
    return new Response("Not found", { status: 404 })
  }
  return null
}
