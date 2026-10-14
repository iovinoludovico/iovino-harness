# The domain metamodel: `domain.ecore.yaml` (Ecore notation in YAML)

An appforge app is described by two files, as in EMF (`.ecore` + `.genmodel`):

| file | contains | edited by |
|---|---|---|
| `domain.ecore.yaml` | **structure**: package, classes, attributes, references, enums, inheritance | `/appforge:metamodel` from the prompt, the web modeler (admin area, Studio), `metamodel reverse` |
| `app.yaml` | **behaviour**: app settings, roles, permissions, workflows, events, reactions, webhooks, UI mapping | `/appforge:model`, `/appforge:ui`, the Studio |

`app.yaml` `entities:` only *adds behaviour* to classes (no `fields`). Adopted apps (not generated) have only
`domain.ecore.yaml`: it documents the database and is checked against it with `metamodel drift`.

## Syntax
```yaml
package: anagrafica                 # EPackage name (lowercase identifier)
nsURI: http://gssi.it/anagrafica    # optional
language: it                        # it | en: default table names and plurals (persona → persone)
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
      codiceFiscale: {type: EString, lower: 1, id: true}   # id: the iD attribute → unique + display
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
`[1]` required, `[*]` many, `[+]` = `lower: 1, upper: -1` (stored as many; at least one is not enforced).

### Data types
`EString`, `Text` (long text), `Email`, `URL`, `EInt`, `ELong`, `EShort`, `EBigInteger`, `EDouble`, `EFloat`,
`EBigDecimal`, `Money`, `EBoolean`, `Date` (day), `EDate` / `DateTime` (timestamp), `JSON`, or an enum.
A multi-valued attribute (`upper: -1`) is stored as a JSON array.

### Attribute keys
`type lower upper default id unique changeable(false = readonly) doc label help list min max max_length
renamed_from column`

### Reference keys
`type lower upper containment opposite doc label help list on_delete(restrict|set_null|cascade) unique
renamed_from column join_table`

### How references are stored (the generator decides, deterministically)
| metamodel | database |
|---|---|
| `r: T` single, no opposite | column `r` on this table, FK to T (`set_null`, or `restrict` if `lower: 1`) |
| `r: T[*]` no opposite, not containment | join table `<table>_r` |
| `r: T[*]` containment | column `<this class>` on T, required, `on delete cascade` |
| pair `r: T[*]` / `o: C` (opposite) | column `o` on T (FK to C); cascade if `r` is a containment |
| pair `r: T[*]` / `o: C[*]` | one join table, owned by the class declared first |
| pair `r: T` / `o: C` (one-to-one) | one unique FK: on the contained side, else the mandatory side, else the first declared |

Check with `appforge metamodel show --format storage`.

### Names
Classes and enums PascalCase; features camelCase (stored snake_case: `dataNascita` → `data_nascita`);
literals any identifier (stored lowercase snake: `IN_PROGRESS` → `in_progress`). Reserved feature names:
`id state createdBy createdAt updatedAt data entity type`; `code` too when the entity has a `code_prefix`.
`User` is built in: reference it, never declare it. Polymorphic references (to an abstract class with more than
one concrete subclass) are not supported: reference a concrete class.

### Renames
Give the feature its new name and `renamed_from: <old name>`: generated apps rename the column keeping the
data (the web modeler sets it automatically).

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
| "un utente", "chi ha creato", "il responsabile" (a person who logs in) | reference to `User` |
| "si chiude/approva/passa da … a …" | not structure: a workflow in app.yaml (`/appforge:model`) |

## Ambiguities to settle with the user (ask, do not guess, when they matter)
1. **Multiplicity** of each end: `[0..1]`, `[1]`, `[*]`.
2. **Containment vs reference**: if the owner is deleted, are the parts deleted too? Can a part move to another owner?
3. **Opposite**: is the relation navigated from both sides (detail page of Y lists its X)?
4. **Attribute or class**: does the value have its own data or lifecycle (Account with email, status, roles → class)?
5. **Enum or class**: will users add values at run time (→ class) or is the list fixed (→ enum)?
6. **Person who logs in** (`User`) or a person in the records (a class such as `Persona`)?
7. **Inheritance or a type enum**: do subclasses have different features (→ inheritance) or only a label (→ enum)?
