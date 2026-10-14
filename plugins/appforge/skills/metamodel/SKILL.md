---
name: metamodel
description: Creates or evolves the domain metamodel (domain.ecore.yaml, Ecore notation) from a natural-language description of the domain, applies proposals saved by the web modeler, and shows the metamodel (Emfatic, class diagram). This skill should be used when the user describes domain concepts and relations ("una Persona ha associato un Account", "un ordine contiene più righe", "aggiungi la classe Fornitore"), asks for the metamodel or the domain model, or invokes /appforge:metamodel.
argument-hint: "<descrizione del dominio> | apply [proposta] | show"
---

# Domain metamodel from the prompt

Request: `$ARGUMENTS`

CLI: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/appforge.py" metamodel …` (if the variable is not expanded, the
plugin root is two directories above this skill's base directory). Read
`${CLAUDE_PLUGIN_ROOT}/skills/modeling/references/ecore-notation.md` before writing the metamodel.

## 1. Where
Find the metamodel: `domain.ecore.yaml` in the current directory or its parents, or the app given (slug or
path). Three cases:
- **generated app** (`app.yaml` + `.appforge/lock.json`): the metamodel drives the generator;
- **adopted app** (only `domain.ecore.yaml`): it documents a hand-written app; changes are implemented by hand;
- **none yet**: a new app (follow with `/appforge:new-app`) or an existing app to adopt (`/appforge:adopt`).
  A generated app with a single-file `app.yaml` is split first: `metamodel extract <app>`.

## 2. `show`
`metamodel show --format emfatic` (readable text) and `--format mermaid` (class diagram: render it inline in
the reply when the client supports Mermaid). `--format storage` shows tables and columns.

## 3. `apply [file]` — proposals from the web modeler
Proposals come from the admin modeler (`.appforge/proposals/*.json` in development, `metamodel pull --db <DSN>`
for production) or from a downloaded file. Run `metamodel apply <file>` (dry run): show the user the changes
and the validation. If they agree, `metamodel apply <file> --write`, then continue from step 6.

## 4. From the description to the metamodel
1. Extract concepts (classes), their data (attributes) and the relations between them, using the table
   "From the user's words to the metamodel" of the notation reference. Keep the user's names and language
   (Italian names → `language: it`).
2. **List the ambiguities that change the structure** (multiplicity, containment vs reference, opposite,
   attribute vs class, enum vs class, User vs a person class, inheritance vs type enum). Ask them in **one**
   round, at most 4 multiple-choice questions, each with your recommended option first; settle the minor ones
   yourself and list them as assumptions. Example for "una Persona ha associato un Account":
   - Account obbligatorio per ogni Persona? (`[1]` / `[0..1]`)
   - Una Persona può avere più Account? (`[0..1]` / `[*]`)
   - Dall'Account si risale alla Persona? (opposite `persona`)
   - L'Account si cancella con la Persona? (containment)
3. Write or edit `domain.ecore.yaml` (minimal edits on an existing file; renames get `renamed_from`). The
   PostToolUse hook validates it: fix any error at once.
4. Show the result as Emfatic text (`metamodel show --format emfatic`) and the class diagram, plus how it will
   be stored (`--format storage`) when the user cares about the database.

## 5. Keep behaviour aligned
Workflows, permissions, reactions and UI in `app.yaml` refer to features of the metamodel. After a change:
`metamodel validate` checks the pair; if a guard, permission, reaction or UI setting refers to something
removed or renamed, update `app.yaml` in the same change (or ask the user). New process classes need a
workflow (`/appforge:model`); new date ranges, status enums, images or containments may deserve a UI view
(`appforge ui suggest`, `/appforge:ui`).

## 6. Make the application follow
- **Generated app**: `appforge generate <app> --dry-run`, explain the effect (tables, columns, manual
  migrations for drops/renames/required fields), then generate on confirmation (`generate` skill). The CI job
  `npm run check:model` fails until the app is regenerated.
- **Adopted app**: implement the change by hand (migration in `supabase/migrations/`, types, pages), then
  `metamodel sync` (refreshes the admin modeler) and `metamodel drift --db <local DSN>` until it reports
  "aligned".
- Optional: `metamodel export -o <name>.ecore` for Eclipse EMF / Epsilon tools.

Report: the metamodel in Emfatic form, the assumptions made, and what changes in the application.
