import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { publicUrl, safeRedirectPath } from "@/lib/public-url";

// The standalone server sees its bind address; the proxy forwards the public host.
const request = (headers: Record<string, string>) => new NextRequest("http://0.0.0.0:3000/auth/callback", { headers });

describe("publicUrl", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("uses APP_BASE_URL and ignores forged headers", () => {
    vi.stubEnv("APP_BASE_URL", "https://invitations.iovino-systems.cloud");
    const url = publicUrl(request({ host: "evil.example", "x-forwarded-host": "evil.example" }), "/login");
    expect(url.href).toBe("https://invitations.iovino-systems.cloud/login");
  });

  it("without APP_BASE_URL uses the host and scheme forwarded by the reverse proxy", () => {
    vi.stubEnv("APP_BASE_URL", "");
    const url = publicUrl(
      request({ host: "invitations.iovino-systems.cloud", "x-forwarded-proto": "https" }),
      "/login?next=%2Finvitations"
    );
    expect(url.href).toBe("https://invitations.iovino-systems.cloud/login?next=%2Finvitations");
  });

  it("without APP_BASE_URL takes the first value of a forwarded list", () => {
    vi.stubEnv("APP_BASE_URL", "");
    const url = publicUrl(
      request({ host: "guest-invitations-web:3000", "x-forwarded-host": "a.example, b.example", "x-forwarded-proto": "https, http" }),
      "/"
    );
    expect(url.href).toBe("https://a.example/");
  });
});

describe("safeRedirectPath", () => {
  it.each([
    ["/invitations/123?tab=x", "/invitations/123?tab=x"],
    [null, "/"],
    ["https://evil.com", "/"],
    ["//evil.com", "/"],
    ["/\\evil.com", "/"],
    ["/\t/evil.com", "/"],
    ["/%2F%2Fevil.com", "/%2F%2Fevil.com"],
  ])("%s → %s", (next, expected) => {
    expect(safeRedirectPath(next)).toBe(expected);
  });
});
