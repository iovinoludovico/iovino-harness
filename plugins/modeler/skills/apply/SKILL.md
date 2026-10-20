---
name: apply
description: Applica le proposte di modifica del metamodello salvate dal modellatore web di un'app o da /modeler:metamodel (.modeler/proposals in sviluppo, tabella model_change_requests in produzione, o un file scaricato) e porta la modifica fino a migrazione, codice e verifica di allineamento. Va usata quando l'utente dice "applica la proposta del modellatore", "ho salvato una modifica in /admin/model", "ci sono proposte da produzione", o invoca /modeler:apply.
argument-hint: "[file della proposta] | pull [DSN di produzione]"
---

# Applicare una proposta del modellatore

Argomenti: `$ARGUMENTS`. Nell'app: `npm run model:proposals`, `npm run model:apply -- …`
(oppure `python3 tools/modeler/modeler.py …`).

1. **Proposte da produzione**: con `pull` esegui `npm run model:pull` (una sola: `-- --id <uuid>`; con un DSN esplicito:
   `npm run model:pull -- --db <DSN>`) solo dopo conferma esplicita dell'utente (scrive sul database di
   produzione: segna le proposte come `pulled`). Le copia in `.modeler/proposals/`.
   - Il DSN si ricava dal progetto collegato con `supabase link` (`supabase/.temp/`), o da `MODELER_PROD_DB`.
     Non collegato: fai eseguire all'utente `supabase link --project-ref <ref>` in un suo terminale.
   - La password viene da `SUPABASE_DB_PASSWORD` (esportata prima di avviare Claude Code) o da `~/.pgpass`
     (la CLI, se manca, stampa la riga da aggiungere; poi `chmod 600 ~/.pgpass`). Altrimenti l'utente lancia il
     comando in un suo terminale, fuori da Claude Code. Non suggerire `! npm run model:pull`: i comandi `! …`
     non hanno un terminale e `psql` non può chiedere la password. Mai chiedere la password in chat, scriverla
     in file del repository o nel comando.
   - Manca lo script `model:pull`: il modellatore installato è vecchio, aggiornalo con `/modeler:install`.
2. `npm run model:proposals`: elenca le proposte (dal modellatore web, o «from the prompt» se salvate da
   `/modeler:metamodel` con `model:propose`) con le differenze rispetto a `domain.ecore.yaml` e, per le proposte
   che portano anche il comportamento (chiave `behavior`, salvata dal modellatore quando l'app ha `behavior.yaml`),
   le righe `behaviour: …` (ruoli, derivazioni, stati, transizioni, ritorno, eventi, reazioni).
3. `npm run model:apply -- [file]` (prova a vuoto; senza file, la proposta più recente): mostra all'utente le
   modifiche e la validazione; segnala ciò che comporta perdita di dati (classi, feature o letterali rimossi) e
   chiedi conferma. Ogni proposta è un metamodello intero: la prova a vuoto elenca le altre proposte già
   contenute in quella scelta (archiviate con lei) e quelle con modifiche in più ("Still pending"), da
   applicare una per una indicando il file o da scartare dal modellatore.
4. Con conferma: `npm run model:apply -- [file] --write` (backup in `.modeler/backups/`, proposta spostata in
   `.modeler/proposals/applied/` insieme a quelle che contiene, `metamodel.json` aggiornato: da qui la proposta
   non compare più tra quelle in attesa nel modellatore locale). Se la proposta porta il comportamento, `apply` lo
   valida contro il metamodello proposto (se non è valido non scrive nulla, né metamodello né comportamento) e
   riscrive `behavior.yaml` per intero (backup in `.modeler/backups/`; i commenti del file non si conservano e
   vengono elencati): controlla `git diff behavior.yaml` e riporta a mano i commenti che contano. Poi `sync`
   rigenera `behavior.json` e `docs/BEHAVIOR.md`; se il comportamento è cambiato, il motore segue la skill `behavior`,
   punto 4: `npm run model:engine -- --write` con il motore generato (una migrazione sostituita), SQL da riportare
   a mano con un motore scritto a mano (`CUSTOM(*-workflow)`: mai `engine --write`); poi `npm run model:drift`. Il file cambia solo nelle righe di ciò che è
   cambiato (ordine, stile e commenti restano); le posizioni del diagramma salvate dall'editor non entrano (il
   file tiene le sue). Se la modifica non si può scrivere riga per riga (intestazione del package, file con un
   layout insolito) `--write` si ferma senza scrivere: applicala a mano, oppure, solo se l'utente accetta di
   perdere ordine, virgolette e commenti, `--write --rewrite`. Se `git diff domain.ecore.yaml` mostra più delle
   righe attese, fermati e segnalalo invece di committare. Se la proposta porta una collezione a `lower > 0` o a un
   `upper` finito (es. `orderLines` da `0..*` a `1..*`), il database non impone il vincolo: proponi subito la guardia
   sulla prima transizione del workflow (`orderLines.notEmpty()`; chiedi su quale) o la regola dell'app, con un test
   della transizione bloccata (skill `behavior`, punto 2); `validate` lo segnala finché manca.
5. Prosegui come la skill `metamodel`, sezione "Applicare": `npm run model:migrate -- --name <nome>
   --write` (bozza dal metamodello committato a quello appena scritto), TODO risolti, codice, migrazione
   applicata in locale, `npm run model:drift` → "aligned", typecheck, lint e test.
   In produzione la migrazione va applicata con `/core:db-push` prima del push del codice.
   Una proposta di produzione può arrivare anche come **PR già aperta** dal bottone «Applica» di `/admin/model`
   (workflow `modeler-apply`, skill `install` sezione 7): revisione della PR, `/core:db-push` prima del merge, merge
   confermato, poi il punto 6 come per ogni proposta di produzione; oppure l'admin la rilascia da `/admin/model`
   («Conferma e rilascia», workflow `modeler-release`), che fa db push, merge, attesa del deploy e `model:done` da
   solo: in quel caso qui non c'è nulla da fare, salvo leggere l'esito sulla riga o nel run.
6. Per le proposte arrivate da produzione, dopo il deploy e solo su richiesta dell'utente: `npm run model:done`
   (prova a vuoto) e `npm run model:done -- --write`. Segna `applied` in `model_change_requests` le proposte in
   `.modeler/proposals/applied/` e `rejected` quelle scartate dal modellatore locale (`rejected/`), così spariscono
   anche dal modellatore di produzione. Usa lo stesso progetto collegato e la stessa password di `model:pull`.
