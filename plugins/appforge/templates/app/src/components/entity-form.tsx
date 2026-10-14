"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ActionForm, SubmitButton } from "@/components/action-form";
import { FormField, NativeCheckbox } from "@/components/form-field";
import { SearchableSelect } from "@/components/searchable-select";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { ActionState } from "@/lib/action-state";
import { MODEL } from "@/lib/model";
import type { EntityDef, FieldDef } from "@/lib/model-types";
import { k, type RefOption } from "@/lib/model-helpers";

type Row = Record<string, unknown>;

// Form generated from the entity's fields (src/lib/model.ts). Inputs are named
// f_<field>; valuesFromForm() converts them back.
export function EntityForm({
  entity,
  row,
  options,
  action,
  submitLabel,
}: {
  entity: EntityDef;
  row?: Row | null;
  options: Record<string, RefOption[]>;
  action: (state: ActionState, formData: FormData) => Promise<ActionState>;
  submitLabel: string;
}) {
  const t = useTranslations();
  const fields = entity.fields.filter((f) => !f.readonly);
  return (
    <ActionForm action={action} className="grid gap-4 sm:grid-cols-2">
      {(state) => (
        <>
          {fields.map((f) => (
            <FormField
              key={f.key}
              label={`${t(k.field(entity, f.key))}${f.required ? " *" : ""}`}
              htmlFor={`f_${f.key}`}
              error={state?.fieldErrors?.[f.key]}
              className={f.widget === "textarea" || f.type === "json" || f.many ? "sm:col-span-2" : undefined}
            >
              <FieldInput field={f} row={row} options={options[f.key] ?? []} />
            </FormField>
          ))}
          <div className="sm:col-span-2">
            <SubmitButton>{submitLabel}</SubmitButton>
          </div>
        </>
      )}
    </ActionForm>
  );
}

function initial(f: FieldDef, row?: Row | null): string {
  const v = row && f.key in row ? row[f.key] : f.default;
  if (v === null || v === undefined) return "";
  if (f.type === "datetime") return String(v).slice(0, 16);
  if (f.type === "json") return JSON.stringify(v, null, 2);
  return String(v);
}

