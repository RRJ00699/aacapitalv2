// app/api/auth/zerodha/callback/route.ts
import { NextRequest, NextResponse } from "next/server"
import { exchangeKiteToken } from "@/lib/brokers/zerodha"
import { getDb } from "@/lib/db/schema"
import { encrypt } from "@/lib/security/crypto"
import { audit, clientIp } from "@/lib/security/audit"

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "https://aacapital.vercel.app"

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const requestToken = searchParams.get("request_token")
    const status       = searchParams.get("status")

    if (status !== "success" || !requestToken) {
      return NextResponse.redirect(`${APP_URL}?error=zerodha_auth_failed`)
    }

    const accessToken = await exchangeKiteToken(requestToken)
    if (!accessToken) throw new Error("No access token")

    // Encrypt before storing — AES-256-GCM (lib/security/crypto.ts)
    const encryptedToken = encrypt(accessToken)

    const sql = getDb()
    await sql`DELETE FROM kite_session`
    await sql`
      INSERT INTO kite_session (access_token, user_id)
      VALUES (${encryptedToken}, ${"owner"})
    `

    await audit("auth.zerodha.callback", {
      ip: clientIp(req),
      detail: { outcome: "success" },
    })

    return NextResponse.redirect(`${APP_URL}?kite=connected&t=${Date.now()}`)
  } catch (err: any) {
    console.error("Kite callback error:", err)
    // Never expose raw errors in redirects (P1-B #6)
    return NextResponse.redirect(`${APP_URL}?error=zerodha_callback_failed`)
  }
}
