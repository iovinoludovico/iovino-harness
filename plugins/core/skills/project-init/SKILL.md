---
name: project-init
description: Crea o aggiorna il CLAUDE.md di un repository a partire dalle convenzioni personali e dallo stack rilevato. Usala quando l'utente chiede di "inizializzare" un progetto per Claude, quando manca CLAUDE.md, o quando il CLAUDE.md esistente è scarno o datato.
argument-hint: "[note aggiuntive sul progetto]"
---

# Inizializza CLAUDE.md del progetto

Obiettivo: un CLAUDE.md **breve** (idealmente sotto le 80 righe) che dica a una sessione futura ciò che non può dedurre leggendo il codice. Le convenzioni generali arrivano già dal plugin core a ogni sessione: **non ricopiarle**, scrivi solo ciò che è specifico di questo repository.

## 1. Raccogli i fatti (senza chiedere ciò che puoi verificare)

- Struttura: `git ls-files | head -200`, cartelle principali, README.
- Comandi reali: script in `package.json`, `Makefile`, `pyproject.toml`, `pom.xml`, workflow in `.github/workflows/`. Annota solo comandi che esistono davvero; se puoi, eseguine uno veloce (lint o type-check) per confermarlo.
- Stack e versioni: Next.js, Supabase (`supabase/config.toml`, cartella `supabase/migrations`), Docker/Compose, Java/Maven, EMF/Epsilon.
- Variabili d'ambiente: nomi da `.env.example` (mai leggere `.env`).
- Deploy: Dockerfile, compose, GHCR, Watchtower, script di deploy.
- Se c'è un `app.yaml` di appforge, segnala che il codice generato non va modificato a mano e che le modifiche al dominio passano dal modello.
- Se esiste già un CLAUDE.md, leggilo: va **aggiornato** conservando ciò che l'utente ha scritto, non riscritto da zero.

Argomenti dell'utente: $ARGUMENTS

## 2. Scrivi CLAUDE.md alla radice del repository

Struttura suggerita, omettendo le sezioni vuote:

```markdown
# <Nome progetto>

<Una o due frasi: cosa fa e per chi.>

## Comandi
- Avvio locale: `…`
- Test: `…`
- Lint / type-check: `…`
- Migrazioni DB: `…`

## Architettura
<5–10 righe: cartelle chiave e responsabilità, flusso principale dei dati.>

## Regole specifiche del progetto
- <vincoli non deducibili dal codice: file generati, migrazioni, servizi esterni, dati sensibili>

## Ambiente
- Variabili richieste (vedi .env.example): `…`
- Deploy: <come e dove>
```

Regole di scrittura: frasi imperative e concrete, comandi copiabili, nessuna ovvietà ("scrivi codice pulito"), nessun segreto.

## 3. Chiudi

Mostra all'utente il file (o il diff se esisteva già) e chiedi se aggiungere qualcosa che solo lui sa: decisioni architetturali, cose da non toccare, persone di riferimento. Non committare: se l'utente vuole, usa `/core:commit`.
