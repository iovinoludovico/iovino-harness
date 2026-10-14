# appforge behaviour model: the language of `app.yaml`

`app.yaml` describes how one application behaves. In split apps (with `domain.ecore.yaml`, see
`ecore-notation.md`) the structure — classes, attributes, references, enums — lives in the metamodel and
`entities.<Class>` here only adds behaviour (kind, code_prefix, display, scope_field, permissions, workflow,
indexes, icon, menu, ui); fields are never declared here. In single-file apps `app.yaml` holds the fields too
(the `fields` syntax below). Every section is optional except `app` and `entities`.
Labels are either a string (default locale) or a map `{it: …, en: …}`; missing locales fall back to the first one.
Run `python3 <plugin>/scripts/appforge.py validate` after every change (the PostToolUse hook does it too).

## app
```yaml
app:
  name: Inviti ospiti                 # display name
  slug: guest-invitations             # kebab-case: registry key, Docker image suffix, Supabase project id
  description: …
  locales: [it, en]                   # first = default (UI fallback, external recipients)
  timezone: Europe/Rome
  auth:
    providers: [google]               # google | email (magic link)
    allowed_domains: [gssi.it]        # empty = any domain (enforced by the Supabase "before user created" hook)
    approval: manual                  # manual: an admin enables new users | auto
    admins: [someone@gssi.it]         # enabled as admin at their first sign-in
  events:
    source: /invitations              # CloudEvents `source`
    type_prefix: it.gssi.invitations. # CloudEvents `type` = prefix + event type
    retention_days: 365
  deploy:
    image: ghcr.io/gssi/guest-invitations   # images <image>-web and <image>-dispatcher
    base_url: https://…                     # links inside events
    platforms: [linux/amd64]                # linux/arm64 for a Raspberry Pi
```

## roles and scope
`admin` is implicit and can do everything. Other roles are global or **scoped**: a scoped role is assigned
for one row of the *scope entity* (e.g. director *of* a department, manager *of* an office).
```yaml
roles:
  office:   { label: { it: Uffici, en: Offices } }
  director: { label: Direttore, scoped: true }
scope: Department            # or { entity: Department }; must be a registry entity
```

## enums
```yaml
enums:
  Priority: [low, medium, high]                       # shorthand
  BookingMethod:
    values:
      - { key: agency, label: { it: Tramite agenzia, en: Through the agency } }
```

## entities
PascalCase names. `User` is built in (the application users, table `profiles`): reference it, never declare it.
```yaml
entities:
  Invitation:
    kind: process               # registry (no workflow, default) | process (needs `workflow`)
    label: { it: Invito, en: Invitation }
    plural: { it: Inviti, en: Invitations }
    table: invitations          # default: snake plural of the name
    code_prefix: INV            # codes INV-2026-0001 (column `code`)
    display: code               # field used as title (default: code, else first string field)
    scope_field: department     # reference to the scope entity: scoped roles apply per row
    icon: mail
    menu: true                  # listed in the navigation
    fields: { … }
    indexes: [[department, state]]
    permissions:
      read:   [field:issuer, creator, director, office]   # default [all]
      create: [issuer, office]                            # default [admin]
      update: [office]                                    # default [admin]; plus state `editable_by`
      delete: [admin]                                     # default [admin]
    workflow: { states: …, transitions: … }
```
Standard columns (never declare them): `id`, `state` (process), `code` (with `code_prefix`), `created_by`,
`created_at`, `updated_at`.

### fields
```yaml
fields:
  title:      { type: string, required: true, max_length: 120 }
  notes:      text                                  # shorthand: just the type
  email:      { type: email, unique: true }
  amount:     { type: money, min: 0 }
  start_date: { type: date, required: true }
  urgent:     { type: bool, default: false }
  priority:   { type: enum, enum: Priority, default: medium }
  guest:      { type: ref, to: Guest, required: true, on_delete: restrict }   # restrict | set_null | cascade
  issuer:     { type: ref, to: User }
  funds:      { type: ref, to: Fund, many: true }     # many-to-many (join table <table>_<field>)
  confirmed_at: { type: datetime, readonly: true }   # set only by reactions or code
  extra:      json
```
Types: `string text email url int number money bool date datetime enum ref json`.
Other keys: `label`, `help`, `list` (column in the generic list; default: first four fields), `min`, `max`,
`renamed_from` (previous key: the generator renames the column and keeps the data; also valid on states).

