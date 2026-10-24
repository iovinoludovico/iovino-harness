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
  colonna tecnica (es. FK verso una tabella esclusa) si esclude con `tabella.colonna`. `user_roles` e l'enum `app_role`
  non si escludono: `reverse` li scrive come `roles:` del metamodello (aggiungi `label`, `doc` e `scope: <Classe>` per i
  ruoli tenuti per istanza) e `drift` li confronta; se l'app ha un `behavior.yaml` con `roles:`, i due devono coincidere.
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
- `src/lib/modeler/view-as.ts`, `src/lib/modeler/view-as-actions.ts` e `src/components/modeler/view-as.tsx` (solo se
  `behavior.yaml` ha `view_as:`: i cookie e le intestazioni `x-view-as`/`x-view-as-user`, le azioni server che
  registrano inizio e fine con `view_as_audit`, il selettore del ruolo, i banner e il registro `<ViewAsLog>`; il
  database fa il resto con il motore generato),
- `src/lib/modeler/metamodel-actions.ts` (salva, elenca e scarta le proposte: file in sviluppo, tabella in produzione;
  «Applica» su una proposta di produzione avvia il workflow `modeler-apply`; `applyWebStatus`/`saveApplyWebSecrets`
  per il pannello «Applicazione dal web», sezione 7),
- `src/lib/modeler/apply-web.ts` (gli helper puri del pannello) e `src/lib/modeler/modeler-apply.json` (`repo` dal
  remote git `origin`, `pooler` dall'URL del pooler del progetto Supabase collegato, senza password; riscritto a ogni
  install tenendo i valori che non riesce a ricavare; si committa: contiene solo host e ref del progetto),
