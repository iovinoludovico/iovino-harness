# State-indexed refinement of a metamodel

_Draft of 2026-10-21. Research note behind `states.<key>.model` of the `modeler` plugin (0.31.0): the definitions
the feature rests on, the properties it is meant to have, how it compares with the literature, and where the code
follows or departs from the definitions. Written to become an article once the order-management case is in
production; the examples use the `invitations` fixture of the plugin tests._

## 1. The problem

A model-driven application has one domain metamodel `MM` (Ecore in `domain.ecore.yaml`) and, for some classes, a
workflow in `behavior.yaml`: a state attribute and the transitions that move a record between states. The
constraints a record has to satisfy are not the same in every state. An invitation in `draft` may lack its
dates; once it is `pending_director` the dates are required, the flat amount must not change, the travel method
may only be one of two values. Classic answers keep `MM` static and push the state-dependent part elsewhere: OCL
invariants of the form `state = X implies …`, guards on the transitions, or code in the forms. None of them gives
a *metamodel as seen from the state* that documentation, forms, static checks and the database engine can all be
derived from.

`states.<key>.model` writes the state-dependent part as a **restrictive overlay** of the class, one per state,
and derives everything else from it. This note makes that precise.

## 2. Definitions

### 2.1 Metamodel

A metamodel `MM` is a set of classes. A class `C` has features `F(C)`; a feature `f` has a type (a primitive
type, an enum `E` with literals `L(E)`, or a class), a multiplicity `lower(f) ∈ {0, 1}`, `upper(f) ∈ {1, *}`, and
`changeable(f) ∈ {true, false}`. A feature with `upper = 1` is *single-valued*, otherwise a *collection*. Derived
features (`derived: true`) are computed from others and are not written.

An instance `i` of `C` gives every single-valued feature a value or `⊥` (unset) and every collection a finite set.
Static conformance `i ⊨ MM` is the usual one, restricted to what matters here:

- `lower(f) = 1` ⇒ `i.f ≠ ⊥` (single-valued) or `|i.f| ≥ 1` (collection);
- `f : E` ⇒ `i.f ∈ L(E) ∪ {⊥}`;
- `changeable(f) = false` ⇒ `i.f` never changes after creation.

### 2.2 Workflow

A workflow on `C` is `W = (S, s₀, Sf, T, σ)`: a finite set of states `S`, the initial state `s₀ ∈ S`, the final
states `Sf ⊆ S`, the transitions `T` and the state attribute `σ : F(C)`, an enum whose literals are `S`. A
transition `t ∈ T` is `(from(t) ⊆ S, to(t) ∈ S, guard(t))` with `guard(t)` a boolean expression over `i`
(plus who may fire it, which plays no role here). `σ(i)` is the current state of `i`.

### 2.3 Overlay of a state

The overlay of a state `s` is a partial function

```
O_s : F(C) ⇀ { lower ∈ {0, 1, —},  readonly ∈ 𝔹,  hidden ∈ 𝔹,  in ∈ 𝒫(L(E)) ∪ {—} }
```

written in `behavior.yaml` as `states.<s>.model: {f: {lower, readonly, hidden, in}}`, with `requires: [f]` the
shorthand for `model: {f: {lower: 1}}`. Normalisation (`state_overlay`): `hidden ⇒ readonly`; a feature not in
`dom(O_s)` is left as `MM` says. There is no inheritance between states: `O_s` is complete for `s`.

Well-formedness (`validate`, function `_check_state_model`) asks that `O_s` only *tightens* `MM`:

- `f ∈ F(C)`, `f ≠ σ`; a derived `f` may only be `hidden`;
- `lower = 0` is an error when `lower(f) = 1` in `MM` (a state cannot relax the metamodel);
- `hidden ∧ lower = 1` is an error (a hidden feature cannot be set);
- `in` only on a single-valued enum attribute, non-empty, `in ⊆ L(E)`;
- what `MM` already says (`lower = 1`, `changeable = false`, `in = L(E)`) is a warning: the overlay adds nothing.

### 2.4 Refinement

The metamodel as seen from `s` is `MM_s = apply(MM, O_s)`: the same metamodel, where for every `f ∈ dom(O_s)`

```
lower_s(f)      = max(lower(f), O_s(f).lower)            (— counts as 0)
changeable_s(f) = changeable(f) ∧ ¬ O_s(f).readonly
L_s(f)          = L(E) ∩ O_s(f).in                       (L(E) when in = —)
visible_s(f)    = ¬ O_s(f).hidden
```

