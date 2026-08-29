// app/api/auth/zerodha/callback/route.ts
// Legacy manual OAuth callback retained as a Cloudflare-only fallback.
// It never writes Neon. The automated token refresh / broker Worker remains canonical.
import { NextRequest, NextResponse } from "next/server"
import { exchangeKiteToken } from "@/lib/brokers/zerodha"
import { audit, clientIp } from "@/lib/security/audit"
import { getCloudflareContext } from "@opennextjs/cloudflare"

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "https://aacapitalprivatelimited.com"

type KvLike = { put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void> }

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const requestToken = searchParams.get("request_token")
    const status = searchParams.get("status")

    if (status !== "success" || !requestToken) {
      return NextResponse.redirect(`${APP_URL}?error=zerodha_auth_failed`)
    }

    const accessToken = await exchangeKiteToken(requestToken)
    if (!accessToken) throw new Error("No access token")

    const { env } = await getCloudflareContext({ async: true })
    const cache = (env as unknown as { CACHE?: KvLike }).CACHE
    if (!cache) throw new Error("Cloudflare CACHE binding unavailable")

    // Kite access tokens are daily. TTL deliberately stays below 24h so stale
    // credentials disappear instead of silently surviving into the next session.
    await cache.put("broker:kite:access-token", accessToken, { expirationTtl: 23 * 60 * 60 })

    await audit("auth.zerodha.callback", {
      ip: clientIp(req),
      detail: { outcome: "success", store: "cloudflare_kv" },
    })

    return NextResponse.redirect(`${APP_URL}?kite=connected&t=${Date.now()}`)
  } catch (err: any) {
    console.error("Kite callback error:", err)
    return NextResponse.redirect(`${APP_URL}?error=zerodha_callback_failed`)
  }
}
