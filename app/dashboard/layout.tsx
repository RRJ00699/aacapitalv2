// app/dashboard/layout.tsx
// Server-side auth gate for every /dashboard/* page. Replaces proxy.ts page
// protection (proxy.ts used Node-runtime middleware, which Cloudflare Workers
// can't run). auth() uses @neondatabase/serverless + JWT — edge-compatible.
// Logged-out visitors are redirected to /login before any dashboard page renders.
import { redirect } from "next/navigation"
import { auth } from "@/auth"

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  // UAT fixture mode: the fixture env replaces the DB entirely (lib/db), so
  // opening the page gate here can never expose real data. Guard-tested.
  if (!process.env.UAT_FIXTURE_JSON) {
    const session = await auth()
    if (!session?.user) redirect("/login")
  }
  return <>{children}</>
}
