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
  { v: "ipo",           l: "IPO",           href: "/ipo",            e: "⚡" },
  // Today removed from nav — Domestic + Global markets now live on the IPO page.
  // { v: "today",         l: "Today",         href: "/today",          e: "🏠" },
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
    background: active ? "#EFF6FF" : "transparent",
    color: active ? "#2563EB" : "#6B7280",
    fontFamily: "'IBM Plex Mono',monospace", fontSize: 11,
    fontWeight: active ? 600 : 400, textDecoration: "none",
    cursor: "pointer", transition: "all .12s", whiteSpace: "nowrap" as const,
  });

  return (
    <div style={{ background: "#EEF2F8", borderBottom: "1px solid #DCE3EE", padding: "0 16px", display: "flex", alignItems: "center", gap: 12, height: 64, position: "sticky", top: 0, zIndex: 300, overflow: "visible" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ background: "transparent", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <img src="/aa-logo-emblem.png" alt="AA Capital" style={{ width: 50, height: 50, objectFit: "contain" }} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", lineHeight: 1.14, marginLeft: 3 }}>
          <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 800, fontSize: 20, color: "#0F1B2D", letterSpacing: "-0.3px" }}>AACapital</div>
          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 12, color: "#B8860B", letterSpacing: "1.6px", fontWeight: 600 }}>WHERE MARKETS MAKE SENSE.</div>
        </div>
      </div>
      <div style={{ flex: 1 }} />
      <div style={{ width: 300, marginRight: 6, position: "relative", zIndex: 99999 }}>
        <IpoSearch onSelect={onSearchSelect} placeholder="Search IPO..." />
      </div>
      {TABS.map(({ v, l, href, e }) => {
        const active = current === v;
        return (
          <Link key={v} href={href} prefetch={false} style={tabStyle(active)}>
            <span style={{ fontSize: 13 }}>{e}</span>{l}
          </Link>
        );
      })}
      {isAdmin && (
        <Link href="/dashboard/admin" prefetch={false} style={tabStyle(current === "admin")}>
          <span style={{ fontSize: 13 }}>🛠</span>Admin
        </Link>
      )}
      {refreshTime && <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 11, color: "#374151" }}>↻{refreshTime}</div>}
    </div>
  );
}
