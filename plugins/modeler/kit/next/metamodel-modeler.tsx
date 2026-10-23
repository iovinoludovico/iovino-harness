"use client";

// Domain modeler of this app (installed by the modeler plugin, upgraded by re-running `modeler install`):
// wraps the framework-free <metamodel-editor> (public/modeler/metamodel-editor.js).
// The page passes the metamodel (src/lib/modeler/metamodel.json) and a server action that stores the proposal.
// The proposals saved and not yet applied are listed above the editor: each can be opened or rejected.
// With `behavior` (src/lib/modeler/behavior.json, when the app has a behavior.yaml) the editor marks derived
// attributes and workflow states, shows and edits the workflow of the selected class in its bottom panel, and the
// behaviour is listed below the editor (<BehaviorView>). A save carries the behaviour too: the proposal updates
// behavior.yaml as well when applied (/modeler:apply).
// In production the «Apply from the web» panel above the list holds the settings of the two GitHub workflows: the
// admin enters the Anthropic API key, the production database password and (optional) the merge token, and the server
// action writes them as sealed repository secrets; the app keeps nothing and shows only when each was set.

import Script from "next/script";
import { useCallback, useEffect, useRef, useState, type DetailedHTMLProps, type HTMLAttributes, type Ref } from "react";
import { applyWebStatus, listMetamodelProposals, rejectMetamodelProposal, requestProposalApply, requestProposalRelease, proposalPullRequest, saveApplyWebSecrets, type PendingProposal, type ProposalPullRequest } from "@/lib/modeler/metamodel-actions";
import { envOverrideCommand, type ApplyWebStatus } from "@/lib/modeler/apply-web";
import { BehaviorView } from "./behavior-view";

export type ProposalResult = { ok: boolean; message: string };

type Props = {
  metamodel: unknown;
  behavior?: unknown;         // src/lib/modeler/behavior.json: optional, the page passes it when the app has a behavior.yaml
  canEdit: boolean;
  lang?: string;
  theme?: "light" | "dark";   // omitted: the editor follows the page (html.dark / data-theme / the body's background)
  saveLabel?: string;
  downloadLabel?: string;
  onSave: (json: string, note: string, behaviorJson?: string | null) => Promise<ProposalResult>;
};

