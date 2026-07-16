// app/api/admin/diagnostics/route.ts — phone-first, WHITELISTED, READ-ONLY
// diagnostics. Rakesh runs these from Settings without a SQL console (Neon has
// no mobile app). Every query is fixed — no user SQL ever reaches this route.
// Each check is individually try/caught: a missing table/column reports itself
// as text instead of failing the panel (the #159 lesson, applied defensively).
import { NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
export const dynamic = "force-dynamic";

const CANON = String.raw`(ltd|limited|pvt|private|ipo|and|&)|[^a-z0-9]`;

export async function GET(req: Request) {
  const check = new URL(req.url).searchParams.get("check") ?? "";
  const sql = neon(process.env.DATABASE_URL!);
  try {
    let rows: unknown[] = [];
    switch (check) {
      case "pipeline_failures":
        rows = await sql`SELECT step, LEFT(stderr_tail,160) AS error, failed_at
          FROM pipeline_failures WHERE failed_at > NOW() - interval '7 days'
          ORDER BY failed_at DESC LIMIT 20`;
        break;
      case "rhp_status":
        rows = await sql`SELECT i.company_name,
            (ri.company_name IS NOT NULL) AS has_rhp,
            COALESCE(ri.full_json->>'verdict', ri.full_json->'aacapital_decision'->>'verdict') AS verdict
          FROM ipo_intelligence i
          LEFT JOIN ipo_rhp_intel ri ON regexp_replace(lower(ri.company_name), ${CANON}, '', 'g')
                                      = regexp_replace(lower(i.company_name),  ${CANON}, '', 'g')
          WHERE i.listing_date >= CURRENT_DATE - 7
          ORDER BY i.listing_date NULLS LAST LIMIT 25`;
        break;
      case "sbi_notes":
        rows = await sql`SELECT company, source, rating,
            (pdf_path IS NOT NULL) AS has_pdf, parsed_at
          FROM ipo_research_notes ORDER BY parsed_at DESC NULLS LAST LIMIT 20`;
        break;
      case "twin_census":
        rows = await sql`SELECT regexp_replace(lower(company_name), ${CANON}, '', 'g') AS canon,
            COUNT(*) AS n, array_agg(company_name) AS names
          FROM ipo_intelligence GROUP BY 1 HAVING COUNT(*) > 1`;
        break;
      case "kite_session":
        rows = await sql`SELECT user_id, created_at, expires_at,
            (expires_at > NOW()) AS valid
          FROM kite_session ORDER BY created_at DESC LIMIT 3`;
        break;
      case "rhp_run_log":
        rows = await sql`SELECT * FROM rhp_run_log ORDER BY 1 DESC LIMIT 5`;
        break;
      case "preopen_book":
        rows = await sql`SELECT symbol, COUNT(*) AS polls,
            MIN(captured_at) AS first, MAX(captured_at) AS last,
            MAX(lean_pct) AS max_lean, MIN(lean_pct) AS min_lean
          FROM ipo_preopen_book GROUP BY symbol ORDER BY MAX(captured_at) DESC LIMIT 10`;
        break;
      case "eps_coverage":
        rows = await sql`SELECT COALESCE(eps_source,'(pre-existing)') AS source, COUNT(*) AS n
          FROM ipo_intelligence WHERE eps_post IS NOT NULL GROUP BY 1 ORDER BY 2 DESC`;
        break;
      default:
        return NextResponse.json({ ok: false, error: "unknown check" }, { status: 400 });
    }
    return NextResponse.json({ ok: true, check, rows,
      ranAt: new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) + " IST" });
  } catch (e: unknown) {
    return NextResponse.json({ ok: true, check,
      rows: [{ note: e instanceof Error ? e.message.slice(0, 180) : "query failed" }] });
  }
}
