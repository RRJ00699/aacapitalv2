// lib/design-tokens.ts
// Single source of truth for colors, spacing, typography.
// Import this in every feature component for consistent UI.

export const T = {
  // Surfaces
  bg:      "#FAFAF8",
  surface: "#FFFFFF",
  border:  "#E5E7EB",
  hover:   "#F8FAFC",

  // Text
  text:    "#111827",
  textSub: "#374151",
  meta:    "#6B7280",
  dim:     "#9CA3AF",

  // Semantic
  green:    "#16A34A", greenBg:  "#F0FDF4", greenBd:  "#BBF7D0",
  blue:     "#2563EB", blueBg:   "#EFF6FF", blueBd:   "#BFDBFE",
  amber:    "#D97706", amberBg:  "#FFFBEB", amberBd:  "#FDE68A",
  red:      "#DC2626", redBg:    "#FEF2F2", redBd:    "#FECACA",
  orange:   "#EA580C", orangeBg: "#FFF7ED", orangeBd: "#FED7AA",
  teal:     "#0D9488", tealBg:   "#F0FDFA", tealBd:   "#99F6E4",
  purple:   "#7C3AED", purpleBg: "#F5F3FF", purpleBd: "#DDD6FE",

  // Neutral chips
  grayBg:  "#F3F4F6",
  grayBd:  "#E5E7EB",

  // Radius
  card:   12,
  btn:    8,
  pill:   20,

  // Score colors
  scoreColor: (s: number) =>
    s >= 80 ? "#16A34A" : s >= 65 ? "#0D9488" : s >= 50 ? "#D97706" : "#DC2626",
  scoreBg: (s: number) =>
    s >= 80 ? "#F0FDF4" : s >= 65 ? "#F0FDFA" : s >= 50 ? "#FFFBEB" : "#FEF2F2",
}

export type DesignTokens = typeof T
