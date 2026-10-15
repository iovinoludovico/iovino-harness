# Convenzioni di lavoro di Ludovico (harness core)

## Comunicazione
- Rispondi in italiano; codice, identificatori, commenti nel codice e messaggi di commit in inglese.
- Sii conciso: risultato, cosa resta da fare, eventuali rischi. Niente riassunti dei passaggi.
- Se una decisione è irreversibile o ambigua (schema dati, deploy, cancellazioni), chiedi prima di procedere.

## Git
- Mai `push`, `push --force`, tag o release senza richiesta esplicita.
- Modifiche non banali su un branch dedicato (`feat/…`, `fix/…`); `main` resta deployabile.
- Commit piccoli, in Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`), con il perché nel corpo quando non è ovvio.
- Prima di committare: test e lint del progetto verdi.
- Il merge su `main` richiede sempre conferma esplicita, anche se la PR l'ha aperta Claude (su un'app con deploy automatico il merge è un rilascio); per push, PR, CI e merge usa `/core:ship`.
- Quando proponi di committare o di fare push, includi il messaggio di commit proposto in un blocco ```text copiabile: Conventional Commits in inglese, titolo di circa 72 caratteri al massimo, riga vuota, corpo con il perché, righe di attribuzione se il repository le prevede. Un blocco per commit; se i commit sono già fatti e proponi solo il push, mostra in un blocco l'elenco `git log --oneline` di ciò che verrebbe pubblicato.

## Sviluppo guidato dai modelli
- Queste regole valgono nei progetti che hanno un modello: `domain.ecore.yaml` o un altro modello dichiarato nel loro `CLAUDE.md`. Se il `CLAUDE.md` dice "Nessun modello", si sviluppa direttamente sul codice: non proporre il modellatore né il metamodello, salvo richiesta. In un progetto senza modello e senza questa indicazione, proponilo una sola volta (`/core:project-init` registra la scelta).
- Nei progetti con modello, il modello guida lo sviluppo: la struttura del dominio sta nel metamodello `domain.ecore.yaml` (notazione Ecore). Ogni modifica di schema parte dal metamodello e va, nella stessa modifica, con la migrazione e il codice che la usa; mai il contrario.
- Il metamodello resta allineato al database: `npm run model:drift` deve rispondere "aligned" (plugin `modeler`, che installa nell'app il modellatore web `/admin/model` e la CLI `tools/modeler/`).
- Prima di scrivere codice a mano verifica se il metamodello può esprimere la richiesta; se può, cambia il metamodello.
- Una tabella di lookup su più dimensioni (riferimenti o enum, con una riga di default come fallback) ha la combinazione unica nel metamodello (`unique` di classe, nulls not distinct) e si gestisce come matrice che mostra valori propri, ereditati dal default e mancanti, non riga per riga.
- Le personalizzazioni (ciò che il modello non esprime) sono ammesse solo se chiarite in modo esplicito:
  - registrate in `docs/customizations.md` con: identificativo, motivo per cui il modello non basta, elementi del modello coinvolti, file in cui vivono, come si verificano;
  - nel codice marcate con un commento `CUSTOM(<id>)` all'inizio del blocco;
  - se una personalizzazione diventa ricorrente, proponi di portarla nel metamodello o nel plugin (`core:harness-note`).
- Se una richiesta è ambigua tra modello e personalizzazione, chiedi prima di procedere.

## Lavoro sul codice
- Leggi `CLAUDE.md` e la documentazione del progetto prima di modificare; segui i pattern esistenti invece di introdurne di nuovi.
- Non dichiarare finito un lavoro senza averlo verificato: test, typecheck, build o un'esecuzione reale.
- Prima di dire in che stato è l'harness o un suo plugin (branch da unire, versione pubblicata, release da fare), esegui `git fetch --prune` e guarda `origin/main` (log, `version` in `plugin.json`): non riusare un controllo fatto prima nella sessione.
- Segreti mai nel repository: `.env*` restano locali, si versionano solo gli `.env.example`.
- Migrazioni del database append-only: mai modificare una migrazione già applicata.
- Migrazioni sul Supabase cloud solo con `/core:db-push` (controlli, conferma, verifica), prima del push del codice che le usa.
- Editor e diagrammi di modelli (nodi e connettori): segui la skill `core:diagrams` (layout che riempie il contenitore, layout come funzione pura con test, connettori ortogonali non sovrapposti, etichette leggibili).
- File generati non si modificano a mano: si cambia la sorgente e si rigenera. Il modellatore installato (`public/modeler/`, `src/components/modeler/`, `src/lib/modeler/metamodel-actions.ts`, `tools/modeler/`) si aggiorna con `/modeler:install`, non a mano.

## Stack ricorrente
- Web: Next.js + Supabase (RLS, logica nel database), Docker, GitHub Actions → GHCR, deploy su VPS (Hostinger) con docker compose e Watchtower.
- App model-based (plugin modeler): metamodello `domain.ecore.yaml` dal prompt (`/modeler:metamodel`) o dal database (`/modeler:install`); il modellatore web fa parte dell'app e salva proposte che si applicano con `/modeler:apply`.
- Ricerca MDE: Eclipse/EMF, Epsilon (ETL, EOL, EVL), Java/Spring Boot, metamodelli Ecore/Emfatic.

## Fine sessione
- Per lavori lunghi o da riprendere altrove, aggiorna `HANDOFF.md` con la skill `core:handoff`.
- Se qualcosa è andato storto per una lacuna di queste regole, annotalo con `core:harness-note`.
