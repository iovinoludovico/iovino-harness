# The behaviour model: `behavior.yaml`

`domain.ecore.yaml` says *what* the domain is; `behavior.yaml`, next to it, says *what happens*: roles,
derivations of the attributes marked `derived` in the metamodel, workflows (states, transitions, guards, timed
transitions), domain events, reactions (who is notified when) and webhook subscriptions. Every name in it is a
concept of the metamodel, navigated with **typed paths**: `modeler validate` (`npm run model:validate`) checks
the behaviour against the metamodel, the PostToolUse hook does it after every edit of either file, `apply`
reports a proposal that breaks it, and CI runs the same check. A domain change that breaks a guard, a
recipient or a derivation is therefore found before the database is. From the model, `sync` generates
`docs/BEHAVIOR.md` and `src/lib/modeler/behavior.json`, `behavior --format sql|engine` the SQL and the workflow
versions of the runtime engine, `drift` compares the workflows with the versions published in the database, and
**`engine`** generates the SQL engine itself: the functions and triggers that run the behaviour in PostgreSQL.

## Syntax
```yaml
doc: Inviti dei visiting researcher, dalla richiesta al pagamento

roles:                                  # who acts, besides the built-in admin and creator
  office:   {label: {it: Uffici amministrativi, en: Administrative offices}}
  director: {scope: Department, label: {it: Direttore, en: Director}}    # held per Department

derivations:                            # formulas of the attributes `derived: true` in the metamodel
  Invitation:
    agencyBookingRequired: accommodationMethod = agency or travelMethod = agency
    fundsTotal: invitationFunds.amount.sum()
    dataComplete: reason.isSet() and (compensationType <> hourly or hours > 0) and fundsTotal = totalAmount
    compensationAmount: if compensationType = hourly then round(coalesce(hours, 0) * coalesce(hourlyRate, 0), 2) else coalesce(flatAmount, 0)
    mealsPerDay: if mealsMethod <> none then round(mealsAmount / (endDate - startDate + 1), 2) else 0

workflows:
  Invitation:
    state: state                        # the attribute holding the state: EString, or an enum whose literals are the states
    states:
      draft:    {initial: true, owner: [self.issuer], editable_by: [self.issuer, office], label: {it: Bozza, en: Draft}}
      pending:  {owner: [director], reminder: {after: 7d, template: approval_reminder}, requires: [reason, hours],
                 model: {hourlyRate: {readonly: true}, notes: {hidden: true}}}   # the class as seen from this state
      closed:   {final: true}
    transitions:
      submit:   {from: draft, to: pending, by: [self.issuer], guard: dataComplete, label: {it: Emetti, en: Submit}}
      approve:  {from: pending, to: closed, by: [director], when: not agencyBookingRequired, guard: dataComplete}
      reject:   {from: pending, to: draft, by: [director], comment: required}
      expire:   {from: pending, to: closed, at: endDate + 1d, emits: expired}      # timed: no `by`
    revert: {by: [office], final_by: [office], comment: required}

events:                                 # events a class emits besides the built-in ones
  Invitation:
    expired: {doc: Nobody approved it in time}

reactions:                              # one reaction = notify someone when an event happens
  - {name: notify_submitted, event: Invitation.transitioned, when: "transition in [submit]", notify: [director], template: invitation_submitted}
  - {name: notify_guest, event: Invitation.transitioned, when: transition = approve, notify: [self.guest.email], template: approved_guest}
  - {name: notify_reverted, event: Invitation.reverted, notify: [self.issuer], template: invitation_reverted}

subscriptions:                          # webhook subscribers (n8n, …)
  - {name: n8n, url_env: N8N_WEBHOOK_URL, events: [Invitation.*, Guest.created, user.*]}
```
Top-level keys: `metamodel doc roles derivations workflows events reactions subscriptions`. Quote an
expression that contains `[`, `:` or `#` (YAML flow syntax): `when: "transition in [submit, resubmit]"`. The
reaction key is `event`, not `on` (`on` is a boolean in YAML).

## Expressions (guards, conditions, derivations)
Read in the context of an instance of the class (`self`, optional: `dataComplete` = `self.dataComplete`).

