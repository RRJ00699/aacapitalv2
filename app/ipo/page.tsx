"use client";
// app/ipo/page.tsx
// Real IPO route (Phase 1 of the routing migration). Replaces the old redirect("/")
// stub. Self-contained: shared nav + IPO sub-nav + the live dashboard + the global
// stock-research overlay (so search works here too). Has its own URL → refresh stays
// here, and its own render boundary → no whole-app re-hydration flash.

import { useState } from "react";
import AppNav from "@/components/app-shell/AppNav";
import Footer from "@/components/Footer";
import { StockResearchWorkspace } from "@/components/features/stock-research-workspace";
import { IpoListingDashboard } from "@/components/features/ipo-listing-dashboard";
import { IpoPlaybookScreen } from "@/components/features/ipo-playbook";

const SUBTABS = [
  { id: "command",  label: "⚡ Command Center" },
  { id: "playbook", label: "🎯 Quick Profit Playbook" },
];

export default function IpoRoute() {
  const [workspaceSymbol, setWorkspaceSymbol] = useState<string | null>(null);
  const [ipoView, setIpoView] = useState("command");

  return (
    <div style={{ background: "#FAFAF8", minHeight: "100vh", fontFamily: "'DM Sans',sans-serif", color: "#111827" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&family=DM+Sans:wght@300;400;500;600&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        ::-webkit-scrollbar{width:4px;height:4px;}::-webkit-scrollbar-thumb{background:#d1d5db;border-radius:2px;}
        input,button,textarea{outline:none;font-family:inherit;}
      `}</style>

      <AppNav current="ipo" onSearchSelect={(s) => setWorkspaceSymbol(s)} />

      {/* IPO sub-nav */}
      <div style={{ background: "#fff", borderBottom: "1px solid #E5E7EB", padding: "8px 20px", display: "flex", gap: 6, position: "sticky", top: 64, zIndex: 9 }}>
        {SUBTABS.map((t) => (
          <button key={t.id} onClick={() => setIpoView(t.id)}
            style={{
              padding: "5px 12px", borderRadius: 20,
              border: `1px solid ${ipoView === t.id ? "#2563EB" : "#E5E7EB"}`,
              background: ipoView === t.id ? "#EFF6FF" : "transparent",
              color: ipoView === t.id ? "#2563EB" : "#64748B",
              fontSize: 12, fontWeight: ipoView === t.id ? 700 : 400, cursor: "pointer",
            }}>
            {t.label}
          </button>
        ))}
      </div>

      {ipoView === "command"  && <IpoListingDashboard />}
      {ipoView === "playbook" && <IpoPlaybookScreen />}

      {workspaceSymbol && (
        <StockResearchWorkspace symbol={workspaceSymbol} onClose={() => setWorkspaceSymbol(null)} />
      )}

      <Footer />
    </div>
  );
}
