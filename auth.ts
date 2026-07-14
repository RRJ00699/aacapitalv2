// auth.ts  (project root)
// Login gate, three rings — designed so the owner can NEVER be locked out:
//   1. env ALLOWED_EMAILS / ADMIN_EMAILS  -> always in, zero DB involved (family unchanged)
//   2. allowed_users table                 -> people you approved on the fly
//   3. unknown email                       -> recorded in access_requests + push
//      notification (ntfy) -> you approve at /dashboard/access -> next sign-in works.
// DB failure: ring-1 users unaffected (never query); strangers fail CLOSED.
import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import { neon } from "@neondatabase/serverless";

function emailList(v: string | undefined) {
  return (v ?? "").split(",").map((e) => e.trim().toLowerCase()).filter(Boolean);
}

async function dbAllowedOrRequest(email: string, name: string | null): Promise<boolean> {
  try {
    const sql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);
    const hit = await sql`SELECT 1 FROM allowed_users WHERE email = ${email} LIMIT 1`;
    if (hit.length) return true;
    await sql`CREATE TABLE IF NOT EXISTS access_requests (
      email TEXT PRIMARY KEY, name TEXT, status TEXT NOT NULL DEFAULT 'pending',
      requested_at TIMESTAMPTZ DEFAULT now(), decided_at TIMESTAMPTZ, decided_by TEXT)`;
    await sql`INSERT INTO access_requests (email, name)
              VALUES (${email}, ${name})
              ON CONFLICT (email) DO UPDATE
              SET requested_at = now(),
                  status = CASE WHEN access_requests.status = 'denied'
                                THEN 'denied' ELSE 'pending' END`;
    let topic = process.env.NTFY_TOPIC;
    if (!topic) {
      const t = await sql`SELECT value FROM platform_config WHERE key='ntfy_topic' LIMIT 1`;
      topic = t[0]?.value as string | undefined;
    }
    if (topic) {
      await fetch(`https://ntfy.sh/${topic}`, {
        method: "POST",
        headers: { Title: "AACapital access request", Priority: "high",
          Click: "https://www.aacapitalprivatelimited.com/dashboard/access" },
        body: `${name ?? "Someone"} <${email}> is requesting access. Tap to approve.`,
      }).catch(() => {});
    }
  } catch { /* strangers fail closed; family never reaches here */ }
  return false;
}

export const { handlers, signIn, signOut, auth } = NextAuth(() => ({
  trustHost: true, // required on Cloudflare Workers (non-Vercel host) — else "Configuration" error
  secret: process.env.AUTH_SECRET, // explicit — Workers env auto-detection can miss it
  providers: [
    Google({
      clientId: process.env.AUTH_GOOGLE_ID,
      clientSecret: process.env.AUTH_GOOGLE_SECRET,
    }),
  ],
  session: { strategy: "jwt" },
  pages: { signIn: "/login", error: "/login" },
  callbacks: {
    async signIn({ user }) {
      const email = user.email?.toLowerCase();
      if (!email) return false;
      const ALLOWED = emailList(process.env.ALLOWED_EMAILS);
      const ADMINS = emailList(process.env.ADMIN_EMAILS);
      if (ADMINS.includes(email) || ALLOWED.includes(email)) return true;   // ring 1
      if (ALLOWED.length === 0 && ADMINS.length === 0) return true;         // legacy open mode
      if (await dbAllowedOrRequest(email, user.name ?? null)) return true;  // ring 2
      return "/login?requested=1";                                          // ring 3
    },
    authorized({ auth }) {
      return !!auth?.user;
    },
  },
}));