function FieldInput({ field: f, row, options }: { field: FieldDef; row?: Row | null; options: RefOption[] }) {
  const t = useTranslations();
  const name = `f_${f.key}`;
  const value = initial(f, row);
  // The widget comes from the UI mapping of the model (src/lib/model.ts, app.yaml `ui.widgets`).
  switch (f.widget) {
    case "textarea":
      return <Textarea id={name} name={name} rows={4} defaultValue={value} required={f.required} maxLength={f.maxLength} />;
    case "json":
      return <Textarea id={name} name={name} rows={4} defaultValue={value} className="font-mono text-xs" />;
    case "tags": {
      const list = Array.isArray(row?.[f.key]) ? (row![f.key] as unknown[]).join(", ") : value;
      return <Input id={name} name={name} defaultValue={list} placeholder="a, b, c" />;
    }
    case "checkbox":
    case "switch": {
      const checked = row && f.key in row ? Boolean(row[f.key]) : Boolean(f.default);
      return (
        <div className="flex h-9 items-center">
          {f.widget === "switch" ? (
            <label className="relative inline-flex cursor-pointer items-center">
              <input id={name} name={name} type="checkbox" role="switch" defaultChecked={checked} className="peer sr-only" />
              <span className="h-5 w-9 rounded-full bg-input transition-colors peer-checked:bg-primary peer-focus-visible:ring-2 peer-focus-visible:ring-ring" />
              <span className="pointer-events-none absolute left-0.5 top-0.5 size-4 rounded-full bg-background shadow transition-transform peer-checked:translate-x-4" />
            </label>
          ) : (
            <NativeCheckbox id={name} name={name} defaultChecked={checked} />
          )}
        </div>
      );
    }
    case "slider":
      return <SliderInput name={name} min={f.min ?? 0} max={f.max ?? 10} step={f.type === "int" ? 1 : 0.5} defaultValue={value} />;
    case "currency":
      return (
        <div className="relative">
          <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-muted-foreground">€</span>
          <Input id={name} name={name} type="number" inputMode="decimal" step={0.01} min={f.min} max={f.max}
                 defaultValue={value} required={f.required} className="pl-7" />
        </div>
      );
    case "number":
      return (
        <Input id={name} name={name} type="number" inputMode="decimal" defaultValue={value} required={f.required}
               step={f.type === "int" ? 1 : "any"} min={f.min} max={f.max} />
      );
    case "date":
      return <Input id={name} name={name} type="date" defaultValue={value} required={f.required} />;
    case "datetime":
      return <Input id={name} name={name} type="datetime-local" defaultValue={value} required={f.required} />;
    case "radio": {
      const values = MODEL.enums[f.enum!] ?? [];
      return (
        <div role="radiogroup" className="flex min-h-9 flex-wrap items-center gap-x-4 gap-y-1">
          {!f.required && (
            <label className="flex items-center gap-1.5 text-sm">
              <input type="radio" name={name} value="" defaultChecked={!value} className="accent-primary" />
              {t("common.dash")}
            </label>
          )}
          {values.map((v) => (
            <label key={v} className="flex items-center gap-1.5 text-sm">
              <input type="radio" name={name} value={v} defaultChecked={value === v} required={f.required} className="accent-primary" />
              {t(k.enumValue(f.enum!, v))}
            </label>
          ))}
        </div>
      );
    }
    case "select": {
      const values = MODEL.enums[f.enum!] ?? [];
      return (
        <SearchableSelect
          id={name}
          name={name}
          required={f.required}
          defaultValue={value}
          options={[...(f.required ? [] : [{ value: "", label: t("common.dash") }]),
                    ...values.map((v) => ({ value: v, label: t(k.enumValue(f.enum!, v)) }))]}
        />
      );
    }
    case "ref-checklist":
    case "ref-select": {
      if (f.many) {
        const selected = new Set(((row?.[f.key] as { target: { id: string } | null }[] | undefined) ?? []).map((x) => x.target?.id));
        if (f.widget === "ref-select") {
          return (
            <select id={name} name={name} multiple defaultValue={[...selected].filter(Boolean) as string[]}
                    className="h-40 w-full rounded-md border border-input bg-transparent p-1 text-sm">
              {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          );
        }
        return (
          <div className="grid max-h-56 gap-1 overflow-auto rounded-md border p-2 sm:grid-cols-2">
            {options.length === 0 && <p className="text-sm text-muted-foreground">{t("records.noOptions")}</p>}
            {options.map((o) => (
              <label key={o.value} className="flex items-center gap-2 text-sm">
                <NativeCheckbox name={name} value={o.value} defaultChecked={selected.has(o.value)} />
                {o.label}
              </label>
            ))}
          </div>
        );
      }
      return (
        <SearchableSelect
          id={name}
          name={name}
          required={f.required}
          defaultValue={value}
          options={[...(f.required ? [] : [{ value: "", label: t("common.dash") }]), ...options]}
        />
      );
    }
    case "image":
      return <ImageUrlInput name={name} defaultValue={value} required={f.required} />;
    default:
      return (
        <Input id={name} name={name} type={f.widget === "email" ? "email" : f.widget === "url" ? "url" : "text"}
               defaultValue={value} required={f.required} maxLength={f.maxLength} />
      );
  }
}

function SliderInput({ name, min, max, step, defaultValue }: { name: string; min: number; max: number; step: number; defaultValue: string }) {
  const [v, setV] = useState(defaultValue || String(min));
  return (
    <div className="flex h-9 items-center gap-3">
      <input id={name} name={name} type="range" min={min} max={max} step={step} value={v}
             onChange={(e) => setV(e.target.value)} className="w-full accent-primary" />
      <span className="w-10 text-right text-sm tabular-nums">{v}</span>
    </div>
  );
}

function ImageUrlInput({ name, defaultValue, required }: { name: string; defaultValue: string; required: boolean }) {
  const [v, setV] = useState(defaultValue);
  return (
    <div className="flex items-center gap-3">
      {/^https?:\/\//.test(v) ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={v} alt="" className="size-10 shrink-0 rounded-md border object-cover" />
      ) : (
        <span className="size-10 shrink-0 rounded-md border bg-muted" />
      )}
      <Input id={name} name={name} type="url" value={v} onChange={(e) => setV(e.target.value)} required={required} />
    </div>
  );
}
