# Handoff — sviluppo dell'harness iovino-harness
_Aggiornato: 2026-10-15 · branch `main`_

## Obiettivo
Marketplace personale di plugin per Claude Code, installabile su ogni computer con `./install.sh`:
convenzioni e guardrail comuni (`core`) e sviluppo model-based delle app Next.js + Supabase (`modeler`).
Si raffina un pezzo alla volta applicando le note raccolte nei progetti (`NOTES.md`, con `/core:harness-review`);
poi arriveranno i plugin `research` e `mde`.

## Stato
- Pubblicato su `origin/main` (`3ffbb42`): **core 0.7.1, modeler 0.11.2**. Nessun branch remoto aperto; resta solo
  il branch locale `fix/modeler-wrapper-react-lint`, fermo su `8b70469` e senza commit propri (cancellabile).
- Oggi (PR #1–#5):
  - **#1** `model:pull` senza DSN: lo ricava dal progetto collegato con `supabase link` (`supabase/.temp/pooler-url`
    o `project-ref`) o da `MODELER_PROD_DB` (`remote_dsn` in `plugins/modeler/scripts/metamodel/cli.py`);
    versione installata nella barra dell'editor (`install` sostituisce `__MODELER_VERSION__` in
    `kit/metamodel-editor.js`).
  - **#2** `apply` archivia con la proposta applicata le altre che contiene (`_contained` sui modelli espansi);
    nuovo `model:done [-- --write]` (`cmd_done`): segna `applied`/`rejected` in `model_change_requests` le
    proposte di `.modeler/proposals/applied/` e `rejected/`. `pull` salva l'`id` della riga.
  - **#3** `apply` tiene il `diagram` del file e ignora quello della proposta; se non può scrivere riga per riga,
    `--write` si ferma (riscrittura completa solo con `--rewrite`). Riga in `conventions.md`: controllare
    `origin/main` prima di dire in che stato è l'harness.
  - **#4** guardia in `guard_harness_edit` (`plugins/core/scripts/hook.py`): chiede conferma se una sessione aperta
    su un'altra cartella modifica il clone dell'harness (tranne `NOTES.md`); `/core:harness-note` suggerisce una
    seconda sessione nell'harness se il problema blocca il lavoro.
  - **#5** `_prod_query` (usato da `pull` e `done --write`) si ferma prima di collegarsi se non c'è password né
    terminale, con la riga di `~/.pgpass` da aggiungere (`_pgpass_line`); senza terminale `psql -w`; le skill
    `modeler:apply` e `core:db-push` non suggeriscono più `! …` per i comandi che chiedono la password.
- Flusso delle proposte di produzione (skill `modeler:apply`): `npm run model:pull` → `npm run model:apply`
  (poi `-- --write`) → migrazione e codice → `/core:db-push` → deploy → `npm run model:done -- --write`.
- `NOTES.md`: nessuna nota da valutare. Rinviate: il bus dell'editor; le proposte di produzione in
  `modeler proposals` (ora fattibile con `_prod_query`, in sola lettura); il controllo di `origin/main`
  nell'hook di sessione.
- Verificato (2026-10-15, su `main` prima del merge di #5): `python3 -m unittest discover -s tests` → 23 OK;
  `python3 -m unittest discover -s plugins/modeler/tests` → 48 OK (5 skip senza `MODELER_PG`; 48 OK con
  `MODELER_PG` sul container `postgres:16` dedicato); `claude plugin validate .` → passed.
- Non committato: nulla (salvo questo `HANDOFF.md`).

## Decisioni
- Le migliorie all'harness si annotano nella sessione dell'app (`/core:harness-note`) e si applicano in una
  sessione aperta nell'harness — solo lì è caricato il suo `CLAUDE.md` (branch, test, release), e il clone
  installato in place non va condiviso tra sessioni (oggi è comparso un commit estraneo su un branch e
  `NOTES.md` modificato da un'altra sessione). La guardia di #4 lo rende esplicito.
- `pull`/`done` dal progetto collegato, password solo da `SUPABASE_DB_PASSWORD`, `~/.pgpass` o un terminale proprio
  — mai in chat, nel comando o in file del repository; mai `! …` (non ha un terminale).
- `pull` non ripiega mai sul Supabase locale — ha senso solo in produzione.
- Proposte "contenute" confrontate sui modelli espansi, non sulle righe di `diff` — il diff perde
  `unique`/`default`/`label` (trovato dalla revisione di `core:code-reviewer`).
- Il `diagram` della proposta non entra nel repository; niente riscrittura completa silenziosa di
  `domain.ecore.yaml`.
- Controllo di `origin/main` come regola in `conventions.md`, non nell'hook — l'hook chiederebbe la rete a ogni avvio.

## Problemi aperti
- `model:pull` e `model:done --write` non ancora riusciti su un progetto cloud reale: in guest-invitations-af
  `done --write` è fallito con `fe_sendauth: no password supplied` (lanciato con `! …`, prima di #5). Sul computer
  esiste `~/.pgpass`, probabilmente senza la riga del pooler.
- `supabase link`/`supabase db push` lanciati con `! …` non provati: le skill comunque non li suggeriscono più così.
- La guardia di #4 copre solo Edit/Write, non le scritture fatte con comandi della shell.
- Le app nate con appforge citano ancora appforge.

## Prossimi passi
1. In guest-invitations-af: `/modeler:install` (la barra dell'editor deve mostrare `v0.11.2`) e `/reload-plugins`.
2. Aggiungere a `~/.pgpass` la riga `<host del pooler>:5432:postgres:postgres.<ref>:<password>` e `chmod 600` (la CLI
   stampa la riga esatta se manca), poi `npm run model:done -- --write`; verificare che le righe passino ad
   `applied` e spariscano da `/admin/model` in produzione.
3. Alla prossima proposta: tutto il flusso pull → apply → done, controllando che `git diff domain.ecore.yaml` mostri
   solo le righe cambiate.
4. Sugli altri computer: `claude plugin update core@iovino-harness` e `claude plugin update modeler@iovino-harness`.
5. Facoltativi: proposte di produzione in `modeler proposals`, `drift --linked`; poi plugin `mde` e `research`.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test con database: `docker run -d --rm --name modeler-pg-test -e POSTGRES_PASSWORD=pg -p 55499:5432 postgres:16`,
poi `MODELER_PG=postgresql://postgres:pg@localhost:55499/postgres python3 -m unittest discover -s plugins/modeler/tests`
e `docker stop modeler-pg-test` (non usare il database Supabase di un'app per i test).
File da leggere per primi: `CLAUDE.md`, `NOTES.md`, `plugins/modeler/skills/apply/SKILL.md`,
`plugins/modeler/scripts/metamodel/cli.py` (`cmd_apply`, `cmd_pull`, `cmd_done`, `remote_dsn`, `_prod_query`),
`plugins/core/scripts/hook.py` (`guard_harness_edit`), `plugins/core/context/conventions.md`.
