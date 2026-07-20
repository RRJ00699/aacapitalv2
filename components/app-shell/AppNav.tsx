"use client";
// components/app-shell/AppNav.tsx
// Shared top nav for the routed app. During migration, IPO is a real route (/ipo);
// not-yet-migrated tabs link to /#<tab> and are restored by AACapitalApp's hash sync.
// As each tab becomes a real route, flip its href from "/#x" to "/x".
//
// Admin tab: appended only when /api/admin/check says the signed-in user is an admin.
// Non-admins never see it; the /dashboard/admin page also bounces them server-side.

import { useEffect, useState } from "react";
import { IpoSearch } from "@/components/features/ipo-search";
import Link from "next/link";

// IPO Power House — nav trimmed to the IPO engine. Today kept beside it.
// but their routes still exist — restore a line here to bring one back.
const TABS = [
  { v: "ipo",           l: "IPO",           href: "/ipo" },
  // Today removed from nav — Domestic + Global markets now live on the IPO page.
];

export default function AppNav({
  current,
  onSearchSelect,
  refreshTime,
}: {
  current: string;
  onSearchSelect: (symbol: string) => void;
  refreshTime?: string;
}) {
  const [isAdmin, setIsAdmin] = useState(false);
  useEffect(() => {
    let alive = true;
    fetch("/api/admin/check", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => { if (alive) setIsAdmin(!!j.admin); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  const tabStyle = (active: boolean) => ({
    display: "flex" as const, alignItems: "center" as const, gap: 5,
    padding: "5px 11px", borderRadius: 7, border: "none",
    background: active ? "var(--t-amberBg)" : "transparent",
    color: active ? "var(--t-gold)" : "var(--t-meta)",
    fontFamily: "'IBM Plex Mono',monospace", fontSize: 11,
    fontWeight: active ? 600 : 400, textDecoration: "none",
    cursor: "pointer", transition: "all .12s", whiteSpace: "nowrap" as const,
  });

  return (
    <div style={{ background: "var(--t-header)", borderBottom: "1px solid var(--t-border)", padding: "0 16px", display: "flex", alignItems: "center", gap: 12, height: 64, position: "sticky", top: 0, zIndex: 300, overflow: "visible" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <img src="/aa-logo-full.png" alt="AA Capital" style={{ height: 40, width: "auto", objectFit: "contain", flexShrink: 0 }} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", lineHeight: 1.14, marginLeft: 3 }}>
          <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 800, fontSize: 20, color: "var(--t-headerText)", letterSpacing: "-0.3px" }}>AACapital</div>
          <div className="nav-tagline" style={{ fontFamily: "var(--f-mono)", fontSize: 11, color: "var(--t-gold)", letterSpacing: "1.4px", fontWeight: 600 }}>WHERE MARKETS MAKE SENSE.</div>
        </div>
      </div>
      <div style={{ flex: 1 }} />
      <div style={{ flex: "0 1 300px", minWidth: 110, marginRight: 6, position: "relative", zIndex: 99999 }}>
        <IpoSearch onSelect={onSearchSelect} placeholder="Search IPO..." />
      </div>
      {TABS.map(({ v, l, href }) => {
        const active = current === v;
        return (
          <Link key={v} href={href} prefetch={false} style={tabStyle(active)}>
            {l}
          </Link>
        );
      })}
      {isAdmin && (
        <Link href="/dashboard/admin" prefetch={false} style={tabStyle(current === "admin")}>
          Admin
        </Link>
      )}
      {refreshTime && <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 11, color: "var(--t-dim)" }}>↻{refreshTime}</div>}
    </div>
  );
}
