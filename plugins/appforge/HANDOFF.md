# appforge — documento di passaggio (handoff)

Stato al 7 ottobre 2026, versione 0.1.0. Questo file serve a riprendere lo sviluppo del plugin in un'altra
sessione di Claude Code. Il codice sorgente è nella cartella del plugin (`appforge/`, dentro
`appforge-marketplace/plugins/` se installato dal marketplace locale).

## 1. Obiettivo
Ludovico sviluppa con Claude Code applicativi web che hanno sempre la stessa architettura; cambia solo il
dominio (es. `gssi/guest-invitations`, `ACS-GSSI`). appforge rende questa architettura un **framework
model-driven**:

- il **modello di dominio** (`app.yaml`) è l'unica fonte di verità: entità, campi, relazioni, ruoli (globali o
  con ambito), permessi, workflow, eventi, reazioni;
- un **generatore deterministico** produce SQL (Supabase), artefatti TypeScript, traduzioni e documentazione;
- l'**agente** (Claude Code) interviene solo dove il modello non arriva: migrazioni manuali per modifiche
  distruttive, handler `custom`, pagine personalizzate;
- un **meta-sistema** gestisce gli applicativi generati: registro delle app (ognuna è un repository autonomo
  che vive di vita propria) e **Studio grafico** per modellare, oltre alla CLI e ai comandi in conversazione.

## 2. Architettura di riferimento delle app generate
Ricavata da guest-invitations (la versione più matura) e ACS:

