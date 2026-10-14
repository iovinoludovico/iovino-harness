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

## Lavoro sul codice
- Leggi `CLAUDE.md` e la documentazione del progetto prima di modificare; segui i pattern esistenti invece di introdurne di nuovi.
- Non dichiarare finito un lavoro senza averlo verificato: test, typecheck, build o un'esecuzione reale.
- Segreti mai nel repository: `.env*` restano locali, si versionano solo gli `.env.example`.
- Migrazioni del database append-only: mai modificare una migrazione già applicata.
- File generati (ad esempio da appforge) non si modificano a mano: si cambia la sorgente e si rigenera.

## Stack ricorrente
- Web: Next.js + Supabase (RLS, logica nel database), Docker, GitHub Actions → GHCR, deploy su VPS (Hostinger) con docker compose e Watchtower.
- Ricerca MDE: Eclipse/EMF, Epsilon (ETL, EOL, EVL), Java/Spring Boot, metamodelli Ecore/Emfatic.

## Fine sessione
- Per lavori lunghi o da riprendere altrove, aggiorna `HANDOFF.md` con la skill `core:handoff`.
- Se qualcosa è andato storto per una lacuna di queste regole, annotalo con `core:harness-note`.
