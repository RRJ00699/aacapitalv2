export interface IngestEnv {
  DB: D1DatabaseLike
  D1_INGEST_AUTH_SECRET: string
}

type D1Prepared = {
  bind: (...values: unknown[]) => D1Prepared
  first: <T = Record<string, unknown>>() => Promise<T | null>
  all: <T = Record<string, unknown>>() => Promise<{ results?: T[] }>
  run: () => Promise<unknown>
}

type D1DatabaseLike = {
  prepare: (sql: string) => D1Prepared
}

type Op = { op: string; [key: string]: any }

const MAX_BODY_BYTES = 4_000_000
const MAX_OPS = 2000
const STATUS_RANK: Record<string, number> = {
  ANNOUNCED: 0, UPCOMING: 1, OPEN: 2, CLOSED: 3, ALLOTTED: 4, LISTED: 5, WITHDRAWN: 99,
}

function response(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
  })
}

function bad(error: string, status = 400) { return response({ ok: false, error }, { status }) }
function unauthorized() { return bad("unauthorized", 401) }

function timingSafeEqual(a: string, b: string): boolean {
  const enc = new TextEncoder()
  const aa = enc.encode(a)
  const bb = enc.encode(b)
  let diff = aa.length ^ bb.length
  const max = Math.max(aa.length, bb.length)
  for (let i = 0; i < max; i++) diff |= (aa[i] ?? 0) ^ (bb[i] ?? 0)
  return diff === 0
}

function authenticated(req: Request, env: IngestEnv): boolean {
  const expected = env.D1_INGEST_AUTH_SECRET || ""
  if (!expected) return false
  const auth = req.headers.get("authorization") || ""
  const bearer = auth.toLowerCase().startsWith("bearer ") ? auth.slice(7) : ""
  const header = req.headers.get("x-aac-ingest-key") || ""
  return timingSafeEqual(bearer || header, expected)
}

function iso(value: unknown): string | null {
  if (value == null || value === "") return null
  const d = new Date(String(value))
  return Number.isNaN(d.getTime()) ? String(value) : d.toISOString()
}

function text(value: unknown): string | null {
  return value == null || value === "" ? null : String(value)
}

function integer(value: unknown): number | null {
  if (value == null || value === "") return null
  const n = Number(value)
  return Number.isInteger(n) ? n : null
}

function jsonText(value: unknown): string | null {
  if (value == null) return null
  return typeof value === "string" ? value : JSON.stringify(value)
}

function boolInt(value: unknown): number | null {
  if (value == null) return null
  return value ? 1 : 0
}

async function first<T = Record<string, unknown>>(db: D1DatabaseLike, sql: string, values: unknown[] = []): Promise<T | null> {
  return db.prepare(sql).bind(...values).first<T>()
}

async function all<T = Record<string, unknown>>(db: D1DatabaseLike, sql: string, values: unknown[] = []): Promise<T[]> {
  const out = await db.prepare(sql).bind(...values).all<T>()
  return out.results ?? []
}

async function run(db: D1DatabaseLike, sql: string, values: unknown[] = []): Promise<void> {
  await db.prepare(sql).bind(...values).run()
}

async function readJson(req: Request): Promise<any> {
  const len = Number(req.headers.get("content-length") || 0)
  if (len > MAX_BODY_BYTES) throw new Error("body_too_large")
  const raw = await req.text()
  if (raw.length > MAX_BODY_BYTES) throw new Error("body_too_large")
  return raw ? JSON.parse(raw) : {}
}

async function resolveIdentity(db: D1DatabaseLike, payload: any) {
  const isin = text(payload?.isin)?.trim().toUpperCase() || null
  const nameNorm = text(payload?.name_norm)?.trim() || null
  const byIsin = isin ? await first<any>(db, "SELECT id,isin,name,name_norm,nse_symbol,status FROM ipo WHERE isin=? LIMIT 1", [isin]) : null
  const byName = nameNorm ? await first<any>(db, "SELECT id,isin,name,name_norm,nse_symbol,status FROM ipo WHERE name_norm=? LIMIT 1", [nameNorm]) : null
  if (byIsin && byName && Number(byIsin.id) !== Number(byName.id)) throw new Error("identity_conflict")
  return byIsin || byName || null
}

