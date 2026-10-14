import type { PostgrestError } from "@supabase/supabase-js";
import { getTranslations } from "next-intl/server";
import { dbMessageKey } from "@/lib/db-errors";

export type ActionState = {
  ok?: boolean;
  message?: string;
  error?: string;
  fieldErrors?: Record<string, string>;
} | null;

const PG_CODES: Record<string, string> = {
  "23505": "duplicate",
  "23503": "foreignKey",
  "23502": "required",
  "23514": "invalid",
  "42501": "forbidden",
  "22P02": "invalid",
};

// Maps a Supabase/Postgres error to a translated, user-facing message.
export async function dbError(error: PostgrestError): Promise<ActionState> {
  const t = await getTranslations("errors");
  const key = dbMessageKey(error.message) ?? PG_CODES[error.code];
  if (key) return { error: t(key) };
  return { error: error.message };
}
