// Unit tests for the Credentials-provider password check. Run: `npm test`.
// The neon client is mocked — these never touch a live database.
import test from "node:test";
import assert from "node:assert/strict";
import bcrypt from "bcryptjs";
import { verifyPassword, DUMMY_HASH } from "./credentials-auth";
import type { SqlClient } from "./credentials-auth";

// A neon tagged-template stand-in that returns a fixed row set for any query.
function mockSql(rows: Record<string, unknown>[]): SqlClient {
  return ((_s: TemplateStringsArray, ..._v: unknown[]) => Promise.resolve(rows)) as SqlClient;
}

const PASSWORD = "correct horse battery staple";
const HASH = bcrypt.hashSync(PASSWORD, 12); // a real allowed_users.password_hash

test("allowlisted + correct password -> user", async () => {
  const user = await verifyPassword("USER@Example.com", PASSWORD, mockSql([{ password_hash: HASH }]));
  assert.deepEqual(user, {
    id: "user@example.com",
    email: "user@example.com",
    name: "user@example.com",
  });
});

test("NOT allowlisted (no row) + correct password -> null", async () => {
  const user = await verifyPassword("stranger@example.com", PASSWORD, mockSql([]));
  assert.equal(user, null);
});

test("allowlisted + NULL password_hash (Google-only) -> null", async () => {
  const user = await verifyPassword("google-only@example.com", PASSWORD, mockSql([{ password_hash: null }]));
  assert.equal(user, null);
});

test("allowlisted + wrong password -> null", async () => {
  const user = await verifyPassword("user@example.com", "wrong-password", mockSql([{ password_hash: HASH }]));
  assert.equal(user, null);
});

// Guards the anti-enumeration property: the no-row path compares against this, so it
// must be a real 12-round bcrypt hash (same cost as a genuine one).
test("DUMMY_HASH is a real 12-round bcrypt hash", () => {
  assert.match(DUMMY_HASH, /^\$2[aby]\$12\$/);
});
