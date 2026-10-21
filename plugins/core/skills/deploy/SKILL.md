---
name: deploy
description: Riferimento per la produzione delle app Next.js + Supabase - Supabase cloud, immagini private su GHCR pubblicate da GitHub Actions, VPS Hostinger gestito dal Docker Manager del pannello (non un .env copiato via SSH), Nginx Proxy Manager con Let's Encrypt, Watchtower, rollback e diagnosi. Usala quando si scrive o aggiorna docs/deploy.md di un'app, per il primo deploy, quando l'utente chiede "come lo metto in produzione", "quale proxy host imposto", "che variabili metto nel pannello", "il server non si aggiorna", "come torno alla versione precedente", o invoca /core:deploy.
---

# Deploy in produzione (Supabase cloud + VPS Hostinger con Docker Manager)

Le app vanno in produzione tutte allo stesso modo; questi sono i passi veri, provati su più app. Non inventare
istruzioni diverse (cartelle `/opt/<app>`, `scp` di compose e `.env`, `docker compose up -d` via SSH): il server è
gestito dal pannello. Se un'app ha un `docs/deploy.md`, vale quello per i valori (dominio, progetto, immagini);
se è in contrasto con questi passi, segnalalo e proponi di allinearlo.

**Mai**: un `.env` di produzione da copiare sul server, segreti in chat, nel repository o in un comando. L'unico
segreto del server è `DATABASE_URL` e vive solo nelle variabili del pannello.

## Catena
```
push su main ── GitHub Actions: typecheck, lint, build ── GHCR (immagini private, tag latest e sha-<commit>)
                                                            │
VPS Hostinger ── Docker Manager (progetto <app>: web [, dispatcher/worker], watchtower) ◄─┘ Watchtower aggiorna latest in ~2 min
      └── Nginx Proxy Manager (già sul VPS, porte 80/443, Let's Encrypt) ── <app>-web:3000
Supabase cloud ── database, Auth, Storage, pg_cron
```
Valori per app in `docs/deploy.md`: dominio `<app>.iovino-systems.cloud`, progetto Supabase (ref, regione UE),
immagini `ghcr.io/<org>/<repo>-web` (e `-dispatcher`/`-worker`), rete del proxy, nome del progetto nel pannello.
Il compose di produzione è `deploy/docker-compose.prod.yml` (solo `image:`, nessuna `build`); le variabili con un
predefinito stanno in `deploy/.env.production.example`, solo come documentazione.

## 1. Supabase cloud (una volta)
1. Progetto in regione UE; annota URL, chiave publishable (anon), password del database e stringa del **session
   pooler** (porta 5432; il transaction pooler 6543 non supporta LISTEN/NOTIFY, che un dispatcher usa).
2. Authentication → URL Configuration: Site URL `https://<app>.iovino-systems.cloud`, Redirect URLs
   `https://<app>.iovino-systems.cloud/auth/callback` (o `/**`). Il dominio deve essere quello reale, già
   risolto dal DNS: un dominio sbagliato qui rompe il login senza errori chiari.
3. Authentication → Providers → Google: client id e secret, una sola volta ciascuno; sulla Google Console il
   redirect autorizzato è `https://<project-ref>.supabase.co/auth/v1/callback`. Se l'app limita i domini email con
   un hook `before_user_created_hook`: Authentication → Hooks → Before User Created, tipo Postgres, la funzione
   dell'app (in locale lo attiva `config.toml`, sul cloud va attivato nel pannello; le registrazioni restano attive
   solo se l'hook è attivo). `supabase config push` non si usa: `config.toml` contiene gli URL locali.
