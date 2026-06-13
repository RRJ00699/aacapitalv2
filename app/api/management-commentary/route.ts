// app/api/management-commentary/route.ts
// Sprint 10 — Management Commentary Engine
// Extracts structured guidance, tone, order book from:
//   Strategy A: Uploaded IR PDF (document extraction)
//   Strategy B: Claude web search (fallback for stocks without IR access)
// Stores in management_commentary table — never re-calls until next quarter

import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";

// ─── Claude API (raw fetch — @anthropic-ai/sdk not installed) ──────────────
const CLAUDE_API = "https://api.anthropic.com/v1/messages";
const CLAUDE_MODEL = "claude-sonnet-4-20250514";

// Current quarter detection
function getCurrentQuarter(): string {
  const now = new Date();
  const month = now.getMonth() + 1;
  const year = now.getFullYear();
  // Indian FY: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar
  const fy = month >= 4 ? year : year - 1;
  const q = month >= 4 && month <= 6 ? "Q1"
    : month >= 7 && month <= 9 ? "Q2"
    : month >= 10 && month <= 12 ? "Q3"
    : "Q4";
  return `${q}FY${String(fy + 1).slice(-2)}`;
}

const EXTRACTION_SYSTEM_PROMPT = `You are a financial analyst specializing in Indian listed companies. 
Your job is to extract structured management commentary data from earnings calls, investor presentations, and IR materials.

Always respond in valid JSON only. No preamble, no markdown, no explanation. 
The JSON must exactly match the schema provided.

Be conservative — only report what is explicitly stated. Do not infer. 
If a field is not mentioned, use null.
For tone, use one of: "BULLISH" | "CAUTIOUSLY_OPTIMISTIC" | "NEUTRAL" | "CAUTIOUS" | "BEARISH"
For guidance_direction, use: "RAISED" | "MAINTAINED" | "LOWERED" | "FIRST_GUIDANCE" | "WITHDRAWN" | "NOT_PROVIDED"`;

const WEB_SEARCH_PROMPT = (symbol: string, companyName: string, quarter: string) =>
  `Search for the latest management commentary for ${companyName} (NSE: ${symbol}) for ${quarter}.

Look for:
1. Earnings call transcript or investor presentation
2. Revenue and margin guidance for next quarter/year
3. Order book size (if applicable — manufacturing, infra, defense)
4. Management tone — are they confident or cautious?
5. Key growth drivers mentioned
6. Key risks acknowledged
7. Any guidance changes vs previous quarter
8. CEO/CFO specific quotes about outlook

After searching, extract and return ONLY this JSON (no other text):
{
  "symbol": "${symbol}",
  "company_name": "${companyName}",
  "quarter": "${quarter}",
  "revenue_guidance": null or string (e.g. "15-18% growth FY27"),
  "margin_guidance": null or string (e.g. "EBITDA 22-24%"),
  "order_book_cr": null or number (crores),
  "order_book_coverage": null or string (e.g. "2.3x FY27 revenue"),
  "management_tone": "BULLISH" | "CAUTIOUSLY_OPTIMISTIC" | "NEUTRAL" | "CAUTIOUS" | "BEARISH",
  "guidance_direction": "RAISED" | "MAINTAINED" | "LOWERED" | "FIRST_GUIDANCE" | "WITHDRAWN" | "NOT_PROVIDED",
  "key_growth_drivers": [] (array of strings, max 4),
  "key_risks": [] (array of strings, max 3),
  "positive_surprises": [] (array of strings, max 3),
  "negative_surprises": [] (array of strings, max 2),
  "mgmt_quality_score": null or number 0-100 (based on specificity, track record, transparency),
  "data_source": "WEB_SEARCH",
  "source_url": null or string (URL if found),
  "confidence": "HIGH" | "MEDIUM" | "LOW" (your confidence in accuracy),
  "extraction_notes": null or string (any caveats)
}`;

