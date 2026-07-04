// app/api/admin/check/route.ts
// Lightweight yes/no so the client nav can decide whether to show the Admin tab.
// Behind the login wall already (proxy.ts); returns admin=false for non-admins.
import { NextResponse } from "next/server";
import { getAdminEmail } from "@/lib/admin";

export const dynamic = "force-dynamic";

export async function GET() {
  const admin = await getAdminEmail();
  return NextResponse.json({ admin: !!admin });
}
