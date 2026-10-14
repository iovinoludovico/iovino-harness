# {{APP_NAME}}

{{APP_DESCRIPTION}}

Generata con appforge dal modello `app.yaml` (vedi `docs/domain.md` per entità, workflow ed eventi).

## Avvio locale
```bash
cp .env.example .env.local        # chiavi da `supabase status`
npm install
supabase start
supabase db reset                 # applica le migrazioni generate
npm run db:types                  # tipi TypeScript dello schema (facoltativo)
npm run dev                       # http://localhost:3000
npm run worker:dev                # consegna degli eventi ai webhook
```
Il primo accesso con un'email elencata in `app.auth.admins` crea l'amministratore.

## Deploy
Un push su `main` costruisce le immagini `{{IMAGE}}-web` e `-dispatcher` (GitHub Actions → GHCR);
sul server `deploy/docker-compose.prod.yml` con Watchtower le aggiorna. Variabili: `deploy/.env.production.example`.
Migrazioni sul progetto Supabase cloud: `supabase link` e `supabase db push`.