async function extractViaWebSearch(
  symbol: string,
  companyName: string,
  quarter: string
): Promise<Record<string, unknown>> {
  const response = await fetch(CLAUDE_API, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": process.env.ANTHROPIC_API_KEY!,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: CLAUDE_MODEL,
      max_tokens: 1000,
      system: EXTRACTION_SYSTEM_PROMPT,
      tools: [
        {
          type: "web_search_20250305",
          name: "web_search",
        },
      ],
      messages: [
        {
          role: "user",
          content: WEB_SEARCH_PROMPT(symbol, companyName, quarter),
        },
      ],
    }),
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Claude API error ${response.status}: ${err}`);
  }

  const data = await response.json();

  // Extract the final text response (after web search tool use)
  let jsonText = "";
  for (const block of data.content ?? []) {
    if (block.type === "text") {
      jsonText = block.text;
      break;
    }
  }

  // Strip markdown fences if present (defensive)
  jsonText = jsonText.replace(/```json|```/g, "").trim();

  try {
    return JSON.parse(jsonText);
  } catch {
    throw new Error(`Claude returned non-JSON: ${jsonText.slice(0, 200)}`);
  }
}

async function extractFromPDF(
  symbol: string,
  companyName: string,
  quarter: string,
  pdfBase64: string
): Promise<Record<string, unknown>> {
  const pdfPrompt = `Extract management commentary from this investor relations document for ${companyName} (${symbol}) - ${quarter}.

