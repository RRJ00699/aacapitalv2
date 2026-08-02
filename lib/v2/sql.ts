// lib/v2/sql.ts — shared neon tagged-template type so every V2 query builder can
// take an INJECTED client: the real neon() in production, a mock in unit tests.
// Tests never open a live database connection.
export type SqlClient = (
  strings: TemplateStringsArray,
  ...values: unknown[]
) => Promise<Record<string, unknown>[]>;
