# Note per l'harness

Lezioni annotate con `/core:harness-note`, da rivedere e applicare al plugin core.

## 2026-10-14 — modeler install: ignorare il bytecode Python nell'app
- **Progetto**: guest-invitations-af
- **Cosa è successo**: la CLI copiata in `tools/modeler/` genera `__pycache__/` quando gira dentro l'app (`npm run model:*`); l'app non lo ignorava e i `.pyc` sono finiti in un commit. L'installer già salta `__pycache__` quando copia, ma non protegge l'app dopo.
- **Proposta**: `modeler install` aggiunge `__pycache__/` (o `tools/modeler/**/__pycache__/`) al `.gitignore` dell'app se manca, come fa la skill per `.modeler/proposals/`; un test in `test_modeler.py` lo verifica, e il passo 4 della skill install lo cita.
- **Plugin**: modeler
- **Tipo**: skill

## 2026-10-14 — Automatizzare pull request e merge su main dopo conferma
- **Progetto**: guest-invitations-af (con iovino-harness)
- **Cosa è successo**: dopo il push di un branch `feat/…` la PR va aperta a mano dal browser (sul computer manca `gh`) e il merge su `main` va fatto a parte, in due repository; il controllo della CI resta manuale.
- **Proposta**: una skill `core:ship` (o `core:pr`) che, dopo i controlli del progetto, fa push del branch, apre la PR (titolo e corpo dai Conventional Commits, con l'attribuzione), aspetta l'esito della CI e la mostra, poi **chiede conferma esplicita** e solo allora fa il merge su `main` (e cancella il branch). Prerequisito: `gh` installato e autenticato (`! brew install gh && gh auth login`), o in alternativa l'API GitHub. Regola in `conventions.md`: il merge su `main` di un'app con deploy automatico richiede sempre la conferma, anche se la PR l'ha aperta Claude; per l'harness ricordare `release.py --write` prima del push.
- **Plugin**: core
- **Tipo**: skill

## 2026-10-14 — Editor e diagrammi di modellazione: modello leggibile, connettori non sovrapposti
- **Progetto**: guest-invitations-af (diagramma del workflow in `/admin/workflows/[id]`; vale anche per l'editor del metamodello)
- **Cosa è successo**: il diagramma aveva dimensioni fisse (più largo della pagina, con scroll) e connettori Bézier semitrasparenti sovrapposti: una transizione con 7 sorgenti verso uno stato finale disegnava 7 curve una sull'altra, e le etichette erano illeggibili. L'utente ha chiesto elementi che occupano tutto il contenitore e connettori non sovrapposti.
- **Proposta**: aggiungere a `conventions.md` (o a una skill/riferimento per editor e diagrammi di modelli) queste indicazioni, da applicare ogni volta che si crea o si modifica un editor o un diagramma di modellazione:
  - il layout riempie il contenitore: lo misura (ResizeObserver) e allarga gli elementi fino a un massimo. Sotto una larghezza minima, cioè la parola più lunga dei nomi, scorre invece di stringersi;
  - il layout è una funzione pura (`layout(nodi, archi, larghezza)`), testata con vitest su un modello reale del progetto: niente nodi sovrapposti, nessuna coppia di connettori con un tratto collineare in comune, nessun connettore che attraversa un nodo, etichette che non coprono nodi né altre etichette;
  - i connettori sono ortogonali, con angoli arrotondati, e ognuno ha la propria corsia tra le colonne e tra le righe. Ogni connettore ha il proprio punto di attacco sul lato del nodo, ordinato in base a dove sta l'altro capo; le porte in entrata sono sfalsate di qualche px rispetto a quelle in uscita;
  - un arco con molte sorgenti verso lo stesso nodo (es. "annulla" da ogni stato) diventa un bus (un tronco, una sola freccia e una sola etichetta), e il nodo di destinazione va su una riga a parte;
  - i connettori sono ben visibili (tratto ~1.75px, opacità alta, colore della destinazione, punta della freccia piena). Le etichette sono disegnate sopra tutte le linee, su uno sfondo, e posizionate cercando tra più candidati quello che non copre nodi, etichette o altri connettori;
  - l'hover su un connettore o sulla sua etichetta lo evidenzia e attenua gli altri.
  Riferimento d'implementazione: `src/lib/workflow-layout.ts` e `tests/workflow-layout.test.ts` di guest-invitations-af. Valutare di portare le stesse regole nell'editor del metamodello (`kit/metamodel-editor.js`).
- **Plugin**: core (convenzione) + modeler (editor del metamodello)
- **Tipo**: convenzione
