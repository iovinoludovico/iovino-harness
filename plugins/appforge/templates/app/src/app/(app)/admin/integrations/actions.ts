"use server";

import { revalidatePath } from "next/cache";
import { getTranslations } from "next-intl/server";
import { createClient } from "@/lib/supabase/server";
import { requireRole } from "@/lib/auth";
import { dbError, type ActionState } from "@/lib/action-state";

const done = () => revalidatePath("/admin/integrations");

export async function createEndpoint(_: ActionState, formData: FormData): Promise<ActionState> {
  await requireRole("admin");
  const t = await getTranslations();
  const name = String(formData.get("name") ?? "").trim();
  const url = String(formData.get("url") ?? "").trim();
  const filters = String(formData.get("event_filters") ?? "*").split(",").map((s) => s.trim()).filter(Boolean);
  const user = String(formData.get("basic_auth_username") ?? "").trim();
  const password = String(formData.get("basic_auth_password") ?? "");
  if (!name || !/^https?:\/\//.test(url)) return { error: t("validation.checkFields") };
  const supabase = await createClient();
  const { error } = await supabase.from("webhook_endpoints").insert({
    name,
    url,
    event_filters: filters.length ? filters : ["*"],
    basic_auth_username: user || null,
    basic_auth_password: user ? password : null,
  });
  if (error) return dbError(error);
  done();
  return { ok: true, message: t("integrations.created") };
}

export async function toggleEndpoint(id: string, active: boolean): Promise<void> {
  await requireRole("admin");
  const supabase = await createClient();
  await supabase.from("webhook_endpoints").update({ active }).eq("id", id);
  done();
}

export async function deleteEndpoint(id: string): Promise<void> {
  await requireRole("admin");
  const supabase = await createClient();
  await supabase.from("webhook_endpoints").delete().eq("id", id);
  done();
}

export async function sendTest(id: string): Promise<void> {
  await requireRole("admin");
  const supabase = await createClient();
  await supabase.rpc("send_test_webhook", { p_endpoint_id: id });
  done();
}

export async function rotateSecret(id: string): Promise<void> {
  await requireRole("admin");
  const supabase = await createClient();
  await supabase.rpc("rotate_webhook_secret", { p_endpoint_id: id });
  done();
}

export async function redeliver(deliveryId: string): Promise<void> {
  await requireRole("admin");
  const supabase = await createClient();
  await supabase.rpc("redeliver_webhook", { p_delivery_id: deliveryId });
  done();
}
