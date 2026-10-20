---
name: ship
description: Pubblica il branch corrente fino a main in modo controllato - controlli del progetto, push del branch, pull request con titolo e corpo dai Conventional Commits, attesa della CI, poi merge su main solo dopo conferma esplicita. Usala quando l'utente chiede di "aprire la PR", "fare il merge su main", "spedire il branch" o invoca /core:ship.
argument-hint: "[--no-merge] [--squash|--merge]"
disable-model-invocation: true
---

# Ship: branch → pull request → main

Argomenti: `$ARGUMENTS` (`--no-merge`: fermati dopo la CI; `--squash`/`--merge`: tipo di merge, default `--squash`).

Invocare `/core:ship` vale come richiesta esplicita di **push del branch e apertura della PR**, non del merge:
il merge su `main` chiede sempre una conferma a parte (l'hook di `core` chiederà comunque conferma per `git push`
e `gh pr merge`: è voluto).

## 1. Precondizioni (fermati se una manca e spiega cosa fare)
- Branch corrente diverso da `main`/`master` (e dal default branch del remoto).
- Nessuna modifica non committata (`git status --porcelain`): altrimenti proponi `/core:commit`.
- `gh auth status` ok. Se `gh` manca o non è autenticato, suggerisci `! brew install gh && gh auth login`.
- Il branch ha commit rispetto a `main` (`git log --oneline origin/main..HEAD` dopo `git fetch`); se `main` remoto è
  avanzato, segnalalo e proponi di aggiornare il branch prima di proseguire (merge o rebase solo su richiesta).

## 2. Controlli del progetto
- Test, lint e typecheck che il `CLAUDE.md` del progetto prevede. Se falliscono, non pubblicare: riporta l'errore.
- Se il repository ha `scripts/release.py` (repository harness): `python3 scripts/release.py`, poi `--write`, che crea
  il commit `chore(release): …`. Senza, il pre-push blocca.
- App con Supabase cloud collegato (`supabase/.temp/project-ref`): `supabase migration list --linked`. Se il branch
  porta migrazioni non ancora remote, esegui qui i punti 2-4 della skill `core:db-push` (pre-controlli, elenco,
  rischi) e chiedi **una sola conferma** «migrazioni in produzione + push e PR»; con il sì applica le migrazioni
  (`supabase db push`) e prosegui. Prima il database, poi il codice: non pubblicare codice che usa migrazioni non
  ancora applicate.

## 3. Push e pull request
- Mostra in un blocco ```text l'elenco `git log --oneline origin/main..HEAD`: è ciò che verrà pubblicato.
- `git push -u origin <branch>`.
- Se esiste già una PR per il branch (`gh pr view --json url`), usala; altrimenti `gh pr create --base main`:
  - titolo: il commit principale del branch (Conventional Commits, in inglese), o una sintesi se sono più temi;
  - corpo: perché, cosa cambia (un punto per commit significativo), come è stato verificato, righe di attribuzione
    se il repository le prevede. Passalo con `--body-file -` via heredoc.
- Mostra il link della PR.

## 4. CI
- `gh pr checks --watch --fail-fast`. Se il repository non ha controlli, dillo (nessuna CI su cui contare).
- Se un controllo fallisce: fermati, mostra il nome e il link del job (`gh run view <id> --log-failed` per i
  dettagli) e proponi l'agente `core:debugger`. Niente merge.
- Con `--no-merge`, fermati qui.

## 5. Merge (solo dopo conferma)
- Riassumi: PR, controlli verdi, commit che entrano in `main`, e se l'app ha un deploy automatico su `main`
  (GitHub Actions, Watchtower): il merge lo avvia.
- Chiedi la conferma con AskUserQuestion (merge / non ora). Senza un sì esplicito non fare il merge. (In un'app
  con il modellatore la PR di una proposta può essere rilasciata dall'admin con «Conferma e rilascia» in
  `/admin/model`: il workflow `modeler-release` fa questi stessi passi; se la PR è già in rilascio, non unirla a mano.)
- `gh pr merge <n> --squash --delete-branch` (o `--merge` se richiesto), poi `git switch main && git pull --ff-only`.
- Se l'app ha migrazioni nuove non ancora in produzione, ricorda `/core:db-push` prima del merge, non dopo.
- Nel resoconto, per ciò che resta da fare sul server (variabili del pannello, proxy host, rollback, Watchtower che
  non aggiorna) rimanda ai passi della skill `core:deploy` e al `docs/deploy.md` dell'app: non inventare
  istruzioni SSH o un `.env` da copiare.
- Se il merge avvia il primo deploy, o la PR tocca Auth, dominio o infrastruttura (proxy, compose, workflow),
  proponi `/core:security-audit` appena la produzione è aggiornata.
- App con un workflow di deploy su `main`: attendi il run **dello SHA del merge**, non l'ultimo run (quello del merge
  precedente, o un run ancora in coda, inganna `gh run watch`): `sha=$(git rev-parse origin/main)`, poi in polling
  ogni 30 s per al massimo 15 min `gh run list --commit "$sha" --json databaseId,name,status,conclusion,url` finché
  ogni run è `completed`; riporta esito e link; un run `failure` → `gh run view <id> --log-failed`, niente altro.
- App con il modellatore: se `.modeler/proposals/applied/` contiene proposte arrivate da produzione (file con `id`)
  non ancora chiuse (senza `closed`), proponi `npm run model:done` (prova a vuoto, poi `--write`), come dice la
  skill `modeler:apply` punto 6.
- Se `HANDOFF.md` esiste ed è più vecchio dell'ultimo merge (`git log -1 --format=%ct -- HANDOFF.md` contro il
  commit di merge), proponi `/core:handoff`.

## Non fare
- Merge senza conferma, `gh pr merge --admin`, `--no-verify`, `git push --force`, merge di PR altrui.

Alla fine: link della PR, esito della CI, stato del merge e branch corrente, in poche righe.
