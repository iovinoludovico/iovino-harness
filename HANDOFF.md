# Handoff — harness review del 2026-10-21 unita in main: `requires` per stato, immagini del worker, zoom a pulsanti
_Aggiornato: 2026-10-21 · branch `main` (`0a9b9a9`, PR #29), albero pulito_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Questa sessione: revisione delle 4 note aperte
di `NOTES.md` con `/core:harness-review` (tutte chiuse), più la richiesta sull'editor web (zoom solo con pulsanti,
diagramma che riempie l'editor). Tutto rilasciato: **core 0.19.0, modeler 0.30.0** su `origin/main`.

## Stato
- Fatto (PR #29, squash di 6 commit):
  - `core:deploy` «2b. Immagini» (worker con stage proprio: `src/` intero o test import ↔ `COPY`, `docker build
    --target` prima del merge), flag di Watchtower `--include-restarting` (§4), Redeploy/Restart (§7), «Un solo
    container resta indietro» (§8); `core:ship` §2 e §5 (attesa che il worker riparta); riga Web di
    `conventions.md`; voce «Immagini» nel `code-reviewer`; riga in `modeler:install`.
  - Modeler `states.<key>.requires` (`behavior.py`: `STATE_KEYS`, `_check_requires`, `requires_tests`, `uses` kind
    `requires`, `diff`, colonna «Richiede» in `BEHAVIOR.md`, `engine_version`, `sql_view`; `engine.py`:
    `_requires`, `v_missing` in `perform_transition`, `missing`/`guard_ok` in `_available_transitions`, controllo
    nel trigger `<k>_workflow_guard` con errcode `23514`; kit: pannello degli stati, diff e lint JS,
    `behavior-view.tsx`; skill `behavior`, `metamodel`, `apply`, notazione, README).
  - `model:drift` segnala `RECORD_URL …` quando i testi usano `{{url}}` e il database non ha
    `public.record_url(text, uuid)` (`B.uses_url`, `D.has_record_url`, `cli.cmd_drift`).
  - Editor web: niente zoom con la rotella (scorre la pagina), pulsanti «+»/«−» accanto ad «Adatta», fit
    all'apertura e al ridimensionamento finché l'utente non zooma; `Layout.fitView`/`zoomView` pure; regola in
    `core:diagrams`.
  - `NOTES.md`: 2026-10-20 worker applicata; 2026-10-21 requires applicata (rinviati: rilevamento in `reverse`,
    annotazione «1 da <stato>» nel diagramma e in `<WorkflowView>`); 2026-10-19 link negli eventi chiusa (motore
    scartato); 2026-10-19 collezioni rinviata (primo progetto con `upper` finito). Nessuna nota aperta.
- Verificato: `python3 -m unittest discover -s tests` → 23 OK; `python3 -m unittest discover -s plugins/modeler/tests`
  → 104 OK (anche con `MODELER_PG` su Postgres 16 in Docker: `requires` fine a fine in `test_workflow_end_to_end`);
  `node --test` dei 4 file `.mjs` → 181 OK; `claude plugin validate .` OK; editor provato in Chrome (headless e
  reale, pagina di prova con il kit e la fixture `invitations`): fit all'apertura (k 0,683, margine 24), rotella
  senza effetto sulla vista e pagina che scorre, «+» ×1,25 attorno al centro, «−», «Adatta», refit a 900 px.
- Non committato: nulla (la cartella `help/` non è tracciata: decidere se versionarla o ignorarla).
- Plugin ricaricati in questa sessione (`/reload-plugins`: core 0.19.0, modeler 0.30.0).

## Decisioni
- `requires` è una chiave dello stato, non una guardia ripetuta né `lower: 1`: il metamodello resta `[0..1]`
  (`lower: 1` = dalla creazione); l'invariante nello stato vale solo per i campi singoli (una parte cancellata non
  è intercettabile dal trigger del container); nessuna ereditarietà fra stati (modello leggibile).
- `missing` compare in `_available_transitions` solo per le transizioni verso stati con `requires`, così i frammenti
  SQL del motore già testati restano uguali.
- `record_url` non viene generata dal motore: la mappa delle viste sostituite è dell'app (convenzione sui link ai
  record); il promemoria sta in `drift`, non in `validate` (un warning permanente sulla fixture avrebbe rotto
  7 test e disturbato ogni app con la funzione già definita).
