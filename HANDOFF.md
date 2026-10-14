# Handoff — sviluppo dell'harness iovino-harness
_Aggiornato: 2026-10-14 · branch `feat/commit-message-suggestion`_

## Obiettivo
Marketplace personale di plugin per Claude Code, installabile su ogni computer con `./install.sh`:
convenzioni e guardrail comuni (`core`) e sviluppo model-based delle app Next.js + Supabase (`modeler`).
Si raffina un pezzo alla volta; poi arriveranno i plugin `research` e `mde`.

## Stato
- `plugins/core`: convenzioni iniettate a inizio sessione (`context/conventions.md`: il metamodello
  `domain.ecore.yaml` guida lo schema, personalizzazioni in `docs/customizations.md` con `CUSTOM(<id>)`),
  hook Python (`scripts/hook.py`: session, guard-file, guard-bash, format), agenti `code-reviewer` e `debugger`,
  skill `project-init`, `handoff`, `commit`, `db-push` (migrazioni sul Supabase cloud con anteprima e conferma),
  `harness-note` (note in `NOTES.md` di questo clone).
  Quando Claude propone commit o push mostra il messaggio di commit in un blocco copiabile (convenzione Git).
- `plugins/modeler` (v0.1.0): metamodello Ecore in YAML (`scripts/metamodel/`: notazione, mappatura su tabelle,
  reverse e drift via psql, export Ecore/Emfatic/Mermaid), kit del modellatore web (`kit/`) che `install` copia
  nell'app insieme alla CLI (`tools/modeler/`, script `npm run model:*`): l'app resta allineata senza il plugin.
  Skill `install`, `metamodel`, `apply`, `notation`; hook di validazione, promemoria sulle migrazioni, stato a
  inizio sessione (versione del modellatore vendorizzato, drift con `MODELER_DRIFT_DB`).
- appforge (generatore di app da `app.yaml`, Studio, registro) è **dismesso**: rimosso dall'harness; del suo
  codice restano solo metamodello, reverse/drift ed editor, ripuliti dal comportamento.
- Rilasci: `scripts/release.py` alza la versione dei plugin modificati (livello dai Conventional Commits, file
  gemelli come `__version__` del modeler) e crea `chore(release): …`; `.githooks/pre-push` (attivato da
  `install.sh`) blocca il push di un plugin non rilasciato; regola nel `CLAUDE.md` del repository. README con le
  due installazioni (clone + `install.sh`, marketplace GitHub `iovinoludovico/iovino-harness`).
- Verificato: test core (`python3 -m unittest discover -s tests`), test modeler
  (`python3 -m unittest discover -s plugins/modeler/tests`, 16 test; con `MODELER_PG` anche reverse e drift su
  Postgres 16 in Docker), `tsc` del kit in un'app Next di prova, editor provato in Chromium headless.

## Decisioni
- Hook in Python con sola libreria standard: nessuna dipendenza sui computer.
- Permessi via `install.sh` (i plugin non possono impostarli); convenzioni via hook SessionStart.
- Il modello è solo `domain.ecore.yaml` (struttura); workflow, permessi e pagine sono codice.
- Il modellatore è parte dell'app (codice e CLI vendorizzati); il plugin lo installa e lo aggiorna.
  File del modellatore sostituiti a ogni `install`; `access.ts` e la pagina admin restano dell'app.
- Il modellatore salva proposte: l'app cambia solo passando dal repository (metamodello + migrazione + codice).

## Problemi aperti
- Il modellatore non è ancora installato in nessuna app reale (`/admin/model` mai provato con Supabase reale).
- Le app nate con appforge (`guest-invitations-af`, `order-management`) hanno `app.yaml` e CLAUDE.md che citano
  appforge: da migrare con `/modeler:install` quando serve (metamodello dal database).

## Prossimi passi
1. Provare `/core:db-push` per davvero alla prima migrazione da portare in produzione.
2. `/modeler:install` su un'app reale con `supabase start` (prova completa di `/admin/model` e proposte).
3. Pubblicare il repo su GitHub (privato) e installarlo sugli altri computer.
4. Rivedere `NOTES.md` e applicare le lezioni a convenzioni, hook e skill.
5. Plugin `mde` (Eclipse/EMF, Epsilon) e `research`.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
File da leggere per primi: `README.md`, `plugins/core/context/conventions.md`, `plugins/modeler/README.md`.