- **Supabase Postgres = cervello**: RLS su ogni tabella, permessi come relazioni (`<e>_principals(row)` →
  `all, admin, creator, <ruolo>, field:<ref a User>`; i ruoli con ambito valgono nell'ambito della riga),
  motore di workflow (`<e>_perform_transition`, guard = requisiti che bloccano spiegando, condition = percorsi
  alternativi che nascondono l'azione, transizioni a data, solleciti, storico in `record_history`),
  **transactional outbox** (`emit_event` → `events`), reazioni interne nella stessa transazione
  (`react_to_event`), job pg_cron (eventi pianificati ogni 5 min, transizioni a data 01:00, solleciti 07:00,
  pulizia eventi 03:30).
- **Next.js 16** (App Router, `src/proxy.ts`, next-intl, shadcn su Base UI): pagine generiche guidate dal
  metamodello generato `src/lib/model.ts` → `/e/[entity]` (elenco), `/new`, `/[id]` (dati, azioni di workflow
  con requisiti mancanti, form di modifica, storico); scrivania "In carico a me" (`my_inbox()`); admin utenti e
  ruoli (approvazione, pre-registrazione, ruoli con ambito); integrazioni (endpoint webhook, consegne, catalogo).
- **Dispatcher** (`worker/dispatcher.ts`, copiato da guest-invitations): LISTEN/NOTIFY + poll, `FOR UPDATE SKIP
  LOCKED`, CloudEvents 1.0, firma Standard Webhooks, Basic auth opzionale, retry 1m/5m/30m/2h/12h/24h, dead letter.
- Notifiche: i destinatari sono risolti nel DB e messi nell'evento (`data.recipients`: email, locale,
  recipient_type, template_key); n8n sceglie solo il template.
- Deploy: Dockerfile multi-stage (web + dispatcher), GitHub Actions → GHCR, `deploy/docker-compose.prod.yml` con
  Watchtower e rete del reverse proxy.

## 3. Struttura del plugin
```
.claude-plugin/plugin.json      manifest (validato con `claude plugin validate`)
hooks/hooks.json                PreToolUse guard, PostToolUse validate, SessionStart status
skills/                         comandi: new-app, spec, model, generate, custom, check, apps, studio, upgrade
                                conoscenza: modeling (references/metamodel.md + 2 esempi), architecture
                                (references/where-code-goes.md, events.md)
agents/                         domain-modeler, sql-engineer, ui-engineer, architecture-reviewer
scripts/appforge.py             entry point CLI
scripts/appforge/model.py       load/normalize/validate del modello (+ dump/loads YAML, vendored PyYAML fallback)
scripts/appforge/sqlgen.py      SQL: core / struttura / comportamento (≈2000 righe)
scripts/appforge/diff.py        evoluzione: delta strutturale additivo + operazioni manuali (pre/post)
scripts/appforge/tsgen.py       model.ts, events/catalog.ts, namespace `model` dei messages, docs/domain.md
scripts/appforge/project.py     scaffold, generate, lock, status, registro, check_db
scripts/appforge/studio.py      server HTTP dello Studio (127.0.0.1 + token di sessione)
scripts/appforge/guard.py       hook pre/post/session
scripts/appforge/testing/supabase_stub.sql   ruoli/auth minimi per provare le migrazioni su Postgres puro
scripts/tests/test_appforge.py  regressione (python3 -m unittest discover -s scripts/tests)
scripts/vendor/yaml             PyYAML puro (fallback se non installato)
studio/                         UI dello Studio (index.html, app.js ≈1100 righe vanilla JS + SVG, style.css)
schema/app.schema.json          JSON Schema di app.yaml (copiato nelle app in .appforge/)
templates/app/                  template dell'applicazione (file `_dot_*` → dotfile; segnaposto {{APP_SLUG}} …)
examples/guest-invitations/app.yaml, examples/acs/app.yaml
```

## 4. Il metamodello (sintesi; riferimento completo in skills/modeling/references/metamodel.md)
- `app`: name, slug, locales, timezone, auth (providers google|email, allowed_domains, approval manual|auto,
  admins), events (source, type_prefix, retention_days), deploy (image, base_url, platforms).
- `roles` (admin implicito), `scope` (entità anagrafica che fa da ambito), `enums`.
- `entities`: kind registry|process, label/plural, table, code_prefix, display, scope_field, fields
  (string text email url int number money bool date datetime enum ref json; required, unique, default, list,
  readonly, min/max/max_length, to, many, on_delete, renamed_from), indexes, permissions (read/create/update/
  delete con principals), workflow (states: kind, owner, editable_by, reminder, color, renamed_from;
  transitions: from (stato|lista|*), to, by, trigger manual|{at, offset}, comment, guard, condition, emits).
- Eventi automatici: `<e>.created|updated|deleted` (+ `transitioned|completed|reminder` per i processi);
  `events:` dichiara solo quelli aggiuntivi.
- `reactions`: on + when (transition/to/from/clauses) + do: notify | set | transition | schedule | broadcast |
  custom. Il validatore rifiuta i cicli tra reazioni.
- `subscriptions`: sottoscrittori consigliati (solo documentazione).

## 5. Generazione ed evoluzione
- Tre livelli SQL: **core** (una volta), **struttura** (prima generazione completa, poi solo delta additivi),
  **comportamento** (idempotente, rigenerato per intero a ogni evoluzione).
- Prima generazione: `*_appforge_core.sql`, `*_appforge_structure.sql`, `*_appforge_behavior.sql`.
- Evoluzione N: `*_manual_evolve_N.sql` (pre: drop/rename/spostamenti, solo se servono) →
  `*_appforge_evolve_N_types.sql` (nuovi valori di enum/ruoli, committati prima) → `*_appforge_evolve_N.sql`
  (struttura additiva + comportamento completo) → `*_manual_evolve_N_post.sql` (backfill di nuovi campi
  obbligatori). I file manuali contengono `TODO(appforge)`: `status` li segnala finché non vengono completati.
- Rinomine automatiche con `renamed_from` per campi (colonna, vincoli, indici, tabelle di collegamento) e stati
  (record, storico, solleciti). Lo Studio imposta `renamed_from` quando si rinomina. La rinomina di entità è manuale.
- `.appforge/lock.json`: modello normalizzato + **raw** (il confronto ri-normalizza il raw con il normalizzatore
  corrente, così un generatore nuovo non scambia le proprie modifiche per modifiche al modello; l'ordine delle
  chiavi conta: niente sort_keys), hash di file e migrazioni generate (l'hook li protegge), handler custom.
- Cambio di versione del generatore → `generate` produce un'evoluzione "solo comportamento"
  (`--rebuild-behavior` per forzarla).
- Handler `custom`: stub creato una volta sola (`create function` solo se non esiste), il corpo si scrive in una
  migrazione a mano con `create or replace`.

## 6. Registro e Studio
- Registro: `~/.appforge/registry.json` (o `$APPFORGE_HOME`). `appforge apps [list|add|remove|show]`.
- Studio: `appforge studio [--port 4321] [--app slug] [--no-browser]`. API: GET /api/apps, GET/PUT /api/model,
  POST /api/validate, /api/yaml, /api/generate (dry_run), /api/check-db, /api/register, /api/unregister,
  /api/new. Viste: Dominio (box trascinabili, frecce dei riferimenti), Workflow (layout a livelli BFS,
  transizioni curve, "Nuova transizione" = stato di partenza selezionato → clic sull'arrivo), Eventi e reazioni,
  Ruoli e impostazioni, YAML (salvato così com'è, commenti inclusi), Genera. Posizioni in
  `.appforge/studio-layout.json`. Undo (Ctrl+Z), salvataggio (Ctrl+S), validazione live.

## 7. Verifiche fatte
- I due esempi validano; le migrazioni si applicano su PostgreSQL 16 con lo stub Supabase.
- Scenario SQL completo su guest-invitations: approvazioni utenti, permessi per ruolo/ambito, transizioni,
  guard, commento obbligatorio, stato bloccato fuori dalle transizioni, campo readonly, transizioni a data,
  solleciti (una volta sola), eventi pianificati, reazione `set`, destinatari nelle notifiche (anche
  `field:guest` verso un'entità con email), storico.
- Via PostgREST 12 con JWT di utenti diversi: insert/list/detail con embedding dei riferimenti (`selectFor`),
  molti-a-molti, `can`, `available_transitions`, `my_inbox`, RLS (update/delete negati).
- Evoluzioni: additive, manuali pre/post completate, rinomine su DB popolato (dati conservati).
- App generate (guest e ACS): `tsc`, ESLint, Vitest (26 test), `next build` ok.
- Plugin in una sessione Claude Code nuova (`claude -p --plugin-dir`): `/appforge:new-app` ha creato
  un'app di prenotazione aule da una descrizione; `/appforge:model` ha fatto rinomina + nuovo campo
  obbligatorio con migrazioni manuali e check --db; `/appforge:apps` funziona.
- Studio provato con Playwright: tutte le viste, aggiunta entità/campo/riferimento/transizione, salvataggio,
  anteprima, generazione.
- `python3 -m unittest discover -s scripts/tests` → OK (con `APPFORGE_PG` anche il test delle migrazioni).

## 8. Limiti noti e prossimi passi (in ordine di utilità)
1. **Prova con Supabase reale** (Auth, Realtime, pg_cron, hook before_user_created): mai eseguita (niente
   Docker nell'ambiente di sviluppo). Primo test: sandbox `invitations-demo`, `supabase start`, `db reset`,
   login con magic link (Mailpit), percorso completo dell'invito, broadcast sul canale `dashboard`.
2. **Rinomina di entità** automatica (tabella, vincoli, trigger/policy/funzioni con il vecchio nome).
3. **Test pgTAP generati** per entità e workflow (oggi solo il check su DB e i test Python).
4. **UI generica**: filtri per ambito, ordinamento/paginazione, upload file, campi calcolati, pagina monitor
   pubblica (serve per ACS), revert di stato e cambio versione workflow (presenti in guest-invitations, non
   nel metamodello).
5. **Funzionalità di guest-invitations non ancora nel metamodello**: workflow versionati modificabili a runtime
   (modellatore nel backoffice), regole di dominio come dati (`invitation_rules`), branding, "vedi come…".
   Valutare se portare il livello models@runtime (entity_types/records di guest-invitations) come opzione.
6. **Studio**: etichette dei valori enum (oggi solo via YAML), editor delle `subscriptions`, layout automatico
   del diagramma ER migliore, apertura dell'app generata nel browser, diff visuale tra modello e lock.
7. **Componente edge** (es. Raspberry Pi di ACS): un template opzionale `device/` che usa RPC dedicate.
8. Seed dei webhook da `subscriptions` (comando o script).

## 9. Comandi utili per lo sviluppo del plugin
```bash
python3 scripts/appforge.py validate examples/guest-invitations/app.yaml
APPFORGE_HOME=/tmp/af python3 scripts/appforge.py new /tmp/af/guest --model examples/guest-invitations/app.yaml
APPFORGE_PG=postgresql://postgres:postgres@127.0.0.1:5432/postgres python3 scripts/appforge.py check /tmp/af/guest --db
python3 -m unittest discover -s scripts/tests
claude plugin validate .claude-plugin/plugin.json
claude --plugin-dir . -p "/appforge:apps"          # prova del plugin senza installarlo
python3 scripts/appforge.py studio
```
Nelle app generate: `npm install` (c'è il package-lock nel template), `npm run typecheck`, `npm test`,
`npm run lint`, `npm run build`.

## 10. Convenzioni da mantenere
- Messaggi di errore SQL in italiano, mappati in `templates/app/src/lib/db-errors.ts` e tradotti in
  `messages/*.json` (`errors.*`); il test i18n dell'app lo verifica.
- Funzioni SQL: `security definer`, `set search_path = ''`, nomi qualificati; `revoke execute on all functions`
  + grant espliciti solo per le RPC (nel livello comportamento).
- Il generatore non sovrascrive mai i file del template dopo lo scaffold: gli aggiornamenti del template si
  propongono con `/appforge:upgrade`.
- Identificatori snake_case, entità PascalCase, slug kebab-case; YAML 1.1: la chiave `on` delle reazioni viene
  ripristinata da `_fix_on_keys`.

## 10. Aggiornamento 14 ottobre 2026: metamodello, modellatore web, UI mapping (plugin nel marketplace iovino-harness)
Il plugin ora vive in `iovino-harness/plugins/appforge` (marketplace personale insieme a `core`).
- **Metamodello** `domain.ecore.yaml` (`scripts/appforge/ecore.py`): notazione Ecore in YAML (classi astratte e
  supertipi, attributi con tipi Ecore + Text/Email/URL/Money/Date/JSON, riferimenti con lower/upper,
  containment, opposite, enum). `compose()` lo unisce ad `app.yaml` (solo comportamento) nel modello appforge;
  regole di storage deterministiche (vedi `skills/modeling/references/ecore-notation.md`). `extract()` separa un
  app.yaml a file singolo (round-trip verificato); `scaffold` separa sempre. Export/import `.ecore` XMI,
  Emfatic, Mermaid, diff. `language: it` per tabelle e plurali italiani.
- **CLI** `appforge metamodel validate|show|extract|export|import|diff|proposals|apply|pull|reverse|drift|install-modeler|sync`
  (`scripts/appforge/mmcli.py`), `appforge ui show|suggest`.
- **Reverse e drift** (`dbschema.py`): catalogo Postgres via psql → metamodello (FK cascade → containment, join
  table → many, check IN → enum, `column:` per i nomi); drift metamodello ↔ database.
- **Modellatore web** `modeler/metamodel-editor.js` (custom element senza dipendenze): diagramma, inspector,
  rinomine con `renamed_from`, stereotipo «process», workflow/eventi/reazioni/webhook/viste per classe (dal
  `behaviour` in `metamodel.json`), avvisi quando si toglie una feature usata dal comportamento. Usato da
  `/admin/model` delle app (wrapper `modeler/next/*`, proposte su file in dev o tabella `model_change_requests`
  in prod) e dalla scheda Metamodello dello Studio.
- **UI mapping** (`ui.py`): widget per campo e viste (table, cards, kanban, calendar) + pannelli correlati;
  override `entities.<E>.ui`; suggerimenti; cambi solo-UI non producono migrazioni. Template: widget nel form,
  viste nella lista, pannelli correlati nel dettaglio, creazione precompilata.
- **Allineamento**: `npm run check:model` in CI; apply/Studio rifiutano proposte che rompono app.yaml; hook che
  ricorda di aggiornare il metamodello nelle app adottate; drift a inizio sessione con `APPFORGE_DRIFT_DB`.
- Verifiche: 25 test (`APPFORGE_PG=… python3 -m unittest discover -s scripts/tests`), tsc/eslint/vitest/next build
  di app generate, Playwright su modellatore e Studio, e2e `claude -p /appforge:metamodel` da descrizione.
- Non verificato: le pagine nuove (kanban, calendario, pannelli, /admin/model) in esecuzione con Supabase reale.
