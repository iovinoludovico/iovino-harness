---
name: check
description: Verifies an appforge application — model validity, generated files untouched, pending manual migrations, translation parity, migrations applied on a scratch database, and the app's own tests and type checks. This skill should be used when the user asks "controlla l'app", "è tutto a posto?", "verifica le migrazioni", before a deploy, or invokes /appforge:check.
argument-hint: "[app]"
---

# Check an appforge app

1. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/appforge.py" check <app>` — model, lock, generated-file hashes,
   manual migrations still containing `TODO(appforge)`, i18n key parity.
2. Database: `appforge check <app> --db` applies every migration (with Supabase stubs) to a scratch database.
   Needs `psql` and a server: set `APPFORGE_PG=postgresql://user:pass@host:5432/postgres` (e.g. the local
   Supabase DB `postgresql://postgres:postgres@127.0.0.1:54322/postgres`). If unavailable, say so and suggest
   `supabase db reset`.
3. App tests when `node_modules` exists: `npm test`, `npm run typecheck`, `npm run lint`; `supabase test db`
   if Supabase is running.
4. Optionally run the `architecture-reviewer` agent for a review of hand-written code against the
   architecture rules.
5. Report problems first, each with the concrete fix; then what passed.
