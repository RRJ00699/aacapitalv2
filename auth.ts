// auth.ts  (project root)
// Login gate, three rings — designed so the owner can NEVER be locked out:
//   1. env ALLOWED_EMAILS / ADMIN_EMAILS  -> always in, zero DB involved
//   2. D1 allowed_users                    -> people approved on the fly
//   3. unknown email                       -> D1 access_requests + ntfy
// DB failure: ring-1 users unaffected; strangers fail CLOSED.
import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import Credentials from "next-auth/providers/credentials";
import { verifyPassword } from "@/lib/credentials-auth";
import { d1First, d1Run } from "@/lib/d1";

function emailList(v: string | undefined) {
  return (v ?? "").split(",").map((e) => e.trim().toLowerCase()).filter(Boolean);
}

async function dbAllowedOrRequest(email: string, name: string | null): Promise<boolean> {
  try {
    const hit = await d1First<{ ok: number }>("SELECT 1 AS ok FROM allowed_users WHERE email=? LIMIT 1", [email]);
    if (hit) return true;
    await d1Run(
      `INSERT INTO access_requests(email,name,status,requested_at)
       VALUES(?,?, 'pending', CURRENT_TIMESTAMP)
       ON CONFLICT(email) DO UPDATE SET
         name=excluded.name,
         requested_at=CURRENT_TIMESTAMP,
         status=CASE WHEN access_requests.status='denied' THEN 'denied' ELSE 'pending' END`,
      [email, name],
    );
    const topic = process.env.NTFY_TOPIC;
    if (topic) {
      await fetch(`https://ntfy.sh/${topic}`, {
        method: "POST",
        headers: { Title: "AACapital access request", Priority: "high",
          Click: "https://www.aacapitalprivatelimited.com/dashboard/access" },
        body: `${name ?? "Someone"} <${email}> is requesting access. Tap to approve.`,
      }).catch(() => {});
    }
  } catch { /* strangers fail closed; ring-1 never reaches here */ }
  return false;
}

export const { handlers, signIn, signOut, auth } = NextAuth(() => ({
  trustHost: true,
  secret: process.env.AUTH_SECRET,
  providers: [
    Google({
      clientId: process.env.AUTH_GOOGLE_ID,
      clientSecret: process.env.AUTH_GOOGLE_SECRET,
    }),
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
      if (account?.provider === "credentials") return true;
      const email = user.email?.toLowerCase();
      if (!email) return false;
      const ALLOWED = emailList(process.env.ALLOWED_EMAILS);
      const ADMINS = emailList(process.env.ADMIN_EMAILS);
      if (ADMINS.includes(email) || ALLOWED.includes(email)) return true;
      if (ALLOWED.length === 0 && ADMINS.length === 0) return true;
      if (await dbAllowedOrRequest(email, user.name ?? null)) return true;
      return "/login?requested=1";
    },
    authorized({ auth }) {
      return !!auth?.user;
    },
  },
}));
