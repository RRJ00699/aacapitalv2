import { handleIngestRequest } from "./index"

interface Env {
  DB: { prepare(sql: string): { bind(...v: unknown[]): any; first<T = any>(): Promise<T | null> } }
  D1_INGEST_AUTH_SECRET: string
}

function timingSafeEqual(a: string, b: string): boolean {
  const enc = new TextEncoder(); const aa = enc.encode(a); const bb = enc.encode(b)
  let diff = aa.length ^ bb.length; const max = Math.max(aa.length, bb.length)
  for (let i = 0; i < max; i++) diff |= (aa[i] ?? 0) ^ (bb[i] ?? 0)
  return diff === 0
}

function authenticated(req: Request, env: Env): boolean {
  const expected = env.D1_INGEST_AUTH_SECRET || ""
  const auth = req.headers.get("authorization") || ""
  const bearer = auth.toLowerCase().startsWith("bearer ") ? auth.slice(7) : ""
  const header = req.headers.get("x-aac-ingest-key") || ""
  return !!expected && timingSafeEqual(bearer || header, expected)
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })
}

async function extractionGuard(req: Request, env: Env): Promise<Response> {
  if (!authenticated(req, env)) return json({ ok: false, error: "unauthorized" }, 401)
  let p: any
  try { p = await req.json() } catch { return json({ ok: false, error: "invalid_json" }, 400) }
  const sha = String(p?.document_sha256 || "").toLowerCase()
  const model = String(p?.model || "")
  const prompt = String(p?.prompt_version || "")
  if (!/^[0-9a-f]{64}$/.test(sha) || !model || !prompt) return json({ ok: false, error: "invalid_guard_key" }, 400)
  const row = await env.DB.prepare(
    `SELECT id,ipo_id,source_type,status,extracted_at,input_tokens,output_tokens,cost_usd
       FROM extraction_runs
      WHERE document_sha256=? AND model=? AND prompt_version=? LIMIT 1`
  ).bind(sha, model, prompt).first<any>()
  return json({ ok: true, extracted: !!row, row: row ?? null })
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url)
    if (url.pathname === "/v1/state/extraction" && req.method === "POST") {
      return extractionGuard(req, env)
    }
    return handleIngestRequest(req, env as any)
  },
}
