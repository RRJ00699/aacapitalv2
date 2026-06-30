"use client";
// app/portfolio/page.tsx
import { useState } from "react";
import AppShell, { useOpenStock } from "@/components/app-shell/AppShell";
import SubTabs from "@/components/app-shell/SubTabs";
import { RoiTracker } from "@/components/features/roi-tracker";
import { PortfolioDoctor } from "@/components/features/portfolio-doctor";
import { PortfolioTab } from "@/components/features/portfolio-tab";
import { PriceAlertsScreen } from "@/components/features/price-alerts-screen";
import { CapitalDeploymentOptimizer } from "@/components/features/sprint8-features";

const TABS = [
  { id: "roi",      label: "📊 ROI Tracker" },
  { id: "doctor",   label: "Portfolio doctor" },
  { id: "holdings", label: "Holdings" },
  { id: "alerts",   label: "Price alerts" },
  { id: "deploy",   label: "Deploy capital" },
];

function Body() {
  const open = useOpenStock();
  const [v, setV] = useState("doctor");
  return (
    <div>
      <SubTabs tabs={TABS} active={v} onChange={setV} />
      {v === "roi"      && <RoiTracker />}
      {v === "doctor"   && <PortfolioDoctor simple={false} onStockSelect={open} />}
      {v === "holdings" && <PortfolioTab />}
      {v === "alerts"   && <PriceAlertsScreen onStockSelect={open} />}
      {v === "deploy"   && <CapitalDeploymentOptimizer />}
    </div>
  );
}
export default function PortfolioRoute() {
  return <AppShell current="portfolio"><Body /></AppShell>;
}
