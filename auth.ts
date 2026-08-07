// auth.ts  (project root)
// Login gate, three rings — designed so the owner can NEVER be locked out:
//   1. env ALLOWED_EMAILS / ADMIN_EMAILS  -> always in, zero DB involved (family unchanged)
//   2. allowed_users table                 -> people you approved on the fly
//   3. unknown email                       -> recorded in access_requests + push
//      notification (ntfy) -> you approve at /dashboard/access -> next sign-in works.
// DB failure: ring-1 users unaffected (never query); strangers fail CLOSED.
import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import Credentials from "next-auth/providers/credentials";
import { neon } from "@neondatabase/serverless";
import { verifyPassword } from "@/lib/credentials-auth";

function emailList(v: string | undefined) {
  return (v ?? "").split(",").map((e) => e.trim().toLowerCase()).filter(Boolean);
}

async function dbAllowedOrRequest(email: string, name: string | null): Promise<boolean> {
  try {
    const sql = neon(process.env.DATABASE_URL!);
    const hit = await sql`SELECT 1 FROM allowed_users WHERE email = ${email} LIMIT 1`;
    if (hit.length) return true;
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
    // Username/password — sits ALONGSIDE Google, never in front of it. The same
    // allowlist gates here (see lib/credentials-auth.ts): allowed_users IS the
    // lookup, so a non-allowlisted email has no row and a correct password can
    // never match. A NULL password_hash means the user is Google-only.
    Credentials({
      name: "Password",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      authorize: (creds) =>
        verifyPassword(String(creds?.email ?? ""), String(creds?.password ?? "")),
    }),
  ],
  session: { strategy: "jwt" },
  pages: { signIn: "/login", error: "/login" },
  callbacks: {
    async signIn({ user, account }) {
      // Credentials logins are already fully gated in authorize() above (email must
      // exist in allowed_users with a matching bcrypt hash), so skip the Google
      // discovery path — no bogus access_request / ntfy for a password sign-in.
      if (account?.provider === "credentials") return true;
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
