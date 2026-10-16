---
name: security-audit
description: Audit di sicurezza, in sola lettura, di un'app Next.js + Supabase in produzione - login e dominio (provider, hook di dominio, redirect), RLS e permessi del database, impostazioni della piattaforma Supabase, header e redirect dell'app pubblica, segreti nel bundle e nel repository, GitHub/GHCR, coerenza della configurazione di deploy. Rapporto controllo per controllo, correzioni solo dopo conferma. Usala dopo il primo deploy in produzione, dopo cambi di Auth, dominio o infrastruttura, quando l'utente chiede "verifica che entrino solo con il nostro dominio", "controlla la sicurezza della produzione", "fai l'audit", o invoca /core:security-audit.
argument-hint: "[A|B|C|D|E|F …] (blocchi da eseguire; vuoto: tutti)"
---

# Audit di sicurezza della produzione

Argomenti: `$ARGUMENTS` (lettere dei blocchi da eseguire, es. `A F`; vuoto: tutti).

**Solo letture.** L'audit non cambia nulla: ogni correzione è proposta nel rapporto e si fa dopo conferma
esplicita, le migrazioni con `/core:db-push`, le impostazioni di Supabase e del pannello dalla dashboard.
Mai scrivere segreti nel rapporto, in file o in chat: se un comando ne mostra uno, riporta solo che esiste.

## 0. Contesto
- Dal `docs/deploy.md` dell'app e da `supabase/.temp/project-ref`: dominio pubblico `<app>`, progetto Supabase
  `<ref>` (`https://<ref>.supabase.co`), chiave publishable `<pub>`, repository `<org>/<repo>`.
