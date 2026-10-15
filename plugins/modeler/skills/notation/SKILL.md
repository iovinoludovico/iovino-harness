---
name: notation
description: Riferimento della notazione del metamodello di dominio domain.ecore.yaml (Ecore in YAML) - classi, attributi, riferimenti con molteplicità, containment, opposite, enum, ereditarietà, unicità su più colonne - e di come si traduce in tabelle e colonne. Va usata ogni volta che si legge o scrive un domain.ecore.yaml, quando l'utente descrive concetti del dominio e relazioni ("un ordine contiene più righe", "una persona ha un account") o chiede come modellare qualcosa nel metamodello.
---

# Il metamodello di dominio: `domain.ecore.yaml`

Il metamodello descrive la **struttura** del dominio di un'applicazione Next.js + Supabase: package, classi,
attributi, riferimenti, enum, ereditarietà. È la fonte di verità dello schema: ogni modifica di schema parte da
qui e va nella stessa modifica con la migrazione e il codice che la usa. Il comportamento (workflow, permessi,
pagine) non sta nel metamodello: vive nel codice dell'app, e ciò che il metamodello non esprime è una
personalizzazione dichiarata in `docs/customizations.md`.

Riferimento completo della sintassi, della mappatura su database e delle ambiguità da chiarire con l'utente:
[references/ecore-notation.md](references/ecore-notation.md). Leggilo prima di scrivere il metamodello.

Comandi utili (dal plugin `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/modeler.py" …`, nell'app `npm run model:*`):
- `validate`, `show --format emfatic|mermaid|storage|json|yaml`;
- `diff <vecchio> <nuovo>` (yaml, `.ecore` o proposta `.json`);
- `export -o <nome>.ecore` / `import <file>.ecore` per Eclipse EMF ed Epsilon;
- `reverse --db <DSN>` e `drift [--db <DSN>]` contro un database reale.
