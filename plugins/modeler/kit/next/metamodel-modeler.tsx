"use client";

// Domain modeler of this app (installed by the modeler plugin, upgraded by re-running `modeler install`):
// wraps the framework-free <metamodel-editor> (public/modeler/metamodel-editor.js).
// The page passes the metamodel (src/lib/modeler/metamodel.json) and a server action that stores the proposal.
// The proposals saved and not yet applied are listed above the editor: each can be opened or rejected.
// With `behavior` (src/lib/modeler/behavior.json, when the app has a behavior.yaml) the editor marks derived
// attributes and workflow states, shows and edits the workflow of the selected class in its bottom panel, and the
// behaviour is listed below the editor (<BehaviorView>). A save carries the behaviour too: the proposal updates
// behavior.yaml as well when applied (/modeler:apply).

import Script from "next/script";
import { useCallback, useEffect, useRef, useState, type DetailedHTMLProps, type HTMLAttributes, type Ref } from "react";
import { listMetamodelProposals, rejectMetamodelProposal, requestProposalApply, type PendingProposal } from "@/lib/modeler/metamodel-actions";
import { BehaviorView } from "./behavior-view";

export type ProposalResult = { ok: boolean; message: string };

type Props = {
  metamodel: unknown;
  behavior?: unknown;         // src/lib/modeler/behavior.json: optional, the page passes it when the app has a behavior.yaml
  canEdit: boolean;
  lang?: string;
  saveLabel?: string;
  downloadLabel?: string;
  onSave: (json: string, note: string, behaviorJson?: string | null) => Promise<ProposalResult>;
};

type EditorElement = HTMLElement & { metamodel: unknown; behavior: unknown; changesTo: (mm: unknown, bh?: unknown) => string[] };
type SaveDetail = { metamodel: unknown; behavior: unknown | null; note: string };
type SelectDetail = { kind: "class" | "enum" | null; name: string | null };
type Pending = PendingProposal & { lines: string[] };

const TEXT = {
  it: {
    pending: (n: number) => (n === 1 ? "1 proposta salvata e non ancora applicata" : `${n} proposte salvate e non ancora applicate`),
    apply: "La applica lo sviluppatore con /modeler:apply (npm run model:apply).",
    open: "Apri nell'editor",
    reject: "Scarta",
    confirmReject: "Scartare questa proposta? Non verrà applicata.",
    viewing: (d: string) => `Stai vedendo la proposta del ${d}: salvandola ne crei una nuova.`,
    back: "Torna al modello in esercizio",
    noChanges: "nessuna differenza dal modello in esercizio",
    more: (n: number) => `… e altre ${n}`,
    confirmSave: (n: number) => `C'è già ${n === 1 ? "una proposta" : `${n} proposte`} in attesa: salvarne un'altra?`,
    by: "di",
    applyWeb: "Applica (apre una PR)",
    retry: "Riprova",
    confirmApply: "Avviare l'applicazione automatica? Claude Code applica la proposta su un branch e apre una pull request (qualche minuto, qualche dollaro di credito API). Merge e migrazione in produzione restano manuali.",
    applying: (d: string) => `in corso dalle ${d}…`,
    prOpen: "PR aperta",
    applyFailed: "applicazione fallita",
  },
  en: {
    pending: (n: number) => (n === 1 ? "1 proposal saved and not applied yet" : `${n} proposals saved and not applied yet`),
    apply: "The developer applies it with /modeler:apply (npm run model:apply).",
    open: "Open in the editor",
    reject: "Reject",
    confirmReject: "Reject this proposal? It will not be applied.",
    viewing: (d: string) => `You are viewing the proposal of ${d}: saving it creates a new one.`,
    back: "Back to the running model",
    noChanges: "no difference from the running model",
    more: (n: number) => `… and ${n} more`,
    confirmSave: (n: number) => `${n === 1 ? "A proposal is" : `${n} proposals are`} already waiting: save another one?`,
    by: "by",
    applyWeb: "Apply (opens a PR)",
    retry: "Retry",
    confirmApply: "Start the automatic apply? Claude Code applies the proposal on a branch and opens a pull request (a few minutes, a few dollars of API credit). Merge and the production migration stay manual.",
    applying: (d: string) => `running since ${d}…`,
    prOpen: "PR open",
    applyFailed: "apply failed",
  },
};