function advancedStatus(current: string | null, incoming: string | null): string | null {
  if (!incoming) return current
  const next = incoming.toUpperCase()
  if (!(next in STATUS_RANK)) throw new Error("invalid_status")
  if (!current) return next
  const cur = current.toUpperCase()
  if (next === "WITHDRAWN") return next
  if (cur === "WITHDRAWN") return cur
  return (STATUS_RANK[next] ?? -1) >= (STATUS_RANK[cur] ?? -1) ? next : cur
}

async function spineUpsert(db: D1DatabaseLike, op: Op) {
  const name = text(op.name)?.trim()
  const nameNorm = text(op.name_norm)?.trim()
  if (!name || !nameNorm) throw new Error("spine_requires_name_and_name_norm")
  const isin = text(op.isin)?.trim().toUpperCase() || null
  const existing = await resolveIdentity(db, { isin, name_norm: nameNorm })
  if (!existing) {
    await run(db, `INSERT INTO ipo(isin,name,name_norm,nse_symbol,bse_symbol,security_kind,status,discovered_at)
      VALUES(?,?,?,?,?,?,?,?)`, [
      isin, name, nameNorm, text(op.nse_symbol)?.toUpperCase() || null,
      text(op.bse_symbol)?.toUpperCase() || null,
      (text(op.security_kind) || "EQUITY").toUpperCase(),
      (text(op.status) || "ANNOUNCED").toUpperCase(), iso(op.discovered_at) || new Date().toISOString(),
    ])
    const created = await resolveIdentity(db, { isin, name_norm: nameNorm })
    if (!created) throw new Error("spine_insert_not_visible")
    return { ipo_id: Number(created.id), created: true }
  }
  if (isin && existing.isin && String(existing.isin).toUpperCase() !== isin) throw new Error("isin_owner_conflict")
  const status = advancedStatus(text(existing.status), text(op.status))
  await run(db, `UPDATE ipo SET
      isin=COALESCE(isin,?),
      nse_symbol=COALESCE(nse_symbol,?),
      bse_symbol=COALESCE(bse_symbol,?),
      security_kind=COALESCE(?,security_kind),
      status=COALESCE(?,status),
      discovered_at=COALESCE(discovered_at,?)
    WHERE id=?`, [
      isin, text(op.nse_symbol)?.toUpperCase() || null, text(op.bse_symbol)?.toUpperCase() || null,
      text(op.security_kind)?.toUpperCase() || null, status,
      iso(op.discovered_at), Number(existing.id),
    ])
  return { ipo_id: Number(existing.id), created: false }
}

async function issueUpsert(db: D1DatabaseLike, op: Op) {
  const ipoId = integer(op.ipo_id); if (!ipoId) throw new Error("ipo_id_required")
  const f = op.fields || {}
  await run(db, `INSERT INTO ipo_issue(
      ipo_id,open_date,close_date,allotment_date,listing_date,is_book_built,
      band_lo_rs,band_hi_rs,issue_price_rs,face_value_rs,lot_size_shares,
      issue_size_cr,fresh_cr,ofs_cr,market_cap_cr,registrar_name,brlm_json,
      source_name,source_observed_at)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(ipo_id) DO UPDATE SET
      open_date=COALESCE(excluded.open_date,ipo_issue.open_date),
      close_date=COALESCE(excluded.close_date,ipo_issue.close_date),
      allotment_date=COALESCE(excluded.allotment_date,ipo_issue.allotment_date),
      listing_date=COALESCE(excluded.listing_date,ipo_issue.listing_date),
      is_book_built=COALESCE(excluded.is_book_built,ipo_issue.is_book_built),
      band_lo_rs=COALESCE(excluded.band_lo_rs,ipo_issue.band_lo_rs),
      band_hi_rs=COALESCE(excluded.band_hi_rs,ipo_issue.band_hi_rs),
      issue_price_rs=COALESCE(excluded.issue_price_rs,ipo_issue.issue_price_rs),
      face_value_rs=COALESCE(excluded.face_value_rs,ipo_issue.face_value_rs),
      lot_size_shares=COALESCE(excluded.lot_size_shares,ipo_issue.lot_size_shares),
      issue_size_cr=COALESCE(excluded.issue_size_cr,ipo_issue.issue_size_cr),
      fresh_cr=COALESCE(excluded.fresh_cr,ipo_issue.fresh_cr),
      ofs_cr=COALESCE(excluded.ofs_cr,ipo_issue.ofs_cr),
      market_cap_cr=COALESCE(excluded.market_cap_cr,ipo_issue.market_cap_cr),
      registrar_name=COALESCE(excluded.registrar_name,ipo_issue.registrar_name),
      brlm_json=COALESCE(excluded.brlm_json,ipo_issue.brlm_json),
      source_name=COALESCE(excluded.source_name,ipo_issue.source_name),
      source_observed_at=COALESCE(excluded.source_observed_at,ipo_issue.source_observed_at)`, [
      ipoId, text(f.open_date), text(f.close_date), text(f.allotment_date), text(f.listing_date),
      f.is_book_built == null ? 1 : boolInt(f.is_book_built),
      text(f.band_lo_rs), text(f.band_hi_rs), text(f.issue_price_rs), text(f.face_value_rs),
      integer(f.lot_size_shares), text(f.issue_size_cr), text(f.fresh_cr), text(f.ofs_cr),
      text(f.market_cap_cr), text(f.registrar_name), jsonText(f.brlm_json),
      text(op.source_name) || "pipeline", iso(op.observed_at) || new Date().toISOString(),
    ])
  return { ipo_id: ipoId }
}

