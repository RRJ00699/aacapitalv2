"use client";
// app/research/page.tsx
import { useState } from "react";
import AppShell from "@/components/app-shell/AppShell";
import SubTabs from "@/components/app-shell/SubTabs";
import { RoiTracker } from "@/components/features/roi-tracker";
import { BacktestScreen } from "@/components/features/backtest-screen";
import { TradeJournalScreen } from "@/components/features/sprint8-features";
import { SettingsTab } from "@/components/features/settings-tab";

const TABS = [
  { id: "roi",      label: "📊 ROI Tracker" },
  { id: "backtest", label: "Backtest" },
  { id: "journal",  label: "Trade journal" },
  { id: "settings", label: "Settings" },
];

function Body() {
  const [v, setV] = useState("roi");
  return (
    <div>
      <SubTabs tabs={TABS} active={v} onChange={setV} />
      {v === "roi"      && <RoiTracker />}
      {v === "backtest" && <BacktestScreen />}
      {v === "journal"  && <TradeJournalScreen />}
      {v === "settings" && <SettingsTab />}
    </div>
  );
}
export default function ResearchRoute() {
  return <AppShell current="research"><Body /></AppShell>;
}
