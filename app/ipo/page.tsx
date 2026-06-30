"use client";
// app/ipo/page.tsx — IPO route, now on the shared AppShell.

import { useState } from "react";
import AppShell from "@/components/app-shell/AppShell";
import { IpoListingDashboard } from "@/components/features/ipo-listing-dashboard";
import { IpoPlaybookScreen } from "@/components/features/ipo-playbook";

const SUBTABS = [
  { id: "command",  label: "⚡ Command Center" },
  { id: "playbook", label: "🎯 Quick Profit Playbook" },
];

function IpoBody() {
  const [ipoView, setIpoView] = useState("command");
  return (
    <div>
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
    </div>
  );
}

export default function IpoRoute() {
  return (
    <AppShell current="ipo">
      <IpoBody />
    </AppShell>
  );
}
