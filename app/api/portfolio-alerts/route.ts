// app/api/portfolio-alerts/route.ts
// Portfolio Intelligence Engine — scores every Zerodha holding against all engines
// Returns EXIT / TRIM / ADD / HOLD per position with reasoning

import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import { getBroker } from "@/lib/brokers";

// ─── Alert Thresholds ──────────────────────────────────────────────────────
const THRESHOLDS = {
  EXIT: {
    convergence_below: 35,    // Score collapsed — exit signal
    stage4_confirmed: true,   // Downtrend stage — exit regardless
    smart_money_sell: 75,     // Heavy distribution by Tier-1 — exit
    loss_pct: -15,            // Stop loss triggered
  },
  TRIM: {
    convergence_below: 50,    // Weakening signal
    gain_pct: 40,             // Take partial profits at +40%
    stage3_distribution: true,// Entering distribution phase
    sector_rank_below: 40,    // Sector rotation signal waning
  },
  ADD: {
    convergence_above: 70,    // Strong signal — add on dips
    stage2_confirmed: true,   // Uptrend confirmed
    nr7_flag: true,           // Coiling — imminent move
    sm_accumulation: 65,      // Smart money buying
    max_position_pct: 12,     // Don't add beyond 12% of portfolio
  },
  HOLD: {
    // Default when no EXIT/TRIM/ADD triggers
  },
};

// Matches BrokerHolding from lib/brokers/interface.ts exactly
import type { BrokerHolding as Holding } from "@/lib/brokers/interface";

interface AlertResult {
  symbol: string;
  action: "EXIT" | "TRIM" | "ADD" | "HOLD";
  urgency: "IMMEDIATE" | "THIS_WEEK" | "MONITOR";
  current_price: number;
  average_price: number;
  pnl_pct: number;
  convergence_score: number;
  convergence_version: string;
  engines_fired: number;
  reasons: string[];
  weekly_signal?: string;
  suggested_action: string;
  risk_flags: string[];
}

