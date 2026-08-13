"use client"
// lib/theme.ts — AACapital theme: Slate Blue (light/day) + Midnight Teal (dark/night)
// Both palettes share the SAME keys as the existing C object, so pages swap
// `const C = {...}` for `const C = useTheme()` with zero other changes.
import { createContext, useContext, useEffect, useState, createElement, type ReactNode } from "react"

export type Palette = {
  bg: string; surface: string; surface2: string; border: string; line: string; text: string;
  sub: string; meta: string; dim: string;
  green: string; greenBg: string; greenBd: string;
  blue: string; blueBg: string; blueBd: string;
  amber: string; amberBg: string; amberBd: string;
  red: string; redBg: string; redBd: string; grayBg: string; gold: string;
  header: string; headerText: string;  // header bar
}

// LIGHT — Slate Blue. Readability fixed: softer bg so white cards get edges, near-black text, fewer grays.
export const LIGHT: Palette = {
  bg:"#EDF1F6", surface:"#FFFFFF", surface2:"#F5F8FC", border:"#DDE4EE", line:"#E9EEF5", text:"#17233A",
  sub:"#3C4A63", meta:"#5B6880", dim:"#8A96AC",
  green:"#0F7A5E", greenBg:"#E4F1EC", greenBd:"#BBE0D3",
  blue:"#2456A8", blueBg:"#E9F0FA", blueBd:"#C2D6F0",
  amber:"#8A5A0E", amberBg:"#FBF2E0", amberBd:"#EAD3A0",
  red:"#C23A2E", redBg:"#FBECEA", redBd:"#F0C7C1", grayBg:"#EBEFF5", gold:"#9A7414",
  header:"#1B2A44", headerText:"#EEF3FA",
}

// DARK — Midnight Teal. Deep navy-teal, bright accents, crisp light text. Easy for lights-off nights.
export const DARK: Palette = {
  bg:"#12202B", surface:"#182A36", surface2:"#1E323F", border:"#274050", line:"#223642", text:"#EAF1EF",
  sub:"#C4D2D0", meta:"#8397A2", dim:"#61757F",
  green:"#34C79D", greenBg:"#16302A", greenBd:"#1E5C48",
  blue:"#5B9BE0", blueBg:"#16283B", blueBd:"#2A4A6B",
  amber:"#E0B15E", amberBg:"#2E2718", amberBd:"#5A4A28",
  red:"#E67C73", redBg:"#301A18", redBd:"#5C2A26", grayBg:"#1C2E39", gold:"#E0B15E",
  header:"#0E1922", headerText:"#EAF1EF",
}

// Theme modes (agreed first version). "system" follows prefers-color-scheme;
// "light"/"dark" are explicit manual overrides that persist across reloads.
export type Mode = "system" | "light" | "dark"
export const THEME_STORAGE_KEY = "aac-theme"

// Normalize any stored value (incl. the legacy "auto") to a valid Mode.
export function normalizeMode(v: unknown): Mode {
  if (v === "light" || v === "dark") return v
  return "system" // "system", legacy "auto", null, or anything unexpected
}

// Read the persisted mode synchronously so the very first client render already
// matches the pre-paint inline script (see app/layout.tsx) — no flash, no
// server/client class divergence to reconcile.
function readStoredMode(): Mode {
  if (typeof window === "undefined") return "system"
  try { return normalizeMode(window.localStorage.getItem(THEME_STORAGE_KEY)) } catch { return "system" }
}

