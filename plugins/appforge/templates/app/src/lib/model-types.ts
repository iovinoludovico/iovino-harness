// Types of the static metamodel generated in src/lib/model.ts (do not edit model.ts).

export type FieldType =
  | "string" | "text" | "email" | "url" | "int" | "number" | "money" | "bool"
  | "date" | "datetime" | "enum" | "ref" | "json";

/** UI component rendering a field (default mapping by type/constraints, overridable in app.yaml `ui.widgets`). */
export type Widget =
  | "text" | "textarea" | "email" | "url" | "image" | "number" | "slider" | "currency" | "checkbox" | "switch"
  | "date" | "datetime" | "select" | "radio" | "ref-select" | "ref-checklist" | "json" | "tags";

export type ViewKind = "table" | "cards" | "kanban" | "calendar";

export type EntityUi = {
  view: ViewKind;
  views: ViewKind[];
  /** "state" (workflow) or an enum field. */
  kanban?: { group_by: string };
  calendar?: { start: string; end?: string };
  cards?: { title: string; subtitle?: string | null; image?: string | null };
  /** Records of other entities that reference this one, listed on the detail page. */
  related: { entity: string; field: string }[];
};

export type FieldDef = {
  key: string;
  type: FieldType;
  widget: Widget;
  required: boolean;
  list: boolean;
  readonly: boolean;
  many: boolean;
  enum?: string;
  /** Reference target: entity name or "User". */
  to?: string;
  toTable?: string;
  /** Key of the target entity ("user" for User). */
  toEntity?: string;
  /** Column shown for a referenced row. */
  toDisplay?: string;
  joinTable?: string;
  min?: number;
  max?: number;
  maxLength?: number;
  default?: unknown;
};

export type StateDef = { key: string; kind: "initial" | "normal" | "final"; color: string; owner: string[] };
export type TransitionDef = { key: string; from: string[]; to: string; trigger: "manual" | "timed"; comment: string };

export type EntityDef = {
  name: string;
  /** snake_case key: URL segment, event prefix, i18n key. */
  key: string;
  table: string;
  kind: "registry" | "process";
  icon: string;
  menu: boolean;
  order: number;
  codePrefix: string | null;
  display: string;
  scopeField: string | null;
  fields: FieldDef[];
  /** Principals allowed to create (UI hint only: the database decides). */
  create: string[];
  ui: EntityUi;
  workflow?: { states: StateDef[]; transitions: TransitionDef[] };
};

export type AppModel = {
  app: { name: string; slug: string; locales: string[]; scope: string | null };
  roles: Record<string, { scoped: boolean }>;
  enums: Record<string, string[]>;
  entities: Record<string, EntityDef>;
};
