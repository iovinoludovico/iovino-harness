# Handoff — «Applicazione dal web» configurata da `/admin/model`, segreti dell'app scritti da soli (PR #39, #40)
_Aggiornato: 2026-10-23 · branch `main` (`0f3b691`, PR #40), albero pulito_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Il tratto «proposta in produzione → PR → rilascio»
(`/admin/model` → `repository_dispatch` → workflow `modeler-apply` con Claude Code headless → PR → «Conferma e rilascia»
→ workflow `modeler-release`) esiste da PR #27/#28 ma non ha ancora un run vero: chiedeva segreti in tre posti e in
order-management mancavano o erano sbagliati. Oggi, in due PR: il riquadro «Applicazione dal web» in `/admin/model`
scrive i segreti dei workflow come repository secrets cifrati di GitHub Actions (PR #39: core 0.23.0, modeler 0.37.0) e
quelli che l'app ha già nel proprio ambiente li scrive da sé, così l'admin digita solo la chiave Anthropic; inoltre
`<workflow-view>` riceve il metamodello e traduce i destinatari `self.…` (PR #40: modeler 0.38.0). `NOTES.md`: 0 note
aperte, 1 rinviata (massimo finito delle collezioni).

## Stato
- Fatto (PR #39, `88873e2`): `kit/next/apply-web.ts` (puro: `APPLY_SECRETS`, `APPLY_ENVIRONMENTS`, tipi, `dsnWithPassword`,
  `dsnHasPassword`, `envOverrideCommand`); `metamodel-actions.ts`: `applyRepo()` (`MODELER_APPLY_REPO` ||
  `modeler-apply.json`), `appDatabaseUrl()` (`MODELER_PROD_DB`/`DATABASE_URL` del processo web con password), `gh()`/
  `ghDetail()`, `applyWebStatus()`, `saveApplyWebSecrets()`; `metamodel-modeler.tsx`: `ApplyWebPanel` (`<details>` sopra
  le proposte, solo `canEdit`, nullo in file mode); CLI: `APPLY_JSON`, `NPM_DEPENDENCIES` (`libsodium-wrappers ^0.8.4`,
  porta i tipi), `git_origin_url`/`github_repo`/`pooler_url`/`write_apply_config`, `install` copia `apply-web.ts`, scrive
  sempre `src/lib/modeler/modeler-apply.json` e aggiunge la dipendenza una volta («run `npm install`»); skill `install`
  §3/§6/§7, skill `deploy`, README, commenti dei due yml (i workflow non cambiano).
- Fatto (PR #40, `0f3b691`, due note dell'harness del 2026-10-23):
  - `applyWebStatus` scrive da sé su GitHub, con `putSecrets` (public key → `crypto_box_seal` → `PUT
    /actions/secrets/<name>`), i secret mancanti che derivano dall'ambiente: `MODELER_PROD_DB` da `DATABASE_URL`,
    `MODELER_GH_TOKEN` dal token dell'app; `ApplyWebSecret.fromEnv`, riga «impostata il … · dall'ambiente dell'app»;
    niente più caselle: il modulo ha la chiave Anthropic, il token di un maintainer (facoltativo) e, solo se il web non
    ha `DATABASE_URL`, la password (nell'URL del pooler) o la stringa intera; la frase d'apertura dice che i workflow
    girano su GitHub Actions. `compose_hint(root)` in `cli.py` (glob `COMPOSE_FILES`, stampato da `cmd_install`) segnala
    «DATABASE_URL reaches only <worker> in <compose>: pass it to `web` too»; test
    `test_install_tells_when_database_url_reaches_only_the_worker`.
  - `<workflow-view>`: proprietà `metamodel` (`_mm`, usata come `mm` con `cn` = attributo `name` nel contesto di
    `workflowModel`); `workflow-view.tsx`: prop facoltativa `metamodel` (import di `@/lib/modeler/metamodel.json`);
    esempi in skill `install` §4 e README; test «workflowModel with mm/cn» in `layout.test.mjs`.
- Verificato: `node --test plugins/modeler/tests/*.mjs` → 190 OK; `python3 -m unittest discover -s plugins/modeler/tests`
  → 118 OK, 9 saltati (Postgres spento); `-s tests` → 23 OK; `claude plugin validate .` OK; sandbox con i file nuovi:
  `tsc --noEmit`, `eslint src/components/modeler src/lib/modeler`, `next build` (con la 0.37.0: Turbopack impacchetta
  libsodium senza `serverExternalPackages`); ricetta sealed box contro l'API di GitHub su questo repository con un secret
  di prova (`PUT` 201, elencato con data, 404 sull'environment assente, `DELETE` 204). Non provato: il riquadro in un
  browser con un admin loggato. Nessuna CI nel repository.
- Non committato: nulla. Plugin ricaricati in questa sessione (core 0.23.0, modeler 0.38.0). La sandbox ha i file del
  kit 0.38.0 copiati a mano e `package.json`/lockfile modificati dall'install 0.37.0, non committati.

## Decisioni
- **L'app è il pannello, GitHub Actions il deposito** — il lavoro (Claude, `db push`, merge) gira su GitHub Actions, che
  non legge nulla dall'app; l'app ha già un token per il `repository_dispatch`. Scartata la via «segreti nel database
  consegnati via OIDC» (service-role nel container web, JWT, rotta che consegna segreti, workflow da modificare).
- **Ciò che l'app ha già non si digita** — `applyWebStatus` scrive i secret derivati dall'ambiente appena mancano (solo
  quelli mancanti, idempotente, solo admin, solo con il token che elenca i secret): una lettura della pagina può
  scrivere su GitHub, accettato per non chiedere valori che l'app possiede. Il compose dell'app non viene modificato da
  `install` (è un file dell'app): solo il suggerimento.
- **Repository secrets, non environment secrets** — un solo permesso in più sul token (Secrets write). Un secret omonimo
  in un environment prevale: il riquadro lo dice con `gh secret delete NOME --env … --repo …`.
- **Il token dell'app fa da `MODELER_GH_TOKEN`** — con Pull requests write unisce la PR e, essendo un PAT, avvia il
  deploy; il campo facoltativo ammette il token di un maintainer.
- **Nessuna fermata umana su GitHub per i repository privati Free** — «Required reviewers» esiste solo sui repo pubblici
  per Free/Pro/Team: il gate è il clic in `/admin/model` più `MODELER_APPLY_BUDGET`.
- **`modeler-apply.json` importato staticamente e committato** — con `output: "standalone"` `src/` non è nell'immagine;
  contiene solo host del pooler e ref del progetto.
- **`metamodel` facoltativo su `<WorkflowView>`** — senza, il percorso resta com'è (nessuna rottura nelle pagine
  esistenti); `behavior-view.tsx` elenca le chiavi e resta com'è.
- (Ereditate, PR #36–#38) tema dal `body`/`html` della pagina nel kit; tooltip disegnato solo per la busta; etichette dei
  destinatari solo presentazione; notazione EMF per `User.roles`; conferma al salvataggio senza righe; `/core:release`
  separata da `/core:ship`.

## Problemi aperti
- **Il flusso dal web non ha ancora un run vero** (`modeler-apply` né `modeler-release`, in nessuna app). In
  order-management: token `MODELER_APPLY_TOKEN` da rigenerare con Contents write + Pull requests write + Secrets write;
  `DATABASE_URL` da passare anche a `web` nel compose (`deploy/docker-compose.prod.yml` la dà solo al `dispatcher`:
  `install` lo segnalerà) e nel pannello del server (già c'è, stesso valore); env secret `ANTHROPIC_API_KEY`
  nell'environment `modeler-apply` che prevarrebbe (`gh secret delete ANTHROPIC_API_KEY --env modeler-apply --repo
  gssi/order-management`); nessun environment `modeler-release`. invitations-af non ha i workflow del modeler.
- Il riquadro non è stato visto nel browser: layout e testi solo da `tsc`/`eslint`. Se `next build` di un'app fallisce
  su `libsodium-wrappers`: `serverExternalPackages: ["libsodium-wrappers"]` in `next.config.ts`.
- order-management (modeler 0.37.0 o precedente, `CUSTOM(modeler-theme)` in `globals.css`): `/modeler:install` per
  0.38.0, togliere `CUSTOM(modeler-theme)`; `metamodel={metamodel}` su `<WorkflowView>` in `/orders/<id>`; verificare
  `/orders/<id>` «Diagramma» (Mac scuro, app chiara) e `/admin/model` (box `Role`/`User`, buste, tooltip «Fondo ›
  Responsabile» se le reference hanno `label`, altrimenti `fund › manager`). Restano `view_as: {users_by: [admin]}` al
  posto di `CUSTOM(view-as)` e «+ Nuovo» in modale per il fornitore.
- Nessun progetto usa ancora `states.<key>.model`; il `MAX_ROWS` non si applica al box `Role`; la select dei template
  nel pannello della transizione è un campo di testo.
- Ereditati: `psql` assente sul Mac (shim in «Per riprendere»); `model:pull`/`model:done` mai riusciti su un progetto
  cloud; `guard_harness_edit` solo Edit/Write; la cartella `help/` non è tracciata.

## Prossimi passi
1. Sugli altri computer: `claude plugin marketplace update iovino-harness && claude plugin update core@iovino-harness
   modeler@iovino-harness` (qui già ricaricati).
2. In order-management: `/modeler:install` (atteso `src/lib/modeler/modeler-apply.json` = `{"repo": "gssi/order-management",
   "pooler": "postgresql://postgres.eydrssvailjcjjlzbhte@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"}` e il
   suggerimento su `DATABASE_URL`), `npm install`, `DATABASE_URL: ${DATABASE_URL}` sotto `web.environment` nel compose,
   `metamodel={metamodel}` su `<WorkflowView>`, togliere `CUSTOM(modeler-theme)`, typecheck/lint/build, `/core:ship`;
   nel Docker Manager rigenerare `MODELER_APPLY_TOKEN` (Contents write, Pull requests write, Secrets write) e Redeploy
   (il compose nel pannello va aggiornato a mano come il repository).
3. In `/admin/model` di order-management: aprire il riquadro «Applicazione dal web» (scrive da sé `MODELER_PROD_DB` e
   `MODELER_GH_TOKEN`), digitare la chiave Anthropic, «Salva su GitHub»; `gh secret list --repo gssi/order-management` deve
   mostrare i tre secret; cancellare l'env secret che prevale (comando sopra).
4. Primo run vero: proposta innocua (una `label` o un `doc`) salvata da `/admin/model`, «Applica», lettura del run
   (`gh run list --workflow modeler-apply.yml --repo gssi/order-management`), revisione della PR, «Conferma e rilascia»,
   riga su `applied`. Ogni inciampo → `/core:harness-note`.
5. Poi in order-management: `view_as: {users_by: [admin]}` con `/modeler:behavior`, «+ Nuovo» per il fornitore, campi per
   stato come `requires`/`model`; invitations-af: `/modeler:install` porta anche i workflow.
6. Sandbox: committare o scartare le modifiche dell'install; provare il riquadro con `MODELER_PROPOSALS=db` (serve un admin
   loggato: `npm run db:start`, `PORT=3077 npm run dev`).

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
Rilascio: `/core:release` (prova a vuoto, poi `--write`), poi `/core:ship` (push, PR, merge su conferma); il pre-push
blocca un plugin modificato con la versione vecchia. Harness-review con più gruppi: un commit per gruppo; per i file
condivisi (skill, README) si stagia per hunk con `git diff -U0` filtrato e `git apply --cached --unidiff-zero`.
Sandbox: `cd ~/Documents/GitHub/modeler-sandbox && npm run db:start && PORT=3077 npm run dev`; reinstallare il kit dal
clone: `python3 plugins/modeler/scripts/modeler.py install ~/Documents/GitHub/modeler-sandbox --no-migration`, poi
`npm install && npx tsc --noEmit && npx eslint src/components/modeler src/lib/modeler && npm run build`.
Prova della ricetta dei segreti senza app: script Node con `libsodium-wrappers` che prende `gh auth token`, legge
`GET /repos/<o>/<r>/actions/secrets/public-key`, `crypto_box_seal` + `to_base64(…, ORIGINAL)`, `PUT /actions/secrets/<NOME>`,
`GET /actions/secrets`, `DELETE` (fatto su `iovinoludovico/iovino-harness` con `MODELER_SEAL_TEST`).
Stato di un'app: `gh secret list --repo <o>/<r>`, `gh secret list --env modeler-apply --repo <o>/<r>`,
`gh api repos/<o>/<r>/environments --jq '.environments[].name'`, `gh run list --workflow modeler-apply.yml --repo <o>/<r>`.
Prova del kit in Chrome headless (tema, buste, tooltip): ricetta in `git show 44be544:HANDOFF.md`, «Per riprendere».
File da leggere per primi: `CLAUDE.md`, `plugins/modeler/skills/install/SKILL.md` §4 e §7, `plugins/modeler/kit/next/apply-web.ts`,
`plugins/modeler/kit/next/metamodel-actions.ts` (`githubConfig`, `appDatabaseUrl`, `applyWebStatus`, `putSecrets`,
`saveApplyWebSecrets`), `plugins/modeler/kit/next/metamodel-modeler.tsx` (`ApplyWebPanel`),
`plugins/modeler/kit/next/workflow-view.tsx`, `plugins/modeler/scripts/metamodel/cli.py` (`write_apply_config`,
`compose_hint`, `install`), `NOTES.md` (ultime due voci).
