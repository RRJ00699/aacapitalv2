"use client";
// app/today/page.tsx — Today route (Phase 2). Default landing page.

import AppShell, { useOpenStock } from "@/components/app-shell/AppShell";
import { TodayScreen } from "@/components/features/today-screen";

function TodayBody() {
  const openStock = useOpenStock();
  return <TodayScreen onStockSelect={openStock} />;
}

export default function TodayRoute() {
  return (
    <AppShell current="today">
      <TodayBody />
    </AppShell>
  );
}