| form | meaning | type |
|---|---|---|
| `a.b.c` | navigation through attributes and single-valued references | the type of the last feature |
| `parts.amount` | navigation through a many-valued reference: a collection (one level at most) | collection of the type |
| `x.isSet()` / `x.isEmpty()` | a single value is / is not set (a reference: linked; a string: not empty) | bool |
| `parts.notEmpty()` / `parts.isEmpty()` / `parts.size()` / `parts.amount.sum()` | on a collection | bool, bool, int, number |
| `+ - * /`, `-x` | arithmetic on numbers (`/` never truncates); `date2 - date1` is the number of days | int or number |
| `round(x)`, `round(x, 2)` | rounding | number |
| `coalesce(a, b, …)` | the first value that is set | the type of `a` |
| `if c then a else b` | a choice (lowest precedence: write `(if … then … else …) + 1`) | the type of `a`/`b` |
| `= <> < <= > >=` | comparison; `< <= > >=` only on numbers and dates | bool |
| `x in [a, b]` | membership | bool |
| `and or not ( )` | boolean operators | bool |
| `12`, `1.5`, `'text'`, `true`, `false` | literals | |
| `hourly` | a bare name is the literal of the enum on the other side of a comparison (`kind = hourly`, `kind in [a, b]`, `if … then hourly else flat`) | the enum |

Typing: numbers compare with numbers (EInt, EDouble, EBigDecimal, Money…), strings with strings (EString, Text,
Email, URL), dates with dates (Date, EDate, DateTime), booleans with booleans, an enum with its literals;
a reference is only tested with `isSet()` or navigated; a collection is only closed by its operations.
`guard`, `when` and a reaction's `when` are booleans; a derivation has the type of its attribute. Of a `User` only
`email` can be navigated. A derived attribute without a derivation (a formula the language cannot write: a lookup
in another table, an external value) is computed in code and reported as a warning.

## Principals (`by`, `owner`, `editable_by`, `notify`, `revert.by`, `revert.final_by`)
| form | meaning |
|---|---|
| `admin`, `creator` | built in: the administrators; who created the record |
| `office` | a role declared in `roles` without scope |
| `director` | a role with `scope: Department`: held per department, the record's one being the only single-valued reference of the class to Department (own or inherited) |
| `director@department` | the same, naming the reference when the class has none or several to the scope class |
| `self.issuer`, `self.department.createdBy` | the user(s) reached by a navigation (a `User` reference; through a many-valued reference, all of them) |
| `self.guest.email` | in `notify` only: also an `Email` attribute |

A principal path always starts with `self.`: this tells the reference `issuer` apart from a role named `issuer`.

## Workflows
- `state`: an attribute of the (concrete) class, `EString` or an enum. With an enum, states and literals must
  coincide, both ways.
- States: exactly one `initial: true`, at least one `final: true`, every state reachable from the initial one
  through the transitions; keys are lowercase identifiers. `owner` is who the record waits for (desk,
  reminders), `editable_by` who may edit it while it is there; `reminder: {after: 7d, template}` reminds the
  owners (durations: `7d`, `12h`, `2w`). `label`, `doc`, `color` are presentation.
- `requires: [feature, …]`: attributes or references of the class that must be set (a collection: not empty) **from
  that state on**: an implicit guard of every transition entering the state (the engine names the missing fields:
  "Required in state pending: reason, hours"; `_available_transitions` lists them as `missing`), and an invariant
  while the record is there (an update that clears a single-valued one is refused, SQLSTATE `23514`; a collection
  is checked only on entering: a deleted part is not seen by the container). Nothing is inherited: each state lists
  its own. The metamodel keeps the feature optional (`[0..1]`): `lower: 1` means required from creation, `requires`
  means required from a state. Not for derived attributes (computed after the check: test them in a guard) nor the
  state attribute; `validate` warns when the metamodel already requires the feature, when the initial state requires
  one (that is `lower: 1`) and when a guard of an entering transition repeats `x.isSet()`.
