---
name: new-app
description: Creates a new appforge application (an independent repository) from a domain model, scaffolding the reference architecture and generating database, events, UI metamodel and docs. This skill should be used when the user asks to "creare una nuova app", "generare un applicativo", "nuovo progetto con appforge", or invokes /appforge:new-app.
argument-hint: "[cartella] [descrizione del dominio o percorso di un app.yaml]"
---

# New appforge application

Arguments: `$ARGUMENTS`

`appforge` CLI: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/appforge.py"` (if the variable is not expanded, the
plugin root is two directories above this skill's base directory). Python 3.10+ is enough (YAML is vendored).

## Steps
1. **Target directory.** Use the folder given in the arguments; otherwise ask for it (default: a new folder
   named after the app slug in the current directory). It must be empty or not exist.
2. **Model.** If the arguments point to an existing `app.yaml` (with or without `domain.ecore.yaml` beside it),
   use it. Otherwise build the model with the `spec` skill: the metamodel `domain.ecore.yaml` from the
   description (`metamodel` skill) and the behaviour `app.yaml`, both in the target directory. Load the
   `modeling` skill before writing YAML.
3. **Validate**: `appforge validate <dir>/app.yaml`. Fix every error; show warnings to the user.
4. **Create**: `appforge new <dir> --model <dir>/app.yaml` (scaffolds the template, generates the initial
   migrations and artefacts, registers the app in `~/.appforge/registry.json`).
5. **Repository**: `git init`, first commit ("Initial appforge generation") unless the user said otherwise.
6. **Optional checks** (ask, they take time): `npm install`, `npm test`, `npm run typecheck`;
   `appforge check <dir> --db` if a PostgreSQL is reachable (`APPFORGE_PG=postgresql://…/postgres`).
7. **Report** in a few lines (mention the web modeler at `/admin/model`, the UI suggestions of
   `appforge ui suggest`, and that CI runs `npm run check:model`): where the app is, entities and workflows generated, custom handlers to implement
   (`/appforge:custom`), next commands (`supabase start`, `supabase db reset`, `npm run dev`), and that the model
   can be edited graphically with `/appforge:studio`.

## Notes
- The app does not depend on the plugin at run time: it is a normal Next.js + Supabase repository.
- Deploy: GitHub Actions builds `<image>-web` and `<image>-dispatcher`; `deploy/docker-compose.prod.yml`
  runs them with Watchtower. Remind the user to set the repository Variables `NEXT_PUBLIC_SUPABASE_URL`,
  `NEXT_PUBLIC_SUPABASE_ANON_KEY` before the first push to `main`.
