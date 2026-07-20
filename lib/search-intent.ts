// lib/search-intent.ts — Phase 9: Search → Understand → Navigate → Decide.
// Pure functions (no fetch, no window) so the harness/tests can execute them.
// Consumes the ipo-command payload's cards+post (KV-served — zero-idle by
// construction). The BACKEND supplies research statuses (card.research);
// this module only parses intent, filters, ranks and picks the stage action.

export type Stage = "UPCOMING" | "OPEN" | "CLOSED" | "LISTING" | "LISTED";
export type Row = Record<string, unknown>;

export const FILTER_CHIPS = [
  "Upcoming", "Open", "Listing Today", "Recently Listed",
  "GOOD", "WATCH", "JUNK", "Incomplete",
  "RHP Pending", "SBI Pending", "High QIB", "MoS Ready",
] as const;
export type Chip = (typeof FILTER_CHIPS)[number];

// status-keyword → chip. "good IPOs" → Company Quality = GOOD, etc.
const INTENT: Array<[RegExp, Chip]> = [
  [/\bgood\b/i, "GOOD"], [/\bwatch\b/i, "WATCH"], [/\bjunk\b/i, "JUNK"],
  [/\bincomplete\b/i, "Incomplete"],
  [/\b(listing\s*today|today)\b/i, "Listing Today"],
  [/\bupcoming\b/i, "Upcoming"], [/\bopen\b/i, "Open"],
  [/\b(recently\s*listed|listed)\b/i, "Recently Listed"],
  // "rhp"/"sbi" alone stay TEXT (company prefixes!) — chips need "pending"
  [/\brhp\s+pending\b/i, "RHP Pending"], [/\bsbi\s+pending\b/i, "SBI Pending"],
  [/\b(high\s*qib|qib)\b/i, "High QIB"],
  [/\b(mos|margin\s*of\s*safety)\b/i, "MoS Ready"],
];

export function parseIntent(raw: string): { text: string; chips: Chip[] } {
  let text = raw;
  const chips: Chip[] = [];
  for (const [re, chip] of INTENT) {
    if (re.test(text)) { chips.push(chip); text = text.replace(re, " "); }
  }
  // drop filler so "good IPOs" leaves no residual text
  text = text.replace(/\b(ipos?|companies|company|stocks?|pending)\b/gi, " ")
             .replace(/\s+/g, " ").trim();
  return { text, chips };
}

export function stageOf(c: Row): Stage {
  const st = String(c.state ?? "");
  if (st === "LISTING") return "LISTING";
  if (st === "OPEN") return "OPEN";
  if (st === "UPCOMING") return "UPCOMING";
  if (st === "INWINDOW") return "LISTED";
  if (c.listing_gap_pct != null || c.__post) return "LISTED";
  return c.close_date && !c.listing_date ? "CLOSED" : "UPCOMING";
}

type Research = {
  research_completeness?: { label?: string };
  company_quality?: { status?: string; verdict?: string };
  rhp_status?: string; sbi_status?: string;
  fair_value_status?: string; margin_of_safety_status?: string;
  prelisting_score?: { score?: number | null; band?: string | null };
} | null;

const R = (c: Row): Research => (c.research as Research) ?? null;

function chipMatch(c: Row, chip: Chip): boolean {
  const r = R(c), stage = stageOf(c);
  switch (chip) {
    case "Upcoming": return stage === "UPCOMING";
    case "Open": return stage === "OPEN";
    case "Listing Today": return stage === "LISTING";
    case "Recently Listed": return stage === "LISTED";
    case "GOOD": case "WATCH": case "JUNK":
      return r?.company_quality?.status === "CONFIRMED" && r.company_quality.verdict === chip;
    case "Incomplete": return r?.company_quality?.status === "INCOMPLETE";
    case "RHP Pending": return r?.rhp_status === "PENDING" || r?.rhp_status === "PARTIAL";
    case "SBI Pending": return r?.sbi_status === "PENDING" || r?.sbi_status === "PARTIAL";
    case "High QIB": return Number(c.final_qib) >= 5;
    case "MoS Ready": return r?.margin_of_safety_status === "READY";
  }
}

const STAGE_RANK: Record<Stage, number> = { LISTING: 0, OPEN: 1, UPCOMING: 2, LISTED: 3, CLOSED: 4 };

export function searchRank(c: Row, text: string): number {
  // 1 exact symbol · 2 exact name · 3 prefix · then stage priority — never
  // text similarity alone.
  if (!text) return 40 + STAGE_RANK[stageOf(c)];
  const q = text.toLowerCase();
  const sym = String(c.sym ?? "").toLowerCase();
  const name = String(c.company_name ?? "").toLowerCase();
  if (sym === q) return 0;
  if (name === q) return 1;
  if (sym.startsWith(q) || name.startsWith(q)) return 2 + STAGE_RANK[stageOf(c)] / 10;
  if (name.includes(q) || sym.includes(q)) return 10 + STAGE_RANK[stageOf(c)];
  return -1; // no match
}

export function runSearch(cards: Row[], post: Row[], raw: string, activeChips: Chip[]): Row[] {
  const { text, chips } = parseIntent(raw);
  const allChips = [...new Set([...chips, ...activeChips])];
  const pool = [
    ...cards,
    ...post.map((p) => ({ ...p, __post: true })),
  ];
  return pool
    .map((c) => ({ c, r: searchRank(c, text) }))
    .filter(({ c, r }) => r >= 0 && allChips.every((ch) => chipMatch(c, ch)))
    .sort((a, b) => a.r - b.r)
    .slice(0, 30)
    .map(({ c }) => c);
}

// Stage-aware primary action — never one generic "View".
export function primaryAction(c: Row): { label: string; target: "command" | "subscription" | "live" | "journey" } {
  switch (stageOf(c)) {
    case "LISTING": return { label: "Open Live Screen", target: "live" };
    case "OPEN": return { label: "View Subscription", target: "subscription" };
    case "LISTED": return { label: "View Journey", target: "journey" };
    default: return { label: "Open Command Center", target: "command" };
  }
}