type EditorElement = HTMLElement & { metamodel: unknown; behavior: unknown; changesTo: (mm: unknown, bh?: unknown) => string[] };
type SaveDetail = { metamodel: unknown; behavior: unknown | null; note: string };
type SelectDetail = { kind: "class" | "enum" | "user" | "roles" | null; name: string | null };
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
    review: "Rivedi",
    hideReview: "Chiudi",
    release: "Conferma e rilascia",
    confirmRelease: "Rilasciare questa modifica? Il workflow applica le migrazioni al database di produzione, unisce la PR (parte il deploy) e chiude la proposta. Non si annulla.",
    releasing: (d: string) => `rilascio in corso dalle ${d}…`,
    merged: "unita, deploy in corso",
    releaseFailed: "rilascio fallito",
    onGitHub: "apri su GitHub",
    prFacts: (p: ProposalPullRequest) => `${p.state}${p.merged ? ", merged" : ""} · ${p.changedFiles} file, +${p.additions} −${p.deletions} · ${p.mergeable === false ? "non unibile" : p.mergeable ? "unibile" : "stato in calcolo"} (${p.mergeableState})`,
    applyWebTitle: "Applicazione dal web",
    applyWebReady: "configurata",
    applyWebMissing: (n: number) => (n === 1 ? "1 segreto da impostare" : `${n} segreti da impostare`),
    applyWebNoToken: "token dell'app mancante o non valido (MODELER_APPLY_TOKEN)",
    applyWebIntro: "I segreti dei workflow «Applica» e «Conferma e rilascia» si salvano nel repository GitHub dell'app (Actions): l'app li cifra con la chiave pubblica del repository e non li conserva.",
    applyWebRepo: "Repository",
    applyWebNoRepo: "sconosciuto: rilancia `modeler install` con il remote `origin` configurato, o imposta MODELER_APPLY_REPO",
    applyWebSetOn: (d: string) => `impostata il ${d}`,
    applyWebUnset: "mancante",
    applyWebOverride: (env: string) => `un segreto con lo stesso nome nell'environment ${env} ha la precedenza: rimuovilo con`,
    applyWebEnvUnchecked: "environment non verificati (il token non li legge: serve Environments: read)",
    applyWebAnthropic: "Chiave API Anthropic (ANTHROPIC_API_KEY): paga i run con il credito API",
    applyWebDbPassword: "Password del database di produzione (MODELER_PROD_DB)",
    applyWebDbPasswordHelp: (p: string) => `inserita nella URL del pooler ${p}`,
    applyWebUseAppDb: "usa la connessione al database che l'app ha già (DATABASE_URL del container web)",
    applyWebDsn: "Stringa di connessione al database di produzione, con la password (MODELER_PROD_DB)",
    applyWebDsnHelp: "pooler sconosciuto: `supabase link` e poi `modeler install` lo ricavano da soli",
    applyWebMergeToken: "Token che unisce la PR (MODELER_GH_TOKEN, facoltativo)",
    applyWebUseAppToken: "usa il token dell'app per il merge (serve Pull requests: write; il deploy parte solo con un token personale)",
    applyWebSave: "Salva su GitHub",
    applyWebSaving: "salvataggio…",
    applyWebLeaveEmpty: "I campi vuoti non cambiano il segreto esistente.",
    applyWebReviewers: "Su un repository privato con piano Free GitHub non offre «Required reviewers»: la conferma umana è il clic in questa pagina, il tetto di spesa è MODELER_APPLY_BUDGET.",
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
    review: "Review",
    hideReview: "Close",
    release: "Confirm and release",
    confirmRelease: "Release this change? The workflow applies the migrations to the production database, merges the PR (the deploy starts) and closes the proposal. This cannot be undone.",
    releasing: (d: string) => `release running since ${d}…`,
    merged: "merged, deploying",
    releaseFailed: "release failed",
    onGitHub: "open on GitHub",
    prFacts: (p: ProposalPullRequest) => `${p.state}${p.merged ? ", merged" : ""} · ${p.changedFiles} files, +${p.additions} −${p.deletions} · ${p.mergeable === false ? "not mergeable" : p.mergeable ? "mergeable" : "computing"} (${p.mergeableState})`,
    applyWebTitle: "Apply from the web",
    applyWebReady: "configured",
    applyWebMissing: (n: number) => (n === 1 ? "1 secret to set" : `${n} secrets to set`),
    applyWebNoToken: "app token missing or invalid (MODELER_APPLY_TOKEN)",
    applyWebIntro: "The secrets of the «Apply» and «Confirm and release» workflows are stored in the app's GitHub repository (Actions): the app encrypts them with the repository's public key and keeps nothing.",
    applyWebRepo: "Repository",
    applyWebNoRepo: "unknown: run `modeler install` again with the `origin` remote set, or set MODELER_APPLY_REPO",
    applyWebSetOn: (d: string) => `set on ${d}`,
    applyWebUnset: "missing",
    applyWebOverride: (env: string) => `a secret with the same name in the ${env} environment takes precedence: remove it with`,
    applyWebEnvUnchecked: "environments not checked (the token cannot read them: Environments: read)",
    applyWebAnthropic: "Anthropic API key (ANTHROPIC_API_KEY): bills the runs on the API credit",
    applyWebDbPassword: "Production database password (MODELER_PROD_DB)",
    applyWebDbPasswordHelp: (p: string) => `inserted in the pooler URL ${p}`,
    applyWebUseAppDb: "use the database connection the app already has (DATABASE_URL of the web container)",
    applyWebDsn: "Production database connection string, with the password (MODELER_PROD_DB)",
    applyWebDsnHelp: "pooler unknown: `supabase link` and then `modeler install` derive it",
    applyWebMergeToken: "Token that merges the PR (MODELER_GH_TOKEN, optional)",
    applyWebUseAppToken: "use the app token for the merge (needs Pull requests: write; only a personal token triggers the deploy)",
    applyWebSave: "Save on GitHub",
    applyWebSaving: "saving…",
    applyWebLeaveEmpty: "Empty fields leave the existing secret untouched.",
    applyWebReviewers: "On a private repository on the Free plan GitHub has no «Required reviewers»: the human gate is the click on this page, the spending cap is MODELER_APPLY_BUDGET.",
  },
};

const when = (iso: string, lang: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(lang);
};

/** The settings of the two workflows, written as repository secrets of the app's GitHub repository. Hidden in
 * development (file mode) and when the status cannot be read: the editor works without it. */
