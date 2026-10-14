import { describe, expect, it } from "vitest";
import { eventTypeMatches } from "@/lib/events/match";
import { CLOUDEVENTS_TYPE_PREFIX } from "@/lib/events/catalog";
import { toCloudEvent } from "@/lib/events/envelope";
import { sign, signatureHeaders, verify } from "@/lib/events/signature";
import { retryDelaySeconds } from "@/lib/events/backoff";

describe("event type filters", () => {
  it.each([
    ["*", "invitation.created", true],
    ["invitation.*", "invitation.transitioned", true],
    ["invitation.*", "guest.created", false],
    ["invitation.created", "invitation.created", true],
    ["invitation.created", "invitation.created_x", false],
    ["*.updated", "guest.updated", true],
  ])("%s matches %s → %s", (pattern, type, expected) => {
    expect(eventTypeMatches(pattern, type)).toBe(expected);
  });
});

describe("CloudEvents envelope", () => {
  it("maps an outbox row to a 1.0 structured event", () => {
    const ce = toCloudEvent(
      {
        id: "8b6c1d3e-0000-4000-8000-000000000001",
        seq: 42,
        type: "invitation.transitioned",
        source: "/invitations",
        subject: "INV-2026-0001",
        data: { a: 1 },
        correlation_id: null,
        occurred_at: "2026-10-03T10:00:00Z",
      },
      "https://app.example.org"
    );
    expect(ce).toEqual({
      specversion: "1.0",
      id: "8b6c1d3e-0000-4000-8000-000000000001",
      type: CLOUDEVENTS_TYPE_PREFIX + "invitation.transitioned",
      source: "/invitations",
      subject: "INV-2026-0001",
      time: "2026-10-03T10:00:00.000Z",
      datacontenttype: "application/json",
      dataschema: "https://app.example.org/schemas/invitation.transitioned/v1",
      sequence: "42",
      data: { a: 1 },
    });
  });
});

describe("Standard Webhooks signature", () => {
  // Test vector from the Standard Webhooks reference implementation.
  const secret = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw";
  const id = "msg_p5jXN8AQM9LWM0D4loKWxJek";
  const ts = 1614265330;
  const body = '{"test": 2432232314}';

  it("matches the reference vector", () => {
    expect(sign(secret, id, ts, body)).toBe("v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE=");
  });

  it("verifies its own headers and rejects tampering or stale timestamps", () => {
    const now = Date.now();
    const headers = signatureHeaders([secret], id, body, now);
    expect(verify(secret, headers, body, { now })).toBe(true);
    expect(verify(secret, headers, body + " ", { now })).toBe(false);
    expect(verify(secret, headers, body, { now: now + 10 * 60_000 })).toBe(false);
  });

  it("signs with both secrets during rotation", () => {
    const old = "whsec_" + Buffer.from("old-secret").toString("base64");
    const headers = signatureHeaders([secret, old], id, body);
    expect(headers["webhook-signature"].split(" ")).toHaveLength(2);
    expect(verify(old, headers, body)).toBe(true);
    expect(verify(secret, headers, body)).toBe(true);
  });
});

describe("retry backoff", () => {
  it("grows with attempts and stays within ±10% jitter", () => {
    expect(retryDelaySeconds(1, () => 0.5)).toBe(60);
    expect(retryDelaySeconds(2, () => 0.5)).toBe(300);
    expect(retryDelaySeconds(5, () => 0.5)).toBe(43200);
    expect(retryDelaySeconds(99, () => 0.5)).toBe(86400);
    expect(retryDelaySeconds(1, () => 0)).toBe(54);
    expect(retryDelaySeconds(1, () => 1)).toBe(66);
  });
});