async function documentUpsert(db: D1DatabaseLike, op: Op) {
  const sha = text(op.sha256)?.toLowerCase(); const ipoId = integer(op.ipo_id)
  if (!sha || sha.length !== 64 || !ipoId || !text(op.doc_type)) throw new Error("invalid_document")
  const old = await first<any>(db, "SELECT ipo_id,doc_type,r2_key,size_bytes FROM documents WHERE sha256=?", [sha])
  if (old && (Number(old.ipo_id) !== ipoId || String(old.doc_type) !== String(op.doc_type))) throw new Error("document_owner_conflict")
  await run(db, `INSERT INTO documents(sha256,ipo_id,doc_type,source_url,size_bytes,page_count,r2_key,fetched_at)
    VALUES(?,?,?,?,?,?,?,?)
    ON CONFLICT(sha256) DO UPDATE SET
      source_url=COALESCE(documents.source_url,excluded.source_url),
      size_bytes=COALESCE(documents.size_bytes,excluded.size_bytes),
      page_count=COALESCE(documents.page_count,excluded.page_count),
      r2_key=COALESCE(documents.r2_key,excluded.r2_key),
      fetched_at=COALESCE(documents.fetched_at,excluded.fetched_at)`, [
      sha, ipoId, text(op.doc_type), text(op.source_url), integer(op.size_bytes), integer(op.page_count),
      text(op.r2_key), iso(op.fetched_at) || new Date().toISOString(),
    ])
  return { sha256: sha }
}

