import { NextRequest, NextResponse } from "next/server";
import { Pool } from "pg";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const connectionString =
  process.env.DATABASE_URL ||
  process.env.NEON_DATABASE_URL ||
  process.env.POSTGRES_URL ||
  process.env.POSTGRES_PRISMA_URL;

if (!connectionString) throw new Error("Missing database connection string");

const globalForIpo = globalThis as unknown as { ipoPredictionsPool?: Pool };

const pool =
  globalForIpo.ipoPredictionsPool ??
  new Pool({
    connectionString,
    max: 5,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 10000,
    ssl: /localhost|127\.0\.0\.1|sslmode=disable/i.test(connectionString)
      ? undefined
      : { rejectUnauthorized: false },
  });

if (process.env.NODE_ENV !== "production") globalForIpo.ipoPredictionsPool = pool;

const num = (v: unknown, fb = 0) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : fb;
};

const js = (v: unknown, fb: any) => {
  if (!v) return fb;
  if (typeof v === "object") return v;
  try { return JSON.parse(String(v)); } catch { return fb; }
};

function strength(row: any) {
  const decision = String(row.final_decision || "UNKNOWN").toUpperCase();
  const p10 = num(row.p_gain_10);
  const loss = num(row.p_loss);
  const exp = num(row.expected_return_pct);
  const quality = num(row.feature_quality_score);
  const conf = num(row.final_confidence);
  if (decision === "APPLY" && p10 >= 75 && loss <= 15 && exp >= 25 && quality >= 85 && conf >= 80) return "STRONG_APPLY";
  if (decision === "APPLY") return "APPLY";
  if (decision === "WATCH" && quality >= 70) return "HIGH_QUALITY_WATCH";
  if (decision === "WATCH") return "WATCH";
  if (decision === "AVOID") return "AVOID";
  return "UNKNOWN";
}

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const limit = Math.min(Math.max(Number(sp.get("limit") || 75), 1), 300);
  const decision = sp.get("decision");
  const q = sp.get("q")?.trim();
  const where: string[] = [];
  const values: any[] = [];

  if (decision && decision !== "ALL") {
    values.push(decision.toUpperCase());
    where.push(`COALESCE(p.final_decision, p.decision) = $${values.length}`);
  }

  if (q) {
    values.push(`%${q}%`);
    where.push(`(m.company_name ILIKE $${values.length} OR COALESCE(m.symbol, '') ILIKE $${values.length})`);
  }

  values.push(limit);

  const query = `
    SELECT
      m.id AS ipo_id, m.company_name, m.symbol, m.sector, m.status,
      m.open_date, m.close_date, m.listing_date,
      m.issue_price, m.issue_size_cr, m.fresh_issue_cr, m.ofs_cr,
      lf.gmp, lf.gmp_pct, lf.qib_sub, lf.nii_sub, lf.retail_sub, lf.total_sub,
      p.lqi_score, p.p_gain_10, p.p_gain_20, p.p_loss,
      COALESCE(p.expected_return_pct, p.expected_return) AS expected_return_pct,
      COALESCE(p.expected_drawdown_pct, p.expected_drawdown) AS expected_drawdown_pct,
      COALESCE(p.final_decision, p.decision, 'UNKNOWN') AS final_decision,
      COALESCE(p.final_confidence, p.confidence, 0) AS final_confidence,
      p.feature_quality_score, p.feature_quality_bucket, p.apply_eligible,
      COALESCE(p.decision_reasons, p.reasons, '{}'::jsonb) AS decision_reasons,
      p.model_version, p.updated_at,
      fs.has_live_feed, fs.has_gmp, fs.has_subscription, fs.has_similarity,
      fs.missing_features, fs.quality_reasons
    FROM ipo_predictions p
    JOIN ipo_master m ON m.id = p.ipo_id
    LEFT JOIN ipo_live_feed lf ON lf.ipo_id::text = m.id::text
    LEFT JOIN ipo_feature_store fs ON fs.ipo_id = p.ipo_id
    ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
    ORDER BY
      CASE COALESCE(p.final_decision, p.decision)
        WHEN 'APPLY' THEN 1 WHEN 'WATCH' THEN 2 WHEN 'AVOID' THEN 3 ELSE 4
      END,
      COALESCE(p.feature_quality_score, 0) DESC,
      COALESCE(p.lqi_score, 0) DESC
    LIMIT $${values.length}
  `;

  const client = await pool.connect();
  try {
    const rows = (await client.query(query, values)).rows;
    const ids = rows.map((r) => Number(r.ipo_id)).filter(Boolean);
    const similarById = new Map<number, any[]>();

    if (ids.length) {
      const simRows = (await client.query(
        `SELECT ipo_id, similar_ipo_id, similar_company_name, similar_symbol, similarity_score, listing_gain_pct, reasons
         FROM ipo_similarity_results
         WHERE ipo_id = ANY($1::bigint[])
         ORDER BY ipo_id, similarity_score DESC`,
        [ids],
      )).rows;

      for (const r of simRows) {
        const id = Number(r.ipo_id);
        const arr = similarById.get(id) || [];
        if (arr.length < 7) {
          arr.push({
            ipoId: Number(r.similar_ipo_id),
            companyName: r.similar_company_name,
            symbol: r.similar_symbol,
            similarityScore: num(r.similarity_score),
            listingGainPct: num(r.listing_gain_pct),
            reasons: js(r.reasons, {}),
          });
        }
        similarById.set(id, arr);
      }
    }

    const items = rows.map((r) => {
      const ipoId = Number(r.ipo_id);
      return {
        ipoId,
        companyName: r.company_name,
        symbol: r.symbol,
        sector: r.sector,
        status: r.status,
        dates: { openDate: r.open_date, closeDate: r.close_date, listingDate: r.listing_date },
        issue: {
          issuePrice: num(r.issue_price),
          issueSizeCr: num(r.issue_size_cr),
          freshIssueCr: num(r.fresh_issue_cr),
          ofsCr: num(r.ofs_cr),
        },
        live: {
          gmp: num(r.gmp),
          gmpPct: num(r.gmp_pct),
          qibSub: num(r.qib_sub, 1),
          niiSub: num(r.nii_sub, 1),
          retailSub: num(r.retail_sub, 1),
          totalSub: num(r.total_sub, 1),
          hasLiveFeed: Boolean(r.has_live_feed),
          hasGmp: Boolean(r.has_gmp),
          hasSubscription: Boolean(r.has_subscription),
          hasSimilarity: Boolean(r.has_similarity),
        },
        scores: {
          lqiScore: num(r.lqi_score),
          pGain10: num(r.p_gain_10),
          pGain20: num(r.p_gain_20),
          pLoss: num(r.p_loss),
          expectedReturnPct: num(r.expected_return_pct),
          expectedDrawdownPct: num(r.expected_drawdown_pct),
          confidence: num(r.final_confidence),
        },
        quality: {
          featureQualityScore: num(r.feature_quality_score),
          featureQualityBucket: r.feature_quality_bucket || "UNKNOWN",
          applyEligible: Boolean(r.apply_eligible),
          missingFeatures: js(r.missing_features, []),
          qualityReasons: js(r.quality_reasons, {}),
        },
        decision: {
          finalDecision: r.final_decision || "UNKNOWN",
          decisionStrength: strength(r),
          reasons: js(r.decision_reasons, {}),
        },
        similarIpos: similarById.get(ipoId) || [],
        modelVersion: r.model_version,
        updatedAt: r.updated_at,
      };
    });

    const summary = items.reduce((acc: any, item: any) => {
      acc.total += 1;
      acc.byDecision[item.decision.finalDecision] = (acc.byDecision[item.decision.finalDecision] || 0) + 1;
      acc.byQuality[item.quality.featureQualityBucket] = (acc.byQuality[item.quality.featureQualityBucket] || 0) + 1;
      return acc;
    }, { total: 0, byDecision: {}, byQuality: {} });

    return NextResponse.json({ ok: true, summary, items });
  } catch (e: any) {
    console.error("[api/ipo/predictions]", e);
    return NextResponse.json({ ok: false, error: e?.message || "Failed to load IPO predictions" }, { status: 500 });
  } finally {
    client.release();
  }
}
