# Handoff — modellatore: diagramma del workflow con lo stato corrente nelle pagine di dettaglio
_Aggiornato: 2026-10-19 · branch `feat/modeler-workflow-tabs` (2 commit sopra `main` `7d6910b`, non pushati)_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Questa sessione: nelle app model-based la pagina di
dettaglio di un record di un'entità con workflow mostra un div con il diagramma degli stati e lo stato corrente
evidenziato, come pezzo riusabile del kit del modeler (provato nella sandbox).

## Stato
- `origin/main` è alla PR #19 (`7d6910b`, squash di `feat/modeler-workflow-hint`): **core 0.11.0, modeler 0.20.0**
  (PR #18 `a7ce9bd`: `<workflow-view>`; PR #19: `cli.workflow_hint` in `install`, hook di sessione e `reverse`, punto
  «Motore a mano» in `metamodel` §3b, riga nelle convenzioni, `help/harness-process.html` tracciato).
- Branch locale `feat/modeler-workflow-tabs` (seconda revisione delle note, da unire con `/core:ship`):
  `edd9131 feat(modeler): existing workflow view and <WorkflowView> live in tabs` + `878f428 chore(release): core 0.12.0,
  modeler 0.21.0`. Solo testo: skill `install` §4 (vista del workflow esistente e `<WorkflowView>` in due schede, quella
  esistente predefinita, scheda in `localStorage`, snippet `WorkflowTabs`), rimando in `metamodel` §4, riga nelle
  convenzioni (Lavoro sul codice); `NOTES.md` con la nota 2026-10-19 «due schede» in parte applicata (scartato il
  componente nel kit).
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
1. `/core:ship` del branch `feat/modeler-workflow-tabs` (push, PR, merge su conferma); poi sugli altri computer
   `claude plugin update core@iovino-harness modeler@iovino-harness` (0.12.0 / 0.21.0).
2. In order-management (modeler 0.20.0, `<WorkflowView>` in `/orders/[id]`): portare `StatePath` e diagramma nelle due
   schede come dice la skill `install` §4; `behavior.yaml` dell'Ordine se manca ancora (skill `metamodel` §3b).
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
