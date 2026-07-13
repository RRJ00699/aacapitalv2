// app/dashboard/tracker/page.tsx
// Private distraction tracker. Server gate (admin only), then the client UI.
import { redirect } from "next/navigation";
import { getAdminEmail } from "@/lib/admin";
import TrackerClient from "./TrackerClient";
import AppShell from "@/components/app-shell/AppShell";

export const dynamic = "force-dynamic";

export default async function TrackerPage() {
  const admin = await getAdminEmail();
  if (!admin) redirect("/dashboard/ipo");
  return (
    <AppShell current="tracker">
      <TrackerClient />
    </AppShell>
  );
}
