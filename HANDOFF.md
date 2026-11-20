# Handoff — Harness dopo la revisione del 2026-11-07 (PR #43): regioni, apply riga per riga, Supabase CLI 3.x
_Aggiornato: 2026-11-20 · branch `main` (`374667a`, PR #43), allineato a `origin/main`_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core` 0.25.0, `modeler` 0.40.0). L'ultima modifica è la PR #43, che ha
applicato le tre note valutate il 2026-11-07. Il 2026-11-20 `/core:harness-review` non ha trovato nulla da valutare:
`NOTES.md` ha 0 note aperte e 1 rinviata (2026-10-19, trigger del massimo delle collezioni e annotazione in `DOMAIN.md`),
la cui condizione («primo progetto con `upper` finito») non si è avverata. Il tratto «proposta in produzione → PR →
rilascio» del modeler non risulta ancora provato con un run vero.

## Stato
- Fatto (PR #43, `374667a`, squash di cinque commit):
  - **Regioni ortogonali** (nota 2026-10-29): `regions: {<chiave>: {state, states, transitions, label, doc}}` in un
    workflow di `behavior.yaml`, ciascuna sul suo attributo di stato; `records: {by, at}` su qualsiasi transizione; gli
    attributi di stato sono tipizzati come letterali (`accountingState = checked`, `state = draft`). `validate`
    (`behavior.py`, `_check_flow`/`_check_workflow`), motore (`engine.py`, `_workflow` con `cls.flows`: stessa
    `<entity>_perform_transition`, solleciti come `<regione>.<stato>`), `drift`/`engine_version`, `BEHAVIOR.md`, kit
    (`metamodel-editor.js`, `<WorkflowView>` con `regionStates`, `<BehaviorView>`). Le regioni si modificano nel file,
    non nelle tabelle del modellatore web.
  - **`apply --write` riga per riga su entrambi i file** (nota 2026-10-15, caso del 2026-11-05): `patch_text` del
    metamodello (`ecore.py`: ruoli voce per voce, stile della riga vicina con `_entry_lines`/`_like`) e `patch_text`
    nuova per `behavior.yaml` (`behavior.py`); `cmd_apply` calcola le due patch prima di scrivere e senza `--rewrite` si
    ferma se una non è possibile. Le skill `apply`, `metamodel`, `behavior` chiedono `git diff --stat` dei due file dopo
    `--write`.
  - **Supabase CLI 3.x** (nota 2026-11-02): `core:db-push` e `core:ship` leggono versione della CLI e
    `SUPABASE_DB_PASSWORD`/`~/.pgpass` prima di ogni comando verso il cloud, non lanciano nulla che aspetti la password,
    usano `--remote` (e `--yes` dopo la conferma dell'utente); `kit/github/modeler-release.yml` passa `--yes` al push vero.
  - `NOTES.md` con le tre righe Stato; `chore(release): core 0.25.0, modeler 0.40.0`.
- Verificato (2026-11-20, su `374667a`, Postgres spento): `python3 -m unittest discover -s tests` → 24 OK;
  `-s plugins/modeler/tests` → 129 OK, 10 saltati (quelli con `MODELER_PG`: motore end-to-end, `test_region_end_to_end`,
  «view as», migrazione dei ruoli **non** eseguiti oggi); `node --test plugins/modeler/tests/*.test.mjs` → 191 OK;
  `claude plugin validate .` → passed. Nessuna CI nel repository.
- Non committato: questo `HANDOFF.md`.
- Stato delle app visto oggi nei cloni locali (sola lettura, senza `git pull`): order-management ha
  `tools/modeler` 0.40.0 e `roles:` in `domain.ecore.yaml`; invitations-af ha `tools/modeler` 0.39.0, `roles:` in
  `domain.ecore.yaml` e i workflow `modeler-apply.yml`/`modeler-release.yml`. Lo spostamento dei ruoli chiesto dalla
  PR #42 è quindi fatto in entrambe.

## Decisioni
- **La nota del 2026-10-19 resta rinviata** — nei cinque `domain.ecore.yaml` locali (order-management, invitations-af,
  LudoActivityManager, ACS-GSSI, modeler-sandbox) nessun `upper` vale 2 o più: senza un caso reale il trigger del
  massimo non avrebbe un progetto su cui provarlo.
- **La regione è la forma modellata, il flag resta valido** (PR #43) — «flag + autotransizioni + guardia» è ancora
  documentata per le app con il motore a mano; nessuna migrazione forzata.
- **`apply --write` si ferma invece di riscrivere** (PR #43) — la riscrittura completa perde i commenti, che in un'app
  con il motore a mano portano le regole del progetto; si ottiene solo con `--rewrite`.
- **Nessun comando Supabase che possa aspettare la password** (PR #43) — senza terminale resta appeso fino al timeout:
  i comandi si danno all'utente e l'output incollato vale come verifica.
- (Ereditate, PR #42) ruoli nel solo behavior = errore di `validate`; `drift` segnala `user_roles` esclusa; nell'editor
  un avviso, non riquadri dai ruoli del behavior.

## Problemi aperti
- **order-management usa ancora il flag** per il controllo contabile (`accountingChecked` con `accounting_check`/
  `accounting_uncheck` in `behavior.yaml`, visto oggi): la nota del 2026-10-29 chiede di valutare il passaggio a
  `regions` (`accountingState`, `records` al posto della personalizzazione dei tre campi).
- **invitations-af è a modeler 0.39.0**: le manca la 0.40.0 (`/modeler:install` nella sua sessione).
- **`--yes` in `modeler-release.yml`** non è stato visto in un run vero (`modeler:install` §7 dice di controllarlo al
  primo).
- Non ricontrollati da qui, ereditati dall'handoff del 2026-10-24 (lo stato vero è nell'`HANDOFF.md` di ciascuna app):
  primo run di `modeler-apply`/`modeler-release`; in order-management `MODELER_APPLY_TOKEN`, `DATABASE_URL` per `web`,
  l'env secret `ANTHROPIC_API_KEY` che prevale; in invitations-af `publicUrl(req, target)`, badge dell'header,
  `delete_user`; sandbox con modifiche dell'install non committate.
- L'avviso dei ruoli e i riquadri delle regioni nell'editor non risultano visti nel browser (coperti solo dai test
  `.mjs`).
- Ereditati: `psql` assente sul Mac (shim qui sotto); `guard_harness_edit` solo Edit/Write; la cartella `help/` non è
  tracciata; `MAX_ROWS` non si applica al box `Role`.

## Prossimi passi
1. In invitations-af: `/modeler:install` per la 0.40.0, poi `npm run model:validate` e `npm run model:drift`.
2. In order-management: decidere se portare il controllo contabile a regione (`/modeler:behavior`); se sì, colonna
   `accountingState`, `records: {by: accountingCheckedBy, at: accountingCheckedAt}`, guardia
   `linesWithoutCoan = 0 and accountingState = checked`, via la personalizzazione `order-workflow` dei tre campi.
3. Primo run vero del flusso dal web in una delle due app (proposta innocua da `/admin/model`, «Applica»,
   `gh run list --workflow modeler-apply.yml`, «Conferma e rilascia»), guardando che il push con `--yes` passi. Ogni
   inciampo → `/core:harness-note`.
4. Qui, con Docker acceso: i test con `MODELER_PG` (comandi sotto), per vedere `test_region_end_to_end` verde.
5. Se compare un progetto con `upper` finito su una collezione: riprendere la nota rinviata del 2026-10-19.

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
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (ultime tre voci e la rinviata del 2026-10-19),
`plugins/modeler/scripts/metamodel/behavior.py` (`patch_text`, `_check_flow`), `plugins/modeler/scripts/metamodel/engine.py`
(`_workflow`), `plugins/modeler/skills/notation/references/behavior-notation.md` («Workflows», `regions`),
`plugins/core/skills/db-push/SKILL.md`.
