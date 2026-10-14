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