function computeAlert(
  holding: Holding,
  fundamentals: Record<string, unknown>,
  weeklyDNA: Record<string, unknown> | null,
  convergenceScore: number,
  convergenceVersion: string,
  enginesFired: number
): AlertResult {
  const pnlPct = holding.investedValue > 0
    ? ((holding.currentValue - holding.investedValue) / holding.investedValue) * 100
    : 0;
  const reasons: string[] = [];
  const riskFlags: string[] = [];
  let action: "EXIT" | "TRIM" | "ADD" | "HOLD" = "HOLD";
  let urgency: "IMMEDIATE" | "THIS_WEEK" | "MONITOR" = "MONITOR";

  const stage = weeklyDNA ? Number(weeklyDNA.stage ?? 0) : 0;
  const nr7 = weeklyDNA ? Boolean(weeklyDNA.is_nr7) : false;
  const smScore = Number(fundamentals.smart_money_score ?? 50);

  // ── EXIT checks (highest priority) ─────────────────────────────────────
  if (stage === 4) {
    action = "EXIT";
    urgency = "IMMEDIATE";
    reasons.push("Stage 4 downtrend confirmed — trend broken");
    riskFlags.push("STAGE4");
  }

  if (pnlPct <= THRESHOLDS.EXIT.loss_pct) {
    action = "EXIT";
    urgency = "IMMEDIATE";
    reasons.push(`Stop loss hit: ${pnlPct.toFixed(1)}% loss (limit: -15%)`);
    riskFlags.push("STOP_LOSS");
  }

  if (convergenceScore <= THRESHOLDS.EXIT.convergence_below && action !== "EXIT") {
    action = "EXIT";
    urgency = "THIS_WEEK";
    reasons.push(
      `Convergence collapsed to ${convergenceScore} (exit threshold: <35)`
    );
    riskFlags.push("CONVERGENCE_COLLAPSE");
  }

  if (smScore >= THRESHOLDS.EXIT.smart_money_sell && action !== "EXIT") {
    // High smart money SELL score = heavy distribution
    const smSignal = String(fundamentals.smart_money_signal ?? "");
    if (smSignal.includes("Distribution") || smSignal.includes("Selling")) {
      action = "EXIT";
      urgency = "THIS_WEEK";
      reasons.push("Tier-1 institutional distribution detected");
      riskFlags.push("INSTITUTIONAL_SELLING");
    }
  }

  // ── TRIM checks ──────────────────────────────────────────────────────────
  if (action === "HOLD") {
    if (pnlPct >= THRESHOLDS.TRIM.gain_pct) {
      action = "TRIM";
      urgency = "THIS_WEEK";
      reasons.push(
        `Gain of +${pnlPct.toFixed(1)}% — trim 30-40% to lock profits`
      );
    }

    if (
      stage === 3 &&
      convergenceScore < 55
    ) {
      action = "TRIM";
      urgency = "THIS_WEEK";
      reasons.push("Stage 3 distribution + weakening convergence");
      riskFlags.push("STAGE3_DISTRIBUTION");
    }

    if (
      convergenceScore <= THRESHOLDS.TRIM.convergence_below &&
      convergenceScore > THRESHOLDS.EXIT.convergence_below
    ) {
      action = "TRIM";
      urgency = "THIS_WEEK";
      reasons.push(`Convergence declining: ${convergenceScore} (trim threshold: <50)`);
    }
  }

  // ── ADD checks ───────────────────────────────────────────────────────────
  if (action === "HOLD") {
    const addReasons: string[] = [];

    if (convergenceScore >= THRESHOLDS.ADD.convergence_above) {
      addReasons.push(`High convergence: ${convergenceScore}`);
    }
    if (stage === 2) {
      addReasons.push("Stage 2 uptrend confirmed");
    }
    if (nr7) {
      addReasons.push("NR7 — coiling for breakout");
    }
    if (smScore >= THRESHOLDS.ADD.sm_accumulation) {
      const smSignal = String(fundamentals.smart_money_signal ?? "");
      if (smSignal.includes("Accum")) {
        addReasons.push("Tier-1 accumulation active");
      }
    }

    // Need at least 2 ADD signals to upgrade from HOLD to ADD
    if (addReasons.length >= 2) {
      action = "ADD";
      urgency = pnlPct < 0 ? "THIS_WEEK" : "MONITOR"; // Dip = act faster
      reasons.push(...addReasons);
    }
  }

  // ── Weekly signal summary ────────────────────────────────────────────────
  let weeklySignalText: string | undefined;
  if (weeklyDNA) {
    const signals: string[] = [];
    if (nr7) signals.push("NR7");
    if (Boolean(weeklyDNA.is_nr4)) signals.push("NR4");
    if (stage > 0) signals.push(`Stage ${stage}`);
    const vcPct = Number(weeklyDNA.vol_contraction_pct ?? 0);
    if (vcPct >= 20) signals.push(`Vol -${vcPct.toFixed(0)}%`);
    weeklySignalText = signals.join(" · ") || "No weekly signal";
  }

  // ── Build suggested action text ──────────────────────────────────────────
  let suggested: string;
  switch (action) {
    case "EXIT":
      suggested =
        urgency === "IMMEDIATE"
          ? "Exit full position at market — stop loss or trend broken"
          : "Plan exit this week — convergence or trend deteriorating";
      break;
    case "TRIM":
      suggested =
        pnlPct >= 40
          ? `Sell 30-40% at ₹${holding.lastPrice.toFixed(2)} to lock gains`
          : `Reduce by 25-30% — weakening signal, preserve capital`;
      break;
    case "ADD":
      suggested =
        nr7
          ? `Add on breakout — NR7 coil with convergence ${convergenceScore}`
          : `Add on next dip — strong engines, ${enginesFired} of 6+ fired`;
      break;
    default:
      suggested = "Hold — monitor weekly for signal change";
  }

  if (reasons.length === 0) {
    reasons.push(`Holding steady — convergence ${convergenceScore}, ${enginesFired} engines active`);
  }

  return {
    symbol: holding.symbol,
    action,
    urgency,
    current_price: holding.lastPrice,
    average_price: holding.avgPrice,
    pnl_pct: Math.round(pnlPct * 10) / 10,
    convergence_score: convergenceScore,
    convergence_version: convergenceVersion,
    engines_fired: enginesFired,
    reasons,
    weekly_signal: weeklySignalText,
    suggested_action: suggested,
    risk_flags: riskFlags,
  };
}

