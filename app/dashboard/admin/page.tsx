// app/dashboard/admin/page.tsx
// Server gate, then render the client console. The page is already behind the
// login wall (proxy.ts); this adds the admin-email gate and bounces non-admins.
import { redirect } from "next/navigation";
import { getAdminEmail } from "@/lib/admin";
import AdminConsoleClient from "./AdminConsoleClient";
import AppShell from "@/components/app-shell/AppShell";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const admin = await getAdminEmail();
  if (!admin) redirect("/dashboard/ipo2");
  return (
    <AppShell current="admin">
      <AdminConsoleClient adminEmail={admin} />
    </AppShell>
  );
}
