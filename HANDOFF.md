# Handoff — modello di comportamento `behavior.yaml` nel plugin modeler
_Aggiornato: 2026-10-17 · branch `feat/modeler-behavior` (6 commit avanti a `origin/main`, non pushato)_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`), installato con `./install.sh`. Il lavoro in corso
aggiunge al modeler il **secondo modello**: `behavior.yaml` accanto a `domain.ecore.yaml` (ruoli, workflow con guardie
e passaggi temporizzati, attributi derivati, eventi, reazioni, webhook), verificato contro il metamodello e tradotto
in documentazione, JSON tipizzato e un motore SQL (funzioni e trigger PostgreSQL) generato, al posto degli
`app.yaml` archiviati e delle clausole SQL scritte a mano nelle app (guest-invitations-af, kura, order-management).

## Stato
- `origin/main` è alla PR #9 (`ae238e2`): **core 0.9.0, modeler 0.12.1**. Nessun branch remoto aperto.
- Il branch locale `feat/modeler-behavior` contiene, già con il commit di release `bd12419` (**core 0.9.1, modeler 0.13.0**):
  - `eb8f9a5` `behavior.yaml` + `expr.py` (linguaggio di espressioni tipizzato: path, collezioni, confronti, enum,
    and/or/not) + `behavior.py` (validazione: feature sconosciute, tipi, principal che non arrivano a `User`/Email,
    ruoli con scope senza riferimento, stati irraggiungibili, cicli tra derivazioni). `validate` controlla entrambi
    i file (`--behavior` per nominarne uno), `apply` segnala una proposta che rompe il comportamento, l'hook
    `plugins/modeler/hooks/hook.py` valida `behavior.yaml` dopo ogni modifica di uno dei due file. Attributi
    `derived: true` nel metamodello (Emfatic, XMI, docs, diff), formula nel behavior. Fixture:
    `plugins/modeler/tests/fixtures/invitations.{ecore,behavior}.yaml` (tutto il comportamento di guest-invitations).
  - `40ece68` riga «comportamento» in `plugins/core/context/conventions.md` (Sviluppo guidato dai modelli).
  - `0785fa0` `from __future__ import annotations` nei test degli hook core (Python 3.9).
  - `ff9e054` espressioni con aritmetica, `round`, `coalesce`, `if … then … else`, differenze di date;
    `expr.to_sql` (path → subselect, collezioni → aggregati, join table e containment secondo lo storage mapping).
    `sync` scrive `docs/BEHAVIOR.md` e `src/lib/modeler/behavior.json`; comando `behavior` (`--format sql|engine`);
    `drift` confronta i workflow con `workflow_versions/states/transitions` pubblicati e dice quando l'app non ha
    quelle tabelle. Guardie non valutabili come clausole → consiglio di spostarle in un attributo derivato.
  - `0d40d98` `engine.py` + comando `engine [--write]`: una migrazione idempotente (`supabase/migrations/…behavior_engine…`)
    con trigger before per le derivazioni in ordine di dipendenza (e refresh quando cambia una riga riferita),
    `<entity>_perform_transition` (principal via `<entity>_principals`: admin, creator, ruoli nello scope, utenti
    puntati; condizione, guardia, commento, `workflow_history`, eventi con destinatari delle reazioni),
    `_available_transitions`, `_revert`, `_run_timed_transitions`, `_run_reminders`, trigger di lifecycle, `_can_edit`.
    Si appoggia a `current_profile_id`, `is_admin`, `has_role`, `role_members`, `emit_entity_event` dell'app, con
    fallback solo dove mancano (ruoli da `user_roles`, outbox eventi). `workflow_history` e `workflow_reminders`
    sono tabelle del motore, ignorate da `drift`. `creator` richiede un riferimento `createdBy: User`.
    Script npm installati: `model:behavior`, `model:engine` (`cli.py` righe 52–53).
  - Skill aggiornate: `modeler:metamodel` (sezione 3b «Il comportamento»), `modeler:notation`
    (+ `references/behavior-notation.md`), README del modeler (sezione Behaviour, tabella dei file generati).
- Verificato (2026-10-17, su `bd12419`):
  - `python3 -m unittest discover -s tests` → 23 OK
  - `python3 -m unittest discover -s plugins/modeler/tests` → 90 OK (8 skip senza `MODELER_PG`)
  - con `MODELER_PG` sul container `postgres:16` (vedi «Per riprendere») → 90 OK, nessuno skip: compresi
    `test_workflow_end_to_end` (guardie, permessi, condizioni, notifiche, passaggio temporizzato, reminder, revert,
    completamento) e `test_generated_sql_runs_and_workflows_align`
  - `node --test plugins/modeler/tests/layout.test.mjs plugins/modeler/tests/diff.test.mjs plugins/modeler/tests/lint.test.mjs`
    → 93 pass, 1 todo (il bus)
  - `claude plugin validate .` → passed; `python3 scripts/release.py` → «Nothing to release».
- Non committato: nulla (solo questo `HANDOFF.md`).

## Decisioni
- Comportamento in un **file separato** `behavior.yaml`, non dentro `domain.ecore.yaml`: il metamodello resta Ecore
  puro (esportabile in XMI/Emfatic); il behavior lo referenzia per nome e la validazione incrociata sostituisce il
  legame «solo per nome» che si rompeva al rinominare una feature.
- Le formule degli attributi derivati vivono nel behavior; il metamodello dice solo `derived: true`. Così il database
  (colonna materializzata dal trigger) e la documentazione restano coerenti senza duplicare la formula.
- Il motore è **generato come una sola migrazione idempotente**, rigenerata e sostituita a ogni cambio del behavior
  (una migrazione del motore per release), non una serie append-only: è codice derivato, non uno schema. Le tabelle
  del motore (`workflow_history`, `workflow_reminders`) sono fuori dal metamodello e `drift` le ignora.
- Il motore riusa le funzioni dell'app (`current_profile_id`, `is_admin`, `has_role`, `role_members`,
  `emit_entity_event`) e crea un fallback solo se mancano, per potersi innestare nelle app esistenti senza
  riscriverne la sicurezza.
- Guardie con `or`, calcoli o navigazioni non diventano clausole del motore: si spostano in un attributo derivato
  (`model:behavior -- --format engine` elenca cosa non è valutabile). Mantiene il motore semplice e le formule
  in un posto solo.
- Messaggi del motore nella lingua del metamodello, come `DOMAIN.md`.
- Release già fatta nel branch (`bd12419`) perché il push arriverà via PR: `release.py` non segnala nulla da fare.

## Problemi aperti
- Il branch non è ancora su GitHub: niente PR, niente CI. Su questo computer `gh` non è installato (`command not
  found`): `/core:ship` va fatto da un computer con `gh` oppure PR a mano dal browser dopo il push.
- Il motore generato non è stato ancora provato su un'**app reale**: solo sul fixture di guest-invitations in
  PostgreSQL nudo. Da verificare nelle app: convivenza con le funzioni esistenti (`emit_entity_event`, policy RLS
  che chiamano `_can_edit`), confronto fra il SQL generato e l'engine scritto a mano (`docs/behavior.md`,
  migrazioni), ordine fra la migrazione del motore e quelle dello schema in `supabase db reset`.
- `test_behavior.py` e `test_modeler.py` con `MODELER_PG` richiedono `psql` sul PATH: su questo Mac non c'è, i test
  girano con uno shim che inoltra a `docker exec modeler-pg-test psql` (vedi «Per riprendere»). Alternativa da
  valutare: far usare ai test `docker exec` direttamente o documentare `brew install libpq`.
- Ereditati dall'handoff precedente, ancora validi: `model:pull`/`model:done --write` mai riusciti su un progetto
  cloud reale (`fe_sendauth: no password supplied`, manca la riga del pooler in `~/.pgpass`); la guardia
  `guard_harness_edit` copre solo Edit/Write; `docs/DOMAIN.md` non visto in anteprima GitHub; parte app della nota
  sulle viste sostituite in guest-invitations-af (`listHref` o redirect `/e/economic_rate` → `/x/economic_rate`);
  bus dell'editor rinviato (test `todo` in `tests/layout.test.mjs`, order-management ha 10 riferimenti a `User`).
- `NOTES.md`: nessuna nota aperta.

## Prossimi passi
1. Pubblicare: `/core:ship` (da un computer con `gh`) o `git push -u origin feat/modeler-behavior` + PR dal browser;
   merge su `main` solo dopo conferma. Dopo il merge, sugli altri computer `claude plugin update core@iovino-harness`
   e `claude plugin update modeler@iovino-harness` (0.9.1 / 0.13.0).
2. In guest-invitations-af: `/reload-plugins`, `/modeler:install` (barra dell'editor `v0.13.0`), poi scrivere
   `behavior.yaml` partendo da `plugins/modeler/tests/fixtures/invitations.behavior.yaml` (è già la sua traduzione)
   e marcare `derived: true` gli attributi calcolati; `npm run model:validate`, `npm run model:sync`, confrontare
   `npm run model:behavior -- --format sql` con le clausole in produzione e `npm run model:drift` sui workflow
   pubblicati (`workflow_versions`).
3. Sempre lì, provare il motore generato: `npm run model:engine -- --write`, `supabase db reset`, i test dell'app,
   `npm run model:drift`; decidere se sostituisce l'engine a mano o resta un confronto, e correggere `engine.py`
   dove il SQL generato non coincide con ciò che l'app fa.
4. Ripetere `/modeler:install` in kura e order-management; in order-management anche `/core:security-audit`
   (prima prova vera della skill) e `docs/deploy.md` allineato a `core:deploy`.
5. `~/.pgpass`: aggiungere la riga del pooler stampata dalla CLI, poi `npm run model:done -- --write` e verificare
   `applied` in `/admin/model`.
6. Facoltativi: bus dell'editor; proposte di produzione in `modeler proposals`; plugin `mde` e `research`.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test senza database: `python3 -m unittest discover -s tests && python3 -m unittest discover -s plugins/modeler/tests && claude plugin validate .`
Test con database (anche il motore end-to-end):
```bash
docker run -d --rm --name modeler-pg-test -e POSTGRES_PASSWORD=pg -p 55499:5432 postgres:16
# senza psql locale: shim in una cartella sul PATH
cat > /tmp/pgbin/psql <<'PY'
#!/usr/bin/env python3
import subprocess, sys
args = [a.replace("localhost:55499", "localhost:5432") for a in sys.argv[1:]]
sys.exit(subprocess.run(["docker", "exec", "-i", "-e", "PGPASSWORD=pg", "modeler-pg-test", "psql", *args], stdin=sys.stdin).returncode)
PY
chmod +x /tmp/pgbin/psql
PATH=/tmp/pgbin:$PATH MODELER_PG=postgresql://postgres:pg@localhost:55499/postgres python3 -m unittest discover -s plugins/modeler/tests
docker stop modeler-pg-test
```
Prova rapida sui fixture: `python3 plugins/modeler/scripts/modeler.py engine plugins/modeler/tests/fixtures/invitations.ecore.yaml --behavior plugins/modeler/tests/fixtures/invitations.behavior.yaml`.
File da leggere per primi: `CLAUDE.md`, `plugins/modeler/README.md` (sezione Behaviour),
`plugins/modeler/skills/notation/references/behavior-notation.md`, `plugins/modeler/skills/metamodel/SKILL.md` (3b),
`plugins/modeler/scripts/metamodel/behavior.py` (`validate`), `expr.py` (`parse`, `to_sql`), `engine.py` (`engine_sql`),
`cli.py` (`cmd_behavior`, `cmd_engine`, `cmd_drift`, `sync`), `plugins/modeler/tests/test_behavior.py`
(`EngineDatabaseTests.test_workflow_end_to_end`), `plugins/modeler/hooks/hook.py` (`_check_behavior`).
