"use client";
// components/app-shell/AppNav.tsx
// Shared top nav for the routed app. During migration, IPO is a real route (/ipo);
// not-yet-migrated tabs link to /#<tab> and are restored by AACapitalApp's hash sync.
// As each tab becomes a real route, flip its href from "/#x" to "/x".

import Link from "next/link";
import { TrendingUp, Zap, Home, Activity, Briefcase, Star } from "lucide-react";
import { StockSearch } from "@/components/features/stock-search";

const TABS = [
  { v: "today",         l: "Today",         href: "/",               icon: Home },
  { v: "stocks",        l: "Stocks",        href: "/#stocks",        icon: TrendingUp },
  { v: "opportunities", l: "Opportunities", href: "/#opportunities", icon: Activity },
  { v: "watchlist",     l: "Watch",         href: "/#watchlist",     icon: Star },
  { v: "ipo",           l: "IPO",           href: "/ipo",            icon: Zap },        // real route
  { v: "portfolio",     l: "Portfolio",     href: "/#portfolio",     icon: Briefcase },
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
  return (
    <div style={{ background: "#FFFFFF", borderBottom: "1px solid #F0EDE8", padding: "0 16px", display: "flex", alignItems: "center", gap: 12, height: 64, position: "sticky", top: 0, zIndex: 300, overflow: "visible" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <img src="/aa-logo-emblem.png" alt="AA Capital" style={{ width: 54, height: 54, objectFit: "contain" }} />
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", lineHeight: 1.14, marginLeft: 3 }}>
          <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 800, fontSize: 20, color: "#0F1B2D", letterSpacing: "-0.3px" }}>AACapital</div>
          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 12, color: "#B8860B", letterSpacing: "1.6px", fontWeight: 600 }}>WHERE MARKETS MAKE SENSE.</div>
        </div>
      </div>
      <div style={{ flex: 1 }} />
      <div style={{ width: 320, marginRight: 6, position: "relative", zIndex: 99999 }}>
        <StockSearch onSelect={onSearchSelect} placeholder="Search stock..." />
      </div>
      {TABS.map(({ v, l, href, icon: Icon }) => {
        const active = current === v;
        return (
          <Link key={v} href={href} prefetch={false}
            style={{
              display: "flex", alignItems: "center", gap: 5,
              padding: "5px 11px", borderRadius: 7, border: "none",
              background: active ? "#EFF6FF" : "transparent",
              color: active ? "#2563EB" : "#6B7280",
              fontFamily: "'IBM Plex Mono',monospace", fontSize: 11,
              fontWeight: active ? 600 : 400, textDecoration: "none",
              cursor: "pointer", transition: "all .12s", whiteSpace: "nowrap",
            }}>
            <Icon size={13} />{l}
          </Link>
        );
      })}
      {refreshTime && <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 11, color: "#374151" }}>↻{refreshTime}</div>}
    </div>
  );
}
