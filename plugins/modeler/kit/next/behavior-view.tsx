"use client";

// Behaviour of the domain next to the modeler (installed by the modeler plugin, upgraded by re-running `modeler install`):
// a read-only view of src/lib/modeler/behavior.json (behavior.yaml as `npm run model:sync` writes it): roles, one
// workflow per class (states, transitions), derived attributes with their formula, events, reactions, subscriptions.
// The same content as docs/BEHAVIOR.md; the class selected in the editor is highlighted (no scrolling: the diagram
// stays where the user is looking). The behaviour changes in
// behavior.yaml (/modeler:behavior), not here.

import type { ReactNode } from "react";

type Label = string | Record<string, string> | null | undefined;
type Typed = { text: string; type?: string } | null | undefined;
type State = {
  initial?: boolean; final?: boolean; label?: Label; color?: string; owner?: string[]; editable_by?: string[];
  reminder?: { after?: string; template?: string } | null;
};
type Transition = {
  from?: string[]; to?: string | null; by?: string[]; when?: Typed; guard?: Typed; comment?: string | null;
  at?: string | null; emits?: string[]; label?: Label;
};
type Workflow = {
  state?: string; states?: Record<string, State>; transitions?: Record<string, Transition>;
  revert?: { by?: string[]; final_by?: string[]; comment?: string | null } | null;
};
type Reaction = { name?: string; event?: string; when?: Typed; notify?: string[]; template?: string };
type Subscription = { name?: string; url?: string; url_env?: string; events?: string[] };
type Use = { kind: string; of: string };
type Uses = Record<string, { attributes?: Record<string, Use[]>; references?: Record<string, Use[]>; class?: Use[] }>;
export type Behavior = {
  doc?: string;
  uses?: Uses;
  roles?: Record<string, { scope?: string | null; label?: Label }>;
  derivations?: Record<string, Record<string, Typed>>;
  workflows?: Record<string, Workflow>;
  events?: Record<string, Record<string, { doc?: string }>>;
  reactions?: Reaction[];
  subscriptions?: Subscription[];
};
type Metamodel = { classes?: Record<string, { attributes?: Record<string, { derived?: boolean }> }> };

type Props = {
  behavior: unknown;          // src/lib/modeler/behavior.json
  metamodel?: unknown;        // src/lib/modeler/metamodel.json: which attributes are derived (also those computed in code)
  lang?: string;
  selected?: string | null;   // the class selected in the editor (`select` event): its workflow and derivations are highlighted
};

const TEXT = {
  it: {
    title: "Comportamento", note: "Generato da behavior.yaml (npm run model:sync): il comportamento si modifica nel modello con /modeler:behavior, non qui.",
    roles: "Ruoli", role: "Ruolo", label: "Etichetta", scope: "Ambito", global: "globale", per: (c: string) => `per ${c}`,
    builtinRoles: "Oltre ai ruoli predefiniti admin (amministratori) e creator (chi ha creato il record).",
    workflow: (c: string) => `Workflow di ${c}`, stateAttr: (a: string) => `Lo stato è l'attributo ${a}.`,
    states: "Stati", state: "Stato", kind: "Tipo", initial: "iniziale", final: "finale", owner: "In attesa di", editableBy: "Modificabile da",
    reminder: "Sollecito", after: (d: string, t: string) => `dopo ${d} (${t})`,
    transitions: "Transizioni", transition: "Transizione", fromTo: "Da → A", by: "Chi", when: "Condizione", guard: "Requisito",
    comment: "Commento", required: "obbligatorio", optional: "facoltativo", emits: "Eventi", system: (at: string) => `sistema: ${at}`,
    revert: (by: string, finalBy: string, c: string) => `Ritorno a uno stato precedente: ${by}; da uno stato finale: ${finalBy}; commento ${c}.`,
    derivations: "Attributi calcolati", cls: "Classe", attribute: "Attributo", formula: "Formula", inCode: "calcolato nel codice",
    involved: "Classi coinvolte nel comportamento", feature: "Attributo o riferimento", usedBy: "Usato da",
    involvedNote: "Classi senza workflow di cui il comportamento legge o usa attributi e riferimenti (formule, condizioni, destinatari, ambiti dei ruoli).",
    kinds: { derivation: "derivazione", guard: "requisito", when: "condizione", at: "scadenza", by: "chi", owner: "in attesa di", editable_by: "modificabile da", notify: "destinatario", revert: "ritorno", scope: "ambito del ruolo" } as Record<string, string>,
    events: "Eventi", event: "Evento", description: "Descrizione",
    lifecycle: "Ogni classe emette created, updated, deleted; una classe con workflow anche transitioned, completed, reverted, reminder.",
    reactions: "Reazioni", name: "Nome", recipients: "Destinatari", template: "Template",
    subscriptions: "Sottoscrizioni", url: "URL", none: "—",
  },
  en: {
    title: "Behaviour", note: "Generated from behavior.yaml (npm run model:sync): the behaviour changes in the model with /modeler:behavior, not here.",
    roles: "Roles", role: "Role", label: "Label", scope: "Scope", global: "global", per: (c: string) => `per ${c}`,
    builtinRoles: "Besides the built-in roles admin (administrators) and creator (who created the record).",
    workflow: (c: string) => `Workflow of ${c}`, stateAttr: (a: string) => `The state is the attribute ${a}.`,
    states: "States", state: "State", kind: "Kind", initial: "initial", final: "final", owner: "Waiting for", editableBy: "Editable by",
    reminder: "Reminder", after: (d: string, t: string) => `after ${d} (${t})`,
    transitions: "Transitions", transition: "Transition", fromTo: "From → To", by: "Who", when: "Condition", guard: "Requirement",
    comment: "Comment", required: "required", optional: "optional", emits: "Events", system: (at: string) => `system: ${at}`,
    revert: (by: string, finalBy: string, c: string) => `Back to a previous state: ${by}; from a final state: ${finalBy}; comment ${c}.`,
    derivations: "Derived attributes", cls: "Class", attribute: "Attribute", formula: "Formula", inCode: "computed in code",
    involved: "Classes involved in the behaviour", feature: "Attribute or reference", usedBy: "Used by",
    involvedNote: "Classes without a workflow whose attributes and references the behaviour reads or points to (formulas, conditions, recipients, role scopes).",
    kinds: { derivation: "derivation", guard: "requirement", when: "condition", at: "due", by: "who", owner: "waiting for", editable_by: "editable by", notify: "recipient", revert: "revert", scope: "role scope" } as Record<string, string>,
    events: "Events", event: "Event", description: "Description",
    lifecycle: "Every class emits created, updated, deleted; a class with a workflow also transitioned, completed, reverted, reminder.",
    reactions: "Reactions", name: "Name", recipients: "Recipients", template: "Template",
    subscriptions: "Subscriptions", url: "URL", none: "—",
  },
};

