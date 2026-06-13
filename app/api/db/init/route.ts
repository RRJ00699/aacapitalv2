// app/api/db/init/route.ts
import { NextResponse } from "next/server"
import { initDb } from "@/lib/db/schema"
import { requireAdminSecret } from "@/lib/security/guard"
import { audit, clientIp } from "@/lib/security/audit"

export async function POST(req: Request) {
  // Returns 404 to anyone without x-admin-secret header (P1-B #2)
  const blocked = requireAdminSecret(req)
  if (blocked) return blocked

  try {
    const result = await initDb()
    await audit("db.init", { ip: clientIp(req) })
    // Spread result first, then ok:true wins if result also has ok
    return NextResponse.json({ ...result, ok: true, message: "Database initialized successfully" })
  } catch (err: any) {
    console.error("DB init error:", err)
    // Never expose internal errors (P1-B #6)
    return NextResponse.json({ error: "Initialization failed" }, { status: 500 })
  }
}
