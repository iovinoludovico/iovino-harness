import { notFound } from "next/navigation";
import { format } from "date-fns";
import { getLocale, getTranslations } from "next-intl/server";
import { mayCreate, requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { availableTransitions, formatter, getRow, history, listRows, refOptionsFor } from "@/lib/records";
import { entityByKey, formatValue, k, rowTitle } from "@/lib/model-helpers";
import { pickLabel } from "@/i18n/config";
import { StateBadge } from "@/components/state-badge";
import { EntityForm } from "@/components/entity-form";
import { TransitionActions } from "@/components/transition-actions";
import { DeleteButton } from "@/components/delete-button";
import { LinkButton } from "@/components/link-button";
import { RecordsTable } from "@/components/views/records-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { deleteRow, performTransition, saveRow } from "../../actions";

// Generic detail page: facts, workflow actions, edit form, history.
export default async function EntityDetailPage({ params }: PageProps<"/e/[entity]/[id]">) {
  const user = await requireUser();
  const { entity: key, id } = await params;
  const e = entityByKey(key);
  if (!e) notFound();
  const row = await getRow(e, id);
  if (!row) notFound();
  const supabase = await createClient();
  const [t, locale, fmt, transitions, events, options, canEdit, canDelete] = await Promise.all([
    getTranslations(),
    getLocale(),
    formatter(),
    availableTransitions(e, id),
    history(e, id),
    refOptionsFor(e),
    supabase.rpc("can", { p_entity: e.key, p_action: "update", p_id: id }).then((r) => r.data === true),
    supabase.rpc("can", { p_entity: e.key, p_action: "delete", p_id: id }).then((r) => r.data === true),
  ]);
  // Related panels: records of other entities referencing this one (containments by default, see ui.related).
  const related = await Promise.all(
    e.ui.related.map(async (r) => {
      const child = entityByKey(r.entity);
      return child ? { child, field: r.field, rows: await listRows(child, { parent: { field: r.field, id } }) } : null;
    }),
  );
  const state = e.workflow?.states.find((s) => s.key === row.state);
  const fieldLabel = (f: string) => (t.has(k.field(e, f)) ? t(k.field(e, f)) : f);
  const describe = (c: { field: string; op: string; value?: unknown }) =>
    [fieldLabel(c.field), t(`ops.${c.op}`), c.value === undefined ? "" : String(c.value)].join(" ").trim();
  const who = (a: { type: string; name?: string | null; email?: string }) => (a.type === "system" ? t("common.system") : (a.name ?? a.email ?? ""));

  return (
    <>
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="mb-1.5 text-sm text-muted-foreground">{t(k.entity(e))}</p>
          <h1 className="flex flex-wrap items-center gap-3 text-4xl font-bold">
            {rowTitle(e, row)}
            {state && <StateBadge label={t(k.state(e, state.key))} color={state.color} />}
          </h1>
        </div>
        {e.workflow && (
          <div className="max-w-xl">
            <TransitionActions
              action={performTransition.bind(null, e.key, id)}
              transitions={transitions.map((tr) => ({
                key: tr.key,
                labels: { [locale]: t.has(k.transition(e, tr.key)) ? t(k.transition(e, tr.key)) : pickLabel(tr.labels, locale) },
                to: { key: tr.to.key, labels: { [locale]: t(k.state(e, tr.to.key)) } },
                comment: tr.comment,
                unmet: tr.unmet.map(describe),
              }))}
            />
          </div>
        )}
      </header>

      <div className="space-y-6">
        <Card>
          <CardContent>
            <dl className="grid gap-x-6 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
              {e.fields.map((f) => {
                const wide = f.type === "text" || f.type === "json";
                return (
                  <div key={f.key} className={wide ? "min-w-0 sm:col-span-2 lg:col-span-3" : "min-w-0"}>
                    <dt className="text-[13px] text-muted-foreground">{fieldLabel(f.key)}</dt>
                    <dd className={wide ? "mt-1 whitespace-pre-wrap" : "mt-1 truncate text-[17px] font-semibold"}>
                      {formatValue(f, row, fmt) || t("common.dash")}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </CardContent>
        </Card>

        {related.map(
          (r) =>
            r && (
              <Card key={`${r.child.key}.${r.field}`}>
                <CardHeader className="flex flex-row items-center justify-between gap-2">
                  <CardTitle>
                    {t(k.plural(r.child))}
                    {r.child.fields.filter((f) => f.to === e.name).length > 1 && (
                      <span className="ml-2 text-sm font-normal text-muted-foreground">({t(k.field(r.child, r.field))})</span>
                    )}
                  </CardTitle>
                  {mayCreate(user, r.child.create) && (
                    <LinkButton href={`/e/${r.child.key}/new?f_${r.field}=${id}`} variant="outline" size="sm">
                      {t("records.new")}
                    </LinkButton>
                  )}
                </CardHeader>
                <CardContent>
                  {r.rows.length === 0 ? (
                    <p className="text-sm text-muted-foreground">{t("records.empty")}</p>
                  ) : (
                    <RecordsTable entity={r.child} rows={r.rows} fmt={fmt} hide={[r.field]} />
                  )}
                </CardContent>
              </Card>
            ),
        )}

        {canEdit && (
          <Card>
            <CardHeader>
              <CardTitle>{t("records.edit")}</CardTitle>
            </CardHeader>
            <CardContent>
              <EntityForm
                key={String(row.updated_at)}
                entity={e}
                row={row}
                options={options}
                action={saveRow.bind(null, e.key, id)}
                submitLabel={t("common.save")}
              />
            </CardContent>
          </Card>
        )}

        {e.workflow && (
          <Card>
            <CardHeader>
              <CardTitle>{t("records.history")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-4">
                {events.map((h) => (
                  <li key={h.id}>
                    <p>
                      <strong>{h.transition && t.has(k.transition(e, h.transition)) ? t(k.transition(e, h.transition)) : t(k.state(e, h.to_state))}</strong>{" "}
                      <span className="text-muted-foreground">
                        {who(h.actor)}, {format(new Date(h.created_at), "dd/MM/yyyy HH:mm")}
                      </span>
                    </p>
                    {h.comment && <p className="mt-0.5 whitespace-pre-wrap text-foreground/80">«{h.comment}»</p>}
                  </li>
                ))}
                <li>
                  <strong>{t("records.created")}</strong>{" "}
                  <span className="text-muted-foreground">{format(new Date(String(row.created_at)), "dd/MM/yyyy HH:mm")}</span>
                </li>
              </ol>
            </CardContent>
          </Card>
        )}

        {canDelete && (
          <div className="flex justify-end">
            <DeleteButton action={deleteRow.bind(null, e.key, id)} />
          </div>
        )}
      </div>
    </>
  );
}
