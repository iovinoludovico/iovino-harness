---
name: metamodel
description: Crea o fa evolvere il metamodello di dominio domain.ecore.yaml (notazione Ecore: classi, attributi, relazioni, enum, regole) di un'app Next.js + Supabase partendo da una descrizione in linguaggio naturale, e porta la modifica fino a migrazione, codice e verifica di allineamento. Va usata quando l'utente descrive concetti e relazioni del dominio ("una Persona ha associato un Account", "un ordine contiene più righe", "aggiungi la classe Fornitore", "aggiungi il campo telefono"), chiede di vedere il metamodello, o invoca /modeler:metamodel. Stati, passaggi, guardie, campi calcolati e notifiche sono di /modeler:behavior: se la richiesta tocca entrambi, la parte di comportamento si fa con quella skill nella stessa modifica.
argument-hint: "<descrizione del dominio o della modifica> | show"
---

# Metamodello dal prompt

Richiesta: `$ARGUMENTS`

CLI: nell'app `npm run model:<comando>` (o `python3 tools/modeler/modeler.py <comando>`); se il modellatore non
è ancora installato, `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/modeler.py" <comando>`. Leggi prima
`${CLAUDE_PLUGIN_ROOT}/skills/notation/references/ecore-notation.md`; se la richiesta tocca anche stati, passaggi,
campi calcolati, notifiche o eventi, la parte di comportamento segue la skill `behavior` (sezione 3b).

## 0. Appunti in `docs/DOMAIN.md`
`npm run model:docs`. Se segnala modifiche a mano, leggile come parte della richiesta, sezione per sezione:
- fatti strutturali (classi, attributi, relazioni) → chiavi del metamodello, con la migrazione (sezione 4);
- vincoli che la notazione esprime (`lower: 1`, `unique`, enum, `max_length`, `default`, `unique` di classe) →
  quelle chiavi;
- stati e passaggi, chi li esegue e quando, campi calcolati, notifiche → `behavior.yaml` (skill `behavior`);
- tutto il resto ("non può", "deve sempre", invarianti) → `rules` della classe o del package,
  `text` con le parole dell'utente e un `id` breve in snake_case.
Poi `npm run model:sync -- --force` rigenera il file (copia dell'originale in `.modeler/backups/`). Nel resoconto:
cosa è diventato struttura, cosa regola, cosa non si è potuto collocare (chiedi).

## 1. Dove
Cerca `domain.ecore.yaml` nella cartella corrente o nelle superiori.
- Esiste e il modellatore è installato (`tools/modeler/`): la modifica diventa una **proposta** visibile in
  `/admin/model` (sezione 3, punto 3) e `domain.ecore.yaml` cambia solo all'apply; modifiche minime, rinomine con
  `renamed_from`.
- Esiste ma il modellatore non è installato: modifica `domain.ecore.yaml` direttamente (nessuna pagina che
  mostri una proposta) e prosegui con la sezione 4.
- Non esiste ma l'app ha già un database: proponi prima `/modeler:install` (ricava il metamodello dal database
  con `reverse`): non riscrivere a mano uno schema che esiste già.
- App nuova: scrivi il metamodello da zero alla radice del repository.

## 2. `show`
`show --format emfatic` (testo leggibile) e `--format mermaid` (diagramma delle classi, da mostrare in linea se
il client lo supporta); `--format storage` mostra tabelle e colonne.

