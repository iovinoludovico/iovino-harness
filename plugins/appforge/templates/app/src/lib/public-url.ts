import type { NextRequest } from "next/server";

// Public origin of the app. In production APP_BASE_URL is authoritative: the
// standalone server sees HOSTNAME (0.0.0.0:3000) in request.nextUrl and the
// Host / X-Forwarded-* headers can be forged by the client. Without it (local
// development) the origin comes from the headers.
export function publicOrigin(request: NextRequest): string {
  const configured = process.env.APP_BASE_URL;
  if (configured) return new URL(configured).origin;
  const first = (value: string | null) => value?.split(",")[0].trim() || null;
  const host = first(request.headers.get("x-forwarded-host")) ?? first(request.headers.get("host"));
  const proto = first(request.headers.get("x-forwarded-proto")) ?? request.nextUrl.protocol.replace(":", "");
  return host ? `${proto}://${host}` : request.nextUrl.origin;
}

/** Absolute URL on the public origin. */
export function publicUrl(request: NextRequest, path: string): URL {
  return new URL(path, publicOrigin(request));
}

/** A same-origin relative path (`/…`), or "/" for anything that could leave the app. */
export function safeRedirectPath(next: string | null): string {
  if (!next || !next.startsWith("/") || /[\\\u0000-\u001f\u007f]/.test(next)) return "/";
  const base = "http://app.invalid";
  const url = new URL(next, base);
  return url.origin === base ? `${url.pathname}${url.search}${url.hash}` : "/";
}