- Strumenti: `curl`, `supabase` (progetto collegato: `supabase db query --linked "<sql>"` per il SQL; se non è
  collegato, fai collegare l'utente in un suo terminale), `gh` per il blocco E. Se uno manca, segna i suoi
  controlli come «da verificare a mano».
- Controlli che l'app non prevede (nessuna tabella `app_settings`, nessun hook di dominio, nessun bucket): non
  applicabili, non da correggere.

## A. Login e dominio
1. `curl -s https://<ref>.supabase.co/auth/v1/settings -H "apikey: <pub>"`: `disable_signup` (le registrazioni
   restano aperte solo se l'hook di dominio è attivo), provider abilitati (`external.google`, `external.email`:
   email spenta se si entra solo con Google), `mailer_autoconfirm`.
2. `curl -s -o /dev/null -w '%{redirect_url}\n' "https://<ref>.supabase.co/auth/v1/authorize?provider=google"`:
   un solo `client_id` che finisce in `apps.googleusercontent.com` (un Client ID incollato due volte produce un
   valore doppio) e `redirect_uri` = `https://<ref>.supabase.co/auth/v1/callback`.
3. SQL, se l'app ha queste tabelle:
   - `select key, value from public.app_settings where key in ('allowed_email_domains','approval_mode','bootstrap_admins','app_base_url')`:
     domini attesi, `app_base_url` = `https://<app>`;
   - `select split_part(email,'@',2) as domain, count(*) from auth.users group by 1`: nessun dominio estraneo;
   - utenti con ruolo admin (tabella profili dell'app): solo gli attesi;
   - `select grantee, privilege_type from information_schema.routine_privileges where routine_name = 'before_user_created_hook'`:
     solo `supabase_auth_admin`, `service_role`, `postgres`.
4. L'attivazione dell'hook Before User Created non si legge dall'API pubblica: **test manuale obbligatorio**, da
   chiedere all'utente, con un account Google di un altro dominio, che deve essere rifiutato ("Dominio email non
   autorizzato" o equivalente). Il parametro `hd` del login Google è solo un suggerimento di interfaccia: non è un
   controllo.

## B. Database (equivalente dei Security Advisor, via SQL)
- Tabelle di `public` senza RLS: `select relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' and not c.relrowsecurity`.
- RLS attiva ma nessuna policy (= nega tutto; segnalare solo se inatteso): tabelle con `relrowsecurity` e nessuna
  riga in `pg_policies`.
- Funzioni `security definer` senza `search_path`: `select proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.prosecdef and coalesce(array_to_string(p.proconfig,','),'') not like '%search_path%'`.
- Policy che si applicano ad `anon` o `public`: `select tablename, policyname, roles from pg_policies where schemaname='public' and (roles @> '{anon}' or roles @> '{public}')`.
- Tabelle di dominio leggibili da `anon`: `select table_name from information_schema.tables where table_schema='public' and has_table_privilege('anon', format('%I.%I', table_schema, table_name), 'SELECT')`.
- Viste senza `security_invoker`: `select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='v' and coalesce(array_to_string(c.reloptions,','),'') not like '%security_invoker=true%'`.
- Storage: `select id, public from storage.buckets`; policy su `storage.objects` (`select policyname, cmd, roles from pg_policies where schemaname='storage'`).
- Prova pratica come anonimo (solo letture e un `POST` che deve fallire):
  `curl -s "https://<ref>.supabase.co/rest/v1/<tabella>?select=*&limit=1" -H "apikey: <pub>"` → `[]` o errore
  `42501`; `curl -s -X POST … -d '{}'` → violazione RLS; `curl -s -X POST https://<ref>.supabase.co/storage/v1/object/list/<bucket> -H "apikey: <pub>" -H 'Content-Type: application/json' -d '{"prefix":""}'`
  → vuoto o errore.

## C. Piattaforma Supabase
- `supabase ssl-enforcement get --experimental --project-ref <ref>`: consiglia l'attivazione se tutti i client
  usano `ssl: "require"` (dispatcher, pooler).
- `supabase network-restrictions get --experimental --project-ref <ref>`: aperto a tutti è accettabile;
  restringere bloccherebbe `db push` dal computer di sviluppo, segnalarlo come scelta.
- `supabase backups list --project-ref <ref>`: PITR sì/no.

## D. App pubblica
- `curl -sI http://<app>/` → 301 su `https://`; `curl -sI https://<app>/login`: `strict-transport-security`,
  `content-security-policy` (con `connect-src` limitato al progetto Supabase), `x-frame-options` o
  `frame-ancestors`, `x-content-type-options: nosniff`, `referrer-policy`, `permissions-policy`; nessun
  `x-powered-by`.
- Pagine protette e API senza sessione: `curl -sI https://<app>/<pagina protetta>` → redirect a `/login`;
  `curl -s https://<app>/api/<rotta>` → 401/redirect, mai dati.
- Redirect aperti: `curl -sI "https://<app>/login?next=//evil.example"` e `…/auth/callback?next=/\evil.example`
  → mai un `location` fuori dal dominio.
- Segreti nel bundle: scarica la pagina, estrai i chunk `/_next/static/**/*.js` e cerca `service_role`,
  `sb_secret_`, `eyJhbGciOi` (JWT), `postgres://`, `postgresql://`. Nel repository: `git grep -nE
  'sb_secret_|service_role|postgres(ql)?://[^ ]+:[^ ]+@' -- ':!*.example'`: niente fuori dagli `.example`.

## E. GitHub e GHCR
- `gh repo view <org>/<repo> --json visibility,isPrivate`: privato.
- `gh secret list` e `gh variable list`: le Variables contengono solo valori pubblici (`NEXT_PUBLIC_*`); i segreti
  (se ce ne sono) sono Secrets.
- Branch protection su `main`: `gh api repos/<org>/<repo>/branches/main/protection`; su piano Free con repository
  privato non è disponibile: segnalarlo, non è una correzione possibile.
- Pacchetti GHCR privati: `gh api /orgs/<org>/packages/container/<repo>-web --jq .visibility` (serve lo scope
  `read:packages`; senza, verifica manuale nella pagina dei pacchetti).

## F. Coerenza della configurazione di deploy
I casi visti al primo deploy di un'app, da controllare uno per uno contro `docs/deploy.md` e la skill `core:deploy`:
- Site URL e Redirect URLs di Supabase Auth = dominio reale, risolto dal DNS (`dig +short <app>`), con il percorso
  `/auth/callback`;
- `APP_BASE_URL` (variabile del pannello o predefinito del compose) e `app_settings.app_base_url` uguali al
  dominio reale;
- Client ID di Google senza duplicazioni (A.2);
- registrazioni attive solo se l'hook di dominio è attivo (A.1 e A.4);
- proxy host in NPM con i buffer per i cookie di Supabase (`proxy_buffer_size 128k; proxy_buffers 4 256k;
  proxy_busy_buffers_size 256k;`): senza, 502 sul callback dopo il login (non leggibile da fuori: chiedere
  all'utente di controllare la scheda Advanced).

## Rapporto
Tabella, un controllo per riga: blocco e controllo → esito (**OK** / **da correggere** / **da verificare a
mano** / non applicabile) → correzione proposta (dove: dashboard Supabase, pannello, migrazione, codice).
Poi la lista delle correzioni in ordine di gravità, ognuna con il comando o il percorso; chiedi conferma con
AskUserQuestion prima di applicarne una qualsiasi (migrazioni con `/core:db-push`). Se un controllo non si può
fare (strumento assente, permesso mancante), dillo nella riga: non segnare OK ciò che non hai visto.
