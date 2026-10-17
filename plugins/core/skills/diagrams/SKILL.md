---
name: diagrams
description: Regole per costruire o modificare editor e diagrammi di modelli (metamodelli, workflow, grafi di stati, diagrammi a nodi e connettori) - layout che riempie il contenitore, layout come funzione pura testata, connettori ortogonali non sovrapposti, bus per molte sorgenti, etichette leggibili, evidenziazione al passaggio del mouse. Va usata ogni volta che si crea o si cambia un diagramma o un editor grafico di un modello, anche se l'utente chiede solo "rendilo più leggibile" o "i connettori si sovrappongono".
---

# Editor e diagrammi di modelli

Si applicano a ogni diagramma a nodi e connettori: l'editor del metamodello (`plugins/modeler/kit/metamodel-editor.js`),
i diagrammi di workflow delle app, grafi di stati. Riferimento d'implementazione: `src/lib/workflow-layout.ts` e
`tests/workflow-layout.test.ts` di guest-invitations-af; lo stesso algoritmo, portato in JavaScript, è `Layout.workflowLayout`
in `plugins/modeler/kit/metamodel-editor.js` (il satellite «workflow» dell'editor del metamodello), con i test in
`plugins/modeler/tests/layout.test.mjs`.

## Spazio
- Il layout riempie il contenitore: misuralo (`ResizeObserver`) e ingrandisci gli elementi fino a un massimo.
  Sotto una larghezza minima (la parola più lunga dei nomi) il diagramma scorre invece di stringersi.
- Si riadatta quando il contenitore cambia, finché l'utente non fa zoom o spostamenti a mano; un comando
  "Adatta" lo riporta all'adattamento automatico.

## Layout testabile
- Il layout è una funzione pura (`layout(nodi, archi, larghezza)` → posizioni e percorsi), separata dal disegno.
- Test (vitest, o il framework del progetto) su un modello reale del progetto che verificano: nessun nodo
  sovrapposto; nessuna coppia di connettori con un tratto collineare in comune; nessun connettore che attraversa un
  nodo; etichette che non coprono nodi né altre etichette.

## Connettori
- Ortogonali, con angoli arrotondati; ognuno con la propria corsia tra le colonne e tra le righe.
- Ogni connettore ha il proprio punto di attacco sul lato del nodo, ordinato secondo la posizione dell'altro capo;
  le porte in entrata sono sfalsate di qualche px rispetto a quelle in uscita.
- Molte sorgenti verso lo stesso nodo (es. "annulla" da ogni stato): un **bus**, cioè un tronco con una sola
  freccia e una sola etichetta; il nodo di destinazione va su una riga a parte.
- Ben visibili: tratto ~1.75px, opacità alta, colore della destinazione. La forma delle estremità segue la notazione
  del modello quando ne ha una: in un metamodello EMF freccia aperta per i riferimenti, rombo pieno sul contenitore,
  triangolo vuoto sul supertipo; altrove punta della freccia piena.

## Etichette e interazione
- Le etichette sono disegnate sopra tutte le linee, con uno sfondo, nella posizione scelta tra più candidate che
  non copre nodi, altre etichette o altri connettori.
- Il passaggio del mouse su un connettore o sulla sua etichetta lo evidenzia e attenua gli altri.

## Verifica
Oltre ai test del layout, una prova nel browser (anche headless) a due risoluzioni con un modello reale:
nessun errore, nessuna sovrapposizione, screenshot da mostrare all'utente.
