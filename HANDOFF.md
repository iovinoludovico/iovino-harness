# Handoff — sviluppo dell'harness iovino-harness
_Aggiornato: 2026-10-15 · branch `main`_

## Obiettivo
Marketplace personale di plugin per Claude Code, installabile su ogni computer con `./install.sh`:
convenzioni e guardrail comuni (`core`) e sviluppo model-based delle app Next.js + Supabase (`modeler`).
Si raffina un pezzo alla volta, applicando le note raccolte nei progetti (`NOTES.md`, con `/core:harness-review`);
poi arriveranno i plugin `research` e `mde`.

## Stato
- Rilasciato e pubblicato su GitHub: core 0.5.0, modeler 0.8.0. Plugin installati su questo computer aggiornati.
  Nessun branch aperto oltre `main`.
- Novità della modeler 0.8.0:
  - `apply --write` riscrive solo le righe cambiate (`patch_text`, `align_order` in
    `plugins/modeler/scripts/metamodel/ecore.py`, usati da `cmd_apply`; se non può, riscrittura completa con avviso
    sui commenti persi): sul metamodello di guest-invitations-af una modifica = 2 righe di diff invece di 194;
  - `/admin/model` elenca sopra l'editor le proposte in sospeso con le differenze (`Layout.diff` in
    `metamodel-editor.js`, uguale a `modeler diff`, test `diff.test.mjs`), "Apri nell'editor", "Scarta"
    (`listMetamodelProposals`, `rejectMetamodelProposal` in `kit/next/metamodel-actions.ts`), avviso al salvataggio;
    l'hook di sessione del modeler segnala le proposte in `.modeler/proposals/`.
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
- `NOTES.md`: 6 note, tutte decise: 5 applicate (due con una parte rinviata: `pull` e l'elenco delle proposte di
  produzione dalla CLI, che richiedono un accesso in sola lettura al database di produzione), 1 rinviata (il bus
  dell'editor).
- Verificato (2026-10-15): `python3 -m unittest discover -s tests` → 21 OK;
  `python3 -m unittest discover -s plugins/modeler/tests` → 36 OK (4 skip senza `MODELER_PG`; lancia anche
  `layout.test.mjs` e `diff.test.mjs`); `claude plugin validate .` → passed; kit TypeScript compilato con `tsc` in
  un progetto di prova (con i `node_modules` di guest-invitations-af). Non provato nel browser dentro un'app.
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
- `pull` e l'elenco delle proposte di produzione richiedono ancora il DSN di produzione: da riprendere dopo aver
  verificato una lettura in sola lettura (es. `supabase db query --linked`, comando non ancora verificato).
- L'avviso delle proposte in `/admin/model` non è stato visto nel browser in un'app reale.
- Il modellatore non è ancora installato in nessuna app reale con questa versione (`/admin/model` mai provato con
  Supabase reale).
- Le app nate con appforge (`guest-invitations-af`, `order-management`) citano ancora appforge.
- Sugli altri computer i plugin sono alla versione precedente finché non si aggiornano.

## Prossimi passi
1. `/modeler:install` su guest-invitations-af (porta la 0.8.0 nell'app) e prova in browser di `/admin/model`: avviso
   delle proposte in sospeso, "Apri nell'editor", "Scarta", nuovo layout, `unique` di classe sulle tariffe; se il
   metamodello ha ≥4 classi verso la stessa, riprendere la nota rinviata sul bus.
2. Sugli altri computer: `git pull` nel clone e `./install.sh`, oppure `claude plugin update core@iovino-harness` e
   `claude plugin update modeler@iovino-harness`.
3. Provare `/core:db-push` alla prima migrazione da portare in produzione.
4. Plugin `mde` (Eclipse/EMF, Epsilon) e `research`.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test con database: `docker run -d --rm --name modeler-pg-test -e POSTGRES_PASSWORD=pg -p 55499:5432 postgres:16`,
poi `MODELER_PG=postgresql://postgres:pg@localhost:55499/postgres python3 -m unittest discover -s plugins/modeler/tests`
(non usare il database Supabase di un'app per i test).
File da leggere per primi: `CLAUDE.md`, `NOTES.md`, `plugins/core/context/conventions.md`,
`plugins/modeler/README.md`, `plugins/core/skills/harness-review/SKILL.md`.
