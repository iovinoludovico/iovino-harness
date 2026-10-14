import Link from "next/link";
import { format } from "date-fns";
import { getTranslations } from "next-intl/server";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { entityByKey, k, menuEntities } from "@/lib/model-helpers";
import { PageHeader, Panel } from "@/components/page-header";
import { StateBadge } from "@/components/state-badge";

type InboxRow = { entity: string; id: string; code: string | null; display: string | null; state: string; updated_at: string };

// Dashboard: records waiting for the current user (owner of their state) and the entities.
export default async function DashboardPage() {
  const user = await requireUser();
  const t = await getTranslations();
  const supabase = await createClient();
  const { data } = await supabase.rpc("my_inbox");
  const inbox = (data as InboxRow[] | null) ?? [];

  return (
    <>
      <PageHeader title={t("dashboard.title", { name: user.profile.full_name ?? user.profile.email })} />
      <section className="mb-10">
        <h2 className="mb-3 text-xl font-semibold">{t("dashboard.inbox")}</h2>
        <Panel>
          {inbox.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">{t("dashboard.inboxEmpty")}</p>
          ) : (
            <ul className="divide-y">
              {inbox.map((r) => {
                const e = entityByKey(r.entity);
                const st = e?.workflow?.states.find((s) => s.key === r.state);
                return (
                  <li key={`${r.entity}:${r.id}`} className="flex flex-wrap items-center justify-between gap-3 py-3">
                    <Link href={`/e/${r.entity}/${r.id}`} className="font-medium hover:underline">
                      {e ? t(k.entity(e)) : r.entity} · {r.code ?? r.display}
                      {r.code && r.display && r.display !== r.code ? <span className="text-muted-foreground"> — {r.display}</span> : null}
                    </Link>
                    <span className="flex items-center gap-3 text-sm text-muted-foreground">
                      {e && st && <StateBadge label={t(k.state(e, r.state))} color={st.color} />}
                      {format(new Date(r.updated_at), "dd/MM/yyyy")}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </section>
      <section>
        <h2 className="mb-3 text-xl font-semibold">{t("dashboard.entities")}</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {menuEntities().map((e) => (
            <Link key={e.key} href={`/e/${e.key}`} className="rounded-2xl border bg-card p-5 hover:border-primary">
              <p className="text-lg font-semibold">{t(k.plural(e))}</p>
              <p className="text-sm text-muted-foreground">{e.kind === "process" ? t("dashboard.process") : t("dashboard.registry")}</p>
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}
