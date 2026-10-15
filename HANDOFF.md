# Handoff — sviluppo dell'harness iovino-harness
_Aggiornato: 2026-10-15 · branch `fix/harness-review-apply-diagram`_

## Obiettivo
Marketplace personale di plugin per Claude Code, installabile su ogni computer con `./install.sh`:
convenzioni e guardrail comuni (`core`) e sviluppo model-based delle app Next.js + Supabase (`modeler`).
Si raffina un pezzo alla volta applicando le note raccolte nei progetti (`NOTES.md`, con `/core:harness-review`);
poi arriveranno i plugin `research` e `mde`.

## Stato
- Pubblicato su `origin/main` (`94396cc`): core 0.6.0, modeler 0.11.0.
- Branch aperto `fix/harness-review-apply-diagram`, 3 commit non pubblicati e **senza release** (`release.py`
  propone core 0.6.1, modeler 0.11.1):
  - `e97760a` fix(modeler): `apply` tiene il `diagram` del file e ignora quello della proposta; se la modifica non
    si scrive riga per riga, `--write` si ferma (riscrittura completa solo con `--rewrite`). In
    `cmd_apply` di `plugins/modeler/scripts/metamodel/cli.py`. Causa verificata: con il `diagram` della proposta
    assente dal file, `patch_text` (`ecore.py`) ritornava `None` e si riscriveva tutto;
  - `2cbf0ad` docs(core): riga in `plugins/core/context/conventions.md` ("Lavoro sul codice"): `git fetch --prune` e
    controllo di `origin/main` prima di dire in che stato è l'harness;
  - `0372646` docs: decisioni in `NOTES.md` (include le note aggiunte da un'altra sessione).
- Flusso delle proposte di produzione nel modeler 0.10–0.11 (da `/modeler:apply`):
  1. `npm run model:pull`: DSN dal progetto collegato con `supabase link` (`supabase/.temp/pooler-url` o
     `project-ref`) o `MODELER_PROD_DB`; password da `SUPABASE_DB_PASSWORD`, `~/.pgpass` o dal prompt di `psql`
     (`remote_dsn`, `_prod_query`). Il file della proposta ora contiene l'`id` della riga.
  2. `npm run model:apply [-- <file>] [--write]`: archivia con la proposta applicata le altre che contiene
     (`_contained` sui modelli espansi, non sulle righe di `diff`), elenca le altre come "Still pending".
  3. Migrazione e codice, `/core:db-push`, deploy.
  4. `npm run model:done [-- --write]`: segna `applied`/`rejected` in `model_change_requests` le proposte di
     `.modeler/proposals/applied/` e `rejected/`; segnala le righe già chiuse in produzione senza sovrascriverle.
  - L'editor mostra la versione installata nella barra (`v0.11.0`), scritta da `install` al posto di
    `__MODELER_VERSION__` in `kit/metamodel-editor.js`.
- `NOTES.md`: 7 note, nessuna da valutare. Rinviate: il bus dell'editor; le proposte di produzione in
  `modeler proposals` (ora fattibile riusando `_prod_query`); il controllo di `origin/main` nell'hook di sessione.
- Verificato (2026-10-15, sul branch): `python3 -m unittest discover -s tests` → 22 OK;
  `python3 -m unittest discover -s plugins/modeler/tests` → 47 OK (5 skip senza `MODELER_PG`; con `MODELER_PG`
  47 OK, incluso `test_pull_apply_done` end-to-end); `claude plugin validate .` → passed.
- Non committato: nulla (salvo questo `HANDOFF.md`).

## Decisioni
- `pull`/`done` dal progetto collegato invece del DSN incollato — `supabase link` è già richiesto da
  `/core:db-push`; la password non va mai in file né sulla riga di comando (`PGPASSWORD` nell'ambiente di `psql`).
- `pull` non ripiega mai sul Supabase locale — ha senso solo in produzione.
- Proposte "contenute" confrontate sui modelli espansi — il confronto sulle righe di `diff` perdeva modifiche a
  `unique`/`default`/`label` (trovato dalla revisione di `core:code-reviewer`).
- Il `diagram` della proposta non entra nel repository — le posizioni sono stato dell'editor, e il layout
  automatico le ricalcola.
- Niente riscrittura completa silenziosa di `domain.ecore.yaml` — meglio fermarsi e chiedere `--rewrite`.
- Controllo di `origin/main` come regola, non nell'hook — l'hook chiederebbe la rete a ogni avvio.

## Problemi aperti
- `model:pull` e `model:done` non sono ancora stati provati su un progetto cloud reale (né il prompt della password
  di `psql` con l'output catturato).
- Il modellatore 0.11 non è ancora installato in guest-invitations-af: l'utente farà `/modeler:install` e l'apply.
- I test su database di questa sessione sono girati sul Postgres del Supabase locale di
  `appforge-order-management` (porta 55022), su database temporanei `modeler_*` creati e cancellati: contro la
  regola qui sotto; la prossima volta usare il container dedicato.
- Le app nate con appforge citano ancora appforge.

## Prossimi passi
1. Pubblicare il branch: `/core:ship` (lancia `python3 scripts/release.py --write` → core 0.6.1, modeler 0.11.1,
   poi PR e merge con conferma).
2. In guest-invitations-af: `/modeler:install` (la barra dell'editor deve mostrare la nuova versione), poi
   `! npm run model:pull`, `npm run model:apply`, `/modeler:apply` per migrazione e codice, `/core:db-push`, deploy,
   `npm run model:done -- --write`. Verificare che `git diff domain.ecore.yaml` mostri solo le righe cambiate.
3. Sugli altri computer: `claude plugin update core@iovino-harness` e `claude plugin update modeler@iovino-harness`.
4. Se serve: proposte di produzione in `modeler proposals` (sola lettura con `_prod_query`), `drift --linked`.
5. Plugin `mde` (Eclipse/EMF, Epsilon) e `research`.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test con database: `docker run -d --rm --name modeler-pg-test -e POSTGRES_PASSWORD=pg -p 55499:5432 postgres:16`,
poi `MODELER_PG=postgresql://postgres:pg@localhost:55499/postgres python3 -m unittest discover -s plugins/modeler/tests`
(non usare il database Supabase di un'app per i test).
File da leggere per primi: `CLAUDE.md`, `NOTES.md`, `plugins/modeler/skills/apply/SKILL.md`,
`plugins/modeler/scripts/metamodel/cli.py` (`cmd_apply`, `cmd_pull`, `cmd_done`, `remote_dsn`),
`plugins/core/context/conventions.md`.
