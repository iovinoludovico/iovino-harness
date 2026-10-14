# Events in appforge apps

## Flow
1. A change happens in a transaction (insert/update/delete trigger, `perform_transition`, a reaction, cron).
2. `<entity>_emit(type, row, extra)` builds `data = {<entity>: payload, ...extra, recipients?}` and calls
   `emit_event()`, which inserts into `public.events` (outbox) in the same transaction.
3. After insert on `events`:
   - `react_to_event()` runs the internal reactions (`set`, `transition`, `schedule`, `broadcast`, `custom`);
   - `fan_out_event()` creates one `webhook_deliveries` row per matching subscriber and `NOTIFY`s the dispatcher.
4. On commit the dispatcher claims due deliveries (`FOR UPDATE SKIP LOCKED`), POSTs the CloudEvent, records
   the outcome, retries with backoff (1m, 5m, 30m, 2h, 12h, 24h ±10%), and marks `dead` after `max_attempts`.

## Envelope
CloudEvents 1.0 structured mode: `id` (outbox id = idempotency key), `type` = `app.events.type_prefix` + type,
`source`, `subject` (code or display), `time`, `sequence`, `dataschema`, `data`. Headers: `webhook-id`,
`webhook-timestamp`, `webhook-signature` (`v1,<base64 HMAC-SHA256(secret, id.timestamp.body)>`), optional Basic auth.

## Payload
`data.<entity>`: `id`, `entity`, `display`, `url`, `code`, every field (references as `{id, display, code?, email?}`,
enums as `{key, labels}`), `state` (`{key, label, labels, kind, color}`), `created_by`, timestamps.
Workflow events add `transition` (`key`, `labels`, `trigger`, `from`, `to`), `actor`, `comment`.
`updated` adds `changed` (field list); `reminder` adds `reminder` (`state`, `after_days`, `count`);
scheduled events add `scheduled`. `recipients` = `[{email, locale, recipient_type, template_key}]`.

## Writing a subscriber (n8n)
- Webhook node with Basic auth (or verify the signature in a Code node).
- Deduplicate on the `webhook-id` header.
- Switch on `type`; for notifications iterate `data.recipients` and pick the template by `template_key` and
  `locale`. Answer 2xx only after the work is done (otherwise the dispatcher retries).
