---
name: notation
description: Riferimento delle notazioni del metamodello di dominio domain.ecore.yaml (Ecore in YAML - classi, attributi, riferimenti con molteplicità, containment, opposite, enum, ereditarietà, unicità su più colonne, attributi derived - e come si traduce in tabelle e colonne) e del modello di comportamento behavior.yaml (ruoli, derivazioni, workflow con stati, transizioni e guardie, eventi, reazioni, webhook, con espressioni tipizzate sul metamodello). Va usata ogni volta che si legge o scrive uno dei due file, quando l'utente descrive concetti del dominio e relazioni ("un ordine contiene più righe", "una persona ha un account"), stati e passaggi ("si approva solo se…", "avvisa il direttore quando…") o chiede come modellare qualcosa.
---

# Il metamodello di dominio: `domain.ecore.yaml`

Il metamodello descrive la **struttura** del dominio di un'applicazione Next.js + Supabase: package, classi,
attributi, riferimenti, enum, ereditarietà. È la fonte di verità dello schema: ogni modifica di schema parte da
qui e va nella stessa modifica con la migrazione e il codice che la usa. Il comportamento (ruoli, workflow,
guardie, eventi, reazioni, webhook) sta nel **modello di comportamento `behavior.yaml`** (skill `behavior`), accanto al metamodello:
è scritto sui concetti del metamodello con espressioni tipizzate (`reason.compensationType = hourly and hours > 0`)
e verificato contro di esso da `validate`, dall'hook a ogni modifica di uno dei due file e in CI. Gli attributi
calcolati sono `derived: true` nel metamodello e hanno la formula in `derivations` del behavior. Ciò che nessuno
dei due esprime (aritmetica, pagine, chiamate esterne) è una personalizzazione dichiarata in
`docs/customizations.md`. Le regole di dominio che la struttura non esprime si dichiarano in `rules` (id e testo,
sul package o su una classe) e compaiono in `docs/DOMAIN.md`, la descrizione del dominio generata dal metamodello
(`sync`), dove l'utente può annotare a mano ciò che va tradotto (`docs`).

Riferimenti completi, da leggere prima di scrivere i file:
- metamodello, mappatura su database, ambiguità da chiarire con l'utente: [references/ecore-notation.md](references/ecore-notation.md);
- comportamento (espressioni, principal, workflow, eventi, reazioni, cosa segnala la verifica):
  [references/behavior-notation.md](references/behavior-notation.md).

Comandi utili (dal plugin `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/modeler.py" …`, nell'app `npm run model:*`):
- `validate` (metamodello e, se c'è, `behavior.yaml` contro di esso), `show --format emfatic|mermaid|markdown|storage|json|yaml`,
  `behavior --format markdown|mermaid|json|sql|engine` (il comportamento spiegato, i diagrammi di stato, le
  espressioni tipizzate con il loro SQL, le versioni del workflow come le memorizza il motore),
  `engine [--write]` (la migrazione del motore SQL: funzioni e trigger generati dal comportamento);
- `sync [--force]` (rigenera `metamodel.json` e `docs/DOMAIN.md`; con `behavior.yaml` anche `behavior.json`, con la mappa `uses` delle feature usate dal comportamento, e
  `docs/BEHAVIOR.md`), `docs` (stato di `docs/DOMAIN.md`: allineato,
  da rigenerare, o modifiche a mano da tradurre nel metamodello);
- `diff <vecchio> <nuovo>` (yaml, `.ecore` o proposta `.json`);
- `export -o <nome>.ecore` / `import <file>.ecore` per Eclipse EMF ed Epsilon;
- `reverse --db <DSN>` e `drift [--db <DSN>]` contro un database reale (`drift` confronta anche i workflow con la
  versione pubblicata nelle tabelle `workflow_*`, se l'app le ha).
