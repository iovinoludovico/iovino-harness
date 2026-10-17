# The behaviour model: `behavior.yaml`

`domain.ecore.yaml` says *what* the domain is; `behavior.yaml`, next to it, says *what happens*: roles,
derivations of the attributes marked `derived` in the metamodel, workflows (states, transitions, guards, timed
transitions), domain events, reactions (who is notified when) and webhook subscriptions. Every name in it is a
concept of the metamodel, navigated with **typed paths**: `modeler validate` (`npm run model:validate`) checks
the behaviour against the metamodel, the PostToolUse hook does it after every edit of either file, `apply`
reports a proposal that breaks it, and CI runs the same check. A domain change that breaks a guard, a
recipient or a derivation is therefore found before the database is.

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

workflows:
  Invitation:
    state: state                        # the attribute holding the state: EString, or an enum whose literals are the states
    states:
      draft:    {initial: true, owner: [self.issuer], editable_by: [self.issuer, office], label: {it: Bozza, en: Draft}}
      pending:  {owner: [director], reminder: {after: 7d, template: approval_reminder}}
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
| `= <> < <= > >=` | comparison; `< <= > >=` only on numbers and dates | bool |
| `x in [a, b]` | membership | bool |
| `and or not ( )` | boolean operators | bool |
| `12`, `1.5`, `'text'`, `true`, `false` | literals | |
| `hourly` | a bare name is the literal of the enum on the other side of a comparison (`kind = hourly`, `kind in [a, b]`) | the enum |

Typing: numbers compare with numbers (EInt, EDouble, EBigDecimal, Money…), strings with strings (EString, Text,
Email, URL), dates with dates (Date, EDate, DateTime), booleans with booleans, an enum with its literals;
a reference is only tested with `isSet()` or navigated; a collection is only closed by its operations.
`guard`, `when` and a reaction's `when` are booleans; a derivation has the type of its attribute. Of a `User` only
`email` can be navigated. Arithmetic (`+ - * /`, `round`, `if … then … else`) is not available yet: an attribute
whose formula needs it stays `derived: true` without a derivation (reported as a warning: computed in code).

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
- A subscription names the webhook URL by environment variable (`url_env`) or `url`, and the event patterns it
  receives: `<Class>.*`, `<Class>.<event>`, and the system patterns `user.*`, `webhook.test`.

## What the check reports
Unknown class, feature or state; a path through a many-valued reference used as a single value; a type
mismatch in a comparison or a derivation; a literal that is not in its enum; a role not declared, scoped by a
class the record does not reference (or references twice) or written like a reference; a `notify` path that does
not end on a User or an Email; a transition without `by`/`at`, with an unknown `from`/`to`, an `at` that is not
a date, an `emits` not declared; unreachable states, several initial states, no final state; a derivation on an
attribute that is not `derived`, with the wrong type, or in a cycle; derived attributes without a derivation
(warning). The same check runs when `domain.ecore.yaml` changes: the message then says the domain change
breaks the behaviour and where.

## From the user's words to the behaviour model
| the user says | behaviour model |
|---|---|
| "chi approva / gli uffici / il direttore del dipartimento" | `roles` (with `scope` when held per instance of a class) |
| "passa da … a … quando …", "si può … solo se …" | a transition with `when` (hidden) or `guard` (blocked with an explanation) |
| "dopo N giorni dalla data di fine", "scade il …" | a timed transition `at: <date attribute> + Nd` |
| "si calcola come", "è completo quando" | `derived: true` on the attribute (metamodel) and its formula in `derivations` |
| "avvisa X quando Y" | a reaction `event: <Class>.<event>`, `when`, `notify`, `template` |
| "n8n riceve gli eventi di …" | a subscription |
| what no key expresses (arithmetic, external calls) | code, a customization (`docs/customizations.md`, `CUSTOM(<id>)`) |