async function executeOp(db: D1DatabaseLike, op: Op): Promise<any> {
  switch (op.op) {
    case "spine_upsert": return spineUpsert(db, op)
    case "issue_upsert": return issueUpsert(db, op)
    case "document_upsert": return documentUpsert(db, op)
    case "company_profile_upsert": {
      const id = integer(op.ipo_id); if (!id) throw new Error("ipo_id_required")
      await run(db, `INSERT INTO company_profile(ipo_id,business_description,sector,industry,incorporated_date,registered_office,website,promoters_json)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(ipo_id) DO UPDATE SET
        business_description=COALESCE(excluded.business_description,company_profile.business_description),
        sector=COALESCE(excluded.sector,company_profile.sector),industry=COALESCE(excluded.industry,company_profile.industry),
        incorporated_date=COALESCE(excluded.incorporated_date,company_profile.incorporated_date),
        registered_office=COALESCE(excluded.registered_office,company_profile.registered_office),
        website=COALESCE(excluded.website,company_profile.website),promoters_json=COALESCE(excluded.promoters_json,company_profile.promoters_json)`, [
        id,text(op.business_description),text(op.sector),text(op.industry),text(op.incorporated_date),text(op.registered_office),text(op.website),jsonText(op.promoters_json)])
      return { ipo_id: id }
    }
    case "financial_upsert": {
      const id = integer(op.ipo_id); if (!id || !text(op.period) || !text(op.basis)) throw new Error("invalid_financial")
      await run(db, `INSERT INTO financial_statements(ipo_id,period,basis,revenue_cr,total_income_cr,ebitda_cr,pat_cr,net_worth_cr,reserves_cr,debt_cr,assets_cr,cash_cr,document_sha256,page)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ipo_id,period,basis) DO UPDATE SET
        revenue_cr=COALESCE(excluded.revenue_cr,financial_statements.revenue_cr),total_income_cr=COALESCE(excluded.total_income_cr,financial_statements.total_income_cr),
        ebitda_cr=COALESCE(excluded.ebitda_cr,financial_statements.ebitda_cr),pat_cr=COALESCE(excluded.pat_cr,financial_statements.pat_cr),
        net_worth_cr=COALESCE(excluded.net_worth_cr,financial_statements.net_worth_cr),reserves_cr=COALESCE(excluded.reserves_cr,financial_statements.reserves_cr),
        debt_cr=COALESCE(excluded.debt_cr,financial_statements.debt_cr),assets_cr=COALESCE(excluded.assets_cr,financial_statements.assets_cr),
        cash_cr=COALESCE(excluded.cash_cr,financial_statements.cash_cr),document_sha256=COALESCE(excluded.document_sha256,financial_statements.document_sha256),
        page=COALESCE(excluded.page,financial_statements.page)`, [
        id,text(op.period),text(op.basis),text(op.revenue_cr),text(op.total_income_cr),text(op.ebitda_cr),text(op.pat_cr),text(op.net_worth_cr),
        text(op.reserves_cr),text(op.debt_cr),text(op.assets_cr),text(op.cash_cr),text(op.document_sha256),integer(op.page)])
      return { ipo_id: id, period: op.period }
    }
    case "object_upsert": {
      const id = integer(op.ipo_id); if (!id || integer(op.row_order) == null || !text(op.purpose_raw)) throw new Error("invalid_object")
      await run(db, `INSERT INTO objects_of_issue(ipo_id,row_order,purpose_code,purpose_raw,amount_cr,document_sha256,page)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(ipo_id,row_order,document_sha256) DO UPDATE SET
        purpose_code=COALESCE(excluded.purpose_code,objects_of_issue.purpose_code),amount_cr=COALESCE(excluded.amount_cr,objects_of_issue.amount_cr),page=COALESCE(excluded.page,objects_of_issue.page)`,
        [id,integer(op.row_order),text(op.purpose_code),text(op.purpose_raw),text(op.amount_cr),text(op.document_sha256),integer(op.page)])
      return { ipo_id: id }
    }
    case "peer_upsert": {
      const id = integer(op.ipo_id); if (!id || !text(op.peer_name_raw)) throw new Error("invalid_peer")
      await run(db, `INSERT INTO peer_comparisons(ipo_id,peer_name_raw,eps_rs,pe_x,pb_x,roe_pct,ronw_pct,market_cap_cr,as_of_date,document_sha256,page)
        VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ipo_id,peer_name_raw,as_of_date,document_sha256) DO UPDATE SET
        eps_rs=COALESCE(excluded.eps_rs,peer_comparisons.eps_rs),pe_x=COALESCE(excluded.pe_x,peer_comparisons.pe_x),pb_x=COALESCE(excluded.pb_x,peer_comparisons.pb_x),
        roe_pct=COALESCE(excluded.roe_pct,peer_comparisons.roe_pct),ronw_pct=COALESCE(excluded.ronw_pct,peer_comparisons.ronw_pct),market_cap_cr=COALESCE(excluded.market_cap_cr,peer_comparisons.market_cap_cr),page=COALESCE(excluded.page,peer_comparisons.page)`,
        [id,text(op.peer_name_raw),text(op.eps_rs),text(op.pe_x),text(op.pb_x),text(op.roe_pct),text(op.ronw_pct),text(op.market_cap_cr),text(op.as_of_date),text(op.document_sha256),integer(op.page)])
      return { ipo_id: id }
    }
    case "source_fact_insert": {
      await run(db, `INSERT INTO source_facts(ipo_id,target_table,target_field,raw_value,normalized_value,unit,source_name,document_sha256,raw_object_sha256,observed_at,parser_version,confidence,observation_fingerprint)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(observation_fingerprint) DO NOTHING`, [
        integer(op.ipo_id),text(op.target_table)||"source_facts",text(op.target_field)||"unknown",text(op.raw_value),text(op.normalized_value),text(op.unit),
        text(op.source_name)||"pipeline",text(op.document_sha256),text(op.raw_object_sha256),iso(op.observed_at)||new Date().toISOString(),text(op.parser_version)||"d1-pipeline-v1",text(op.confidence),text(op.observation_fingerprint)])
      return { fingerprint: op.observation_fingerprint }
    }
    case "research_finding_insert": {
      const id = integer(op.ipo_id); if (!id || !text(op.document_sha256) || !text(op.content_fingerprint)) throw new Error("invalid_finding")
      await run(db, `INSERT INTO research_findings(ipo_id,category,finding_text,direction,document_sha256,page,evidence_excerpt,model,prompt_version,confidence,content_fingerprint)
        VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(content_fingerprint) DO NOTHING`, [
        id,text(op.category)||"research",text(op.finding_text)||"",text(op.direction),text(op.document_sha256),integer(op.page),text(op.evidence_excerpt)||"",text(op.model),text(op.prompt_version),text(op.confidence),text(op.content_fingerprint)])
      return { fingerprint: op.content_fingerprint }
    }
    case "extraction_run_insert": {
      await run(db, `INSERT INTO extraction_runs(ipo_id,document_sha256,source_type,model,prompt_version,extracted_at,status,input_tokens,output_tokens,cost_usd,output_json,extraction_fingerprint)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(document_sha256,model,prompt_version) DO NOTHING`, [
        integer(op.ipo_id),text(op.document_sha256),text(op.source_type)?.toUpperCase(),text(op.model),text(op.prompt_version),iso(op.extracted_at)||new Date().toISOString(),
        text(op.status)||"EXTRACTED",integer(op.input_tokens),integer(op.output_tokens),text(op.cost_usd),jsonText(op.output_json)||"{}",text(op.extraction_fingerprint)])
      return { fingerprint: op.extraction_fingerprint }
    }
    case "reservation_upsert": {
      await run(db, `INSERT INTO reservations(ipo_id,category,shares_reserved,reservation_pct,source_observed_at) VALUES(?,?,?,?,?)
        ON CONFLICT(ipo_id,category) DO UPDATE SET shares_reserved=COALESCE(excluded.shares_reserved,reservations.shares_reserved),reservation_pct=COALESCE(excluded.reservation_pct,reservations.reservation_pct),source_observed_at=excluded.source_observed_at`,
        [integer(op.ipo_id),text(op.category),integer(op.shares_reserved),text(op.reservation_pct),iso(op.source_observed_at)||new Date().toISOString()])
      return { category: op.category }
    }
    case "subscription_insert": {
      await run(db, `INSERT INTO subscription_snapshots(ipo_id,captured_at,category,shares_reserved,shares_bid,subscription_x,is_final,observation_fingerprint)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(observation_fingerprint) DO NOTHING`, [
        integer(op.ipo_id),iso(op.captured_at)||new Date().toISOString(),text(op.category),integer(op.shares_reserved),integer(op.shares_bid),text(op.subscription_x),boolInt(op.is_final)??0,text(op.observation_fingerprint)])
      return { fingerprint: op.observation_fingerprint }
    }
    case "anchor_summary_upsert": {
      await run(db, `INSERT INTO anchor_summary(ipo_id,shares,amount_cr,investor_count,allocation_pct,document_sha256,observed_at) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(ipo_id) DO UPDATE SET shares=COALESCE(excluded.shares,anchor_summary.shares),amount_cr=COALESCE(excluded.amount_cr,anchor_summary.amount_cr),investor_count=COALESCE(excluded.investor_count,anchor_summary.investor_count),allocation_pct=COALESCE(excluded.allocation_pct,anchor_summary.allocation_pct),document_sha256=excluded.document_sha256,observed_at=excluded.observed_at`,
        [integer(op.ipo_id),integer(op.shares),text(op.amount_cr),integer(op.investor_count),text(op.allocation_pct),text(op.document_sha256),iso(op.observed_at)||new Date().toISOString()])
      return { ipo_id: op.ipo_id }
    }
    case "anchor_allocation_insert": {
      await run(db, `INSERT INTO anchor_allocations(ipo_id,allocation_row,investor_name_raw,shares,price_rs,amount_cr,allocation_pct,document_sha256,page,derived_class)
        VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(document_sha256,allocation_row) DO NOTHING`, [
        integer(op.ipo_id),integer(op.allocation_row),text(op.investor_name_raw),integer(op.shares),text(op.price_rs),text(op.amount_cr),text(op.allocation_pct),text(op.document_sha256),integer(op.page),text(op.derived_class)])
      return { row: op.allocation_row }
    }
    case "listing_observation_insert": {
      await run(db, `INSERT INTO listing_observations(ipo_id,observation_type,observed_at,price_rs,buy_qty_shares,sell_qty_shares,ieq_shares,payload_json,source_name,content_fingerprint)
        VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(content_fingerprint) DO NOTHING`, [
        integer(op.ipo_id),text(op.observation_type),iso(op.observed_at)||new Date().toISOString(),text(op.price_rs),integer(op.buy_qty_shares),integer(op.sell_qty_shares),integer(op.ieq_shares),jsonText(op.payload_json),text(op.source_name)||"pipeline",text(op.content_fingerprint)])
      return { fingerprint: op.content_fingerprint }
    }
    case "market_bar_upsert": {
      await run(db, `INSERT INTO market_bars(ipo_id,interval,ts,open_rs,high_rs,low_rs,close_rs,volume_shares,source_name,content_fingerprint)
        VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ipo_id,interval,ts) DO UPDATE SET open_rs=excluded.open_rs,high_rs=excluded.high_rs,low_rs=excluded.low_rs,close_rs=excluded.close_rs,volume_shares=excluded.volume_shares,source_name=excluded.source_name,content_fingerprint=excluded.content_fingerprint`, [
        integer(op.ipo_id),text(op.interval),iso(op.ts)||text(op.ts),text(op.open_rs),text(op.high_rs),text(op.low_rs),text(op.close_rs),integer(op.volume_shares),text(op.source_name)||"kite",text(op.content_fingerprint)])
      return { ipo_id: op.ipo_id, ts: op.ts }
    }
    case "gmp_insert": {
      await run(db, `INSERT INTO gmp_observations(ipo_id,observed_at,gmp_rs,gmp_pct,source_name,is_official,observation_fingerprint)
        VALUES(?,?,?,?,?,0,?) ON CONFLICT(observation_fingerprint) DO NOTHING`, [integer(op.ipo_id),iso(op.observed_at)||new Date().toISOString(),text(op.gmp_rs),text(op.gmp_pct),text(op.source_name)||"street",text(op.observation_fingerprint)])
      return { fingerprint: op.observation_fingerprint }
    }
    case "news_upsert": {
      const url = text(op.url); if (!url) throw new Error("news_url_required")
      const old = await first<any>(db,"SELECT id FROM ipo_news WHERE url=? LIMIT 1",[url])
      if (!old) await run(db,`INSERT INTO ipo_news(company_name,nse_symbol,publisher,headline,url,published_at,snippet,selection_score,source,fetch_status,is_current,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)`,[text(op.company_name),text(op.nse_symbol),text(op.publisher),text(op.headline),url,iso(op.published_at)||text(op.published_at),text(op.snippet),integer(op.selection_score),text(op.source),text(op.fetch_status)||"ok",op.is_current==null?1:boolInt(op.is_current),new Date().toISOString()])
      return { url, created: !old }
    }
    case "valuation_insert": {
      await run(db, `INSERT INTO valuation_runs(ipo_id,calculated_at,engine_version,inputs_json,ratios_json,peer_median_pe_x,fair_value_lo_rs,fair_value_hi_rs,margin_of_safety_pct,missing_inputs_json,run_fingerprint)
        VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(run_fingerprint) DO NOTHING`, [
        integer(op.ipo_id),iso(op.calculated_at)||new Date().toISOString(),text(op.engine_version),jsonText(op.inputs_json)||"{}",jsonText(op.ratios_json),text(op.peer_median_pe_x),text(op.fair_value_lo_rs),text(op.fair_value_hi_rs),text(op.margin_of_safety_pct),jsonText(op.missing_inputs_json),text(op.run_fingerprint)])
      return { fingerprint: op.run_fingerprint }
    }
    case "proforma_insert": {
      await run(db, `INSERT INTO proforma_runs(ipo_id,calculated_at,engine_version,inputs_json,outputs_json,missing_inputs_json,run_fingerprint)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(run_fingerprint) DO NOTHING`, [integer(op.ipo_id),iso(op.calculated_at)||new Date().toISOString(),text(op.engine_version),jsonText(op.inputs_json)||"{}",jsonText(op.outputs_json)||"{}",jsonText(op.missing_inputs_json),text(op.run_fingerprint)])
      return { fingerprint: op.run_fingerprint }
    }
    case "street_summary_upsert": {
      await run(db, `INSERT INTO street_summary(ipo_id,calculated_at,positive_count,neutral_count,negative_count,summary_json,source_fingerprint)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(ipo_id) DO UPDATE SET calculated_at=excluded.calculated_at,positive_count=excluded.positive_count,neutral_count=excluded.neutral_count,negative_count=excluded.negative_count,summary_json=excluded.summary_json,source_fingerprint=excluded.source_fingerprint`, [integer(op.ipo_id),iso(op.calculated_at)||new Date().toISOString(),integer(op.positive_count)||0,integer(op.neutral_count)||0,integer(op.negative_count)||0,jsonText(op.summary_json)||"{}",text(op.source_fingerprint)])
      return { ipo_id: op.ipo_id }
    }
    case "pipeline_run_start": {
      await run(db, `INSERT INTO pipeline_runs(id,started_at,mode,status,orchestrator_version,selected_ipos,paid_cost_usd,summary_json)
        VALUES(?,?,?,'running',?,?,?,?) ON CONFLICT(id) DO NOTHING`, [text(op.run_id),iso(op.started_at)||new Date().toISOString(),text(op.mode)||"live",text(op.orchestrator_version)||"d1-cron-v1",integer(op.selected_ipos)||0,text(op.paid_cost_usd)||"0",jsonText(op.summary_json)])
      return { run_id: op.run_id }
    }
    case "pipeline_run_finish": {
      await run(db, `UPDATE pipeline_runs SET finished_at=?,status=?,selected_ipos=COALESCE(?,selected_ipos),paid_cost_usd=COALESCE(?,paid_cost_usd),summary_json=COALESCE(?,summary_json) WHERE id=?`, [iso(op.finished_at)||new Date().toISOString(),text(op.status)||"ok",integer(op.selected_ipos),text(op.paid_cost_usd),jsonText(op.summary_json),text(op.run_id)])
      return { run_id: op.run_id }
    }
    case "pipeline_event": {
      await run(db, `INSERT INTO pipeline_events(run_id,lane,ipo_id,started_at,finished_at,status,counts_json,detail_json,event_fingerprint)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(event_fingerprint) DO NOTHING`, [text(op.run_id),text(op.lane),integer(op.ipo_id),iso(op.started_at)||new Date().toISOString(),iso(op.finished_at),text(op.status)||"ok",jsonText(op.counts_json),jsonText(op.detail_json),text(op.event_fingerprint)])
      return { fingerprint: op.event_fingerprint }
    }
    default: throw new Error(`unsupported_op:${op.op}`)
  }
}

