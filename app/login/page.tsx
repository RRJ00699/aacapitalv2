// app/login/page.tsx
"use client";
import { signIn } from "next-auth/react";

export default function Login() {
  return (
    <main style={{ minHeight: "100dvh", display: "grid", placeItems: "center" }}>
      <div style={{ textAlign: "center" }}>
        <h1 style={{ marginBottom: 16 }}>AACapital</h1>
        <button
          onClick={() => signIn("google", { callbackUrl: "/" })}
          style={{ padding: "10px 18px", borderRadius: 8, cursor: "pointer" }}
        >
          Sign in with Google
        </button>
      </div>
    </main>
  );
}
