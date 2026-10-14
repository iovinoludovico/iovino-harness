import "server-only";
import { cache } from "react";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export type Profile = {
  id: string;
  auth_user_id: string | null;
  email: string;
  full_name: string | null;
  locale: string;
  active: boolean;
  approved_at: string | null;
};
export type UserRole = { id: string; role: string; scope_id: string | null };

export type CurrentUser = {
  profile: Profile;
  roles: UserRole[];
  isAdmin: boolean;
  hasRole: (role: string) => boolean;
  /** Scope ids (rows of the scope entity) where the user holds the role. */
  scopesFor: (role: string) => string[];
};

// Loads the signed-in user's profile and roles once per request.
export const getCurrentUser = cache(async (): Promise<CurrentUser | null> => {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;
  const { data: profile } = await supabase.from("profiles").select("*").eq("auth_user_id", user.id).maybeSingle();
  if (!profile) return null;
  const { data: roles } = await supabase.from("user_roles").select("id, role, scope_id").eq("profile_id", profile.id);
  const list = (roles ?? []) as UserRole[];
  const has = (role: string) => list.some((r) => r.role === role);
  return {
    profile: profile as Profile,
    roles: list,
    isAdmin: has("admin"),
    hasRole: has,
    scopesFor: (role) => list.filter((r) => r.role === role && r.scope_id).map((r) => r.scope_id!),
  };
});

/** Use in pages/actions that require a signed-in, approved and active user. */
export async function requireUser(): Promise<CurrentUser> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  const current = await getCurrentUser();
  if (!current) redirect("/unauthorized?reason=inactive");
  if (!current.profile.approved_at) redirect("/pending");
  if (!current.profile.active) redirect("/unauthorized?reason=inactive");
  return current;
}

/** Restricts a page/action to users holding at least one of the roles (admin always passes). */
export async function requireRole(...roles: string[]): Promise<CurrentUser> {
  const current = await requireUser();
  if (!current.isAdmin && !roles.some((r) => current.hasRole(r))) redirect("/");
  return current;
}

/** UI hint: may the user create records of an entity? The database has the final word (RLS). */
export function mayCreate(user: CurrentUser, principals: string[]): boolean {
  if (user.isAdmin || principals.includes("all")) return true;
  return principals.some((p) => user.hasRole(p));
}
