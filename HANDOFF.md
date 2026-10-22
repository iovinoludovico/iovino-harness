# Handoff — notifiche sulla transizione e ruoli nel metamodello (PR #34), creazione in modale (PR #33)
_Aggiornato: 2026-10-21 (notte) · branch `main` (`93d646b`, PR #34), albero pulito_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Quarta e quinta revisione delle note del
2026-10-21: su `main` sono entrate la convenzione «+ Nuovo» in modale per i riferimenti nei form (PR #33, core
0.21.0), le notifiche dichiarate sulla transizione e i ruoli dell'applicazione nel metamodello (PR #34, modeler
0.35.0). `NOTES.md`: 0 note aperte, 1 rinviata (massimo finito delle collezioni, nessun progetto lo richiede).

## Stato
- Fatto (PR #33, `bb1523a`): convenzione in `conventions.md` («Lavoro sul codice»: ogni riferimento verso una classe
  offre «+ Nuovo» in modale, stesso componente del form dell'entità, azione gemella che ritorna `{created}`, bottone
  solo se il database permette la creazione, un livello, containment inline, form complessi con `?return=`) e ricetta
  nella skill `modeler:metamodel` §4 punto 3 (`create<E>Inline`, `<ECreate onCreated>`, esempio di order-management).
- Fatto (PR #34, `93d646b`, squash di `5cbec0a` notifiche + `bf62ae9` ruoli):
  - **Notifiche sulla transizione**: `notify: [principals]` e `template:` sulla transizione (forma lunga
    `notify: {to, template, when}`); `behavior.py` `expand` aggiunge la reazione sintetica `notify_<transizione>`
    (marcata `_transition`), `dumps`/`from_editor`/`diff` tengono la forma breve, `runtime_json` porta `notifies` su
    ogni transizione (entrambe le forme), `transition_reactions` riconosce `transition = k and (…)`. Editor: colonne
    «Avvisa»/«Template» nella tabella delle transizioni, reazioni-notifica fuori dal pannello laterale, freccia con ✉
    e tooltip (anche `<workflow-view>`), `<BehaviorView>` colonna «Avvisa». Fixture: `confirm` e `director_return` in
    forma breve. Test `test_notification_declared_on_the_transition`.
  - **Ruoli nel metamodello**: `roles:` a livello di package in `domain.ecore.yaml` (`label`, `doc`, `scope: <Classe>`;
    `admin` predefinito), memorizzati come enum `app_role` + tabella `user_roles` (schema appforge): `E.storage`
    (`roles`), `sqlgen._roles` (tipo e tabella se mancano, FK a `profiles` solo se esiste, `add value if not exists`,
    TODO policy), `D.drift` (`MISSING TYPE/ROLE/TABLE/COLUMN`, `NOT IN METAMODEL role`, suggerimento su `user_roles`),
    `D.reverse` (scrive `roles:`, non una classe), `role: true` su un `ref` a `User` = ruolo di record; Emfatic,
    Mermaid, `DOMAIN.md` («Ruoli», «Ruoli di record»), XMI, `diff`, `patch_text`, `runtime_json` (`builtin_roles`).
    `behavior.py` `bind(raw, e)` unisce i ruoli (`source`: metamodel/behavior/both) e lo usano `validate`,
    `runtime_json`, `to_markdown`, `engine_version`, `sql_view`, `engine_sql`; `roles:` del behavior facoltativo
    (`_check_roles`: errore se lo scope differisce, avvisi su label/doc diversi e su ruoli non dichiarati nel
    metamodello); avviso «ruolo di record» su `self.<ref>` a `User` senza `role: true`; `from_editor` non riscrive i
    ruoli del metamodello. Editor: pannello «Ruoli» su `mm.roles` (ruoli solo del behavior marcati «in
    behavior.yaml»), checkbox «ruolo» sul riferimento a `User`, «role» nella riga del box, `diff` dei ruoli,
    `behaviorSource` esclude i ruoli del metamodello. Fixture: `roles:` in `invitations.ecore.yaml`,
    `issuer: {type: User, role: true}`. Test `RolesTests` (3), `test_roles_migration_applies_and_aligns` (Postgres),
    `RolesFromTheMetamodelTests`.
  - Notazione (`ecore-notation.md` «Roles», `behavior-notation.md` Transitions/Principals/parole), skill `metamodel`
    §3, `behavior` §2-3, `install` §2, README; `NOTES.md` con le decisioni.
- Verificato: `python3 -m unittest discover -s plugins/modeler/tests` → 114 OK, anche con `MODELER_PG` su Postgres 16
  in Docker (motore end-to-end, migrazione dei ruoli idempotente e allineata); `python3 -m unittest discover -s tests`
  → 23 OK; `node --test` dei 4 `.mjs` → 182 OK; `claude plugin validate .` OK. Nessuna CI nel repository.
- Non committato: nulla. Questa sessione gira con core 0.20.0 in cache (`/reload-plugins` per core 0.21.0 e modeler
  0.35.0).

## Decisioni
- Ruoli come **enum di chiavi** (`roles:` del package → `app_role`), non classe `Role` con righe — `by`/`notify`/`view_as`
  citano chiavi fisse; una classe con righe darebbe ruoli a runtime al prezzo di un seed e di un motore diverso.
  Memorizzazione uguale ad appforge (`app_role`, `user_roles`): zero migrazione per le app esistenti.
- `roles:` di `behavior.yaml` resta facoltativo e la fixture lo tiene insieme al metamodello (valori identici: nessun
  avviso) — i file esistenti non vanno migrati; il metamodello vince e le differenze sono segnalate.
- La notifica di una transizione è una **reazione sintetica** in `expand`, non un nuovo concetto del motore — motore,
  dispatcher, template e sottoscrittori non cambiano; le due forme coesistono e `validate` **non** suggerisce la breve
  (le reazioni `transition = k` esistenti restano valide; lo dicono notazione e skill).
- Nessun box `Role`/`User` nel diagramma — `User` non ha un box neppure oggi (righe attenuate nella classe); i ruoli
  stanno nella tabella del pannello laterale, i ruoli di record nella riga del riferimento.
- Nessuna pagina utenti nel kit — `/admin/users` è dell'app (appforge); `metamodel.json` porta i ruoli che può leggere.
- Creazione in modale come convenzione globale più ricetta nella skill, non componente del kit — nessun generatore di form.
- (Ereditate) overlay per stato: transizione morta = errore, parziale = avviso; `record_url` non generata dal motore;
  «vedi come» dichiarato nel modello, mai una sessione dell'altro utente.

## Problemi aperti
- order-management: al prossimo `/modeler:install` (0.35.0) portare i ruoli in `domain.ecore.yaml` (`roles:` da
  `app_role`: rup, rup_assistant, area_director per Department), `role: true` su `Order.rupAssistants`, le 7 reazioni
  `notify_*` in forma breve sulle transizioni, `view_as` al posto di `CUSTOM(view-as)`; `MODELER_EXCLUDE` in
  `package.json` esclude ancora `user_roles` (toglierla: `drift` la confronta).
- Nessun progetto usa ancora `states.<key>.model` né i ruoli nel metamodello: la sandbox e order-management sono la prova.
- Editor: la select dei template con «+ nuovo» nel pannello della transizione è un campo di testo; la colonna «Modello»
  è in sola lettura (editing dell'overlay rinviato).
- Un controllo automatico di «view as» in `security-audit` B resta manuale.
- Ereditati: un rilascio vero dal web (`modeler-release`, PR #28) e un run vero di `modeler-apply` non provati; `psql`
  assente sul Mac (shim in «Per riprendere»); `model:pull`/`model:done` mai riusciti su un progetto cloud;
  `guard_harness_edit` solo Edit/Write; la cartella `help/` non è tracciata (decidere se versionarla o ignorarla).
- Prova in Chrome con l'estensione: con la scheda in secondo piano i `requestAnimationFrame` sono sospesi; un metodo
  nuovo dell'elemento non può chiamarsi `_view` (è la vista della tela).

## Prossimi passi
1. Qui: `/reload-plugins`. Sugli altri computer: `claude plugin marketplace update iovino-harness && claude plugin
   update core@iovino-harness modeler@iovino-harness`.
2. In order-management: `/modeler:install` (0.35.0); `roles:` nel metamodello e `role: true` su `Order.rupAssistants`
   (`npm run model:validate`, `npm run model:drift` senza `user_roles` in `MODELER_EXCLUDE`); le reazioni
   `notify_*` → `notify`/`template` sulle transizioni (`npm run model:sync`, controllare `notifies` in
   `behavior.json` e la ✉ in `/admin/model`); `view_as: {users_by: [admin]}` al posto di `CUSTOM(view-as)`; «+ Nuovo»
   per CPV, fondo e COAN con la ricetta della skill `metamodel` §4.
3. In order-management: `/modeler:behavior` per i campi per stato come `requires`/`model` (`supplier`, `cig`,
   `orderNumber`, `orderDate` da `ordered` con `readonly` dopo l'ordine; `rupAssistants` da `procurement`;
   `deliveryDate` da `delivered`); motore a mano: frammenti da `npm run model:behavior -- --format sql`,
   `field_policy` sullo stesso schema; `CUSTOM(order-workflow)` ridotta. Poi annotare nel §7 di
   `docs/research/state-indexed-refinement.md` cosa il caso ha confermato o cambiato.
4. Sandbox (`~/Documents/GitHub/modeler-sandbox`): reinstallare il kit (0.35.0), `roles:` nel metamodello con
   `npm run model:migrate` (tipo e tabella creati), `notify` su una transizione di `Task`, `view_as` end-to-end,
   `model: {assignee: {lower: 1, readonly: true}}` su uno stato (`model:validate`, `model:engine -- --write`,
   `select task_field_policy(t) from tasks t`).
5. Quando il caso degli ordini è in produzione: rileggere `docs/research/state-indexed-refinement.md` §6–§7 e decidere
   se diventa l'articolo (repository a parte) o resta la specifica del plugin.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test senza database: `python3 -m unittest discover -s tests && python3 -m unittest discover -s plugins/modeler/tests && node --test plugins/modeler/tests/layout.test.mjs plugins/modeler/tests/diff.test.mjs plugins/modeler/tests/lint.test.mjs plugins/modeler/tests/behavior.test.mjs && claude plugin validate .`
Test con database (motore end-to-end, «view as», migrazione dei ruoli; Docker Desktop acceso):
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
Rilascio: `python3 scripts/release.py` (anteprima), `--write` (versioni + commit `chore(release)`), poi `/core:ship`
(push, PR, merge su conferma); il pre-push blocca un plugin modificato con la versione vecchia.
Prova dell'editor in Chrome senza app: una pagina HTML con `<metamodel-editor lang="it">` in un `div` di 1200×760, il kit
inlineato in uno `<script>`, `ed.metamodel = <E.runtime_json(E.load(fixture))>`, `ed._allAttrs = true`,
`ed.behavior = <B.runtime_json(b, meta)>`; selezione con `ed._sel = {kind: "class", name: "Invitation"}; ed._render()`;
la ✉ delle transizioni è `text.wfn[data-notifies]` nel pannello del workflow.
Headless: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --virtual-time-budget=15000 --dump-dom file://…`
(con `fetch`/`requestAnimationFrame` l'output resta vuoto: usare `setTimeout` e tutto inline); reale: `python3 -m http.server`
e l'estensione, con la scheda visibile.
Sandbox: `cd ~/Documents/GitHub/modeler-sandbox && npm run db:start && PORT=3077 npm run dev` (se il DB è nuovo: `npm run db:reset`);
reinstallare il modellatore dal clone: `python3 plugins/modeler/scripts/modeler.py install ~/Documents/GitHub/modeler-sandbox --no-migration`.
Typecheck dei TSX del kit: cartella fuori dal repository con `npm i --legacy-peer-deps typescript @types/react react react-dom next`,
copia di `kit/next/*.tsx` in `src/`, stub di `@/lib/modeler/metamodel-actions` via `paths`, `tsc --noEmit`.
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (ultime tre voci), `plugins/modeler/skills/notation/references/ecore-notation.md`
(«Roles»), `plugins/modeler/skills/notation/references/behavior-notation.md` (Transitions, Principals),
`plugins/modeler/scripts/metamodel/behavior.py` (`expand` con la reazione sintetica, `bind`, `_check_roles`, `_check_principal`),
`plugins/modeler/scripts/metamodel/ecore.py` (`roles` in `expand`/`validate`/`storage`/`patch_text`),
`plugins/modeler/scripts/metamodel/sqlgen.py` (`_roles`), `plugins/modeler/scripts/metamodel/dbschema.py` (`reverse`, `drift`),
`plugins/modeler/kit/metamodel-editor.js` (`_globalBehaviorPanel`, `_workflowEditor`, `workflowSvg`).
