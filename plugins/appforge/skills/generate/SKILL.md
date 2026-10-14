---
name: generate
description: Regenerates an appforge application from its domain model — migrations (additive deltas, full behaviour layer), event catalogue, UI metamodel, translations, docs — and completes the hand-written migrations needed by destructive changes. This skill should be used when the user asks to "rigenerare", "generare le migrazioni", "applicare il modello", after app.yaml changed, or invokes /appforge:generate.
argument-hint: "[app]"
---

# Generate

`appforge` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/appforge.py"` (plugin root = two directories above this
skill's base directory if the variable is not expanded).

1. `appforge validate <app>`; stop on errors.
2. `appforge generate <app>`. It writes, in order:
   - `*_manual_evolve_N.sql` (only for destructive/ambiguous changes, runs **before** the generated migration),
   - `*_appforge_evolve_N_types.sql` (new enum values / roles, committed first),
   - `*_appforge_evolve_N.sql` (additive structure + full behaviour layer),
   - `*_manual_evolve_N_post.sql` (backfills, runs **after**),
   and rewrites `src/lib/model.ts`, `src/lib/events/catalog.ts`, `docs/domain.md`, the `model` namespace of
   `messages/*.json`, `.appforge/lock.json`.
3. If manual migrations were created: complete them now. Load the `architecture` skill
   (`references/where-code-goes.md`). For each `TODO(appforge)` section decide with the user when data is at
   stake (rename vs drop, backfill value), write the SQL, delete the TODO lines. Moving records out of a
   removed state needs `select set_config('app.in_transition', 'on', true);` before the update.
4. New `custom` handlers (listed in the lock as `custom_handlers`) have a stub: offer `/appforge:custom`.
5. Verify: `appforge check <app>` (and `--db` with `APPFORGE_PG` if a PostgreSQL is available); if
   `node_modules` exists also `npm test` and `npm run typecheck`. In a Supabase project:
   `supabase db reset` locally, `supabase db push` for the cloud project.
6. Report: operations applied, files written, manual steps done, what to run next. Offer to commit
   ("appforge evolution #N: <summary>").

Never edit generated files to fix a problem: change `app.yaml`, or add a hand-written migration.
