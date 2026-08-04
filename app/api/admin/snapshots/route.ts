import { NextResponse } from "next/server";
import { fixtureAwareNeon } from "@/lib/db";
import { getAdminEmail } from "@/lib/admin";
import { requireUser } from "@/lib/api-guard";
import { publishVersionedSnapshot } from "@/lib/kv-cache";
import { buildCommand } from "@/lib/v2/ipo-command";
import { buildIpoIndex } from "@/lib/v2/ipo-index";
import type { SqlClient } from "@/lib/v2/sql";

export const dynamic = "force-dynamic";

export async function GET() {
  const gate = await requireUser(); if (gate) return gate;
  if (!await getAdminEmail()) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  return NextResponse.json({ error: "use POST" }, { status: 405 });
}

export async function POST(req: Request) {
  const gate = await requireUser(); if (gate) return gate;
  if (!await getAdminEmail()) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  if (req.headers.get("x-aac-key") !== process.env.ADMIN_JOB_KEY) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  const target = new URL(req.url).searchParams.get("target");
  if (target !== "command" && target !== "index") return NextResponse.json({ error: "target must be command or index" }, { status: 400 });
  const sql = fixtureAwareNeon() as unknown as SqlClient;
  const payload = target === "command" ? await buildCommand(sql) : await buildIpoIndex(sql);
  const generated_at = new Date().toISOString();
  const pointer = await publishVersionedSnapshot(target === "command" ? "ipo-command:v6" : "ipo:index:v3", payload, {
    generated_at, schema_version: "1", source_freshness: { database: generated_at },
    engine_versions: { command: "v6", identity: "v3" },
  });
  return NextResponse.json({ ok: true, target, pointer });
}
