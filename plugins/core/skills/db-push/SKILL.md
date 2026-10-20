---
name: db-push
description: Applica al database Supabase cloud (produzione) le migrazioni del repository che non vi sono ancora, in modo controllato - progetto collegato, pre-controlli locali, elenco di cosa cambierebbe, conferma esplicita, supabase db push, verifica. Usala quando l'utente chiede "porta le migrazioni in produzione", "aggiorna il database cloud", "fai il db push", "supabase db push", prima di pubblicare codice che richiede migrazioni nuove, o invoca /core:db-push.
argument-hint: "[--dry-run]"
---

# Migrazioni sul Supabase cloud

Argomenti: `$ARGUMENTS` (`--dry-run`: fermati dopo il punto 3, senza applicare nulla).

Il database cloud è la produzione: ogni passo che scrive chiede conferma. L'hook di `core` chiederà comunque
conferma per `supabase db push` e `supabase link`: è voluto.

## 1. Contesto
- Radice dell'app: la cartella con `supabase/config.toml` e `supabase/migrations/`.
- Progetto collegato: `supabase/.temp/project-ref`. Mostralo all'utente con il nome del progetto se lo conosci
  (CLAUDE.md o `docs/deploy.md` dell'app): è il database su cui scriverai.
- Non collegato: fai eseguire all'utente `supabase link --project-ref <ref>` in un suo terminale, fuori da Claude
  Code (può chiedere la password del database: un comando `! …` non ha un terminale interattivo e la richiesta
  può fallire). Non chiedere la password in chat.

## 2. Pre-controlli (fermati se uno fallisce e spiega perché)
- `git status --porcelain supabase/`: le migrazioni devono essere committate; segnala il branch corrente
  (di solito si porta in produzione ciò che sta per andare su `main`).
- Se il Supabase locale è attivo (`supabase status`): `supabase db reset` e `supabase test db` devono essere verdi.
  Se non è attivo, dillo e chiedi se proseguire comunque.
- App con il modellatore (`domain.ecore.yaml` e script `model:drift`): `npm run model:drift` deve dare "aligned".

## 3. Cosa cambierebbe
- `supabase migration list --linked`: confronta le colonne Local e Remote.
  - migrazioni solo locali **più recenti** dell'ultima remota: sono quelle da applicare;
  - migrazioni solo locali **più vecchie** dell'ultima remota (fuori ordine): richiedono `--include-all`; non
    usarlo senza una richiesta esplicita dell'utente, dopo avergli spiegato il rischio;
  - migrazioni solo remote: il cloud ha qualcosa che il repository non ha. **Fermati**: va capito prima
    (migrazione fatta da un altro computer o a mano dalla dashboard).
- `supabase db push --dry-run`: elenco esatto di ciò che verrebbe applicato.
- Leggi le migrazioni in arrivo e segnala i rischi: DDL distruttivo (`drop`, `alter … type`, `rename`), nuovi
  vincoli `not null` su tabelle piene, backfill lunghi, modifiche a RLS e permessi.
- Se un comando chiede la password del database: usa `SUPABASE_DB_PASSWORD` se è già nell'ambiente (esportata
  prima di avviare Claude Code), altrimenti fai eseguire il comando all'utente in un suo terminale, fuori da
  Claude Code: i comandi `! …` non hanno un terminale interattivo. Mai scrivere la password in file, nel
  repository o nel comando.
- Con `--dry-run` fermati qui con il resoconto.

## 4. Conferma ed esecuzione
Chiedi conferma con AskUserQuestion: progetto, elenco delle migrazioni, rischi; prima opzione "Applica", ultima
"Non ora". Con il sì: `supabase db push` (se serve la password e `SUPABASE_DB_PASSWORD` non c'è, lo esegue
l'utente in un suo terminale).

## 5. Verifica e resoconto
- `supabase migration list --linked`: Local e Remote devono coincidere.
- Ricorda l'ordine: **prima il database, poi il push del codice** che usa le migrazioni nuove (le immagini
  non applicano migrazioni).
- App con il modellatore: proponi `MODELER_DB=<DSN di produzione> npm run model:drift` solo se l'utente fornisce il
  DSN (è un segreto: non salvarlo).
- Resoconto: progetto, migrazioni applicate, esito della verifica, prossimo passo. Se il database remoto era vuoto
  (primo deploy), il prossimo passo è il deploy con i passi della skill `core:deploy` (Supabase Auth, pannello,
  proxy): rimanda a quelli, non inventare istruzioni per il server; a deploy fatto, `/core:security-audit`.

In CI gli stessi passi (pre-controlli, elenco, stop sulle migrazioni remote sconosciute o fuori ordine, `db push`
--db-url) li fa il workflow `modeler-release` di un'app con il modellatore, avviato da «Conferma e rilascia» in
`/admin/model` (skill `modeler:install`, sezione 7).

## Regole
- Mai `supabase db reset --linked`, mai `supabase migration repair`, mai `--include-all` senza richiesta esplicita.
- Mai modificare una migrazione già applicata: le correzioni sono migrazioni nuove.
- Dopo un errore non riprovare da solo: riporta l'output completo e proponi come procedere.
