---
name: install
description: Rende il modellatore web del dominio parte integrante di un'app Next.js + Supabase (nuova o esistente) - ricava domain.ecore.yaml dal database se manca, installa nel repository editor, pagina /admin/model, salvataggio delle proposte, tabella model_change_requests e la CLI con gli script npm model:*, e imposta il controllo di allineamento tra metamodello e database. Va usata quando l'utente vuole il modellatore o il metamodello in un'app ("aggiungi il modellatore", "ricava il metamodello dal database", "non vedo il modellatore"), quando la sessione segnala un modellatore da aggiornare, o invoca /modeler:install.
argument-hint: "[cartella dell'app] [DSN del database locale]"
---

# Installare (o aggiornare) il modellatore in un'app

Argomenti: `$ARGUMENTS`. CLI del plugin: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/modeler.py" …`.
Lavora su un branch (`feat/modeler`), non toccare mai i file `.env*`. Leggi prima `CLAUDE.md` dell'app e le
pagine della sua area admin.

Dopo l'installazione il modellatore appartiene all'app: editor, wrapper React, azione server e CLI
(`tools/modeler/`, con gli script `npm run model:*`) sono nel repository e funzionano senza il plugin.
Rilanciare questa skill aggiorna i file del modellatore (editor, wrapper, vista del comportamento, azione, CLI) e
non tocca quelli adattati all'app (`src/lib/modeler/access.ts`, la pagina admin): se `install` segnala
"behavior.yaml found", aggiorna la pagina come dice il punto 4.

