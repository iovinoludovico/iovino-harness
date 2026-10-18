# Handoff — workflow nel modellatore (pannello in basso, livelli di coinvolgimento) e sandbox eseguibile
_Aggiornato: 2026-10-18 · branch `main` (PR #14 unita, `c4998fd`)_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Questa sessione: (1) la sandbox
`~/Documents/GitHub/modeler-sandbox` è diventata un sistema eseguibile (PostgreSQL in Docker con schema e motore
generati, UI generica dai due modelli) per provare dominio e cambi di stato in piccolo; (2) nel modellatore il
workflow è disegnato accanto alla classe (satellite «workflow») e il diagramma distingue le classi con workflow,
quelle coinvolte dal comportamento e quelle solo strutturali.

## Stato
- `origin/main` è alla PR #14 (`c4998fd`): **core 0.9.3, modeler 0.16.0**. Nessun branch remoto aperto.
- La PR #14 (release modeler 0.16.0, core 0.9.3) sposta il diagramma degli stati dal satellite nella tela a un **pannello sotto la tela** che segue la selezione (compare selezionando una classe con workflow, sparisce altrimenti), con le larghezze del testo misurate su un canvas 2D (`workflowLayout(..., {measure})`, `wfWrap` a misura, spazio per la parola più lunga): le etichette restano dentro le forme. Rimossi satelliti, ingombro/ostacolo e toggle; `routeEdges(mm, size, {uses})`. Test: etichette dentro il diagramma e larghe quanto il testo misurato.
- La PR #13 aveva portato (release `95866f8` modeler 0.15.0, `112ecf8` core 0.9.2):
  - `6b8e061` fix: `<entity>_available_transitions` restituiva righe avvolte in `{"jsonb_build_object": …}`; ora un array di oggetti (`engine.py`, test del testo SQL).
  - `5d30f7d` `uses` in `behavior.json`: `expr.py` annota ogni passo di un path con la classe proprietaria (`hops`, `hops_used`); `behavior.uses(b, e)` → `{Class: {attributes, references, class: [{kind, of}]}}` (derivation, when, guard, at, by, owner, editable_by, revert, notify, scope); `BEHAVIOR.md` ha «Classi coinvolte nel comportamento». Test `test_uses`.
  - `f1c7613` editor (`kit/metamodel-editor.js`): `Layout.workflowLayout` (porting di `workflow-layout.ts` + `state-path.ts` di invitations-af), `workflowModel`, `satelliteOf`/`satRect`/`footSize`/`satObstacle`, `routeEdges(mm, size, {extra, uses})`, `FRACS` (tratto centrale delle Z a più frazioni), testata «workflow» (`STEREO_H`), marcatori ` ·ƒ`/`ƒ`, legenda, toggle `⟳ Workflow`, satellite trascinabile con la classe, hover `wf:<Class>:<transition>`. `behavior-view.tsx`: tabella «Classi coinvolte». Test: `workflowLayout` su invitations (11 stati, bus `cancel`, `visit_ended` a tempo) e su 4 stati; satellite in tela; righe marcate.
  - `fc169c2` `NOTES.md`: nota 2026-10-17 (behaviour nel web) completata salvo le proposte dal web; nuova nota sul limite del layout masonry.
  - `fbc76d5` skill `core:diagrams`: il riferimento d'implementazione è anche `Layout.workflowLayout`.
- Sandbox (`~/Documents/GitHub/modeler-sandbox`, 6 commit, non ha remoto): `db/bootstrap.sql`, `db/seed.sql`, `scripts/db.sh` (container `modeler-sandbox-pg`, 127.0.0.1:55432, `db:start|reset|migrate|engine|seed|psql`), `src/lib/db` (`pool`, `withUser` → `set_config('app.profile_id')`, `dbError`), `src/lib/model` (naming del plugin, `ClassDef`/`FieldDef`, query), pagine `/e/[entity]` (lista, dettaglio con transizioni/revert/storia/eventi, nuovo, modifica), `/events`, `/scheduler`, selettore «agisci come», home e README. Modeler installato 0.15.0.
- Verificato (2026-10-17):
  - harness: `unittest` core 23 OK, modeler 92 OK (8 skip senza `MODELER_PG`); `node --test` 138 pass; `tsc` sui TSX del kit ok; `claude plugin validate .` passed.
  - sandbox: `tsc --noEmit` e `lint` puliti; scenario end-to-end eseguito (UI + psql): guardia `ready`, permessi per ruolo/assegnatario, destinatari delle reazioni (manager all'avvio, owner al completamento), commento obbligatorio, `expire` a tempo con `task.expired`, reminder dopo invecchiamento, revert, blocco dell'update diretto dello stato.
  - browser su `/admin/model`: satellite sotto `Task` (todo→doing→done, `expire` tratteggiata ⏱, `cancelled`), `ƒ` su `Project`, ` ·ƒ` su `tasks 0..*`, legenda, toggle, hover.
- Non committato: nulla.

## Decisioni
- Satellite derivato dalla posizione della classe, mai salvato in `mm.diagram`: `domain.ecore.yaml` resta pulito.
- `uses` calcolato in Python (conosce la semantica delle espressioni); il JS lo legge soltanto.
- Satellite compatto: le tabelle sotto l'editor restano per owner, reminder, chi e guardie.
- Sandbox senza Supabase: Postgres nudo in Docker, utente corrente da cookie → `app.profile_id` (il fallback del motore); la connessione superuser bypassa RLS (detto nel README).
- Il bug del layout masonry su modelli grandi non è stato affrontato qui: nota in `NOTES.md`, test del satellite limitato alle sue invarianti.

## Problemi aperti
- Layout masonry: sul fixture `invitations.ecore.yaml` 22 dimensioni su 39 hanno un connettore che attraversa una classe, anche senza satelliti (nota 2026-10-17 in `NOTES.md`; script di misura: `tests/` non ancora, vedi la nota).
- Proposte sul `behavior.yaml` dal modellatore web: non ancora fatte (resto della nota 2026-10-17).
- Ereditati: motore generato non provato su un'app vera (la sandbox sì); `psql` assente sul Mac (shim in «Per riprendere»); `model:pull`/`model:done` mai riusciti su un progetto cloud; `guard_harness_edit` solo Edit/Write.

## Prossimi passi
1. Sugli altri computer `claude plugin update modeler@iovino-harness` (0.16.0) e `core@iovino-harness` (0.9.3).
2. Nella sandbox: provare lo scenario dalla UI con i quattro utenti (README «Scenario da provare»); modificare `behavior.yaml` (es. nuovo stato o reazione), `npm run model:sync && npm run model:engine -- --write && npm run db:engine` e vedere satellite, tabelle e motore seguire.
3. In invitations-af: `/modeler:install` (0.15.0), passare `behavior={behavior}` nella pagina admin e guardare il satellite a 11 stati su un'app vera.
4. Nota sul layout masonry: misurare e intervenire su `autoLayout`/router (vedi `NOTES.md`).
5. Proposte sul comportamento dal web (resto della nota 2026-10-17).

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
