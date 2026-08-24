// lib/credentials-auth.ts
import bcrypt from "bcryptjs";
import { d1First } from "@/lib/d1";

export const DUMMY_HASH = "$2b$12$xUjX9huLeJir.2jSux66c.yYe7L1uPZRt93uuVoHya/9/VrO8bM5u";

export type CredentialUser = { id: string; email: string; name: string };

// Retained for unit tests: tests can inject the historical tagged-template mock.
export type SqlClient = (
  strings: TemplateStringsArray,
  ...values: unknown[]
) => Promise<Record<string, unknown>[]>;

export async function verifyPassword(
  emailInput: string,
  password: string,
  sql?: SqlClient,
): Promise<CredentialUser | null> {
  const email = emailInput.toLowerCase().trim();
  if (!email || !password) return null;
  try {
    let hash: string | null = null;
    if (sql) {
      const rows = await sql`SELECT password_hash FROM allowed_users WHERE email = ${email} LIMIT 1`;
      hash = (rows[0]?.password_hash as string | null | undefined) ?? null;
    } else {
      const row = await d1First<{ password_hash: string | null }>(
        "SELECT password_hash FROM allowed_users WHERE email=? LIMIT 1",
        [email],
      );
      hash = row?.password_hash ?? null;
    }
    // Constant-work comparison prevents allowlist membership timing leakage.
    const ok = await bcrypt.compare(password, hash || DUMMY_HASH);
    if (!hash || !ok) return null;
    return { id: email, email, name: email };
  } catch {
    return null;
  }
}
