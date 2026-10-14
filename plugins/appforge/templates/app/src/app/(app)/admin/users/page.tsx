import { getTranslations } from "next-intl/server";
import { format } from "date-fns";
import { requireRole } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { MODEL } from "@/lib/model";
import { entityByKey } from "@/lib/model-helpers";
import { refOptions } from "@/lib/records";
import { PageHeader, Panel } from "@/components/page-header";
import { ActionForm, SubmitButton } from "@/components/action-form";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { addRole, approveUser, preRegister, removeRole, setActive } from "./actions";
import { RoleForm } from "./role-form";

type ProfileRow = {
  id: string;
  email: string;
  full_name: string | null;
  active: boolean;
  approved_at: string | null;
  last_sign_in_at: string | null;
  roles: { id: string; role: string; scope_id: string | null }[];
};

export default async function UsersPage() {
  await requireRole("admin");
  const t = await getTranslations();
  const supabase = await createClient();
  const { data } = await supabase
    .from("profiles")
    .select("id, email, full_name, active, approved_at, last_sign_in_at, roles:user_roles(id, role, scope_id)")
    .order("approved_at", { ascending: true, nullsFirst: true })
    .order("email");
  const users = (data ?? []) as ProfileRow[];
  const scopeEntity = MODEL.app.scope ? entityByKey(MODEL.app.scope) : null;
  const scopes = scopeEntity
    ? await refOptions({ key: "scope", type: "ref", widget: "ref-select", to: scopeEntity.name, required: true, list: false, readonly: false, many: false })
    : [];
  const scopeName = (id: string | null) => scopes.find((s) => s.value === id)?.label ?? "";

  return (
    <>
      <PageHeader title={t("admin.usersTitle")} description={t("admin.usersDescription")} />
      <Panel className="mb-6 py-4">
        <ActionForm action={preRegister} className="flex flex-wrap items-center gap-2 space-y-0" resetOnSuccess>
          <Input name="email" type="email" placeholder={t("admin.emailToRegister")} className="w-72" required />
          <SubmitButton variant="outline">{t("admin.preRegister")}</SubmitButton>
        </ActionForm>
      </Panel>
      <Panel>
        <ul className="divide-y">
          {users.map((u) => (
            <li key={u.id} className="space-y-2 py-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium">
                    {u.full_name ?? u.email} {!u.active && <span className="text-destructive">({t("admin.inactive")})</span>}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {u.email}
                    {u.last_sign_in_at && ` · ${t("admin.lastSignIn")} ${format(new Date(u.last_sign_in_at), "dd/MM/yyyy")}`}
                  </p>
                </div>
                {u.approved_at && (
                  <form action={setActive.bind(null, u.id, !u.active)}>
                    <Button type="submit" variant="ghost" size="sm">
                      {u.active ? t("admin.deactivate") : t("admin.activate")}
                    </Button>
                  </form>
                )}
              </div>
              {!u.approved_at ? (
                <div className="rounded-lg bg-muted/50 p-3">
                  <p className="mb-2 text-sm">{t("admin.pending")}</p>
                  <RoleForm action={approveUser.bind(null, u.id)} scopes={scopes} submitLabel={t("admin.approve")} optionalRole />
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  {u.roles.map((r) => (
                    <form key={r.id} action={removeRole.bind(null, r.id)} className="inline-flex">
                      <span className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs">
                        {t(`model.roles.${r.role}`)}
                        {r.scope_id && ` · ${scopeName(r.scope_id)}`}
                        <button type="submit" className="ml-1 text-muted-foreground hover:text-destructive" aria-label={t("admin.removeRole")}>
                          ×
                        </button>
                      </span>
                    </form>
                  ))}
                  <RoleForm action={addRole.bind(null, u.id)} scopes={scopes} submitLabel={t("admin.addRole")} />
                </div>
              )}
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}