and `MM_s = MM` elsewhere. `hidden` is a *presentation* flag: the feature stays in `MM_s` (frozen, since
`hidden ⇒ readonly`) and its value is kept; it is only not shown. The function `refine` of the plugin produces
the *view* of `MM_s` (`model:show --state C.s`), where hidden features are removed from the printout: that is a
rendering choice, not the refinement, and the difference matters only for the proof of P1 below.

### 2.5 Refinement order

For two metamodels over the same classes, `MM' ⊑ MM` (`MM'` refines `MM`) iff for every feature

```
lower'(f) ≥ lower(f),   changeable'(f) ⇒ changeable(f),   L'(f) ⊆ L(f),   upper'(f) = upper(f).
```

`⊑` is a partial order, and `apply` is monotone by construction: `apply(MM, O) ⊑ MM` for every overlay `O`,
well-formed or not (a `lower: 0` under a static `lower: 1` is absorbed by the `max`). Well-formedness therefore
is not what makes `MM_s` a refinement; it makes the written overlay *mean what it says*. The family
`{MM_s | s ∈ S}` is a set of refinements of one metamodel, indexed by the state: they coexist, none is derived
from another, and `MM` is their least upper bound in the order restricted to the family.

### 2.6 Dynamic conformance

An instance `i` with `σ(i) = s` is *dynamically conformant* iff `i ⊨ MM_s`, that is, over the definitions of 2.1
with `lower_s`, `L_s` in place of `lower`, `L`:

```
i ⊨ MM_{σ(i)}
```

Conformance is thus a relation indexed by a runtime value of the instance itself. The metamodel does not change
at runtime: the instance moves between the members of a fixed family.

### 2.7 Updates and transitions

Two kinds of change touch `i`:

- an **update in the state** `i → i'` with `σ(i') = σ(i) = s` is admitted iff `i' ⊨ MM_s` and, for every `f` with
  `changeable_s(f) = false`, `i'.f = i.f`;
- a **transition** `t` with `σ(i) ∈ from(t)` is admitted iff `guard(t)(i)` and `i ⊨ MM_{to(t)}`; its only effect
  is `σ(i) := to(t)`.

The second clause is the point of the design: a transition is a **verified migration** between two coexisting
refinements. Nothing is transformed; the instance is checked against the target and moved. In the generated
engine the transition carries no payload (`<e>_perform_transition` updates the state column only): whatever
`MM_to` asks must already hold in the source state.

## 3. Properties

### P1 — Conservation

**Claim.** `i ⊨ MM_s ⇒ i ⊨ MM` for every `s`.

**Proof.** Each constraint of `MM` on a feature is implied by its counterpart in `MM_s`: `lower(f) ≤ lower_s(f)`,
`L_s(f) ⊆ L(f)`, and `changeable` only moves to `false`. Hidden features stay in `MM_s` (2.4), so the projection
argument is not needed. ∎

Consequence: one database schema, the one of `MM`, is enough for every state; the overlays never need a column,
a nullability change or a check constraint of their own. This is what the plugin relies on when it generates a
single migration from `MM` and puts the state-dependent part in the workflow trigger.

### P2 — Soundness of the engine (single-valued features)

Let the engine be the generated trigger `<k>_workflow_guard` (before insert or update) plus
`<k>_perform_transition`.

**Claim.** Starting from `i ⊨ MM_{σ(i)}`, every insert, update or transition the engine accepts leads to an
instance `i'` with `i' ⊨ MM_{σ(i')}`, as far as single-valued, non-derived features are concerned; an update in
the state that changes a feature with `changeable_s(f) = false` is refused.

**Proof sketch.** By cases on the statement.

- *Insert.* `σ(i') := s₀` if unset. The trigger checks, for the state of `new`, every `lower_s = 1` feature
  (`is not null`) and every `in` (`new.f is null or new.f in (…)`): exactly the single-valued constraints of
  `MM_{σ(i')}`.
- *Update in the state.* Same checks on `new`, plus `new.f is distinct from old.f` refused for every
  `readonly`/`hidden` feature of the state. `changeable(f) = false` of `MM` itself is enforced elsewhere (the
  update policy), so `changeable_s` is covered as a conjunction.
