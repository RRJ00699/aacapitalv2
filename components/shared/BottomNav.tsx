"use client"
// components/shared/BottomNav.tsx
// Premium light navigation — replaces the dark #0f172a shell.
// Desktop: sticky top bar with 8 tabs.
// Mobile:  fixed bottom 4 primary tabs + More drawer for the rest.
//
// NOTE: Some tab paths below don't have pages yet (Portfolio, Settings, Backtests).
// They'll 404 until those pages are built — that's fine for a personal tool.
// Calc tab intentionally removed; it can live inside Settings later.

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useState } from "react"
import {
  LayoutDashboard, TrendingUp, Zap, BarChart3,
  Users, FlaskConical, Briefcase, Settings,
  MoreHorizontal, X,
} from "lucide-react"

type Tab = { path: string; label: string; Icon: React.ElementType }

const ALL_TABS: Tab[] = [
  { path: "/",          label: "Wealth",    Icon: LayoutDashboard },
  { path: "/market",    label: "Markets",   Icon: TrendingUp },
  { path: "/ipo",       label: "IPOs",      Icon: Zap },
  { path: "/stocks",    label: "Stocks",    Icon: BarChart3 },
  { path: "/screener",  label: "Gurus",     Icon: Users },
  { path: "/backtest",  label: "Backtests", Icon: FlaskConical },
  { path: "/portfolio", label: "Portfolio", Icon: Briefcase },
  { path: "/settings",  label: "Settings",  Icon: Settings },
]

const PRIMARY   = ALL_TABS.slice(0, 4)   // Wealth · Markets · IPOs · Stocks
const SECONDARY = ALL_TABS.slice(4)       // Gurus · Backtests · Portfolio · Settings

// ─── Design tokens (inline so this file is self-contained) ───────────────────
const C = {
  white:    "#FFFFFF",
  blue:     "#2563EB",
  blueBg:   "#EFF6FF",
  gray:     "#6B7280",
  grayLt:   "#9CA3AF",
  grayBg:   "#F8FAFC",
  grayBtn:  "#F3F4F6",
  text:     "#111827",
  border:   "#E5E7EB",
  overlay:  "rgba(0,0,0,0.28)",
}

