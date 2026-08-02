// set-password.mjs — set (or reset) a user's password for the username/password
// login provider. Hashes with bcryptjs and upserts allowed_users(email,
// password_hash), which ALSO allowlists the user (ring 2). The plaintext password
// is read from a hidden TTY prompt — never from argv, never echoed, never logged.
//
// Targets whatever DATABASE_URL is set in the environment. It prints the host and
// refuses to run if unset, so you consciously pick the DB (same safety pattern as
// migrate_auth.py). Because production's DATABASE_URL still points at ep-small-river
// while local dev uses ep-misty-meadow, set the password on EACH DB the worker may
// read:
//
//   # PowerShell — production DB (small-river), so live login works:
//   $env:DATABASE_URL="postgres://...ep-small-river.../..."; npm run set-password -- --email you@example.com
//   # and the local/V2 DB (misty-meadow):
//   $env:DATABASE_URL="postgres://...ep-misty-meadow.../..."; npm run set-password -- --email you@example.com
//
import readline from "node:readline";
import bcrypt from "bcryptjs";
import { neon } from "@neondatabase/serverless";

const MIN_LEN = 8;
const BCRYPT_ROUNDS = 12;

function argEmail() {
  const i = process.argv.indexOf("--email");
  const v = i >= 0 ? process.argv[i + 1] : undefined;
  return String(v ?? "").toLowerCase().trim();
}

// Hidden prompt: prints the query, then mutes echo so the typed password never
// appears on screen or in scrollback.
function askHidden(query) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true });
    rl._writeToOutput = (str) => {
      // let the query through once; suppress everything the user types
      if (!rl.__muted) { rl.output.write(str); return; }
      if (str.includes("\n") || str.includes("\r")) rl.output.write("\n");
    };
    rl.question(query, (val) => { rl.close(); resolve(val); });
    rl.__muted = true;
  });
}

// Visible prompt (for the y/N confirmation — nothing secret here).
function askVisible(query) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(query, (val) => { rl.close(); resolve(val); });
  });
}

async function main() {
  const url = process.env.DATABASE_URL || process.env.NEON_DATABASE_URL;
  if (!url) {
    console.error("Refusing to run: set DATABASE_URL (the DB the worker reads) first.");
    process.exit(1);
  }
  const host = url.split("@").at(-1)?.split("/")[0] ?? "(unparsed)";

  const email = argEmail();
  if (!email || !email.includes("@")) {
    console.error("Usage: npm run set-password -- --email user@example.com");
    process.exit(1);
  }

  console.log(`  target DB host : ${host}`);
  console.log(`  email          : ${email}`);

  const sql = neon(url);
  // Guard against a typo'd email silently creating a brand-new allowlisted account:
  // if the email isn't already in allowed_users, require an explicit confirmation.
  const existing = await sql`SELECT 1 FROM allowed_users WHERE email = ${email} LIMIT 1`;
  if (existing.length === 0) {
    console.log("  note           : this email is NOT currently in allowed_users.");
    const yn = await askVisible("  create a NEW allowlisted account for it? (y/N): ");
    if (yn.trim().toLowerCase() !== "y") {
      console.log("Aborted — email not allowlisted and creation declined. Nothing written.");
      process.exit(0);
    }
  }

  const pw = await askHidden("  new password   : ");
  if (pw.length < MIN_LEN) {
    console.error(`\nPassword too short (min ${MIN_LEN} chars). Nothing written.`);
    process.exit(1);
  }
  const confirm = await askHidden("  confirm        : ");
  if (pw !== confirm) {
    console.error("\nPasswords do not match. Nothing written.");
    process.exit(1);
  }

  const hash = await bcrypt.hash(pw, BCRYPT_ROUNDS);
  // Insert sets added_by on first write; on conflict we only refresh the hash and
  // leave the original added_by intact.
  await sql`INSERT INTO allowed_users (email, password_hash, added_by)
            VALUES (${email}, ${hash}, ${"set-password script"})
            ON CONFLICT (email) DO UPDATE SET password_hash = ${hash}`;

  console.log(`\n  ✓ password set for ${email} on ${host}`);
  console.log("    (bcrypt hash stored; plaintext was never logged)");
}

main().catch((e) => {
  // Print the message only — never the password or the full connection string.
  console.error("\nFailed:", e?.message ?? String(e));
  process.exit(1);
});