- *Update that changes the state.* Refused unless the session setting `app.in_transition` is on, which only
  `<k>_perform_transition` sets, and only around its own `update … set <state> = to`. Before that update the
  function computes `v_missing` for the target: the `lower_to = 1` features (`is not null`, `exists` for a
  collection) and the `in` of the target; a non-empty list raises `23514`. The trigger then re-checks `new` in
  the new state. Read-only features of the source are not re-checked across the state change, which is correct:
  `changeable_s` constrains updates *in* `s`, not the move out of it (and the move changes no other column).

Hence every accepted statement preserves `i ⊨ MM_{σ(i)}`. ∎

**Exceptions (stated, not hidden).**

- *E1, collections on entry only.* `lower_s(f) = 1` on a collection is checked by `perform_transition`
  (`exists`) but not by the trigger: the parts live in their own table, and deleting the last part while in `s`
  is not caught. The invariant holds on entry and is not maintained.
- *E2, readonly/hidden on collections.* Not enforced at all; reported to the application through
  `<k>_field_policy(r)`. `validate` warns.
- *E3, derived features.* Outside the relation: they are computed after the checks; only `hidden` is allowed.
- *E4, the state column.* Soundness assumes nobody changes the state column with `app.in_transition` on outside
  `perform_transition`; the setting is transaction-local and the function resets it.

### P3 — Path consistency

With no payload on transitions, what `MM_to` asks must be reachable from the source. For a feature `f` and a
state `s` let

```
ok_s(f) = L_s(f) ∪ { ⊥ | lower_s(f) = 0 }       (Dom(f) ∪ {⊥ | lower_s(f) = 0} for a non-enum feature)
Poss_s(f) ⊆ ok_s(f)                              the values an instance can actually have for f while in s
```

`Poss_s(f) = ok_s(f)` when `changeable_s(f)` (the value can be set in the state); when `f` is read only in `s`,
`Poss_s(f)` is the set of values instances enter `s` with, which satisfy `MM_s`, hence still `⊆ ok_s(f)`.

A transition `t : s → s'` is **dead for `f`** iff `Poss_s(f) ∩ ok_{s'}(f) = ∅`: no instance in `s` can ever take
it. It is **partial for `f`** iff `f` is read only in `s` and `Poss_s(f) ⊄ ok_{s'}(f)`: the instances that
entered `s` with a value outside `ok_{s'}(f)` are stuck.

**Claim (soundness of the static check).** Using the upper bound `Poss_s(f) ⊆ ok_s(f)`:

- if `ok_s(f) ∩ ok_{s'}(f) = ∅` then `t` is dead for `f`, whatever `readonly` says: an error;
- if `f` is read only in `s` and `ok_s(f) ⊄ ok_{s'}(f)` then `t` is partial for `f`: a warning. The two concrete
  shapes are `⊥ ∈ ok_s(f)`, `⊥ ∉ ok_{s'}(f)` (required in `s'`, not in `s`) and `L_s(f) ⊄ L_{s'}(f)` (narrowed
  in `s'`).

Since `L_s(f)` is never empty (well-formedness) and `Dom(f)` is not, the dead case happens only for an enum
attribute with `in` in both states, disjoint, and `⊥` excluded in at least one of them
(`lower_s(f) = 1 ∨ lower_{s'}(f) = 1`, the static `lower` of `MM` included).

**Precision.** The check is one step: it uses `ok_s(f)` for `Poss_s(f)`. The exact set under read-only chains
is the least fixpoint `Poss_s(f) = ⋃_{t : r → s} (Poss_r(f) ∩ ok_s(f))` over the predecessors (`ok_{s₀}(f)` at
the initial state, which creation can set freely), so a chain `s₁ {in: [a]} → s₂ {readonly, in: [a, b]} → s₃
{in: [b]}` is dead at `s₂ → s₃` but reported as partial. Guards are ignored (they are arbitrary expressions and
can make any transition dead). Both are future work; the one-step check is sound, not complete.

## 4. Related work

- **OCL invariants with a state implication** (`inv: state = pending implies flatAmount <> null`). Same
  expressive power for single features; but the constraints stay scattered formulas over one metamodel, with
  no `MM_s` to print, no field policy for the forms, no refinement order and no path analysis. The overlay is
  the fragment of those invariants that is closed under `apply`.
- **Executable DSMLs** (GEMOC, xMOF/fUML, Kermeta). The runtime state lives in an *execution metamodel* joined
  to the static one, and conformance stays static: the execution model conforms to the execution metamodel
  whatever the state is. Here the state is an attribute of the domain class and conformance is indexed by it.
  The two compose: an xDSML's execution model could be given state overlays.
