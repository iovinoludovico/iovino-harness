import Link from "next/link";
import { addDays, addMonths, endOfMonth, endOfWeek, format, isSameMonth, parseISO, startOfMonth, startOfWeek } from "date-fns";
import { getLocale, getTranslations } from "next-intl/server";
import type { EntityDef } from "@/lib/model-types";
import type { Row } from "@/lib/records";
import { rowTitle } from "@/lib/model-helpers";

// Month calendar: records placed on the days between `ui.calendar.start` and `ui.calendar.end`.
export function monthRange(month: string | undefined) {
  const base = month && /^\d{4}-\d{2}$/.test(month) ? parseISO(`${month}-01`) : startOfMonth(new Date());
  const from = startOfWeek(startOfMonth(base), { weekStartsOn: 1 });
  const to = endOfWeek(endOfMonth(base), { weekStartsOn: 1 });
  return { base, from, to };
}

export async function CalendarView({ entity: e, rows, month, query }: { entity: EntityDef; rows: Row[]; month?: string; query: string }) {
  const [t, locale] = await Promise.all([getTranslations(), getLocale()]);
  const monthName = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" });
  const weekday = new Intl.DateTimeFormat(locale, { weekday: "short" });
  const cal = e.ui.calendar!;
  const { base, from, to } = monthRange(month);
  const days: Date[] = [];
  for (let d = from; d <= to; d = addDays(d, 1)) days.push(d);
  const day = (v: unknown) => (v ? String(v).slice(0, 10) : null);
  const on = (d: Date) => {
    const iso = format(d, "yyyy-MM-dd");
    return rows.filter((r) => {
      const s = day(r[cal.start]);
      const en = cal.end ? day(r[cal.end]) ?? s : s;
      return s !== null && s <= iso && iso <= (en ?? s);
    });
  };
  const link = (m: Date) => `?${query}${query ? "&" : ""}view=calendar&month=${format(m, "yyyy-MM")}`;
  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <Link href={link(addMonths(base, -1))} className="rounded-md border px-2 py-1 text-sm" aria-label={t("calendar.previous")}>‹</Link>
        <h3 className="min-w-40 text-center font-semibold capitalize">{monthName.format(base)}</h3>
        <Link href={link(addMonths(base, 1))} className="rounded-md border px-2 py-1 text-sm" aria-label={t("calendar.next")}>›</Link>
        <Link href={link(new Date())} className="ml-2 text-sm underline">{t("calendar.today")}</Link>
      </div>
      <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg border bg-border text-sm">
        {days.slice(0, 7).map((d) => (
          <div key={`h${d.toISOString()}`} className="bg-muted px-2 py-1 text-xs font-medium capitalize text-muted-foreground">{weekday.format(d)}</div>
        ))}
        {days.map((d) => {
          const items = on(d);
          return (
            <div key={d.toISOString()} className={`min-h-24 bg-background p-1 ${isSameMonth(d, base) ? "" : "opacity-50"}`}>
              <div className="mb-1 text-right text-xs text-muted-foreground">{format(d, "d")}</div>
              {items.slice(0, 3).map((r) => (
                <Link key={r.id} href={`/e/${e.key}/${r.id}`} className="mb-0.5 block truncate rounded bg-primary/10 px-1 text-xs hover:bg-primary/20">
                  {rowTitle(e, r)}
                </Link>
              ))}
              {items.length > 3 && <span className="text-xs text-muted-foreground">+{items.length - 3}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
