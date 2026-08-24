import { handleIngestRequest } from "./index"

interface Prepared {
  bind(...v: unknown[]): Prepared
  first<T = any>(): Promise<T | null>
  all<T = any>(): Promise<{ results?: T[] }>
}
interface Env {
  DB: { prepare(sql: string): Prepared }
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
async function payload(req: Request) { try { return await req.json() as any } catch { return null } }
async function rows<T=any>(env:Env,sql:string,values:unknown[]=[]):Promise<T[]> {
  const out=await env.DB.prepare(sql).bind(...values).all<T>();return out.results??[]
}

async function extractionGuard(req: Request, env: Env): Promise<Response> {
  if (!authenticated(req, env)) return json({ ok: false, error: "unauthorized" }, 401)
  const p=await payload(req); if(!p)return json({ok:false,error:"invalid_json"},400)
  const sha = String(p?.document_sha256 || "").toLowerCase()
  const model = String(p?.model || ""); const prompt = String(p?.prompt_version || "")
  if (!/^[0-9a-f]{64}$/.test(sha) || !model || !prompt) return json({ ok: false, error: "invalid_guard_key" }, 400)
  const row = await env.DB.prepare(
    `SELECT id,ipo_id,source_type,status,extracted_at,input_tokens,output_tokens,cost_usd
       FROM extraction_runs WHERE document_sha256=? AND model=? AND prompt_version=? LIMIT 1`
  ).bind(sha, model, prompt).first<any>()
  return json({ ok: true, extracted: !!row, row: row ?? null })
}

async function valuationInputs(req:Request,env:Env):Promise<Response>{
  if(!authenticated(req,env))return json({ok:false,error:"unauthorized"},401)
  const p=await payload(req);if(!p)return json({ok:false,error:"invalid_json"},400)
  const ipoId=Number(p.ipo_id);if(!Number.isInteger(ipoId)||ipoId<=0)return json({ok:false,error:"invalid_ipo_id"},400)
  const issue=await env.DB.prepare(`SELECT i.id,i.isin,i.name,i.nse_symbol,i.status,
      ii.band_lo_rs,ii.band_hi_rs,ii.issue_price_rs,ii.face_value_rs,ii.issue_size_cr,ii.fresh_cr,ii.ofs_cr,ii.market_cap_cr,ii.listing_date
      FROM ipo i LEFT JOIN ipo_issue ii ON ii.ipo_id=i.id WHERE i.id=?`).bind(ipoId).first<any>()
  if(!issue)return json({ok:false,error:"ipo_not_found"},404)
  const financials=await rows(env,`SELECT period,basis,revenue_cr,total_income_cr,ebitda_cr,pat_cr,net_worth_cr,debt_cr,assets_cr,cash_cr,document_sha256,page
      FROM financial_statements WHERE ipo_id=? ORDER BY period DESC`,[ipoId])
  const facts=await rows(env,`SELECT target_field,normalized_value,raw_value,unit,source_name,document_sha256,observed_at,confidence
      FROM source_facts WHERE ipo_id=? ORDER BY observed_at DESC,id DESC`,[ipoId])
  const peers=await rows(env,`SELECT peer_name_raw,eps_rs,pe_x,pb_x,roe_pct,ronw_pct,market_cap_cr,as_of_date,document_sha256,page
      FROM peer_comparisons WHERE ipo_id=? ORDER BY peer_name_raw`,[ipoId])
  const gmp=await env.DB.prepare(`SELECT observed_at,gmp_rs,gmp_pct,source_name FROM gmp_observations WHERE ipo_id=? ORDER BY observed_at DESC LIMIT 1`).bind(ipoId).first<any>()
  const sbi=await rows(env,`SELECT category,finding_text,direction,page,evidence_excerpt,model,prompt_version,confidence
      FROM research_findings WHERE ipo_id=? ORDER BY id DESC LIMIT 30`,[ipoId])
  const news=await rows(env,`SELECT publisher,headline,url,published_at,snippet,selection_score,source FROM ipo_news
      WHERE (nse_symbol=? OR lower(company_name)=lower(?)) AND COALESCE(is_current,1)=1 ORDER BY published_at DESC LIMIT 20`,[issue.nse_symbol,issue.name])
  return json({ok:true,issue,financials,facts,peers,gmp,sbi,news})
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url)
    if (url.pathname === "/v1/state/extraction" && req.method === "POST") return extractionGuard(req, env)
    if (url.pathname === "/v1/state/valuation-inputs" && req.method === "POST") return valuationInputs(req,env)
    return handleIngestRequest(req, env as any)
  },
}