- **Typestate** (Strom and Yemini; DeLine and Fähndrich, *Fugue*; Plaid). The type of an object changes with its
  state and the compiler checks which methods are callable. The state-indexed refinement is typestate for models:
  the *type* (`MM`) does not change, the conformance relation does; the checked operations are updates and
  transitions rather than method calls, and the check is at runtime in the database rather than static.
- **Dynamic object reclassification and roles** (Drossopoulou et al., *Fickle*; Steimann's role models). The
  object changes class at runtime. Here the class is fixed and the instance moves between refinements of it,
  which keeps one schema (P1) and needs no migration of the object's representation.
- **Metamodel co-evolution and model migration** (Cicchetti et al., Herrmannsdoerfer et al., Edapt). Versions of
  a metamodel in *sequence*, with models migrated from one to the next by transformation. Here the versions are
  in *parallel* and coexist; a transition is a migration that is verified, never transformed (2.7).
- **Models@runtime** (Blair, Bencomo, France). A causally connected model of the running system. The overlays
  are the opposite direction: a fixed family of design-time metamodels selected by a runtime value.

## 5. The definitions in the plugin

| Definition | Plugin | Test |
| :- | :- | :- |
| `O_s`, normalisation (2.3) | `behavior.py`: `_model_spec`, `state_overlay`, `required_features` | `test_state_model_the_class_as_seen_from_a_state` |
| well-formedness (2.3) | `_check_state_model` (errors and warnings) | same, `requires` tests |
| `MM_s`, the view (2.4) | `refine`; `cli.py` `model:show --state`; `ecore.py` `to_emfatic` (`// in: …`) | same |
| `MM_s` in the documents | `state_matrix`, `domain_annotations`; `BEHAVIOR.md` feature × state; `DOMAIN.md` «1 from <s>» | `test_domain_md_follows_the_state_model` |
| P2, trigger (2.7) | `engine.py` `_workflow`: `required`, `_allowed`, `readonly` blocks of `<k>_workflow_guard` | `test_engine_sql_text`, `test_workflow_end_to_end` (Postgres) |
| P2, transition (2.7) | `engine.py`: `v_missing` of `<k>_perform_transition`, `<k>_available_transitions` | same |
| field policy for the forms | `engine.py` `_field_policy` → `<k>_field_policy(r)` | same |
| P3, one-step check | `_check_state_model`, «along the path» | `test_state_model_the_class_as_seen_from_a_state` |

## 6. Review of the code against the definitions (2026-10-21)

Done as part of the harness review that produced this note.

1. **Dead transition was a warning, and conditioned on `readonly`.** The check reported a narrowed `in` only when
   the source was read only. By P3 the dead case (`in` disjoint, `⊥` excluded) does not depend on `readonly`:
   an instance in `s` can only hold values of `L_s(f)` whether or not it can change them. Fixed: error
   «no record in <s> can satisfy <s'> … the transition can never fire», independent of `readonly`; the partial
   cases stay warnings.
2. **The hint «set it in the transition» was not realisable.** The generated transition has no payload (2.7),
   and a read-only feature cannot be set in the source. Fixed: the hint now says to require the feature before
   the source state or to let the source state change it.
3. **`refine` drops hidden features.** Kept as the view; the refinement keeps them (2.4). Documented, no code
   change.
4. **Collections.** E1 and E2 are the known gaps; `validate` already warns on E2. Not changed: enforcing E1
   needs a trigger on the parts' table (the same trigger the deferred note on collection maxima asks for).
5. **Precision of P3.** One-step, sound. The fixpoint analysis is future work.

## 7. Open questions

- *Added structure per state*: an overlay that adds a feature in a state would break P1 (one schema) and the
  refinement order; the current choice is that `MM` is the union and states only restrict. A real case that
  needs the opposite would be the test of the design.
- *Payload on transitions* (`set:` of a transition): would turn 2.7 into a migration with a transformation and
  remove the dead-transition class of P3 at the cost of a second kind of change to verify.
- *Collections* (E1): invariant maintenance on the parts' table.
- *Case study*: order-management with `states.<key>.model` (`Order` from `pending`: lines required, totals read
  only), then compare the overlay with the hand-written `STATE_REQUIRES`/`STATE_EDITORS` it replaces.
