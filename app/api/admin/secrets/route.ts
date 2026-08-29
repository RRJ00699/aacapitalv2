// app/api/admin/secrets/route.ts — secrets are canonical in Cloudflare Secrets.
import { NextRequest, NextResponse } from "next/server";
import { getAdminEmail } from "@/lib/admin";
import { requireUser } from "@/lib/api-guard";
export const dynamic = "force-dynamic";

const KEYS = [
  "screener_username", "screener_password", "screener_cookie", "ntfy_topic", "ipomatrix_cookie",
  "zerodha_totp_secret", "kite_api_key", "kite_api_secret", "kite_user_id", "kite_password",
];

export async function GET() {
  const gate = await requireUser(); if (gate) return gate;
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  const state = Object.fromEntries(KEYS.map((key) => [key, "managed in Cloudflare Secrets"]));
  return NextResponse.json({ state, kite: "managed by Cloudflare Kite broker Worker" });
}

export async function POST(_req: NextRequest) {
  const gate = await requireUser(); if (gate) return gate;
  const admin = await getAdminEmail();
  if (!admin) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  return NextResponse.json(
    { error: "Secret writes moved to Cloudflare Secrets; database secret storage is retired." },
    { status: 410 },
  );
}
