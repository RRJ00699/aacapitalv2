"use client";
// app/today/page.tsx — Today route. Markets-only (Domestic + Global).

import AppShell from "@/components/app-shell/AppShell";
import { TodayScreen } from "@/components/features/today-screen";

export default function TodayRoute() {
  return (
    <AppShell current="today">
      <TodayScreen onStockSelect={() => {}} />
    </AppShell>
  );
}
