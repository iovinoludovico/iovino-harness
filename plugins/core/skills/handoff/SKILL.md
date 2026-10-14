---
name: handoff
description: Scrive o aggiorna HANDOFF.md con lo stato del lavoro, così una sessione successiva (su questo o un altro computer) può riprendere senza perdere contesto. Usala a fine sessione, prima di un cambio di macchina, quando il contesto sta per esaurirsi o quando l'utente dice "passami le consegne" / "genera l'handoff".
argument-hint: "[focus o prossimo obiettivo]"
---

# Handoff di fine sessione

Scrivi `HANDOFF.md` alla radice del repository (o della cartella di lavoro se non è un repo). Se esiste già, **sostituisci** lo stato vecchio con quello attuale: l'handoff descrive il presente, non è un diario. La storia sta in git.

## Raccogli

- `git status --short`, `git branch --show-current`, `git log --oneline -10`, `git diff --stat`.
- Cosa è stato fatto in questa sessione e cosa è stato verificato (test eseguiti, esito).
- Decisioni prese e **perché**, alternative scartate.
- Problemi aperti, errori non risolti con il messaggio esatto, ipotesi in corso.
- Comandi necessari per riprendere (avvio, test, servizi da accendere).

Focus indicato dall'utente: $ARGUMENTS

## Formato

```markdown
# Handoff — <titolo breve del lavoro>
_Aggiornato: <data> · branch `<branch>`_

## Obiettivo
<cosa si sta cercando di ottenere, 2–3 righe>

## Stato
- Fatto: …
- Verificato: <comando> → <esito>
- Non committato: <file o "nulla">

## Decisioni
- <decisione> — <motivo>

## Problemi aperti
- <problema> — <errore esatto / ipotesi>

## Prossimi passi
1. <azione concreta e verificabile>
2. …

## Per riprendere
`<comandi>`  
File da leggere per primi: <percorsi>
```

Sii specifico: percorsi di file, nomi di funzioni, comandi esatti. Niente frasi generiche come "continuare l'implementazione".

## Dopo

- Se in sessione è emersa una lezione utile per **tutti** i progetti (un errore ricorrente, una convenzione mancante), proponi `/core:harness-note`.
- Chiedi se HANDOFF.md va committato: in alcuni progetti è in `.gitignore`. Non committare senza conferma.