async function handleBatch(db: D1DatabaseLike, payload: any) {
  const ops = Array.isArray(payload?.ops) ? payload.ops : []
  if (!ops.length) throw new Error("ops_required")
  if (ops.length > MAX_OPS) throw new Error("too_many_ops")
  const results = []
  for (let i = 0; i < ops.length; i++) {
    try {
      results.push({ index: i, ok: true, result: await executeOp(db, ops[i]) })
    } catch (error) {
      results.push({ index: i, ok: false, error: error instanceof Error ? error.message : String(error) })
      if (payload?.fail_fast !== false) break
    }
  }
  const failed = results.filter((r) => !r.ok)
  return { ok: failed.length === 0, results, failed: failed.length }
}

async function stateActive(db: D1DatabaseLike, payload: any) {
  const limit = Math.max(1, Math.min(100, Number(payload?.limit || 20)))
  const lookback = Math.max(1, Math.min(365, Number(payload?.lookback_days || 100)))
  return all(db, `SELECT i.id,i.isin,i.name,i.name_norm,i.nse_symbol,i.status,i.security_kind,
      ii.open_date,ii.close_date,ii.allotment_date,ii.listing_date,ii.lock30_date,
      ii.band_lo_rs,ii.band_hi_rs,ii.issue_price_rs,ii.face_value_rs,ii.lot_size_shares,
      ii.issue_size_cr,ii.fresh_cr,ii.ofs_cr,ii.market_cap_cr
    FROM ipo i LEFT JOIN ipo_issue ii ON ii.ipo_id=i.id
    WHERE i.security_kind='EQUITY' AND i.status<>'WITHDRAWN'
      AND (ii.listing_date IS NULL OR ii.listing_date >= date('now', '-' || ? || ' days')
           OR ii.open_date >= date('now','-30 days') OR ii.close_date >= date('now','-30 days'))
    ORDER BY CASE WHEN ii.listing_date IS NULL THEN 0 ELSE 1 END, COALESCE(ii.open_date,ii.listing_date) DESC, i.id DESC
    LIMIT ?`, [lookback, limit])
}

