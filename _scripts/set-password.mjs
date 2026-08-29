// set-password.mjs — set/reset a D1 allowed_users password hash.
import readline from "node:readline";
import bcrypt from "bcryptjs";
import { execFileSync } from "node:child_process";

const MIN_LEN = 8;
const BCRYPT_ROUNDS = 12;
const CONFIG = "wrangler.jsonc";
const BINDING = "DB";

function argEmail() {
  const i = process.argv.indexOf("--email");
  const v = i >= 0 ? process.argv[i + 1] : undefined;
  return String(v ?? "").toLowerCase().trim();
}

function sqlv(v) { return `'${String(v).replaceAll("'", "''")}'`; }

function d1(sql) {
  const out = execFileSync(
    process.platform === "win32" ? "npx.cmd" : "npx",
    ["wrangler", "--config", CONFIG, "d1", "execute", BINDING, "--remote", "--command", sql, "--json"],
    { encoding: "utf8", stdio: ["ignore", "pipe", "inherit"] },
  );
  const payload = JSON.parse(out);
  for (const item of Array.isArray(payload) ? payload : [payload]) {
    if (Array.isArray(item?.results)) return item.results;
  }
  return [];
}

function askHidden(query) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true });
    rl._writeToOutput = (str) => {
      if (!rl.__muted) { rl.output.write(str); return; }
      if (str.includes("\n") || str.includes("\r")) rl.output.write("\n");
    };
    rl.question(query, (val) => { rl.close(); resolve(val); });
    rl.__muted = true;
  });
}

function askVisible(query) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(query, (val) => { rl.close(); resolve(val); });
  });
}

async function main() {
  const email = argEmail();
  if (!email || !email.includes("@")) {
    console.error("Usage: npm run set-password -- --email user@example.com");
    process.exit(1);
  }

  console.log("  target         : Cloudflare D1 / DB");
  console.log(`  email          : ${email}`);

  const existing = d1(`SELECT 1 AS ok FROM allowed_users WHERE email=${sqlv(email)} LIMIT 1;`);
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
  d1(`INSERT INTO allowed_users(email,password_hash,added_by,added_at)
      VALUES(${sqlv(email)},${sqlv(hash)},'set-password script',CURRENT_TIMESTAMP)
      ON CONFLICT(email) DO UPDATE SET password_hash=excluded.password_hash;`);

  console.log(`\n  ✓ password set for ${email} in D1`);
  console.log("    (bcrypt hash stored; plaintext was never logged)");
}

main().catch((e) => {
  console.error("\nFailed:", e?.message ?? String(e));
  process.exit(1);
});
