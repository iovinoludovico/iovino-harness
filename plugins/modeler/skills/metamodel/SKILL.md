---
name: metamodel
description: Crea o fa evolvere il metamodello di dominio domain.ecore.yaml (notazione Ecore) e il modello di comportamento behavior.yaml (workflow, guardie, derivazioni, eventi, reazioni) di un'app Next.js + Supabase partendo da una descrizione in linguaggio naturale, e porta la modifica fino a migrazione, codice e verifica di allineamento. Va usata quando l'utente descrive concetti e relazioni del dominio ("una Persona ha associato un Account", "un ordine contiene più righe", "aggiungi la classe Fornitore", "aggiungi il campo telefono"), stati, passaggi e notifiche ("si approva solo se i dati sono completi", "avvisa il direttore quando viene emesso"), chiede di vedere il metamodello, o invoca /modeler:metamodel.
argument-hint: "<descrizione del dominio o della modifica> | show"
---

# Metamodello dal prompt

Richiesta: `$ARGUMENTS`

CLI: nell'app `npm run model:<comando>` (o `python3 tools/modeler/modeler.py <comando>`); se il modellatore non
è ancora installato, `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/modeler.py" <comando>`. Leggi prima
`${CLAUDE_PLUGIN_ROOT}/skills/notation/references/ecore-notation.md` e, se la richiesta tocca stati, passaggi,
campi calcolati, notifiche o eventi, `${CLAUDE_PLUGIN_ROOT}/skills/notation/references/behavior-notation.md`.

## 0. Appunti in `docs/DOMAIN.md`
`npm run model:docs`. Se segnala modifiche a mano, leggile come parte della richiesta, sezione per sezione:
- fatti strutturali (classi, attributi, relazioni) → chiavi del metamodello, con la migrazione (sezione 4);
- vincoli che la notazione esprime (`lower: 1`, `unique`, enum, `max_length`, `default`, `unique` di classe) →
  quelle chiavi;
- stati e passaggi, chi li esegue e quando, campi calcolati, notifiche → `behavior.yaml` (sezione 3b);
- tutto il resto ("non può", "deve sempre", invarianti) → `rules` della classe o del package,
  `text` con le parole dell'utente e un `id` breve in snake_case.
