# Handoff — i segreti di «Applicazione dal web» si impostano da `/admin/model` (PR #39)
_Aggiornato: 2026-10-23 · branch `main` (`88873e2`, PR #39), albero pulito_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Il tratto «proposta in produzione → PR → rilascio»
(`/admin/model` → `repository_dispatch` → workflow `modeler-apply` con Claude Code headless → PR → «Conferma e rilascia»
→ workflow `modeler-release`) era costruito da PR #27/#28 ma non è mai partito davvero: chiedeva segreti in tre posti
(environment GitHub `modeler-apply`, environment `modeler-release`, pannello Docker) e in order-management mancavano o
erano sbagliati. Oggi (PR #39: core 0.23.0, modeler 0.37.0) l'admin li imposta dal riquadro «Applicazione dal web»
in `/admin/model`: l'app li cifra con la chiave pubblica del repository e li scrive come repository secrets di GitHub
Actions, senza conservarli. `NOTES.md`: 0 note aperte, 1 rinviata (massimo finito delle collezioni).

## Stato
- Fatto (PR #39, `88873e2`):
  - `plugins/modeler/kit/next/apply-web.ts` (nuovo, puro, senza `"use server"`): `APPLY_SECRETS`
    (`ANTHROPIC_API_KEY`, `MODELER_PROD_DB`, `MODELER_GH_TOKEN`), `APPLY_ENVIRONMENTS`, tipi `ApplyWebStatus`/`ApplyWebInput`,
    `dsnWithPassword(pooler, password)` (password percent-encoded dopo l'utente, sostituisce `:[YOUR-PASSWORD]`),
    `dsnHasPassword`, `envOverrideCommand`.
  - `metamodel-actions.ts`: `applyRepo()` (`MODELER_APPLY_REPO` || `modeler-apply.json`), `appDatabaseUrl()`
    (`MODELER_PROD_DB`/`DATABASE_URL` del processo web con password), `gh()`/`ghDetail()` per le chiamate GitHub,
    `applyWebStatus()` (lista dei repository secrets con `updated_at`, secret omonimi negli environment → `envOverride`,
    404 = environment assente, 403 = `envChecked:false`), `saveApplyWebSecrets(input)` (public key → `crypto_box_seal`
    con `libsodium-wrappers` importato dinamicamente → `PUT /actions/secrets/<name>`; connessione dal `dsn`, dalla
    password + pooler o da `DATABASE_URL`; token di merge esplicito o quello dell'app). `githubConfig()` con i due
    messaggi nuovi (token mancante, repository sconosciuto).
  - `metamodel-modeler.tsx`: `ApplyWebPanel` (`<details>` sopra la lista delle proposte, solo `canEdit`, nullo in
    file mode o se lo stato non si legge): badge configurata / N da impostare / token mancante, repository, tre righe
    «impostata il …»/«mancante» con l'avviso di override e il comando `gh secret delete`, campi `type="password"`
    (chiave Anthropic; casella «usa la connessione che l'app ha già» se `dbFromEnv`, altrimenti password con l'URL del
    pooler o stringa intera; token di merge + casella «usa il token dell'app»), «Salva su GitHub»; `when(iso, lang)` a
    livello modulo; 23 chiavi `applyWeb*` in `TEXT.it/en`. Lo stato si legge con `readStatus().then(showStatus)`
    nell'effetto (la regola `react-hooks/set-state-in-effect` rifiuta un `await` + setState diretto).
  - CLI `cli.py`: `APPLY_JSON`, `NPM_DEPENDENCIES = {"libsodium-wrappers": "^0.8.4"}` (porta i suoi tipi),
    `git_origin_url` (anche `.git` file con `gitdir:` e `commondir`), `github_repo` (https, `x@`, ssh, `.git` opzionale),
    `pooler_url` (senza password), `write_apply_config` (valori tenuti se non derivabili); `install` copia `apply-web.ts`,
    scrive sempre `src/lib/modeler/modeler-apply.json`, aggiunge la dipendenza una volta e stampa «run `npm install` and
    commit package-lock.json».
  - Docs: skill `install` §3 (file nuovi, dipendenza), §6 (npm install, token da rigenerare), §7 riscritta (una sola
    variabile nel pannello Docker, il resto dal riquadro, override degli environment, Required reviewers solo su repo
    pubblici con piano Free, `serverExternalPackages` come ripiego); skill `deploy` (`DATABASE_URL` anche a `web`);
    README del modeler; commenti di testa dei due yml (i workflow non cambiano).
- Verificato: `node --test plugins/modeler/tests/*.mjs` → 189 OK (nuovo `apply-web.test.mjs`, importa il `.ts` con il
  type stripping di Node 24, `skip` altrove); `python3 -m unittest discover -s plugins/modeler/tests` → 117 OK, 9
  saltati (Postgres spento); `-s tests` → 23 OK; `claude plugin validate .` OK; sandbox: `install`, `npm install`,
  `tsc --noEmit`, `eslint` sui tre file del kit, `next build` (Turbopack impacchetta libsodium senza
  `serverExternalPackages`); ricetta sealed box contro l'API di GitHub su questo repository con un secret di prova
  (`PUT` 201, elencato con data, 404 sull'environment assente, `DELETE` 204). Non provato: il riquadro in un browser con
  un admin loggato. Nessuna CI nel repository.
- Non committato: nulla. Questa sessione gira con core 0.21.0 e modeler 0.36.1 in cache (`/reload-plugins` per
  0.23.0/0.37.0). La sandbox ha il kit 0.37.0 installato e `package.json`/lockfile modificati, non committati.

## Decisioni
- **L'app è il pannello, GitHub Actions il deposito** — il lavoro (Claude, `db push`, merge) gira su GitHub Actions, che
  non legge nulla dall'app; l'app invece ha già un token per il `repository_dispatch`. Scartata la via «segreti nel
  database consegnati via OIDC»: chiave service-role nel container web (oggi assente), libreria JWT, rotta che consegna
  segreti di produzione, modifica dei workflow.
- **Repository secrets, non environment secrets** — un solo permesso in più sul token (Secrets write); gli environment
  li crea GitHub al primo run. Un secret omonimo in un environment prevale: il riquadro lo dice con il comando per
  toglierlo (oggi order-management ha `ANTHROPIC_API_KEY` nell'environment `modeler-apply`).
- **La connessione al database si riusa, non si ridigita** — il processo web la ha se il compose passa `DATABASE_URL`
  anche a `web` (oggi solo al `dispatcher`): casella «usa la connessione che l'app ha già»; costo: il container web
  tiene il DSN con privilegi pieni. Il campo della password resta come ripiego.
- **Il token dell'app può fare da `MODELER_GH_TOKEN`** — con Pull requests write unisce la PR e, essendo un PAT, fa
  partire il deploy; il campo facoltativo ammette il token di un maintainer; la casella non sovrascrive un
  `MODELER_GH_TOKEN` esistente se non spuntata.
- **Nessuna fermata umana su GitHub per i repository privati Free** — «Required reviewers» esiste solo sui repo
  pubblici per Free/Pro/Team: il gate è il clic in `/admin/model` più `MODELER_APPLY_BUDGET`; detto nel riquadro, nei
  docs e negli yml.
- **`modeler-apply.json` importato staticamente e committato** — con `output: "standalone"` `src/` non è
  nell'immagine; contiene solo host del pooler e ref del progetto, già pubblici nel compose.
- (Ereditate, PR #36–#38) tema dal `body`/`html` della pagina nel kit; tooltip disegnato solo per la busta; etichette
  dei destinatari solo presentazione; notazione EMF per `User.roles`; conferma al salvataggio senza righe;
  `/core:release` separata da `/core:ship`.

## Problemi aperti
- **Il flusso dal web non ha ancora un run vero** (`modeler-apply` né `modeler-release`, in nessuna app). In
  order-management: token `MODELER_APPLY_TOKEN` da rigenerare con Contents write + Pull requests write + Secrets write;
  `DATABASE_URL` da passare anche a `web` nel compose; env secret `ANTHROPIC_API_KEY` in `modeler-apply` che
  prevarrebbe (`gh secret delete ANTHROPIC_API_KEY --env modeler-apply --repo gssi/order-management`); nessun environment
  `modeler-release`. invitations-af non ha i workflow del modeler.
- Il riquadro non è stato visto nel browser: layout e testi solo da `tsc`/`eslint`. Se `next build` di un'app fallisce
  su `libsodium-wrappers`: `serverExternalPackages: ["libsodium-wrappers"]` in `next.config.ts` (nella sandbox non è
  servito).
- order-management (modeler 0.36.1, `CUSTOM(modeler-theme)` in `globals.css`): `/modeler:install` per 0.37.0, poi
  togliere `CUSTOM(modeler-theme)`; verificare `/orders/<id>` «Diagramma» (Mac scuro, app chiara) e `/admin/model`
  (box `Role`/`User`, buste, tooltip; `self.fund.manager` mostra `fund › manager` senza `label` sulle reference).
  Restano `view_as: {users_by: [admin]}` al posto di `CUSTOM(view-as)` e «+ Nuovo» in modale per il fornitore.
- Nessun progetto usa ancora `states.<key>.model`; il `MAX_ROWS` non si applica al box `Role`; la select dei template
  nel pannello della transizione è un campo di testo; `principalLabel` di un `self.<ref>` senza `label` mostra il nome
  della reference.
- Ereditati: `psql` assente sul Mac (shim in «Per riprendere»); `model:pull`/`model:done` mai riusciti su un progetto
  cloud; `guard_harness_edit` solo Edit/Write; la cartella `help/` non è tracciata; il bump di `core` a 0.23.0 viene da
  una riga della skill `deploy` (livello dal tipo del commit).

## Prossimi passi
1. Qui: `/reload-plugins` (core 0.23.0, modeler 0.37.0). Sugli altri computer: `claude plugin marketplace update
   iovino-harness && claude plugin update core@iovino-harness modeler@iovino-harness`.
2. In order-management: `/modeler:install` (atteso `src/lib/modeler/modeler-apply.json` = `{"repo": "gssi/order-management",
   "pooler": "postgresql://postgres.eydrssvailjcjjlzbhte@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"}`),
   `npm install`, in `deploy/docker-compose.prod.yml` `DATABASE_URL: ${DATABASE_URL}` anche sotto `web.environment`,
   togliere `CUSTOM(modeler-theme)`, typecheck/lint/build, `/core:ship`; nel Docker Manager rigenerare
   `MODELER_APPLY_TOKEN` (Contents write, Pull requests write, Secrets write) e Redeploy.
3. In `/admin/model` di order-management: riquadro «Applicazione dal web» → chiave Anthropic, caselle della connessione e
   del token dell'app, «Salva su GitHub»; `gh secret list --repo gssi/order-management` deve mostrare i tre secret con la
   data; cancellare l'env secret che prevale (comando sopra).
4. Primo run vero: proposta innocua (una `label` o un `doc`) salvata da `/admin/model`, «Applica», lettura del run
   (`gh run list --workflow modeler-apply.yml --repo gssi/order-management`), revisione della PR, «Conferma e rilascia»,
   riga su `applied`. Ogni inciampo → `/core:harness-note`.
5. Poi in order-management: `view_as: {users_by: [admin]}` con `/modeler:behavior`, «+ Nuovo» per il fornitore, campi per
   stato come `requires`/`model`; invitations-af: `/modeler:install` porta anche i workflow.
6. Sandbox: committare o scartare le modifiche dell'install 0.37.0; provare il riquadro con `MODELER_PROPOSALS=db`
   (serve un admin loggato: `npm run db:start`, `PORT=3077 npm run dev`).

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
blocca un plugin modificato con la versione vecchia.
Sandbox: `cd ~/Documents/GitHub/modeler-sandbox && npm run db:start && PORT=3077 npm run dev`; reinstallare il kit dal
clone: `python3 plugins/modeler/scripts/modeler.py install ~/Documents/GitHub/modeler-sandbox --no-migration`, poi
`npm install && npx tsc --noEmit && npx eslint src/components/modeler src/lib/modeler && npm run build`.
Prova della ricetta dei segreti senza app: script Node con `libsodium-wrappers` che prende `gh auth token`, legge
`GET /repos/<o>/<r>/actions/secrets/public-key`, `crypto_box_seal` + `to_base64(…, ORIGINAL)`, `PUT /actions/secrets/<NOME>`,
`GET /actions/secrets`, `DELETE` (fatto su `iovinoludovico/iovino-harness` con `MODELER_SEAL_TEST`).
Stato di un'app: `gh secret list --repo <o>/<r>`, `gh secret list --env modeler-apply --repo <o>/<r>`,
`gh api repos/<o>/<r>/environments --jq '.environments[].name'`, `gh run list --workflow modeler-apply.yml --repo <o>/<r>`.
Prova del kit in Chrome headless (tema, buste, tooltip): vedi la ricetta nella versione precedente di questo file
(`git show 44be544:HANDOFF.md`, «Per riprendere»).
File da leggere per primi: `CLAUDE.md`, `plugins/modeler/skills/install/SKILL.md` §7, `plugins/modeler/kit/next/apply-web.ts`,
`plugins/modeler/kit/next/metamodel-actions.ts` (`githubConfig`, `applyWebStatus`, `saveApplyWebSecrets`),
`plugins/modeler/kit/next/metamodel-modeler.tsx` (`ApplyWebPanel`), `plugins/modeler/scripts/metamodel/cli.py`
(`write_apply_config`, `install`), `plugins/modeler/kit/github/modeler-apply.yml` (commenti di testa).