- `model: {feature: {lower: 1, readonly: true, hidden: true, in: [a, b]}}`: **the class as seen from that state**, an
  overlay that only tightens the metamodel (the metamodel holds in every state; the overlay lists the features the
  state changes; nothing is inherited between states). `lower: 1` is what `requires` abbreviates; `readonly`: an
  update that changes the feature while the record is in the state is refused (SQLSTATE `23514`); `hidden`: not
  shown by the forms and read only, the value stays; `in`: the literals a single-valued enum attribute may take there
  (checked on entering, listed as `missing`, and while there). The engine enforces all of it on single-valued
  features; on a collection only `lower: 1` (on entering) is enforced, `readonly`/`hidden` are reported to the
  application through `<entity>_field_policy(r)` (`{feature: {required, readonly, hidden, in}}` for the forms).
  `validate` reports a feature the class does not have, the state attribute, a derived attribute (only `hidden` is
  allowed), a `lower` that would relax the metamodel, `hidden` with `lower: 1`, `in` on anything but a single-valued
  enum attribute or with unknown literals; it warns about what the metamodel already says (`lower: 1`,
  `changeable: false`, all the literals) and, **along the path**, about a feature read only or hidden in a source
  state but required or narrowed in the target of a transition (set it before, or in the transition). The views:
  `npm run model:show -- --state <Class>.<state>` prints the metamodel as seen from the state (Emfatic: `[1]`,
  `readonly`, hidden features gone, `// in: a, b`); `BEHAVIOR.md`, `<BehaviorView>` and the web modeler show the
  feature × state table (● required, 🔒 read only, ○ hidden, `{a, b}`); `DOMAIN.md` adds «1 from <state>» to the
  multiplicity and the rest to the constraints.
- Transitions: `from` (one state or a list), `to`, and either `by` (principals) or `at` (a `Date`/`DateTime`
  attribute with an optional offset: `endDate + 1d`, run by the scheduler). `when` hides the transition when
  false (a condition), `guard` blocks it explaining what is missing (a requirement); `comment: required|optional`;
  `emits` lists events declared in `events.<Class>` that fire with the transition.
- `revert`: who can bring a record back to a previous state (`by`), also from a final one (`final_by`).

## Events, reactions, subscriptions
- Every class emits `created`, `updated`, `deleted`; a class with a workflow also `transitioned`, `completed`
  (a final state reached), `reverted`, `reminder`. `events.<Class>` declares the others (`visit_ended`), referenced
  by `emits` and by reactions; the application emits them with the event core (`emit_entity_event`).
- A reaction is `event: <Class>.<event>`, an optional `when` (in `<Class>.transitioned` the variable `transition`
  is the key of the transition that fired: `transition in [submit, resubmit]`), `notify` (principals) and the
  `template` the subscriber renders. Names are unique identifiers.
- The recipients of a user's action travel on the state change: a reaction on `<Class>.transitioned` with
  `when: transition = <key>`, so a subscriber of `<Class>.transitioned` finds them in `recipients` (always present,
  `[]` when nobody; a hand-written engine must do the same: `behavior --format sql`). An event a transition lists in
  `emits` carries extra data (the values chosen, the previous ones), not recipients: a reaction with `notify` on it
  hides them from the subscriber of the state change (and notifies twice if both events have recipients); `validate`
  warns. Recipients belong on a secondary event only when no transition fires (a timed or external event).
  ```yaml
  transitions:
    assign: {from: approved, to: assigned, by: [manager], emits: assigned}        # order.assigned: the assistants chosen
  reactions:
    - {name: notify_assigned, event: Order.transitioned, when: transition = assign, notify: [self.assistants.email], template: order_assigned}
  ```
- A subscription names the webhook URL by environment variable (`url_env`) or `url`, and the event patterns it
  receives: `<Class>.*`, `<Class>.<event>`, and the system patterns `user.*`, `webhook.test`.
