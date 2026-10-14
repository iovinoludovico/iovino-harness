export const LOCALES = {{LOCALES_TS}} as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "{{DEFAULT_LOCALE}}";
export const LOCALE_COOKIE = "NEXT_LOCALE";

export const LOCALE_NAMES: Record<string, string> = { it: "Italiano", en: "English", de: "Deutsch", fr: "Français", es: "Español" };

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** Best match from an Accept-Language header, e.g. "en-GB,en;q=0.9,it;q=0.8". */
export function localeFromAcceptLanguage(header: string | null): Locale | null {
  if (!header) return null;
  const ranked = header
    .split(",")
    .map((part) => {
      const [tag, q] = part.trim().split(";q=");
      return { lang: tag.toLowerCase().split("-")[0], q: q ? Number(q) : 1 };
    })
    .sort((a, b) => b.q - a.q);
  return ranked.map((r) => r.lang).find(isLocale) ?? null;
}

/** Label of a workflow state/transition in the given locale (falls back to the Italian `label`). */
export function localizedLabel(row: { label: string; label_i18n?: unknown }, locale: string): string {
  const i18n = row.label_i18n as Record<string, string> | null | undefined;
  return (i18n && typeof i18n === "object" && i18n[locale]) || row.label;
}

/** A {locale: text} map (event/state labels) in the given locale, with fallback. */
export function pickLabel(labels: unknown, locale: string, fallback = ""): string {
  if (!labels || typeof labels !== "object") return fallback;
  const map = labels as Record<string, string>;
  return map[locale] ?? map[DEFAULT_LOCALE] ?? Object.values(map)[0] ?? fallback;
}
