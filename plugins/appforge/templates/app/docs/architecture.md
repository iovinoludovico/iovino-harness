# Architettura

## Componenti

| Componente | Ruolo |
|---|---|
| **Next.js** (`src/`) | UI e Server Actions. Usa Supabase come utente loggato: le autorizzazioni sono applicate dal database (RLS). Le pagine generiche `/e/[entity]` leggono il metamodello generato (`src/lib/model.ts`). |
| **Supabase Postgres** (`supabase/migrations`) | Dati, permessi (RLS), motore di workflow, outbox degli eventi, reazioni, job `pg_cron`. |
| **Supabase Auth** | Login (Google e/o link email); hook *Before User Created* che rifiuta i domini non ammessi. |
| **Dispatcher** (`worker/dispatcher.ts`) | Processo separato che consegna gli eventi ai webhook sottoscritti. |
| **n8n / altri** (esterni) | Sottoscrittori: ricevono gli eventi e fanno gli effetti esterni (email, API). |

## Livelli generati
Il generatore produce tre livelli di SQL con regole di evoluzione diverse:
1. **core** (prima migrazione): utenti, ruoli, hook di auth, outbox, webhook, tabelle di servizio.
2. **struttura**: enum, tabelle, riferimenti. Le evoluzioni additive sono generate; quelle distruttive o ambigue
   (rimozioni, rinomine, cambi di tipo) producono una migrazione `*_manual_evolve_N.sql` da completare a mano.
3. **comportamento**: funzioni, trigger, policy, catalogo eventi, cron. Idempotente, rigenerato per intero a ogni evoluzione.

## Permessi come relazioni
Per ogni entità `<e>_principals(riga)` calcola le relazioni dell'utente con la riga: `all`, `admin`, `creator`,
i ruoli (quelli con ambito valgono solo nell'ambito della riga) e `field:<campo>` per i riferimenti a utenti.
`<e>_can(azione, riga)` confronta queste relazioni con i permessi del modello; le policy RLS lo usano.

## Workflow
Lo stato cambia **solo** con `perform_transition(entità, id, transizione, commento)`: controlla chi può, le
condizioni (`condition`, nascondono l'azione) e i requisiti (`guard`, la bloccano spiegando cosa manca), scrive lo
storico (`record_history`) ed emette `<e>.transitioned` (+ `<e>.completed` negli stati finali). Le transizioni
`trigger: {at, offset}` sono eseguite da `run_timed_transitions()` (pg_cron, 01:00); i solleciti degli stati da
`run_state_reminders()` (07:00).

## Event-driven: Transactional Outbox + Pub/Sub via webhook

```
 Server Action / pg_cron
          │
          ▼
 perform_transition() ──┐   (una transazione Postgres)
 insert/update/delete ──┼──► <e>_emit() ──► emit_event() ──► events (outbox, append-only)
                        │                                      │ trigger react_to_event(): reazioni interne
                        │                                      │ trigger fan_out_event()
                        │                                      ▼
                        │                              webhook_deliveries ──NOTIFY──┐
                        ▼                                                           ▼
                   commit                                        Dispatcher (LISTEN + poll)
                                                                 firma, POST, retry, dead-letter
```

- L'evento è scritto nella stessa transazione della modifica: esiste se e solo se la modifica è confermata.
- Reazioni (`reactions` del modello): `notify` calcola i destinatari e li mette nell'evento (`data.recipients`:
  email, lingua, `template_key`), il sottoscrittore sceglie solo il template; `set`, `transition`, `schedule`,
  `broadcast`, `custom` vengono eseguite nella stessa transazione da `react_to_event()`.
- Consegna **at-least-once**: il destinatario deduplica con `webhook-id` (= id dell'evento).
- Envelope CloudEvents 1.0; firma Standard Webhooks (`webhook-id`, `webhook-timestamp`, `webhook-signature`),
  opzionale autenticazione Basic. Retry dopo 1m, 5m, 30m, 2h, 12h, 24h (±10%), poi `dead`.
- `broadcast` pubblica su Supabase Realtime (solo tipo e id: i dati si rileggono con RLS).