- The texts of the notifications live in the model, not in the subscriber: `templates:` maps every `template` key
  of the reactions and reminders to its subject and body per language. Placeholders `{{…}}` are the record's own
  paths (`{{self.code}}`, `{{self.guest.email}}`, `{{self.id}}`; `{{order.code}}` with the entity key reads the
  same) and the event's variables: `actor.name`, `actor.email`, `comment`, `url` (`public.record_url(entity, id)`:
  the application defines it, one SQL map of its pages as the `core` convention on record links says; the engine
  calls it when it exists, otherwise `{{url}}` renders empty and `drift` reports the missing function), on a state change `transition.key|label|from|to` and `state.key|label` (labels in the
  language of the metamodel), on a reminder `reminder.days|count|state`. `validate` checks that every template a
  reaction or reminder names has texts in the metamodel's language and that every placeholder exists; without the
  section the subscriber renders the texts (an explicit choice: say so in the app). The engine renders
  `subject` and `body` for every recipient (`<entity>_recipients`, `render_template`); a row of
  `public.notification_templates` (key × locale, edited in the admin page `<NotificationTemplates>`) overrides the
  model's text. The texts of the model are also in `behavior.json` and `docs/BEHAVIOR.md`.
  ```yaml
  templates:
    order_assigned:
      it: {subject: "Ordine {{self.code}} assegnato a te", body: "{{actor.name}} ti ha assegnato l'ordine {{self.code}} ({{transition.label}}). {{url}}"}
      en: {subject: "Order {{self.code}} assigned to you", body: "{{actor.name}} assigned you order {{self.code}} ({{transition.label}}). {{url}}"}
  ```

## What the check reports
Unknown class, feature or state; a path through a many-valued reference used as a single value; a type
mismatch in a comparison or a derivation; a literal that is not in its enum; a role not declared, scoped by a
class the record does not reference (or references twice) or written like a reference; a `notify` path that does
not end on a User or an Email; a transition without `by`/`at`, with an unknown `from`/`to`, an `at` that is not
a date, an `emits` not declared; unreachable states, several initial states, no final state; a derivation on an
attribute that is not `derived`, with the wrong type, or in a cycle; derived attributes without a derivation
(warning); a state's `requires`/`model` naming a feature the class does not have, relaxing the metamodel or
contradicting itself (`hidden` and required), and along the path what a target state asks of a feature its source
state locks (warning). The same check runs when `domain.ecore.yaml` changes: the message then says the domain change
breaks the behaviour and where.

## What is generated
- `npm run model:sync` writes **`docs/BEHAVIOR.md`** (roles, one section per workflow with the Mermaid state diagram
  and the tables of states and transitions, the feature × state table when a state has `requires`/`model`, derived
  attributes, events, reactions, subscriptions; in the language of the metamodel) and **`src/lib/modeler/behavior.json`** (the canonical model with every expression typed: text,
  type, tree and SQL; `entities` maps each class to its snake_case key). `BEHAVIOR.md` is rewritten every time: it
  takes no hand notes (a `docs/behavior.md` with other letter case is another document and blocks it until renamed).
- `npm run model:behavior -- --format markdown|mermaid|json|sql|engine` prints the same views. `sql`: every
  derivation, guard, condition and reaction condition as PostgreSQL on a row `r` of the class's table (paths through
  references become subselects, collections become aggregates), to paste into triggers or functions. `engine`: each
  workflow as a version of the runtime engine (tables `workflow_versions/states/transitions`): states with `kind`,
  `owner`, `editable_by`, `reminder_days`, `requires` and `model` (the overlay per feature); transitions with `allowed`, `trigger`/`at_field`/`at_offset`, `comment`,
  `guard` and `condition` as clauses `[{field, op, value}]`, `emits`, and the `notify` of the reactions that name the
  transition. Principals are stored as the engine reads them: roles as they are, `self.issuer` → `field:issuer`.
- A guard or condition the engine evaluates as clauses must be a **conjunction of tests on single attributes of the
  record** (`a and not b and kind = hourly and n >= 1 and k in [x, y] and ref.isSet()`); `or`, arithmetic and
  navigations go into a derived attribute, which the SQL view computes with the full language. `validate` accepts
  the richer form; `behavior --format engine` and `drift` report what the engine cannot evaluate.