async function stateListingToday(db: D1DatabaseLike, payload: any) {
  const day = text(payload?.day) || new Date().toISOString().slice(0,10)
  const limit = Math.max(1, Math.min(20, Number(payload?.limit || 10)))
  return all(db, `SELECT i.id,i.isin,i.name,i.name_norm,i.nse_symbol,ii.listing_date,ii.issue_size_cr
    FROM ipo i JOIN ipo_issue ii ON ii.ipo_id=i.id
    WHERE ii.listing_date=? AND i.isin IS NOT NULL AND i.nse_symbol IS NOT NULL
      AND i.security_kind='EQUITY' AND i.status<>'WITHDRAWN'
    ORDER BY CAST(COALESCE(ii.issue_size_cr,'0') AS NUMERIC) DESC,i.id LIMIT ?`, [day, limit])
}

async function stateMarket(db: D1DatabaseLike, payload: any) {
  const limit = Math.max(1, Math.min(100, Number(payload?.limit || 30)))
  return all(db, `SELECT i.id,i.isin,i.name,i.nse_symbol,ii.listing_date,ii.lock30_date,ii.issue_price_rs
    FROM ipo i JOIN ipo_issue ii ON ii.ipo_id=i.id
    WHERE i.security_kind='EQUITY' AND i.nse_symbol IS NOT NULL AND ii.listing_date IS NOT NULL
      AND date('now') BETWEEN date(ii.listing_date) AND date(COALESCE(ii.lock30_date,date(ii.listing_date,'+30 days')))
    ORDER BY ii.listing_date DESC,i.id LIMIT ?`, [limit])
}

