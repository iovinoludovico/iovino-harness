# The domain metamodel: `domain.ecore.yaml` (Ecore notation in YAML)

The metamodel describes the **structure** of the domain of a Next.js + Supabase application. It is the source
of truth of the database schema: written from the prompt (`/modeler:metamodel`), edited in the web modeler that
lives inside the app (`/admin/model`, saves proposals), or derived from an existing database (`reverse`).
Behaviour (roles, workflows, guards, events, reactions) is the behaviour model `behavior.yaml` next to it, written on
the metamodel's concepts and checked against it (see `behavior-notation.md`); the metamodel is checked against the
database with `drift`.

## Syntax
```yaml
package: anagrafica                 # EPackage name (lowercase identifier)
nsURI: http://gssi.it/anagrafica    # optional
language: it                        # it | en: default table names (Persona → persone)
doc: Persone, account e gruppi      # optional documentation

classes:
  Soggetto:
    abstract: true                  # no records of its own; subclasses inherit its features
    attributes:
      nome: {type: EString, lower: 1, max_length: 120}
  Persona:
    supertypes: [Soggetto]          # eSuperTypes (features are flattened into the concrete class)
    doc: Una persona fisica
    label: {it: Persona, en: Person}
    attributes:
      codiceFiscale: {type: EString, lower: 1, id: true}   # id: the iD attribute → unique, shown as the record name
      dataNascita: Date                                   # shorthand: optional, single-valued
      ruolo: {type: Ruolo, default: STAFF}                # enum-typed attribute
      attivo: {type: EBoolean, default: true}
    references:
      account: {type: Account, lower: 1, opposite: persona}               # 1 — 0..1 (one-to-one)
      indirizzi: {type: Indirizzo, upper: -1, containment: true, opposite: persona}   # composition
      gruppi: {type: Gruppo, upper: -1, opposite: membri}                 # many-to-many
      utente: User                                                        # the built-in application user
  Account:
    attributes:
      email: {type: Email, lower: 1, unique: true}
    references:
      persona: {type: Persona, opposite: account}
  Indirizzo:
    attributes: {via: EString, citta: EString}
    references:
      persona: {type: Persona, lower: 1, opposite: indirizzi}
  Gruppo:
    attributes: {nome: EString}
    references:
      membri: {type: Persona, upper: -1, opposite: gruppi}

enums:
  Ruolo: [ADMIN, STAFF, {name: OSPITE, label: {it: Ospite esterno, en: External guest}}]
```

### Multiplicity
`lower` (default 0) and `upper` (default 1; `-1` or `"*"` = many). Emfatic-style reading: `[0..1]` optional,
`[1]` required, `[*]` many, `[+]` = `lower: 1, upper: -1` (stored as many). `lower: 1` is required from creation
(`not null`); a feature required only from a state of the workflow on ("the supplier from `ordered`") stays `[0..1]`
here and is listed in that state's `requires` in `behavior.yaml` (whose `model` also locks, hides or narrows a
feature per state: the class as seen from the state). The minimum of a collection cannot be
checked when its container is inserted (the parts come after the record): with a workflow it is a guard of the first
transition (`orderLines.notEmpty()`, `lines.size() >= 2`), evaluated by the generated engine or given by
`behavior --format sql` to a hand-written one; without a workflow it is a rule of the application at its definitive
save. A finite maximum (`upper: 5`) is stored as many: the model does not enforce it (a trigger of the application
on the table of the parts). `validate` warns about every collection whose minimum has no guard and every finite
maximum.

### Data types
`EString`, `Text` (long text), `Email`, `URL`, `EInt`, `ELong`, `EShort`, `EBigInteger`, `EDouble`, `EFloat`,
`EBigDecimal`, `Money`, `EBoolean`, `Date` (day), `EDate` / `DateTime` (timestamp), `JSON`, or an enum.
A multi-valued attribute (`upper: -1`) is stored as a JSON array.

### Class keys
`abstract supertypes doc label plural table unique attributes references rules`

`unique` lists combinations of single-valued features (attributes, or references whose foreign key is in this
table) that must be unique together, typically a lookup on several dimensions:

```yaml
  Tariffa:                       # one row per voce × motivo × posizione; posizione empty = the default row
    unique: [voce, motivo, posizione]          # one group; several: [[a, b], [c, d]]
    attributes: {motivo: {type: Motivo, lower: 1}, importo: Money}
    references: {voce: {type: Voce, lower: 1}, posizione: Posizione}
```

Stored as `unique nulls not distinct (voce, motivo, posizione)`: an empty column counts as a value, so the
default row cannot be repeated either. Subclasses inherit the groups of their supertypes. For a single feature
use `unique: true` on it.

### Attribute keys
`type lower upper default id unique changeable(false = readonly) derived doc label help list min max max_length
renamed_from column`

`derived: true`: the value is computed, never typed (read only, not in forms; the database computes it). Its
formula is written in `behavior.yaml` under `derivations` with the expression language of the guards
(`dataComplete: reason.isSet() and fundsTotal = totalAmount`); a derived attribute without a formula is computed
in code (a customization, reported as a warning).

### Reference keys
`type lower upper containment opposite doc label help list on_delete(restrict|set_null|cascade) unique
renamed_from column join_table`

### Rules
Domain rules the structure cannot express, on the package or on a class: a list of `{id, text}`. The id is a
lowercase identifier (`^[a-z][a-z0-9_]*$`), unique in its scope; the text is one sentence in the user's words
(quote it if it contains a comma or a colon). They produce no DDL: they are shown in `docs/DOMAIN.md`, exported
to Ecore as an annotation, and the code that enforces them is a customization.