function ApplyWebPanel({ lang, t }: { lang: string; t: (typeof TEXT)["it"] }) {
  const [status, setStatus] = useState<ApplyWebStatus | null>(null);
  const [form, setForm] = useState({ anthropicKey: "", dbPassword: "", dsn: "", mergeToken: "", useAppToken: false, useAppDb: false });
  const [saving, setSaving] = useState(false);
  const [res, setRes] = useState<ProposalResult | null>(null);

  // The status is read outside the render (a GitHub call); the panel disappears when it cannot be read.
  const readStatus = useCallback(() => applyWebStatus().catch((): ApplyWebStatus | null => null), []);
  const showStatus = (st: ApplyWebStatus | null) => {
    setStatus(st);
    if (st?.mode === "db") {
      const missing = (name: string) => !st.secrets.some((x) => x.name === name && (x.updatedAt || x.envOverride));
      setForm((f) => ({ ...f, useAppToken: missing("MODELER_GH_TOKEN"), useAppDb: st.dbFromEnv && missing("MODELER_PROD_DB") }));
    }
  };

  useEffect(() => {
    let alive = true;
    readStatus().then((st) => alive && showStatus(st));
    return () => {
      alive = false;
    };
  }, [readStatus]);

  if (!status || status.mode === "file") return null;
  const filled = Boolean(form.anthropicKey || form.dbPassword || form.dsn || form.mergeToken || form.useAppToken || form.useAppDb);
  const badge = !status.tokenOk
    ? <span className="text-destructive">{t.applyWebNoToken}</span>
    : status.configured
      ? <span className="text-green-700 dark:text-green-400">{t.applyWebReady}</span>
      : <span className="text-amber-700 dark:text-amber-400">{t.applyWebMissing(status.secrets.filter((x) => !x.updatedAt && !x.envOverride).length)}</span>;

  const save = async () => {
    setSaving(true);
    setRes(null);
    try {
      const r = await saveApplyWebSecrets({ anthropicKey: form.anthropicKey, dbPassword: form.dbPassword, dsn: form.dsn, mergeToken: form.mergeToken,
                                            useAppTokenForMerge: form.useAppToken, useAppDatabaseUrl: form.useAppDb });
      setRes(r);
      if (r.ok) {
        setForm({ anthropicKey: "", dbPassword: "", dsn: "", mergeToken: "", useAppToken: false, useAppDb: false });
        showStatus(await readStatus());
      }
    } catch (err) {
      setRes({ ok: false, message: err instanceof Error ? err.message : String(err) });
    } finally {
      setSaving(false);
    }
  };
  const input = "w-full rounded border bg-background px-2 py-1";

  return (
    <details className="rounded-md border p-3 text-sm">
      <summary className="cursor-pointer font-medium">{t.applyWebTitle} · {badge}</summary>
      <div className="mt-2 space-y-2">
        <p className="text-muted-foreground">{t.applyWebIntro}</p>
        <p>{t.applyWebRepo}: {status.repo ? <code>{status.repo}</code> : <span className="text-destructive">{t.applyWebNoRepo}</span>}</p>
        {status.error && <p className="text-destructive">{status.error}</p>}
        <ul className="space-y-1">
          {status.secrets.map((x) => (
            <li key={x.name}>
              <code>{x.name}</code>{" "}
              {x.updatedAt ? <span className="text-muted-foreground">{t.applyWebSetOn(when(x.updatedAt, lang))}</span> : <span className="text-amber-700 dark:text-amber-400">{t.applyWebUnset}</span>}
              {x.envOverride && status.repo && (
                <p className="text-xs text-amber-700 dark:text-amber-400">{t.applyWebOverride(x.envOverride)} <code>{envOverrideCommand(x.name, x.envOverride, status.repo)}</code></p>
              )}
            </li>
          ))}
        </ul>
        {!status.envChecked && <p className="text-xs text-muted-foreground">{t.applyWebEnvUnchecked}</p>}
        <label className="block">
          <span className="text-muted-foreground">{t.applyWebAnthropic}</span>
          <input type="password" autoComplete="off" className={input} value={form.anthropicKey} onChange={(e) => setForm({ ...form, anthropicKey: e.target.value })} />
        </label>
        {status.dbFromEnv ? (
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={form.useAppDb} onChange={(e) => setForm({ ...form, useAppDb: e.target.checked })} />
            <span className="text-muted-foreground">{t.applyWebUseAppDb}</span>
          </label>
        ) : status.pooler ? (
          <label className="block">
            <span className="text-muted-foreground">{t.applyWebDbPassword}</span>
            <input type="password" autoComplete="off" className={input} value={form.dbPassword} onChange={(e) => setForm({ ...form, dbPassword: e.target.value })} />
            <span className="text-xs text-muted-foreground">{t.applyWebDbPasswordHelp(status.pooler)}</span>
          </label>
        ) : (
          <label className="block">
            <span className="text-muted-foreground">{t.applyWebDsn}</span>
            <input type="password" autoComplete="off" className={input} value={form.dsn} onChange={(e) => setForm({ ...form, dsn: e.target.value })} />
            <span className="text-xs text-muted-foreground">{t.applyWebDsnHelp}</span>
          </label>
        )}
        <label className="block">
          <span className="text-muted-foreground">{t.applyWebMergeToken}</span>
          <input type="password" autoComplete="off" className={input} value={form.mergeToken} onChange={(e) => setForm({ ...form, mergeToken: e.target.value })} />
        </label>
        {!form.mergeToken && (
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={form.useAppToken} onChange={(e) => setForm({ ...form, useAppToken: e.target.checked })} />
            <span className="text-muted-foreground">{t.applyWebUseAppToken}</span>
          </label>
        )}
        <p className="text-xs text-muted-foreground">{t.applyWebLeaveEmpty} {t.applyWebReviewers}</p>
        <button type="button" className="rounded bg-primary px-2 py-1 font-medium text-primary-foreground disabled:opacity-50" disabled={saving || !status.tokenOk || !filled} onClick={save}>
          {saving ? t.applyWebSaving : t.applyWebSave}
        </button>
        {res && <p className={res.ok ? "text-green-700 dark:text-green-400" : "text-destructive"}>{res.message}</p>}
      </div>
    </details>
  );
}

