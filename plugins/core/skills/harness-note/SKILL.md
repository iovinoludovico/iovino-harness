---
name: harness-note
description: Annota nel repository harness una lezione appresa durante il lavoro (errore ricorrente di Claude, convenzione mancante, guardrail da aggiungere, idea per una skill), così da migliorare nel tempo i plugin dell'harness (core, modeler). Usala quando l'utente dice "annotalo per l'harness", "ricordatelo per la prossima volta in tutti i progetti", o a fine sessione se è emerso qualcosa di generale.
argument-hint: "<la lezione in poche parole>"
---

# Nota per l'harness

Lezione indicata dall'utente: $ARGUMENTS

## Dove scrivere

Nell'ordine, il primo che esiste:

1. Il percorso dato dall'inizio sessione, riga «Note dell'harness (`/core:harness-note`): `<clone>/NOTES.md`».
2. Il repository harness configurato: `${user_config.harness_repo}`. Vale solo se è il percorso di una cartella che
   esiste: un valore vuoto, o il segnaposto rimasto letterale (`${user_config…}`), significa che l'opzione non è
   impostata su questo computer.
3. Un clone sul computer: `ls -d ~/Documents/GitHub/*/.claude-plugin/marketplace.json` e, tra i risultati, la
   cartella che ha anche `plugins/core` (di solito `~/Documents/GitHub/iovino-harness`). Scrivi lì e di' all'utente
   di impostare l'opzione: `/plugin` → `core` → configurazione, `harness_repo` = quel percorso.
4. Solo se sul computer non c'è nessun clone: il file di riserva `${CLAUDE_PLUGIN_DATA}/NOTES.md`. Dillo **in
   evidenza, come prima riga del resoconto** («Nota scritta nel file di riserva, non nel repository harness»): le
   note lì non sono contate dall'avviso di inizio sessione del repository e vanno importate con
   `/core:harness-review` (o portate a mano) quando il clone c'è.

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

## Committa la nota nel clone

Scritta la voce nel `NOTES.md` di un clone (casi 1-3), committala subito, così non resta una modifica sparsa che si
mescola al branch di una revisione e si vede quando è arrivata:

- `git -C <clone> branch --show-current`: solo se è `main`. Su un altro branch (una revisione in corso) lascia la
  nota non committata e dillo.
- `git -C <clone> commit NOTES.md -m "docs(notes): <titolo breve in inglese>"`: il commit contiene **solo**
  `NOTES.md`, anche se il clone ha altre modifiche (non usare `git add -A` né `commit -a`).
- **Mai `git push`** dal progetto in cui stai lavorando: l'inizio sessione avvisa delle note committate e non
  pubblicate, e il push si fa su richiesta dell'utente.

## Regole

- Una voce per lezione, niente duplicati: leggi prima il file e, se una voce simile esiste, aggiornala aggiungendo il nuovo caso.
- Niente dati riservati del progetto (segreti, nomi di clienti, dati personali): la nota deve essere generale.
- Non modificare direttamente `conventions.md`, gli hook o le skill dei plugin: le note si rivedono e si applicano in una sessione dedicata dentro il repository harness, con `/core:harness-review`. L'unico commit che fai lì è quello della nota (sezione sopra). (L'hook di `core` chiede conferma se una sessione aperta altrove modifica il clone dell'harness.)
- Se il problema blocca il lavoro in corso, dopo la nota suggerisci di correggerlo subito in una seconda sessione aperta nel repository harness (`cd ${user_config.harness_repo} && claude`, poi una correzione diretta con release e `/core:ship`); qui, dopo il rilascio, `/reload-plugins` (e `/modeler:install` se la correzione riguarda il modellatore installato nell'app). Nel frattempo, se possibile, aggira il problema a mano senza toccare l'harness.
