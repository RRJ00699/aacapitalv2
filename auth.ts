// auth.ts  → project root (C:\aacapital-v2\auth.ts)
import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

// family allowlist, comma-separated in env: ALLOWED_EMAILS="a@gmail.com,b@gmail.com"
const ALLOWED = (process.env.ALLOWED_EMAILS ?? "")
  .split(",").map((e) => e.trim().toLowerCase()).filter(Boolean);

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [Google], // AUTH_GOOGLE_ID / AUTH_GOOGLE_SECRET auto-inferred from env
  session: { strategy: "jwt" },
  pages: { signIn: "/login", error: "/login" },
  callbacks: {
    // gate at login: only allowlisted family emails get in
    signIn({ user }) {
      const email = user.email?.toLowerCase();
      return !!email && (ALLOWED.length === 0 || ALLOWED.includes(email));
    },
    // used by proxy.ts to protect pages
    authorized({ auth }) {
      return !!auth?.user;
    },
  },
});