async function jobsClaim(db: D1DatabaseLike) {
  const row = await first<any>(db, `SELECT id,job FROM job_runs WHERE status='queued' ORDER BY requested_at LIMIT 1`)
  if (!row) return null
  await run(db, `UPDATE job_runs SET status='running',started_at=CURRENT_TIMESTAMP WHERE id=? AND status='queued'`, [Number(row.id)])
  return first<any>(db, `SELECT id,job,status FROM job_runs WHERE id=?`, [Number(row.id)])
}

async function jobsFinish(db: D1DatabaseLike, payload: any) {
  const id = integer(payload?.id); if (!id) throw new Error("job_id_required")
  const status = text(payload?.status)
  if (!status || !["done","failed","cancelled"].includes(status)) throw new Error("invalid_job_status")
  await run(db, `UPDATE job_runs SET status=?,finished_at=CURRENT_TIMESTAMP,exit_code=?,error=?,log_tail=? WHERE id=?`, [status,integer(payload?.exit_code),text(payload?.error),text(payload?.log_tail),id])
  return { id, status }
}

export async function handleIngestRequest(req: Request, env: IngestEnv): Promise<Response> {
  const url = new URL(req.url)
  if (!authenticated(req, env)) return unauthorized()
  if (url.pathname === "/health" && req.method === "GET") {
    const row = await first<any>(env.DB, "SELECT COUNT(*) AS n FROM ipo")
    return response({ ok: true, service: "aacapital-d1-ingest", ipo_rows: Number(row?.n || 0) })
  }
  if (req.method !== "POST") return bad("unsupported_method", 405)
  let payload: any
  try { payload = await readJson(req) } catch (error) { return bad(error instanceof Error ? error.message : "invalid_json", 400) }
  try {
    if (url.pathname === "/v1/identity/resolve") return response({ ok: true, row: await resolveIdentity(env.DB, payload) })
    if (url.pathname === "/v1/state/active") return response({ ok: true, rows: await stateActive(env.DB, payload) })
    if (url.pathname === "/v1/state/listing-today") return response({ ok: true, rows: await stateListingToday(env.DB, payload) })
    if (url.pathname === "/v1/state/market") return response({ ok: true, rows: await stateMarket(env.DB, payload) })
    if (url.pathname === "/v1/ingest/batch") {
      const result = await handleBatch(env.DB, payload)
      return response(result, { status: result.ok ? 200 : 409 })
    }
    if (url.pathname === "/v1/jobs/claim") return response({ ok: true, job: await jobsClaim(env.DB) })
    if (url.pathname === "/v1/jobs/finish") return response({ ok: true, result: await jobsFinish(env.DB, payload) })
    return bad("unsupported_endpoint", 404)
  } catch (error) {
    return bad(error instanceof Error ? error.message : String(error), 409)
  }
}

export default { fetch: handleIngestRequest }
