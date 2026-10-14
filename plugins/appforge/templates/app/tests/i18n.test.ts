import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { LOCALES, localeFromAcceptLanguage } from "@/i18n/config";
import { dbMessageKey } from "@/lib/db-errors";

const load = (loc: string) =>
  JSON.parse(readFileSync(path.resolve(import.meta.dirname, `../messages/${loc}.json`), "utf8")) as Record<string, unknown>;

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) => (v && typeof v === "object" ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`]));
}

describe("message catalogs", () => {
  it("every locale has the same keys", () => {
    const base = keys(load(LOCALES[0])).sort();
    for (const loc of LOCALES) expect(keys(load(loc)).sort(), loc).toEqual(base);
  });

  it("every database error has a translation", () => {
    const dir = path.resolve(import.meta.dirname, "../supabase/migrations");
    const sql = readdirSync(dir).map((f) => readFileSync(path.join(dir, f), "utf8")).join("\n");
    const messages = [...sql.matchAll(/raise exception '((?:[^']|'')+)'/g)].map((m) => m[1].replaceAll("''", "'"));
    expect(messages.length).toBeGreaterThan(5);
    const errors = load(LOCALES[0]).errors as Record<string, string>;
    for (const message of messages) {
      const key = dbMessageKey(message);
      expect(key, `map "${message}" in src/lib/db-errors.ts`).not.toBeNull();
      expect(errors[key!], key!).toBeDefined();
    }
  });
});

describe("locale helpers", () => {
  it("falls back to null for unknown languages", () => {
    expect(localeFromAcceptLanguage("xx-XX")).toBeNull();
    expect(localeFromAcceptLanguage(null)).toBeNull();
  });
});