### principals (who)
Used by permissions, `owner`, `editable_by`, `by`, and notification recipients:
| principal | meaning |
|---|---|
| `all` | any enabled user |
| `admin` | administrators (always allowed anyway) |
| `<role>` | users with the role; scoped roles only in the row's scope |
| `creator` | the user who created the row |
| `field:<ref>` | the user referenced by the field (`to: User`); in notifications also an entity with an `email` field (e.g. `field:guest`) |
| `email:<address>` | a fixed address (notifications only) |

A user who can act on a record (state owner, `editable_by`, transition `by`) can also read it.

### workflow (process entities)
```yaml
workflow:
  states:
    draft:      { kind: initial, label: Bozza, owner: [field:issuer], editable_by: [field:issuer, creator] }
    pending:    { label: In attesa, owner: [director], reminder: { after_days: 7, template: director_reminder } }
    approved:   { color: "#16a34a" }
    closed:     { kind: final }
  transitions:
    submit:
      label: { it: Emetti, en: Issue }
      from: draft                 # a state, a list, or "*" (every non-final state)
      to: pending
      by: [field:issuer, creator] # who can fire it (admin always can)
      comment: optional           # optional | required | none
      guard:                      # must hold: otherwise the action is disabled and says what is missing
        - { field: guest, op: is_set }
      condition:                  # must hold: otherwise the action is hidden (alternative routes)
        - { field: accommodation, op: eq, value: agency }
      emits: [invitation.submitted_late]   # extra declared events
    expire:
      from: pending
      to: closed
      trigger: { at: end_date, offset: "+1d" }   # timed: run by the system (pg_cron, daily)
```
Exactly one `initial` state; every state reachable from it. `owner` drives the "waiting for me" inbox and the
reminders. Clause operators: `eq neq in not_in gt gte lt lte is_true is_false is_set is_empty`.

## events
Every entity emits `<entity>.created`, `<entity>.updated` (with `changed`) and `<entity>.deleted`; a process also
`<entity>.transitioned`, `<entity>.completed` (final state) and `<entity>.reminder`. `<entity>` is the snake_case
name (`RoomBooking` → `room_booking`). Declare only additional events:
```yaml
events:
  invitation.visit_ended: { description: Fine visita, category: workflow }
  invitation.starts_soon: La visita inizia tra tre giorni    # shorthand: description
```
They are emitted by transitions (`emits`), by `schedule` reactions, or by hand-written SQL with
`public.emit_entity_event('<entity>', id, '<type>', extra)`.

## reactions
```yaml
reactions:
  - name: notify_director            # snake_case, unique
    on: invitation.transitioned      # an event type
    when:                            # optional filters
      transition: [submit]           # workflow events: transition key(s)
      to: [pending]                  # workflow events: target state(s) (reminders: the state)
      from: [draft]
      clauses: [ { field: urgent, op: is_true } ]   # on the record, after the change
    do: notify
    to: [director, email:segreteria@gssi.it]
    template: invitation_to_approve  # the subscriber (n8n) picks the email template from this key
```
| do | parameters | effect (same transaction as the event) |
|---|---|---|
| `notify` | `to`, `template` | recipients resolved now and embedded in the event (`data.recipients`: email, locale, template_key); delivery is done by a webhook subscriber |
| `set` | `set: {field: value}` | updates the record; values may be `=now`, `=today`, `=actor`, `=null` |
| `transition` | `transition` | fires a transition as the system (skipped if not available) |
| `schedule` | `event`, `at: <date field> ± N(d|h|m)` | stores a future event (fired by pg_cron every 5 min); re-scheduled if the record changes |
| `broadcast` | `channel` | Supabase Realtime broadcast with type and ids only (the UI re-reads data via RLS) |
| `custom` | `handler` | calls `public.custom_<handler>(event)`: a stub is generated once, the body is hand-written (/appforge:custom) |

The validator rejects cycles between reactions (e.g. a `set` that triggers `updated` that triggers the same `set`).

## subscriptions
Suggested webhook subscribers (documentation; created in the app under *Integrations*):
```yaml
subscriptions:
  - { name: n8n, url_env: N8N_WEBHOOK_URL, events: ["invitation.*", "user.*"] }
```

## ui (mapping to UI components)
Per entity, optional: `ui: {view, views, kanban: {group_by}, calendar: {start, end}, cards: {title, subtitle,
image}, related: [Entity.field] | false, widgets: {field: widget}}`. Defaults come from the model (see the
`ui` skill); `appforge ui suggest` proposes alternatives. UI-only changes never produce migrations.

## What the model cannot express (on purpose)
Computed fields, cross-entity aggregates, complex validation, external calls. Put them in hand-written code:
see the `architecture` skill ("Where code goes").
