// lib/credentials-auth.ts
// Password verification for the Credentials login provider, extracted from auth.ts
// so it can be unit-tested with a mocked neon client (no live DB) and so the
// timing-safety logic lives in exactly one place.
import bcrypt from "bcryptjs";
import { neon } from "@neondatabase/serverless";

// A real bcrypt hash (12 rounds) of a fixed throwaway string. When no allowed_users
// row exists — or its password_hash is NULL — we STILL run bcrypt.compare against
// this constant, so an unknown / non-allowlisted email costs the same ~250ms as a
// real one. Without it, `!hash → return null` answers in ~1ms and response time
// reveals which emails are allowlisted (enumeration). Must stay 12 rounds so its
// cost matches hashes produced by set-password.mjs.
export const DUMMY_HASH = "$2b$12$xUjX9huLeJir.2jSux66c.yYe7L1uPZRt93uuVoHya/9/VrO8bM5u";

export type CredentialUser = { id: string; email: string; name: string };

// Minimal shape of the neon tagged-template client — enough to inject a mock in tests.
export type SqlClient = (
  strings: TemplateStringsArray,
  ...values: unknown[]
) => Promise<Record<string, unknown>[]>;

function liveSql(): SqlClient {
  return neon(process.env.DATABASE_URL!) as unknown as SqlClient;
}

// The allowlist IS the gate: allowed_users is the only lookup, so a non-allowlisted
// email has no row and no correct password can let it in. `sql` is injected (defaults
// to the live client, evaluated per-call so a missing env never throws at import) so
// tests pass a mock and never touch a database.
export async function verifyPassword(
  emailInput: string,
  password: string,
  sql: SqlClient = liveSql(),
): Promise<CredentialUser | null> {
  const email = emailInput.toLowerCase().trim();
  if (!email || !password) return null;
  try {
    const rows = await sql`SELECT password_hash FROM allowed_users WHERE email = ${email} LIMIT 1`;
    const hash = (rows[0]?.password_hash as string | null | undefined) ?? null;
    // Always compare — even with no row / NULL hash, against DUMMY_HASH — to keep
    // the response constant-time regardless of allowlist membership.
    const ok = await bcrypt.compare(password, hash || DUMMY_HASH);
    if (!hash || !ok) return null;
    return { id: email, email, name: email };
  } catch {
    // Pre-migration (password_hash column absent) or a DB hiccup: fail the password
    // path CLOSED. Google is a separate provider and is unaffected.
    return null;
  }
}
