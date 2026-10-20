# Handoff — modellatore: skill `/modeler:behavior` per il modello di comportamento
_Aggiornato: 2026-10-20 · branch `feat/modeler-behavior-skill` (1 commit sopra `main` `60932ed`, non pushato)_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Questa sessione: nelle app model-based la pagina di
dettaglio di un record di un'entità con workflow mostra un div con il diagramma degli stati e lo stato corrente
evidenziato, come pezzo riusabile del kit del modeler (provato nella sandbox).

## Stato
- Branch locale `feat/modeler-behavior-skill` (da unire con `/core:ship`): nuova skill
  `plugins/modeler/skills/behavior/SKILL.md` (dove; `show`; dalle parole al modello con le regole che stavano in
  `metamodel` §3b: derivazioni, guardie, destinatari sull'evento di stato, cardinalità, `templates:`, ambiguità in
  un giro; struttura nella stessa modifica via `metamodel`; allineamento: validate, sync, motore generato o a mano,
  codice, test, proposte via `apply`). `metamodel` resta per la struttura con un §3b di rimando; puntatori
  aggiornati: `cli.workflow_hint`, nota di `reverse` (`dbschema`), intestazione di `behavior.yaml` (`behavior.dumps`),
  hook di sessione, `behavior-view.tsx`, skill `install` (frase per il `CLAUDE.md` dell'app), `apply` (motore
  generato o a mano), `notation`, convenzioni e `project-init` di core, README, `help/harness-process.html`.
  Test: `workflow_hint` atteso con `/modeler:behavior`. Non provato: la skill su un'app vera (dopo `/reload-plugins`,
  nella sandbox `/modeler:behavior show Task` e una reazione di prova).
- PR #26 (`60932ed`, modeler 0.25.0): testi delle notifiche nel modello (`templates:`), resi dal motore, override
  dalla pagina admin del kit. In order-management i testi sono già nell'app (PR #14 di quel repository: classe
  `NotificationTemplate`, tabella `notification_templates` con colonna `template`, rendering in `render.ts`,
  `/admin/templates`; n8n spedisce soltanto): l'allineamento al kit è facoltativo (vedi «Prossimi passi»).
- `origin/main` è alla PR #20 (`2e6d80c`): **core 0.12.0, modeler 0.21.0**. Storia di oggi: PR #18 `<workflow-view>`
  (modeler 0.19.0); PR #19 `cli.workflow_hint` in `install`/hook/`reverse`, «Motore a mano» in `metamodel` §3b,
  `help/harness-process.html` (core 0.11.0, modeler 0.20.0); PR #20 vista esistente e `<WorkflowView>` in due schede
  (skill `install` §4 con snippet `WorkflowTabs`, rimando in `metamodel` §4, riga nelle convenzioni; core 0.12.0,
  modeler 0.21.0). Nessuna nota aperta in `NOTES.md`.
- PR #21 (`1aba74a`, modeler 0.21.1): lo stato corrente di `<workflow-view>` è pieno del suo colore con testo bianco
  e anello, gli altri stati attenuati, `data-state-missing` per un valore non tra gli stati; sandbox a 0.21.1.
- PR #22 (`d9f433c`, core 0.13.0, modeler 0.21.2): convenzione sui link costruiti dal database, appforge rimosso ovunque.
- PR #23 (`35ef643`, modeler 0.22.0): cardinalità delle collezioni (notazione, warning di `validate`, skill).
- PR #24 (`bcb7da4`, modeler 0.23.0): destinatari sull'evento del cambio di stato (notazione, warning, colonna «Avvisa»).
- PR #25 (`d4dae36`, core 0.14.0, modeler 0.24.0): ciclo di release automatizzato (install con controllo versione e
  aggiornamento automatico, ship con db-push e attesa del deploy, fallback `supabase db query`, guard).
