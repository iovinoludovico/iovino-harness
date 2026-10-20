"use server";

// Notification texts of this app (owned by the modeler, replaced by `modeler install`): the overrides of the
// templates of behavior.yaml kept in public.notification_templates (key x language), read and written by the
// admin page (src/components/modeler/notification-templates.tsx). The defaults come from behavior.json; a row
// here overrides them for the engine (<entity>_recipients) and for every subscriber that renders the texts.

import { modelerDb, requireModelerAdmin } from "./access";

export type TemplateOverride = { key: string; locale: string; subject: string; body: string; updatedAt: string | null };
export type TemplateResult = { ok: boolean; message: string };

const KEY = /^[a-z][a-z0-9_]*$/;
const LOCALE = /^[a-z]{2}$/;

export async function listNotificationTemplates(): Promise<TemplateOverride[]> {
  await requireModelerAdmin();
  const db = await modelerDb();
  const { data, error } = await db.from("notification_templates").select("key, locale, subject, body, updated_at").order("key").order("locale");
  if (error) throw new Error(error.message);
  type Row = { key: string; locale: string; subject: string; body: string | null; updated_at: string | null };
  // supabase-js infers the row shape from the select string: read as `Row` (as metamodel-actions does)
  return ((data ?? []) as unknown as Row[]).map((r) => ({ key: r.key, locale: r.locale, subject: r.subject, body: r.body ?? "", updatedAt: r.updated_at }));
}

/** Saves an override (insert or update) of one template in one language. */
export async function saveNotificationTemplate(key: string, locale: string, subject: string, body: string): Promise<TemplateResult> {
  await requireModelerAdmin();
  if (!KEY.test(key) || !LOCALE.test(locale)) return { ok: false, message: "Invalid template key or language" };
  if (!subject.trim()) return { ok: false, message: "The subject is required" };
  const db = await modelerDb();
  const { error } = await db.from("notification_templates").upsert({ key, locale, subject: subject.trim(), body, updated_at: new Date().toISOString() });
  return error ? { ok: false, message: error.message } : { ok: true, message: "Saved" };
}

/** Removes the override: the text of the model applies again. */
export async function resetNotificationTemplate(key: string, locale: string): Promise<TemplateResult> {
  await requireModelerAdmin();
  const db = await modelerDb();
  const { error } = await db.from("notification_templates").delete().eq("key", key).eq("locale", locale);
  return error ? { ok: false, message: error.message } : { ok: true, message: "Reset to the model" };
}
