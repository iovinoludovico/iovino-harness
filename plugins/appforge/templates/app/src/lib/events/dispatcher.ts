import type { Sql } from "postgres";
import { toCloudEvent, type EventRow } from "./envelope";
import { signatureHeaders } from "./signature";
import { retryDelaySeconds } from "./backoff";

// Webhook dispatcher: claims due deliveries from the outbox, POSTs signed
// CloudEvents to subscribers and records the outcome with retry/backoff.
// Runs in its own process (worker/dispatcher.ts) with a direct DB connection.

type Claimed = {
  delivery_id: string;
  attempts: number;
  endpoint: {
    id: string;
    url: string;
    secret: string;
    previous_secret: string | null;
    headers: Record<string, string>;
    /** Optional HTTP Basic credentials (both or neither). */
    basic_auth_username: string | null;
    basic_auth_password: string | null;
    active: boolean;
    max_attempts: number;
    timeout_ms: number;
  };
  event: EventRow;
};

export type DispatcherOptions = {
  sql: Sql;
  fetch?: typeof fetch;
  batchSize?: number;
  /** In-flight deliveries older than this are considered abandoned (crashed worker). */
  staleAfterSeconds?: number;
  schemaBaseUrl?: string;
  userAgent?: string;
  log?: (msg: string, extra?: Record<string, unknown>) => void;
};

const EXCERPT_LENGTH = 300;

export async function claimDue(sql: Sql, batchSize: number, staleAfterSeconds: number): Promise<Claimed[]> {
  const rows = await sql<Claimed[]>`
    with due as (
      select id
        from public.webhook_deliveries
       where (status in ('pending', 'failed') and next_attempt_at <= now())
          or (status = 'in_flight' and locked_at < now() - make_interval(secs => ${staleAfterSeconds}))
       order by next_attempt_at
       limit ${batchSize}
       for update skip locked
    ),
    claimed as (
      update public.webhook_deliveries d
         set status = 'in_flight', locked_at = now(), attempts = d.attempts + 1
        from due
       where d.id = due.id
      returning d.id, d.attempts, d.event_id, d.endpoint_id
    )
    select c.id as delivery_id,
           c.attempts,
           jsonb_build_object(
             'id', w.id, 'url', w.url, 'secret', w.secret, 'previous_secret', w.previous_secret,
             'headers', w.headers, 'basic_auth_username', w.basic_auth_username,
             'basic_auth_password', w.basic_auth_password, 'active', w.active, 'max_attempts', w.max_attempts, 'timeout_ms', w.timeout_ms
           ) as endpoint,
           jsonb_build_object(
             'id', e.id, 'seq', e.seq, 'type', e.type, 'source', e.source, 'subject', e.subject,
             'data', e.data, 'correlation_id', e.correlation_id, 'occurred_at', e.occurred_at
           ) as event
      from claimed c
      join public.webhook_endpoints w on w.id = c.endpoint_id
      join public.events e on e.id = c.event_id
  `;
  return rows;
}

export type DeliveryOutcome = { ok: boolean; status?: number; body?: string; error?: string };

export async function deliver(
  claimed: Claimed,
  { fetch: fetchImpl = fetch, schemaBaseUrl, userAgent = "{{APP_SLUG}}-webhooks/1.0" }: Omit<DispatcherOptions, "sql">
): Promise<DeliveryOutcome> {
  const body = JSON.stringify(toCloudEvent(claimed.event, schemaBaseUrl));
  const { basic_auth_username: user, basic_auth_password: password } = claimed.endpoint;
  const authorization: Record<string, string> =
    user && password ? { authorization: `Basic ${Buffer.from(`${user}:${password}`).toString("base64")}` } : {};
  const secrets = [claimed.endpoint.secret, claimed.endpoint.previous_secret].filter((s): s is string => !!s);
  try {
    const res = await fetchImpl(claimed.endpoint.url, {
      method: "POST",
      body,
      redirect: "manual",
      signal: AbortSignal.timeout(claimed.endpoint.timeout_ms),
      headers: {
        ...claimed.endpoint.headers,
        ...authorization,
        "content-type": "application/json",
        "user-agent": userAgent,
        "ce-specversion": "1.0",
        "ce-type": claimed.event.type,
        // Same id across retries: receivers use it as idempotency key.
        ...signatureHeaders(secrets, claimed.event.id, body),
      },
    });
    const text = (await res.text().catch(() => "")).slice(0, EXCERPT_LENGTH);
    return { ok: res.status >= 200 && res.status < 300, status: res.status, body: text };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? `${e.name}: ${e.message}` : String(e) };
  }
}

export async function recordOutcome(sql: Sql, claimed: Claimed, outcome: DeliveryOutcome) {
  if (outcome.ok) {
    await sql`
      update public.webhook_deliveries
         set status = 'succeeded', delivered_at = now(), locked_at = null,
             last_status_code = ${outcome.status ?? null}, last_response_excerpt = ${outcome.body ?? null},
             last_error = null
       where id = ${claimed.delivery_id}`;
    return;
  }
  const exhausted = claimed.attempts >= claimed.endpoint.max_attempts;
  const delay = retryDelaySeconds(claimed.attempts);
  await sql`
    update public.webhook_deliveries
       set status = ${exhausted ? "dead" : "failed"},
           next_attempt_at = now() + make_interval(secs => ${delay}),
           locked_at = null,
           last_status_code = ${outcome.status ?? null},
           last_response_excerpt = ${outcome.body ?? null},
           last_error = ${outcome.error ?? `HTTP ${outcome.status}`}
     where id = ${claimed.delivery_id}`;
}

/** Processes due deliveries until none are left. Returns how many were attempted. */
export async function drain(opts: DispatcherOptions): Promise<number> {
  const { sql, batchSize = 10, staleAfterSeconds = 300, log = () => {} } = opts;
  let total = 0;
  for (;;) {
    const batch = await claimDue(sql, batchSize, staleAfterSeconds);
    if (!batch.length) return total;
    total += batch.length;
    await Promise.all(
      batch.map(async (claimed) => {
        const outcome: DeliveryOutcome = claimed.endpoint.active
          ? await deliver(claimed, opts)
          : { ok: false, error: "Endpoint disattivato" };
        if (!claimed.endpoint.active) claimed.attempts = claimed.endpoint.max_attempts;
        await recordOutcome(sql, claimed, outcome);
        log(outcome.ok ? "delivered" : "delivery failed", {
          delivery: claimed.delivery_id,
          event: claimed.event.type,
          url: claimed.endpoint.url,
          attempt: claimed.attempts,
          status: outcome.status,
          error: outcome.error,
        });
      })
    );
  }
}
