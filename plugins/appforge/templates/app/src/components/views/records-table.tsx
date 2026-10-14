import Link from "next/link";
import { getTranslations } from "next-intl/server";
import type { EntityDef } from "@/lib/model-types";
import type { Row } from "@/lib/records";
import { formatValue, k, rowTitle, type Formatter } from "@/lib/model-helpers";
import { StateBadge } from "@/components/state-badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

// Default list view: one column per field with `list: true`.
export async function RecordsTable({ entity: e, rows, fmt, hide = [] }: { entity: EntityDef; rows: Row[]; fmt: Formatter; hide?: string[] }) {
  const t = await getTranslations();
  const columns = e.fields.filter((f) => f.list && !hide.includes(f.key));
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {e.codePrefix && <TableHead>{t(k.field(e, "code"))}</TableHead>}
          {columns.map((f) => (
            <TableHead key={f.key}>{t(k.field(e, f.key))}</TableHead>
          ))}
          {e.workflow && <TableHead>{t("records.state")}</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => {
          const st = e.workflow?.states.find((s) => s.key === r.state);
          return (
            <TableRow key={r.id}>
              {e.codePrefix && (
                <TableCell className="font-medium">
                  <Link href={`/e/${e.key}/${r.id}`} className="hover:underline">{String(r.code)}</Link>
                </TableCell>
              )}
              {columns.map((f, i) => (
                <TableCell key={f.key}>
                  {!e.codePrefix && i === 0 ? (
                    <Link href={`/e/${e.key}/${r.id}`} className="font-medium hover:underline">
                      {formatValue(f, r, fmt) || rowTitle(e, r)}
                    </Link>
                  ) : (
                    formatValue(f, r, fmt)
                  )}
                </TableCell>
              ))}
              {e.workflow && <TableCell>{st && <StateBadge label={t(k.state(e, st.key))} color={st.color} />}</TableCell>}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
