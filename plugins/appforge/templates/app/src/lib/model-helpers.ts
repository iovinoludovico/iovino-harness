import { MODEL } from "@/lib/model";
import type { EntityDef, FieldDef } from "@/lib/model-types";

/** Entity by its key (URL segment), or null. */
export function entityByKey(key: string): EntityDef | null {
  return Object.prototype.hasOwnProperty.call(MODEL.entities, key) ? MODEL.entities[key] : null;
}

export function menuEntities(): EntityDef[] {
  return Object.values(MODEL.entities).filter((e) => e.menu).sort((a, b) => a.order - b.order);
}

/** i18n keys of the generated `model` namespace. */
export const k = {
  entity: (e: EntityDef) => `model.entities.${e.key}.label`,
  plural: (e: EntityDef) => `model.entities.${e.key}.plural`,
  field: (e: EntityDef, f: string) => `model.entities.${e.key}.fields.${f}`,
  state: (e: EntityDef, s: string) => `model.entities.${e.key}.states.${s}`,
  transition: (e: EntityDef, t: string) => `model.entities.${e.key}.transitions.${t}`,
  enumValue: (en: string, v: string) => `model.enums.${en}.${v}`,
  role: (r: string) => `model.roles.${r}`,
};

/** PostgREST select: scalar columns plus references embedded as {id, display}. */
export function selectFor(e: EntityDef, fields: FieldDef[] = e.fields): string {
  const cols = ["id", "created_at", "updated_at", "created_by"];
  if (e.codePrefix) cols.push("code");
  if (e.workflow) cols.push("state");
  for (const f of fields) {
    if (f.type === "ref" && f.many) {
      cols.push(`${f.key}:${f.joinTable}(target:${f.toTable}(id, ${displayColumn(f)}))`);
    } else if (f.type === "ref") {
      cols.push(f.key, `${f.key}_ref:${f.toTable}!${e.table}_${f.key}_fkey(id, ${displayColumn(f)})`);
    } else {
      cols.push(f.key);
    }
  }
  return [...new Set(cols)].join(", ");
}

function displayColumn(f: FieldDef): string {
  return f.to === "User" ? "full_name, email" : f.toDisplay === "id" ? "id" : `${f.toDisplay}`;
}

type Row = Record<string, unknown>;
export type RefOption = { value: string; label: string };

/** Display text of an embedded reference. */
export function refLabel(f: FieldDef, ref: unknown): string {
  if (!ref || typeof ref !== "object") return "";
  const r = ref as Row;
  if (f.to === "User") return String(r.full_name ?? r.email ?? "");
  return String(r[f.toDisplay ?? "id"] ?? r.id ?? "");
}

/** Display text of a row (code, display field or id). */
export function rowTitle(e: EntityDef, row: Row): string {
  if (e.display === "code" && row.code) return String(row.code);
  const v = row[e.display];
  return v === null || v === undefined || v === "" ? String(row.code ?? row.id ?? "") : String(v);
}

export type Formatter = {
  number: (n: number) => string;
  money: (n: number) => string;
  date: (iso: string) => string;
  datetime: (iso: string) => string;
  yes: string;
  no: string;
  enumLabel: (enumName: string, value: string) => string;
};

/** Human-readable value of a field in a row loaded with selectFor(). */
export function formatValue(f: FieldDef, row: Row, fmt: Formatter): string {
  const v = row[f.key];
  if (f.type === "ref" && f.many) {
    const items = (v as { target: Row | null }[] | null) ?? [];
    return items.map((x) => refLabel(f, x.target)).filter(Boolean).join(", ");
  }
  if (f.type === "ref") return refLabel(f, row[`${f.key}_ref`]);
  if (v === null || v === undefined || v === "") return "";
  switch (f.type) {
    case "bool":
      return v ? fmt.yes : fmt.no;
    case "money":
      return fmt.money(Number(v));
    case "int":
    case "number":
      return fmt.number(Number(v));
    case "date":
      return fmt.date(String(v));
    case "datetime":
      return fmt.datetime(String(v));
    case "enum":
      return fmt.enumLabel(f.enum!, String(v));
    case "json":
      return JSON.stringify(v);
    default:
      return String(v);
  }
}

/** Form data → column values (many-references returned apart). */
export function valuesFromForm(e: EntityDef, form: FormData): { values: Row; many: Record<string, string[]> } {
  const values: Row = {};
  const many: Record<string, string[]> = {};
  for (const f of e.fields) {
    if (f.readonly) continue;
    const name = `f_${f.key}`;
    if (f.type === "ref" && f.many) {
      many[f.key] = form.getAll(name).map(String).filter(Boolean);
      continue;
    }
    if (f.type === "bool") {
      values[f.key] = form.get(name) === "on" || form.get(name) === "true";
      continue;
    }
    const raw = form.get(name);
    const s = raw === null ? "" : String(raw).trim();
    if (s === "") {
      values[f.key] = null;
      continue;
    }
    switch (f.type) {
      case "int":
        values[f.key] = Number.parseInt(s, 10);
        break;
      case "number":
      case "money":
        values[f.key] = Number(s.replace(",", "."));
        break;
      case "email":
        values[f.key] = s.toLowerCase();
        break;
      case "json":
        if (f.widget === "tags") {
          values[f.key] = s.split(",").map((x) => x.trim()).filter(Boolean);
          break;
        }
        try {
          values[f.key] = JSON.parse(s);
        } catch {
          values[f.key] = s;
        }
        break;
      default:
        values[f.key] = s;
    }
  }
  return { values, many };
}

/** Client-side required-field check (the database enforces it anyway). */
export function missingRequired(e: EntityDef, values: Row): string[] {
  return e.fields
    .filter((f) => f.required && !f.readonly && !f.many && f.type !== "bool")
    .filter((f) => values[f.key] === null || values[f.key] === undefined || values[f.key] === "")
    .map((f) => f.key);
}
