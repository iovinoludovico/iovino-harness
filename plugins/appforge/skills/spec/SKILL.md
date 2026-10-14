---
name: spec
description: Builds or extends the model of an appforge application (metamodel domain.ecore.yaml + behaviour app.yaml) through a short guided interview with the user. This skill should be used when the user describes a new application domain in natural language, asks "aiutami a modellare il dominio", "intervista per il modello", or invokes /appforge:spec.
argument-hint: "[descrizione del dominio]"
---

# Domain interview → app.yaml

Starting description: `$ARGUMENTS`

Load the `modeling` skill first (metamodel reference and examples).

## Interview (ask only what the description leaves open; group questions, max 4 at a time)
1. **Concepts**: which things are managed? Which are master data (registries) and which have a lifecycle
   (processes)? Key fields and references between them.
2. **People and authority**: roles; is authority bound to an organisational unit (department, office…) →
   `scope` + scoped roles? Who creates, who reads, who edits?
3. **Lifecycle** of each process: states, who has the record in charge in each state, transitions and who fires
   them, requirements (guards) and alternative routes (conditions), deadlines (timed transitions), reminders.
4. **Notifications and effects**: who is told what and when (`notify` + template keys), automatic updates
   (`set`), follow-ups (`schedule`), live screens (`broadcast`), anything needing code (`custom`), external
   systems (webhook subscribers).
5. **App settings**: name, languages, login (Google / email link), allowed email domains, first admin.

## Output
- Structure first: write `domain.ecore.yaml` following the `metamodel` skill (concepts, relations,
  multiplicities, containment; ask the structural ambiguities in one round).
- Then `app.yaml` with the behaviour only (app settings, roles, permissions, workflows, events, reactions,
  subscriptions for n8n, `ui` where the defaults do not fit). New app: in the target directory; existing app:
  edit in place, keeping the user's comments and shorthand. Labels in every locale.
- Validate with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/appforge.py" validate <path>` and fix errors.
- Summarise the model in a short table (entities, roles, workflows) and list the assumptions you made, so the
  user can correct them before generation. Suggest `/appforge:studio` to review it graphically.
