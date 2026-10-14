---
name: apps
description: Manages the registry of applications generated with appforge — list them with their state, show details, register an existing app, remove one from the registry, open one to work on it. This skill should be used when the user asks "quali app ho generato", "stato degli applicativi", "registra questa app", "apri l'app X", or invokes /appforge:apps.
argument-hint: "[list | show <app> | add <cartella> | remove <slug>]"
---

# Application registry

Arguments: `$ARGUMENTS` (default `list`).

The registry (`~/.appforge/registry.json`, or `$APPFORGE_HOME/registry.json`) only indexes the apps: each app is
an independent repository with its own `app.yaml` and `.appforge/lock.json`.

- `list`: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/appforge.py" apps --json`. Present a compact table: name,
  slug, state (up to date / model changed / never generated / problems / missing), evolution, path. For apps
  with problems, show them and propose the fix (`/appforge:generate`, complete a manual migration…).
- `show <app>`: `appforge apps show <app>` plus `appforge describe <app>`.
- `add <folder>`: `appforge apps add <folder>` (the folder must contain `app.yaml`).
- `remove <slug>`: confirm first; only the registry entry is removed, never the files.
- To work on an app, `cd` into its path; the SessionStart hook prints its state when a session starts there.
- For a visual overview of all apps and their models suggest `/appforge:studio`.
