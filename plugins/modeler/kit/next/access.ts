// Domain modeler of this app: who may open /admin/model and save proposals, and the database client.
// Written once by `modeler install` and never replaced: adapt it to the app (its admin check and its
// Supabase server client). The default expects `public.is_admin()`, as the model_change_requests policy does.

import { createClient } from "@/lib/supabase/server";

export type ModelerAdmin = { email: string };

export async function requireModelerAdmin(): Promise<ModelerAdmin> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("Not signed in");
  const { data: isAdmin, error } = await supabase.rpc("is_admin");
  if (error || !isAdmin) throw new Error("Admins only");
  return { email: user.email ?? "" };
}

export async function modelerDb() {
  return createClient();
}
