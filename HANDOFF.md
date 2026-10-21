# Handoff — overlay per stato formalizzato (`docs/research/`) e `validate` allineato
_Aggiornato: 2026-10-21 (notte) · branch `main` (`b240dff`, PR #31), albero pulito_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Terza revisione delle note del 2026-10-21: la
nota «Formalizzare l'overlay per stato» è applicata per intero: il disegno di `states.<key>.model` (modeler 0.31.0)
ha ora definizioni, proprietà e confronto con la letteratura in `docs/research/state-indexed-refinement.md`, e
`validate` è stato corretto dove si discostava dalla teoria. Rilasciato: **core 0.19.1, modeler 0.32.0** su
`origin/main`. `NOTES.md`: 0 note aperte, 1 rinviata (collezioni con `upper` finito, nessun progetto la richiede).

## Stato
- Fatto (PR #31, squash di 3 commit):
  - `docs/research/state-indexed-refinement.md` (nuova cartella, in inglese, bozza di articolo): §2 definizioni
    (`MM`, `W = (S, s₀, Sf, T, σ)`, overlay `O_s`, `MM_s = apply(MM, O_s)`, ordine `⊑`, conformità dinamica
    `i ⊨ MM_σ(i)`, update nello stato e transizione come migrazione verificata senza payload); §3 proprietà P1
    conservazione, P2 correttezza del motore con le eccezioni E1 (collezioni solo in ingresso), E2 (readonly/hidden
    sulle collezioni), E3 (derivate), E4 (colonna di stato e `app.in_transition`), P3 coerenza di cammino con gli
    insiemi `ok_s(f)`/`Poss_s(f)`, transizione morta e parziale, verifica a un passo corretta ma non completa; §4
    confronto (OCL con implicazione sullo stato, xDSML/GEMOC/xMOF, typestate, Fickle/ruoli, co-evoluzione,
    models@runtime); §5 tabella definizione → funzione → test; §6 revisione del codice; §7 questioni aperte.
  - `behavior.py` `_check_state_model`, blocco «along the path»: una transizione con `in` disgiunti fra sorgente e
    destinazione (attributo richiesto in una delle due, `lower` statico incluso) è un **errore** «'f' is a, b in
    <src> but <tgt> allows only c: `t` can never fire», in entrambe le direzioni e indipendentemente da `readonly`
    (prima: avviso solo con `readonly`); le transizioni parziali (sorgente `readonly` che ammette più della
    destinazione) restano avvisi; il suggerimento è «require it before <src> or let <src> change it» (il vecchio «set
    it in the transition» era irrealizzabile: `<e>_perform_transition` aggiorna solo la colonna di stato). Le feature
    derivate sono escluse dal controllo di cammino. Notazione aggiornata (`behavior-notation.md`, bullet `model` e
    «What the check reports»); test `test_state_model_the_class_as_seen_from_a_state` esteso (`confirm_bookings` e
    `rebook` morte, caso con l'attributo facoltativo in entrambi gli stati: nessun errore).
  - `README.md`: riga su `docs/research/`. `NOTES.md`: nota chiusa con il dettaglio.
- Verificato: `python3 -m unittest discover -s tests` → 23 OK; `python3 -m unittest discover -s plugins/modeler/tests`
  → 106 OK, anche con `MODELER_PG` su Postgres 16 in Docker; `node --test` dei 4 `.mjs` → 182 OK;
  `claude plugin validate .` OK. Nessuna CI nel repository.
- Non committato: nulla. Questa sessione gira con core 0.19.0 in cache (`/reload-plugins` per 0.19.1 e modeler 0.32.0).

## Decisioni
- Documento nell'harness, non in un repository dell'articolo — è la specifica del plugin: la tabella del §5 lega ogni
  definizione a una funzione e a un test, e va aggiornata insieme al codice.
- `hidden` resta nella relazione di conformità (feature congelata, valore conservato); `refine` la toglie solo nella
  **vista** (`model:show --state`) — serve per dimostrare P1 senza proiezioni; nessun cambio al codice.
- Transizione morta = errore, parziale = avviso — morta è decidibile dagli overlay (gli insiemi ammessi sono
  disgiunti); parziale dipende dai dati (quali istanze sono entrate nello stato sorgente).
- Verifica di cammino a un passo, non a punto fisso — `ok_s(f)` è un limite superiore corretto di `Poss_s(f)`; il
  punto fisso lungo catene `readonly` scoprirebbe più transizioni morte ma non è richiesto da nessun caso reale.
- Collezioni (E1): invariante mantenuto solo in ingresso — imporlo richiede un trigger sulla tabella delle parti,
  lo stesso della nota rinviata sul massimo delle collezioni; si fa quando un progetto lo chiede.

## Problemi aperti
- Nessun progetto usa ancora `model`: `field_policy` e i form per stato sono da provare su order-management
  (`STATE_REQUIRES`/`STATE_EDITORS` scritti a mano) e nella sandbox; il caso reale è la prova del disegno (§7).
- Lavoro futuro del documento (§7): struttura aggiunta per stato (romperebbe P1), payload delle transizioni (`set:`),
  invarianti sulle collezioni, analisi a punto fisso, guardie ignorate dal controllo di cammino.
- Ereditati: un rilascio vero dal web (`modeler-release`, PR #28) e un run vero di `modeler-apply` non provati;
  `psql` assente sul Mac (shim in «Per riprendere»); `model:pull`/`model:done` mai riusciti su un progetto cloud;
  `guard_harness_edit` solo Edit/Write; la cartella `help/` non è tracciata (decidere se versionarla o ignorarla);
  editing dell'overlay dal modellatore web rinviato (colonna «Modello» in sola lettura).
- Prova in Chrome con l'estensione: con la scheda in secondo piano i `requestAnimationFrame` sono sospesi; un metodo
  nuovo dell'elemento non può chiamarsi `_view` (è la vista della tela).

## Prossimi passi
1. Qui: `/reload-plugins`. Sugli altri computer: `claude plugin marketplace update iovino-harness && claude plugin
   update core@iovino-harness modeler@iovino-harness`.
2. In order-management: `/modeler:install` (0.32.0), poi `/modeler:behavior` per portare in `behavior.yaml` i campi
   per stato come `requires`/`model` (`supplier`, `cig`, `orderNumber`, `orderDate` da `ordered`, con `readonly` dopo
   l'ordine; `rupAssistants` da `procurement`; `deliveryDate` da `delivered`); motore a mano: i frammenti da
   `npm run model:behavior -- --format sql`, `field_policy` scritta a mano sullo stesso schema, i form leggono
   `order_field_policy(record)` e spariscono `STATE_REQUIRES`/`STATE_EDITORS`; `CUSTOM(order-workflow)` ridotta in
   `docs/customizations.md`; `npm run model:sync` (DOMAIN.md con «1 da In istruttoria»). Poi annotare nel §7 del
   documento cosa il caso ha confermato o cambiato.
3. Prova nella sandbox (`~/Documents/GitHub/modeler-sandbox`): reinstallare il kit (0.32.0), `model: {assignee:
   {lower: 1, readonly: true}, notes: {hidden: true}}` su uno stato di `Task`, `npm run model:validate`, `model:sync`,
   `model:engine -- --write`, migrazione locale, update rifiutato nello stato, `select task_field_policy(t) from
   tasks t`; in `/admin/model` la colonna «Modello» e l'hover sugli stati; una coppia di stati con `in` disgiunti
   per vedere l'errore «can never fire».
4. Facoltativo: typecheck dei TSX del kit (`behavior-view.tsx` con `Overlay`) come descritto sotto.
5. Quando il caso degli ordini è in produzione: rileggere `docs/research/state-indexed-refinement.md` §6–§7 e
   decidere se diventa l'articolo (repository a parte) o resta la specifica del plugin.

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
File da leggere per primi: `CLAUDE.md`, `docs/research/state-indexed-refinement.md` (§2 definizioni, §5 mappa sul codice, §7 aperto),
`NOTES.md` (ultime due voci), `plugins/modeler/skills/notation/references/behavior-notation.md` (Workflows, `model`),
`plugins/modeler/scripts/metamodel/behavior.py` (`state_overlay`, `_check_state_model`, `refine`),
`plugins/modeler/scripts/metamodel/engine.py` (`_field_policy`, `_workflow`).