- `npm run model:drift` also compares the workflows with the **published** versions in the database (states and
  their principals and reminders; transitions, allowed principals, trigger, offset, comment, clauses, emitted
  events; labels, colours and notifications are not compared). An app without workflow tables (its workflows are
  code) gets a note, not a drift.

## The SQL engine (`npm run model:engine -- --write`)
One idempotent migration (`create or replace`, `create … if not exists`), regenerated after every change of the
behaviour and applied like any other, that runs the behaviour inside the database. For every class with a
workflow, derivations or reactions (`<entity>` = the snake_case of the class, `invitation`):
- `<entity>_principals(r)`: who the current user is for the record (`all`, `admin`, `creator`, the roles held in
  the record's scope, `field:<path>` for the users it points to); `<entity>_can_edit(r)`: may they edit it in
  its state (`editable_by`), for the application's update policies.
- Derived attributes: `<entity>_derive()` computes them before insert and update, in dependency order; a change
  of a referenced row (the funds of an invitation, its reason) refreshes them through a trigger on that table
  (one hop: a deeper navigation, a many-to-many reference or a user profile does not refresh them, noted in the
  output).
- Workflow: the state is set to the initial one on insert and **changes only through
  `<entity>_perform_transition(id, key, comment)`**, which checks the current state, who performs it, the `when`
  (hidden: "not available"), the `guard` (blocked: "requirements not met: <guard>"), the fields the target state
  `requires` (blocked: "required in state <state>: <fields>"; the before-update trigger keeps them set while the
  record stays there), the comment, writes
  `workflow_history`, emits `<entity>.transitioned` (`.completed` in a final state, plus the transition's
  `emits`). `<entity>_available_transitions(id)` lists what the current user may do now, each with `guard_ok`.
  `<entity>_revert(id, state, comment)` goes back to a state in the record's history (`revert.by`,
  `final_by`). `<entity>_run_timed_transitions()` fires the `at` transitions that are due and
  `<entity>_run_reminders()` emits `<entity>.reminder` to the owners of a state after its `reminder.after` (once
  per period, `workflow_reminders`): schedule both with pg_cron (the lines are at the end of the file).
- Events: `<entity>_emit(type, r, extra)` adds `recipients` (`[{email, principal, template}]`, from the reactions
  whose `event` and `when` match, resolved by `<entity>_recipients`) and calls the application's
  `emit_entity_event`; a lifecycle trigger emits `created`, `updated`, `deleted`.
- Contract: the engine calls `current_profile_id()`, `is_admin()`, `has_role(role, scope)`,
  `role_members(role, scope)` and `emit_entity_event(entity, id, type, extra)`. The migration creates a fallback
  only where the application has none: the profile from the setting `app.profile_id`, roles from a `user_roles`
  table when it exists (else a stub that raises), an `events` outbox table. Messages are in the language of the
  metamodel. `workflow_history` and `workflow_reminders` belong to the engine (`drift` ignores them).
- In an app with a hand-written engine the generated functions replace the app's functions with the same names:
  review the migration before applying it, and `npm run model:drift` must stay aligned afterwards.

## From the user's words to the behaviour model
| the user says | behaviour model |
|---|---|
| "chi approva / gli uffici / il direttore del dipartimento" | `roles` (with `scope` when held per instance of a class) |
| "passa da … a … quando …", "si può … solo se …" | a transition with `when` (hidden) or `guard` (blocked with an explanation) |
| "dopo N giorni dalla data di fine", "scade il …" | a timed transition `at: <date attribute> + Nd` |
| "si calcola come", "è completo quando" | `derived: true` on the attribute (metamodel) and its formula in `derivations` |
| "X è obbligatorio da quando è in …", "X non si tocca più dopo …", "in bozza X non compare", "qui Y vale solo a o b" | `requires` / `model` of that state (the class as seen from the state) |
| "avvisa X quando Y" | a reaction `event: <Class>.<event>`, `when`, `notify`, `template`, and its texts in `templates:` |
| "n8n riceve gli eventi di …" | a subscription |
| what no key expresses (arithmetic, external calls) | code, a customization (`docs/customizations.md`, `CUSTOM(<id>)`) |
