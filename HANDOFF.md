# Handoff — comportamento nel modellatore web e bus dei connettori (plugin modeler)
_Aggiornato: 2026-10-17 · branch `main` (PR #11 unita, `d2c3b6a`)_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`), installato con `./install.sh`. Questa sessione
è stata una `/core:harness-review`: le due note aperte di `NOTES.md` sono state applicate nel modeler, che ora mostra
il modello di comportamento (`behavior.yaml`) accanto alla struttura nel modellatore web e disegna un bus quando molte
classi puntano alla stessa.

## Stato
- `origin/main` è alla PR #11 (`d2c3b6a`, squash dei commit sotto): **core 0.9.1, modeler 0.14.0**. Nessun branch remoto aperto.
- La PR #11 ha portato (release `1a50ab3`, **modeler 0.14.0**):
  - `cbe096d` comportamento nel modellatore web: l'editor (`plugins/modeler/kit/metamodel-editor.js`) accetta la
    proprietà `behavior` (`src/lib/modeler/behavior.json`): attributi derivati `/nome` con formula nel tooltip e nel
    pannello, attributo di stato `⟳` con conteggio di stati e transizioni, transizioni nel pannello, evento `select`
    (`Layout.rowItems`, puro, testato). Nuova `kit/next/behavior-view.tsx` (installata in
    `src/components/modeler/`): ruoli, workflow con stati e transizioni, derivazioni, eventi, reazioni,
    sottoscrizioni in sola lettura sotto l'editor, classe selezionata evidenziata. Prop opzionale `behavior` del
    wrapper, import documentato (commentato) in `kit/next/page.tsx`, `cli.behavior_page_hint` stampato da `install`
    quando `behavior.yaml` c'è e la pagina admin non passa `behavior=`.
  - `c2713d8` bus: da 4 riferimenti semplici che entrano nello stesso lato di una classe, una porta e una freccia,
    tronco a `BUS_GAP` dal lato, un ramo per sorgente (`branchRoute`), punti di giunzione, una sola etichetta se i
    riferimenti si leggono uguali; gli altri riferimenti verso quella classe si uniscono al bus se il ramo non
    attraversa box. Nel risultato di `routeEdges` un bus è un edge con `pts` (stub), `trunk`, `branches`.
  - `686bcdb` `NOTES.md`: nota del 2026-10-17 in parte applicata, nota del 2026-10-14 (bus) applicata.
- Verificato (2026-10-17, su `1a50ab3`):
  - `python3 -m unittest discover -s tests` → 23 OK
  - `python3 -m unittest discover -s plugins/modeler/tests` → 91 OK (8 skip senza `MODELER_PG`)
  - `node --test plugins/modeler/tests/layout.test.mjs plugins/modeler/tests/diff.test.mjs plugins/modeler/tests/lint.test.mjs`
    → 134 pass, 0 todo (hub(8) a ogni dimensione: un bus di 8, una freccia, un'etichetta)
  - typecheck di `metamodel-modeler.tsx` e `behavior-view.tsx` con `tsc` (strict, stub di `metamodel-actions`) → ok
  - `claude plugin validate .` → passed; `python3 scripts/release.py` → fatto (`--write`, modeler 0.14.0)
- Non committato: nulla.

## Decisioni
- Il comportamento nel web è **solo lettura**: le proposte dal modellatore restano sul metamodello; `behavior.yaml`
  si modifica con `/modeler:metamodel`. Prima si vede, poi si deciderà se proporre modifiche dal web.
- Gli stati del workflow sono una **tabella**, non un diagramma: il diagramma degli stati in SVG (layout puro e
  testato, regole `core:diagrams`) è rinviato, registrato come "Da fare" nella nota del 2026-10-17.
- Il flag `derived` (prefisso `/`) viene dal metamodello, quindi si vede anche senza `behavior.json`; la formula
  arriva dal behavior, altrimenti "calcolato nel codice", come in `docs/BEHAVIOR.md`.
- La pagina admin è dell'app: `install` non la riscrive, stampa l'avviso (`behavior.yaml found: …`) finché non
  passa `behavior=` nel JSX (regex su `<MetamodelModeler … behavior=`, non sul testo, perché il template lo cita
  in un commento).
- Bus: etichetta unica solo se tutti i riferimenti si leggono uguali (nome e molteplicità), altrimenti una
  etichetta per sorgente alla porta di uscita; bus instradati prima dei connettori singoli.

## Problemi aperti
- Il repository non ha CI (`.github/workflows` assente): i controlli sono quelli locali. `gh` 2.102 è installato
  e autenticato (account iovinoludovico): `/core:ship` funziona da qui.
- La vista del comportamento e il bus non sono ancora stati visti in un'app reale (solo test di layout e tsc):
  da controllare in guest-invitations-af dopo `/modeler:install` (0.14.0), con `behavior.yaml` e la pagina che passa
  `behavior={behavior}`.
- Ereditati, ancora validi: il motore generato (`model:engine`) non provato su un'app reale; `test_behavior.py` e
  `test_modeler.py` con `MODELER_PG` richiedono `psql` sul PATH (shim in «Per riprendere»); `model:pull`/`model:done
  --write` mai riusciti su un progetto cloud reale (`fe_sendauth: no password supplied`, manca la riga del pooler in
  `~/.pgpass`); `guard_harness_edit` copre solo Edit/Write; `docs/DOMAIN.md` non visto in anteprima GitHub; parte app
  della nota sulle viste sostituite in guest-invitations-af (`listHref` o redirect `/e/economic_rate` → `/x/economic_rate`).
- `NOTES.md`: nessuna nota da valutare; la nota del 2026-10-17 è in parte applicata (resta il diagramma degli stati
  grafico e le proposte sul behavior dal web).

## Prossimi passi
1. Sugli altri computer `claude plugin update modeler@iovino-harness` (0.14.0).
2. In guest-invitations-af: `/reload-plugins`, `/modeler:install` (barra dell'editor `v0.14.0`); se manca,
   `behavior.yaml` da `plugins/modeler/tests/fixtures/invitations.behavior.yaml` e `derived: true` sugli attributi
   calcolati; nella pagina admin togliere il commento a `import behavior from "@/lib/modeler/behavior.json"` e passare
   `behavior={behavior}`; aprire `/admin/model` e controllare `/attributi`, `⟳ state`, la sezione sotto l'editor e
   l'evidenziazione selezionando `Invitation`.
3. Sempre lì: `npm run model:validate`, `npm run model:sync`, `npm run model:behavior -- --format sql` contro le
   clausole in produzione, `npm run model:drift`; poi il motore (`npm run model:engine -- --write`,
   `supabase db reset`, test dell'app).
4. In order-management: `/modeler:install` e verifica del bus sui 10 riferimenti verso la stessa classe (etichette,
   nessun tratto sovrapposto); poi `/core:security-audit` e `docs/deploy.md` allineato a `core:deploy`.
5. Quando torna utile: diagramma degli stati in SVG nella `behavior-view` (nota 2026-10-17, "Da fare").

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test senza database: `python3 -m unittest discover -s tests && python3 -m unittest discover -s plugins/modeler/tests && node --test plugins/modeler/tests/layout.test.mjs plugins/modeler/tests/diff.test.mjs plugins/modeler/tests/lint.test.mjs && claude plugin validate .`
Test con database (anche il motore end-to-end):
```bash
docker run -d --rm --name modeler-pg-test -e POSTGRES_PASSWORD=pg -p 55499:5432 postgres:16
# senza psql locale: shim in una cartella sul PATH
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
Typecheck dei TSX del kit (fuori dal repository): cartella con `npm i --legacy-peer-deps typescript @types/react react react-dom next`,
copia di `kit/next/metamodel-modeler.tsx` e `behavior-view.tsx` in `src/`, stub di `@/lib/modeler/metamodel-actions`
(`PendingProposal`, `listMetamodelProposals`, `rejectMetamodelProposal`) via `paths`, `tsc --noEmit`.
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (ultime due note), `plugins/modeler/kit/metamodel-editor.js`
(`rowItems`, `branchRoute`, `routeEdges`, `_behaviorPanel`), `plugins/modeler/kit/next/behavior-view.tsx`,
`plugins/modeler/kit/next/metamodel-modeler.tsx`, `plugins/modeler/scripts/metamodel/cli.py` (`behavior_page_hint`,
`install`), `plugins/modeler/tests/layout.test.mjs` (test del bus e dei marcatori), `plugins/modeler/skills/install/SKILL.md` (§3, §4).
