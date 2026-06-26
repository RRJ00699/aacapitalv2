// ── Workboard engine config ──────────────────────────────────────────────────
// Controls which scoring engine shows on the stock workboard.
//   "new"  → only the decomposed VerdictHeader (Quality/Smart money/Valuation/Momentum)
//   "old"  → only the legacy 6-Engine Convergence rings
//   "both" → show both (default — compare them side by side)
//
// To switch: change WORKBOARD_ENGINE below and redeploy (one-line flip).
// Nothing is deleted — the old engine stays in the code, just hidden when not selected.
// Decide to retire "old" only after 10yr candle data confirms "new" is better.

export type WorkboardEngine = "new" | "old" | "both"

export const WORKBOARD_ENGINE = "both" as WorkboardEngine

export const showNewEngine = () => WORKBOARD_ENGINE === "new" || WORKBOARD_ENGINE === "both"
export const showOldEngine = () => WORKBOARD_ENGINE === "old" || WORKBOARD_ENGINE === "both"
