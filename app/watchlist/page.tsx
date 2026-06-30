"use client";
// app/watchlist/page.tsx
import AppShell, { useOpenStock } from "@/components/app-shell/AppShell";
import { WatchlistScreen } from "@/components/features/watchlist-screen";

function Body() {
  const open = useOpenStock();
  return <WatchlistScreen onStockSelect={open} />;
}
export default function WatchlistRoute() {
  return <AppShell current="watchlist"><Body /></AppShell>;
}