declare module "react" {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "metamodel-editor": DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
        lang?: string;
        "save-label"?: string;
        readonly?: string;
        theme?: string;
      };
    }
  }
}

export function MetamodelModeler({ metamodel, behavior = null, canEdit, lang = "it", theme, saveLabel, downloadLabel = "Download", onSave }: Props) {
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

  // "Review": the pull request as GitHub describes it, under the proposal; "Confirm and release" starts the release workflow.
  const [review, setReview] = useState<{ id: string; pr: ProposalPullRequest | null; error: string | null } | null>(null);
  const toggleReview = async (p: Pending) => {
    if (review?.id === p.id) { setReview(null); return; }
    const res = await proposalPullRequest(p.id);
    if ("ok" in res) setReview({ id: p.id, pr: null, error: res.message });
    else setReview({ id: p.id, pr: res, error: null });
  };
  const releaseWeb = async (p: Pending) => {
    if (!window.confirm(t.confirmRelease)) return;
    const res = await requestProposalRelease(p.id);
    setResult(res);
    setReview(null);
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

  return (
    <div className="space-y-3">
      <Script src="/modeler/metamodel-editor.js" strategy="afterInteractive" />
      {canEdit && <ApplyWebPanel lang={lang} t={t} />}
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
                    <span className="font-medium">{when(p.createdAt, lang)}</span>
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
                    {canEdit && p.prUrl && !p.mergedAt && !p.releaseRequestedAt && (
                      <button type="button" className="underline" onClick={() => toggleReview(p)}>
                        {review?.id === p.id ? t.hideReview : t.review}
                      </button>
                    )}
                    {canEdit && p.prUrl && p.releaseError && !p.mergedAt && (
                      <button type="button" className="underline" onClick={() => toggleReview(p)}>
                        {review?.id === p.id ? t.hideReview : t.retry}
                      </button>
                    )}
                    {canEdit && p.prUrl && p.releaseRequestedAt && !p.mergedAt && !p.releaseError && (
                      <span className="text-muted-foreground">{t.releasing(when(p.releaseRequestedAt, lang))}</span>
                    )}
                    {canEdit && p.mergedAt && !p.deployedAt && !p.releaseError && (
                      <span className="text-muted-foreground">{t.merged}</span>
                    )}
                    {canEdit && !p.prUrl && p.applyRequestedAt && !p.applyError && !p.applyFinishedAt && (
                      <span className="text-muted-foreground">{t.applying(when(p.applyRequestedAt, lang))}</span>
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
                  {p.releaseError && (
                    <p className="mt-1 text-xs text-destructive">{t.releaseFailed}: {p.releaseError}</p>
                  )}
                  {review?.id === p.id && (
                    <div className="mt-2 rounded border bg-muted/40 p-2 text-xs">
                      {review.error && <p className="text-destructive">{review.error}</p>}
                      {review.pr && (
                        <>
                          <p className="font-medium">#{review.pr.number} {review.pr.title}</p>
                          <p className="text-muted-foreground">{t.prFacts(review.pr)} · <a className="underline" href={review.pr.htmlUrl} target="_blank" rel="noreferrer">{t.onGitHub}</a></p>
                          <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap font-mono">{review.pr.body.split("\n").slice(0, 60).join("\n")}</pre>
                          {!p.mergedAt && review.pr.state === "open" && !review.pr.merged && (
                            <button type="button" className="mt-2 rounded bg-primary px-2 py-1 font-medium text-primary-foreground" onClick={() => releaseWeb(p)}>
                              {t.release}
                            </button>
                          )}
                        </>
                      )}
                    </div>
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
          <span>{t.viewing(when(viewing.createdAt, lang))}</span>
          <button type="button" className="underline" onClick={backToRunning}>
            {t.back}
          </button>
        </div>
      )}
      <metamodel-editor
        ref={ref as Ref<HTMLElement>}
        lang={lang}
        theme={theme}
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
