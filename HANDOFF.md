# Handoff — sviluppo dell'harness iovino-harness
_Aggiornato: 2026-10-15 · branch `feat/modeler-composite-unique`_

## Obiettivo
Marketplace personale di plugin per Claude Code, installabile su ogni computer con `./install.sh`:
convenzioni e guardrail comuni (`core`) e sviluppo model-based delle app Next.js + Supabase (`modeler`).
Si raffina un pezzo alla volta, applicando le note raccolte nei progetti (`NOTES.md`, con `/core:harness-review`);
poi arriveranno i plugin `research` e `mde`.

## Stato
- `main` (`52b6ac2`, core 0.4.0, modeler 0.6.1) è l'ultima versione rilasciata. Tre branch da pubblicare, tutti
  creati da `main`, da unire **in quest'ordine**:
  1. `feat/core-harness-review` (`1cc8d6c`): skill `/core:harness-review` e promemoria a inizio sessione
     (`note_states`, `is_harness_repo` in `cmd_session` di `plugins/core/scripts/hook.py`: "N note da valutare in
     NOTES.md"); `harness-note` scrive `- **Stato**: da valutare`.
  2. `feat/harness-review-ship-editor`:
     - `8ea2f60` skill `/core:ship` (`plugins/core/skills/ship/SKILL.md`: push, PR, `gh pr checks --watch`, merge
       su `main` solo dopo conferma) + riga in `conventions.md` sezione Git;
     - `f9528cc` editor del metamodello: sezione `Layout` pura in `plugins/modeler/kit/metamodel-editor.js`
       (`rowsOf`, `boxSize`, `normalize`, `autoLayout`, `routeEdges`, `edgesOf`, esportate con `module.exports`),
       porte sfalsate e scorrevoli, variante a Z, etichette tra più candidate, hover; test
       `plugins/modeler/tests/layout.test.mjs` (lanciato da `EditorLayoutTests` in `test_modeler.py`).
  3. `feat/modeler-composite-unique` (corrente, `616733d`): chiave di classe `unique: [a, b, c]` nel metamodello
     (`ecore.py`: `_check_unique_groups`, `storage()[…]["unique"]`, diff, export Ecore; `sqlgen.py`: `_add_unique`
     → `unique nulls not distinct`; `dbschema.py`: `composite_uniques`, reverse e drift anche da indici unici;
     catalogo con `unique_indexes`), documentata in `skills/notation/references/ecore-notation.md`; riga in
     `conventions.md` sui lookup a più dimensioni come matrice; test `UniqueTogetherTests` e
     `test_unique_together_applies_aligns_and_rejects_a_second_default`.
- `NOTES.md`: tutte le note sono decise. Applicate: `__pycache__`, PR/merge, lookup a più dimensioni (vista
  `matrix` scartata). In parte applicata: editor dei diagrammi (bus rinviato). Ogni branch aggiorna la propria
  nota, quindi l'unione dei branch dà conflitti banali in fondo a `NOTES.md`.
- Verificato (2026-10-15):
  - `python3 -m unittest discover -s tests` → 20 OK;
  - `python3 -m unittest discover -s plugins/modeler/tests` → 30 OK con `MODELER_PG` (Postgres 16 in un container
    usa e getta), 26 + 4 skip senza; sul branch dell'editor anche `node --test plugins/modeler/tests/layout.test.mjs`
    → 79 pass, 1 todo;
  - `claude plugin validate .` → passed; editor in Chrome headless a 1280×720 e 760×900 senza errori.
- Non committato: questo `HANDOFF.md`.

## Decisioni
- Layout puro dentro `metamodel-editor.js` (non un file separato) — le app caricano ancora un solo script e
  installer e `metamodel-modeler.tsx` non cambiano.
- Bus per molte sorgenti rinviato — con 8 classi verso la stessa le corsie non bastano; si decide dopo la prova
  del modellatore su un'app reale (`test.todo` con `hub(8)` in `layout.test.mjs`).
- `unique` di classe usa `nulls not distinct` — nei lookup la colonna vuota è la riga di default e non deve
  ripetersi. Il drift segnala solo i gruppi del metamodello mancanti nel database, non quelli presenti solo nel
  database, per non rompere l'allineamento delle app esistenti.
- Niente vista `matrix` generata dal modeler — il metamodello descrive solo la struttura; la pagina a matrice è
  codice dell'app.
- `/core:ship` ha `disable-model-invocation`: invocarla vale come richiesta di push e PR, non di merge.
- Hook in Python con sola libreria standard; permessi via `install.sh`; il modellatore è vendorizzato nell'app e
  salva proposte.

## Problemi aperti
- I tre branch alzano tutti `core` a 0.5.0 e `modeler` a 0.7.0: va rilasciato un branch alla volta (vedi
  Prossimi passi), altrimenti il pre-push blocca o le versioni si sovrappongono.
- Bus dell'editor non fatto.
- Il modellatore non è ancora installato in nessuna app reale (`/admin/model` mai provato con Supabase reale);
  guest-invitations-af può adottare `unique` di classe per le tariffe dopo `/modeler:install`.
- Le app nate con appforge (`guest-invitations-af`, `order-management`) citano ancora appforge.
- Branch locale `feat/exclude-columns` senza commit oltre `main`: da cancellare se non serve.

## Prossimi passi
1. Committare questo handoff (`docs: update handoff`), sul branch corrente.
2. Rilascio in sequenza, per ogni branch nell'ordine 1 → 2 → 3:
   `git switch <branch> && git merge main` (risolvere `NOTES.md` tenendo tutte le voci),
   `python3 scripts/release.py --write`, test, poi `/core:ship` (merge su `main` solo con conferma).
3. `/modeler:install` su guest-invitations-af con `supabase start`: prova di `/admin/model`, delle proposte, del
   nuovo layout e di `unique` di classe sulle tariffe; poi decidere il bus.
4. Provare `/core:db-push` alla prima migrazione da portare in produzione.
5. Plugin `mde` (Eclipse/EMF, Epsilon) e `research`.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test con database: `docker run -d --rm --name modeler-pg-test -e POSTGRES_PASSWORD=pg -p 55499:5432 postgres:16`,
poi `MODELER_PG=postgresql://postgres:pg@localhost:55499/postgres python3 -m unittest discover -s plugins/modeler/tests`
(non usare il database Supabase di un'app per i test).
File da leggere per primi: `CLAUDE.md`, `NOTES.md`, `plugins/core/context/conventions.md`,
`plugins/modeler/README.md`, `plugins/core/skills/harness-review/SKILL.md`.
