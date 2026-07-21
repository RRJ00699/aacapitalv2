"use client";
// components/app-shell/AppShell.tsx
// Shared chrome for every routed page: global style, AppNav (with IPO search), Footer.

import { ReactNode, useEffect, useState } from "react";
import AppNav from "./AppNav";
import Footer from "@/components/Footer";

export default function AppShell({
  current,
  children,
  refreshTime,
}: {
  current: string;
  children: ReactNode;
  refreshTime?: string;
}) {
  // IPO search selection → broadcast so the IPO page can scroll to / highlight it.
  const handleSearchSelect = (company: string, target?: string) => {
    if (typeof window === "undefined") return;
    // 2026-07-21 ('search doesn't take me anywhere'): the dashboard is the
    // ONLY listener for aac:focus-ipo — a select made from Admin/Settings
    // dispatched into the void. Off-dashboard: hand off via sessionStorage
    // and route there; the dashboard replays it once data loads.
    if (!window.location.pathname.startsWith("/dashboard/ipo2")) {
      try { sessionStorage.setItem("aac:pending-focus", JSON.stringify({ company, target })); } catch { /* best-effort */ }
      window.location.assign("/dashboard/ipo2");
      return;
    }
    window.dispatchEvent(new CustomEvent("aac:focus-ipo", { detail: { company, target } }));
  };

  // ── Keyboard shortcuts (feat/ux-premium): '/' search · g c|l|p views · '?' help.
  const [helpOpen, setHelpOpen] = useState(false);
  useEffect(() => {
    let pendingG = false; let gTimer: ReturnType<typeof setTimeout> | undefined;
    const goView = (v: string) => {
      if (!window.location.pathname.startsWith("/dashboard/ipo2")) {
        try { sessionStorage.setItem("aac:pending-view", v); } catch { /* best-effort */ }
        window.location.assign("/dashboard/ipo2"); return;
      }
      window.dispatchEvent(new CustomEvent("aac:set-view", { detail: { view: v } }));
    };
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (e.key === "/") { e.preventDefault();
        (document.querySelector('input[role="combobox"]') as HTMLInputElement | null)?.focus(); return; }
      if (e.key === "?") { setHelpOpen((h) => !h); return; }
      if (e.key === "Escape") { setHelpOpen(false); return; }
      if (pendingG) {
        pendingG = false; if (gTimer) clearTimeout(gTimer);
        if (e.key === "c") goView("command");
        if (e.key === "l") goView("live");
        if (e.key === "p") goView("post");
        return;
      }
      if (e.key === "g") { pendingG = true; gTimer = setTimeout(() => { pendingG = false; }, 900); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div style={{ background: "var(--t-bg)", backgroundAttachment: "fixed", minHeight: "100vh", fontFamily: "'DM Sans',sans-serif", color: "var(--t-text)" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&family=DM+Sans:wght@300;400;500;600&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        ::-webkit-scrollbar{width:4px;height:4px;}::-webkit-scrollbar-thumb{background:var(--t-border);border-radius:2px;}
        input,button,textarea{outline:none;font-family:inherit;}
        @keyframes fade{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
        .fade{animation:fade .3s ease}
      `}</style>

      <AppNav current={current} onSearchSelect={handleSearchSelect} refreshTime={refreshTime} />
      <div style={{ position: "fixed", bottom: 4, right: 6, zIndex: 9, fontSize: 8.5,
        fontFamily: "var(--f-mono)", color: "var(--t-dim,#9ca3af)", opacity: .55, pointerEvents: "none" }}>
        build {String(process.env.NEXT_PUBLIC_BUILD_ID || "dev").slice(0, 7)}</div>

      {children}

      {helpOpen && (
        <div role="dialog" aria-label="Keyboard shortcuts" onClick={() => setHelpOpen(false)}
          style={{ position: "fixed", bottom: 18, right: 18, zIndex: 80, background: "var(--t-surface)",
            border: "1px solid var(--t-border)", borderRadius: 12, padding: "12px 16px",
            boxShadow: "0 12px 34px rgba(20,30,60,.18)", fontSize: 12, color: "var(--t-sub)", lineHeight: 1.9 }}>
          <b style={{ color: "var(--t-text)" }}>Keyboard</b><br/>
          <kbd>/</kbd> search · <kbd>g</kbd> then <kbd>c</kbd> Command / <kbd>l</kbd> Live / <kbd>p</kbd> Post-Listing · <kbd>?</kbd> toggle this
        </div>
      )}

      <Footer />
    </div>
  );
}
