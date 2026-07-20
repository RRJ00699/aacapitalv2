// lib/design/tokens.ts
// AACapital Design System — single source of truth.
// Import from here in every component. Never use raw hex values or
// hardcoded Tailwind classes scattered across files.

// ─── Palette ────────────────────────────────────────────────────────────────

export const colors = {
  // Page & surface
  background:  "#FAFAF8", // warm white — page bg
  surface:     "#FFFFFF", // card bg
  surfaceSoft: "#F8FAFC", // subtle section bg

  // Text
  textPrimary:   "#111827",
  textSecondary: "#64748B",
  textMuted:     "#9CA3AF",

  // Border
  border:       "#E5E7EB",
  borderSubtle: "#F3F4F6",

  // Semantic — actions & status
  green:  "#16A34A", // apply, positive, accumulate, strong buy
  blue:   "#2563EB", // info, research, DNA, accumulate
  purple: "#7C3AED", // multibagger, contrarian, frozen regime
  amber:  "#D97706", // watch, caution, hold
  red:    "#DC2626", // avoid, exit, risk, stop loss

  // Semantic — soft backgrounds (for badges, tags, highlights)
  greenBg:  "#F0FDF4",
  blueBg:   "#EFF6FF",
  purpleBg: "#F5F3FF",
  amberBg:  "#FFFBEB",
  redBg:    "#FEF2F2",
} as const

// ─── Shadows ────────────────────────────────────────────────────────────────

export const shadows = {
  card:       "0 2px 12px rgba(0,0,0,0.05)",
  cardHover:  "0 12px 30px rgba(15,23,42,0.08)",
  nav:        "0 1px 0 #E5E7EB",        // top nav bottom border
  navBottom:  "0 -1px 0 #E5E7EB",       // bottom nav top border
  dropdown:   "0 8px 24px rgba(0,0,0,0.10)",
} as const

// ─── Border radius ──────────────────────────────────────────────────────────

export const radius = {
  sm:     "6px",
  md:     "10px",   // buttons
  card:   "16px",   // standard card
  cardLg: "24px",   // hero cards
  pill:   "999px",  // badges, chips
} as const

// ─── Typography ─────────────────────────────────────────────────────────────

export const type = {
  // Scale
  xs:  "11px",
  sm:  "12px",
  base:"14px",
  md:  "15px",
  lg:  "16px",
  xl:  "18px",
  "2xl": "20px",
  "3xl": "24px",
  "4xl": "28px",
  "5xl": "32px",

  // Weight
  normal:   "400",
  medium:   "500",
  semibold: "600",
  bold:     "700",

  // Line height
  tight:  "1.2",
  snug:   "1.375",
  normal_lh: "1.5",
  relaxed:"1.625",
} as const

// ─── Spacing ────────────────────────────────────────────────────────────────

export const spacing = {
  cardPad:      "24px",
  cardPadSm:    "16px",
  sectionGap:   "16px",
  pageGutter:   "16px",  // mobile
  pageGutterMd: "24px",  // desktop
} as const

// ─── Semantic aliases ────────────────────────────────────────────────────────
// Use these in components — they express intent, not implementation.

export const semantic = {
  conviction: (score: number): string => {
    if (score >= 80) return colors.green
    if (score >= 60) return colors.blue
    if (score >= 40) return colors.amber
    return colors.red
  },
  convictionBg: (score: number): string => {
    if (score >= 80) return colors.greenBg
    if (score >= 60) return colors.blueBg
    if (score >= 40) return colors.amberBg
    return colors.redBg
  },
  recommendation: (rec: string): string => {
    const r = rec?.toUpperCase() ?? ""
    if (r.includes("STRONG BUY")) return colors.green
    if (r.includes("BUY"))        return colors.green
    if (r.includes("ACCUMULATE")) return colors.blue
    if (r.includes("HOLD"))       return colors.amber
    return colors.red
  },
  regime: (regime: string): string => {
    const r = regime?.toUpperCase() ?? ""
    if (r === "HOT")    return colors.green
    if (r === "NORMAL") return colors.blue
    if (r === "CAUTION")return colors.amber
    if (r === "COLD")   return colors.red
    if (r === "FROZEN") return colors.purple
    return colors.textSecondary
  },
  regimeBg: (regime: string): string => {
    const r = regime?.toUpperCase() ?? ""
    if (r === "HOT")    return colors.greenBg
    if (r === "NORMAL") return colors.blueBg
    if (r === "CAUTION")return colors.amberBg
    if (r === "COLD")   return colors.redBg
    if (r === "FROZEN") return colors.purpleBg
    return colors.surfaceSoft
  },
} as const

// ─── Tailwind class helpers ──────────────────────────────────────────────────
// Pre-composed class strings for consistent patterns across components.

export const tw = {
  // Cards
  card:      "bg-white rounded-2xl border border-gray-100",
  cardShadow:"bg-white rounded-2xl border border-gray-100 shadow-sm",
  cardPad:   "p-6",
  cardPadSm: "p-4",

  // Page layout
  pageWrapper: "min-h-screen bg-[#FAFAF8]",
  pageGutter:  "px-4 md:px-6",
  maxWidth:    "max-w-5xl mx-auto",

  // Typography
  label:    "text-xs font-medium text-gray-500 uppercase tracking-wide",
  sublabel: "text-xs text-gray-400",
  value:    "text-2xl font-bold text-gray-900",
  heading:  "text-lg font-semibold text-gray-900",
  subheading:"text-sm font-medium text-gray-600",

  // Badges
  badge: {
    green:  "bg-green-50 text-green-700 text-xs font-medium px-2 py-0.5 rounded",
    blue:   "bg-blue-50 text-blue-700 text-xs font-medium px-2 py-0.5 rounded",
    amber:  "bg-amber-50 text-amber-700 text-xs font-medium px-2 py-0.5 rounded",
    red:    "bg-red-50 text-red-700 text-xs font-medium px-2 py-0.5 rounded",
    purple: "bg-purple-50 text-purple-700 text-xs font-medium px-2 py-0.5 rounded",
    gray:   "bg-gray-100 text-gray-600 text-xs font-medium px-2 py-0.5 rounded",
  },

  // Buttons
  btn: {
    primary:   "bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors",
    secondary: "bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-medium px-4 py-2 rounded-lg transition-colors",
    ghost:     "hover:bg-gray-100 text-gray-600 text-sm font-medium px-3 py-1.5 rounded-lg transition-colors",
    danger:    "bg-red-50 hover:bg-red-100 text-red-600 text-sm font-medium px-4 py-2 rounded-lg transition-colors",
  },

  // Divider
  divider: "border-t border-gray-100 my-4",

  // Section spacing
  section: "space-y-4",
  sectionLg: "space-y-6",
} as const

// ─── CSS variables (inject into :root in layout.tsx or globals.css) ──────────

export const cssVariables = `
  --aac-bg: ${colors.background};
  --aac-surface: ${colors.surface};
  --aac-surface-soft: ${colors.surfaceSoft};
  --aac-text: ${colors.textPrimary};
  --aac-text-secondary: ${colors.textSecondary};
  --aac-border: ${colors.border};
  --aac-green: ${colors.green};
  --aac-blue: ${colors.blue};
  --aac-purple: ${colors.purple};
  --aac-amber: ${colors.amber};
  --aac-red: ${colors.red};
  --aac-shadow-card: ${shadows.card};
  --aac-shadow-card-hover: ${shadows.cardHover};
  --aac-radius-card: ${radius.card};
`
