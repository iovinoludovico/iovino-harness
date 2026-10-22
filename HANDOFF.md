# Handoff — i ruoli e gli utenti nel diagramma del modellatore (PR #36), lint del kit (PR #35)
_Aggiornato: 2026-10-22 · branch `main` (`2cb499f`, PR #36), albero pulito_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Dopo le revisioni del 2026-10-21 (notifiche sulla
transizione, ruoli nel metamodello: PR #34, modeler 0.35.0) oggi sono entrate su `main` la pulizia del lint del kit
(PR #35, modeler 0.35.1) e i riquadri predefiniti `Role «enumeration»` e `User «built-in»` nel diagramma del
modellatore web (PR #36, modeler 0.36.0). `NOTES.md`: 0 note aperte, 1 rinviata (massimo finito delle collezioni,
nessun progetto lo richiede).

## Stato
- Fatto (PR #35, `4299db8`): nessun `eslint-disable` nel kit (`delete rest.source` al posto del rest con binding inutile);
  test `lint.test.mjs` «the kit silences no lint rule», eccezione `no-namespace` nei TSX.
- Fatto (PR #36, `2cb499f`, nota del 2026-10-22): quando il metamodello ha `roles:` o una reference `role: true`, il
  kit `metamodel-editor.js` disegna `Role «enumeration»` (`admin` primo, scope come `director (Department)`) e
  `User «built-in»` (riga `email`, bordo tratteggiato, CSS `.box.builtin`), uniti da `roles 0..*`. Una reference
  `role: true` è un connettore classe → `User` (molteplicità, overlay di stato, ` ·ƒ` sull'etichetta) e non più una riga;
  le altre reference a `User` (`createdBy`) restano righe attenuate. Helper puri in `Layout`: `recordRoles`,
  `builtinNodes`, `nodeNames`, `roleLiterals`, costanti `USER`/`ROLE`/`ADMIN`; `boxSize`, `autoLayout` (`near`:
  `User` vicino alle classi con ruoli di record, `Role` vicino a `User`), `edgesOf` (gate su `builtinNodes`, così un
  `diagram.User` stantio non disegna nulla), `routeEdges` e i filtri dell'editor (`_freeSpot`, `_fit`, `_separate`)
  usano `nodeNames`; `_renderDiagram` dà una posizione ai box predefiniti che compaiono dopo un edit; `_anchor`/`_center`
  (senza chiamanti) rimossi; `_renameClass` aggiorna gli `scope` dei ruoli. Selezione: kind `user`/`roles`
  (`SelectDetail` del wrapper TSX), clic su `Role` → `_rolesPanel()` (estratto da `_globalBehaviorPanel`), su `User` →
  ruoli e ruoli di record; i18n `builtinHint`, `builtinName`, `select`. `Role` riservato come `User`: editor
  (`_allNames`, `_issues`) e `ecore.py` (`BUILTIN_ENUMS`, `validate` su classi ed enum, `runtime_json.builtin_enums`);
  `to_mermaid` disegna `Role`/`User` anche con soli ruoli di record. Docs: `ecore-notation.md` «Roles», README del
  modeler, skill `metamodel` §3.
- Verificato: `node --test plugins/modeler/tests/*.mjs` → 184 OK (nuovo test «built-in User and Role boxes» a 400×480,
  1280×720, 1900×900 con `checkDiagram`; conteggio dei box e righe aggiornati); `python3 -m unittest discover -s
  plugins/modeler/tests` → 114 OK, 9 saltati (container Postgres spento, nessuna modifica SQL); `tests` → 23 OK;
  `claude plugin validate .` OK; Chrome headless sulla fixture invitations a 1200×760 e 480×640: box, connettori
  `Invitation.issuer` e `User.roles`, pannelli laterali, zero problemi. Nessuna CI nel repository.
- Non committato: nulla. Questa sessione gira con core 0.21.0 e modeler 0.35.1 in cache (`/reload-plugins` per 0.36.0).

## Decisioni
- **Box `Role` e `User` nel diagramma** (ribalta la scelta del 2026-10-21) — i ruoli sono un enum come gli altri e Mermaid,
  Emfatic e XMI già li disegnavano: il modellatore web mostrava meno di `DOMAIN.md`. Solo quando il metamodello ha
  ruoli o ruoli di record: le app senza ruoli non cambiano.
- **Ruolo di record = connettore, non riga** — nessuna reference classe→classe è insieme riga e connettore; il box si
  accorcia; la vista per stato (🔒/hidden al passaggio del mouse) non si applica più a quella reference: accettato.
- **`createdBy` e le altre reference a `User` restano righe** — un box `User` collegato a tutte le classi sporcherebbe
  il diagramma (Mermaid invece le disegna tutte: differenza voluta).
- Ruoli come **enum di chiavi** (`roles:` → `app_role`), non classe con righe; memorizzazione uguale ad appforge.
- La notifica di una transizione è una **reazione sintetica** in `expand`; `validate` non suggerisce la forma breve.
- Nessuna pagina utenti nel kit — `/admin/users` è dell'app.
- (Ereditate) creazione in modale come convenzione più ricetta, non componente del kit; overlay per stato: transizione
  morta = errore, parziale = avviso; «vedi come» dichiarato nel modello, mai una sessione dell'altro utente.

## Problemi aperti
- order-management ha già i ruoli nel metamodello (`roles:` rup, rup_assistant, area_director per Department; `role:
  true` su `Fund.manager` e `Order.rupAssistants`; notifiche in forma breve; modeler 0.35.1 con le PR #24/#25
  dell'app). Restano: `/modeler:install` per la 0.36.0 (i due box compaiono con i connettori `Fund.manager` e
  `Order.rupAssistants`), la prova nel browser di `/admin/model` (tabella «Ruoli», box `Role`/`User`, ✉ sulle frecce),
  `view_as: {users_by: [admin]}` al posto di `CUSTOM(view-as)`; «+ Nuovo» in modale solo per il fornitore (CPV, fondo e
  COAN sono registri dell'amministratore).
- Nessun progetto usa ancora `states.<key>.model`: la sandbox e order-management sono la prova.
- Editor: la select dei template con «+ nuovo» nel pannello della transizione è un campo di testo; la colonna «Modello»
  è in sola lettura; `MAX_ROWS` non si applica al box `Role` (con molti ruoli cresce, come gli enum).
- Nello screenshot headless a 1200×760 il diagramma adattato tocca il bordo inferiore (la legenda copre l'ultima riga):
  comportamento di `fitView` preesistente in headless, da verificare con l'estensione a scheda visibile.
- Un controllo automatico di «view as» in `security-audit` B resta manuale.
- Ereditati: un rilascio vero dal web (`modeler-release`) e un run vero di `modeler-apply` non provati; `psql` assente
  sul Mac (shim in «Per riprendere»); `model:pull`/`model:done` mai riusciti su un progetto cloud;
  `guard_harness_edit` solo Edit/Write; la cartella `help/` non è tracciata (decidere se versionarla o ignorarla).

## Prossimi passi
1. Qui: `/reload-plugins`. Sugli altri computer: `claude plugin marketplace update iovino-harness && claude plugin
   update core@iovino-harness modeler@iovino-harness`.
2. In order-management: `/modeler:install` (0.36.0), poi `/admin/model` in locale (login via Mailpit): box `Role` con
   `rup`, `rup_assistant`, `area_director (Department)`, box `User`, connettori `manager 1` da `Fund` e
   `rupAssistants 0..*` da `Order`, clic su `Role` → tabella «Ruoli»; `npm run lint` pulito; screenshot da conservare.
3. In order-management: `view_as: {users_by: [admin]}` con `/modeler:behavior` (SQL del motore 0.33 al posto di
   `CUSTOM(view-as)`), «+ Nuovo» per il fornitore con la ricetta della skill `metamodel` §4; poi i campi per stato come
   `requires`/`model` (vedi HANDOFF dell'app, punto 3).
4. Sandbox (`~/Documents/GitHub/modeler-sandbox`): reinstallare il kit (0.36.0), `roles:` nel metamodello con
   `npm run model:migrate`, `notify` su una transizione di `Task`, `view_as` end-to-end, `model: {assignee: {lower: 1,
   readonly: true}}` su uno stato.
5. Quando il caso degli ordini è in produzione: rileggere `docs/research/state-indexed-refinement.md` §6–§7 e decidere
   se diventa l'articolo (repository a parte) o resta la specifica del plugin.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test senza database: `python3 -m unittest discover -s tests && python3 -m unittest discover -s plugins/modeler/tests && node --test plugins/modeler/tests/*.mjs && claude plugin validate .`
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
inlineato in uno `<script>`, `ed.metamodel = <E.runtime_json(E.load(fixture))>`, `ed.behavior = <B.runtime_json(b, meta)>`
dentro un `setTimeout`; i box predefiniti sono `g.box.builtin[data-name=User|Role]`, i connettori `[data-edge="User.roles"]`
e `[data-edge="Invitation.issuer"]`; pannelli con `ed._sel = {kind: "roles", name: "Role"}; ed._render()` (o `kind: "user"`);
la ✉ delle transizioni è `text.wfn[data-notifies]` nel pannello del workflow.
Headless: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --virtual-time-budget=8000 --window-size=1200,760 --screenshot=out.png file://…`
e `--dump-dom` (con `fetch`/`requestAnimationFrame` l'output resta vuoto: usare `setTimeout` e tutto inline, scrivere il
risultato in un `<pre>`); reale: `python3 -m http.server` e l'estensione, con la scheda visibile.
Sandbox: `cd ~/Documents/GitHub/modeler-sandbox && npm run db:start && PORT=3077 npm run dev` (se il DB è nuovo: `npm run db:reset`);
reinstallare il modellatore dal clone: `python3 plugins/modeler/scripts/modeler.py install ~/Documents/GitHub/modeler-sandbox --no-migration`.
Typecheck dei TSX del kit: cartella fuori dal repository con `npm i --legacy-peer-deps typescript @types/react react react-dom next`,
copia di `kit/next/*.tsx` in `src/`, stub di `@/lib/modeler/metamodel-actions` via `paths`, `tsc --noEmit`.
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (ultime due voci), `plugins/modeler/skills/notation/references/ecore-notation.md`
(«Roles»), `plugins/modeler/kit/metamodel-editor.js` (`recordRoles`/`builtinNodes`/`nodeNames`/`roleLiterals` in cima a
`Layout`, `boxSize`, `autoLayout`, `edgesOf`, il ciclo dei box predefiniti in `_renderDiagram`, `_renderSide`,
`_rolesPanel`), `plugins/modeler/tests/layout.test.mjs` (ultimo test), `plugins/modeler/scripts/metamodel/ecore.py`
(`BUILTIN_ENUMS`, `validate`, `to_mermaid`), `plugins/modeler/scripts/metamodel/behavior.py` (`expand`, `bind`).
