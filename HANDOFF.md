# Handoff — sviluppo dell'harness iovino-harness
_Aggiornato: 2026-10-14 · branch `main`_

## Obiettivo
Marketplace personale di plugin per Claude Code, installabile su ogni computer con `./install.sh`:
convenzioni e guardrail comuni (`core`) e sviluppo model-based dello stack Supabase + Next.js (`appforge`).
Si raffina un pezzo alla volta; poi arriveranno i plugin `research` e `mde`.

## Stato
- `plugins/core`: convenzioni iniettate a inizio sessione (`context/conventions.md`, inclusa la regola "i modelli
  guidano lo sviluppo, le personalizzazioni si dichiarano in docs/customizations.md con CUSTOM(<id>)"),
  hook Python (`scripts/hook.py`: session, guard-file, guard-bash, format), agenti `code-reviewer` e `debugger`,
  skill `project-init`, `handoff`, `commit`, `harness-note`.
- `plugins/appforge` (v0.2.0): metamodello `domain.ecore.yaml` + comportamento `app.yaml`, generatore,
  modellatore web, mappatura UI, adozione di app esistenti, controlli di allineamento. Dettagli e storia in
  `plugins/appforge/HANDOFF.md` (sezione 10 per le ultime novità).
- `install.sh`: registra il marketplace dal clone (caricato in place), installa `core` e `appforge`, unisce i
  permessi consigliati in `~/.claude/settings.json` (backup automatico).
- Verificato: test core (`python3 -m unittest discover -s tests`), test appforge
  (`cd plugins/appforge && APPFORGE_PG=postgresql://postgres:postgres@127.0.0.1:5432/postgres python3 -m unittest discover -s scripts/tests`, 25 test),
  `claude plugin validate .`, e2e con `claude -p --plugin-dir`.

## Decisioni
- Hook in Python con sola libreria standard: nessuna dipendenza sui computer.
- Permessi via `install.sh` (i plugin non possono impostarli); convenzioni via hook SessionStart (il CLAUDE.md
  di un plugin non viene caricato).
- Metamodello in YAML con concetti Ecore (scelta dell'utente), comportamento separato come genmodel.
- Il modellatore nell'admin crea proposte: l'app cambia solo passando dal repository (modifica + deploy).

## Problemi aperti
- Pagine nuove delle app generate (viste kanban/calendario/schede, pannelli correlati, `/admin/model`) mai
  provate con un Supabase reale: solo type-check, lint, test e build.
- `/appforge:adopt` non ancora provato su guest-invitations reale (serve il suo Supabase locale).

## Prossimi passi
1. Pubblicare il repo su GitHub (privato) e installarlo sugli altri computer.
2. `/appforge:adopt` su guest-invitations, in un worktree, con `supabase start`.
3. Prova completa di un'app generata con `supabase start` (login, liste, kanban, calendario, modellatore).
4. Rivedere `NOTES.md` e applicare le lezioni a convenzioni, hook e skill.
5. Plugin `mde` (Eclipse/EMF, Epsilon) e `research`.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
File da leggere per primi: `README.md`, `plugins/core/context/conventions.md`, `plugins/appforge/HANDOFF.md`.
