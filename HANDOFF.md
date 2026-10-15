# Handoff — sviluppo dell'harness iovino-harness
_Aggiornato: 2026-10-15 · branch `main`_

## Obiettivo
Marketplace personale di plugin per Claude Code, installabile su ogni computer con `./install.sh`:
convenzioni e guardrail comuni (`core`) e sviluppo model-based delle app Next.js + Supabase (`modeler`).
Si raffina un pezzo alla volta, applicando le note raccolte nei progetti (`NOTES.md`, con `/core:harness-review`);
poi arriveranno i plugin `research` e `mde`.

## Stato
- Rilasciato e pubblicato su GitHub: `0f588b7` `chore(release): core 0.5.0, modeler 0.7.0`. Plugin installati su
  questo computer aggiornati (core 0.5.0, modeler 0.7.0). Nessun branch aperto oltre `main`.
- Novità della 0.5.0 / 0.7.0:
  - `/core:harness-review` e promemoria a inizio sessione (`note_states`, `is_harness_repo` in `cmd_session` di
    `plugins/core/scripts/hook.py`): conta le note aperte, le rinviate a parte;
  - `/core:ship` (`plugins/core/skills/ship/SKILL.md`): push, PR, CI, merge su `main` solo dopo conferma;
  - editor del metamodello con layout puro e testato (sezione `Layout` di `plugins/modeler/kit/metamodel-editor.js`,
    test `plugins/modeler/tests/layout.test.mjs`): porte sfalsate e scorrevoli, variante a Z, etichette tra più
    candidate, hover;
  - `unique` di classe nel metamodello (`unique: [a, b, c]` → `unique nulls not distinct`), letto da reverse e
    controllato da drift, anche da indici unici;
  - due righe nuove in `conventions.md`: merge su `main` sempre con conferma; lookup a più dimensioni come matrice
    con combinazione unica.
- `NOTES.md`: 3 note applicate, 1 rinviata (il bus dell'editor), **2 da valutare** (aggiunte il 2026-10-15 da
  guest-invitations-af):
  - `modeler apply --write` riscrive tutto `domain.ecore.yaml` (chiavi riordinate: diff di 187 righe per una
    modifica);
  - il modellatore non mostra le proposte salvate e non ancora applicate.
- Verificato su `main` (2026-10-15): `python3 -m unittest discover -s tests` → 21 OK;
  `python3 -m unittest discover -s plugins/modeler/tests` → 31 OK (4 skip senza `MODELER_PG`; con Postgres 16 in
  Docker tutti verdi); `node --test plugins/modeler/tests/layout.test.mjs` → 79 pass, 1 todo;
  `claude plugin validate .` → passed.
- Non committato: nulla.

## Decisioni
- Layout puro dentro `metamodel-editor.js` (non un file separato) — le app caricano ancora un solo script.
- Bus per molte sorgenti rinviato — si progetta su un metamodello reale (`test.todo` con `hub(8)`).
- `unique` di classe con `nulls not distinct` — la colonna vuota è la riga di default e non deve ripetersi; il drift
  segnala solo i gruppi del metamodello mancanti nel database, per non rompere le app già allineate.
- Niente vista `matrix` generata dal modeler — il metamodello descrive la struttura, le pagine sono codice dell'app.
- Rilascio unico dopo aver unito più branch in `main` (un solo `release.py --write`), invece di un rilascio per
  branch.

## Problemi aperti
- Le 2 note da valutare (vedi Stato): la prima è un bug della CLI che tocca ogni app con il modellatore.
- Il modellatore non è ancora installato in nessuna app reale con questa versione (`/admin/model` mai provato con
  Supabase reale).
- Le app nate con appforge (`guest-invitations-af`, `order-management`) citano ancora appforge.
- Sugli altri computer i plugin sono alla versione precedente finché non si aggiornano.

## Prossimi passi
1. `/core:harness-review` sulle 2 note aperte; per `apply --write` partire da `E.dump`/`dumps` in
   `plugins/modeler/scripts/metamodel/ecore.py` (ordine delle chiavi) e da `cmd_apply` in `cli.py`, con un test
   "una modifica nella proposta → una riga di diff".
2. Sugli altri computer: `git pull` nel clone e `./install.sh`, oppure `claude plugin update core@iovino-harness` e
   `claude plugin update modeler@iovino-harness`.
3. `/modeler:install` su guest-invitations-af con `supabase start`: prova di `/admin/model`, delle proposte, del
   nuovo layout e di `unique` di classe sulle tariffe; se il metamodello ha ≥4 classi verso la stessa, riprendere la
   nota rinviata sul bus.
4. Provare `/core:db-push` alla prima migrazione da portare in produzione.
5. Plugin `mde` (Eclipse/EMF, Epsilon) e `research`.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test con database: `docker run -d --rm --name modeler-pg-test -e POSTGRES_PASSWORD=pg -p 55499:5432 postgres:16`,
poi `MODELER_PG=postgresql://postgres:pg@localhost:55499/postgres python3 -m unittest discover -s plugins/modeler/tests`
(non usare il database Supabase di un'app per i test).
File da leggere per primi: `CLAUDE.md`, `NOTES.md`, `plugins/core/context/conventions.md`,
`plugins/modeler/README.md`, `plugins/core/skills/harness-review/SKILL.md`.
