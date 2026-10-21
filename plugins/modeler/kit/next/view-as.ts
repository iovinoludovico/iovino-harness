// «View as» of this app (installed by the modeler plugin when behavior.yaml declares `view_as`, upgraded by
// re-running `modeler install`): the cookies that keep the choice and the headers the Supabase server client sends.
// The database decides what they mean: `x-view-as` keeps one of the user's own roles (it removes privileges, never
// adds any); `x-view-as-user` lets who `view_as.users_by` lists use the application as another user, with what they
// do attributed to them (`impersonated_by`) and logged (`view_as_log`). Add `...viewAsHeaders()` to the
// `global.headers` of the server client; nothing else in the app has to know.

import { cookies } from "next/headers";

export const VIEW_AS_ROLE_COOKIE = "view_as";
export const VIEW_AS_USER_COOKIE = "view_as_user";
const ROLE = /^[a-z][a-z0-9_]*$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isRoleKey(value: unknown): value is string {
  return typeof value === "string" && ROLE.test(value);
}

/** The role the session is restricted to, or null. */
export async function viewAsRole(): Promise<string | null> {
  const value = (await cookies()).get(VIEW_AS_ROLE_COOKIE)?.value;
  return isRoleKey(value) ? value : null;
}

/** The profile id the session acts as, or null. */
export async function viewAsUser(): Promise<string | null> {
  const value = (await cookies()).get(VIEW_AS_USER_COOKIE)?.value;
  return value && UUID.test(value) ? value : null;
}

/** The headers for the Supabase server client: acting as a user takes precedence over a restricted role. */
export async function viewAsHeaders(): Promise<Record<string, string>> {
  const [role, user] = await Promise.all([viewAsRole(), viewAsUser()]);
  return user ? { "x-view-as-user": user } : role ? { "x-view-as": role } : {};
}
