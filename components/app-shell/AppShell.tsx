"use client";
// components/app-shell/AppShell.tsx
// The shared chrome for every routed page: global style, AppNav, the stock-research
// overlay (opened via the useOpenStock() context from any page), and Footer.
// A route page becomes:  <AppShell current="today"><Body/></AppShell>

import { createContext, useContext, useState, ReactNode } from "react";
import AppNav from "./AppNav";
import Footer from "@/components/Footer";
import { StockResearchWorkspace } from "@/components/features/stock-research-workspace";

const OpenStockCtx = createContext<(symbol: string) => void>(() => {});
/** Open the global stock-research overlay from any page inside AppShell. */
export const useOpenStock = () => useContext(OpenStockCtx);

export default function AppShell({
  current,
  children,
  refreshTime,
}: {
  current: string;
  children: ReactNode;
  refreshTime?: string;
}) {
  const [workspaceSymbol, setWorkspaceSymbol] = useState<string | null>(null);

  return (
    <div style={{ background: "#FAFAF8", minHeight: "100vh", fontFamily: "'DM Sans',sans-serif", color: "#111827" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&family=DM+Sans:wght@300;400;500;600&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        ::-webkit-scrollbar{width:4px;height:4px;}::-webkit-scrollbar-thumb{background:#d1d5db;border-radius:2px;}
        input,button,textarea{outline:none;font-family:inherit;}
        @keyframes fade{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
        .fade{animation:fade .3s ease}
      `}</style>

      <AppNav current={current} onSearchSelect={(s) => setWorkspaceSymbol(s)} refreshTime={refreshTime} />

      <OpenStockCtx.Provider value={(s) => setWorkspaceSymbol(s)}>
        {children}
      </OpenStockCtx.Provider>

      {workspaceSymbol && (
        <StockResearchWorkspace symbol={workspaceSymbol} onClose={() => setWorkspaceSymbol(null)} />
      )}

      <Footer />
    </div>
  );
}
