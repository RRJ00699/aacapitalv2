// lib/security/crypto.ts
// AES-256-GCM encryption for secrets at rest (Zerodha access tokens).
// No new dependencies — uses Node built-in crypto, works on Node 24 / Vercel.
//
// Generate ENCRYPTION_KEY (run in PowerShell, one line):
//   node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"
// Add to Vercel env AND .env.local as ENCRYPTION_KEY=<value>
//
// Stored format: v1.<iv>.<tag>.<ciphertext>  (base64url parts)

import crypto from "node:crypto"

const ALGORITHM = "aes-256-gcm"
const IV_LENGTH  = 12  // 96-bit nonce — correct for GCM
const KEY_LENGTH = 32  // 256-bit key

function getKey(): Buffer {
  const raw = process.env.ENCRYPTION_KEY
  if (!raw) throw new Error("ENCRYPTION_KEY is not set")
  const key = /^[0-9a-fA-F]{64}$/.test(raw)
    ? Buffer.from(raw, "hex")
    : Buffer.from(raw, "base64")
  if (key.length !== KEY_LENGTH)
    throw new Error(
      `ENCRYPTION_KEY must decode to ${KEY_LENGTH} bytes (got ${key.length}). ` +
      `Generate: node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"`
    )
  return key
}

export function encrypt(plaintext: string): string {
  const key = getKey()
  const iv  = crypto.randomBytes(IV_LENGTH)
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv)
  const ciphertext = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()])
  const tag = cipher.getAuthTag()
  return ["v1", iv.toString("base64url"), tag.toString("base64url"), ciphertext.toString("base64url")].join(".")
}

export function decrypt(payload: string): string {
  const key   = getKey()
  const parts = payload.split(".")
  if (parts.length !== 4 || parts[0] !== "v1") throw new Error("Invalid ciphertext format")
  const iv         = Buffer.from(parts[1], "base64url")
  const tag        = Buffer.from(parts[2], "base64url")
  const ciphertext = Buffer.from(parts[3], "base64url")
  const decipher   = crypto.createDecipheriv(ALGORITHM, key, iv)
  decipher.setAuthTag(tag)
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf8")
}

// True only for values produced by encrypt(). Lets legacy plaintext tokens
// keep working during the migration window — re-encrypted on next login.
export function isEncrypted(value: string | null | undefined): boolean {
  return typeof value === "string" && value.startsWith("v1.")
}