const ThemeCtx = createContext<{ pal: Palette; mode: Mode; isDark: boolean; setMode: (m: Mode) => void }>({
  pal: LIGHT, mode: "system", isDark: false, setMode: () => {},
})

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>(readStoredMode)
  const [sysDark, setSysDark] = useState(false)

  useEffect(() => {
    // Re-sync from storage once mounted (covers SSR's "system" default) and
    // migrate a legacy "auto" value in place.
    const raw = (() => { try { return window.localStorage.getItem(THEME_STORAGE_KEY) } catch { return null } })()
    const norm = normalizeMode(raw)
    setMode(norm)
    if (raw === "auto") { try { window.localStorage.setItem(THEME_STORAGE_KEY, norm) } catch { /* ignore */ } }
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    setSysDark(mq.matches)
    const on = (e: MediaQueryListEvent) => setSysDark(e.matches)
    mq.addEventListener("change", on)
    return () => mq.removeEventListener("change", on)
  }, [])

  const isDark = mode === "dark" || (mode === "system" && sysDark)
  const pal = isDark ? DARK : LIGHT

  const set = (m: Mode) => {
    setMode(m)
    try { window.localStorage.setItem(THEME_STORAGE_KEY, m) } catch { /* ignore */ }
  }

  useEffect(() => {
    if (typeof document !== "undefined") {
      const root = document.documentElement
      root.style.background = pal.bg
      root.style.colorScheme = isDark ? "dark" : "light"
      // Drive the CSS variables: an explicit choice stamps data-theme; "system"
      // removes it so the prefers-color-scheme media query in globals.css wins.
      if (mode === "light") root.setAttribute("data-theme", "light")
      else if (mode === "dark") root.setAttribute("data-theme", "dark")
      else root.removeAttribute("data-theme")
    }
  }, [pal.bg, mode, isDark])

  return createElement(ThemeCtx.Provider, { value: { pal, mode, isDark, setMode: set } }, children)
}

// pages use: const C = useTheme()  — returns the active palette
export function useTheme(): Palette { return useContext(ThemeCtx).pal }
export function useThemeControls() { return useContext(ThemeCtx) }

// ═══ UX system additions (feat/ux-premium 2026-07-21) ════════════════════
// Static CSS-var tokens for non-hook contexts + the ONE status-color map.

export const VARS = {
  bg: "var(--t-bg)", surface: "var(--t-surface)", surface2: "var(--t-surface2)",
  border: "var(--t-border)", line: "var(--t-line)",
  text: "var(--t-text)", sub: "var(--t-sub)", meta: "var(--t-meta)", dim: "var(--t-dim)",
  green: "var(--t-green)", greenBg: "var(--t-greenBg)", greenBd: "var(--t-greenBd)",
  blue: "var(--t-blue)", blueBg: "var(--t-blueBg)", blueBd: "var(--t-blueBd)",
  amber: "var(--t-amber)", amberBg: "var(--t-amberBg)", amberBd: "var(--t-amberBd)",
  red: "var(--t-red)", redBg: "var(--t-redBg)", redBd: "var(--t-redBd)",
  grayBg: "var(--t-grayBg)", gold: "var(--t-gold)",
} as const

export const FONT = { display: "var(--f-display)", mono: "var(--f-mono)" } as const
export const MOTION = { fast: "var(--m-fast)", base: "var(--m-base)", slow: "var(--m-slow)", ease: "var(--m-ease)" } as const

export type Tone = "good" | "watch" | "junk" | "info" | "neutral"
export const TONE: Record<Tone, { fg: string; bg: string; bd: string }> = {
  good: { fg: "var(--s-good)", bg: "var(--s-good-bg)", bd: "var(--s-good-bd)" },
  watch: { fg: "var(--s-watch)", bg: "var(--s-watch-bg)", bd: "var(--s-watch-bd)" },
  junk: { fg: "var(--s-junk)", bg: "var(--s-junk-bg)", bd: "var(--s-junk-bd)" },
  info: { fg: "var(--s-info)", bg: "var(--s-info-bg)", bd: "var(--s-info-bd)" },
  neutral: { fg: "var(--s-neutral)", bg: "var(--s-neutral-bg)", bd: "var(--s-neutral-bd)" },
}

// Status vocabulary → tone: the UI never picks ad-hoc colors for these words.
export const toneFor = (s: string | null | undefined): Tone => {
  const k = String(s ?? "").toUpperCase()
  if (["GOOD", "CONFIRMED", "BUY", "TRADE", "READY", "RESEARCH COMPLETE", "STRONG", "FAVORABLE", "OK"].includes(k)) return "good"
  if (["WATCH", "PARTIAL", "PENDING", "INCOMPLETE", "CAUTION", "AWAITING", "RESEARCH PARTIAL", "RESEARCH PENDING", "NEUTRAL"].includes(k)) return "watch"
  if (["JUNK", "FAILED", "SKIP", "AVOID", "MISSED", "ERROR"].includes(k)) return "junk"
  if (["UPCOMING", "OPEN", "LISTING", "LISTING TODAY", "INFO"].includes(k)) return "info"
  return "neutral"
}
