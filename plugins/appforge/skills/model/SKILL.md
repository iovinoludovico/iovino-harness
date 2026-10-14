---
name: model
description: Applies a change to the domain model of an appforge application from a natural-language command (add or change entities, fields, roles, permissions, states, transitions, events, reactions) and previews its effect. This skill should be used when the user asks to change an existing appforge app's domain, e.g. "aggiungi l'entità Fornitore", "il direttore deve poter rimandare indietro", "notifica gli uffici quando…", or invokes /appforge:model.
argument-hint: "<modifica al modello> [app]"
---

# Change the domain model

Request: `$ARGUMENTS`

1. Locate the app: current directory (nearest `app.yaml`), or the slug/path given; list apps with
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/appforge.py" apps` if unclear.
2. Load the `modeling` skill. Read `app.yaml` and, for context, `appforge describe <app>`. If the app has a
   `domain.ecore.yaml`, structural changes (classes, attributes, references, enums) go there through the
   `metamodel` skill; this skill edits the behaviour.
3. Edit `app.yaml` minimally (keep comments and the author's style). The PostToolUse hook validates the file:
   fix any reported error immediately.
4. Preview the consequences: `appforge generate <app> --dry-run`. Tell the user in plain words what will
   change (tables/columns added, behaviour regenerated) and flag any **manual** operation (drops, renames,
   type changes, new required fields on existing data): these need a hand-written data migration.
5. Ask whether to generate now; if yes follow the `generate` skill.

Renames: give the field or state its new key and add `renamed_from: <old key>`; the generator renames the
column (constraints, indexes, join tables) or moves the records to the new state, keeping the data. The hint
can stay in the model afterwards. Entity renames are not automatic: generation produces a manual migration.