export async function GET(req: NextRequest) {
  const sql = neon(process.env.DATABASE_URL!);

  // ── Load holdings via broker abstraction (same as broker/holdings/route.ts) ─
  let holdings: Holding[] = [];

  try {
    const broker = getBroker();
    const connected = await broker.isConnected();

    if (!connected) {
      return NextResponse.json(
        { error: "Broker not connected", loginUrl: "/api/auth/zerodha" },
        { status: 401 }
      );
    }

    holdings = await broker.getHoldings();
  } catch (err) {
    console.error("Holdings fetch failed:", err);
    return NextResponse.json(
      { error: "Failed to fetch holdings" },
      { status: 500 }
    );
  }

  if (!holdings.length) {
    return NextResponse.json({ alerts: [], count: 0 });
  }

  const symbols = holdings.map((h) => h.symbol.toUpperCase());

  // ── Fetch engine data for all held symbols ───────────────────────────────
  const [fundamentalsRows, weeklyRows] = await Promise.all([
    sql`
      SELECT
        nse_symbol,
        business_dna_score,
        earnings_score,
        smart_money_score,
        smart_money_signal,
        sector_rotation_score,
        return_3m,
        return_6m,
        LEAST(100, GREATEST(0,
          50
          + COALESCE(return_3m, 0) * 0.8
          + COALESCE(return_6m, 0) * 0.4
        ))::numeric AS technical_dna_score
      FROM stock_fundamentals
      WHERE nse_symbol = ANY(${symbols})
    `,
    sql`
      SELECT
        tradingsymbol,
        is_nr7,
        is_nr4,
        stage,
        vol_contraction_pct,
        breakout_ready,
        rs_vs_nifty_4w,
        rs_vs_nifty_12w,
        weeks_in_base
      FROM weekly_dna
      WHERE tradingsymbol = ANY(${symbols})
    `,
  ]);

  const fundamentalsMap = new Map(
    fundamentalsRows.map((f) => [f.nse_symbol, f])
  );
  const weeklyMap = new Map(weeklyRows.map((w) => [w.tradingsymbol, w]));

  // ── Score each holding ───────────────────────────────────────────────────
  const alerts: AlertResult[] = [];

  for (const holding of holdings) {
    const sym = holding.symbol.toUpperCase();
    const f = fundamentalsMap.get(sym);
    const w = weeklyMap.get(sym) ?? null;

    if (!f) {
      // Symbol not in our DB — skip with a note
      const invested = holding.investedValue;
      const current = holding.currentValue;
      alerts.push({
        symbol: sym,
        action: "HOLD",
        urgency: "MONITOR",
        current_price: holding.lastPrice,
        average_price: holding.avgPrice,
        pnl_pct: invested > 0 ? Math.round(((current - invested) / invested) * 1000) / 10 : 0,
        convergence_score: 0,
        convergence_version: "UNAVAILABLE",
        engines_fired: 0,
        reasons: ["Symbol not in AACapital database — no engine data available"],
        suggested_action: "Check manually — not in our coverage universe",
        risk_flags: ["NOT_COVERED"],
      });
      continue;
    }

    // Compute inline convergence (same logic as convergence-score API)
    const hasWeekly = w != null;
    const weights = hasWeekly
      ? { biz: 0.28, techM: 0.17, techW: 0.13, earn: 0.18, sm: 0.14, sec: 0.10 }
      : { biz: 0.30, techM: 0.25, techW: 0, earn: 0.20, sm: 0.15, sec: 0.10 };

    let weeklyScore = 0;
    if (hasWeekly && w) {
      let ws = 40;
      if (w.is_nr7) ws += 15;
      if (w.is_nr4) ws += 8;
      const stage = Number(w.stage ?? 0);
      if (stage === 2) ws += 20;
      else if (stage === 1) ws += 10;
      else if (stage === 3) ws -= 10;
      else if (stage === 4) ws -= 25;
      if (Number(w.vol_contraction_pct ?? 0) >= 30) ws += 12;
      if (Number(w.rs_vs_nifty_4w ?? 0) > 0) ws += 10;
      if (Number(w.weeks_in_base ?? 0) >= 12) ws += 8;
      weeklyScore = Math.max(0, Math.min(100, ws));
    }

    const bizScore = Number(f.business_dna_score ?? 0);
    const techMScore = Number(f.technical_dna_score ?? 0);
    const earnScore = Number(f.earnings_score ?? 0);
    const smScore2 = Number(f.smart_money_score ?? 0);
    const secScore = Number(f.sector_rotation_score ?? 0);

    const raw =
      bizScore * weights.biz +
      techMScore * weights.techM +
      weeklyScore * weights.techW +
      earnScore * weights.earn +
      smScore2 * weights.sm +
      secScore * weights.sec;

    const convergenceScore = Math.round(raw);
    const convergenceVersion = hasWeekly ? "V2" : "V1_FALLBACK";

    const scores = [bizScore, techMScore, earnScore, smScore2, secScore];
    if (hasWeekly) scores.push(weeklyScore);
    const enginesFired = scores.filter((s) => s >= 65).length;

    const alert = computeAlert(
      holding,
      f as Record<string, unknown>,
      w as Record<string, unknown> | null,
      convergenceScore,
      convergenceVersion,
      enginesFired
    );

    alerts.push(alert);
  }

  // Sort: EXIT (immediate) → EXIT (this week) → TRIM → ADD → HOLD
  const urgencyOrder = { IMMEDIATE: 0, THIS_WEEK: 1, MONITOR: 2 };
  const actionOrder = { EXIT: 0, TRIM: 1, ADD: 2, HOLD: 3 };

  alerts.sort((a, b) => {
    const actionDiff = actionOrder[a.action] - actionOrder[b.action];
    if (actionDiff !== 0) return actionDiff;
    return urgencyOrder[a.urgency] - urgencyOrder[b.urgency];
  });

  // Summary stats
  const summary = {
    total: alerts.length,
    exit: alerts.filter((a) => a.action === "EXIT").length,
    trim: alerts.filter((a) => a.action === "TRIM").length,
    add: alerts.filter((a) => a.action === "ADD").length,
    hold: alerts.filter((a) => a.action === "HOLD").length,
    immediate_action: alerts.filter((a) => a.urgency === "IMMEDIATE").length,
    weekly_coverage: weeklyRows.length,
    v2_scored: alerts.filter((a) => a.convergence_version === "V2").length,
  };

  return NextResponse.json({ summary, alerts });
}
