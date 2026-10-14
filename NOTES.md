# Note per l'harness

Lezioni annotate con `/core:harness-note`, da rivedere e applicare al plugin core.

## 2026-10-14 — modeler install: ignorare il bytecode Python nell'app
- **Progetto**: guest-invitations-af
- **Cosa è successo**: la CLI copiata in `tools/modeler/` genera `__pycache__/` quando gira dentro l'app (`npm run model:*`); l'app non lo ignorava e i `.pyc` sono finiti in un commit. L'installer già salta `__pycache__` quando copia, ma non protegge l'app dopo.
- **Proposta**: `modeler install` aggiunge `__pycache__/` (o `tools/modeler/**/__pycache__/`) al `.gitignore` dell'app se manca, come fa la skill per `.modeler/proposals/`; un test in `test_modeler.py` lo verifica, e il passo 4 della skill install lo cita.
- **Plugin**: modeler
- **Tipo**: skill