4. Schema: `supabase link --project-ref <ref>` (l'utente, in un suo terminale), poi `/core:db-push`.
5. Impostazioni dell'app nel database (es. `app_settings.app_base_url`): il valore dello scaffold va sostituito
   con l'URL pubblico reale, nel SQL Editor o con una migrazione.

## 2. GitHub (una volta)
- Repository privato nell'organizzazione; il workflow (`.github/workflows/deploy.yml` o `docker.yml`) pubblica a
  ogni push su `main`. URL e chiave publishable di Supabase sono i predefiniti di workflow e compose (sono valori
  pubblici: finiscono nel bundle del browser); Settings → Secrets and variables → Actions → **Variables** (non
  Secrets) `NEXT_PUBLIC_SUPABASE_URL` e `NEXT_PUBLIC_SUPABASE_ANON_KEY` servono solo per cambiarli. Le variabili
  `NEXT_PUBLIC_*` entrano nel bundle alla build: cambiarle richiede una build nuova.
- Pacchetti GHCR privati: lasciarli come li crea il primo push (mai «Change visibility»); nell'organizzazione
  conviene Settings → Packages → Package creation solo «Private».

## 2b. Immagini
- Un worker (dispatcher, cron) ha uno stage proprio nel `Dockerfile`. Se lo stage copia a mano una lista di cartelle
  (`COPY worker/ src/lib/events/ …`) si rompe in silenzio quando un import nuovo esce dalla lista: build e deploy
  verdi, in produzione il container muore all'avvio con `Cannot find module '@/lib/…'` e Docker lo riavvia in loop
  (la build di Next vede tutto `src/`, l'immagine del worker no). Due scelte:
  - lo stage copia `src/` intero (semplice, immagine un po' più grande);
  - un test dell'app segue gli import del punto d'ingresso del worker (relativi e `@/`, ricorsivamente) e pretende
    che ogni file sia coperto da una riga `COPY` dello stage (`tests/<worker>-image.test.ts`): legge il
    `Dockerfile`, prende le `COPY` fra `FROM … AS <stage>` e il `FROM` successivo, risolve gli import con una regex
    su `from "…"` / `import("…")` e fallisce elencando i file scoperti.
- Prima del merge di una PR che tocca il worker o il suo stage: `docker build --target <stage> -t <app>-worker:test .`
  e un avvio contro il database locale (`docker run --rm -e DATABASE_URL=… <app>-worker:test`) fino al primo log di
  polling.
- Con il modellatore: quando il dispatcher rende i testi delle notifiche legge `behavior.json` e la cartella dei
  template (`modeler:install`): quei file entrano nell'immagine.

## 3. DNS
Record A `<app>.iovino-systems.cloud` → IP del VPS. Un errore del certificato in NPM = DNS non ancora propagato.

## 4. Server (una volta, via SSH da root solo per il login al registry)
1. Login a GHCR, perché le immagini sono private: PAT **classico** con il solo scope `read:packages` (i
   fine-grained non coprono i pacchetti di organizzazione), di un utente che può leggere i pacchetti:
   ```bash
   echo <PAT> | docker login ghcr.io -u <utente> --password-stdin   # Watchtower legge /root/.docker/config.json
   ```
2. hPanel → VPS → **Docker Manager** → Create project, nome **`<app>`** (stabile: con un altro nome Compose
   avvierebbe un secondo gruppo di container invece di sostituire questi; i file stanno in `/docker/<app>/`, i
   container si chiamano `<app>-web-1`, `<app>-watchtower-1`, …):
   - **Compose**: il contenuto di `deploy/docker-compose.prod.yml`, incollato invariato (un eventuale `name:` è
     ignorato: il nome lo dà il pannello; Watchtower filtra per etichetta di scope). Il servizio `watchtower` gira
     con `--scope <app> --interval 120 --cleanup --include-restarting`: senza `--include-restarting` aggiorna solo
     i container `running`, e un container in crash loop (quasi sempre `restarting`) resta sull'immagine vecchia
     anche quando quella corretta è pubblicata;
   - **Variabili**: `DATABASE_URL` (session pooler, con la password) è l'unica senza predefinito ed è un segreto:
     solo qui. Le altre (`deploy/.env.production.example`) solo per cambiare i predefiniti del compose.
     Con il modellatore e l'applicazione dal web (skill `modeler:install`, sezione 7) anche `MODELER_APPLY_REPO`
     (`owner/repo`) e `MODELER_APPLY_TOKEN` (token fine-grained, Contents: write e Pull requests: read su quel
     repository): secondo segreto del pannello, mai nel compose né nel repository. Il token con cui il workflow
     `modeler-release` unisce la PR (`MODELER_GH_TOKEN`) sta nei secrets di GitHub, non nel pannello.
3. Deploy dal pannello **dopo** che il workflow ha pubblicato le immagini (primo push su `main`).
4. Le modifiche al compose si fanno nel pannello e si riportano in `deploy/docker-compose.prod.yml` (e
   viceversa): repository e server restano uguali.

Il servizio `web` **non pubblica porte**: entra nella rete Docker esterna di NPM (`PROXY_NETWORK`, di solito
`nginx-proxy`; sul server `docker network ls | grep proxy`) con un alias stabile `<app>-web`.

## 5. Proxy host in Nginx Proxy Manager
NPM → Hosts → Proxy Hosts → Add:
- Details: domain `<app>.iovino-systems.cloud`, scheme `http`, forward hostname **`<app>-web`** (l'alias, non il
  nome del container), forward port `3000`, «Block common exploits» e «Websockets support» attivi;
- SSL: «Request a new SSL certificate» (Let's Encrypt), «Force SSL», «HTTP/2 support»;
- Advanced → Custom Nginx Configuration, per i cookie di Supabase Auth sul callback (altrimenti 502 dopo il login):
  ```nginx
  proxy_buffer_size 128k;
  proxy_buffers 4 256k;
  proxy_busy_buffers_size 256k;
  ```
NPM inoltra `X-Forwarded-Proto` e `X-Forwarded-For`, che servono a Next per i cookie `Secure`.

## 6. Verifica
- `https://<app>.iovino-systems.cloud/login` (o `/api/health`) risponde; `http://` reindirizza a `https://`.
- 502: `web` non è sulla rete del proxy o l'alias è sbagliato:
  `docker inspect <app>-web-1 --format '{{json .NetworkSettings.Networks}}'`.
- Login con l'account previsto (il primo accesso con un'email tra gli admin di bootstrap crea l'amministratore).
- Poi `/core:security-audit`.

## 7. Aggiornamenti
1. Migrazioni sul cloud con `/core:db-push` **prima** del push del codice (le immagini non applicano migrazioni;
   le migrazioni restano additive, così la versione in esercizio continua a funzionare).
2. Merge su `main` (`/core:ship`): Actions pubblica `latest`, Watchtower ricrea i container entro ~2 minuti.
   Nessun clic sul pannello; il **Redeploy** del progetto (ricrea i container dall'immagine pubblicata) serve
   solo per cambiare variabili, compose o immagini che Watchtower non segue; il «Restart» di un container riavvia
   la stessa immagine.
3. Rollback: variabile `APP_TAG=sha-<commit>` (o il nome usato dal compose) nel progetto del pannello e Redeploy;
   fermare Watchtower (`docker stop <app>-watchtower-1`) finché non c'è un `latest` buono, altrimenti torna a
   `latest`. Lo schema non torna indietro.

## 7b. Build visibile
Con il deploy automatico non si capisce dall'app se il server ha già preso l'ultimo rilascio: ogni app mostra
nell'header la build in esercizio, `#<numero di commit di main> · <sha breve>`, lo stesso SHA del tag `sha-<commit>`
dell'immagine (collaudato in invitations-af, customizzazione `build-badge`).
- `src/lib/build-info.ts`: `parseBuild(commits, sha)`, `buildInfo()` (legge `process.env.NEXT_PUBLIC_APP_COMMITS` e
  `process.env.NEXT_PUBLIC_APP_SHA` **con riferimenti letterali**: Next.js inlinea solo `process.env.NEXT_PUBLIC_X`
  scritto per esteso; letti da un parametro o da `process.env[k]` restano vuoti nel bundle), `formatBuild()` →
  `#123 · ab12cd3`; test unitario su `parseBuild`/`formatBuild`.
- Badge accanto al nome dell'app nell'header, con tooltip tradotto (`nav.build`); senza valori il badge non compare.
- `next.config.ts`: `env: { NEXT_PUBLIC_APP_COMMITS, NEXT_PUBLIC_APP_SHA }` dai build args `APP_COMMITS`/`APP_SHA`
  (immagine), altrimenti da `git rev-list --count HEAD` e `git rev-parse --short HEAD` se c'è un checkout (sviluppo),
  altrimenti vuoti.
- `Dockerfile`: `ARG APP_COMMITS` e `ARG APP_SHA` passati come `ENV` prima della build; workflow di deploy con
  `actions/checkout` a `fetch-depth: 0` e uno step che calcola conteggio e SHA e li passa come `build-args`.
- Verifica: dopo la build cercare lo SHA nei chunk (`grep -rl <sha> .next/server | head -1`); in produzione il badge
  deve corrispondere all'ultimo commit di `main` (`gh api repos/<owner>/<repo>/commits/main --jq .sha | cut -c1-7`);
  dopo un rollback (`APP_TAG=sha-<commit>`) il badge torna al numero precedente: è il modo di vedere che ha funzionato.
- Registrare la personalizzazione in `docs/customizations.md` e la riga nel `docs/deploy.md` dell'app.

## 8. Diagnosi
- **Il server non si aggiorna** (Actions ha pubblicato `latest`, la produzione resta indietro):
  `docker logs --tail=20 <app>-watchtower-1`; `403 Forbidden`, `auth: "not present"`, `denied` = credenziali GHCR
  non più valide (PAT scaduto). Watchtower non avvisa: salta e riprova.
  ```bash
  cd /docker/<app>
  echo <PAT> | docker login ghcr.io -u <utente> --password-stdin   # nuovo PAT read:packages
  docker compose pull web && docker compose up -d web
  docker compose up -d --force-recreate watchtower
  ```
  **Dopo ogni `docker login` ricreare Watchtower**: monta `config.json` come singolo file e il login lo
  sostituisce, quindi il container continua a leggere la versione vecchia. Verifica:
  `docker inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' <app>-web-1` = ultimo commit
  di `main`. Un PAT senza scadenza, o con scadenza annotata, evita che si ripeta.
- **Un solo container resta indietro** (`web` aggiornato, il worker no): è in crash loop, stato `restarting`
  (`docker inspect -f '{{.State.Status}}' <app>-dispatcher-1`, o la lista del pannello), e Watchtower senza
  `--include-restarting` lo ignora. Segnali dall'app: righe della coda che restano `pending` con `attempts 0` e
  nessun `locked_at`, nessuna sessione del ruolo del worker in `pg_stat_activity`
  (`select count(*) from pg_stat_activity where usename = '<ruolo>'` con `supabase db query --linked`), log del
  container nel pannello con `Cannot find module` o lo stack dell'avvio. Rimedio: **Redeploy** del progetto dal
  Docker Manager (non «Restart»), poi `--include-restarting` nel compose così non si ripete; se l'immagine è
  rotta, correggerla e ripubblicarla (sezione 2b).
- **Progetto sparito dal pannello** (`/docker/<app>` rimossa): i container restano accesi ma `docker compose` non li
  gestisce più e Watchtower non si ricrea. Variabili dai container ancora attivi
  (`docker inspect <app>-web-1 --format '{{range .Config.Env}}{{println .}}{{end}}'`, senza incollare
  `DATABASE_URL` altrove), poi progetto ricreato come al punto 4; se il pannello rifiuta perché i container
  esistono, `docker rm -f <app>-web-1 …` e di nuovo Deploy (i dati sono su Supabase).
- Log: `docker compose logs -f web` da `/docker/<app>`, o per servizio nel pannello.

## Scrivere `docs/deploy.md` di un'app
Tabella dei valori (dominio, URL, repository, immagini, rete del proxy e alias, progetto Supabase con ref, chiave
publishable, progetto del Docker Manager), poi le sezioni 1–8 (con 2b se l'app ha un worker) con i valori dell'app
al posto dei segnaposto.
Nel resoconto di `/core:ship` e `/core:db-push` rimanda a queste sezioni invece di inventare istruzioni.