## 3. Dalla descrizione al metamodello
1. Estrai classi, attributi e relazioni con la tabella "From the user's words to the metamodel" del
   riferimento. Mantieni nomi e lingua dell'utente (nomi italiani → `language: it`).
   «Chi può fare cosa» parte da qui: i ruoli dell'applicazione (`gli uffici`, `il direttore del dipartimento`) sono
   `roles:` del metamodello (`scope: <Classe>` se tenuti per istanza di una classe; `admin` è predefinito), memorizzati
   come enum `app_role` e tabella `user_roles` (la migrazione li crea se mancano; `drift` li confronta); un utente
   nominato dal record («il responsabile del fondo», «gli assistenti dell'ordine») è un `ref` a `User` con `role: true`
   (ruolo di record). Nel diagramma compaiono come riquadri predefiniti `Role «enumeration»` e `User «built-in»`
   (i ruoli di record sono connettori verso `User`; `Role` e `User` non si dichiarano). Chi fa cosa con quei ruoli
   (`by`, `notify`, `view_as`) va poi in `behavior.yaml`.
2. **Elenca le ambiguità che cambiano la struttura** (molteplicità, containment o riferimento, opposite,
   attributo o classe, enum o classe, `User` o una classe persona, ruolo dell'app o ruolo di record, ereditarietà o enum di tipo). Chiedile in
   **un solo giro**, al massimo 4 domande a scelta multipla con l'opzione consigliata per prima; le minori
   decidile tu e riportale come ipotesi. Esempio per "una Persona ha associato un Account":
   - Account obbligatorio per ogni Persona? (`[1]` dalla creazione / `[0..1]` / da uno stato del workflow in poi:
     `[0..1]` qui e `requires` sullo stato in `behavior.yaml`; se in uno stato è anche bloccato, nascosto o limitato
     a certi valori, `model` di quello stato)
   - Una Persona può avere più Account? (`[0..1]` / `[*]`)
   - Dall'Account si risale alla Persona? (opposite `persona`)
   - L'Account si cancella con la Persona? (containment)
3. **Bozza e proposta** (modellatore installato): copia `domain.ecore.yaml` in `.modeler/drafts/` (e `behavior.yaml`
   se la modifica lo tocca: skill `behavior`) e modifica la bozza, non il file; l'hook PostToolUse valida la bozza
   come il file vero (stesso nome): correggi subito gli errori. Poi
   `npm run model:propose -- --note "<la richiesta dell'utente, in una riga>"`: valida, stampa il diff, salva la
   proposta in `.modeler/proposals/<data>-prompt.json` (lo stesso JSON che salva il modellatore web) e cancella la
   bozza. Nessuna differenza o bozza non valida: non salva nulla, correggi e ripeti. Di' all'utente che la
   proposta è in `/admin/model` tra quelle in attesa (banner sopra l'editor: diff, «Apri» per vederla nel
   diagramma, «Scarta»). App nuova o modellatore assente: scrivi `domain.ecore.yaml` direttamente.
4. Mostra il risultato in Emfatic e come diagramma (`show --format emfatic|mermaid <bozza o file>`), più
   `show --format storage` quando conta il database.

## 3b. Il comportamento: `behavior.yaml`
Stati e transizioni, chi le esegue, scadenze, campi calcolati, eventi, notifiche e i loro testi non vanno nel
metamodello né direttamente nel codice: vanno in `behavior.yaml`, accanto a `domain.ecore.yaml`, e si modificano con
`/modeler:behavior` **nella stessa modifica** (un campo calcolato è `derived: true` qui e ha la formula là; un
attributo di stato è un `EString` o un enum con un letterale per stato; una collezione con `lower > 0` o `upper`
finito chiede una guardia; un campo obbligatorio solo da uno stato in poi resta `[0..1]` qui ed è `requires` di
quello stato là, e ciò che in uno stato è in sola lettura, nascosto o limitato a certi valori è `model` di quello
stato: il metamodello è ciò che vale in ogni stato). L'hook valida `behavior.yaml` anche quando cambia il metamodello: una rinomina che rompe
una guardia o un destinatario viene segnalata subito, e va sistemata qui. Con un motore scritto a mano
(`CUSTOM(*-workflow)`) non si lancia `npm run model:engine -- --write`: i dettagli sono nella skill `behavior`,
sezione 4.

## 4. Applicare (nella stessa modifica, su un branch)
Con una proposta in attesa chiedi con AskUserQuestion: «Applico ora (migrazione, sync, codice, drift)» (consigliato)
o «La lascio in attesa nel modellatore». Nel secondo caso il resoconto finisce con il file della proposta e il
rimando a `/modeler:apply`. Nel primo, e quando il file è stato modificato direttamente, i passi sono quelli
della skill `apply`: `npm run model:apply -- <file> --write` (solo con la proposta; controlla `git diff
domain.ecore.yaml`), poi:
1. **Migrazione**: `npm run model:migrate` mostra la bozza generata dal confronto tra il metamodello committato
   (`HEAD`) e quello nuovo (`--from HEAD~1` se l'hai già committato, `--from empty` per lo schema intero); poi
   `npm run model:migrate -- --name <nome> --write` la salva in `supabase/migrations/`. Tabelle, colonne, FK con
   `on delete`, join table, letterali di enum e rinomine (`renamed_from` → `rename column`, i dati restano) sono
   già scritti. Risolvi **ogni** riga `TODO(modeler)`: policy RLS e grant secondo le convenzioni dell'app (le
   tabelle nuove nascono con RLS attivo e nessuna policy), backfill dei campi diventati obbligatori, conferma
   esplicita dell'utente prima di scommentare drop o cambi di tipo (perdita di dati). Rinomine di classe: rinomina
   la tabella invece di drop + create. Mai modificare una migrazione già applicata.
2. `npm run model:sync` (aggiorna il modellatore in `/admin/model` e `docs/DOMAIN.md`, la descrizione del dominio
   generata dal metamodello; con `behavior.yaml` anche `behavior.json` e `docs/BEHAVIOR.md`).
3. Codice: tipi (`supabase gen types` o lo script dell'app), query, form e pagine che usano la struttura nuova.
   Una vista generata dal modello (es. `<WorkflowView>`) che arriva su una pagina con una vista equivalente scritta a
   mano va in schede, con quella esistente predefinita (skill `install`, punto 4).
   Riferimenti nei form (convenzione «+ Nuovo» in modale): per ogni `ref` non containment verso una classe con un
   form, select + `<ECreate onCreated>`: `create<E>Inline(prev, formData)` valida e inserisce come `save<E>` ma
   ritorna `{ok, created: {id, label, hint?}}` senza redirect; `<ECreate>` è un `Dialog` (`max-h-[90vh]
   overflow-y-auto`) che monta lo stesso `<EForm action={create<E>Inline}>` e chiama `onCreated`; il chiamante
   tiene le opzioni in `useState` (`setOptions(cur => [created, ...cur]); setValue(created.id)`) e riceve
   `canCreate<E>` dal server component. Test: l'azione inline non reindirizza e ritorna il record. Chiavi i18n
   `addNew`, `newTitle`, `create`. Esempio: `SupplierCreate`/`createSupplierInline` di order-management.
4. Applica la migrazione al database locale (`supabase db reset` o `supabase migration up`) e
   `npm run model:drift` finché risponde "metamodel and database are aligned".
5. Typecheck, lint e test dell'app.

Le regole di dominio dichiarative stanno in `rules` del metamodello (package o classe) e compaiono in
`docs/DOMAIN.md`; il comportamento (workflow, derivazioni, eventi, reazioni) in `behavior.yaml` (skill `behavior`); il codice che li
applica è una personalizzazione (`docs/customizations.md`, `CUSTOM(<id>)`), come ogni logica che nessuno dei
due modelli esprime (aritmetica, pagine speciali).

Resoconto: il metamodello in Emfatic, le ipotesi fatte, la migrazione e cosa cambia nell'applicazione.
