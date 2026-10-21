"use server";

// «View as»: the server actions behind the switcher, the «view as user» button and the banners (installed by the
// modeler plugin, replaced by `modeler install`). The database enforces everything (`view_as_role`,
// `view_as_profile_id`, `view_as_audit`): these actions only keep the cookies and record start and end.

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { modelerDb } from "./access";
import { isRoleKey, VIEW_AS_ROLE_COOKIE, VIEW_AS_USER_COOKIE, viewAsUser } from "./view-as";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const COOKIE = { path: "/", sameSite: "lax" as const, httpOnly: true };

/** Restricts the session to one of the user's roles (null: all of them). The database ignores a role the user does not hold. */
export async function setViewAsRole(role: string | null): Promise<void> {
  const store = await cookies();
  if (isRoleKey(role)) store.set(VIEW_AS_ROLE_COOKIE, role, COOKIE);
  else store.delete(VIEW_AS_ROLE_COOKIE);
  revalidatePath("/", "layout");
}

/** Starts using the application as another user: `view_as_audit` checks the real caller and records the start. */
export async function startViewAsUser(profileId: string, home = "/"): Promise<void> {
  if (!UUID.test(profileId) || (await viewAsUser())) redirect(home);
  const db = await modelerDb();
  const { error } = await db.rpc("view_as_audit", { p_profile: profileId, p_start: true });
  if (error) throw new Error(error.message);
  const store = await cookies();
  store.delete(VIEW_AS_ROLE_COOKIE);
  store.set(VIEW_AS_USER_COOKIE, profileId, COOKIE);
  revalidatePath("/", "layout");
  redirect(home);
}

/** Back to oneself: the cookie goes first, so the audit runs as the real user. */
export async function stopViewAsUser(back = "/"): Promise<void> {
  const id = await viewAsUser();
  const store = await cookies();
  store.delete(VIEW_AS_USER_COOKIE);
  if (id) {
    const db = await modelerDb();
    await db.rpc("view_as_audit", { p_profile: id, p_start: false });
  }
  revalidatePath("/", "layout");
  redirect(back);
}
