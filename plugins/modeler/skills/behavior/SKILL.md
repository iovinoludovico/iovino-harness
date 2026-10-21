---
name: behavior
description: Crea o fa evolvere il modello di comportamento behavior.yaml (ruoli, derivazioni, workflow con stati, transizioni, guardie, ritorni e scadenze, eventi, reazioni, solleciti, sottoscrizioni webhook, testi delle notifiche) di un'app Next.js + Supabase che ha il metamodello domain.ecore.yaml, partendo da una descrizione in linguaggio naturale o dal codice esistente, e porta la modifica fino a validazione, sync, motore SQL (generato o a mano) e test. Va usata quando l'utente descrive stati e passaggi ("si approva solo se i dati sono completi", "passa in istruttoria quando…"), chi può fare cosa ("il direttore approva"), scadenze e solleciti ("tre giorni dopo…"), campi calcolati ("si calcola come…"), notifiche e i loro testi ("avvisa il direttore quando viene emesso", "l'oggetto dell'email è…"), chiede di vedere il workflow, o invoca /modeler:behavior. La struttura del dominio (classi, attributi, relazioni) è di /modeler:metamodel.
argument-hint: "<descrizione del comportamento o della modifica> | show [Classe]"
---

# Comportamento dal prompt

Richiesta: `$ARGUMENTS`

CLI: nell'app `npm run model:<comando>` (o `python3 tools/modeler/modeler.py <comando>`); se il modellatore non
è ancora installato, `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/modeler.py" <comando>`. Leggi prima
`${CLAUDE_PLUGIN_ROOT}/skills/notation/references/behavior-notation.md`; `ecore-notation.md` solo se la richiesta
cambia anche la struttura (sezione 3).

## 0. Dove
`behavior.yaml` sta accanto a `domain.ecore.yaml` (cartella corrente o superiori) ed è scritto sui concetti del
metamodello: senza metamodello, prima `/modeler:metamodel` (app nuova) o `/modeler:install` (app con un database).
- `behavior.yaml` esiste: la modifica parte da lì, minima (ordine, stile e commenti del file restano).
- Non esiste ma l'app ha già workflow in codice (`install`, `reverse` e l'inizio sessione segnalano «workflows in
  code but no behavior.yaml»: funzioni `<entità>_perform_transition`, check o enum sull'attributo di stato,
  `CUSTOM(*-workflow)`): scrivilo a partire da ciò che il codice fa (`docs/behavior.md`, migrazioni, pagine che
  mostrano le transizioni), **senza cambiare il comportamento**; è il caso del motore a mano (sezione 4.3).
- App nuova senza workflow in codice: scrivilo da zero, accanto al metamodello.

## 1. `show`
`npm run model:behavior` (markdown: lo stesso `docs/BEHAVIOR.md`, filtra la classe se chiesta), `-- --format
mermaid` (diagrammi di stato, da mostrare in linea se il client li supporta), `--format sql` (derivazioni e guardie
in PostgreSQL) e `--format engine` (le versioni del workflow come le memorizza il motore: dice cosa il motore
runtime valuta e cosa no).

