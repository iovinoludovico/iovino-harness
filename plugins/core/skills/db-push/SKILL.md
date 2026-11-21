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
- **Progetto non gestito dalla CLI** (manca `supabase/config.toml` o `supabase/.temp/project-ref`, le migrazioni non
  hanno il timestamp della CLI, oppure lo storico remoto non coincide con i file): non proporre subito
  `supabase link`. Prima `supabase projects list` deve mostrare il ref di produzione (quello di
  `NEXT_PUBLIC_SUPABASE_URL` o di `docs/deploy.md`); se l'account della CLI non lo vede («does not have the necessary
  privileges»), **fermati e dillo**: il link non può riuscire. Percorso alternativo, dichiarato come tale: elenco
  delle migrazioni da incollare nell'editor SQL della dashboard, in ordine, con i rischi del punto 3, e dopo ognuna
  una query di verifica (`select` su ciò che la migrazione crea: colonne in `information_schema.columns`, policy in
  `pg_policies`, funzioni in `pg_proc`) di cui l'utente incolla il risultato; nel resoconto scrivi che lo storico
  delle migrazioni non è tracciato dalla CLI.
- Server MCP di Supabase: usalo solo se è quello del progetto (`.mcp.json` del repository) e solo dopo aver
  confrontato il suo `project_ref` con quello dell'app (`NEXT_PUBLIC_SUPABASE_URL`, `supabase/.temp/project-ref`,
  `docs/deploy.md`): uno strumento MCP che punta a un altro progetto non si usa, nemmeno in lettura. Se manca
  `SUPABASE_DB_PASSWORD` ma il server MCP del progetto è collegato, `list_migrations` dà la colonna Remote del
  punto 3 senza password (solo lettura: le migrazioni non si applicano dal server MCP).
- Versione della CLI: `supabase --version` (o `npx supabase --version`, che risolve la versione del `package.json`).
  Dalla **3.0** i comandi del database (`db push`, `db pull`, `migration list`, `gen types`) agiscono sullo **stack
  locale** se non ricevono `--remote`: «Target: local stack … pass --remote» e «Local database is up to date» parlano
  del locale, non sono una conferma del cloud. Qui sotto i comandi sono scritti per la 3.x; con la 2.x `--remote`
  si chiama `--linked`.
- Password: prima di qualsiasi comando verso il cloud controlla che `SUPABASE_DB_PASSWORD` sia nell'ambiente
  (`[ -n "$SUPABASE_DB_PASSWORD" ]`) o che `~/.pgpass` esista. Se manca, **non lanciare i comandi**: la CLI la
  chiederebbe su un terminale che Claude Code non ha e il comando resterebbe appeso fino al timeout. Dai all'utente
  i comandi dei punti 3-5 da eseguire nel suo terminale (`supabase migration list --remote`, `supabase db push
  --dry-run --remote`, `supabase db push --remote`) e chiedigli di incollare l'output: è la base dei punti
  seguenti. Mai chiedere la password in chat, scriverla in file, nel repository o nel comando.

## 2. Pre-controlli (fermati se uno fallisce e spiega perché)
- `git status --porcelain supabase/`: le migrazioni devono essere committate; segnala il branch corrente
  (di solito si porta in produzione ciò che sta per andare su `main`).
- `supabase/.temp/` deve essere in `.gitignore` (`git check-ignore -q supabase/.temp`): `supabase --version` vi
  scrive `cli-latest`, che altrimenti risulta come modifica non committata e ferma `/core:ship`. Se manca, proponi
  la riga.
- Se il Supabase locale è attivo (`supabase status`): `supabase db reset` e `supabase test db` devono essere verdi.
  Se non è attivo, dillo e chiedi se proseguire comunque. In un'app senza Supabase locale le migrazioni nuove si
  possono provare su un Postgres usa-e-getta (`docker run --rm -d -e POSTGRES_PASSWORD=pg -p 55432:5432
  postgres:16`) con uno schema ridotto: ruoli `anon`/`authenticated`/`service_role`, `auth.uid()` e le altre
  funzioni di supporto finte, poi le migrazioni in ordine. Nel resoconto dichiara che cosa era finto: la prova
  dice che l'SQL è valido, non che RLS e Auth si comportano come in produzione.
- App con il modellatore (`domain.ecore.yaml` e script `model:drift`): `npm run model:drift` deve dare "aligned".

## 3. Cosa cambierebbe
- `supabase migration list --remote`: confronta le colonne Local e Remote.
  - migrazioni solo locali **più recenti** dell'ultima remota: sono quelle da applicare;
  - migrazioni solo locali **più vecchie** dell'ultima remota (fuori ordine): richiedono `--include-all`; non
    usarlo senza una richiesta esplicita dell'utente, dopo avergli spiegato il rischio;
  - migrazioni solo remote: il cloud ha qualcosa che il repository non ha. **Fermati**: va capito prima
    (migrazione fatta da un altro computer o a mano dalla dashboard).
- `supabase db push --dry-run --remote`: elenco esatto di ciò che verrebbe applicato.
- Leggi le migrazioni in arrivo e segnala i rischi: DDL distruttivo (`drop`, `alter … type`, `rename`), nuovi
  vincoli `not null` su tabelle piene, backfill lunghi, modifiche a RLS e permessi.
- Senza `SUPABASE_DB_PASSWORD` (punto 1) questi due comandi li esegue l'utente nel suo terminale, fuori da Claude
  Code (i comandi `! …` non hanno un terminale interattivo): leggi l'output che incolla come se fosse il tuo.
- Con `--dry-run` fermati qui con il resoconto.

## 4. Conferma ed esecuzione
Chiedi conferma con AskUserQuestion: progetto, elenco delle migrazioni, rischi; prima opzione "Applica", ultima
"Non ora". Con il sì: `supabase db push --remote --yes` (la 3.x chiede una conferma interattiva che senza
terminale blocca il comando: `--yes` la dà, dopo quella appena ricevuta dall'utente; senza `SUPABASE_DB_PASSWORD`
lo esegue l'utente nel suo terminale, senza `--yes`, e incolla l'output).

## 5. Verifica e resoconto
- `supabase migration list --remote`: Local e Remote devono coincidere (o l'output incollato dall'utente).
- Ricorda l'ordine: **prima il database, poi il push del codice** che usa le migrazioni nuove (le immagini
  non applicano migrazioni).
- App con il modellatore: proponi `MODELER_DB=<DSN di produzione> npm run model:drift` solo se l'utente fornisce il
  DSN (è un segreto: non salvarlo).
- Resoconto: progetto, migrazioni applicate, esito della verifica, prossimo passo. Se il database remoto era vuoto
  (primo deploy), il prossimo passo è il deploy con i passi della skill `core:deploy` (Supabase Auth, pannello,
  proxy): rimanda a quelli, non inventare istruzioni per il server; a deploy fatto, `/core:security-audit`.

In CI gli stessi passi (pre-controlli, elenco, stop sulle migrazioni remote sconosciute o fuori ordine, `db push
--db-url … --yes`) li fa il workflow `modeler-release` di un'app con il modellatore, avviato da «Conferma e rilascia» in
`/admin/model` (skill `modeler:install`, sezione 7).

## Regole
- Mai `supabase db reset --remote` (né `--linked`), mai `supabase migration repair`, mai `--include-all` senza richiesta esplicita.
- Mai modificare una migrazione già applicata: le correzioni sono migrazioni nuove.
- Dopo un errore non riprovare da solo: riporta l'output completo e proponi come procedere.
