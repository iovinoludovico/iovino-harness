# Note per l'harness

Lezioni annotate con `/core:harness-note`, da rivedere e applicare al plugin core.

## 2026-10-14 — modeler install: ignorare il bytecode Python nell'app
- **Progetto**: guest-invitations-af
- **Cosa è successo**: la CLI copiata in `tools/modeler/` genera `__pycache__/` quando gira dentro l'app (`npm run model:*`); l'app non lo ignorava e i `.pyc` sono finiti in un commit. L'installer già salta `__pycache__` quando copia, ma non protegge l'app dopo.
- **Proposta**: `modeler install` aggiunge `__pycache__/` (o `tools/modeler/**/__pycache__/`) al `.gitignore` dell'app se manca, come fa la skill per `.modeler/proposals/`; un test in `test_modeler.py` lo verifica, e il passo 4 della skill install lo cita.
- **Plugin**: modeler
- **Tipo**: skill
- **Stato**: applicata il 2026-10-14: `modeler install` aggiunge `__pycache__/` al `.gitignore` dell'app (test `test_install_ignores_python_bytecode`).

## 2026-10-14 — Automatizzare pull request e merge su main dopo conferma
- **Progetto**: guest-invitations-af (con iovino-harness)
- **Cosa è successo**: dopo il push di un branch `feat/…` la PR va aperta a mano dal browser (sul computer manca `gh`) e il merge su `main` va fatto a parte, in due repository; il controllo della CI resta manuale.
- **Proposta**: una skill `core:ship` (o `core:pr`) che, dopo i controlli del progetto, fa push del branch, apre la PR (titolo e corpo dai Conventional Commits, con l'attribuzione), aspetta l'esito della CI e la mostra, poi **chiede conferma esplicita** e solo allora fa il merge su `main` (e cancella il branch). Prerequisito: `gh` installato e autenticato (`! brew install gh && gh auth login`), o in alternativa l'API GitHub. Regola in `conventions.md`: il merge su `main` di un'app con deploy automatico richiede sempre la conferma, anche se la PR l'ha aperta Claude; per l'harness ricordare `release.py --write` prima del push.
- **Plugin**: core
- **Tipo**: skill
- **Stato**: applicata il 2026-10-14: skill `core:ship` (`plugins/core/skills/ship/SKILL.md`: push, PR, `gh pr checks --watch`, merge solo dopo conferma) e riga in `conventions.md` sezione Git; la conferma per `gh pr merge` era già in `ASK_RULES` di `hook.py`.

## 2026-10-14 — Editor e diagrammi di modellazione: modello leggibile, connettori non sovrapposti
- **Progetto**: guest-invitations-af (diagramma del workflow in `/admin/workflows/[id]`; vale anche per l'editor del metamodello)
- **Cosa è successo**: il diagramma aveva dimensioni fisse (più largo della pagina, con scroll) e connettori Bézier semitrasparenti sovrapposti: una transizione con 7 sorgenti verso uno stato finale disegnava 7 curve una sull'altra, e le etichette erano illeggibili. L'utente ha chiesto elementi che occupano tutto il contenitore e connettori non sovrapposti.
- **Proposta**: aggiungere a `conventions.md` (o a una skill/riferimento per editor e diagrammi di modelli) queste indicazioni, da applicare ogni volta che si crea o si modifica un editor o un diagramma di modellazione:
  - il layout riempie il contenitore: lo misura (ResizeObserver) e allarga gli elementi fino a un massimo. Sotto una larghezza minima, cioè la parola più lunga dei nomi, scorre invece di stringersi;
  - il layout è una funzione pura (`layout(nodi, archi, larghezza)`), testata con vitest su un modello reale del progetto: niente nodi sovrapposti, nessuna coppia di connettori con un tratto collineare in comune, nessun connettore che attraversa un nodo, etichette che non coprono nodi né altre etichette;
  - i connettori sono ortogonali, con angoli arrotondati, e ognuno ha la propria corsia tra le colonne e tra le righe. Ogni connettore ha il proprio punto di attacco sul lato del nodo, ordinato in base a dove sta l'altro capo; le porte in entrata sono sfalsate di qualche px rispetto a quelle in uscita;
  - un arco con molte sorgenti verso lo stesso nodo (es. "annulla" da ogni stato) diventa un bus (un tronco, una sola freccia e una sola etichetta), e il nodo di destinazione va su una riga a parte;
  - i connettori sono ben visibili (tratto ~1.75px, opacità alta, colore della destinazione, punta della freccia piena). Le etichette sono disegnate sopra tutte le linee, su uno sfondo, e posizionate cercando tra più candidati quello che non copre nodi, etichette o altri connettori;
  - l'hover su un connettore o sulla sua etichetta lo evidenzia e attenua gli altri.
  Riferimento d'implementazione: `src/lib/workflow-layout.ts` e `tests/workflow-layout.test.ts` di guest-invitations-af. Valutare di portare le stesse regole nell'editor del metamodello (`kit/metamodel-editor.js`).
- **Plugin**: core (convenzione) + modeler (editor del metamodello)
- **Tipo**: convenzione
- **Stato**: rinviata il 2026-10-15 per il solo bus (il resto è applicato): si riprende quando il modellatore è installato su un'app reale con almeno 4 classi che puntano alla stessa. Già fatto: regole nella skill `core:diagrams` (2026-10-14); nell'editor del metamodello (`kit/metamodel-editor.js`) layout e connettori sono funzioni pure (`Layout`, esportate per Node) testate da `plugins/modeler/tests/layout.test.mjs` su molte dimensioni della tela, con porte in entrata sfalsate, porte che scorrono sul lato, variante a Z per le L che attraversano un box, etichette scelte tra più candidate ed evidenziazione al passaggio del mouse. Rinviato fino alla prova del modellatore su un'app reale: il bus per molte sorgenti verso la stessa classe (test `todo` con 8 sorgenti).

## 2026-10-15 — Lookup su più dimensioni: gestione e specifica in forma di tabella
- **Progetto**: guest-invitations-af
- **Cosa è successo**: le tariffe (voce × motivo × posizione, con la riga senza posizione come default e fallback) si gestivano riga per riga nella lista generica: impossibile vedere quali combinazioni mancavano, e nessun vincolo impediva due righe per la stessa combinazione (la proposta ne sceglieva una a caso).
- **Proposta**: in `conventions.md` (sviluppo guidato dai modelli): "Se un registry è una tabella di lookup su più dimensioni (riferimenti o enum, con riga di default e fallback), specificalo e gestiscilo come tabella/matrice che mostra valori propri, ereditati dal default e non definiti, invece che riga per riga; imponi l'unicità della combinazione (indice unico `nulls not distinct`)". Nel plugin modeler: un'opzione di vista `matrix` per le classi registry che indica le dimensioni (righe, colonne, default = null) e genera pagina e vincolo; finché manca, è una personalizzazione `CUSTOM(...)`.
- **Plugin**: core (convenzione) + modeler (vista matrix e unicità composta nel metamodello)
- **Tipo**: convenzione
- **Stato**: applicata il 2026-10-15 senza la vista matrix (scartata): chiave di classe `unique` nel metamodello (`ecore.py`: validazione, `storage`, diff, export Ecore; `sqlgen.py`: `unique nulls not distinct`; `dbschema.py`: reverse e drift, anche da indici unici), documentata in `notation`, test `UniqueTogetherTests` e test su Postgres; riga in `conventions.md` (Sviluppo guidato dai modelli). Vista `matrix` scartata: il modello descrive solo la struttura, le pagine sono codice dell'app.

## 2026-10-15 — `modeler apply --write` riscrive tutto domain.ecore.yaml
- **Progetto**: guest-invitations-af
- **Cosa è successo**: una proposta con una sola modifica (`Invitation.invitationFunds: lower 0 -> 1`) applicata con `npm run model:apply -- <file> --write` ha riordinato alfabeticamente le chiavi di tutte le classi (attributi, `label`, `doc` senza virgolette): diff di 187 righe per un cambiamento di una, e perso l'ordine curato degli attributi. Annullato e applicato a mano.
- **Proposta**: in `tools/modeler` `apply` deve modificare il YAML in modo chirurgico (patch delle sole feature cambiate, preservando ordine, stile e commenti) o almeno serializzare senza `sort_keys`; test: applicare una proposta con una modifica produce un diff di una riga. Anche: `pull` richiede il DSN di produzione; valutare la lettura via `supabase db query --linked` (sola lettura) e una marcatura `pulled` separata e confermata.
- **Plugin**: modeler
- **Tipo**: altro (bug della CLI)
- **Stato**: applicata il 2026-10-15 senza la lettura di `pull` via Supabase CLI (rinviata: comando da verificare prima di usarlo in produzione): `apply --write` riscrive solo le righe cambiate (`patch_text` e `align_order` in `ecore.py`, usati da `cmd_apply`; ricade sulla riscrittura completa con avviso sui commenti persi), test `PatchTextTests` e `test_apply_changes_only_the_changed_lines`; sul metamodello di guest-invitations-af una modifica = 2 righe di diff invece di 194; skill `apply` aggiornata. La parte rinviata su `pull` è superata il 2026-10-15: `pull` ricava il DSN dal progetto collegato con `supabase link` (modeler 0.10.0, PR #1).
- **Nuovo caso (2026-10-15, modeler 0.11.0)**: riaperta. Una proposta scaricata da produzione (`model_change_requests`, jsonb) con 2 modifiche (`Invitation.reason`/`createdBy`: lower 0 -> 1), applicata con `npm run model:apply -- --write`, ha di nuovo riscritto più del necessario: virgolette tolte a `doc`/`label` di tutte le classi, `references` di una classe compattati su una riga, blocco `diagram:` aggiunto in fondo con le posizioni salvate dall'editor. Ripristinato dal backup e applicato a mano. Ipotesi: la proposta contiene `diagram`, che non è nel metamodello del repository, e/o l'ordine delle chiavi riscritto da jsonb fa ricadere il writer chirurgico sulla riscrittura completa. Proposta: `apply` ignora `diagram` (o lo scrive solo su richiesta esplicita), segnala in modo evidente quando ricade sulla riscrittura completa (o si ferma senza `--force`), test con una proposta passata da jsonb (chiavi riordinate) e con `diagram`.
- **Stato (nuovo caso)**: applicata il 2026-10-15: causa confermata, il `diagram` della proposta assente dal file faceva rinunciare `patch_text` (ritorno `None`) e `cmd_apply` riscriveva tutto. Ora `apply` tiene il `diagram` del file e ignora quello della proposta, e se la scrittura riga per riga non è possibile `--write` si ferma senza scrivere (riscrittura completa solo con `--rewrite`); test `test_apply_ignores_the_diagram_of_a_production_proposal` e `test_apply_stops_instead_of_rewriting_the_whole_file`; skill `apply` aggiornata.

## 2026-10-15 — Il modellatore non mostra le proposte salvate e non ancora applicate
- **Progetto**: guest-invitations-af
- **Cosa è successo**: una modifica al metamodello proposta e salvata da `/admin/model` in produzione (riga `open` in `model_change_requests`) non lasciava alcuna traccia riaprendo l'editor: l'editor mostra solo il metamodello in esercizio, e l'utente ha dovuto chiedere "che fine ha fatto la mia modifica?" per scoprire che era ancora in attesa.
- **Proposta**: nella pagina `/admin/model` del plugin modeler:
  - all'apertura, un avviso con le proposte in sospeso (`open`/`pulled`, sia `.modeler/proposals/` in sviluppo sia `model_change_requests` in produzione): data, autore, nota e un riepilogo delle differenze rispetto al metamodello in esercizio (stesso formato di `modeler diff`, es. `~ Invitation.invitationFunds: lower 0 -> 1`);
  - per ciascuna: "Apri nell'editor" (carica la proposta per rivederla o continuarla), "Scarta" (stato `rejected`, con conferma) e l'indicazione di come applicarla (`/modeler:apply`); stato `applied` mostrato come storico;
  - un indicatore nel menu/titolo ("1 proposta da applicare") e, al salvataggio di una nuova proposta, l'avviso se ce n'è già una in sospeso (sostituirla o aggiungerla);
  - nella CLI, `modeler proposals` elenca anche quelle di produzione (lettura via DSN o `supabase db query --linked`) e la skill `modeler:apply`/l'hook di sessione segnala all'avvio le proposte in sospeso.
- **Plugin**: modeler
- **Tipo**: altro (funzionalità del modellatore)
- **Stato**: applicata il 2026-10-15 senza la lettura di produzione in `modeler proposals` e senza lo storico delle `applied` (rinviate: serve un accesso in sola lettura al database di produzione, come per `pull`): `/admin/model` elenca sopra l'editor le proposte in sospeso con data, autore, nota e differenze (`Layout.diff` nell'editor, uguale a `modeler diff`, test `diff.test.mjs`), con "Apri nell'editor", "Scarta" e avviso al salvataggio (`metamodel-modeler.tsx`, azioni `listMetamodelProposals` e `rejectMetamodelProposal`); l'hook di sessione del modeler segnala le proposte in `.modeler/proposals/`. Verificato con `tsc` in un progetto di prova.

## 2026-10-15 — Controllare `origin/main` dell'harness prima di indicare lo stato del plugin
- **Progetto**: guest-invitations-af
- **Cosa è successo**: Claude ha detto più volte che il modellatore installato nell'app veniva da un branch harness (`feat/modeler-apply-done`) "da unire prima del merge", basandosi su un controllo fatto ore prima. Il branch era già stato unito in `main` con una PR e cancellato.
- **Proposta**: in `conventions.md`, sezione "Lavoro sul codice": "Prima di dare indicazioni sullo stato del repository harness o dei suoi plugin (branch da unire, versione pubblicata, release da fare), esegui `git fetch --prune` e controlla `origin/main` (log, versione in `plugin.json`): non riusare un controllo fatto prima nella sessione." In più: l'hook di sessione, o `/modeler:install` e `/core:ship`, segnalano se il plugin caricato viene da un branch diverso da `main` o è indietro rispetto a `origin/main`.
- **Plugin**: core
- **Tipo**: convenzione
- **Stato**: applicata il 2026-10-15 senza l'hook (rinviato: chiederebbe la rete a ogni avvio di sessione, e l'hook mostra già le versioni caricate; si riprende se l'errore si ripete nonostante la regola): riga in `plugins/core/context/conventions.md`, sezione "Lavoro sul codice".

## 2026-10-15 — La password di `psql` non si può chiedere con `! …` in Claude Code
- **Progetto**: guest-invitations-af
- **Cosa è successo**: `! npm run model:done -- --write` è fallito con `fe_sendauth: no password supplied`. `psql`, lanciato dalla CLI del modeler con `capture_output`, chiede la password, ma un comando `!` non ha un terminale interattivo e la risposta arriva vuota. Non è stato scritto niente. La skill `modeler:apply` (punto 1) suggerisce proprio `! npm run model:pull` quando la password non è nell'ambiente: con `pull` e `done --write` l'indicazione non funziona.
- **Proposta**:
  - nelle skill `modeler:apply` (pull, done) e nei messaggi della CLI, senza password nell'ambiente: indicare di lanciare il comando da un terminale proprio, fuori da Claude Code, oppure di configurare `~/.pgpass` (riga host:porta:db:utente del pooler, `chmod 600`). Mai `! …` e mai la password scritta nel comando, che finirebbe nella cronologia;
  - nella CLI (`pull`, `done --write`): se non c'è password (`_has_password`, `PGPASSWORD`, `SUPABASE_DB_PASSWORD`, `~/.pgpass`) e `stdin` non è un TTY, fermarsi prima di connettersi con questo messaggio, invece di far fallire `psql`;
  - da verificare anche per `core:db-push`, che suggerisce `! supabase db push` "se serve la password interattiva".
- **Plugin**: modeler (e core per db-push)
- **Tipo**: skill
- **Stato**: applicata il 2026-10-15: `_prod_query` (`plugins/modeler/scripts/metamodel/cli.py`, usato da `pull` e `done --write`) si ferma prima di collegarsi se non c'è password (DSN, `PGPASSWORD`, `SUPABASE_DB_PASSWORD`, `~/.pgpass`) e non c'è un terminale (`_can_prompt`), con la riga di `~/.pgpass` da aggiungere (`_pgpass_line`); senza terminale `psql` gira con `-w`, e l'errore `no password supplied` (es. `~/.pgpass` senza la riga del pooler) riceve lo stesso aiuto; test `test_pull_without_a_password_stops_before_psql`. Skill `modeler:apply` e `core:db-push` e README del modeler: niente più `! …` per comandi che chiedono la password, ma `SUPABASE_DB_PASSWORD`, `~/.pgpass` o un terminale proprio. Il comportamento di `supabase link`/`db push` con `! …` non è stato provato: la skill evita comunque `! …`.

## 2026-10-15 — Una pagina personalizzata che sostituisce la vista generica va collegata ovunque, non solo nel menu
- **Progetto**: guest-invitations-af (matrice delle tariffe del trattamento economico, `/x/economic_rate`, nata dalla nota "Lookup su più dimensioni")
- **Cosa è successo**: la nuova vista ha sostituito la lista generica `/e/economic_rate`, ma è stata collegata con un caso speciale scritto a mano solo nel menu (`layout.tsx`: `e.key === "economic_rate" ? "/x/…" : "/e/…"`). Gli altri link dell'app costruiscono ancora `/e/${entity}`: le schede della dashboard, "tutti i risultati" della ricerca, il link "← elenco" della scheda record, i redirect dopo salvataggio ed eliminazione, i link dei riferimenti. L'utente arriva di nuovo alla vecchia vista. Né la revisione né i test se ne sono accorti.
- **Proposta**:
  - convenzione (`conventions.md`, Lavoro sul codice): "Quando una pagina personalizzata sostituisce una vista generica, tutti i link all'entità passano da un'unica funzione (es. `entityListHref(key)` / `entityHref(key, id?)` con una mappa delle viste sostituite), non da casi speciali sparsi; prima di chiudere cerca nel codice tutti i punti che costruiscono quel percorso (`grep '/e/\${'`) e aggiungi un test che verifichi la mappa";
  - nelle app con pagine generiche `/e/[entity]` (stack ex appforge): valutare un campo di vista nel modello dell'app (`model.ts`, es. `listHref`) o un redirect in `src/proxy.ts` da `/e/<entità>` a `/x/<entità>`, così i link vecchi e salvati nei preferiti arrivano comunque alla vista nuova;
  - nella checklist del `core:code-reviewer`: per una pagina che sostituisce una vista esistente, controllare tutti i punti d'ingresso (menu, dashboard, ricerca, breadcrumb, redirect, riferimenti).
- **Plugin**: core
- **Tipo**: convenzione
- **Stato**: applicata il 2026-10-15 per la parte harness: riga in `plugins/core/context/conventions.md` (Lavoro sul codice: unica funzione con la mappa delle viste sostituite, redirect dal percorso vecchio, ricerca di tutti i punti che costruiscono il percorso, test sulla mappa) e punto "Punti d'ingresso" nella checklist di `plugins/core/agents/code-reviewer.md`. La parte app (`listHref` nel modello dell'app o redirect in `src/proxy.ts` da `/e/<entità>` a `/x/<entità>`) è lavoro di guest-invitations-af, da fare nella sua sessione: l'harness non ha un template per le app ex appforge.

## 2026-10-15 — Editor del modellatore: «+ Classe» / «+ Enum» posiziona il nuovo riquadro sopra uno esistente
- **Progetto**: order-management (modeler 0.11.2, `/admin/model`)
- **Cosa è successo**: cliccando «+ Classe» il riquadro `NuovaClasse` è comparso sopra `Department`, coprendolo in parte. `_freeSpot()` (`plugins/modeler/kit/metamodel-editor.js`, ~riga 596) parte dal centro della vista e scarta solo i punti entro 40px dall'angolo in alto a sinistra di un altro riquadro: non considera larghezza e altezza dei riquadri (né il riquadro nuovo), quindi un posto "libero" può cadere dentro un riquadro con l'angolo lontano.
- **Proposta**: estrarre il calcolo in una funzione pura (es. `freeSpot(occupied: {x,y,w,h}[], size: {w,h}, start: {x,y}, viewport)`) che cerca, a spirale o a griglia dal punto di partenza, il primo rettangolo che non interseca nessun riquadro (con un margine, es. 24px) e preferisce restare nella vista; usarla in `_addClass` e `_addEnum` con le dimensioni reali dei riquadri (le stesse usate dal layout). Test in `plugins/modeler/tests/layout.test.mjs`: nessuna intersezione con i riquadri esistenti, posizione stabile a parità di input, diagramma vuoto → punto di partenza. Rilascio con bump della versione del plugin; le app si aggiornano con `/modeler:install`.
- **Plugin**: modeler
- **Tipo**: altro
- **Stato**: applicata il 2026-10-15: `Layout.freeSpot(occupied, size, start, view)` in `plugins/modeler/kit/metamodel-editor.js` (pura: griglia a passi di 30px dal punto di partenza, il primo rettangolo che non interseca nessun riquadro con margine 24px, dentro la vista quando possibile); `_freeSpot(name)` la chiama con le misure reali (`_boxSize`) da `_addClass` e `_addEnum`. Test in `tests/layout.test.mjs` (nessuna intersezione, anche con le misure reali dei modelli di prova; stessa posizione a parità di input; diagramma vuoto → punto di partenza; vista piena → fuori dalla vista). Verificato anche in Chrome headless con tre riquadri aggiunti. Le app si aggiornano con `/modeler:install` dopo la release.
