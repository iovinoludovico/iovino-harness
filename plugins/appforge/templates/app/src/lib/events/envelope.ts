import { CLOUDEVENTS_TYPE_PREFIX } from "./catalog";

export type EventRow = {
  id: string;
  seq: number | string;
  type: string;
  source: string;
  subject: string | null;
  data: unknown;
  correlation_id: string | null;
  occurred_at: string | Date;
};

export type CloudEvent = {
  specversion: "1.0";
  id: string;
  type: string;
  source: string;
  subject?: string;
  time: string;
  datacontenttype: "application/json";
  dataschema?: string;
  correlationid?: string;
  sequence: string;
  data: unknown;
};

/** Builds a CloudEvents 1.0 envelope (JSON structured mode) from an outbox row. */
export function toCloudEvent(row: EventRow, schemaBaseUrl?: string, schemaVersion = 1): CloudEvent {
  return {
    specversion: "1.0",
    id: row.id,
    type: CLOUDEVENTS_TYPE_PREFIX + row.type,
    source: row.source,
    ...(row.subject ? { subject: row.subject } : {}),
    time: new Date(row.occurred_at).toISOString(),
    datacontenttype: "application/json",
    ...(schemaBaseUrl ? { dataschema: `${schemaBaseUrl}/schemas/${row.type}/v${schemaVersion}` } : {}),
    ...(row.correlation_id ? { correlationid: row.correlation_id } : {}),
    sequence: String(row.seq),
    data: row.data,
  };
}
