import Link from "next/link";
import { notFound } from "next/navigation";
import { format } from "date-fns";
import { getTranslations } from "next-intl/server";
import { mayCreate, requireUser } from "@/lib/auth";
import { formatter, listRows, type ListFilters } from "@/lib/records";
import { entityByKey, k } from "@/lib/model-helpers";
import type { ViewKind } from "@/lib/model-types";
import { PageHeader, Panel } from "@/components/page-header";
import { LinkButton } from "@/components/link-button";
import { SearchableSelect } from "@/components/searchable-select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RecordsTable } from "@/components/views/records-table";
import { KanbanView } from "@/components/views/kanban-view";
import { CardsView } from "@/components/views/cards-view";
import { CalendarView, monthRange } from "@/components/views/calendar-view";

// Generic list of an entity. The available views (table, cards, kanban, calendar) come from
// the UI mapping of the model (app.yaml `entities.<Entity>.ui`, see `appforge ui suggest`).
export default async function EntityListPage({ params, searchParams }: PageProps<"/e/[entity]">) {
  const user = await requireUser();
  const { entity: key } = await params;
  const e = entityByKey(key);
  if (!e) notFound();
  const sp = await searchParams;
  const str = (n: string) => (typeof sp[n] === "string" && sp[n] ? (sp[n] as string) : undefined);
  const requested = str("view") as ViewKind | undefined;
  const view: ViewKind = requested && e.ui.views.includes(requested) ? requested : e.ui.view;
  const filters: ListFilters = { state: str("state"), q: str("q") };
  if (view === "calendar" && e.ui.calendar) {
    const { from, to } = monthRange(str("month"));
    filters.range = { start: e.ui.calendar.start, end: e.ui.calendar.end, from: format(from, "yyyy-MM-dd"), to: format(to, "yyyy-MM-dd") };
  }
  const [t, fmt, rows] = await Promise.all([getTranslations(), formatter(), listRows(e, filters)]);
  const keep = new URLSearchParams(Object.entries({ q: filters.q, state: filters.state }).filter(([, v]) => v) as [string, string][]).toString();

  return (
    <>
      <PageHeader
        title={t(k.plural(e))}
        actions={mayCreate(user, e.create) && <LinkButton href={`/e/${e.key}/new`}>{t("records.new")}</LinkButton>}
      />
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <form className="flex flex-wrap items-end gap-2">
          {view !== "table" && <input type="hidden" name="view" value={view} />}
          <Input name="q" defaultValue={filters.q ?? ""} placeholder={t("records.search")} className="w-64" />
          {e.workflow && view !== "kanban" && (
            <SearchableSelect
              name="state"
              aria-label={t("records.state")}
              defaultValue={filters.state ?? ""}
              className="w-56"
              options={[{ value: "", label: t("records.allStates") },
                        ...e.workflow.states.map((s) => ({ value: s.key, label: t(k.state(e, s.key)) }))]}
            />
          )}
          <Button type="submit" variant="outline">
            {t("common.filter")}
          </Button>
        </form>
        {e.ui.views.length > 1 && (
          <nav aria-label={t("records.views.label")} className="flex rounded-md border p-0.5 text-sm">
            {e.ui.views.map((v) => (
              <Link
                key={v}
                href={`?${keep}${keep ? "&" : ""}view=${v}`}
                aria-current={v === view ? "page" : undefined}
                className={`rounded px-3 py-1 ${v === view ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
              >
                {t(`records.views.${v}`)}
              </Link>
            ))}
          </nav>
        )}
      </div>
      {view === "kanban" ? (
        <KanbanView entity={e} rows={rows} fmt={fmt} />
      ) : view === "calendar" && e.ui.calendar ? (
        <Panel>
          <CalendarView entity={e} rows={rows} month={str("month")} query={keep} />
        </Panel>
      ) : rows.length === 0 ? (
        <Panel>
          <p className="py-6 text-center text-sm text-muted-foreground">{t("records.empty")}</p>
        </Panel>
      ) : view === "cards" ? (
        <CardsView entity={e} rows={rows} fmt={fmt} />
      ) : (
        <Panel>
          <RecordsTable entity={e} rows={rows} fmt={fmt} />
        </Panel>
      )}
    </>
  );
}