- Branch locale `feat/modeler-notification-templates` (settima revisione delle note, da unire con `/core:ship`):
  `d0224ba feat(modeler): notification texts in the model, rendered by the engine, overridable from the admin page` +
  `90d9979 chore(release): modeler 0.25.0`. `templates:` in `behavior.yaml` (per lingua, segnaposto sul record e
  sull'evento), `validate` (`_check_templates`), `BEHAVIOR.md`, `behavior.json`; motore: `render_template`,
  `<entità>_template_vars`, `<entità>_recipients` con `subject`/`body` resi e override da `notification_templates`;
  kit: `notification_templates.sql`, `notification-templates.tsx` (matrice), `notification-actions.ts`,
  `templates-page.tsx`, `install` (`has_templates`, `templates_page_hint`); skill `metamodel` e `install`.
  Provato sulla sandbox (database reale): override, testi del modello, sollecito; sandbox a 0.25.0 con i testi di Task.
- Storia (PR #25, già in `main`): branch `feat/release-cycle-automation`:
  `92e59f2 feat: automate the plugin release cycle …` + `62d9ca5 chore(release): core 0.14.0, modeler 0.24.0`.
  Skill `install`: «0. Versione del plugin» (cache contro `origin/main` dell'harness, comando di aggiornamento e
  stop) e «6. Aggiornamento di un'app già installata» (branch, install, validate, sync, controlli, commit con i titoli
  delle PR, `/core:ship`); hook di sessione con il comando di aggiornamento. Skill `ship`: migrazioni non in cloud →
  passi di `db-push` con una sola conferma; dopo il merge polling del run di deploy sullo SHA del merge, proposta di
  `model:done` e di `core:handoff`. CLI: `dbschema.cli_query` (`supabase db query -o json`, `--linked` via Management
  API senza password, busta agent-mode aperta e HTML unescaped) usata senza `psql` da `pull`/`done`
  (`_prod_target`) e da `drift`/`reverse`; `.modeler/backups/` in `.gitignore`. Guard di `core`: `supabase db query`
  che scrive chiede, una select passa. **Non provato qui**: la CLI Supabase non è installata su questo Mac; il formato
  dell'output viene dal sorgente della CLI (`SIDE_EFFECTS.md` di `db query`), da verificare al primo `model:pull` reale.
- Storia (PR #24, già in `main`): branch `feat/modeler-transition-recipients`:
  `c2622dd feat(modeler): recipients of a transition travel on the state-change event` + `dab0d50 chore(release):
  modeler 0.23.0`: regola ed esempio in `behavior-notation.md`; `validate` avvisa per destinatari su un evento
  secondario (`emits`), per doppi destinatari e per reazioni che nessuna `subscription` riceve
  (`_check_recipients_event`, `transition_reactions`); colonna «Avvisa» in `BEHAVIOR.md`; test sul `recipients`
  sempre presente nel motore generato. Nessuna nota «da valutare» in `NOTES.md` (restano i due residui a condizione).
- Storia (PR #23, già in `main`): branch `feat/modeler-collection-multiplicities`:
  `feat(modeler): minimum and maximum of a collection, enforced by a guard or reported` + release (modeler 0.22.0):
  notazione, `_check_multiplicities`/`_guarded` in `behavior.validate` (minimo senza guardia), warning di
  `ecore.validate` per `upper` finito (normalizzato a many), skill `metamodel` §3b e `apply`, fixture con
  `invitationFunds.notEmpty()`. Rinviati: trigger del massimo generato e annotazione in `DOMAIN.md`.
- Storia (PR #22, già in `main`): branch `feat/core-record-url-convention`:
  `749732b feat(core): record links built in the database follow the replaced views too` (convenzione «pagina che
  sostituisce la vista generica» estesa al database: `<e>_json` con `app_base_url`, `grep -n "/e/"` nelle migrazioni,
  unica `record_url(entity, id)` SQL, test sull'`url`), `fa34fe7 docs: record harness note decisions` (nota «link
  negli eventi» in parte applicata: la `record_url` generata dal motore è rinviata finché `engine.py` non costruisce URL
  nei payload; nota «due schede» chiusa come applicata), `25bd14e chore(release): core 0.13.0`; poi `92cbfeb refactor:
  drop appforge everywhere` (skill, README, docstring, avviso in `install.sh`, import `.ecore` senza le annotazioni
  `source="appforge"`; `NOTES.md` intatto come storico) + `1772123 chore(release): modeler 0.21.2`.
- Cosa c'è nel kit (`plugins/modeler/kit/metamodel-editor.js`): secondo custom element **`<workflow-view>`** nello
  stesso file (proprietà `workflow` = `behavior.workflows[Classe]`, attributi `lang`, `name`, `state`; `state` anche come
  proprietà riflessa): `Layout.workflowLayout` alla larghezza del contenitore (`contain:inline-size` sull'host, così una
  cella di griglia non si allarga sull'SVG; `ResizeObserver`; scroll orizzontale sotto il minimo), box dello stato
  corrente riempito del suo colore (`style` inline: la regola `.wfs` vince su un attributo `fill`) con bordo 3.5,
  transizioni in uscita a piena forza (classe `out`), le altre attenuate (`far`, opacità .3), hover come nell'editor.
  Condivisi tra editor e viewer: `workflowSvg(cn, L, {current, focus})`, `textMeasure()`, `applyHover(roots, key)`,
  `hostCss` + `wfCss`. Nel layout puro ogni edge porta `from` (sorgenti; il bus tutte) e `Layout.workflowFocus(edges, state)`
  dà gli id degli edge in uscita (test in `layout.test.mjs`).
- Wrapper React `kit/next/workflow-view.tsx` (`<WorkflowView behavior entity state lang className style>`, `null` se la
  classe non ha workflow; `next/script` dedup per `src`), installato da `install` in `src/components/modeler/workflow-view.tsx`
  (test in `test_modeler.py`); skill `install` §3/§4/§5 e README aggiornati.
- Sandbox (`~/Documents/GitHub/modeler-sandbox`, commit `chore: modeler 0.19.0 (workflow view on the record detail)`):
  `src/app/e/[entity]/[id]/page.tsx` importa `behavior.json` e mette `<WorkflowView>` nella colonna destra sopra
  «Transizioni». Provato nel browser: record `done`/`cancelled` (nessuna uscita), record `todo` (Avvia, Annulla, Scaduta
  a piena forza), contenitore stretto (host 207 px, diagramma 452 px con scroll), `/admin/model` invariato (pannello,
  hover, tabelle). Screenshot in `/var/folders/.../claude-chrome-screenshots-*` (temporanei).
- Verificato (2026-10-19): `node --test` 180 pass; `unittest` modeler 94 OK (8 skip), core 23 OK; `claude plugin validate .`;
  sandbox `tsc --noEmit` e `eslint` puliti (è anche il typecheck dei TSX del kit, installati lì).
- Non committato nell'harness: la cartella `help/` (estranea a questo lavoro; decidere se versionarla o ignorarla).

## Decisioni
- Un solo algoritmo di layout: il viewer riusa `Layout.workflowLayout` dallo stesso file del kit (niente porting in TSX);
  per questo il wrapper carica `public/modeler/metamodel-editor.js` anche sulle pagine di dettaglio (cache del browser).
- Evidenziazione: stato corrente riempito + transizioni in uscita; gli stati già attraversati (storia) non sono mostrati.
- Il componente prende `behavior` intero + `entity` (semplice per le app); se un `behavior.json` diventa grande, aggiungere
  una prop `workflow` alternativa.
- Posizione nella sandbox: colonna destra (accanto a badge e azioni); con workflow lunghi (10+ stati) le app lo mettono a
  tutta larghezza (detto nella skill `install`).

## Problemi aperti
- Il ridimensionamento della finestra di Chrome via estensione non ha effetto su questo Mac: la larghezza stretta è stata
  simulata restringendo `main` via JS (il comportamento a viewport telefono reale non è stato visto).
- Ereditati: motore generato non provato su un'app vera (la sandbox sì); `psql` assente sul Mac (shim in «Per riprendere»);
  `model:pull`/`model:done` mai riusciti su un progetto cloud; `guard_harness_edit` solo Edit/Write.

## Prossimi passi
1. `/core:ship` del branch `feat/modeler-behavior-skill` (push, PR, merge su conferma); poi `/reload-plugins` e sugli
   altri computer `claude plugin update core@iovino-harness modeler@iovino-harness`. Prova nella sandbox:
   `/modeler:behavior show Task` e una reazione di prova («avvisa l'assegnatario quando il task torna in todo»):
   reazione, template, `sync`, `engine --write` senza passare da `model:migrate`.
2. In order-management (modeler installato 0.23.0): `/modeler:install` segue da solo il punto 6 della skill e porta nel
   `CLAUDE.md` dell'app la riga su `/modeler:behavior`; rifiutare la migrazione `notification_templates` del kit
   (colonna `key`; la tabella dell'app ha `template` e la sua pagina). Facoltativo: `templates:` in `behavior.yaml`
   con i testi del seed riscritti con i segnaposto della notazione (`{{self.code}}`, `{{actor.name}}`, `{{url}}`) e
   `render.ts` che li risolve. Al primo `npm run model:pull` senza `psql` verificare la busta di `supabase db query`
   (se il formato differisce, adattare `dbschema.cli_query`).
4. In order-management, per la convenzione sui link costruiti dal database: migrazione `create or replace` delle
   `<e>_json` con una `record_url(entity, id)` SQL, redirect `/e/<entità>/<id>` → pagina nuova e test sull'`url`.
3. In invitations-af e order-management: `/modeler:install` (0.19.0) e `<WorkflowView>` nelle pagine di dettaglio delle
   entità con workflow (Invitation a 11 stati: a tutta larghezza).
4. Eventuale: stati già attraversati (da `workflow_history`) con un riempimento più leggero, prop `workflow` alternativa.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test senza database: `python3 -m unittest discover -s tests && python3 -m unittest discover -s plugins/modeler/tests && node --test plugins/modeler/tests/layout.test.mjs plugins/modeler/tests/diff.test.mjs plugins/modeler/tests/lint.test.mjs && claude plugin validate .`
Sandbox: `cd ~/Documents/GitHub/modeler-sandbox && npm run db:start && PORT=3077 npm run dev` (se il DB è nuovo: `npm run db:reset`);
reinstallare il modellatore dal clone: `python3 plugins/modeler/scripts/modeler.py install ~/Documents/GitHub/modeler-sandbox --no-migration`.
Test con database (anche il motore end-to-end):
```bash
docker run -d --rm --name modeler-pg-test -e POSTGRES_PASSWORD=pg -p 55499:5432 postgres:16
mkdir -p /tmp/pgbin && cat > /tmp/pgbin/psql <<'PY'
#!/usr/bin/env python3
import subprocess, sys
args = [a.replace("localhost:55499", "localhost:5432") for a in sys.argv[1:]]
sys.exit(subprocess.run(["docker", "exec", "-i", "-e", "PGPASSWORD=pg", "modeler-pg-test", "psql", *args], stdin=sys.stdin).returncode)
PY
chmod +x /tmp/pgbin/psql
PATH=/tmp/pgbin:$PATH MODELER_PG=postgresql://postgres:pg@localhost:55499/postgres python3 -m unittest discover -s plugins/modeler/tests
docker stop modeler-pg-test
```
Typecheck dei TSX del kit: cartella fuori dal repository con `npm i --legacy-peer-deps typescript @types/react react react-dom next`,
copia di `kit/next/*.tsx` in `src/`, stub di `@/lib/modeler/metamodel-actions` via `paths`, `tsc --noEmit`.
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (ultime tre note), `plugins/modeler/kit/metamodel-editor.js`
(`workflowLayout`, `satelliteOf`, `routeEdges`, `_drawSatellite`, `_satellite`), `plugins/modeler/scripts/metamodel/behavior.py`
(`uses`), `expr.py` (`_navigate`, `hops_used`), `plugins/modeler/tests/layout.test.mjs`, e nella sandbox `README.md`,
`src/lib/db/with-user.ts`, `src/lib/model/model.ts`, `src/app/e/[entity]/[id]/page.tsx`, `scripts/db.sh`.