## 0. Versione del plugin (prima di tutto)
La cache del plugin può essere indietro rispetto all'harness: confronta la versione caricata
(`${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`) con quella di `origin/main` dell'harness:
`gh api repos/iovinoludovico/iovino-harness/contents/plugins/modeler/.claude-plugin/plugin.json --jq .content | base64 -d`
(o, se il clone dell'harness è sul computer, `git -C <clone> fetch -q && git -C <clone> show origin/main:plugins/modeler/.claude-plugin/plugin.json`).
Se la cache è indietro, fermati e fai eseguire all'utente, nel suo terminale:
`claude plugin marketplace update iovino-harness && claude plugin update modeler@iovino-harness`, poi `/reload-plugins`
e una nuova invocazione di questa skill. Se è aggiornata, prosegui: prima installazione (punti 1-5) o aggiornamento
di un'app già installata (punto 6).

## 1. Database da leggere (solo se manca `domain.ecore.yaml`)
Di solito il Supabase locale dell'app: `supabase start`, poi il DSN con la porta di `[db]` in
`supabase/config.toml` (la CLI la ricava da sola se ometti `--db`). Se non è avviato chiedi all'utente di
avviarlo; mai un database di produzione senza permesso esplicito.

## 2. Metamodello dal database (solo se manca)
`reverse --package <nome> -o domain.ecore.yaml [--db <DSN>] [--exclude <tabelle infrastrutturali>]`, poi
rivedilo **con l'utente**:
- nomi di classi e feature (rinomina liberamente: `column:` mantiene il legame con la colonna);
- containment dedotti da `on delete cascade`, molti-a-molti dalle join table, enum dai `check (… in …)`;
- `language: it` se i nomi sono italiani; `doc`/`label` per le classi principali;
- tabelle tecniche dell'app da escludere (`--exclude`, e `MODELER_EXCLUDE` per `model:drift`); una singola
  colonna tecnica (es. FK verso una tabella esclusa) si esclude con `tabella.colonna`.
`validate` e `drift` devono dare "OK" e "aligned".

## 3. Installazione
`install <app>` copia o aggiorna:
- `public/modeler/metamodel-editor.js` (editor senza dipendenze),
- `src/components/modeler/metamodel-modeler.tsx` (wrapper React),
- `src/components/modeler/behavior-view.tsx` (il comportamento in sola lettura sotto l'editor: ruoli, workflow con
  stati e transizioni, attributi calcolati con la formula, eventi, reazioni; compare solo se la pagina passa
  `behavior.json`),
- `src/components/modeler/workflow-view.tsx` (`<WorkflowView>`: il diagramma degli stati del workflow di un'entità con
  lo stato corrente del record evidenziato, per le pagine di dettaglio dell'app; disegnato dall'elemento
  `<workflow-view>` di `metamodel-editor.js`),
- `src/components/modeler/notification-templates.tsx` e `src/lib/modeler/notification-actions.ts` (la pagina admin
  a matrice dei testi delle notifiche, template × lingua: valori propri, dal modello, mancanti; gli override vanno in
  `public.notification_templates`),
- `supabase/migrations/<ts>_notification_templates.sql` (solo la prima volta e solo se `behavior.yaml` ha `templates:`:
  la tabella degli override che il motore e la pagina usano),
- `src/lib/modeler/metamodel-actions.ts` (salva, elenca e scarta le proposte: file in sviluppo, tabella in produzione;
  «Applica» su una proposta di produzione avvia il workflow `modeler-apply`),
- `supabase/migrations/<ts>_model_change_requests_apply.sql` (solo la prima volta: le colonne `pr_url`, `apply_error`,
  `apply_requested_at`, `apply_finished_at` dell'esito di un'applicazione dal web),
- `.github/workflows/modeler-apply.yml`, `.github/modeler-apply-rules.md` e `.github/workflows/modeler-release.yml`
  (solo se mancano: il workflow che applica una proposta di produzione con Claude Code e apre la PR, le regole del
  run, e il workflow che rilascia la PR confermata dal modellatore; sezione 7),
- `src/lib/modeler/access.ts` (solo se manca: chi è admin e quale client Supabase usare),
- `src/lib/modeler/metamodel.json` (il metamodello letto dalla pagina),
- `docs/DOMAIN.md` (la descrizione del dominio generata dal metamodello; si rigenera con `npm run model:sync`).
  Se in `docs/` c'è già un `domain.md` con altre maiuscole (scritto da uno strumento precedente), `install` non scrive
  `DOMAIN.md` e lo dice: rinominalo (es. `docs/behavior.md`) aggiornando i riferimenti in `CLAUDE.md` e README, o
  cancellalo se `DOMAIN.md` lo sostituisce, poi `npm run model:sync`,
- `tools/modeler/` (la CLI, con `VERSION`) e gli script `model:*` in `package.json`,
- `supabase/migrations/<ts>_model_change_requests.sql` (solo la prima volta; ha la colonna `behavior jsonb` per le
  proposte che portano il comportamento). In un'app installata prima di questa colonna aggiungi una migrazione con
  `alter table public.model_change_requests add column if not exists behavior jsonb;` (il modellatore in
  produzione lo segnala salvando "senza il comportamento" finché manca).

## 4. Adattamento all'app (solo alla prima installazione)
- `access.ts`: usa il controllo admin e il client Supabase server dell'app (l'import di default è
  `@/lib/supabase/server`, il controllo di default la RPC `is_admin`).
- Nella migrazione `model_change_requests`, sostituisci `public.is_admin()` con il predicato admin dell'app se
  si chiama diversamente (la migrazione non è ancora applicata: si può modificare).
- Pagina admin: parti da `${CLAUDE_PLUGIN_ROOT}/kit/next/page.tsx` e mettila nell'area admin dell'app (es.
  `src/app/(admin)/admin/model/page.tsx`), con layout, titolo e traduzioni dell'app; aggiungi il link nella
  navigazione admin. `lang` segue la lingua dell'utente.
- Se l'app ha `behavior.yaml`: nella pagina togli il commento a `import behavior from "@/lib/modeler/behavior.json"`
  e passa `behavior={behavior}` a `<MetamodelModeler>`: nel diagramma la classe con workflow ha la testata «workflow»
  e, quando è selezionata, il diagramma degli stati in un pannello sotto la tela, gli attributi calcolati
  hanno il prefisso `/` (formula nel tooltip e nel pannello), l'attributo di stato il segno `⟳`, le feature usate dal
  comportamento ` ·ƒ` (tooltip «usato da»), le classi coinvolte senza workflow `ƒ` in testata, con una legenda dei tre
  livelli; sotto l'editor compare il comportamento e la classe selezionata evidenzia il suo workflow. `install` lo segnala ("behavior.yaml found: …") finché la
  pagina non lo passa, anche nelle reinstallazioni. Nel pannello del workflow e nella barra laterale si modificano
  stati, transizioni, ritorno, formule dei derivati, eventi, ruoli e reazioni: «Salva» produce una proposta con
  metamodello e comportamento, che `/modeler:apply` porta in `domain.ecore.yaml` e `behavior.yaml`.
