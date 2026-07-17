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
  const handleSearchSelect = (company: string) => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("aac:focus-ipo", { detail: { company } }));
    }
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
