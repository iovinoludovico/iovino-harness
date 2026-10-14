"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/auth";
import { dbError, type ActionState } from "@/lib/action-state";
import { entityByKey, missingRequired, valuesFromForm } from "@/lib/model-helpers";

// Server actions of the generic pages. Permissions, codes, states and events
// are handled by the database (RLS, triggers, transition functions).

export async function saveRow(entityKey: string, id: string | null, _: ActionState, formData: FormData): Promise<ActionState> {
  await requireUser();
  const e = entityByKey(entityKey);
  const t = await getTranslations();
  if (!e) return { error: t("errors.unknownEntity") };
  const { values, many } = valuesFromForm(e, formData);
  const missing = missingRequired(e, values);
  if (missing.length) {
    return {
      error: t("validation.checkFields"),
      fieldErrors: Object.fromEntries(missing.map((m) => [m, t("validation.required")])),
    };
  }
  const supabase = await createClient();
  let rowId = id;
  if (id) {
    const { data, error } = await supabase.from(e.table).update(values).eq("id", id).select("id");
    if (error) return dbError(error);
    if (!data?.length) return { error: t("errors.cannotEdit") };
  } else {
    const { data, error } = await supabase.from(e.table).insert(values).select("id").single();
    if (error) return dbError(error);
    rowId = data.id as string;
  }
  // Many-references: replace the links (join table rows).
  for (const f of e.fields.filter((x) => x.many && !x.readonly)) {
    const ids = many[f.key] ?? [];
    const del = await supabase.from(f.joinTable!).delete().eq("record_id", rowId!);
    if (del.error) return dbError(del.error);
    if (ids.length) {
      const ins = await supabase.from(f.joinTable!).insert(ids.map((target_id, position) => ({ record_id: rowId, target_id, position })));
      if (ins.error) return dbError(ins.error);
    }
  }
  revalidatePath(`/e/${e.key}`);
  if (!id) redirect(`/e/${e.key}/${rowId}`);
  revalidatePath(`/e/${e.key}/${id}`);
  return { ok: true, message: t("records.saved") };
}

export async function deleteRow(entityKey: string, id: string): Promise<ActionState> {
  await requireUser();
  const e = entityByKey(entityKey);
  const t = await getTranslations();
  if (!e) return { error: t("errors.unknownEntity") };
  const supabase = await createClient();
  const { data, error } = await supabase.from(e.table).delete().eq("id", id).select("id");
  if (error) return dbError(error);
  if (!data?.length) return { error: t("errors.forbidden") };
  revalidatePath(`/e/${e.key}`);
  redirect(`/e/${e.key}`);
}

export async function performTransition(
  entityKey: string,
  id: string,
  transitionKey: string,
  _: ActionState,
  formData: FormData
): Promise<ActionState> {
  await requireUser();
  const t = await getTranslations();
  const supabase = await createClient();
  const comment = String(formData.get("comment") ?? "").trim();
  const { error } = await supabase.rpc("perform_transition", {
    p_entity: entityKey,
    p_id: id,
    p_transition: transitionKey,
    p_comment: comment || null,
  });
  if (error) return dbError(error);
  revalidatePath("/", "layout");
  return { ok: true, message: t("records.actionDone") };
}
