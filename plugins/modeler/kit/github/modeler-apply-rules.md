# Rules for the modeler-apply run (CI, unattended)

You run inside GitHub Actions, started by the "Apply" button of the admin modeler. Nobody can answer a question:
never ask, never wait. Decide with the app's conventions (`CLAUDE.md`, the existing migrations and pages) and say
in the summary what you decided.

Do, in this order:
1. `npm run model:apply -- <the proposal file given in the prompt> --write` (only that proposal; the dry run first
   if you want to read the changes). If apply refuses to write (data loss, layout of the file, invalid behaviour),
   stop and write why in `.modeler/apply-summary.md`: the workflow reports the failure.
2. `npm run model:migrate -- --name <first 8 chars of the proposal id>_<short slug> --write`, then resolve every
   `TODO(modeler)` line following the app's conventions (RLS policies like the neighbouring tables, grants,
   backfills with a sensible default). **Never uncomment a drop, a type change or any step that loses data**: leave
   those lines commented and list them in the summary for the reviewer.
3. `npm run model:sync`; regenerate the types the app uses (`supabase gen types` or the app's script, see
   `package.json`); update queries, forms and pages that use the new structure, following the existing patterns
   (`entityListHref`, generated views in tabs next to hand-written ones, `CUSTOM(<id>)` for what the model does not
   express). Behaviour changes: `npm run model:engine -- --write` only if the app uses the generated engine (a
   hand-written engine, `CUSTOM(*-workflow)`, is never replaced: describe the SQL to change instead).
4. Apply the migration to the local database (`npx supabase migration up` or `npx supabase db reset`) and run
   `npm run model:drift` until it reports "aligned"; then typecheck, lint and the tests of the app. Fix what you
   broke; do not disable tests.
5. Commit everything (including `.modeler/proposals/applied/<file>`) as one Conventional Commits commit in English
   (`feat(model): …`), body with the proposal note and the decisions taken. Do not push, do not open the pull
   request, do not run `supabase db push`, do not call `/core:ship`, `/core:db-push` or `/core:commit`: the
   workflow pushes and opens the PR.
6. Write `.modeler/apply-summary.md` (it becomes the PR body): what changes in the model, the migration and the
   code; the `TODO(modeler)` lines left commented and why; what the reviewer must do before the merge
   (`/core:db-push`) and after the deploy (`npm run model:done -- --write`).

Keep the run short: no exploration beyond what the change needs, no refactoring, no unrelated fixes.