Poi `npm run model:sync -- --force` rigenera il file (copia dell'originale in `.modeler/backups/`). Nel resoconto:
cosa è diventato struttura, cosa regola, cosa non si è potuto collocare (chiedi).

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

## 3b. Il comportamento: `behavior.yaml`
Stati e transizioni ("passa da … a …", "si approva solo se …"), chi le esegue, scadenze ("N giorni dopo la data
di fine"), campi calcolati ("si calcola come …", "è completo quando …"), eventi e notifiche ("avvisa X quando Y")
e sottoscrizioni webhook non vanno nel metamodello né direttamente nel codice: vanno in `behavior.yaml`, accanto a
`domain.ecore.yaml`, scritti sui concetti del metamodello con le espressioni tipizzate del riferimento
`behavior-notation.md` (`guard: dataComplete`, `when: not agencyBookingRequired`, `at: endDate + 1d`,
`notify: [director, self.issuer]`).
- Un campo calcolato è `derived: true` nel metamodello e ha la formula in `derivations` (aritmetica, `round`,
  `coalesce`, `if … then … else`, somme su collezioni); se la formula non si può scrivere (lookup in un'altra
  tabella, valori esterni) resta `derived: true` senza formula e il calcolo è una personalizzazione.
- Una `guard`/`when` che il motore runtime valuta come clausole è una congiunzione di test su singoli attributi
  del record; `or`, calcoli e navigazioni vanno in un attributo derivato (`npm run model:behavior -- --format
  engine` dice cosa il motore non valuta).
- L'attributo di stato (`state:` del workflow) è un `EString` o un enum con un letterale per stato.
- Ambiguità da chiedere in un giro solo, insieme a quelle della struttura: chi può eseguire una transizione
  (ruolo, con quale ambito, o un utente collegato al record come `self.issuer`); se una condizione nasconde la
  transizione (`when`) o la blocca spiegando cosa manca (`guard`); se il commento è obbligatorio.
- Dopo ogni modifica l'hook valida il file contro il metamodello (anche quando cambia il metamodello: una
  rinomina che rompe una guardia o un destinatario viene segnalata subito); `npm run model:validate` fa lo stesso
  in CI. Se un file non esiste ancora e l'app ha già workflow in codice, proponi di scriverlo a partire da ciò che
  il codice fa (`docs/behavior.md`, migrazioni), senza cambiare il comportamento.
Il comportamento si modifica anche dal modellatore web (`/admin/model`: pannello del workflow della classe
selezionata, ruoli e reazioni nella barra laterale): la proposta salvata si applica con `/modeler:apply`.
Dopo ogni modifica: `npm run model:sync` rigenera `docs/BEHAVIOR.md` e `src/lib/modeler/behavior.json`;
`npm run model:engine -- --write` rigenera la migrazione del motore (funzioni e trigger: derivazioni,
`<entità>_perform_transition`, `_available_transitions`, `_revert`, transizioni a tempo, solleciti, eventi con i
destinatari; idempotente, una per rilascio, da rivedere nei `TODO(modeler)`: catalogo degli eventi, policy RLS con
`<entità>_can_edit`, pg_cron), da applicare in locale e poi `npm run model:drift`. Il motore si appoggia a
`current_profile_id`, `has_role`, `role_members`, `emit_entity_event` dell'app (fallback se mancano).
- **Motore a mano** (app nate con appforge, o con un workflow già scritto in SQL: `<entità>_perform_transition`,
  `<entità>_principals`, `<entità>_emit`, eventi `*.transitioned`, `CUSTOM(*-workflow)`): `behavior.yaml` descrive,
  l'SQL dell'app implementa. Scrivilo a partire da ciò che il codice fa, senza cambiare il comportamento, e **non
  lanciare `npm run model:engine -- --write`**: le funzioni generate hanno gli stessi nomi di quelle a mano e le
  sostituirebbero. Per allineare: `npm run model:behavior -- --format sql|engine` dà l'SQL e la versione del
  workflow da riportare nel codice, `drift` confronta i workflow con la versione pubblicata; la modifica di
  `behavior.yaml` e quella del codice vanno nella stessa modifica. Resta CUSTOM (in `docs/customizations.md`) ciò
  che il modello non esprime: grant per gruppo, valori passati alla transizione, campi obbligatori per stato.
  `install`, `reverse` e l'inizio sessione segnalano «workflows in code but no behavior.yaml» finché il file manca.

## 4. Allineare l'applicazione (nella stessa modifica, su un branch)
1. **Migrazione**: `npm run model:migrate` mostra la bozza generata dal confronto tra il metamodello committato
   (`HEAD`) e quello nuovo (`--from HEAD~1` se l'hai già committato, `--from empty` per lo schema intero); poi
   `npm run model:migrate -- --name <nome> --write` la salva in `supabase/migrations/`. Tabelle, colonne, FK con
   `on delete`, join table, letterali di enum e rinomine (`renamed_from` → `rename column`, i dati restano) sono
   già scritti. Risolvi **ogni** riga `TODO(modeler)`: policy RLS e grant secondo le convenzioni dell'app (le
   tabelle nuove nascono con RLS attivo e nessuna policy), backfill dei campi diventati obbligatori, conferma
   esplicita dell'utente prima di scommentare drop o cambi di tipo (perdita di dati). Rinomine di classe: rinomina
   la tabella invece di drop + create. Mai modificare una migrazione già applicata.
2. `npm run model:sync` (aggiorna il modellatore in `/admin/model` e `docs/DOMAIN.md`, la descrizione del dominio
   generata dal metamodello).
3. Codice: tipi (`supabase gen types` o lo script dell'app), query, form e pagine che usano la struttura nuova.
   Una vista generata dal modello (es. `<WorkflowView>`) che arriva su una pagina con una vista equivalente scritta a
   mano va in schede, con quella esistente predefinita (skill `install`, punto 4).
4. Applica la migrazione al database locale (`supabase db reset` o `supabase migration up`) e
   `npm run model:drift` finché risponde "metamodel and database are aligned".
5. Typecheck, lint e test dell'app.

Le regole di dominio dichiarative stanno in `rules` del metamodello (package o classe) e compaiono in
`docs/DOMAIN.md`; il comportamento (workflow, derivazioni, eventi, reazioni) in `behavior.yaml`; il codice che li
applica è una personalizzazione (`docs/customizations.md`, `CUSTOM(<id>)`), come ogni logica che nessuno dei
due modelli esprime (aritmetica, pagine speciali).

Resoconto: il metamodello in Emfatic, le ipotesi fatte, la migrazione e cosa cambia nell'applicazione.
