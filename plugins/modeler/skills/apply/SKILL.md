---
name: apply
description: Applica le proposte di modifica del metamodello salvate dal modellatore web di un'app (.modeler/proposals in sviluppo, tabella model_change_requests in produzione, o un file scaricato) e porta la modifica fino a migrazione, codice e verifica di allineamento. Va usata quando l'utente dice "applica la proposta del modellatore", "ho salvato una modifica in /admin/model", "ci sono proposte da produzione", o invoca /modeler:apply.
argument-hint: "[file della proposta] | pull [DSN di produzione]"
---

# Applicare una proposta del modellatore

Argomenti: `$ARGUMENTS`. Nell'app: `npm run model:proposals`, `npm run model:apply -- …`
(oppure `python3 tools/modeler/modeler.py …`).

1. **Proposte da produzione**: con `pull` esegui `npm run model:pull` (con un DSN esplicito:
   `npm run model:pull -- --db <DSN>`) solo dopo conferma esplicita dell'utente (scrive sul database di
   produzione: segna le proposte come `pulled`). Le copia in `.modeler/proposals/`.
   - Il DSN si ricava dal progetto collegato con `supabase link` (`supabase/.temp/`), o da `MODELER_PROD_DB`.
     Non collegato: fai eseguire all'utente `! supabase link --project-ref <ref>`.
   - La password viene da `SUPABASE_DB_PASSWORD`, `~/.pgpass` o dal prompt di `psql`: se non è nell'ambiente,
     fai eseguire all'utente `! npm run model:pull`. Mai chiedere la password in chat né scriverla in file.
   - Manca lo script `model:pull`: il modellatore installato è vecchio, aggiornalo con `/modeler:install`.
2. `npm run model:proposals`: elenca le proposte con le differenze rispetto a `domain.ecore.yaml`.
3. `npm run model:apply -- [file]` (prova a vuoto): mostra all'utente le modifiche e la validazione; segnala
   ciò che comporta perdita di dati (classi, feature o letterali rimossi) e chiedi conferma.
4. Con conferma: `npm run model:apply -- [file] --write` (backup in `.modeler/backups/`, proposta spostata in
   `.modeler/proposals/applied/`, `metamodel.json` aggiornato). Il file cambia solo nelle righe di ciò che è
   cambiato (ordine, stile e commenti restano); se `git diff domain.ecore.yaml` mostra di più, fermati e
   segnalalo invece di committare.
5. Prosegui come la skill `metamodel`, sezione "Allineare l'applicazione": `npm run model:migrate -- --name <nome>
   --write` (bozza dal metamodello committato a quello appena scritto), TODO risolti, codice, migrazione
   applicata in locale, `npm run model:drift` → "aligned", typecheck, lint e test.
   In produzione la migrazione va applicata con `/core:db-push` prima del push del codice.
6. Per le proposte arrivate da produzione: dopo il deploy, segna la riga come `applied` (o `rejected`) solo su
   richiesta dell'utente.
