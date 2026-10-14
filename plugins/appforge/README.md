# appforge

A model-driven generator and manager of event-driven web applications, packaged as a Claude Code plugin.

You describe the **domain** in two files, as in EMF (`.ecore` + `.genmodel`): the **metamodel**
`domain.ecore.yaml` (classes, attributes, references with multiplicity/containment/opposite, enums,
inheritance — Ecore notation in YAML, exportable to `.ecore`) and the **behaviour** `app.yaml` (roles,
permissions, workflows, events, reactions, webhooks for n8n, UI mapping); appforge generates an application with a fixed reference architecture, distilled from
`guest-invitations` and `ACS-GSSI`:

- **Supabase Postgres** as the brain: tables and references, row-level security from the permission model,
  a workflow engine (transitions with guards/conditions, timed transitions, reminders, history), a
  **transactional outbox** with internal reactions and pg_cron jobs;
- **Next.js 16** web app with generic pages driven by the metamodel (lists, forms, workflow actions, history,
  inbox), user approval and roles, webhook integrations, i18n;
- a **dispatcher** delivering signed CloudEvents to subscribers such as n8n;
- Docker images, GitHub Actions CI/CD to GHCR, production compose with Watchtower.

Every generated app is an **independent repository** that lives on its own. The plugin keeps a registry of them
and lets you evolve each one by changing its model: additive changes become migrations automatically,
destructive ones become a hand-written migration that Claude completes with you.

## Ways to model
- **From the prompt** — `/appforge:metamodel "una Persona ha associato un Account…"` writes the metamodel,
  asking the ambiguities that matter (multiplicity, containment, opposite, enum vs class);
  `/appforge:spec` (guided interview) and `/appforge:model "<change>"` for the behaviour.
- **Web modeler in every app** — `/admin/model`: class diagram editor with workflow, events and webhooks shown
  on each class. Saving creates a *proposal* (a file in development, a `model_change_requests` row in
  production) that the developer applies with `/appforge:metamodel apply`: the app never drifts from the model.
- **Graphical Studio** — `/appforge:studio`: entity diagram, workflow editor, events and reactions, YAML,
  generation preview, registry of all apps. Local web UI on 127.0.0.1.
- **Text** — edit `app.yaml` directly (JSON Schema in `.appforge/app.schema.json` for editor completion).

All three write the same file and use the same validator.

## Always aligned
- generated files and migrations are protected by a hook and hashed in `.appforge/lock.json`;
- `npm run check:model` (in CI) fails if the model changed without regenerating or a generated file was edited;
- proposals and Studio saves are refused when they would break `app.yaml` (a guard, permission, reaction or
  UI setting referring to a removed feature);
- adopted apps: `appforge metamodel drift --db <DSN>` compares the metamodel with the live schema.

## UI mapping
Every concept gets a component by a default mapping (type, constraints, relations, workflow); `ui` in
`app.yaml` overrides it per entity and `appforge ui suggest` proposes alternatives (calendar for date ranges,
kanban for workflows and status enums, cards, related panels for inverse references, radio, slider…).

## Commands (skills)
| Command | What it does |
|---|---|
| `/appforge:metamodel <description\|apply\|show>` | metamodel from natural language; applies modeler proposals |
| `/appforge:adopt [app]` | brings an existing hand-written app under the metamodel (reverse engineering, modeler, drift) |
| `/appforge:ui [suggest\|request]` | shows and changes the UI mapping of the model |
| `/appforge:new-app [dir] [description\|app.yaml]` | creates a new app (model → scaffold → generation → registry) |
| `/appforge:spec [description]` | interview that writes or extends `app.yaml` |
| `/appforge:model <change>` | applies a model change described in words, previews its effect |
| `/appforge:generate [app]` | generates migrations and artefacts; completes manual migrations |
| `/appforge:custom <handler>` | implements a `custom` reaction or other hand-written SQL, with tests |
| `/appforge:check [app]` | model, generated files, i18n, migrations on a scratch DB, tests |
| `/appforge:apps [list\|show\|add\|remove]` | registry of the generated apps |
| `/appforge:studio [app]` | starts the graphical Studio |
| `/appforge:upgrade [app]` | moves an app to the current generator and template |

Knowledge skills loaded automatically: `modeling` (the language of `app.yaml`), `architecture` (the reference
architecture and where hand-written code goes).

Agents: `domain-modeler`, `sql-engineer`, `ui-engineer`, `architecture-reviewer`.

Hooks: block edits of generated files and migrations (PreToolUse), validate `app.yaml` after every edit
(PostToolUse), print the app's state when a session starts inside an app (SessionStart).

## Requirements
- Python 3.10+ (PyYAML is used if installed, otherwise the vendored pure-Python copy).
- For the generated apps: Node 20.9+, the Supabase CLI and Docker for local development.
- Optional: `psql` and a PostgreSQL server for `check --db` (`APPFORGE_PG=postgresql://user:pass@host:5432/postgres`).
- `APPFORGE_HOME` changes the registry location (default `~/.appforge`).

## CLI
Everything the skills do is available directly:
```bash
python3 scripts/appforge.py validate examples/guest-invitations/app.yaml
python3 scripts/appforge.py new ~/apps/inviti --model examples/guest-invitations/app.yaml
python3 scripts/appforge.py generate ~/apps/inviti --dry-run
python3 scripts/appforge.py status inviti        # by slug, path, or current directory
python3 scripts/appforge.py check inviti --db
python3 scripts/appforge.py apps
python3 scripts/appforge.py studio
```

## Layout
```
.claude-plugin/plugin.json
skills/            commands and knowledge (SKILL.md + references)
agents/            subagents
hooks/hooks.json   guards
scripts/appforge/  model, validator, SQL/TS generators, evolution diff, registry, Studio server
scripts/vendor/    pure-Python PyYAML (fallback)
studio/            Studio web UI (no build step, no external assets)
schema/            JSON Schema of app.yaml
templates/app/     reference application template
examples/          guest-invitations and acs models
```

## Status
Version 0.1.0. Verified: both examples generate, migrations apply on PostgreSQL 16 (with Supabase stubs),
workflow/permissions/events/reactions exercised through PostgREST, the generated apps pass `tsc`, ESLint,
Vitest and `next build`. Not yet verified end to end against a running Supabase stack (Auth + Realtime).
