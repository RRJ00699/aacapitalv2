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

type Mode = "auto" | "light" | "dark"
const ThemeCtx = createContext<{ pal: Palette; mode: Mode; isDark: boolean; setMode: (m: Mode) => void }>({
  pal: LIGHT, mode: "auto", isDark: false, setMode: () => {},
})

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>("auto")
  const [sysDark, setSysDark] = useState(false)

  useEffect(() => {
    const saved = (typeof window !== "undefined" && window.localStorage.getItem("aac-theme")) as Mode | null
    if (saved) setMode(saved)
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    setSysDark(mq.matches)
    const on = (e: MediaQueryListEvent) => setSysDark(e.matches)
    mq.addEventListener("change", on)
    return () => mq.removeEventListener("change", on)
  }, [])

  const isDark = mode === "dark" || (mode === "auto" && sysDark)
  const pal = isDark ? DARK : LIGHT

  const set = (m: Mode) => {
    setMode(m)
    try { window.localStorage.setItem("aac-theme", m) } catch { /* ignore */ }
  }

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.style.background = pal.bg
      // drive the CSS variables: explicit choice sets data-theme; auto removes it (CSS media query handles it)
      if (mode === "light") document.documentElement.setAttribute("data-theme", "light")
      else if (mode === "dark") document.documentElement.setAttribute("data-theme", "dark")
      else document.documentElement.removeAttribute("data-theme")
    }
  }, [pal.bg, mode])

  return createElement(ThemeCtx.Provider, { value: { pal, mode, isDark, setMode: set } }, children)
}

// pages use: const C = useTheme()  — returns the active palette
export function useTheme(): Palette { return useContext(ThemeCtx).pal }
export function useThemeControls() { return useContext(ThemeCtx) }