export default function BottomNav() {
  const pathname  = usePathname()
  const [more, setMore] = useState(false)

  function active(path: string) {
    return path === "/" ? pathname === "/" : pathname.startsWith(path)
  }

  return (
    <>
      {/* ── Desktop: sticky top nav ───────────────────────────────────── */}
      <header className="aac-top-nav" style={{
        position: "sticky", top: 0, zIndex: 300,
        background: C.white, borderBottom: `1px solid ${C.border}`,
        height: 56, padding: "0 24px",
        display: "flex", alignItems: "center",
      }}>
        {/* Wordmark */}
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: 9, marginRight: 28, textDecoration: "none" }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8, background: C.blue,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <span style={{ color: C.white, fontWeight: 800, fontSize: 13, letterSpacing: "-0.5px" }}>AA</span>
          </div>
          <span style={{ fontWeight: 600, fontSize: 16, color: C.text, letterSpacing: "-0.3px" }}>
            AACapital
          </span>
        </Link>

        {/* Tab list */}
        <nav style={{ display: "flex", alignItems: "center", gap: 2, flex: 1 }}>
          {ALL_TABS.map(({ path, label, Icon }) => {
            const on = active(path)
            return (
              <Link key={path} href={path} style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "5px 11px", borderRadius: 7,
                fontSize: 13, fontWeight: on ? 600 : 500,
                color: on ? C.blue : C.gray,
                background: on ? C.blueBg : "transparent",
                textDecoration: "none",
                transition: "background 0.12s, color 0.12s",
                whiteSpace: "nowrap",
              }}>
                <Icon size={14} />
                {label}
              </Link>
            )
          })}
        </nav>
      </header>

      {/* ── Mobile: brand bar (top, scrolls away) ────────────────────── */}
      <div className="aac-mobile-brand" style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "10px 16px",
        background: C.white, borderBottom: `1px solid ${C.border}`,
      }}>
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: 8, textDecoration: "none" }}>
          <div style={{ width: 28, height: 28, borderRadius: 7, background: C.blue, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <span style={{ color: C.white, fontWeight: 800, fontSize: 11 }}>AA</span>
          </div>
          <span style={{ fontWeight: 600, fontSize: 15, color: C.text, letterSpacing: "-0.2px" }}>AACapital</span>
        </Link>
      </div>

      {/* ── Mobile: fixed bottom nav ──────────────────────────────────── */}
      <nav className="aac-bottom-nav" style={{
        position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 300,
        background: C.white, borderTop: `1px solid ${C.border}`,
        display: "flex",
        paddingBottom: "env(safe-area-inset-bottom)",
      }}>
        {PRIMARY.map(({ path, label, Icon }) => {
          const on = active(path)
          return (
            <Link key={path} href={path} style={{
              flex: 1, display: "flex", flexDirection: "column",
              alignItems: "center", gap: 3, padding: "7px 4px",
              textDecoration: "none",
            }}>
              <Icon size={22} color={on ? C.blue : C.grayLt} strokeWidth={on ? 2.5 : 1.75} />
              <span style={{ fontSize: 10, fontWeight: on ? 600 : 400, color: on ? C.blue : C.grayLt }}>
                {label}
              </span>
            </Link>
          )
        })}

        {/* More button */}
        <button onClick={() => setMore(o => !o)} style={{
          flex: 1, display: "flex", flexDirection: "column",
          alignItems: "center", gap: 3, padding: "7px 4px",
          background: "transparent", border: "none", cursor: "pointer",
        }}>
          <MoreHorizontal size={22} color={more ? C.blue : C.grayLt} strokeWidth={1.75} />
          <span style={{ fontSize: 10, fontWeight: 400, color: more ? C.blue : C.grayLt }}>More</span>
        </button>
      </nav>

      {/* ── More: backdrop ────────────────────────────────────────────── */}
      {more && (
        <div
          className="aac-bottom-nav"
          onClick={() => setMore(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 290,
            background: C.overlay,
            backdropFilter: "blur(2px)",
          }}
        />
      )}

      {/* ── More: sheet ───────────────────────────────────────────────── */}
      {more && (
        <div className="aac-bottom-nav" style={{
          position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 295,
          background: C.white,
          borderRadius: "20px 20px 0 0",
          padding: "16px 16px",
          paddingBottom: "calc(2rem + env(safe-area-inset-bottom))",
          boxShadow: "0 -8px 24px rgba(0,0,0,0.10)",
        }}>
          {/* Sheet header */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: C.text }}>More</span>
            <button onClick={() => setMore(false)} style={{
              background: C.grayBtn, border: "none", borderRadius: 8,
              padding: 6, cursor: "pointer", display: "flex", alignItems: "center",
            }}>
              <X size={16} color={C.gray} />
            </button>
          </div>

          {/* 4-column grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
            {SECONDARY.map(({ path, label, Icon }) => {
              const on = active(path)
              return (
                <Link key={path} href={path} onClick={() => setMore(false)} style={{
                  display: "flex", flexDirection: "column",
                  alignItems: "center", gap: 6,
                  padding: "12px 8px", borderRadius: 12,
                  background: on ? C.blueBg : C.grayBg,
                  textDecoration: "none",
                }}>
                  <Icon size={20} color={on ? C.blue : C.gray} />
                  <span style={{ fontSize: 11, fontWeight: 500, color: on ? C.blue : C.gray }}>
                    {label}
                  </span>
                </Link>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Responsive display rules ──────────────────────────────────── */}
      <style>{`
        /* Desktop (≥ 768px): show top nav, hide mobile elements */
        @media (min-width: 768px) {
          .aac-top-nav       { display: flex !important; }
          .aac-mobile-brand  { display: none !important; }
          .aac-bottom-nav    { display: none !important; }
        }
        /* Mobile (< 768px): hide top nav, show mobile elements */
        @media (max-width: 767px) {
          .aac-top-nav       { display: none !important; }
          .aac-mobile-brand  { display: flex !important; }
          .aac-bottom-nav    { display: flex !important; }
        }
      `}</style>
    </>
  )
}
