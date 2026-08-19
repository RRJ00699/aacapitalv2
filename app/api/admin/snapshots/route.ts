import { NextRequest, NextResponse } from "next/server";
import { kvStore } from "@/lib/kv-cache";
import { publishVersionedSnapshot, type SnapshotKV } from "@/lib/versioned-snapshot";
import { PIPELINE_LIMITS } from "@/lib/config/pipeline";

export const dynamic = "force-dynamic";

type Publication = { name: string; payload: unknown };
type DiagnosticStage =
  | "request_validation"
  | "publish_key_validation"
  | "json_parsing"
  | "schema_validation"
  | "snapshot_serialization"
  | "kv_immutable_write"
  | "previous_pointer_write"
  | "active_pointer_write"
  | "response_generation";

const ALLOWED = /^(ipo-command:v6|ipo:index:v3|ipo-live-preopen:v2|pipeline-health:v1|market-india:v1|journey:isin:[A-Z0-9]{12}:v1|journey-15m:isin:[A-Z0-9]{12}:v1|listing-cumulative-volume:isin:[A-Z0-9]{12}:v1|listing-ticks:isin:[A-Z0-9]{12}:v1|ipo-details:isin:[A-Z0-9]{12}:v1)$/;
const REDACTED = "[REDACTED]";

function exceptionClass(error: unknown): string {
  return error instanceof Error ? error.name : typeof error;
}

function safeExceptionMessage(error: unknown, additionalSecrets: string[] = []): string {
  let message = error instanceof Error ? error.message : String(error);
  const secrets = [
    process.env.SNAPSHOT_PUBLISH_KEY,
    ...additionalSecrets,
  ].filter((value): value is string => Boolean(value));
  for (const secret of secrets) message = message.split(secret).join(REDACTED);
  return message;
}

function logFailure(stage: DiagnosticStage, snapshotName: string | null, error: unknown, secrets: string[] = []): void {
  console.error({
    stage,
    snapshot_name: snapshotName,
    exception_class: exceptionClass(error),
    exception_message: safeExceptionMessage(error, secrets),
  });
}

function failureResponse(): NextResponse {
  return NextResponse.json({ error: "snapshot publication failed" }, { status: 500 });
}

function diagnosticStore(store: SnapshotKV, snapshotName: string, serializedPayload: string): SnapshotKV {
  return {
    get: (key) => store.get(key),
    put: async (key, value, options) => {
      const stage: DiagnosticStage = key.endsWith(":previous")
        ? "previous_pointer_write"
        : key.endsWith(":active")
          ? "active_pointer_write"
          : "kv_immutable_write";
      try {
        await store.put(key, value, options);
      } catch (error) {
        logFailure(stage, snapshotName, error, [serializedPayload, value]);
        throw error;
      }
    },
  };
}

/** Publication only: this Worker validates JSON supplied by the pipeline and writes KV.
 * It intentionally has no database/domain-builder import and cannot wake Neon. */
export async function POST(req: NextRequest) {
  if (!req || typeof req.json !== "function") {
    const error = new TypeError("invalid publication request");
    logFailure("request_validation", null, error);
    return failureResponse();
  }

  if (!process.env.SNAPSHOT_PUBLISH_KEY || req.headers.get("x-aac-key") !== process.env.SNAPSHOT_PUBLISH_KEY) {
    logFailure("publish_key_validation", null, new Error("publication key rejected"));
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const store = kvStore();
  if (!store) return NextResponse.json({ error: "CACHE binding unavailable" }, { status: 503 });

  let body: { snapshots?: Publication[] };
  try {
    body = await req.json();
  } catch (error) {
    logFailure("json_parsing", null, error);
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  if (!Array.isArray(body.snapshots) || !body.snapshots.length
      || body.snapshots.length > PIPELINE_LIMITS.SNAPSHOT_MAX_PUBLICATION_ITEMS) {
    logFailure("request_validation", null, new TypeError("snapshots must contain an allowed bounded item count"));
    return NextResponse.json({ error: "snapshots must contain an allowed bounded item count" }, { status: 400 });
  }

  const serialized = new Map<Publication, string>();
  for (const item of body.snapshots) {
    if (!item || typeof item.name !== "string" || !ALLOWED.test(item.name) || item.payload === undefined) {
      logFailure("schema_validation", null, new TypeError("invalid snapshot item"));
      return NextResponse.json({ error: "invalid snapshot item" }, { status: 400 });
    }
    try {
      const payload = JSON.stringify(item.payload);
      if (payload === undefined) throw new TypeError("snapshot payload is not JSON serializable");
      JSON.parse(payload);
      serialized.set(item, payload);
    } catch (error) {
      logFailure("snapshot_serialization", item.name, error);
      return failureResponse();
    }
  }

  const published: Record<string, string> = {};
  for (const item of body.snapshots) {
    try {
      published[item.name] = await publishVersionedSnapshot(
        diagnosticStore(store, item.name, serialized.get(item)!), item.name, item.payload,
      );
    } catch {
      return failureResponse();
    }
  }

  try {
    return NextResponse.json({ ok: true, published });
  } catch (error) {
    logFailure("response_generation", null, error);
    return failureResponse();
  }
}

/** No read/list surface: publication credentials authorize POST only. */
export async function GET() {
  return NextResponse.json({ error: "unauthorized" }, { status: 401 });
}
