import "server-only";
import { format } from "date-fns";
import { getFormatter, getTranslations } from "next-intl/server";
import { createClient } from "@/lib/supabase/server";
import { MODEL } from "@/lib/model";
import type { EntityDef, FieldDef } from "@/lib/model-types";
import { k, selectFor, type Formatter, type RefOption } from "@/lib/model-helpers";

// Data access of the generic pages (/e/[entity]). Every query runs as the user:
// what is not readable is simply not returned (RLS).

export type Row = Record<string, unknown> & { id: string };

export type ListFilters = {
  state?: string;
  q?: string;
  /** Records overlapping [from, to] on a date range (calendar view). */
  range?: { start: string; end?: string; from: string; to: string };
  /** Records referencing a parent (related panels). */
  parent?: { field: string; id: string };
};

export async function listRows(e: EntityDef, filters: ListFilters = {}): Promise<Row[]> {
  const supabase = await createClient();
  const extra = [e.ui.kanban?.group_by, e.ui.calendar?.start, e.ui.calendar?.end, e.ui.cards?.title, e.ui.cards?.subtitle, e.ui.cards?.image];
  const fields = e.fields.filter((f) => f.list || f.key === e.display || extra.includes(f.key));
  let query = supabase.from(e.table).select(selectFor(e, fields)).order("updated_at", { ascending: false }).limit(500);
  if (filters.state && e.workflow) query = query.eq("state", filters.state);
  if (filters.parent) query = query.eq(filters.parent.field, filters.parent.id);
  if (filters.range) {
    const { start, end, from, to } = filters.range;
    query = query.lte(start, to);
    query = end ? query.or(`${end}.gte.${from},and(${end}.is.null,${start}.gte.${from})`) : query.gte(start, from);
  }
  if (filters.q) {
    const searchable = e.fields.filter((f) => ["string", "email", "text"].includes(f.type)).map((f) => f.key);
    const cols = [...(e.codePrefix ? ["code"] : []), ...searchable];
    if (cols.length) query = query.or(cols.map((c) => `${c}.ilike.%${filters.q!.replace(/[,()%]/g, " ")}%`).join(","));
  }
  const { data, error } = await query;
  if (error) throw new Error(error.message);
  return (data ?? []) as unknown as Row[];
}

export async function getRow(e: EntityDef, id: string): Promise<Row | null> {
  const supabase = await createClient();
  const { data } = await supabase.from(e.table).select(selectFor(e)).eq("id", id).maybeSingle();
  return (data as unknown as Row) ?? null;
}

/** Choices for a reference field (rows of the target the user can read). */
export async function refOptions(f: FieldDef): Promise<RefOption[]> {
  const supabase = await createClient();
  if (f.to === "User") {
    const { data } = await supabase.from("profiles").select("id, full_name, email").not("approved_at", "is", null).order("email").limit(1000);
    return (data ?? []).map((p) => ({ value: p.id as string, label: (p.full_name as string | null) ?? (p.email as string) }));
  }
  const target = Object.values(MODEL.entities).find((x) => x.name === f.to);
  if (!target) return [];
  const disp = target.display;
  const cols = disp === "id" ? "id" : disp === "code" ? "id, code" : `id, ${disp}`;
  const { data } = await supabase.from(target.table).select(cols).order(disp === "id" ? "created_at" : disp).limit(1000);
  return ((data ?? []) as unknown as Row[]).map((r) => ({ value: r.id, label: String(r[disp] ?? r.id) }));
}

export async function refOptionsFor(e: EntityDef): Promise<Record<string, RefOption[]>> {
  const refs = e.fields.filter((f) => f.type === "ref" && !f.readonly);
  const all = await Promise.all(refs.map((f) => refOptions(f)));
  return Object.fromEntries(refs.map((f, i) => [f.key, all[i]]));
}

export type AvailableTransition = {
  key: string;
  labels: Record<string, string>;
  to: { key: string; labels: Record<string, string>; color?: string };
  comment: "optional" | "required" | "none";
  unmet: { field: string; op: string; value?: unknown }[];
};

export async function availableTransitions(e: EntityDef, id: string): Promise<AvailableTransition[]> {
  if (!e.workflow) return [];
  const supabase = await createClient();
  const { data } = await supabase.rpc("available_transitions", { p_entity: e.key, p_id: id });
  return (data as AvailableTransition[] | null) ?? [];
}

export type HistoryItem = {
  id: string;
  kind: string;
  transition: string | null;
  from_state: string | null;
  to_state: string;
  comment: string | null;
  created_at: string;
  actor: { type: string; name?: string | null; email?: string };
};

export async function history(e: EntityDef, id: string): Promise<HistoryItem[]> {
  if (!e.workflow) return [];
  const supabase = await createClient();
  const { data } = await supabase.rpc("record_history_of", { p_entity: e.key, p_id: id });
  return (data as HistoryItem[] | null) ?? [];
}

/** Value formatter for the current locale. */
export async function formatter(): Promise<Formatter> {
  const [fmt, t] = await Promise.all([getFormatter(), getTranslations()]);
  return {
    number: (n) => fmt.number(n),
    money: (n) => fmt.number(n, { style: "currency", currency: "EUR" }),
    date: (iso) => format(new Date(iso), "dd/MM/yyyy"),
    datetime: (iso) => format(new Date(iso), "dd/MM/yyyy HH:mm"),
    yes: t("common.yes"),
    no: t("common.no"),
    enumLabel: (en, v) => (t.has(k.enumValue(en, v)) ? t(k.enumValue(en, v)) : v),
  };
}
