"use client";

// «View as» (installed by the modeler plugin when behavior.yaml declares `view_as`, replaced by `modeler install`):
// the role switcher for users holding several roles, the banner while the session is restricted or acts as another
// user, and the register of who acted as whom. The pages pass the data (the user's roles with their labels from
// behavior.json, the current choice from src/lib/modeler/view-as.ts, the rows of `view_as_log(limit)`).

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { setViewAsRole, stopViewAsUser } from "@/lib/modeler/view-as-actions";

export type RoleOption = { value: string; label: string };
export type ViewAsEntry = { occurred_at: string; started: boolean; actor_email: string | null; user_email: string | null };

const TEXT = {
  it: { label: "Vedi come", all: "tutti i miei ruoli", restricted: "Stai vedendo l'app come {role}.", reset: "Torna a tutti i ruoli",
        asUser: "Stai usando l'app come {user} (sei {by}): ogni azione è registrata a tuo nome.", backToMe: "Torna a te",
        log: "Accessi «vedi come»", started: "inizio", ended: "fine", empty: "Nessun accesso registrato." },
  en: { label: "View as", all: "all my roles", restricted: "You are seeing the application as {role}.", reset: "Back to all roles",
        asUser: "You are using the application as {user} (you are {by}): every action is recorded in your name.", backToMe: "Back to me",
        log: "«View as» sessions", started: "start", ended: "end", empty: "No session recorded." },
};
const t = (lang: string | undefined, key: keyof typeof TEXT.en, vars: Record<string, string> = {}) =>
  (TEXT[lang === "it" ? "it" : "en"][key] as string).replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");

/** Shown only to users holding more than one role: restricts the session to one of them. */
export function ViewAsSwitcher({ roles, current, lang }: { roles: RoleOption[]; current: string | null; lang?: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  if (roles.length < 2) return null;
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
      {t(lang, "label")}
      <select
        value={current ?? ""}
        disabled={pending}
        onChange={(e) => {
          const role = e.target.value || null;
          start(async () => {
            await setViewAsRole(role);
            router.refresh();
          });
        }}
        className="h-7 rounded-md border bg-background px-1.5 text-xs text-foreground"
      >
        <option value="">{t(lang, "all")}</option>
        {roles.map((r) => (
          <option key={r.value} value={r.value}>
            {r.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** While the session is restricted to one role. */
export function ViewAsRoleBanner({ role, lang }: { role: string; lang?: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  return (
    <div role="status" className="border-b border-amber-300 bg-amber-50 px-4 py-2 text-center text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
      {t(lang, "restricted", { role })}{" "}
      <button type="button" disabled={pending} className="font-medium underline underline-offset-4"
              onClick={() => start(async () => { await setViewAsRole(null); router.refresh(); })}>
        {t(lang, "reset")}
      </button>
    </div>
  );
}

/** Always in sight while the session acts as another user. */
export function ImpersonationBanner({ user, by, back, lang }: { user: string; by: string; back?: string; lang?: string }) {
  const [pending, start] = useTransition();
  return (
    <div role="status" className="sticky top-0 z-50 border-b border-amber-400 bg-amber-100 px-4 py-2 text-center text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-50">
      <span>{t(lang, "asUser", { user, by })}</span>{" "}
      <button type="button" disabled={pending} className="rounded-md border border-amber-500 bg-background/70 px-2 py-0.5 font-medium hover:bg-background"
              onClick={() => start(async () => { await stopViewAsUser(back); })}>
        {t(lang, "backToMe")}
      </button>
    </div>
  );
}

/** The register: who acted as whom, from `select * from view_as_log(limit)`. */
export function ViewAsLog({ entries, lang }: { entries: ViewAsEntry[]; lang?: string }) {
  return (
    <section className="rounded-lg border p-4">
      <h3 className="mb-2 font-medium">{t(lang, "log")}</h3>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t(lang, "empty")}</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {entries.map((e, i) => (
            <li key={i} className="flex flex-wrap gap-x-2">
              <span className="tabular-nums text-muted-foreground">{new Date(e.occurred_at).toLocaleString(lang === "it" ? "it-IT" : "en-GB")}</span>
              <span>{e.actor_email ?? "?"} → {e.user_email ?? "?"}</span>
              <span className="text-muted-foreground">({t(lang, e.started ? "started" : "ended")})</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
