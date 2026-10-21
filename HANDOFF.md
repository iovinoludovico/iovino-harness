# Handoff — «view as» nel modello (PR #32) e creazione in modale dai form (PR #33)
_Aggiornato: 2026-10-21 (sera) · branch `main` (`bb1523a`, PR #33), albero pulito_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Dopo le tre revisioni delle note del 2026-10-21
sono entrate su `main` due funzionalità: «Vedi come» dichiarato in `behavior.yaml` e generato dal motore (PR #32) e
la convenzione «+ Nuovo» in modale per i riferimenti nei form (PR #33, quarta revisione delle note). Rilasciato:
**core 0.21.0, modeler 0.34.0** su `origin/main`. `NOTES.md`: 0 note aperte, 1 rinviata (massimo finito delle
collezioni, nessun progetto lo richiede).

## Stato
- Fatto (PR #32, `af4c56a`, «view as»): chiave `view_as: {users_by: [admin, …]}` in `behavior.yaml` (solo `admin` e
  ruoli senza ambito; `_check_view_as`, `dumps`, `diff`, `from_editor`, BEHAVIOR.md, diff del kit web, `<BehaviorView>`);
  motore generato (`engine.py` `_view_as`: `real_profile_id`/`has_role_real`, `view_as_role`, `view_as_profile_id`,
  `view_as_can_impersonate`, `current_profile_id`, `impersonator_id`, `has_role` avvolta, tabella `view_as_log`,
  `view_as_audit`; `impersonated_by` in `workflow_history` e negli eventi; `drift` ignora `view_as_log`); kit `install`
  (`src/lib/modeler/view-as.ts`, `view-as-actions.ts`, `src/components/modeler/view-as.tsx`); convenzione in
  `conventions.md` («Stack ricorrente»), controllo B di `core:security-audit`, domanda una tantum in `core:project-init`.
- Fatto (PR #33, `bb1523a`, questa sessione): convenzione in `conventions.md` («Lavoro sul codice»): ogni riferimento
  verso una classe in un form offre «+ Nuovo» in modale, stesso componente del form dell'entità, azione server gemella
  che ritorna `{created: {id, label, hint}}` senza redirect, bottone solo se il database permette la creazione
  (`<e>_can('create')`/RLS letto nel server component), un solo livello, parti containment inline, form complessi con
  `?return=`. Ricetta nella skill `modeler:metamodel` §4 punto 3 (`create<E>Inline`, `<ECreate onCreated>`, opzioni in
  `useState`, `canCreate<E>`, test sull'azione inline, chiavi i18n `addNew`/`newTitle`/`create`), presa da
  `SupplierCreate`/`createSupplierInline` di order-management. Nessuna skill nuova né `ui-patterns.md`.
- Verificato: `python3 -m unittest discover -s tests` → 23 OK; `python3 -m unittest discover -s plugins/modeler/tests`
  → 108 OK (8 saltati senza `MODELER_PG`); `claude plugin validate .` OK. Nessuna CI nel repository.
- Non committato: nulla. Questa sessione gira con core 0.20.0 in cache (`/reload-plugins` per 0.21.0 e modeler 0.34.0).

## Decisioni
- Creazione in modale come **convenzione globale** più ricetta nella skill `metamodel`, non una skill nuova né un
  componente del kit — l'utente la vuole in ogni app, anche senza modello; senza un generatore di form un riferimento
  separato sarebbe solo da mantenere. Quando l'harness avrà form generati dal metamodello, la modale è parte del
  componente del riferimento (`ref` non containment); `containment` resta inline.
- «Vedi come» dichiarato nel modello e generato dal motore, mai una sessione o un token dell'altro utente — tutto
  intestato all'utente reale (`impersonated_by`) e registrato in `view_as_log`; `view_as_allowed` creata solo se manca
  per non rompere le app con una versione a mano.
- `record_url` non generata dal motore (nota 2026-10-19 chiusa) — la mappa delle viste sostituite è dell'app; il motore
  la chiama se esiste e `model:drift` segnala `RECORD_URL …` quando i testi usano `{{url}}` e manca.
- Overlay per stato (PR #31): transizione morta = errore, parziale = avviso; verifica di cammino a un passo; `hidden`
  resta nella conformità, `refine` lo toglie solo nella vista. Specifica in `docs/research/state-indexed-refinement.md`.

## Problemi aperti
- order-management tiene `CUSTOM(view-as)` scritto a mano finché non adotta `view_as` nel modello (motore generato o
  frammenti); la modale «+ Nuovo» esiste solo per il fornitore, mancano CPV (ricerca + nuovo codice), fondo e COAN.
- Nessun progetto usa ancora `states.<key>.model`: `field_policy` e i form per stato sono da provare su order-management
  (`STATE_REQUIRES`/`STATE_EDITORS` a mano) e nella sandbox; il caso reale è la prova del disegno (§7 del documento).
- Un controllo automatico di «view as» in `security-audit` B resta manuale (query su `view_as_log` e sui ruoli).
- Ereditati: un rilascio vero dal web (`modeler-release`, PR #28) e un run vero di `modeler-apply` non provati; `psql`
  assente sul Mac (shim in «Per riprendere»); `model:pull`/`model:done` mai riusciti su un progetto cloud;
  `guard_harness_edit` solo Edit/Write; la cartella `help/` non è tracciata (decidere se versionarla o ignorarla);
  editing dell'overlay dal modellatore web rinviato (colonna «Modello» in sola lettura).
- Prova in Chrome con l'estensione: con la scheda in secondo piano i `requestAnimationFrame` sono sospesi; un metodo
  nuovo dell'elemento non può chiamarsi `_view` (è la vista della tela).

## Prossimi passi
1. Qui: `/reload-plugins`. Sugli altri computer: `claude plugin marketplace update iovino-harness && claude plugin
   update core@iovino-harness modeler@iovino-harness`.
2. In order-management: `/modeler:install` (0.34.0, il kit propone «view_as found» se il modello lo dichiara); portare
   `view_as: {users_by: [admin]}` in `behavior.yaml` al posto di `CUSTOM(view-as)`; estendere «+ Nuovo» a CPV, fondo e
   COAN seguendo la ricetta della skill `metamodel` §4 (azione `create<E>Inline`, `<ECreate>`, `canCreate<E>` dalla
   pagina), con il test che l'azione inline non reindirizza.
3. In order-management: `/modeler:behavior` per i campi per stato come `requires`/`model` (`supplier`, `cig`,
   `orderNumber`, `orderDate` da `ordered` con `readonly` dopo l'ordine; `rupAssistants` da `procurement`;
   `deliveryDate` da `delivered`); motore a mano: frammenti da `npm run model:behavior -- --format sql`, `field_policy`
   sullo stesso schema, i form leggono `order_field_policy(record)`; `CUSTOM(order-workflow)` ridotta; `npm run
   model:sync`. Poi annotare nel §7 del documento cosa il caso ha confermato o cambiato.
4. Sandbox (`~/Documents/GitHub/modeler-sandbox`): reinstallare il kit (0.34.0), provare `view_as` end-to-end
   (`view_as_log`, `impersonated_by` in `workflow_history`) e `model: {assignee: {lower: 1, readonly: true}, notes:
   {hidden: true}}` su uno stato di `Task` (`model:validate`, `model:engine -- --write`, update rifiutato nello stato,
   `select task_field_policy(t) from tasks t`, colonna «Modello» in `/admin/model`).
5. Quando il caso degli ordini è in produzione: rileggere `docs/research/state-indexed-refinement.md` §6–§7 e decidere
   se diventa l'articolo (repository a parte) o resta la specifica del plugin.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test senza database: `python3 -m unittest discover -s tests && python3 -m unittest discover -s plugins/modeler/tests && node --test plugins/modeler/tests/layout.test.mjs plugins/modeler/tests/diff.test.mjs plugins/modeler/tests/lint.test.mjs plugins/modeler/tests/behavior.test.mjs && claude plugin validate .`
Test con database (anche il motore end-to-end e «view as»; Docker Desktop acceso):
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
`ed.behavior = <B.runtime_json(b, meta)>`; selezione con `ed._sel = {kind: "class", name: "Invitation"}; ed._render()`.
Headless: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --virtual-time-budget=15000 --dump-dom file://…`
(con `fetch`/`requestAnimationFrame` l'output resta vuoto: usare `setTimeout` e tutto inline); reale: `python3 -m http.server`
e l'estensione, con la scheda visibile.
Sandbox: `cd ~/Documents/GitHub/modeler-sandbox && npm run db:start && PORT=3077 npm run dev` (se il DB è nuovo: `npm run db:reset`);
reinstallare il modellatore dal clone: `python3 plugins/modeler/scripts/modeler.py install ~/Documents/GitHub/modeler-sandbox --no-migration`.
Typecheck dei TSX del kit: cartella fuori dal repository con `npm i --legacy-peer-deps typescript @types/react react react-dom next`,
copia di `kit/next/*.tsx` in `src/`, stub di `@/lib/modeler/metamodel-actions` via `paths`, `tsc --noEmit`.
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (ultime due voci: «view as» e «modale dal form»),
`plugins/core/context/conventions.md` («Lavoro sul codice», «Stack ricorrente»), `plugins/modeler/skills/metamodel/SKILL.md` (§4),
`plugins/modeler/scripts/metamodel/engine.py` (`_view_as`, `_field_policy`, `_workflow`),
`plugins/modeler/scripts/metamodel/behavior.py` (`_check_view_as`, `state_overlay`, `_check_state_model`),
`docs/research/state-indexed-refinement.md` (§5 mappa sul codice, §7 aperto).