- Se l'app ha `behavior.yaml`, nella pagina di dettaglio di un record di una classe con workflow aggiungi il diagramma
  degli stati con lo stato corrente: `import behavior from "@/lib/modeler/behavior.json"` e
  `<WorkflowView behavior={behavior} entity="<Classe>" state={record.<attributo di stato>} lang="…" />`
  (`@/components/modeler/workflow-view`), sopra le azioni di transizione; non compare se la classe non ha workflow.
  Lo stato corrente è pieno del suo colore con testo bianco e un anello, gli altri stati sono attenuati, le transizioni
  che ne partono sono a piena forza, le altre attenuate (un valore non tra gli stati lascia il diagramma neutro e mette
  `data-state-missing` sull'elemento);
  il diagramma si adatta alla larghezza del contenitore e sotto la larghezza minima scorre in orizzontale: con
  workflow lunghi (10+ stati) mettilo a tutta larghezza.
  Se la pagina ha già una vista del workflow scritta a mano (un percorso degli stati, `StatePath` o simile), non
  metterle una sotto l'altra: due schede con il componente a schede dell'app (es. `Tabs` di shadcn), quella esistente
  predefinita («Percorso») e `<WorkflowView>` nella seconda («Diagramma»); la scheda scelta si ricorda per utente in
  `localStorage` come comodità, mai come stato condiviso; sostituire la vista esistente è una decisione dell'utente.
  ```tsx
  "use client";
  // Workflow of the record: the app's own path first, the full diagram in the second tab
  const KEY = "workflow-tab";
  export function WorkflowTabs({ path, diagram }: { path: ReactNode; diagram: ReactNode }) {
    const [tab, setTab] = useState("path");
    useEffect(() => { try { const t = localStorage.getItem(KEY); if (t === "diagram") setTab(t); } catch {} }, []);
    const pick = (t: string) => { setTab(t); try { localStorage.setItem(KEY, t); } catch {} };
    return (
      <Tabs value={tab} onValueChange={pick}>
        <TabsList><TabsTrigger value="path">Percorso</TabsTrigger><TabsTrigger value="diagram">Diagramma</TabsTrigger></TabsList>
        <TabsContent value="path">{path}</TabsContent>
        <TabsContent value="diagram">{diagram}</TabsContent>
      </Tabs>
    );
  }
  // nella pagina: <WorkflowTabs path={<StatePath … />} diagram={<WorkflowView behavior={behavior} entity="Order" state={row.status} lang="it" />} />
  ```
- Se `behavior.yaml` ha `templates:` (`install` lo segnala con «templates found in behavior.yaml»): parti da
  `${CLAUDE_PLUGIN_ROOT}/kit/next/templates-page.tsx` per la pagina admin dei testi delle notifiche (es.
  `src/app/(admin)/admin/notifications/page.tsx`, link nella navigazione admin) e applica la migrazione
  `notification_templates` (in locale, poi `/core:db-push`). Il motore generato (`npm run model:engine -- --write`)
  rende `subject` e `body` in `recipients`; con un motore a mano il dispatcher legge i testi da `behavior.json`
  (`templates`) e gli override dalla tabella, con lo stesso `render_template` del motore (skill `behavior`, punto 4).
  Il dispatcher ora importa `behavior.json` e la cartella dei template: se ha uno stage proprio nel `Dockerfile` con
  una lista di `COPY`, aggiungili (o copia `src/` intero), altrimenti muore all'avvio in produzione con build e
  deploy verdi (skill `core:deploy`, sezione «Immagini»).
- `tsconfig.json` deve avere `resolveJsonModule` (la pagina importa `metamodel.json`, e `behavior.json` se c'è).
- `.gitignore`: `install` aggiunge `__pycache__/` (il bytecode della CLI in `tools/modeler/`), `.modeler/backups/` e
  `.modeler/drafts/` (le bozze che `model:propose` trasforma in proposte); non ignorare `.modeler/proposals/` (le
  proposte si rivedono nel repository).
- In `CLAUDE.md` dell'app: "Il metamodello del dominio è `domain.ecore.yaml`: ogni modifica di schema parte da
  lì (/modeler:metamodel) insieme alla migrazione; `npm run model:sync` aggiorna il modellatore,
  `npm run model:drift` deve dare 'aligned'. Il comportamento (workflow, guardie, notifiche e i loro testi) è
  `behavior.yaml`: si modifica con /modeler:behavior nella stessa modifica del codice che lo esegue. Le proposte del
  modellatore si applicano con /modeler:apply.
  `docs/DOMAIN.md` è generato dal metamodello: lì si annotano a mano dettagli e regole da portare nel metamodello
  (/modeler:metamodel), mai la struttura." Se l'app formatta `docs/` con Prettier, aggiungi `docs/DOMAIN.md` a
  `.prettierignore`.
- Proponi uno step di CI che applica le migrazioni a un database temporaneo ed esegue
  `npm run model:validate` e `MODELER_DB=<dsn> npm run model:drift`.
- Logica scritta a mano che il metamodello non esprime (workflow, regole, pagine speciali): elencala in
  `docs/customizations.md` (id, perché il modello non basta, elementi coinvolti, file, verifica) e marca il
  codice con `CUSTOM(<id>)`; conferma l'elenco con l'utente.

## 5. Verifica
`npm run model:validate`, `npm run model:drift` (con il database locale avviato e la migrazione applicata),
typecheck, lint, test e build dell'app; poi apri `/admin/model` in sviluppo, fai una modifica e salva:
deve comparire un file in `.modeler/proposals/`; se c'è un workflow, apri il dettaglio di un record a due larghezze
(desktop e telefono) e controlla che il diagramma mostri lo stato corrente e scorra invece di stringersi. Prima del deploy, la migrazione `model_change_requests` va
applicata al cloud con `/core:db-push`.

## 6. Aggiornamento di un'app già installata (automatico)
Quando `tools/modeler/VERSION` è più vecchio del plugin (l'inizio sessione lo segnala), fai da solo, senza chiedere
passo per passo:
1. branch `chore/modeler-<versione>` da `main` aggiornato;
2. `install <app>` (punto 3), poi `npm run model:validate` e `npm run model:sync`;
3. typecheck, lint e test dell'app (gli script di `package.json`); se `install` stampa un suggerimento
   («behavior.yaml found», «workflows in code», `<WorkflowView>`), applicalo o riportalo all'utente;
4. commit `chore(modeler): upgrade the modeler to <versione>` con, nel corpo, i titoli delle PR dell'harness tra le
   due versioni (`gh pr list --repo iovinoludovico/iovino-harness --state merged --limit 30 --json number,title,mergedAt`,
   quelle con `modeler` nel titolo e più recenti della versione installata) e ciò che l'app deve ancora fare a mano;
5. proponi `/core:ship` (porta anche le migrazioni nuove in cloud prima del push, se ce ne sono).
`install` aggiunge a `.gitignore` anche `.modeler/backups/` (i backup di `apply` e `sync --force` sporcavano
l'albero e bloccavano `ship`) e `.modeler/drafts/`. Senza `psql`, `pull`, `done`, `drift` e `reverse` usano `supabase db query`
(`--linked` via Management API con il token di `supabase login`, altrimenti `--db-url`).

## 7. Applicare dal web (facoltativo)
Una proposta salvata in produzione si applica anche dal bottone «Applica (apre una PR)» di `/admin/model`: la server
action `requestProposalApply` manda un `repository_dispatch` al repository GitHub dell'app e il workflow
`.github/workflows/modeler-apply.yml` fa il checkout, avvia Supabase locale, scarica quella sola proposta
(`npm run model:pull -- --id <uuid>`), lancia Claude Code headless con il plugin `modeler`
(`claude -p "/modeler:apply <file>" --output-format json --permission-mode dontAsk --max-budget-usd …`, regole in
`.github/modeler-apply-rules.md`), fa push del branch `model/<id8>`, apre la PR e scrive il link sulla riga
(`npm run model:track -- <uuid> --pr <url> --write`); se il run fallisce scrive l'errore e la pagina offre «Riprova».
Sulla riga con la PR, «Rivedi» mostra la PR come la descrive GitHub (titolo, file cambiati, unibilità e il corpo
scritto da Claude: cosa cambia, `TODO(modeler)` lasciati, costo) e «Conferma e rilascia» avvia il workflow
`.github/workflows/modeler-release.yml`, che fa gli stessi passi di `/core:db-push` e `/core:ship` §5, con le stesse
fermate: PR aperta, su `main`, aggiornata e unibile; database locale ricostruito dalle migrazioni
(`supabase db reset`, `supabase test db` se ci sono test, `model:drift` aligned); **DDL distruttivo non commentato →
si ferma** (si rilascia solo dalla scheda Actions con l'input `allow_destructive`); migrazioni solo remote o fuori
ordine → si ferma; `supabase db push --db-url` (prima il database, poi il codice); `gh pr merge --squash` con
`MODELER_GH_TOKEN` (il push su `main` avvia il deploy); attesa del run di deploy dello SHA del merge (15 min; un
deploy fallito → errore sulla riga, migrazione già applicata e PR unita: rollback secondo `core:deploy`);
`npm run model:done -- --write` chiude la proposta. La riga mostra «rilascio in corso», «unita, deploy in corso»,
«rilascio fallito» con «Riprova». I drop e i cambi di tipo restano commentati nella migrazione: li elenca la PR, e il
rilascio dal modellatore non li applica mai.
- Da impostare una volta, nel repository GitHub dell'app, nell'environment `modeler-apply` (Settings →
  Environments; il job gira lì e GitHub lo crea al primo run se manca; con «Required reviewers» ogni run aspetta
  l'approvazione di una persona prima di spendere) o nei secrets del repository (Settings → Secrets and variables →
  Actions): segreti `ANTHROPIC_API_KEY` (i run si pagano con il credito API, non con l'abbonamento) e `MODELER_PROD_DB` (DSN del
  pooler del progetto Supabase, con la password: serve solo a `pull`/`track`, nessuna migrazione passa da lì);
  variabili facoltative `MODELER_APPLY_MODEL` (default `claude-opus-5-5`), `MODELER_APPLY_BUDGET` (dollari per run,
  default 10), `MODELER_HARNESS` (marketplace, default `iovinoludovico/iovino-harness`; se il repository dell'harness
  è privato il passo «Claude Code and the modeler plugin» va adattato con un token).
- Per il rilascio: environment `modeler-release` con **«Required reviewers»** (la conferma umana fuori dall'app: il
  run aspetta l'approvazione su GitHub prima di toccare il database di produzione) e il secret `MODELER_GH_TOKEN`,
  token fine-grained di chi può unire su `main` con Contents + Pull requests: write su quel solo repository (serve
  perché un merge fatto con `GITHUB_TOKEN` non avvia il workflow di deploy); con la branch protection su `main`,
  il proprietario del token deve essere tra chi può unire. `MODELER_PROD_DB` serve anche qui (`db push --db-url`).
- Nel pannello dell'app (Docker Manager, come `DATABASE_URL`; skill `core:deploy`): `MODELER_APPLY_REPO`
  (`owner/repo`) e `MODELER_APPLY_TOKEN`, un token fine-grained con Contents: write (i `repository_dispatch`) e
  Pull requests: read («Rivedi») su quel repository. Senza, il bottone spiega cosa manca.
- Costo per run (stima; il valore reale è `total_cost_usd` nel riepilogo del job): modifica piccola (attributo,
  relazione, letterale) 2–5 $ con Opus 5.5, 1–2,5 $ con Sonnet 5.5; media (classe nuova con tabella, policy, form,
  pagina) 8–20 $ / 4–10 $. `MODELER_APPLY_BUDGET` ferma il run oltre la soglia (la riga mostra l'errore, nessuna PR).
- Prova: Actions → `modeler-apply` → «Run workflow» con l'id di una proposta di prova; poi, per il rilascio, una
  proposta con una migrazione innocua e `modeler-release` → «Run workflow» (id, numero della PR); la prima volta con
  il reviewer attivo. I workflow sono dell'app: `install` non li sovrascrive (adattali liberamente, es. i servizi
  di `supabase start`).
