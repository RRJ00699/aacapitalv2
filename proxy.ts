// proxy.ts  (Next.js 16). Protects PAGES *and* data APIs.
// Auth routes and cron/webhook routes stay open (cron is secured by its own secret header).
// Next 16.2.7 has the middleware-bypass CVE-2025-29927 patched, so edge auth here is solid;
// lib/api-guard.ts remains available for belt-and-suspenders on the most sensitive routes.
export { auth as proxy } from "./auth";

export const config = {
  matcher: [
    // everything except: auth endpoints, the cron webhook, zerodha oauth callback, login page, static assets
    "/((?!api/auth|api/cron|login|_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|ico|webp)$).*)",
  ],
};
