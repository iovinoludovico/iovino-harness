# Handoff — Harness dopo la revisione del 2026-11-20 (PR #44, #45): apply voce per voce, MCP Supabase di progetto, note che arrivano nel repository
_Aggiornato: 2026-11-21 · branch `main` (`fd85475`, PR #45), allineato a `origin/main`_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core` 0.26.0, `modeler` 0.40.1). La revisione del 2026-11-20 ha
valutato nove note di `NOTES.md` (otto arrivate dal file di riserva, una aggiunta in revisione) e le ha applicate con
la PR #44; la PR #45 corregge `install.sh`. `NOTES.md` ha 0 note aperte e 2 rinviate.

## Stato
- Fatto (PR #44, `80d8dbe`, squash di otto commit):
  - **`apply --write` voce per voce** (nota 2026-11-09): `patch_text` in `plugins/modeler/scripts/metamodel/ecore.py`
    modifica le regole del package e di classe una per riga (`_rule_edits`, `_rule_line`, virgolette della vicina), le
    chiavi di classe (`doc`, `label`, `unique`…) una per riga in `feature_edits`, gli `attributes`/`references` su una
    riga restando su una riga, una classe nuova nello stile del file (`class_lines`). Un blocco si riscrive intero solo
    se è scritto come lo scrive `dumps` (`canonical`); altrimenti `apply --write` si ferma. Sul metamodello di ACS-GSSI
    una regola cambiata dà +1 −1 (prima +76 −20).
  - **Supabase** (note 2026-11-15 e 2026-11-20): `core:db-push` §1 ha il caso «progetto non gestito dalla CLI»
    (`supabase projects list` prima di `link`, percorso dall'editor SQL con query di verifica) e la regola sul server
    MCP (confronto del `project_ref`, `list_migrations` senza password); §2 `supabase/.temp/` in `.gitignore` e prova
    su Postgres usa-e-getta. `core:ship` §2 chiede delle migrazioni nuove anche senza `project-ref`. Server MCP di
    Supabase solo a scope progetto: `conventions.md`, `core:project-init`, `core:deploy` §1.5, avviso a inizio sessione
    (`supabase_mcp_warnings` in `plugins/core/scripts/hook.py`).
  - **Build, output degli strumenti, query** (note 2026-11-16 e 2026-11-18): tre righe in `conventions.md` «Lavoro sul
    codice»; `core:ship` §2 `npm run build` letto dal codice di uscita; `npm audit --omit=dev` nel blocco D di
    `core:security-audit`; punto 10 «Errori delle query» in `agents/code-reviewer.md`.
  - **Branch non allineato** (nota 2026-11-19): riga in `conventions.md` «Git»; `core:ship` §1 propone il commit.
  - **Branding** (nota 2026-11-20, in parte): riga in `conventions.md` «Stack ricorrente», controlli in
    `core:project-init` e `core:security-audit` blocco D.
  - **Note che non si perdono** (due note 2026-11-20): `hook.py` trova il clone (`configured_harness`,
    `find_harness_clone` in `~/Documents/GitHub`), scrive in ogni sessione dove vanno le note, conta quelle nel file di
    riserva e i commit `docs(notes)` non pubblicati (`harness_notes_info`); `core:harness-note` committa il solo
    `NOTES.md` se il clone è su `main`, mai push; `core:harness-review` §1 importa il file di riserva.
- Fatto (PR #45, `fd85475`): `install.sh` imposta `harness_repo` con `claude plugin configure --values-stdin` anche
  quando il plugin viene solo aggiornato (prima solo con `claude plugin install`).
- Verificato (2026-11-21, prima del push della PR #44, Postgres spento): `python3 -m unittest discover -s tests` →
  26 OK; `-s plugins/modeler/tests` → 130 OK, 10 saltati (quelli con `MODELER_PG`); `node --test
  plugins/modeler/tests/*.test.mjs` → 191 OK; `claude plugin validate .` → passed. Dopo il merge rieseguiti solo i test
  core (26 OK). Della PR #45 è stato eseguito solo il blocco nuovo di `install.sh` (prima volta imposta, seconda non
  tocca), non lo script intero. Nessuna CI nel repository.
- Su questo computer: `./install.sh` eseguito (core 0.26.0, modeler 0.40.1, permessi con il commit di `NOTES.md`),
  `harness_repo` impostata su questo clone, `/reload-plugins` dato; file di riserva vuoto.
- Non committato: questo `HANDOFF.md`.
- Modellatore installato nei cloni locali (sola lettura, senza `git pull`): order-management, invitations-af e
  ACS-GSSI 0.40.0; LudoActivityManager 0.39.0; modeler-sandbox 0.36.2. Nessuna ha la 0.40.1.

## Decisioni
- **Un blocco scritto a mano non si riscrive mai intero** (PR #44) — `apply --write` si ferma se la modifica non si
  lascia fare riga per riga; può fermarsi più spesso di prima, resta `--rewrite`. Gli enum si riscrivono ancora a
  blocco intero (fuori dalla nota).
- **Server MCP: regola solo per Supabase** — estenderla a ogni server MCP di progetto era un'interpretazione, non un
  caso visto.
- **`npm audit` a inizio sessione scartato** — lento e richiede la rete; sta in `core:security-audit`.
- **«Non allineato» = modifiche non committate o commit non pubblicati** — si propone commit e push a fine lavoro; un
  branch indietro rispetto a `main` si segnala soltanto.
- **Branding = nome, sottotitolo, logo, favicon** — il colore principale resta nel tema dell'app.
- **`harness-note` committa ma non pubblica** — un push su `main` dalla sessione di un altro progetto sarebbe un push
  non chiesto; l'inizio sessione avvisa delle note non pubblicate.
- **Rinviate**: nota 2026-10-19 (trigger del massimo delle collezioni, al primo progetto con `upper` finito: nessuno
  nei cinque metamodelli locali); pagina e tabella di branding nel kit di `modeler:install` (alla prima app nuova).

## Problemi aperti
- `find_harness_clone` cerca solo in `~/Documents/GitHub/`: su un computer con i repository altrove serve l'opzione
  `harness_repo`.
- Il commit automatico di `harness-note` e l'importazione del file di riserva in `harness-review` sono istruzioni di
  skill mai provate in una sessione vera; l'hook ha il test `test_where_the_harness_notes_go`.
- L'avviso del server MCP dipende dal formato di `~/.claude.json` (`mcpServers`, `projects.<path>.mcpServers`); su
  questo computer non c'è nessun server a scope utente, quindi si è visto solo nel test.
- Sugli altri computer `harness_repo` può essere ancora vuota: la imposta `./install.sh` dopo `git pull`.
- Ereditati e non ricontrollati: order-management usa ancora il flag `accountingChecked` invece di una regione;
  `--yes` in `modeler-release.yml` mai visto in un run vero; primo run di `modeler-apply`/`modeler-release`; avviso dei
  ruoli e riquadri delle regioni non visti nel browser; `psql` assente sul Mac (shim sotto); `guard_harness_edit` solo
  Edit/Write; cartella `help/` non tracciata; `MAX_ROWS` non si applica al box `Role`.

## Prossimi passi
1. Sugli altri computer: `git pull && ./install.sh` nel clone (o `claude plugin update core@iovino-harness` e
   `modeler@iovino-harness`), poi riavvio; controllare che l'inizio sessione non dica «`harness_repo` non è impostata».
2. Nelle app: `/modeler:install` per la 0.40.1 (ACS-GSSI per prima: è il caso della nota), poi `npm run
   model:validate` e `npm run model:drift`; LudoActivityManager è alla 0.39.0.
3. In ACS-GSSI: rifare con `npm run model:apply -- <proposta> --write` una proposta che cambia una regola e
   controllare `git diff --stat domain.ecore.yaml`: solo le righe cambiate.
4. Alla prossima `/core:harness-note` da un'altra app: guardare che la nota arrivi in questo `NOTES.md` come commit
   `docs(notes): …` e che l'inizio sessione qui la segnali come non pubblicata.
5. Con Docker acceso: i test con `MODELER_PG` (comandi sotto), mai eseguiti dopo la PR #43.
6. Prima app nuova con `modeler:install`: riprendere la pagina di branding nel kit.

## Per riprendere
`cd <clone> && claude` — dopo una modifica ai plugin: `/reload-plugins`.
Test senza database: `python3 -m unittest discover -s tests && python3 -m unittest discover -s plugins/modeler/tests && node --test plugins/modeler/tests/*.test.mjs && claude plugin validate .`
Test con database (motore end-to-end, «view as», migrazione dei ruoli; Docker Desktop acceso):
```bash
docker run -d --rm --name modeler-pg-test -e POSTGRES_PASSWORD=pg -p 55499:5432 postgres:16
mkdir -p /tmp/pgbin && cat > /tmp/pgbin/psql <<'PY'
#!/usr/bin/env python3
import subprocess, sys
args = [a.replace("localhost:55499", "localhost:5432") for a in sys.argv[1:]]
sys.exit(subprocess.run(["docker", "exec", "-i", "-e", "PGPASSWORD=pg", "modeler-pg-test", "psql", *args], stdin=sys.stdin).returncode)
PY
chmod +x /tmp/pgbin/psql
PATH=/tmp/pgbin:$PATH MODELER_PG=postgresql://postgres:pg@localhost:55499/postgres python3 -m unittest discover -s plugins/modeler/tests
docker stop modeler-pg-test
```
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (ultime nove voci e le due rinviate),
`plugins/modeler/scripts/metamodel/ecore.py` (`patch_text`, `_rule_edits`), `plugins/core/scripts/hook.py`
(`harness_notes_info`, `supabase_mcp_warnings`), `plugins/core/skills/harness-note/SKILL.md`,
`plugins/core/skills/db-push/SKILL.md`, `install.sh`.
