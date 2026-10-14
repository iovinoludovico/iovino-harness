"use server";

import { revalidatePath } from "next/cache";
import { getTranslations } from "next-intl/server";
import { createClient } from "@/lib/supabase/server";
import { requireRole } from "@/lib/auth";
import { dbError, type ActionState } from "@/lib/action-state";
import { MODEL } from "@/lib/model";

function roleAndScope(formData: FormData) {
  const role = String(formData.get("role") ?? "");
  const scope = String(formData.get("scope_id") ?? "") || null;
  return { role, scope };
}

export async function approveUser(profileId: string, _: ActionState, formData: FormData): Promise<ActionState> {
  await requireRole("admin");
  const t = await getTranslations("admin");
  const { role, scope } = roleAndScope(formData);
  const supabase = await createClient();
  const { error } = await supabase.rpc("approve_user", {
    p_profile_id: profileId,
    p_role: role || null,
    p_scope_ids: scope ? [scope] : null,
  });
  if (error) return dbError(error);
  revalidatePath("/admin/users");
  return { ok: true, message: t("approved") };
}

export async function addRole(profileId: string, _: ActionState, formData: FormData): Promise<ActionState> {
  await requireRole("admin");
  const t = await getTranslations();
  const { role, scope } = roleAndScope(formData);
  if (!role) return { error: t("validation.required") };
  if (MODEL.roles[role]?.scoped && !scope) return { error: t("errors.roleNeedsScope") };
  const supabase = await createClient();
  const { error } = await supabase
    .from("user_roles")
    .insert({ profile_id: profileId, role, scope_id: MODEL.roles[role]?.scoped ? scope : null });
  if (error) return dbError(error);
  revalidatePath("/admin/users");
  return { ok: true, message: t("admin.roleAdded") };
}

export async function removeRole(roleId: string): Promise<void> {
  await requireRole("admin");
  const supabase = await createClient();
  await supabase.from("user_roles").delete().eq("id", roleId);
  revalidatePath("/admin/users");
}

export async function setActive(profileId: string, active: boolean): Promise<void> {
  await requireRole("admin");
  const supabase = await createClient();
  await supabase.from("profiles").update({ active }).eq("id", profileId);
  revalidatePath("/admin/users");
}

/** Pre-registers a user by email (enabled at the first sign-in, roles assigned now). */
export async function preRegister(_: ActionState, formData: FormData): Promise<ActionState> {
  await requireRole("admin");
  const t = await getTranslations();
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return { error: t("validation.email") };
  const supabase = await createClient();
  const { error } = await supabase.from("profiles").insert({ email, approved_at: new Date().toISOString() });
  if (error) return dbError(error);
  revalidatePath("/admin/users");
  return { ok: true, message: t("admin.preRegistered") };
}