```yaml
rules:
  - {id: email_unica, text: Un account per persona con email unica nel sistema}
classes:
  Prenotazione:
    rules:
      - {id: no_overlap, text: "Due prenotazioni della stessa sala non si sovrappongono"}
```

### How the metamodel is stored (deterministic: migrations follow it, `drift` checks it)
| metamodel | database |
|---|---|
| `r: T` single, no opposite | column `r` on this table, FK to T (`set_null`, or `restrict` if `lower: 1`) |
| `r: T[*]` no opposite, not containment | join table `<table>_r` |
| `r: T[*]` containment | column `<this class>` on T, required, `on delete cascade` |
| pair `r: T[*]` / `o: C` (opposite) | column `o` on T (FK to C); cascade if `r` is a containment |
| pair `r: T[*]` / `o: C[*]` | one join table, owned by the class declared first |
| pair `r: T` / `o: C` (one-to-one) | one unique FK: on the contained side, else the mandatory side, else the first declared |
| class `unique: [a, b]` | constraint `<table>_a_b_key unique nulls not distinct (a, b)`; `drift` reports it when missing |

Tables: `table` if given, else the plural snake_case of the class (`BookingItem` → `booking_items`;
`language: it` → `Persona` → `persone`). Columns: `column` if given, else the snake_case of the feature.
Enum attributes: a Postgres enum or a `text` column with `check (… in …)`; literals are stored lowercase snake.
Every table also has `id`, `created_at`, `updated_at` (not described). `User` is the table `profiles`
(or `auth.users`).

Column types written by `migrate`: string/Email/URL → `text` (`varchar(n)` with `max_length`), Text → `text`,
EInt/ELong/… → `integer`, EDouble/EBigDecimal/… → `numeric`, Money → `numeric(12,2)`, EBoolean → `boolean`,
Date → `date`, EDate/DateTime → `timestamptz`, JSON and multi-valued attributes → `jsonb`, references → `uuid`.

Check with `modeler show --format storage` (in the app: `npm run model:show -- --format storage`); draft the
migration with `modeler migrate` (`npm run model:migrate`).

### Names
Classes and enums PascalCase; features camelCase (stored snake_case: `dataNascita` → `data_nascita`);
literals any identifier (stored lowercase snake: `IN_PROGRESS` → `in_progress`). Reserved feature names (standard columns): `id createdAt updatedAt`.
`User` is built in: reference it, never declare it. Polymorphic references (to an abstract class with more than
one concrete subclass) are not supported: reference a concrete class.

### Renames
Give the feature its new name and `renamed_from: <old name>` (the web modeler sets it automatically): the
migration renames the column (`alter table … rename column …`) keeping the data. Remove `renamed_from` once the
migration is applied everywhere.

### Existing databases
`column:` keeps the link to a column whose name is not the snake_case of the feature (`room: {type: Room, column:
room_id}`), `join_table:` names an existing join table, `table:` an existing table. `reverse` writes them.

## From the user's words to the metamodel
| the user says | metamodel |
|---|---|
| "un X ha un nome, una data…" | attributes of X (pick the data type from the meaning: email, url, money, date…) |
| "un X ha / è associato a un Y" | reference `y: Y` (ask: obbligatorio? `lower: 1`) |
| "un X ha molti Y", "più Y" | `ys: Y[*]` (ask: Y appartiene a X? → containment; Y ha un solo X? → opposite single) |
| "X è composto da / contiene / le righe di X" | containment `[*]` + opposite on the part |
| "X e Y si conoscono a vicenda", "dato Y voglio vedere i suoi X" | add the `opposite` |
| "un X è un tipo di Y", "X e Z sono entrambi Y" | supertypes; Y abstract if it has no records of its own |
| "può essere A, B o C", "stato/tipo/categoria fissa" | enum (a closed list); an open list the users extend is a class |
| "identificato da", "codice univoco" | `id: true` (or `unique: true`) |
| "una sola X per ogni combinazione di A e B", "la tariffa per voce e motivo, con un default" | class `unique: [a, b]` (a lookup on several dimensions) |
| "un utente", "chi ha creato", "il responsabile" (a person who logs in) | reference to `User` |
| "si chiude/approva/passa da … a …" | the states are an enum (or EString) attribute (`stato: StatoOrdine`); states, transitions, who and when are the workflow in `behavior.yaml` |
| "si calcola come…", "è completo quando…" | the attribute is `derived: true`; its formula is a derivation in `behavior.yaml` |
| "non può", "deve sempre", "al massimo uno per…" (what no key expresses) | a rule in `rules` of the class or package (`{id, text}`), shown in `docs/DOMAIN.md` |

## Ambiguities to settle with the user (ask, do not guess, when they matter)
1. **Multiplicity** of each end: `[0..1]`, `[1]`, `[*]`.
2. **Containment vs reference**: if the owner is deleted, are the parts deleted too? Can a part move to another owner?
3. **Opposite**: is the relation navigated from both sides (detail page of Y lists its X)?
4. **Attribute or class**: does the value have its own data or lifecycle (Account with email, status, roles → class)?
5. **Enum or class**: will users add values at run time (→ class) or is the list fixed (→ enum)?
6. **Person who logs in** (`User`) or a person in the records (a class such as `Persona`)?
7. **Inheritance or a type enum**: do subclasses have different features (→ inheritance) or only a label (→ enum)?
