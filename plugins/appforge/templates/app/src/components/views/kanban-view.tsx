import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { MODEL } from "@/lib/model";
import type { EntityDef } from "@/lib/model-types";
import type { Row } from "@/lib/records";
import { formatValue, k, rowTitle, type Formatter } from "@/lib/model-helpers";

// Board view: one column per workflow state (or per value of an enum field).
// Records move between columns through the workflow actions of the detail page.
export async function KanbanView({ entity: e, rows, fmt }: { entity: EntityDef; rows: Row[]; fmt: Formatter }) {
  const t = await getTranslations();
  const by = e.ui.kanban?.group_by ?? "state";
  const field = e.fields.find((f) => f.key === by);
  const columns =
    by === "state" && e.workflow
      ? e.workflow.states.map((s) => ({ key: s.key, label: t(k.state(e, s.key)), color: s.color }))
      : (MODEL.enums[field?.enum ?? ""] ?? []).map((v) => ({ key: v, label: fmt.enumLabel(field!.enum!, v), color: "#64748b" }));
  const details = e.fields.filter((f) => f.list && f.key !== by && f.key !== e.display).slice(0, 2);
  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {columns.map((c) => {
        const items = rows.filter((r) => String(r[by] ?? "") === c.key);
        return (
          <section key={c.key} className="w-72 shrink-0 rounded-lg border bg-muted/40 p-2">
            <h3 className="mb-2 flex items-center gap-2 px-1 text-sm font-semibold">
              <span className="size-2.5 rounded-full" style={{ background: c.color }} />
              {c.label}
              <span className="ml-auto text-xs font-normal text-muted-foreground">{items.length}</span>
            </h3>
            <ul className="space-y-2">
              {items.map((r) => (
                <li key={r.id}>
                  <Link href={`/e/${e.key}/${r.id}`} className="block rounded-md border bg-background p-2.5 text-sm shadow-xs hover:border-primary">
                    <span className="font-medium">{rowTitle(e, r)}</span>
                    {details.map((f) => {
                      const v = formatValue(f, r, fmt);
                      return v ? <span key={f.key} className="block truncate text-xs text-muted-foreground">{v}</span> : null;
                    })}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
