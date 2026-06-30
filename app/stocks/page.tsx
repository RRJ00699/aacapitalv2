"use client";
// app/stocks/page.tsx
import AppShell, { useOpenStock } from "@/components/app-shell/AppShell";
import StockScorecardGrid from "@/components/features/StockScorecardGrid";

function Body() {
  const open = useOpenStock();
  return <StockScorecardGrid onStockSelect={open} />;
}
export default function StocksRoute() {
  return <AppShell current="stocks"><Body /></AppShell>;
}