- `libsodium-wrappers` tra le `dependencies` di `package.json` (solo se manca; cifra i segreti per GitHub): poi
  `npm install` e commit di `package-lock.json`, l'immagine Docker fa `npm ci`,
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
  degli stati con lo stato corrente: `import behavior from "@/lib/modeler/behavior.json"`, `import metamodel from
  "@/lib/modeler/metamodel.json"` e
  `<WorkflowView behavior={behavior} metamodel={metamodel} entity="<Classe>" state={record.<attributo di stato>} lang="…" />`
  (`@/components/modeler/workflow-view`), sopra le azioni di transizione; non compare se la classe non ha workflow.
  `metamodel` è facoltativo: con esso il tooltip della busta scrive un destinatario `self.fund.manager` con le
  etichette delle feature («Fondo › Responsabile»), come il pannello del modellatore; senza, il percorso resta com'è.
  Lo stato corrente è pieno del suo colore con testo bianco e un anello, gli altri stati sono attenuati, le transizioni
  che ne partono sono a piena forza, le altre attenuate (un valore non tra gli stati lascia il diagramma neutro e mette
  `data-state-missing` sull'elemento);
  il diagramma si adatta alla larghezza del contenitore e sotto la larghezza minima scorre in orizzontale: con
  workflow lunghi (10+ stati) mettilo a tutta larghezza.
  I colori di `<MetamodelModeler>` e `<WorkflowView>` seguono il tema della pagina (classe `dark` o `data-theme` su
  `html`, altrimenti lo sfondo del `body`), non lo schema del sistema: non serve CSS nell'app, e la prop
  `theme="light" | "dark"` lo forza quando l'app lo decide altrove.
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
  // nella pagina: <WorkflowTabs path={<StatePath … />} diagram={<WorkflowView behavior={behavior} metamodel={metamodel} entity="Order" state={row.status} lang="it" />} />
  ```
- Se `install` segnala «roles found in behavior.yaml only»: l'app è nella forma precedente la 0.35, con i ruoli solo
  nel comportamento, e niente lo mostra (nessun riquadro `Role`/`User` nel diagramma, nessuna sezione «Ruoli» in
  `DOMAIN.md`, `drift` cieco se `user_roles` è in `MODELER_EXCLUDE`); `model:validate` lo rifiuta. Sposta il blocco
  `roles:` da `behavior.yaml` a `domain.ecore.yaml` (stesse chiavi: `label`, `doc`, `scope: <Classe>`; in
  `behavior.yaml` possono restare al più `label` e `doc`), marca `role: true` i riferimenti a `User` che il comportamento
  usa come principal (`self.<riferimento>`, `validate` li elenca; nessuna migrazione), togli `user_roles` da
  `MODELER_EXCLUDE` (`.env*` restano dell'utente: indicagli la riga) e rilancia `model:validate`, `model:sync` e
  `model:drift`.
- Se `behavior.yaml` ha `templates:` (`install` lo segnala con «templates found in behavior.yaml»): parti da
  `${CLAUDE_PLUGIN_ROOT}/kit/next/templates-page.tsx` per la pagina admin dei testi delle notifiche (es.
  `src/app/(admin)/admin/notifications/page.tsx`, link nella navigazione admin) e applica la migrazione
  `notification_templates` (in locale, poi `/core:db-push`). Il motore generato (`npm run model:engine -- --write`)
  rende `subject` e `body` in `recipients`; con un motore a mano il dispatcher legge i testi da `behavior.json`
  (`templates`) e gli override dalla tabella, con lo stesso `render_template` del motore (skill `behavior`, punto 4).
  Il dispatcher ora importa `behavior.json` e la cartella dei template: se ha uno stage proprio nel `Dockerfile` con
  una lista di `COPY`, aggiungili (o copia `src/` intero), altrimenti muore all'avvio in produzione con build e
  deploy verdi (skill `core:deploy`, sezione «Immagini»).
- Se uno stato di `behavior.yaml` ha `requires` o `model` (campi richiesti, in sola lettura, nascosti o limitati per
  stato): i form dell'entità leggono `<entità>_field_policy(record)` del motore (`{campo: {required, readonly,
  hidden, in}}`, `{}` quando lo stato non cambia nulla) e lo riflettono (obbligatorio, disabilitato, non mostrato,
  opzioni ridotte); liste come `STATE_REQUIRES`/`STATE_EDITORS` scritte a mano si tolgono o restano solo come
  `CUSTOM(...)` motivata. Con un motore a mano i frammenti vengono da `npm run model:behavior -- --format sql`.
- Se `behavior.yaml` ha `view_as:` (`install` lo segnala con «view_as found in behavior.yaml»): nel client Supabase
  server aggiungi `...(await viewAsHeaders())` (da `@/lib/modeler/view-as`) alle `global.headers` di
  `createServerClient`; nel layout monta `<ViewAsSwitcher roles={…} current={await viewAsRole()} lang="it" />` (i
  ruoli dell'utente reale con le etichette di `behavior.json`, solo se ne ha più di uno), `<ViewAsRoleBanner>` quando
  `viewAsRole()` non è nullo e `<ImpersonationBanner user={…} by={…}>` quando `viewAsUser()` non è nullo (il profilo
  reale si legge con `select real_profile_id()`); nella pagina admin degli utenti un bottone «Vedi come» per utente
  (`startViewAsUser(id)`) e `<ViewAsLog entries={(await supabase.rpc("view_as_log", {p_limit: 10})).data ?? []} />`.
  Poi `npm run model:engine -- --write` e la migrazione: il motore rinomina `current_profile_id` → `real_profile_id`
  e `has_role` → `has_role_real` dell'app (da lì in poi si modificano quelle), e crea `view_as_allowed(uuid)` solo se
  manca: definiscila nell'app per escludere utenti inattivi o non approvati. Un'app che aveva già «Vedi come» a mano
  (`CUSTOM(view-as)`) toglie la sua versione nella stessa modifica o la tiene come personalizzazione motivata.
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
2. `install <app>` (punto 3), `npm install` se lo chiede (dipendenza nuova), poi `npm run model:validate` e
   `npm run model:sync`;
3. typecheck, lint e test dell'app (gli script di `package.json`); se `install` stampa un suggerimento
   («roles found in behavior.yaml only»: i ruoli vanno nel metamodello, punto 4, nello stesso commit, perché
   `model:validate` li rifiuta; «behavior.yaml found», «workflows in code», `<WorkflowView>`, «DATABASE_URL reaches only the worker»: aggiungi
   `DATABASE_URL: ${DATABASE_URL}` all'`environment` di `web` nel compose del repository e ricorda che il pannello del
   server va aggiornato a mano), applicalo o riportalo all'utente;
4. commit `chore(modeler): upgrade the modeler to <versione>` con, nel corpo, i titoli delle PR dell'harness tra le
   due versioni (`gh pr list --repo iovinoludovico/iovino-harness --state merged --limit 30 --json number,title,mergedAt`,
   quelle con `modeler` nel titolo e più recenti della versione installata) e ciò che l'app deve ancora fare a mano;
5. proponi `/core:ship` (porta anche le migrazioni nuove in cloud prima del push, se ce ne sono).
Se l'app passa a un modellatore con il pannello «Applicazione dal web» (sezione 7), ricorda all'utente di rigenerare
`MODELER_APPLY_TOKEN` con Pull requests: write e Secrets: write e di impostare i segreti dal pannello.
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
- Da impostare una volta. Nel pannello dell'app (Docker Manager, come `DATABASE_URL`; skill `core:deploy`) **una sola
  variabile**: `MODELER_APPLY_TOKEN`, token fine-grained sul solo repository dell'app con Contents: write (i
  `repository_dispatch`), Pull requests: write («Rivedi», e il merge quando fa anche da `MODELER_GH_TOKEN`) e Secrets:
  write (il pannello qui sotto); facoltativo Environments: read per l'avviso sui secret degli environment. Il
  proprietario del token deve poter unire su `main` (con la branch protection, tra chi può unire). Il repository lo
  conosce `modeler-apply.json` (dal remote git, scritto da `install`); `MODELER_APPLY_REPO` serve solo per forzarlo.
- Tutto il resto dal pannello **«Applicazione dal web»** in testa a `/admin/model` (visibile a chi può modificare, non
  in sviluppo). Ciò che l'app ha già nel suo ambiente lo scrive da sé su GitHub appena manca (`applyWebStatus`, al
  caricamento del pannello; la riga dice «impostata il … · dall'ambiente dell'app»): `MODELER_PROD_DB` dalla
  `DATABASE_URL` del container `web` (nel compose passala a `web` come al worker: `install` lo segnala quando raggiunge
  solo il worker) e `MODELER_GH_TOKEN` dal token dell'app (un merge fatto con `GITHUB_TOKEN` non avvia il deploy). Da
  digitare resta la chiave API Anthropic (`ANTHROPIC_API_KEY`: i run si pagano con il credito API, non con
  l'abbonamento); facoltativo il token di un maintainer al posto di quello dell'app; se il web non ha `DATABASE_URL`, la
  password del database (inserita nell'URL del pooler ricavato da `supabase link`) o la stringa di connessione intera
  se il pooler è sconosciuto. «Salva su GitHub» cifra ogni valore con la chiave pubblica del repository (sealed box di
  libsodium, come `gh secret set`) e lo scrive come **repository secret**; l'app non conserva nulla e mostra solo
  «impostata il …». I campi vuoti non toccano il segreto esistente. Lo stesso si può fare a mano con
  `gh secret set NOME --repo owner/repo`.
- Un secret con lo stesso nome negli environment `modeler-apply`/`modeler-release` **prevale** su quello del
  repository: il pannello lo segnala con il comando `gh secret delete NOME --env … --repo …` per toglierlo. «Required
  reviewers» sugli environment (il run aspetta l'approvazione di una persona) esiste solo sui repository pubblici con
  i piani Free, Pro e Team: su un repository privato la conferma umana è il clic in `/admin/model` e il tetto di spesa
  `MODELER_APPLY_BUDGET`. Variabili facoltative (Settings → Secrets and variables → Actions → Variables):
  `MODELER_APPLY_MODEL` (default `claude-opus-5-5`), `MODELER_APPLY_BUDGET` (dollari per run, default 10),
  `MODELER_HARNESS` (marketplace, default `iovinoludovico/iovino-harness`; se il repository dell'harness è privato il
  passo «Claude Code and the modeler plugin» va adattato con un token).
- Se `next build` dell'app fallisce su `libsodium-wrappers` (import dinamico nella server action), aggiungi
  `serverExternalPackages: ["libsodium-wrappers"]` in `next.config.ts`: il pacchetto resta esterno al bundle e Next lo
  copia nello standalone.
- Costo per run (stima; il valore reale è `total_cost_usd` nel riepilogo del job): modifica piccola (attributo,
  relazione, letterale) 2–5 $ con Opus 5.5, 1–2,5 $ con Sonnet 5.5; media (classe nuova con tabella, policy, form,
  pagina) 8–20 $ / 4–10 $. `MODELER_APPLY_BUDGET` ferma il run oltre la soglia (la riga mostra l'errore, nessuna PR).
- Prova: Actions → `modeler-apply` → «Run workflow» con l'id di una proposta di prova; poi, per il rilascio, una
  proposta con una migrazione innocua e `modeler-release` → «Run workflow» (id, numero della PR). I workflow sono
  dell'app: `install` non li sovrascrive (adattali liberamente, es. i servizi di `supabase start`).
