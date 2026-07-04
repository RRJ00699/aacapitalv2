// lib/admin.ts — admin gate for the job console (new, self-contained).
// Admins are a subset of the family login allowlist. Set ADMIN_EMAILS in Vercel
// (comma-separated). If unset it falls back to ALLOWED_EMAILS so you can't lock
// yourself out — but set ADMIN_EMAILS to just your own email for a real gate.
import { auth } from "@/auth";

const ADMINS = (process.env.ADMIN_EMAILS ?? process.env.ALLOWED_EMAILS ?? "")
  .split(",").map((e) => e.trim().toLowerCase()).filter(Boolean);

export function isAdminEmail(email?: string | null): boolean {
  const e = email?.toLowerCase();
  // deny-by-default: empty allowlist => nobody is admin
  return !!e && ADMINS.length > 0 && ADMINS.includes(e);
}

/** Returns the admin's email if the current session is an admin, else null. */
export async function getAdminEmail(): Promise<string | null> {
  const session = await auth();
  const email = session?.user?.email ?? null;
  return isAdminEmail(email) ? email!.toLowerCase() : null;
}
