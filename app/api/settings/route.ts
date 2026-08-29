// app/api/settings/route.ts — D1-backed user preferences.
import { NextResponse } from "next/server";
import { d1All, d1Run } from "@/lib/d1";

export async function GET() {
  try {
    const rows = await d1All<{ key: string; value_json: string }>("SELECT key,value_json FROM user_settings");
    const settings: Record<string, unknown> = {};
    for (const row of rows) {
      try { settings[row.key] = JSON.parse(row.value_json); }
      catch { settings[row.key] = row.value_json; }
    }
    return NextResponse.json({ ok: true, settings });
  } catch (err) {
    console.error("Settings GET error:", err);
    return NextResponse.json({ error: "Failed to load settings" }, { status: 500 });
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    for (const [key, value] of Object.entries(body)) {
      await d1Run(
        `INSERT INTO user_settings(key,value_json,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)
         ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=CURRENT_TIMESTAMP`,
        [key, JSON.stringify(value)],
      );
    }
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("Settings POST error:", err);
    return NextResponse.json({ error: "Failed to save settings" }, { status: 500 });
  }
}
