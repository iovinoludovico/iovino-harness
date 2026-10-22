# Handoff — tema del diagramma dalla pagina, busta e destinatari con le etichette, `/core:release` (PR #38)
_Aggiornato: 2026-10-22 · branch `main` (`cc7f807`, PR #38), albero pulito_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Oggi sono entrate su `main` tre revisioni delle
note dell'harness: i riquadri predefiniti `Role «enumeration»` e `User «built-in»` nel diagramma (PR #36, modeler
0.36.0), la notazione EMF unica per gli attributi tipati con un enum e il diff del kit indipendente dall'ordine delle
chiavi di `jsonb` (PR #37, 0.36.1), e infine il tema dei due elementi del kit preso dalla pagina invece che dal sistema,
la busta delle notifiche come `<path>` con i destinatari etichettati e la skill `/core:release` (PR #38: core 0.22.0,
modeler 0.36.2). `NOTES.md`: 0 note aperte, 1 rinviata (massimo finito delle collezioni, nessun progetto lo richiede).

## Stato
- Fatto (PR #36, `2cb499f`): con `roles:` o una reference `role: true` il kit disegna `Role «enumeration»` (`admin`
  primo, scope come `director (Department)`) e `User «built-in»` (bordo tratteggiato, `.box.builtin`); un ruolo di record
  è un connettore classe → `User`, le altre reference a `User` (`createdBy`) restano righe. Helper puri in `Layout`:
  `recordRoles`, `builtinNodes`, `nodeNames`, `roleLiterals`, `userRows`; selezione `user`/`roles`, `_rolesPanel()`;
  `Role` riservato come `User` (editor e `ecore.py` `BUILTIN_ENUMS`); `to_mermaid` disegna i due box.
- Fatto (PR #37, `dc7ddcc`): `User` elenca `roles: Role [0..*]` come riga, senza connettore (notazione EMF, come
  `Order.state: OrderState`), nell'editor e in Mermaid; `stableJson`/`same` nel kit (chiavi ordinate, ricorsivo) per
  `diff` e `behaviorDiff`, così una proposta riletta da `model_change_requests` non mostra righe fasulle; «Salva» chiede
  conferma (`saveNoChanges`) quando la proposta non ha righe (solo posizioni, che `apply` scarta).
- Fatto (PR #38, `cc7f807`, nota del 2026-10-22 da order-management):
  - `Layout.pageTheme({dataTheme, htmlClass, colorScheme, bodyBg})` → `light|dark` (html `data-theme`, classe
    `dark`/`light`, `color-scheme` calcolato se uno solo, luminanza dello sfondo del `body` in rgb/oklch/hsl/lab/color(srgb),
    altrimenti `light`); `followPageTheme`/`stopPageTheme`/`themeAttrChanged` (fuori da `Layout`, dopo `textMeasure`):
    i due elementi impostano `theme` da soli in `connectedCallback` e lo aggiornano con un `MutationObserver` su `html`
    (`class`, `data-theme`, `style`) e `matchMedia` sul cambio di schema; un `theme` messo dall'app vince (prop `theme`
    su `<WorkflowView>` e `<MetamodelModeler>`); `hostCss` ha solo `:host` chiaro e `:host([theme="dark"])`.
  - Busta `<g class="wfn">` con `rect.wfn-hit` + `path.wfn-env` (`WF_ENV = {w: 12, h: 9}`), `tabindex`, `data-notifies`
    e `<title>`; `Layout.principalLabel(p, {roles, lang, texts, mm, cn})` (etichetta del ruolo, `t.principals` per
    `creator`/`admin`, `self.a.b` → etichette delle feature unite da ` › ` quando c'è il metamodello, altrimenti com'è);
    `workflowModel(w, lang, ctx)` mette `text` su ogni notifica; `notifyTips(listen, container, leave)` disegna
    `div.tip` (sullo shadow root per la vista, sul pannello per l'editor); `<workflow-view>` ha la proprietà `roles`
    (il wrapper passa `behavior.roles`); `_principalCtx(cn)` nell'editor; riga `.hint` con le etichette sotto l'input
    «Avvisa» della tabella delle transizioni.
  - `/core:release` (`plugins/core/skills/release/SKILL.md`): precondizioni (repo harness, albero pulito, branch ≠
    `main`), prova a vuoto, `--write`, niente push; README, `CLAUDE.md` e `harness-review` §5 la citano.
- Verificato: `node --test plugins/modeler/tests/*.mjs` → 187 OK (nuovi «pageTheme» e «principalLabel / workflowModel»);
  `python3 -m unittest discover -s plugins/modeler/tests` → 114 OK, 9 saltati (Postgres spento, nessuna modifica SQL);
  `-s tests` → 23 OK; `claude plugin validate .` OK; Chrome headless: pagina chiara → `light`, `html.dark`, `data-theme`
  e body scuro → `dark`, `theme` esplicito vince e tolto torna a seguire; 12 buste come path, nessun glifo di testo,
  tooltip «avvisa: Direttore di dipartimento (director_confirmation_requested)» nella vista e nel pannello, etichette
  nella tabella. Nessuna CI nel repository.
- Non committato: nulla. Questa sessione gira con core 0.21.0 e modeler 0.36.1 in cache (`/reload-plugins` per
  0.22.0/0.36.2).

## Decisioni
- **Tema nel kit, non nei wrapper** — una sola sede per i due elementi e per le pagine senza React; la luminanza dello
  sfondo del `body` copre anche Tailwind in modalità `media` (nessuna classe); `prefers-color-scheme` non decide mai:
  in assenza di segnali la pagina è chiara. L'app può forzare con la prop `theme`.
- **Tooltip disegnato solo per la busta** — i `<title>` nativi di `ƒ`/`·ƒ` restano: piccola incoerenza accettata, da
  rivedere insieme se serve. Il `<title>` della busta resta per l'accessibilità.
- **Le etichette non entrano nel modello** — `notify` tiene le chiavi (si editano); le etichette sono solo
  presentazione (`text` del `workflowModel`, riga `.hint` sotto l'input).
- **`/core:release` separata da `/core:ship`** — ship la include già; la skill serve per il solo commit di rilascio
  (senza push), e documenta le precondizioni.
- **Notazione EMF per `User.roles`** (PR #37) — un attributo tipato con un enum è una riga, mai un connettore; `Role`
  resta vicino a `User` nell'`autoLayout`.
- **Conferma al salvataggio senza righe** (PR #37) — `apply` scarta le posizioni: una proposta di sole posizioni resta
  aperta in produzione senza effetto.
- (Ereditate) box `Role`/`User` solo con ruoli nel metamodello; ruolo di record = connettore; `createdBy` riga; ruoli
  come enum di chiavi; notifica sulla transizione = reazione sintetica; creazione in modale per convenzione; overlay per
  stato; «vedi come» dichiarato nel modello.

## Problemi aperti
- order-management (modeler 0.36.1, PR #24/#25 dell'app, `CUSTOM(modeler-theme)` in `globals.css` come rimedio
  temporaneo): `/modeler:install` per 0.36.2, poi togliere `CUSTOM(modeler-theme)` e verificare `/orders/<id>` scheda
  «Diagramma» con il Mac in tema scuro e l'app in tema chiaro; `/admin/model`: box `Role`/`User`, buste e tooltip con
  «Direttore generale», «Responsabile del fondo» (il percorso `self.fund.manager` mostra `fund › manager` se le reference
  non hanno `label`: valutare se aggiungere le etichette nel metamodello). Restano `view_as: {users_by: [admin]}` al
  posto di `CUSTOM(view-as)` e «+ Nuovo» in modale per il fornitore.
- `principalLabel` di un `self.<ref>` senza `label` nel metamodello mostra il nome della reference; `<workflow-view>`
  (senza metamodello) mostra il percorso com'è.
- Headless: lo screenshot dell'editor senza altezza esplicita sull'elemento fa crescere il pannello del workflow
  (`wrapH * 0.5` su un host che cresce con il contenuto): nelle prove dare `style="height:…"` all'elemento, come fa il
  wrapper (`calc(100dvh - 12rem)`); non è un difetto nelle app.
- Nessun progetto usa ancora `states.<key>.model`; il `MAX_ROWS` non si applica al box `Role`; la select dei template
  nel pannello della transizione è un campo di testo.
- Ereditati: un rilascio vero dal web (`modeler-release`) e un run vero di `modeler-apply` non provati; `psql` assente
  sul Mac (shim in «Per riprendere»); `model:pull`/`model:done` mai riusciti su un progetto cloud;
  `guard_harness_edit` solo Edit/Write; la cartella `help/` non è tracciata.

## Prossimi passi
1. Qui: `/reload-plugins` (core 0.22.0, modeler 0.36.2). Sugli altri computer: `claude plugin marketplace update
   iovino-harness && claude plugin update core@iovino-harness modeler@iovino-harness`.
2. In order-management: `/modeler:install`, togliere `CUSTOM(modeler-theme)` da `globals.css`, `npm run lint`, prova nel
   browser di `/orders/<id>` (tema scuro del Mac, app chiara) e di `/admin/model` (box `Role`/`User`, busta, tooltip,
   riga delle etichette sotto «Avvisa»); se le etichette dei ruoli di record non bastano, `label` sulle reference
   `Fund.manager`/`Order.rupAssistants` con `/modeler:metamodel`.
3. In order-management: `view_as: {users_by: [admin]}` con `/modeler:behavior`, «+ Nuovo» per il fornitore (skill
   `metamodel` §4), poi i campi per stato come `requires`/`model`.
4. Sandbox (`~/Documents/GitHub/modeler-sandbox`): reinstallare il kit (0.36.2), `roles:` nel metamodello, `notify` su
   una transizione di `Task` con un ruolo etichettato, tema scuro/chiaro della pagina, `view_as` end-to-end.
5. Quando il caso degli ordini è in produzione: rileggere `docs/research/state-indexed-refinement.md` §6–§7.

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
Rilascio: `/core:release` (prova a vuoto, poi `--write`: versioni + commit `chore(release)`), poi `/core:ship` (push,
PR, merge su conferma; include il rilascio); il pre-push blocca un plugin modificato con la versione vecchia.
Prova del kit in Chrome senza app: una pagina HTML con `<workflow-view lang="it" name="Invitation" state="…">` e
`<metamodel-editor lang="it" style="height:520px">`, il kit inlineato in uno `<script>`, poi `wv.roles = bh.roles;
wv.workflow = bh.workflows.Invitation; ed.metamodel = <E.runtime_json(E.load(fixture))>; ed.behavior = <B.runtime_json(b, meta)>`;
il probe in un solo `setTimeout(async …)` con `await null` tra una mutazione e la lettura (i `MutationObserver` sono
microtask), risultato scritto in un `<pre id="out">`. Tema: `html.classList.add("dark")`, `html.dataset.theme`,
`getComputedStyle(box).fill`; buste `g.wfn[data-notifies]` (`pointerover` con `bubbles, composed` → `.wfview > .tip` o
`.wfbody > .tip`); pannello del workflow: `pointerdown`/`pointerup` sul `.box[data-name="Invitation"]`.
Headless: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --virtual-time-budget=8000 --dump-dom file://…`
ed estrarre il `<pre>` con `sed -n '/<pre id="out">/,/<\/pre>/p'` (con `grep -o` si vede solo la prima riga);
screenshot con `--window-size=940,1000 --screenshot=out.png`.
Sandbox: `cd ~/Documents/GitHub/modeler-sandbox && npm run db:start && PORT=3077 npm run dev` (se il DB è nuovo: `npm run db:reset`);
reinstallare il modellatore dal clone: `python3 plugins/modeler/scripts/modeler.py install ~/Documents/GitHub/modeler-sandbox --no-migration`.
Typecheck dei TSX del kit: cartella fuori dal repository con `npm i --legacy-peer-deps typescript @types/react react react-dom next`,
copia di `kit/next/*.tsx` in `src/`, stub di `@/lib/modeler/metamodel-actions` via `paths`, `tsc --noEmit`.
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (ultime quattro voci), `plugins/modeler/kit/metamodel-editor.js`
(`pageTheme` e `principalLabel` in `Layout`, `followPageTheme`/`notifyTips`/`workflowSvg` dopo `textMeasure`,
`_principalCtx`, `_workflowEditor`, la classe `WorkflowView`), `plugins/modeler/kit/next/workflow-view.tsx`,
`plugins/modeler/tests/layout.test.mjs` (ultimi due test), `plugins/core/skills/release/SKILL.md`,
`plugins/modeler/skills/notation/references/ecore-notation.md` («Roles»).
