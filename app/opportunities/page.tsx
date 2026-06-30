"use client";
// app/opportunities/page.tsx
import { useState } from "react";
import AppShell, { useOpenStock } from "@/components/app-shell/AppShell";
import SubTabs from "@/components/app-shell/SubTabs";
import OpportunitiesScreener from "@/components/features/OpportunitiesScreener";
import RadarScreen from "@/components/features/RadarScreen";
import QualityValueScreen from "@/components/features/QualityValueScreen";
import TechnicalScreen from "@/components/features/TechnicalScreen";
import { MultibaggerDiscovery } from "@/components/features/multibagger-discovery";
import { BreakoutWatchScreen } from "@/components/features/breakout-watch";
import { EarningsScreen } from "@/components/features/earnings-screen";
import EarningsBeatsScreen from "@/components/features/EarningsBeatsScreen";
import { SectorRotationScreen } from "@/components/features/sector-rotation";

const TABS = [
  { id: "screener",       label: "🎯 Screener" },
  { id: "radar",          label: "📡 Radar" },
  { id: "quality-value",  label: "💎 Quality + Value" },
  { id: "rel-strength",   label: "📈 Rel. Strength" },
  { id: "multibagger",    label: "Multibagger discovery" },
  { id: "breakout-watch", label: "🔭 Breakout Watch" },
  { id: "earnings",       label: "Earnings" },
  { id: "earnings-beats", label: "🔥 Earnings Beats" },
  { id: "sector",         label: "Sector rotation" },
];

function Body() {
  const open = useOpenStock();
  const [v, setV] = useState("screener");
  return (
    <div>
      <SubTabs tabs={TABS} active={v} onChange={setV} />
      {v === "screener"       && <OpportunitiesScreener onStockSelect={open} />}
      {v === "radar"          && <RadarScreen onStockSelect={open} />}
      {v === "quality-value"  && <QualityValueScreen onStockSelect={open} />}
      {v === "rel-strength"   && <TechnicalScreen onStockSelect={open} />}
      {v === "multibagger"    && <MultibaggerDiscovery simple={false} onStockSelect={open} />}
      {v === "breakout-watch" && <BreakoutWatchScreen simple={false} onStockSelect={open} />}
      {v === "earnings"       && <EarningsScreen onStockSelect={open} />}
      {v === "earnings-beats" && <EarningsBeatsScreen onStockSelect={open} />}
      {v === "sector"         && <SectorRotationScreen />}
    </div>
  );
}
export default function OpportunitiesRoute() {
  return <AppShell current="opportunities"><Body /></AppShell>;
}
