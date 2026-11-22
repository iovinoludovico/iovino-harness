# Handoff — Harness dopo la revisione del 2026-11-22 (PR #46, #47): «Stato del rilascio» con i comandi da digitare
_Aggiornato: 2026-11-22 · branch `main` (`8ba3de0`, PR #47), allineato a `origin/main`_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core` 0.28.0, `modeler` 0.40.1). Le due note del 2026-11-21 arrivate
da kura sono applicate (PR #46 e #47): a fine iterazione il resoconto si chiude con lo «Stato del rilascio» e con i
comandi da digitare. `NOTES.md` ha 0 note aperte e 2 rinviate.

## Stato
- Fatto (PR #46, `8639134`, `core` 0.27.0): due righe in `plugins/core/context/conventions.md` «Git»: «Stato del
  rilascio» a fine iterazione (migrazioni e `/core:db-push`, codice e `/core:ship` con PR e CI, cosa è su `main` e in
  produzione); `/core:ship`, `/core:commit` e `/core:release` le lancia solo l'utente
  (`disable-model-invocation: true`), quindi si chiede di digitarle invece di rifarne i passi a mano.
- Fatto (`e915342`): `CLAUDE.md` chiede di chiudere ogni rilascio pubblicato con i comandi per portarlo altrove.
- Fatto (PR #47, `8ba3de0`, `core` 0.28.0, revisione del 2026-11-22): frase in coda alla riga «A fine iterazione» di
  `conventions.md` «Git»: se restano passi, i comandi da digitare uno per riga, nell'ordine di esecuzione, con la
  condizione quando non è «subito». Nota 2026-11-21 segnata applicata in `NOTES.md`.
- Verificato (2026-11-22, sul branch dopo il commit `chore(release)`, Postgres spento): `python3 -m unittest discover
  -s tests` → 26 OK; `-s plugins/modeler/tests` → 130 OK, 10 saltati (quelli con `MODELER_PG`); `claude plugin
  validate .` → passed. Non eseguiti: `node --test plugins/modeler/tests/*.test.mjs` (modeler non toccato). Nessuna CI
  nel repository.
- Su questo computer: `claude plugin update core@iovino-harness` dice 0.28.0; `./install.sh` non rieseguito dopo la
  PR #47; la sessione della revisione caricava ancora le skill della 0.26.0 (serve `/reload-plugins` o riavvio). File
  di riserva delle note vuoto.
- Non committato: questo `HANDOFF.md`.
- Modellatore nei cloni locali (dato del 2026-11-21, non ricontrollato): order-management, invitations-af e ACS-GSSI
  0.40.0; LudoActivityManager 0.39.0; modeler-sandbox 0.36.2. Nessuna ha la 0.40.1.

## Decisioni
- **Skill `/core:next-steps` non fatta** (PR #47) — ricavare i passi dallo stato reale duplicherebbe i controlli di
  `core:ship` §1 e `core:db-push` §1, e il tag dell'APK è specifico di kura; si riprende solo se la riga in
  `conventions.md` non basta.
- **Le skill di pubblicazione restano a sola invocazione dell'utente** (PR #46) — è voluto; le skill di progetto che
  rimandano a `/core:ship` chiedono all'utente di digitarla.
- Dalla revisione del 2026-11-20, ancora valide: un blocco scritto a mano non si riscrive mai intero (`apply --write`
  si ferma, resta `--rewrite`); regola del server MCP solo per Supabase; `harness-note` committa ma non pubblica;
  branding = nome, sottotitolo, logo, favicon.
- **Rinviate**: nota 2026-10-19 (trigger del massimo delle collezioni, al primo progetto con `upper` finito); pagina e
  tabella di branding nel kit di `modeler:install` (alla prima app nuova). Condizioni non ricontrollate il 2026-11-22.

## Problemi aperti
- Le convenzioni dello «Stato del rilascio» sono istruzioni senza test: vanno osservate in una sessione vera di un'app
  (kura è il caso d'origine).
- L'importazione del file di riserva in `harness-review` §1 non è ancora stata provata con note presenti (il
  2026-11-22 il file era vuoto).
- `find_harness_clone` cerca solo in `~/Documents/GitHub/`: su un computer con i repository altrove serve l'opzione
  `harness_repo`; sugli altri computer può essere ancora vuota (la imposta `./install.sh` dopo `git pull`).
- L'avviso del server MCP dipende dal formato di `~/.claude.json` (`mcpServers`, `projects.<path>.mcpServers`): visto
  solo nel test.
- Ereditati e non ricontrollati: order-management usa ancora il flag `accountingChecked` invece di una regione;
  `--yes` in `modeler-release.yml` mai visto in un run vero; primo run di `modeler-apply`/`modeler-release`; avviso dei
  ruoli e riquadri delle regioni non visti nel browser; `psql` assente sul Mac (shim sotto); `guard_harness_edit` solo
  Edit/Write; cartella `help/` non tracciata; `MAX_ROWS` non si applica al box `Role`.

## Prossimi passi
1. Qui e nelle sessioni aperte in altri progetti: `/reload-plugins` (o riavvio) per caricare `core` 0.28.0.
2. Sugli altri computer: `git pull && ./install.sh` nel clone (o `claude plugin marketplace update iovino-harness &&
   claude plugin update core@iovino-harness`), poi riavvio; controllare che l'inizio sessione non dica «`harness_repo`
   non è impostata».
3. Alla prossima iterazione in kura: guardare che il resoconto si chiuda con «Stato del rilascio» e con i comandi
   nell'ordine giusto; se non basta, riaprire la nota 2026-11-21 per la skill `/core:next-steps`.
4. Nelle app: `/modeler:install` per la 0.40.1 (ACS-GSSI per prima), poi `npm run model:validate` e `npm run
   model:drift`; LudoActivityManager è alla 0.39.0.
5. In ACS-GSSI: rifare con `npm run model:apply -- <proposta> --write` una proposta che cambia una regola e
   controllare `git diff --stat domain.ecore.yaml`: solo le righe cambiate.
6. Con Docker acceso: i test con `MODELER_PG` (comandi sotto), mai eseguiti dopo la PR #43.
7. Prima app nuova con `modeler:install`: riprendere la pagina di branding nel kit.

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
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (le due voci del 2026-11-21 e le due rinviate),
`plugins/core/context/conventions.md` (sezione «Git»), `plugins/core/skills/ship/SKILL.md`,
`plugins/core/skills/harness-review/SKILL.md`, `plugins/core/scripts/hook.py` (`harness_notes_info`).
