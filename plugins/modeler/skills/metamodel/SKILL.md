---
name: metamodel
description: Crea o fa evolvere il metamodello di dominio domain.ecore.yaml (notazione Ecore) di un'app Next.js + Supabase partendo da una descrizione in linguaggio naturale, e porta la modifica fino a migrazione, codice e verifica di allineamento. Va usata quando l'utente descrive concetti e relazioni del dominio ("una Persona ha associato un Account", "un ordine contiene più righe", "aggiungi la classe Fornitore", "aggiungi il campo telefono"), chiede di vedere il metamodello, o invoca /modeler:metamodel.
argument-hint: "<descrizione del dominio o della modifica> | show"
---

# Metamodello dal prompt

Richiesta: `$ARGUMENTS`

CLI: nell'app `npm run model:<comando>` (o `python3 tools/modeler/modeler.py <comando>`); se il modellatore non
è ancora installato, `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/modeler.py" <comando>`. Leggi prima
`${CLAUDE_PLUGIN_ROOT}/skills/notation/references/ecore-notation.md`.

## 1. Dove
Cerca `domain.ecore.yaml` nella cartella corrente o nelle superiori.
- Esiste: la modifica parte da lì (modifiche minime, rinomine con `renamed_from`).
- Non esiste ma l'app ha già un database: proponi prima `/modeler:install` (ricava il metamodello dal database
  con `reverse`): non riscrivere a mano uno schema che esiste già.
- App nuova: scrivi il metamodello da zero alla radice del repository.

## 2. `show`
`show --format emfatic` (testo leggibile) e `--format mermaid` (diagramma delle classi, da mostrare in linea se
il client lo supporta); `--format storage` mostra tabelle e colonne.

## 3. Dalla descrizione al metamodello
1. Estrai classi, attributi e relazioni con la tabella "From the user's words to the metamodel" del
   riferimento. Mantieni nomi e lingua dell'utente (nomi italiani → `language: it`).
2. **Elenca le ambiguità che cambiano la struttura** (molteplicità, containment o riferimento, opposite,
   attributo o classe, enum o classe, `User` o una classe persona, ereditarietà o enum di tipo). Chiedile in
   **un solo giro**, al massimo 4 domande a scelta multipla con l'opzione consigliata per prima; le minori
   decidile tu e riportale come ipotesi. Esempio per "una Persona ha associato un Account":
   - Account obbligatorio per ogni Persona? (`[1]` / `[0..1]`)
   - Una Persona può avere più Account? (`[0..1]` / `[*]`)
   - Dall'Account si risale alla Persona? (opposite `persona`)
   - L'Account si cancella con la Persona? (containment)
3. Scrivi o modifica `domain.ecore.yaml`. L'hook PostToolUse lo valida: correggi subito gli errori.
4. Mostra il risultato in Emfatic e come diagramma, più `show --format storage` quando conta il database.

## 4. Allineare l'applicazione (nella stessa modifica, su un branch)
1. **Migrazione**: `npm run model:migrate` mostra la bozza generata dal confronto tra il metamodello committato
   (`HEAD`) e quello nuovo (`--from HEAD~1` se l'hai già committato, `--from empty` per lo schema intero); poi
   `npm run model:migrate -- --name <nome> --write` la salva in `supabase/migrations/`. Tabelle, colonne, FK con
   `on delete`, join table, letterali di enum e rinomine (`renamed_from` → `rename column`, i dati restano) sono
   già scritti. Risolvi **ogni** riga `TODO(modeler)`: policy RLS e grant secondo le convenzioni dell'app (le
   tabelle nuove nascono con RLS attivo e nessuna policy), backfill dei campi diventati obbligatori, conferma
   esplicita dell'utente prima di scommentare drop o cambi di tipo (perdita di dati). Rinomine di classe: rinomina
   la tabella invece di drop + create. Mai modificare una migrazione già applicata.
2. `npm run model:sync` (aggiorna il modellatore in `/admin/model`).
3. Codice: tipi (`supabase gen types` o lo script dell'app), query, form e pagine che usano la struttura nuova.
4. Applica la migrazione al database locale (`supabase db reset` o `supabase migration up`) e
   `npm run model:drift` finché risponde "metamodel and database are aligned".
5. Typecheck, lint e test dell'app.

Logica che il metamodello non esprime (workflow, regole, pagine speciali) è una personalizzazione: va in
`docs/customizations.md` e nel codice con `CUSTOM(<id>)`.

Resoconto: il metamodello in Emfatic, le ipotesi fatte, la migrazione e cosa cambia nell'applicazione.