- Zoom solo con pulsanti: la rotella sulla tela faceva zoom accidentale mentre si scorreva la pagina.

## Problemi aperti
- Un rilascio vero dal web (`modeler-release`, PR #28) e un run vero di `modeler-apply` restano non provati
  (servono order-management con i secrets e una proposta innocua); il costo per run (`total_cost_usd`) tara
  `MODELER_APPLY_BUDGET` (skill `install` §7).
- Ereditati: `psql` assente sul Mac (shim in «Per riprendere»); `model:pull`/`model:done` mai riusciti su un progetto
  cloud (formato di `supabase db query` da verificare al primo uso); `guard_harness_edit` solo Edit/Write.
- La prova in Chrome con la scheda in secondo piano dà la vista non adattata: i `requestAnimationFrame` sono sospesi
  finché la scheda non è visibile. Non è un difetto dell'editor, ma va ricordato quando si prova con l'estensione.

## Prossimi passi
1. Sugli altri computer: `claude plugin marketplace update iovino-harness && claude plugin update
   core@iovino-harness modeler@iovino-harness`.
2. In order-management: `/modeler:install` (0.30.0, segue da solo il punto 6 della skill), poi `/modeler:behavior`
   per portare in `behavior.yaml` i campi obbligatori per stato come `requires` (`supplier`, `cig`, `orderNumber`,
   `orderDate` da `ordered`; `rupAssistants` da `procurement`; `deliveryDate` da `delivered`): motore a mano, quindi
   `npm run model:behavior -- --format sql` dà i frammenti da riportare nelle clausole `unmet` e nel trigger, la mappa
   `STATE_REQUIRES` in TypeScript legge `behavior.json`; ridurre `CUSTOM(order-workflow)` in `docs/customizations.md`.
   Con questo si riprendono i rinvii della nota 2026-10-21 (annotazione «1 da <stato>» nel diagramma e in
   `<WorkflowView>`).
3. In order-management: `npm run model:drift` dopo l'aggiornamento: se segnala `RECORD_URL`, migrazione con
   `record_url(entity, id)` e le `<e>_json` che la usano (convenzione sui link, nota 2026-10-19).
4. Prova nella sandbox (`~/Documents/GitHub/modeler-sandbox`): reinstallare il kit (0.30.0), `requires: [assignee]`
   su uno stato di `Task`, `npm run model:validate`, `model:sync`, `model:engine -- --write`, migrazione locale,
   transizione bloccata e `update` rifiutato; in `/admin/model` la colonna «Richiede» e i pulsanti di zoom.
5. Facoltativo: typecheck dei TSX del kit (`behavior-view.tsx` con `requires`) come descritto sotto.

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
Prova dell'editor in Chrome senza app: una pagina HTML con `<metamodel-editor lang="it">` in un `div` di 1200×700,
il kit inlineato e `ed.metamodel = <runtime_json del metamodello>` (`E.runtime_json(E.load(fixture))`), servita con
`python3 -m http.server`; da JS si leggono `ed._view`, `ed._autoFit` e i pulsanti in `ed.shadowRoot.querySelectorAll(".bar button")`.
Sandbox: `cd ~/Documents/GitHub/modeler-sandbox && npm run db:start && PORT=3077 npm run dev` (se il DB è nuovo: `npm run db:reset`);
reinstallare il modellatore dal clone: `python3 plugins/modeler/scripts/modeler.py install ~/Documents/GitHub/modeler-sandbox --no-migration`.
Typecheck dei TSX del kit: cartella fuori dal repository con `npm i --legacy-peer-deps typescript @types/react react react-dom next`,
copia di `kit/next/*.tsx` in `src/`, stub di `@/lib/modeler/metamodel-actions` via `paths`, `tsc --noEmit`.
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (ultime due note), `plugins/modeler/scripts/metamodel/behavior.py`
(`_check_requires`, `requires_tests`, `sql_view`), `plugins/modeler/scripts/metamodel/engine.py` (`_requires`, `_workflow`),
`plugins/modeler/kit/metamodel-editor.js` (`fitView`, `zoomView`, `_zoom`, pannello degli stati), `plugins/core/skills/deploy/SKILL.md` (2b, §8).
