import Link from "next/link";
import type { EntityDef } from "@/lib/model-types";
import type { Row } from "@/lib/records";
import { formatValue, rowTitle, type Formatter } from "@/lib/model-helpers";

// Cards view: title, subtitle and an optional image (app.yaml `ui.cards`).
export function CardsView({ entity: e, rows, fmt }: { entity: EntityDef; rows: Row[]; fmt: Formatter }) {
  const cfg = e.ui.cards ?? { title: e.display };
  const sub = e.fields.find((f) => f.key === cfg.subtitle) ?? e.fields.find((f) => f.list && f.key !== cfg.title && f.key !== cfg.image);
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {rows.map((r) => {
        const img = cfg.image ? String(r[cfg.image] ?? "") : "";
        const title = cfg.title && cfg.title !== e.display ? String(r[cfg.title] ?? "") || rowTitle(e, r) : rowTitle(e, r);
        return (
          <li key={r.id}>
            <Link href={`/e/${e.key}/${r.id}`} className="flex items-center gap-3 rounded-lg border bg-card p-3 hover:border-primary">
              {cfg.image &&
                (/^https?:\/\//.test(img) ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={img} alt="" className="size-12 shrink-0 rounded-md object-cover" />
                ) : (
                  <span className="flex size-12 shrink-0 items-center justify-center rounded-md bg-muted text-lg font-semibold">
                    {title.slice(0, 1).toUpperCase()}
                  </span>
                ))}
              <span className="min-w-0">
                <span className="block truncate font-medium">{title}</span>
                {sub && <span className="block truncate text-sm text-muted-foreground">{formatValue(sub, r, fmt)}</span>}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
