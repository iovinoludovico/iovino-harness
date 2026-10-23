# Handoff — Revisione delle note dell'harness: URL assoluti dietro il proxy, tap target, «Elimina utente» (PR #41)
_Aggiornato: 2026-10-23 · branch `main` (`e2c3d59`, PR #41), albero pulito_

## Obiettivo
Marketplace personale di plugin per Claude Code (`core`, `modeler`). Oggi, dopo le due PR sull'«Applicazione dal web»
(#39, #40), `/core:harness-review` ha valutato le tre note del 2026-10-23 nate in invitations-af e le ha applicate al
plugin `core` (0.24.0): un redirect costruito da `request.nextUrl` finiva su `0.0.0.0:3000` in produzione, il badge dei
non letti nell'header era troppo piccolo da premere, `/admin/users` poteva solo disattivare un utente. Il tratto
«proposta in produzione → PR → rilascio» del modeler (PR #27/#28, #39, #40) esiste ma non ha ancora un run vero.
`NOTES.md`: 0 note aperte, 1 rinviata (massimo finito delle collezioni).

## Stato
- Fatto (PR #41, `e2c3d59`, core 0.23.0 → 0.24.0, nessuna modifica al modeler):
  - `028ea80` URL assoluti: riga in `plugins/core/context/conventions.md` (Lavoro sul codice: mai `request.nextUrl`/
    `request.url`/`host`, unico helper `publicUrl(request, path)` su `APP_BASE_URL`, `X-Forwarded-*` solo in sviluppo,
    redirect relativi nelle server action, grep a zero righe); voce 8 «URL assoluti» in `plugins/core/agents/code-reviewer.md`;
    punto «Redirect dietro il proxy» in `plugins/core/skills/security-audit/SKILL.md` §D (curl con cookie su una rotta che
    reindirizza + `git grep`); guard `ask` in `cmd_guard_file` di `plugins/core/scripts/hook.py` (`ABSOLUTE_URL_FILES_RE`:
    `route.[jt]sx?`, `proxy.[jt]s`, `middleware.[jt]s`; `ABSOLUTE_URL_RE`: `new URL(…, req|request.nextUrl|url)` o
    `request.nextUrl.origin|host|href`) con `test_absolute_url_from_request_asks` in `tests/test_core_hooks.py`; README §hook.
  - `1485b05` tap target: riga in `conventions.md` (area ≥ 40×40 px, 44 su telefono; badge dentro il bottone `size-10`/
    `size-11` + `grid place-items-center`, badge `min-w-5 h-5 text-xs`, o nel testo del link «Notifiche · 3»; header
    provato a larghezza telefono); voce 9 «UI» nel `code-reviewer`.
  - `e5e283b` utenti: riga «Utenti» in `conventions.md` (Stack ricorrente): approva / disattiva / elimina, RPC
    `public.delete_user(p_profile_id)` security definer solo admin che rifiuta l'admin stesso, l'ultimo admin attivo e i
    profili con record vivi, cancella profilo e `auth.users`, emette `user.deleted`; bottone «Elimina» solo su profili
    disattivati o mai approvati, testi della conferma, pgTAP.
  - `e292ce1` `NOTES.md` con le tre righe Stato; `20f85de` release core 0.24.0.
- Verificato: `python3 -m unittest discover -s tests` → 24 OK; `-s plugins/modeler/tests` → 118 OK, 9 saltati (Postgres
  spento); `node --test plugins/modeler/tests/*.mjs` → 190 OK; `claude plugin validate .` OK. Nessuna CI nel repository.
  Il guard è provato solo dai test dell'hook, non in una sessione reale su un'app.
- Non committato: nulla. Plugin **non** ricaricati in questa sessione dopo il merge (`/reload-plugins`; sugli altri
  computer `claude plugin marketplace update iovino-harness && claude plugin update core@iovino-harness`).
- Ereditato da #39/#40: la sandbox ha i file del kit 0.38.0 copiati a mano e `package.json`/lockfile modificati
  dall'install 0.37.0, non committati.

## Decisioni
- **Guard dell'hook anche per gli URL assoluti** — il difetto è invisibile in locale e la revisione non lo coglie senza
  una regola: l'`ask` agisce prima che il codice esista. Limitato a `route.*`, `proxy.*`, `middleware.*` (l'helper
  `src/lib/public-url.ts` non lo attiva); ordine: deny dei segreti, poi questo ask, poi `guard_harness_edit`.
- **Le parti «kit» delle note non entrano nell'harness** — header e pagina `/admin/users` sono di appforge, non di
  questo repository: solo convenzione + checklist del reviewer. RPC `delete_user` e bottone si fanno prima in
  invitations-af; se il pattern regge, l'SQL può entrare nel kit del modeler accanto a `notification_templates.sql`.
- **Convenzione «Utenti» completa, non corta** — scelta dell'utente: meglio il pattern intero nel contesto che una
  riga da reinterpretare a ogni app.
- (Ereditate, PR #39/#40) l'app è il pannello e GitHub Actions il deposito dei segreti; ciò che l'app ha già non si
  digita; repository secrets, non environment secrets; il token dell'app fa da `MODELER_GH_TOKEN`; nessuna fermata
  umana su GitHub per i repo privati Free; `modeler-apply.json` committato; `metamodel` facoltativo su `<WorkflowView>`.

## Problemi aperti
- **Il flusso dal web non ha ancora un run vero** (`modeler-apply` né `modeler-release`, in nessuna app). In
  order-management: token `MODELER_APPLY_TOKEN` da rigenerare con Contents write + Pull requests write + Secrets write;
  `DATABASE_URL` da passare anche a `web` nel compose (`deploy/docker-compose.prod.yml` la dà solo al `dispatcher`:
  `install` lo segnala) e nel pannello del server; env secret `ANTHROPIC_API_KEY` nell'environment `modeler-apply` che
  prevarrebbe (`gh secret delete ANTHROPIC_API_KEY --env modeler-apply --repo gssi/order-management`). invitations-af non
  ha i workflow del modeler.
- Il riquadro «Applicazione dal web» non è stato visto nel browser. Se `next build` di un'app fallisce su
  `libsodium-wrappers`: `serverExternalPackages: ["libsodium-wrappers"]` in `next.config.ts`.
- order-management (modeler ≤ 0.37.0, `CUSTOM(modeler-theme)` in `globals.css`): `/modeler:install` per 0.38.0, togliere
  `CUSTOM(modeler-theme)`, `metamodel={metamodel}` su `<WorkflowView>` in `/orders/<id>`. Restano `view_as: {users_by:
  [admin]}` al posto di `CUSTOM(view-as)` e «+ Nuovo» in modale per il fornitore.
- Nessun progetto usa `states.<key>.model`; `MAX_ROWS` non si applica al box `Role`; la select dei template nel pannello
  della transizione è un campo di testo.
- Ereditati: `psql` assente sul Mac (shim in «Per riprendere»); `model:pull`/`model:done` mai riusciti su un progetto
  cloud; `guard_harness_edit` solo Edit/Write; la cartella `help/` non è tracciata.

## Prossimi passi
1. `/reload-plugins` qui; sugli altri computer `claude plugin marketplace update iovino-harness && claude plugin update
   core@iovino-harness`.
2. In invitations-af (sessione sua, con core 0.24.0): `src/app/notifications/[id]/route.ts` usa `publicUrl(req, target)`
   di `src/lib/public-url.ts` al posto di `new URL(target, req.nextUrl)`, poi `grep -rnE "new URL\(.*(nextUrl|req\.url|
   request\.url)" src` a zero righe e `curl -sI -b <cookie> https://<app>/notifications/<id>` → `location` sul dominio;
   badge dell'header dentro il bottone (`size-10`, `min-w-5 h-5 text-xs`) provato a larghezza telefono; migrazione con
   `public.delete_user(p_profile_id)` + evento `user.deleted` in `behavior.yaml` + pgTAP (ultimo admin, record vivi,
   cascata) e bottone «Elimina» in `/admin/users` secondo la riga «Utenti» di `conventions.md`. Se l'RPC regge:
   `/core:harness-note` per portarla nel kit del modeler.
3. In order-management: `/modeler:install` (atteso `src/lib/modeler/modeler-apply.json` e il suggerimento su
   `DATABASE_URL`), `npm install`, `DATABASE_URL: ${DATABASE_URL}` sotto `web.environment`, `metamodel={metamodel}` su
   `<WorkflowView>`, togliere `CUSTOM(modeler-theme)`, typecheck/lint/build, `/core:ship`; nel Docker Manager rigenerare
   `MODELER_APPLY_TOKEN` (Contents, Pull requests, Secrets write) e Redeploy.
4. In `/admin/model` di order-management: riquadro «Applicazione dal web», chiave Anthropic, «Salva su GitHub»;
   `gh secret list --repo gssi/order-management` con i tre secret; cancellare l'env secret che prevale.
5. Primo run vero: proposta innocua salvata da `/admin/model`, «Applica», `gh run list --workflow modeler-apply.yml --repo
   gssi/order-management`, revisione della PR, «Conferma e rilascia», riga su `applied`. Ogni inciampo → `/core:harness-note`.
6. Sandbox: committare o scartare le modifiche dell'install; provare il riquadro con `MODELER_PROPOSALS=db`.

## Per riprendere
`cd <clone> && claude` — i plugin si caricano da questa cartella: dopo una modifica usa `/reload-plugins`.
Test senza database: `python3 -m unittest discover -s tests && python3 -m unittest discover -s plugins/modeler/tests && node --test plugins/modeler/tests/*.mjs && claude plugin validate .`
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
File da leggere per primi: `CLAUDE.md`, `NOTES.md` (ultime tre voci), `plugins/core/context/conventions.md` (righe nuove in
«Lavoro sul codice» e «Utenti»), `plugins/core/scripts/hook.py` (`cmd_guard_file`), `plugins/core/skills/release/SKILL.md`.
