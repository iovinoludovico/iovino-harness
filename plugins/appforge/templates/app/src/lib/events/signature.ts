import { createHmac, timingSafeEqual } from "node:crypto";

// "Standard Webhooks" signatures (https://www.standardwebhooks.com):
//   signed content = `${webhook-id}.${webhook-timestamp}.${body}`
//   key            = base64-decoded secret without the "whsec_" prefix
//   header         = space-separated list of "v1,<base64 HMAC-SHA256>"

const PREFIX = "whsec_";

function secretKey(secret: string): Buffer {
  return Buffer.from(secret.startsWith(PREFIX) ? secret.slice(PREFIX.length) : secret, "base64");
}

export function sign(secret: string, id: string, timestamp: number, body: string): string {
  const mac = createHmac("sha256", secretKey(secret)).update(`${id}.${timestamp}.${body}`).digest("base64");
  return `v1,${mac}`;
}

/** Headers for a delivery; signs with every provided secret (current + previous during rotation). */
export function signatureHeaders(secrets: string[], id: string, body: string, now = Date.now()) {
  const timestamp = Math.floor(now / 1000);
  return {
    "webhook-id": id,
    "webhook-timestamp": String(timestamp),
    "webhook-signature": secrets.map((s) => sign(s, id, timestamp, body)).join(" "),
  };
}

/** Verifies a delivery (used in tests and as reference for receivers). */
export function verify(
  secret: string,
  headers: { "webhook-id": string; "webhook-timestamp": string; "webhook-signature": string },
  body: string,
  { toleranceSeconds = 300, now = Date.now() } = {}
): boolean {
  const ts = Number(headers["webhook-timestamp"]);
  if (!Number.isFinite(ts) || Math.abs(now / 1000 - ts) > toleranceSeconds) return false;
  const expected = Buffer.from(sign(secret, headers["webhook-id"], ts, body));
  return headers["webhook-signature"].split(" ").some((candidate) => {
    const got = Buffer.from(candidate);
    return got.length === expected.length && timingSafeEqual(got, expected);
  });
}
