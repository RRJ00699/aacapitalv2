// app/uat/ops-preview/page.tsx — FIXTURE-ONLY preview harness for owner-check
// screenshots of the Admin Operations overview and its screen states. It renders
// ONLY when the UAT fixture server is active (UAT_FIXTURE_JSON set) or in dev;
// in production it 404s. It exposes no secrets — OperationsOverview reads only
// the KV-backed /api/ipo-command snapshot (same data the Command Center uses),
// so this harness cannot leak anything the admin console would. Its sole purpose
// is to let Playwright drive loading / degraded / unavailable / healthy states
// (via route mocking) without a signed-in admin session.
import { notFound } from "next/navigation";
import OperationsOverview from "../../dashboard/admin/OperationsOverview";
import ThemeToggle from "@/components/ui/ThemeToggle";

export const dynamic = "force-dynamic";

export default function OpsPreviewPage() {
  const enabled = !!process.env.UAT_FIXTURE_JSON || process.env.NODE_ENV !== "production";
  if (!enabled) notFound();
  return (
    <div style={{ padding: "20px 24px", background: "var(--c-bg, var(--t-bg))", minHeight: "100vh" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
        <h1 style={{ fontFamily: "var(--f-display)", fontSize: 18, fontWeight: 800, color: "var(--t-text)", margin: 0 }}>
          Admin · Operations (preview harness)
        </h1>
        <ThemeToggle compact />
      </div>
      <OperationsOverview />
    </div>
  );
}
