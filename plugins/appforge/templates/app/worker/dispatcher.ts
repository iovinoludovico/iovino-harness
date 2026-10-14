// Webhook dispatcher process. Usage: `npm run worker` (DATABASE_URL required).
//
// Wakes up on NOTIFY 'webhook_deliveries' (new deliveries committed) and on a
// periodic timer (retries whose backoff expired, missed notifications).
import postgres from "postgres";
import { drain } from "../src/lib/events/dispatcher";

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) {
  console.error("DATABASE_URL is required");
  process.exit(1);
}
const POLL_INTERVAL_MS = Number(process.env.DISPATCHER_POLL_INTERVAL_MS ?? 30_000);

// TLS towards the hosted database; plain connection only to a local stack.
const isLocalDb = ["localhost", "127.0.0.1", "host.docker.internal"].includes(new URL(DATABASE_URL).hostname);
const sql = postgres(DATABASE_URL, { max: 5, onnotice: () => {}, ssl: isLocalDb ? false : "require" });

const log = (msg: string, extra: Record<string, unknown> = {}) =>
  console.log(JSON.stringify({ time: new Date().toISOString(), msg, ...extra }));

let running = false;
let rerun = false;
let stopping = false;

async function tick() {
  if (stopping) return;
  if (running) {
    rerun = true;
    return;
  }
  running = true;
  try {
    do {
      rerun = false;
      await drain({ sql, log, schemaBaseUrl: process.env.APP_BASE_URL });
    } while (rerun && !stopping);
  } catch (e) {
    log("dispatcher error", { error: e instanceof Error ? e.message : String(e) });
  } finally {
    running = false;
  }
}

let timer: NodeJS.Timeout | undefined;

async function main() {
  await sql.listen("webhook_deliveries", () => void tick());
  timer = setInterval(() => void tick(), POLL_INTERVAL_MS);
  log("dispatcher started", { pollIntervalMs: POLL_INTERVAL_MS });
  void tick();
}

async function shutdown(signal: string) {
  stopping = true;
  clearInterval(timer);
  log("dispatcher stopping", { signal });
  while (running) await new Promise((r) => setTimeout(r, 100));
  await sql.end({ timeout: 5 });
  process.exit(0);
}
process.on("SIGTERM", () => void shutdown("SIGTERM"));
process.on("SIGINT", () => void shutdown("SIGINT"));

main().catch((e) => {
  log("dispatcher failed to start", { error: e instanceof Error ? e.message : String(e) });
  process.exit(1);
});
