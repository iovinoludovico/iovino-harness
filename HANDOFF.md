# Handoff — metamodello dipendente dallo stato (`states.<key>.model`) unito in main
_Aggiornato: 2026-10-21 (sera) · branch `main` (`061696f`, PR #30), albero pulito_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Seconda revisione delle note del 2026-10-21:
la nota «Metamodello dipendente dagli stati» è applicata come **overlay restrittivo per stato** (`states.<key>.model`
in `behavior.yaml`), non come più metamodelli: un solo metamodello e un solo schema, le versioni `MM_s ⊑ MM` sono
derivate. Rilasciato: **core 0.19.1, modeler 0.31.0** su `origin/main`. Nessuna nota aperta in `NOTES.md`
(1 rinviata: collezioni con `upper` finito).

## Stato
- Fatto (PR #30, squash di 6 commit):
  - Notazione `model: {feature: {lower: 1, readonly, hidden, in: [a, b]}}` sullo stato, `requires` = abbreviazione di
    `lower: 1`; `hidden` = sola lettura e non mostrato, valore conservato; nessuna ereditarietà fra stati
    (`behavior-notation.md`, bullet dopo `requires`; `ecore-notation.md` Multiplicity; skill `behavior`, `metamodel`,
    `apply`, `install`; README).
  - `behavior.py`: `MODEL_KEYS`, `_model_spec`, `state_overlay`, `required_features`, `refine` (il metamodello come visto
    da uno stato), `state_matrix`, `domain_annotations`, `state_columns`, `overlay_mark`, `_check_state_model` (al posto
    di `_check_requires`: raffinamento, `in` solo su enum singolo, controllo lungo il percorso), `uses` con i kind
    `allowed`/`readonly`/`hidden`, `diff`, `engine_version` (`model`), BEHAVIOR.md con «Il metamodello per stato»,
    `sql_view` con i frammenti `in` e sola lettura.
  - `ecore.py`: `to_markdown(raw, lang, states)` e `markdown_document(…, states)`: DOMAIN.md con «0..1 · 1 da <stato>»
    nella molteplicità e sola lettura/assente/valori nelle note; `to_emfatic` stampa `// in: a, b`. `cli.py`:
    `domain_states(root, raw)` letto da `docs_status` e `write_docs` (un cambio dell'overlay rende DOMAIN.md «stale»),
    `show --state Classe.stato [--behavior]`.
  - `engine.py`: messaggi `readonly`/`allowed`, `_allowed`, `_field_policy`; trigger `<e>_workflow_guard` con gli
    invarianti (richiesto, «Read only in state %: %», «Not allowed in state %: %», errcode 23514), `in` fra i `missing`
    di `perform_transition`/`_available_transitions`, nuova `<e>_field_policy(r)` → `{campo: {required, readonly,
    hidden, in}}` (`{}` senza overlay), TODO in coda per i form.
  - Kit: `metamodel-editor.js` (`Layout.stateView`, `stateOverlay`, `viewMark`, `wfLabel` esportati; `rowItems`/
    `rowsOf`/`boxSize` con `opts {overlay, view, from}`; `edgesOf`/`routeEdges`/`autoLayout` con `overlay`; elemento:
    `_overlay`, `_overlays`, `_stateViewOf`, `_rowOpts`, `_wfView` impostato da `mouseenter`/`mouseleave` sui
    `[data-state]` del pannello e `_renderDiagram()`; stereotipo «workflow · <stato>», CSS `.box text.hidden`,
    `.box.viewed`; colonna «Modello» in sola lettura nel pannello degli stati; lint; `behaviorDiff` con `model`;
    `behaviorSource` scrive `model` compatto), `behavior-view.tsx` (`Overlay`, `overlayOf`, `requiredOf`, `mark`,
    tabella feature × stato).
  - `core`: `hook.py` `note_states` legge l'ultima riga `**Stato…**` di una voce (test in `tests/test_core_hooks.py`);
    frase nella skill `harness-review`.
  - `NOTES.md`: la nota 2026-10-21 «Metamodello dipendente dagli stati» è applicata, con i rinvii (sotto).
- Verificato: `python3 -m unittest discover -s tests` → 23 OK; `python3 -m unittest discover -s plugins/modeler/tests`
  → 106 OK, anche con `MODELER_PG` su Postgres 16 in Docker (fine a fine: update rifiutato nello stato, `in` in
  ingresso, `field_policy`); `node --test` dei 4 `.mjs` → 182 OK; `claude plugin validate .` OK; editor provato in
  Chrome headless e reale (pagina di prova con la fixture `invitations` e un overlay su `pending_director`: righe e
  connettori con «1 da In attesa di approvazione», colonna «Modello», hover sullo stato → `🔒 flatAmount [1]`,
  `travelMethod [1] ∈ {agency, receipts}`, `notes` barrato, ritorno alla vista statica al `mouseleave`).
- Non committato: nulla. I plugin in questa sessione sono ancora core 0.14.0 nella cache (il harness si carica dal
  clone: `/reload-plugins` per le versioni nuove).

## Decisioni
- Overlay restrittivo, non più metamodelli — n copie sarebbero da co-evolvere e darebbero uno schema per stato;
  l'overlay stringe soltanto (`validate` rifiuta un `lower` più basso dello statico), così il database resta unico e
  le «versioni» sono viste (`refine`). È una riclassificazione dinamica disciplinata (typestate per i modelli), non
  una sottoclasse per stato.
- `hidden` conserva il valore — la migrazione fra stati non perde dati; `hidden` implica `readonly`.
- `readonly`/`hidden` su una collezione sono solo segnalati (avviso di `validate`, `field_policy`) — il trigger del
  container non vede le parti.
- `in` solo su attributi enum singoli; violazioni elencate fra i `missing` (stesso meccanismo di `requires`).
- DOMAIN.md dipende anche da `behavior.yaml` — l'annotazione «1 da <stato>» deve stare dove si legge la struttura;
  `docs_status` rigenera con lo stesso overlay, quindi lo stato «edited» non scatta per questo.
- Editing dell'overlay dal modellatore web rinviato — nel pannello degli stati `model` è una colonna in sola lettura
  (una sintassi testuale per `{lower, readonly, hidden, in}` in un input sarebbe fragile); si scrive in `behavior.yaml`.
- Conteggio delle note: decide l'ultima riga Stato — la convenzione «Stato (parte rimasta)» è già nel file.

## Problemi aperti
- Nessun progetto usa ancora `model`: `field_policy` e i form per stato sono da provare su order-management
  (`STATE_REQUIRES`/`STATE_EDITORS` scritti a mano) e nella sandbox.
- Ereditati: un rilascio vero dal web (`modeler-release`, PR #28) e un run vero di `modeler-apply` non provati;
  `psql` assente sul Mac (shim in «Per riprendere»); `model:pull`/`model:done` mai riusciti su un progetto cloud;
  `guard_harness_edit` solo Edit/Write; la cartella `help/` non è tracciata (decidere se versionarla o ignorarla).
- Prova in Chrome con l'estensione: con la scheda in secondo piano i `requestAnimationFrame` sono sospesi; e un
  metodo nuovo dell'elemento non può chiamarsi `_view` (è la vista della tela): errore scoperto solo nel browser.
- Parte di ricerca della nota (overlay = raffinamento indicizzato dallo stato, transizione = migrazione dell'istanza,
  legami con typestate, Fickle/riclassificazione dinamica, co-evoluzione, EVL): fuori dal plugin, da scrivere con il
  caso degli ordini.

## Prossimi passi
1. Qui: `/reload-plugins` (core 0.19.1, modeler 0.31.0). Sugli altri computer: `claude plugin marketplace update
   iovino-harness && claude plugin update core@iovino-harness modeler@iovino-harness`.
2. In order-management: `/modeler:install` (0.31.0), poi `/modeler:behavior` per portare in `behavior.yaml` i campi
   per stato come `requires`/`model` (`supplier`, `cig`, `orderNumber`, `orderDate` da `ordered`, con `readonly` dopo
   l'ordine; `rupAssistants` da `procurement`; `deliveryDate` da `delivered`); motore a mano: i frammenti da
   `npm run model:behavior -- --format sql`, `field_policy` scritta a mano sullo stesso schema, i form leggono
   `order_field_policy(record)` e spariscono `STATE_REQUIRES`/`STATE_EDITORS`; `CUSTOM(order-workflow)` ridotta in
   `docs/customizations.md`; `npm run model:sync` (DOMAIN.md con «1 da In istruttoria»).
3. Prova nella sandbox (`~/Documents/GitHub/modeler-sandbox`): reinstallare il kit (0.31.0), `model: {assignee:
   {lower: 1, readonly: true}, notes: {hidden: true}}` su uno stato di `Task`, `npm run model:validate`, `model:sync`,
   `model:engine -- --write`, migrazione locale, update rifiutato nello stato, `select task_field_policy(t) from
   tasks t`; in `/admin/model` la colonna «Modello» e l'hover sugli stati.
4. Facoltativo: typecheck dei TSX del kit (`behavior-view.tsx` con `Overlay`) come descritto sotto; `npm run
   model:show -- --state Task.done` nella sandbox.
5. Se il caso degli ordini conferma il disegno: `/core:harness-note` per l'editing dell'overlay dal web e per la
   bozza dell'articolo (le note della ricerca sono nella voce 2026-10-21 di `NOTES.md`).

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test senza database: `python3 -m unittest discover -s tests && python3 -m unittest discover -s plugins/modeler/tests && node --test plugins/modeler/tests/layout.test.mjs plugins/modeler/tests/diff.test.mjs plugins/modeler/tests/lint.test.mjs plugins/modeler/tests/behavior.test.mjs && claude plugin validate .`
Test con database (anche il motore end-to-end; Docker Desktop acceso):
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
Prova dell'editor in Chrome senza app: una pagina HTML con `<metamodel-editor lang="it">` in un `div` di 1200×760, il kit
inlineato in uno `<script>`, `ed.metamodel = <E.runtime_json(E.load(fixture))>`, `ed._allAttrs = true`,
`ed.behavior = <B.runtime_json(b, meta)>` con `requires`/`model` aggiunti a uno stato; selezione con
`ed._sel = {kind: "class", name: "Invitation"}; ed._render()`; dal pannello `panel.querySelector('[data-state="…"]')` e
`dispatchEvent(new MouseEvent("mouseenter"))`; righe in `ed.shadowRoot.querySelectorAll('.box[data-name="Invitation"] text')`.
Headless: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --virtual-time-budget=15000 --dump-dom file://…`
(con `fetch`/`requestAnimationFrame` l'output resta vuoto: usare `setTimeout` e tutto inline); reale: `python3 -m http.server`
e l'estensione, con la scheda visibile.
Sandbox: `cd ~/Documents/GitHub/modeler-sandbox && npm run db:start && PORT=3077 npm run dev` (se il DB è nuovo: `npm run db:reset`);
reinstallare il modellatore dal clone: `python3 plugins/modeler/scripts/modeler.py install ~/Documents/GitHub/modeler-sandbox --no-migration`.
Typecheck dei TSX del kit: cartella fuori dal repository con `npm i --legacy-peer-deps typescript @types/react react react-dom next`,
copia di `kit/next/*.tsx` in `src/`, stub di `@/lib/modeler/metamodel-actions` via `paths`, `tsc --noEmit`.
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (ultima voce: disegno e rinvii), `plugins/modeler/skills/notation/references/behavior-notation.md`
(Workflows, `model`), `plugins/modeler/scripts/metamodel/behavior.py` (`state_overlay`, `_check_state_model`, `refine`),
`plugins/modeler/scripts/metamodel/engine.py` (`_field_policy`, `_workflow`), `plugins/modeler/kit/metamodel-editor.js`
(`stateView`, `rowItems`, `_renderWorkflowPanel`).
