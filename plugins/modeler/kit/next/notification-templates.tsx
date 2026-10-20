"use client";

// Notification texts of this app (installed by the modeler plugin, upgraded by re-running `modeler install`):
// a matrix template x language. Every cell shows where its text comes from: an override saved here (own), the
// text of the model (behavior.yaml `templates:`, the default), or nothing yet (missing). Editing a cell saves an
// override in public.notification_templates; "Reset" removes it so the model's text applies again. The
// placeholders {{…}} are those of the model (record paths, transition.label, actor.name, comment, url, reminder.days).

import { useMemo, useState, useTransition } from "react";
import { resetNotificationTemplate, saveNotificationTemplate, type TemplateOverride, type TemplateResult } from "@/lib/modeler/notification-actions";

type Texts = { subject?: string; body?: string };
type Behavior = { templates?: Record<string, Record<string, Texts>> };

type Props = {
  behavior: unknown;              // src/lib/modeler/behavior.json: the defaults (templates per language)
  overrides: TemplateOverride[];  // listNotificationTemplates()
  lang?: string;
  languages?: string[];           // the columns; default: the languages of the model
};

const TEXT = {
  it: { title: "Testi delle notifiche", own: "proprio", model: "dal modello", missing: "mancante", subject: "Oggetto", body: "Corpo",
        save: "Salva", reset: "Torna al modello", cancel: "Annulla", edit: "Modifica",
        note: "Un testo proprio sostituisce quello del modello per quella lingua; i segnaposto {{…}} sono quelli del modello." },
  en: { title: "Notification texts", own: "own", model: "from the model", missing: "missing", subject: "Subject", body: "Body",
        save: "Save", reset: "Back to the model", cancel: "Cancel", edit: "Edit",
        note: "An own text replaces the model's for that language; the placeholders {{…}} are those of the model." },
};

export function NotificationTemplates({ behavior, overrides, lang = "it", languages }: Props) {
  const t = TEXT[lang.startsWith("en") ? "en" : "it"];
  const defaults = useMemo(() => (behavior as Behavior | null)?.templates ?? {}, [behavior]);
  const [own, setOwn] = useState<Record<string, TemplateOverride>>(() => Object.fromEntries(overrides.map((o) => [`${o.key}|${o.locale}`, o])));
  const [editing, setEditing] = useState<{ key: string; locale: string; subject: string; body: string } | null>(null);
  const [result, setResult] = useState<TemplateResult | null>(null);
  const [pending, start] = useTransition();
  const cols = languages ?? Array.from(new Set(Object.values(defaults).flatMap((l) => Object.keys(l)))).sort();
  const keys = Array.from(new Set([...Object.keys(defaults), ...overrides.map((o) => o.key)])).sort();

  const cell = (key: string, locale: string) => {
    const o = own[`${key}|${locale}`];
    const d = defaults[key]?.[locale];
    if (o) return { kind: "own" as const, subject: o.subject, body: o.body };
    if (d?.subject) return { kind: "model" as const, subject: d.subject, body: d.body ?? "" };
    return { kind: "missing" as const, subject: "", body: "" };
  };
  const save = () => {
    if (!editing) return;
    const e = editing;
    start(async () => {
      const r = await saveNotificationTemplate(e.key, e.locale, e.subject, e.body);
      setResult(r);
      if (r.ok) {
        setOwn((cur) => ({ ...cur, [`${e.key}|${e.locale}`]: { key: e.key, locale: e.locale, subject: e.subject.trim(), body: e.body, updatedAt: new Date().toISOString() } }));
        setEditing(null);
      }
    });
  };
  const reset = (key: string, locale: string) => {
    start(async () => {
      const r = await resetNotificationTemplate(key, locale);
      setResult(r);
      if (r.ok) setOwn((cur) => { const next = { ...cur }; delete next[`${key}|${locale}`]; return next; });
      setEditing(null);
    });
  };
  const badge = { own: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100",
                  model: "bg-sky-100 text-sky-900 dark:bg-sky-900 dark:text-sky-100",
                  missing: "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100" };

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">{t.title}</h2>
      <p className="text-sm text-muted-foreground">{t.note}</p>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th className="border-b p-2 text-left">Template</th>
            {cols.map((l) => <th key={l} className="border-b p-2 text-left">{l}</th>)}
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => (
            <tr key={key} className="align-top">
              <td className="border-b p-2 font-mono text-xs">{key}</td>
              {cols.map((l) => {
                const c = cell(key, l);
                const isEditing = editing && editing.key === key && editing.locale === l;
                return (
                  <td key={l} className="border-b p-2">
                    <span className={`mr-2 rounded px-1.5 py-0.5 text-xs ${badge[c.kind]}`}>{t[c.kind]}</span>
                    {isEditing ? (
                      <div className="mt-1 space-y-1">
                        <input className="w-full rounded border px-2 py-1" value={editing.subject} placeholder={t.subject}
                               onChange={(ev) => setEditing({ ...editing, subject: ev.target.value })} />
                        <textarea className="w-full rounded border px-2 py-1" rows={4} value={editing.body} placeholder={t.body}
                                  onChange={(ev) => setEditing({ ...editing, body: ev.target.value })} />
                        <div className="flex gap-2">
                          <button type="button" className="rounded border px-2 py-1" disabled={pending} onClick={save}>{t.save}</button>
                          <button type="button" className="rounded border px-2 py-1" disabled={pending} onClick={() => setEditing(null)}>{t.cancel}</button>
                          {c.kind === "own" && <button type="button" className="rounded border px-2 py-1" disabled={pending} onClick={() => reset(key, l)}>{t.reset}</button>}
                        </div>
                      </div>
                    ) : (
                      <button type="button" className="text-left" title={t.edit}
                              onClick={() => setEditing({ key, locale: l, subject: c.subject, body: c.body })}>
                        <div className="font-medium">{c.subject || "—"}</div>
                        {c.body && <div className="whitespace-pre-wrap text-xs text-muted-foreground">{c.body}</div>}
                      </button>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {result && <p className={`text-sm ${result.ok ? "text-emerald-700" : "text-red-700"}`}>{result.message}</p>}
    </section>
  );
}
