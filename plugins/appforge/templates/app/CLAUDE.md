# {{APP_NAME}}

Applicazione generata con **appforge** (generatore {{GENERATOR_VERSION}}) a partire dal modello: il metamodello
`domain.ecore.yaml` (struttura, notazione Ecore) e `app.yaml` (comportamento: ruoli, permessi, workflow, eventi,
reazioni, webhook, mappatura UI).
L'app vive di vita propria: questo repository contiene tutto ciò che serve per svilupparla, testarla e deployarla.

## Regola d'oro: il modello è la fonte di verità e l'app resta allineata
- Classi, attributi, riferimenti ed enum si cambiano in `domain.ecore.yaml` (`/appforge:metamodel`, oppure il
  modellatore in `/admin/model`, che crea proposte da applicare con `/appforge:metamodel apply`).
- Ruoli, permessi, workflow, eventi, reazioni, webhook e viste UI si cambiano in `app.yaml` (`/appforge:model`,
  `/appforge:ui`). Poi `/appforge:generate`. Non scrivere a mano ciò che il modello sa esprimere.
- `npm run check:model` (anche in CI) fallisce se il modello è cambiato senza rigenerare o se un file generato è
  stato modificato a mano.
- File generati (non modificarli: un hook li protegge, `.appforge/lock.json` ne tiene gli hash):
  `src/lib/model.ts`, `src/lib/events/catalog.ts`, `src/lib/appforge/metamodel.json`,
  `public/appforge/metamodel-editor.js`, `docs/domain.md`, il namespace `model` di `messages/*.json`,
  e le migrazioni `supabase/migrations/*_appforge_*.sql`.
- Le migrazioni sono immutabili. Per logica scritta a mano crea una **nuova** migrazione (`supabase migration new <nome>`).

## Personalizzazioni: ammesse solo se chiarite
Ciò che il modello non esprime è una personalizzazione. Ognuna va registrata in `docs/customizations.md`
(identificativo, motivo per cui il modello non basta, elementi del modello coinvolti, file, come si verifica) e
marcata nel codice con `CUSTOM(<id>)`. Se una personalizzazione si ripete, proponi di portarla nel modello.

## Dove va il codice scritto a mano
| Esigenza | Dove |
|---|---|
| Reazione `custom` del modello (`handler: x`) | nuova migrazione con `create or replace function public.custom_x(p_event public.events)` |
| Regola di dominio non esprimibile come guard/condition | funzione SQL in una nuova migrazione, usata da un trigger o da una RPC |
| Evento di dominio emesso dal codice | `perform public.emit_entity_event('<entità>', id, '<entità>.<evento>', extra)`; l'evento va dichiarato in `app.yaml` |
| Vista diversa per un'entità (calendario, bacheca, schede, pannelli correlati, widget) | `ui` dell'entità in `app.yaml` (`appforge ui suggest`) |
| Pagina personalizzata per un'entità | `src/app/(app)/x/<entità>/...` (le pagine generiche restano in `/e/[entity]`) |
| Integrazione esterna (email, API) | sottoscrittore webhook (n8n): mai chiamate di rete dal database |

## Architettura
Vedi `docs/architecture.md` e `docs/domain.md` (generato). In breve:
- **Postgres/Supabase** è il cervello: RLS su ogni tabella, permessi come relazioni (`<entità>_principals`), workflow
  (`<entità>_perform_transition`), eventi nella stessa transazione (`emit_event` → `events`), reazioni interne
  (`react_to_event`), job `pg_cron` (transizioni a tempo, solleciti, eventi pianificati).
- **Next.js** (`src/`) usa Supabase come utente loggato: l'autorizzazione è sempre nel database.
- **Dispatcher** (`worker/dispatcher.ts`) consegna gli eventi ai webhook (CloudEvents + Standard Webhooks, at-least-once).

## Convenzioni
- Next.js 16: `src/proxy.ts` (non middleware); `params`/`searchParams`/`cookies()` sono async.
- UI multilingua (next-intl): ogni testo in tutti i file `messages/*.json` con le stesse chiavi (test `tests/i18n.test.ts`).
- Nuovi `raise exception` in SQL: mappali in `src/lib/db-errors.ts` e traducili in `errors.*`.
- Dopo modifiche allo schema: `supabase db reset`, `npm run db:types`, `npm test`, `npm run typecheck`.

## Comandi
```bash
supabase start && supabase db reset   # database locale con tutte le migrazioni
npm run dev                            # http://localhost:3000
npm run worker:dev                     # dispatcher dei webhook
npm test && npm run typecheck && npm run lint && npm run check:model
```