## 2. Dalle parole al modello
Stati e transizioni ("passa da … a …", "si approva solo se …"), chi le esegue, scadenze ("N giorni dopo la data
di fine"), campi calcolati ("si calcola come …", "è completo quando …"), eventi e notifiche ("avvisa X quando Y")
e sottoscrizioni webhook non vanno nel metamodello né direttamente nel codice: vanno in `behavior.yaml`, con le
espressioni tipizzate del riferimento (`guard: dataComplete`, `when: not agencyBookingRequired`, `at: endDate + 1d`,
`notify: [director, self.issuer]`). Usa la tabella «From the user's words to the behaviour model» del riferimento e
mantieni nomi e lingua dell'utente.
- Un campo calcolato è `derived: true` nel metamodello e ha la formula in `derivations` (aritmetica, `round`,
  `coalesce`, `if … then … else`, somme su collezioni); se la formula non si può scrivere (lookup in un'altra
  tabella, valori esterni) resta `derived: true` senza formula e il calcolo è una personalizzazione.
- Una `guard`/`when` che il motore runtime valuta come clausole è una congiunzione di test su singoli attributi
  del record; `or`, calcoli e navigazioni vanno in un attributo derivato (`npm run model:behavior -- --format
  engine` dice cosa il motore non valuta).
- L'attributo di stato (`state:` del workflow) è un `EString` o un enum con un letterale per stato.
- I destinatari di una transizione viaggiano sull'evento del cambio di stato (`Order.transitioned` con `when:
  transition = …`), non su un evento secondario; ogni reazione con `notify` ha una `subscription` che la riceve,
  altrimenti `validate` avvisa.
- Una collezione con un minimo (`lower: 1`, `[+]`) o un massimo finito: il database la memorizza come many, quindi il
  minimo si impone con una guardia della prima transizione del workflow (`orderLines.notEmpty()`,
  `lines.size() >= 2`: le parti arrivano dopo il record, un vincolo all'inserimento è impossibile) o, senza workflow,
  con una regola dell'app al salvataggio definitivo; il massimo con un trigger dell'app sulla tabella delle parti.
  Quando una modifica (anche una proposta del modellatore) porta una collezione a `lower > 0` o a un `upper` finito,
  proponi subito la guardia (chiedi su quale transizione) o la regola, con un test della transizione bloccata;
  `validate` lo segnala finché manca.
- Un campo che diventa obbligatorio **da uno stato in poi** («il fornitore va indicato dall'ordine in avanti», «X è
  obbligatorio dopo l'approvazione», anche una collezione non vuota «da pending») è `requires: [x, …]` sullo stato
  in `behavior.yaml`: non `lower: 1` nel metamodello (che lo richiederebbe già alla creazione) né `x.isSet()`
  ripetuto nelle guardie delle transizioni d'ingresso. Il motore lo verifica entrando nello stato (elenca i campi
  mancanti, `missing` in `_available_transitions`) e finché il record vi resta (campi singoli, trigger); nessuna
  ereditarietà, ogni stato elenca i suoi; `npm run model:behavior -- --format sql` dà i frammenti per un motore a
  mano. `validate` avvisa se il metamodello lo richiede già, se lo richiede lo stato iniziale o se una guardia lo ripete.
- Una reazione o un sollecito con `notify` ha i suoi testi nel modello: `templates: {<chiave>: {it: {subject, body},
  en: {…}}}` con i segnaposto `{{self.<path>}}`, `{{transition.label}}`, `{{actor.name}}`, `{{comment}}`, `{{url}}`,
  `{{reminder.days}}` (riferimento, «Events, reactions, subscriptions»); se i testi usano `{{url}}` l'app definisce
  `public.record_url(entity text, id uuid)`, l'unica mappa SQL delle sue pagine (convenzione di `core` sui link ai
  record), che il motore chiama se esiste. Chiedi i testi insieme alle altre
  ambiguità, o proponine di provvisori da far correggere all'utente; mai lasciarli al sottoscrittore (n8n spedisce,
  non scrive). Il motore li rende per destinatario; l'app li corregge dalla pagina admin a matrice
  (`<NotificationTemplates>`, tabella `notification_templates` che `install` aggiunge quando il modello ha testi).
- **Ambiguità da chiedere in un giro solo**, al massimo 4 domande a scelta multipla con l'opzione consigliata per
  prima (le minori decidile tu e riportale come ipotesi): chi può eseguire una transizione (ruolo, con quale
  ambito, o un utente collegato al record come `self.issuer`); se una condizione nasconde la transizione (`when`)
  o la blocca spiegando cosa manca (`guard`); se il commento è obbligatorio; chi riceve la notifica e con quale
  testo; se un passaggio a tempo è automatico (`at`) o un sollecito (`reminder`).
Scrivi o modifica `behavior.yaml`. L'hook PostToolUse lo valida contro il metamodello (anche quando cambia il
metamodello: una rinomina che rompe una guardia o un destinatario viene segnalata subito): correggi subito gli
errori; `npm run model:validate` fa lo stesso in CI. Con il modellatore installato la modifica può passare dalla
stessa bozza e proposta di `metamodel` (sezione 3, punto 3: `.modeler/drafts/behavior.yaml` accanto alla bozza del
metamodello, poi `npm run model:propose`), così compare in `/admin/model` prima di essere applicata; con un motore a
mano o senza modellatore modifica il file direttamente.

## 3. Se serve anche la struttura
Un attributo `derived` nuovo, un attributo di stato o un letterale dell'enum che manca, un riferimento usato da una
guardia o da un destinatario (`self.fund.manager`): si aggiungono a `domain.ecore.yaml` **nella stessa modifica**,
seguendo `/modeler:metamodel` (sezioni 3 e 4: ambiguità della struttura, migrazione con i `TODO(modeler)`
risolti, `model:drift`). Mai un `behavior.yaml` che cita feature che il metamodello non ha: l'hook lo blocca.

## 4. Allineare l'applicazione (nella stessa modifica, su un branch)
1. `npm run model:validate`: zero errori, e leggi i warning (minimo senza guardia, campo di `requires` già
   obbligatorio nel metamodello o ripetuto da una guardia, testi con `{{url}}` senza `record_url` nell'app, template
   mancante o in una lingua sola, reazione che nessuna sottoscrizione riceve, destinatari su un evento secondario,
   doppi destinatari).
2. `npm run model:sync` rigenera `docs/BEHAVIOR.md` e `src/lib/modeler/behavior.json` (il modellatore web in
   `/admin/model` mostra il workflow nuovo).
3. Il motore SQL, in uno dei due modi:
   - **Motore generato**: `npm run model:engine -- --write` rigenera la migrazione del motore (funzioni e trigger:
     derivazioni, `<entità>_perform_transition`, `_available_transitions`, `_revert`, transizioni a tempo,
     solleciti, eventi con i destinatari e i testi resi; idempotente, una per rilascio, da rivedere nei
     `TODO(modeler)`: catalogo degli eventi, policy RLS con `<entità>_can_edit`, pg_cron). Il motore si appoggia a
     `current_profile_id`, `has_role`, `role_members`, `emit_entity_event` dell'app (fallback se mancano).
     Applicala in locale (`supabase migration up`), poi `npm run model:drift` finché i workflow risultano allineati;
     in cloud con `/core:db-push` prima del codice che la usa.
   - **Motore a mano** (app con un workflow già scritto in SQL: `<entità>_perform_transition`,
     `<entità>_principals`, `<entità>_emit`, eventi `*.transitioned`, `CUSTOM(*-workflow)`): `behavior.yaml`
     descrive, l'SQL dell'app implementa. **Non lanciare `npm run model:engine -- --write`**: le funzioni generate
     hanno gli stessi nomi di quelle a mano e le sostituirebbero. `npm run model:behavior -- --format sql|engine` dà
     l'SQL delle espressioni e la versione del workflow da riportare nel codice; `drift` confronta i workflow con
     la versione pubblicata; con `templates:` il dispatcher dell'app rende i testi da `behavior.json` e gli
     override dalla tabella `notification_templates` (skill `install`, punto 4); i campi richiesti da uno stato
     (`requires`) si riportano nelle clausole `unmet` delle transizioni d'ingresso e nel trigger della tabella
     (`--format sql` li stampa). Resta CUSTOM (in `docs/customizations.md`) ciò che il modello non esprime: grant
     per gruppo, valori passati alla transizione.
4. Codice che segue il comportamento: pagine che mostrano stati e transizioni (`<WorkflowView>` in schede accanto a
   una vista scritta a mano, skill `install` punto 4), pagina admin dei testi quando compaiono `templates:` (`install`
   punto 4), sottoscrittori (n8n spedisce `recipients[].subject/body`, non compone testi).
5. Test: la transizione bloccata dalla guardia, i destinatari della reazione, il sollecito, un testo reso (pgTAP o
   test dell'app); poi typecheck, lint e test dell'app.
6. Le modifiche fatte dal modellatore web (`/admin/model`: pannello del workflow della classe selezionata, ruoli e
   reazioni nella barra laterale) arrivano come proposta: si applicano con `/modeler:apply`, che poi segue questi
   stessi passi.

Il comportamento (workflow, derivazioni, eventi, reazioni, testi) sta in `behavior.yaml`; le regole di dominio
dichiarative in `rules` del metamodello; il codice che li applica oltre al motore è una personalizzazione
(`docs/customizations.md`, `CUSTOM(<id>)`), come ogni logica che nessuno dei due modelli esprime.

Resoconto: la parte di `BEHAVIOR.md` o il diagramma di stato toccati, le ipotesi fatte, cosa cambia nel motore
(migrazione rigenerata o SQL da riportare) e nell'applicazione.