declare module "react" {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "metamodel-editor": DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
        lang?: string;
        "save-label"?: string;
        readonly?: string;
      };
    }
  }
}

export function MetamodelModeler({ metamodel, behavior = null, canEdit, lang = "it", saveLabel, downloadLabel = "Download", onSave }: Props) {
  const t = TEXT[lang.startsWith("en") ? "en" : "it"];
  const ref = useRef<EditorElement | null>(null);
  const [ready, setReady] = useState(false);
  const [result, setResult] = useState<ProposalResult | null>(null);
  const [last, setLast] = useState<SaveDetail | null>(null);
  const [pending, setPending] = useState<Pending[]>([]);
  const [selected, setSelected] = useState<string | null>(null);   // the class selected in the editor, for the behaviour view
  // The proposal shown in the editor, tied to the running metamodel it was opened over: a new one closes it.
  const [opened, setOpened] = useState<{ proposal: Pending; over: unknown } | null>(null);
  const viewing = opened && opened.over === metamodel ? opened.proposal : null;

  // Pending proposals with their differences from the running model (computed by the editor, outside render).
  const loadPending = useCallback(async (): Promise<Pending[]> => {
    try {
      const list = await listMetamodelProposals();
      return list.map((p) => {
        let lines: string[] = [];
        try {
          lines = ref.current?.changesTo?.(p.metamodel, p.behavior ?? undefined) ?? [];
        } catch {
          // no differences shown
        }
        return { ...p, lines };
      });
    } catch {
      return [];   // the list is a help: the editor works without it
    }
  }, []);

  useEffect(() => {
    let alive = true;
    customElements.whenDefined("metamodel-editor").then(() => alive && setReady(true));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (ready && ref.current) ref.current.metamodel = metamodel;
  }, [ready, metamodel]);

  useEffect(() => {
    if (ready && ref.current) ref.current.behavior = behavior ?? null;
  }, [ready, behavior]);

  useEffect(() => {
    const el = ref.current;
    if (!ready || !el) return;
    const handler = (ev: Event) => {
      const d = (ev as CustomEvent<SelectDetail>).detail;
      setSelected(d.kind === "class" ? d.name : null);
    };
    el.addEventListener("select", handler);
    return () => el.removeEventListener("select", handler);
  }, [ready]);

  useEffect(() => {
    if (!ready) return;
    let alive = true;
    loadPending().then((list) => alive && setPending(list));
    return () => {
      alive = false;
    };
  }, [ready, metamodel, loadPending]);

  const waiting = pending.length;
  useEffect(() => {
    const el = ref.current;
    if (!ready || !el) return;
    const handler = async (ev: Event) => {
      const detail = (ev as CustomEvent<SaveDetail>).detail;
      if (waiting > 0 && !window.confirm(t.confirmSave(waiting))) return;
      setLast(detail);
      setResult(null);
      try {
        setResult(await onSave(JSON.stringify(detail.metamodel), detail.note, detail.behavior ? JSON.stringify(detail.behavior) : null));
      } catch (err) {
        setResult({ ok: false, message: err instanceof Error ? err.message : String(err) });
      }
      setPending(await loadPending());
    };
    el.addEventListener("save", handler);
    return () => el.removeEventListener("save", handler);
  }, [ready, onSave, loadPending, waiting, t]);

  const openProposal = (p: Pending) => {
    if (!ref.current) return;
    ref.current.metamodel = p.metamodel;
    if (p.behavior) ref.current.behavior = p.behavior;      // the proposal's behaviour too, when it carries one
    setOpened({ proposal: p, over: metamodel });
  };

  // changesTo compares with the metamodel loaded in the editor: back on the running one, the differences are recomputed.
  const backToRunning = async () => {
    if (ref.current) { ref.current.metamodel = metamodel; ref.current.behavior = behavior ?? null; }
    setOpened(null);
    setPending(await loadPending());
  };

  const reject = async (p: Pending) => {
    if (!window.confirm(t.confirmReject)) return;
    const res = await rejectMetamodelProposal(p.id);
    setResult(res);
    if (viewing?.id === p.id) await backToRunning();
    else setPending(await loadPending());
  };

  const applyWeb = async (p: Pending) => {
    if (!window.confirm(t.confirmApply)) return;
    const res = await requestProposalApply(p.id);
    setResult(res);
    setPending(await loadPending());
  };

  const download = () => {
    if (!last) return;
    const blob = new Blob([JSON.stringify({ note: last.note, created_at: new Date().toISOString(), metamodel: last.metamodel, ...(last.behavior ? { behavior: last.behavior } : {}) }, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `metamodel-proposal-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const when = (iso: string) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(lang);
  };

  return (
    <div className="space-y-3">
      <Script src="/modeler/metamodel-editor.js" strategy="afterInteractive" />
      {pending.length > 0 && !viewing && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-700 dark:bg-amber-950">
          <p className="font-medium">{t.pending(pending.length)}</p>
          <p className="text-muted-foreground">{t.apply}</p>
          <ul className="mt-2 space-y-2">
            {pending.map((p) => {
              const lines = p.lines;
              return (
                <li key={p.id} className="rounded border bg-background p-2">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="font-medium">{when(p.createdAt)}</span>
                    {p.author && <span className="text-muted-foreground">{t.by} {p.author}</span>}
                    {p.status === "pulled" && <span className="text-muted-foreground">(pulled)</span>}
                    {p.note && <span>· {p.note}</span>}
                    <span className="grow" />
                    <button type="button" className="underline" onClick={() => openProposal(p)}>
                      {t.open}
                    </button>
                    {canEdit && (
                      <button type="button" className="text-destructive underline" onClick={() => reject(p)}>
                        {t.reject}
                      </button>
                    )}
                    {canEdit && p.prUrl && (
                      <a className="font-medium underline" href={p.prUrl} target="_blank" rel="noreferrer">
                        {t.prOpen}
                      </a>
                    )}
                    {canEdit && !p.prUrl && p.applyRequestedAt && !p.applyError && !p.applyFinishedAt && (
                      <span className="text-muted-foreground">{t.applying(when(p.applyRequestedAt))}</span>
                    )}
                    {canEdit && !p.prUrl && (!p.applyRequestedAt || p.applyError || p.applyFinishedAt) && (
                      <button type="button" className="underline" onClick={() => applyWeb(p)}>
                        {p.applyError ? t.retry : t.applyWeb}
                      </button>
                    )}
                  </div>
                  {p.applyError && !p.prUrl && (
                    <p className="mt-1 text-xs text-destructive">{t.applyFailed}: {p.applyError}</p>
                  )}
                  <pre className="mt-1 whitespace-pre-wrap font-mono text-xs text-muted-foreground">
                    {lines.length ? lines.slice(0, 8).join("\n") + (lines.length > 8 ? `\n${t.more(lines.length - 8)}` : "") : t.noChanges}
                  </pre>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {viewing && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-sky-300 bg-sky-50 p-2 text-sm dark:border-sky-700 dark:bg-sky-950">
          <span>{t.viewing(when(viewing.createdAt))}</span>
          <button type="button" className="underline" onClick={backToRunning}>
            {t.back}
          </button>
        </div>
      )}
      <metamodel-editor
        ref={ref as Ref<HTMLElement>}
        lang={lang}
        save-label={saveLabel}
        readonly={canEdit ? undefined : ""}
        style={{ display: "block", height: "calc(100dvh - 12rem)", minHeight: 560 }}
      />
      {result && (
        <div className={`flex flex-wrap items-center gap-3 text-sm ${result.ok ? "text-green-700 dark:text-green-400" : "text-destructive"}`}>
          <span>{result.message}</span>
          {last && (
            <button type="button" className="underline" onClick={download}>
              {downloadLabel}
            </button>
          )}
        </div>
      )}
      {behavior ? <BehaviorView behavior={behavior} metamodel={metamodel} lang={lang} selected={selected} /> : null}
    </div>
  );
}