Return ONLY this JSON (no other text):
{
  "symbol": "${symbol}",
  "company_name": "${companyName}",
  "quarter": "${quarter}",
  "revenue_guidance": null or string,
  "margin_guidance": null or string,
  "order_book_cr": null or number,
  "order_book_coverage": null or string,
  "management_tone": "BULLISH" | "CAUTIOUSLY_OPTIMISTIC" | "NEUTRAL" | "CAUTIOUS" | "BEARISH",
  "guidance_direction": "RAISED" | "MAINTAINED" | "LOWERED" | "FIRST_GUIDANCE" | "WITHDRAWN" | "NOT_PROVIDED",
  "key_growth_drivers": [],
  "key_risks": [],
  "positive_surprises": [],
  "negative_surprises": [],
  "mgmt_quality_score": null or number 0-100,
  "data_source": "PDF_EXTRACTION",
  "source_url": null,
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "extraction_notes": null or string
}`;

  const response = await fetch(CLAUDE_API, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": process.env.ANTHROPIC_API_KEY!,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: CLAUDE_MODEL,
      max_tokens: 1000,
      system: EXTRACTION_SYSTEM_PROMPT,
      messages: [
        {
          role: "user",
          content: [
            {
              type: "document",
              source: {
                type: "base64",
                media_type: "application/pdf",
                data: pdfBase64,
              },
            },
            { type: "text", text: pdfPrompt },
          ],
        },
      ],
    }),
  });

  if (!response.ok) {
    throw new Error(`Claude PDF extraction failed: ${response.status}`);
  }

  const data = await response.json();
  const jsonText = (data.content?.[0]?.text ?? "")
    .replace(/```json|```/g, "")
    .trim();

  return JSON.parse(jsonText);
}

// ─── GET: Retrieve stored commentary ──────────────────────────────────────
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const symbol = searchParams.get("symbol")?.toUpperCase();
  const quarter = searchParams.get("quarter") ?? getCurrentQuarter();

  if (!symbol) {
    return NextResponse.json({ error: "symbol required" }, { status: 400 });
  }

  const sql = neon(process.env.DATABASE_URL!);

  const rows = await sql`
    SELECT *
    FROM management_commentary
    WHERE nse_symbol = ${symbol}
    ORDER BY quarter DESC
    LIMIT 4
  `;

  if (!rows.length) {
    return NextResponse.json({
      symbol,
      quarter,
      cached: false,
      message: "No commentary yet — POST to extract",
    });
  }

  return NextResponse.json({
    symbol,
    cached: true,
    latest: rows[0],
    history: rows.slice(1),
  });
}

// ─── POST: Extract + store commentary ─────────────────────────────────────
export async function POST(req: NextRequest) {
  const body = await req.json();
  const {
    symbol,
    company_name,
    quarter: reqQuarter,
    pdf_base64, // optional — Strategy A
    force_refresh, // optional — re-extract even if cached
  } = body as {
    symbol: string;
    company_name?: string;
    quarter?: string;
    pdf_base64?: string;
    force_refresh?: boolean;
  };

  if (!symbol) {
    return NextResponse.json({ error: "symbol required" }, { status: 400 });
  }

  const upperSymbol = symbol.toUpperCase();
  const quarter = reqQuarter ?? getCurrentQuarter();
  const sql = neon(process.env.DATABASE_URL!);

  // Check cache — don't re-call Claude if already done this quarter
  if (!force_refresh) {
    const cached = await sql`
      SELECT id, management_tone, guidance_direction, mgmt_quality_score,
             revenue_guidance, order_book_cr, data_source, created_at
      FROM management_commentary
      WHERE nse_symbol = ${upperSymbol} AND quarter = ${quarter}
      LIMIT 1
    `;

    if (cached.length) {
      return NextResponse.json({
        cached: true,
        message: `Already extracted for ${quarter} — use force_refresh=true to re-run`,
        data: cached[0],
      });
    }
  }

  // Look up company name if not provided
  let name = company_name;
  if (!name) {
    const nameRow = await sql`
      SELECT name FROM stock_fundamentals WHERE nse_symbol = ${upperSymbol} LIMIT 1
    `;
    name = nameRow[0]?.name ?? upperSymbol;
  }

  // Extract commentary
  let extracted: Record<string, unknown>;
  let strategy: string;

  try {
    if (pdf_base64) {
      // Strategy A: PDF extraction
      extracted = await extractFromPDF(upperSymbol, name ?? '', quarter, pdf_base64);
      strategy = "PDF_EXTRACTION";
    } else {
      // Strategy B: Web search fallback
      extracted = await extractViaWebSearch(upperSymbol, name ?? '', quarter);
      strategy = "WEB_SEARCH";
    }
  } catch (err) {
    console.error(`Commentary extraction failed for ${upperSymbol}:`, err);
    return NextResponse.json(
      { error: `Extraction failed: ${(err as Error).message}` },
      { status: 500 }
    );
  }

  // Store in DB
  try {
    await sql`
      INSERT INTO management_commentary (
        nse_symbol, company_name, quarter,
        revenue_guidance, margin_guidance,
        order_book_cr, order_book_coverage,
        management_tone, guidance_direction,
        key_growth_drivers, key_risks,
        positive_surprises, negative_surprises,
        mgmt_quality_score,
        data_source, source_url, confidence, extraction_notes,
        created_at, updated_at
      ) VALUES (
        ${upperSymbol},
        ${name},
        ${quarter},
        ${(extracted.revenue_guidance as string) ?? null},
        ${(extracted.margin_guidance as string) ?? null},
        ${(extracted.order_book_cr as number) ?? null},
        ${(extracted.order_book_coverage as string) ?? null},
        ${(extracted.management_tone as string) ?? "NEUTRAL"},
        ${(extracted.guidance_direction as string) ?? "NOT_PROVIDED"},
        ${JSON.stringify(extracted.key_growth_drivers ?? [])},
        ${JSON.stringify(extracted.key_risks ?? [])},
        ${JSON.stringify(extracted.positive_surprises ?? [])},
        ${JSON.stringify(extracted.negative_surprises ?? [])},
        ${(extracted.mgmt_quality_score as number) ?? null},
        ${strategy},
        ${(extracted.source_url as string) ?? null},
        ${(extracted.confidence as string) ?? "LOW"},
        ${(extracted.extraction_notes as string) ?? null},
        NOW(), NOW()
      )
      ON CONFLICT (nse_symbol, quarter) DO UPDATE SET
        revenue_guidance = EXCLUDED.revenue_guidance,
        margin_guidance = EXCLUDED.margin_guidance,
        order_book_cr = EXCLUDED.order_book_cr,
        order_book_coverage = EXCLUDED.order_book_coverage,
        management_tone = EXCLUDED.management_tone,
        guidance_direction = EXCLUDED.guidance_direction,
        key_growth_drivers = EXCLUDED.key_growth_drivers,
        key_risks = EXCLUDED.key_risks,
        positive_surprises = EXCLUDED.positive_surprises,
        negative_surprises = EXCLUDED.negative_surprises,
        mgmt_quality_score = EXCLUDED.mgmt_quality_score,
        data_source = EXCLUDED.data_source,
        source_url = EXCLUDED.source_url,
        confidence = EXCLUDED.confidence,
        extraction_notes = EXCLUDED.extraction_notes,
        updated_at = NOW()
    `;
  } catch (err) {
    console.error("DB insert failed:", err);
    return NextResponse.json(
      { error: "Extracted but DB store failed", extracted },
      { status: 500 }
    );
  }

  return NextResponse.json({
    success: true,
    symbol: upperSymbol,
    quarter,
    strategy,
    data: extracted,
  });
}