const label = (spec: Label, key: string, lang: string) => (typeof spec === "string" ? spec : spec?.[lang]) || key;

function Code({ children }: { children?: string | null }) {
  if (!children) return null;
  return <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">{children}</code>;
}

function Codes({ items }: { items?: string[] }) {
  if (!items?.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {items.map((x) => (
        <Code key={x}>{x}</Code>
      ))}
    </span>
  );
}

function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  if (!rows.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} className="border-b px-2 py-1 text-left font-medium text-muted-foreground">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j} className="border-b px-2 py-1 align-top">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BehaviorView({ behavior, metamodel, lang = "it", selected = null }: Props) {
  const l = lang.startsWith("en") ? "en" : "it";
  const t = TEXT[l];
  const b = (behavior && typeof behavior === "object" ? behavior : {}) as Behavior;
  const mm = (metamodel && typeof metamodel === "object" ? metamodel : {}) as Metamodel;
  const workflows = b.workflows ?? {};

  // derived attributes: the flag is in the metamodel, the formula in the behaviour (or the attribute is computed in code)
  const derived: [string, string, Typed][] = [];
  const classes = Object.keys(mm.classes ?? {}).length ? Object.keys(mm.classes ?? {}) : Object.keys(b.derivations ?? {});
  for (const cn of classes) {
    const attrs = mm.classes?.[cn]?.attributes;
    const names = attrs ? Object.keys(attrs).filter((an) => attrs[an]?.derived) : Object.keys(b.derivations?.[cn] ?? {});
    for (const an of names) derived.push([cn, an, b.derivations?.[cn]?.[an]]);
  }
  const hi = (cn: string) => (cn === selected ? "bg-sky-50 dark:bg-sky-950" : "");
  const roles = Object.entries(b.roles ?? {});
  // classes without a workflow that the behaviour uses: the involvement the tables above do not show
  const involved: [string, string, Use[]][] = [];
  for (const [cn, g] of Object.entries(b.uses ?? {})) {
    if (workflows[cn]) continue;
    for (const [fn, us] of Object.entries(g.attributes ?? {})) involved.push([cn, fn, us]);
    for (const [fn, us] of Object.entries(g.references ?? {})) involved.push([cn, fn, us]);
    if (g.class?.length) involved.push([cn, "—", g.class]);
  }
  const usedBy = (us: Use[]) => us.map((u) => `${t.kinds[u.kind] ?? u.kind}: ${u.of}`).join(", ");
  const events = Object.entries(b.events ?? {}).flatMap(([cn, evs]) => Object.entries(evs ?? {}).map(([en, ev]) => [cn, en, ev?.doc ?? ""] as const));
  const reactions = b.reactions ?? [];
  const subscriptions = b.subscriptions ?? [];

  return (
    <section className="space-y-4 text-sm" aria-label={t.title}>
      <div>
        <h2 className="text-lg font-semibold">{t.title}</h2>
        {b.doc && <p>{b.doc}</p>}
        <p className="text-xs text-muted-foreground">{t.note}</p>
      </div>

      {roles.length > 0 && (
        <div className="space-y-1">
          <h3 className="font-medium">{t.roles}</h3>
          <Table head={[t.role, t.label, t.scope]} rows={roles.map(([rn, r]) => [<Code key="n">{rn}</Code>, label(r.label, rn, l), r.scope ? t.per(r.scope) : t.global])} />
          <p className="text-xs text-muted-foreground">{t.builtinRoles}</p>
        </div>
      )}

      {Object.entries(workflows).map(([cn, w]) => {
        const states = Object.entries(w.states ?? {});
        const transitions = Object.entries(w.transitions ?? {});
        const rv = w.revert;
        return (
          <div key={cn} className={`space-y-2 rounded-md border p-3 ${cn === selected ? "border-sky-400 ring-1 ring-sky-400" : ""}`}>
            <h3 className="font-medium">{t.workflow(cn)}</h3>
            {w.state && (
              <p className="text-xs text-muted-foreground">
                ⟳ {t.stateAttr(w.state)} {states.length} {t.states.toLowerCase()}, {transitions.length} {t.transitions.toLowerCase()}.
              </p>
            )}
            <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t.states}</h4>
            <Table
              head={[t.state, t.label, t.kind, t.owner, t.editableBy, t.reminder]}
              rows={states.map(([sn, s]) => [
                <span key="s" className="inline-flex items-center gap-1">
                  {s.color && <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />}
                  <Code>{sn}</Code>
                </span>,
                label(s.label, sn, l),
                s.initial ? t.initial : s.final ? t.final : "",
                <Codes key="o" items={s.owner} />,
                <Codes key="e" items={s.editable_by} />,
                s.reminder?.after ? t.after(s.reminder.after, s.reminder.template ?? `${sn}_reminder`) : "",
              ])}
            />
            <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t.transitions}</h4>
            <Table
              head={[t.transition, t.label, t.fromTo, t.by, t.when, t.guard, t.comment, t.emits]}
              rows={transitions.map(([tn, tr]) => [
                <Code key="t">{tn}</Code>,
                label(tr.label, tn, l),
                `${(tr.from ?? []).join(", ")} → ${tr.to ?? ""}`,
                tr.by?.length ? <Codes key="b" items={tr.by} /> : t.system(tr.at ?? ""),
                <Code key="w">{tr.when?.text}</Code>,
                <Code key="g">{tr.guard?.text}</Code>,
                tr.comment === "required" ? t.required : "",
                <Codes key="e" items={tr.emits} />,
              ])}
            />
            {rv && (
              <p className="text-xs text-muted-foreground">
                {t.revert((rv.by ?? []).join(", ") || t.none, (rv.final_by ?? []).join(", ") || t.none, rv.comment === "required" ? t.required : t.optional)}
              </p>
            )}
          </div>
        );
      })}

      {derived.length > 0 && (
        <div className="space-y-1">
          <h3 className="font-medium">{t.derivations}</h3>
          <Table
            head={[t.cls, t.attribute, t.formula]}
            rows={derived.map(([cn, an, f]) => [
              <span key="c" className={`rounded px-1 ${hi(cn)}`}>{cn}</span>,
              <Code key="a">{`/${an}`}</Code>,
              f?.text ? <Code key="f">{f.text}</Code> : <em key="f" className="text-muted-foreground">{t.inCode}</em>,
            ])}
          />
        </div>
      )}

      {involved.length > 0 && (
        <div className="space-y-1">
          <h3 className="font-medium">{t.involved}</h3>
          <p className="text-xs text-muted-foreground">{t.involvedNote}</p>
          <Table
            head={[t.cls, t.feature, t.usedBy]}
            rows={involved.map(([cn, fn, us]) => [
              <span key="c" className={`rounded px-1 ${hi(cn)}`}>{cn}</span>,
              fn === "—" ? "—" : <Code key="f">{fn}</Code>,
              <span key="u" className="text-xs">{usedBy(us)}</span>,
            ])}
          />
        </div>
      )}

      <div className="space-y-1">
        <h3 className="font-medium">{t.events}</h3>
        <p className="text-xs text-muted-foreground">{t.lifecycle}</p>
        <Table head={[t.cls, t.event, t.description]} rows={events.map(([cn, en, doc]) => [<span key="c" className={`rounded px-1 ${hi(cn)}`}>{cn}</span>, <Code key="e">{en}</Code>, doc])} />
      </div>

      {reactions.length > 0 && (
        <div className="space-y-1">
          <h3 className="font-medium">{t.reactions}</h3>
          <Table
            head={[t.name, t.event, t.when, t.recipients, t.template]}
            rows={reactions.map((r) => [
              <Code key="n">{r.name}</Code>,
              <span key="e" className={`rounded px-1 ${hi((r.event ?? "").split(".")[0])}`}><Code>{r.event}</Code></span>,
              <Code key="w">{r.when?.text}</Code>,
              <Codes key="r" items={r.notify} />,
              <Code key="t">{r.template}</Code>,
            ])}
          />
        </div>
      )}

      {subscriptions.length > 0 && (
        <div className="space-y-1">
          <h3 className="font-medium">{t.subscriptions}</h3>
          <Table head={[t.name, t.url, t.events]} rows={subscriptions.map((s) => [<Code key="n">{s.name}</Code>, <Code key="u">{s.url_env ? `$${s.url_env}` : s.url}</Code>, <Codes key="e" items={s.events} />])} />
        </div>
      )}
    </section>
  );
}
