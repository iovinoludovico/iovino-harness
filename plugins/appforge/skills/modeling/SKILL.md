---
name: modeling
description: Reference of the appforge modeling languages - the domain metamodel (domain.ecore.yaml, Ecore notation) and the behaviour model (app.yaml - roles, permissions, workflows, events, reactions, webhooks, UI mapping). This skill should be used whenever domain.ecore.yaml or app.yaml is read or written, when the user describes a domain ("abbiamo ordini che passano da bozza ad approvato…", "aggiungi un campo", "chi può approvare") or asks how to model something with appforge.
---

# Modeling with appforge

An appforge application is described by two files that together are the single source of truth:
- `domain.ecore.yaml` — the **metamodel** (structure, Ecore notation): read `references/ecore-notation.md`;
- `app.yaml` — the **behaviour** attached to its classes (app settings, roles, permissions, workflows, events,
  reactions, webhooks, UI mapping): read `references/metamodel.md`.
Older apps keep everything in `app.yaml` (`entities.<E>.fields`); `appforge metamodel extract` splits them.
Examples: `references/example-guest-invitations.ecore.yaml` + `references/example-guest-invitations.yaml`
(split; full process with workflow, reminders, scheduled events, UI views), `references/example-acs.yaml`
(single file; registries, scoped roles, realtime broadcast, custom handler).

## How to model
1. Name the concepts as the user does (Italian or English), as PascalCase entities. Registries are master data
   (people, places, catalogues); processes have a lifecycle (requests, orders, bookings) and get a workflow.
2. Model relationships as references in the metamodel (multiplicity, containment, opposite); in single-file
   apps as `ref` fields (`many: true` for many-to-many). `User` is the built-in user.
3. Decide who can do what with principals (roles, `creator`, `field:<ref to User>`). If authority depends on an
   organisational unit (department, office, lab), declare it as `scope` and mark those roles `scoped: true`.
4. For processes: states with `owner` (whose desk it is on), transitions with `by`, `guard` (requirements) and
   `condition` (alternative routes); timed transitions for deadlines; reminders for stuck states.
5. Side effects are reactions to events. External effects (emails, APIs) are `notify` or webhook subscribers,
   never calls from the database. Anything not expressible becomes `custom`.
6. Provide labels in every locale of `app.locales`.

## Rules
- Validate after each edit: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/appforge.py" validate <app.yaml>` (if the
  variable is not expanded, the plugin root is two directories above this skill's base directory).
- Never declare standard columns (`id`, `state`, `code`, `created_by`, `created_at`, `updated_at`) nor the
  automatic events (`<entity>.created|updated|deleted|transitioned|completed|reminder`).
- Keep the user's shorthand when editing by hand; the Studio rewrites the file in expanded form.
- Renaming or removing fields/entities of an app already generated is allowed: generation will produce a
  manual migration to complete (see the `generate` skill). Warn the user that data may be involved.
- When the user's description is ambiguous on authority (who approves, who sees what), ask: permissions are the
  part of the model with the highest cost of a wrong guess.
