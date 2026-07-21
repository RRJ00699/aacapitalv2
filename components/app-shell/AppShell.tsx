"use client";
// components/app-shell/AppShell.tsx
// Shared chrome for every routed page: global style, AppNav (with IPO search), Footer.

import { ReactNode } from "react";
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

      <Footer />
    </div>
  );
}
