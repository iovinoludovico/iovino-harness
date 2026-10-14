---
name: harness-note
description: Annota nel repository harness una lezione appresa durante il lavoro (errore ricorrente di Claude, convenzione mancante, guardrail da aggiungere, idea per una skill), così da migliorare nel tempo i plugin dell'harness (core, modeler). Usala quando l'utente dice "annotalo per l'harness", "ricordatelo per la prossima volta in tutti i progetti", o a fine sessione se è emerso qualcosa di generale.
argument-hint: "<la lezione in poche parole>"
---

# Nota per l'harness

Lezione indicata dall'utente: $ARGUMENTS

## Dove scrivere

- Repository harness configurato: `${user_config.harness_repo}`
- Se il valore sopra è vuoto o la cartella non esiste su questo computer, usa il file di riserva `${CLAUDE_PLUGIN_DATA}/NOTES.md` e dillo all'utente: potrà spostare le note nel repository più tardi (o configurare la cartella con `/config`).

Il file è `NOTES.md` alla radice del repository harness. Crealo se non esiste, con il titolo `# Note per l'harness`.

## Cosa scrivere

Aggiungi in fondo una voce con questo formato:

```markdown
## <AAAA-MM-GG> — <titolo breve>
- **Progetto**: <nome della cartella o del repo in cui è emersa>
- **Cosa è successo**: <fatto concreto, 1–2 righe>
- **Proposta**: <modifica concreta: riga da aggiungere a conventions.md, regola di guard, nuova skill, modifica a una skill esistente>
- **Plugin**: core | modeler | nuovo
- **Tipo**: convenzione | guardrail | skill | agente | altro
- **Stato**: da valutare
```

La riga **Stato** la aggiorna `/core:harness-review` quando la nota viene applicata, scartata o rinviata.

Se l'utente non ha dato una lezione esplicita, ricavala dalla sessione e mostrala prima di scriverla.

## Regole

- Una voce per lezione, niente duplicati: leggi prima il file e, se una voce simile esiste, aggiornala aggiungendo il nuovo caso.
- Niente dati riservati del progetto (segreti, nomi di clienti, dati personali): la nota deve essere generale.
- Non modificare direttamente `conventions.md`, gli hook o le skill dei plugin: le note si rivedono e si applicano in una sessione dedicata dentro il repository harness, con `/core:harness-review`. Non committare lì senza richiesta.
