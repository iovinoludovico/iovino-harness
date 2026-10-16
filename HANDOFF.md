# Handoff — sviluppo dell'harness iovino-harness
_Aggiornato: 2026-10-16 · branch `main`_

## Obiettivo
Marketplace personale di plugin per Claude Code, installabile su ogni computer con `./install.sh`:
convenzioni e guardrail comuni (`core`) e sviluppo model-based delle app Next.js + Supabase (`modeler`).
Si raffina un pezzo alla volta applicando le note raccolte nei progetti (`NOTES.md`, con `/core:harness-review`);
poi arriveranno i plugin `research` e `mde`.

## Stato
- Pubblicato su `origin/main` con la PR #8 (`3033016`): **core 0.8.0, modeler 0.12.1**. Nessun branch aperto, né locale né remoto.
- PR #1–#8 (15–16 ottobre):
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
  - **#6** `Layout.freeSpot(occupied, size, start, view)` in `kit/metamodel-editor.js` (pura, testata in
    `tests/layout.test.mjs`): «+ Classe»/«+ Enum» mettono il riquadro nuovo su spazio libero, con le misure reali
    dei riquadri. Riga in `conventions.md` e punto "Punti d'ingresso" nel `code-reviewer`: una pagina che
    sostituisce una vista generica si collega da un'unica funzione con la mappa delle viste sostituite.
  - **#7** `docs/DOMAIN.md` generato dal metamodello (`to_markdown`/`markdown_document` in `ecore.py`): intestazione,
    diagramma Mermaid, una sezione per classe (attributi, riferimenti, regole), enum con etichette, nella lingua del
    metamodello. Nuova chiave `rules` (`[{id, text}]`) su package e classi: validata, in `diff` (CLI ed editor),
    scritta riga per riga da `apply`, annotazione `rules` in Ecore; nessun effetto sul database. Il file è l'inbox
    delle note a mano: `npm run model:docs` (`cmd_docs`) elenca le sezioni toccate con un estratto di diff;
    `npm run model:sync` (`sync`, `docs_status`) rigenera solo se `missing`/`aligned`/`stale` e rifiuta con exit 1
    se `edited`, `-- --force` fa il backup in `.modeler/backups/DOMAIN.md.<ts>` e riscrive. Le note si misurano
    contro `.modeler/DOMAIN.generated.md` (copia di ciò che `sync` ha scritto l'ultima volta), non contro la
    generazione attuale. `/modeler:metamodel` passo 0 traduce le note (struttura → metamodello e migrazione,
    vincoli esprimibili → chiavi, il resto → `rules`); l'hook di sessione segnala `edited`/`stale`/`missing`;
    `install` scrive il file e `show --format markdown` lo stampa senza marker.
  - **#8** (revisione delle note del 2026-10-16) `docs_clash` in `cli.py`: un `docs/domain.md` con altre maiuscole
    (app ex appforge) dà stato `clash` in `docs_status`; `sync` (anche `--force`), `install` e `apply` non scrivono
    `DOMAIN.md` e dicono di rinominarlo o cancellarlo, l'hook di sessione lo segnala. `BOX_W` tolta dal kit;
    `tests/lint.test.mjs` fallisce su ogni costante maiuscola del kit mai usata (toglie l'avviso di eslint nelle app).
- Flusso delle proposte di produzione (skill `modeler:apply`): `npm run model:pull` → `npm run model:apply`
  (poi `-- --write`) → migrazione e codice → `/core:db-push` → deploy → `npm run model:done -- --write`.
- `NOTES.md`: nessuna nota da valutare (le due del 2026-10-16 applicate con #8). Rinviate: il bus dell'editor; le proposte di produzione in
  `modeler proposals` (ora fattibile con `_prod_query`, in sola lettura); il controllo di `origin/main`
  nell'hook di sessione.
- Verificato (2026-10-16, prima del merge di #8): `python3 -m unittest discover -s tests` → 23 OK;
  `python3 -m unittest discover -s plugins/modeler/tests` → 56 OK (5 skip senza `MODELER_PG`; con `MODELER_PG`
  sul container `postgres:16` dedicato verificato prima di #5); `node --test plugins/modeler/tests/layout.test.mjs
  plugins/modeler/tests/diff.test.mjs plugins/modeler/tests/lint.test.mjs` → 93 pass, 1 todo (il bus); `node --test`
  sulla cartella non funziona con questo Node, vanno elencati i file; `claude plugin validate .` → passed. Prova
  manuale di #7 in un'app temporanea: `install` → nota a mano → `docs` → `sync` (rifiuta) → `sync --force`
  (backup e rigenera); revisione `core:code-reviewer` applicata.
- Non committato: nulla.

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
- `docs/DOMAIN.md`: fonte di verità il metamodello, il file è generato e serve da inbox (modifiche a mano
  rilevate e tradotte da `/modeler:metamodel`, poi rigenerato) — un file scritto a mano andrebbe fuori sincrono.
  `rules` solo `{id, text}`, senza `sql` → CHECK (scartato per ora). Diagramma Mermaid in cima. Le note a mano si
  confrontano con la copia generata, non con la generazione attuale: altrimenti con metamodello cambiato e nota
  insieme il report le mescolava (trovato dalla revisione). Riformattazioni (Prettier) non contano come modifiche.

## Problemi aperti
- `model:pull` e `model:done --write` non ancora riusciti su un progetto cloud reale: in guest-invitations-af
  `done --write` è fallito con `fe_sendauth: no password supplied` (lanciato con `! …`, prima di #5). Sul computer
  esiste `~/.pgpass`, probabilmente senza la riga del pooler.
- `supabase link`/`supabase db push` lanciati con `! …` non provati: le skill comunque non li suggeriscono più così.
- La guardia di #4 copre solo Edit/Write, non le scritture fatte con comandi della shell.
- Le app nate con appforge citano ancora appforge.
- Un'altra sessione ha committato una nota direttamente su `main` locale (`9651a19`, non pushato): il branch della
  revisione l'ha portata nella PR #8 e `main` è stato riallineato con `git reset --hard origin/main`. Le note vanno
  committate nell'harness solo dalla sessione aperta qui, o lasciate nel working tree.
- `docs/DOMAIN.md` non ancora visto in un'anteprima Markdown/GitHub (tabelle, blocco Mermaid) né provato il passo 0
  di `/modeler:metamodel` con note vere in un'app.
- Parte app della nota sulle viste sostituite, ancora da fare in guest-invitations-af: `listHref` nel modello
  dell'app o redirect in `src/proxy.ts` da `/e/economic_rate` a `/x/economic_rate` (oggi solo il menu ha il caso
  speciale; dashboard, ricerca, breadcrumb, redirect e riferimenti portano ancora alla vista generica).

## Prossimi passi
1. In guest-invitations-af e order-management: `/reload-plugins` e `/modeler:install` (la barra dell'editor deve
   mostrare `v0.12.1`, `npm run lint` senza l'avviso su `BOX_W`; scrive `docs/DOMAIN.md`, da aggiungere a
   `.prettierignore` se l'app formatta `docs/`; in guest-invitations-af `docs/domain.md` è già stato rinominato
   `docs/behavior.md`);
   aprire `docs/DOMAIN.md` su GitHub e provare una nota a mano → `npm run model:docs` → `/modeler:metamodel`;
   in guest-invitations-af chiudere la parte app della nota sulle viste sostituite.
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
`plugins/modeler/scripts/metamodel/cli.py` (`cmd_apply`, `cmd_pull`, `cmd_done`, `remote_dsn`, `_prod_query`,
`docs_status`, `docs_clash`, `sync`, `cmd_docs`), `plugins/modeler/scripts/metamodel/ecore.py` (`to_markdown`, `markdown_changes`),
`plugins/modeler/skills/metamodel/SKILL.md` (passo 0),
`plugins/core/scripts/hook.py` (`guard_harness_edit`), `plugins/core/context/conventions.md`.
