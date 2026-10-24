# Handoff — Revisione delle note dell'harness: i ruoli non vivono mai nel solo comportamento (PR #42)
_Aggiornato: 2026-10-24 · branch `main` (`88e006a`, PR #42), albero pulito_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Oggi `/core:harness-review` ha valutato l'unica
nota aperta (2026-10-24, nata in invitations-af dopo l'aggiornamento del modellatore alla 0.38.0): i ruoli dell'app
erano rimasti solo in `behavior.yaml`, il metamodello non aveva `roles:` e nessun controllo lo diceva (`validate` 0
errori, `drift` «aligned» con `user_roles` in `MODELER_EXCLUDE`, nessun riquadro `Role`/`User` nel diagramma, nessuna
sezione «Ruoli» in `DOMAIN.md`). Applicata con la PR #42 (core 0.24.1, modeler 0.39.0). Il tratto «proposta in
produzione → PR → rilascio» del modeler (PR #27/#28, #39, #40) esiste ma non ha ancora un run vero.
`NOTES.md`: 0 note aperte, 1 rinviata (massimo finito delle collezioni, da riprendere al primo `upper` finito).

## Stato
- Fatto (PR #42, `88e006a`, squash di quattro commit):
  - `validate` (`plugins/modeler/scripts/metamodel/behavior.py`, `_check_roles`): `roles:` nel behavior con un metamodello
    senza `roles:` è **un** errore su `roles` con la soluzione (spostare il blocco in `domain.ecore.yaml`, `reverse` lo
    scrive da `app_role`/`user_roles`, nel behavior restano al più `label` e `doc`); `self.<ref>` verso `User` usato come
    principal senza `role: true` da avviso a errore (`test_behavior.py`, caso «the form before the roles moved»).
  - `install` stampa «roles found in behavior.yaml only (…)» (`cli.py` `roles_hint`, primo della lista dei suggerimenti;
    test `test_install_says_when_the_roles_are_declared_in_the_behaviour_only` in `test_modeler.py`); skill install §4
    (passi: blocco, `role: true`, `user_roles` fuori da `MODELER_EXCLUDE`, `validate`/`sync`/`drift`) e checklist §6.
  - `drift` (`dbschema.py`): riga `EXCLUDED user_roles: the metamodel declares no roles …` quando la tabella esiste, è
    esclusa e il metamodello non ha ruoli (assert in `test_migration_reverse_and_drift`).
  - Editor web (`kit/metamodel-editor.js`, `_warnings()`): avviso «dichiarati solo in behavior.yaml: non compaiono nel
    diagramma, spostali nel metamodello (pannello Ruoli)» quando `this._bh.roles` ha `source: behavior` e `mm.roles` è
    vuoto; chiave i18n `rolesInBehavior` (it/en). Non blocca il salvataggio.
  - Documentazione: `ecore-notation.md` «Roles», `behavior-notation.md` (chiavi top-level), README del modeler,
    `plugins/core/context/conventions.md` (riga «Utenti e ruoli vengono dal dominio» al posto di «Il comportamento (ruoli,
    …) sta in `behavior.yaml`»).
  - `NOTES.md` con la riga Stato della nota; `chore(release): core 0.24.1, modeler 0.39.0`
    (`plugins/modeler/scripts/metamodel/__init__.py` a 0.39.0 via `release.py`).
- Verificato (prima del merge, sullo stesso albero): `python3 -m unittest discover -s tests` → 24 OK;
  `-s plugins/modeler/tests` → 119 OK, 9 saltati (Postgres spento: motore end-to-end, «view as», migrazione dei ruoli non
  provati); `node --test plugins/modeler/tests/*.test.mjs` → 190 OK; `claude plugin validate .` OK. Nessuna CI nel
  repository. L'avviso dell'editor non è stato visto nel browser (nessun test `.mjs` copre `_warnings()`).
- Non committato: nulla. Plugin **non** ricaricati dopo il merge (`/reload-plugins`; sugli altri computer
  `claude plugin marketplace update iovino-harness && claude plugin update core@iovino-harness modeler@iovino-harness`).
- Ereditato da #39/#40: la sandbox ha i file del kit 0.38.0 copiati a mano e `package.json`/lockfile modificati
  dall'install 0.37.0, non committati.

## Decisioni
- **Errore, non avviso, per i ruoli nel solo behavior** — la nota nasce proprio da un vuoto senza segnale; `install` §6
  lancia `model:validate` nell'aggiornamento, quindi l'app lo vede nel commit di upgrade. Costo accettato: invitations-af e
  order-management falliranno `validate` finché non spostano i ruoli (pochi minuti, nessuna migrazione: `role: true` è
  solo un marcatore).
- **Niente riscrittura automatica di `domain.ecore.yaml` da `install`** — `install` non legge il database; il blocco
  `roles:` ha la stessa sintassi nei due file e si copia tale e quale seguendo la skill.
- **`drift` segnala `user_roles` esclusa** anche se «escluso» di norma vuol dire tacere — la notazione dice già che
  `user_roles`/`app_role` non si escludono; copre le app senza `behavior.yaml`. Un `drift` rosso blocca `modeler-release`
  finché l'app non si adegua: voluto.
- **Diagramma: avviso, non riquadri dai ruoli del behavior** (variante (4) della nota scartata) — il layout resta
  funzione pura del solo metamodello e il diagramma non mostra elementi che il metamodello non ha; con `validate` e
  `install` lo stato vecchio è transitorio. Avviso in `_warnings()` e non in `_issues()` perché gli issues disabilitano
  «Salva» e la correzione si fa proprio dal pannello «Ruoli».
- (Ereditate, PR #41) guard dell'hook per gli URL assoluti; le parti «kit» delle note non entrano nell'harness;
  convenzione «Utenti» completa. (PR #39/#40) l'app è il pannello e GitHub Actions il deposito dei segreti; repository
  secrets; il token dell'app fa da `MODELER_GH_TOKEN`; `modeler-apply.json` committato.

## Problemi aperti
- **Le due app sono nella forma vecchia**: invitations-af (modeler 0.38.0, ruoli `office`, `issuer`, `director` con
  ambito `Department` solo in `behavior.yaml`, `Invitation.issuer` senza `role: true`, `user_roles` in `MODELER_EXCLUDE`)
  e order-management (modeler ≤ 0.37.0, ruoli `admin`, `rup`, `rup_assistant`, `area_director`). Con la 0.39.0
  `model:validate` le ferma: lo spostamento va nello stesso commit dell'aggiornamento.
- **Il flusso dal web non ha ancora un run vero** (`modeler-apply` né `modeler-release`, in nessuna app). In
  order-management: token `MODELER_APPLY_TOKEN` da rigenerare con Contents write + Pull requests write + Secrets write;
  `DATABASE_URL` da passare anche a `web` nel compose e nel pannello del server; env secret `ANTHROPIC_API_KEY`
  nell'environment `modeler-apply` che prevarrebbe (`gh secret delete ANTHROPIC_API_KEY --env modeler-apply --repo
  gssi/order-management`). invitations-af non ha i workflow del modeler.
- Da PR #41, ancora da fare in invitations-af: `publicUrl(req, target)` in `src/app/notifications/[id]/route.ts`, badge
  dell'header dentro il bottone, RPC `public.delete_user` + bottone «Elimina» (se regge → `/core:harness-note` per il kit).
- order-management: `/modeler:install` per 0.39.0, togliere `CUSTOM(modeler-theme)`, `metamodel={metamodel}` su
  `<WorkflowView>`; restano `view_as: {users_by: [admin]}` al posto di `CUSTOM(view-as)` e «+ Nuovo» in modale.
- Il riquadro «Applicazione dal web» e l'avviso dei ruoli nell'editor non sono stati visti nel browser. Se `next build`
  fallisce su `libsodium-wrappers`: `serverExternalPackages: ["libsodium-wrappers"]` in `next.config.ts`.
- Nessun progetto usa `states.<key>.model`; `MAX_ROWS` non si applica al box `Role`; la select dei template nel pannello
  della transizione è un campo di testo.
- Ereditati: `psql` assente sul Mac (shim in «Per riprendere»); `model:pull`/`model:done` mai riusciti su un progetto
  cloud; `guard_harness_edit` solo Edit/Write; la cartella `help/` non è tracciata.

## Prossimi passi
1. `/reload-plugins` qui; sugli altri computer `claude plugin marketplace update iovino-harness && claude plugin update
   core@iovino-harness modeler@iovino-harness`.
2. In invitations-af (sessione sua, modeler 0.39.0): `/modeler:install` → atteso «roles found in behavior.yaml only
   (office, issuer, director)»; spostare il blocco `roles:` in `domain.ecore.yaml` (prima di `classes:`), `role: true` su
   `Invitation.issuer`, togliere `user_roles` da `MODELER_EXCLUDE` (`.env*`: indicare la riga all'utente), `npm run
   model:validate` → «Behaviour OK», `model:sync` (atteso «Ruoli» in `DOMAIN.md`), `model:drift` → aligned con
   `user_roles` confrontata; aprire `/admin/model` e vedere i riquadri `Role «enumeration»` e `User «built-in»`. Poi le
   tre cose della PR #41 (passo 3 dell'handoff precedente: `publicUrl`, badge, `delete_user`).
3. In order-management: `/modeler:install` per 0.39.0 (stesso spostamento dei ruoli, più `modeler-apply.json`, suggerimento
   su `DATABASE_URL`), `npm install`, `DATABASE_URL: ${DATABASE_URL}` sotto `web.environment`, `metamodel={metamodel}` su
   `<WorkflowView>`, togliere `CUSTOM(modeler-theme)`, typecheck/lint/build, `/core:ship`; nel Docker Manager rigenerare
   `MODELER_APPLY_TOKEN` e Redeploy.
4. Primo run vero del flusso dal web in order-management: riquadro «Applicazione dal web», `gh secret list --repo
   gssi/order-management` con i tre secret, cancellare l'env secret che prevale; proposta innocua da `/admin/model`,
   «Applica», `gh run list --workflow modeler-apply.yml`, revisione della PR, «Conferma e rilascia», riga su `applied`.
   Ogni inciampo → `/core:harness-note`.
5. Sandbox: committare o scartare le modifiche dell'install; provare il riquadro con `MODELER_PROPOSALS=db`.
6. Se compare un progetto con `upper` finito su una collezione: riprendere la nota rinviata del 2026-10-19.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test senza database: `python3 -m unittest discover -s tests && python3 -m unittest discover -s plugins/modeler/tests && node --test plugins/modeler/tests/*.test.mjs && claude plugin validate .`
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
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (ultima voce), `plugins/modeler/scripts/metamodel/behavior.py`
(`_check_roles`), `plugins/modeler/scripts/metamodel/cli.py` (`roles_hint`, `cmd_install`),
`plugins/modeler/skills/install/SKILL.md` (§4 ruoli, §6), `plugins/modeler/skills/notation/references/ecore-notation.md` («Roles»).
